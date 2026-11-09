"""The child half of the plugin bridge: ask the host, wait, take the answer or the refusal.

core/sandbox/bridge_client.py

The confined worker is what runs this file, and that fact decides its shape. Measured on the
production rail, the child cannot import `core` — the repository root is behind the boundary
and `import core` answers `PermissionError` — so the client is not something a plugin imports
by name: `worker_launcher` hands it to the callable as a third argument when the callable
asks for one. A plugin that needs nothing keeps the two-argument signature it
has always had, and nothing about the bridge reaches it.

What it can reach is `core/sandbox/bridge.py`, the envelope codec, because the launcher's own
directory is the one piece of this repository the worker is allowed to read and the child
starts with it on `sys.path`. The codes, the version marker and the grammar of an envelope
have that one home, so the two halves of the bridge cannot drift into speaking different
protocols. The import below resolves in both directions: beside the launcher inside the
worker, and through the package in the host, where a test drives this class over in-memory
pipes.

The wire is the pipe the tool already speaks on. A request goes out as one line on stdout,
the host's answer comes back as one line on stdin, and the call blocks in between. There is
one outstanding call at a time, which is what makes the id a check rather than a
multiplexer: an answer that names a different request than the one waiting is a protocol
fault, and the client says so instead of handing back somebody else's result.

A refusal is an exception with a code on it, never a string to parse. The codes are the
host's, listed in `bridge.py`; the plugin author reads them in the manifest reference, and
the human reads the audit row the same call wrote.
"""
from __future__ import annotations

import itertools
import sys
from typing import Any

try:  # inside the confined worker the codec sits beside this file, on the launcher's path
    from bridge import (
        ARGS_INVALID,
        BRIDGE_VERSION,
        INTERNAL,
        METHOD_DENIED,
        METHOD_UNKNOWN,
        PAYLOAD_TOO_LARGE,
        RATE_LIMITED,
        BridgeError,
        encode_request,
        parse_reply,
    )
except ImportError:  # in the host the same module is reached as part of the package
    from core.sandbox.bridge import (
        ARGS_INVALID,
        BRIDGE_VERSION,
        INTERNAL,
        METHOD_DENIED,
        METHOD_UNKNOWN,
        PAYLOAD_TOO_LARGE,
        RATE_LIMITED,
        BridgeError,
        encode_request,
        parse_reply,
    )

__all__ = [
    "ARGS_INVALID",
    "BRIDGE_VERSION",
    "Bridge",
    "BridgeError",
    "INTERNAL",
    "METHOD_DENIED",
    "METHOD_UNKNOWN",
    "PAYLOAD_TOO_LARGE",
    "RATE_LIMITED",
]


class Bridge:
    """One worker run's handle on the host. Created by the launcher, never by a plugin."""

    def __init__(self, out: Any = None, inp: Any = None) -> None:
        self._out = out if out is not None else sys.stdout
        self._inp = inp if inp is not None else sys.stdin
        self._ids = itertools.count(1)

    def call(self, method: str, **args: Any) -> Any:
        """Ask for one bridged method and wait for the answer."""
        call_id = next(self._ids)
        self._out.write(encode_request(call_id, method, args))
        self._out.flush()

        line = self._inp.readline()
        if not line:
            raise BridgeError(INTERNAL, "the host closed the bridge mid-call")
        reply = parse_reply(line)
        if reply is None:
            raise BridgeError(INTERNAL, "the host answered on a protocol this worker does not speak")
        if reply.get("id") != call_id:
            raise BridgeError(
                INTERNAL,
                f"the answer names request {reply.get('id')!r}, this one is {call_id}",
            )
        if not reply.get("ok"):
            raise BridgeError(
                str(reply.get("code") or INTERNAL), str(reply.get("detail") or "")
            )
        return reply.get("result")

    def fetch(self, url: str) -> dict[str, Any]:
        """Read one URL through the host. The convenience the first bundle actually calls."""
        return self.call("fetch", url=url)

    def search(self, query: str, max_results: int | None = None) -> dict[str, Any]:
        """Run one query through the host. The text is the kernel tool's own sentence.

        `max_results` stays off the wire when the caller left it out, so the host function
        keeps the default it already documents.
        """
        if max_results is None:
            return self.call("search", query=query)
        return self.call("search", query=query, max_results=max_results)

    def fetch_url(self, url: str, prompt: str | None = None) -> dict[str, Any]:
        """Run the kernel page tool. The text is that function's own sentence.

        `prompt` stays off the wire when the caller left it out. The kernel tool
        accepts the argument and does not answer it.
        """
        if prompt is None:
            return self.call("fetch_url", url=url)
        return self.call("fetch_url", url=url, prompt=prompt)

    def memory_add(
        self, target: str, content: str | None = None, old_text: str | None = None,
        memory_type: str | None = None, supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Ask the host to add one entry. Omitted fields stay off the wire."""
        return self.call("memory_add", **_memory_fields(
            target, content=content, old_text=old_text,
            memory_type=memory_type, supersedes=supersedes,
        ))

    def memory_replace(
        self, target: str, content: str | None = None, old_text: str | None = None,
        memory_type: str | None = None, supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Ask the host to correct one entry. Omitted fields stay off the wire."""
        return self.call("memory_replace", **_memory_fields(
            target, content=content, old_text=old_text,
            memory_type=memory_type, supersedes=supersedes,
        ))

    def memory_remove(
        self, target: str, content: str | None = None, old_text: str | None = None,
        memory_type: str | None = None, supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Ask the host to remove one entry. Omitted fields stay off the wire."""
        return self.call("memory_remove", **_memory_fields(
            target, content=content, old_text=old_text,
            memory_type=memory_type, supersedes=supersedes,
        ))

    def memory_list(
        self, target: str, content: str | None = None, old_text: str | None = None,
        memory_type: str | None = None, supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Ask the host to list one tier. Omitted fields stay off the wire."""
        return self.call("memory_list", **_memory_fields(
            target, content=content, old_text=old_text,
            memory_type=memory_type, supersedes=supersedes,
        ))

    def memory_action(
        self, action: str, target: str, content: str | None = None,
        old_text: str | None = None, memory_type: str | None = None,
        supersedes: str | None = None,
    ) -> dict[str, Any]:
        """Ask the host to judge an action outside the four.

        The four actions have their own methods. This one exists so an unknown
        action still receives the kernel sentence. The host refuses to run a
        known action through it.
        """
        return self.call("memory_action", action=action, **_memory_fields(
            target, content=content, old_text=old_text,
            memory_type=memory_type, supersedes=supersedes,
        ))

    def browser_go(self, url: str) -> dict[str, Any]:
        """Open one address through the host. The kernel tool owns the address check."""
        return self.call("browser_go", url=url)

    def browser_screenshot(self) -> dict[str, Any]:
        """Ask the host for the current page image. The sentence names the file."""
        return self.call("browser_screenshot")

    def browser_click(self, target_description: str) -> dict[str, Any]:
        """Ask the host to click a described target in the page."""
        return self.call("browser_click", target_description=target_description)

    def browser_type(self, text: str) -> dict[str, Any]:
        """Ask the host to type. The text stays an argument."""
        return self.call("browser_type", text=text)

    def browser_press(self, key: str) -> dict[str, Any]:
        """Ask the host to press one key."""
        return self.call("browser_press", key=key)

    def browser_scroll(
        self, direction: str | None = None, amount: int | None = None,
    ) -> dict[str, Any]:
        """Ask the host to scroll. A field the caller left out stays off the wire."""
        payload: dict[str, Any] = {}
        if direction is not None:
            payload["direction"] = direction
        if amount is not None:
            payload["amount"] = amount
        return self.call("browser_scroll", **payload)

    def browser_evaluate(self, js: str) -> dict[str, Any]:
        """Ask the host to evaluate one expression in the page."""
        return self.call("browser_evaluate", js=js)

    def browser_exec(
        self, code: str, session: str | None = None, timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Ask the host to run one browser block.

        `session` and `timeout_s` stay off the wire when the caller left them
        out, so the kernel function keeps the defaults it already documents.
        """
        payload: dict[str, Any] = {"code": code}
        if session is not None:
            payload["session"] = session
        if timeout_s is not None:
            payload["timeout_s"] = timeout_s
        return self.call("browser_exec", **payload)

    def vision_click(self, target_description: str) -> dict[str, Any]:
        # The confirmation stays in the kernel function. The description stays an argument.
        return self.call("vision_click", target_description=target_description)

    def vision_type(self, text: str, press_enter: bool | None = None) -> dict[str, Any]:
        # press_enter stays off the wire when the caller left it out.
        if press_enter is None:
            return self.call("vision_type", text=text)
        return self.call("vision_type", text=text, press_enter=press_enter)

    def analyze_image(
        self,
        path: str,
        question: str | None = None,
        region: list | None = None,
    ) -> dict[str, Any]:
        # question and region stay off the wire when the caller left them out.
        payload: dict[str, Any] = {"path": path}
        if question is not None:
            payload["question"] = question
        if region is not None:
            payload["region"] = region
        return self.call("analyze_image", **payload)

    def run_shell(
        self,
        command: str,
        cwd: str | None = None,
        run_in_background: bool | None = None,
    ) -> dict[str, Any]:
        # cwd and run_in_background stay off the wire when the caller left them out.
        payload: dict[str, Any] = {"command": command}
        if cwd is not None:
            payload["cwd"] = cwd
        if run_in_background is not None:
            payload["run_in_background"] = run_in_background
        return self.call("run_shell", **payload)

    def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        return self.call("read_file", **payload)

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        return self.call("write_file", path=path, content=content)

    def edit_file(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": path,
            "old_string": old_string,
            "new_string": new_string,
        }
        if replace_all is not None:
            payload["replace_all"] = replace_all
        return self.call("edit_file", **payload)

    def list_directory(self, path: str) -> dict[str, Any]:
        return self.call("list_directory", path=path)

    def file_search(self, query: str, path: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query}
        if path is not None:
            payload["path"] = path
        return self.call("file_search", **payload)

    def load_workspace(
        self,
        path: str,
        extensions: list | None = None,
        max_depth: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if extensions is not None:
            payload["extensions"] = extensions
        if max_depth is not None:
            payload["max_depth"] = max_depth
        return self.call("load_workspace", **payload)

    def analyze_project(self, path: str) -> dict[str, Any]:
        return self.call("analyze_project", path=path)

    def run_tests(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"command": command}
        if cwd is not None:
            payload["cwd"] = cwd
        return self.call("run_tests", **payload)

    def run_linter(
        self,
        path: str,
        fix: bool | None = None,
        max_issues: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if fix is not None:
            payload["fix"] = fix
        if max_issues is not None:
            payload["max_issues"] = max_issues
        return self.call("run_linter", **payload)

    def format_code(self, path: str, check_only: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if check_only is not None:
            payload["check_only"] = check_only
        return self.call("format_code", **payload)

    def scaffold_project(
        self,
        target_dir: str,
        template: str | None = None,
        project_name: str | None = None,
        description: str | None = None,
        author: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"target_dir": target_dir}
        if template is not None:
            payload["template"] = template
        if project_name is not None:
            payload["project_name"] = project_name
        if description is not None:
            payload["description"] = description
        if author is not None:
            payload["author"] = author
        return self.call("scaffold_project", **payload)

    def create_pdf(
        self,
        title: str,
        content: str,
        filename: str | None = None,
        template: str | None = None,
        document: bool | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "content": content}
        if filename is not None:
            payload["filename"] = filename
        if template is not None:
            payload["template"] = template
        if document is not None:
            payload["document"] = document
        return self.call("create_pdf", **payload)

    def create_docx(
        self, title: str, content: str, filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "content": content}
        if filename is not None:
            payload["filename"] = filename
        return self.call("create_docx", **payload)

    def create_qrcode(
        self,
        data: str,
        filename: str | None = None,
        fill_color: str | None = None,
        back_color: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"data": data}
        if filename is not None:
            payload["filename"] = filename
        if fill_color is not None:
            payload["fill_color"] = fill_color
        if back_color is not None:
            payload["back_color"] = back_color
        return self.call("create_qrcode", **payload)

    def extract_pdf_text(
        self, path: str, max_chars: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if max_chars is not None:
            payload["max_chars"] = max_chars
        return self.call("extract_pdf_text", **payload)

    def build_document(
        self,
        topic: str,
        source_paths: str | None = None,
        include_web_research: bool | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"topic": topic}
        if source_paths is not None:
            payload["source_paths"] = source_paths
        if include_web_research is not None:
            payload["include_web_research"] = include_web_research
        if filename is not None:
            payload["filename"] = filename
        return self.call("build_document", **payload)

    def export_source_brief(
        self,
        notebook_path: str,
        question: str | None = None,
        filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"notebook_path": notebook_path}
        if question is not None:
            payload["question"] = question
        if filename is not None:
            payload["filename"] = filename
        return self.call("export_source_brief", **payload)

    def create_source_notebook(
        self,
        paths: list | str,
        title: str | None = None,
        notebook_id: str | None = None,
        extensions: list | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"paths": paths}
        if title is not None:
            payload["title"] = title
        if notebook_id is not None:
            payload["notebook_id"] = notebook_id
        if extensions is not None:
            payload["extensions"] = extensions
        return self.call("create_source_notebook", **payload)

    def query_source_notebook(
        self,
        notebook_path: str,
        question: str,
        max_chunks: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "notebook_path": notebook_path,
            "question": question,
        }
        if max_chunks is not None:
            payload["max_chunks"] = max_chunks
        return self.call("query_source_notebook", **payload)

    def verify_artifact(
        self, path: str, checks: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if checks is not None:
            payload["checks"] = checks
        return self.call("verify_artifact", **payload)

    def create_xlsx(
        self,
        title: str,
        data,
        filename: str | None = None,
        path: str | None = None,
        formats: dict | list | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"title": title, "data": data}
        if filename is not None:
            payload["filename"] = filename
        if path is not None:
            payload["path"] = path
        if formats is not None:
            payload["formats"] = formats
        return self.call("create_xlsx", **payload)

    def generate_chart(
        self,
        chart_type: str,
        title: str,
        labels,
        values=None,
        xlabel: str | None = None,
        ylabel: str | None = None,
        color: str | None = None,
        theme: str | None = None,
        series=None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chart_type": chart_type,
            "title": title,
            "labels": labels,
        }
        if values is not None:
            payload["values"] = values
        if xlabel is not None:
            payload["xlabel"] = xlabel
        if ylabel is not None:
            payload["ylabel"] = ylabel
        if color is not None:
            payload["color"] = color
        if theme is not None:
            payload["theme"] = theme
        if series is not None:
            payload["series"] = series
        return self.call("generate_chart", **payload)

    def create_pptx_deck(
        self,
        topic: str,
        slides=None,
        audience: str | None = None,
        thesis: str | None = None,
        filename: str | None = None,
        deck_profile: str | None = None,
        design_theme: str | None = None,
        source_notes: str | None = None,
        evidence_level: str | None = None,
        enterprise_grade: bool | None = None,
        template_path: str | None = None,
        brand_name: str | None = None,
        brand_primary: str | None = None,
        brand_secondary: str | None = None,
        deck_quality_profile: str | None = None,
        source_notebook_path: str | None = None,
        asset_paths=None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"topic": topic}
        if slides is not None:
            payload["slides"] = slides
        if audience is not None:
            payload["audience"] = audience
        if thesis is not None:
            payload["thesis"] = thesis
        if filename is not None:
            payload["filename"] = filename
        if deck_profile is not None:
            payload["deck_profile"] = deck_profile
        if design_theme is not None:
            payload["design_theme"] = design_theme
        if source_notes is not None:
            payload["source_notes"] = source_notes
        if evidence_level is not None:
            payload["evidence_level"] = evidence_level
        if enterprise_grade is not None:
            payload["enterprise_grade"] = enterprise_grade
        if template_path is not None:
            payload["template_path"] = template_path
        if brand_name is not None:
            payload["brand_name"] = brand_name
        if brand_primary is not None:
            payload["brand_primary"] = brand_primary
        if brand_secondary is not None:
            payload["brand_secondary"] = brand_secondary
        if deck_quality_profile is not None:
            payload["deck_quality_profile"] = deck_quality_profile
        if source_notebook_path is not None:
            payload["source_notebook_path"] = source_notebook_path
        if asset_paths is not None:
            payload["asset_paths"] = asset_paths
        return self.call("create_pptx_deck", **payload)

    def create_pitch_deck(
        self,
        topic: str,
        slides=None,
        audience: str | None = None,
        thesis: str | None = None,
        filename: str | None = None,
        include_animation_preview: bool | None = None,
        deck_profile: str | None = None,
        design_theme: str | None = None,
        source_notes: str | None = None,
        evidence_level: str | None = None,
        enterprise_grade: bool | None = None,
        deck_quality_profile: str | None = None,
        brand_kit: dict | None = None,
        source_notebook_path: str | None = None,
        asset_paths=None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"topic": topic}
        if slides is not None:
            payload["slides"] = slides
        if audience is not None:
            payload["audience"] = audience
        if thesis is not None:
            payload["thesis"] = thesis
        if filename is not None:
            payload["filename"] = filename
        if include_animation_preview is not None:
            payload["include_animation_preview"] = include_animation_preview
        if deck_profile is not None:
            payload["deck_profile"] = deck_profile
        if design_theme is not None:
            payload["design_theme"] = design_theme
        if source_notes is not None:
            payload["source_notes"] = source_notes
        if evidence_level is not None:
            payload["evidence_level"] = evidence_level
        if enterprise_grade is not None:
            payload["enterprise_grade"] = enterprise_grade
        if deck_quality_profile is not None:
            payload["deck_quality_profile"] = deck_quality_profile
        if brand_kit is not None:
            payload["brand_kit"] = brand_kit
        if source_notebook_path is not None:
            payload["source_notebook_path"] = source_notebook_path
        if asset_paths is not None:
            payload["asset_paths"] = asset_paths
        return self.call("create_pitch_deck", **payload)

    def inspect_pptx_template(
        self, path: str, filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"path": path}
        if filename is not None:
            payload["filename"] = filename
        return self.call("inspect_pptx_template", **payload)

    def edit_pptx_template(
        self,
        template_path: str,
        replacements,
        filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "template_path": template_path,
            "replacements": replacements,
        }
        if filename is not None:
            payload["filename"] = filename
        return self.call("edit_pptx_template", **payload)

    def qa_pptx_deck(self, pptx_path: str) -> dict[str, Any]:
        return self.call("qa_pptx_deck", pptx_path=pptx_path)

    def create_diagram(
        self,
        kind: str,
        title: str,
        items,
        filename: str | None = None,
        theme: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": kind, "title": title, "items": items}
        if filename is not None:
            payload["filename"] = filename
        if theme is not None:
            payload["theme"] = theme
        return self.call("create_diagram", **payload)

    def create_svg(
        self, svg_code: str, filename: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"svg_code": svg_code}
        if filename is not None:
            payload["filename"] = filename
        return self.call("create_svg", **payload)

    def generate_image(
        self,
        prompt: str,
        filename: str | None = None,
        size: str | None = None,
    ) -> dict[str, Any]:
        # filename and size stay off the wire when the caller left them out.
        payload: dict[str, Any] = {"prompt": prompt}
        if filename is not None:
            payload["filename"] = filename
        if size is not None:
            payload["size"] = size
        return self.call("generate_image", **payload)

    def synthesize(self, text: str) -> dict[str, Any]:
        """Speak one sentence through the local piper writer."""
        return self.call("synthesize", text=text)

    def transcribe(self, name: str) -> dict[str, Any]:
        """Transcribe one file already stored in the session audio folder."""
        return self.call("transcribe", name=name)


def _memory_fields(
    target: str, *, content: str | None, old_text: str | None,
    memory_type: str | None, supersedes: str | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"target": target}
    if content is not None:
        payload["content"] = content
    if old_text is not None:
        payload["old_text"] = old_text
    if memory_type is not None:
        payload["memory_type"] = memory_type
    if supersedes is not None:
        payload["supersedes"] = supersedes
    return payload
