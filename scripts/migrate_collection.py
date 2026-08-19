"""Rebuild the Qdrant collection with the hybrid schema and re-ingest every source.

There is no in-place migration from unnamed vectors to named dense+sparse ones, so
this deletes the collection and loads it again from disk. That makes this the only
script here that can destroy data, which is why it refuses to run by default, snapshots
before it touches anything, and verifies itself afterwards with an exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from rag_chatbot_tung.configs import get_settings
from rag_chatbot_tung.logging import setup_logging
from rag_chatbot_tung.orchestrator import RAGOrchestrator

SNAPSHOT_DIR = Path("data/eval")
SNAPSHOT_PREFIX = "migration-snapshot-"
# Written immediately before the destructive step and removed only on success. Finding
# one on startup means a previous run died partway through.
MARKER = SNAPSHOT_DIR / "migration-in-progress.json"


def _snapshot_path(now: datetime) -> Path:
    return SNAPSHOT_DIR / f"{SNAPSHOT_PREFIX}{now.strftime('%Y%m%dT%H%M%SZ')}.json"


def _open_snapshots() -> list[Path]:
    """Snapshots from runs that never completed, oldest first."""
    return sorted(p for p in SNAPSHOT_DIR.glob(f"{SNAPSHOT_PREFIX}*.json") if not _is_closed(p))


def _is_closed(path: Path) -> bool:
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("closed"))
    except (OSError, json.JSONDecodeError):
        return False


def _read_state(orchestrator: RAGOrchestrator) -> dict:
    sources = orchestrator.vector_store.list_sources()
    return {
        "taken": datetime.now(UTC).isoformat(),
        "closed": False,
        "points_count": orchestrator.collection_info().points_count,
        "sources": [{"source": s.source, "chunks": s.chunks} for s in sources],
    }


def _write_snapshot(snapshot: dict, path: Path) -> None:
    if path.exists():
        # Overwriting is how the safety net destroys itself: a re-run after a crash
        # would record the post-crash state as the baseline and then "verify" against
        # it successfully while sources stayed lost.
        raise SystemExit(f"refusing to overwrite an existing snapshot: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _schema_is_hybrid(orchestrator: RAGOrchestrator) -> bool:
    store = orchestrator.vector_store
    if not store._client.collection_exists(store.collection):
        return False
    vectors = store._client.get_collection(store.collection).config.params.vectors
    return isinstance(vectors, dict) and "dense" in vectors


def _locate_on_disk(source: str, dirs: list[Path]) -> Path | None:
    for directory in dirs:
        candidate = directory / source
        if candidate.is_file():
            return candidate
    return None


def _report_recoverability(snapshot: dict, dirs: list[Path]) -> list[str]:
    missing = [
        entry["source"]
        for entry in snapshot["sources"]
        if _locate_on_disk(entry["source"], dirs) is None
    ]
    print(f"sources in index : {len(snapshot['sources'])}")
    print(f"points in index  : {snapshot['points_count']}")
    print(f"recoverable      : {len(snapshot['sources']) - len(missing)}")
    if missing:
        print(f"NOT on disk ({len(missing)}) — these are lost if you continue:")
        for name in missing:
            # Sources ingested by URL have no local copy; this is the real hole in the
            # rollback path, so it is stated rather than discovered afterwards.
            print(f"  ! {name}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="report only, touch nothing (default)",
    )
    parser.add_argument("--yes", action="store_true", help="actually delete and rebuild")
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="continue even though sources are absent from disk and will be lost",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    orchestrator = RAGOrchestrator(settings)
    dirs = [settings.storage.documents_dir, settings.storage.upload_dir]

    # Resume only on evidence that a destructive run actually started: the marker, or
    # an open snapshot sitting next to an already-migrated collection. An open snapshot
    # on its own is not evidence — otherwise a dry-run would make every later run
    # resume against a stale baseline.
    resuming = MARKER.exists() or (_schema_is_hybrid(orchestrator) and bool(_open_snapshots()))
    if resuming:
        open_snapshots = _open_snapshots()
        if not open_snapshots:
            raise SystemExit(
                "an in-progress marker exists but no open snapshot was found — refusing "
                "to guess the baseline. Inspect data/eval/ by hand."
            )
        # The OLDEST open snapshot is the true pre-migration state; a newer one would
        # already reflect whatever the interrupted run managed to destroy.
        snapshot_path = open_snapshots[0]
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        print(f"RESUMING against the earlier snapshot: {snapshot_path}")
        print("(a previous run did not finish; its baseline is used, not a fresh reading)")
    else:
        snapshot_path = _snapshot_path(datetime.now(UTC))
        snapshot = _read_state(orchestrator)

    missing = _report_recoverability(snapshot, dirs)

    if not args.yes:
        # Deliberately no snapshot file here: a dry-run must leave no state behind.
        print("\ndry run — nothing was modified.")
        print("Re-run with --yes to delete and rebuild the collection.")
        return 0

    if missing and not args.allow_missing:
        print("\nABORTED: sources above are not on disk and could not be restored.")
        print("Re-run with --allow-missing only if you accept losing them.")
        return 1

    if not resuming:
        _write_snapshot(snapshot, snapshot_path)
        print(f"snapshot written : {snapshot_path}")

    MARKER.write_text(
        json.dumps({"started": datetime.now(UTC).isoformat(), "snapshot": str(snapshot_path)})
        + "\n",
        encoding="utf-8",
    )

    print("\ndeleting collection...")
    orchestrator.vector_store._client.delete_collection(orchestrator.vector_store.collection)
    orchestrator.startup()

    # Re-ingest exactly what the snapshot recorded, never whole directories.
    # DELETE /documents drops the vectors but leaves the uploaded file on disk, so a
    # directory sweep would silently resurrect every document the user ever deleted —
    # and change the corpus the eval baselines were measured against.
    for entry in snapshot["sources"]:
        source = entry["source"]
        path = _locate_on_disk(source, dirs)
        if path is None:
            print(f"  ! {source}: not on disk, skipped")
            continue
        print(f"  {source}: {orchestrator.pipeline.ingest_file(path)} chunks")

    after_points = orchestrator.collection_info().points_count
    after_sources = {s.source for s in orchestrator.vector_store.list_sources()}
    lost = [e["source"] for e in snapshot["sources"] if e["source"] not in after_sources]

    print(f"\npoints  : {snapshot['points_count']} -> {after_points}")
    print(f"sources : {len(snapshot['sources'])} -> {len(after_sources)}")

    # A larger count is fine — data/documents/ may hold files that were never ingested.
    # Only a shrink, or a source that failed to come back, means the migration lost data.
    if after_points < snapshot["points_count"] or lost:
        print("\nFAILED: the collection did not come back intact.")
        for name in lost:
            print(f"  missing after migration: {name}")
        print(f"The snapshot is kept at {snapshot_path} — re-run to resume.")
        return 1

    snapshot["closed"] = True
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    MARKER.unlink(missing_ok=True)
    print("\nmigration verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
