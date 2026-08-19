---
phase: 2
title: "Eval Foundation"
status: pending
plan: 260817-1100-p2-multiturn-hybrid
created: 2026-08-17
harness_version: 5.1.2
harness_kit_digest: 19d7d467322359e595c7f21ed6afec43e4a70a8757216913da11add0cbd1f858
harness_schema_version: 1.0
---

# Phase 2 — Eval Foundation

## Overview

**Đây là phase quan trọng nhất của cả plan, và là phase dễ bị bỏ qua nhất** — vì nó không thêm tính năng nào người dùng nhìn thấy.

Bộ eval hiện tại: **6 case, đúng 2 nguồn** [OBSERVED: `data/eval/qa.jsonl` 6 dòng, `expected_source` chỉ có `sample_faq.txt` và `sample_guide.md`]. Đoán bừa giữa 2 nguồn đã cho hit-rate 50%. Không thể dùng con số này để chứng minh bất cứ điều gì: không chứng minh được gate của DEC-2 (phase 5), không chứng minh được RRF fusion có hơn dense-only (phase 7), không chứng minh được cross-encoder đáng 2GB image (phase 8).

Phase này làm ba việc:

1. Mở rộng dữ liệu: ≥40 case trên ≥6 nguồn — và trước đó là **viết thêm tài liệu**, vì hiện chỉ có 2 tài liệu trên đĩa (R11).
2. Tạo bộ multi-turn: cặp câu hỏi *có đại từ* / *tự đủ nghĩa* cho cùng một đáp án, để phase 5 có A/B thật sự chứ không phải cảm nhận.
3. Nâng `EvalReport` để đo được **từng tầng**, không chỉ tổng — không có phân tách này thì phần B tốn 2GB image mà không biết tầng nào đóng góp.

Phụ thuộc: phase 1 (nghiệm thu P1 phải sạch trước khi chồng thay đổi lên).

## Files

- **Create** `data/documents/*.md` / `*.txt` — ≥4 tài liệu mới, chủ đề khác nhau rõ rệt.
- **Modify** `data/eval/qa.jsonl` — lên ≥40 case, ≥6 nguồn.
- **Create** `data/eval/qa_multiturn.jsonl` — bộ multi-turn.
- **Modify** `src/rag_chatbot_tung/evaluate/metrics.py` — `EvalCase` nhận trường mới, `EvalReport` đo theo tầng, ghi lại `score` thật.
- **Modify** `scripts/run_eval.py` — in bảng, thêm `--baseline` để diff, thêm `--cases` cho bộ multi-turn.
- **Create** `tests/test_metrics.py` — hiện `evaluate/` **không có test nào** [OBSERVED: `ls tests/` không có `test_metrics.py`]. Phase này sửa luôn khoảng trống đó, vì sắp tới mọi kết luận đều dựa vào module này.

`data/documents/` **không** bị gitignore (`.gitignore:30-33` chỉ loại `/data/embeddings/*` và `/data/uploads/`), nên tài liệu mới được track bình thường.

## Tài liệu mới — ràng buộc nội dung

Không phải văn bản lorem ipsum. Eval chỉ có nghĩa khi các nguồn **phân biệt được nhưng không tách biệt hoàn toàn**:

- Nếu 6 tài liệu nói 6 chủ đề chẳng liên quan gì nhau, retrieval nào cũng đạt gần 100% và bộ eval lại vô dụng theo hướng ngược lại.
- Cần **chồng lấn có kiểm soát**: vài tài liệu cùng nhắc tới Qdrant/embedding/chunking nhưng ở góc độ khác nhau, để câu hỏi thật sự phải phân biệt.
- Cần cả **tiếng Việt** — tokenizer BM25 của phase 7 sẽ được đo trên chính bộ này, và một bộ eval toàn tiếng Anh sẽ giấu đi đúng cái điểm yếu cần nhìn thấy (`docs/ARCHITECTURE.md` và các sample hiện tại đều tiếng Anh).
- Đủ dài để chia thành nhiều chunk: `chunk_size: 1000`, `min_chunk_size: 50` (`configs/default.yaml:29-32`), nên tài liệu ~3000+ ký tự mới sinh ra vài chunk.
- Có ít nhất một `.md` nhiều heading, để `split_markdown` gán `title` cho chunk (`chunking/splitter.py:56-69`) — phase 9 cần dữ liệu này cho quy tắc boost theo heading.

**Nguồn `.pdf`: hạng mục người dùng cung cấp.** Không sinh ra được một PDF có nội dung thật bằng code trong repo này (`pypdf` là thư viện đọc; `reportlab` không có trong dependency và thêm nó chỉ để sinh dữ liệu test là trái YAGNI). Nếu người dùng thả một PDF vào `data/documents/`, thêm case cho nó; nếu không, phase vẫn đạt với ≥6 nguồn `.txt`/`.md` và **ghi rõ vào verification rằng nhánh `.pdf` chưa được phủ**. Đừng giả vờ là đã phủ.

## Schema dữ liệu

`data/eval/qa.jsonl` giữ nguyên schema hiện tại — `load_cases` gọi `EvalCase(**json.loads(line))` (`metrics.py:33-39`) nên mọi khoá thừa sẽ nổ `TypeError`:

```json
{"question": "...", "expected_source": "sample_faq.txt"}
```

`data/eval/qa_multiturn.jsonl` là schema mở rộng, và đây là chỗ **thiết kế quyết định giá trị của phase 5**:

```json
{
  "question": "Nó lưu vector ở đâu?",
  "question_selfcontained": "Hệ thống lưu vector ở đâu?",
  "expected_source": "sample_faq.txt",
  "history": [
    {"role": "user", "content": "Hệ thống dùng cơ sở dữ liệu nào?"},
    {"role": "assistant", "content": "Qdrant được dùng làm vector store."}
  ]
}
```

Cặp `question` / `question_selfcontained` là **toàn bộ cơ chế đo của phase 5**: chạy cùng một bộ hai lần, một lần với câu có đại từ, một lần với câu tự đủ nghĩa, rồi lấy hiệu hit-rate. Không có cặp này thì phase 5 chỉ có một con số trơ trọi chẳng so với cái gì.

`history` ở đây là `list[dict[str, str]]` thuần dữ liệu — **cố ý không phụ thuộc `Turn`** (model đó mới sinh ra ở phase 3). Giữ như vậy để phase 2 không phải chờ phase 3, và để `metrics.py` không kéo `validate.py` vào chỉ vì một trường dữ liệu.

`EvalCase` là `@dataclass(slots=True)` (`metrics.py:12-15`), đúng chuẩn value object nội bộ ở `docs/code-standards.md:35-36` — giữ nguyên dạng đó, thêm field có default:

```python
@dataclass(slots=True)
class EvalCase:
    question: str
    expected_source: str | None            # None = case lạc đề, xem B2 bên dưới
    question_selfcontained: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
```

Có default nên `qa.jsonl` cũ **vẫn nạp được không sửa** — backwards compatible, và có test giữ điều đó.

### B2 — nhóm case lạc đề, `expected_source: null`

Bộ eval chỉ đo "tài liệu đúng có xuất hiện không". Nó **không phạt rác đi kèm**, nên nó mù hoàn toàn trước lỗi mà phase 7 sắp tạo ra: hybrid trả về đoạn văn không liên quan cho câu hỏi lạc đề, thay vì `NO_CONTEXT_ANSWER` [OBSERVED: probe ở `phase-7`, dense-only 0 hits vs hybrid 4 hits].

Thêm **≥6 case lạc đề** với `expected_source: null` — câu hỏi về chủ đề hoàn toàn ngoài bộ tài liệu, nhưng có chia sẻ stopword tiếng Việt/tiếng Anh thông thường với chúng (đó chính là kịch bản BM25 lọt lưới).

`EvalReport` cần thêm hai số cho nhóm này:
- `abstain_correct` — case lạc đề trả về rỗng (đúng).
- `false_positive` — case lạc đề trả về chunk (sai — đây là con số mà phase 7 phải giữ ở 0).

Không gộp nhóm này vào `hit_rate`: trộn hai loại câu hỏi vào một tỉ lệ sẽ giấu đúng cái cần thấy.

## Đo theo tầng

`EvalReport` hiện chỉ có `total`, `hits`, `reciprocal_rank_sum` (`metrics.py:18-30`). Cần tách được hit-rate của: dense-only → sau fusion → sau rerank → sau metadata.

Cách rẻ nhất và ít suy đoán nhất: **không** nhồi 4 tầng vào một `EvalReport`. Giữ `EvalReport` là kết quả của **một cấu hình**, và để `run_eval.py` chạy nhiều cấu hình rồi in bảng so sánh. Lý do: các tầng ở phase 7/8/9 đều có công tắc config; chạy lại eval với công tắc khác là một dòng env, còn nhét bốn đường ống song song vào `evaluate_retrieval` là dựng một bản sao của orchestrator bên trong module đo — chỗ đó chắc chắn sẽ trôi khỏi đường thật.

Cái `EvalReport` **cần thêm** là chi tiết mỗi case, để so sánh giữa các lần chạy có nghĩa:

```python
@dataclass(slots=True)
class EvalCaseResult:
    question: str
    expected_source: str
    hit: bool
    rank: int | None        # None nếu trượt
    scores: list[float]     # score thật của từng chunk trả về, theo thứ tự
    sources: list[str]      # source của từng chunk, theo thứ tự
```

`EvalReport` giữ thêm `results: list[EvalCaseResult]`. Từ đây có ngay hai thứ:

- **Kiểm chứng nhận định "`score_threshold: 0.3` gần như không lọc gì"** — đọc thẳng phân bố `scores`. Đây là dữ liệu đầu vào cho R4 ở phase 7, và nó phải được lấy **trước** khi fusion làm thang điểm đổi.
- `--baseline`: nạp một file JSON kết quả cũ, in ra case nào chuyển từ hit sang miss và ngược lại. Tổng hit-rate giữ nguyên trong khi 5 case đổi chỗ cho nhau là một thông tin mà con số tổng che mất hoàn toàn.

`run_eval.py` thêm `--out <path>` để ghi kết quả JSON, `--baseline <path>` để so.

## TDD

Toàn bộ test của phase này chạy **offline**, dùng `orchestrator` fixture (`FakeEmbedder` + `QdrantClient(":memory:")`, `tests/conftest.py:102-104`). Việc chạy eval trên hạ tầng thật là một hạng mục riêng, ở mục Success.

**Tests-before (RED)** — `tests/test_metrics.py` mới:

1. `test_load_cases_reads_legacy_schema` — nạp một file 2 dòng chỉ có `question` + `expected_source`, khẳng định `question_selfcontained is None` và `history == []`.
   *Đỏ vì:* `EvalCase` chưa có hai field đó → `AttributeError`. Đây là đỏ vì nghiệp vụ (schema chưa mở rộng), không phải vì import.
2. `test_load_cases_reads_multiturn_schema` — nạp một dòng đủ 4 khoá, khẳng định cả bốn về đúng chỗ.
   *Đỏ vì:* `EvalCase(**...)` ném `TypeError: unexpected keyword argument 'history'` — chính xác là hành vi hiện tại của `metrics.py:38`.
3. `test_report_records_per_case_detail` — nạp `sample_txt` vào `orchestrator`, chạy `evaluate_retrieval`, khẳng định `report.results` có đúng `len(cases)` phần tử và mỗi phần tử có `scores` không rỗng khi có chunk trả về.
   *Đỏ vì:* `EvalReport` chưa có `results`.
4. `test_report_records_miss_with_rank_none` — một case có `expected_source` không tồn tại → `hit is False`, `rank is None`, và `hit_rate` tính đúng.
5. `test_hit_rate_and_mrr_on_empty_case_list` — 0 case → `hit_rate == 0.0`, `mrr == 0.0`, không `ZeroDivisionError`. Nhánh này đã có trong code (`metrics.py:26,30`) nhưng chưa có test giữ.
6. `test_eval_dataset_files_are_wellformed` — đọc thật `data/eval/qa.jsonl` và `data/eval/qa_multiturn.jsonl`: mỗi dòng parse được, `qa.jsonl` có ≥40 case và ≥6 giá trị `expected_source` phân biệt, `qa_multiturn.jsonl` có mọi case đủ `question_selfcontained` và `history` không rỗng.
   *Đỏ vì:* file hiện 6 dòng / 2 nguồn. **Đây là test biến R1 thành một điều kiện kiểm được bằng máy** thay vì một lời nhắc trong plan.
7. `test_every_expected_source_exists_on_disk` — mọi `expected_source` trong cả hai file phải là một file có thật trong `data/documents/`. Không có test này thì một lỗi chính tả trong tên file biến thành "retrieval kém" và người ta đi tối ưu nhầm chỗ suốt vài giờ.

Lưu ý cho test 6 và 7: fixture `away_from_dotenv` (autouse) `chdir` sang `tmp_path` (`tests/conftest.py:56-67`), nên **đường dẫn tương đối sẽ trỏ sai**. Phải dựng đường dẫn tuyệt đối từ một mỏ neo trong package, ví dụ `rag_chatbot_tung.configs.PROJECT_ROOT` (`configs.py:17`). Bỏ qua chi tiết này là cách nhanh nhất để có một test đỏ vì lý do sai hoàn toàn.

**Implement** → xanh:
- Viết ≥4 tài liệu mới vào `data/documents/`.
- Viết `qa.jsonl` (≥40 case) và `qa_multiturn.jsonl`.
- Mở rộng `EvalCase` / `EvalReport` / `evaluate_retrieval`.
- Mở rộng `run_eval.py` (`--out`, `--baseline`, in bảng).

**Regression gate:**

```
uv run pytest -q                 → ≈84 passed, không giảm dưới 78
uv run ruff check src tests
uv run black --check src tests
uv run mypy src
```

## Success

**Đo bằng máy (cook làm được):**

- [ ] 7 test mới xanh; tổng không giảm so với 78.
- [ ] Bốn cổng sạch.
- [ ] `data/eval/qa.jsonl` ≥ 40 dòng, ≥ 6 `expected_source` phân biệt; mọi nguồn tồn tại trên đĩa.
- [ ] `data/eval/qa_multiturn.jsonl` ≥ 10 case, mỗi case đủ cặp `question` / `question_selfcontained` và `history` không rỗng.
- [ ] `uv run python scripts/run_eval.py --help` liệt kê `--cases`, `--top-k`, `--out`, `--baseline`.

**Cần hạ tầng thật (người dùng chạy — R12):**

- [ ] `docker compose up -d qdrant` → `uv run python scripts/ingest.py` → mọi tài liệu mới được index, `points_count` tăng đúng.
- [ ] `uv run python scripts/run_eval.py --out data/eval/baseline.json` chạy xong, in ra **hit-rate và MRR baseline**. Con số này được chép vào `artifacts/verification-P2.json` và là mốc so của phase 5, 7, 8, 9, 10.
- [ ] Nhìn phân bố `scores` trong `baseline.json` và trả lời bằng số: `score_threshold: 0.3` thật sự lọc bao nhiêu chunk? Nếu gần như không lọc gì thì ghi rõ — đó là dữ kiện R4 cần.

**Cổng của phase:** eval chạy được và in ra baseline number. **Không có con số đó thì phase 2 chưa xong**, bất kể test có xanh hay không — vì mục đích duy nhất của phase này là tạo ra một mốc để so.

## Risks

- **Viết 40 case là việc tay, và việc tay thì bị cắt xén khi mệt.** Cám dỗ: sinh 40 case bằng cách diễn đạt lại 6 câu cũ. Kết quả là một bộ eval trông to mà phương sai thật vẫn bằng 6. Ràng buộc chống lại: ≥6 nguồn phân biệt, và mỗi nguồn có ≥4 case chạm vào các phần **khác nhau** của tài liệu.
- **Rò rỉ đáp án qua từ khoá.** Nếu câu hỏi chép nguyên một cụm từ hiếm chỉ có trong đúng một tài liệu, thì cả dense lẫn BM25 đều trúng dễ dàng và bộ eval mất khả năng phân biệt hai phương pháp — đúng cái phase 7 cần đo. Viết câu hỏi bằng lời của người dùng, không bằng lời của tài liệu.
- **Chuẩn hoá Unicode lệch nhau giữa hai đầu.** Đã kiểm và đây là một bất đối xứng có thật: mọi văn bản đi qua ingest đều được `clean_text` chuẩn hoá **NFKC** (`src/rag_chatbot_tung/utils/text.py:19-23`, gọi ở `retrieval/document_retrieval.py:89,91,97,145`), nhưng **câu hỏi thì không** — `orchestrator.py:56` đưa `request.question` thẳng vào `embed_query`. Với embedding dày thì lệch NFC/NFD chỉ làm vector nhích nhẹ; với BM25 ở phase 7 thì "máy" dạng NFC và dạng NFD là **hai term khác nhau hoàn toàn**, và câu truy vấn sẽ trượt sạch mà không ai hiểu vì sao. Phase 2 chỉ **ghi nhận** điều này (và viết dữ liệu eval ở dạng NFC nhất quán); việc xử lý thuộc phase 7 — tokenizer sparse phải tự chuẩn hoá cùng một kiểu với ingest. Đừng lặng lẽ sửa `orchestrator.py` ở đây.
- **Bộ eval mở rộng làm hit-rate baseline TỤT so với con số cũ.** Gần như chắc chắn xảy ra: 6 case dễ trên 2 nguồn cho con số đẹp giả tạo. Đây **không phải regression** và đừng ai đọc nó như regression. Baseline được định nghĩa lại tại phase này, và mọi so sánh về sau là so với baseline mới.
- **Chạy eval tốn tiền OpenAI thật** (R12). 40 case × 1 lần embed câu hỏi là nhỏ, nhưng lặp lại ở phase 5/7/8/9/10 thì cộng dồn. Không có cách tránh — embedding phải thật thì kết quả retrieval mới thật.
</content>
