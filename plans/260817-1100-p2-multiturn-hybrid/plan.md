---
id: 260817-1100-p2-multiturn-hybrid
title: "P2 — Hội thoại nhiều lượt, rồi hybrid retrieval có rerank"
status: completed
mode: hard
tdd: true
branch: feat/ui-chat-static
created: 2026-08-17
author: user:v.tungnt200@vinsmartfuture.tech
decisions: [DEC-1, DEC-2, DEC-3, DEC-4, DEC-5, DEC-7]
phases:
  - phases/phase-1-p1-acceptance.md
  - phases/phase-2-eval-foundation.md
  - phases/phase-3-multiturn-core.md
  - phases/phase-4-multiturn-ui.md
  - phases/phase-5-dec2-evidence.md
  - phases/phase-6-collection-migration.md
  - phases/phase-7-bm25-fusion.md
  - phases/phase-8-cross-encoder-rerank.md
  - phases/phase-9-metadata-adjust.md
  - phases/phase-10-eval-final-docs.md
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Plan: P2 — Hội thoại nhiều lượt, rồi hybrid retrieval có rerank

## Tổng quan

Hai phần độc lập, cố ý xếp **nối tiếp** chứ không đan xen.

**Phần A (phase 1–5) — hội thoại nhiều lượt.** Thiết kế đã chốt ở DEC-2, không có gì tranh luận lại. Client gửi `history`, server vẫn stateless, chỉ câu hỏi hiện tại được embed. Rủi ro thấp: không đổi schema Qdrant, không thêm dependency runtime. Hôm nay `history` xuất hiện **0 lần** trong `validate.py` / `orchestrator.py` / `prompts.py` [OBSERVED: `grep -rn history` trên ba file trả về 0 dòng], nên đây là code mới hoàn toàn chứ không phải sửa cái đang có.

**Phần B (phase 6–10) — thay tầng retrieval** bằng kiến trúc người dùng đã chỉ định:

```
Query → [dense top30 | BM25 top30] → RRF fusion top30
      → cross-encoder top10 → metadata adjustment → top5 → LLM
```

Rủi ro cao: đổi schema collection (buộc re-ingest toàn bộ — `ensure_collection` dựng `VectorParams` **không tên** ở `src/rag_chatbot_tung/retrieval/vector_search.py:52`), mở rộng `VectorStore` Protocol (`src/rag_chatbot_tung/adaptor/protocols.py:41-43`), và kéo `torch` vào một repo tới giờ vẫn cố ý nhẹ.

Phần A **không** phụ thuộc phần B. Nếu phải dừng giữa chừng, **dừng sau phase 5**: lúc đó multi-turn đã chạy, đã được đo, tài liệu đã đồng bộ, và chưa tiêu một đồng nào cho hạ tầng nặng.

Nguyên tắc xuyên suốt phần B: **mỗi tầng mới ship với công tắc mặc định TẮT.** `retriever.hybrid`, `rerank.provider=noop`, `metadata_adjust.enabled` đều mặc định giữ nguyên hành vi cũ. Ba lý do, cả ba đều nghiệp vụ chứ không phải trang trí: (1) rollback một tầng là lật một dòng config chứ không phải `git revert` một phase đã có phase khác chồng lên; (2) phase 10 lập được bảng đóng góp từng tầng bằng cách bật dần, chứ không phải checkout lại từng commit cũ; (3) merge được phase 7 vào nhánh chính mà không đổi hành vi production trong lúc phase 8 còn dang dở.

## Quyết định đã khoá

Không re-litigate. Nguồn: [docs/decisions.md](../../docs/decisions.md) và chỉ thị của người dùng cho plan này.

| ID | Nội dung ràng buộc plan này |
|---|---|
| DEC-2 | `history` nằm trong `QueryRequest`, **chỉ đưa vào phần LLM**. Vector truy vấn vẫn là câu hỏi hiện tại. Giữ tối đa **3 lượt hỏi-đáp gần nhất**. Server stateless, client giữ lịch sử — không Redis, không session store. |
| DEC-2 | **Query-rewriting bị CHẶN** cho tới khi `scripts/run_eval.py` chứng minh câu hỏi có đại từ thật sự làm tụt hit-rate. Phase 5 tồn tại chính là để lấy đúng bằng chứng đó. Không phase nào trong plan này được thêm một lượt LLM phụ để viết lại truy vấn. |
| DEC-3 | Thứ tự thi công: P1 → P2 multi-turn → P3 hardening → mới mở internet. Plan này vẫn **localhost**: không đụng CORS, không đụng auth, không đổi port binding, không thêm endpoint công khai nào. |
| DEC-5 | Embeddings ở lại OpenAI và tách vĩnh viễn khỏi LLM provider. Không phase nào được đổi `embeddings.model` — đổi là phá số chiều vector đã ghi vào Qdrant. |
| DEC-7 | Khả năng của hạ tầng phải **ĐO**, không suy ra. Áp dụng cứng ở phase 6–10: mọi con số image size / latency / hit-rate trong plan này là ô trống chờ đo, không phải lời hứa. |
| DEC-1 | UI vẫn là trang tĩnh vanilla JS, không build step, không thêm dependency frontend. Phase 4 sửa `app.js`/`index.html` trong khuôn khổ đó. |
| DEC-4 | Đường đi 5 tầng khi đổi `VectorStore` Protocol đã có tiền lệ: `validate.py` → `adaptor/protocols.py` → `retrieval/vector_search.py` → `orchestrator.py` → tests. Phase 7 đi lại đúng đường đó. |
| Người dùng chốt | Phạm vi gồm **cả** phần A (multi-turn) **và** phần B (hybrid retrieval). Reranker là **cross-encoder chạy local**, không phải API. |

### Deviation phải ghi DEC mới — không tự lật DEC-3

Phần B (phase 6–10) **không nằm trong thứ tự đã chốt ở DEC-3**: nó không phải "P3 hardening", nó là một hạng mục mới chen vào giữa P2 và P3.

Plan này **không tự ý lật DEC-3**. Ràng buộc cứng: **phase 6 không được viết dòng code nào trước khi một DEC mới được ghi vào `docs/decisions.md`** qua `decision_register.py --append-alloc`, nội dung tối thiểu: hybrid retrieval được chèn vào giữa P2 và P3 hardening, lý do, và cái gì bị đẩy lùi. Đây là success criterion đầu tiên của phase 6, kiểm được bằng `grep` chứ không phải bằng lời hứa.

Số hiệu DEC do script cấp phát, plan không tự đánh số. Trong các phase file, DEC của phase 5 gọi là `DEC-<phase5>` và của phase 6 là `DEC-<phase6>`.

## Đã đo trước khi viết plan

Không có dòng nào dưới đây là suy diễn. Tất cả chạy thật trên `.venv` hiện tại.

| Câu hỏi | Kết quả | Hệ quả lên plan |
|---|---|---|
| `pytest -q` hiện tại? | **78 passed** [OBSERVED: `uv run pytest -q` → `78 passed, 2 warnings in 1.10s`] | Mốc so sánh của mọi phase. Trùng khớp `docs/code-standards.md:17`. |
| `QdrantClient(":memory:")` chạy được sparse vector + RRF fusion không? | **Có.** `query_points(prefetch=[...], query=FusionQuery(RRF))` trả kết quả đúng | Test **vẫn chạy offline** — giữ được tính chất cốt lõi ở `docs/ARCHITECTURE.md:85-87` và `docs/code-standards.md:67-73`. |
| `models.Modifier.IDF` có hoạt động server-side ở local mode không? | **Có.** Từ hiếm 0.9808 vs từ phổ biến 0.1335 | **BM25 KHÔNG cần thêm dependency nào.** Tokenizer thuần Python gửi term-frequency, Qdrant tự tính IDF. Không kéo `fastembed`/`onnxruntime`. |
| `torch` / `sentence_transformers` đã có chưa? | **Chưa** [OBSERVED: `importlib.util.find_spec` → `ABSENT` cho `torch`, `sentence_transformers`, `fastembed`, `onnxruntime`; `qdrant-client 1.19.0`] | Cross-encoder là dependency nặng **duy nhất** của cả plan. |
| Collection cũ (unnamed) phân biệt được với collection hybrid không? | **Có.** Legacy: `config.params.vectors` là `VectorParams`, `config.params.sparse_vectors` là `None`. Hybrid: `vectors` là `dict` khoá `['dense']`, `sparse_vectors` là dict khoá `['bm25']` | R3 kiểm được bằng máy, không cần đoán. Chi tiết ở phase 6. |
| Query một collection có vector đặt tên mà quên `using=` thì sao? | **Raise** `ValueError: Dense vector  is not found in the collection` | Migration hỏng sẽ nổ ra ồn ào chứ không im lặng trả kết quả sai. |
| Upsert vector không tên vào collection có tên? | **Raise** `ValueError: Unnamed vectors are not allowed when a collection has named vectors...` | Ingest cũ không thể âm thầm ghi rác vào schema mới. |
| Điểm RRF nằm ở thang nào? | **0.3333 – 0.8333** trong probe 4 điểm | R4: `score_threshold: 0.3` (hiệu chỉnh cho cosine) là so hai đại lượng khác đơn vị. |
| `hash()` của Python trên `str` có ổn định qua tiến trình không? | **KHÔNG.** `hash('máy học')` cho 3 giá trị khác nhau trong 3 tiến trình; `zlib.crc32` cho `176058915` cả 3 lần | R2 được xác nhận bằng đo, không phải bằng kiến thức nền. |

Baseline dữ liệu: `data/eval/qa.jsonl` = **6 case / đúng 2 nguồn** (`sample_faq.txt`, `sample_guide.md`) [OBSERVED: file 6 dòng]. `data/documents/` chỉ có **2 tài liệu** được track (`git ls-files data/`). `top_k: 3`, `score_threshold: 0.3`, `context_token_budget: 6000` (`configs/default.yaml:22,26-27`).

## Ràng buộc (constraint-scan)

Đã quét, kết quả:

- Repo này **không có** `ownership.yaml`, `stage-policy.yaml`, hay `schemas/` — không phải repo clone harness [OBSERVED: `find -maxdepth 3` trả về rỗng cho cả ba; `/harness` không tồn tại]. Không có zone/policy nào chi phối vị trí file.
- Ràng buộc thật đến từ chính repo:

| Ràng buộc | Anchor |
|---|---|
| Bốn cổng phải sạch: `ruff check src tests`, `black --check src tests`, `mypy src`, `pytest -q` | `docs/code-standards.md:10-15` |
| `ruff`/`black` line-length 100, target py311, lint select `E,F,I,UP,B` | `pyproject.toml:50-59` |
| `from __future__ import annotations` ở đầu mọi module có logic trong `src/` và `tests/` | `docs/code-standards.md:22-23` |
| Type hint kiểu mới (`list[str]`, `X \| None`), không `typing.List`/`Optional` | `docs/code-standards.md:24` |
| DI qua `typing.Protocol`, **không** qua kế thừa. `orchestrator.py` không bao giờ import class provider cụ thể | `docs/code-standards.md:26-31`, `docs/system-architecture.md:14-25` |
| `providers.py` là nơi DUY NHẤT ánh xạ giá trị `provider` sang class | `docs/system-architecture.md:22-25`, `src/rag_chatbot_tung/providers.py:15-41` |
| `@dataclass(slots=True)` cho value object nội bộ; `pydantic.BaseModel` cho mọi thứ đi qua biên | `docs/code-standards.md:33-42` |
| Comment giải thích **LÝ DO**, không diễn giải lại code | `docs/code-standards.md:50-51` |
| Toàn bộ test chạy offline qua `FakeEmbedder`/`FakeLLM`/`QdrantClient(":memory:")` | `docs/code-standards.md:67-73`, `tests/conftest.py:17-53,80-84` |
| Fixture `away_from_dotenv` (autouse) không được xoá hay vô hiệu hoá | `docs/code-standards.md:75-78`, `tests/conftest.py:56-67` |
| TDD: đỏ trước, và phải đỏ **đúng lý do nghiệp vụ**, không phải đỏ vì lỗi import | `docs/code-standards.md:80-87` |
| Thứ tự ưu tiên config: constructor > env > `.env` > YAML > default. Không thêm cơ chế đọc config thứ hai | `docs/system-architecture.md:60-64`, `src/rag_chatbot_tung/configs.py:102-118` |
| Biến env tuỳ chọn để **comment out**, không để `KEY=` rỗng | `docs/code-standards.md:105-108` |
| Chưa có chuẩn structured logging và chưa có coverage threshold — **đừng bịa** | `docs/code-standards.md:110-115` |
| `RAGOrchestrator` là **singleton toàn tiến trình** (`app.state.orchestrator` dựng một lần trong lifespan) — cấm thêm state khả biến vào nó | `src/rag_chatbot_tung/api/app.py:36`, `src/rag_chatbot_tung/api/dependencies.py:10-11` |

Ràng buộc cuối cùng là ràng buộc dễ vi phạm nhất trong plan này: R9 đòi "đếm số lần `NO_CONTEXT_ANSWER` bật ra", và cách tự nhiên nhất — thêm một biến đếm vào `RAGOrchestrator` — sẽ rò rỉ qua mọi request và mọi test dùng chung fixture. Đếm phải đi qua log, không qua state.

## Phases

| # | Theme | Phụ thuộc | Cỡ | Cần hạ tầng thật? | Test sau phase (ước tính) |
|---|---|---|---|---|---|
| 1 | **P1 Acceptance** — đóng nợ `manual-acceptance: SKIP`. Không viết code | — | S | **Có** — Qdrant + `OPENAI_API_KEY` + tài liệu đã nạp | 78 (không đổi) |
| 2 | **Eval Foundation** — mở rộng bộ eval, đo theo từng tầng | 1 | L | **Có** cho lần chạy đo; test đơn vị thì offline | ≈84 |
| 3 | **Multiturn Core** — `Turn`/`history`, prompt, ngân sách token | 2 | L | Không | ≈93 |
| 4 | **Multiturn UI** — `app.js` giữ lịch sử, gỡ nhãn một-lượt | 3 | M | Không | ≈94 |
| 5 | **DEC-2 Evidence** — đo tác động của đại từ, ghi DEC, đồng bộ docs. Không viết code sản phẩm | 4 | M | **Có** | ≈94 (không đổi) |
| 6 | **Collection Migration** — schema named + sparse, script migrate | 5 | L | **Có** cho lần migrate thật | ≈98 |
| 7 | **BM25 + RRF Fusion** — tokenizer, prefetch, fusion | 6 | XL | Không cho test; **Có** cho lần đo | ≈108 |
| 8 | **Cross-encoder Rerank** — Protocol `Reranker`, Noop mặc định | 7 | L | **Có** cho đo image size + latency | ≈114 |
| 9 | **Metadata Adjust** — 3 quy tắc tất định, top10 → top5 | 8 | M | Không cho test; **Có** cho đo ngân sách token | ≈121 |
| 10 | **Eval Final + Docs** — bảng đóng góp từng tầng, cập nhật tài liệu | 9 | M | **Có** | ≈121 (không đổi) |

Cột "test sau phase" là **ước tính**, không phải cam kết. Cổng cứng là *không giảm so với phase trước* và *không test cũ nào phải sửa để xanh trừ chỗ đã nêu tên*. Con số thật do cook ghi vào `artifacts/verification-P<n>.json`.

Chuỗi này **gần như tuần tự hoàn toàn** — mỗi phase dựa trên phase trước. `plan-graph.yaml` không có antichain nào rộng hơn một node, và điều đó là thật chứ không phải thận trọng thừa: xem phần comment trong file đó để biết cạnh nào là logic, cạnh nào chỉ để nối tiếp tránh đụng file.

### Điểm dừng an toàn: sau phase 5

**Dừng sau phase 5 là một kết cục hợp lệ, không phải bỏ dở.** Ở thời điểm đó:

- Multi-turn chạy đầy đủ từ UI xuống LLM, có test giữ.
- Bộ eval đã đủ lớn để nói được điều gì đó.
- Có số liệu trả lời câu hỏi "câu hỏi có đại từ tụt hit-rate bao nhiêu", và một DEC ghi lại kết luận.
- `docs/system-architecture.md:48-52` (đang nói multi-turn "đã quyết, CHƯA triển khai") và sơ đồ ở `docs/ARCHITECTURE.md:3-26` đã được phase 5 cập nhật cho đúng thực tế.
- Chưa có một dependency nặng nào, chưa đụng schema Qdrant, chưa có gì phải migrate.

Phần B bắt đầu bằng một phase phá vỡ tương thích. Không có lý do gì phải bước vào đó trước khi nhìn thấy số liệu của phase 5.

## Out of scope

Cố ý **không** làm đợt này:

- **Query-rewriting / condensing câu hỏi bằng một lượt LLM phụ.** Bị DEC-2 chặn cho tới khi phase 5 đưa ra bằng chứng. Ngay cả khi phase 5 mở cổng, việc triển khai vẫn là plan khác.
- **Session store phía server** (Redis, cookie, `conversation_id`). DEC-2 chốt stateless.
- **Thư viện tách từ tiếng Việt** (`underthesea`, `pyvi`, ...). Tokenizer của phase 7 là unigram thuần Python; hạn chế được ghi lại, không được vá bằng dependency mới.
- **Cohere / Jina / bất kỳ reranker qua API nào.** Người dùng chốt cross-encoder local. `Reranker` là Protocol nên đường lùi sang API tồn tại, nhưng plan này không đi.
- **Đổi `embeddings.model`** hay bất cứ thứ gì đụng số chiều vector (DEC-5).
- **Auth, rate limit, siết CORS, trần chi tiêu** — thuộc P3, DEC-3.
- **Streaming câu trả lời.** Đường sinh vẫn đồng bộ (`orchestrator.py:69-76`).
- **Recency boost trong metadata adjustment.** Payload hiện có `source`, `source_type`, `title`, `page`, `index` (`src/rag_chatbot_tung/validate.py:17-25`) — **không có timestamp**, nên không làm được. Thêm timestamp vào payload = một lần re-ingest nữa, không đáng ở đợt này.
- **Structured logging / coverage threshold.** `docs/code-standards.md:110-115` nói rõ chưa có chuẩn; plan này không tiện tay đặt ra.
- **Facet API cho `list_sources`.** Điều kiện đổi đã ghi ở DEC-4 (`points_count` > ~50000 **và** đã đo độ trễ) — chưa tới.
- **Test trình duyệt (Playwright)** cho phase 4. Thêm dependency frontend là trái DEC-1; hành vi tương tác nghiệm thu bằng tay như P1 đã làm.

## Acceptance (toàn plan)

- [ ] Mỗi phase red→green TDD, bằng chứng đỏ/xanh ghi vào `artifacts/verification-P<n>.json` trường `tdd-red`, và **đỏ đúng lý do nghiệp vụ** (`docs/code-standards.md:80-87`).
- [ ] `uv run pytest -q` xanh sau mỗi phase, **≥78 và không giảm**. Không test cũ nào bị xoá; test duy nhất được phép sửa nội dung khẳng định là `tests/test_ui.py:91` `test_page_states_single_turn` ở phase 4, và phải sửa thành khẳng định ngược lại chứ không xoá.
- [ ] `uv run ruff check src tests`, `uv run black --check src tests`, `uv run mypy src` sạch sau mỗi phase.
- [ ] Toàn bộ suite vẫn chạy **hoàn toàn offline**: không test nào tải model, không test nào gọi mạng. Kể cả sau phase 8, `import rag_chatbot_tung.rerank` không được kéo `torch` vào.
- [ ] Nghiệm thu thủ công P1 (phase 1) đã chạy thật và ghi kết quả — hai check `manual-acceptance: SKIP` ở `plans/260812-1221-p1-chat-ui/artifacts/verification-P3.json` và `verification-P5.json` được đóng lại.
- [ ] `data/eval/qa.jsonl` ≥ 40 case trên ≥ 6 nguồn; `data/eval/qa_multiturn.jsonl` tồn tại với cặp câu hỏi có-đại-từ / tự-đủ-nghĩa.
- [ ] `POST /query` nhận `history` và trả lời có tính tới lịch sử; client cũ **không gửi** `history` vẫn chạy y hệt (backwards compatible, có test).
- [ ] Lịch sử hội thoại **không bao giờ** trở thành nguồn trích dẫn: `SYSTEM_PROMPT` nói rõ, và có test khẳng định nội dung history không lọt vào khối passage đánh số.
- [ ] Ngân sách token: history bị cắt **trước**, context lấy phần dư, và có test chứng minh 3 lượt dài không bóp nghẹt đoạn văn truy xuất.
- [ ] Một DEC mới được ghi ở phase 5 (kết luận về gate DEC-2) và một DEC nữa ở phase 6 (chấp nhận deviation khỏi thứ tự DEC-3), cả hai qua `decision_register.py`.
- [ ] Sau migration (phase 6): `points_count` sau ≥ trước, và danh sách `source` sau khớp danh sách trước — đối chiếu bằng file snapshot mà script ghi ra **trước khi** xoá collection.
- [ ] Chỉ số sparse tất định qua tiến trình: có test chạy trong subprocess với `PYTHONHASHSEED` khác nhau, **cộng** một test đối chứng chứng minh bộ test này bắt được nếu ai đó dùng `hash()`.
- [ ] `score_threshold` không còn được áp lên điểm đã fusion — có test khẳng định nó nằm trong `Prefetch` dense.
- [ ] Phase 10 có bảng 4 dòng (baseline / +fusion / +rerank / +metadata) với **số đo thật** cho hit-rate, MRR, p95 latency và image size. Ô trống không được điền bằng ước lượng.
- [ ] `docs/ARCHITECTURE.md`, `docs/system-architecture.md`, `README.md`, `docs/QUICK_REFERENCE.md`, `docs/PROJECT_STRUCTURE.md` không còn câu nào mô tả sai hệ thống sau khi plan kết thúc.

## Rollback

Mỗi phase một commit riêng trên nhánh `feat/ui-chat-static`. Hoàn tác thường lệ: `git revert <sha>` hoặc `git revert <range>`, rồi chạy lại bốn cổng.

Nhưng "revert được" không đồng nghĩa "vô hại". Chia ba nhóm theo mức độ:

**Nhóm 1 — revert sạch (phase 1, 3, 4, 5).** Không tạo state ngoài git. Phase 3/4 chỉ thêm field tuỳ chọn và sửa file tĩnh. Revert xong hệ thống về đúng trạng thái trước đó.

**Nhóm 2 — revert sạch nhưng mất dữ liệu người viết (phase 2).** `data/eval/qa.jsonl` mở rộng và các tài liệu mới trong `data/documents/` là công sức tay. Revert phase 2 là vứt chúng đi. Nếu cần lùi, lùi code trong `metrics.py`/`run_eval.py` và **giữ lại** dữ liệu.

**Nhóm 3 — KHÔNG revert được bằng git (phase 6).** Đây là chỗ duy nhất trong plan mà `git revert` không đủ.

- Phase 6 xoá và dựng lại collection Qdrant. Revert code không mọc lại collection cũ.
- Đường lùi thật: `git revert` code phase 6 **rồi chạy lại `scripts/ingest.py`** để dựng lại collection schema cũ từ `data/documents/`.
- Điều kiện để đường lùi đó hoạt động: mọi nguồn đang có trong index phải có mặt trên đĩa. Script migrate **bắt buộc** kiểm tra điều này trước khi xoá và dừng nếu thiếu (xem phase 6, R8).

**Nhóm 4 — KHÔNG lùi được bằng công tắc (phase 9).** `retriever.top_k` đổi mặc định 3→5, và `index.html` đổi mặc định slider theo. Cả hai **không** nằm sau công tắc nào.

Nói cách khác: tắt cả ba công tắc (`RETRIEVER__HYBRID=false`, `RERANK__PROVIDER=noop`, `METADATA_ADJUST__ENABLED=false`) **không** đưa đường truy vấn về đúng hành vi dense-only như câu ở đầu mục này ngụ ý — nó vẫn để lại +67% token context mỗi truy vấn, vĩnh viễn, và đó là tiền thật. Muốn lùi hẳn phải sửa `configs/default.yaml` và `src/rag_chatbot_tung/api/static/index.html` bằng tay.
- Tài liệu nạp qua `POST /ingest` với `url` (`orchestrator.py:87-89`) **không** có mặt trên đĩa. Đây là lỗ hổng thật của đường lùi, và cách xử là script ghi ra snapshot danh sách nguồn trước khi xoá để người dùng nạp lại bằng tay.

**Phase 7, 8, 9 — rollback không cần git.** Đây là lý do công tắc mặc định TẮT tồn tại: `RETRIEVER__HYBRID=false`, `RERANK__PROVIDER=noop`, `METADATA_ADJUST__ENABLED=false` đưa đường truy vấn về đúng hành vi dense-only, không cần build lại, không cần đụng collection. `git revert` chỉ cần khi muốn gỡ hẳn code.

Riêng phase 8: revert code không thu nhỏ image đã build. Phải build lại. Nếu dùng Docker target riêng cho reranker (xem phase 8) thì image mặc định chưa bao giờ phình, nên không có gì phải thu nhỏ.

## Red-team — 8 finding đã áp vào plan

Vòng red-team (2026-08-18) tìm 22 finding. Ba BLOCKER và năm HIGH đã được sửa thẳng vào các phase file; 10 MEDIUM/LOW đã đăng ký `BL-001`..`BL-010` trong `BACKLOG.md`.

| ID | Vấn đề | Phase đã sửa |
|---|---|---|
| **B1** | `run_eval.py` không đi qua `answer()` — `metrics.py:50-53` gọi thẳng `vector_store.search`. Rerank và metadata sẽ **không bao giờ được đo**, bảng phase 10 in cùng con số ba lần, và DEC kết luận sẽ ghi "cross-encoder vô dụng" dựa trên phép đo chưa từng gọi nó. | 8, 9 — tách `RAGOrchestrator.retrieve()`, `metrics.py` gọi nó; cổng "`rerank.json` giống `fusion.json` = chưa đo, không phải vô dụng" |
| **B2** | Bật hybrid **gỡ bỏ cả hai lớp chống bịa** mà `ARCHITECTURE.md:94-95` tuyên bố. Đo được: cùng truy vấn lạc đề, dense-only 0 hit → `NO_CONTEXT_ANSWER`; hybrid 4 hit rác vào LLM. Hit-rate mù trước lỗi này. | 7 — sàn liên quan sau fusion; 2 — nhóm case `expected_source: null` + đếm `false_positive` |
| **B3** | Migrate đứt giữa chừng → chạy lại → snapshot **bị ghi đè** bằng trạng thái sau sự cố → bước đối chiếu báo **PASS** trong khi đã mất 5 nguồn. Lưới an toàn tự phá chính nó. | 6 — snapshot có timestamp, cấm ghi đè, marker in-progress, chế độ resume, và **diễn thật** kịch bản đứt |
| **H1** | `metadata=false` + `rerank=cross_encoder` → LLM nhận **10** chunk thay vì 5; dòng 3 bảng phase 10 chạy khác biến so với 3 dòng kia. | 9 — tắt phần điều chỉnh, **không** tắt phần cắt |
| **H2** | Chuẩn hoá role không xử lý `[user, user, assistant]` — vẫn lọt hai `user` liền nhau tới Anthropic, đúng thứ R10 sinh ra để chặn. | 3 — gộp dãy liên tiếp cùng role trước; test 7 phủ 3 input |
| **H3** | `top_k` 3→5 làm baseline bảng cuối không so được với phase 2; và mục Rollback **sai** — tắt cả 3 công tắc vẫn để lại +67% token vĩnh viễn. | 10 — ép `--top-k` cho cả 4 dòng, ghi `k=`; plan.md — thêm Nhóm 4 |
| **H4** | `uv sync --extra rerank && pytest` sẽ **tải 90MB từ HuggingFace trong lúc chạy test** — vi phạm `code-standards.md:67-73`. | 8 — test tự dựng điều kiện qua `monkeypatch`; fixture autouse `HF_HUB_OFFLINE=1` |
| **H5** | Reranker inject qua constructor không nhận fan-out → "lối lùi sang Cohere" không chạy như hứa, và test vẫn xanh. | 8 — `_reranks` tính cả reranker được inject; `top_n = max(top_n, top_k)` |

Mảng red-team kiểm mà **sạch**, ghi lại để khỏi kiểm lại: `crc32` vào u32 index (probe OK), sparse vector rỗng không nổ, env nesting hai từ hoạt động, không có cạnh nào thiếu trong `plan-graph.yaml`, và 12 anchor `file:line` kiểm mẫu đều chính xác.

## Risks

| # | Rủi ro | Bằng chứng | Phase | Xử lý |
|---|---|---|---|---|
| **R1** | **Eval 6 case / 2 nguồn không chứng minh được gì.** Đoán bừa giữa 2 nguồn đã cho hit-rate 50%. Mọi kết luận của phase 5 và phần B đều dựa lên con số này; nếu nó vô nghĩa thì 2GB image được ship mà không ai biết có tốt hơn không. | `data/eval/qa.jsonl` = 6 dòng, `expected_source` chỉ có 2 giá trị [OBSERVED] | 2 | **Phase 2 là tiên quyết CỨNG.** Không phase nào sau nó được coi là xong khi eval chưa mở rộng. ≥40 case / ≥6 nguồn. Kèm ràng buộc ít ai để ý: cần **≥6 tài liệu thật** trong `data/documents/` — hiện chỉ có 2 (xem R11). |
| **R2** | **`hash()` của Python trên `str` bị ngẫu nhiên hoá theo tiến trình.** Dùng nó sinh chỉ số sparse thì index ghi hôm nay đọc hôm sau ra rác — và lỗi này **không lộ ra trong một lần chạy test duy nhất**, vì trong cùng một tiến trình `hash()` hoàn toàn ổn định. Đây là dạng lỗi tệ nhất: test xanh, production hỏng âm thầm. | [OBSERVED: `hash('máy học')` cho 3 giá trị khác nhau trong 3 tiến trình; `zlib.crc32` cho `176058915` cả 3 lần] | 7 | Bắt buộc `zlib.crc32`. Test **đa tiến trình** (`subprocess` + `PYTHONHASHSEED` khác nhau) **cộng một test đối chứng** khẳng định `hash()` thật sự thay đổi qua chính bộ subprocess đó — không có test đối chứng thì test chính có thể xanh giả. |
| **R3** | **`ensure_collection` return sớm nếu collection đã tồn tại** → im lặng bỏ qua việc nâng schema, rồi mọi truy vấn hybrid hỏng theo cách khó chẩn đoán. | `src/rag_chatbot_tung/retrieval/vector_search.py:48-49` | 6 | Kiểm tra schema **tường minh** khi collection đã tồn tại, và raise lỗi có nêu tên lệnh migrate. Kiểm được bằng máy: legacy có `config.params.vectors` là `VectorParams` và `sparse_vectors` là `None`; hybrid là hai dict [OBSERVED]. |
| **R4** | **`score_threshold: 0.3` mất ý nghĩa sau RRF fusion.** Điểm RRF không phải cosine — áp ngưỡng hiệu chỉnh cho cosine lên điểm fusion là so hai đại lượng khác đơn vị. | `configs/default.yaml:27`; điểm RRF quan sát được nằm trong 0.3333–0.8333 [OBSERVED] | 7 | Chuyển ngưỡng **vào trong `Prefetch` dense** (lọc trước khi fusion). Ngưỡng ngoài của truy vấn fusion để `None`. Có test khẳng định vị trí này. |
| **R5** | **History poisoning.** `history` do client gửi, nên ai cũng bịa được một turn `assistant` chứa thông tin sai rồi hỏi tiếp dựa trên nó. `SYSTEM_PROMPT` hiện chỉ nói "chỉ dùng các đoạn văn được đánh số" — không nói gì về lịch sử. | `src/rag_chatbot_tung/llm_generator/prompts.py:10-17` | 3 | Bổ sung luật vào `SYSTEM_PROMPT`: lịch sử là **ngữ cảnh để hiểu câu hỏi**, không phải nguồn sự thật, không được trích dẫn. Test riêng. **Giới hạn phải nói thẳng**: test offline chỉ chứng minh được luật có trong prompt và nội dung history không lọt vào khối passage đánh số — nó **không** chứng minh model tuân luật. Phần đó thuộc nghiệm thu tay ở phase 5. |
| **R6** | **History chia chung `context_token_budget: 6000` với đoạn văn truy xuất.** Để history ăn tự do thì 3 lượt dài bóp nghẹt context, và câu trả lời tệ đi **dù retrieval hoàn toàn đúng** — triệu chứng trông y hệt lỗi retrieval, dẫn người debug đi sai hướng. | `configs/default.yaml:22`, `src/rag_chatbot_tung/configs.py:53`, `prompts.py:29-32` | 3 | Trần cứng riêng cho history (`llm.history_token_budget`, mặc định 1500). Cắt history **TRƯỚC**, context lấy phần dư. Test: 3 lượt cực dài vẫn để lại ≥1 passage. |
| **R7** | **Docker image phình + latency tăng do cross-encoder.** Repo giữ được sự gọn nhẹ một cách có chủ ý (DEC-1 loại Gradio/React cũng vì lý do đó). | `torch`/`sentence_transformers` chưa có [OBSERVED]. Con số "~200MB → ~2GB" trong bản nháp **chưa từng được đo trong repo này** — `[ASSUMED]` | 8 | **Đo cả hai, ghi vào verification.** Giảm nhẹ bằng kiến trúc: `sentence-transformers` là **optional dependency**, và Dockerfile có target riêng — image mặc định (`RERANK__PROVIDER=noop`) không phình một byte. Lối lùi: `Reranker` là Protocol nên đổi sang API chỉ là một class mới. |
| **R8** | **Migration làm mất index đang có.** Không có đường migrate tại chỗ từ vector không tên sang có tên; phải re-ingest toàn bộ. Nguồn nạp qua URL không có mặt trên đĩa để nạp lại. | `vector_search.py:52` (unnamed); `orchestrator.py:87-89` (nạp qua url) | 6 | Script migrate: (1) ghi snapshot `list_sources()` ra file **trước khi** xoá; (2) đối chiếu từng nguồn với `data/documents/` + `data/uploads/`, **abort mặc định nếu thiếu** (`--allow-missing` để ép); (3) `--dry-run`; (4) so `points_count` trước/sau và exit ≠ 0 nếu tụt. |
| **R9** | **Multi-turn làm `NO_CONTEXT_ANSWER` bật ra thường xuyên hơn.** Câu như "giải thích rõ hơn đi" sẽ không retrieve được gì, và người dùng nhận câu từ chối — một bước lùi trải nghiệm do chính multi-turn tạo ra. | `src/rag_chatbot_tung/orchestrator.py:61-67` | 3, 5 | **Giữ nguyên hành vi** (DEC-2 chốt chỉ embed câu hỏi hiện tại), nhưng **đếm tần suất** và đưa vào bằng chứng phase 5. Đếm qua log, **không** qua state trên `RAGOrchestrator` — nó là singleton toàn tiến trình (`api/app.py:36`), thêm biến đếm là rò rỉ qua mọi request và mọi test. |
| **R10** | **Anthropic có thể từ chối messages không xen kẽ role.** `AnthropicLLM._split_system` nhấc system ra rồi đẩy phần còn lại nguyên xi làm `messages`. Nếu `history` client gửi kết thúc bằng một turn `user`, request sẽ có hai message `user` liền nhau. OpenAI chấp nhận; Anthropic thì `[PRIOR]` là đòi xen kẽ. | `src/rag_chatbot_tung/llm_generator/anthropic_llm.py:63-74`, `openai_llm.py:22-27` | 3 | Không đi xác minh bằng API thật (tốn tiền, và câu trả lời có thể đổi theo phiên bản). Chuẩn hoá phòng thủ trong `build_rag_messages`: bỏ các turn `assistant` dẫn đầu và turn `user` ở cuối, để history luôn kết thúc bằng `assistant`. Rẻ, tất định, test offline được, và đúng bất kể API có khó tính hay không. |
| **R11** | **Không thể có ≥6 nguồn eval khi chỉ có 2 tài liệu.** `data/documents/` chỉ track `sample_faq.txt` và `sample_guide.md`. Mở rộng eval lên ≥6 nguồn đòi viết thêm tài liệu thật, và nguồn `.pdf` thì không sinh ra được bằng code. | [OBSERVED: `git ls-files data/` → 2 tài liệu] | 2 | Phase 2 tạo ≥4 tài liệu `.md`/`.txt` mới. **Nguồn `.pdf` là hạng mục người dùng cung cấp**, không phải việc cook làm được — nếu người dùng không thả file PDF vào, phase 2 vẫn đạt với ≥6 nguồn text/markdown và ghi rõ khoảng trống `.pdf` chưa được phủ. |
| **R12** | **Ba phase (2, 5, 10) có cổng cần hạ tầng thật.** `scripts/run_eval.py` dựng `RAGOrchestrator(settings)` với provider thật (`orchestrator.py:41-43` → `providers.py:28-41`), nên chạy eval cần Qdrant sống **và** `OPENAI_API_KEY` thật, và **tốn tiền thật**. Không có bước nào trong `pytest` thay thế được. | `scripts/run_eval.py:20-23`, `src/rag_chatbot_tung/providers.py:34-41` | 2, 5, 10 | Nói thẳng trong từng phase: phần đo được bằng máy và phần cần người chạy là hai danh sách tách biệt. Verification ghi `PASS` cho phần máy và `SKIP` kèm lý do cho phần chưa chạy — đúng khuôn mẫu P1 đã dùng, chứ không gộp làm một verdict giả. |
</content>
</invoke>
