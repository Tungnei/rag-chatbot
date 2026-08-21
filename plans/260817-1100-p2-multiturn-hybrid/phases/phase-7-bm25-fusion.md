---
phase: 7
title: "Bm25 Fusion"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 7 — BM25 + RRF Fusion

## Overview

Bật nửa còn lại của hybrid: mã hoá term-frequency lúc ingest, hai `Prefetch` song song lúc truy vấn, hợp nhất bằng RRF.

```
Query → [dense top30 | BM25 top30] → RRF fusion top30
```

**BM25 không cần thêm một dependency nào.** `models.Modifier.IDF` hoạt động server-side kể cả ở local mode [OBSERVED: từ hiếm 0.9808 vs từ phổ biến 0.1335], nên tokenizer thuần Python chỉ việc gửi tần suất term thô và Qdrant lo phần còn lại. Không `fastembed`, không `onnxruntime`. Đây là kết quả có giá trị nhất trong các probe: nó biến "thêm BM25" từ một quyết định về dependency thành một quyết định về ~40 dòng code.

Phase ship với công tắc **mặc định TẮT** (`retriever.hybrid: false`). Hành vi production không đổi khi merge; bật là một biến môi trường; tắt lại cũng vậy.

Phụ thuộc: phase 6 (schema `bm25` phải tồn tại).

## Files

- **Create** `src/rag_chatbot/retrieval/sparse.py` — tokenizer + mã hoá term-frequency.
- **Modify** `src/rag_chatbot/adaptor/protocols.py` — `SparseVector`, `VectorPoint.sparse`, tham số `query_text` cho `VectorStore.search`.
- **Modify** `src/rag_chatbot/retrieval/vector_search.py` — prefetch + `FusionQuery(RRF)`.
- **Modify** `src/rag_chatbot/retrieval/document_retrieval.py` — sinh sparse vector lúc ingest.
- **Modify** `src/rag_chatbot/retrieval/__init__.py` — export những gì cần.
- **Modify** `src/rag_chatbot/orchestrator.py` — truyền `query_text`.
- **Modify** `src/rag_chatbot/evaluate/metrics.py` — truyền `query_text` (nếu không thì eval đo đường cũ và bảng của phase 10 vô nghĩa).
- **Modify** `src/rag_chatbot/configs.py`, `configs/default.yaml` — `RetrieverSettings` mở rộng.
- **Create** `tests/test_sparse.py`.
- **Modify** `tests/test_vector_search.py`.

## Chữ ký `search` — thêm vào, không phá

Bản nháp nói "đổi chữ ký `search` kéo theo 5 tầng". Đã kiểm lại toàn bộ call site, và có cách rẻ hơn nhiều:

```python
def search(
    self,
    vector: list[float],
    top_k: int,
    score_threshold: float | None = None,
    query_text: str | None = None,
) -> list[RetrievedChunk]: ...
```

Tham số **tuỳ chọn, có default**. `query_text=None` → đường dense-only y hệt hôm nay.

Danh sách đầy đủ 6 call site (không phải "cập nhật tất cả caller" — đây là tất cả, đã liệt kê hết):

| Call site | Phải sửa? |
|---|---|
| `src/rag_chatbot/orchestrator.py:55` | **Có** — truyền `query_text=request.question` |
| `src/rag_chatbot/evaluate/metrics.py:50` | **Có** — truyền `query_text=case.question` |
| `tests/test_vector_search.py:22` | Không — dense-only, và **phải giữ nguyên** làm bằng chứng không hồi quy |
| `tests/test_vector_search.py:30` | Không — cùng lý do |
| `tests/test_vector_search.py:38` | Không — cùng lý do |
| `tests/test_document_retrieval.py:26` | Không — cùng lý do |

Bản nháp liệt kê `tests/conftest.py` trong danh sách file phải sửa. **Đã kiểm và không cần**: `conftest.py` không có fake `VectorStore` nào — fixture `vector_store` dùng chính `QdrantVectorStore` thật với `QdrantClient(":memory:")` (`conftest.py:80-84`). Không có double nào phải cập nhật theo Protocol. Đây là phần thưởng của quyết định ở DEC-4 (dùng lớp thật với client in-memory thay vì viết fake).

`adaptor/protocols.py` thêm:

```python
@dataclass(slots=True)
class SparseVector:
    indices: list[int]
    values: list[float]


@dataclass(slots=True)
class VectorPoint:
    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)
    sparse: SparseVector | None = None
```

`@dataclass(slots=True)` cho value object nội bộ, đúng `docs/code-standards.md:35-36`. **Không import `qdrant_client` vào `adaptor/`** — hiện tại file này không có import hạ tầng nào (`protocols.py:1-13`) và đó là cả điểm của tầng adaptor. Việc dịch `SparseVector` sang `models.SparseVector` nằm trong `vector_search.py`.

## `retrieval/sparse.py`

```python
_TOKEN = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    # Ingested text is NFKC-normalised by clean_text, but the question is not — it goes
    # straight from the request into the query path. For dense vectors that only nudges
    # the embedding; for BM25 an NFC "máy" and an NFD "máy" are two different terms and
    # the query silently misses everything. Normalise here so both sides agree.
    return _TOKEN.findall(unicodedata.normalize("NFKC", text).lower())


def term_index(term: str) -> int:
    # zlib.crc32 and not hash(): Python randomises str hashing per process, so an index
    # written by one process would be unreadable by the next — and a single-process test
    # run can never catch it, because hash() is perfectly stable within one process.
    return zlib.crc32(term.encode("utf-8"))


def encode(text: str) -> SparseVector:
    counts = Counter(tokenize(text))
    ...  # raw term frequency; Qdrant's IDF modifier supplies the rest
```

**Bất đối xứng chuẩn hoá là lỗi thật, không phải phòng thủ thừa.** Đã xác minh: mọi văn bản đi qua ingest được `clean_text` chuẩn hoá NFKC (`utils/text.py:19-23`, gọi ở `document_retrieval.py:89,91,97,145`), nhưng câu hỏi thì không — `orchestrator.py:56` đưa `request.question` thẳng vào `embed_query`. Chuẩn hoá bên trong `tokenize` là cách sửa đúng chỗ: nó phục vụ cả hai chiều (ingest và query đều gọi `encode`) mà không đụng `orchestrator.py`.

**Va chạm chỉ số**: `crc32` cho không gian 2³². Với ~10⁵ term phân biệt, số va chạm kỳ vọng ≈ n²/2^33 ≈ 1. Một va chạm làm hai term dùng chung một chiều — xếp hạng nhiễu nhẹ, **không** hỏng index. Ghi lại như giới hạn đã biết; đừng đổi sang hash 64-bit rồi cắt, vì Qdrant nhận chỉ số u32 và cắt lại đưa về đúng cùng một bài toán.

**Tiếng Việt**: tách âm tiết theo khoảng trắng nên unigram dùng được, nhưng "máy học" thành hai token rời và mất nghĩa ghép. **Chấp nhận ở phase này** — BM25 chỉ là một nửa của fusion, nửa dense vẫn bắt được ngữ nghĩa. Ghi lại như giới hạn đã biết, **không** giải bằng thư viện tách từ (thêm dependency là đánh mất chính cái ưu điểm vừa giành được từ probe IDF).

## Truy vấn hybrid

```python
hits = self._client.query_points(
    collection_name=self.collection,
    prefetch=[
        models.Prefetch(
            query=vector,
            using=_DENSE_VECTOR,
            limit=dense_limit,
            score_threshold=score_threshold,   # R4: ngưỡng nằm Ở ĐÂY
        ),
        models.Prefetch(
            query=models.SparseVector(indices=..., values=...),
            using=_SPARSE_VECTOR,
            limit=sparse_limit,
        ),
    ],
    query=models.FusionQuery(fusion=models.Fusion.RRF),
    limit=top_k,
    # No score_threshold here: see below.
    with_payload=True,
).points
```

**R4 — `score_threshold: 0.3` mất ý nghĩa sau fusion.** Điểm RRF không phải cosine: probe cho ra 0.3333 / 0.5 / 0.8333 trên một tập 4 điểm [OBSERVED], và giá trị phụ thuộc **số lượng danh sách và thứ hạng**, không phụ thuộc độ tương đồng. Áp ngưỡng hiệu chỉnh cho cosine lên điểm fusion là so hai đại lượng khác đơn vị — nó sẽ lọc theo một quy luật mà không ai chủ ý đặt ra, và quy luật đó đổi khi `limit` đổi.

Xử: ngưỡng vào **trong `Prefetch` dense** (lọc trước fusion, ở đúng thang mà nó được hiệu chỉnh). Prefetch sparse **không** đặt ngưỡng — điểm BM25 sau IDF ở một thang khác nữa, và chưa có phép đo nào để đặt ngưỡng cho nó. Đặt bừa còn tệ hơn không đặt. Ngưỡng ngoài của truy vấn fusion để `None`.

### B2 — sàn liên quan sau fusion (BẮT BUỘC, không phải tuỳ chọn)

Chỉ làm hai việc trên là **gỡ bỏ cả hai lớp chống bịa** mà `docs/ARCHITECTURE.md:94-95` và `docs/system-architecture.md:43-45` tuyên bố hệ thống có. Đã đo, không phải suy đoán:

```
dense-only (score_threshold=0.9) -> 0 hits  => orchestrator.py:61-67 trả NO_CONTEXT_ANSWER
hybrid fusion (sparse không sàn) -> 4 hits  scores=[0.5, 0.3333, 0.25, 0.2]
```
[OBSERVED: probe trên `QdrantClient(":memory:")`, 4 tài liệu, truy vấn lạc đề chỉ chia sẻ một stopword]

Cùng một câu hỏi lạc đề: dense-only từ chối trả lời, hybrid nạp 4 đoạn văn **hoàn toàn không liên quan** vào LLM rồi bảo nó trả lời từ đó. Nguyên nhân: BM25 trả kết quả khi câu hỏi chia sẻ **một** token bất kỳ với tài liệu, mà stopword thì chia sẻ với mọi tài liệu. Không tầng nào sau đó đặt lại sàn — `NoopReranker` chỉ cắt, `CrossEncoderReranker` chỉ xếp lại rồi cắt `top_n`; không cái nào **loại bỏ**.

Ba hệ quả dây chuyền nếu để nguyên:
1. Guard mà `ARCHITECTURE.md:95` mô tả không còn được thi hành khi `hybrid=true` — tài liệu thành nói dối.
2. R9 của phase 5 đếm tần suất `NO_CONTEXT_ANSWER` để đánh giá multi-turn; phase 7 đẩy con số đó về ~0 vì một lý do **không liên quan gì** tới multi-turn, làm mọi so sánh R9 xuyên phần A/B thành vô nghĩa.
3. **Hit-rate không bắt được lỗi này** — nó chỉ đo `expected_source` có xuất hiện không, không phạt rác đi kèm. Bảng phase 10 sẽ nói "fusion tốt hơn" đúng lúc chất lượng grounding tụt.

**Xử (đã chốt với người dùng):** sau fusion, giữ lại chunk thoả **ít nhất một** trong hai điều kiện:
- có mặt trong tập kết quả của prefetch **dense đã qua ngưỡng** (chạy prefetch dense một lần, giữ set id), **hoặc**
- điểm sparse vượt một sàn `retriever.sparse_score_floor` đo được từ dữ liệu thật.

Sàn sparse **không được đặt bừa**: phase này phải log phân bố điểm BM25 trên bộ eval của phase 2 rồi chọn số từ phân bố đó, và ghi con số cùng cách đo vào verification. Nếu chưa đo được thì để `None` và **chỉ** dùng điều kiện thứ nhất — vẫn đóng được lỗ hổng, chỉ hy sinh một phần recall của nhánh sparse thuần.

Giữ nguyên hình dạng pipeline người dùng đã chốt: đây là một bước lọc thêm vào giữa fusion và rerank, không phải đổi kiến trúc.

Đã xác minh `score_threshold` **chấp nhận được bên trong `Prefetch`** [OBSERVED: probe chạy đúng với `Prefetch(..., score_threshold=0.3)`].

Nhánh sparse chỉ chạy khi `query_text` khác `None` **và** `settings.retriever.hybrid` bật. Thiếu một trong hai → đường dense-only y hệt phase 6.

## Ingest

`document_retrieval.py:161-168` thêm `sparse=sparse.encode(chunk.text)` vào `VectorPoint`. `QdrantVectorStore.upsert` dịch sang `models.SparseVector` và gộp vào dict vector cùng `dense`.

**Point đã có sẵn từ phase 6 chưa có sparse vector.** Chúng đơn giản là vắng mặt trong kết quả prefetch sparse [OBSERVED: query sparse trên collection trộn trả về đúng 2 trong 4 point, không lỗi]. Không crash, nhưng cũng **không đóng góp gì cho nhánh BM25**. Hệ quả thực tế: sau phase 7 phải **re-ingest lại một lần nữa** để sparse có dữ liệu. Nói trước ở đây, và `docs/SETUP.md` (phase 6) nên gộp cả hai lần này vào một quy trình nếu phase 6 và 7 chạy liền nhau.

## Config

```yaml
retriever:
  # Still "how many chunks the LLM gets" at this phase. Phase 8 adds fusion_limit and
  # takes the fan-out job away from this number — do NOT overload it here.
  top_k: 3
  score_threshold: 0.3
  # Off by default: this phase can merge without changing production behaviour, and
  # turning it back off is one variable rather than a revert.
  hybrid: false
  dense_prefetch_limit: 30
  sparse_prefetch_limit: 30
```

`RetrieverSettings` (`configs.py:59-61`) nhận đúng 3 field mới. Không thêm cơ chế đọc config thứ hai (`docs/system-architecture.md:60-64`).

**`top_k` giữ nguyên ý nghĩa ở phase này.** Nó vẫn là số chunk cuối cùng đưa cho LLM; phần mới chỉ là 60 ứng viên (30 dense + 30 sparse) được xét trước khi chọn ra `top_k` đó, thay vì 3 ứng viên như trước. Cám dỗ đáng nêu tên: mượn luôn `top_k` làm giới hạn fusion để phase 8 khỏi phải thêm config. Đừng — làm thế là để `top_k` mang hai nghĩa, và phase 9 sẽ phải gỡ ra. Con số điều khiển quạt ra (`fusion_limit`) sinh ra ở phase 8, đúng lúc có tầng rerank cần tới nó.

## TDD

**Tests-before (RED)** — `tests/test_sparse.py`:

1. `test_tokenize_lowercases_and_splits_on_non_word` — cơ bản.
2. `test_tokenize_normalises_unicode` — chuỗi NFD và NFC của cùng một từ tiếng Việt cho **cùng một danh sách token**. *Đỏ vì:* chưa có `tokenize`. Đây là bất đối xứng NFKC ở trên, thành test.
3. `test_encode_counts_term_frequency` — "a b a" → term "a" có value 2.0, "b" có 1.0.
4. `test_encode_of_empty_text_is_empty` — chuỗi rỗng / toàn dấu câu → `indices == []`. Nhánh này quan trọng: một sparse vector rỗng gửi lên Qdrant phải không nổ.
5. **`test_term_index_is_stable_across_processes`** — R2, test quan trọng nhất của phase:

   ```python
   expected = term_index("máy")
   for seed in ("0", "1", "2"):
       out = subprocess.run(
           [sys.executable, "-c",
            "from rag_chatbot.retrieval.sparse import term_index; print(term_index('máy'))"],
           env={**os.environ, "PYTHONHASHSEED": seed},
           capture_output=True, text=True, check=True,
       )
       assert int(out.stdout) == expected
   ```

   *Đỏ vì:* chưa có `term_index`. Dùng `sys.executable` (python của venv) nên import chạy được bất kể `away_from_dotenv` đã `chdir` sang `tmp_path` (`conftest.py:56-67`) — chi tiết này phải để ý, bỏ qua nó là có một test đỏ vì lý do hoàn toàn sai.

6. **`test_plain_hash_would_have_been_caught`** — test đối chứng, và **không được bỏ**:

   ```python
   values = set()
   for seed in ("0", "1", "2"):
       out = subprocess.run([sys.executable, "-c", "print(hash('máy'))"], ...)
       values.add(out.stdout.strip())
   assert len(values) > 1, "PYTHONHASHSEED no longer varies str hashing — test 5 is now vacuous"
   ```

   Lý do nó tồn tại: test 5 chỉ có nghĩa nếu bộ subprocess **thật sự** tạo ra được sự khác biệt mà nó tuyên bố phát hiện. Nếu một ngày `hash()` trở nên ổn định (hoặc `PYTHONHASHSEED` bị đặt cứng ở tầng nào đó), test 5 sẽ xanh với **bất kỳ** implementation nào — kể cả implementation sai. Đây đúng là bài học `test_app_js_never_uses_innerhtml` xanh giả (`docs/code-standards.md:84-87`) áp vào một chỗ khác: một test chỉ có nghĩa đúng bằng cái nó thật sự chạy qua. [OBSERVED: `hash('máy học')` cho 3 giá trị khác nhau trong 3 tiến trình; `zlib.crc32` cho `176058915` cả 3 lần.]

*`tests/test_vector_search.py`*

7. `test_upsert_stores_sparse_vector` — upsert point có `sparse`, rồi query sparse thuần → trả về đúng point đó.
8. `test_hybrid_search_fuses_both_lists` — hai point: một chỉ khớp dense mạnh, một chỉ khớp term. `search(vector, top_k=5, query_text="...")` trả về **cả hai**, còn dense-only chỉ trả về một. *Đỏ vì:* chưa có nhánh fusion. Đây là bằng chứng fusion thật sự làm việc chứ không chỉ chạy được.
9. **`test_score_threshold_applies_before_fusion_not_after`** — R4 thành test. Dựng dữ liệu sao cho một điểm fused rơi **dưới** 0.3: khẳng định nó **vẫn có** trong kết quả (ngưỡng không áp ngoài), trong khi một point có cosine dưới ngưỡng bị prefetch dense loại. *Đỏ vì:* chưa có nhánh này. Điểm RRF quan sát được nằm trong 0.3333–0.8333 [OBSERVED] nên phải dựng dữ liệu cẩn thận để chạm ngưỡng — nếu không dựng được một điểm fused dưới 0.3, **hạ giả định xuống**: khẳng định thẳng vào đối tượng `Prefetch` được truyền cho client (dùng một client giả ghi lại tham số) chứ đừng viết một test suy đoán rồi tin nó.
10. `test_hybrid_off_matches_dense_only` — cùng dữ liệu, `hybrid=false` và `query_text` được truyền → kết quả **y hệt** `search` không có `query_text`. Đây là bằng chứng công tắc thật sự tắt.
11. `test_points_without_sparse_survive_hybrid_search` — collection trộn (có point cũ không sparse) → truy vấn hybrid không lỗi, và point cũ vẫn về qua nhánh dense. [OBSERVED trong probe, nhưng cần một test giữ.]

**Bốn call site cũ phải xanh không sửa**: `tests/test_vector_search.py:22,30,38` và `tests/test_document_retrieval.py:26`.

**Implement** → xanh: `sparse.py` → `protocols.py` → `vector_search.py` → `document_retrieval.py` → `orchestrator.py` + `metrics.py` → config.

**Regression gate:**

```
uv run pytest -q                 → ≈108 passed, không giảm
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

`mypy src` là thứ bắt sót nếu một implementation của `VectorStore` không khớp Protocol mới — chỉ có một implementation (`QdrantVectorStore`), đã kiểm.

## Success

**Đo bằng máy:**

- [ ] 11 test mới xanh, gồm **cả** test đối chứng số 6. Test 6 thiếu = phase chưa xong.
- [ ] 4 call site `search` cũ xanh không sửa.
- [ ] Bốn cổng sạch, tổng test không giảm.
- [ ] `grep -rn "hash(" src/rag_chatbot/retrieval/sparse.py` → không có `hash(` trần nào.
- [ ] `grep -rn "qdrant" src/rag_chatbot/adaptor/protocols.py` → rỗng (tầng adaptor vẫn sạch hạ tầng).
- [ ] `retriever.hybrid` mặc định `false`; suite chạy với mặc định đó.
- [ ] **B2**: với `hybrid=true` trên collection có dữ liệu, mọi case `expected_source: null` trong `qa.jsonl` vẫn trả `NO_CONTEXT_ANSWER`. Đây là test **duy nhất** trong cả plan chạy nhánh `hybrid=true` với câu hỏi lạc đề — thiếu nó thì lỗ hổng grounding không có gì canh.
- [ ] **B2**: sàn sparse hoặc là một con số **đo được từ phân bố điểm BM25 trên bộ eval** (ghi cả con số lẫn cách đo vào verification), hoặc là `None` kèm ghi chú chỉ dùng điều kiện dense-set. Không được có số chọn tay không giải thích được.

**Cần hạ tầng thật (R12):**

- [ ] Re-ingest để sinh sparse vector cho toàn bộ point.
- [ ] `RETRIEVER__HYBRID=false uv run python scripts/run_eval.py --out data/eval/dense.json` → phải **khớp baseline phase 2** trong sai số thứ tự lưu trữ. Lệch nhiều nghĩa là công tắc tắt chưa thật sự tắt.
- [ ] `RETRIEVER__HYBRID=true uv run python scripts/run_eval.py --out data/eval/fusion.json --baseline data/eval/dense.json`.
- [ ] Ghi vào verification: hit-rate + MRR của cả hai, **và danh sách case đổi chỗ theo tên**.
- [ ] Nhìn phân bố `scores` trong `fusion.json`: xác nhận thang điểm đã đổi so với `dense.json`. Đây là R4 được nhìn thấy bằng mắt chứ không chỉ bằng test.

**Cổng của phase:** hit-rate sau fusion so với baseline phase 2. **Nếu không hơn, DỪNG và xem xét trước khi sang phase 8** — chi cả một cross-encoder 2GB lên trên một tầng fusion không chứng minh được giá trị là cách chắc chắn nhất để không bao giờ biết cái nào đã hỏng.

## Risks

- **R2 — hash không tất định.** Đã xử bằng `zlib.crc32` + test 5 + **test đối chứng 6**. Rủi ro còn lại gần bằng 0, nhưng chỉ khi test 6 tồn tại. Nếu ai đó thấy test 6 "thừa" và xoá đi, R2 quay về nguyên vẹn mà không có dấu hiệu nào.
- **R4 — ngưỡng sai thang.** Đã xử bằng ngưỡng trong `Prefetch` + test 9. Rủi ro còn lại: prefetch sparse **không** có ngưỡng, nên nhánh BM25 luôn trả đủ `sparse_prefetch_limit` kết quả kể cả khi khớp rất yếu. RRF thì chỉ quan tâm thứ hạng nên kết quả rác xếp cuối, nhưng chúng **vẫn chiếm chỗ** trong top-30 đưa sang rerank. Đây là một trong những thứ phase 8 phải dọn, và là lý do rerank tồn tại.
- **Point cũ không có sparse vector.** Không crash [OBSERVED] nhưng đóng góp bằng 0 cho nhánh BM25. Nếu quên re-ingest, hit-rate hybrid sẽ ≈ hit-rate dense và người ta sẽ kết luận sai rằng "fusion không giúp gì". Đưa bước re-ingest vào Success chính vì thế.
- **Tiếng Việt bị tách rời từ ghép.** Giới hạn đã biết, chấp nhận có ý thức. Cách kiểm nó có thành vấn đề hay không: nhìn danh sách case đổi chỗ ở cổng phase — nếu các case trượt tập trung vào từ ghép, thì đã có bằng chứng để mở lại thảo luận (bằng một DEC), chứ không phải bằng linh cảm.
- **`metrics.py` quên truyền `query_text`.** Lỗi này im lặng tuyệt đối: eval chạy xong, in ra số đẹp, và số đó đo đường dense trong khi ai cũng tưởng đang đo fusion. Xử: test 10 (`hybrid off == dense only`) cộng với việc **so `dense.json` và `fusion.json` phải KHÁC nhau** ở cổng. Hai file giống hệt nhau là dấu hiệu của đúng lỗi này, không phải dấu hiệu fusion vô dụng.
</content>
