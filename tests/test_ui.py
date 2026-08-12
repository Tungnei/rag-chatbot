"""The browser UI is served as static files by the API itself."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_chatbot_tung.api.app import create_app


@pytest.fixture
def client(settings, orchestrator):
    with TestClient(create_app(settings, orchestrator=orchestrator)) as c:
        yield c


def test_ui_index_served(client):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_ui_bare_path_redirects_to_index(client):
    # Starlette answers /ui with a 307 to /ui/; TestClient follows redirects, curl
    # does not unless given -L. A bare `curl localhost:8000/ui` reporting 307 is the
    # mount working, not the mount broken.
    assert client.get("/ui").status_code == 200


def test_mount_does_not_shadow_api(client):
    # Mounting at "/" instead of "/ui", or mounting before the router, would swallow
    # the whole API. This guard is green from the start by design: it fails only if a
    # later change moves the mount.
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
