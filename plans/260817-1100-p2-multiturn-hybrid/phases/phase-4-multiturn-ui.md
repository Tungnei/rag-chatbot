---
phase: 4
title: "Multiturn Ui"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 4 — Multiturn UI

## Overview

Cho trang `/ui` thật sự nhớ: `app.js` giữ mảng lịch sử trong bộ nhớ trang và gửi 3 lượt gần nhất kèm mỗi câu hỏi.

Không có dòng Python nào. Toàn bộ phase là hai file tĩnh và một file test.

Điểm đáng chú ý duy nhất về kỷ luật: `tests/test_ui.py:91` `test_page_states_single_turn` đang khẳng định `id="single-turn-notice"` có trong HTML (`src/rag_chatbot/api/static/index.html:17`). Test đó **sẽ đỏ, và đỏ đúng** — nó đang bảo vệ một lời hứa mà phase này cố ý phá. **Sửa test, không xoá test.**

Phụ thuộc: phase 3 (backend phải nhận `history` trước, nếu không UI gửi lên chỉ nhận 422).

## Files

- **Modify** `src/rag_chatbot/api/static/app.js` — giữ mảng history, gửi 6 phần tử cuối.
- **Modify** `src/rag_chatbot/api/static/index.html` — thay `#single-turn-notice` bằng `#history-notice`.
- **Modify** `tests/test_ui.py` — sửa `test_page_states_single_turn`, thêm test cho `app.js`.

**Không** đụng `styles.css`: chỉ báo mới dùng lại class `notice` và `muted` đã có (`index.html:17`, `app.js:120,139`). Giữ được như vậy thì phase này không tranh chấp file nào với phase khác, và diff dễ đọc.

**Không** đụng `admin/index.html` hay `admin/admin.js` — trang admin không có hội thoại.

## Hợp đồng với API

Payload `POST /query` nay có thêm một trường (`validate.py` sau phase 3):

```
{question, top_k, include_sources, history: [{role, content}, ...]}
```

Ràng buộc UI phải tự tôn trọng trước khi gửi:

| Trường | Ràng buộc | Nguồn |
|---|---|---|
| `history[].role` | đúng `"user"` hoặc `"assistant"` | `Literal` trong `Turn`, phase 3 |
| `history[].content` | 1–4.000 ký tự, **không rỗng** | `Field(min_length=1, max_length=4000)`, phase 3 |
| `history` | ≤ 50 phần tử; server tự cắt còn 6 | phase 3 |

UI gửi `history.slice(-6)` — cắt ở client cho đúng ý định, và server vẫn cắt lần nữa vì server không được tin client.

## Hành vi bắt buộc

**Chỉ ghi vào history khi có câu trả lời thật.** Đường xử lý lỗi hiện tại có hai nhánh sớm: `!response.ok` (`app.js:212-216`) và `catch` (`app.js:219-224`). Cả hai **không** được đẩy gì vào history. Đẩy một câu hỏi thất bại vào lịch sử là bơm nhiễu vào mọi lượt sau, và người dùng không có cách nào gỡ ra ngoài việc tải lại trang.

`NO_CONTEXT_ANSWER` **thì có** ghi vào history: nó là một câu trả lời thật của hệ thống, và lượt sau cần biết là lượt trước đã trượt.

**Thứ tự ghi:** đẩy turn `user` và turn `assistant` **sau khi** `renderAnswer` chạy xong, theo cặp. Không đẩy `user` ngay lúc submit (`app.js:238`) — làm thế thì một câu hỏi lỗi để lại một turn `user` mồ côi, và lượt sau gửi lên một history kết thúc bằng `user`, tức là đúng cái R10 mà phase 3 phải dọn.

**Chỉ báo phải nói đúng sự thật.** Nhãn cũ nói *"bot không nhớ câu hỏi trước đó"* (`index.html:17-20`) — sau phase này là nói dối. Nhãn mới phải nói đủ ba điều, vì cả ba đều là điều người dùng sẽ đoán sai:

1. Bot nhớ **3 lượt gần nhất**, không phải toàn bộ.
2. Lịch sử **chỉ nằm trong trang này** và mất khi tải lại — server không lưu gì (DEC-2).
3. Số lượt đang được gửi kèm, cập nhật theo thời gian thực.

Điểm 3 biến nhãn tĩnh thành một chỉ báo sống, và nó rẻ: một `textContent` cập nhật trong hàm đã đẩy history.

**Tham số vẫn lưu, lịch sử vẫn không lưu.** `STORAGE_KEY` chỉ giữ `topK` và `includeSources` (`app.js:43-55`). Đừng thêm history vào `localStorage`: nó biến một mảng bộ nhớ thành trạng thái bền vững mà không ai yêu cầu, và mọi turn `assistant` cũ trở thành đầu vào lâu dài cho R5.

**Ràng buộc XSS từ P1 không được nới một milimét.** `test_no_static_asset_injects_markup` (`tests/test_ui.py:69-88`) quét mọi `.js`/`.html` trong `STATIC_DIR` với danh sách cấm ở `tests/test_ui.py:36-48`. Render history bằng `textContent` như `addMessage` đang làm (`app.js:61-68`). Test này phải tiếp tục xanh — và lưu ý nó cấm cả chuỗi trong **comment**, đúng như artifact P3 của plan trước đã ghi lại (*"lần chạy đầu FAIL vì comment trong app.js có chữ innerHTML"*).

## TDD

Giới hạn nói trước, đúng như P1 đã nói: **không có test trình duyệt** (thêm Playwright là thêm dependency, trái DEC-1). Test ở đây là test tài sản — quét chuỗi trong file trả về. Nó chặn con đường phổ biến nhất, không chứng minh hành vi. Hành vi nghiệm thu bằng tay ở mục Success.

**Tests-before (RED)** — `tests/test_ui.py`:

1. **Sửa** `test_page_states_single_turn` → `test_page_states_multi_turn_limit` (`tests/test_ui.py:91-96`). Khẳng định mới:
   - `'id="single-turn-notice"' not in html` — **bắt buộc phải có dòng này.** Nếu chỉ thêm khẳng định về nhãn mới mà không khẳng định nhãn cũ đã biến mất, để lại cả hai vẫn xanh, và trang sẽ mâu thuẫn với chính nó.
   - `'id="history-notice"' in html`
   - `"3 lượt"` in html (chỉ báo giới hạn)
   - `"tải lại"` in html (nói rõ lịch sử mất khi reload)

   *Đỏ vì:* `index.html:17` vẫn có `id="single-turn-notice"` và chưa có `#history-notice`. **Đây là đỏ vì nghiệp vụ** — trang đang hứa một điều mà phase này đổi. Giữ nguyên comment giải thích ở đầu test (`tests/test_ui.py:92-93`), cập nhật nội dung: nhãn vẫn là một phần hợp đồng với người dùng, chỉ có nội dung hợp đồng đổi.

2. `test_app_js_sends_history` — đọc `client.get("/ui/app.js").text`, khẳng định chứa `"history"` và `"slice(-6)"`.
   *Đỏ vì:* `app.js:203-207` hiện chỉ gửi 3 trường.
   **Ghi giới hạn vào docstring:** đây là quét chuỗi, nó chứng minh hai chuỗi có mặt chứ không chứng minh payload đúng. Đừng để ai đọc tên test rồi tin nhiều hơn thế.

3. `test_app_js_does_not_persist_history` — khẳng định `app.js` không có `localStorage` trong cùng câu lệnh với `history`. Cụ thể và kiểm được: khẳng định chuỗi `STORAGE_KEY` chỉ xuất hiện đúng số lần như hiện tại (3 lần: khai báo `app.js:11`, `getItem` `:30`, `setItem` `:45`). Test này giữ ranh giới "lịch sử không bền vững" ở mục Hành vi.
   *Đỏ vì:* không đỏ ngay — nó xanh từ đầu và là dây bảo hiểm. Ghi rõ như vậy trong verification, đừng đếm nó vào vòng đỏ.

4. `test_chat_page_has_required_hooks` (`tests/test_ui.py:51-61`) — **thêm** `history-notice` vào danh sách id. Test cũ vẫn giữ nguyên các id đang có.
   *Đỏ vì:* id chưa tồn tại.

**Implement** → xanh: sửa `index.html` trước (nhãn), rồi `app.js` (mảng history + gửi + cập nhật chỉ báo).

**Regression gate:**

```
uv run pytest -q                 → ≈94 passed, không giảm
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

`ruff`/`black`/`mypy` không đọc JS và CSS — chấp nhận, đây là hiện trạng từ P1 và phase này không thêm linter frontend (trái DEC-1).

## Success

**Đo bằng máy:**

- [ ] `test_page_states_single_turn` đã được **sửa thành** `test_page_states_multi_turn_limit` và xanh; **không có test nào bị xoá** — kiểm bằng `git diff --stat tests/test_ui.py` cho thấy số dòng test không giảm.
- [ ] `test_no_static_asset_injects_markup` vẫn xanh, và `len(assets) >= 4` vẫn đúng (`tests/test_ui.py:83`).
- [ ] 3 test mới xanh, tổng không giảm.
- [ ] Bốn cổng sạch.
- [ ] `grep -c "single-turn-notice" src/rag_chatbot/api/static/index.html` → `0`.

**Nghiệm thu bằng tay** (cần Qdrant + `OPENAI_API_KEY` thật + tài liệu đã nạp — tốn tiền thật):

- [ ] Hỏi "Hệ thống dùng cơ sở dữ liệu nào?" → trả lời đúng. Hỏi tiếp **"Nó chạy ở cổng nào?"** → câu trả lời hiểu "nó" là cái vừa nói tới. Đây là toàn bộ tính năng của plan phần A, thu về một lần bấm.
- [ ] Chỉ báo hiển thị đúng số lượt và tăng dần theo hội thoại, dừng ở 3.
- [ ] Mở DevTools → Network → xem payload `POST /query`: `history` có mặt, ≤6 phần tử, role xen kẽ, kết thúc bằng `assistant`.
- [ ] Tải lại trang → hội thoại trống, chỉ báo về 0, câu hỏi tiếp theo gửi `history: []`.
- [ ] Tắt Qdrant → hỏi → hiện lỗi, và **history không tăng**. Bật lại, hỏi tiếp → history vẫn liền mạch từ trước lúc lỗi.
- [ ] Hỏi một câu không liên quan → `NO_CONTEXT_ANSWER`; câu tiếp theo vẫn gửi kèm lượt đó trong history.
- [ ] Nạp một tài liệu chứa `<img src=x onerror=alert(1)>`, hỏi chạm vào nó, rồi hỏi tiếp một lượt nữa → chuỗi đó nằm trong history và vẫn hiển thị **dạng chữ** ở cả hai lượt, không hộp thoại nào bật lên.

## Risks

- **Xoá test thay vì sửa test.** Rủi ro thật nhất của phase này, vì xoá là cách nhanh nhất để hết đỏ. Cách chặn: Success có một dòng kiểm số dòng test không giảm, và verification phải ghi tên test cũ + tên test mới cạnh nhau.
- **Chuỗi cấm lọt vào comment `app.js`.** Đã xảy ra đúng một lần trong plan P1 (`verification-P3.json`, check `xss-guard`: *"lần chạy đầu FAIL vì comment trong app.js có chữ innerHTML. Sửa comment, không nới test."*). Khi viết comment về history rất dễ nhắc tới các API bị cấm. Sửa comment, đừng nới test.
- **Turn `user` mồ côi khi request lỗi.** Đã xử ở mục Hành vi (đẩy theo cặp, sau khi có câu trả lời). Nếu bỏ qua, phase 3 sẽ âm thầm cắt nó đi ở bước chuẩn hoá R10 — hệ thống vẫn chạy, nhưng người dùng thấy lượt hỏi lỗi biến mất khỏi ngữ cảnh mà không hiểu vì sao. Sửa ở đúng chỗ là ở đây.
- **`slice(-6)` trên mảng cặp có thể cắt giữa cặp.** Nếu history luôn được đẩy theo cặp `user`+`assistant` thì độ dài luôn chẵn và `slice(-6)` luôn bắt đầu bằng `user` — bất biến này do quy tắc "đẩy theo cặp" bảo đảm. Nếu ai đó sau này đẩy lẻ, bất biến gãy. Phase 3 có bước chuẩn hoá đỡ được (R10), nên đây là phòng thủ hai lớp chứ không phải một.
- **Người dùng tưởng bot nhớ toàn bộ hội thoại.** Khung chat trông giống ChatGPT nên kỳ vọng đi theo. Chỉ báo số lượt là thứ duy nhất chống lại kỳ vọng đó, nên nó phải **thấy được**, không phải một dòng chữ xám 11px.
</content>
