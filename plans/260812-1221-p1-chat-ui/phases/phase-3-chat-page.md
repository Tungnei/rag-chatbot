---
phase: 3
title: "Chat Page"
status: pending
plan: 260812-1221-p1-chat-ui
created: 2026-08-12
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 3 — Chat Page

## Overview

Trang chat thật tại `/ui`: bố cục **hai cột** — hội thoại bên trái, panel nguồn bên phải — cộng bảng tham số. Bấm `[1]` trong câu trả lời thì panel cuộn tới và làm nổi nguồn số 1.

Phase nặng nhất của P1, nhưng **không có một dòng Python nào**.

Phụ thuộc: phase 2.

## Files

- **Modify** `src/rag_chatbot/api/static/index.html` — thay placeholder bằng trang thật.
- **Create** `src/rag_chatbot/api/static/styles.css`
- **Create** `src/rag_chatbot/api/static/app.js`
- **Modify** `tests/test_ui.py` — thêm nhóm test cho trang chat.

Tách ba file thay vì nhồi một `index.html` là mở rộng có chủ ý của DEC-1: quyết định đó khoá "trang tĩnh vanilla JS, không thêm dependency", không khoá số lượng file. Ba file vẫn không cần build step.

## Hợp đồng với API

Chỉ gọi đúng một endpoint:

```
POST /query   {question, top_k, include_sources}
           →  {answer, sources[], model, tokens_used, latency_ms}
```

Anchor: `api/routes.py:35-37`, `validate.py:56-68`.

Ràng buộc lấy thẳng từ schema, UI phải tự tôn trọng trước khi gửi:

| Trường | Ràng buộc | Anchor |
|---|---|---|
| `question` | 1–2000 ký tự | `validate.py:57` |
| `top_k` | 1–20, hoặc bỏ trống để backend dùng mặc định 3 | `validate.py:58`, `configs/default.yaml:23` |
| `include_sources` | bool, mặc định `true` | `validate.py:59` |

`sources[]` gồm `source`, `snippet`, `score`, `page` (`validate.py:38-42`). `snippet` bị cắt cứng 240 ký tự ở backend (`orchestrator.py:28`, `orchestrator.py:123`) — UI không được hứa hiển thị trọn đoạn văn, vì nó không có trọn đoạn văn.

Thứ tự `sources[]` khớp thứ tự đánh số `[1] [2]` mà prompt yêu cầu LLM trích dẫn (`llm_generator/prompts.py:15`, `prompts.py:25-31`). Đây là cơ sở để `[n]` bấm được. **Nhưng đây là quy ước, không phải bảo đảm**: khi ngân sách token cắt bớt passage (`prompts.py:29-32`) hoặc khi model trích dẫn `[4]` trong lúc chỉ có 3 nguồn, `n` sẽ trỏ ra ngoài mảng. UI phải xử lý: `[n]` không có nguồn tương ứng thì hiển thị như chữ thường, không tạo nút, không ném lỗi JS.

## Hành vi bắt buộc

- **Trạng thái chờ**: không streaming (`orchestrator.py:68-83` gọi đồng bộ), câu trả lời mất vài giây. Phải có skeleton hoặc spinner ngay khi bấm gửi, và khoá nút gửi tới khi có phản hồi.
- **Nhãn một-lượt**: trang hiển thị lịch sử hội thoại nhưng **mỗi câu hỏi là độc lập** — backend không nhận `history` (DEC-2). Phải có một dòng ghi chú thấy được trên giao diện nói đúng điều đó. Khung chat mà im lặng về việc này là đang nói dối người dùng.
- **Lỗi**: `fetch` hỏng hoặc status ≠ 200 thì hiện thông báo lỗi trong luồng chat kèm status code, không nuốt lỗi vào console.
- **Ghi nhớ tham số**: `top_k` và `include_sources` lưu `localStorage`. Lịch sử chat **không** lưu — nó chỉ nằm trong bộ nhớ trang, đúng với bản chất một-lượt.
- **Số liệu**: hiện `latency_ms` và `tokens_used` dưới mỗi câu trả lời.

## An toàn khi render (R2 — không thương lượng)

Câu trả lời và `snippet` đều bắt nguồn từ nội dung tài liệu đã index. Tài liệu có thể chứa HTML.

Quy tắc: **cấm `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval` trong toàn bộ `app.js`.** Dựng DOM bằng `document.createElement` và gán chữ bằng `textContent`. Để làm `[n]` bấm được, tách chuỗi câu trả lời bằng regex `/\[(\d+)\]/g`, phần chữ đi vào `createTextNode`, phần `[n]` đi vào `document.createElement("button")`.

Không dùng thư viện markdown. Câu trả lời hiển thị dạng văn bản thuần với xuống dòng giữ nguyên bằng CSS `white-space: pre-wrap`.

## TDD

Test được cho một trang tĩnh là test tài sản, không phải test DOM. Nói thẳng giới hạn: **không có test trình duyệt** trong P1 (thêm Playwright là thêm dependency, trái DEC-1), nên hành vi tương tác được nghiệm thu bằng tay ở mục Success.

**Tests-before (RED)** — thêm vào `tests/test_ui.py`:

1. `test_chat_page_has_required_hooks` — `GET /ui/` chứa các id mà `app.js` bám vào: `chat-form`, `question-input`, `messages`, `sources-panel`, `top-k`, `include-sources`. Test này bắt đúng lỗi hay gặp nhất: đổi tên id trong HTML mà quên đổi trong JS.
2. `test_static_assets_served` — `GET /ui/app.js` và `GET /ui/styles.css` trả 200.
3. `test_app_js_never_uses_innerhtml` — đọc nội dung `app.js` trả về, khẳng định không chứa `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`. **Đây là cách R2 được thi hành bằng máy.** Nói cho đúng mức: nó chặn con đường phổ biến nhất, không phải mọi con đường — `setAttribute("onclick", ...)`, `href="javascript:..."` hay ghép chuỗi vào `style` vẫn lọt qua. Test này là rào cản chứ không phải chứng minh; kỷ luật `textContent` vẫn phải giữ khi viết code.
4. `test_page_states_single_turn` — HTML chứa dòng ghi chú về việc mỗi câu hỏi độc lập. Nhãn này là cam kết với người dùng, nên phải có test giữ, không để ai lặng lẽ xoá.

**Implement** → xanh: viết `index.html`, `styles.css`, `app.js`.

**Regression**: `uv run pytest` (48 + 4 = 52), ruff, black, mypy. Commit khi xanh.

## Success

Đo bằng máy:

- [ ] 4 test mới xanh, tổng 52 test.
- [ ] ruff / black / mypy sạch (JS và CSS không thuộc phạm vi các công cụ này — chấp nhận, P1 không thêm linter cho frontend).

Nghiệm thu bằng tay. Điều kiện: Qdrant đang chạy, `.env` có `OPENAI_API_KEY` thật, và đã index ít nhất một tài liệu. **Bước này gọi OpenAI thật nên tốn tiền thật** — khác hẳn 52 test ở trên vốn chạy offline bằng `FakeEmbedder`/`FakeLLM` (`tests/conftest.py:17-51`). Dùng `gpt-4o-mini` và vài câu hỏi thì chi phí không đáng kể, nhưng đừng để vòng lặp thử nghiệm chạy vô hạn.

- [ ] Mở `http://localhost:8000/ui`, hỏi một câu có trong `data/documents/sample_faq.txt` → hiện câu trả lời, panel phải liệt kê nguồn kèm `score` và `page`.
- [ ] Bấm `[1]` → panel cuộn tới nguồn 1 và làm nổi nó.
- [ ] Kéo `top_k` lên 10 → số nguồn trả về tăng theo.
- [ ] Tắt `include_sources` → panel rỗng, câu trả lời vẫn có.
- [ ] Hỏi câu không liên quan gì tới tài liệu → hiện đúng `NO_CONTEXT_ANSWER` (`llm_generator/prompts.py:8`), panel rỗng, trang không vỡ.
- [ ] Tắt Qdrant rồi hỏi → hiện thông báo lỗi rõ ràng trong luồng chat, không treo spinner vĩnh viễn. (Lưu ý R1: nếu Qdrant chết **trước khi** app khởi động thì cả trang không tải được — đó là hành vi đã biết, không phải bug của phase này.)
- [ ] Index một file `.txt` có chứa `<img src=x onerror=alert(1)>` rồi hỏi câu chạm vào nó → chuỗi đó hiện ra dạng chữ trong `snippet`, không có hộp thoại nào bật lên.

## Risks

- **Trôi id giữa HTML và JS**: test số 1 chặn.
- **`[n]` trỏ ra ngoài mảng nguồn**: đã nêu ở mục Hợp đồng — phải xử lý, không được để `sources[n-1]` trả `undefined` rồi ném lỗi.
- **Cám dỗ thêm markdown**: câu trả lời của LLM thường có `**đậm**` và danh sách. Trong P1 chấp nhận hiển thị thô. Muốn markdown thì phải tự viết parser an toàn hoặc thêm dependency — cả hai đều nằm ngoài phase này.
- **Màn hình hẹp**: hai cột dưới 900px phải xếp chồng (`@media`), nếu không panel nguồn bóp nát khung chat.
