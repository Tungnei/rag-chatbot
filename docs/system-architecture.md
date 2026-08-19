# System Architecture (bản đồ định hướng)

File này chỉ trả lời "đứng ở đâu trong hệ thống, đừng thiết kế sai chỗ nào". Chi tiết luồng
request/ingest, bảng module, deployment: xem `docs/ARCHITECTURE.md`. Quyết định kèm lý do:
`docs/decisions.md` (DEC-1..DEC-8).

## Hình dạng hệ thống

FastAPI app (`src/rag_chatbot_tung/api/`) phục vụ cả API JSON lẫn UI tĩnh (`/ui`, `/ui/admin`
— vanilla HTML/CSS/JS, không build step). `RAGOrchestrator` (`orchestrator.py`) là điểm hội tụ
duy nhất của hai luồng nghiệp vụ: `answer()` (query) và `ingest()`/`ingest_directory()`. Qdrant
là vector store, OpenAI là embeddings, LLM là OpenAI hoặc Anthropic tuỳ config.

## Nguyên tắc bất biến — tầng adaptor

`adaptor/protocols.py` định nghĩa ba `typing.Protocol` (`@runtime_checkable`):
`EmbeddingProvider`, `VectorStore`, `LLMProvider`, cộng `VectorPoint` (`@dataclass(slots=True)`).

`RAGOrchestrator.__init__` (`orchestrator.py:33-46`) nhận ba phụ thuộc này qua constructor
injection dưới dạng Protocol. Class cụ thể mà nó import chỉ là hạ tầng mặc định, không phải
provider: `QdrantVectorStore`, `IngestionPipeline`, `TextSplitter`. **Không bao giờ
import một class provider cụ thể (`OpenAILLM`, `AnthropicLLM`, `OpenAIEmbedder`, ...) vào
`orchestrator.py`** — đó là việc của `providers.py`, nơi DUY NHẤT ánh xạ giá trị `provider` sang
class và biết provider nào cần key nào (`_LLM_KEY_FIELDS`). Thêm provider mới = một class mới
implement đúng Protocol + một nhánh trong `providers.py`; orchestrator, API, test đều không đổi.

## Embeddings tách vĩnh viễn khỏi LLM provider (DEC-5)

`EMBEDDINGS__PROVIDER` và `LLM__PROVIDER` là hai setting độc lập, không đi theo nhau. Lý do kép:
Anthropic không có API embeddings; và model embedding quyết định số chiều vector đã ghi vào
Qdrant, đổi kèm LLM sẽ phá collection đang có. `build_embedder` (`providers.py:34-41`) hiện chỉ
trả `OpenAIEmbedder` nhưng vẫn giữ dạng factory vì lý do đó — đừng "dọn" nó thành gọi thẳng
`OpenAIEmbedder()`.

Khi trỏ LLM/embeddings qua gateway (`LLM__BASE_URL` / `EMBEDDINGS__BASE_URL`, DEC-6/DEC-7):
protocol của base_url phải khớp `provider` đã chọn (vd. `LLM__PROVIDER=anthropic` cần gateway
nói Messages API). Bài học DEC-7: **khả năng của một gateway phải được ĐO bằng một request thật,
không suy ra** từ việc nó là gateway — một gateway OpenAI-protocol không mặc định có endpoint
embeddings.

## Luồng query (rút gọn)

`answer()` (`orchestrator.py:51-84`): embed câu hỏi hiện tại → `vector_store.search` → **rỗng
thì trả `NO_CONTEXT_ANSWER` ngay, không gọi LLM** (dòng 61-67, một trong hai lớp chống bịa cùng
với `retriever.score_threshold`) → `build_rag_messages` (kèm `history` nếu client gửi) →
`llm.generate`. Chi tiết sơ đồ đầy đủ: `docs/ARCHITECTURE.md`.

Đa lượt (DEC-2) — **đã triển khai** (P2 phase 3-4, 2026-08-18): `QueryRequest` có `history:
list[Turn]`, client gửi lịch sử, **server vẫn stateless** — không session store, không Redis,
không `conversation_id`. Ràng buộc cốt lõi vẫn nguyên và vẫn là ràng buộc: **chỉ câu hỏi hiện
tại được embed** để truy vấn vector; `history` chỉ đi vào phần LLM. Có test thi hành điều này
(`test_history_does_not_change_the_embedded_query`) chứ không chỉ là quy ước.

Chi tiết đang áp dụng: giữ tối đa 3 lượt hỏi-đáp gần nhất (cắt trong `build_rag_messages`, không
phải 422); `llm.history_token_budget` (mặc định 1500) là trần cứng riêng để lịch sử không bóp
nghẹt đoạn văn truy xuất; role được chuẩn hoá về xen kẽ user/assistant trước khi gửi đi, vì
Anthropic đòi xen kẽ và `history` là dữ liệu client không được tin.

Query-rewriting vẫn **BỊ CHẶN** — xem DEC-8: phép đo ở phase 5 (n=12) cho hướng nhất quán nhưng
chưa đủ để kết luận.

## Luồng ingest (rút gọn)

`IngestionPipeline` (`retrieval/document_retrieval.py`) idempotent: point id là
`uuid5(_POINT_NAMESPACE, f"{source}:{index}")`, và `delete_by_source()` chạy trước `upsert()`
(dòng 163-171) nên ingest lại một nguồn không tạo chunk trùng hay để sót chunk cũ.

## Config

`configs.py:102-118` (`Settings.settings_customise_sources`) chốt thứ tự ưu tiên:
constructor args > env > `.env` > `configs/default.yaml` > field defaults. Field lồng nhau dùng
`__` (`RETRIEVER__TOP_K`). Đừng thêm một cơ chế đọc config thứ hai song song thứ tự này.

## Bảo mật — trạng thái hiện tại (DEC-3)

Chưa có auth tự viết trong FastAPI, và có chủ đích: SPA chạy trong trình duyệt không giấu được
API key nên cơ chế key-trong-header vô nghĩa; auth phải là một lớp phía trước (reverse proxy)
cấp session cookie, 0 dòng code ứng dụng. Thứ tự thi công đã chốt: P1 UI localhost → P2
multi-turn → P3 hardening → mới mở internet. Trước khi mở `/ingest`, `/ingest/upload`,
`DELETE /documents` ra internet: đọc DEC-3 trước, đừng tự suy luận là an toàn.

## Endpoint liệt kê nguồn — vì sao dùng scroll chứ không facet (DEC-4)

`VectorStore.list_sources()` (`retrieval/vector_search.py:115-166`) đi qua `scroll`, O(số chunk).
Chủ ý: test chạy `QdrantClient(":memory:")` và chưa xác minh chế độ local có hỗ trợ facet;
`scroll` chắc chắn chạy được cả hai phía. Ngưỡng đổi sang facet đã ghi trong DEC-4
(`points_count` vượt khoảng 50000 VÀ đã đo được độ trễ thật) — đừng tối ưu sớm khi chưa tới đó.

## Xem thêm

- `docs/ARCHITECTURE.md` — sơ đồ luồng đầy đủ, bảng module, deployment (docker-compose, k8s).
- `docs/decisions.md` — DEC-1..DEC-8, lý do đằng sau mỗi quyết định trên.
- `docs/PROJECT_STRUCTURE.md` — cây thư mục có chú thích từng file.
