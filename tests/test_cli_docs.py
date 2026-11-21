"""Every verb the CLI offers has a home in a document a human reads.

The parser is the only place the verb list exists and the documents are the only place the
promise lives; the product cannot import a markdown file, so holding the two together needs a
test that reads text. `docs/CLI.md` and the README are the two surfaces the command speaks
through. The product reads `_actions` the same way to print usage (`ephe_cli.py`, the loops over
`build_parser()._actions` and `parser._actions`).
"""
from __future__ import annotations

import argparse
import pathlib
import re

import ephe_cli

DOC_FILES = (pathlib.Path("docs/CLI.md"), pathlib.Path("README.md"))


def _verbs() -> list[str]:
    parser = ephe_cli.build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    raise AssertionError("the parser has no subcommands at all — this test would prove nothing")


def test_every_cli_verb_is_named_in_a_document() -> None:
    verbs = _verbs()
    # A lookup that came back empty would let the assertion below pass for free.
    assert len(verbs) > 20 and "start" in verbs, f"unexpected verb set: {verbs}"
    text = "\n".join(path.read_text(encoding="utf-8") for path in DOC_FILES)
    silent = [verb for verb in verbs if f"ephe {verb}" not in text]
    assert not silent, (
        f"verbs no document names: {silent} — `ephe {silent[0] if silent else '?'} --help` works, "
        "so the command exists and no page says it does"
    )


#: ``--flag … is a flag of `a`, `b` and `c`` — the sentence that copies the parser into
#: prose, which is the sentence that goes stale when a verb gains a flag.
_FLAG_SPAN = re.compile(r"`(?P<flag>--[a-z][a-z0-9-]+)[^`]*`")
_CLAIM = " is a flag of "


def _documented_flag_claims(text: str) -> dict[str, set[str]]:
    """``{flag: the verbs the document names for it}``, for every claim the page makes.

    One claim ends where the next flag span begins, so a sentence carrying two of
    them attributes each verb list to its own flag.
    """
    claims: dict[str, set[str]] = {}
    spans = list(_FLAG_SPAN.finditer(text))
    for index, span in enumerate(spans):
        stop = spans[index + 1].start() if index + 1 < len(spans) else len(text)
        window = text[span.end() : stop]
        if _CLAIM not in window:
            continue
        verbs = window.split(_CLAIM, 1)[1].split(".")[0]
        claims[span.group("flag")] = set(re.findall(r"`([a-z][a-z-]+)`", verbs))
    return claims


def _flags_by_verb() -> dict[str, set[str]]:
    """``{flag: the verbs that declare it}``, straight from the parser."""
    declared: dict[str, set[str]] = {}
    for action in ephe_cli.build_parser()._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for verb, sub in action.choices.items():
            for option in (o for a in sub._actions for o in a.option_strings if o.startswith("--")):
                declared.setdefault(option, set()).add(verb)
    return declared


def test_an_enumerated_flag_names_exactly_the_verbs_that_declare_it() -> None:
    """The page may name a flag's verbs or stay quiet, but a named list is held to the parser.

    `scripts/cli_docs_check.py` asks whether a flag is named anywhere, so a verb that
    takes a flag no section of its own documents — and a header sentence that stopped
    listing verbs — both read as documented there. This asks the narrower question the
    page can actually answer: a list it chose to write down has to be the parser's answer.
    """
    claims = _documented_flag_claims(pathlib.Path("docs/CLI.md").read_text(encoding="utf-8"))
    # A page that says nothing about any flag would make the loop below pass for free.
    assert claims, "docs/CLI.md names no flag verbs at all — this guard would prove nothing"
    declared = _flags_by_verb()
    for flag, documented in sorted(claims.items()):
        truth = declared.get(flag)
        assert truth, f"docs/CLI.md enumerates {flag}, which no verb of the parser declares"
        assert documented == truth, (
            f"docs/CLI.md says {flag} is a flag of {sorted(documented)}; the parser defines it "
            f"on {sorted(truth)}"
        )


#: The housekeeping section is prose over a parser fact: which of the three verbs carries
#: `--apply` decides whether a run deletes. A sentence that says so is checked against the
#: parser, so the page cannot promise a preview the verb does not have.
_APPLY_CLAIM = re.compile(r"`(?P<verb>[a-z]+)`")
_APPLY_HEADING = "## `ephe reap`, `ephe prune`, `ephe device`"


def _flags_by_command() -> dict[str, set[str]]:
    """``{verb: the flags it declares}`` — the enumeration helper's mirror image."""
    by_verb: dict[str, set[str]] = {}
    for flag, verbs in _flags_by_verb().items():
        for verb in verbs:
            by_verb.setdefault(verb, set()).add(flag)
    return by_verb


def _housekeeping_section() -> str:
    text = pathlib.Path("docs/CLI.md").read_text(encoding="utf-8")
    start = text.find(_APPLY_HEADING)
    assert start >= 0, f"docs/CLI.md lost the heading {_APPLY_HEADING!r}"
    rest = text[start + len(_APPLY_HEADING) :]
    end = rest.find("\n## ")
    return rest if end < 0 else rest[:end]


def test_the_housekeeping_section_describes_the_apply_flag_the_parser_has() -> None:
    """`reap` acts and the other two plan — the page says so, and the parser decides.

    Each clause of the section carries its own verbs and its own side of `--apply`,
    so a clause naming `prune` and `device` cannot borrow `reap`'s wording, and a verb
    the parser gave `--apply` cannot be described as the one that deletes.
    """
    section = _housekeeping_section()
    by_command = _flags_by_command()
    claimed: set[str] = set()
    for sentence in re.split(r"(?<=\.)\s+", section):
        if "--apply" not in sentence:
            continue
        for clause in re.split(r"[,;]", sentence):
            verbs = _APPLY_CLAIM.findall(clause)
            if not verbs:
                continue
            acts = "acts" in clause
            plans = "plan" in clause or "dry run" in clause
            assert acts != plans, (
                f"a clause about --apply must say which side a verb is on, and this one says "
                f"both or neither: {clause!r}"
            )
            for verb in verbs:
                claimed.add(verb)
                has_apply = "--apply" in by_command.get(verb, set())
                assert has_apply != acts, (
                    f"docs/CLI.md calls `ephe {verb}` the verb that {'acts' if acts else 'plans'}"
                    f" at --apply, yet the parser {'defines' if has_apply else 'defines no'} "
                    "--apply for it"
                )
    # A section that never mentions the flag would let every assertion above pass unused.
    assert claimed == {"reap", "prune", "device"}, f"the section speaks of: {sorted(claimed)}"
