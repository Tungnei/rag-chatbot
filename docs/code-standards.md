# Code Standards (bản đồ định hướng)

Quy tắc thật đang được tuân theo trong repo, xác minh trực tiếp qua code — không phải quy tắc
lý tưởng. Kiến trúc/luồng: `docs/system-architecture.md`. Cây thư mục: `docs/PROJECT_STRUCTURE.md`.

## Toolchain (bắt buộc sạch trước khi coi là xong)

`uv` quản lý dependency và venv. Chạy qua `uv run`:

```
uv run ruff check src tests    # lint
uv run black --check src tests # format
uv run mypy src                # type check
uv run pytest -q               # test
```

Cả bốn phải sạch. Baseline hiện tại: `pytest -q` → **156 passed**. Python 3.11
(`.python-version`, `requires-python = ">=3.11"`).

## Quy ước ngôn ngữ

- `from __future__ import annotations` ở đầu mọi module có logic trong `src/` và `tests/`.
  Ngoại lệ đã xác minh: các `__init__.py` chỉ re-export không cần dòng này.
- Type hint kiểu mới (`list[str]`, `X | None`), không dùng `typing.List`/`Optional`.

## Dependency injection qua Protocol, không qua kế thừa

`orchestrator.py` chỉ phụ thuộc `adaptor/protocols.py` (`typing.Protocol`,
`@runtime_checkable`), không bao giờ import một class provider cụ thể. Đây là quy tắc kiến
trúc quan trọng nhất của repo — chi tiết và lý do ở `docs/system-architecture.md`. Khi thêm
provider mới: implement đúng shape của Protocol, không thêm base class hay kế thừa.

## Chọn dataclass hay Pydantic BaseModel

- `@dataclass(slots=True)` cho value object nội bộ, không đi qua boundary nào: `VectorPoint`
  (`adaptor/protocols.py`), `EvalCase`/`EvalReport` (`evaluate/metrics.py`).
- `pydantic.BaseModel` cho mọi thứ đi qua biên: request/response API và các model nghiệp vụ
  (`validate.py` — `Chunk`, `QueryRequest`, `QueryResponse`, `HealthResponse`, ...) và toàn bộ
  config (`configs.py` — `Settings` kế thừa `BaseSettings`, các `*Settings` kế thừa `BaseModel`).

Đừng đảo ngược: không dùng dataclass cho response API, không dùng BaseModel cho value object
nội bộ chỉ sống trong một hàm.

## Docstring và comment

Docstring: ngắn, một dòng, chỉ ở hàm/class public khi nó thêm thông tin thật (vd.
`providers.py`, `retrieval/vector_search.py`). Nhiều hàm nội bộ không có docstring — đó là
bình thường trong repo này, không phải thiếu sót cần bổ sung hàng loạt.

Comment giải thích **LÝ DO**, không diễn giải lại code — đây là quy ước mạnh và nhất quán nhất
trong codebase, giữ nguyên phong cách này khi sửa/thêm code. Ví dụ thật:

- `retrieval/vector_search.py:22-28` — vì sao `_coerce_source_type` phải phòng thủ thay vì để
  `SourceType(...)` raise thẳng.
- `retrieval/vector_search.py:116-120`, `:139-141`, `:154-157`, `:164-165` — vì sao dùng
  `scroll` chứ không facet, vì sao point thiếu `source` bị bỏ qua, vì sao title lấy từ chunk 0,
  vì sao kết quả phải sort.
- `configs.py:30-31`, `:46-47`, `:49-50`, `:54-56` — vì sao embeddings tách provider riêng, vì
  sao Anthropic không nhận `temperature`, vì sao `max_tokens` cần headroom lớn hơn trên Claude.
- `providers.py:20-21`, `:35-40` — vì sao báo lỗi thiếu key ngay thay vì để provider raise sau,
  vì sao `build_embedder` vẫn là factory dù hiện chỉ có một nhánh.
- `chunking/splitter.py:65`, `:111` — vì sao heading không có nội dung bị bỏ, vì sao overlap
  phải cắt tại word boundary.
- `tests/conftest.py:58-65` — vì sao test phải chạy tránh xa `.env` của máy dev (xem mục Test
  bên dưới).

## Test phải chạy hoàn toàn offline

Không test nào được gọi mạng thật. Cơ chế: `tests/conftest.py` cung cấp `FakeEmbedder` (vector
tất định bằng sha256 hash, không gọi OpenAI), `FakeLLM` (trả lời cố định), và
`QdrantVectorStore` được khởi với `QdrantClient(":memory:")`. Test mới cần một provider phải
dùng ba fixture này qua `orchestrator`/`pipeline`/`vector_store` fixture có sẵn, không tự tạo
client thật.

Fixture `away_from_dotenv` (autouse, `tests/conftest.py:56-67`) chdir sang `tmp_path` trước
mỗi test: `Settings` đọc `env_file=".env"` theo working directory và `.env` có ưu tiên cao hơn
YAML lẫn default, nên chạy suite từ repo root với `.env` thật của dev sẽ làm suite đỏ tuỳ máy.
Không được xoá hay vô hiệu hoá fixture này.

## TDD: đỏ trước, và phải đỏ đúng lý do

Bằng chứng đỏ/xanh phải ghi lại trong artifact verification của plan (mẫu:
`plans/260812-1221-p1-chat-ui/artifacts/verification-P*.json`, trường `tdd-red`). "Đỏ" không
đủ — phải đỏ vì đúng lý do nghiệp vụ, không phải vì lỗi import hay file thiếu tình cờ. Bài học
đã từng gặp trong repo: `test_app_js_never_uses_innerhtml` từng xanh giả vì `app.js` còn trả
404 (test không thực sự chạy qua nhánh cần kiểm) — chỉ có nghĩa sau khi file đó tồn tại. Trước
khi tin một test đỏ hay xanh, đọc log thất bại/thành công thật, đừng suy diễn từ tên test.

## Commit message

Conventional commits có scope, subject mô tả **hành vi quan sát được đã thay đổi**, không phải
tên thứ bị sửa. Ví dụ thật từ `git log`:

- `fix(llm): stop the OpenAI health check from retrieving a single model`
- `feat(llm): route a provider through a gateway via LLM__BASE_URL`
- `perf(docker): stop a one-line source edit from reinstalling every dependency`
- `fix(compose): keep the container listening on the port the mapping targets`

Tránh subject kiểu "update providers.py" hay "fix bug" — nêu triệu chứng/hành vi đã đổi.

## Secrets

`.env` không commit (`.gitignore`). `.env.example` là mẫu placeholder.

Quy ước về biến tuỳ chọn (căn cứ: commit `38ddd5f`, không phải DEC): biến chỉ cần khi hạ tầng
thật sự đòi thì để **comment out**, đừng để `KEY=` rỗng. Lý do đã đo: giá trị rỗng KHÁC với
unset — `QDRANT__API_KEY=` làm client cảnh báo đang gửi key qua kết nối không an toàn, dù người
dùng chưa hề đặt key nào.

## Chưa có chuẩn — đừng bịa khi được hỏi

Repo hiện chưa có chuẩn logging có cấu trúc (structured logging), chưa có chuẩn versioning/
changelog ngoài `pyproject.toml` `version`, và chưa có test coverage threshold bắt buộc dù
`pytest-cov` có trong dev dependencies. Nếu cần một trong các chuẩn này, đề xuất và chốt qua
DEC trước khi coi là quy ước đang áp dụng.

## Xem thêm

- `docs/system-architecture.md` — vì sao tầng adaptor tồn tại, vì sao embeddings tách provider.
- `docs/decisions.md` — DEC-1..DEC-8.
- `docs/SETUP.md`, `docs/QUICK_REFERENCE.md` — lệnh chạy dev hằng ngày.
