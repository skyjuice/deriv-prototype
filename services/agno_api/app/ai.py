from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from .config import settings
from .schemas import AIReviewStep, AnnouncementItem, ExceptionCase, MatchDecision

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
logger = logging.getLogger(__name__)
CHAT_SYSTEM_PROMPT = (
    "You are Recon Finance Assistant for operations users. "
    "Answer ONLY from the provided database JSON context and conversation history. "
    "Use history to resolve follow-up references like it/that/those. "
    "If answer is missing in context, say: Not found in current database snapshot. "
    "Never invent run IDs, merchant refs, counts, statuses, or dates. "
    "Response style: no markdown headings, no long report format, "
    "start with one short sentence then up to 4 concise bullets with concrete values."
)
REVIEW_SYSTEM_PROMPT = (
    "You are a reconciliation reviewer for finance exception handling. "
    "Return JSON only, concise, evidence-based, and avoid markdown."
)
GREETING_TOKENS = {"hi", "hello", "hey", "yo", "sup", "hiya", "morning", "afternoon", "evening"}
THANKS_PHRASES = {"thanks", "thank you", "thx", "ok thanks", "great thanks"}
HELP_PHRASES = {"help", "what can you do", "how to use", "how do i use this", "commands"}


def _safe_confidence(value: Any, fallback: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        return fallback
    if parsed < 0:
        return 0.0
    if parsed > 1:
        return 1.0
    return round(parsed, 4)


def _default_review_chain(
    exception: ExceptionCase,
    reasons: str,
    reviewed_at: str,
    review_request_id: str,
) -> list[AIReviewStep]:
    intern = AIReviewStep(
        exception_id=exception.id,
        stage="intern",
        confidence=0.72,
        output_json={
            "summary": f"Initial verification suggests mismatch due to: {reasons}",
            "root_cause": "source_discrepancy",
            "engine": "local_fallback",
            "reviewed_at": reviewed_at,
            "review_request_id": review_request_id,
        },
    )
    manager = AIReviewStep(
        exception_id=exception.id,
        stage="manager",
        confidence=0.78,
        output_json={
            "second_opinion": "Evidence is sufficient to keep as doubtful pending manual resolution.",
            "agreement_with_intern": True,
            "engine": "local_fallback",
            "reviewed_at": reviewed_at,
            "review_request_id": review_request_id,
        },
    )
    supervisor = AIReviewStep(
        exception_id=exception.id,
        stage="supervisor",
        confidence=0.81,
        output_json={
            "suggested_action": "verify",
            "note": "Request supporting documents or source correction.",
            "engine": "local_fallback",
            "reviewed_at": reviewed_at,
            "review_request_id": review_request_id,
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


def _extract_openrouter_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _extract_json_object(content: str) -> dict[str, Any] | None:
    text = content.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _safe_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return fallback


def _call_openrouter_review_stage(
    *,
    stage: str,
    model: str,
    exception: ExceptionCase,
    prior_outputs: dict[str, Any],
) -> dict[str, Any] | None:
    if stage == "intern":
        schema = '{"confidence": number, "summary": string, "root_cause": string}'
        stage_instruction = "Focus on first-pass diagnosis."
    elif stage == "manager":
        schema = '{"confidence": number, "second_opinion": string, "agreement_with_intern": boolean}'
        stage_instruction = "Provide second opinion and agreement flag."
    else:
        schema = '{"confidence": number, "suggested_action": string, "note": string}'
        stage_instruction = "Provide decision-ready action recommendation."

    payload = {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 260,
        "messages": [
            {"role": "system", "content": REVIEW_SYSTEM_PROMPT},
            {
                "role": "system",
                "content": f"Stage={stage}. {stage_instruction} Return strict JSON object only with schema {schema}.",
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "exception": {
                            "exception_id": exception.id,
                            "merchant_ref": exception.merchant_ref,
                            "severity": exception.severity,
                            "reason_codes": exception.reason_codes,
                            "state": exception.state,
                        },
                        "prior_outputs": prior_outputs,
                    },
                    ensure_ascii=True,
                ),
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    try:
        logger.info("ai review stage=%s model=%s exception_id=%s", stage, model, exception.id)
        with httpx.Client(timeout=35.0) as client:
            response = client.post(OPENROUTER_CHAT_URL, headers=headers, json=payload)
            response.raise_for_status()
        content = _extract_openrouter_content(response.json())
        return _extract_json_object(content)
    except Exception as exc:
        logger.warning(
            "ai review openrouter stage failed stage=%s model=%s exception_id=%s error=%s",
            stage,
            model,
            exception.id,
            exc,
        )
        return None


def run_ai_review_chain(exception: ExceptionCase) -> list[AIReviewStep]:
    reasons = ", ".join(exception.reason_codes) or "MANUAL_REVIEW_REQUIRED"
    reviewed_at = datetime.now(timezone.utc).isoformat()
    review_request_id = str(uuid.uuid4())
    fallback = _default_review_chain(exception, reasons, reviewed_at, review_request_id)

    if not settings.openrouter_api_key:
        return fallback

    fallback_by_stage = {item.stage: item for item in fallback}
    intern_stage = _call_openrouter_review_stage(
        stage="intern",
        model=settings.openrouter_review_intern_model,
        exception=exception,
        prior_outputs={},
    )
    intern_output = (
        {
            "summary": str(intern_stage.get("summary") or f"Initial verification suggests mismatch due to: {reasons}"),
            "root_cause": str(intern_stage.get("root_cause") or "source_discrepancy"),
            "engine": "openrouter",
            "model": settings.openrouter_review_intern_model,
            "reviewed_at": reviewed_at,
            "review_request_id": review_request_id,
        }
        if isinstance(intern_stage, dict)
        else fallback_by_stage["intern"].output_json
    )
    intern_confidence = (
        _safe_confidence(intern_stage.get("confidence"), fallback_by_stage["intern"].confidence)
        if isinstance(intern_stage, dict)
        else fallback_by_stage["intern"].confidence
    )

    manager_stage = _call_openrouter_review_stage(
        stage="manager",
        model=settings.openrouter_review_manager_model,
        exception=exception,
        prior_outputs={"intern": intern_output},
    )
    manager_output = (
        {
            "second_opinion": str(
                manager_stage.get("second_opinion")
                or "Evidence is sufficient to keep as doubtful pending manual resolution."
            ),
            "agreement_with_intern": _safe_bool(manager_stage.get("agreement_with_intern"), True),
            "engine": "openrouter",
            "model": settings.openrouter_review_manager_model,
            "reviewed_at": reviewed_at,
            "review_request_id": review_request_id,
        }
        if isinstance(manager_stage, dict)
        else fallback_by_stage["manager"].output_json
    )
    manager_confidence = (
        _safe_confidence(manager_stage.get("confidence"), fallback_by_stage["manager"].confidence)
        if isinstance(manager_stage, dict)
        else fallback_by_stage["manager"].confidence
    )

    supervisor_stage = _call_openrouter_review_stage(
        stage="supervisor",
        model=settings.openrouter_review_supervisor_model,
        exception=exception,
        prior_outputs={"intern": intern_output, "manager": manager_output},
    )
    supervisor_output = (
        {
            "suggested_action": str(supervisor_stage.get("suggested_action") or "verify"),
            "note": str(supervisor_stage.get("note") or "Request supporting documents or source correction."),
            "engine": "openrouter",
            "model": settings.openrouter_review_supervisor_model,
            "reviewed_at": reviewed_at,
            "review_request_id": review_request_id,
        }
        if isinstance(supervisor_stage, dict)
        else fallback_by_stage["supervisor"].output_json
    )
    supervisor_confidence = (
        _safe_confidence(supervisor_stage.get("confidence"), fallback_by_stage["supervisor"].confidence)
        if isinstance(supervisor_stage, dict)
        else fallback_by_stage["supervisor"].confidence
    )

    return [
        AIReviewStep(
            exception_id=exception.id,
            stage="intern",
            confidence=intern_confidence,
            output_json=intern_output,
        ),
        AIReviewStep(
            exception_id=exception.id,
            stage="manager",
            confidence=manager_confidence,
            output_json=manager_output,
        ),
        AIReviewStep(
            exception_id=exception.id,
            stage="supervisor",
            confidence=supervisor_confidence,
            output_json=supervisor_output,
        ),
    ]


def _normalize_history(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    if not history:
        return []

    out: list[dict[str, str]] = []
    for row in history[-10:]:
        if not isinstance(row, dict):
            continue
        role = str(row.get("role", "")).strip().lower()
        content = str(row.get("content", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        out.append({"role": role, "content": content[:1600]})
    return out


def _is_followup_question(question: str) -> bool:
    q = question.lower()
    followup_terms = {"it", "that", "those", "them", "this", "same", "again", "what about", "how about"}
    return any(token in q for token in followup_terms)


def _normalized_text(question: str) -> str:
    cleaned = re.sub(r"[^a-z0-9\s]", " ", question.lower())
    return " ".join(cleaned.split())


def _small_talk_reply(question: str, context: dict[str, Any]) -> str | None:
    text = _normalized_text(question)
    if not text:
        return None

    tokens = text.split()
    summary = context.get("summary", {})
    runs_total = summary.get("runs_total", 0)
    open_exceptions = summary.get("open_exceptions", 0)

    if text in THANKS_PHRASES:
        return (
            "You are welcome.\n"
            "- Ask me for run status, doubtful refs, daily ops, or monthly close.\n"
            f"- Current snapshot: {runs_total} runs, {open_exceptions} open exceptions."
        )

    if text in HELP_PHRASES:
        return (
            "I can answer from reconciliation data in the database.\n"
            "- Try: monthly close status for 2026-02\n"
            "- Try: show doubtful refs for latest run\n"
            "- Try: what is next action for run RUN-XXXXXXX\n"
            "- Try: summarize daily ops today"
        )

    if len(tokens) <= 3 and any(token in GREETING_TOKENS for token in tokens):
        return (
            "Hi, I can help with reconciliation data.\n"
            "- Ask about run status, doubtful transactions, daily ops, or monthly close.\n"
            f"- Current snapshot: {runs_total} runs, {open_exceptions} open exceptions."
        )

    return None


def _fallback_chat_answer(question: str, context: dict[str, Any], history: list[dict[str, str]] | None = None) -> str:
    summary = context.get("summary", {})
    runs = context.get("runs", [])
    monthly = context.get("monthly_close", [])
    tx_index = context.get("transaction_index", [])
    history = history or []
    effective_question = question
    if _is_followup_question(question):
        for row in reversed(history):
            if row.get("role") == "user":
                prior = row.get("content", "").strip()
                if prior and prior != question:
                    effective_question = f"{prior}\nFollow-up: {question}"
                    break
    q_lower = effective_question.lower()

    lines: list[str] = []
    lines.append(
        "Current data snapshot: "
        f"{summary.get('runs_total', 0)} runs, "
        f"{summary.get('decisions_total', 0)} transactions, "
        f"{summary.get('open_exceptions', 0)} open exceptions."
    )

    raw_tokens = re.findall(r"[A-Z0-9][A-Z0-9-]{4,}", effective_question.upper())
    ref_tokens = [token for token in raw_tokens if "-" in token or any(char.isdigit() for char in token)]
    matched_refs: list[dict[str, Any]] = []
    if ref_tokens and isinstance(tx_index, list):
        wanted = set(ref_tokens)
        for item in tx_index:
            if not isinstance(item, dict):
                continue
            merchant_ref = str(item.get("merchant_ref", "")).upper()
            if merchant_ref in wanted:
                matched_refs.append(item)
        if matched_refs:
            lines.append("Reference details:")
            for item in matched_refs[:3]:
                reasons = ", ".join(item.get("reason_codes", []) or []) or "none"
                lines.append(
                    f"- {item.get('merchant_ref')}: {item.get('final_status')} "
                    f"(run {str(item.get('run_id', ''))[:8]}, month {item.get('transaction_month', 'unknown')}, reasons: {reasons})"
                )
        elif wanted:
            lines.append(f"No transaction found for reference(s): {', '.join(sorted(wanted))}.")

    if ("monthly" in q_lower or "erp" in q_lower) and isinstance(monthly, list):
        lines.append("Monthly close status:")
        for item in monthly[:3]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"- {item.get('month')}: ready={item.get('ready_for_erp')} "
                f"journal={item.get('journal_created')} submitted={item.get('submitted_to_erp')} "
                f"next={item.get('next_action')}"
            )

    if ("daily" in q_lower or "bau" in q_lower or "run" in q_lower) and isinstance(runs, list):
        lines.append("Latest runs:")
        for run in runs[:3]:
            if not isinstance(run, dict):
                continue
            lines.append(
                f"- {run.get('run_number')} ({run.get('business_date')}): "
                f"status={run.get('status')}, close={run.get('daily_close_state')}, next={run.get('daily_next_action')}"
            )

    if len(lines) == 1:
        lines.append("Ask for a run ID, merchant ref, daily close, or monthly close and I will answer from stored data.")
    return "\n".join(lines[:12])


async def answer_data_question(
    question: str,
    context: dict[str, Any],
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    safe_question = question.strip()
    if not safe_question:
        return {"answer": "Question is empty.", "source": "fallback", "model": None}
    normalized_history = _normalize_history(history)

    small_talk = _small_talk_reply(safe_question, context)
    if small_talk:
        return {"answer": small_talk, "source": "system", "model": None}

    if settings.openrouter_api_key:
        context_prompt = (
            "Database context JSON (source of truth):\n"
            f"{json.dumps(context, ensure_ascii=True)}"
        )
        payload = {
            "model": settings.openrouter_model,
            "temperature": 0.1,
            "max_tokens": 500,
            "messages": [
                {"role": "system", "content": CHAT_SYSTEM_PROMPT},
                {"role": "system", "content": context_prompt},
                *normalized_history,
                {"role": "user", "content": safe_question},
            ],
        }
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                response = await client.post(OPENROUTER_CHAT_URL, headers=headers, json=payload)
                response.raise_for_status()
            content = _extract_openrouter_content(response.json())
            if content:
                return {
                    "answer": content,
                    "source": "openrouter",
                    "model": settings.openrouter_model,
                }
        except Exception:
            # Degrade gracefully to deterministic local answer when model call fails.
            pass

    return {
        "answer": _fallback_chat_answer(safe_question, context, history=normalized_history),
        "source": "fallback",
        "model": None,
    }
