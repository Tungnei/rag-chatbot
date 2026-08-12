# Brainstorm: giao diện tương tác với chatbot

Ngày: 2026-08-12
Trạng thái: đã hội tụ — chốt hướng, chốt thứ tự thi công
Quyết định đã ghi: DEC-1, DEC-2, DEC-3 trong [docs/decisions.md](../../docs/decisions.md)

## 1. Hiện trạng backend (scout)

| Sự kiện | Bằng chứng |
|---|---|
| `POST /query` stateless, một lượt, không có trường lịch sử | `src/rag_chatbot_tung/api/routes.py:35-37`, `src/rag_chatbot_tung/validate.py:56-68` |
| Không streaming — handler đồng bộ, trả nguyên câu trả lời | `src/rag_chatbot_tung/orchestrator.py:68-83` |
| Không xác thực, CORS mở toàn bộ | `src/rag_chatbot_tung/api/app.py:42-47`, `configs/default.yaml:30-35` |
| Chưa có hạ tầng frontend nào | `pyproject.toml:10-24`, không có `StaticFiles`, không có `web/` |
| Dockerfile copy thẳng `src` vào image | `Dockerfile:24` |
| Mỗi câu trả lời kèm `sources[]` có `snippet`, `score`, `page` | `src/rag_chatbot_tung/orchestrator.py:118-128` |
| LLM được yêu cầu trích dẫn dạng `[1] [2]`, khớp thứ tự `sources[]` | `src/rag_chatbot_tung/llm_generator/prompts.py:15` |
| Đã có thước đo retrieval: hit-rate và MRR | `scripts/run_eval.py`, `data/eval/qa.jsonl` |

## 2. So sánh hướng triển khai UI

| Tiêu chí | A. Trang tĩnh | B. Gradio nhúng | C. SPA React/Next |
|---|---|---|---|
| Dependency mới | không | nặng, ràng buộc phiên bản `fastapi`/`pydantic` | toolchain Node |
| Code tự viết | khoảng 250 dòng | khoảng 35 dòng | trên 1000 dòng |
| Thay đổi deploy | không | không | thêm 1 service compose |
| Kiểm soát render trích dẫn | toàn phần | hạn chế trong Markdown | toàn phần |
| Đường nâng cấp lên streaming | dễ, `EventSource` | phụ thuộc framework | dễ |

Chọn A. Ít dòng code hơn không đồng nghĩa đơn giản hơn: B đổi 200 dòng mình kiểm soát được lấy một framework mình không kiểm soát, mà cái giá phải trả nằm đúng chỗ đắt nhất là ràng buộc phiên bản với `uv.lock` đang khoá. Bù lại, giá trị lớn nhất của một UI RAG là trích dẫn bấm được — thứ mà B làm kém nhất.

## 3. Ba tiểu dự án

Yêu cầu ban đầu chứa ba mối quan tâm độc lập, nên được tách thay vì gộp.

### P1 — UI tĩnh: chat, nguồn, bảng tham số, trang admin

Phạm vi: thuần frontend, không đụng backend.

- `src/rag_chatbot_tung/api/static/index.html`, mount `StaticFiles(directory=..., html=True)` tại `/ui`.
- Trang quản trị tách đường dẫn riêng `/ui/admin` — upload, xem `/collections`, xoá nguồn.
- Bảng tham số bám ràng buộc schema: `top_k` 1-20, toggle `include_sources`, hiện `latency_ms` và `tokens_used`.
- Trích dẫn `[n]` trong câu trả lời bấm được, bung snippet tương ứng trong `sources[n-1]`.
- Kiểm chứng cần làm một lần: `uv build` rồi kiểm tra wheel có kèm thư mục `static/` không. Nếu `uv_build` bỏ qua file không phải Python thì chuyển thư mục ra gốc repo và `COPY` như `configs`.
- Bổ sung test vào `tests/test_api.py`: `/ui` trả 200 và trả HTML.

### P2 — Hội thoại nhiều lượt

Phạm vi: sửa backend, không phải việc của UI.

Ba phương án đã cân nhắc:

1. Client tự nối lịch sử vào `question` — 0 dòng backend, nhưng vector truy vấn bị pha loãng và đụng trần 2000 ký tự. Từ chối.
2. Thêm `history` vào `QueryRequest`, chỉ đưa vào phần LLM, vẫn embed đúng câu hỏi hiện tại. Retrieval không suy giảm, server vẫn stateless. **Chọn phương án này.**
3. Phương án 2 cộng một lượt gọi LLM phụ viết lại câu hỏi thành câu độc lập trước khi embed. Xử lý đúng câu có đại từ, nhưng cộng khoảng 500ms và một lần gọi API cho mọi câu hỏi.

Điều kiện nâng lên phương án 3: thêm case hỏi nối tiếp có đại từ vào `data/eval/qa.jsonl`, chạy `scripts/run_eval.py`, và chỉ đổi khi số liệu hit-rate cho thấy vấn đề là thật. Không trả 500ms mỗi câu cho một giả định chưa được đo.

Ràng buộc ngân sách: `context_token_budget` là 6000 và đang chia cho các đoạn văn truy xuất. Lịch sử hội thoại giành chỗ với chúng, nên chốt cứng giữ 3 lượt gần nhất.

### P3 — Cổng bảo vệ trước khi công khai

Điều kiện bắt buộc để P1 và P2 được mở ra internet.

- Xác thực đặt ở reverse proxy phía trước, không tự viết trong FastAPI. Lý do kỹ thuật: SPA chạy trong trình duyệt không giấu được API key, nên cơ chế key-trong-header vô nghĩa với UI công khai; phải là session cookie do lớp phía trước cấp. Ứng viên: Caddy basic auth, oauth2-proxy, Cloudflare Access.
- Tách quyền: `/ingest`, `/ingest/upload`, `DELETE /documents` và `/ui/admin` nằm sau cổng chặt hơn cổng của `/query`.
- Siết CORS: bỏ `["*"]`. UI cùng origin với API nên danh sách gần như có thể để rỗng.
- Rate limit theo IP ở proxy, cộng hard limit ngân sách trong dashboard OpenAI.

## 4. Rủi ro đã nhận diện

| Rủi ro | Hệ quả | Xử lý |
|---|---|---|
| `DELETE /documents` không auth mà mở ra internet | Người ngoài xoá sạch index | P3 trước khi mở mạng; admin tách sau cổng riêng |
| `/ingest` nhận `url` và server tự fetch | SSRF — người ngoài mượn server gọi vào mạng nội bộ | Cùng cổng admin ở P3 |
| `/query` không auth | Người ngoài đốt token OpenAI | Rate limit cộng trần chi tiêu ở P3 |
| Khung chat gợi ý có trí nhớ trong khi backend không có | Người dùng hỏi nối tiếp và nhận câu trả lời sai ngữ cảnh | Trước P2: gắn nhãn rõ là hỏi đáp từng câu độc lập |
| Không streaming, chờ 2-5 giây không phản hồi | Cảm giác treo | Skeleton hoặc spinner bắt buộc trong P1 |
| Lịch sử hội thoại ăn vào `context_token_budget` | Đoạn văn truy xuất bị cắt bớt, câu trả lời kém đi | Giới hạn 3 lượt, đo lại bằng `run_eval.py` |

## 5. Thứ tự thi công đã chốt

P1 (chạy localhost) → P2 → P3 → mới mở ra internet.

Phần quản lý tài liệu vẫn được xây trong P1 nhưng chỉ chạy localhost; đến P3 mới gắn cổng rồi mở. Lý do chọn thứ tự này thay vì làm P3 trước: P1 cho giá trị sử dụng ngay mà không phát sinh rủi ro nào khi còn ở localhost, còn P3 là công việc hạ tầng — làm trước sẽ chặn nhiều ngày trước khi nhìn thấy con chatbot chạy lần đầu.

## 6. Bước tiếp theo

`/hs:plan` cho P1. P2 và P3 lập kế hoạch riêng, không gộp chung.
