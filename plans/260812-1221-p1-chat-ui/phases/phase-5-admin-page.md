---
phase: 5
title: "Admin Page"
status: pending
plan: 260812-1221-p1-chat-ui
created: 2026-08-12
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 5 — Admin Page

## Overview

Trang quản trị tài liệu tại `/ui/admin`: upload file, xem số chunk đã index, xoá một nguồn.

Đặt ở đường dẫn riêng chứ không nhét vào sidebar của trang chat — đó là điều DEC-1 khoá, và lý do là P3: khi cần khoá, chỉ việc chĩa reverse proxy vào prefix `/ui/admin` cùng `/ingest*` và `DELETE /documents`, không phải viết lại UI.

Phụ thuộc: phase 2 (mount) và **phase 4** (`GET /documents` — trang này tiêu thụ endpoint đó). Cùng sửa `tests/test_ui.py` và `styles.css` với phase 3 nên chạy sau phase 3.

## Files

- **Create** `src/rag_chatbot/api/static/admin/index.html`
- **Create** `src/rag_chatbot/api/static/admin/admin.js`
- **Modify** `src/rag_chatbot/api/static/styles.css` — dùng chung, thêm phần cho admin.
- **Modify** `tests/test_ui.py`

`StaticFiles(html=True)` từ phase 2 tự phục vụ `admin/index.html` cho `/ui/admin/` — không cần thêm mount thứ hai.

## Hợp đồng với API

| Thao tác | Endpoint | Anchor |
|---|---|---|
| Upload | `POST /ingest/upload`, multipart, field tên `file` | `api/routes.py:50-70` |
| Index theo đường dẫn hoặc URL | `POST /ingest` `{path}` **hoặc** `{url}` — đúng một trong hai | `api/routes.py:40-47`, `validate.py:74-78` |
| Đếm chunk | `GET /collections` → `{name, points_count, vector_size}` | `api/routes.py:73-75`, `validate.py:87-90` |
| **Liệt kê nguồn** | `GET /documents` → `{documents[], total}` | phase 4 |
| Xoá nguồn | `DELETE /documents?source=<tên>` → **204 No Content** | `api/routes.py:78-82` |

Ba chi tiết dễ làm sai, đã tra từ code:

1. `DELETE /documents` trả **204 và không có body**. JS gọi `.json()` trên response này sẽ ném lỗi. Kiểm tra `res.status === 204` rồi dừng, đừng parse.
2. `POST /ingest` với cả `path` lẫn `url`, hoặc không có cái nào, trả **422** từ validator (`validate.py:74-78`). Form phải cho chọn một trong hai bằng radio, không để người dùng điền cả hai rồi mới báo lỗi.
3. `total` trong `GET /documents` là số **nguồn**, còn `points_count` trong `/collections` là số **chunk**. Hiện cả hai trên giao diện thì phải gắn nhãn khác nhau rõ ràng, nếu không người dùng sẽ tưởng một trong hai bị sai.

Danh sách tài liệu lấy từ `GET /documents` là **nội dung thật của index**, không phải ghi chép phía client. Sau mỗi lần upload và mỗi lần xoá đều gọi lại endpoint này thay vì tự suy diễn trạng thái trong JS — nguồn sự thật nằm ở Qdrant, không nằm trong bộ nhớ trang.

## Hành vi bắt buộc

- **Chặn cỡ file phía client**: từ chối file lớn hơn 10MB trước khi gửi, kèm thông báo. Lý do: `/ingest/upload` đọc trọn file vào RAM rồi ghi đĩa, không kiểm tra cỡ (`api/routes.py:62`). Đây chỉ là rào phép lịch sự — người dùng vẫn `curl` thẳng được. Rào thật thuộc P3.
- **Chặn đuôi file phía client**: chỉ nhận `.txt`, `.md`, `.pdf` (`README.md:43`). Đuôi khác backend trả 415, nhưng chặn trước cho đỡ mất công upload.
- **Xác nhận trước khi xoá**: `DELETE /documents` xoá toàn bộ chunk của một nguồn và không hoàn tác được. Bắt buộc có bước xác nhận gõ lại tên nguồn.
- **Xoá bằng cách bấm, không bằng cách gõ**: mỗi dòng trong danh sách có nút xoá riêng, tên nguồn lấy từ dữ liệu chứ không từ ô nhập. Vẫn giữ bước xác nhận, nhưng người dùng không còn phải nhớ tên file.
- **Cập nhật sau mỗi thao tác**: sau mỗi upload và mỗi lần xoá, gọi lại **cả** `/documents` và `/collections`, hiện danh sách mới và `points_count` mới.
- **Cảnh báo không auth**: trang phải có một dải cảnh báo thấy rõ — trang này không có xác thực, chỉ dùng ở localhost (DEC-3).

## TDD

**Tests-before (RED)** — thêm vào `tests/test_ui.py`:

1. `test_admin_page_served` — `GET /ui/admin/` trả 200, `content-type` là `text/html`. Kiểm luôn `GET /ui/admin` (không có gạch cuối) kết thúc ở 200 sau redirect.
2. `test_admin_page_has_required_hooks` — HTML chứa `upload-form`, `file-input`, `collection-count`, `documents-list`, `delete-form`, `delete-source-input`.
3. `test_admin_js_never_uses_innerhtml` — cùng bộ cấm như phase 3, áp cho `admin.js`. Tên nguồn do người dùng gõ và tên file upload đều là dữ liệu không tin cậy.
4. `test_admin_page_warns_no_auth` — HTML chứa dòng cảnh báo không có xác thực. Cảnh báo này là một phần của hợp đồng an toàn P1/P3, phải có test giữ.

**Implement** → xanh.

**Regression**: `uv run pytest` (56 + 4 = 60), ruff, black, mypy. Commit khi xanh.

## Success

Đo bằng máy:

- [ ] 4 test mới xanh, tổng 60 test.
- [ ] ruff / black / mypy sạch.

Nghiệm thu bằng tay. Điều kiện: Qdrant đang chạy và `.env` có `OPENAI_API_KEY` thật — upload gọi embedding API thật, tốn tiền theo số chunk:

- [ ] Upload `data/documents/sample_faq.txt` → hiện `chunks_indexed > 0`, `points_count` tăng, và file xuất hiện trong danh sách tài liệu.
- [ ] Hỏi ở `/ui` một câu về nội dung file vừa upload → trả lời được, nguồn trỏ đúng tên file.
- [ ] Xoá nguồn đó bằng nút trên dòng danh sách → biến mất khỏi danh sách và `points_count` trở về mức trước khi upload.
- [ ] Tải lại trang → danh sách vẫn đúng, vì nó đến từ `GET /documents` chứ không từ bộ nhớ trang.
- [ ] Upload file `.docx` → bị chặn ngay ở client, không phát sinh request.
- [ ] Gửi `POST /ingest` với đúng một trong `path`/`url` → 200; giao diện không cho phép gửi cả hai.
- [ ] Huỷ ở bước xác nhận xoá → không có request nào được gửi.

## Risks

- **Xoá nhầm không hoàn tác được**: `delete_by_source` xoá sạch chunk của nguồn (`orchestrator.py:102-103`). Bước xác nhận là rào duy nhất trong P1. Nút xoá nằm ngay cạnh mỗi dòng nên rủi ro bấm nhầm **cao hơn** so với phương án gõ tên — bù lại bằng hộp xác nhận nêu rõ tên nguồn và số chunk sắp mất.
- **`.json()` trên 204**: đã nêu, là lỗi kinh điển với endpoint kiểu này.
- **Danh sách và số đếm lệch nhau**: `GET /documents` và `/collections` là hai lần gọi riêng. Nếu chỉ làm mới một cái sau thao tác, giao diện sẽ tự mâu thuẫn với chính nó. Luôn gọi cả hai.
- **Upload trùng tên**: `/ingest/upload` ghi đè file cùng tên trong `data/uploads/` (`api/routes.py:61-62`), và pipeline xoá chunk cũ của nguồn đó trước khi ghi mới (`docs/ARCHITECTURE.md`, phần idempotent). Hành vi này đúng, nhưng UI nên nói cho người dùng biết là "ghi đè", không im lặng.
