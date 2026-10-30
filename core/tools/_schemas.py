"""Ephe – static base tool schemas (data-only, split out of registry.py).

Pure JSON schema constants. No logic, no imports needed.
The parity/discovery/utility/sandbox schemas live as their own module constants
in their tool modules and are appended in registry.get_tool_schemas().
"""

BASE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "manage_tasks",
            "description": (
                "Manages the user's personal tasks and to-do lists. Actions: 'add' (new), 'update' (change/complete), 'delete' (remove), 'list' (show all)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["add", "update", "delete", "list"], "description": "Operation: add, update, delete, or list."},
                    "title": {"type": "string", "description": "Task title (for add/update)"},
                    "task_id": {"type": "string", "description": "Task ID (for update/delete)"},
                    "status": {"type": "string", "enum": ["open", "done", "in_progress"], "description": "New status (for update)"},
                    "project": {"type": "string", "description": "Project affiliation (optional)"}
                },
                "required": ["action"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_go",
            "description": (
                "Opens a headless browser and navigates to a URL. Use this tool only when you need to visually inspect a page, fill forms or interact with it. For quick web research use web_search (DuckDuckGo) instead. When you need to click buttons (e.g. cookie banners), call browser_click() afterwards. Reach: http/https and data: URLs, plus file: only inside Ephe's own output folders; other local files are read with read_file, never navigated to."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL (z.B. https://wikipedia.de)"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_screenshot",
            "description": (
                "Returns an exact screenshot of the currently active headless browser. Use this when you want to look at the page (e.g. to spot cookie banners, captchas or layouts), since the image is shown to you in the chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_click",
            "description": (
                "Finds a described target in the headless browser via Llama-Vision and performs a mouse click on it. Required: you must have called browser_screenshot or browser_go once beforehand. Ideal for cookie banners, links or menus."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_description": {"type": "string", "description": "What exactly should be clicked (e.g. 'the big green accept button')"}
                },
                "required": ["target_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_type",
            "description": (
                "Types text into the headless browser like a real keyboard. Usually executed into a search field after a preceding browser_click."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_press",
            "description": "Presses a single key in the headless browser (e.g. 'Enter', 'Escape').",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Tastenname (z.B. 'Enter')"}
                },
                "required": ["key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Primary web research tool. Searches the internet via DuckDuckGo and returns real, current results with title, URL and content excerpt. Use this tool ALWAYS when you need current information, facts, news or documentation from the internet. Reach: a result whose target is outside fetch_url's reach (cloud metadata, loopback, internal name spaces such as .local/.internal/.svc) is marked with a 'Reichweite:' line instead of being handed over as an openable link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query, e.g. 'Python asyncio tutorial 2026'",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_search",
            "description": (
                "Searches the computer for files (macOS: Spotlight, Linux: find). Use this tool when the user is looking for a file on their computer."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "File name or search term, e.g. 'invoice 2026' or 'resume.pdf'",
                    },
                    "path": {
                        "type": "string",
                        "description": "Optional search root — absolute or ~-relative, e.g. '~/Desktop'. Defaults to the active workspace.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Reads the contents of a file and returns its text with 1-based line numbers "
                "(N-tab format). Supports plain text, code, Markdown, and PDF files. "
                "Optional offset (1-based start line) and limit (line count, default 2000) window the output. "
                "Use this tool when the user wants to read, analyze, summarize, or explain a file. "
                "For PDF files the text is automatically extracted page by page. "
                "Security: Only files in the home directory, Desktop, Documents, Downloads are allowed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path, e.g. '~/Desktop/contract.pdf'",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-based line number to start reading from (for large files).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of lines to return (default 2000).",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replaces an exact snippet (old_string) in a text file with new_string. "
                "Fails safely if old_string is missing or ambiguous — no partial writes; "
                "set replace_all=true to replace every occurrence. "
                "Returns a unified diff of the change. "
                "Security: Only files in the home directory, Desktop, Documents, Downloads are allowed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path to the text file.",
                    },
                    "old_string": {
                        "type": "string",
                        "description": "Exact text to replace (must occur exactly once without replace_all; include surrounding context).",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "Replacement text.",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace every occurrence instead of requiring a unique match (default false).",
                    },
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": (
                "Deletes one file inside the active workspace. Returns a confirmation string. "
                "Use this to finish a rename (create the new file, then delete the old one) "
                "or to remove a stale file. "
                "Security: Only files in the home directory, Desktop, Documents, Downloads are allowed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path to the file, or a bare file name resolved against the workspace.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover_projects",
            "description": (
                "Finds local code projects on the Mac in allowed user directories (Developer, Projects, Documents, Desktop, Downloads), scores them by marker files and returns stack, path and score. Use this when the user says: find a project, repo, workspace or codebase on my Mac."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search term, e.g. project name, repo name or stack.",
                    },
                    "root": {
                        "type": "string",
                        "description": "Optional start folder — absolute or ~-relative, e.g. '~/Developer' or '~/Documents'.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of projects, default 10.",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_project",
            "description": (
                "Analyses a local project folder top-down: stack, marker files, test command, risks and next steps. Use this for as-is analyses, codebase reviews and when the user wants to understand or improve an existing project."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute or ~-relative path to the project folder.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_source_notebook",
            "description": (
                "Creates a local source notebook from files or folders. Indexes text/PDF/code into citable evidence chunks and stores a local manifest. Use this when the user wants to work with documents, sources, knowledge, source grounding, study notes or citable quotes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "paths": {
                        "type": ["array", "string"],
                        "items": {"type": "string"},
                        "description": "One or more local files/folders — absolute or ~-relative, e.g. ['~/Documents/report.pdf', '~/Documents/project'].",
                    },
                    "title": {"type": "string", "description": "Notebook-Titel."},
                    "notebook_id": {"type": "string", "description": "Optionaler stabiler Dateiname/Slug."},
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional allowed extensions, e.g. ['.pdf', '.md', '.py'].",
                    },
                },
                "required": ["paths"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_source_notebook",
            "description": (
                "Queries a local source notebook and returns a conservative, source-grounded answer with evidence chunks in the format [S001-C001]. Use this after create_source_notebook or when an existing notebook manifest is given."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notebook_path": {"type": "string", "description": "Absolute or ~-relative path to the SOURCE_NOTEBOOK_FILE JSON manifest returned by create_source_notebook."},
                    "question": {"type": "string", "description": "Question that must only be answered from the indexed sources."},
                    "max_chunks": {"type": "integer", "description": "Maximum evidence chunks, default 6.", "default": 6},
                },
                "required": ["notebook_path", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_source_brief",
            "description": (
                "Exports a high-quality markdown briefing from a local source notebook: executive summary, evidence register and source manifest. Use this for reliable reports, study guides, project briefings and source documentation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "notebook_path": {"type": "string", "description": "Absolute or ~-relative path to the SOURCE_NOTEBOOK_FILE JSON manifest."},
                    "question": {"type": "string", "description": "Optional focus question the brief must answer."},
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                },
                "required": ["notebook_path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "Lists the contents of a directory. Use this tool when the user wants to know what is inside a folder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory — absolute or ~-relative, e.g. '~/Desktop' or '~/Documents'.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": (
                "Returns the current date and time. Use this tool when the user asks for the date, time or day of week."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Executes a terminal command. Only whitelisted commands are allowed (ls, find, grep, git, echo, cat, head, tail, wc, mkdir, cp, mv, python, node, npm, ...); destructive patterns (rm, sudo, > /dev/, ...) are blocked. The user sees a confirmation prompt before execution and can deny it — on denial you receive a message that the command was not approved; then choose a different path."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The terminal command, e.g. 'git status' or 'npm install'",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Optional working directory inside the active workspace, e.g. 'src' or 'tests' (workspace-relative, not an absolute path).",
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_workspace_dev_server",
            "description": (
                "Starts the workspace's own dev command (package.json → scripts.dev) in the background on a free loopback port and returns the URL. Use this when the user asks to look at their project and run it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Project directory — absolute or ~-relative. Empty uses the active workspace.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_workspace",
            "description": (
                "Reads all files of a directory (workspace) recursively. Use this tool when the user wants to analyse, understand or review a whole project. Ideal for code reviews, project overviews and documentation tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the directory — absolute or ~-relative, e.g. '~/Desktop/my-project'.",
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Only load these file extensions, e.g. ['.py', '.md']. Empty = all.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_image",
            "description": (
                "Analyses an image with AI vision (OCR, description, recognition). Use this tool when the user wants to show, describe, read out or explain an image, screenshot, photo or document. Supported: PNG, JPG, WebP, GIF, BMP."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the image — absolute or ~-relative, e.g. '~/Desktop/screenshot.png'.",
                    },
                    "question": {
                        "type": "string",
                        "description": "Question about the image, e.g. 'What does this invoice say?' or 'Describe this screenshot'",
                    },
                    "region": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Optional [x1,y1,x2,y2] crop in original pixels to zoom into small text or fine detail before analysis.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vision_click",
            "description": (
                "Uses visual screen analysis to find a UI element on the primary desktop and physically clicks it with the mouse. Use this tool when you are asked to drive GUI applications or the user's browser. (The analysis takes a moment)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_description": {
                        "type": "string",
                        "description": "What should be clicked? e.g. 'the red save button top right' or 'the Chrome icon in the dock'. As precise as possible.",
                    },
                },
                "required": ["target_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "vision_type",
            "description": (
                "Types a string into the currently focused input field on the user's screen. Often paired with a preceding vision_click to focus a search field."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The exact text to type.",
                    },
                    "press_enter": {
                        "type": "boolean",
                        "description": "Should the Enter key be pressed after typing? (default: false)",
                        "default": False,
                    },
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": (
                "Creates a screenshot of the local screen of the computer (the host Mac). Use this tool ALWAYS when the user asks you to show something on screen, says 'take a screenshot' or wants to know 'what do you see right now'. It returns the image inline in the chat."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_chart",
            "description": (
                "Creates a data chart (bar/line/pie) as an SVG image in Ephe design. Use this when the user wants to visualize data. The image appears in the chat automatically. theme='light' (default) matches a PDF page; theme='dark' for the studio surface. For bar/line pass series=[{name, values}, …] to draw several groups or lines with a legend, and embed the result in a PDF with a whole line ![chart](/absolute/path.svg)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": ["bar", "line", "pie"], "description": "Chart kind: one of bar, line, pie."},
                    "title": {"type": "string", "description": "Chart title shown above the plot."},
                    "labels": {"type": "array", "items": {"type": "string"}, "description": "Category labels, one per value."},
                    "values": {"type": "array", "items": {"type": "number"}, "description": "Numeric values, same length as labels. Required unless series is given."},
                    "xlabel": {"type": "string", "description": "Optional x-axis label."},
                    "ylabel": {"type": "string", "description": "Optional y-axis label."},
                    "color": {"type": "string", "description": "Optional #rrggbb accent colour for a single series."},
                    "theme": {"type": "string", "enum": ["light", "dark"], "description": "light (paper/PDF) or dark (studio). Default light."},
                    "series": {"type": ["array", "null"], "items": {"type": "object"}, "description": "Optional multi-series data for bar/line: a list of {name, values}; labels and every series must have equal length."},
                },
                "required": ["chart_type", "title", "labels"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_pdf",
            "description": (
                "Creates a quality-checked PDF document from markdown-like text. The result names the finished file — never guess or invent a path, and never tell the user which folder it went to. Use this for Executive Summary documents, structured reports, source references, attachments and high-quality summaries."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Document title (also the file-name base)."},
                    "content": {"type": "string", "description": "Body content as markdown-like text (# headings, bullets, paragraphs). A whole line ![chart](/absolute/path.svg) embeds a local chart or diagram; create it with generate_chart or create_diagram using theme='light' so it matches the page."},
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                    "template": {"type": "string", "enum": ["report", "brief", "analysis", "checklist"], "description": "Layout preset: one of report, brief, analysis, checklist."},
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_pitch_deck",
            "description": (
                "Creates a high-end 16:9 pitch deck as quality-checked PDF slides plus an optional animated HTML preview. The result names the finished files. Use this for investor decks, sales decks, product pitches and presentation-ready slides."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Deck topic / title."},
                    "audience": {"type": "string", "description": "Target audience for the deck."},
                    "thesis": {"type": "string", "description": "Core thesis or claim the deck argues."},
                    "slides": {
                        "type": ["array", "string", "null"],
                        "description": "Optional: slide outline as a list of {{title, claim, body, visual}} or markdown sections.",
                    },
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                    "include_animation_preview": {"type": "boolean", "description": "When true, also renders an animated HTML preview of the deck."},
                    "deck_profile": {
                        "type": "string",
                        "enum": ["product-platform", "engineering-platform", "strategy-leadership", "gtm-growth", "finance-ir", "consumer-retail"],
                        "description": "Deck profile: product-platform, engineering-platform, strategy-leadership, gtm-growth, finance-ir, or consumer-retail.",
                    },
                    "design_theme": {
                        "type": "string",
                        "enum": ["evergreen", "executive", "studio"],
                        "description": "Visual theme: evergreen, executive, or studio.",
                    },
                    "source_notes": {
                        "type": "string",
                        "description": "What the deck is based on: user-provided facts, files, assumptions, or missing evidence.",
                    },
                    "evidence_level": {
                        "type": "string",
                        "enum": ["sources", "mixed", "assumptions", "user-provided"],
                        "description": "How strongly the deck is grounded in evidence.",
                    },
                    "enterprise_grade": {
                        "type": "boolean",
                        "description": "When true, applies Fortune-500/board-level scoring and anti-amateur constraints.",
                    },
                    "deck_quality_profile": {
                        "type": "string",
                        "enum": ["enterprise", "board", "investor", "sales"],
                        "description": "Quality profile for Deck Engine v2; enterprise is the local default.",
                    },
                    "brand_kit": {
                        "type": ["object", "null"],
                        "description": "Optional local brand kit object with brand_name, primary, and secondary fields.",
                    },
                    "source_notebook_path": {
                        "type": "string",
                        "description": "Optional absolute or ~-relative path to a local Source Notebook used for evidence-grounded deck generation.",
                    },
                    "asset_paths": {
                        "type": ["array", "string", "null"],
                        "description": "Optional absolute or ~-relative paths to local image/logo/brand assets. Missing assets are surfaced as Studio warnings.",
                    },
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_pptx_deck",
            "description": (
                "Creates a native, editable enterprise pitch deck as .pptx with real text boxes, shapes, scorecard and claim-spine manifest. Use this when the user asks for PowerPoint, PPTX, editable slides or Fortune-500/board-level presentations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Deck topic / title."},
                    "audience": {"type": "string", "description": "Target audience for the deck."},
                    "thesis": {"type": "string", "description": "Core thesis or claim the deck argues."},
                    "slides": {
                        "type": ["array", "string", "null"],
                        "description": "Optional: slide outline as a list of {{title, claim, body, visual, proof}} or markdown sections.",
                    },
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                    "deck_profile": {
                        "type": "string",
                        "enum": ["product-platform", "engineering-platform", "strategy-leadership", "gtm-growth", "finance-ir", "consumer-retail"],
                        "description": "Deck profile: product-platform, engineering-platform, strategy-leadership, gtm-growth, finance-ir, or consumer-retail.",
                    },
                    "design_theme": {
                        "type": "string",
                        "enum": ["evergreen", "executive", "studio"],
                        "description": "Visual theme: evergreen, executive, or studio.",
                    },
                    "source_notes": {"type": "string", "description": "What the deck is based on: user-provided facts, files, assumptions, or missing evidence."},
                    "evidence_level": {
                        "type": "string",
                        "enum": ["sources", "mixed", "assumptions", "user-provided"],
                        "description": "How strongly the deck is grounded in evidence.",
                    },
                    "enterprise_grade": {"type": "boolean", "description": "When true, applies Fortune-500/board-level scoring and anti-amateur constraints."},
                    "template_path": {"type": "string", "description": "Optional absolute or ~-relative path to a .pptx template to base the deck on."},
                    "brand_name": {"type": "string", "description": "Brand name shown on the slides."},
                    "brand_primary": {"type": "string", "description": "Hex color, e.g. #003366"},
                    "brand_secondary": {"type": "string", "description": "Hex color, e.g. #16a34a"},
                    "deck_quality_profile": {
                        "type": "string",
                        "enum": ["enterprise", "board", "investor", "sales"],
                        "description": "Quality profile for Deck Engine v2; enterprise is the local default.",
                    },
                    "source_notebook_path": {
                        "type": "string",
                        "description": "Optional absolute or ~-relative path to a local Source Notebook used for evidence-grounded deck generation.",
                    },
                    "asset_paths": {
                        "type": ["array", "string", "null"],
                        "description": "Optional absolute or ~-relative paths to local image/logo/brand assets. Missing assets are surfaced as Studio warnings.",
                    },
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "inspect_pptx_template",
            "description": "Analyses a local PPTX file as a template: slides, editable text runs, palette, sample texts and warnings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or ~-relative path to the .pptx file to analyse."},
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_pptx_template",
            "description": "Copies an existing PPTX and replaces text runs in-place to preserve the template layout and styles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_path": {"type": "string", "description": "Absolute or ~-relative path to the source .pptx that is copied and edited."},
                    "replacements": {
                        "type": ["object", "array"],
                        "description": "Mapping old_text -> new_text or list of {{from,to}}.",
                    },
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                },
                "required": ["template_path", "replacements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "qa_pptx_deck",
            "description": "Creates a local PPTX QA report and HTML contact sheet for visual review of the slide structure.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pptx_path": {"type": "string", "description": "Absolute or ~-relative path to the .pptx deck to QA."},
                },
                "required": ["pptx_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_svg",
            "description": (
                "Saves SVG graphics code as a .svg file. You write the SVG code yourself. The result names the finished file. For logos, icons, diagrams."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "svg_code": {"type": "string", "description": "The SVG source code to save."},
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                },
                "required": ["svg_code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_xlsx",
            "description": (
                "Creates a real Excel file (.xlsx): styled header, typed cells, safe formulas, number formats, auto filter, frozen header and a bold total row. Cell values starting with = are written as live formulas when they are regular spreadsheet formulas (=SUM(B2:B10), =B2*C2, =IF(...)); unsafe payloads stay inert text. Percentages, currencies (EUR, USD, CHF, GBP) and ISO dates are recognised automatically. Pass the data as rows (JSON array of arrays or CSV text). Use this for tables, evaluations, lists."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title shown as the heading (also the file-name base)."},
                    "data": {
                        "type": "string",
                        "description": "Rows as JSON array of arrays or CSV text (first row = header)",
                    },
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                    "formats": {
                        "type": ["object", "array", "null"],
                        "description": "Optional column formats: an object keyed by header name or 1-based column index, or a list by column position. Each value is a format code or one of currency, percent, integer, decimal, date.",
                    },
                },
                "required": ["title", "data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_docx",
            "description": (
                "Creates a real Word document (.docx) from a markdown subset: # headings, bullets, numbered lists, tables (| a | b |), paragraphs. Use this for letters, reports and documentation as an editable Word file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title shown as the heading (also the file-name base)."},
                    "content": {"type": "string", "description": "Body content as markdown-like text (# headings, bullets, paragraphs)."},
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_qrcode",
            "description": (
                "Creates a real, scannable QR code as PNG. Use this for URLs, WiFi access data, contact data, texts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Content of the QR code (URL, text, WiFi data)"},
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                },
                "required": ["data"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_diagram",
            "description": (
                "Creates a professional SVG diagram in Ephe design. kind: 'mindmap' | 'timeline' | 'flowchart'. items: list of points, optionally 'Label | Description' per point. Use this for mind maps, timelines/roadmaps and process/flow diagrams. theme='dark' (default) is the studio surface; theme='light' is the print palette for embedding in a PDF with a whole line ![diagram](/absolute/path.svg)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["mindmap", "timeline", "flowchart"], "description": "Diagram kind: one of mindmap, timeline, flowchart."},
                    "title": {"type": "string", "description": "Title shown as the heading (also the file-name base)."},
                    "items": {
                        "type": "string",
                        "description": "Points as JSON array or rows in the format 'Label | Description'",
                    },
                    "filename": {"type": "string", "description": "Optional output file name (a bare name, not a path); the result line names the finished file."},
                    "theme": {"type": "string", "enum": ["dark", "light"], "description": "dark (studio, default) or light (paper/PDF)."},
                },
                "required": ["kind", "title", "items"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": (
                "Generates a real image from a text description (text-to-image) and saves it as PNG/JPEG. Use this when the user wants an image, an illustration, a photo motif or an AI graphic. Runs via an OpenAI-compatible /images/generations endpoint — local and free (SD-WebUI/LM-Studio) or cloud (cloud APIs with your own key) depending on the user's setup. Provide a detailed English image description."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Detaillierte Bildbeschreibung (Motiv, Stil, Licht)"},
                    "filename": {"type": "string", "description": "Target file name (optional, ends with .png)"},
                    "size": {"type": "string", "description": "Image size, e.g. '1024x1024' (optional)"},
                },
                "required": ["prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Creates or overwrites a file inside the workspace (approval-gated). "
                "Use for new files or full rewrites; prefer edit_file for targeted changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Target file path — absolute or ~-relative preferred; a workspace-relative path resolves against the active workspace."},
                    "content": {"type": "string", "description": "Full file content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": (
                "Runs a test command in the workspace (pytest / vitest / npm test / python -m pytest) "
                "and returns the output tail. Use this to VERIFY every code change."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Test command, e.g. 'pytest -q tests/test_x.py'"},
                    "cwd": {"type": "string", "description": "Optional working directory inside the active workspace, e.g. 'src' or 'tests' (workspace-relative, not an absolute path)."}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "verify_artifact",
            "description": (
                "Evidence gate for generated deliverables. Verifies that a file or project directory "
                "really exists and is complete (PDF page count, deck slide count, DOCX/XLSX content, "
                "project required files). Returns ARTIFACT_VERIFIED or ARTIFACT_FAILED with metrics. "
                "Always call this before announcing an artifact as finished."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or ~-relative path to the file or project directory to verify."},
                    "checks": {
                        "type": "string",
                        "description": (
                            "JSON object with optional keys: kind (auto|pdf|pptx|docx|xlsx|project|file|image), "
                            "min_pages, min_slides, min_words, min_sheets, min_rows, min_files, min_bytes, "
                            "required_files (array of relative paths)"
                        ),
                    },
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scaffold_project",
            "description": (
                "Project Factory: creates a complete, runnable project skeleton in one call — "
                "manifest, sources, real tests, docs, license, gitignore — then verifies it "
                "structurally. Returns PROJECT_SCAFFOLD_VERIFIED only when the verification gate "
                "passed. Refuses non-empty target directories (nothing is ever overwritten)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_dir": {"type": "string", "description": "Absolute or ~-relative path to a fresh directory inside an allowed root (e.g. ~/Projekte/meine-app) that is empty or absent."},
                    "template": {
                        "type": "string",
                        "description": "One of: python-cli (default), python-api, node-cli, web-app, generic",
                    },
                    "project_name": {"type": "string", "description": "Project name (kebab-case), e.g. 'budget-tracker'"},
                    "description": {"type": "string", "description": "One-line project description for README/manifest"},
                    "author": {"type": "string", "description": "Author name used in the license"},
                },
                "required": ["target_dir"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "build_document",
            "description": (
                "Document Factory: builds a report-grade briefing PDF (NotebookLM-style) from local "
                "source files and optional web research — executive summary, key findings, analysis, "
                "next steps and source notes — then verifies the PDF really has pages. Returns "
                "DOCUMENT_BUILT_VERIFIED with the file path only on success."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Topic/question the briefing answers"},
                    "source_paths": {"type": "string", "description": "Comma-separated absolute or ~-relative paths to local files (txt/md/py/html/pdf) used as evidence."},
                    "include_web_research": {"type": "boolean", "description": "Add web research to the evidence base (default true)"},
                    "filename": {"type": "string", "description": "Optional output filename — the file is delivered as an artifact; the result line names it"},
                },
                "required": ["topic"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "browser_scroll",
            "description": (
                "Scrolls the current browser page in a direction by a pixel amount. Returns the new scroll position."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["up", "down", "left", "right"],
                        "description": "Scroll direction (default: down).",
                    },
                    "amount": {
                        "type": "integer",
                        "description": "Pixels to scroll (default 600).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_evaluate",
            "description": (
                "Evaluates a JavaScript expression in the current page and returns the JSON-serialized result (like Playwright page.evaluate)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "js": {
                        "type": "string",
                        "description": "The JS expression, e.g. 'document.title' or '(() => document.querySelectorAll(\"a\").length)()'.",
                    },
                },
                "required": ["js"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_read",
            "description": ("Reads the clipboard text via the page's navigator.clipboard."),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "clipboard_write",
            "description": ("Writes text to the clipboard via the page's navigator.clipboard."),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The text to place on the clipboard."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_display_info",
            "description": (
                "Returns viewport size, device-pixel-ratio and scroll height of the current page."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "browser_exec",
            "description": (
                "Runs Python against the embedded browser with pre-imported helpers. "
                "Start the code with a one-line comment naming the step. Helpers: new_tab(url), "
                "goto_url(url), wait_for_load(), page_info(), js(expr), fill_input(selector, text), "
                "click_at_xy(x, y), capture_screenshot(), cdp(method, **params). Batch each "
                "sub-procedure into one call. Use for full page interaction in a single round-trip."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python source using the pre-imported browser helpers; print(...) for output.",
                    },
                    "session": {
                        "type": "string",
                        "description": "Isolated browser session name (parallel subagents use one each; omit = shared default).",
                    },
                    "timeout_s": {
                        "type": "integer",
                        "description": "Wall-clock budget for this block in seconds (1-300, default 120). On expiry the output so far is returned and the session namespace is discarded.",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": (
                "Fetches one URL and converts the page to plain text. It returns the extracted text; "
                "answer the user's question from it. Uses a 15-minute response cache. "
                "A failed fetch starts with '[fetch failed]' and a refused target with '[fetch refused]'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch, e.g. 'https://example.com/docs'.",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Accepted for older callers and ignored; the fetched text is returned either way.",
                    },
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_output",
            "description": (
                "Returns status and buffered output of a background shell task started with run_shell(run_in_background=true). "
                "With block=true it waits (up to timeout_s) for completion; with block=false it reads the current state immediately."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task id returned by run_shell, e.g. 'bg1'.",
                    },
                    "block": {
                        "type": "boolean",
                        "description": "Wait for completion (default true) or read the current state immediately.",
                    },
                    "timeout_s": {
                        "type": "number",
                        "description": "Max seconds to wait when block=true (default 30).",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "task_stop",
            "description": (
                "Cancels a running background shell task (the one started with run_shell(run_in_background=true)) and marks it as stopped."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task id returned by run_shell, e.g. 'bg1'.",
                    },
                },
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "agent_message",
            "description": (
                "Continues a finished swarm agent with a new message. The agent's stored conversation history is reused as context."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {
                        "type": "string",
                        "description": "The agent's id (as reported by the swarm run).",
                    },
                    "message": {
                        "type": "string",
                        "description": "The follow-up message for the agent.",
                    },
                },
                "required": ["agent_id", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_video",
            "description": (
                "Records the product demo clips with the built-in media pipeline (Playwright + ffmpeg). "
                "Returns the created GIF/WebP/PNG paths. Optional single case: chat|shell|help|edit."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "case": {
                        "type": "string",
                        "enum": ["chat", "shell", "help", "edit"],
                        "description": "Single clip; omit for the full v4 pipeline (all clips + hero banner).",
                    }
                },
            },
        },
    },
]
