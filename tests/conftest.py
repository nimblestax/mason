import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


class _Workspace(BaseHTTPRequestHandler):
    """Just enough of a workspace for `databricks bundle validate` to run offline."""

    def do_GET(self) -> None:
        if "/scim/v2/Me" in self.path:
            self._reply(200, {"id": "1", "userName": "ci@example.com"})
        elif "/workspace/get-status" in self.path:
            self._reply(200, {"object_type": "DIRECTORY", "object_id": 1})
        else:
            self._reply(404, {"error_code": "RESOURCE_DOES_NOT_EXIST", "message": "not found"})

    def do_POST(self) -> None:
        self._reply(200, {})

    def _reply(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format: str, *args: object) -> None:
        pass  # Keeps test output clean.


@pytest.fixture
def stub_workspace() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Workspace)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
