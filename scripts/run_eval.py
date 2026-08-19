"""Measure retrieval hit-rate and MRR against a golden Q&A set."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rag_chatbot_tung.configs import get_settings
from rag_chatbot_tung.evaluate.metrics import EvalReport, evaluate_retrieval, load_cases
from rag_chatbot_tung.logging import setup_logging
from rag_chatbot_tung.orchestrator import RAGOrchestrator


def _print_report(report: EvalReport, top_k: int) -> None:
    print(f"top_k          : {top_k}")
    print(
        f"cases          : {report.total} "
        f"({report.scored} scored, {report.offtopic_total} off-topic)"
    )
    print(f"hit rate       : {report.hit_rate:.2%}")
    print(f"MRR            : {report.mrr:.3f}")
    if report.offtopic_total:
        print(f"abstain rate   : {report.abstain_rate:.2%}")
        print(f"false positive : {report.false_positive}")


def _print_score_distribution(report: EvalReport, threshold: float) -> None:
    """Answer 'how much does score_threshold actually filter?' with numbers.

    This has to be read before fusion changes what the score even means.
    """
    scores = [s for r in report.results for s in r.scores]
    if not scores:
        print("scores         : none returned")
        return

    scores.sort()
    lowest = scores[0]
    print(f"scores         : n={len(scores)} min={lowest:.4f} max={scores[-1]:.4f}")
    print(f"                 median={scores[len(scores) // 2]:.4f} threshold={threshold}")
    print(f"                 margin above threshold at the weakest hit: {lowest - threshold:+.4f}")


def _diff_against_baseline(report: EvalReport, baseline_path: Path) -> None:
    """Show which cases flipped, not just whether the total moved.

    An unchanged hit-rate with five cases swapping direction is information the
    headline number erases completely.
    """
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    # Keyed on case_id, not on the question text: a pronoun run and a self-contained
    # run of the same set embed different strings but are the same cases.
    was = {r.get("case_id", r["question"]): r["hit"] for r in baseline.get("results", [])}

    gained = [r.case_id for r in report.results if r.hit and not was.get(r.case_id, False)]
    lost = [r.case_id for r in report.results if not r.hit and was.get(r.case_id, False)]
    unseen = [r.case_id for r in report.results if r.case_id not in was]

    print()
    print(f"baseline       : {baseline_path}")
    print(f"  hit rate     : {baseline.get('hit_rate', 0.0):.2%} -> {report.hit_rate:.2%}")
    print(f"  MRR          : {baseline.get('mrr', 0.0):.3f} -> {report.mrr:.3f}")
    print(f"  gained ({len(gained)}):")
    for q in gained:
        print(f"    + {q}")
    print(f"  lost ({len(lost)}):")
    for q in lost:
        print(f"    - {q}")
    if unseen:
        print(f"  not in baseline ({len(unseen)}) — comparison covers the overlap only")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("data/eval/qa.jsonl"))
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--out", type=Path, default=None, help="write the report as JSON")
    parser.add_argument("--baseline", type=Path, default=None, help="diff against a saved report")
    parser.add_argument(
        "--selfcontained",
        action="store_true",
        help="use the pronoun-free phrasing of each case (multi-turn A/B)",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    top_k = args.top_k or settings.retriever.top_k
    report = evaluate_retrieval(
        RAGOrchestrator(settings),
        load_cases(args.cases),
        args.top_k,
        selfcontained=args.selfcontained,
    )

    _print_report(report, top_k)
    _print_score_distribution(report, settings.retriever.score_threshold)

    if args.baseline:
        _diff_against_baseline(report, args.baseline)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        payload = report.to_dict()
        payload["top_k"] = top_k
        payload["score_threshold"] = settings.retriever.score_threshold
        payload["cases_file"] = str(args.cases)
        payload["selfcontained"] = args.selfcontained
        args.out.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
