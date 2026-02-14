from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    INTERNAL = "internal"
    ERP = "erp"
    PSP = "psp"


class RunStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FORMAT_FAILED = "format_failed"
    FAILED = "failed"


class FinalStatus(str, Enum):
    GOOD = "good_transaction"
    DOUBTFUL = "doubtful_transaction"


class ReconciliationRun(BaseModel):
    id: str
    status: RunStatus = RunStatus.DRAFT
    stage: str = "created"
    initiated_by: str
    created_at: datetime
    updated_at: datetime
    counters: dict[str, int] = Field(default_factory=lambda: {
        "total": 0,
        "good": 0,
        "doubtful": 0,
        "exceptions": 0,
    })


class SourceFileRecord(BaseModel):
    id: str
    run_id: str
    source_type: SourceType
    format_type: str
    filename: str
    checksum: str
    parse_status: str = "pending"
    mapping_json: dict[str, str] | None = None


class NormalizedTransaction(BaseModel):
    psp_txn_id: str
    merchant_ref: str
    gross_amount: float
    currency: str
    processing_fee: float
    net_payout: float
    transaction_date: str
    settlement_date: str
    client_id: str
    client_name: str
    description: str
    status: str
    payment_method: str
    settlement_bank: str
    bank_country: str
    fx_rate: float | None = None


class ReconcileJobRequest(BaseModel):
    run_id: str


class StageResult(BaseModel):
    exact_hash: bool = False
    fuzzy: bool = False
    three_way: bool = False
    backdated: bool = False
    fx_handled: bool = False


class MatchDecision(BaseModel):
    run_id: str
    merchant_ref: str
    final_status: FinalStatus
    reason_codes: list[str]
    stage_results: StageResult
    transaction_month: str | None = None
    fuzzy_score: float | None = None
    backdated_gap_days: int | None = None
    fx_detail: str | None = None
    trace_json: dict[str, Any] | None = None


class ExceptionCase(BaseModel):
    id: str
    run_id: str
    merchant_ref: str
    severity: str
    reason_codes: list[str]
    state: str = "open"


class AIReviewStep(BaseModel):
    exception_id: str
    stage: str
    confidence: float
    output_json: dict[str, Any]


class AnnouncementItem(BaseModel):
    id: str
    run_id: str
    level: str
    title: str
    message: str
    payload_json: dict[str, Any] = Field(default_factory=dict)


class MonthlyAlertRecipient(BaseModel):
    recipient_key: str
    recipient_label: str
    reason: str
    count: int = 0
    merchant_refs: list[str] = Field(default_factory=list)


class MonthlyDoubtfulDetail(BaseModel):
    merchant_ref: str
    state: str
    reason_codes: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    recipients: list[str] = Field(default_factory=list)


class MonthlySubmissionSummary(BaseModel):
    run_id: str
    month: str
    total_transactions: int = 0
    good_transactions: int = 0
    doubtful_transactions: int = 0
    addressed_doubtful: int = 0
    unresolved_doubtful: int = 0
    ready_for_submission: bool = False
    notified_to_source: bool = False
    journal_created: bool = False
    submitted_to_erp: bool = False
    next_action: str = "collect_transactions"
    notified_at: str | None = None
    journal_created_at: str | None = None
    submitted_at: str | None = None
    alert_recipients: list[MonthlyAlertRecipient] = Field(default_factory=list)
    doubtful_details: list[MonthlyDoubtfulDetail] = Field(default_factory=list)


class DailyNotificationTarget(BaseModel):
    recipient_key: str
    recipient_label: str
    count: int = 0
    merchant_refs: list[str] = Field(default_factory=list)


class DailyOpsSummary(BaseModel):
    run_id: str
    run_status: str
    business_date: str
    total_transactions: int = 0
    good_transactions: int = 0
    doubtful_transactions: int = 0
    unresolved_doubtful: int = 0
    addressed_doubtful: int = 0
    notifications_required: int = 0
    notifications_sent: int = 0
    close_state: str = "open"  # open | ready_to_close | closed
    next_action: str = "address_doubtful"
    closed_at: str | None = None
    notification_targets: list[DailyNotificationTarget] = Field(default_factory=list)
    monthly_items: list[MonthlySubmissionSummary] = Field(default_factory=list)


class MonthlyCloseBatch(BaseModel):
    month: str
    source_run_ids: list[str] = Field(default_factory=list)
    source_run_count: int = 0
    total_transactions: int = 0
    good_transactions: int = 0
    doubtful_transactions: int = 0
    ready_for_erp: bool = False
    journal_created: bool = False
    submitted_to_erp: bool = False
    next_action: str = "wait_for_daily_close"  # wait_for_daily_close | create_journal | submit_to_erp | completed
    journal_created_at: str | None = None
    submitted_at: str | None = None


class RunSummary(BaseModel):
    run: ReconciliationRun
    decisions: list[MatchDecision]
    exceptions: list[ExceptionCase]
    monthly_submissions: list[MonthlySubmissionSummary] = Field(default_factory=list)
    daily_ops: DailyOpsSummary | None = None
