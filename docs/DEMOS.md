# Demos

Screen recordings of the real app — the React PWA against the FastAPI backend — captured with
`scripts/create_demo_media.py`. The artifact clips drive the real local tools and need no network; the
chat clip streams from the configured engine.

| Chat & thinking | Artifacts (QR + Excel) |
|---|---|
| ![Chat demo](media/ephe-demo-chat.gif) | ![Artifacts demo](media/ephe-demo-artifacts.gif) |
| Streaming answers with a separate thinking channel | Artifact tools create real files with inline preview |

| Agent Panel | Command palette & navigation | Plugin Store | Mobile PWA |
|---|---|---|---|
| ![Agent Panel demo](media/ephe-demo-agent-panel.gif) | ![Palette demo](media/ephe-demo-palette.gif) | ![Plugins demo](media/ephe-demo-plugins.gif) | ![Mobile demo](media/ephe-demo-mobile.gif) |
| Git diffs, tasks, and a shell with approval gates | ⌘K palette, session rename, shortcut cheatsheet | Extensions 1.0: master switch, detail sheet, signed bundles | Same app on a phone viewport |

Regenerate them with `./dev.sh` running, plus `ffmpeg` and Python `playwright`:

```bash
./.venv/bin/python scripts/create_demo_media.py
```
