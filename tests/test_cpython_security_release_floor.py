"""The CPython release that carries CVE-2026-114583 and CVE-2026-115557, held by the pin.

Both advisories are fixed in the interpreter, and a package audit cannot see either one:
`tarfile.tar_filter` never ran the link check that `data_filter` ran, so a link member named
after the destination directory replaced it and later members landed outside it (PSF-2026-45);
and `ssl` now rejects a chain carrying a public key on a distrusted list, added after the
eMudhra compromise (PSF-2026-46). The exposed thing is the interpreter `.python-version`
names, so the only way to hold it is to read it back.

Measured on this machine 2026-11-09, against the installs uv actually has:

 * 3.13.16 — the tarfile guard is absent from `Lib/tarfile.py`, `_ssl`'s dependency list names
   no `distrusted_spki.h`, and the reproducers were left unrun.
 * 3.13.17 — both absent, and `filter="tar"` did not refuse: RecursionError on the link member,
   and the empty-name chain left `dest/a` pointing out of the destination.
 * 3.13.18 — both present, and every case here was refused with `OutsideDestinationError` with
   nothing written outside the destination.
 * 3.12.15 — both absent, reproducers unrun.
 * 3.12.16 — both present, reproducers unrun.

The ssl half was also checked behaviourally, which is the stronger reading: upstream ships
`Lib/test/certdata/distrusted.zip`, a chain that is otherwise valid and whose intermediate
public key is on the list, and `test_ssl.py::test_distrusted_spki` handshakes it through a
`MemoryBIO` pair. Run by hand here, 3.13.18 refused with `verify_code=28 (certificate
rejected)` and 3.13.17 completed the handshake. That fixture stays out of this repository
because it holds private key material, which is why CPython itself keeps it in a
password-protected archive, so the durable local reading is the build manifest plus the pin,
together with the tarfile half, which needs no fixture and is asserted behaviourally below.

`.github/advisories-ignore.txt` cannot hold either CVE: its `ecosystem=` vocabulary is the
three audited package ecosystems, and `scripts/advisory_id_check.py` resolves a row by asking
OSV which package it affects. For these two, OSV returns a Git-scoped record whose
`affected[].package` is empty, so the row would fail the register's own check.
"""
from __future__ import annotations

import io
import sys
import sysconfig
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Per minor, the first release whose stdlib carries both fixes, as measured above. A minor
#: is added here only when its floor has been read off an install, not inferred from a
#: changelog: a floor nobody measured is a floor that goes red on somebody else's machine.
FIXED_FLOOR: dict[tuple[int, int], tuple[int, int, int]] = {
    (3, 13): (3, 13, 18),
    (3, 12): (3, 12, 16),
}

#: Names a link member resolves to the destination itself, which is what the guard rejects.
DESTINATION_NAMED_LINKS = ("", ".", "./")


def _semver(text: str) -> tuple[int, int, int]:
    parts = (text.split("-")[0].split(".") + ["0", "0", "0"])[:3]
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def _pin() -> str:
    return (ROOT / ".python-version").read_text(encoding="utf-8").strip()


def _floor(release: tuple[int, int, int]) -> tuple[int, int, int] | None:
    return FIXED_FLOOR.get(release[:2])


def _here() -> str:
    return ".".join(map(str, sys.version_info[:3]))


def _archive(name: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        member = tarfile.TarInfo(name)
        member.type = tarfile.SYMTYPE
        member.linkname = "."
        member.mode = 0o777
        tf.addfile(member)
    return buf.getvalue()


def _unmeasured(release: tuple[int, int, int]) -> str | None:
    """Skip reason for a minor nobody has read an install of; a below-floor minor gets none.

    An unmeasured minor is this repository's blind spot, so it says so out loud and skips; it
    is not allowed to look like a pass. A measured minor below its floor is the interpreter's
    own defect, and the assertions below run and go red on it.
    """
    if _floor(release) is None:
        return f"{_here()} is a minor with no measured advisory floor here; read an install and add it"
    return None


def _refusal(release: tuple[int, int, int]) -> str | None:
    """Why that release may not run the product, or None when this file has no claim about it.

    Kept separate from any assertion so the comparison can be handed a release the machine does
    not have installed; the interpreter cannot be downgraded to prove the fence answers.
    """
    floor = _floor(release)
    if floor is None:
        return None
    if release < floor:
        return (
            f"{'.'.join(map(str, release))} is below the floor "
            f"{'.'.join(map(str, floor))} that carries CVE-2026-114583 and CVE-2026-115557"
        )
    return None


def test_the_pin_names_a_release_that_carries_both_fixes():
    pin = _semver(_pin())
    floor = _floor(pin)
    assert floor, (
        f".python-version pins {pin}, a minor with no measured advisory floor here; read the "
        "install and add it, or move the pin to a minor that has one"
    )
    assert pin >= floor, (
        f".python-version pins {'.'.join(map(str, pin))}, below the floor "
        f"{'.'.join(map(str, floor))} that carries CVE-2026-114583 and CVE-2026-115557"
    )


def test_the_interpreter_running_this_suite_is_at_or_above_its_floor():
    """The pin is a claim about which release the project wants; this asks which one executes it.

    `.python-version` is text, and every other test here either reads that text or asks the
    stdlib to behave. A `.venv` recreated with an older interpreter — a system `python3`, a stale
    uv cache, a runner image that carried an earlier patch — passes the pin test while running
    the vulnerable `tarfile` and the trusting `ssl`. The comparison is made against
    `sys.version_info` so the answer comes from the interpreter, with the pin printed beside it.
    """
    running = tuple(sys.version_info[:3])
    skip = _unmeasured(running)
    if skip:
        pytest.skip(skip)
    refusal = _refusal(running)
    assert refusal is None, (
        f"the interpreter executing this suite is {sys.version.split()[0]} at {sys.executable} "
        f"and {refusal}; .python-version pins {_pin()}, which the venv does not match — recreate "
        "it with `uv sync` rather than editing the floor"
    )


def test_a_release_below_the_floor_is_refused_by_that_comparison():
    """The mutation the comparison has to survive: being handed the release that predates both fixes.

    3.13.17 is the release this file measured as carrying neither guard, and it is the release the
    fence exists to refuse. The interpreter cannot be downgraded to prove the fence answers for it,
    so the release is handed to the comparison directly, together with the two edges that must
    still be answered the other way.
    """
    floor = FIXED_FLOOR[(3, 13)]
    below = (floor[0], floor[1], floor[2] - 1)
    assert _refusal(below) is not None, f"{below} predates the fixes and was not refused"
    assert _refusal(floor) is None, f"{floor} is the floor itself and must be admitted"
    assert _refusal((floor[0], floor[1], floor[2] + 1)) is None
    unmeasured = _refusal((3, 14, 0))
    assert unmeasured is None, (
        "3.14 has no measured floor, so this file makes no claim about it; if an install was "
        "read, add the minor to FIXED_FLOOR and make this case name the floor"
    )


@pytest.mark.parametrize("filter_name", ["tar", "data"])
@pytest.mark.parametrize("member_name", DESTINATION_NAMED_LINKS)
def test_tar_filter_refuses_a_link_named_after_the_destination(tmp_path, member_name, filter_name):
    """The CVE-2026-114583 half, run against the interpreter that is executing this suite.

    `filter="tar"` is the case that used to pass: `data_filter` refused this link and
    `tar_filter` did not look, so the destination became a symlink and every later member
    went somewhere else.
    """
    skip = _unmeasured(sys.version_info[:3])
    if skip:
        pytest.skip(skip)
    destination = tmp_path / "dest"
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(_archive(member_name))) as tf:
        try:
            tf.extractall(destination, filter=filter_name)
        except tarfile.OutsideDestinationError:
            return
        except Exception as exc:  # noqa: BLE001 - any other exception is the finding
            raise AssertionError(
                f"filter={filter_name!r} on a link member named {member_name!r} raised "
                f"{type(exc).__name__}: {exc}, not the CVE-2026-114583 refusal "
                f"OutsideDestinationError; {_here()} does not carry the guard"
                f" (floor {'.'.join(map(str, _floor(sys.version_info[:3])))})"
            ) from exc
    raise AssertionError(
        f"filter={filter_name!r} on a link member named {member_name!r} extracted a symlink "
        f"onto the destination without refusing it, so later members can land outside it; "
        f"{_here()} is vulnerable to CVE-2026-114583 (floor "
        f"{'.'.join(map(str, _floor(sys.version_info[:3])))})"
    )


def test_the_interpreter_build_carries_the_distrusted_spki_table():
    """The CVE-2026-115557 half, read off the build that compiled `_ssl`.

    `Modules/_ssl/distrusted_spki.h` is a file the fix added, and the build records it in
    `_ssl`'s dependency list. The reading is of that manifest: it says the interpreter was
    built from a tree carrying the list, which is the strongest claim this repository can
    make without committing key material, while the handshake that would prove it lives in
    the fixture upstream keeps out of git. A build that reports no dependency list at all (a
    vendor rebuild that dropped the generated Makefile) skips and prints the reason.
    """
    skip = _unmeasured(sys.version_info[:3])
    if skip:
        pytest.skip(skip)
    deps = sysconfig.get_config_var("MODULE__SSL_DEPS")
    if not deps:
        pytest.skip("this build reports no _ssl dependency list")
    assert "distrusted_spki.h" in deps, (
        f"_ssl was built without the distrusted-SPKI table, so this interpreter still trusts "
        f"the eMudhra keys (CVE-2026-115557); it is {_here()} and the floor is "
        f"{'.'.join(map(str, _floor(sys.version_info[:3])))}"
    )
