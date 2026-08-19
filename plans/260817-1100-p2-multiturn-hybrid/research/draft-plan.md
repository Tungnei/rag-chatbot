---
id: 260817-1100-p2-multiturn-hybrid
title: "P2 — Hội thoại nhiều lượt, rồi hybrid retrieval có rerank"
description: "Phần A: multi-turn theo đúng thiết kế DEC-2. Phần B: dense+BM25 → RRF fusion → cross-encoder → metadata adjustment → top-5."
status: draft
priority: P2
effort: "9 phases, 2 phần tách rời"
tdd: true
branch: feat/ui-chat-static
tags: [multi-turn, retrieval, hybrid, bm25, rerank, rag]
created: 2026-08-17
decisions: [DEC-2, DEC-3, DEC-5, DEC-7]
---

# Plan: P2 — Multi-turn, rồi hybrid retrieval

## Tóm tắt

Hai phần độc lập, cố ý xếp nối tiếp chứ không đan xen:

**Phần A (phase 0–4)** — hội thoại nhiều lượt. Thiết kế đã chốt sẵn ở DEC-2, không có gì để tranh luận lại. Rủi ro thấp, đụng 4 file, không đổi schema Qdrant.

**Phần B (phase 5–9)** — thay toàn bộ tầng retrieval bằng kiến trúc bạn chỉ định:

```
Query → [dense top30 | BM25 top30] → RRF fusion top30
      → cross-encoder top10 → metadata adjustment → top5 → LLM
```

Rủi ro cao: đổi schema collection (buộc re-ingest toàn bộ), đổi `VectorStore` Protocol, và kéo `torch` vào một repo tới giờ vẫn nhẹ.

Phần A không phụ thuộc phần B. **Nếu phải dừng giữa chừng, dừng sau phase 4** — lúc đó bạn đã có multi-turn chạy được và có số liệu để quyết phần B có đáng làm không.

## Quyết định đã khoá — không mở lại

| ID | Ràng buộc lên plan này |
|---|---|
| DEC-2 | `history` nằm trong `QueryRequest`, **chỉ đưa vào phần LLM**. Vector truy vấn vẫn là câu hỏi hiện tại. Giữ tối đa 3 lượt gần nhất. Server stateless, client giữ lịch sử. |
| DEC-2 | **Query-rewriting bị chặn** cho tới khi `run_eval.py` chứng minh câu hỏi có đại từ làm tụt hit-rate. Phase 4 tồn tại chính để lấy bằng chứng đó. |
| DEC-3 | Thứ tự: P1 → P2 multi-turn → P3 hardening → mở mạng. Vẫn localhost, không đụng CORS/auth. |
| DEC-5 | Embeddings ở lại OpenAI, tách khỏi LLM provider. Đổi model embedding sẽ phá collection. |
| DEC-7 | Khả năng của hạ tầng phải **đo**, không suy ra. Áp dụng ở phase 5–6. |

### Deviation cần bạn duyệt

Phần B **không nằm trong thứ tự DEC-3** (nó không phải P3 hardening). Đây là hạng mục mới chen vào giữa. Khi bắt đầu phase 5, cần ghi một DEC mới cho việc này — plan không tự ý lật DEC-3.

## Đã đo trước khi viết plan

Ba probe chạy thật trên `.venv` hiện tại (`qdrant-client 1.19.0`), vì DEC-4 từng vướng đúng chuyện "local mode có hỗ trợ không":

| Câu hỏi | Kết quả | Hệ quả |
|---|---|---|
| `QdrantClient(':memory:')` có chạy sparse vector + RRF fusion không? | **Có.** `query_points(prefetch=[...], query=FusionQuery(RRF))` trả kết quả đúng | Test vẫn chạy offline — giữ được tính chất cốt lõi ở `ARCHITECTURE.md:86` |
| `Modifier.IDF` có hoạt động server-side không? | **Có.** Từ hiếm 0.9808 vs từ phổ biến 0.1335 | **BM25 không cần dependency nào.** Chỉ cần tokenizer thuần Python gửi term-frequency; Qdrant tự tính IDF. Không phải kéo `fastembed`/onnxruntime |
| `torch` / `sentence-transformers` đã có chưa? | **Chưa** | Cross-encoder là dependency nặng duy nhất của phần B |

## Baseline

- `pytest -q` → **78 passed** (mốc để so sánh mọi phase sau)
- `data/eval/qa.jsonl` → **6 case, đúng 2 nguồn**
- Collection dùng **vector không tên** (`VectorParams` trần, `vector_search.py:52`)
- `top_k: 3`, `score_threshold: 0.3`, `context_token_budget: 6000`

---

# PHẦN A — Multi-turn

## Phase 0 — Đóng nợ P1

P1 còn treo `manual-acceptance: SKIP` ở verification P3 và P5 (lý do cũ: docker daemon thiếu root CA). Container smoke ở P6 **đã chạy thật**, nên chướng ngại đó không còn.

Nghiệm thu thủ công trang `/ui` và `/ui/admin` với Qdrant thật + ít nhất 1 tài liệu đã nạp: hỏi được, trích dẫn `[1]` bấm được, upload/xoá được. Ghi kết quả vào `verification-P0.json`.

Không viết code. Nếu phát hiện lỗi, chúng thuộc P1 và phải sửa trước khi sang phase 1.

## Phase 1 — Mở rộng nền đo lường

**Đây là phase quan trọng nhất của cả plan, và là phase dễ bị bỏ qua nhất.**

Eval hiện tại có 6 case trên 2 nguồn. Đoán bừa giữa 2 nguồn đã cho hit-rate 50%. Không thể dùng con số này để chứng minh bất kỳ điều gì — kể cả gate mà DEC-2 đặt ra, kể cả việc phần B có cải thiện gì không.

**Files**
- Modify `data/eval/qa.jsonl` — lên **≥40 case, ≥6 nguồn**, đủ cả `.md`/`.txt`/`.pdf`
- Create `data/eval/qa_multiturn.jsonl` — case có đại từ/tham chiếu ngữ cảnh, schema thêm `history`
- Modify `src/rag_chatbot_tung/evaluate/metrics.py` — đo theo **từng tầng**, không chỉ tổng
- Modify `scripts/run_eval.py` — in bảng so sánh, thêm `--baseline` để diff

`EvalReport` cần tách được hit-rate của: dense-only → sau fusion → sau rerank → sau metadata. Không có phân tách này thì phần B tốn 2GB image mà không biết tầng nào đóng góp.

Thêm luôn: log `score` thật của các chunk trả về, để kiểm chứng nhận định "`score_threshold: 0.3` gần như không lọc gì".

**Gate:** eval chạy được, in ra baseline number. Ghi lại con số này — mọi phase sau so với nó.

## Phase 2 — Multi-turn: schema, prompt, budget

**Files**
- Modify `src/rag_chatbot_tung/validate.py` — thêm `Turn`, thêm `history` vào `QueryRequest`
- Modify `src/rag_chatbot_tung/llm_generator/prompts.py` — dựng messages có lịch sử
- Modify `src/rag_chatbot_tung/orchestrator.py` — truyền `request.history` xuống
- Modify `tests/test_prompts.py`, `tests/test_orchestrator.py`, `tests/test_api.py`

**Schema**

```python
class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    include_sources: bool = True
    history: list[Turn] = Field(default_factory=list, max_length=6)
```

`max_length=6` = 3 lượt hỏi-đáp, đúng DEC-2. Server **cắt bớt** phần thừa chứ không từ chối request — client cũ gửi dư không nên bị 422.

**Ba cái bẫy phải xử lý, không được bỏ qua**

1. **Ngân sách token.** `context_token_budget: 6000` giờ phải chia cho cả history lẫn context. Nếu để history ăn tự do, 3 lượt dài sẽ bóp nghẹt đoạn văn truy xuất và câu trả lời tệ đi *dù retrieval vẫn đúng*. Cắt history **trước**, phần còn lại mới giao cho `format_context`. Đề xuất: trần cứng cho history (ví dụ 1500 token), context lấy phần dư.

2. **History poisoning.** `history` do client gửi, nghĩa là ai cũng bịa được một turn `assistant` chứa thông tin sai, rồi hỏi tiếp dựa trên nó. `SYSTEM_PROMPT` hiện nói "chỉ dùng các đoạn văn được đánh số" — phải bổ sung rõ rằng lịch sử hội thoại là **ngữ cảnh chỉ dùng để hiểu câu hỏi**, không phải nguồn sự thật và không được trích dẫn. Cần một test riêng: bơm history bịa đặt, khẳng định câu trả lời không lấy nó làm căn cứ.

3. **Short-circuit `NO_CONTEXT_ANSWER`.** `orchestrator.py:61` trả lời cụt khi không có chunk nào. Ở chế độ multi-turn, câu như "giải thích rõ hơn đi" sẽ không retrieve được gì và người dùng nhận câu từ chối — một bước lùi rõ rệt về trải nghiệm mà chính multi-turn tạo ra. Phase này **giữ nguyên hành vi** (DEC-2 chốt "chỉ embed câu hỏi hiện tại"), nhưng phải ghi lại số lần xảy ra: đó là dữ liệu đầu vào cho phase 4.

## Phase 3 — Multi-turn: UI

**Files**
- Modify `src/rag_chatbot_tung/api/static/app.js` — giữ mảng history, gửi 3 lượt gần nhất
- Modify `src/rag_chatbot_tung/api/static/index.html` — gỡ `#single-turn-notice`
- Modify `tests/test_ui.py` — sửa `test_page_states_single_turn` (`tests/test_ui.py:91`)

Lưu ý: `test_page_states_single_turn` khẳng định `id="single-turn-notice"` có trong HTML. Test này sẽ đỏ, và đỏ **đúng** — nó đang bảo vệ một lời hứa mà phase này cố tình phá. Sửa test thành khẳng định ngược lại (notice đã biến mất, và có chỉ báo số lượt đang giữ). Không xoá test.

Giữ nguyên ràng buộc XSS từ P1: `test_app_js_never_uses_innerhtml` phải tiếp tục xanh — render history bằng `textContent`.

## Phase 4 — Lấy bằng chứng cho gate của DEC-2

Chạy `run_eval.py` trên `qa_multiturn.jsonl` và trả lời đúng một câu hỏi:

> Câu hỏi có đại từ/tham chiếu ngữ cảnh có thật sự làm tụt hit-rate so với câu hỏi tự đủ nghĩa không, và tụt bao nhiêu?

- **Nếu tụt đáng kể** → gate của DEC-2 mở. Query-rewriting trở thành hạng mục hợp lệ, ghi DEC mới, và nó **nên được cân nhắc trước phần B** vì rẻ hơn nhiều.
- **Nếu không tụt** → DEC-2 giữ nguyên, query-rewriting đóng lại, đi thẳng phần B.

Phase này không viết code sản phẩm. Đầu ra là số liệu + một DEC.

**Đây là điểm dừng an toàn của plan.** Multi-turn đã chạy, đã đo, chưa tiêu tốn gì cho hạ tầng nặng.

---

# PHẦN B — Hybrid retrieval

> Cảnh báo chi phí, nói một lần rồi thôi: cross-encoder local kéo `torch` + `sentence-transformers`, đẩy Docker image từ ~200MB lên khoảng **2GB**, và thêm latency CPU đáng kể mỗi query. Repo này tới giờ giữ được sự gọn nhẹ một cách có chủ ý (DEC-1 loại Gradio/React cũng vì lý do đó). Bạn đã chọn hướng này nên plan triển khai đúng như vậy — nhưng phase 7 có sẵn một lối lùi sang Cohere API nếu con số image size là không chấp nhận được khi nhìn thấy thật.

## Phase 5 — Migration schema collection

**Đây là phase phá vỡ tương thích. Làm sai là mất index.**

Collection hiện dùng **vector không tên**. Hybrid cần **vector có tên**: `dense` + sparse `bm25`. Đây không phải thay đổi thêm-vào — nó là schema khác hẳn.

Hai chướng ngại cụ thể:

1. `ensure_collection` **return sớm nếu collection đã tồn tại** (`vector_search.py:48-49`). Nó sẽ không bao giờ nâng cấp schema, và cũng không báo lỗi — im lặng chạy tiếp với schema cũ, rồi mọi truy vấn hybrid sẽ hỏng theo cách khó hiểu. Phải thêm bước **phát hiện schema cũ** và báo rõ ràng.

2. Phải **re-ingest toàn bộ tài liệu**. Không có đường migrate tại chỗ từ vector không tên sang có tên.

**Files**
- Modify `src/rag_chatbot_tung/retrieval/vector_search.py` — `ensure_collection` dựng named + sparse; thêm kiểm tra schema
- Create `scripts/migrate_collection.py` — dựng lại collection và nạp lại từ `data/documents/`
- Modify `docs/SETUP.md` — quy trình migrate

**Gate:** migrate xong, `points_count` khớp trước/sau, và `/query` cũ (dense-only) vẫn trả kết quả tương đương. Chưa bật hybrid ở phase này.

## Phase 6 — BM25 + RRF fusion

**Files**
- Create `src/rag_chatbot_tung/retrieval/sparse.py` — tokenizer + mã hoá term-frequency
- Modify `src/rag_chatbot_tung/adaptor/protocols.py` — đổi chữ ký `search`
- Modify `src/rag_chatbot_tung/retrieval/vector_search.py` — prefetch + `FusionQuery(RRF)`
- Modify `src/rag_chatbot_tung/retrieval/document_retrieval.py` — sinh sparse vector lúc ingest
- Modify `src/rag_chatbot_tung/orchestrator.py`, `configs/default.yaml`
- Create `tests/test_sparse.py`; modify `tests/test_vector_search.py`, `tests/conftest.py`

**Bẫy nghiêm trọng nhất: hàm băm term phải tất định.**

`hash()` của Python trên `str` **được ngẫu nhiên hoá theo tiến trình** (PYTHONHASHSEED). Dùng nó để sinh chỉ số sparse thì mỗi lần khởi động lại process, cùng một từ ra chỉ số khác — index đã ghi trở thành rác, và lỗi này **không lộ ra trong một lần chạy test duy nhất**. Bắt buộc dùng `zlib.crc32` hoặc `hashlib`. Cần một test khẳng định chỉ số ổn định qua nhiều tiến trình.

**Bẫy thứ hai: `score_threshold: 0.3` mất hết ý nghĩa sau fusion.**

Điểm RRF không phải cosine — probe cho thấy nó nằm ở thang hoàn toàn khác (0.5–0.83 trong ví dụ 3 điểm). Áp ngưỡng 0.3 lên điểm đã fusion là so sánh hai đại lượng khác đơn vị. Ngưỡng phải chuyển **vào trong từng `Prefetch`** (lọc ở tầng dense trước khi fusion), hoặc bỏ hẳn và để rerank làm nhiệm vụ lọc.

**Tokenizer với tiếng Việt:** tiếng Việt tách âm tiết theo khoảng trắng nên unigram dùng được cho BM25, nhưng "máy học" thành hai token rời. Chấp nhận ở phase này — BM25 chỉ là một nửa của fusion, nửa dense vẫn bắt được ngữ nghĩa. Ghi lại như một giới hạn đã biết, không cố giải quyết bằng thư viện tách từ (thêm dependency nữa).

**Chữ ký `search` đổi** kéo theo 5 tầng đúng như đường DEC-4 đã đi: `protocols.py` → `vector_search.py` → `orchestrator.py` → `conftest.py` → tests.

**Gate:** eval hit-rate sau fusion so với baseline phase 1. Nếu không hơn, dừng lại và xem xét trước khi sang phase 7.

## Phase 7 — Cross-encoder rerank (top30 → top10)

**Files**
- Modify `src/rag_chatbot_tung/adaptor/protocols.py` — thêm `Reranker` Protocol
- Create `src/rag_chatbot_tung/rerank/__init__.py`, `cross_encoder.py`, `noop.py`
- Modify `src/rag_chatbot_tung/providers.py`, `configs.py`, `orchestrator.py`, `Dockerfile`, `pyproject.toml`
- Create `tests/test_rerank.py`

`NoopReranker` là mặc định và là thứ test dùng — bộ test **phải chạy offline không tải model**, giữ đúng tính chất ở `ARCHITECTURE.md:86`.

**Quyết định phải chốt trong phase này: model nằm ở đâu?**

- *Nướng vào image*: image phình thêm ~500MB nữa nhưng container khởi động là chạy được, không phụ thuộc mạng.
- *Tải lúc runtime*: image nhỏ hơn, nhưng lần khởi động đầu cần internet — hỏng hẳn trong môi trường air-gapped, và làm health check thành phụ thuộc mạng.

Khuyến nghị nướng vào image: nó biến một lỗi runtime khó chẩn đoán thành một con số build-time nhìn thấy được.

**Lối lùi:** nếu image size không chấp nhận được, `Reranker` là Protocol nên `CohereReranker` thay vào chỉ là một class mới, không đụng orchestrator — đúng lý do tầng adaptor tồn tại.

**Gate:** đo cả hit-rate **lẫn latency p95**. Rerank cải thiện chất lượng nhưng đánh đổi bằng thời gian; cả hai con số phải nằm trong báo cáo.

## Phase 8 — Metadata adjustment (top10 → top5)

Sơ đồ bạn vẽ có tầng này nhưng chưa định nghĩa nội dung. Payload hiện có: `source`, `source_type`, `title`, `page`, `index` — **không có timestamp**, nên không làm được recency boost.

Đề xuất ba quy tắc tất định, không tốn model, dễ test:

1. **Trần theo nguồn** — tối đa N chunk mỗi `source`. Hiện tại một tài liệu có thể chiếm trọn cả 3 slot; đây là chỗ sửa.
2. **Gộp chunk liền kề** — cùng `source` và `index` liên tiếp thì nối lại, khôi phục ngữ cảnh mà chunking đã cắt (đặc biệt có ích cho PDF bị cắt cứng theo trang).
3. **Boost khi khớp heading** — `title` từ `split_markdown` khớp từ khoá truy vấn thì nâng hạng nhẹ.

Cả ba đều thuần thuật toán, chạy trong micro giây, và test được không cần mạng. Nếu bạn có ý khác cho tầng này thì đây là chỗ nói.

**Gate:** `top_k` cuối = 5. Kiểm tra ngân sách token: 5 chunk × ~1000 ký tự, cộng history, phải nằm gọn trong `context_token_budget`. Với tiếng Việt tỉ lệ token/ký tự xấu hơn tiếng Anh — đo thật, đừng ước lượng.

## Phase 9 — Eval tổng kết + tài liệu

Chạy eval đầy đủ, lập bảng đóng góp từng tầng:

| Cấu hình | Hit-rate | MRR | p95 latency | Image size |
|---|---|---|---|---|
| Baseline (dense top3) | | | | |
| + fusion | | | | |
| + rerank | | | | |
| + metadata | | | | |

Bảng này là thứ trả lời được câu "2GB image có đáng không" bằng số thay vì bằng cảm giác.

Cập nhật `ARCHITECTURE.md` (sơ đồ request flow đã sai kể từ phase 6), `README.md`, `QUICK_REFERENCE.md`, `docs/decisions.md`.

---

## Rủi ro đã nhận diện

| # | Rủi ro | Phase | Xử lý |
|---|---|---|---|
| R1 | Eval 6 case không chứng minh được gì; phần B ship mà không biết có tốt hơn không | 1 | Phase 1 là điều kiện tiên quyết cứng, không được bỏ |
| R2 | Hash term không tất định → index thành rác, test một lần vẫn xanh | 6 | `zlib.crc32`; test đa tiến trình |
| R3 | `ensure_collection` im lặng bỏ qua schema cũ | 5 | Kiểm tra schema tường minh + báo lỗi rõ |
| R4 | `score_threshold` vô nghĩa sau fusion | 6 | Chuyển ngưỡng vào `Prefetch` |
| R5 | History poisoning qua turn `assistant` bịa đặt | 2 | Sửa SYSTEM_PROMPT + test riêng |
| R6 | History ăn hết token budget, câu trả lời tệ đi dù retrieval đúng | 2 | Trần cứng cho history, cắt trước context |
| R7 | Docker image 2GB, latency tăng | 7 | Đo và báo cáo; lối lùi Cohere qua Protocol |
| R8 | Migration làm mất index đang có | 5 | Script migrate riêng, đối chiếu `points_count` |
| R9 | Multi-turn làm `NO_CONTEXT_ANSWER` bật ra thường xuyên hơn | 2, 4 | Giữ hành vi, đếm tần suất, đưa vào bằng chứng phase 4 |

## Cổng chung cho mọi phase

```
pytest -q          → ≥78 pass, không giảm
ruff check src tests
black --check src tests
mypy src
```

TDD: đỏ trước, và phải đỏ **đúng lý do** — không phải đỏ vì lỗi import. Đây là chuẩn mà verification P2–P5 của plan trước đã giữ, giữ tiếp.
