---
phase: 6
title: "Collection Migration"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 6 — Collection Migration

## Overview

**Đây là phase phá vỡ tương thích. Làm sai là mất index.**

Collection hiện dùng **vector không tên** — `ensure_collection` truyền `models.VectorParams(...)` trần vào `vectors_config` (`src/rag_chatbot/retrieval/vector_search.py:50-56`). Hybrid cần **vector có tên**: `dense` + sparse `bm25`. Đây không phải thay đổi thêm-vào; nó là schema khác hẳn, và Qdrant từ chối trộn hai kiểu [OBSERVED: upsert vector không tên vào collection có tên → `ValueError: Unnamed vectors are not allowed when a collection has named vectors or multivectors: ['dense'], []`].

**Phase này KHÔNG bật hybrid.** Nó chỉ đổi schema và chứng minh đường dense-only vẫn cho kết quả tương đương sau khi đổi. Tách như vậy để khi phase 7 làm hỏng chất lượng retrieval, ta biết chắc thủ phạm là fusion chứ không phải migration.

**Quyết định thiết kế đáng nói:** phase này khai báo **cả hai** vector — `dense` có tên **và** sparse `bm25` với `Modifier.IDF` — dù phase 7 mới bắt đầu ghi sparse. Lý do: một lần migrate thay vì hai. Khai báo một sparse vector rỗng không tốn gì (point không có sparse vector đơn giản là vắng mặt trong kết quả sparse [OBSERVED: probe trả về đúng 2 trong 4 point khi query sparse]), còn bắt người dùng re-ingest toàn bộ tài liệu hai lần thì tốn thật.

Phụ thuộc: phase 5 (và điều kiện DEC dưới đây).

## Điều kiện tiên quyết — DEC cho deviation

Phần B **không nằm trong thứ tự đã chốt ở DEC-3** (P1 → P2 multi-turn → P3 hardening → mở mạng). Nó là hạng mục mới chen vào giữa.

**Không được viết dòng code nào của phase này trước khi một DEC mới có mặt trong `docs/decisions.md`**, ghi qua `decision_register.py --append-alloc`, nội dung tối thiểu:

- Hybrid retrieval được chèn vào giữa P2 và P3 hardening.
- Lý do (người dùng chốt phạm vi gồm cả phần B).
- Cái gì bị đẩy lùi vì nó (P3 hardening).
- Chi phí đã biết được chấp nhận: một lần re-ingest toàn bộ, cộng dependency nặng ở phase 8.
- `affects:` phải liệt kê `src/rag_chatbot/retrieval/vector_search.py`, `scripts/migrate_collection.py`, `configs/default.yaml`.

Plan này **không tự lật DEC-3**. Đây là success criterion đầu tiên và kiểm được bằng `grep`.

## Files

- **Modify** `src/rag_chatbot/retrieval/vector_search.py` — schema có tên, phát hiện schema cũ, `upsert`/`search` dùng tên vector.
- **Create** `scripts/migrate_collection.py` — dựng lại collection và nạp lại.
- **Modify** `tests/test_vector_search.py` — test cho nhánh phát hiện schema.
- **Modify** `docs/SETUP.md` — quy trình migrate.

**Không** đụng `adaptor/protocols.py`: `VectorPoint.vector` vẫn là `list[float]` (`protocols.py:16-20`), việc ánh xạ sang `{"dense": vector}` nằm trọn trong `QdrantVectorStore.upsert`. Đây là đúng chỗ — tầng adaptor mô tả *cái gì*, còn *Qdrant gọi nó là gì* là chi tiết của implementation. Giữ được ranh giới này thì `document_retrieval.py` (`:161-168`) không phải đổi một dòng.

**Không** đụng `tests/conftest.py`: fixture `vector_store` gọi `ensure_collection()` trên một `QdrantClient(":memory:")` trắng (`conftest.py:80-84`), nên nó luôn đi nhánh tạo mới. Đã kiểm.

## Schema mới

```python
_DENSE_VECTOR = "dense"
_SPARSE_VECTOR = "bm25"


class CollectionSchemaError(RuntimeError):
    """Raised when an existing collection predates the hybrid schema."""
```

`ensure_collection`:

```python
def ensure_collection(self) -> None:
    if self._client.collection_exists(self.collection):
        # Returning early here used to mean a collection created before the hybrid
        # schema kept being used as-is: every hybrid query would then fail somewhere
        # far away from the cause. Fail loudly at startup instead.
        self._require_hybrid_schema()
        return
    self._client.create_collection(
        collection_name=self.collection,
        vectors_config={
            _DENSE_VECTOR: models.VectorParams(
                size=self._settings.vector_size,
                distance=models.Distance(self._settings.distance),
            )
        },
        sparse_vectors_config={
            # IDF is computed server-side, so the encoder only has to ship raw term
            # frequencies — that is what keeps BM25 free of any new dependency.
            _SPARSE_VECTOR: models.SparseVectorParams(modifier=models.Modifier.IDF)
        },
    )
    ...
```

`_require_hybrid_schema` — cách phát hiện **đã đo**, không đoán:

| | `config.params.vectors` | `config.params.sparse_vectors` |
|---|---|---|
| Collection cũ (unnamed) | `VectorParams` | `None` |
| Collection hybrid | `dict` khoá `['dense']` | `dict` khoá `['bm25']` |

[OBSERVED trên `qdrant-client 1.19.0`, `QdrantClient(":memory:")`]

```python
def _require_hybrid_schema(self) -> None:
    params = self._client.get_collection(self.collection).config.params
    vectors = params.vectors
    if not isinstance(vectors, dict) or _DENSE_VECTOR not in vectors:
        raise CollectionSchemaError(
            f"collection '{self.collection}' uses the pre-hybrid unnamed vector schema. "
            f"Run: uv run python scripts/migrate_collection.py --yes"
        )
    if _SPARSE_VECTOR not in (params.sparse_vectors or {}):
        raise CollectionSchemaError(
            f"collection '{self.collection}' has no '{_SPARSE_VECTOR}' sparse vector. "
            f"Run: uv run python scripts/migrate_collection.py --yes"
        )
```

Thông báo lỗi **phải nêu tên lệnh cần chạy**. Một `RuntimeError` nói "schema mismatch" trơ trọi chỉ chuyển sự bối rối từ chỗ này sang chỗ khác.

`upsert` (`vector_search.py:65-75`): `vector={_DENSE_VECTOR: p.vector}`.

`search` (`vector_search.py:77-100`): thêm `using=_DENSE_VECTOR` vào `query_points`. **Bắt buộc** — thiếu nó thì raise [OBSERVED: `ValueError: Dense vector  is not found in the collection`]. Chi tiết này thực ra là tin tốt: quên `using=` là nổ ngay chứ không im lặng trả kết quả sai.

`ensure_collection` được gọi từ `orchestrator.startup()` (`orchestrator.py:48-49`) trong lifespan (`api/app.py:37`), nên `CollectionSchemaError` sẽ **chặn app khởi động**. Đó là hành vi đúng: chạy với schema sai còn tệ hơn không chạy. Ghi vào `docs/SETUP.md` để người gặp lỗi này biết ngay phải làm gì.

## `scripts/migrate_collection.py`

Đây là script duy nhất trong repo có thể **xoá dữ liệu**, nên nó được viết như vậy. Trình tự bắt buộc:

1. **Chụp trước khi đụng.** `list_sources()` (`vector_search.py:115-166`) + `info().points_count`, ghi ra `data/eval/migration-snapshot-<UTC timestamp>.json`. Ghi **trước** mọi thao tác phá huỷ, không phải sau.

   **B3 — snapshot KHÔNG được ghi đè, và phải có chế độ resume.** Đây là lỗ hổng khiến lưới an toàn của phase này tự phá chính nó:

   > Người dùng chạy `--yes`. Snapshot ghi 8 nguồn / 340 point. `delete_collection` chạy. Đang `ingest_directory` thì Ctrl-C / rate limit OpenAI / mạng đứt sau 3 nguồn — collection còn 3 nguồn / 120 point. Người dùng chạy lại script. Bước 1 **ghi đè** snapshot bằng trạng thái sau sự cố (3 nguồn / 120 point); bản ghi 8 nguồn biến mất vĩnh viễn. Bước 2 đối chiếu 3 nguồn với đĩa → qua. Bước 6 so 340-mới với 120-cũ → **exit 0, báo thành công**. Mất 5 nguồn, im lặng.

   Ba ràng buộc bắt buộc:
   - Tên file có timestamp; script **abort nếu path đích đã tồn tại**. Không bao giờ ghi đè một snapshot.
   - Ghi một marker `data/eval/migration-in-progress.json` ngay trước `delete_collection`, xoá nó ở bước 6 khi thành công. Marker còn tồn tại = lần chạy trước đứt giữa chừng.
   - Khi khởi động: nếu marker tồn tại **hoặc** collection đã mang schema hybrid mà vẫn có snapshot chưa đóng → vào **chế độ resume**: đọc snapshot chưa đóng **cũ nhất** làm mốc đối chiếu, **không** chụp lại. Nếu không xác định được mốc → abort và nói rõ, đừng đoán.

   Lưu ý làm nó dễ xảy ra hơn: `--dry-run` là mặc định nên người dùng buộc phải gõ `--yes` — nghĩa là lần chạy lại gần như chắc chắn cũng có `--yes` (đã gõ một lần rồi).
2. **Đối chiếu khả năng phục hồi.** Mỗi `source` trong snapshot phải khớp một file trong `settings.storage.documents_dir` hoặc `settings.storage.upload_dir` (`configs.py:76-78`). **Thiếu bất kỳ nguồn nào → abort, exit ≠ 0**, in danh sách nguồn không tìm thấy. Cờ `--allow-missing` để ép, và khi đó phải in cảnh báo liệt kê chính xác cái sắp mất.
   Đây là điểm cốt lõi của R8: nguồn nạp qua `POST /ingest` với `url` (`orchestrator.py:87-89`) **không có mặt trên đĩa** và sẽ biến mất vĩnh viễn. Script phải nói ra, không để người dùng phát hiện sau.
3. **`--dry-run`** (nên là mặc định): in snapshot, in danh sách sẽ nạp lại, in cái sắp mất — rồi thoát mà không đụng gì.
4. **Đòi `--yes`** để thực sự chạy. Không có thì in hướng dẫn rồi thoát.
5. `delete_collection` → `ensure_collection()` (giờ dựng schema mới) → `pipeline.ingest_directory()` cho `documents_dir`, rồi cho `upload_dir`.
6. **Đối chiếu sau.** `points_count` sau, và `list_sources()` sau. In bảng trước/sau. **Exit ≠ 0 nếu `points_count` sau < trước, hoặc nếu có nguồn trong snapshot vắng mặt sau.**

Bước 6 là thứ biến "chắc là được rồi" thành một mã thoát. `points_count` sau **có thể lớn hơn** trước nếu `data/documents/` đã có tài liệu chưa từng nạp — đó là bình thường, chỉ nhỏ hơn mới là hỏng.

Script dùng `RAGOrchestrator` để nạp lại (`orchestrator.ingest_directory`, `orchestrator.py:100-101`) chứ không tự dựng đường ingest thứ hai — nạp lại bằng một đường khác đường thật là cách chắc chắn nhất để hai đường trôi khỏi nhau.

## TDD

**Tests-before (RED)** — `tests/test_vector_search.py`:

1. `test_ensure_collection_creates_named_and_sparse_vectors` — sau `ensure_collection()` trên client trắng: `config.params.vectors` là `dict` có khoá `dense`, `config.params.sparse_vectors` có khoá `bm25` với `modifier` là IDF.
   *Đỏ vì:* `vector_search.py:52` dựng `VectorParams` trần → `vectors` là `VectorParams`, không phải `dict`. Đỏ vì nghiệp vụ (schema sai), không phải vì import.
2. `test_ensure_collection_rejects_legacy_unnamed_schema` — dựng tay một collection unnamed bằng `client.create_collection(..., vectors_config=VectorParams(...))`, rồi gọi `store.ensure_collection()` → `pytest.raises(CollectionSchemaError)` và thông báo lỗi **chứa chuỗi `"migrate_collection.py"`**.
   *Đỏ vì:* hiện tại `vector_search.py:48-49` return im lặng. **Đây là R3 biến thành test.** Khẳng định vào nội dung thông báo là cố ý: một exception không chỉ đường thì chỉ hoãn sự bối rối.
3. `test_ensure_collection_rejects_named_without_sparse` — collection có `dense` nhưng thiếu `bm25` → cũng raise. Nhánh này bắt trường hợp migrate nửa vời.
4. `test_ensure_collection_is_idempotent_on_the_new_schema` — gọi hai lần liên tiếp, lần hai không raise và không tạo lại.

**Ba test cũ phải xanh không sửa** — đây là bằng chứng migration không làm hỏng đường dense:

- `test_search_returns_typed_chunks` (`tests/test_vector_search.py:20-25`)
- `test_score_threshold_filters_weak_matches` (`:28-30`)
- `test_upsert_with_same_id_replaces` (`:33-38`)

Cộng `tests/test_document_retrieval.py:26` (`vector_store.search(...)` qua đường ingest thật) và toàn bộ `tests/test_api.py`. Nếu bất kỳ cái nào phải sửa để xanh, migration đã đổi hành vi ngoài phạm vi — dừng lại xem xét.

**Implement** → xanh: `vector_search.py`, rồi `scripts/migrate_collection.py`, rồi `docs/SETUP.md`.

**Regression gate:**

```
uv run pytest -q                 → ≈98 passed, không giảm
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

## Success

**Đo bằng máy:**

- [ ] DEC cho deviation đã có trong `docs/decisions.md` **trước** commit đầu tiên của phase — kiểm bằng `git log` so với timestamp DEC.
- [ ] 4 test mới xanh; 3 test search cũ + `test_document_retrieval.py` xanh **không sửa một ký tự**.
- [ ] Bốn cổng sạch.
- [ ] `uv run python scripts/migrate_collection.py --help` liệt kê `--dry-run`, `--yes`, `--allow-missing`.
- [ ] Chạy script **không** `--yes` → không đụng gì, exit 0 kèm hướng dẫn.

**Cần hạ tầng thật (R12):**

- [ ] `--dry-run` trên collection thật in đúng danh sách nguồn hiện có, khớp với `GET /documents`.
- [ ] Thử nghiệm đường abort: tạm đổi tên một file trong `data/documents/` → script **abort, exit ≠ 0**, nêu đúng tên nguồn thiếu. Đổi tên lại. **Đây là bước duy nhất chứng minh R8 đã được xử** — không kiểm thì lưới an toàn chỉ là code chưa từng chạy.
- [ ] Migrate thật: `points_count` sau ≥ trước, `list_sources()` sau khớp snapshot.
- [ ] **B3 — kịch bản đứt giữa chừng phải được diễn thật, không chỉ lập luận:** chạy migrate, giết tiến trình giữa `ingest_directory`, chạy lại script. Khẳng định: snapshot cũ **còn nguyên**, script vào chế độ resume và đối chiếu với mốc 8-nguồn, và nếu chỉ khôi phục được 3 nguồn thì **exit ≠ 0**. Đây là kịch bản duy nhất mà lưới an toàn từng tự phá chính nó — chưa diễn lại được thì phase chưa xong.
- [ ] App khởi động lại được, `/query` (vẫn dense-only) trả kết quả **tương đương trước migration** — chạy `run_eval.py` và so với baseline phase 2. Sai lệch nhỏ do thứ tự lưu trữ chấp nhận được; hit-rate tụt rõ rệt thì migration đã hỏng gì đó.
- [ ] Thử nghiệm R3 từ phía người dùng: trỏ app vào một collection cũ (đổi `QDRANT__COLLECTION_NAME`) → app **không khởi động**, log nêu đúng lệnh migrate.

**Cổng của phase:** migrate xong, `points_count` khớp, `/query` cũ trả kết quả tương đương. **Chưa bật hybrid ở phase này.**

## Risks

- **R8 — mất index.** Đã xử bằng 6 bước ở trên. Rủi ro còn lại **không thể xoá hết**: nguồn nạp qua URL không có trên đĩa. Snapshot ghi lại tên chúng để nạp tay, nhưng nếu URL đã chết thì nội dung mất thật. Nói trước, không giấu.
- **R3 — schema cũ trôi qua im lặng.** Đã xử bằng `_require_hybrid_schema` + test 2. Rủi ro còn lại: cách phát hiện dựa vào hình dạng `config.params` của `qdrant-client 1.19.0`; một bản nâng cấp có thể đổi hình dạng đó. Giảm nhẹ: test 1 và 2 sẽ đỏ ngay khi nâng cấp làm đổi hình dạng — chúng khẳng định thẳng vào cấu trúc, nên chúng chính là cái phát hiện thay đổi.
- **App không khởi động được sau khi lỗi migrate.** Đây là hành vi *đúng* nhưng vẫn là sự cố với người vận hành: `/ui` cũng chết theo (R1 của P1 — lifespan gọi `startup()`, `api/app.py:37`). Xử: `docs/SETUP.md` phải có mục "app không khởi động sau khi nâng cấp" với thông báo lỗi nguyên văn và lệnh cần chạy.
- **Migrate trên máy dev xong tưởng là xong.** Mỗi môi trường có collection riêng. `docs/SETUP.md` phải nói rõ migrate là việc chạy **một lần cho mỗi Qdrant instance**, không phải một lần cho mỗi repo.
- **Khai báo sparse vector sớm ở phase này có thể là thừa nếu phần B bị bỏ giữa chừng.** Chấp nhận có ý thức: một sparse vector rỗng không tốn dung lượng đáng kể và không đụng đường dense. Cái giá của phương án ngược lại — migrate hai lần — cao hơn nhiều.
</content>
