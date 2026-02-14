from __future__ import annotations

import uuid
from datetime import datetime, timezone

from .schemas import AIReviewStep, AnnouncementItem, ExceptionCase, MatchDecision


def run_ai_review_chain(exception: ExceptionCase) -> list[AIReviewStep]:
    reasons = ", ".join(exception.reason_codes)
    intern = AIReviewStep(
        exception_id=exception.id,
        stage="intern",
        confidence=0.72,
        output_json={
            "summary": f"Initial verification suggests mismatch due to: {reasons}",
            "root_cause": "source_discrepancy",
        },
    )
    manager = AIReviewStep(
        exception_id=exception.id,
        stage="manager",
        confidence=0.78,
        output_json={
            "second_opinion": "Evidence is sufficient to keep as doubtful pending manual resolution.",
            "agreement_with_intern": True,
        },
    )
    supervisor = AIReviewStep(
        exception_id=exception.id,
        stage="supervisor",
        confidence=0.81,
        output_json={
            "suggested_action": "verify",
            "note": "Request supporting documents or source correction.",
        },
    )
    return [intern, manager, supervisor]


def build_announcements(run_id: str, decisions: list[MatchDecision], exceptions: list[ExceptionCase]) -> list[AnnouncementItem]:
    now = datetime.now(timezone.utc).isoformat()
    good_count = sum(1 for d in decisions if d.final_status.value == "good_transaction")
    doubtful_count = sum(1 for d in decisions if d.final_status.value == "doubtful_transaction")

    out = [
        AnnouncementItem(
            id=str(uuid.uuid4()),
            run_id=run_id,
            level="good",
            title="Reconciliation completed",
            message=f"Good transactions: {good_count}",
            payload_json={"good_count": good_count, "created_at": now},
        )
    ]

    if doubtful_count:
        refs = [e.merchant_ref for e in exceptions]
        out.append(
            AnnouncementItem(
                id=str(uuid.uuid4()),
                run_id=run_id,
                level="doubtful",
                title="Doubtful transactions require attention",
                message=f"Doubtful transactions: {doubtful_count}",
                payload_json={"doubtful_count": doubtful_count, "merchant_refs": refs, "created_at": now},
            )
        )

    return out
