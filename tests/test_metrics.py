from __future__ import annotations

import json

import pytest

from rag_chatbot_tung.configs import PROJECT_ROOT
from rag_chatbot_tung.evaluate.metrics import EvalCase, EvalReport, evaluate_retrieval, load_cases

# The autouse `away_from_dotenv` fixture chdirs into tmp_path, so a relative path here
# would resolve against the temp dir and silently read nothing. Anchor on the package
# instead — a test that goes red for the wrong reason is worse than no test.
EVAL_DIR = PROJECT_ROOT / "data" / "eval"
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"

MIN_CASES = 40
MIN_SOURCES = 6
MIN_MULTITURN_CASES = 10
MIN_OFFTOPIC_CASES = 6


def _write_jsonl(path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )


def _read_jsonl(path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_load_cases_reads_legacy_schema(tmp_path):
    """The pre-existing two-key schema must keep loading untouched."""
    path = tmp_path / "legacy.jsonl"
    _write_jsonl(
        path,
        [
            {"question": "What embedding model is used?", "expected_source": "sample_faq.txt"},
            {"question": "Where are vectors stored?", "expected_source": "sample_faq.txt"},
        ],
    )

    cases = load_cases(path)

    assert len(cases) == 2
    assert cases[0].question == "What embedding model is used?"
    assert cases[0].expected_source == "sample_faq.txt"
    # The new fields must default rather than be required, or every existing row breaks.
    assert cases[0].question_selfcontained is None
    assert cases[0].history == []


def test_load_cases_reads_multiturn_schema(tmp_path):
    path = tmp_path / "multiturn.jsonl"
    _write_jsonl(
        path,
        [
            {
                "question": "Nó lưu vector ở đâu?",
                "question_selfcontained": "Hệ thống lưu vector ở đâu?",
                "expected_source": "sample_faq.txt",
                "history": [
                    {"role": "user", "content": "Hệ thống dùng cơ sở dữ liệu nào?"},
                    {"role": "assistant", "content": "Qdrant được dùng làm vector store."},
                ],
            }
        ],
    )

    cases = load_cases(path)

    assert len(cases) == 1
    case = cases[0]
    assert case.question == "Nó lưu vector ở đâu?"
    assert case.question_selfcontained == "Hệ thống lưu vector ở đâu?"
    assert case.expected_source == "sample_faq.txt"
    assert len(case.history) == 2
    assert case.history[0]["role"] == "user"
    assert case.history[1]["content"] == "Qdrant được dùng làm vector store."


def test_load_cases_reads_offtopic_case_with_null_source(tmp_path):
    """`expected_source: null` marks an off-topic case: retrieving nothing is correct."""
    path = tmp_path / "offtopic.jsonl"
    _write_jsonl(path, [{"question": "Giá vé máy bay đi Paris?", "expected_source": None}])

    cases = load_cases(path)

    assert cases[0].expected_source is None


def test_report_records_per_case_detail(orchestrator, pipeline, sample_txt):
    """Per-case scores/sources are what makes two eval runs comparable."""
    pipeline.ingest_file(sample_txt)
    cases = [EvalCase(question="What database is used?", expected_source=sample_txt.name)]

    report = evaluate_retrieval(orchestrator, cases)

    assert len(report.results) == len(cases)
    result = report.results[0]
    assert result.question == "What database is used?"
    assert result.sources, "a retrieved chunk must record its source"
    assert result.scores, "a retrieved chunk must record its real score"
    assert len(result.scores) == len(result.sources)
    assert all(isinstance(s, float) for s in result.scores)


def test_report_records_miss_with_rank_none(orchestrator, pipeline, sample_txt):
    pipeline.ingest_file(sample_txt)
    cases = [EvalCase(question="What database is used?", expected_source="does_not_exist.txt")]

    report = evaluate_retrieval(orchestrator, cases)

    assert report.hits == 0
    assert report.hit_rate == 0.0
    result = report.results[0]
    assert result.hit is False
    assert result.rank is None


def test_offtopic_case_scores_abstain_and_false_positive(orchestrator, pipeline, sample_txt):
    """Hit-rate is blind to junk returned for an off-topic question; these counters are not.

    Phase 7 must hold false_positive at 0 once BM25 joins the query path.
    """
    pipeline.ingest_file(sample_txt)
    cases = [EvalCase(question="Giá vé máy bay đi Paris?", expected_source=None)]

    report = evaluate_retrieval(orchestrator, cases)

    # Off-topic cases must not pollute the hit-rate denominator.
    assert report.total == 1
    assert report.abstain_correct + report.false_positive == 1


def test_hit_rate_and_mrr_on_empty_case_list(orchestrator):
    report = evaluate_retrieval(orchestrator, [])

    assert report.total == 0
    assert report.hit_rate == 0.0
    assert report.mrr == 0.0
    assert report.results == []


def test_eval_dataset_files_are_wellformed():
    """Turns R1 (a 6-case eval proves nothing) into a machine-checkable condition."""
    qa_path = EVAL_DIR / "qa.jsonl"
    assert qa_path.exists(), f"missing {qa_path}"

    records = _read_jsonl(qa_path)
    assert len(records) >= MIN_CASES, f"need >={MIN_CASES} cases, found {len(records)}"

    sources = {r["expected_source"] for r in records if r["expected_source"] is not None}
    assert (
        len(sources) >= MIN_SOURCES
    ), f"need >={MIN_SOURCES} distinct sources, found {len(sources)}"

    offtopic = [r for r in records if r["expected_source"] is None]
    assert (
        len(offtopic) >= MIN_OFFTOPIC_CASES
    ), f"need >={MIN_OFFTOPIC_CASES} off-topic cases, found {len(offtopic)}"

    for record in records:
        assert record["question"].strip(), "every case needs a non-empty question"
        assert set(record) <= {"question", "expected_source", "question_selfcontained", "history"}


def test_multiturn_dataset_is_wellformed():
    path = EVAL_DIR / "qa_multiturn.jsonl"
    assert path.exists(), f"missing {path}"

    records = _read_jsonl(path)
    assert len(records) >= MIN_MULTITURN_CASES

    for record in records:
        # The pronoun/self-contained pair IS the measurement mechanism of phase 5;
        # a case missing either half contributes nothing to that A/B.
        assert record["question"].strip()
        assert record["question_selfcontained"].strip()
        assert record["question"] != record["question_selfcontained"]
        assert record["history"], "history must not be empty"
        for turn in record["history"]:
            assert turn["role"] in {"user", "assistant"}
            assert turn["content"].strip()


@pytest.mark.parametrize("filename", ["qa.jsonl", "qa_multiturn.jsonl"])
def test_every_expected_source_exists_on_disk(filename):
    """A typo in a source name reads as 'bad retrieval' and costs hours of wrong tuning."""
    records = _read_jsonl(EVAL_DIR / filename)
    referenced = {r["expected_source"] for r in records if r["expected_source"] is not None}

    missing = sorted(name for name in referenced if not (DOCUMENTS_DIR / name).exists())

    assert not missing, f"{filename} references sources absent from data/documents/: {missing}"


def test_eval_dataset_text_is_nfc_normalised():
    """Ingest normalises to NFKC (utils/text.py) but questions are embedded raw.

    For dense vectors an NFC/NFD split only nudges the vector; for the phase 7 BM25
    tokenizer they are different terms outright, so the dataset is pinned to NFC here.
    """
    import unicodedata

    for filename in ("qa.jsonl", "qa_multiturn.jsonl"):
        for record in _read_jsonl(EVAL_DIR / filename):
            question = record["question"]
            assert question == unicodedata.normalize(
                "NFC", question
            ), f"{filename}: question is not NFC-normalised: {question!r}"


def test_report_exposes_serialisable_payload(orchestrator, pipeline, sample_txt):
    """--out/--baseline diffing needs the report to round-trip through JSON."""
    pipeline.ingest_file(sample_txt)
    cases = [EvalCase(question="What database is used?", expected_source=sample_txt.name)]

    report: EvalReport = evaluate_retrieval(orchestrator, cases)
    payload = report.to_dict()

    assert payload["total"] == 1
    assert payload["hit_rate"] == report.hit_rate
    assert payload["mrr"] == report.mrr
    assert len(payload["results"]) == 1
    json.dumps(payload)  # must not raise


def test_case_id_is_stable_across_phrasings(orchestrator, pipeline, sample_txt):
    """A pronoun run and a self-contained run must share a key.

    Without this the --baseline diff joins on the embedded question text, finds no
    overlap between the two runs, and reports every case as "gained" while the
    hit-rate visibly falls — a diff that contradicts its own headline.
    """
    pipeline.ingest_file(sample_txt)
    cases = [
        EvalCase(
            question="Nó lưu ở đâu?",
            question_selfcontained="Hệ thống lưu vector ở đâu?",
            expected_source=sample_txt.name,
        )
    ]

    pronoun = evaluate_retrieval(orchestrator, cases)
    selfcontained = evaluate_retrieval(orchestrator, cases, selfcontained=True)

    assert pronoun.results[0].question != selfcontained.results[0].question
    assert pronoun.results[0].case_id == selfcontained.results[0].case_id == "Nó lưu ở đâu?"
