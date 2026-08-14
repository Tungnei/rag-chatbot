# Decision Register

---
id: DEC-1
status: active
date: 2026-08-12
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-12T04:49:02.326808+00:00"
affects: "src/rag_chatbot_tung/api/app.py,src/rag_chatbot_tung/api/static/,tests/test_api.py,Dockerfile"
---

## DEC-1 — Giao dien chatbot: trang tinh vanilla JS do FastAPI phuc vu tai /ui

Zero dependency moi, khong doi deploy (Dockerfile da COPY src), toan quyen render sources/citations. Gradio bi loai vi keo cay phu thuoc nang va tu rang buoc phien ban fastapi/pydantic dang khoa trong uv.lock; React/Next bi loai vi them toolchain Node va mot service compose cho mot repo Python dang gon. Admin dat o /ui/admin tach duong dan de P3 khoa bang proxy ma khong viet lai UI.

---
id: DEC-2
status: active
date: 2026-08-12
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-12T04:49:15.827701+00:00"
affects: "src/rag_chatbot_tung/validate.py,src/rag_chatbot_tung/orchestrator.py,src/rag_chatbot_tung/llm_generator/prompts.py,data/eval/qa.jsonl"
---

## DEC-2 — Hoi thoai nhieu luot: client gui history, server van stateless, chi embed cau hoi hien tai

Them history vao QueryRequest va chi dua vao phan LLM; vector truy van van la cau hoi hien tai nen chat luong retrieval khong suy giam. Client giu lich su nen khong can Redis/session store. Giu toi da 3 luot gan nhat vi context_token_budget 6000 phai chia voi cac doan van truy xuat. Query-rewriting bang mot luot LLM phu chi duoc them khi scripts/run_eval.py chung minh cau hoi co dai tu that su lam tut hit-rate.

---
id: DEC-3
status: active
date: 2026-08-12
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-12T04:49:29.456056+00:00"
affects: "configs/default.yaml,src/rag_chatbot_tung/api/app.py,src/rag_chatbot_tung/api/routes.py,docker-compose.yaml,deploy/k8s.yaml"
---

## DEC-3 — Cong khai internet chi sau khi co reverse proxy auth; khong tu viet auth trong FastAPI

SPA chay trong trinh duyet khong giau duoc API key nen co che key-trong-header vo nghia; phai la session cookie do lop phia truoc cap (Caddy basic auth / oauth2-proxy / Cloudflare Access), 0 dong code ung dung. /ingest, /ingest/upload va DELETE /documents phai nam sau cong chat hon cong chat vi hien tai ai cung xoa duoc index; /ingest nhan url la SSRF khi mo ra internet. CORS ['*'] phai siet lai (UI cung origin). Tran chi tieu dat o dashboard OpenAI vi do la bao dam bang tien, doc lap voi bug trong code. Thu tu thi cong chot: P1 UI localhost -> P2 multi-turn -> P3 hardening -> moi mo mang.

---
id: DEC-4
status: active
date: 2026-08-12
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-12T07:06:38.217922+00:00"
affects: "src/rag_chatbot_tung/validate.py,src/rag_chatbot_tung/adaptor/protocols.py,src/rag_chatbot_tung/retrieval/vector_search.py,src/rag_chatbot_tung/orchestrator.py,src/rag_chatbot_tung/api/routes.py"
---

## DEC-4 — Them GET /documents de trang admin liet ke nguon that trong index

Phuong an ghi chep localStorage bi loai: xoa cache trinh duyet la danh sach bien mat trong khi index van nguyen, va tai lieu do nguoi khac nap thi khong bao gio hien ra. Endpoint di xuyen 5 tang theo dung kien truc: validate.py (DocumentSummary/DocumentList) -> adaptor/protocols.py (them list_sources vao VectorStore Protocol) -> retrieval/vector_search.py -> orchestrator.py -> api/routes.py. Cai bang client.scroll voi with_vectors=False chu khong dung facet, vi test chay che do local QdrantClient(':memory:') va chua xac minh duoc che do local co ho tro facet; scroll chac chan chay o ca hai. Danh doi: scroll la O(so chunk). Dieu kien doi sang facet: points_count vuot khoang 50000 VA da do duoc do tre that. Quyet dinh nay pha rang buoc 'P1 khong them endpoint nghiep vu' mot cach co y thuc, chot tai gate validate cua plan 260812-1221-p1-chat-ui.

---
id: DEC-5
status: active
date: 2026-08-13
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-13T11:07:20.326241+00:00"
affects: "src/rag_chatbot_tung/providers.py,src/rag_chatbot_tung/configs.py,src/rag_chatbot_tung/llm_generator/anthropic_llm.py,src/rag_chatbot_tung/orchestrator.py,pyproject.toml,.env.example"
---

## DEC-5 — Chon LLM provider bang env; embeddings vinh vien tach rieng va o lai OpenAI

LLM__PROVIDER chon giua openai va anthropic qua Literal trong LLMSettings, providers.py anh xa sang lop cu the. Orchestrator chi phu thuoc Protocol nen khong doi dong nao. EMBEDDINGS__PROVIDER la mot setting RIENG va hien chi nhan 'openai': Anthropic khong co API embeddings (Messages/Batches/Files/TokenCounting/Models, khong co endpoint nao cho embeddings, danh muc model khong co model embedding). Tach rieng con vi ly do thu hai: model embedding quyet dinh so chieu vector da ghi vao Qdrant, doi kem theo LLM se pha collection dang co. AnthropicLLM KHONG gui temperature (Claude doi moi tra 400) va chi gui output_config.effort khi duoc dat (Sonnet 4.5 loi neu nhan). max_tokens tren Claude bao trum ca thinking lan cau tra loi nen can headroom lon hon. Them dependency anthropic>=0.40 (da cai 0.121).

---
id: DEC-6
status: active
date: 2026-08-14
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-14T07:13:01.303595+00:00"
affects: "src/rag_chatbot_tung/configs.py,src/rag_chatbot_tung/llm_generator/anthropic_llm.py,src/rag_chatbot_tung/llm_generator/openai_llm.py,src/rag_chatbot_tung/embeddings/openai_embedder.py,.env.example"
---

## DEC-6 — Them LLM__BASE_URL / EMBEDDINGS__BASE_URL de tro toi gateway cung giao thuc

Khoa cua nguoi dung di qua cliproxy (cli-proxy-api, cong 8317) chu khong phai api.anthropic.com — da xac minh: api.anthropic.com tra 401 invalid x-api-key, con proxy tra 200 tren POST /v1/messages. base_url rong = endpoint goc cua provider. Giao thuc van phai khop provider: LLM__PROVIDER=anthropic + base_url tro toi cong noi Messages API. Sua kem mot bug that: health() cu goi models.retrieve() (GET /v1/models/{id}) ma proxy tra 404, nen /health se bao openai:false du sinh cau tra loi van chay; doi sang models.list() (GET /v1/models) chay ca hai phia. Da do: cliproxy phuc vu 15 model Claude, KHONG co model embedding, /v1/embeddings tra 404 — nen gateway Claude khong lam OPENAI_API_KEY tro nen tuy chon.

---
id: DEC-7
status: active
date: 2026-08-14
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-14T10:29:14.097315+00:00"
affects: ".env.example,README.md"
---

## DEC-7 — OpenRouter phuc vu ca chat lan embeddings; ca hai nua chay qua mot khoa duy nhat

Do truc tiep: POST https://openrouter.ai/api/v1/embeddings voi model 'openai/text-embedding-3-small' tra vector 1536 chieu, dung bang QDRANT__VECTOR_SIZE nen KHONG phai index lai. Chat 'openai/gpt-4o-mini' cung chay (OpenRouter dinh tuyen qua Azure). Vi OpenRouter noi giao thuc OpenAI nen cau hinh dung la LLM__PROVIDER=openai + LLM__BASE_URL + EMBEDDINGS__BASE_URL, khong can adapter moi. Dieu nay KHONG lat DEC-5: Anthropic van khong co embeddings; diem khac la gateway nao dung sau. Bai hoc ghi lai de khoi suy dien: kha nang cua mot gateway phai DO chu khong suy ra tu viec no la gateway.
