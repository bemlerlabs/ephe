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
            "name": "stop_workspace_dev_server",
            "description": (
                "Stops a dev server this session started, by the port start_workspace_dev_server returned."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "port": {"type": "integer", "description": "The port the start call returned."},
                },
                "required": ["port"],
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

