"""
◑ Ephe – Descriptions for the deep settings (wave I3)
core/settings_hints.py

A field in the register cannot be explained without text, and text for a field
without a reader states a false depth: the user sees an explained control that
does nothing. That is why the same bar applies here as in
tests/test_settings_surface_is_real.py — only what the wiring actually feeds is
written down. A field is wired (an accessor call) and its text is added in the
same slice; a field without a reader stays without text.

Form: HINTS[key] = the English sentence the register carries. The German half of
every pair is a leaf in app/src/locales/de.json under hint_key(key); the settings
seam resolves that key with t(). The register answers with the English text under
both `hint` and `hintEn` — the response shape is frozen by
tests/test_w3_68_api_contract_frozen.py — so a client that does not know the key
reads English. tests/test_settings_hints.py holds both halves to the same field.
"""
from __future__ import annotations

from typing import Final
from core.sol.hints import SOL_HINTS  # SOL field texts: core/sol/hints.py

#: English sentence per field key: the fallback the register carries. The German half of each
#: pair is a locale leaf under hint_key(key). Checked by tests/test_settings_hints.py: the
#: field is wired, both halves exist, the text echoes no label and runs 24-240 chars.
HINTS: Final[dict[str, str]] = {
    "shortcuts.global_enabled":
        "The one switch that claims a key outside the window: Cmd+Shift+E on macOS, "
        "Ctrl+Shift+E elsewhere, brings Ephe to the front. Off is the default; if another app "
        "owns the chord, Ephe writes the value back to off.",
    "advanced.api_timeout":
        "Time limit for one non-streaming request to the engine (10-1800 seconds). The "
        "streaming path keeps its own bounds (300 s read) and is untouched by this field.",
    "advanced.film_sfx_dir":
        "A folder of your own .wav files that the film studio resolves by name. The "
        "EPHE_SFX_DIR environment variable takes precedence when it is set.",
    "chat.details_mode":
        "Starting state of a finished turn: expanded shows the whole timeline (reasoning, "
        "tools, answer) and the millisecond readout; collapsed the answer with the plain "
        "check sentence in seconds. A click on the head overrides it for that turn.",
    "chat.allow_input_while_streaming":
        "On: Enter queues another task while Ephe answers. Off: the composer is read-only "
        "during a turn and Enter does nothing.",
    "chat.show_tool_count":
        "Shows after a tool group how often it was called — live as done/total, finished as a "
        "number; a single call shows no number. Off hides only that counter; the line stays.",
    "chat.expand_tool_calls":
        "The top tool group of a turn starts open instead of closed. Your own click always "
        "wins — the default holds until the first click on a line.",
    "chat.show_thinking_loader":
        "The pulsing “thinking…” line with its ticking seconds while the phase runs. Off "
        "drops only that line; the reasoning text follows “Show reasoning”.",
    "chat.stream_idle_seconds":
        "Aborts a running stream when the server sends no byte for this long (10-600 "
        "seconds). Only silence counts, not total duration — a long answer is left alone.",
    "chat.duration_format":
        "How long something took: compact per Ephe norm (4m 12s, at most two units) or as a "
        "clock (04:12, 1:04:12 past an hour). Applies to the turn head, the durations of the "
        "panels and the memory row; the thinking line stays terse.",
    "chat.show_reasoning":
        "Shows the model's reasoning as its own line — at its position in the timeline, first "
        "in the legacy layout. Off hides only the reasoning text; tools and the answer stay.",
    "chat.tool_result_chars":
        "How many characters a tool result may carry before it is shortened into the "
        "conversation context (2,000-120,000). Low saves room in long tool chains, high keeps "
        "more of the file or shell output.",
    "chat.continue_attempts":
        "How often Ephe nudges an answer that announces a step but never runs it (0-5). At 0 "
        "the stop stands and no extra model round is started.",
    "appearance.font_scale":
        "Scales the interface text in percent around the chosen base text size (80-150 "
        "percent); rem spacing stays. Applies right after saving.",
    "appearance.base_font_px": "Base step in px (13, 14 or 15); the percentage dials scale it.",
    "appearance.chat_font_scale":
        "Scales only the conversation text between 80 and 150 percent; the rest of the "
        "interface keeps following the general font scale.",
    "appearance.reading_width":
        "Caps the conversation width between 480 and 1200 pixels; on narrow windows the "
        "available width stays the limit.",
    "appearance.accent":
        "Chooses the curated accent for the mark and live actions; grounds, status tones and "
        "selection stay unchanged.",
    "appearance.companion_enabled":
        "Shows the chosen companion on the welcome screen and in the active chat. Off hides "
        "it everywhere while form, size and sound choices stay stored and return the next "
        "time it is switched on.",
    "appearance.companion_species":
        "Chooses the form in the workspace: the folded paper moth, the golden spark with ghost "
        "eyes from the film, or a calm emblem. The moth carries wings and a gaze; the spark is a "
        "glow with two eyes.",
    "appearance.companion_behavior":
        "Sets place and motion: flying and clickable at the composer, sitting calmly at the "
        "input, resting in the header next to the mark, or only on the welcome screen after "
        "the first chat. On the welcome screen the figure always stands.",
    "appearance.companion_sound":
        "Turns the wing flutter and the spark's crystal note on or off. The system's "
        "reduced-motion setting and the animations switch keep the synthesizer silent as "
        "well, whatever this switch says.",
    "appearance.companion_mode":
        "Chooses the companion's work: sit quietly at the edge, point at targets on the "
        "surface, or act as a co-pilot that runs safe actions itself after a visible "
        "countdown. Riskier actions always stay with the user.",
    "appearance.companion_scale":
        "Scales the companion alone (70-140 percent); type, spacing and touch targets stay.",
    "appearance.companion_countdown_seconds": "Time before it acts (0-10 s); at 0 it acts at once.",
    "appearance.animations_enabled":
        "Turns transitions and CSS animations on or off; off also stills the spring entrance "
        "of messages and the companion's sounds. The operating system's reduced-motion keeps "
        "applying on top.",
    "appearance.show_timestamps":
        "Shows the time under each message. Off hides only that line; content, tool trail and "
        "buttons stay put.",
    "appearance.update_channel":
        "Release: published tags only; the signed app and the PWA move with them. Commit: "
        "every green merge from main — the backend and PWA follow, the desktop shell only at "
        "the next release. The terminal stays on releases.",
    "appearance.update_check":
        "Polls the GitHub releases anonymously every 30 minutes and then shows the update "
        "banner. Off: no outbound request, no banner.",
    "memory.capture_enabled":
        "After each answer, decide whether the pair is worth keeping and store it. Off: no "
        "new facts are added — search, injection and the memory tool keep working.",
    "memory.capture_min_answer_chars":
        "Below this length an answer is too thin to become a memory (20-2000 characters); the "
        "question itself needs at least 8 characters. Someone who explicitly asks Ephe to "
        "keep it passes the answer bound.",
    "memory.dedupe_score_threshold":
        "From which similarity (0.5 to 1) a hit counts as a duplicate and the new pair is not "
        "stored. The check reads the 8 closest hits from the question's first 200 characters, "
        "over Ephe's own entries only; an identical text can score below it.",
    "memory.inject_max_entries":
        "At most how many entries are lifted into the system prompt (1-50) — the same number "
        "bounds injection's own search. More knowledge, more tokens.",
    "memory.inject_min_score":
        "Below this value (0 to 1) a found entry is not injected, because it would only cost "
        "tokens. Higher keeps the block leaner, lower lets more through.",
    "memory.embedder":
        "EmbeddingGemma 2 emits 768 values, Ephe stores the leading 256; all-MiniLM-L6-v2 "
        "stays at 384. A switch applies from the next stored entry; the other model's rows "
        "return to the search after the re-embed run.",
    "memory.embedder_allow_download":
        "Allows the automatic fetch of the EmbeddingGemma weights (542 MB) from "
        "huggingface.co into the device folder. The popup's button fetches once as its own "
        "consent without this switch; without weights the vector arm stays off.",
    "ephemera.idle_ttl_minutes":
        "How long a cell survives without a run (5-240 minutes); the next access discards it "
        "and its namespace is gone. Only a run moves the boundary. A new value applies to the "
        "next cell built.",
    "ephemera.evaporate_on_delete":
        "Whether deleting a session in the app also frees its work directory at once instead "
        "of waiting for the idle limit; the API delete, the clear and retention wait it out. "
        "Files a run wrote to the output folder stay — no switch deletes them.",
    "ephemera.trash_retention_days":
        "How long a deleted task waits in the trash before Ephe deletes it for good. 0-365 "
        "days; 0 keeps everything until you empty the trash yourself. The clock starts at the "
        "delete; every run the sweep takes leaves one line in the log.",
    "cron.misfire_grace_minutes":
        "How long a one-shot may still start after its time when Ephe was not running (0-1440 "
        "minutes); 0 never catches up and past the window the run lapses. Recurring slots "
        "always wait for their next time.",
    "cron.history_keep":
        "How many runs are kept — in memory and in schedule_results.json (10-500). Oldest go "
        "first; export anything you need before it drops.",
    "cron.history_rows":
        "How many runs the list under a schedule shows (5-100). Changes nothing about what is "
        "stored — only what is visible.",
    "cron.max_parallel_jobs":
        "How many runs of the same job may overlap (1-10). At 1, the default, a slot that "
        "falls into a run still going is skipped and does not catch up.",
    "advanced.public_tunnel_idle_minutes":
        "How long a public tunnel stands without a request from the phone (5-240 minutes); "
        "then Ephe closes it and the public address is gone. A phone in use moves the "
        "boundary.",
    "hooks.enabled":
        "Off runs none of the commands in hooks.json — no subprocess before or after a tool "
        "call. The file stays as it is; tools and answers keep running unchanged.",
    "plugins.plugin_autorun":
        "Applies at install time only: a new plugin lands enabled in the registry, a bundled "
        "or verified pack always; with the plugin switches read-only nothing lands on. "
        "Existing entries stay as they are.",
    "plugins.plugin_signature_check":
        "Checks on enable whether the plugin content still matches its stored signature; on "
        "drift the activation fails with 409 and an audit entry. Installation is checked "
        "independently.",
    **SOL_HINTS,
}


def _camel(field_key: str) -> str:
    """A field key in the case the bundles use: chat.show_reasoning becomes chatShowReasoning."""
    parts = [part for chunk in field_key.split(".") for part in chunk.split("_") if part]
    camel = "".join(part[:1].upper() + part[1:] for part in parts)
    return camel[:1].lower() + camel[1:]


def hint_key(field_key: str) -> str:
    """The locale leaf a hint travels under, derived from the field key: settings.<Section><LeafCamel>Hint.

    One home for the naming rule, so the register cannot name a leaf the bundles do not
    carry: tests/test_settings_hints.py walks every field and fails on a missing half.
    """
    return "settings." + _camel(field_key) + "Hint"


def label_key(field_key: str) -> str:
    """The locale leaf a row title travels under: settings.<Section><LeafCamel>, the sibling of hint_key."""
    return "settings." + _camel(field_key)


def option_key(field_key: str, value: str) -> str:
    """The leaf one option of a select travels under: settings.<FieldCamel>Option<ValuePascal>.

    Derived the way `hint_key` is, so the register writes no key of its own: the schema names
    the option's value, and the value decides the leaf. A rename of a value is a data change
    that moves the leaf with it, which is what `tests/test_settings_hints.py` pins.
    """
    parts = [part for chunk in value.split("_") for part in chunk.split() if part]
    pascal = "".join(part[:1].upper() + part[1:] for part in parts)
    return "settings." + _camel(field_key) + "Option" + pascal


def hints_for(key: str) -> str | None:
    return HINTS.get(key)


#: English sentence per key of the generation block (engine.json). Not in the
#: register — the inference parameters have their own map in the settings
#: surface. The text says what the value does inside the request: all values
#: are read (I2-5 for temperatur/top_p/max_tokens, I3-8 for the others). The
#: German half is a locale leaf under hint_key("generation." + key).
GENERATION_HINTS: Final[dict[str, str]] = {
    "temperature":
        "How random the wording gets: 0 pins the engine to the most likely token, higher "
        "values vary more. Sent with every request; 0.0 is the deliberate default here "
        "because eval runs need repeatability.",
    "top_p":
        "Nucleus sampling: admits only the most probable mass up to this value. Empty lets "
        "the engine decide; set, it ships with every request.",
    "max_tokens":
        "Upper bound of tokens per answer. Empty lets the engine decide; a set value caps "
        "every response.",
    "tool_budget":
        "How many tool calls one turn may make at most (1-40). It stops the agent loop, not "
        "the model. Unset keeps the class default: 25 rounds, /ephe up to the cap of 40.",
    "context_window":
        "Context window Ephe assumes for this model: caps how much history and tool text fit "
        "into the request. Unset falls back to the model table.",
    "memory_max_entries":
        "Ceiling for stored memory entries. Above it, auto-memory evicts the least valuable "
        "self-learned ones, at most 50 per pass.",
    "swarm_max_parallel":
        "How many swarm agents of one wave may run at the same time (1 = one after another). "
        "The rest queue up until a slot frees.",
}


def generation_hint(key: str) -> str | None:
    return GENERATION_HINTS.get(key)
