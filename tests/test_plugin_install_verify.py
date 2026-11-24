"""Every refusal the install chain claims, planted as bytes on disk.

A checker that refuses nothing is not built, and one that lets nothing through is
not built either, so each test here writes a real fault — forged signature bytes, a
listing hash over different bytes, a key inside the artifact, a bundle under another
version than the catalog says — and demands the refusal by code and reason. The
honest installs in the same file are the other half: an artifact that carries a
verifiable record installs, and the answer names the key that answered for it.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import ephe_cli  # noqa: E402
from core import (  # noqa: E402
    marketplace_planner,
    marketplace_service,
    marketplace_sources,
    plugin_install,
    plugin_signing,
)
from core.plugin_store import sha256_hex  # noqa: E402

FORGED = "00" * 32


def _manifest(name: str, version: str, *, tool_families: list[str] | None = None) -> dict:
    return {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "description": f"{name} {version}",
        "permissions": {"tool_families": tool_families or [], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": []},
        "engines": {"ephe": ">=0.1.0"},
    }


def _tree(
    root: Path,
    name: str,
    version: str,
    *,
    extra: dict[str, str] | None = None,
    tool_families: list[str] | None = None,
) -> Path:
    """A bundle directory as a publisher would ship it, plus planted files."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(_manifest(name, version, tool_families=tool_families)), encoding="utf-8"
    )
    (directory / "NOTES.md").write_text(f"{name} {version}\n", encoding="utf-8")
    for rel, text in (extra or {}).items():
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return directory


def _zip_dir(directory: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(directory.parent))
    return buf.getvalue()


def _signed_tree(
    root: Path,
    name: str,
    version: str,
    *,
    kid: str = "publisher",
    extra: dict[str, str] | None = None,
    tool_families: list[str] | None = None,
) -> tuple[bytes, dict, bytes]:
    """(artifact bytes, signature record, public PEM) from a key the test holds."""
    private, public = plugin_signing.generate_keypair()
    directory = _tree(root, name, version, extra=extra, tool_families=tool_families)
    record = plugin_signing.sign_plugin_dir(directory, private, kid=kid)
    return _zip_dir(directory), record, public


def _listing_entry(
    name: str,
    version: str,
    payload: bytes,
    *,
    trust: str,
    signature: dict | None = None,
    sha256: str | None = None,
    extra: dict | None = None,
) -> dict:
    entry = {
        "name": name,
        "version": version,
        "sha256": sha256 if sha256 is not None else sha256_hex(payload),
        "url": f"https://market.example.invalid/{name}-{version}.zip",
        "description": f"{name} {version}",
        "tags": [],
        "trust": trust,
    }
    if signature is not None:
        entry["signature"] = signature
    entry.update(extra or {})
    return entry


def _install(entry: dict, payload: bytes, **kwargs) -> dict:
    return plugin_install.install_from_marketplace(
        str(entry["name"]),
        marketplace={"plugins": [entry]},
        fetcher=lambda url: payload,
        **kwargs,
    )


def _zip_names(payload: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        return archive.namelist()


def _tree_state(root: Path) -> dict[str, str]:
    if not root.is_dir():
        return {}
    return {
        str(path.relative_to(root)): sha256_hex(path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def device(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    from core import audit_log, plugin_runtime

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    monkeypatch.setattr(plugin_signing, "TRUSTED_KEYS_LOADER", None)
    plugin_runtime.invalidate_ownership_cache()
    yield cfg
    plugin_runtime.invalidate_ownership_cache()


def _publish_user_key(cfg: Path, public: bytes, name: str = "publisher.pub.pem") -> Path:
    """A key of the operator's own, placed where a key belongs."""
    folder = cfg / "trusted-keys"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    target.write_bytes(public)
    return target


def _v2_index(root: Path, versions: list[dict], *, trust: str = "local") -> Path:
    index = {
        "format": 2,
        "name": "test-index",
        "owner": {"name": "Test"},
        "plugins": [
            {
                "name": "alpha",
                "displayName": "Alpha",
                "description": {"en": "Alpha plugin"},
                "publisher": {"name": "Test"},
                "trust": trust,
                "categories": ["code"],
                "versions": versions,
            }
        ],
    }
    path = root / "index.json"
    path.write_text(json.dumps(index), encoding="utf-8")
    return path


def _v2_version(
    version: str, artifact: Path, digest: str, *, signature: dict | None = None,
    tool_families: list[str] | None = None,
) -> dict:
    block = {
        "version": version,
        "publishTimestamp": 1790000000,
        "source": {"type": "zip", "url": f"artifacts/{artifact.name}", "sha256": digest},
        "engines": {"ephe": ">=0.1.0"},
        "permissions": {"tool_families": tool_families or [], "data_roots": []},
        "components": [],
    }
    if signature is not None:
        block["source"]["signature"] = signature
    return block


def _run_cli(argv: list[str], capsys) -> tuple[int, str, str]:
    code = ephe_cli.cmd_plugin(ephe_cli.build_parser().parse_args(list(argv)))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _local_source(tmp_path, monkeypatch, index: Path) -> dict:
    monkeypatch.setattr(marketplace_sources, "_home_root", lambda: tmp_path)
    return marketplace_sources.add_source("local", "Test source", str(index))


def _write_artifact(directory: Path, name: str, version: str, payload: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}-{version}.zip"
    path.write_bytes(payload)
    return path


def test_an_untrusted_signature_installs_nothing(device, tmp_path) -> None:
    """A record from a key nobody trusts is refused while the staging directory
    still holds the bytes, so the plugins root never sees them."""
    payload, record, _public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")

    result = _install(_listing_entry("my-tool", "1.2.3", payload, trust="official", signature=record), payload)

    assert result["status"] == "quarantined", result
    assert result["code"] == "signature_invalid", result
    assert "not from a trusted key" in result["reason"], result
    assert result["kid"] == "publisher", result
    assert not (device / "plugins" / "my-tool").exists()
    assert not list((device / "plugins").glob("*staging*"))


def test_a_key_inside_the_artifact_is_never_the_key_that_answers(device, tmp_path) -> None:
    """Criterion: the key a signature is checked against comes from the keyring.

    The artifact is signed by the key whose public half it also carries, so the
    signature is arithmetically valid for that key and the install still has to
    refuse — a bundle that ships its own judge proves nothing."""
    private, public = plugin_signing.generate_keypair()
    directory = _tree(
        tmp_path / "src",
        "my-tool",
        "1.2.3",
        extra={
            "first-party.pub.pem": public.decode("utf-8"),
            "trusted-keys/planted.pub.pem": public.decode("utf-8"),
        },
    )
    record = plugin_signing.sign_plugin_dir(directory, private, kid="publisher")
    payload = _zip_dir(directory)

    assert "my-tool/trusted-keys/planted.pub.pem" in _zip_names(payload)
    result = _install(_listing_entry("my-tool", "1.2.3", payload, trust="official", signature=record), payload)

    assert result["status"] == "quarantined", result
    assert "not from a trusted key" in result["reason"], result
    assert not (device / "plugins" / "my-tool").exists()


def test_a_key_offered_by_the_listing_is_never_the_key_that_answers(device, tmp_path) -> None:
    """The catalog entry is allowed to carry a signature record and nothing else
    that decides trust; the keyring keeps its three sources."""
    payload, record, public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")
    entry = _listing_entry(
        "my-tool",
        "1.2.3",
        payload,
        trust="official",
        signature=record,
        extra={"public_key": public.decode("utf-8"), "trusted_keys": [public.decode("utf-8")]},
    )

    result = _install(entry, payload)

    assert result["status"] == "quarantined", result
    assert "not from a trusted key" in result["reason"], result
    origins = {key.origin for key in plugin_signing.load_trusted_key_records()}
    assert plugin_signing.key_fingerprint(public) not in {
        key.fingerprint for key in plugin_signing.load_trusted_key_records()
    }, origins


def test_a_key_in_the_config_folder_is_the_one_that_answers(device, tmp_path) -> None:
    """Both halves of where a key belongs: without one in `trusted-keys` the
    community entry is refused for the missing key, and the same bytes install once
    the operator's own key is filed there, naming that file."""
    payload, record, public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")
    entry = _listing_entry("my-tool", "1.2.3", payload, trust="community", signature=record)

    refused = _install(dict(entry), payload)

    assert refused["status"] == "quarantined", refused
    assert "no_trusted_key" in refused["reason"], refused
    assert refused["trust_class"] == plugin_signing.USER, refused

    _publish_user_key(device, public)
    installed = _install(dict(entry), payload)

    assert installed["status"] == "extracted", installed
    signature = installed["verified"]["signature"]
    assert signature["key_origin"] == "config:trusted-keys/publisher.pub.pem", signature
    assert signature["trust_class"] == plugin_signing.USER, signature
    assert signature["key_fingerprint"] == plugin_signing.key_fingerprint(public), signature
    assert signature["kid"] == "publisher", signature


def test_forged_signature_bytes_are_refused_although_the_key_is_trusted(device, tmp_path) -> None:
    """The trusted key is in place and the bytes match the listing; only the
    signature bytes are wrong, and that alone has to stop the install."""
    payload, record, public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")
    forged = dict(record)
    forged["signature"] = record["signature"][:-4] + ("AAAA" if not record["signature"].endswith("AAAA") else "BBBB")
    _publish_user_key(device, public)

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="community", signature=forged), payload
    )

    assert result["status"] == "quarantined", result
    assert result["code"] == "signature_invalid", result
    assert "not from a trusted key" in result["reason"], result
    assert not (device / "plugins" / "my-tool").exists()


def test_a_forged_artifact_hash_in_the_listing_is_refused(device, tmp_path) -> None:
    """The listing promises the digest of other bytes. Nothing is committed, and
    the refusal carries both digests so the reader can see which side moved."""
    payload, _record, _public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")
    other, _other_record, _other_public = _signed_tree(
        tmp_path / "other", "my-tool", "1.2.3", extra={"EXTRA.md": "different build\n"}
    )

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="local", sha256=sha256_hex(other)),
        payload,
        allow_local_trust=True,
    )

    assert result["status"] == "hash_mismatch", result
    assert result["expected"] == sha256_hex(other), result
    assert result["actual"] == sha256_hex(payload), result
    assert not (device / "plugins" / "my-tool").exists()


def test_the_hash_of_the_delivered_bytes_is_compared_even_when_the_listing_hopes(device, tmp_path) -> None:
    """A listing with no hash at all is not an invitation: the digest is computed
    and a missing comparison value refuses."""
    payload, _record, _public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="local", sha256=""),
        payload,
        allow_local_trust=True,
    )

    assert result["status"] == "hash_mismatch", result
    assert result["actual"] == sha256_hex(payload), result


def test_the_caller_supplied_hash_is_a_second_witness_the_catalog_cannot_vouch_for(
    device, tmp_path
) -> None:
    """Listing and bytes agree with each other; the value the operator read before
    asking disagrees, which is the case only the caller can bring."""
    payload, _record, _public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")
    entry = _listing_entry("my-tool", "1.2.3", payload, trust="local")

    refused = _install(dict(entry), payload, allow_local_trust=True, expected_sha256=FORGED)

    assert refused["status"] == "hash_mismatch", refused
    assert "expected hash given at install" in refused["error"], refused
    assert refused["expected"] == FORGED, refused

    installed = _install(
        dict(entry), payload, allow_local_trust=True, expected_sha256=sha256_hex(payload)
    )

    assert installed["status"] == "extracted", installed
    assert installed["verified"]["sha256"] == sha256_hex(payload), installed


def test_a_bundle_under_another_version_than_the_catalog_promises_is_refused(
    device, tmp_path
) -> None:
    """The signature is valid, the hash is honest and the artifact is a build of
    1.2.4 while the entry sells 1.2.3: the listing is the witness the reader read."""
    payload, record, public = _signed_tree(tmp_path / "src", "my-tool", "1.2.4")
    _publish_user_key(device, public)

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="community", signature=record), payload
    )

    assert result["status"] == "identity_mismatch", result
    assert "listing offers 1.2.3" in result["error"], result
    assert "the artifact carries 1.2.4" in result["error"], result
    assert not (device / "plugins" / "my-tool").exists()


def test_a_record_over_other_content_is_refused_as_drift(device, tmp_path) -> None:
    """A publisher's record over one build, shipped with a file added afterwards:
    the hash the key covers disagrees, so the install is quarantined."""
    private, public = plugin_signing.generate_keypair()
    directory = _tree(tmp_path / "src", "my-tool", "1.2.3")
    record = plugin_signing.sign_plugin_dir(directory, private, kid="publisher")
    (directory / "LATER.md").write_text("added after signing\n", encoding="utf-8")
    payload = _zip_dir(directory)
    _publish_user_key(device, public)

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="community", signature=record), payload
    )

    assert result["status"] == "quarantined", result
    assert result["reason"].startswith("drift:"), result


def test_a_nested_signature_record_is_refused_because_no_key_covers_it(device, tmp_path) -> None:
    """`dir_sha256` skips the record name at any depth, so a second record hidden
    in a subdirectory would be invisible to the signature. The package is refused."""
    payload, record, public = _signed_tree(tmp_path / "src", "my-tool", "1.2.3")
    directory = tmp_path / "src" / "my-tool"
    nested = directory / "sub"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "ephe-plugin.sig.json").write_text(json.dumps(record), encoding="utf-8")
    _publish_user_key(device, public)
    delivered = _zip_dir(directory)

    result = _install(
        _listing_entry(
            "my-tool", "1.2.3", delivered, trust="community", signature=record, sha256=sha256_hex(delivered)
        ),
        delivered,
    )

    assert result["status"] == "quarantined", result
    assert "not covered by the hash" in result["reason"], result


def test_an_artifact_shipping_its_own_verdict_is_quarantined(device, tmp_path) -> None:
    """`VERIFY.json` is what the scanner writes after a clean pass; a bundle
    arriving with one already inside claims a verdict no scanner gave."""
    payload, record, public = _signed_tree(
        tmp_path / "src",
        "my-tool",
        "1.2.3",
        extra={"VERIFY.json": json.dumps({"verdict": "checked-clean", "findings": []})},
    )
    _publish_user_key(device, public)

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="community", signature=record), payload
    )

    assert result["status"] == "quarantined", result
    assert result["code"] == "verdict_file_present", result
    assert not (device / "plugins" / "my-tool").exists()


def test_a_detached_record_beside_the_artifact_verifies_and_says_so(
    device, tmp_path, monkeypatch
) -> None:
    """The record stands outside the archive, so the archive cannot carry its own
    judge; the key comes from the keyring and the answer repeats it."""
    private, public = plugin_signing.generate_keypair()
    payload = _zip_dir(_tree(tmp_path / "src", "my-tool", "1.2.3"))
    record = {
        "alg": plugin_signing.SIG_ALG,
        "kid": "release",
        "sha256": sha256_hex(payload),
        "signature": plugin_signing.sign(
            {"alg": plugin_signing.SIG_ALG, "kid": "release", "sha256": sha256_hex(payload)}, private
        ),
    }
    monkeypatch.setattr(
        plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [(public, plugin_signing.FIRST_PARTY)]
    )

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="local"),
        payload,
        allow_local_trust=True,
        detached_signature=record,
    )

    assert result["status"] == "extracted", result
    assert result["verified"]["signature_kind"] == "detached", result
    assert result["verified"]["signature"]["kid"] == "release", result
    assert result["verified"]["signature"]["key_origin"] == "loader", result


def test_forged_detached_bytes_are_refused(device, tmp_path, monkeypatch) -> None:
    """Same artifact, same trusted key, one character moved in the detached
    signature: the install stops and the staging directory goes with it."""
    private, public = plugin_signing.generate_keypair()
    payload = _zip_dir(_tree(tmp_path / "src", "my-tool", "1.2.3"))
    fields = {"alg": plugin_signing.SIG_ALG, "kid": "release", "sha256": sha256_hex(payload)}
    honest = plugin_signing.sign(fields, private)
    forged = dict(
        fields,
        signature=honest[:-4] + ("AAAA" if not honest.endswith("AAAA") else "BBBB"),
    )
    monkeypatch.setattr(
        plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [(public, plugin_signing.FIRST_PARTY)]
    )

    result = _install(
        _listing_entry("my-tool", "1.2.3", payload, trust="local"),
        payload,
        allow_local_trust=True,
        detached_signature=forged,
    )

    assert result["status"] == "quarantined", result
    assert result["code"] == "signature_invalid", result
    assert result["kid"] == "release", result
    assert not (device / "plugins" / "my-tool").exists()


def test_an_unsigned_local_artifact_is_refused_until_the_trust_is_named(device, tmp_path) -> None:
    """Without the trust word the install stops at the gate and says which word it
    needs; nothing is staged, so nothing can be half-installed."""
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))

    result = _install(
        _listing_entry("alpha", "1.0.0", payload, trust="local", sha256=sha256_hex(payload)),
        payload,
        allow_local_trust=False,
    )

    assert result["status"] == "local_trust_required", result
    assert result["trust"] == "local", result
    assert "explicit trust" in result["error"], result
    assert not (device / "plugins" / "alpha").exists()


def test_a_record_beside_the_file_is_a_signature_the_trust_word_does_not_cover(
    device, tmp_path, monkeypatch
) -> None:
    """The gate asks whether the artifact is signed, and a record the publisher put
    beside the file is a signature. Demanding the trust word on top of it would only
    train operators to type it for bytes that were verified anyway."""
    private, public = plugin_signing.generate_keypair()
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    fields = {"alg": plugin_signing.SIG_ALG, "kid": "release", "sha256": sha256_hex(payload)}
    record = dict(fields, signature=plugin_signing.sign(fields, private))
    monkeypatch.setattr(
        plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [(public, plugin_signing.FIRST_PARTY)]
    )

    result = _install(
        _listing_entry("alpha", "1.0.0", payload, trust="local", sha256=sha256_hex(payload)),
        payload,
        allow_local_trust=False,
        detached_signature=record,
    )

    assert result["status"] == "extracted", result
    assert result["verified"]["signature_kind"] == "detached", result


def test_a_forged_record_beside_the_file_meets_the_verifier_and_not_the_gate(
    device, tmp_path, monkeypatch
) -> None:
    """The relaxation above may not become a way in: a record that does not verify
    has to be quarantined, which is a harder answer than the trust gate gives."""
    private, public = plugin_signing.generate_keypair()
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    fields = {"alg": plugin_signing.SIG_ALG, "kid": "release", "sha256": sha256_hex(payload)}
    forged = dict(fields, signature=plugin_signing.sign(fields, private)[:-4] + "AAAA")
    monkeypatch.setattr(
        plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [(public, plugin_signing.FIRST_PARTY)]
    )

    result = _install(
        _listing_entry("alpha", "1.0.0", payload, trust="local", sha256=sha256_hex(payload)),
        payload,
        allow_local_trust=False,
        detached_signature=forged,
    )

    assert result["status"] == "quarantined", result
    assert result["code"] == "signature_invalid", result
    assert not (device / "plugins" / "alpha").exists()


def test_the_plan_refuses_an_unsigned_local_artifact_before_anything_is_ready(
    device, tmp_path, monkeypatch
) -> None:
    """A plan is shown to the reader as "ready" or not. An unsigned artifact from a
    source the index does not vouch for is not ready, and the refusal says which word
    would change that."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)

    answer = marketplace_planner.plan(source["id"], "alpha", allow_local_trust=False)

    assert answer["status"] == "refused", answer
    assert answer["code"] == "local_trust_required", answer
    assert not (device / "plugins" / "alpha").exists()


def test_a_record_beside_the_file_makes_the_plan_ready_without_the_trust_word(
    device, tmp_path, monkeypatch
) -> None:
    """The plan reads the same folder the install reads: a record beside the artifact
    is a signature, so the plan can say ready while the trust word stays untyped."""
    private, public = plugin_signing.generate_keypair()
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    fields = {"alg": plugin_signing.SIG_ALG, "kid": "release", "sha256": sha256_hex(payload)}
    (artifact.parent / f"{artifact.name}.sig").write_text(
        json.dumps(dict(fields, signature=plugin_signing.sign(fields, private))), encoding="utf-8"
    )
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)

    answer = marketplace_planner.plan(source["id"], "alpha", allow_local_trust=False)

    assert answer["status"] == "ready", answer
    assert answer["sidecar_signature"] is True, answer
    assert answer["signature"] is None, answer


def test_an_unreadable_record_beside_the_file_is_a_refusal_not_a_missing_one(
    device, tmp_path, monkeypatch
) -> None:
    """A truncated record is the shape an interrupted write or a careless attacker
    leaves behind. Treating it as absent would install the artifact unsigned."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    (artifact.parent / f"{artifact.name}.sig").write_text('{"alg": "ES256", ', encoding="utf-8")
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)

    answer = marketplace_planner.plan(source["id"], "alpha", allow_local_trust=True)

    assert answer["status"] == "refused", answer
    assert answer["code"] == "signature_record_invalid", answer
    assert not (device / "plugins" / "alpha").exists()


def test_a_record_that_appears_after_the_plan_is_still_read_by_the_install(
    device, tmp_path, monkeypatch
) -> None:
    """The plan and the install are two reads of the disk. A record that turns up in
    between, unreadable, has to stop the install: the plan's word is not a permit."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)
    plan = marketplace_planner.plan(source["id"], "alpha", allow_local_trust=True)
    assert plan["status"] == "ready", plan

    (artifact.parent / f"{artifact.name}.sig").write_text("not a record", encoding="utf-8")
    result = marketplace_service.install(plan)

    assert result["status"] == "refused", result
    assert result["code"] == "signature_record_invalid", result
    assert not (device / "plugins" / "alpha").exists()


def test_an_unsigned_local_install_without_a_comparison_value_refuses(
    device, tmp_path, monkeypatch, capsys
) -> None:
    """`--trust-local` alone is not a comparison value. The CLI refuses and says
    out loud that this source's index carries no signature."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)

    code, out, err = _run_cli(
        ["plugin", "install", "alpha", "--source", source["id"], "--trust-local"], capsys
    )

    assert code == 1, (out, err)
    assert "unverified_source" in err, err
    assert "--expected-sha256" in err, err
    assert "no signature" in err, err
    assert not (device / "plugins" / "alpha").exists()


def test_an_unsigned_local_install_with_the_stated_hash_names_what_it_verified(
    device, tmp_path, monkeypatch, capsys
) -> None:
    """The install that goes through on a caller-supplied hash still has to say the
    truth about it: no key answered, and the source is not signature-checked."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)

    code, out, err = _run_cli(
        [
            "plugin",
            "install",
            "alpha",
            "--source",
            source["id"],
            "--trust-local",
            "--expected-sha256",
            sha256_hex(payload),
        ],
        capsys,
    )

    assert code == 0, (out, err)
    assert "installed: alpha 1.0.0" in out, out
    assert f"sha256 {sha256_hex(payload)}" in out, out
    assert "key      none" in out, out
    assert "source   local" in out, out
    assert "no signature" in out, out
    assert "installed on explicit local trust" in out, out
    assert "state    off" in out, out
    assert "ephe plugin enable alpha" in out, out


def test_a_wrong_expected_hash_refuses_before_anything_lands(device, tmp_path, monkeypatch, capsys) -> None:
    """A real tree, compared before and after: the refusal leaves the plugins root
    byte-identical."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)
    before = _tree_state(device / "plugins")

    code, out, err = _run_cli(
        [
            "plugin",
            "install",
            "alpha",
            "--source",
            source["id"],
            "--trust-local",
            "--expected-sha256",
            FORGED,
        ],
        capsys,
    )

    assert code == 1, (out, err)
    assert "hash_mismatch" in err, err
    assert _tree_state(device / "plugins") == before
    assert "alpha" not in json.dumps(_tree_state(device / "plugins"))


def test_a_new_permission_is_approved_by_its_digest_and_by_nothing_else(
    device, tmp_path, monkeypatch, capsys
) -> None:
    """Two calls, one digest. The first installs nothing and prints the delta's
    digest; the second names that digest and the artifact lands."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0", tool_families=["read"]))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(
        tmp_path / "market",
        [_v2_version("1.0.0", artifact, sha256_hex(payload), tool_families=["read"])],
    )
    source = _local_source(tmp_path, monkeypatch, index)
    digest = marketplace_planner.permission_delta(None, {"tool_families": ["read"], "data_roots": []})["digest"]
    base = [
        "plugin",
        "install",
        "alpha",
        "--source",
        source["id"],
        "--trust-local",
        "--expected-sha256",
        sha256_hex(payload),
    ]

    code, out, err = _run_cli(base, capsys)

    assert code == 1, (out, err)
    assert "permission" in err, err
    assert digest in err, err
    assert not (device / "plugins" / "alpha").exists()

    code, out, err = _run_cli(base + ["--approve-permissions", digest], capsys)

    assert code == 0, (out, err)
    assert "installed: alpha 1.0.0" in out, out
    assert (device / "plugins" / "alpha" / "ephe-plugin.json").is_file()


def test_a_permission_approval_over_a_different_digest_is_refused(
    device, tmp_path, monkeypatch, capsys
) -> None:
    """The approval is bound to the digest: an approval for one artifact's
    permissions does not carry over to another's, and the refusal prints both."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0", tool_families=["read"]))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(
        tmp_path / "market",
        [_v2_version("1.0.0", artifact, sha256_hex(payload), tool_families=["read"])],
    )
    source = _local_source(tmp_path, monkeypatch, index)
    other = marketplace_planner.permission_delta(None, {"tool_families": ["write"], "data_roots": []})["digest"]

    code, out, err = _run_cli(
        [
            "plugin",
            "install",
            "alpha",
            "--source",
            source["id"],
            "--trust-local",
            "--expected-sha256",
            sha256_hex(payload),
            "--approve-permissions",
            other,
        ],
        capsys,
    )

    assert code == 1, (out, err)
    assert "permission_digest_mismatch" in err, err
    assert other in err, err
    assert not (device / "plugins" / "alpha").exists()


def test_yes_is_not_a_word_the_install_parser_knows() -> None:
    """`--yes` belongs to `remove`, never to `install`: an install's consent word
    is the permission digest, and the parser refuses the shortcut outright."""
    with pytest.raises(SystemExit) as caught:
        ephe_cli.build_parser().parse_args(["plugin", "install", "alpha", "--yes"])

    assert caught.value.code == 2


def test_a_hand_carried_yes_flag_cannot_wave_a_permission_review_through(
    device, tmp_path, monkeypatch
) -> None:
    """Someone handing the install path a Namespace that already carries `yes`
    still gets the refusal: the install never reads that word."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0", tool_families=["read"]))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(
        tmp_path / "market",
        [_v2_version("1.0.0", artifact, sha256_hex(payload), tool_families=["read"])],
    )
    source = _local_source(tmp_path, monkeypatch, index)

    code = ephe_cli._plugin_install(
        argparse.Namespace(
            action="install",
            plugin_id="alpha",
            source=source["id"],
            version="",
            trust_local=True,
            expected_sha256=sha256_hex(payload),
            approve_permissions="",
            json=False,
            yes=True,
        )
    )

    assert code == 1
    assert not (device / "plugins" / "alpha").exists()


def test_a_signed_detached_artifact_from_a_local_source_names_the_key_and_the_source(
    device, tmp_path, monkeypatch, capsys
) -> None:
    """The lead's preferred shape for a local source: a detached record beside the
    file, verified against the keyring. The output names the key, the source and
    the state the install actually left behind."""
    private, public = plugin_signing.generate_keypair()
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    fields = {"alg": plugin_signing.SIG_ALG, "kid": "release", "sha256": sha256_hex(payload)}
    (artifact.parent / f"{artifact.name}.sig").write_text(
        json.dumps(dict(fields, signature=plugin_signing.sign(fields, private))), encoding="utf-8"
    )
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, sha256_hex(payload))])
    source = _local_source(tmp_path, monkeypatch, index)
    monkeypatch.setattr(
        plugin_signing, "TRUSTED_KEYS_LOADER", lambda: [(public, plugin_signing.FIRST_PARTY)]
    )

    code, out, err = _run_cli(["plugin", "install", "alpha", "--source", source["id"]], capsys)

    assert code == 0, (out, err)
    assert "installed: alpha 1.0.0" in out, out
    assert "kid=release" in out, out
    assert plugin_signing.key_fingerprint(public) in out, out
    assert "record read beside the artifact file" in out, out
    assert "source   local" in out, out
    assert "unverified" not in out, out


def test_a_local_index_whose_artifact_hash_disagrees_is_refused_by_the_service(
    device, tmp_path, monkeypatch, capsys
) -> None:
    """The catalog's promise and the bytes on disk disagree, and the plan cannot
    talk its way past the comparison: nothing lands."""
    artifacts = tmp_path / "market" / "artifacts"
    payload = _zip_dir(_tree(tmp_path / "src", "alpha", "1.0.0"))
    artifact = _write_artifact(artifacts, "alpha", "1.0.0", payload)
    index = _v2_index(tmp_path / "market", [_v2_version("1.0.0", artifact, FORGED)])
    source = _local_source(tmp_path, monkeypatch, index)

    plan = marketplace_planner.plan(source["id"], "alpha", approve_permissions=True, allow_local_trust=True)

    assert plan["status"] == "ready", plan
    result = marketplace_service.install(plan)

    assert result["status"] == "hash_mismatch", result
    assert result["expected"] == FORGED, result
    assert not (device / "plugins" / "alpha").exists()
