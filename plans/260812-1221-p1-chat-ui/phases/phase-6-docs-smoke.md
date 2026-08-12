---
phase: 6
title: "Docs Smoke"
status: pending
plan: 260812-1221-p1-chat-ui
created: 2026-08-12
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 6 — Docs + Smoke

## Overview

Hai việc, cả hai đều là nghiệm thu chứ không phải dọn dẹp:

1. **Smoke trong container** — chứng minh file tĩnh thật sự vào được image. Đây là chỗ duy nhất trong plan giải quyết được R3; trước phase này nó vẫn là `[ASSUMED]`.
2. **Cập nhật tài liệu** — `/ui` và `/ui/admin` chỉ tồn tại với người dùng nếu docs nói ra, kèm cảnh báo không có auth.

Phụ thuộc: phase 3, 4 và 5.

## Files

- **Modify** `README.md` — thêm `/ui`, `/ui/admin` vào phần Quick start, và thêm **`GET /documents`** vào bảng API (`README.md:34-41`). Endpoint mới mà không có trong bảng thì coi như không tồn tại với người đọc.
- **Modify** `docs/QUICK_REFERENCE.md` — lệnh mở UI.
- **Modify** `docs/PROJECT_STRUCTURE.md` — thêm `api/static/` vào cây thư mục, và thêm `DocumentSummary` / `DocumentList` vào bảng "Key types" (phase 4 đưa chúng vào `validate.py`).
- **Modify** `docs/SETUP.md` — ghi hành vi đã biết ở R1: Qdrant chết thì app không khởi động được, nên `/ui` cũng không mở được; cách kiểm tra là `docker compose ps` và `curl localhost:8000/health`.
- **Modify** `docs/ARCHITECTURE.md` — một dòng trong bảng Module responsibilities: `api/static/` phục vụ giao diện, không chứa logic. Thêm `list_sources()` vào phần mô tả `VectorStore`, vì Protocol đã đổi ở phase 4 và tài liệu kiến trúc đang liệt kê đúng bộ method cũ.

## Smoke thật (bắt buộc chạy, không phải suy luận)

```bash
docker compose up --build -d
curl -s -o /dev/null -w '%{http_code}\n' -L localhost:8000/ui
curl -s -o /dev/null -w '%{http_code}\n' -L localhost:8000/ui/admin
curl -s -o /dev/null -w '%{http_code}\n' localhost:8000/health
docker compose down
```

Cờ `-L` là bắt buộc: Starlette chuyển `/ui` sang `/ui/` bằng 307, `curl` không có `-L` sẽ báo 307 và làm người ta tưởng mount hỏng.

Kỳ vọng: `200`, `200`, `200`. Nếu `/ui` trả 404 trong container mà chạy tốt ở máy thật thì R3 đã thành hiện thực — khi đó chuyển thư mục static ra gốc repo và thêm `COPY static ./static` vào `Dockerfile` cạnh dòng 25 (`COPY configs ./configs`), rồi trỏ `STATIC_DIR` qua `PROJECT_ROOT` của `configs.py:16`. Nhánh dự phòng này đã được nghĩ sẵn, không phải ứng biến.

Ghi kết quả smoke (ba mã status thật, không phải kỳ vọng) vào artifact nghiệm thu của phase.

## TDD

Phase tài liệu, không có cặp đỏ-xanh mới. Vẫn phải chạy lại toàn bộ gate:

- `uv run pytest` — 60 test xanh.
- `uv run ruff check src tests`, `uv run black --check src tests`, `uv run mypy src`.

## Success

- [ ] Ba lệnh smoke trả `200 / 200 / 200`, và con số thật được ghi lại.
- [ ] `README.md` có `/ui` trong Quick start và trong bảng API, kèm một dòng cảnh báo: chưa có xác thực, chỉ chạy localhost.
- [ ] `docs/PROJECT_STRUCTURE.md` phản ánh đúng cây thư mục sau P1.
- [ ] `docs/SETUP.md` mô tả hành vi R1 để người sau không mất thời gian tưởng UI hỏng.
- [ ] Toàn bộ gate xanh.
- [ ] `docker compose down` đã chạy, không để container treo.

## Risks

- **Docs viết theo kỳ vọng thay vì theo thực tế**: chỉ ghi những gì smoke vừa chứng minh. Nếu `/ui/admin` trả 404 thì viết đúng như vậy và quay lại phase 5, đừng ghi 200 cho tròn.
- **Build lại image tốn thời gian**: `docker compose up --build` chạy lại `uv sync --frozen` (`Dockerfile:11`). Bình thường, không phải lỗi.
- **`.env` phải tồn tại**: compose khai báo `env_file: .env` (`docker-compose.yaml:17-18`); thiếu file này thì `docker compose up` fail trước cả khi bàn tới static. Kiểm tra `.env` trước khi kết luận về R3.
