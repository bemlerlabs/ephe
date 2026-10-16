"""Self-check for generate_image — fails when the logic breaks. No framework, no fixtures.

Covers: the import, registry registration, schema exposure, the no-endpoint error path,
and the real b64_json roundtrip against a local mock endpoint (a real PNG on disk).
"""
import asyncio, base64, os, struct, sys, threading, zlib
from http.server import BaseHTTPRequestHandler, HTTPServer


def _make_png() -> bytes:
    """Build a real 1x1 RGBA PNG via zlib/struct (no invented blob)."""
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1, 8bit, RGBA
    raw = b"\x00" + b"\x00\x00\x00\xFF"                    # filter-byte + 1 RGBA pixel
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


PNG = _make_png()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        import traceback
        try:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = {"data": [{"b64_json": base64.b64encode(PNG).decode()}]}
            raw = __import__("json").dumps(body).encode()
            self.send_response(200, [("Content-Type", "application/json")])
            self.end_headers()
            self.wfile.write(raw)
            self.wfile.flush()
        except Exception:
            traceback.print_exc()
            raise

    def log_message(self, *a):
        pass


def main():
    # A) import + registry + schema
    from core.tools import generate_image, TOOL_MAP, get_tool_schemas
    assert "generate_image" in TOOL_MAP, "nicht in TOOL_MAP"
    assert "generate_image" in get_tool_schemas()[0].keys() or any(
        s["function"]["name"] == "generate_image" for s in get_tool_schemas()
    ), "Schema fehlt"
    print("OK import+registry+schema")

    # B) no endpoint -> an honest error message, NO invented image
    for k in ("EPHE_IMAGE_BASE_URL", "EPHE_IMAGE_API_KEY", "EPHE_IMAGE_MODEL",
              "EPHE_OPENAI_COMPAT_BASE_URL", "EPHE_OPENAI_COMPAT_API_KEY"):
        os.environ.pop(k, None)
    # neutralise the active provider (otherwise it falls back to the DGX default)
    import core.model_provider as mp
    orig = mp.get_active_provider
    mp.get_active_provider = lambda *a, **k: (_ for _ in ()).throw(Exception("no provider"))
    r = asyncio.run(generate_image(prompt="a cat"))
    mp.get_active_provider = orig
    assert r.startswith("[image error:") and "no image endpoint" in r, f"no-endpoint wrong: {r}"
    print("OK no-endpoint -> ehrlicher Fehler:", r[:60])

    # C) empty prompt
    r = asyncio.run(generate_image(prompt="   "))
    assert "empty description" in r, f"empty wrong: {r}"
    print("OK empty prompt ->", r[:50])

    # D) real b64_json roundtrip against a local mock -> a real PNG on disk
    srv = HTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    os.environ["EPHE_IMAGE_BASE_URL"] = f"http://127.0.0.1:{port}/v1"
    os.environ["EPHE_IMAGE_API_KEY"] = "test"
    out = os.path.expanduser("~/Downloads/ephe_selfcheck.png")
    if os.path.exists(out):
        os.remove(out)
    r = asyncio.run(generate_image(prompt="a cat", filename="ephe_selfcheck.png"))
    srv.shutdown()
    assert r.startswith("PNG_FILE:"), f"roundtrip wrong: {r}"
    path = r.split("PNG_FILE:", 1)[1].strip()
    assert os.path.exists(path), f"datei fehlt: {path}"
    head = open(path, "rb").read(8)
    assert head == b"\x89PNG\r\n\x1a\n", f"kein echtes PNG: {head!r}"
    print("OK roundtrip ->", path, os.path.getsize(path), "bytes, PNG-Magic korrekt")
    os.remove(path)
    print("\nALLE CHECKS GRUEN")


if __name__ == "__main__":
    sys.argv[1:] = []  # shove aside the argv text http.server would read
    main()
