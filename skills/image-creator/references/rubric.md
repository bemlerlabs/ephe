# Quality Rubric

1. Always call generate_image for image requests. Never answer with text only when the user asked for a picture.
2. Write the prompt argument as a detailed ENGLISH description (subject, style, lighting, composition) — image models perform best in English, regardless of the chat language.
3. Pass a bare filename when the user named a file. The tool forces the suffix .png.
4. Keep the default size 1024x1024 unless the user explicitly asks for another ratio.
5. If the tool returns an error, relay that line and claim no picture. This skill does not draw an SVG.
6. Relay the PNG_FILE path the tool printed. Do not invent a path.
