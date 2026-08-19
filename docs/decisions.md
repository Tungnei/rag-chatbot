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

---
id: DEC-8
status: active
date: 2026-08-18
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-18T11:23:58.959622+00:00"
affects: "docs/decisions.md, scripts/run_eval.py, src/rag_chatbot_tung/evaluate/metrics.py, data/eval/qa_multiturn.jsonl"
---

## DEC-8 — Cong query-rewriting cua DEC-2 van DONG: do duoc voi n=12 chua du ket luan

Phase 5 chay phep do ma DEC-2 doi hoi, tren data/eval/qa_multiturn.jsonl (12 case, moi case mot cap question co dai tu / question_selfcontained tu du nghia, cung expected_source). Ket qua: co dai tu hit-rate 66.67% (8/12) MRR 0.486; tu du nghia hit-rate 83.33% (10/12) MRR 0.667. Moc tinh tao: qa.jsonl chinh 97.37% / MRR 0.722. Diff theo tung case: 0 case tot len, 2 case xau di ('Vay con khi no khong tim thay gi thi sao?' va 'Cai do ton tien o cho nao?'); 2 case khac truot o CA HAI cach dien dat nen khong lien quan toi dai tu. HUONG cua bang chung nhat quan (khong co nhieu nguoc chieu) nhung TOAN BO hieu ung nam tren 2 case trong 12 — khong du de goi la 'dang ke'. Theo dung nhanh C ma plan du lieu: KHONG ep thanh A hay B. Ket luan: cong cua DEC-2 GIU NGUYEN TRANG THAI CHAN, query-rewriting van chua duoc phep. De ket luan duoc can bo multi-turn >= 40 case (gap ~3.3 lan hien tai) de mot case khong con doi duoc ket qua. Ghi kem hai phat hien lam thay doi cach doc so lieu: (1) --baseline cua run_eval.py truoc do noi hai lan chay theo CHUOI CAU HOI nen hai cach dien dat khong khop key, bao 'gained 8 lost 0' trong khi hit-rate TUT — da sua sang case_id on dinh va co test giu, neu tin ban dau thi DEC nay da ghi ket luan nguoc. (2) Gia thuyet R9 'multi-turn lam NO_CONTEXT_ANSWER bat ra thuong xuyen hon' la SAI o tang orchestrator: 0/12 cau hoi co dai tu tra ve 0 chunk, moi case deu du 5 chunk, nen nhanh short-circuit khong bao gio chay va bo dem qua log khong co gi de dem; loi tu choi that su den tu LLM va duong do khong sinh log (xem BL-015).

---
id: DEC-9
status: active
date: 2026-08-18
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-18T11:27:16.792856+00:00"
affects: "src/rag_chatbot_tung/retrieval/vector_search.py, scripts/migrate_collection.py, configs/default.yaml, docs/SETUP.md"
---

## DEC-9 — Chen hybrid retrieval vao giua P2 va P3 hardening — deviation co y thuc khoi thu tu DEC-3

DEC-3 chot thu tu thi cong P1 UI localhost -> P2 multi-turn -> P3 hardening -> moi mo internet. Hybrid retrieval (dense+BM25 RRF fusion, cross-encoder rerank, metadata adjustment) KHONG nam trong thu tu do: no la mot hang muc moi chen vao giua P2 va P3. DEC nay ghi nhan deviation thay vi de plan tu lat DEC-3. LY DO: nguoi dung chot pham vi dot nay gom ca phan A (multi-turn) lan phan B (hybrid retrieval), va tai gate phase 5 da xac nhan tiep tuc sang phase 6-10 SAU KHI nhin thay hai so lieu bat loi: (a) phase 2 do duoc hit-rate baseline da kich tran 97.37% nen fusion/rerank/metadata gan nhu khong the chung minh gia tri qua hit-rate — chi MRR 0.7215 va false_positive 4/7 con du dia (BL-013); (b) phase 5 voi n=12 chua ket luan duoc ve query-rewriting, tuc la phuong an RE HON phan B van chua bi loai (DEC-8). CAI BI DAY LUI: P3 hardening (auth qua reverse proxy, rate limit, siet CORS, tran chi tieu) lui lai sau toan bo phase 6-10. He thong van o localhost trong suot thoi gian do, dung theo DEC-3 — plan nay khong dung CORS, khong dung auth, khong doi port binding, khong them endpoint cong khai. CHI PHI DA BIET VA DUOC CHAP NHAN: (1) mot lan re-ingest TOAN BO vi doi schema collection tu vector khong ten sang vector co ten dense + sparse bm25 — khong co duong migrate tai cho, va nguon nap qua URL khong co ban sao tren dia se mat vinh vien; (2) dependency nang torch/sentence-transformers o phase 8, la dependency nang duy nhat cua ca repo tu truoc toi nay; (3) top_k mac dinh doi 3->5 o phase 9 lam tang ~67% token context moi truy van va KHONG nam sau cong tac nao. Giam nhe: moi tang moi ship voi cong tac mac dinh TAT (retriever.hybrid=false, rerank.provider=noop, metadata_adjust.enabled=false) nen merge duoc tung phase ma khong doi hanh vi production.

---
id: DEC-10
status: active
date: 2026-08-19
actor: "user:v.tungnt200@vinsmartfuture.tech"
ts: "2026-08-19T07:32:21.627515+00:00"
affects: "configs/default.yaml, src/rag_chatbot_tung/configs.py, docs/ARCHITECTURE.md, docs/system-architecture.md, README.md"
---

## DEC-10 — Ket luan phan B: bat hybrid fusion, de rerank va metadata TAT mac dinh

Bang dong gop tung tang, do tren CUNG bo eval / CUNG collection / CUNG lan ingest, ep --top-k 5 giong nhau cho moi dong (n=45 case, 38 co dap an, 7 lac de). BANG: (1) Baseline dense: hit 97.37%, MRR 0.721, p95 retrieval 3954ms; (2) +fusion: hit 100.00%, MRR 0.847, p95 3101ms; (3) +rerank cross-encoder: hit 97.37%, MRR 0.839, p95 3638ms; (4) +metadata (tren rerank): hit 100.00%, MRR 0.845, p95 4412ms. Do them cau hinh (5) +metadata KHONG rerank: hit 100.00%, MRR 0.844. false_positive = 4 va abstain_rate = 42.86% o CA NAM cau hinh — khong tang nao lam thay doi grounding. DICH CHUYEN THEO TUNG CASE (thu quan trong hon con so tong): baseline->fusion duoc 1 case ('Doi mo hinh sinh vector...'); fusion->rerank MAT 1 case khac ('Can bat nhung tien trinh nao...'); rerank->metadata duoc lai DUNG case ma rerank vua lam mat. Tuc la dong gop DUY NHAT do duoc cua metadata la va lai thiet hai cua rerank; khi rerank tat thi metadata khong con gi de va va con lam MRR tut nhe 0.847 -> 0.844. QUYET DINH: (a) RETRIEVER__HYBRID=true — BAT. Ly do bang so: +2.63 diem hit-rate, +0.126 MRR (+17.5%), khong lam tang false_positive, khong them mot dependency nao (Qdrant tinh IDF server-side), va p50 chi +12% (1007 -> 1128ms). (b) RERANK__PROVIDER=noop — GIU TAT. Ly do: lam XAU DI ca hai metric (hit -2.63 diem, MRR -0.008) trong khi doi +1.0GB dung luong (.venv 275M -> 1.3G, ban da la CPU-only) va +79% p50 latency (1128 -> 2021ms). Ship mot tang vo dung o trang thai bat la tra chi phi vinh vien cho mot cai thien khong ton tai. (c) METADATA_ADJUST__ENABLED=false — GIU TAT. Ly do: khong co dong gop doc lap do duoc; MRR 0.847 -> 0.844 khi bat tren fusion. NGUONG XET LAI: bat lai rerank khi VA CHI KHI (1) bo eval du lon de hit-rate khong con kich tran — hien 100% sau fusion nen khong con cho do; hoac (2) doi sang mot cross-encoder da fine-tune cho tieng Viet, va do lai bang chinh bang nay. Bat lai metadata khi corpus co nhieu tai lieu chong lan hon va xuat hien cau hoi can doi chieu hai nguon ma panel nguon cho thay bi mot tai lieu chiem het. GHI CHU: hit-rate da kich tran 100% sau fusion nen no khong con kha nang phan biet cac tang; moi danh gia ve sau phai dung MRR va false_positive lam cot chinh (xem BL-013). Image size cua target runtime-rerank KHONG DO DUOC: docker daemon thieu root CA nen khong keo duoc base image (can sudo); image runtime hien tai 448MB.
