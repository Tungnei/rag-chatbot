---
id: 260812-1221-p1-chat-ui
title: "P1 — Giao dien chat tinh phuc vu tai /ui"
description: "Trang tinh vanilla JS do FastAPI phuc vu tai /ui va /ui/admin, khong them dependency, chi chay localhost."
status: in_progress
priority: P1
effort: "6 phases"
mode: hard
tdd: true
branch: feat/ui-chat-static
tags: [frontend, fastapi, static, rag]
created: 2026-08-12
author: user:v.tungnt200@vinsmartfuture.tech
decisions: [DEC-1, DEC-2, DEC-3, DEC-4]
phases:
  - phases/phase-1-dev-env.md
  - phases/phase-2-static-mount.md
  - phases/phase-3-chat-page.md
  - phases/phase-4-list-endpoint.md
  - phases/phase-5-admin-page.md
  - phases/phase-6-docs-smoke.md
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Plan: P1 — Giao diện chat tĩnh phục vụ tại /ui

## Tổng quan

Xây giao diện web để hỏi chatbot, dưới dạng **trang tĩnh vanilla JS do chính FastAPI phục vụ** — không thêm một dependency nào vào `pyproject.toml`, không thêm service nào vào compose.

Hai trang:

- `/ui` — khung chat hai cột: hội thoại bên trái, panel nguồn bên phải, cộng bảng tham số (`top_k`, `include_sources`) và hiển thị `latency_ms` / `tokens_used`.
- `/ui/admin` — upload tài liệu, xem danh sách nguồn thật đang có trong index, xoá nguồn.

Backend gần như không đổi. Hai thay đổi Python, không hơn:

1. Mount `StaticFiles` trong `api/app.py` (phase 2).
2. Thêm `GET /documents` để liệt kê nguồn thật trong index (phase 4) — quyết định ở gate validate, ghi tại DEC-4. Không đụng `llm_generator/`, không đụng đường truy vấn, không đổi hành vi endpoint nào đang có.

Phạm vi vận hành đợt này là **localhost**. Việc mở ra internet là P3 và bị DEC-3 chặn.

## Quyết định đã khoá

Không re-litigate. Nguồn: [docs/decisions.md](../../docs/decisions.md) và phiên phỏng vấn của plan này.

| ID | Nội dung ràng buộc plan này |
|---|---|
| DEC-1 | Trang tĩnh vanilla JS phục vụ tại `/ui`; admin tách đường dẫn `/ui/admin`. Gradio và React đã bị loại, không mở lại. |
| DEC-2 | Hội thoại nhiều lượt thuộc P2. P1 **không** được thêm `history` vào `QueryRequest`. |
| DEC-3 | Không tự viết auth trong FastAPI; P1 chỉ chạy localhost, không đổi CORS, không đổi port binding. |
| Phỏng vấn | Dựng môi trường bằng `uv` cài lên máy thật (không chạy test trong Docker). |
| Phỏng vấn | Bố cục chat **hai cột** (chat + panel nguồn), không phải một cột kiểu ChatGPT. |
| DEC-4 | Thêm `GET /documents` vào backend để trang admin liệt kê nguồn thật. Phương án ghi chép `localStorage` đã bị loại. |
| Phỏng vấn | Câu trả lời render **văn bản thuần** (`white-space: pre-wrap`), không parse markdown, không sửa `SYSTEM_PROMPT`. |
| Phỏng vấn | R1 (Qdrant chết thì `/ui` không mở được) **chấp nhận** trong P1, chỉ ghi vào docs. Không bọc `try-except` quanh `startup()`. |

## Ràng buộc (constraint-scan)

Đã quét, kết quả:

- Repo này **không có** `ownership.yaml`, `stage-policy.yaml`, hay `schemas/` — không phải repo clone harness. Không có zone/policy nào chi phối vị trí file. [OBSERVED: `ls` trả về "No such file or directory" cho cả ba]
- Ràng buộc thật đến từ chính repo:

| Ràng buộc | Anchor |
|---|---|
| `ruff` + `black` line-length 100, target py311; lint select `E,F,I,UP,B` | `pyproject.toml:49-58` |
| `mypy` python_version 3.11, chạy trên `src` | `pyproject.toml:60-62`, `README.md:58` |
| `pytest` chỉ đọc `testpaths = ["tests"]`, `asyncio_mode = "auto"` | `pyproject.toml:64-66` |
| `api/` là module sở hữu toàn bộ bề mặt FastAPI — UI phải nằm trong đó, không tạo top-level package mới | `docs/ARCHITECTURE.md` bảng Module responsibilities |
| Toàn bộ test chạy offline qua `FakeEmbedder` / `FakeLLM` | `tests/conftest.py:17-51` |
| Không thêm runtime dependency | DEC-1 |

## Phases

| # | Theme | Phụ thuộc | Cỡ | Test sau phase |
|---|---|---|---|---|
| 1 | Dev Env — cài `uv`, `uv sync`, 45 test xanh làm mốc | — | S | 45 |
| 2 | Static Mount — `StaticFiles` tại `/ui`, test đỏ→xanh | 1 | S | 48 |
| 3 | Chat Page — hai cột, trích dẫn bấm được, bảng tham số | 2 | L | 52 |
| 4 | List Endpoint — `GET /documents` xuyên 5 tầng backend | 1 | M | 56 |
| 5 | Admin Page — `/ui/admin`: upload, danh sách, xoá nguồn | 2, 3, 4 | M | 60 |
| 6 | Docs + Smoke — README/docs, smoke thật trong container | 3, 4, 5 | S | 60 |

Phase 3 và 5 cùng sửa `tests/test_ui.py` và `styles.css`, nên `plan-graph.yaml` có cạnh nối tiếp giữa chúng để không rơi vào cùng một lô song song. Phase 4 về lý thuyết chạy song song được với 2 và 3 (khác hoàn toàn tập file), nhưng plan này chạy tuần tự — không dùng `--parallel`, vì lợi ích tiết kiệm thời gian ở quy mô này không bù được rủi ro trộn hai vùng thay đổi trong một lần review.

## Out of scope

Cố ý **không** làm đợt này:

- Streaming câu trả lời (cần endpoint SSE + đường async mới; backend hiện đồng bộ — `orchestrator.py:68-83`).
- Hội thoại nhiều lượt / trí nhớ ngữ cảnh — thuộc P2, DEC-2.
- Xác thực, rate limit, siết CORS, trần chi tiêu — thuộc P3, DEC-3.
- Build toolchain (npm, bundler, framework). Không có `package.json`.
- Đa ngôn ngữ giao diện, theme switcher, tối ưu mobile chuyên sâu. Trang chỉ cần không vỡ ở màn hình hẹp.
- Render markdown trong câu trả lời — hiển thị văn bản thuần, giữ xuống dòng.
- Phân trang / lọc / sắp xếp cho `GET /documents`. Endpoint trả toàn bộ danh sách, hết.
- Tối ưu `GET /documents` bằng API `facet` của Qdrant. Chỉ xét lại khi `points_count` vượt khoảng 50.000 **và** đã đo được độ trễ thật.
- Sửa bất kỳ logic truy vấn hay sinh câu trả lời nào. Thay đổi backend duy nhất được phép là `GET /documents` và cái mount ở phase 2.

## Acceptance (toàn plan)

- [ ] `uv run pytest` xanh — 60 test: 45 mốc **cộng** 15 test mới của phase 2/3/4/5, và không test cũ nào phải sửa để xanh.
- [ ] `uv run ruff check src tests`, `uv run black --check src tests`, `uv run mypy src` đều sạch.
- [ ] `GET /ui` trả 200 với `content-type: text/html`; `GET /ui/admin` trả 200.
- [ ] Hỏi một câu qua UI: hiện câu trả lời, panel nguồn liệt kê từng `source` kèm `score` và `page`, và bấm `[1]` trong câu trả lời cuộn panel tới đúng nguồn số 1.
- [ ] Bảng tham số: `top_k` không cho vượt khoảng 1–20 (`validate.py:58`), toggle `include_sources` thật sự đổi payload, hiện `latency_ms` và `tokens_used` sau mỗi câu.
- [ ] `GET /documents` trả đúng danh sách nguồn thật, tổng `chunks` của các nguồn khớp `points_count` ở `/collections`.
- [ ] `/ui/admin`: upload một `.txt` → `chunks_indexed > 0`, file xuất hiện trong danh sách, `points_count` tăng; xoá nguồn đó → biến mất khỏi danh sách và `points_count` giảm về mức cũ; tải lại trang thì danh sách vẫn đúng.
- [ ] Nội dung tài liệu chứa HTML thô (ví dụ `<img onerror=...>`) hiển thị ra **dưới dạng chữ**, không thực thi. Được thi hành bằng máy qua test cấm `innerHTML`/`eval` trong JS (P1 không có test trình duyệt — thêm Playwright là thêm dependency, trái DEC-1), và kiểm bằng tay một lần ở phase 3.
- [ ] `docker compose up --build -d` rồi `curl -sL -o /dev/null -w '%{http_code}' localhost:8000/ui` trả `200` — chứng minh file tĩnh thật sự vào được image. Cờ `-L` bắt buộc: `/ui` bị chuyển 307 sang `/ui/`.
- [ ] `README.md` và `docs/QUICK_REFERENCE.md` ghi đường dẫn `/ui`, `/ui/admin` và cảnh báo "chưa có auth, chỉ chạy localhost".

## Rollback

Mỗi phase một commit riêng trên nhánh `feat/ui-chat-static`. Hoàn tác bằng `git revert <sha>` hoặc `git revert <range>`.

Rủi ro hoàn tác gần như bằng 0: plan này **không** tạo migration, không đổi schema, không đổi định dạng dữ liệu trong Qdrant. Trạng thái duy nhất phát sinh là file người dùng upload qua `/ui/admin` nằm trong `data/uploads/` — revert code không xoá chúng, phải xoá tay hoặc qua `DELETE /documents`.

Phase 1 (cài `uv`) không nằm trong git, hoàn tác bằng cách gỡ binary; nó không đụng repo.

## Risks

| # | Rủi ro | Bằng chứng | Xử lý |
|---|---|---|---|
| R1 | **UI chết cùng Qdrant.** `lifespan` gọi `startup()` → `ensure_collection()` gọi Qdrant thật; Qdrant sập thì uvicorn không boot, nên `/ui` cũng không tải được. Trang UI không bao giờ tự báo được "backend lỗi". | `api/app.py:30-31`, `retrieval/vector_search.py:24-33` | Chấp nhận có ý thức trong P1, ghi rõ trong `docs/SETUP.md` ở phase 6. Không cố hack cho `/ui` sống sót khi app không boot — sửa đúng chỗ là tách `ensure_collection` khỏi lifespan, và đó là thay đổi backend nằm ngoài P1. |
| R2 | **XSS từ chính tài liệu đã index.** Câu trả lời và `snippet` bắt nguồn từ nội dung tài liệu; nếu render bằng `innerHTML` để làm `[1]` bấm được thì tài liệu độc hại chèn được HTML vào DOM. | `orchestrator.py:118-128` trả `snippet` thô từ `chunk.text` | Bắt buộc: dựng DOM bằng `textContent` + `createElement`, tách `[n]` bằng regex trên chuỗi rồi tạo `<button>` riêng. Cấm `innerHTML` với mọi dữ liệu từ API. Có test ở phase 3. |
| R3 | **File tĩnh không vào được image.** Nếu app chạy từ site-packages thay vì `/app/src`, `Path(__file__).parent/"static"` trỏ sai. | `Dockerfile:24-25`, `configs.py:16-17`, `docker-compose.yaml:24-25` | Đã hạ rủi ro bằng suy luận: `PROJECT_ROOT = parents[2]` đang được dùng cho `configs/` và `data/`, và volume mount `./data/documents:/app/data/documents` chỉ đúng khi app chạy từ `/app/src`. Tức là giả định này **ứng dụng đã phụ thuộc sẵn**, P1 không thêm giả định mới. Vẫn `[ASSUMED]` cho tới khi smoke ở phase 6 chạy thật. |
| R4 | **Upload không giới hạn dung lượng.** `/ingest/upload` đọc trọn file vào RAM rồi ghi đĩa, không kiểm tra cỡ. UI kéo-thả làm việc này dễ xảy ra hơn nhiều so với `curl`. | `api/routes.py:58-62` | P1 chỉ chặn phía client (từ chối file > 10MB trước khi gửi) và hiện lỗi rõ ràng. Giới hạn thật ở tầng server thuộc P3 — ghi vào phần Out of scope của phase 5, không âm thầm sửa route. |
| R5 | **Trang admin không có rào nào.** Ai vào được `/ui/admin` là xoá được index. | `api/routes.py:78-82` | P1 chỉ localhost (DEC-3). Phase 6 phải in cảnh báo trong README. Tách sẵn đường dẫn `/ui/admin` chính là để P3 chỉ cần chĩa proxy vào một prefix. |
| R9 | **`GET /documents` mở rộng bề mặt cần khoá ở P3.** Nó phơi ra tên mọi tài liệu đã index — trước đây `/collections` chỉ trả một con số vô hại. | DEC-4 | Không phải vấn đề của P1 (localhost), nhưng **P3 phải xếp `GET /documents` vào nhóm admin** cùng `/ingest*` và `DELETE /documents`, không để chung nhóm với `/query`. Đã ghi vào DEC-4 để P3 không bỏ sót. |
| R6 | **`/ui` có thể nuốt route khác.** Mount sai thứ tự hoặc mount vào `/` sẽ che `/docs`, `/health`. | `api/app.py:58` | Mount tại prefix `/ui` chứ không phải `/`, và mount **sau** `include_router`. Test phase 2 phải khẳng định `/health` và `/docs` vẫn 200 sau khi mount. |
| R7 | **`GET /documents` duyệt toàn bộ điểm.** `scroll` là O(số chunk); index lớn thì endpoint chậm dần, và trang admin gọi nó sau **mỗi** thao tác. | phase 4, `retrieval/vector_search.py` | Chấp nhận ở quy mô hiện tại. Điều kiện đổi sang `facet` đã ghi rõ trong Out of scope — đo trước, đổi sau. Bắt buộc `with_vectors=False`, thiếu nó là kéo cả collection vector về mỗi lần liệt kê. |
| R8 | **Thêm method vào `VectorStore` Protocol có sức lan.** Mọi implementation phải có `list_sources()`. | `adaptor/protocols.py:31-44` | Đã kiểm: chỉ có một implementation (`QdrantVectorStore`), và test dùng chính lớp đó với `QdrantClient(":memory:")` (`tests/conftest.py:69-73`) — không có fake nào phải cập nhật. `mypy src` là thứ bắt lỗi này ngay nếu sai. |
