"""Ingest every supported document under data/documents/ into Qdrant."""

from __future__ import annotations

import argparse
from pathlib import Path

from rag_chatbot_tung.configs import get_settings
from rag_chatbot_tung.logging import setup_logging
from rag_chatbot_tung.orchestrator import RAGOrchestrator


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=None, help="directory to ingest")
    parser.add_argument("--url", action="append", default=[], help="URL to ingest (repeatable)")
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)

    orchestrator = RAGOrchestrator(settings)
    orchestrator.startup()

    for source, count in orchestrator.ingest_directory(args.dir).items():
        print(f"{source}: {count} chunks")

    for url in args.url:
        print(f"{url}: {orchestrator.pipeline.ingest_url(url)} chunks")

    print(f"collection now holds {orchestrator.collection_info().points_count} points")


if __name__ == "__main__":
    main()
