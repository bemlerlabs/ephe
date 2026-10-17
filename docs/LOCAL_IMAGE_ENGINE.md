# Local Image Generation (free & offline)

`generate_image` (tool `/image` skill) renders real PNG/JPEG images through any
**OpenAI-compatible `/v1/images/generations` endpoint**. The image engine is
*your* choice — the tool itself ships no model and never simulates output.

## Recommended: LocalAI (free, self-hosted)

[LocalAI](https://localai.io/docs/features/image-generation/) is the strongest
free drop-in: it serves `/v1/images/generations` with Stable Diffusion
backends, runs on CPU (no GPU required) and keeps everything on your machine.

```bash
# 1. Start LocalAI (Docker) — first run downloads the SD model (~2 GB)
docker run -p 8080:8080 --name localai localai/localai:latest

# 2. Point Ephe at it and restart the server
# Preferred (R16): Settings → Engine → Image endpoint (writes ~/.ephe/image.json)
# Alternatively via env:
export EPHE_IMAGE_BASE_URL="http://127.0.0.1:8080/v1"
# optional: export EPHE_IMAGE_MODEL="stablediffusion"
# optional: export EPHE_IMAGE_API_KEY="..."   # only for cloud providers
```

Then just ask: *"Create an image of a fox in the Black Forest"* (or type
`/image`). The tool is approval-gated (mutating + network): the chat shows a
confirmation before the first generation.

## Alternatives (all free)

| Engine | Notes |
|---|---|
| [openedai-images-flux](https://github.com/matatonic/openedai-images-flux) | Purpose-built OpenAI images API (FLUX/SD), Docker, low maintenance activity |
| [LlamaEdge sd-api-server](https://llamaedge.com/docs/ai-models/text-to-image/quick-start-sd) | OpenAI-compatible SD/FLUX server, Wasm-based |
| [OpenVINO Model Server](https://docs.openvino.ai/2026/model-server/ovms_demos_image_generation.html) | OpenAI-style image API, optimized for Intel hardware |
| Any cloud provider (OpenAI/Stability/…) | Works with the same `EPHE_IMAGE_*` variables — but is **not** local |

## What the local chat engine can and cannot do

Your text-only chat model (e.g. `qwen3.8-flash-next`) **cannot rasterize
pixels** — that is a property of the model class, not of Ephe. True image
generation needs a diffusion backend like the ones above. Ephe therefore
ships two honest paths:

1. **Raster images** — `/image` + `generate_image` + a configured image
   endpoint (LocalAI = free & local).
2. **Vector graphics with zero install** — the deterministic SVG tools
   (`create_diagram`, `create_svg`, charts, QR codes, posters) work fully
   offline today and are clearly labeled as SVG, never as generated photos.

## Security notes

- `generate_image` is classified **mutating + network** and is never
  auto-approved.
- Without a configured endpoint the tool returns an honest setup hint — it
  does not fabricate an image.
- Downloaded artifacts land in `~/Downloads` (allowed root), filenames are
  sanitized.
