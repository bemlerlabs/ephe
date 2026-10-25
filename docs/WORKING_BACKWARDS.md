# Working Backwards — Ephe

Written for the S21 W0 wave (2026-10-25). The order asks for the press release
first, then the questions a buyer would ask, then the ten truths that have to
hold for the sentence to be true. Where a truth is not yet demonstrated, it is
named as open, not assumed.

## Press release

**Ephe — the local-first agent workspace that just runs.**

Ephe is an agent workspace you install on your own machine. It talks to the
engine you chose — a local Ollama model or any OpenAI-compatible endpoint — and
fails closed when none is configured, instead of quietly picking one for you.
Your files stay where they are. There is no account. The chat keeps working
after a broken connection: a lost stream leaves the partial answer, names why it
stopped, and the next message goes out without a reload. Tools report what they
did — a page that could not be fetched says so, with the reason, instead of a
green check. Ephe runs as a desktop app, a browser app, and a terminal UI, and
all three are built from the same tree.

## FAQ

**For whom?** People who want an agent on their own machine with their own
engine, and who need to trust what the interface tells them. Not for someone who
wants a hosted account with a model included.

**Why not Hermes, Qoder, or pi?** Each is a different product with a different
centre of gravity, and this document does not claim to beat any of them. What
Ephe offers is the combination of engine ownership, a fail-closed engine choice,
and a surface that names failures. The comparison that would support a claim is
in `docs/COMPETITIVE_MATRIX.md`; the cells that are not measured are marked as
such.

**What does it cost?** The software is Business Source Licence 1.1. Inference
costs whatever the engine you chose costs: nothing for a local model, the
provider's price for a hosted one. Ephe adds no subscription and no account.

**Privacy?** Local by default: the app and the backend run on this machine. A
hosted engine means prompts leave the machine — that is the engine's data flow,
and the settings surface says so when the decision layer would send state to it.
Web search and web fetch are opt-in tool calls.

**What if the engine is down?** The turn fails with a reason code and a sentence
in the UI language. It does not fall back to another engine, and it does not
pretend a tool succeeded.

**Installation?** One command installs a checkout, its virtualenv and the app;
the app updates itself, the backend is updated by the documented `ephe update`
path. Both surfaces must report the same version — a mismatch is a defect, not
a state to live with.

**What is the catch?** Local models are slower than hosted ones, and the
desktop app depends on a Python backend that is installed beside it. A hosted
engine is a second data flow the user has to accept deliberately.

## The ten truths

1. The engine is the user's choice, persisted, and never defaulted silently.
2. A turn that loses its terminal frame keeps its partial answer and the next
   message works.
3. Every tool result says what happened: completed, failed with a reason, or
   refused by policy.
4. No tool calls a different engine than the one the user chose.
5. An image the product produces is shown inline, or the card names the concrete
   reason it cannot be.
6. The desktop app and the Python backend report the same version after an
   update.
7. The layout holds at 360, 768 and 1280 px without clipping a status or a
   tool name.
8. Both surfaces are built from the same source at release time.
9. No number in a document is written without the command that produced it.
10. A competitive claim carries its measurement beside it, or it is not made.

Truths 1–3 and 5 are demonstrated in this wave (see the S21 receipt). Truth 4 is
asserted by a source test and by removing the one call that violated it. Truth 6
is open: the in-app update moved the shell to 0.1.6 while the backend stayed at
0.1.4 until it was repaired by hand. Truths 7 and 8 are partly demonstrated by
tests and builds; the pixel proof at three widths is still owed. Truths 9 and 10
are process rules, checked in the receipt format.
