# How Ephe came to be

This page is the product's own account of its history, written by hand for the
release it ships in. It names no commits and no repositories, and it quotes no
figures it cannot show. Where a claim here matters, the document that carries the
evidence is linked.

## The starting hurt

The tools this team reached for first were agents that lived in someone else's
cloud. They answered well and asked for everything in return: a signup, an
upload, a bill keyed to every prompt, and a model nobody had chosen — a default
picked by a product manager somewhere else. The work itself — the prompts, the
half-formed drafts, the files a run touched — sat on hardware the team did not
own. Leaving any of those tools meant leaving the work behind.

The starting question was narrow and stubborn: what would an agent workbench look
like if the machine it runs on is the user's machine, and the model it answers
with is the one the user named?

## Early shape

The first working version was a Python backend and a plain web page: one process
on one laptop, one terminal, no accounts. The rules came before the features, and
they are still the rules:

- The product ships no model weights and picks no default model. A run answers
  with the engine the user chose — a local Ollama model, or an
  OpenAI-compatible endpoint the user named with its own endpoint and key. With
  no choice stored there is no answer: the server starts in setup mode, the
  terminal opens its own provider setup, and the headless commands stop with a
  hint. That behaviour was an owner decision before it was a test, and it is
  both now.
- Nothing leaves the machine unless the user's own choice names a remote
  endpoint, or the user turns an online path on. Web research, hosted voice,
  public phone access: each is opt-in, and the interface labels it that way
  (see [SECURITY_AND_PRIVACY.md](SECURITY_AND_PRIVACY.md)).
- The agent's hands are gated. The default profile asks before a file edit or a
  shell command; the approval shows what will run. Convenience campaigns tried
  to loosen this twice; the strict default stayed, because the trust the product
  sells is the approval gate, not the model's good intentions.

The PWA and the desktop shell were not a later polish. From early on the team
held that the browser app and the desktop app are one product with two doors, and
that a terminal on a SSH session deserves the same backend as the graphical
surfaces. The phone joined the same way: not a native app, but the same PWA,
reached by a QR code over the user's own network, because carrying a laptop to
the couch should not require a second product.

## Why a film studio

A chat that quotes other people's documents proves little about an agent. The
team wanted an end-to-end proof that the agent can make a real file on a real
machine: something you can play back and hand to someone. An agent that cuts a
short film — title cards, a music bed, a spoken line, all synthesised locally and
joined with ffmpeg, every tool call shown and approved in the chat — is that
proof, because every step leaves an artifact a sceptic can open. The tools that
make it (`film_card`, `film_music`, `film_sound`, `film_clip`) grew out of that
exercise and stayed in the product; [DEMO_VIDEO.md](DEMO_VIDEO.md) records the 40-second film
they were built to cut, frame by frame. The tree publishes no copy of that film — the only
moving picture that ships with the product is the first-run sequence under
`app/public/onboarding/`, which the product plays itself. There is no text-to-video model in
Ephe, and that film never suggested one.

## Plugins, skills and the store

Features that only one person's workflow needs should not be everyone's defaults.
The answer was bundles: plugins add commands and a skill pack, presets add one
capability each, and everything first-party ships as plain files with a manifest
and a hash in this repository. The Discover shelf shows what an entry can do, and
an install lands in the user's own profile only after a confirmation. The one
bundled third-party pack, Superpowers, is marked as what it is — third-party
content under MIT — and mounts without a signature claim
([PLUGINS.md](PLUGINS.md)). A public catalogue for outside publishers is planned;
it is not here yet, and the README says so.

## Memory, cells and keeping things

Sessions were made disposable early — a run gets a cell, destroyed when the
session ends — while anything the user saves stays on disk in plain reach. The
long-term store, Kepta, grew from a demand rather than a feature list: notes the
agent may recall must be notes the user can delete, and both operations ask
first ([MEMORY.md](MEMORY.md)).

## What was taken out

The public release was a moment to delete, not only to add.

- The package-manager channels were retired and their repositories deleted: the
  one-command installers and Docker are the install paths, and nothing in the
  tree advertises another.
- The benchmark board and its published figure tables left the product. A page
  that renders pass-rates is a claim; a harness that measures them offline, in
  the hands of whoever runs it, is engineering. The evaluation harness under
  `evals/` and the `ephe bench` verify gate ship; a board surface and
  unreproducible headline numbers do not, and the film's provenance page says so
  where an older frame shows the board.
- Company positioning, marketing personas and any prose about funding or
  sponsorship were kept out of the product and its documents. The licence and
  the security policy speak plainly instead ([../LICENSE](../LICENSE),
  [../COMMERCIAL.md](../COMMERCIAL.md), [../SECURITY.md](../SECURITY.md)).
- Language rules became a gate, not a style note: the tree is English, and
  German lives only where it is product — the German locale bundle and
  deliberately German content. A script holds the line
  (`scripts/language_gate.py`).

## The version line

Internal milestones ran under several numbers that never described a public
release. With the public repository, the version line restarts: **0.1.0 is the
first version, and the changelog begins there** ([../CHANGELOG.md](../CHANGELOG.md)).
Nothing before it is promised, numbered or linked, because the repository anyone
can open begins here too.

## Why BUSL-1.1

The team wants the source open to read, audit and modify, wants non-production
use free, and does not want the work resold as a hosted product by someone who
did not build it. BUSL-1.1 says exactly that, and each version falls to Apache
2.0 four years after its first public release, with or without anyone's
permission. Production use is a conversation, not a ransom
([COMMERCIAL.md](../COMMERCIAL.md)).

## Where it goes

The roadmap is the gap between the README's "What is not there yet" and this
tree: native-quality mobile use without a second product, a public plugin
catalogue with real publisher checks, one-click MCP installs that survive a
security review, and more measured proof behind every number the project dares
to print. Each arrives as code, in a release, with its document — or it does not
arrive at all.
