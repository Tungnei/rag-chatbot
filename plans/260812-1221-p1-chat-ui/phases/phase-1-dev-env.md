---
phase: 1
title: "Dev Env"
status: pending
plan: 260812-1221-p1-chat-ui
created: 2026-08-12
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 1 — Dev Env

## Overview

Dựng môi trường chạy được test. Đây là phase bắt buộc chứ không phải thủ tục: máy này **chưa có `uv` và chưa có `.venv`**, nên 45 test trong repo chưa từng chạy ở đây. Một plan `--tdd` mà không chạy được test thì mọi bước "đỏ → xanh" phía sau đều là lời nói suông.

[OBSERVED] `which uv` không tìm thấy; `~/.local/bin/uv`, `~/.cargo/bin/uv`, `/usr/local/bin/uv` đều không tồn tại; `ls .venv` báo không có thư mục.

Phase này **không đụng file nào trong repo**. Không commit.

## Files

Không tạo, không sửa file nào trong repo. Việc duy nhất chạm vào git là **tạo nhánh**: repo đang ở `main` và toàn bộ P1 phải nằm trên `feat/ui-chat-static` (khớp `branch:` trong frontmatter của plan).

```bash
git switch -c feat/ui-chat-static
```

## TDD

Phase hạ tầng, không có cặp đỏ-xanh. Thay vào đó là một mốc đo:

- **Cài `uv`**: `curl -LsSf https://astral.sh/uv/install.sh | sh`, mở lại shell hoặc `source ~/.bashrc` cho `~/.local/bin` vào `PATH`.
- **Đồng bộ phụ thuộc**: `uv sync` (kéo Python 3.11 theo `.python-version` + toàn bộ dev group ở `pyproject.toml:39-47`).
- **Chạy mốc**: `uv run pytest` — ghi lại con số chính xác.

## Success

- [ ] `uv --version` in ra phiên bản.
- [ ] `git branch --show-current` in ra `feat/ui-chat-static`.
- [ ] `uv run pytest` xanh và số test đúng bằng **45**. Con số này có hai nguồn khớp nhau: README công bố (`README.md:56`) và đếm tĩnh số hàm `test_` trong `tests/` [OBSERVED: grep đếm được đúng 45]. Lệch số thì dừng và điều tra trước khi sang phase 2 — mốc sai thì mọi so sánh về sau vô nghĩa.
- [ ] `uv run ruff check src tests`, `uv run black --check src tests`, `uv run mypy src` đều sạch **trước khi** viết bất cứ dòng nào. Nếu chúng đã đỏ sẵn, ghi lại nguyên trạng để không nhầm lỗi cũ thành lỗi do P1 gây ra.

## Risks

- Cài `uv` bằng script từ internet: nếu môi trường chặn mạng thì rơi về `pipx install uv` hoặc `pip install --user uv`. Không rơi về "chạy test trong Docker" — người dùng đã loại phương án đó.
- `uv sync` sẽ tải Python 3.11 riêng nếu hệ thống không có. Lần đầu chậm, không phải lỗi.
- Nếu 45 test **không** xanh ngay từ mốc, đó là phát hiện thuộc về repo chứ không thuộc P1: báo lại người dùng, đừng vá lấp để đi tiếp.
