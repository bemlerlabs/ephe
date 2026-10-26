# The backend path

Date: 2026-10-26. Order: S25 T3. What `~/.ephe/desktop.json` names on this
machine today, why the directory carries an old name, and what replaces the
checkout.

## What is configured

```json
{
  "python": "/Users/sanji/.local/share/ephe/current/.venv/bin/python",
  "project_root": "/Users/sanji/.local/share/ephe/current",
  "port": 8765
}
```

`current` is a symlink to `0.1.4`, and the checkout inside it runs `main`:
measured at `64f8763` on 2026-10-26 after the 0.1.8 update. The name of the
physical directory is the residue of the first install; the symlink is what the
shell and the parity check use, and `/api/health` reports the resolved path.

## Why the rename is not cosmetic

The venv inside that directory carries absolute paths. Moving the directory
would break `.venv/bin/python` and every console script, so the stable path is
the symlink and the directory keeps its name until a versioned bundle replaces
it. A second symptom of the same coupling: `app/dist` is untracked, so the
parity move updates the Python code and leaves the PWA the backend serves on
`:8765` at the version built before the move. A browser pointed at that port can
read `0.1.8` from `/api/health` and load an older service-worker stamp. The
Tauri shell is unaffected: it loads its own bundled assets.

## What the parity move does

`app/src-tauri/src/parity.rs` runs two commands with the configured root as the
working directory: `git fetch origin main:refs/remotes/origin/main` and
`git checkout -B main origin/main`. It refuses a root that is not this product's
checkout and a checkout with local changes, and it never kills the backend that
answers, so the new code is loaded by the next start and the verdict says
`updated_restart`.

## Sidecar plan (0.2.0-beta.2)

The checkout, the venv and the PWA build become one versioned bundle under
`~/.local/share/ephe/<version>/`, addressed through `current`, with a manifest
that names the Python, the dist stamp and the schema. The update writes a new
directory, flips `current`, and restarts the backend; a rollback flips it back.
Until then the checkout stays, and the two gaps above are recorded with each
release instead of being hidden.
