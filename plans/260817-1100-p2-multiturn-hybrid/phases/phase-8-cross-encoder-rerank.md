---
phase: 8
title: "Cross Encoder Rerank"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 8 — Cross-encoder Rerank

## Overview

Tầng thứ ba của sơ đồ: `RRF fusion top30 → cross-encoder top10`.

Cross-encoder đọc **cặp (câu hỏi, đoạn văn)** cùng lúc thay vì so hai vector đã mã hoá độc lập, nên nó bắt được liên quan mà cả dense lẫn BM25 đều bỏ sót. Đây cũng là tầng dọn dẹp thứ rác mà phase 7 để lại: prefetch sparse không có ngưỡng nên top-30 luôn chứa vài kết quả khớp rất yếu.

**Đây là dependency nặng duy nhất của cả plan.** `torch` và `sentence_transformers` đều chưa có trong `.venv` [OBSERVED]. Repo tới giờ giữ được sự gọn nhẹ một cách có chủ ý — DEC-1 loại Gradio và React cũng chính vì lý do đó. Người dùng đã chọn hướng này nên phase triển khai đúng như vậy, nhưng triển khai theo cách để cái giá **chỉ phải trả bởi người bật nó**.

`NoopReranker` là mặc định và là thứ test dùng. Bộ test **phải chạy offline không tải model** — đó là tính chất cốt lõi ở `docs/ARCHITECTURE.md:85-87` và `docs/code-standards.md:67-73`, và nó không có ngoại lệ cho phase này.

Phụ thuộc: phase 7.

## Files

- **Modify** `src/rag_chatbot/adaptor/protocols.py` — thêm `Reranker` Protocol.
- **Create** `src/rag_chatbot/rerank/__init__.py`, `noop.py`, `cross_encoder.py`.
- **Modify** `src/rag_chatbot/providers.py` — `build_reranker`.
- **Modify** `src/rag_chatbot/configs.py`, `configs/default.yaml` — `RerankSettings`.
- **Modify** `src/rag_chatbot/orchestrator.py` — chèn rerank vào `answer()`.
- **Modify** `pyproject.toml` — optional dependency group.
- **Modify** `Dockerfile` — target riêng.
- **Create** `tests/test_rerank.py`.
- **Modify** `tests/test_providers.py` — nhánh `build_reranker`.
- **Modify** `src/rag_chatbot/evaluate/metrics.py` — **B1**: chuyển `evaluate_retrieval` từ `orchestrator.vector_store.search(...)` (`metrics.py:50-53`) sang `orchestrator.retrieve(...)`. Không có dòng này thì cả phase 8 lẫn phase 9 không bao giờ được đo.
- **Modify** `tests/conftest.py` — **H4**: fixture autouse đặt `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1`.

## Protocol

```python
@runtime_checkable
class Reranker(Protocol):
    def rerank(
        self, query: str, chunks: list[RetrievedChunk], top_n: int
    ) -> list[RetrievedChunk]: ...
```

Đây là Protocol thứ tư, cùng chỗ với ba cái đang có (`protocols.py:23-58`). `RAGOrchestrator.__init__` (`orchestrator.py:33-46`) nhận nó qua constructor injection như ba cái kia, mặc định `None` → `build_reranker(settings)`. **Orchestrator không bao giờ import class cụ thể** (`docs/system-architecture.md:19-25`) — `providers.py` là nơi duy nhất ánh xạ giá trị `provider` sang class (`providers.py:1-6`).

`rerank` trả `list[RetrievedChunk]` chứ không trả điểm số riêng: `RetrievedChunk.score` đã có sẵn (`validate.py:28-35`) và reranker ghi đè nó. Hệ quả cần biết: sau rerank, `score` trong `sources[]` trả về UI là **điểm cross-encoder**, không phải cosine. Panel nguồn ở `/ui` hiển thị `Number(source.score).toFixed(3)` (`app.js:140`) và sẽ hiện một thang khác. Không phá gì, nhưng phải ghi vào tài liệu ở phase 10 — con số trên màn hình đổi ý nghĩa mà không đổi hình dạng là kiểu thay đổi làm người ta mất buổi chiều.

## `NoopReranker`

```python
class NoopReranker:
    """Keeps the fusion order and cuts to top_n."""

    def rerank(self, query, chunks, top_n):
        return chunks[:top_n]
```

Mặc định, và là thứ mọi test dùng. Không import gì ngoài stdlib.

## `CrossEncoderReranker`

```python
class CrossEncoderReranker:
    def __init__(self, settings: RerankSettings) -> None:
        # Imported here, not at module scope: importing this package must not drag in
        # torch. The whole test suite runs offline and must keep doing so even after a
        # ~2GB dependency exists somewhere in the tree.
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(settings.model, device=settings.device)
```

**Import trễ là ràng buộc kiến trúc, không phải mẹo vặt.** Nếu `from sentence_transformers import CrossEncoder` nằm ở đầu module, thì `rerank/__init__.py` re-export sẽ kéo `torch` vào mọi lần chạy `pytest`, và tính chất "suite chạy offline" chết lặng lẽ. Có một test khẳng định điều này (test 5).

## Quyết định phải chốt: model nằm ở đâu?

Sơ đồ có tầng này nhưng chưa nói model được nạp thế nào. Phải chốt trong phase, vì hai lựa chọn hỏng theo hai kiểu hoàn toàn khác nhau.

**Phương án A — nướng vào image lúc build.**

- ✔ Container khởi động là chạy được, không phụ thuộc mạng. Chạy được trong môi trường air-gapped.
- ✔ Cái giá là **một con số build-time nhìn thấy được** (`docker image ls`), phát hiện ngay lúc build.
- ✘ Image phình thêm dung lượng model (~90MB cho `ms-marco-MiniLM-L-6-v2` `[PRIOR]` — phải đo, không tin con số này).
- ✘ Đổi model = build lại image.

**Phương án B — tải lúc runtime.**

- ✔ Image nhỏ hơn.
- ✘ Lần khởi động đầu cần internet. **Hỏng hẳn trong môi trường air-gapped.**
- ✘ Biến một lỗi build-time thành một lỗi runtime khó chẩn đoán: container "khởi động chậm" hoá ra đang tải 90MB qua một mạng chặn HuggingFace.
- ✘ `/health` (`orchestrator.py:113-121`) trở thành phụ thuộc mạng, hoặc phải nói dối trong lúc model chưa sẵn sàng.

**Chốt: phương án A.** Lý do quyết định không phải dung lượng mà là **kiểu lỗi**: A biến một sự cố runtime khó chẩn đoán thành một con số nhìn thấy lúc build. Đây cũng là logic đã dùng cho R3 ở phase 6 — thà nổ ồn ào lúc khởi động còn hơn sai âm thầm lúc chạy.

## Cái giá chỉ trả bởi người bật nó

`sentence-transformers` là **optional dependency**, không phải dependency thường:

```toml
[project.optional-dependencies]
rerank = ["sentence-transformers>=3.0"]
```

`Dockerfile` có target riêng chứ không sửa target `runtime` đang có (`Dockerfile:22-41`):

- `runtime` — **không đổi một dòng**. `RERANK__PROVIDER=noop`, không có `torch`, dung lượng y như trước.
- `runtime-rerank` — `uv sync --frozen --no-dev --extra rerank`, cộng một bước nướng model vào cache (đặt `HF_HOME` rồi `COPY --from=builder` cache đó sang).

Hệ quả: câu hỏi "2GB có đáng không" trở thành câu hỏi mà **người vận hành trả lời khi chọn image**, chứ không phải cái giá mọi người phải trả vì một tính năng mặc định tắt. Đây cũng là cách R7 được giảm nhẹ ở mức kiến trúc thay vì mức lời hứa.

**Lối lùi:** nếu image size không chấp nhận được khi nhìn thấy số thật, `Reranker` là Protocol nên `CohereReranker` thay vào chỉ là một class mới + một nhánh trong `providers.py` — orchestrator, API, test đều không đổi. Đúng lý do tầng adaptor tồn tại (`docs/system-architecture.md:14-25`). Plan này **không** đi đường đó (người dùng chốt cross-encoder local), chỉ ghi lại rằng cửa vẫn mở.

## Config

```yaml
retriever:
  # New here, not in phase 7: how many fused candidates are handed to the reranker.
  # Kept separate from top_k on purpose — top_k means "chunks the LLM gets" and must
  # keep meaning exactly that.
  fusion_limit: 30

rerank:
  # noop keeps the fusion order and costs nothing; cross_encoder needs the `rerank`
  # extra and a much larger image.
  provider: noop          # noop | cross_encoder
  model: cross-encoder/ms-marco-MiniLM-L-6-v2
  device: cpu
  top_n: 10
```

`RerankSettings(BaseModel)` với `provider: Literal["noop", "cross_encoder"] = "noop"` — cùng khuôn với `LLMSettings.provider` (`configs.py:41`) và `EmbeddingSettings.provider` (`configs.py:32`).

`top_n: 10` khớp sơ đồ (top30 → top10).

## Chèn vào `answer()`

`top_k` hiệu lực vẫn tính như hôm nay (`orchestrator.py:53`): `request.top_k or settings.retriever.top_k`, và vẫn có đúng một nghĩa — **số chunk LLM nhận được**.

**B1 — tách `retrieve()` ra khỏi `answer()`. Đây là thay đổi cấu trúc bắt buộc của phase này, không phải dọn dẹp tuỳ chọn.**

Lý do: `evaluate_retrieval` gọi **thẳng** `orchestrator.vector_store.search(...)` (`metrics.py:50-53`), không đi qua `answer()`. Nếu rerank chỉ được chèn vào `answer()`, thì `run_eval.py` không bao giờ chạy qua nó — `rerank.json` sẽ giống byte-for-byte `fusion.json`, và bảng của phase 10 in cùng một con số ba lần. DEC kết luận của phase 10 khi đó sẽ ghi "cross-encoder không chứng minh được giá trị" dựa trên một phép đo chưa từng gọi cross-encoder.

Chính `phase-2` đã lập luận đúng chỗ này (*"nhét bốn đường ống song song vào `evaluate_retrieval` là dựng một bản sao của orchestrator bên trong module đo"*) — bản sao đó **đã tồn tại**: `metrics.py:50-53` lặp lại `orchestrator.py:55-59`. Phase này đóng nó lại.

```python
def retrieve(self, question: str, top_k: int) -> list[RetrievedChunk]:
    """Đường truy xuất DUY NHẤT. answer() và evaluate_retrieval() cùng gọi hàm này."""
    # Fan out only when there is a reranker to consume the extra candidates; with the
    # default NoopReranker this stays exactly the phase-7 behaviour.
    fan_out = self.settings.retriever.fusion_limit if self._reranks else top_k
    chunks = self.vector_store.search(..., top_k=fan_out, query_text=question)
    if not chunks:
        return []
    chunks = self.reranker.rerank(question, chunks, self._effective_top_n(top_k))
    return chunks[:top_k]                # <-- phase 9 THAY THẾ đúng dòng này

def answer(self, request):
    top_k = request.top_k or self.settings.retriever.top_k
    chunks = self.retrieve(request.question, top_k)
    if not chunks: ...                   # NO_CONTEXT_ANSWER, giữ nguyên (orchestrator.py:61-67)
```

`retrieve()` **không** gọi LLM — đó là chủ ý: `evaluate_retrieval` chạy 40 case × 4 cấu hình, đi qua `answer()` là tiền thật không cần tiêu.

`evaluate/metrics.py` PHẢI đổi trong phase này để gọi `orchestrator.retrieve(case.question, k)` thay cho `orchestrator.vector_store.search(...)`. Nó nằm trong `files_to_modify` của cả P8 lẫn P9 vì lý do đó.

Rerank chạy **sau** kiểm tra rỗng. Không đảo: gọi model trên danh sách rỗng là tốn thời gian để nhận lại danh sách rỗng, và nó phá lớp chống bịa mà `docs/ARCHITECTURE.md:93-96` mô tả.

**H5 — `_reranks` phải nhận cả reranker được inject qua constructor.**

Định nghĩa ngây thơ `settings.rerank.provider != "noop"` sai trong đúng trường hợp mà mục "Lối lùi" của phase này hứa là sẽ chạy: `RAGOrchestrator(settings, reranker=CohereReranker())` với `settings.rerank.provider` còn là `"noop"` → `fan_out = top_k = 5` → reranker nhận 5 ứng viên và xếp lại 5 thành 5. Toàn bộ giá trị của rerank (chọn 10 tốt nhất từ 30) biến mất **im lặng**, và test 6/8 vẫn xanh vì chúng chỉ kiểm "có được gọi không", không kiểm số ứng viên.

```python
self._reranks = reranker is not None or settings.rerank.provider != "noop"
```

Vẫn không `isinstance` một class cụ thể nên không phá quy tắc ở `docs/system-architecture.md:19-25`.

**H5b — `top_n` không được nhỏ hơn `top_k`.** `validate.py:58` cho `top_k` tới `le=20` nhưng `rerank.top_n: 10` chặn cứng ở 10: người dùng kéo slider lên 20 sẽ nhận về 10 nguồn, im lặng. `_effective_top_n(top_k) = max(settings.rerank.top_n, top_k)`.

## TDD

**Tests-before (RED)** — `tests/test_rerank.py`:

1. `test_noop_preserves_order_and_cuts` — 5 chunk, `top_n=3` → đúng 3 chunk đầu, thứ tự nguyên.
2. `test_noop_handles_fewer_chunks_than_top_n` — 2 chunk, `top_n=10` → 2 chunk, không lỗi.
3. `test_noop_handles_empty_list` — `[]` → `[]`.
4. `test_noop_satisfies_the_protocol` — `isinstance(NoopReranker(), Reranker)`. `@runtime_checkable` làm được điều này (`protocols.py:23,35,54`).
5. **`test_importing_rerank_package_does_not_import_torch`** — test giữ tính chất offline:

   ```python
   out = subprocess.run(
       [sys.executable, "-c",
        "import sys; import rag_chatbot.rerank; "
        "print('torch' in sys.modules, 'sentence_transformers' in sys.modules)"],
       capture_output=True, text=True, check=True,
   )
   assert out.stdout.strip() == "False False"
   ```

   Chạy trong **subprocess sạch**, không phải kiểm `sys.modules` trong tiến trình test — tiến trình test đã import cả trăm thứ và kết quả sẽ phụ thuộc vào thứ tự chạy test. Đây đúng là kiểu "xanh giả vì test không thật sự chạy qua nhánh cần kiểm" ở `docs/code-standards.md:84-87`.
   *Đỏ vì:* package chưa tồn tại → `ModuleNotFoundError`. Đây là **đỏ vì import**, tức là đỏ vì lý do yếu. Chấp nhận cho test này vì bản chất nó là test về import; nhưng phải chạy lại nó **sau khi** package tồn tại với một import module-scope cố ý sai, để thấy nó thật sự bắt được. Ghi kết quả cả hai lần vào `tdd-red`.

6. `test_orchestrator_applies_reranker` — orchestrator với một reranker giả ghi lại lời gọi (định nghĩa trong chính file test, không đưa vào `conftest.py` — chỉ một file test dùng nó). Khẳng định `rerank` được gọi đúng một lần với `query == request.question` và `top_n == settings.rerank.top_n`.
7. `test_reranker_not_called_when_no_chunks` — không có tài liệu nào → `NO_CONTEXT_ANSWER` và reranker **không** được gọi. Đây là thứ tự ở mục trên, thành test.
8. `test_reranker_output_flows_into_sources` — reranker giả đảo ngược thứ tự → `response.sources` theo đúng thứ tự đã đảo. Chứng minh rerank thật sự điều khiển cái LLM thấy và cái người dùng thấy, chứ không phải chạy rồi bị bỏ qua.

*`tests/test_providers.py`*

9. `test_build_reranker_defaults_to_noop` — `build_reranker(settings)` trả `NoopReranker`.
10. `test_build_reranker_cross_encoder_without_extra_raises_clearly` — `provider="cross_encoder"` khi `sentence_transformers` chưa cài → lỗi **nêu tên extra cần cài** (`uv sync --extra rerank`), không phải `ModuleNotFoundError` trần. Cùng tinh thần với `_require` (`providers.py:18-25`): *"Name the variable: 'authentication error' from the provider three calls later is a much worse way to learn the key was never set."*

    **H4 — test này PHẢI tự dựng điều kiện của nó, không được dựa vào việc máy chưa cài extra.** Trên một máy đã chạy `uv sync --extra rerank`, `build_reranker` sẽ đi vào nhánh thật → `CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")` → **tải ~90MB từ HuggingFace trong lúc chạy pytest**. Vi phạm thẳng `docs/code-standards.md:67-73` (*"Không test nào được gọi mạng thật"*) và acceptance của chính plan này. Trên máy thiếu root CA Vingroup (đúng chướng ngại đã ghi ở phase 1) nó không tải được mà treo tới timeout.

    Viết: `monkeypatch.setitem(sys.modules, "sentence_transformers", None)` rồi mới gọi `build_reranker` → tất định trên mọi máy, không phụ thuộc trạng thái `.venv`.

11. **Fixture chặn mạng (autouse, thêm vào `tests/conftest.py`)** — đặt `HF_HUB_OFFLINE=1` và `TRANSFORMERS_OFFLINE=1` cho toàn bộ suite. Đây là lưới thứ hai: nếu sau này ai đó lỡ tay dựng một `CrossEncoder` thật trong test, nó **nổ ngay** thay vì lặng lẽ tải model. `NoopReranker` mặc định chỉ chặn các test *khác*; nó không chặn một test cố tình dựng `cross_encoder`.

**Không có test nào nạp model thật.** `CrossEncoderReranker` chỉ được kiểm qua đường "chưa cài thì báo lỗi rõ ràng". Hành vi thật của nó nghiệm thu bằng tay ở mục Success. Nói thẳng giới hạn này, đừng để ai đọc "10 test rerank xanh" rồi tưởng cross-encoder đã được kiểm.

**Implement** → xanh: `protocols.py` → `rerank/` → `providers.py` → config → `orchestrator.py` → `pyproject.toml` + `Dockerfile`.

**Regression gate:**

```
uv run pytest -q                 → ≈114 passed, không giảm
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

## Success

**Đo bằng máy:**

- [ ] 10 test mới xanh, tổng không giảm.
- [ ] Bốn cổng sạch.
- [ ] Suite chạy **không có** `torch`/`sentence_transformers` trong `.venv` — tức là `uv sync` mặc định (không `--extra rerank`) vẫn cho suite xanh đủ.
- [ ] `grep -rn "^from sentence_transformers\|^import torch" src/` → rỗng (mọi import nặng đều nằm trong hàm).
- [ ] `rerank.provider` mặc định `noop`.
- [ ] `grep -rn "import" src/rag_chatbot/orchestrator.py | grep -i "rerank\."` → chỉ import Protocol, không import class cụ thể.

**Cần hạ tầng thật (R12) — đây là phần R7 được trả lời bằng số:**

- [ ] `docker build --target runtime` → **đo `docker image ls`**. Con số này phải **bằng con số trước phase 8**. Nếu nó tăng thì optional dependency đã rò rỉ vào target mặc định.
- [ ] `docker build --target runtime-rerank` → **đo `docker image ls`**. Ghi con số thật vào verification.
- [ ] Con số "~200MB → ~2GB" trong bản nháp **chưa từng được đo trong repo này** — `[ASSUMED]`. Verification ghi số thật, không chép lại ước lượng.
- [ ] `RERANK__PROVIDER=cross_encoder uv run python scripts/run_eval.py --out data/eval/rerank.json --baseline data/eval/fusion.json`.
- [ ] **B1 — cổng chống "đo nhầm đường":** `rerank.json` **không được** giống byte-for-byte `fusion.json`. Giống nhau = tầng rerank **chưa được đo**, KHÔNG phải tầng rerank vô dụng. Hai kết luận đó ngược nhau hoàn toàn, và nhầm chúng là cách rẻ nhất để plan này tự lừa mình. Cùng khuôn mẫu với cổng `query_text` mà phase 7 đã đặt — chỉ là tổng quát hoá nó.
- [ ] **Đo p95 latency** trên cùng bộ eval, cả `noop` lẫn `cross_encoder`. Rerank cải thiện chất lượng nhưng đánh đổi bằng thời gian trên CPU; **cả hai con số phải nằm trong báo cáo**, không chỉ con số đẹp.
- [ ] Chạy container `runtime-rerank` **ngắt mạng** → khởi động và trả lời được. Đây là bước duy nhất chứng minh phương án A đã thật sự đạt mục tiêu của nó; thiếu nó thì "nướng vào image" chỉ là ý định.

**Cổng của phase:** đo cả hit-rate **lẫn p95 latency** **lẫn image size**. Ba con số, không phải một.

## Risks

- **R7 — image phình + latency tăng.** Đã giảm nhẹ ở mức kiến trúc (optional extra + Docker target riêng) nên image mặc định không đổi. Rủi ro còn lại thuộc về người bật nó, và họ bật khi đã thấy số thật. Lối lùi sang API vẫn mở qua Protocol.
- **Import nặng rò rỉ lên module scope.** Rủi ro âm thầm nhất của phase: một lần refactor "dọn dẹp import" là suite bắt đầu kéo `torch`. Test 5 chặn, nhưng chỉ khi nó chạy trong subprocess sạch. Nếu ai đó "đơn giản hoá" nó thành kiểm `sys.modules` trong tiến trình test, nó thành xanh giả.
- **Cross-encoder chạy trên CPU với 30 cặp mỗi truy vấn.** `[ASSUMED]`: chưa đo. Đây có thể là chi phí lớn nhất của cả đường truy vấn, và với `top_n=10` từ 30 cặp thì cả 30 cặp đều phải chạy qua model. Nếu p95 không chấp nhận được, hai nút vặn có sẵn mà **không** cần đổi kiến trúc: giảm `fusion_limit` (ít cặp hơn) hoặc chuyển `device`. Đừng vội chuyển sang API khi chưa thử hai cái đó.
- **Model đa ngôn ngữ.** `ms-marco-MiniLM-L-6-v2` huấn luyện trên dữ liệu tiếng Anh `[PRIOR]`. Bộ eval của phase 2 có tiếng Việt, nên rerank **có thể làm tệ đi** trên các case tiếng Việt trong khi cải thiện case tiếng Anh — và con số tổng sẽ che mất chuyện đó. Xử: ở cổng phase, xem **danh sách case đổi chỗ theo tên** chứ không chỉ tổng; nếu các case tệ đi tập trung vào tiếng Việt thì đó là bằng chứng để đổi sang một model đa ngôn ngữ, ghi bằng một DEC.
- **`score` đổi ý nghĩa mà không đổi hình dạng.** Sau rerank, `score` trong `sources[]` là điểm cross-encoder chứ không phải cosine, và UI vẫn hiển thị nó với 3 chữ số thập phân như cũ (`app.js:140`). Không phá gì, nhưng phải ghi vào tài liệu ở phase 10.
</content>
