from __future__ import annotations

from tempfile import TemporaryDirectory

from app.schemas import ExceptionCase, FinalStatus, MatchDecision, RunStatus, StageResult
from app.storage import Storage
from app.storage import settings as storage_settings


def test_build_chat_context_includes_run_transaction_and_exception() -> None:
    original_storage_dir = storage_settings.storage_dir
    with TemporaryDirectory() as temp_dir:
        object.__setattr__(storage_settings, "storage_dir", temp_dir)
        try:
            storage = Storage()
            run = storage.create_run("analyst")
            run.status = RunStatus.COMPLETED
            run.stage = "completed"
            storage.update_run(run, actor="system")

            decisions = [
                MatchDecision(
                    run_id=run.id,
                    merchant_ref="CHAT-001",
                    final_status=FinalStatus.GOOD,
                    reason_codes=[],
                    stage_results=StageResult(exact_hash=True, fuzzy=True, three_way=True, backdated=True, fx_handled=True),
                    transaction_month="2026-01",
                ),
                MatchDecision(
                    run_id=run.id,
                    merchant_ref="CHAT-002",
                    final_status=FinalStatus.DOUBTFUL,
                    reason_codes=["MISSING_IN_ONE_OR_MORE_SOURCES"],
                    stage_results=StageResult(exact_hash=False, fuzzy=False, three_way=False, backdated=True, fx_handled=True),
                    transaction_month="2026-01",
                    trace_json={"sources_present": {"internal": False, "erp": True, "psp": True}},
                ),
            ]
            storage.add_decisions(run.id, decisions)
            storage.add_exceptions(
                run.id,
                [
                    ExceptionCase(
                        id="exc-chat-002",
                        run_id=run.id,
                        merchant_ref="CHAT-002",
                        severity="medium",
                        reason_codes=["MISSING_IN_ONE_OR_MORE_SOURCES"],
                        state="open",
                    )
                ],
            )

            context = storage.build_chat_context()
            assert context["summary"]["runs_total"] == 1
            assert context["summary"]["decisions_total"] == 2
            assert context["summary"]["exceptions_total"] == 1
            assert context["summary"]["open_exceptions"] == 1
            assert context["runs"][0]["run_number"].startswith("RUN-")
            assert any(row["merchant_ref"] == "CHAT-002" for row in context["transaction_index"])
            assert any(row["merchant_ref"] == "CHAT-002" for row in context["exceptions_index"])

            scoped = storage.build_chat_context(run_id=run.id)
            assert scoped["scope"]["run_id"] == run.id
            assert scoped["scope"]["selected_run_ids"] == [run.id]
        finally:
            object.__setattr__(storage_settings, "storage_dir", original_storage_dir)
