---
phase: 1
title: "P1 Acceptance"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 1 — P1 Acceptance

## Overview

Đóng nợ nghiệm thu thủ công còn treo từ plan P1. Hai artifact ghi `manual-acceptance: SKIP`:

- `plans/260812-1221-p1-chat-ui/artifacts/verification-P3.json` — *"HOÃN, chưa chạy: cần Qdrant server nên cần docker pull, mà daemon chưa có root CA Vingroup (cần sudo)."*
- `plans/260812-1221-p1-chat-ui/artifacts/verification-P5.json` — *"HOÃN cùng phase 3: cần Qdrant server, mà docker daemon chưa pull được vì thiếu root CA."*

Chướng ngại đó **không còn**: `verification-P6.json` ghi `container-smoke: PASS` với chi tiết *"ĐÃ CHẠY THẬT trong container (docker compose, cổng host 8001 → 8000)"*. Tức là docker đã pull được. Ghi chú cuối của P6 nói rõ khoản nợ duy nhất còn lại: *"nghiệm thu thủ công trên trình duyệt (phase 3 và 5) — cần `OPENAI_API_KEY` thật."*

**Phase này KHÔNG viết một dòng code nào.** Đây là việc **người dùng phải tự làm**: nó cần một Qdrant thật đang chạy, một `OPENAI_API_KEY` thật (tốn tiền thật), ít nhất một tài liệu đã nạp, và một trình duyệt do người thật bấm. Không agent nào thay thế được, và không bước nào trong `pytest` chứng minh được thay.

Phụ thuộc: không có. Đây là node gốc.

Vì sao nó đứng đầu chứ không chạy song song: nếu nghiệm thu phát hiện lỗi, lỗi đó thuộc P1 và phải sửa trước — sửa một lỗi P1 sau khi phase 3/4 đã chồng thay đổi lên `app.js` và `index.html` là gỡ rối trong đống rối.

## Files

Không tạo, không sửa file nguồn nào.

Đầu ra duy nhất: `plans/260817-1100-p2-multiturn-hybrid/artifacts/verification-P1.json`.

Nếu nghiệm thu phát hiện lỗi thật, **dừng phase, báo cáo, và sửa như một việc P1 riêng** — không lặng lẽ vá trong phase này.

## TDD

Phase này **không có vòng đỏ→xanh**, và nói dối về điều đó sẽ làm hỏng ý nghĩa của trường `tdd-red` trong toàn bộ chuỗi verification. Không có code mới thì không có test mới.

- **Tests-before (RED)**: không áp dụng. Ghi `tdd-red: N/A` kèm lý do "phase không viết code" vào verification.
- **Implement**: không áp dụng.
- **Regression gate**: vẫn chạy đủ bốn cổng để xác nhận nhánh đang ở trạng thái sạch trước khi plan bắt đầu sửa gì:

```
uv run pytest -q                 → 78 passed, không hơn không kém
uv run ruff check src tests      → sạch
uv run black --check src tests   → sạch
uv run mypy src                  → sạch
```

Bốn lệnh lấy từ `docs/code-standards.md:10-15`. Con số 78 lấy từ `docs/code-standards.md:17` và đã đo lại [OBSERVED].

## Chuẩn bị

```bash
docker compose up -d qdrant          # hoặc: docker run -d -p 6333:6333 qdrant/qdrant
cp .env.example .env                 # đặt OPENAI_API_KEY thật
uv run python scripts/ingest.py      # nạp data/documents/
uv run rag-chatbot
```

Lệnh lấy từ `docs/SETUP.md` mục "Option B". `scripts/ingest.py` nạp `data/documents/`, hiện có `sample_faq.txt` và `sample_guide.md` [OBSERVED: `git ls-files data/`].

**Cảnh báo chi phí**: từ đây trở đi mọi câu hỏi đều gọi OpenAI thật. Với `gpt-4o-mini` và vài chục câu thì không đáng kể, nhưng đây khác hẳn 78 test chạy offline bằng `FakeEmbedder`/`FakeLLM` (`tests/conftest.py:17-53`).

## Danh mục nghiệm thu

Chép nguyên từ phần "Nghiệm thu bằng tay" của `plans/260812-1221-p1-chat-ui/phases/phase-3-chat-page.md` và phase 5 tương ứng. Mỗi dòng ghi PASS/FAIL kèm quan sát thật, không ghi "OK".

**Trang chat `/ui` (nợ của P1 phase 3):**

- [ ] Hỏi một câu có trong `sample_faq.txt` → hiện câu trả lời, panel bên phải liệt kê nguồn kèm `score` và `page`.
- [ ] Bấm `[1]` trong câu trả lời → panel cuộn tới nguồn 1 và làm nổi nó (`app.js:70-78`).
- [ ] Kéo `top_k` lên 10 → số nguồn trả về tăng theo.
- [ ] Tắt `include_sources` → panel rỗng, câu trả lời vẫn có.
- [ ] Hỏi câu không liên quan gì tới tài liệu → hiện đúng `NO_CONTEXT_ANSWER` (`llm_generator/prompts.py:8`), panel rỗng, trang không vỡ.
- [ ] Tắt Qdrant **sau khi** app đã khởi động rồi hỏi → thông báo lỗi rõ ràng trong luồng chat, không treo spinner vĩnh viễn. (R1 của P1: Qdrant chết **trước khi** app khởi động thì cả trang không tải được — hành vi đã biết, không phải bug.)
- [ ] Nạp một `.txt` chứa `<img src=x onerror=alert(1)>` rồi hỏi câu chạm vào nó → chuỗi hiện ra **dạng chữ** trong snippet, không hộp thoại nào bật lên.
- [ ] Nhãn một-lượt (`id="single-turn-notice"`, `index.html:17-20`) hiển thị đúng và nói đúng sự thật hiện tại.

**Trang admin `/ui/admin` (nợ của P1 phase 5):**

- [ ] Upload một `.txt` → `chunks_indexed > 0`, file xuất hiện trong danh sách, `points_count` tăng.
- [ ] Xoá nguồn đó → biến mất khỏi danh sách, `points_count` giảm về mức cũ.
- [ ] Tải lại trang → danh sách vẫn đúng (chứng minh nó đọc từ index thật chứ không từ `localStorage` — đây là toàn bộ lý do DEC-4 tồn tại).
- [ ] Cảnh báo không-auth (`id="no-auth-warning"`) hiển thị.

## Success

- [ ] Bốn cổng sạch, `pytest -q` đúng **78 passed**.
- [ ] Toàn bộ 12 dòng nghiệm thu ở trên có kết quả **PASS hoặc FAIL kèm quan sát cụ thể** — không dòng nào để trống, không dòng nào ghi "chắc là được".
- [ ] `artifacts/verification-P1.json` có check `manual-acceptance` với `status: PASS` (hoặc `FAIL` kèm danh sách lỗi tìm được). **`SKIP` ở phase này là thất bại của phase**, vì đóng khoản `SKIP` chính là toàn bộ mục đích của nó.
- [ ] Nếu tìm ra lỗi: mỗi lỗi được ghi thành một dòng riêng với đường dẫn file nghi ngờ, và phase 2 **không được bắt đầu** cho tới khi lỗi được xử lý hoặc được chấp nhận có ý thức bằng một ghi chú.

## Risks

- **Người dùng không có sẵn Qdrant / key khi cook chạy tới đây.** Đây là rủi ro thật và cao nhất của phase. Xử: cook **dừng và hỏi**, không tự ghi `SKIP` rồi đi tiếp — vì đi tiếp chính là lặp lại đúng cái đã xảy ra ở P1. Nếu người dùng chọn hoãn, thì đó là quyết định của người dùng và phải ghi kèm tên người quyết định.
- **Cám dỗ tự động hoá bằng một test giả.** Không có cách nào viết một `pytest` chứng minh "bấm `[1]` thì panel cuộn tới". P1 đã đối mặt chuyện này và giải bằng test quét chuỗi tài sản — và cũng chính P1 để lại bài học `test_app_js_never_uses_innerhtml` **xanh giả vì `app.js` còn trả 404** (`docs/code-standards.md:84-87`). Đừng thêm một test kiểu đó nữa để cảm thấy an tâm.
- **Nghiệm thu tìm ra lỗi làm trượt lịch cả plan.** Chấp nhận có ý thức. Phát hiện một lỗi P1 ở đây rẻ hơn nhiều so với phát hiện nó ở phase 4 khi `app.js` đã bị sửa.
</content>
