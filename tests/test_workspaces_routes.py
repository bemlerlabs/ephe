"""tests/test_workspaces_routes.py — the isolation surface behind /api, and its refusals.

`core/workspace_lifecycle`, `core/change_set`, `core/review_gate` and `core.atomic_publish`
each had their own tests and no caller: a page could read none of them, so a wave's trees,
its change sets, the verdict on one and the publish itself were reachable from the CLI
only. This file pins the HTTP surface — the ten operations, their envelopes, and the three
refusals the router owns: 404 for a name no store holds, 422 for an argument a module turns
down, and 409 for a request the state cannot carry.

It also pins the surface that answers a collision while it is still a decision: what a build
tells the run that just wrote (`conflicts`), what a publish refuses when another run holds the
path (`publish_path_claimed`), and what `GET /api/change-sets/claims` answers — who is in a
path, and since when.

Every case runs against a throwaway repository and stores inside the test's own tmp
directory. The register, the change-set store and the review ledger are the developer's own
under ``~/.ephe`` when a test forgets to redirect them, so each fixture below points all
three at tmp_path before the app is built.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MISSING_WORKSPACE = "00000000"
MISSING_CHANGE_SET = "cs-20260101T000000Z-deadbeef"
PROVENANCE = {
    "session_id": "s-1",
    "agent_id": "agent-a",
    "why": "the wave asked for a described publish",
}


def _git(args: list[str], cwd: Path) -> str:
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A repository on ``main`` with one commit, and the managed directory beside it."""
    from core import workspace_lifecycle as life

    root = tmp_path / "checkout"
    root.mkdir()
    _git(["init", "-q", "-b", "main"], root)
    (root / "README.md").write_text("the checkout\n", encoding="utf-8")
    _git(["add", "README.md"], root)
    _git(
        ["-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "init"],
        root,
    )
    monkeypatch.setattr(life, "REPO_ROOT", root)
    monkeypatch.setattr(life, "WORKSPACES_DIR", tmp_path / "managed")
    return root


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """The change-set store and the review ledger, both inside the test's own directory."""
    from core import change_set, review_gate
    from core.review_gate import ReviewLedger

    changesets = tmp_path / "changesets"
    monkeypatch.setenv("EPHE_CHANGESETS_DIR", str(changesets))
    monkeypatch.setattr(change_set, "CHANGESETS_DIR", changesets)
    monkeypatch.setattr(review_gate, "_default_ledger", ReviewLedger(tmp_path / "reviews.jsonl"))
    return changesets


@pytest.fixture
def client(checkout, stores, tmp_path, monkeypatch):
    """The app under test. Its router is registered in ``server/main.py`` like every other."""
    monkeypatch.setenv("EPHE_WORKSPACES_DIR", str(tmp_path / "managed"))
    # The read gained a ``runs`` leg and two of its three sources are process-wide, so a
    # worker that already ran a subagent or an approval case carries its runs into a board
    # this test believes is empty: the helper registry is a cached snapshot under
    # EPHE_CONFIG_DIR, and the approval waits are an app-wide dict. Point the first at this
    # test's own directory and clear both, or the two empty-board cases below only hold on a
    # tree where nothing else has run.
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core import subagent_history
    from server.routes import chat as chat_routes

    subagent_history.reset_for_test()
    chat_routes._active_sandbox_events.clear()
    from server.main import create_app

    return TestClient(create_app())


def _create(client: TestClient, owner: str = "agent-a", base: str = "main") -> dict:
    res = client.post("/api/workspaces", json={"owner": owner, "base": base})
    assert res.status_code == 200, res.text
    return res.json()["workspace"]


def _build(client: TestClient, workspace_id: str, provenance: dict | None = None) -> dict:
    res = client.post(
        "/api/change-sets",
        json={
            "workspace_id": workspace_id,
            "summary": "one edit and one new file",
            "provenance": PROVENANCE if provenance is None else provenance,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()["change_set"]


def _reason(path: str, why: str = "this line reads wrong") -> dict:
    return {"path": path, "line": 1, "why": why}


def _message(res) -> str:
    """The sentence the app's error envelope carries for a refusal (server/main.py:208)."""
    return res.json()["error"]["message"]


def _code(res) -> str:
    """The stable reason code that travels beside that sentence, for the surface to translate."""
    return res.json()["error"]["reason_code"]


def _edit_tree(path: str, extra: str = "edited\n") -> None:
    target = Path(path) / "README.md"
    target.write_text("the checkout\n" + extra, encoding="utf-8")


def _approve(client: TestClient, change_set: dict, reviewer: str = "agent-b"):
    first = change_set["files"][0]["path"]
    return client.post(
        f"/api/change-sets/{change_set['id']}/review",
        json={"verdict": "approve", "reviewer": reviewer, "reasons": [_reason(first)]},
    )


# The tree surface


def test_the_tree_surface_answers_the_register(client, checkout):
    """Given no tree yet; When one is created; Then every read names the same tree."""
    assert client.get("/api/workspaces").json() == {"workspaces": [], "runs": []}

    created = _create(client)
    assert created["owner"] == "agent-a"
    assert created["state"] == "ready"
    assert created["branch"] == f"ws/agent-a-{created['id']}"
    assert created["created_at"]
    assert Path(created["path"]).parent == checkout.parent / "managed"

    listed = client.get("/api/workspaces").json()["workspaces"]
    assert [row["id"] for row in listed] == [created["id"]]
    # The six fields the register owns come back unchanged; the run fields the fleet read
    # adds (G2) sit beside them rather than replacing anything.
    assert {key: listed[0][key] for key in created} == created
    assert listed[0]["run_state"] == "running"
    assert listed[0]["needs_you"] is False
    assert listed[0]["owner_alive"] is True

    assert client.get(f"/api/workspaces/{created['id']}").json() == {"workspace": created}


def test_a_read_takes_the_state_from_the_tree_itself(client):
    """Given a clean tree; When the tree carries an edit; Then the read says dirty."""
    created = _create(client)
    _edit_tree(created["path"])

    assert client.get(f"/api/workspaces/{created['id']}").json()["workspace"]["state"] == "dirty"


def test_creating_a_tree_refuses_a_base_git_cannot_reach(client):
    """Given a base no ref names; When it is asked for; Then 409 and no live row."""
    res = client.post("/api/workspaces", json={"owner": "agent-a", "base": "no-such-ref"})
    assert res.status_code == 409, res.text
    assert "no-such-ref" in _message(res)
    assert _code(res) == "workspace_create_refused"

    assert client.get("/api/workspaces").json() == {"workspaces": [], "runs": []}


@pytest.mark.parametrize("payload", [{}, {"owner": ""}, {"owner": "a", "base": ""}])
def test_creating_a_tree_refuses_a_blank_argument(client, payload):
    """Given a request with no owner (or a blank one); Then 422, never 500."""
    assert client.post("/api/workspaces", json=payload).status_code == 422


def test_deleting_a_tree_refuses_a_dirty_one_until_force(client):
    """Given a tree with a local edit; When it is removed; Then 409, then force takes it."""
    created = _create(client)
    _edit_tree(created["path"])

    refused = client.delete(f"/api/workspaces/{created['id']}")
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "workspace_remove_refused"
    assert Path(created["path"]).is_dir()

    assert client.delete(f"/api/workspaces/{created['id']}", params={"force": "true"}).json() == {
        "removed": created["id"]
    }
    assert not Path(created["path"]).exists()
    assert client.get("/api/workspaces").json() == {"workspaces": [], "runs": []}


def test_reaping_collects_the_row_a_failed_create_left_behind(client):
    """Given a discarded row and a live tree; When reaped; Then only the row goes."""
    from core import workspace_lifecycle as life

    live = _create(client)
    client.post("/api/workspaces", json={"owner": "agent-b", "base": "no-such-ref"})
    rows = json.loads(life.register_file().read_text(encoding="utf-8"))["workspaces"]
    discarded = [row["id"] for row in rows if row["state"] == "discarded"]
    assert len(discarded) == 1

    # An absent body is the module's own default grace period; nothing is old enough yet.
    assert client.post("/api/workspaces/reap").json() == {"reaped": []}

    assert client.post("/api/workspaces/reap", json={"older_than_minutes": 0}).json() == {
        "reaped": discarded
    }
    assert [row["id"] for row in client.get("/api/workspaces").json()["workspaces"]] == [live["id"]]


def test_reaping_refuses_a_negative_grace(client):
    """Given a grace period below zero; Then 422, and the register is read instead."""
    res = client.post("/api/workspaces/reap", json={"older_than_minutes": -1})
    assert res.status_code == 422


def test_creating_a_tree_refuses_while_the_wave_is_at_its_width(client, monkeypatch):
    """Given a wave whose width is one tree; When a second is asked for; Then 429 names it."""
    from core import agent_limits

    monkeypatch.setattr(
        agent_limits,
        "defaults",
        lambda: agent_limits.Limits(
            max_agents=1,
            max_turns_per_agent=40,
            max_cpu_share=0.75,
            max_disk_mb=2048,
            max_runtime_s=1800,
        ),
    )
    _create(client)
    refused = client.post("/api/workspaces", json={"owner": "agent-b", "base": "main"})
    assert refused.status_code == 429, refused.text
    assert _message(refused).startswith("agent-limit")
    assert _code(refused) == "agent_limit_reached"


# The change-set surface


def test_a_change_set_records_the_paths_the_tree_moved(client):
    """Given a tree with one edit and one new file; Then the record names both, sorted."""
    created = _create(client)
    _edit_tree(created["path"])
    (Path(created["path"]) / "new.txt").write_text("new\n", encoding="utf-8")

    built = _build(client, created["id"])
    assert built["id"].startswith("cs-")
    assert built["state"] == "draft"
    assert built["summary"] == "one edit and one new file"
    assert built["provenance"] == PROVENANCE
    assert [change["path"] for change in built["files"]] == ["README.md", "new.txt"]
    assert [change["op"] for change in built["files"]] == ["modify", "create"]
    assert all(change["diff_sha"].startswith("sha256:") for change in built["files"])
    # The record carries the key the store files it under, which is the resolved path.
    assert built["workspace_id"] == str(Path(created["path"]).resolve())

    assert client.get(f"/api/change-sets/{built['id']}").json() == {"change_set": built}


def test_change_sets_are_listed_by_register_id_or_by_path(client):
    """Given two records in one tree; Then both reads find them, newest first."""
    created = _create(client)
    _edit_tree(created["path"])
    first = _build(client, created["id"])
    _edit_tree(created["path"], "and again\n")
    second = _build(client, created["id"])

    by_id = client.get("/api/change-sets", params={"workspace_id": created["id"]}).json()
    by_path = client.get("/api/change-sets", params={"workspace_id": created["path"]}).json()
    assert [row["id"] for row in by_id["change_sets"]] == [second["id"], first["id"]]
    assert by_path == by_id


def test_a_change_set_is_refused_when_it_cannot_say_why(client):
    """Given a provenance with no why; Then 422 — the record that cannot say why is absent."""
    created = _create(client)
    _edit_tree(created["path"])
    res = client.post(
        "/api/change-sets",
        json={
            "workspace_id": created["id"],
            "summary": "an edit",
            "provenance": {"session_id": "s-1", "agent_id": "agent-a"},
        },
    )
    assert res.status_code == 422, res.text
    assert "why" in _message(res)
    assert _code(res) == "change_set_build_refused"
    assert client.get("/api/change-sets", params={"workspace_id": created["id"]}).json() == {
        "change_sets": []
    }


def test_a_directory_no_managed_tree_holds_is_no_workspace(client, tmp_path):
    """Given a directory outside the managed trees; Then 404 — a caller names a tree.

    The register is the source of the name, so the path `core.change_set` is keyed by
    never comes from the request. A name no store holds answers the same 404, and a
    missing or empty one answers 422.
    """
    res = client.post(
        "/api/change-sets",
        json={
            "workspace_id": str(tmp_path),
            "summary": "an edit",
            "provenance": PROVENANCE,
        },
    )
    assert res.status_code == 404, res.text
    assert _code(res) == "workspace_unknown"

    unknown = client.get("/api/change-sets", params={"workspace_id": "not-a-workspace"})
    assert unknown.status_code == 404
    assert _code(unknown) == "workspace_unknown"
    blank = client.get("/api/change-sets", params={"workspace_id": ""})
    assert blank.status_code == 422
    assert "workspace_id is required" in _message(blank)
    assert _code(blank) == "workspace_id_required"
    assert client.get("/api/change-sets").status_code == 422


def test_a_link_out_of_the_managed_root_is_no_workspace(client, tmp_path):
    """Given a name inside the managed directory that points outside it; Then 404.

    The name is folded out before it is compared, so a link is refused rather than
    followed and the store is never keyed by the directory it names.
    """
    created = _create(client)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = Path(created["path"]).parent / "escape"
    link.symlink_to(outside)

    res = client.get("/api/change-sets", params={"workspace_id": str(link)})
    assert res.status_code == 404, res.text
    assert _code(res) == "workspace_unknown"


# The review surface


def test_a_review_refuses_the_author_and_a_reason_outside_the_set(client):
    """Given a set authored by agent-a; Then its own approval is no verdict at all."""
    created = _create(client)
    _edit_tree(created["path"])
    built = _build(client, created["id"])
    path = built["files"][0]["path"]

    def review(verdict: str, reviewer: str, reasons: list[dict]):
        return client.post(
            f"/api/change-sets/{built['id']}/review",
            json={"verdict": verdict, "reviewer": reviewer, "reasons": reasons},
        )

    own = review("approve", "agent-a", [_reason(path)])
    assert own.status_code == 422, own.text
    assert "cannot sign its own change set" in _message(own)
    # J2: the four-eyes refusal names itself, so a surface can translate it.
    assert _code(own) == "self_sign_forbidden"

    outside = review("approve", "agent-b", [_reason("somewhere/else.txt")])
    assert outside.status_code == 422, outside.text
    assert "does not touch" in _message(outside)
    assert _code(outside) == "review_refused"

    assert review("sideways", "agent-b", [_reason(path)]).status_code == 422
    assert review("approve", "agent-b", []).status_code == 422
    assert review("approve", "agent-b", [{}]).status_code == 422
    assert review("approve", "agent-b", [_reason(path, "")]).status_code == 422

    # Nothing above reached the ledger, so the set still may not publish.
    unapproved = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert unapproved.status_code == 409
    assert _code(unapproved) == "publish_without_approval"


def test_a_review_records_the_verdict_with_its_reasons(client):
    """Given a reviewer other than the author; Then the verdict comes back located."""
    created = _create(client)
    _edit_tree(created["path"])
    built = _build(client, created["id"])
    path = built["files"][0]["path"]

    res = client.post(
        f"/api/change-sets/{built['id']}/review",
        json={
            "verdict": "request_changes",
            "reviewer": "agent-b",
            "reasons": [_reason(path, "the second line needs a reason")],
        },
    )
    assert res.status_code == 200, res.text
    assert res.json() == {
        "verdict": {
            "change_set_id": built["id"],
            "verdict": "request_changes",
            "reviewer": "agent-b",
            "reasons": [
                {"path": path, "line": 1, "why": "the second line needs a reason"},
            ],
        }
    }


def test_a_review_falls_back_to_the_owner_the_register_names(client):
    """Given provenance that names no agent; Then the tree's owner is the author it holds."""
    created = _create(client, owner="agent-a")
    _edit_tree(created["path"])
    built = _build(client, created["id"], provenance={"why": "the wave asked for it"})
    path = built["files"][0]["path"]

    def review(reviewer: str):
        return client.post(
            f"/api/change-sets/{built['id']}/review",
            json={"verdict": "approve", "reviewer": reviewer, "reasons": [_reason(path)]},
        )

    assert review("agent-a").status_code == 422
    assert review("agent-b").status_code == 200


def test_a_review_is_refused_when_nobody_is_named_at_all(client, tmp_path):
    """Given a set whose workspace is unregistered and whose provenance names nobody."""
    repo = tmp_path / "managed" / "spare"
    repo.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], repo)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(["add", "a.txt"], repo)
    _git(["-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "in"], repo)
    (repo / "a.txt").write_text("a\nb\n", encoding="utf-8")
    built = _build(client, str(repo), provenance={"why": "no agent took this one"})

    res = client.post(
        f"/api/change-sets/{built['id']}/review",
        json={"verdict": "approve", "reviewer": "agent-b", "reasons": [_reason("a.txt")]},
    )
    assert res.status_code == 422, res.text
    assert "names no author" in _message(res)
    assert _code(res) == "change_set_no_author"


# The publish surface


def test_a_dry_run_reports_without_an_approval_and_moves_no_ref(client, checkout):
    """Given a set nobody approved; Then a dry run answers and the branch stays put."""
    before = _git(["rev-parse", "refs/heads/main"], checkout).strip()
    created = _create(client)
    _edit_tree(created["path"])
    built = _build(client, created["id"])

    res = client.post(f"/api/change-sets/{built['id']}/publish", json={"dry_run": True})
    assert res.status_code == 200, res.text
    result = res.json()["result"]
    assert result["ok"] is True
    assert result["applied"] == [built["files"][0]["path"]]
    assert result["rolled_back"] == []
    assert "dry run" in result["reason"]
    assert _git(["rev-parse", "refs/heads/main"], checkout).strip() == before


def test_publishing_is_refused_until_a_second_agent_approves(client):
    """Given the author's own set; Then 409, and one approval by another agent opens it."""
    created = _create(client)
    _edit_tree(created["path"])
    built = _build(client, created["id"])

    refused = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert refused.status_code == 409, refused.text
    assert "no approval" in _message(refused)
    assert _code(refused) == "publish_without_approval"

    assert _approve(client, built).status_code == 200
    assert client.post(f"/api/change-sets/{built['id']}/publish", json={}).status_code == 200


def test_publishing_lands_the_whole_set_on_the_target_branch(client, checkout):
    """Given an approved set; Then the target carries every path, and the tree is untouched."""
    created = _create(client)
    _edit_tree(created["path"])
    (Path(created["path"]) / "new.txt").write_text("new\n", encoding="utf-8")
    built = _build(client, created["id"])
    assert _approve(client, built).status_code == 200

    res = client.post(
        f"/api/change-sets/{built['id']}/publish", json={"target": "main"}
    )
    assert res.status_code == 200, res.text
    result = res.json()["result"]
    assert result["ok"] is True
    assert sorted(result["applied"]) == ["README.md", "new.txt"]
    assert result["rolled_back"] == []

    assert _git(["show", "main:README.md"], checkout) == "the checkout\nedited\n"
    assert _git(["show", "main:new.txt"], checkout) == "new\n"
    # A publish moves the ref; the tree that asked for it keeps its own bytes.
    assert (Path(created["path"]) / "new.txt").is_file()


def test_publishing_is_refused_when_the_tree_moved_after_the_record(client):
    """Given an approved set and an edit made after it; Then 409 names the drifted path."""
    created = _create(client)
    _edit_tree(created["path"])
    built = _build(client, created["id"])
    assert _approve(client, built).status_code == 200
    _edit_tree(created["path"], "and again\n")

    refused = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert refused.status_code == 409, refused.text
    assert _message(refused) == (
        "the tree moved after this set was recorded: README.md — record the set again and publish"
    )
    assert _code(refused) == "publish_tree_moved"

    # The set built after the edit is the one the tree now holds, so it publishes — and an
    # absent body is the module's own target, the way an absent reap body is its own grace.
    fresh = _build(client, created["id"])
    assert _approve(client, fresh).status_code == 200
    assert client.post(f"/api/change-sets/{fresh['id']}/publish").status_code == 200


def test_publishing_is_refused_when_the_tree_is_gone(client, tmp_path):
    """Given an approved set whose workspace directory was taken away; Then 409, not 500."""
    repo = tmp_path / "managed" / "spare"
    repo.mkdir(parents=True)
    _git(["init", "-q", "-b", "main"], repo)
    (repo / "a.txt").write_text("a\n", encoding="utf-8")
    _git(["add", "a.txt"], repo)
    _git(["-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-qm", "in"], repo)
    (repo / "a.txt").write_text("a\nb\n", encoding="utf-8")
    built = _build(client, str(repo))
    assert _approve(client, built).status_code == 200

    import shutil

    shutil.rmtree(repo)
    refused = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert refused.status_code == 409, refused.text
    assert "not a directory" in _message(refused)
    assert _code(refused) == "change_set_tree_gone"


# The collision surface


def _build_full(client: TestClient, workspace_id: str, provenance: dict | None = None) -> dict:
    """The whole build envelope: the set, and the runs the router read back beside it."""
    res = client.post(
        "/api/change-sets",
        json={
            "workspace_id": workspace_id,
            "summary": "one edit and one new file",
            "provenance": PROVENANCE if provenance is None else provenance,
        },
    )
    assert res.status_code == 200, res.text
    return res.json()


BY_SECOND = {"session_id": "s-2", "agent_id": "agent-b", "why": "the other half of the wave"}


def test_a_second_builder_is_told_in_its_own_answer_which_run_is_in_the_file(client):
    """Given a path one run already holds; Then the next build names it, before any publish."""
    first = _create(client, "agent-a")
    _edit_tree(first["path"])
    assert _build_full(client, first["id"])["conflicts"] == [], "nobody else is in the file yet"

    second = _create(client, "agent-b")
    _edit_tree(second["path"], "by the second run\n")
    body = _build_full(client, second["id"], BY_SECOND)

    rows = body["conflicts"]
    assert [row["path"] for row in rows] == ["README.md"]
    holders = rows[0]["holders"]
    assert [holder["author"] for holder in holders] == ["agent-a"]
    assert holders[0]["state"] == "draft"
    assert holders[0]["since"], "the reader is told since when, not only who"
    assert holders[0]["change_set_id"]
    assert holders[0]["op"] == "modify"
    assert holders[0]["diff_sha"].startswith("sha256:")


def test_publishing_is_refused_until_the_other_run_is_named(client):
    """Given two approved runs on one path; Then 409 names the holder, and force is the move."""
    first = _create(client, "agent-a")
    _edit_tree(first["path"])
    mine = _build(client, first["id"])
    assert _approve(client, mine).status_code == 200

    second = _create(client, "agent-b")
    _edit_tree(second["path"], "by the second run\n")
    theirs = _build(client, second["id"], BY_SECOND)
    assert _approve(client, theirs, reviewer="agent-c").status_code == 200

    refused = client.post(f"/api/change-sets/{mine['id']}/publish", json={"target": "main"})
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "publish_path_claimed"
    assert "agent-b" in _message(refused), "the refusal names the other run, not just the path"
    assert "README.md" in _message(refused)

    landed = client.post(
        f"/api/change-sets/{mine['id']}/publish", json={"target": "main", "force": True}
    )
    assert landed.status_code == 200, landed.text
    assert landed.json()["result"]["ok"] is True


def test_a_dry_run_reports_a_collision_and_still_moves_no_ref(client, checkout):
    """Given two runs on one path; Then the rehearsal answers with the holder and no refusal."""
    before = _git(["rev-parse", "refs/heads/main"], checkout).strip()
    first = _create(client, "agent-a")
    _edit_tree(first["path"])
    _build(client, first["id"])
    second = _create(client, "agent-b")
    _edit_tree(second["path"], "by the second run\n")
    theirs = _build(client, second["id"], BY_SECOND)

    res = client.post(f"/api/change-sets/{theirs['id']}/publish", json={"dry_run": True})

    assert res.status_code == 200, res.text
    assert res.json()["result"]["ok"] is True
    assert [holder["author"] for holder in res.json()["conflicts"][0]["holders"]] == ["agent-a"]
    assert _git(["rev-parse", "refs/heads/main"], checkout).strip() == before


def test_a_landing_after_the_record_stops_the_set_that_would_write_over_it(client):
    """Given a set recorded while a peer held the path, and that peer landed since; Then 409."""
    first = _create(client, "agent-a")
    _edit_tree(first["path"])
    older = _build(client, first["id"])
    second = _create(client, "agent-b")
    _edit_tree(second["path"], "by the second run\n")
    newer = _build(client, second["id"], BY_SECOND)
    assert _approve(client, older).status_code == 200

    # The holder lands first, which is the only way out of a refused publish it did not ask for.
    landed = client.post(
        f"/api/change-sets/{older['id']}/publish", json={"target": "main", "force": True}
    )
    assert landed.status_code == 200, landed.text
    assert client.get(f"/api/change-sets/{older['id']}").json()["change_set"]["state"] == "published"

    assert _approve(client, newer, reviewer="agent-c").status_code == 200
    refused = client.post(f"/api/change-sets/{newer['id']}/publish", json={"target": "main"})
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "publish_path_claimed"
    assert "agent-a" in _message(refused), "the run whose bytes are on the branch is the one named"


def test_a_run_recorded_after_a_landing_is_not_refused_for_it(client):
    """Given a branch that already moved before this run branched; Then it publishes freely."""
    first = _create(client, "agent-a")
    _edit_tree(first["path"])
    landed_set = _build(client, first["id"])
    assert _approve(client, landed_set).status_code == 200
    assert client.post(f"/api/change-sets/{landed_set['id']}/publish", json={}).status_code == 200

    second = _create(client, "agent-b")
    _edit_tree(second["path"], "after the landing\n")
    body = _build_full(client, second["id"], BY_SECOND)

    assert body["conflicts"] == [], "a landing older than this record is not a collision"
    fresh = body["change_set"]
    assert _approve(client, fresh, reviewer="agent-c").status_code == 200
    assert client.post(f"/api/change-sets/{fresh['id']}/publish", json={}).status_code == 200


def test_the_claim_list_answers_who_is_in_a_path_and_since_when(client):
    """Given two runs holding one path; Then the read names both, and one bound drops one."""
    first = _create(client, "agent-a")
    _edit_tree(first["path"])
    _build(client, first["id"])
    second = _create(client, "agent-b")
    _edit_tree(second["path"], "by the second run\n")
    _build(client, second["id"], BY_SECOND)

    res = client.get("/api/change-sets/claims")
    assert res.status_code == 200, res.text
    rows = {row["path"]: row["holders"] for row in res.json()["paths"]}
    assert "README.md" in rows
    assert sorted(holder["author"] for holder in rows["README.md"]) == ["agent-a", "agent-b"]
    assert all(holder["since"] for holder in rows["README.md"])
    assert sorted(holder["workspace_id"] for holder in rows["README.md"]) == sorted(
        [first["id"], second["id"]]
    ), "the holder answers in the register's own id form"

    narrowed = client.get(
        "/api/change-sets/claims", params={"path": "README.md", "exclude_workspace": first["id"]}
    )
    assert narrowed.status_code == 200, narrowed.text
    holders = narrowed.json()["paths"][0]["holders"]
    assert [holder["author"] for holder in holders] == ["agent-b"]

    assert client.get("/api/change-sets/claims", params={"path": "nothing.txt"}).json() == {
        "paths": []
    }


# Unknown names


@pytest.mark.parametrize(
    ("method", "path", "code"),
    [
        ("GET", f"/api/workspaces/{MISSING_WORKSPACE}", "workspace_not_live"),
        ("DELETE", f"/api/workspaces/{MISSING_WORKSPACE}", "workspace_not_live"),
        ("GET", f"/api/change-sets/{MISSING_CHANGE_SET}", "change_set_unknown"),
    ],
)
def test_an_unknown_id_answers_404(client, method: str, path: str, code: str):
    """Given a name no store holds; Then 404, the answer this app's routes give for ids."""
    res = client.request(method, path)
    assert res.status_code == 404
    assert _code(res) == code


def test_an_unknown_change_set_answers_404_before_its_body_is_read(client):
    """Given a valid body against a name no store holds; Then the id answers before the body is read."""
    review = client.post(
        f"/api/change-sets/{MISSING_CHANGE_SET}/review",
        json={"verdict": "approve", "reviewer": "agent-b", "reasons": [_reason("a.txt")]},
    )
    assert review.status_code == 404
    assert _code(review) == "change_set_unknown"
    publish = client.post(f"/api/change-sets/{MISSING_CHANGE_SET}/publish", json={})
    assert publish.status_code == 404
    assert _code(publish) == "change_set_unknown"


# The chain of custody


def _custody(client: TestClient, change_set: dict) -> dict:
    res = client.get(f"/api/change-sets/{change_set['id']}/custody")
    assert res.status_code == 200, res.text
    return res.json()


def test_custody_states_the_stop_before_anyone_signed(client):
    """Given a recorded set nobody has signed; Then the refusal is stated before it is asked for."""
    _create(client, "agent-b")
    tree = _create(client)
    _edit_tree(tree["path"])
    change_set = _build(client, tree["path"])
    body = _custody(client, change_set)

    assert body["author"] == "agent-a"
    assert body["approval"] is None
    assert body["publishable"] is False
    assert body["refusal"]["code"] == "publish_without_approval"
    assert "agent-b" in body["custodians"]
    assert "agent-a" not in body["custodians"]


def test_custody_names_the_moved_bytes_after_a_reviewer_signed(client):
    """Given an approved set whose tree moved; Then the drift is named per path, with both digests."""
    _create(client, "agent-b")
    tree = _create(client)
    _edit_tree(tree["path"])
    change_set = _build(client, tree["path"])
    assert _approve(client, change_set).status_code == 200

    first = change_set["files"][0]
    assert _custody(client, change_set)["publishable"] is True

    _edit_tree(tree["path"], "and more\n")
    body = _custody(client, change_set)

    assert body["checked"] is True
    assert body["publishable"] is False
    assert body["refusal"]["code"] == "publish_tree_moved"
    assert first["path"] in body["refusal"]["sentence"]
    moved = [row for row in body["files"] if row["moved"]]
    assert [row["path"] for row in moved] == [first["path"]]
    assert moved[0]["recorded"] == first["diff_sha"]
    assert moved[0]["current"] not in (None, first["diff_sha"])


def test_custody_states_the_sentence_the_publish_would_refuse_with(client):
    """Given a drifted set; Then the sentence read before the publish is the sentence it answers."""
    _create(client, "agent-b")
    tree = _create(client)
    _edit_tree(tree["path"])
    change_set = _build(client, tree["path"])
    _approve(client, change_set)
    _edit_tree(tree["path"], "and more\n")

    stated = _custody(client, change_set)["refusal"]
    published = client.post(f"/api/change-sets/{change_set['id']}/publish", json={})

    assert published.status_code == 409
    assert _code(published) == stated["code"]
    assert _message(published) == stated["sentence"]


def test_custody_is_clean_once_the_record_matches_and_a_reviewer_signed(client):
    """Given an approved set whose tree still matches; Then nothing is refused."""
    _create(client, "agent-b")
    tree = _create(client)
    _edit_tree(tree["path"])
    change_set = _build(client, tree["path"])
    _approve(client, change_set)

    body = _custody(client, change_set)

    assert body["approval"]["reviewer"] == "agent-b"
    assert body["approval"]["reasons"][0]["why"] == "this line reads wrong"
    assert body["refusal"] is None
    assert body["publishable"] is True
    assert all(not row["moved"] and row["current"] == row["recorded"] for row in body["files"])


def test_custody_answers_an_unknown_id_the_way_every_other_read_does(client):
    """Given a name no store holds; Then 404 with the code this app's id routes carry."""
    res = client.get(f"/api/change-sets/{MISSING_CHANGE_SET}/custody")

    assert res.status_code == 404
    assert _code(res) == "change_set_unknown"


# The loop: a verdict moves the set it decided, a set sent back is amended under its own id,
# and only an approved set publishes. Before this the state never moved off `draft`, so a
# reviewer read the word for a stage the record had left out.


def _review(client: TestClient, change_set: dict, verdict: str, why: str = "this line reads wrong"):
    first = change_set["files"][0]["path"]
    return client.post(
        f"/api/change-sets/{change_set['id']}/review",
        json={"verdict": verdict, "reviewer": "agent-b", "reasons": [_reason(first, why)]},
    )


def _stored_state(client: TestClient, change_set_id: str) -> str:
    return client.get(f"/api/change-sets/{change_set_id}").json()["change_set"]["state"]


def _built(client: TestClient) -> tuple[dict, dict]:
    created = _create(client)
    _edit_tree(created["path"])
    return created, _build(client, created["id"])


def test_a_verdict_moves_the_set_it_decided(client):
    """Given a draft; Then each verdict leaves the record in the stage it reached."""
    _, built = _built(client)
    assert _stored_state(client, built["id"]) == "draft"

    assert _review(client, built, "request_changes").status_code == 200
    assert _stored_state(client, built["id"]) == "review"

    assert _review(client, built, "approve").status_code == 200
    assert _stored_state(client, built["id"]) == "approved"

    assert _review(client, built, "reject").status_code == 200
    assert _stored_state(client, built["id"]) == "rejected"


def test_publishing_moves_an_approved_set_to_published(client):
    """Given an approved set; Then the publish that lands moves it past approved to published."""
    _, built = _built(client)
    assert _approve(client, built).status_code == 200
    assert _stored_state(client, built["id"]) == "approved"

    done = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert done.status_code == 200, done.text
    assert done.json()["result"]["ok"] is True
    assert _stored_state(client, built["id"]) == "published"


def test_a_publish_sentence_names_what_landed(client):
    """Given an approved set that lands; Then the sentence names the files that landed."""
    _, built = _built(client)
    _approve(client, built)
    body = client.post(f"/api/change-sets/{built['id']}/publish", json={}).json()

    assert body["result"]["applied"] == ["README.md"]
    assert body["sentence"].startswith("published 1 file(s) to main")
    assert "README.md" in body["sentence"]


def test_a_rehearsal_says_what_would_land_and_moves_nothing(client):
    """Given a draft; Then a dry run names the count and leaves every state where it stood."""
    _, built = _built(client)
    body = client.post(f"/api/change-sets/{built['id']}/publish", json={"dry_run": True}).json()

    assert "dry run" in body["sentence"]
    assert _stored_state(client, built["id"]) == "draft"


def test_the_lifecycle_endpoint_names_the_stage_the_line_and_the_reasons(client):
    """Given a set sent back; Then the life names where it stands and what the verdict said."""
    _, built = _built(client)
    why = "the second line needs a reason"
    assert _review(client, built, "request_changes", why).status_code == 200

    life = client.get(f"/api/change-sets/{built['id']}/lifecycle").json()["lifecycle"]

    assert life["change_set_id"] == built["id"]
    assert life["state"] == "review"
    assert [row["name"] for row in life["stations"]] == [
        "draft", "review", "approved", "published",
    ]
    assert [row["name"] for row in life["stations"] if row["current"]] == ["review"]
    assert life["verdict"]["reviewer"] == "agent-b"
    assert life["reasons"] == [{"path": built["files"][0]["path"], "line": 1, "why": why}]
    assert life["withdraw"] == ["draft"]
    assert life["decidable"] is True
    assert life["amendable"] is True
    assert life["can_publish"] is False


def test_the_lifecycle_is_read_for_a_name_no_store_holds(client):
    """Given an id nothing was filed under; Then the life answers 404 like every other read."""
    res = client.get(f"/api/change-sets/{MISSING_CHANGE_SET}/lifecycle")
    assert res.status_code == 404
    assert _code(res) == "change_set_unknown"


def test_amending_keeps_the_id_the_provenance_and_stands_the_set_in_draft(client):
    """Given a set sent back and a tree edited again; Then the same set describes the new tree."""
    created, built = _built(client)
    _edit_tree(created["path"], "and again\n")

    res = client.post(f"/api/change-sets/{built['id']}/amend", json={})
    assert res.status_code == 200, res.text
    amended = res.json()["change_set"]

    assert amended["id"] == built["id"]
    assert amended["workspace_id"] == built["workspace_id"]
    assert amended["provenance"] == built["provenance"]
    assert amended["created_at"] == built["created_at"]
    assert amended["state"] == "draft"
    assert amended["files"][0]["diff_sha"] != built["files"][0]["diff_sha"]
    # The store keeps one record, under the same id — not a second set beside the first.
    assert client.get(f"/api/change-sets/{built['id']}").json()["change_set"] == amended


def test_an_amended_set_may_not_publish_on_the_approval_it_no_longer_earned(client):
    """Given an approval, then an amend; Then the refusal names the superseded approval."""
    created, built = _built(client)
    assert _approve(client, built).status_code == 200
    _edit_tree(created["path"], "and again\n")
    assert client.post(f"/api/change-sets/{built['id']}/amend", json={}).status_code == 200

    refused = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "change_set_approval_superseded"
    assert "filed against bytes an amend replaced" in _message(refused)


def test_an_amended_tree_is_what_a_fresh_approval_then_publishes(client):
    """Given the amended set approved again; Then the publish lands the bytes on disk now."""
    created, built = _built(client)
    _edit_tree(created["path"], "and again\n")
    amended = client.post(f"/api/change-sets/{built['id']}/amend", json={}).json()["change_set"]
    assert _approve(client, amended).status_code == 200

    done = client.post(f"/api/change-sets/{built['id']}/publish", json={})
    assert done.status_code == 200, done.text
    assert done.json()["result"]["applied"] == ["README.md"]


def test_amending_a_published_set_answers_409(client):
    """Given a set already on the branch; Then amend names the one way left: a new set."""
    _, built = _built(client)
    _approve(client, built)
    assert client.post(f"/api/change-sets/{built['id']}/publish", json={}).status_code == 200

    refused = client.post(f"/api/change-sets/{built['id']}/amend", json={})
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "change_set_amend_refused"
    assert _stored_state(client, built["id"]) == "published"


def test_a_surface_may_reopen_a_set_by_hand_and_nothing_else(client):
    """Given an approved set; Then the hand move reopens it, and every earned state is refused."""
    _, built = _built(client)
    _approve(client, built)

    reopened = client.post(f"/api/change-sets/{built['id']}/state", json={"state": "draft"})
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["change_set"]["state"] == "draft"
    assert _stored_state(client, built["id"]) == "draft"

    for earned in ("approved", "published", "rejected"):
        refused = client.post(f"/api/change-sets/{built['id']}/state", json={"state": earned})
        assert refused.status_code == 409, (earned, refused.text)
        assert _code(refused) == "change_set_state_reserved"
    assert _stored_state(client, built["id"]) == "draft"


def test_a_hand_move_the_loop_turns_down_answers_422(client):
    """Given a draft asked to reopen as a draft; Then the loop refuses the move itself."""
    _, built = _built(client)
    res = client.post(f"/api/change-sets/{built['id']}/state", json={"state": "draft"})

    assert res.status_code == 422, res.text
    assert _code(res) == "change_set_state_refused"
    assert "does not move to" in _message(res)


def test_a_hand_move_for_a_name_no_store_holds_answers_404(client):
    """Given an id nothing was filed under; Then the move answers 404 like every other read."""
    res = client.post(f"/api/change-sets/{MISSING_CHANGE_SET}/state", json={"state": "draft"})
    assert res.status_code == 404
    assert _code(res) == "change_set_unknown"


def test_amending_a_set_whose_tree_is_gone_answers_409(client, tmp_path):
    """Given a set whose workspace directory was taken away; Then the answer is 409."""
    created, built = _built(client)
    import shutil

    shutil.rmtree(created["path"])
    refused = client.post(f"/api/change-sets/{built['id']}/amend", json={})
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "change_set_tree_gone"


def test_amending_a_set_whose_tree_holds_no_change_answers_409(client):
    """Given a tree put back the way HEAD holds it; Then the amend is refused outright."""
    created, built = _built(client)
    (Path(created["path"]) / "README.md").write_text("the checkout\n", encoding="utf-8")

    refused = client.post(f"/api/change-sets/{built['id']}/amend", json={})
    assert refused.status_code == 409, refused.text
    assert _code(refused) == "change_set_amend_refused"
    assert client.get(f"/api/change-sets/{built['id']}").json()["change_set"]["files"] == built["files"]


def test_the_review_list_carries_why_a_set_was_sent_back(client):
    """Given a set sent back with a located reason; Then the list carries verdict and reason."""
    created, built = _built(client)
    first = built["files"][0]["path"]
    sent_back = client.post(
        f"/api/change-sets/{built['id']}/review",
        json={"verdict": "request_changes", "reviewer": "agent-b",
              "reasons": [_reason(first, "the second line needs a reason")]},
    )
    assert sent_back.status_code == 200, sent_back.text

    rows = client.get("/api/change-sets", params={"workspace_id": created["id"]}).json()
    row = next(entry for entry in rows["change_sets"] if entry["id"] == built["id"])

    assert row["latest"]["verdict"] == "request_changes"
    assert row["latest"]["reviewer"] == "agent-b"
    assert row["latest"]["reasons"] == [
        {"path": first, "line": 1, "why": "the second line needs a reason"}
    ]


def test_a_landing_records_the_oid_the_publish_wrote(client, checkout):
    """Given an approved set; When it publishes; Then the record names the commit it landed as."""
    created, built = _built(client)
    assert _approve(client, built).status_code == 200
    assert client.post(f"/api/change-sets/{built['id']}/publish", json={}).status_code == 200

    landed = client.get(f"/api/change-sets/{built['id']}").json()["change_set"]
    assert landed["state"] == "published"
    assert landed["published_oid"] == _git(["rev-parse", "refs/heads/main"], checkout).strip()


def test_a_landing_can_be_taken_back_and_the_set_may_land_again(client):
    """Given a published set; Then an unpublish leaves it a draft the loop carries again."""
    created, built = _built(client)
    assert _approve(client, built).status_code == 200
    assert client.post(f"/api/change-sets/{built['id']}/publish", json={}).status_code == 200

    reverted = client.post(f"/api/change-sets/{built['id']}/unpublish")
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["change_set"]["state"] == "draft"

    life = client.get(f"/api/change-sets/{built['id']}/lifecycle").json()["lifecycle"]
    assert life["state"] == "draft"
    assert life["amendable"] is True
    assert life["can_publish"] is False


def test_an_unpublish_of_a_set_that_never_landed_answers_409(client):
    """Given a draft; When an unpublish is asked for; Then 409 names the rule it broke."""
    created, built = _built(client)

    refused = client.post(f"/api/change-sets/{built['id']}/unpublish")

    assert refused.status_code == 409, refused.text
    assert _code(refused) == "change_set_unpublish_refused"
    assert "has no landing to take back" in _message(refused)


def test_an_unpublish_of_a_name_no_store_holds_answers_404(client):
    """Given an id nothing was filed under; Then the unpublish answers 404 like every read."""
    res = client.post(f"/api/change-sets/{MISSING_CHANGE_SET}/unpublish")
    assert res.status_code == 404
    assert _code(res) == "change_set_unknown"
