"""The browser UI is served as static files by the API itself."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rag_chatbot_tung.api.app import STATIC_DIR, create_app


@pytest.fixture
def client(settings, orchestrator):
    with TestClient(create_app(settings, orchestrator=orchestrator)) as c:
        yield c


def test_ui_index_served(client):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_ui_bare_path_redirects_to_index(client):
    # Starlette answers /ui with a 307 to /ui/; TestClient follows redirects, curl does
    # not unless given -L. A bare `curl localhost:8000/ui` reporting 307 is the mount
    # working, not the mount broken. Asserted without following, so the test actually
    # observes the redirect instead of any path that happens to end in a 200.
    redirect = client.get("/ui", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"].endswith("/ui/")
    assert client.get("/ui").status_code == 200


# Markup-injecting sinks, plus the inline-handler and javascript: routes a substring
# scan of the JS alone would miss. Split so the constant does not trip its own check.
BANNED_MARKUP = (
    "inner" + "HTML",
    "outer" + "HTML",
    "insertAdjacent" + "HTML",
    "document.write",
    "eval(",
    "new Function(",
    "srcdoc",
    "createContextualFragment",
    "javascript:",
    'setAttribute("on',
    "setAttribute('on",
)


def test_chat_page_has_required_hooks(client):
    html = client.get("/ui/").text
    for element_id in (
        "chat-form",
        "question-input",
        "messages",
        "sources-panel",
        "top-k",
        "include-sources",
    ):
        assert f'id="{element_id}"' in html


def test_static_assets_served(client):
    for path in ("/ui/app.js", "/ui/styles.css"):
        assert client.get(path).status_code == 200


def test_no_static_asset_injects_markup():
    """Scan every shipped asset, not a hardcoded pair of paths.

    Answers and snippets come from indexed documents, so they are untrusted text. This
    walks STATIC_DIR, which means a file added later is covered by construction rather
    than by someone remembering to extend a list.

    It is a barrier, not a proof: the textContent discipline still has to be kept by
    hand, and a determined author can evade a substring scan. It exists to make the
    unsafe route something you have to work at rather than something you can reach for.
    """
    assets = sorted(STATIC_DIR.rglob("*.js")) + sorted(STATIC_DIR.rglob("*.html"))
    # Two pages and their two scripts. A lower number means the walk found nothing and
    # the loop below would pass by doing no work at all.
    assert len(assets) >= 4, f"only found {[a.name for a in assets]}"

    for asset in assets:
        text = asset.read_text(encoding="utf-8")
        for banned in BANNED_MARKUP:
            assert banned not in text, f"{asset.name} uses {banned}"


def test_page_states_single_turn(client):
    # The transcript looks like a chat, but the backend gets no history. Saying so is
    # part of the contract with the user, so it gets a test rather than good intentions.
    html = client.get("/ui/").text
    assert 'id="single-turn-notice"' in html
    assert "không nhớ" in html


def test_admin_page_served(client):
    response = client.get("/ui/admin/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert client.get("/ui/admin").status_code == 200


def test_admin_page_has_required_hooks(client):
    html = client.get("/ui/admin/").text
    for element_id in (
        "upload-form",
        "file-input",
        "collection-count",
        "documents-list",
        "delete-form",
        "delete-source-input",
    ):
        assert f'id="{element_id}"' in html


def test_admin_assets_served(client):
    assert client.get("/ui/admin/admin.js").status_code == 200


def test_admin_page_warns_no_auth(client):
    # The page can wipe the index and has no authentication in front of it. Saying so
    # is part of the P1/P3 safety contract, so it gets a test.
    html = client.get("/ui/admin/").text
    assert 'id="no-auth-warning"' in html
    assert "xác thực" in html


def test_mount_does_not_shadow_api(client):
    # Mounting at "/" instead of "/ui", or mounting before the router, would swallow
    # the whole API. This guard is green from the start by design: it fails only if a
    # later change moves the mount.
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
