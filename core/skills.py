"""
◑ Ephe – Skills System
core/skills.py

Loads and tests Markdown-based skills.

Skill format (Markdown):
  # skill-name
  **Trigger**: /trigger
  **Description**: the description
  **Tools**: tool1, tool2

  ## System Prompt
  You are a...

  ## Test
  **Input**: test input
  **Expect Tool**: tool_name
  **Expect Contains**: expected text

Skill directories (priority):
  1. ~/.ephe/skills/     (user skills)
  2. skills/                 (built-in skills in the repo)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core import skill_router
from core.engine_config import config_subdir
from core.workspace_rules import workspace_key

if TYPE_CHECKING:
    pass

DEFAULT_USER_SKILLS_DIR = config_subdir("skills")
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"
SKILL_CACHE_TTL_SECONDS = 60.0
_SKILL_LIST_CACHE: dict[tuple[str, str], tuple[float, list["Skill"]]] = {}


def invalidate_skill_cache() -> None:
    """E2: plugin enable/disable must act on the NEXT lookup, not after the
    TTL — the plugin routes call this whenever plugin state flips."""
    _SKILL_LIST_CACHE.clear()
# R16 skill manager: disabled skills (they stay loaded, but are never
# resolved automatically). Persisted separately from the skill list.
DISABLED_SKILLS_FILE = DEFAULT_USER_SKILLS_DIR.parent / "skills_state.json"


# Data Classes

@dataclass
class SkillTest:
    """Test definition inside a skill."""
    input: str = ""
    expect_tool: str = ""
    expect_contains: str = ""


@dataclass
class Skill:
    """A loaded skill object."""
    name: str
    trigger: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    test: SkillTest = field(default_factory=SkillTest)
    # R16 pack format: semantic version from the SKILL.md frontmatter.
    # Flat skills (user CRUD) get "1.0.0" as the default.
    version: str = "1.0.0"
    when_to_use: list[str] = field(default_factory=list)
    when_not_to_use: list[str] = field(default_factory=list)
    quality_profile: str = "standard"
    artifact_types: list[str] = field(default_factory=list)
    allowed_tools: list[str] = field(default_factory=list)
    has_references: bool = False
    reference_text: str = ""
    example_text: str = ""
    # P1-A: inline `## Example` fenced block taken from the SKILL.md body.
    # Injected into the few-shot channel in addition to the examples/ sidecars.
    # Before, this gold-standard block was dead: the system-prompt regex
    # `(?=##|\Z)` stopped at `## Example` and the section reached no field.
    example_block: str = ""
    # P1-2: declares whether the skill has a deterministic fast path
    # (no tool dialog). Precedence annotation for the model.


@dataclass
class SkillTestResult:
    """Result of a skill test."""
    skill_name: str
    passed: bool
    message: str = ""
    tool_called: str = ""
    response: str = ""


# Exception

class SkillLoadError(Exception):
    "Skill file invalid or not found."


def _unreachable_engine_note() -> str:
    """The engine-down note for the engine this skill test really dialled.

    ``OllamaNotReachableError`` is the transport-down bucket of *every*
    provider (an OpenAI-compatible engine raises it too), so its class alone
    cannot name the engine: only a local-Ollama turn may be told to start
    Ollama, or the reader is sent to a program the test never used. The active
    provider decides the sentence, the same way the chat routes decide theirs.
    """
    from core.model_provider import get_active_provider

    active = get_active_provider()
    if getattr(active, "provider", "") == "local_ollama":
        return "Ollama not reachable — test skipped."
    base_url = getattr(active, "base_url", "") or "the configured endpoint"
    return f"Engine not reachable: {base_url} — test skipped."


# Parser

def _parse_frontmatter(content: str) -> tuple[dict[str, object], str]:
    if not content.startswith("---\n"):
        return {}, content
    end = content.find("\n---", 4)
    if end == -1:
        return {}, content
    raw = content[4:end].strip()
    body = content[end + 4:].lstrip()
    meta: dict[str, object] = {}
    current_key: str | None = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and current_key:
            values = meta.setdefault(current_key, [])
            if isinstance(values, list):
                values.append(line[4:].strip())
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        current_key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip("'\"") for item in value[1:-1].split(",") if item.strip()]
            meta[current_key] = items
        elif value:
            meta[current_key] = value.strip("'\"")
        else:
            meta[current_key] = []
    return meta, body


def _as_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _as_bool(value: object) -> bool:
    """P1-2: frontmatter boolean (true/1/yes, case-insensitive)."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "ja"}


#: P1-6 (Deep-Audit 2026-09-13): sidecar budget. References/gold examples get
#: injected into the active system block; without a cap a single golden.md eats
#: 15-25 % of the context on 4b/12b models. An example (few-shot) weighs more
#: than a reference, hence the larger budget for examples.
SIDECAR_MAX_CHARS_REFERENCE = 1200
SIDECAR_MAX_CHARS_EXAMPLE = 1600


def _dedupe_lines(text: str) -> str:
    """P1-6: reduce exactly duplicated non-empty lines per block to their first
    hit. The golden.md files carry their numbered lists twice (block 1 == block 2
    word for word); that is dead weight in the system prompt."""
    seen: set[str] = set()
    out: list[str] = []
    for line in text.splitlines():
        key = line.strip()
        if not key:
            out.append(line)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out)


def _cap_sidecar(text: str, limit: int) -> str:
    """P1-6: cap at the line edge (never cut a list entry in the middle)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    nl = cut.rfind("\n")
    return (cut[:nl] if nl > 0 else cut) + "\n…"


# P1-3 (Deep-Audit 2026-09-14): skill-stratified sidecar budget
# Standard skills: 1600/1200. Artifact/source-based skills need
# more room for complete multi-step few-shot examples.
_SIDECAR_BUDGETS: dict[str, tuple[int, int]] = {
    "standard":        (SIDECAR_MAX_CHARS_EXAMPLE, SIDECAR_MAX_CHARS_REFERENCE),
    "artifact":        (2000, 1400),
    "source_grounded": (2400, 1600),
}


def _read_supporting_text(
    skill_dir: Path,
    folder_name: str,
    quality_profile: str = "standard",
) -> tuple[bool, str, str]:
    """Reads the examples/ and references/ sidecars with a skill-stratified budget."""
    ex_cap, ref_cap = _SIDECAR_BUDGETS.get(quality_profile, _SIDECAR_BUDGETS["standard"])
    reference_parts: list[str] = []
    example_parts: list[str] = []
    for rel, target in (("references", reference_parts), ("examples", example_parts)):
        directory = skill_dir / rel
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.md")):
            body = _dedupe_lines(path.read_text(encoding="utf-8"))
            target.append(f"# {folder_name}/{rel}/{path.name}\n{body}")
    reference_text = _cap_sidecar("\n\n".join(reference_parts), ref_cap)
    example_text = _cap_sidecar("\n\n".join(example_parts), ex_cap)
    return bool(reference_parts or example_parts), reference_text, example_text


def _phrase_score(message: str, reference: str) -> int:
    stop = {
        "a", "an", "and", "the", "for", "with", "user", "asks", "ask", "use",
        "to", "of", "in", "my", "me", "please", "bitte", "und", "der", "die",
        "das", "für", "nur", "only",
        # German filler words — without them any sentence containing "mit/auf/aus"  # language-gate: ignore (quotes the German stopword literals in the set below)
        # routes to some skill (F1: shell prompt -> project-assistant fast path).
        "auf", "mit", "aus", "an", "am", "im", "dem", "den", "des", "vom",
        "von", "zum", "zur", "bei", "nach", "ohne", "über", "unter", "vor",
        "kein", "keine", "keiner", "kein...", "diesem", "diesen", "diese",
        "dieses", "dieser", "jeder", "jedes", "alle", "wird", "werden",
        "wurde", "haben", "habe", "hat", "hatte", "sein", "sind", "war",
        "wenn", "dann", "das", "daß", "damit", "als", "wie", "auch",
        "noch", "schon", "immer", "wieder", "sehr", "etwas", "manche",
    }
    message_words = set(re.findall(r"[a-zA-Z0-9_-]{3,}", message.lower())) - stop
    reference_words = set(re.findall(r"[a-zA-Z0-9_-]{3,}", reference.lower())) - stop
    return len(message_words & reference_words)



# P1-1 (Deep-Audit 2026-09-14): TF-IDF routing + hard veto
_IDF_TABLE: dict = {}
_IDF_TABLE_KEY: tuple | None = None


def _compute_idf_table(skills):
    import math
    n = len(skills)
    if n == 0:
        return {}
    df: dict = {}
    for skill in skills:
        for term in skill.when_to_use:
            for word in re.findall(r"[a-zA-Z0-9_-]{3,}", term.lower()):
                df[word] = df.get(word, 0) + 1
    return {word: math.log(n / count) for word, count in df.items() if count < n}


def _idf_weighted_score(message: str, terms: list, idf_table: dict) -> float:
    """P1-1: Stem-Prefix-matching TF-IDF score (min 3 chars common prefix).

    Handles German inflection: 'test'/'tests', 'schreiben'/'schreibe'  # language-gate: ignore (the inflection pair this matcher handles, quoted verbatim)
    match via their shared 3-character prefix.
    """
    msg_words = sorted(set(re.findall(r"[a-zA-Z0-9_-]{3,}", message.lower())))
    term_words  = sorted(set(re.findall(r"[a-zA-Z0-9_-]{3,}", " ".join(terms).lower())))
    if not msg_words or not term_words:
        return 0.0
    # Stem prefix match: a msg-word matches when it has a term-word as its
    # prefix (>= 3 characters) or the other way round, so an inflected form still matches.
    # F2 parity: at least 2 word overlaps required (prevents a single-word hijack).
    matches: list[str] = []
    for mw in msg_words:
        for tw in term_words:
            n = min(len(mw), len(tw))
            if n >= 3 and mw[:n] == tw[:n]:
                matches.append(tw)
                break
    # F2: at least 2 word overlaps required (prevents a single-word hijack).
    if len(matches) < 2:
        return 0.0
    return sum(idf_table.get(w, 1.0) for w in matches)


def _veto_hit(message: str, when_not_to_use: list) -> bool:
    """P1-1: stem prefix match veto (>= 3 characters of shared prefix).

    A single negative word overlapping the message by a >=3 character
    prefix rules the skill out.
    """
    msg_words = sorted(set(re.findall(r"[a-zA-Z0-9_-]{3,}", message.lower())))
    neg_words = sorted(set(re.findall(r"[a-zA-Z0-9_-]{3,}", " ".join(when_not_to_use).lower())))
    for mw in msg_words:
        for nw in neg_words:
            n = min(len(mw), len(nw))
            if n >= 3 and mw[:n] == nw[:n]:
                return True
    return False


def _parse_skill(name: str, content: str, *, skill_dir: Path | None = None) -> Skill:
    """
    Parses one Markdown skill file.

    Raises:
        SkillLoadError: when required fields are missing
    """
    meta, body = _parse_frontmatter(content)

    # Trigger
    trigger_match = re.search(r"\*\*Trigger\*\*:\s*(\S+)", body)
    trigger = str(meta.get("trigger", "") or "").strip()
    if not trigger_match:
        if not trigger:
            raise SkillLoadError(
                f"skill '{name}': missing required field '**Trigger**:'"
            )
    else:
        trigger = trigger_match.group(1).strip()

    # Description — P1-7: the frontmatter is the only truth; the **Description**-
    # line in the body is only a fallback when the frontmatter field is missing. On a
    # mismatch, warn instead of silently overwriting (routing uses description).
    desc_match = re.search(r"\*\*Description\*\*:\s*(.+)", body)
    description = str(meta.get("description", "") or "").strip()
    if not description and desc_match:
        description = desc_match.group(1).strip()
    elif description and desc_match and desc_match.group(1).strip() != description:
        import warnings as _warnings

        _warnings.warn(
            f"skill '{name}': frontmatter/bold mismatch on 'description'",
            stacklevel=2,
        )

    # Tools — P1-7: same precedence (frontmatter > body fallback + mismatch warning).
    # `[ \t]*(.*)$` put two quantifiers on one space class, which a long body makes
    # quadratic (py/polynomial-redos); `$` is unneeded since `.` stops at the newline,
    # and the per-token `.strip()` below drops the leading blanks.
    tools_match = re.search(r"^\*\*Tools\*\*:(.*)", body, re.MULTILINE)
    tools: list[str] = _as_list(meta.get("tools"))
    if not tools and tools_match:
        tools = [t.strip() for t in tools_match.group(1).split(",") if t.strip()]
    elif tools and tools_match:
        body_tools = [t.strip() for t in tools_match.group(1).split(",") if t.strip()]
        if body_tools and body_tools != tools:
            import warnings as _warnings

            _warnings.warn(
                f"skill '{name}': frontmatter/bold mismatch on 'tools'",
                stacklevel=2,
            )

    # System Prompt (between ## System Prompt and ## Test or the end)
    # The lazy `.*?` under a `(?=##|\Z)` lookahead backtracked quadratically on a
    # long body (py/polynomial-redos); `[^\S\n]` is whitespace minus the line feed,
    # and the section end is a plain string search now.
    sp_head = re.search(r"##[^\S\n]+System Prompt[^\S\n]*\n", body)
    if not sp_head:
        raise SkillLoadError(
            f"skill '{name}': missing '## System Prompt' block"
        )
    _sp_tail = body[sp_head.end():]
    _sp_cut = _sp_tail.find("##")
    system_prompt = (_sp_tail if _sp_cut < 0 else _sp_tail[:_sp_cut]).strip()
    if not system_prompt:
        raise SkillLoadError(
            f"skill '{name}': system prompt is empty"
        )

    # Test Block (optional)
    skill_test = SkillTest()
    test_block_match = re.search(r"##\s+Test\s*\n(.*?)(?:\Z)", body, re.DOTALL)
    if test_block_match:
        tb = test_block_match.group(1)
        inp = re.search(r"\*\*Input\*\*:\s*(.+)", tb)
        exp_tool = re.search(r"\*\*Expect Tool\*\*:\s*(\S+)", tb)
        exp_contains = re.search(r"\*\*Expect Contains\*\*:\s*(.+)", tb)

        skill_test = SkillTest(
            input=inp.group(1).strip() if inp else "",
            expect_tool=exp_tool.group(1).strip() if exp_tool else "",
            expect_contains=exp_contains.group(1).strip() if exp_contains else "",
        )

    has_references = False
    reference_text = ""
    example_text = ""
    # P1-3: determine quality_profile before the sidecar read so that the
    # stratified budget (artifact/source_grounded gets more room) takes effect.
    _artifact_types_raw = _as_list(meta.get("artifact_types"))
    _qp_raw = str(meta.get("quality_profile", "") or ("artifact" if _artifact_types_raw else "standard"))
    if skill_dir:
        has_references, reference_text, example_text = _read_supporting_text(skill_dir, name, _qp_raw)

    # P1-A: extract the inline `## Example` fenced block from the SKILL.md body.
    # The system-prompt regex `(?=##|\Z)` stops at `## Example`, so this
    # gold-standard block reached no field before. It is captured here (with the
    # ```json fences kept for the few-shot format) and folded into example_block
    # and example_text so the model actually sees the concrete trace structure
    # (schema fidelity -> fewer tool errors).
    # Same cut as the system-prompt block: the next `##` heading ends the section,
    # and the lazy quantifier under the lookahead is gone (py/polynomial-redos).
    ex_head = re.search(r"##[^\S\n]+Example[^\S\n]*\n", body)
    example_block = ""
    if ex_head:
        _ex_tail = body[ex_head.end():]
        _ex_cut = re.search(r"^##\s", _ex_tail, re.MULTILINE)
        example_block = (_ex_tail if _ex_cut is None else _ex_tail[:_ex_cut.start()]).strip()
    _ex_cap = _SIDECAR_BUDGETS.get(_qp_raw, _SIDECAR_BUDGETS["standard"])[0]
    if example_block:
        merged = f"{example_text}\n\n{example_block}".strip() if example_text else example_block
        example_text = _cap_sidecar(merged, _ex_cap)

    artifact_types = _artifact_types_raw
    if not artifact_types:
        lowered = f"{name} {trigger} {' '.join(tools)}".lower()
        artifact_types = [
            artifact
            for marker, artifact in (("pdf", "pdf"), ("svg", "svg"), ("chart", "chart"), ("deck", "deck"), ("presentation", "deck"), ("xlsx", "xlsx"), ("excel", "xlsx"), ("docx", "docx"), ("word", "docx"), ("qr", "qrcode"), ("image", "image"), ("bild", "image"), ("video", "video"), ("diagram", "svg"), ("flowchart", "svg"))
            if marker in lowered
        ]

    return Skill(
        name=str(meta.get("name", name) or name),
        trigger=trigger,
        description=description,
        system_prompt=system_prompt,
        tools=tools,
        test=skill_test,
        version=str(meta.get("version", "") or "1.0.0"),
        when_to_use=_as_list(meta.get("when_to_use")),
        when_not_to_use=_as_list(meta.get("when_not_to_use")),
        quality_profile=_qp_raw,
        artifact_types=artifact_types,
        allowed_tools=_as_list(meta.get("allowed_tools")) or list(tools),
        has_references=has_references,
        reference_text=reference_text,
        example_text=example_text,
        example_block=example_block,
    )


# Loader


# Artifact intents (round 10/11): deterministic, BEFORE the fuzzy scoring.
# Failure pattern before: "erstelle … eine PDF" scored only 1 (<2) → model path  # language-gate: ignore (the German utterance quoted from the routing examples this pattern documents)
# without a create_pdf requirement → the promised PDF never got built.
# Both word orders: "erstelle ein PDF" AND "PDF erstellen".  # language-gate: ignore (the German word orders quoted from the routing examples)
_ARTIFACT_VERB = r"(?:erstell\w*|mach(?:e|en)?|baue|bau|build|create|generate|generier\w*|exportier\w*|schreib\w*|zeichn\w*)"
_ARTIFACT_NOUNS: tuple[tuple[str, str], ...] = (
    (r"(?:pdf)s?", "/pdf"),
    (r"(?:decks?|slides?|folien|pptx|powerpoint|pitch\s*decks?)", "/deck"),
    # BEFORE chart: mind map/timeline/flowchart are structure diagrams; the
    # generic "Diagramm" stays with the data chart.  # language-gate: ignore (the German word quoted from the skill-routing examples)
    (r"(?:mindmaps?|mind-?maps?|timelines?|zeitstrahl|zeitlinie|roadmaps?|flowcharts?|flussdiagramm|prozessdiagramm|ablaufdiagramm)", "/diagram"),
    (r"(?:charts?|diagramm(?:e|s)?)", "/chart"),
    (r"svg", "/svg"),
    (r"(?:excel|xlsx|spreadsheet|tabell(?:e|en))", "/xlsx"),
    (r"(?:word|docx)", "/docx"),
    (r"qr-?\s?codes?", "/qr"),
    # Image generation (generate_image) — no overlap with chart/svg;
    # \b prevents false hits inside compounds such as "Bildschirm"/"Bildunterschrift".
    (r"(?:bild(?:er|es|s)?|images?|pictures?|photos?|fotos?|fotografie)", "/image"),
)
_ARTIFACT_INTENTS: tuple[tuple["re.Pattern[str]", str], ...] = tuple(
    (re.compile(
        r"\b" + _ARTIFACT_VERB + r"\b[^.!?]{0,60}?\b" + nouns + r"\b",
        re.IGNORECASE,
    ), skill)
    for nouns, skill in _ARTIFACT_NOUNS
) + tuple(
    (re.compile(
        r"\b" + nouns + r"\b[^.!?]{0,60}?\b" + _ARTIFACT_VERB + r"\b",
        re.IGNORECASE,
    ), skill)
    for nouns, skill in _ARTIFACT_NOUNS
)

# R34 project factory intents: deterministic, AFTER the artifact intents
# ("erstelle ein PDF" stays with /pdf — only whole-project/document wordings  # language-gate: ignore (the German utterance the factory intents must not steal)
# without an artifact noun steer here). The mandatory verb inside the window prevents
# descriptive sentences ("das ist ein komplettes Projekt") from being redirected.  # language-gate: ignore (quoted German example utterance the factory intent must not match)
_FACTORY_VERB = r"(?:erstell\w*|mach(?:e|en)?|bau(?:e)?|build|create|generier\w*|starte|scaffold\w*|bootstrapp?\w*|installier\w*|developp?e?)"
_FACTORY_NOUNS: tuple[tuple[str, str], ...] = (
    (r"\b" + _FACTORY_VERB + r"\b[^.,;!?]{0,45}?\b(?:komplett(?:e|es|en)?|vollst\w*|complete|full|finished|fertige?)\b[^.,;!?]{0,25}?\b(?:projekt(?:e|s)?|projects?|repos?|repositories|anwendung(?:en)?|apps?)\b", "/factory"),
    (r"\b" + _FACTORY_VERB + r"\b[^.,;!?]{0,45}?\b(?:projekt(?:e|s)?|projects?|repos?|apps?)\b[^.,;!?]{0,30}?(?:von\s+grund(?:auf)?|from\s+scratch|komplett(?:e|es)?|complete)\b", "/factory"),
    (r"\b(?:scaffold|boilerplate|boots?trap|ger[üu]st)\b[^.,;!?]{0,30}?\b(?:projekt(?:e|s)?|project|repo|app)\w*", "/factory"),
    (r"\b(?:neues|new|fresh)\s+(?:software[-\s])?(?:projekt|project|repo(?:sitory)?|app)\b", "/factory"),
    (r"\b(?:briefing|whitepaper|research[-\s]?brief|kurzbericht)\b[^.,;!?]{0,30}?(?:pdf|dokument|document)\b", "/doc-factory"),
    (r"\b(?:pdf|dokument|document)\b[^.,;!?]{0,30}?(?:briefing|whitepaper|bericht|zusammenfassung|research|recherche)", "/doc-factory"),
)
_FACTORY_INTENTS: tuple[tuple["re.Pattern[str]", str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), skill)
    for pattern, skill in _FACTORY_NOUNS
)


class SkillLoader:
    """
    Loads skills from Markdown files.

    Looks in:
      1. skills_dir (user skills, default: ~/.ephe/skills/)
      2. BUILTIN_SKILLS_DIR (built-in skills in the repo)
    """

    def __init__(
        self,
        skills_dir: Path | None = None,
        builtin_dir: Path | None = None,
        plugin_root: Path | None = None,
    ) -> None:
        self._user_dir = Path(skills_dir or DEFAULT_USER_SKILLS_DIR)
        self._builtin_dir = Path(builtin_dir or BUILTIN_SKILLS_DIR)
        # E2: manifest plugins (ephe-plugin.json) can bundle skill packs;
        # active packs join the candidate scan (below user/builtin priority).
        self._plugin_root = plugin_root  # None = plugin_manifest default

    # Public API

    def load(self, name: str) -> Skill:
        """
        Loads one skill by name.

        Looks for: {name}.md in user_dir, then builtin_dir.

        Raises:
            SkillLoadError: when the file is not found or invalid
        """
        for directory in [self._user_dir, self._builtin_dir]:
            for path in [directory / f"{name}.md", directory / name / "SKILL.md"]:
                if path.exists():
                    content = path.read_text(encoding="utf-8")
                    skill_dir = path.parent if path.name == "SKILL.md" else directory / name
                    return _parse_skill(name, content, skill_dir=skill_dir)

        raise SkillLoadError(
            f"Skill '{name}' not found in:\n  {self._user_dir}/{name}.md\n  {self._user_dir}/{name}/SKILL.md\n  {self._builtin_dir}/{name}.md\n  {self._builtin_dir}/{name}/SKILL.md"
        )

    def load_all(self) -> list[Skill]:
        """
        Loads every available skill from both directories.
        Skips faulty files (no crash).

        Returns:
            The list of all valid skills.
        """
        cache_key = (workspace_key(self._user_dir), workspace_key(self._builtin_dir), workspace_key(self._plugin_root))
        now = time.monotonic()
        cached = _SKILL_LIST_CACHE.get(cache_key)
        if cached and now - cached[0] < SKILL_CACHE_TTL_SECONDS:
            return cached[1]

        skills: list[Skill] = []
        seen_names: set[str] = set()

        # E2: bundled packs of ACTIVE manifest plugins (own pack dirs).
        plugin_pack_dirs: list[Path] = []
        try:
            from core import plugin_manifest

            plugin_pack_dirs = plugin_manifest.active_skill_roots(self._plugin_root)
        except Exception:
            plugin_pack_dirs = []  # plugins layer must never break skill loading

        for directory in [self._user_dir, self._builtin_dir]:
            if not directory.exists():
                continue
            # `_` prefix = metadata file (e.g. _TEMPLATE.md), not a skill — same idea as
            # Python underscore modules. Keeps the quality suite free of
            # pseudo-skills.
            candidates = [
                (md_file.stem, md_file, directory / md_file.stem)
                for md_file in sorted(directory.glob("*.md"))
                if not md_file.name.startswith("_")
            ]
            candidates.extend(
                (skill_dir.name, skill_dir / "SKILL.md", skill_dir)
                for skill_dir in sorted(p for p in directory.iterdir() if p.is_dir() and (p / "SKILL.md").exists())
            )
            for name, skill_file, skill_dir in candidates:
                if name in seen_names:
                    continue  # the user skill takes priority, do not load twice
                try:
                    skill = _parse_skill(name, skill_file.read_text(encoding="utf-8"), skill_dir=skill_dir)
                    skills.append(skill)
                    seen_names.add(name)
                except SkillLoadError:
                    continue  # skip the faulty file

        # E2: bundled packs of active manifest plugins — lowest priority
        # (user dir and built-ins always win via seen_names dedupe).
        for pack_dir in plugin_pack_dirs:
            name = pack_dir.name
            if name in seen_names:
                continue
            try:
                skill = _parse_skill(name, (pack_dir / "SKILL.md").read_text(encoding="utf-8"), skill_dir=pack_dir)
                skills.append(skill)
                seen_names.add(name)
            except SkillLoadError:
                continue  # skip the faulty file

        _SKILL_LIST_CACHE[cache_key] = (now, skills)
        return skills

    def resolve_trigger(self, trigger: str) -> Skill | None:
        """
        Finds a skill by its trigger.

        Returns:
            The skill object or None when no (enabled) trigger matches.
        """
        for skill in self.load_all():
            if skill.trigger == trigger and not self.is_disabled(skill.name):
                return skill
        return None

    # Round 6: deterministic artifact intents — action verb + artifact noun
    # inside one sentence segment force the skill resolution BEFORE the score threshold.
    # Failure pattern before: "erstelle … eine PDF" scored only 1 (<2) → model path  # language-gate: ignore (the German utterance quoted from the routing examples this pattern documents)
    # without a create_pdf requirement → the promised PDF never got built.
    def resolve_for_message(self, message: str) -> Skill | None:
        """Best-effort automatic skill resolver using positive and negative trigger metadata."""
        return self.route_for_message(message).skill

    def route_for_message(self, message: str) -> skill_router.SkillRoute:
        """Resolve a message to a skill, and to the Decision that chose it.

        The deterministic tiers (factory/artifact intent, named tool) return a
        SkillRoute without a Decision: a rule match is not a choice. The fuzzy
        TF-IDF tier routes through core.decisions (core.skill_router) and always
        carries a Decision — including when the result is "no skill".
        """
        text = (message or "").lower()
        # R34: factory intents first — they demand factory-specific vocabulary
        # (komplett+Projekt, scaffold, briefing/whitepaper) and are therefore  # language-gate: ignore (names the German regex alternatives the factory intents match)
        # less ambiguous than a generic artifact noun ("... PDF").
        for pattern, skill_name in _FACTORY_INTENTS:
            if pattern.search(message or ""):
                resolved = self.resolve_trigger(skill_name)
                if resolved and not self.is_disabled(resolved.name):
                    return skill_router.SkillRoute(resolved)
        # Round 6: the intent rule wins — an explicit "verb + artifact" is
        # high-confidence, however short the skill description is.
        for pattern, skill_name in _ARTIFACT_INTENTS:
            if pattern.search(message or ""):
                resolved = self.resolve_trigger(skill_name)
                if resolved and not self.is_disabled(resolved.name):
                    return skill_router.SkillRoute(resolved)
        # R38: an explicitly named tool is the second strongest signal — the declaring
        # skill wins deterministically (no fuzzy hijack through the score loop;
        # single-word scores stay a barrier >=2). The winner must declare EVERY tool the
        # message names, because that list becomes the session's whole tool array in
        # full-access mode (owner decision 2026-10-10, docs/ENDSTATE_DELTA_2026-10-10.md).
        # Aliases count as their canonical tool, so "read" is measured as read_file.
        from core.tools.registry import TOOL_MAP

        def _canonical(token: str) -> str:
            # A fold is only valid onto a name skills can declare, a registry key.
            name = getattr(TOOL_MAP.get(token), "__name__", "")
            return name if name in TOOL_MAP else token

        named: set[str] = set()
        for raw_token in (message or "").lower().split():
            token = raw_token.strip(".,;:()")
            if token in TOOL_MAP:
                named.add(_canonical(token))
        if named:
            for skill in self.load_all():
                if self.is_disabled(skill.name):
                    continue
                declared = {
                    _canonical(t) for t in (skill.tools or [])
                } | {
                    _canonical(t) for t in (skill.allowed_tools or [])
                }
                if named <= declared:
                    return skill_router.SkillRoute(skill)
        # P1-1: build the IDF table lazily (once per cache fill).
        global _IDF_TABLE, _IDF_TABLE_KEY
        all_skills = self.load_all()
        ck = (workspace_key(self._user_dir), workspace_key(self._builtin_dir))
        if _IDF_TABLE_KEY != ck:
            _IDF_TABLE = _compute_idf_table(all_skills)
            _IDF_TABLE_KEY = ck
        # P1-1 tier 2: the TF-IDF candidates. The winner is chosen through
        # core.decisions.route() (core.skill_router), so the pick is a recorded
        # Decision; the >= 2.0 confidence floor is applied to that Decision.
        candidates: list[skill_router.RouteCandidate] = []
        for skill in all_skills:
            if self.is_disabled(skill.name):
                continue  # R16: disabled skills never route automatically
            # P1-1 tier 2a: hard veto — >=1 overlap with when_not_to_use
            if skill.when_not_to_use and _veto_hit(text, skill.when_not_to_use):
                continue
            # P1-1 tier 2b: IDF-weighted score over when_to_use + description
            positive_terms = [*skill.when_to_use, skill.description, skill.trigger]
            idf_score = _idf_weighted_score(text, positive_terms, _IDF_TABLE)
            # Tiebreaker: when_to_use exact phrase score (direct match count)
            # at an equal IDF score the skill with the more direct
            # when_to_use hit wins (e.g. test-writer vs coding-agent for 'tests').
            wtu_score = _phrase_score(text, " ".join(skill.when_to_use)) if skill.when_to_use else 0
            candidates.append(
                skill_router.RouteCandidate(skill=skill, score=idf_score, phrase=wtu_score)
            )
        return skill_router.route_skills(message or "", candidates)

    def build_skill_index(self, *, max_desc: int = 70) -> str:
        """P1-1: compact, model-visible skill index (name + trigger + 1 line).

        Injected only when the deterministic layer (trigger,
        factory/artifact intent, tool name, phrase score) yields no single
        result — as a semantic fallback before the ask_mode guard.
        It therefore costs context exactly when the regex routing reaches the wrong goal.
        """
        active = [s for s in self.load_all() if not self.is_disabled(s.name)]
        # R45: prioritise by relevance — more when_to_use terms (= broader
        # activation) first, on a tie the shorter description, then the name.
        # Deterministic; keeps the injected index small and the hit rate high.
        active.sort(
            key=lambda s: (
                -len(s.when_to_use or []),
                len((s.description or "").strip()),
                s.name,
            )
        )
        lines: list[str] = []
        for skill in active:
            desc = (skill.description or "").strip().replace("\n", " ")
            if len(desc) > max_desc:
                desc = desc[: max_desc - 1].rstrip() + "…"
            lines.append(f"- {skill.name} ({skill.trigger}): {desc}")
        if not lines:
            return ""
        header = ("Verfuegbare Skills (waehle den passenden Namen; "
                  "kein Treffer -> frei antworten):")
        return header + "\n" + "\n".join(lines)

    def _probe(self, root: Path, name: str) -> bool:
        """True when `<name>.md` or `<name>/SKILL.md` exists below `root`.

        Both candidates are built from the real path of `root` and checked to stay
        under it, so a name that carries a separator or `..` finds nothing instead of
        reaching a file outside the skills directory (py/path-injection).
        """
        base = os.path.realpath(root)
        for rel in (f"{name}.md", os.path.join(str(name), "SKILL.md")):
            target = os.path.realpath(os.path.join(base, rel))
            if not target.startswith(base + os.sep):
                continue
            if os.path.exists(target):
                return True
        return False

    def is_builtin(self, name: str) -> bool:
        """Returns True when the skill is a built-in (not deletable)."""
        return self._probe(self._builtin_dir, name)

    def is_user_skill(self, name: str) -> bool:
        """Returns True when a user skill with this name exists."""
        return self._probe(self._user_dir, name)

    # W3-14: signed skill packs — the verify path on the load side.

    def pack_dir(self, name: str) -> Path | None:
        """The pack directory (one that carries `SKILL.md`) for a name, the
        user directory taking priority over the built-ins. None for a flat
        skill (`{name}.md`) — a single file cannot carry a signature record."""
        for directory in (self._user_dir, self._builtin_dir):
            cand = directory / name
            if (cand / "SKILL.md").is_file():
                return cand
        return None

    def signature_status(self, name: str) -> dict[str, object]:
        """Signature state of a pack, for the load path and the verify route.

        Fail-soft: reports, never raises. A signed pack is verified against its
        CURRENT content with the shared trust anchors; drift or a foreign key
        is reported as `verified=False` with a reason. Unsigned packs (flat
        skills, or packs without a record) report `signed=False, verified=None`
        — the caller decides whether that matters."""
        from core import skill_signing  # lazy: no import cycle with core.skills

        pack = self.pack_dir(name)
        if pack is None:
            return {"signed": False, "verified": None, "reason": "not a pack (flat skill)", "kid": ""}
        record = skill_signing.read(pack)
        if record is None:
            return {"signed": False, "verified": None, "reason": "unsigned", "kid": ""}
        from core.plugin_signing import load_trusted_public_keys

        ok, reason = skill_signing.verify_skill_pack(pack, record, load_trusted_public_keys())
        return {"signed": True, "verified": ok, "reason": reason, "kid": str(record.get("kid", ""))}

    # R16: skill manager (disable / pack delete / cache reset)

    def is_disabled(self, name: str) -> bool:
        """True when the skill is disabled in skills_state.json.

        Disabled skills stay visible in load_all() (UI toggle), but
        resolve_trigger/resolve_for_message never resolve them again.
        """
        try:
            data = json.loads(DISABLED_SKILLS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return False
        return name in {str(n) for n in data.get("disabled", [])}

    def set_disabled(self, name: str, disabled: bool) -> bool:
        """Persists the disabled state atomically (0600) and invalidates the cache.

        Raises:
            SkillLoadError: when the skill does not exist (disabling an unknown name).
        """
        if disabled and not (self.is_builtin(name) or self.is_user_skill(name)):
            raise SkillLoadError(f"Skill '{name}' not found.")
        try:
            data = json.loads(DISABLED_SKILLS_FILE.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        disabled_set = {str(n) for n in data.get("disabled", [])}
        if disabled:
            disabled_set.add(name)
        else:
            disabled_set.discard(name)
        DISABLED_SKILLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DISABLED_SKILLS_FILE.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"disabled": sorted(disabled_set)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(DISABLED_SKILLS_FILE)
        try:
            DISABLED_SKILLS_FILE.chmod(0o600)
        except OSError:
            pass
        self._clear_cache()
        return disabled

    def invalidate_cache(self) -> None:
        """Public cache reset — after install/update from the pack manager."""
        self._clear_cache()

    def save(
        self,
        name: str,
        trigger: str,
        description: str,
        tools: list[str],
        system_prompt: str,
        test_input: str = "",
        test_expect_tool: str = "",
        test_expect_contains: str = "",
    ) -> Skill:
        """
        Stores a user skill as a Markdown file.

        Creates the user skills directory when it is not there yet.
        Overwrites existing files (for update).

        Safety:
          - path traversal protection (target must lie inside _user_dir)
          - the file name is reduced to its base name

        Returns:
            The stored skill object (parsed for validation).

        Raises:
            SkillLoadError:   when the resulting skill would be invalid
            PermissionError:  on a path traversal attempt
        """
        self._user_dir.mkdir(parents=True, exist_ok=True)

        # Path traversal protection: base name only, and the realpath of the target
        # has to stay under the user skills root. `os.path.realpath` is the normalizer
        # CodeQL pairs with the prefix check (py/path-injection); Path.resolve() is not
        # that model, which is why the alert stayed open on the write below.
        safe_name = Path(name).name
        if not safe_name or safe_name.startswith("."):
            raise SkillLoadError(f"invalid skill name: '{name}'")

        allowed = os.path.realpath(self._user_dir)
        target = os.path.realpath(os.path.join(allowed, f"{safe_name}.md"))
        if not target.startswith(allowed + os.sep):
            raise PermissionError(
                f"Security violation: path '{target}' is outside the allowed directory '{allowed}'."
            )
        path = Path(target)

        tools_str = ", ".join(tools) if tools else ""
        content = (
            f"# {safe_name}\n\n"
            f"**Trigger**: {trigger}\n"
            f"**Description**: {description}\n"
            f"**Tools**: {tools_str}\n\n"
            f"## System Prompt\n\n"
            f"{system_prompt}\n"
        )
        # P2-2: optional test block (only when at least one field is filled),
        # so the skill takes part in the golden example format (parity gate).
        if test_input.strip() or test_expect_tool.strip() or test_expect_contains.strip():
            content += (
                "\n## Test\n\n"
                f"**Input**: {test_input.strip()}\n"
                f"**Expect Tool**: {test_expect_tool.strip()}\n"
                f"**Expect Contains**: {test_expect_contains.strip()}\n"
            )

        # Validate before writing
        _parse_skill(safe_name, content)  # raises SkillLoadError if invalid

        path.write_text(content, encoding="utf-8")
        self._clear_cache()
        return _parse_skill(safe_name, content)

    def delete(self, name: str) -> None:
        """
        Deletes a user skill (flat file OR R16 pack directory).

        Raises:
            PermissionError: when the skill is a built-in, or when the name
                addresses a path outside the user skills root
            SkillLoadError: when the skill does not exist as a user skill
        """
        if self.is_builtin(name):
            raise PermissionError(
                f"Built-in skill '{name}' cannot be deleted."
            )
        allowed = os.path.realpath(self._user_dir)
        pack_dir = os.path.realpath(os.path.join(allowed, name))
        flat_file = os.path.realpath(os.path.join(allowed, f"{name}.md"))
        if not pack_dir.startswith(allowed + os.sep):
            raise PermissionError(
                f"Security violation: path '{pack_dir}' is outside the allowed directory '{allowed}'."
            )
        if not flat_file.startswith(allowed + os.sep):
            raise PermissionError(
                f"Security violation: path '{flat_file}' is outside the allowed directory '{allowed}'."
            )
        pack_manifest = os.path.join(pack_dir, "SKILL.md")
        if os.path.isdir(pack_dir) and os.path.exists(pack_manifest):
            shutil.rmtree(pack_dir)
            self._clear_cache()
            return
        if not os.path.exists(flat_file):
            raise SkillLoadError(f"User skill '{name}' not found.")
        os.unlink(flat_file)
        self._clear_cache()

    def _clear_cache(self) -> None:
        # E2: cache key gained the plugin-root element — pop every variant
        # (any plugin_root value) so save/delete always invalidate.
        user = workspace_key(self._user_dir)
        builtin = workspace_key(self._builtin_dir)
        for key in list(_SKILL_LIST_CACHE.keys()):
            if len(key) >= 2 and key[0] == user and key[1] == builtin:
                _SKILL_LIST_CACHE.pop(key, None)
    async def run_test(self, name: str) -> SkillTestResult:
        """
        Runs the self-test of a skill.

        Uses chat_with_tools with the skill as the system prompt.
        Checks whether the expected tool was called.

        Returns:
            SkillTestResult (passed = True/False)
        """
        from core.chat import chat_with_tools, OllamaNotReachableError

        try:
            skill = self.load(name)
        except SkillLoadError as exc:
            return SkillTestResult(
                skill_name=name,
                passed=False,
                message=f"Skill could not be loaded: {exc}",
            )

        if not skill.test.input:
            return SkillTestResult(
                skill_name=name,
                passed=True,
                message="No test defined (skipped).",
            )

        # Ollama call with the skill system prompt
        tool_called: list[str] = []
        chunks: list[str] = []

        history = [
            {"role": "system", "content": skill.system_prompt},
            {"role": "user",   "content": skill.test.input},
        ]

        try:
            from core.model_provider import chosen_model

            model = chosen_model("a skill test run")
            response = await chat_with_tools(
                model=model,
                history=history,
                on_chunk=chunks.append,
                on_tool_start=lambda n, _, cid="": tool_called.append(n),
            )
        except OllamaNotReachableError:
            return SkillTestResult(
                skill_name=name,
                passed=False,
                message=_unreachable_engine_note(),
            )
        except Exception as exc:
            return SkillTestResult(
                skill_name=name,
                passed=False,
                message=f"Error during test: {exc}",
            )

        full_response = response or "".join(chunks)

        # checks
        if skill.test.expect_tool and skill.test.expect_tool not in tool_called:
            return SkillTestResult(
                skill_name=name,
                passed=False,
                message=(
                    f"Expected tool '{skill.test.expect_tool}' but called: "
                    f"{tool_called or 'none'}"
                ),
                tool_called=", ".join(tool_called),
                response=full_response[:200],
            )

        if skill.test.expect_contains:
            if skill.test.expect_contains.lower() not in full_response.lower():
                return SkillTestResult(
                    skill_name=name,
                    passed=False,
                    message=(
                        f"Answer does not contain '{skill.test.expect_contains}'"
                    ),
                    tool_called=", ".join(tool_called),
                    response=full_response[:200],
                )

        return SkillTestResult(
            skill_name=name,
            passed=True,
            message="Test bestanden.",
            tool_called=", ".join(tool_called),
            response=full_response[:200],
        )
