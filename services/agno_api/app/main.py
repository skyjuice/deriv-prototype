from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auto_download import run_download
from .schemas import AnnouncementItem, DailyOpsSummary, MonthlyCloseBatch, ReconcileJobRequest, ReconciliationRun, RunSummary, SourceType
from .service import execute_reconciliation, queue_reconciliation
from .storage import storage

app = FastAPI(title="Reconciliation Agno API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateRunRequest(BaseModel):
    initiated_by: str = "analyst"


class ExceptionActionRequest(BaseModel):
    action: str


class RemoteFetchRequest(BaseModel):
    source_type: SourceType
    url: str


class AutoDownloadRequest(BaseModel):
    source_type: SourceType = SourceType.PSP
    task: str | None = None


class FeedbackRequest(BaseModel):
    user_id: str = "analyst"
    stage: str = "supervisor"
    feedback_type: str
    reason_codes: list[str] = []
    edited_action: str | None = None
    comment: str | None = None


class DailyBusinessDateRequest(BaseModel):
    business_date: str


class ChatHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatQueryRequest(BaseModel):
    question: str
    run_id: str | None = None
    history: list[ChatHistoryTurn] = Field(default_factory=list)


def _announce_monthly_action(run_id: str, level: str, title: str, message: str, payload: dict[str, Any]) -> None:
    item = AnnouncementItem(
        id=str(uuid4()),
        run_id=run_id,
        level=level,
        title=title,
        message=message,
        payload_json=payload,
    )
    storage.add_announcements(run_id, [item])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "ts": datetime.now(timezone.utc).isoformat()}


@app.post("/v1/runs", response_model=ReconciliationRun)
def create_run(payload: CreateRunRequest) -> ReconciliationRun:
    return storage.create_run(payload.initiated_by)


@app.get("/v1/runs")
def list_runs() -> dict[str, Any]:
    return {"runs": [r.model_dump(mode="json") for r in storage.list_runs()]}


@app.get("/v1/runs/{run_id}", response_model=ReconciliationRun)
def get_run(run_id: str) -> ReconciliationRun:
    try:
        return storage.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.post("/v1/runs/{run_id}/files")
async def upload_run_file(run_id: str, source_type: SourceType, file: UploadFile = File(...)) -> dict[str, Any]:
    payload = await file.read()
    rec = storage.save_source_file(run_id=run_id, source_type=source_type, filename=file.filename or "upload.bin", payload=payload)
    return {"file": rec.model_dump(mode="json")}


@app.post("/v1/runs/{run_id}/fetch-remote")
async def fetch_remote_file(run_id: str, body: RemoteFetchRequest) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(body.url)
        resp.raise_for_status()
    filename = body.url.rsplit("/", 1)[-1] or "remote.csv"
    rec = storage.save_source_file(run_id=run_id, source_type=body.source_type, filename=filename, payload=resp.content)
    return {"file": rec.model_dump(mode="json")}


@app.post("/v1/runs/{run_id}/auto-download")
async def auto_download_run_file(run_id: str, body: AutoDownloadRequest) -> dict[str, Any]:
    try:
        storage.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc

    try:
        downloaded_path = await run_download(task=body.task)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"auto download failed: {exc}") from exc

    if not downloaded_path:
        raise HTTPException(status_code=400, detail="auto download did not produce a file")

    local_path = Path(downloaded_path)
    if not local_path.exists() or not local_path.is_file():
        raise HTTPException(status_code=400, detail=f"downloaded file not found: {downloaded_path}")

    payload = local_path.read_bytes()
    rec = storage.save_source_file(
        run_id=run_id,
        source_type=body.source_type,
        filename=local_path.name,
        payload=payload,
    )
    return {"file": rec.model_dump(mode="json"), "downloaded_path": downloaded_path}


@app.post("/v1/jobs/reconcile")
def enqueue_reconcile_job(payload: ReconcileJobRequest) -> dict[str, str]:
    try:
        return queue_reconciliation(payload.run_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/jobs/reconcile/{run_id}/execute")
def execute_job_inline(run_id: str) -> dict[str, Any]:
    try:
        result = execute_reconciliation(run_id)
        return {"run": result.run.model_dump(mode="json"), "summary": result.summary}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/format/check-and-fix")
async def format_check_and_fix(file: UploadFile = File(...)) -> dict[str, Any]:
    from .formatting import parse_tabular_bytes, parse_pdf_bytes, standardize_frame

    payload = await file.read()
    ext = (file.filename or "").split(".")[-1].lower()
    if ext in {"csv", "xlsx"}:
        df = parse_tabular_bytes(payload, ext)
    elif ext == "pdf":
        df = parse_pdf_bytes(payload)
    else:
        raise HTTPException(status_code=400, detail=f"unsupported file extension: {ext}")

    _, result = standardize_frame(df)
    return {
        "ok": result.ok,
        "confidence": result.confidence,
        "mapping": result.mapping,
        "reason": result.reason,
    }


@app.get("/v1/jobs/{run_id}", response_model=RunSummary)
def get_job_summary(run_id: str) -> RunSummary:
    try:
        run = storage.get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc

    decisions = storage.get_decisions(run_id)
    exceptions = storage.get_exceptions(run_id)
    monthly_submissions = storage.list_monthly_submissions(run_id)
    try:
        daily_ops = storage.get_daily_ops(run_id)
    except KeyError:
        daily_ops = None
    return RunSummary(run=run, decisions=decisions, exceptions=exceptions, monthly_submissions=monthly_submissions, daily_ops=daily_ops)


@app.get("/v1/runs/{run_id}/transactions/{merchant_ref}")
def get_run_transaction_source_snapshot(run_id: str, merchant_ref: str) -> dict[str, Any]:
    try:
        return storage.get_transaction_source_snapshot(run_id=run_id, merchant_ref=merchant_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="run not found") from exc


@app.get("/v1/daily-ops")
def list_daily_ops() -> dict[str, Any]:
    return {"items": [row.model_dump(mode="json") for row in storage.list_daily_ops()]}


@app.get("/v1/daily-ops/{run_id}", response_model=DailyOpsSummary)
def get_daily_ops(run_id: str) -> DailyOpsSummary:
    try:
        return storage.get_daily_ops(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="daily run not found") from exc


@app.post("/v1/daily-ops/{run_id}/business-date", response_model=DailyOpsSummary)
def set_daily_business_date(run_id: str, body: DailyBusinessDateRequest) -> DailyOpsSummary:
    try:
        return storage.set_daily_business_date(run_id, body.business_date, actor="analyst")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="daily run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/daily-ops/{run_id}/address-doubtful", response_model=DailyOpsSummary)
def address_daily_doubtful(run_id: str) -> DailyOpsSummary:
    try:
        summary = storage.address_daily_doubtful(run_id, actor="analyst")
        _announce_monthly_action(
            run_id,
            "doubtful",
            "Daily doubtful review completed",
            "Doubtful transactions were addressed and moved to verified for notification handling.",
            {"run_id": run_id, "next_action": summary.next_action},
        )
        return summary
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="daily run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/daily-ops/{run_id}/notify", response_model=DailyOpsSummary)
def notify_daily_ops(run_id: str) -> DailyOpsSummary:
    try:
        summary = storage.notify_daily_ops(run_id, actor="analyst")
        _announce_monthly_action(
            run_id,
            "doubtful",
            "Daily notification batch sent",
            "Notifications were sent to PSP and backoffice counterparties for non-tally items.",
            {
                "run_id": run_id,
                "notifications_required": summary.notifications_required,
                "notifications_sent": summary.notifications_sent,
                "notification_targets": [item.model_dump(mode="json") for item in summary.notification_targets],
            },
        )
        return summary
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="daily run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/daily-ops/{run_id}/close", response_model=DailyOpsSummary)
def close_daily_ops(run_id: str) -> DailyOpsSummary:
    try:
        summary = storage.close_daily_ops(run_id, actor="supervisor")
        _announce_monthly_action(
            run_id,
            "good",
            "Daily run closed",
            "Daily BAU checks are complete. This run is now eligible for monthly close aggregation.",
            {"run_id": run_id, "closed_at": summary.closed_at},
        )
        return summary
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="daily run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/monthly-close")
def list_monthly_close() -> dict[str, Any]:
    return {"items": [row.model_dump(mode="json") for row in storage.list_monthly_close_batches()]}


@app.get("/v1/monthly-close/{month}", response_model=MonthlyCloseBatch)
def get_monthly_close(month: str) -> MonthlyCloseBatch:
    try:
        return storage.get_monthly_close_batch(month)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly batch not found") from exc


@app.post("/v1/monthly-close/{month}/journal", response_model=MonthlyCloseBatch)
def create_monthly_close_journal(month: str) -> MonthlyCloseBatch:
    try:
        batch = storage.create_monthly_close_journal(month, actor="supervisor")
        _announce_monthly_action(
            "monthly-close",
            "good",
            "Monthly close journal created",
            f"{month}: consolidated journal prepared from daily-closed runs.",
            {"month": month, "source_run_ids": batch.source_run_ids},
        )
        return batch
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly batch not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/monthly-close/{month}/submit", response_model=MonthlyCloseBatch)
def submit_monthly_close(month: str) -> MonthlyCloseBatch:
    try:
        batch = storage.submit_monthly_close_to_erp(month, actor="admin")
        _announce_monthly_action(
            "monthly-close",
            "good",
            "Monthly close submitted to ERP",
            f"{month}: consolidated monthly batch submitted to ERP.",
            {"month": month, "source_run_ids": batch.source_run_ids, "submitted_to_erp": batch.submitted_to_erp},
        )
        return batch
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly batch not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/monthly-close/{month}/revert", response_model=MonthlyCloseBatch)
def revert_monthly_close_submission(month: str) -> MonthlyCloseBatch:
    try:
        batch = storage.revert_monthly_close_submission(month, actor="admin")
        _announce_monthly_action(
            "monthly-close",
            "doubtful",
            "Monthly close submission reverted",
            f"{month}: ERP submission was reverted and returned to journal creation stage.",
            {"month": month, "next_action": batch.next_action},
        )
        return batch
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly batch not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/runs/{run_id}/monthly-submissions")
def get_monthly_submissions(run_id: str) -> dict[str, Any]:
    return {"items": [row.model_dump(mode="json") for row in storage.list_monthly_submissions(run_id)]}


@app.post("/v1/runs/{run_id}/monthly-submissions/{month}/address-doubtful")
def address_monthly_doubtful(run_id: str, month: str) -> dict[str, Any]:
    try:
        summary = storage.address_monthly_doubtful(run_id, month, actor="analyst")
        _announce_monthly_action(
            run_id,
            "doubtful",
            "Monthly doubtful transactions addressed",
            f"{month}: doubtful exceptions were moved to verified for monthly processing.",
            {
                "month": month,
                "next_action": summary.next_action,
                "doubtful_details": [item.model_dump(mode="json") for item in summary.doubtful_details],
            },
        )
        return {"item": summary.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly bucket not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/runs/{run_id}/monthly-submissions/{month}/notify")
def notify_monthly_sources(run_id: str, month: str) -> dict[str, Any]:
    try:
        summary = storage.mark_monthly_notified(run_id, month, actor="analyst")
        _announce_monthly_action(
            run_id,
            "doubtful",
            "Monthly notification sent",
            f"{month}: notification sent to PSP/backoffice/internal owners for doubtful items.",
            {
                "month": month,
                "next_action": summary.next_action,
                "alert_recipients": [item.model_dump(mode="json") for item in summary.alert_recipients],
                "doubtful_details": [item.model_dump(mode="json") for item in summary.doubtful_details],
            },
        )
        return {"item": summary.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly bucket not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/runs/{run_id}/monthly-submissions/{month}/journal")
def create_monthly_journal(run_id: str, month: str) -> dict[str, Any]:
    try:
        summary = storage.create_monthly_journal(run_id, month, actor="supervisor")
        _announce_monthly_action(
            run_id,
            "good",
            "Journal prepared for ERP",
            f"{month}: journal has been created and is ready for ERP submission.",
            {"month": month, "next_action": summary.next_action},
        )
        return {"item": summary.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly bucket not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/runs/{run_id}/monthly-submissions/{month}/submit")
def submit_monthly_to_erp(run_id: str, month: str) -> dict[str, Any]:
    try:
        summary = storage.submit_monthly_to_erp(run_id, month, actor="admin")
        _announce_monthly_action(
            run_id,
            "good",
            "Monthly submission sent to ERP",
            f"{month}: transaction pool submitted to ERP financial accounting.",
            {"month": month, "submitted_to_erp": summary.submitted_to_erp},
        )
        return {"item": summary.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="monthly bucket not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/runs/{run_id}/exceptions")
def get_run_exceptions(run_id: str) -> dict[str, Any]:
    return {"exceptions": [e.model_dump(mode="json") for e in storage.get_exceptions(run_id)]}


@app.post("/v1/exceptions/{exception_id}/actions")
def action_exception(exception_id: str, body: ExceptionActionRequest) -> dict[str, Any]:
    try:
        updated = storage.update_exception_state(exception_id, body.action)
        return {"exception": updated.model_dump(mode="json")}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="exception not found") from exc


@app.post("/v1/exceptions/{exception_id}/review")
def review_exception(exception_id: str) -> dict[str, Any]:
    from .ai import run_ai_review_chain

    try:
        target = storage.get_exception_by_id(exception_id)
        reviews = run_ai_review_chain(target)
        storage.add_reviews(exception_id, reviews)
        return {"reviews": [r.model_dump(mode="json") for r in reviews]}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="exception not found") from exc


@app.get("/v1/exceptions/{exception_id}/reviews")
def list_exception_reviews(exception_id: str) -> dict[str, Any]:
    return {"reviews": [r.model_dump(mode="json") for r in storage.get_reviews(exception_id)]}


@app.post("/v1/exceptions/{exception_id}/feedback")
def submit_exception_feedback(exception_id: str, body: FeedbackRequest) -> dict[str, Any]:
    try:
        payload = storage.add_feedback(
            exception_id=exception_id,
            user_id=body.user_id,
            stage=body.stage,
            feedback_type=body.feedback_type,
            reason_codes=body.reason_codes,
            edited_action=body.edited_action,
            comment=body.comment,
        )
        return {"feedback": payload}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="exception not found") from exc


@app.get("/v1/feedback/metrics")
def feedback_metrics() -> dict[str, Any]:
    return storage.feedback_metrics()


@app.get("/v1/inbox")
def list_inbox() -> dict[str, Any]:
    items = storage.list_announcements()
    return {"items": [i.model_dump(mode="json") for i in sorted(items, key=lambda x: x.id, reverse=True)]}


@app.post("/v1/chat/query")
async def query_chat(body: ChatQueryRequest) -> dict[str, Any]:
    from .ai import answer_data_question

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    if body.run_id:
        try:
            storage.get_run(body.run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run not found") from exc

    context = storage.build_chat_context(run_id=body.run_id)
    history = [item.model_dump(mode="json") for item in body.history]
    reply = await answer_data_question(question, context, history=history)
    return {
        "answer": reply.get("answer", ""),
        "source": reply.get("source", "fallback"),
        "model": reply.get("model"),
        "context_meta": context.get("summary", {}),
    }
