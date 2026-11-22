## What changes

One paragraph: the behaviour before, the behaviour after. Not a list of files.

## Why this and not less

The step this replaces, and why the smaller version would not have held. If the answer is "it
would have", the smaller version is the change.

## How to see it

The command or the surface, and what to look at. A reviewer has to reach the change in under two
minutes, from a checkout of this branch.

## Measured

Every number written in this description comes from a run, and the run is pasted below it.

- [ ] `make verify` on this branch
- [ ] `python3 scripts/language_gate.py`
- [ ] `python3 scripts/prose_tells.py`
- [ ] `python3 scripts/readme_check.py --root .`
- [ ] `python3 scripts/new_file_check.py`
- [ ] `python3 scripts/secret_scan.py --all` reports zero findings
- [ ] `python3 scripts/attribution_check.py --identity` passes
- [ ] For anything under `app/src`: `pnpm run build` in `app/`, and the desktop bundle rebuilt
- [ ] For anything under `server/`: the route contract test moved in the same patch

## What this does not do

The promise I am deliberately not making, so nobody reads more into the diff than it holds. A
capability the tree cannot prove stays out of the product, and out of this description.

## Related

`Fixes #`, `Relates to #`. Security findings go through the channel in `SECURITY.md`, never
through a pull request.
