"""Measure retrieval hit-rate and MRR against a golden Q&A set."""

from __future__ import annotations

import argparse
from pathlib import Path

from rag_chatbot_tung.configs import get_settings
from rag_chatbot_tung.evaluate.metrics import evaluate_retrieval, load_cases
from rag_chatbot_tung.logging import setup_logging
from rag_chatbot_tung.orchestrator import RAGOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=Path("data/eval/qa.jsonl"))
    parser.add_argument("--top-k", type=int, default=None)
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    report = evaluate_retrieval(RAGOrchestrator(settings), load_cases(args.cases), args.top_k)
    print(f"cases     : {report.total}")
    print(f"hit rate  : {report.hit_rate:.2%}")
    print(f"MRR       : {report.mrr:.3f}")


if __name__ == "__main__":
    main()
