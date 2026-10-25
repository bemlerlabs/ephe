# AGENTS.md proposal

Short, for the repository contract. Each line exists because a wave without it
lost time or shipped a lie.

## Working backwards

Write the press release and the FAQ before the code. A feature that cannot be
described in one sentence a user would repeat is not ready to build.

## Definition of done

- Tests first or with the change, and the test names the behaviour it protects.
- Both surfaces build: the PWA (`app/dist`) and the Tauri app.
- The installed app reports the version the release names, backend included.
- The receipt carries raw findings with the command that produced them.

## Tool-engine binding

A tool never constructs its own model client. If a tool needs a model, it gets
the active provider through the one resolver, or it does not call one. A test
fails when a direct client appears in a model-calling tool.

## Truthful UI

A status is an outcome, not a colour. `completed`, `failed` (with a code) and
`denied` (an approval refusal) are three different things and keep three
different words. A failure shows its reason; an unknown code falls back to the
result's own sentence.

## Layout floor

360, 768 and 1280 px are measured, not assumed. A tool name or a status may wrap;
it may not be clipped. A hover explanation belongs in the content, not over it.

## Competitive baseline

No "better than X" without a measurement beside it. A matrix cell without
evidence says `unmeasured`. A competitor is installed and run, not remembered.

## Lanes and the integrator

One lane, one worktree, exclusive paths. Shared files (locales, lockfiles,
manifests, the changelog, workflows) are the integrator's. A lane commits with a
pathspec and reports after its first commit. The integrator runs the gates,
builds both surfaces, and writes the receipt.

## Red team

Every plan gets a contradiction pass before implementation. The three strongest
objections are written down. A finding that cannot survive the objection is
dropped, and the plan changes.
