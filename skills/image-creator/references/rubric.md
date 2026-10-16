# Quality Rubric

1. Always call generate_image for image requests. Never answer with text only when the user asked for a picture.
2. Write the prompt argument as a detailed ENGLISH description (subject, style, lighting, composition) — image models perform best in English, regardless of the chat language.
3. Pick a descriptive ASCII-safe filename ending in .png (or .jpg if the user asks for JPEG).
4. Keep the default size 1024x1024 unless the user explicitly asks for another ratio.
5. If the tool returns an error because no image endpoint is configured: answer honestly, explain the one-line setup (set EPHE_IMAGE_BASE_URL to a local OpenAI-compatible image server such as LocalAI with Stable Diffusion, or a cloud provider), and DO NOT pretend an image was created. You may offer a deterministic SVG graphic or diagram as an explicit vector alternative — clearly labeled as SVG, not as a generated photo.
6. Ground every number/path on real tool output; no simulated output without a returned path.
