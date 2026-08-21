---
phase: 2
title: "Static Mount"
status: pending
plan: 260812-1221-p1-chat-ui
created: 2026-08-12
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 2 — Static Mount

## Overview

Mở đường cho UI: mount `StaticFiles` tại prefix `/ui` trong app factory, kèm một `index.html` tối thiểu chỉ để chứng minh đường ống chạy. Nội dung thật của trang là phase 3.

Đây là **toàn bộ** thay đổi Python của P1. Sau phase này, backend không được sửa thêm dòng nào nữa.

Phụ thuộc: phase 1 (phải chạy được `pytest`).

## Files

- **Modify** `src/rag_chatbot/api/app.py` — import `StaticFiles`, khai báo `STATIC_DIR`, mount sau `include_router`.
- **Create** `src/rag_chatbot/api/static/index.html` — placeholder tối thiểu, hợp lệ HTML5.
- **Create** `tests/test_ui.py` — file test mới, tách khỏi `tests/test_api.py` để phase 3 và 4 mở rộng cùng một chỗ.

Hình dạng thay đổi trong `app.py` (mount **sau** `app.include_router(router)` ở dòng 58, không phải trước):

```python
STATIC_DIR = Path(__file__).resolve().parent / "static"
...
app.include_router(router)
app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="ui")
return app
```

Dùng `Path(__file__).parent`, **không** dùng `PROJECT_ROOT` của `configs.py:16`: thư mục static thuộc về package `api/`, đường dẫn nên bám vào chính module đó thay vì bám vào bố cục repo.

## TDD

**Tests-before (RED)** — viết `tests/test_ui.py` trước khi sửa `app.py`, cả ba phải fail vì `/ui` chưa tồn tại:

1. `test_ui_index_served` — `client.get("/ui/")` trả 200 và header `content-type` bắt đầu bằng `text/html`.
2. `test_ui_bare_path_redirects_to_index` — `client.get("/ui")` (TestClient tự theo redirect) kết thúc ở 200. Ghi rõ trong test tại sao: Starlette chuyển `/ui` sang `/ui/` bằng 307, nên `curl` **không có `-L` sẽ thấy 307 chứ không phải 200** — đây là cái bẫy khiến người ta tưởng mount hỏng. `[PRIOR]` — hành vi redirect này là kiến thức về Starlette, chưa chạy thật ở máy này (chưa cài được `fastapi`); chính test này là thứ xác minh nó. Nếu thực tế trả 200 thẳng không qua redirect thì sửa lời chú thích trong test, đừng sửa test cho khớp lời chú thích.
3. `test_mount_does_not_shadow_api` — sau khi mount, `/health` vẫn 200 và `/docs` vẫn 200. Đây là test giữ cho R6 không tái diễn.

**Implement** → xanh: thêm mount + `index.html` placeholder.

**Regression**: `uv run pytest` (45 + 3 = 48), `uv run ruff check src tests`, `uv run black --check src tests`, `uv run mypy src`. Commit khi cả bốn xanh.

## Success

- [ ] 3 test mới đã fail đúng lý do trước khi implement (fail vì 404, không phải fail vì lỗi import).
- [ ] `uv run pytest` xanh với 48 test.
- [ ] `/health`, `/docs`, `/query` không đổi hành vi.
- [ ] `mypy src` sạch — chú ý `StaticFiles(directory=...)` nhận `Path`, không cần `str()`.

## Risks

- Mount vào `/` thay vì `/ui` sẽ che toàn bộ API. Test số 3 tồn tại chính vì việc này.
- `StaticFiles(directory=...)` **ném lỗi ngay lúc tạo app** nếu thư mục không tồn tại. Nghĩa là thiếu `index.html`/thiếu thư mục sẽ làm hỏng cả `create_app()`, kéo sập 45 test cũ chứ không chỉ test UI. Tạo thư mục và file placeholder **trong cùng commit** với dòng mount.
- `html=True` là thứ khiến `/ui/admin/` ở phase 5 tự phục vụ `static/admin/index.html`. Đừng bỏ cờ này.
