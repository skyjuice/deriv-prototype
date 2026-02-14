from __future__ import annotations

from tempfile import TemporaryDirectory

from app.schemas import ExceptionCase, FinalStatus, MatchDecision, StageResult
from app.storage import Storage
from app.storage import settings as storage_settings


def test_monthly_submission_lifecycle() -> None:
    original_storage_dir = storage_settings.storage_dir
    with TemporaryDirectory() as temp_dir:
        object.__setattr__(storage_settings, "storage_dir", temp_dir)
        try:
            storage = Storage()
            run = storage.create_run("analyst")

            decisions = [
                MatchDecision(
                    run_id=run.id,
                    merchant_ref="MONTH-001",
                    final_status=FinalStatus.GOOD,
                    reason_codes=[],
                    stage_results=StageResult(exact_hash=True, fuzzy=True, three_way=True, backdated=True, fx_handled=True),
                    transaction_month="2024-01",
                ),
                MatchDecision(
                    run_id=run.id,
                    merchant_ref="MONTH-002",
                    final_status=FinalStatus.DOUBTFUL,
                    reason_codes=["MISSING_IN_ONE_OR_MORE_SOURCES"],
                    stage_results=StageResult(exact_hash=False, fuzzy=True, three_way=False, backdated=True, fx_handled=True),
                    transaction_month="2024-01",
                    trace_json={
                        "sources_present": {
                            "internal": True,
                            "erp": True,
                            "psp": False,
                        }
                    },
                ),
            ]
            storage.add_decisions(run.id, decisions)
            storage.add_exceptions(
                run.id,
                [
                    ExceptionCase(
                        id="exc-001",
                        run_id=run.id,
                        merchant_ref="MONTH-002",
                        severity="medium",
                        reason_codes=["MISSING_IN_ONE_OR_MORE_SOURCES"],
                        state="open",
                    )
                ],
            )

            initial = storage.get_monthly_submission(run.id, "2024-01")
            assert initial.total_transactions == 2
            assert initial.good_transactions == 1
            assert initial.doubtful_transactions == 1
            assert initial.unresolved_doubtful == 1
            assert initial.ready_for_submission is False
            assert initial.next_action == "address_doubtful"
            assert len(initial.alert_recipients) == 1
            assert initial.alert_recipients[0].recipient_key == "psp_provider"
            assert initial.alert_recipients[0].merchant_refs == ["MONTH-002"]
            assert len(initial.doubtful_details) == 1
            assert initial.doubtful_details[0].missing_sources == ["psp"]

            addressed = storage.address_monthly_doubtful(run.id, "2024-01", actor="analyst")
            assert addressed.unresolved_doubtful == 0
            assert addressed.ready_for_submission is True
            assert addressed.next_action == "notify_sources"

            notified = storage.mark_monthly_notified(run.id, "2024-01", actor="analyst")
            assert notified.notified_to_source is True
            assert notified.next_action == "create_journal"

            journal = storage.create_monthly_journal(run.id, "2024-01", actor="supervisor")
            assert journal.journal_created is True
            assert journal.next_action == "submit_to_erp"

            submitted = storage.submit_monthly_to_erp(run.id, "2024-01", actor="admin")
            assert submitted.submitted_to_erp is True
            assert submitted.next_action == "completed"
        finally:
            object.__setattr__(storage_settings, "storage_dir", original_storage_dir)
