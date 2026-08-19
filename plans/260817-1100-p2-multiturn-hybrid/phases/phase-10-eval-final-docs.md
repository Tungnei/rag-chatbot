---
phase: 10
title: "Eval Final Docs"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 10 — Eval tổng kết + tài liệu

## Overview

Chạy eval đầy đủ, lập bảng đóng góp từng tầng, và đồng bộ tài liệu với hệ thống thật.

Bảng đó là thứ trả lời được câu hỏi *"2GB image có đáng không"* bằng **số** thay vì bằng cảm giác. Nếu phase này bị cắt, plan kết thúc với ba tầng mới và không ai biết tầng nào đóng góp gì — tức là mất đúng cái lý do phase 2 tồn tại.

Toàn bộ phase này **chạy được là nhờ công tắc**. Bốn cấu hình trong bảng khác nhau đúng ba biến môi trường; không có công tắc thì mỗi dòng đòi một lần `git checkout` và một lần re-ingest.

Phụ thuộc: phase 9.

## Files

- **Modify** `docs/ARCHITECTURE.md` — sơ đồ request flow (dòng 3-26), bảng module (dòng 51-67), "Grounding strategy" (dòng 89-96).
- **Modify** `docs/system-architecture.md` — "Luồng query (rút gọn)" (dòng 41-46), thêm mục về tầng retrieval mới.
- **Modify** `docs/PROJECT_STRUCTURE.md` — cây thư mục (`rerank/`, `retrieval/sparse.py`, `retrieval/metadata_adjust.py`) và con số test.
- **Modify** `docs/QUICK_REFERENCE.md` — lệnh eval, biến công tắc, lệnh migrate.
- **Modify** `docs/SETUP.md` — build target `runtime-rerank`, extra `rerank`.
- **Modify** `docs/code-standards.md` — **chỉ** con số baseline test (dòng 17).
- **Modify** `README.md` — mô tả đường truy vấn, payload `/query`.
- **Modify** `docs/decisions.md` — qua `decision_register.py`, DEC kết luận cho phần B.

Không đụng `src/`, không đụng `tests/`.

**Về `docs/code-standards.md`:** file này là chuẩn dùng chung, không phải bãi ghi chú của plan. Phạm vi sửa **chỉ** là con số baseline `pytest -q` ở dòng 17 — một số liệu đã đo, không phải một chuẩn mới. Không thêm mục nào, không đặt chuẩn nào ở đây (`docs/code-standards.md:110-115` nói rõ: chuẩn mới phải qua DEC).

## Bảng đóng góp từng tầng

Mỗi dòng là một lần chạy `scripts/run_eval.py` trên cùng bộ `data/eval/qa.jsonl`, khác nhau đúng ba biến:

| Cấu hình | `RETRIEVER__HYBRID` | `RERANK__PROVIDER` | `METADATA_ADJUST__ENABLED` |
|---|---|---|---|
| Baseline (dense) | `false` | `noop` | `false` |
| + fusion | `true` | `noop` | `false` |
| + rerank | `true` | `cross_encoder` | `false` |
| + metadata | `true` | `cross_encoder` | `true` |

Bảng kết quả — **ô trống được điền bằng số đo, không bằng ước lượng**:

| Cấu hình | Hit-rate | MRR | p95 latency | Image size |
|---|---|---|---|---|
| Baseline (dense) | | | | |
| + fusion | | | | |
| + rerank | | | | |
| + metadata | | | | |

Ràng buộc để bảng có nghĩa:

- **Cùng một bộ eval, cùng một collection, cùng một lần ingest.** Đổi dữ liệu giữa các dòng là làm bảng thành vô nghĩa mà vẫn trông đầy đủ.
- **`--out` cho mỗi dòng**, để so từng case chứ không chỉ so tổng.
- **p95 latency đo end-to-end** qua `/query`, không chỉ đo phần retrieval — người dùng cảm nhận cả đường.
- **Image size**: `runtime` cho ba dòng đầu, `runtime-rerank` cho hai dòng cuối. Hai dòng đầu phải cho **cùng một con số** — khác nhau nghĩa là optional dependency đã rò rỉ vào target mặc định.
- **Ghi cả số case**: một bảng đẹp trên 6 case vẫn vô nghĩa. Ghi `n=<số case>` cạnh bảng.
- **H3 — ép `--top-k` tường minh và GIỐNG NHAU cho cả bốn dòng, ghi `k=<giá trị>` cạnh `n=`.** `metrics.py:45` lấy `k = top_k or settings.retriever.top_k`, mà phase 9 đã đổi mặc định 3→5. Cả bốn dòng chạy sau phase 9 nên đều lấy `k=5`, trong khi baseline ghi ở `verification-P2.json` và các mốc so của phase 5/6/7 đều đo ở `k=3`. Hit-rate@5 ≥ hit-rate@3 theo định nghĩa (tập kết quả là tập cha), nên dòng "Baseline (dense)" sẽ **cao hơn** baseline phase 2 mà không tầng nào đóng góp — và phần đóng góp của fusion/rerank bị nén lại tương ứng. Plan đã cẩn thận ràng buộc "cùng bộ eval, cùng collection, cùng lần ingest" nhưng thiếu đúng "cùng `top_k`".

Cộng thêm, và đây là phần con số tổng không nói được: với mỗi bước, **liệt kê theo tên** các case chuyển hit→miss và miss→hit. Một tầng cải thiện tổng 5 điểm phần trăm trong khi làm hỏng 4 case là thông tin hoàn toàn khác với một tầng cải thiện 5 điểm mà không làm hỏng gì.

## DEC kết luận

Ghi qua `decision_register.py --append-alloc`, nội dung tối thiểu:

- Bảng số thật (hit-rate, MRR, p95, image size, n).
- Mỗi tầng: **giữ bật hay để tắt mặc định**, kèm lý do bằng số.
- Nếu một tầng không chứng minh được giá trị: nói thẳng, và để mặc định `false`. Ship một tầng vô dụng ở trạng thái bật là trả chi phí vĩnh viễn cho một cải thiện không tồn tại.
- Ngưỡng để xét lại: điều gì phải thay đổi thì mới bật/tắt lại tầng đó (theo khuôn mẫu DEC-4 đã dùng cho facet API — *"`points_count` vượt khoảng 50000 VÀ đã đo được độ trễ thật"*).

Kết luận "tầng X không đáng" là một kết quả **hợp lệ và có giá trị**. Nó đóng lại một câu hỏi bằng bằng chứng, thay vì để nó quay lại sau sáu tháng.

## Tài liệu — những câu đang sai

| Vị trí | Đang nói | Sự thật sau phase 9 |
|---|---|---|
| `docs/ARCHITECTURE.md:3-26` | sơ đồ: embed → search → build messages → LLM | thêm sparse, fusion, rerank, metadata, history |
| `docs/ARCHITECTURE.md:14-16` | *"top_k nearest chunks above score_threshold"* | ngưỡng nằm trong prefetch dense, không áp sau fusion |
| `docs/ARCHITECTURE.md:51-67` | bảng module thiếu `rerank/` | thêm `rerank/`, `retrieval/sparse.py`, `retrieval/metadata_adjust.py` |
| `docs/ARCHITECTURE.md:58` | *"adaptor/ định nghĩa ba Protocol"* | bốn (thêm `Reranker`) |
| `docs/ARCHITECTURE.md:95` | *"`retriever.score_threshold` drops weak matches before they reach the model"* | vẫn đúng nhưng chỗ áp đã đổi — phải nói rõ |
| `docs/system-architecture.md:16-17` | *"ba `typing.Protocol`"* | bốn |
| `docs/system-architecture.md:41-46` | luồng query cũ | luồng mới |
| `docs/PROJECT_STRUCTURE.md:43` | *"45 tests, fully offline"* | ≈121 [OBSERVED: hôm nay đã là 78, con số này đã sai từ trước plan] |
| `docs/code-standards.md:17` | *"78 passed"* | con số cuối |
| `README.md` | payload `/query`, mô tả retrieval | có `history`, có hybrid |
| `docs/QUICK_REFERENCE.md:12-25` | bảng lệnh | thêm `migrate_collection.py`, biến công tắc |

**Phải giữ nguyên, đừng "dọn dẹp":**

- Tính chất "toàn bộ suite chạy offline" (`docs/ARCHITECTURE.md:85-87`) — vẫn đúng và vẫn là ràng buộc.
- DEC-4 về `scroll` thay vì facet (`docs/system-architecture.md:74-79`) — plan này không đụng `list_sources`.
- DEC-5 về embeddings tách riêng (`docs/system-architecture.md:27-33`) — không đổi.
- Cảnh báo bảo mật DEC-3 (`docs/system-architecture.md:66-72`) — P3 vẫn chưa làm, cảnh báo vẫn đúng.

**Một điểm dễ sót**: sau phase 8, `score` trong `sources[]` là điểm cross-encoder chứ không phải cosine, trong khi UI vẫn hiển thị nó với 3 chữ số thập phân như cũ (`app.js:140`). Một con số đổi ý nghĩa mà không đổi hình dạng là kiểu thay đổi làm người ta mất buổi chiều. Phải ghi vào `README.md` và `docs/ARCHITECTURE.md`.

## TDD

Không có code sản phẩm nên không có vòng đỏ→xanh. Ghi `tdd-red: N/A` kèm lý do.

**Regression gate** vẫn chạy đủ bốn cổng:

```
uv run pytest -q                 → ≈121 passed, không giảm
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

## Success

**Đo bằng máy:**

- [ ] Bốn cổng sạch, test không giảm.
- [ ] `grep -n "ba \`typing.Protocol\`\|three \`Protocol\`" docs/` → rỗng.
- [ ] `grep -n "45 tests" docs/PROJECT_STRUCTURE.md` → rỗng.
- [ ] `docs/code-standards.md:17` mang con số test cuối cùng.
- [ ] Sơ đồ trong `docs/ARCHITECTURE.md` có đủ 4 tầng của phần B cộng history.
- [ ] `docs/decisions.md` có DEC kết luận, ghi qua script.

**Cần hạ tầng thật (R12):**

- [ ] Bốn lần chạy eval hoàn tất, bốn file `--out` tồn tại.
- [ ] Bảng 4 dòng × 4 cột **đầy số thật** trong `artifacts/verification-P10.json`, kèm `n=<số case>`.
- [ ] Với mỗi bước, danh sách case đổi chỗ **theo tên**.
- [ ] Hai con số image size đo bằng `docker image ls`, ghi nguyên văn.
- [ ] p95 latency đo cho cả `runtime` lẫn `runtime-rerank`.
- [ ] Nghiệm thu tay cuối: hỏi 3 câu qua `/ui` với hội thoại nhiều lượt, cấu hình đầy đủ (hybrid + rerank + metadata) → câu trả lời đúng, trích dẫn bấm được, ≤5 nguồn, ≤2 nguồn mỗi tài liệu, chỉ báo lượt đúng.

**Cổng của phase:** bảng đầy số, DEC được ghi. Một ô trống trong bảng là phase chưa xong — và điền nó bằng ước lượng thì tệ hơn để trống, vì một ô trống trung thực còn một con số bịa thì sẽ được ai đó trích dẫn lại.

## Risks

- **Cám dỗ điền bảng bằng ước lượng.** Rủi ro cao nhất của phase, và cũng là rủi ro làm hỏng giá trị của cả plan. Mỗi lần chạy eval tốn tiền và thời gian, và bốn dòng nghĩa là bốn lần. Chống lại: DEC-7 nói thẳng *"khả năng của hạ tầng phải ĐO chứ không suy ra"*, và Success có một dòng cấm ô trống được lấp bằng số bịa.
- **Bảng cho thấy phần B không đáng.** Kết quả hoàn toàn có thể xảy ra, và nếu xảy ra thì đó là **thành công của phase 2**, không phải thất bại của plan — nó có nghĩa là hệ thống đo đã hoạt động đúng chức năng. Xử: DEC ghi thẳng, mặc định để `false`, và code vẫn nằm đó sau một công tắc để bật lại khi bộ tài liệu lớn hơn. Đừng viết lại lịch sử để plan trông thành công.
- **Tài liệu sửa bằng tay thì sót.** `docs/PROJECT_STRUCTURE.md:43` ghi *"45 tests"* trong khi thực tế đã là 78 từ trước plan này [OBSERVED] — bằng chứng sống. Xử: mỗi dòng trong bảng "những câu đang sai" là một checkbox riêng, và Success có vài lệnh `grep` cụ thể thay vì một lời hứa "đã rà".
- **Sửa quá tay vào `docs/code-standards.md`.** File này là chuẩn dùng chung. Phạm vi đã ghi rõ: chỉ dòng 17. Thêm một mục "chuẩn về hybrid retrieval" ở đây là đặt ra chuẩn mới mà không qua DEC, trái chính điều file đó nói ở dòng 110-115.
- **Bốn dòng bảng chạy trên bốn trạng thái dữ liệu khác nhau.** Nếu ai đó re-ingest giữa chừng, bảng vẫn trông đầy đủ và vẫn hoàn toàn vô nghĩa. Xử: ghi `points_count` cạnh mỗi dòng — bốn con số phải giống hệt nhau, và đó là kiểm chứng rẻ nhất cho việc bốn lần chạy thật sự so sánh được với nhau.
</content>
