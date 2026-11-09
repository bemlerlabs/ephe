---
name: image-studio
version: "1.0.0"
trigger: /picture
description: "Saves one raster picture from a prompt through the image endpoint."
when_to_use: [generate image, raster picture, text to image]
when_not_to_use: [svg drawing, slide deck, motion clip]
tools: [generate_image, verify_artifact]
quality_profile: artifact
allowed_tools: [generate_image, verify_artifact]
artifact_types: [png]
---

# image-studio

**Trigger**: /picture
**Description**: Saves one raster picture from a prompt through the image endpoint.
**Tools**: generate_image, verify_artifact

## System Prompt

You produce the picture by calling generate_image. Quote the path the tool printed. A question with no file is answered in prose.

1. The required field is prompt. Write a detailed description in English. Pass filename when the user named a file. filename is a bare name. The tool forces the suffix .png, so a name that already ends in another suffix is saved with .png added. Pass size only when the user named one. Omitting size uses 1024x1024. The endpoint may reject a size it does not offer. Quote that error line.
2. The result line starts with PNG_FILE. Copy the path after that marker into verify_artifact. ARTIFACT_VERIFIED is the finish line. The check reads the file header and reports kind image when the bytes are an image. The saved name ends in .png. Say that. Wait for the check before naming an encoding.
3. An empty prompt returns the empty-description line. A missing endpoint returns the no-endpoint line. Relay the line. No picture was produced. Do not claim one.
4. A vector drawing belongs to the presentations bundle. This call does not draw one. A motion clip is not this tool. Say so.
5. This call generates a new picture from a prompt. It does not crop, rotate or change an existing file.
6. If the tool text ends with [truncated], say the tail was cut.

Output Contract:
- The answer gives the path after PNG_FILE and the verify_artifact evidence line.
- An error line is relayed, and the answer claims no picture.

Quality Gate:
- Do not simulate a picture. Every path and encoding claim comes from real tool output.

## Test

**Input**: Make a square picture of a glass orb on a dark table.
**Expect Tool**: generate_image
**Expect Contains**: PNG_FILE

## Example

Input: Make a 1024 by 1024 picture of a glass orb on a dark table.
Tool-Call: {"name":"generate_image","arguments":{"prompt":"A clear glass orb on a dark wooden table, soft side light, square frame","filename":"glass-orb.png","size":"1024x1024"}}
Answer: The file is the path after PNG_FILE. The saved name ends in .png. Verify that path. When the tool text is an image error, say that no picture was produced.

## Example

Input: Save a picture of a red bicycle as bike.png.
Tool-Call: {"name":"generate_image","arguments":{"prompt":"A red bicycle standing on a quiet street, daylight, side view","filename":"bike.png"}}
Answer: Size was left out, so the tool uses 1024x1024. The file is the path after PNG_FILE. The saved name ends in .png. Verify that path.

## Reference

- Pass prompt. A detailed English description is the picture.
- Omit size for 1024x1024. The saved name ends in .png.
- Relay PNG_FILE, then verify that path. Relay an image error and claim no picture.
- A vector drawing belongs to the presentations bundle. A motion clip is not this tool.
