"""An `env:` block may not reach for a context that is out of scope at its level.

Found on the push of `6e5fe969`: `lint.yml` put `${{ runner.temp }}/ephe-lint` in the file's top-level
`env:` block, GitHub refused to validate the whole workflow, and the result was a run with **zero
jobs, no log at all, and `.github/workflows/lint.yml` printed where the `name:` should be**. Nothing in
our tooling reads that shape: there is no step to inspect, no annotation, and `hygiene` and the test
suite stayed green because the leg simply did not exist. It is the same failure family as the job whose
five steps were `[]` because the account could not allocate it -- a red that carries no evidence.

The rule, from GitHub's context availability: a workflow-level `env` has `github`, `inputs`, `secrets`
and `vars` in scope, and `jobs.<job_id>.env` adds `needs`, `strategy` and `matrix` -- but `runner`,
`steps` and `job` are in scope **only in a step**. Moving the four scratch roots from workflow scope to
job scope therefore did not fix them: the legs still arrived with zero jobs, and it took a second pass
to see that `jobs.<job_id>.env` is not the step scope either. A reference to a context that is out of
scope does not degrade to an empty string at run time -- it invalidates the file.

The guard decides line numbers from the raw text so a refusal can be acted on, and it is tested in both
directions: a planted `runner.temp` at workflow or job scope goes red naming the file and the line,
while the step-level uses this repository relies on do not.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: Contexts GitHub keeps out of scope in a workflow-level `env:` block.
JOB_ONLY = ("runner", "needs", "matrix", "strategy", "steps", "job", "services")
#: Contexts a job-level `env:` block still cannot reach; only a step can.
STEP_ONLY = ("runner", "steps", "job", "jobs")
REFERENCE = re.compile(r"\$\{\{\s*(" + "|".join(JOB_ONLY + STEP_ONLY) + r")\.([A-Za-z0-9_.-]+)")


def workflow_env_values(text: str) -> list[tuple[str, str, int]]:
    """(key, value, line) for every entry in a file's top-level `env:` block.

    `yaml.compose` rather than `safe_load`: the node graph carries the mark, so a refusal can quote the
    line the owner has to open, and a flow-style block (`env: {A: ${{ runner.temp }}}`) is walked the
    same way as the block style every file here uses.
    """
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        return []
    out: list[tuple[str, str, int]] = []
    for key, value in root.value:
        if key.value != "env" or not isinstance(value, yaml.MappingNode):
            continue
        for entry_key, entry_value in value.value:
            text_value = getattr(entry_value, "value", "")
            if isinstance(text_value, str):
                out.append((str(entry_key.value), text_value, int(entry_value.start_mark.line) + 1))
    return out


def job_env_values(text: str) -> list[tuple[str, str, int]]:
    """(key, value, line) for every entry in every `jobs.<id>.env:` block."""
    root = yaml.compose(text)
    if not isinstance(root, yaml.MappingNode):
        return []
    out: list[tuple[str, str, int]] = []
    for key, value in root.value:
        if key.value != "jobs" or not isinstance(value, yaml.MappingNode):
            continue
        for _job_id, job in value.value:
            if not isinstance(job, yaml.MappingNode):
                continue
            for job_key, env_node in job.value:
                if job_key.value != "env" or not isinstance(env_node, yaml.MappingNode):
                    continue
                for entry_key, entry_value in env_node.value:
                    text_value = getattr(entry_value, "value", "")
                    if isinstance(text_value, str):
                        out.append(
                            (str(entry_key.value), text_value, int(entry_value.start_mark.line) + 1)
                        )
    return out


def _report(scope: str, key: str, value: str, line: int, out_of_scope: tuple[str, ...]) -> str | None:
    match = REFERENCE.search(value)
    if not match or match.group(1) not in out_of_scope:
        return None
    context = match.group(1)
    expression = "$" + "{{ " + context + ".… }}"
    return (
        f"{line}: {scope} env `{key}` references {expression} and `{context}` is not in scope there;"
        " move it into the step that uses it, or the whole file fails validation and the run arrives"
        " with no jobs and no log"
    )


def findings(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    reported = []
    for key, value, line in workflow_env_values(text):
        note = _report("workflow-level", key, value, line, JOB_ONLY)
        if note:
            reported.append(f"{path.name}:{note}")
    for key, value, line in job_env_values(text):
        note = _report("job-level", key, value, line, STEP_ONLY)
        if note:
            reported.append(f"{path.name}:{note}")
    return reported


#: Property accesses on `github.event` that no payload GitHub sends defines. A reference to one is a
#: validation failure, not an empty string: `github.event.len` in hygiene.yml's `fetch-depth` kept
#: the whole leg from starting (four pushes, zero jobs, the path where the name belongs) until it
#: was replaced with a constant.
BAD_EVENT_PROPERTY = re.compile(r"github\.event\.(?:len|length|count)\b")


def event_property_findings(path: Path) -> list[str]:
    """Only expressions are judged; a comment that names the bad property is how it gets explained."""
    out = []
    for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = BAD_EVENT_PROPERTY.search(text.split("#", 1)[0])
        if match:
            out.append(
                f"{path.name}:{line}: `{match.group(0)}` is not a field of any event payload; the"
                " reference invalidates the whole workflow and the run arrives with no jobs and no log"
            )
    return out


def planted_workflow(tmp: Path, value: str) -> Path:
    target = tmp / "planted.yml"
    target.write_text(
        "name: Planted\n\non:\n  push:\n    branches: [ main ]\n\n"
        f"env:\n  EPHE_SCRATCH: {value}\n\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: echo hi\n",
        encoding="utf-8",
    )
    return target


class TestGuardOnTheRepository:
    def test_no_workflow_scope_entry_reaches_for_a_job_only_context(self):
        offenders: list[str] = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            offenders.extend(findings(path))
        assert not offenders, "\n".join(offenders)

    def test_the_four_scratch_roots_this_lane_moved_are_now_step_scoped(self):
        """`6e5fe969` pushed three of them at workflow scope; the fourth was in the unpushed set."""
        for name in ("lint.yml", "docklint.yml", "lockfile.yml", "asset-checks.yml"):
            keys = [key for key, _, _ in workflow_env_values((WORKFLOWS / name).read_text("utf-8"))]
            keys += [key for key, _, _ in job_env_values((WORKFLOWS / name).read_text("utf-8"))]
            assert not any("VENV" in key or "TOOLS" in key for key in keys), f"{name}: {keys}"

    def test_the_uses_that_are_correct_today_are_not_flagged(self):
        """Positive control: the same `runner.temp` at step scope is legal and common here."""
        legal = [name for name in ("tests.yml", "ci-gates.yml", "supply-chain.yml", "clean-room.yml")
                 if "runner.temp" in (WORKFLOWS / name).read_text(encoding="utf-8")]
        assert len(legal) >= 3, legal
        for name in legal:
            assert findings(WORKFLOWS / name) == [], name


class TestPlant:
    def test_a_workflow_level_runner_reference_is_refused_with_file_and_line(self, tmp_path):
        target = planted_workflow(tmp_path, "${{ runner.temp }}/scratch")
        reported = findings(target)
        assert len(reported) == 1, reported
        assert "planted.yml:8:" in reported[0], reported[0]
        assert "EPHE_SCRATCH" in reported[0] and "no jobs and no log" in reported[0], reported[0]

    def test_a_job_level_runner_reference_is_refused_too(self, tmp_path):
        """Job scope is not step scope: `runner` is still absent from `jobs.<id>.env`."""
        target = tmp_path / "job_scoped.yml"
        target.write_text(
            "name: Job scoped\n\non: push\n\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
            "    env:\n      EPHE_SCRATCH: ${{ runner.temp }}/scratch\n"
            "    steps:\n      - run: echo hi\n",
            encoding="utf-8",
        )
        reported = findings(target)
        assert len(reported) == 1, reported
        assert "job-level env `EPHE_SCRATCH`" in reported[0], reported[0]

    def test_needs_and_matrix_at_the_same_scope_are_refused_too(self, tmp_path):
        for value, context in (("${{ needs.build.outputs.x }}", "needs"),
                               ("${{ matrix.os }}", "matrix"),
                               ("${{ steps.a.outputs.b }}", "steps")):
            reported = findings(planted_workflow(tmp_path, value))
            assert reported, value
            assert f"`{context}` is not in scope there" in reported[0], reported[0]

    def test_the_in_scope_contexts_are_left_alone(self, tmp_path):
        for value in ("${{ github.workspace }}", "${{ secrets.TOKEN }}", "${{ vars.RUNNER }}",
                      "${{ inputs.thing }}", "/tmp/plain"):
            assert findings(planted_workflow(tmp_path, value)) == [], value

    def test_a_step_scoped_reference_is_not_reported(self, tmp_path):
        target = tmp_path / "step_scoped.yml"
        target.write_text(
            "name: Step scoped\n\non: push\n\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
            "    steps:\n      - run: echo hi\n"
            "        env:\n          EPHE_SCRATCH: ${{ runner.temp }}/scratch\n",
            encoding="utf-8",
        )
        assert findings(target) == []

    def test_a_workflow_without_an_env_block_cannot_produce_a_finding(self, tmp_path):
        target = tmp_path / "no_env.yml"
        target.write_text("name: No env\n\non: push\n\njobs:\n  x:\n    runs-on: ubuntu-latest\n"
                          "    steps: []\n", encoding="utf-8")
        assert findings(target) == []


class TestInvalidEventProperties:
    def test_no_workflow_reads_a_property_no_payload_defines(self):
        offenders = [f for path in sorted(WORKFLOWS.glob("*.yml"))
                     for f in event_property_findings(path)]
        assert not offenders, "\n".join(offenders)

    def test_a_planted_invalid_property_is_refused_with_file_and_line(self, tmp_path):
        target = planted_workflow(tmp_path, "${{ github.event.len + 1 }}")
        reported = event_property_findings(target)
        assert len(reported) == 1, reported
        assert "planted.yml:8:" in reported[0], reported


class TestTheSymptomStaysReadable:
    """Every workflow declares `name:`, so a file path in the run list means one thing.

    The visible half of the incident: `Python lint and types` became `.github/workflows/lint.yml`
    because a workflow whose expressions fail validation is listed by path. If a file ever lacked a
    name, the two causes would be indistinguishable from the run list and the first would be read as
    cosmetic.
    """

    def test_every_workflow_names_itself(self):
        missing = [
            path.name for path in sorted(WORKFLOWS.glob("*.yml"))
            if not (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("name")
        ]
        assert not missing, f"workflows without a name:, so a validation failure is invisible: {missing}"

    def test_the_four_legs_that_had_the_defect_still_carry_their_names(self):
        for name, expected in (("lint.yml", "Python lint and types"),
                               ("docklint.yml", "Container and shell lint"),
                               ("lockfile.yml", "Lockfile agreement"),
                               ("asset-checks.yml", "Shipped asset checks")):
            document = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
            assert document["name"] == expected, name
