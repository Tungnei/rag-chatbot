---
phase: 4
title: "List Endpoint"
status: pending
plan: 260812-1221-p1-chat-ui
created: 2026-08-12
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 4 — List Endpoint (`GET /documents`)

## Overview

Thêm `GET /documents` trả danh sách nguồn thật đang có trong index, kèm số chunk mỗi nguồn.

**Đây là phase duy nhất của P1 chạm vào logic backend**, và nó tồn tại vì một quyết định có ý thức ở gate validate: trang admin cần danh sách tài liệu thật, còn phương án ghi chép bằng `localStorage` chỉ là ảo ảnh — xoá cache trình duyệt là danh sách biến mất trong khi index vẫn nguyên, và index do người khác nạp thì không bao giờ hiện ra. Ghi ở DEC-4.

Đổi lại: P1 không còn là "thuần frontend". Phase này phải đi qua đủ 5 tầng của kiến trúc (`validate.py` → `adaptor/protocols.py` → `retrieval/vector_search.py` → `orchestrator.py` → `api/routes.py`), đúng theo lớp lang mà `docs/ARCHITECTURE.md` mô tả. Không đi tắt.

Phụ thuộc: phase 1 (môi trường test). Độc lập với phase 2 và 3 về file, nhưng xếp sau để giữ thứ tự tuyến tính.

## Files

- **Modify** `src/rag_chatbot_tung/validate.py` — thêm `DocumentSummary`, `DocumentList`.
- **Modify** `src/rag_chatbot_tung/adaptor/protocols.py` — thêm `list_sources()` vào `VectorStore` Protocol.
- **Modify** `src/rag_chatbot_tung/retrieval/vector_search.py` — cài `list_sources()` trong `QdrantVectorStore`.
- **Modify** `src/rag_chatbot_tung/orchestrator.py` — thêm `list_documents()`.
- **Modify** `src/rag_chatbot_tung/api/routes.py` — thêm route `GET /documents`.
- **Modify** `tests/test_vector_search.py`, `tests/test_api.py` — test cho tầng store và tầng HTTP.

Thêm method vào `VectorStore` Protocol là thay đổi có sức lan: mọi implementation phải có nó. Đã kiểm: hiện chỉ có **một** implementation là `QdrantVectorStore`, và `tests/conftest.py` dùng chính lớp đó với `QdrantClient(":memory:")` (`tests/conftest.py:69-73`) chứ không có fake vector store nào. Nên không có lớp giả nào phải cập nhật theo.

## Hợp đồng

```
GET /documents  →  {documents: [{source, source_type, chunks, title}], total}
```

Model mới trong `validate.py`, đặt cạnh `CollectionInfo`:

```python
class DocumentSummary(BaseModel):
    source: str
    source_type: SourceType
    chunks: int
    title: str | None = None


class DocumentList(BaseModel):
    documents: list[DocumentSummary]
    total: int
```

`total` là số **nguồn**, không phải số chunk — `points_count` ở `/collections` mới là số chunk (`validate.py:87-90`). Hai con số này khác nhau và rất dễ nhầm; đặt tên và ghi docstring cho rõ.

Đường dẫn `/documents` đã có method `DELETE` (`api/routes.py:78-82`). Thêm `GET` lên cùng path là đúng lẽ REST, không phải trùng lặp.

## Cách cài `list_sources()`

Dùng `client.scroll()` gom `payload["source"]` rồi gộp trong Python:

```python
def list_sources(self) -> list[DocumentSummary]:
    counts: dict[str, dict] = {}
    offset = None
    while True:
        points, offset = self._client.scroll(
            collection_name=self.collection,
            limit=256,
            offset=offset,
            with_payload=["source", "source_type", "title"],
            with_vectors=False,
        )
        for p in points:
            ...  # gom theo source, đếm chunk, giữ title đầu tiên gặp
        if offset is None:
            break
```

**Vì sao là `scroll` chứ không phải `facet`**: `qdrant-client` đang khoá ở `1.19.0` (`uv.lock:2497-2498`) nên API `facet` có tồn tại, và về lý thuyết nó trả distinct + count nhanh hơn hẳn nhờ payload index trên `source` đã được tạo sẵn (`retrieval/vector_search.py:34-38`). Nhưng test chạy trên chế độ local `QdrantClient(":memory:")`, và **tôi chưa xác minh được chế độ local có cài `facet` hay không** — máy này chưa dựng được môi trường Python. `[ASSUMED]` cho cả hai chiều, nên chọn `scroll`: nó chắc chắn chạy ở cả local lẫn server, và cả `upsert`/`delete`/`query_points` hiện có đều đã dựa vào chế độ local này.

Giới hạn phải nói thẳng: `scroll` duyệt toàn bộ điểm, tức là O(số chunk). Với vài nghìn chunk thì không ai thấy gì; với vài trăm nghìn thì endpoint này sẽ chậm. Điều kiện để đổi sang `facet` (làm sau, không phải bây giờ): khi `points_count` vượt khoảng 50.000 **và** đã đo được độ trễ thật, chứ không phải khi thấy `scroll` xấu.

`with_vectors=False` là bắt buộc — thiếu nó thì mỗi lần liệt kê sẽ kéo về toàn bộ vector 1536 chiều của cả collection.

## TDD

**Tests-before (RED)** — 4 test, viết trước khi có code:

Trong `tests/test_vector_search.py`:

1. `test_list_sources_empty` — collection rỗng trả danh sách rỗng.
2. `test_list_sources_groups_by_source` — nạp 2 nguồn với số chunk khác nhau, khẳng định đúng số nguồn và đúng `chunks` từng nguồn.
3. `test_list_sources_after_delete` — xoá một nguồn bằng `delete_by_source` thì nguồn đó biến mất khỏi danh sách. Test này khoá đúng chỗ dễ hỏng nhất: hai đường đọc và xoá phải nhất quán.

Trong `tests/test_api.py`:

4. `test_get_documents` — ingest rồi `GET /documents` trả 200, `total` khớp số nguồn, và mỗi phần tử có đủ `source`/`chunks`.

**Implement** → xanh, theo đúng thứ tự tầng: model → protocol → store → orchestrator → route.

**Regression**: `uv run pytest` (52 + 4 = 56), ruff, black, mypy. Chú ý `mypy` sẽ bắt ngay nếu `QdrantVectorStore` không khớp `VectorStore` Protocol sau khi thêm method.

## Success

- [ ] 4 test mới xanh, tổng 56 test.
- [ ] `GET /documents` xuất hiện trong `/docs` (OpenAPI) với response model đúng.
- [ ] `mypy src` sạch — đặc biệt là `QdrantVectorStore` vẫn thoả `VectorStore`.
- [ ] Không endpoint cũ nào đổi hành vi; 45 test mốc vẫn xanh không phải sửa.
- [ ] Danh sách trả về sau khi ingest 2 file khớp đúng những gì `/collections` đếm được (tổng `chunks` bằng `points_count`).

## Risks

- **`scroll` phân trang sai** → lặp vô hạn hoặc mất dữ liệu. Vòng lặp phải dừng khi `offset` trả về `None`. Test số 2 nên nạp đủ điểm để vượt `limit=256` ít nhất một lần, nếu không nhánh phân trang không bao giờ được chạy — một test xanh giả.
- **Chế độ local của Qdrant lệch hành vi so với server thật.** Test chạy `:memory:`, production chạy Qdrant thật. Chữ ký `scroll` giống nhau nhưng thứ tự trả về có thể khác. Đừng viết test phụ thuộc vào thứ tự; sắp xếp danh sách theo `source` trước khi trả về để kết quả tất định.
- **Payload thiếu khoá.** Điểm cũ được ingest trước khi có phase này vẫn có `source` (pipeline luôn ghi), nhưng `title` có thể `None`. Dùng `.get()` với mặc định, đừng truy cập thẳng.
- **Phình phạm vi.** Cám dỗ tiếp theo sẽ là thêm phân trang, lọc, sắp xếp cho endpoint này. Không. P1 trả toàn bộ danh sách, hết.
