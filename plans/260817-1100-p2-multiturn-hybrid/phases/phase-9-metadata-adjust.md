---
phase: 9
title: "Metadata Adjust"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 9 — Metadata Adjustment

## Overview

Tầng cuối trước LLM: `cross-encoder top10 → metadata adjustment → top5`.

**Sơ đồ người dùng vẽ có tầng này nhưng chưa định nghĩa nội dung.** Phase này đề xuất nội dung, và đề xuất đó **cần người dùng xác nhận ở gate validate** trước khi cook chạy tới đây. Ba quy tắc dưới đây là suy luận từ payload đang có, không phải yêu cầu người dùng đã nêu.

Payload hiện có đúng năm trường: `source`, `source_type`, `title`, `page`, `index` (`src/rag_chatbot/validate.py:17-25`, ghi vào Qdrant qua `chunk.model_dump(mode="json")` ở `retrieval/document_retrieval.py:165`). **Không có timestamp** → **không làm được recency boost**. Thêm timestamp vào payload là một lần re-ingest nữa, và không đáng ở đợt này.

Phase ship với công tắc mặc định **TẮT** (`metadata_adjust.enabled: false`), như phase 7 và 8.

Phụ thuộc: phase 8.

## Files

- **Create** `src/rag_chatbot/retrieval/metadata_adjust.py` — hàm thuần, không state.
- **Modify** `src/rag_chatbot/evaluate/metrics.py` — **B1**: tầng này thay thế phép cắt cuối trong `retrieve()`, nên đường đo phải phản ánh nó. Cùng lý do với phase 8.
- **Modify** `src/rag_chatbot/retrieval/__init__.py` — export.
- **Modify** `src/rag_chatbot/orchestrator.py` — chèn vào `answer()`.
- **Modify** `src/rag_chatbot/configs.py`, `configs/default.yaml` — `MetadataAdjustSettings`, và **chốt lại toàn bộ chuỗi giới hạn**.
- **Modify** `src/rag_chatbot/api/static/index.html` — mặc định slider `top_k`.
- **Create** `tests/test_metadata_adjust.py`.

**Không** đụng `retrieval/vector_search.py`. Bản nháp gợi ý phase này cũng chạm vào đó; đã xem lại và nó **không đúng chỗ**: metadata adjustment thao tác trên `list[RetrievedChunk]` **sau** rerank, tức là ở tầng orchestrator, không phải tầng store. Nhét nó vào `vector_search.py` là bắt vector store biết về một tầng chạy sau nó — đúng loại đảo ngược phụ thuộc mà tầng adaptor tồn tại để ngăn (`docs/system-architecture.md:14-25`).

## Ba quy tắc đề xuất — CẦN NGƯỜI DÙNG XÁC NHẬN

Cả ba đều **thuần thuật toán**, chạy trong micro giây, không gọi model, và test được không cần mạng. Đó là tiêu chí chọn chúng: tầng này nằm sau một cross-encoder tốn kém, nên nó phải rẻ.

**Quy tắc 1 — trần theo nguồn (`max_per_source`).**
Tối đa N chunk mỗi `source`. Hiện tại một tài liệu có thể chiếm trọn cả 3 slot (`retriever.top_k: 3`, `configs/default.yaml:26`) — người dùng hỏi một câu mà câu trả lời cần đối chiếu hai tài liệu thì không bao giờ nhận được cả hai. Đây là chỗ sửa. Đề xuất `max_per_source: 2`.

**Quy tắc 2 — gộp chunk liền kề.**
Cùng `source` và `index` liên tiếp thì nối lại, khôi phục ngữ cảnh mà chunking đã cắt. Đặc biệt có ích cho PDF: `_chunk_pdf` cắt cứng theo trang (`document_retrieval.py:141-153`), nên một câu bắc qua hai trang bị chia đôi một cách cơ học.

Ba chi tiết phải xử, và cả ba đều mất thông tin:
- `score` của chunk gộp = **max** của các chunk thành phần (không phải tổng — tổng thưởng cho việc gộp và làm hỏng thứ hạng).
- `page` lấy của chunk có `index` nhỏ nhất. **Mất mát chấp nhận được nhưng phải nói ra**: trích dẫn có thể trỏ vào trang đầu của cặp trong khi câu trả lời nằm ở trang sau. UI hiển thị `", trang " + source.page` (`app.js:135`) nên người dùng sẽ thấy con số đó.
- `title` lấy của chunk `index` nhỏ nhất, cùng lý do.

**Quy tắc 3 — boost khi khớp heading.**
`title` từ `split_markdown` (`chunking/splitter.py:56-69`) khớp từ khoá truy vấn thì nâng hạng nhẹ. Dùng lại `tokenize` của phase 7 (`retrieval/sparse.py`) — **DRY**: cùng một định nghĩa "từ là gì" cho BM25 và cho quy tắc này, và cùng một chuẩn hoá NFKC. Viết một tokenizer thứ hai ở đây là gieo một bất đối xứng mới đúng vào chỗ vừa dọn xong.

Boost là **cộng thêm** một hằng số nhỏ (`title_boost: 0.05`), không phải nhân. Lý do: sau rerank, `score` là điểm cross-encoder ở một thang chưa biết trước; nhân thì hiệu ứng phụ thuộc độ lớn tuyệt đối của điểm, cộng thì không. `[ASSUMED]`: chưa đo thang điểm cross-encoder thật; nếu phase 8 cho thấy điểm nằm ngoài khoảng ~[0,1] thì hằng số này phải chỉnh theo, và phase 10 là chỗ ghi lại điều đó.

**Chỉ `title` khớp mới được boost — `text` thì không.** Boost theo nội dung là làm lại việc mà dense, BM25 và cross-encoder đều đã làm, ba lần, tốt hơn.

## Thứ tự — quyết định toàn bộ tính tất định

Không được đảo. Mỗi bước tiêu thụ kết quả của bước trước:

```
chunks (top10 từ rerank)
  → 1. boost theo title           (đổi score)
  → 2. sort giảm dần theo score   (sort ỔN ĐỊNH: hoà thì giữ thứ tự rerank)
  → 3. gộp chunk liền kề          (giảm số phần tử, giữ score max)
  → 4. cap theo source            (giữ thứ tự, bỏ phần vượt trần)
  → 5. cắt còn final_top_k = 5
```

Vì sao đúng thứ tự này:

- **Boost trước sort**: boost mà không sort lại thì không có tác dụng gì.
- **Sort ổn định** (`sorted(..., key=..., reverse=True)` của Python là ổn định): khi điểm bằng nhau, thứ tự rerank được giữ. Cross-encoder đã tốn công xếp hạng; hoà điểm không phải lý do để vứt kết quả đó đi.
- **Gộp trước cap**: gộp làm giảm số chunk của một source, nên gộp sau cap sẽ cap trên các phần tử rồi mới nhập chúng lại — kết quả là ít chunk hơn dự định một cách bất ngờ.
- **Cap trước cắt**: cắt trước rồi cap thì top-5 có thể co lại còn 3 sau khi cap, và slot bị mất không được ai lấp.

Mọi phép so sánh dùng `(source, index)` chứ không dùng vị trí trong list — vị trí đổi sau mỗi bước.

## Chuỗi giới hạn — chốt lại một lần

Sau ba phase có năm con số điều khiển số chunk. Đây là phase chốt lại, và `configs/default.yaml` phải ghi thành một khối liền mạch để không ai phải suy ra:

| Bước | Setting | Đề xuất | Sinh ra ở |
|---|---|---|---|
| dense prefetch | `retriever.dense_prefetch_limit` | 30 | phase 7 |
| sparse prefetch | `retriever.sparse_prefetch_limit` | 30 | phase 7 |
| sau fusion (quạt ra cho rerank) | `retriever.fusion_limit` | 30 | phase 8 |
| sau rerank | `rerank.top_n` | 10 | phase 8 |
| **cuối cùng, LLM nhận** | `retriever.top_k` | **5** | phase này đổi 3 → 5 |

Bất biến giữ xuyên suốt phần B, và phase này chỉ chốt lại chứ không phát minh: **`top_k` có đúng một nghĩa — số chunk LLM nhận được.** Phase 7 giữ nguyên nghĩa đó; phase 8 thêm `fusion_limit` riêng cho việc quạt ra thay vì mượn `top_k`. Việc duy nhất còn lại ở đây là đổi **giá trị mặc định** 3 → 5 cho khớp sơ đồ, không đổi ý nghĩa.

Không có `metadata_adjust.final_top_k`. **DRY**: tầng metadata cắt tới `top_k` hiệu lực (`request.top_k or settings.retriever.top_k`, `orchestrator.py:53`), thay thế đúng phép cắt `chunks[:top_k]` mà phase 8 đặt sẵn ở cuối `answer()`. Một con số, một ý nghĩa, một chỗ.

**Hai chỗ chịu ảnh hưởng của việc đổi mặc định 3 → 5, phải sửa đồng bộ:**

1. `configs/default.yaml:26` và `configs.py:60` — mặc định của `RetrieverSettings.top_k`.
2. `index.html:48,50` — slider gửi `Number(topK.value)` (`app.js:205`) và **luôn** ghi đè mặc định server, nên nếu chỉ đổi YAML thì UI vẫn xin 3 và người dùng qua UI không bao giờ thấy 5. Đổi cả `<output id="top-k-value">3</output>` và `value="3"` của input.

`max="20"` của slider (`index.html:50`) và `le=20` của `QueryRequest` (`validate.py:58`) **không cần đổi**: 5 nằm gọn trong đó, và các giới hạn trung gian (30) là chuyện nội bộ, không phơi ra API. Đây là phần thưởng của việc giữ `top_k` một nghĩa — nếu để nó điều khiển tầng fusion thì đã phải nới `le=20` lên 30 và phơi một chi tiết nội bộ ra hợp đồng công khai.

Việc **đổi mặc định 3 → 5** vẫn cần người dùng xác nhận: nó làm mỗi câu trả lời tốn thêm token và tiền.

## Config

```yaml
retriever:
  # 3 -> 5: the final number of passages the LLM receives. The intermediate limits
  # (dense/sparse prefetch, fusion_limit, rerank.top_n) are internal and stay internal.
  top_k: 5

metadata_adjust:
  # Off by default like the other part-B layers: turning it on is one variable.
  enabled: false
  # A single document can otherwise take every slot, so a question that needs two
  # sources compared against each other never gets both.
  max_per_source: 2
  merge_adjacent: true
  # Added, not multiplied: after reranking, score is a cross-encoder value on a scale
  # this repo has not measured, and a multiplier's effect would depend on it.
  title_boost: 0.05
```

## TDD

Toàn bộ test là hàm thuần trên `list[RetrievedChunk]` — không cần Qdrant, không cần fixture nào ngoài một helper dựng chunk (mượn khuôn `tests/test_prompts.py:7-15`).

**Tests-before (RED)** — `tests/test_metadata_adjust.py`:

1. `test_cap_per_source_keeps_the_best_n` — 5 chunk cùng source điểm giảm dần, `max_per_source=2` → giữ 2 chunk điểm cao nhất, đúng thứ tự.
2. `test_cap_per_source_does_not_touch_other_sources` — 3 source × 3 chunk, cap 2 → 6 chunk, mỗi source 2.
3. `test_merge_adjacent_joins_consecutive_indices` — `index` 4 và 5 cùng source → 1 chunk, `text` nối theo đúng thứ tự index.
4. `test_merge_adjacent_ignores_gaps` — `index` 4 và 6 → **không** gộp.
5. `test_merge_adjacent_ignores_different_sources` — cùng `index` khác `source` → không gộp.
6. `test_merged_chunk_keeps_max_score_and_first_page` — điểm 0.4 và 0.9 → 0.9; page 3 và 4 → 3. Đây là mất mát đã biết ở mục trên, thành test để nó là **quyết định** chứ không phải tai nạn.
7. `test_merge_is_order_independent` — cùng tập chunk theo hai thứ tự đầu vào khác nhau → kết quả giống hệt. Không có test này thì quy tắc 2 tất định trên giấy nhưng phụ thuộc thứ tự trong thực tế.
8. `test_title_boost_applies_on_token_match` — chunk có `title="Cài đặt Qdrant"`, query "cài đặt thế nào" → score tăng đúng `title_boost`.
9. `test_title_boost_is_case_and_unicode_insensitive` — dùng lại `tokenize` của phase 7 nên NFC/NFD và hoa/thường đều khớp. Nếu ai đó viết tokenizer riêng ở đây, test này đỏ.
10. `test_title_boost_skips_chunks_without_title` — `title=None` (thường gặp với `.txt`, `document_retrieval.py:117-127`) → không lỗi, không boost.
11. `test_no_boost_from_text_match` — từ khoá chỉ có trong `text`, không có trong `title` → **không** boost. Ranh giới ở mục quy tắc 3, thành test.
12. **`test_pipeline_order_is_boost_sort_merge_cap_cut`** — test tổng hợp, dựng một tập chunk mà **mỗi thứ tự khác sẽ cho kết quả khác**, rồi khẳng định kết quả của đúng thứ tự đã chốt. Đây là test duy nhất giữ được chuỗi 5 bước; 11 test kia chỉ kiểm từng bước rời.
13. `test_disabled_only_cuts` — `enabled=false` → cùng thứ tự, cùng score, **và `len(result) <= top_k`**. Công tắc tắt phần *điều chỉnh*, **không** tắt phần *cắt*.

    **H1 — vì sao không phải "trả về đúng list vào".** Tầng này thay thế phép cắt `chunks[:top_k]` mà phase 8 đặt ở cuối `retrieve()`. Nếu khi tắt nó trả về nguyên list, thì **không ai cắt**: với `rerank.top_n: 10`, cấu hình `rerank=cross_encoder` + `metadata=false` sẽ đẩy **10** chunk vào LLM thay vì 5.

    Đó chính là **dòng 3 của bảng phase 10** — dòng đó sẽ chạy với 10 đoạn văn trong khi ba dòng còn lại chạy với 5, tức bảng so bốn cấu hình khác nhau ở một biến ngoài dự kiến, và kết luận về đóng góp của cross-encoder bị nhiễu bởi lượng context gấp đôi. Success của phase này cũng có dòng `len(sources) <= 5` — sai ở đúng cấu hình đó.
14. `test_orchestrator_applies_metadata_adjust_after_rerank` — trong `tests/test_metadata_adjust.py` hoặc `tests/test_orchestrator.py`: reranker giả trả 10 chunk, khẳng định `response.sources` có ≤5 và ≤2 chunk mỗi source.

**Implement** → xanh: `metadata_adjust.py` → config → `orchestrator.py` → `index.html`.

**Regression gate:**

```
uv run pytest -q                 → ≈121 passed, không giảm
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

Đặc biệt kiểm: `tests/test_api.py` và `tests/test_orchestrator.py` phải xanh **không sửa** khi `enabled=false`.

## Success

**Đo bằng máy:**

- [ ] 14 test mới xanh, gồm test 12 (thứ tự) và test 7 (độc lập thứ tự đầu vào).
- [ ] Bốn cổng sạch, tổng không giảm.
- [ ] `metadata_adjust.enabled` mặc định `false`; suite chạy với mặc định đó.
- [ ] `grep -rn "def tokenize" src/` → đúng **một** kết quả (`retrieval/sparse.py`). Hai kết quả nghĩa là DRY đã gãy.
- [ ] `configs/default.yaml` có khối chuỗi giới hạn liền mạch với comment nêu bước nào ăn số nào.
- [ ] `index.html` slider mặc định khớp `retriever.top_k` mới.

**Cần hạ tầng thật (R12):**

- [ ] `METADATA_ADJUST__ENABLED=true uv run python scripts/run_eval.py --out data/eval/metadata.json --baseline data/eval/rerank.json`.
- [ ] `top_k` cuối = 5, xác nhận trên một truy vấn thật qua `/query` (`len(sources) <= 5`).
- [ ] **Kiểm ngân sách token bằng đo, không bằng ước lượng.** 5 chunk × ~1000 ký tự (`chunking.chunk_size: 1000`, `configs/default.yaml:30`) cộng history (trần 1500 token từ phase 3) phải nằm gọn trong `context_token_budget: 6000`. Với tiếng Việt tỉ lệ token/ký tự **xấu hơn** tiếng Anh, nên con số phải lấy từ `count_tokens` (`utils/tokens.py:18-19`) trên chunk tiếng Việt **thật** từ `data/documents/`, không phải từ phép chia. Chạy và ghi con số:

  ```
  uv run python -c "..."   # count_tokens trên 5 chunk dài nhất của một tài liệu tiếng Việt
  ```

  Nếu vượt, `format_context` sẽ lặng lẽ cắt bớt passage (`prompts.py:29-32`) và tầng metadata vừa xây thành vô nghĩa ở chunk cuối. Vượt thì chỉnh `context_token_budget` hoặc `chunk_size`, và ghi lý do.
- [ ] Nghiệm thu tay: hỏi một câu cần đối chiếu **hai tài liệu**. Trước phase này (`enabled=false`) và sau (`enabled=true`) → so panel nguồn. Đây là bước duy nhất cho thấy quy tắc 1 giải quyết đúng vấn đề nó được sinh ra để giải quyết.

**Cổng của phase:** `top_k` cuối = 5, ngân sách token đã đo bằng số thật trên văn bản tiếng Việt.

## Risks

- **Ba quy tắc là ĐỀ XUẤT, chưa được người dùng xác nhận.** Rủi ro lớn nhất của phase và nó không phải rủi ro kỹ thuật. Nếu người dùng có ý khác cho tầng này, gate validate là chỗ nói — thực thi trước rồi hỏi sau là làm ba lần công.
- **Gộp chunk làm trích dẫn trỏ sai trang.** Mất mát đã biết, đã có test 6 làm nó thành quyết định. Nếu không chấp nhận được, phương án thay thế là **không gộp** (`merge_adjacent: false`) — công tắc có sẵn chính vì thế.
- **`title_boost: 0.05` là con số chọn tay.** `[ASSUMED]`, không có phép đo nào đứng sau. Nó phụ thuộc thang điểm cross-encoder mà phase 8 mới đo được. Đặt lại sau khi có số của phase 8, và ghi vào phase 10.
- **Quy tắc 1 có thể làm hit-rate TỤT.** Nếu tài liệu đúng thật sự có 3 chunk liên quan nhất, cap về 2 sẽ đẩy một chunk tốt ra để nhường chỗ cho một chunk kém hơn từ nguồn khác. Đây là đánh đổi **cố ý**: đa dạng nguồn đổi lấy độ sâu. Cách kiểm nó có đáng không: nhìn danh sách case đổi chỗ ở cổng, không nhìn con số tổng.
- **Chuỗi 5 bước dễ bị "tối ưu" thành sai.** Nhìn qua thì đảo bước 3 và 4 chẳng khác gì. Test 12 là thứ duy nhất chặn, nên nó phải được dựng bằng dữ liệu mà **mỗi thứ tự khác cho kết quả khác** — một test tổng hợp trên dữ liệu quá hiền sẽ xanh với mọi thứ tự và tệ hơn là không có.
</content>
