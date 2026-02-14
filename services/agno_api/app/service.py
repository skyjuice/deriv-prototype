from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from redis import Redis
from rq import Queue

from .ai import build_announcements, run_ai_review_chain
from .config import settings
from .formatting import parse_any_file, standardize_frame
from .reconciliation import reconcile
from .schemas import ReconciliationRun, RunStatus
from .storage import storage


@dataclass
class RunExecutionResult:
    run: ReconciliationRun
    summary: dict[str, Any]


def _redis_queue() -> Queue | None:
    try:
        conn = Redis.from_url(settings.redis_url)
        conn.ping()
        return Queue("recon", connection=conn)
    except Exception:
        return None


def execute_reconciliation(run_id: str) -> RunExecutionResult:
    run = storage.get_run(run_id)
    run.status = RunStatus.RUNNING
    run.stage = "loading_sources"
    storage.update_run(run)

    files = storage.list_run_files(run_id)
    by_source = {f["source_type"]: f for f in files}
    required = {"internal", "erp", "psp"}
    missing = required - set(by_source)
    if missing:
        run.status = RunStatus.FAILED
        run.stage = f"missing_sources:{','.join(sorted(missing))}"
        storage.update_run(run)
        raise ValueError(run.stage)

    parsed: dict[str, Any] = {}
    for source in ["internal", "erp", "psp"]:
        f = by_source[source]
        run.stage = f"parsing_{source}"
        storage.update_run(run)
        df = parse_any_file(f["path"], f["format_type"])
        standardized, result = standardize_frame(df)
        if not result.ok:
            run.status = RunStatus.FORMAT_FAILED
            run.stage = f"format_failed_{source}:{result.reason}"
            storage.update_run(run)
            raise ValueError(run.stage)
        parsed[source] = standardized

    run.stage = "reconciling"
    storage.update_run(run)
    validation = reconcile(run_id, parsed["internal"], parsed["erp"], parsed["psp"])

    storage.add_decisions(run_id, validation.decisions)
    storage.add_exceptions(run_id, validation.exceptions)

    for exc in validation.exceptions:
        reviews = run_ai_review_chain(exc)
        storage.add_reviews(exc.id, reviews)

    announcements = build_announcements(run_id, validation.decisions, validation.exceptions)
    storage.add_announcements(run_id, announcements)

    run.status = RunStatus.COMPLETED
    run.stage = "completed"
    run.counters = {
        "total": len(validation.decisions),
        "good": sum(1 for d in validation.decisions if d.final_status.value == "good_transaction"),
        "doubtful": sum(1 for d in validation.decisions if d.final_status.value == "doubtful_transaction"),
        "exceptions": len(validation.exceptions),
    }
    storage.update_run(run)

    return RunExecutionResult(
        run=run,
        summary={
            "decisions": len(validation.decisions),
            "exceptions": len(validation.exceptions),
        },
    )


def queue_reconciliation(run_id: str) -> dict[str, str]:
    run = storage.get_run(run_id)
    run.status = RunStatus.QUEUED
    run.stage = "queued"
    storage.update_run(run)

    queue = _redis_queue()
    if queue is None:
        # fallback for local mode without Redis
        execute_reconciliation(run_id)
        return {"job_id": f"local-{run_id}", "mode": "inline"}

    job = queue.enqueue("app.service.execute_reconciliation", run_id, job_timeout=600)
    return {"job_id": job.id, "mode": "queued"}
