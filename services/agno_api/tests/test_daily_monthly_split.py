from __future__ import annotations

from tempfile import TemporaryDirectory

from app.schemas import ExceptionCase, FinalStatus, MatchDecision, RunStatus, StageResult
from app.storage import Storage
from app.storage import settings as storage_settings


def _decision(ref: str, final_status: FinalStatus, month: str, missing_internal: bool = False) -> MatchDecision:
    trace = None
    reasons = []
    if final_status == FinalStatus.DOUBTFUL:
        reasons = ["MISSING_IN_ONE_OR_MORE_SOURCES"]
        trace = {"sources_present": {"internal": not missing_internal, "erp": True, "psp": True}}
    return MatchDecision(
        run_id="",
        merchant_ref=ref,
        final_status=final_status,
        reason_codes=reasons,
        stage_results=StageResult(exact_hash=True, fuzzy=True, three_way=True, backdated=True, fx_handled=True),
        transaction_month=month,
        trace_json=trace,
    )


def test_daily_and_monthly_close_segregation() -> None:
    original_storage_dir = storage_settings.storage_dir
    with TemporaryDirectory() as temp_dir:
        object.__setattr__(storage_settings, "storage_dir", temp_dir)
        try:
            storage = Storage()
            run = storage.create_run("analyst")
            run.status = RunStatus.COMPLETED
            run.stage = "completed"
            storage.update_run(run, actor="system")

            good = _decision("REF-001", FinalStatus.GOOD, "2026-03")
            good.run_id = run.id
            bad = _decision("REF-002", FinalStatus.DOUBTFUL, "2026-03", missing_internal=True)
            bad.run_id = run.id

            storage.add_decisions(run.id, [good, bad])
            storage.add_exceptions(
                run.id,
                [
                    ExceptionCase(
                        id="exc-1",
                        run_id=run.id,
                        merchant_ref="REF-002",
                        severity="medium",
                        reason_codes=["MISSING_IN_ONE_OR_MORE_SOURCES"],
                        state="open",
                    )
                ],
            )

            daily = storage.get_daily_ops(run.id)
            assert daily.close_state == "open"
            assert daily.next_action == "address_doubtful"
            assert daily.notifications_required == 1
            assert daily.notifications_sent == 0

            dated = storage.set_daily_business_date(run.id, "2026-02-03", actor="analyst")
            assert dated.business_date == "2026-02-03"

            storage.address_daily_doubtful(run.id, actor="analyst")
            daily = storage.notify_daily_ops(run.id, actor="analyst")
            assert daily.notifications_sent == 1
            assert daily.unresolved_doubtful == 0
            assert daily.next_action == "close_day"

            closed = storage.close_daily_ops(run.id, actor="supervisor")
            assert closed.close_state == "closed"
            assert closed.closed_at is not None

            monthly = storage.get_monthly_close_batch("2026-03")
            assert monthly.source_run_count == 1
            assert monthly.total_transactions == 2
            assert monthly.doubtful_transactions == 1
            assert monthly.doubtful_notification_required == 1
            assert monthly.doubtful_notification_sent == 1
            assert monthly.ready_for_erp is True
            assert monthly.next_action == "create_journal"
            assert len(monthly.source_runs) == 1
            assert monthly.source_runs[0].business_date == "2026-02-03"
            assert monthly.source_runs[0].run_number.startswith("RUN-")

            journaled = storage.create_monthly_close_journal("2026-03", actor="supervisor")
            assert journaled.journal_created is True
            assert journaled.next_action == "submit_to_erp"

            submitted = storage.submit_monthly_close_to_erp("2026-03", actor="admin")
            assert submitted.submitted_to_erp is True
            assert submitted.next_action == "completed"
            assert submitted.erp_submission_payload is not None
            assert submitted.erp_submission_payload["month"] == "2026-03"
            assert submitted.erp_submission_payload["expected_good_transactions"] == 1

            reverted = storage.revert_monthly_close_submission("2026-03", actor="admin")
            assert reverted.submitted_to_erp is False
            assert reverted.journal_created is False
            assert reverted.next_action == "create_journal"
            assert reverted.submitted_at is None
            assert reverted.journal_created_at is None
            assert reverted.erp_submission_payload is None
        finally:
            object.__setattr__(storage_settings, "storage_dir", original_storage_dir)
