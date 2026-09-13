#!/usr/bin/env python3
"""Run a two-origin P00 iframe prototype with intentional CSP boundaries."""
from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parent
PARENT_ORIGIN = "http://127.0.0.1:4273"

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory: str, role: str, **kwargs):
        self.role = role
        super().__init__(*args, directory=directory, **kwargs)

    def end_headers(self) -> None:
        if self.role == "parent":
            self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self' data: blob:; frame-src http://localhost:4274; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'")
        else:
            self.send_header("Content-Security-Policy", f"default-src 'self'; frame-ancestors {PARENT_ORIGIN}; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

def server(host: str, port: int, directory: Path, role: str) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), lambda *args, **kwargs: Handler(*args, directory=str(directory), role=role, **kwargs))

if __name__ == "__main__":
    parent = server("127.0.0.1", 4273, ROOT, "parent")
    embed = server("127.0.0.1", 4274, ROOT, "embed")
    Thread(target=embed.serve_forever, daemon=True).start()
    print("Parent: http://127.0.0.1:4273/parent/\nEmbed:  http://localhost:4274/embed/")
    try:
        parent.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        parent.shutdown()
        embed.shutdown()
