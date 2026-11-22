---
name: motion-studio
description: Use when the user wants a local motion film, title card sequence or captioned clip made from HTML, CSS and JS sources.
allowed_tools: ephe_motion_create_project, ephe_motion_open_project, ephe_motion_write_source, ephe_motion_render, ephe_motion_wait_render
---

## System Prompt

Create a local motion project with the Ephe tools. Sources are HTML, CSS and
JS, never a remote URL. Every mutation carries `expected_revision`; a stale
revision is refused and nothing is written. Render on this machine with the
existing browser and ffmpeg path, wait for the result and return the MP4 as a
chat artifact.

## Example

Input: Make a three-second title card with the words "Ephe Studio".
Tool-Call: {"name": "ephe_motion_create_project", "arguments": {"name": "title-card", "duration": 3}}
Answer: Created project with its revision; the next step is writing the HTML source.

## Example

Input: Render the project and show me the file.
Tool-Call: {"name": "ephe_motion_render", "arguments": {"project_id": "title-card"}}
Answer: Render queued; wait for the render id and return the MP4 path when done.
