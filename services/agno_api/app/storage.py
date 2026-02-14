from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from .config import settings
from .schemas import (
    AIReviewStep,
    AnnouncementItem,
    DailyNotificationTarget,
    DailyOpsSummary,
    ExceptionCase,
    MatchDecision,
    MonthlyCloseBatch,
    MonthlyAlertRecipient,
    MonthlyDoubtfulDetail,
    MonthlySubmissionSummary,
    ReconciliationRun,
    RunStatus,
    SourceFileRecord,
    SourceType,
)

RECIPIENT_LABELS = {
    "psp_provider": "PSP Provider",
    "internal_backoffice": "Internal Backoffice",
    "cashier_erp": "Cashier (ERP)",
    "reconciliation_ops": "Reconciliation Ops",
}

RECIPIENT_REASONS = {
    "psp_provider": "Missing or inconsistent PSP statement entry.",
    "internal_backoffice": "Missing or inconsistent internal backoffice record.",
    "cashier_erp": "Missing or inconsistent ERP/cashier record.",
    "reconciliation_ops": "General reconciliation mismatch requiring review.",
}


class Storage:
    def __init__(self) -> None:
        self.base = Path(settings.storage_dir)
        self.base.mkdir(parents=True, exist_ok=True)
        self.file_dir = self.base / "files"
        self.file_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.base / "db.json"
        if not self.data_file.exists():
            self._save(
                {
                    "runs": {},
                    "files": {},
                    "decisions": {},
                    "exceptions": {},
                    "reviews": {},
                    "monthly_submissions": {},
                    "daily_ops": {},
                    "monthly_close": {},
                    "ai_feedback": [],
                    "announcements": {},
                    "audit_events": [],
                }
            )

    def _load(self) -> dict[str, Any]:
        payload = json.loads(self.data_file.read_text())
        changed = False
        for key, default in {
            "runs": {},
            "files": {},
            "decisions": {},
            "exceptions": {},
            "reviews": {},
            "monthly_submissions": {},
            "daily_ops": {},
            "monthly_close": {},
            "ai_feedback": [],
            "announcements": {},
            "audit_events": [],
        }.items():
            if key not in payload:
                payload[key] = default
                changed = True
        if changed:
            self._save(payload)
        return payload

    def _save(self, payload: dict[str, Any]) -> None:
        self.data_file.write_text(json.dumps(payload, indent=2, default=str))

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def create_run(self, initiated_by: str) -> ReconciliationRun:
        data = self._load()
        run_id = str(uuid.uuid4())
        now = self.now()
        run = ReconciliationRun(
            id=run_id,
            initiated_by=initiated_by,
            created_at=now,
            updated_at=now,
            status=RunStatus.DRAFT,
            stage="created",
        )
        data["runs"][run_id] = run.model_dump(mode="json")
        self._audit(data, initiated_by, "create_run", "reconciliation_run", run_id, None, run.model_dump(mode="json"))
        self._save(data)
        return run

    def get_run(self, run_id: str) -> ReconciliationRun:
        data = self._load()
        if run_id not in data["runs"]:
            raise KeyError(run_id)
        return ReconciliationRun(**data["runs"][run_id])

    def list_runs(self) -> list[ReconciliationRun]:
        data = self._load()
        runs = [ReconciliationRun(**row) for row in data["runs"].values()]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs

    def update_run(self, run: ReconciliationRun, actor: str = "system") -> ReconciliationRun:
        data = self._load()
        prev = data["runs"].get(run.id)
        run.updated_at = self.now()
        data["runs"][run.id] = run.model_dump(mode="json")
        self._audit(data, actor, "update_run", "reconciliation_run", run.id, prev, run.model_dump(mode="json"))
        self._save(data)
        return run

    def save_source_file(self, run_id: str, source_type: SourceType, filename: str, payload: bytes) -> SourceFileRecord:
        data = self._load()
        file_id = str(uuid.uuid4())
        checksum = hashlib.sha256(payload).hexdigest()
        ext = filename.split(".")[-1].lower()
        physical_name = f"{file_id}_{filename}"
        file_path = self.file_dir / physical_name
        file_path.write_bytes(payload)

        rec = SourceFileRecord(
            id=file_id,
            run_id=run_id,
            source_type=source_type,
            format_type=ext,
            filename=filename,
            checksum=checksum,
            parse_status="pending",
        )
        item = rec.model_dump(mode="json")
        item["path"] = str(file_path)
        data["files"][file_id] = item
        self._audit(data, "system", "upload_file", "source_file", file_id, None, item)
        self._save(data)
        return rec

    def list_run_files(self, run_id: str) -> list[dict[str, Any]]:
        data = self._load()
        return [f for f in data["files"].values() if f["run_id"] == run_id]

    def _ensure_month_state(self, data: dict[str, Any], run_id: str, month: str) -> dict[str, Any]:
        state_by_run = data["monthly_submissions"].setdefault(run_id, {})
        if month not in state_by_run:
            state_by_run[month] = {
                "notified_to_source": False,
                "journal_created": False,
                "submitted_to_erp": False,
            }
        return state_by_run[month]

    def _monthly_index(self, data: dict[str, Any], run_id: str) -> tuple[dict[str, dict[str, int]], dict[str, set[str]]]:
        stats: dict[str, dict[str, int]] = {}
        refs_by_month: dict[str, set[str]] = {}
        exceptions = {
            str(item["merchant_ref"]): str(item.get("state", "open")).lower()
            for item in data["exceptions"].get(run_id, [])
        }
        addressed_states = {"verified", "approved", "resolved"}

        for row in data["decisions"].get(run_id, []):
            decision = MatchDecision(**row)
            month = decision.transaction_month or "unknown"
            if month not in stats:
                stats[month] = {
                    "total_transactions": 0,
                    "good_transactions": 0,
                    "doubtful_transactions": 0,
                    "addressed_doubtful": 0,
                    "unresolved_doubtful": 0,
                }
            refs_by_month.setdefault(month, set()).add(decision.merchant_ref)

            stats[month]["total_transactions"] += 1
            if decision.final_status.value == "good_transaction":
                stats[month]["good_transactions"] += 1
                continue

            stats[month]["doubtful_transactions"] += 1
            if exceptions.get(decision.merchant_ref, "open") in addressed_states:
                stats[month]["addressed_doubtful"] += 1
            else:
                stats[month]["unresolved_doubtful"] += 1

        return stats, refs_by_month

    def _derive_alert_recipients(self, missing_sources: list[str], reason_codes: list[str]) -> list[str]:
        recipients: set[str] = set()
        if "psp" in missing_sources:
            recipients.add("psp_provider")
        if "internal" in missing_sources:
            recipients.add("internal_backoffice")
        if "erp" in missing_sources:
            recipients.add("cashier_erp")
        if not recipients:
            recipients.add("reconciliation_ops")
        return sorted(recipients)

    def _build_monthly_summaries_from_data(self, data: dict[str, Any], run_id: str) -> list[MonthlySubmissionSummary]:
        stats, _ = self._monthly_index(data, run_id)
        exception_state_by_ref = {
            str(item["merchant_ref"]): str(item.get("state", "open")).lower()
            for item in data["exceptions"].get(run_id, [])
        }
        details_by_month: dict[str, list[MonthlyDoubtfulDetail]] = {}
        recipients_by_month: dict[str, dict[str, set[str]]] = {}

        for row in data["decisions"].get(run_id, []):
            decision = MatchDecision(**row)
            if decision.final_status.value != "doubtful_transaction":
                continue

            month = decision.transaction_month or "unknown"
            trace = decision.trace_json or {}
            raw_sources = trace.get("sources_present", {})
            missing_sources: list[str] = []
            if isinstance(raw_sources, dict):
                for source in ("internal", "erp", "psp"):
                    if raw_sources.get(source) is False:
                        missing_sources.append(source)

            recipients = self._derive_alert_recipients(missing_sources, decision.reason_codes)
            detail = MonthlyDoubtfulDetail(
                merchant_ref=decision.merchant_ref,
                state=exception_state_by_ref.get(decision.merchant_ref, "open"),
                reason_codes=decision.reason_codes,
                missing_sources=missing_sources,
                recipients=recipients,
            )
            details_by_month.setdefault(month, []).append(detail)

            target = recipients_by_month.setdefault(month, {})
            for recipient in recipients:
                target.setdefault(recipient, set()).add(decision.merchant_ref)

        state_by_month = data["monthly_submissions"].get(run_id, {})
        months = sorted(set(stats.keys()) | set(state_by_month.keys()))
        out: list[MonthlySubmissionSummary] = []

        for month in months:
            row = stats.get(
                month,
                {
                    "total_transactions": 0,
                    "good_transactions": 0,
                    "doubtful_transactions": 0,
                    "addressed_doubtful": 0,
                    "unresolved_doubtful": 0,
                },
            )
            state = state_by_month.get(month, {})
            ready_for_submission = row["total_transactions"] > 0 and row["unresolved_doubtful"] == 0
            notified_to_source = bool(state.get("notified_to_source", False))
            journal_created = bool(state.get("journal_created", False))
            submitted_to_erp = bool(state.get("submitted_to_erp", False))
            doubtful_details = details_by_month.get(month, [])
            alert_recipients = [
                MonthlyAlertRecipient(
                    recipient_key=recipient,
                    recipient_label=RECIPIENT_LABELS.get(recipient, recipient),
                    reason=RECIPIENT_REASONS.get(recipient, "Reconciliation discrepancy found."),
                    count=len(refs),
                    merchant_refs=sorted(refs),
                )
                for recipient, refs in sorted(recipients_by_month.get(month, {}).items(), key=lambda x: len(x[1]), reverse=True)
            ]

            if submitted_to_erp:
                next_action = "completed"
            elif not ready_for_submission:
                next_action = "address_doubtful"
            elif row["doubtful_transactions"] > 0 and not notified_to_source:
                next_action = "notify_sources"
            elif row["good_transactions"] > 0 and not journal_created:
                next_action = "create_journal"
            else:
                next_action = "submit_to_erp"

            out.append(
                MonthlySubmissionSummary(
                    run_id=run_id,
                    month=month,
                    total_transactions=row["total_transactions"],
                    good_transactions=row["good_transactions"],
                    doubtful_transactions=row["doubtful_transactions"],
                    addressed_doubtful=row["addressed_doubtful"],
                    unresolved_doubtful=row["unresolved_doubtful"],
                    ready_for_submission=ready_for_submission,
                    notified_to_source=notified_to_source,
                    journal_created=journal_created,
                    submitted_to_erp=submitted_to_erp,
                    next_action=next_action,
                    notified_at=state.get("notified_at"),
                    journal_created_at=state.get("journal_created_at"),
                    submitted_at=state.get("submitted_at"),
                    alert_recipients=alert_recipients,
                    doubtful_details=doubtful_details,
                )
            )

        return out

    def list_monthly_submissions(self, run_id: str) -> list[MonthlySubmissionSummary]:
        data = self._load()
        return self._build_monthly_summaries_from_data(data, run_id)

    def get_monthly_submission(self, run_id: str, month: str) -> MonthlySubmissionSummary:
        data = self._load()
        for summary in self._build_monthly_summaries_from_data(data, run_id):
            if summary.month == month:
                return summary
        raise KeyError(month)

    def address_monthly_doubtful(self, run_id: str, month: str, actor: str = "system") -> MonthlySubmissionSummary:
        data = self._load()
        stats, refs_by_month = self._monthly_index(data, run_id)
        if month not in stats and month not in data["monthly_submissions"].get(run_id, {}):
            raise KeyError(month)

        target_refs = refs_by_month.get(month, set())
        updated = 0
        for run_key, items in data["exceptions"].items():
            if run_key != run_id:
                continue
            for idx, item in enumerate(items):
                if str(item.get("merchant_ref")) in target_refs and str(item.get("state", "open")).lower() not in {"verified", "approved", "resolved"}:
                    item["state"] = "verified"
                    items[idx] = item
                    updated += 1
            data["exceptions"][run_key] = items

        state = self._ensure_month_state(data, run_id, month)
        state["doubtful_addressed_at"] = self.now().isoformat()
        self._audit(
            data,
            actor,
            "monthly_address_doubtful",
            "monthly_submission",
            f"{run_id}:{month}",
            None,
            {"month": month, "updated_exceptions": updated},
        )
        self._save(data)
        return self.get_monthly_submission(run_id, month)

    def mark_monthly_notified(self, run_id: str, month: str, actor: str = "system") -> MonthlySubmissionSummary:
        data = self._load()
        summary = None
        for row in self._build_monthly_summaries_from_data(data, run_id):
            if row.month == month:
                summary = row
                break
        if summary is None:
            raise KeyError(month)
        if summary.doubtful_transactions == 0:
            raise ValueError("no doubtful transactions to notify")

        state = self._ensure_month_state(data, run_id, month)
        before = dict(state)
        state["notified_to_source"] = True
        state["notified_at"] = self.now().isoformat()
        self._audit(
            data,
            actor,
            "monthly_notify_sources",
            "monthly_submission",
            f"{run_id}:{month}",
            before,
            state,
        )
        self._save(data)
        return self.get_monthly_submission(run_id, month)

    def create_monthly_journal(self, run_id: str, month: str, actor: str = "system") -> MonthlySubmissionSummary:
        data = self._load()
        summary = None
        for row in self._build_monthly_summaries_from_data(data, run_id):
            if row.month == month:
                summary = row
                break
        if summary is None:
            raise KeyError(month)
        if not summary.ready_for_submission:
            raise ValueError("monthly submission is not ready; resolve doubtful transactions first")
        if summary.good_transactions <= 0:
            raise ValueError("no good transactions available to create journal")

        state = self._ensure_month_state(data, run_id, month)
        before = dict(state)
        state["journal_created"] = True
        state["journal_created_at"] = self.now().isoformat()
        self._audit(
            data,
            actor,
            "monthly_create_journal",
            "monthly_submission",
            f"{run_id}:{month}",
            before,
            state,
        )
        self._save(data)
        return self.get_monthly_submission(run_id, month)

    def submit_monthly_to_erp(self, run_id: str, month: str, actor: str = "system") -> MonthlySubmissionSummary:
        data = self._load()
        summary = None
        for row in self._build_monthly_summaries_from_data(data, run_id):
            if row.month == month:
                summary = row
                break
        if summary is None:
            raise KeyError(month)
        if not summary.ready_for_submission:
            raise ValueError("monthly submission is not ready; resolve doubtful transactions first")

        state = self._ensure_month_state(data, run_id, month)
        if summary.good_transactions > 0 and not bool(state.get("journal_created", False)):
            raise ValueError("create journal before submitting to ERP")

        before = dict(state)
        state["submitted_to_erp"] = True
        state["submitted_at"] = self.now().isoformat()
        self._audit(
            data,
            actor,
            "monthly_submit_erp",
            "monthly_submission",
            f"{run_id}:{month}",
            before,
            state,
        )
        self._save(data)
        return self.get_monthly_submission(run_id, month)

    def _ensure_daily_state(self, data: dict[str, Any], run_id: str) -> dict[str, Any]:
        state = data["daily_ops"].setdefault(run_id, {})
        if "closed_at" not in state:
            state["closed_at"] = None
        if "business_date" not in state:
            state["business_date"] = None
        return state

    def _run_business_date(self, data: dict[str, Any], run_id: str) -> str:
        state = data["daily_ops"].get(run_id, {})
        business_date = str(state.get("business_date") or "").strip()
        if business_date:
            return business_date

        run_row = data["runs"].get(run_id, {})
        created_at = str(run_row.get("created_at", ""))
        if len(created_at) >= 10:
            return created_at[:10]

        months = sorted(
            {
                (row.get("transaction_month") or "unknown")
                for row in data["decisions"].get(run_id, [])
            }
        )
        real_months = [month for month in months if month != "unknown"]
        if len(real_months) == 1:
            return f"{real_months[0]}-01"
        return "unknown"

    def _build_daily_ops_summary_from_data(self, data: dict[str, Any], run_id: str) -> DailyOpsSummary:
        run_row = data["runs"].get(run_id)
        if not run_row:
            raise KeyError(run_id)
        run = ReconciliationRun(**run_row)
        monthly_items = self._build_monthly_summaries_from_data(data, run_id)

        total_transactions = sum(item.total_transactions for item in monthly_items)
        good_transactions = sum(item.good_transactions for item in monthly_items)
        doubtful_transactions = sum(item.doubtful_transactions for item in monthly_items)
        unresolved_doubtful = sum(item.unresolved_doubtful for item in monthly_items)
        addressed_doubtful = sum(item.addressed_doubtful for item in monthly_items)
        notifications_required = sum(1 for item in monthly_items if item.doubtful_transactions > 0)
        notifications_sent = sum(1 for item in monthly_items if item.doubtful_transactions > 0 and item.notified_to_source)

        recipient_map: dict[str, set[str]] = {}
        recipient_label: dict[str, str] = {}
        for item in monthly_items:
            for target in item.alert_recipients:
                key = target.recipient_key
                recipient_label[key] = target.recipient_label
                refs = recipient_map.setdefault(key, set())
                refs.update(target.merchant_refs)

        notification_targets = [
            DailyNotificationTarget(
                recipient_key=key,
                recipient_label=recipient_label.get(key, RECIPIENT_LABELS.get(key, key)),
                count=len(refs),
                merchant_refs=sorted(refs),
            )
            for key, refs in sorted(recipient_map.items(), key=lambda x: len(x[1]), reverse=True)
        ]

        state = self._ensure_daily_state(data, run_id)
        closed_at = state.get("closed_at")

        if closed_at:
            close_state = "closed"
            next_action = "closed"
        elif run.status.value != "completed":
            close_state = "open"
            next_action = "wait_run_completion"
        elif unresolved_doubtful > 0:
            close_state = "open"
            next_action = "address_doubtful"
        elif notifications_sent < notifications_required:
            close_state = "open"
            next_action = "send_notifications"
        else:
            close_state = "ready_to_close"
            next_action = "close_day"

        return DailyOpsSummary(
            run_id=run_id,
            run_status=run.status.value,
            business_date=self._run_business_date(data, run_id),
            total_transactions=total_transactions,
            good_transactions=good_transactions,
            doubtful_transactions=doubtful_transactions,
            unresolved_doubtful=unresolved_doubtful,
            addressed_doubtful=addressed_doubtful,
            notifications_required=notifications_required,
            notifications_sent=notifications_sent,
            close_state=close_state,
            next_action=next_action,
            closed_at=closed_at,
            notification_targets=notification_targets,
            monthly_items=monthly_items,
        )

    def list_daily_ops(self) -> list[DailyOpsSummary]:
        data = self._load()
        runs = [ReconciliationRun(**row) for row in data["runs"].values()]
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return [self._build_daily_ops_summary_from_data(data, run.id) for run in runs]

    def get_daily_ops(self, run_id: str) -> DailyOpsSummary:
        data = self._load()
        return self._build_daily_ops_summary_from_data(data, run_id)

    def set_daily_business_date(self, run_id: str, business_date: str, actor: str = "system") -> DailyOpsSummary:
        data = self._load()
        if run_id not in data["runs"]:
            raise KeyError(run_id)
        try:
            datetime.fromisoformat(business_date)
        except Exception as exc:
            raise ValueError("business_date must be YYYY-MM-DD") from exc

        state = self._ensure_daily_state(data, run_id)
        before = dict(state)
        state["business_date"] = business_date
        self._audit(data, actor, "daily_set_business_date", "daily_ops", run_id, before, state)
        self._save(data)
        return self.get_daily_ops(run_id)

    def address_daily_doubtful(self, run_id: str, actor: str = "system") -> DailyOpsSummary:
        rows = self.list_monthly_submissions(run_id)
        target_months = [row.month for row in rows if row.unresolved_doubtful > 0]
        if not target_months:
            return self.get_daily_ops(run_id)
        for month in target_months:
            self.address_monthly_doubtful(run_id, month, actor=actor)
        return self.get_daily_ops(run_id)

    def notify_daily_ops(self, run_id: str, actor: str = "system") -> DailyOpsSummary:
        rows = self.list_monthly_submissions(run_id)
        target_months: list[str] = []
        for row in rows:
            if row.doubtful_transactions <= 0 or row.notified_to_source:
                continue
            if row.unresolved_doubtful > 0:
                raise ValueError(f"month {row.month} still has unresolved doubtful transactions")
            target_months.append(row.month)
        if not target_months:
            return self.get_daily_ops(run_id)
        for month in target_months:
            self.mark_monthly_notified(run_id, month, actor=actor)
        return self.get_daily_ops(run_id)

    def close_daily_ops(self, run_id: str, actor: str = "system") -> DailyOpsSummary:
        data = self._load()
        summary = self._build_daily_ops_summary_from_data(data, run_id)
        if summary.close_state != "ready_to_close":
            raise ValueError(f"run not ready to close: {summary.next_action}")

        state = self._ensure_daily_state(data, run_id)
        before = dict(state)
        state["closed_at"] = self.now().isoformat()
        self._audit(
            data,
            actor,
            "daily_close",
            "daily_ops",
            run_id,
            before,
            state,
        )

        run = ReconciliationRun(**data["runs"][run_id])
        run.stage = "daily_closed"
        run.updated_at = self.now()
        data["runs"][run_id] = run.model_dump(mode="json")
        self._save(data)
        return self.get_daily_ops(run_id)

    def _ensure_monthly_close_state(self, data: dict[str, Any], month: str) -> dict[str, Any]:
        state = data["monthly_close"].setdefault(month, {})
        if "journal_created" not in state:
            state["journal_created"] = False
        if "submitted_to_erp" not in state:
            state["submitted_to_erp"] = False
        return state

    def _build_monthly_close_batches_from_data(self, data: dict[str, Any]) -> list[MonthlyCloseBatch]:
        aggregates: dict[str, dict[str, Any]] = {}
        runs = [ReconciliationRun(**row) for row in data["runs"].values()]
        runs.sort(key=lambda r: r.created_at)

        for run in runs:
            daily = self._build_daily_ops_summary_from_data(data, run.id)
            if daily.close_state != "closed":
                continue
            for month_item in daily.monthly_items:
                month = month_item.month
                bucket = aggregates.setdefault(
                    month,
                    {
                        "source_run_ids": set(),
                        "total_transactions": 0,
                        "good_transactions": 0,
                        "doubtful_transactions": 0,
                        "unresolved_doubtful": 0,
                    },
                )
                bucket["source_run_ids"].add(run.id)
                bucket["total_transactions"] += month_item.total_transactions
                bucket["good_transactions"] += month_item.good_transactions
                bucket["doubtful_transactions"] += month_item.doubtful_transactions
                bucket["unresolved_doubtful"] += month_item.unresolved_doubtful

        months = sorted(set(aggregates.keys()) | set(data["monthly_close"].keys()))
        out: list[MonthlyCloseBatch] = []
        for month in months:
            state = data["monthly_close"].get(month, {})
            bucket = aggregates.get(
                month,
                {
                    "source_run_ids": set(),
                    "total_transactions": 0,
                    "good_transactions": 0,
                    "doubtful_transactions": 0,
                    "unresolved_doubtful": 0,
                },
            )
            source_run_ids = sorted(bucket["source_run_ids"])
            source_run_count = len(source_run_ids)
            ready_for_erp = source_run_count > 0 and bucket["unresolved_doubtful"] == 0
            journal_created = bool(state.get("journal_created", False))
            submitted_to_erp = bool(state.get("submitted_to_erp", False))
            if submitted_to_erp:
                next_action = "completed"
            elif not ready_for_erp:
                next_action = "wait_for_daily_close"
            elif not journal_created:
                next_action = "create_journal"
            else:
                next_action = "submit_to_erp"

            out.append(
                MonthlyCloseBatch(
                    month=month,
                    source_run_ids=source_run_ids,
                    source_run_count=source_run_count,
                    total_transactions=bucket["total_transactions"],
                    good_transactions=bucket["good_transactions"],
                    doubtful_transactions=bucket["doubtful_transactions"],
                    ready_for_erp=ready_for_erp,
                    journal_created=journal_created,
                    submitted_to_erp=submitted_to_erp,
                    next_action=next_action,
                    journal_created_at=state.get("journal_created_at"),
                    submitted_at=state.get("submitted_at"),
                )
            )

        return out

    def list_monthly_close_batches(self) -> list[MonthlyCloseBatch]:
        data = self._load()
        return self._build_monthly_close_batches_from_data(data)

    def get_monthly_close_batch(self, month: str) -> MonthlyCloseBatch:
        data = self._load()
        for batch in self._build_monthly_close_batches_from_data(data):
            if batch.month == month:
                return batch
        raise KeyError(month)

    def create_monthly_close_journal(self, month: str, actor: str = "system") -> MonthlyCloseBatch:
        data = self._load()
        batch = None
        for row in self._build_monthly_close_batches_from_data(data):
            if row.month == month:
                batch = row
                break
        if batch is None:
            raise KeyError(month)
        if not batch.ready_for_erp:
            raise ValueError("monthly close is not ready; close all daily runs and clear doubtfuls first")
        if batch.good_transactions <= 0:
            raise ValueError("no good transactions available to create journal")

        state = self._ensure_monthly_close_state(data, month)
        before = dict(state)
        state["journal_created"] = True
        state["journal_created_at"] = self.now().isoformat()
        self._audit(data, actor, "monthly_close_create_journal", "monthly_close", month, before, state)
        self._save(data)
        return self.get_monthly_close_batch(month)

    def submit_monthly_close_to_erp(self, month: str, actor: str = "system") -> MonthlyCloseBatch:
        data = self._load()
        batch = None
        for row in self._build_monthly_close_batches_from_data(data):
            if row.month == month:
                batch = row
                break
        if batch is None:
            raise KeyError(month)
        if not batch.ready_for_erp:
            raise ValueError("monthly close is not ready; close all daily runs and clear doubtfuls first")

        state = self._ensure_monthly_close_state(data, month)
        if batch.good_transactions > 0 and not bool(state.get("journal_created", False)):
            raise ValueError("create monthly journal before submitting to ERP")

        before = dict(state)
        state["submitted_to_erp"] = True
        state["submitted_at"] = self.now().isoformat()
        self._audit(data, actor, "monthly_close_submit_erp", "monthly_close", month, before, state)
        self._save(data)
        return self.get_monthly_close_batch(month)

    def add_decisions(self, run_id: str, decisions: list[MatchDecision]) -> None:
        data = self._load()
        data["decisions"][run_id] = [d.model_dump(mode="json") for d in decisions]
        for decision in decisions:
            self._ensure_month_state(data, run_id, decision.transaction_month or "unknown")
        self._save(data)

    def get_decisions(self, run_id: str) -> list[MatchDecision]:
        data = self._load()
        return [MatchDecision(**d) for d in data["decisions"].get(run_id, [])]

    def add_exceptions(self, run_id: str, exceptions: list[ExceptionCase]) -> None:
        data = self._load()
        data["exceptions"][run_id] = [e.model_dump(mode="json") for e in exceptions]
        self._save(data)

    def get_exceptions(self, run_id: str) -> list[ExceptionCase]:
        data = self._load()
        return [ExceptionCase(**e) for e in data["exceptions"].get(run_id, [])]

    def get_exception_by_id(self, exception_id: str) -> ExceptionCase:
        data = self._load()
        for items in data["exceptions"].values():
            for item in items:
                if item["id"] == exception_id:
                    return ExceptionCase(**item)
        raise KeyError(exception_id)

    def update_exception_state(self, exception_id: str, action: str) -> ExceptionCase:
        data = self._load()
        for run_id, items in data["exceptions"].items():
            for idx, item in enumerate(items):
                if item["id"] == exception_id:
                    item["state"] = action
                    items[idx] = item
                    data["exceptions"][run_id] = items
                    self._audit(data, "system", "exception_action", "exception", exception_id, None, item)
                    self._save(data)
                    return ExceptionCase(**item)
        raise KeyError(exception_id)

    def add_reviews(self, exception_id: str, reviews: list[AIReviewStep]) -> None:
        data = self._load()
        data["reviews"][exception_id] = [r.model_dump(mode="json") for r in reviews]
        self._save(data)

    def get_reviews(self, exception_id: str) -> list[AIReviewStep]:
        data = self._load()
        return [AIReviewStep(**r) for r in data["reviews"].get(exception_id, [])]

    def add_feedback(
        self,
        exception_id: str,
        user_id: str,
        stage: str,
        feedback_type: str,
        reason_codes: list[str] | None = None,
        edited_action: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        data = self._load()
        target = self.get_exception_by_id(exception_id)
        payload = {
            "id": str(uuid.uuid4()),
            "exception_id": exception_id,
            "run_id": target.run_id,
            "user_id": user_id,
            "stage": stage,
            "feedback_type": feedback_type,
            "reason_codes": reason_codes or [],
            "edited_action": edited_action,
            "comment": comment,
            "created_at": self.now().isoformat(),
        }
        data["ai_feedback"].append(payload)
        self._audit(data, user_id, "ai_feedback", "exception", exception_id, None, payload)
        self._save(data)
        return payload

    def list_feedback(self, run_id: str | None = None) -> list[dict[str, Any]]:
        data = self._load()
        rows = data["ai_feedback"]
        if run_id:
            rows = [row for row in rows if row["run_id"] == run_id]
        return rows

    def feedback_metrics(self) -> dict[str, Any]:
        rows = self.list_feedback()
        total = len(rows)
        by_type: dict[str, int] = {}
        reject_reasons: dict[str, int] = {}
        for row in rows:
            feedback_type = row.get("feedback_type", "unknown")
            by_type[feedback_type] = by_type.get(feedback_type, 0) + 1
            if feedback_type == "reject":
                for reason in row.get("reason_codes", []):
                    reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
        accepted = by_type.get("accept", 0)
        acceptance_rate = round((accepted / total) * 100, 2) if total else 0.0
        top_reject_reasons = sorted(reject_reasons.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "total_feedback": total,
            "acceptance_rate": acceptance_rate,
            "by_type": by_type,
            "top_reject_reasons": [{"reason": k, "count": v} for k, v in top_reject_reasons],
        }

    def add_announcements(self, run_id: str, items: list[AnnouncementItem]) -> None:
        data = self._load()
        existing = data["announcements"].get(run_id, [])
        existing.extend([a.model_dump(mode="json") for a in items])
        data["announcements"][run_id] = existing
        self._save(data)

    def list_announcements(self) -> list[AnnouncementItem]:
        data = self._load()
        out: list[AnnouncementItem] = []
        for rows in data["announcements"].values():
            out.extend(AnnouncementItem(**r) for r in rows)
        return out

    def _audit(
        self,
        data: dict[str, Any],
        actor: str,
        action: str,
        entity_type: str,
        entity_id: str,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
    ) -> None:
        data["audit_events"].append(
            {
                "id": str(uuid.uuid4()),
                "actor_id": actor,
                "action": action,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "before_json": before,
                "after_json": after,
                "timestamp": self.now().isoformat(),
            }
        )

    async def try_write_pocketbase_health(self) -> None:
        if not settings.pocketbase_url:
            return
        headers = {}
        if settings.pocketbase_admin_token:
            headers["Authorization"] = settings.pocketbase_admin_token
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(f"{settings.pocketbase_url}/api/health", headers=headers)


storage = Storage()
