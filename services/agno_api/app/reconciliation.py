from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .formatting import date_diff_days
from .rules import BACKDATE_WINDOW_DAYS, FUZZY_THRESHOLD, FUZZY_WEIGHTS, STATUS_NORMALIZATION
from .schemas import ExceptionCase, FinalStatus, MatchDecision, StageResult


@dataclass
class ValidationResult:
    decisions: list[MatchDecision]
    exceptions: list[ExceptionCase]


def _norm_status(status: str) -> str:
    return STATUS_NORMALIZATION.get((status or "").strip().lower(), (status or "").upper())


def _hash_row(row: pd.Series) -> str:
    key = "|".join(
        [
            str(row.get("merchant_ref", "")),
            str(row.get("gross_amount", "")),
            str(row.get("currency", "")),
            str(row.get("processing_fee", "")),
            str(row.get("net_payout", "")),
            str(row.get("transaction_date", ""))[:10],
            str(row.get("client_id", "")),
        ]
    )
    return hashlib.sha256(key.encode()).hexdigest()


def _score_fuzzy(a: pd.Series, b: pd.Series) -> float:
    score = 0.0
    if a["merchant_ref"] == b["merchant_ref"]:
        score += FUZZY_WEIGHTS["merchant_ref"]

    amounts_match = (
        float(a["gross_amount"]) == float(b["gross_amount"])
        and float(a["processing_fee"]) == float(b["processing_fee"])
        and float(a["net_payout"]) == float(b["net_payout"])
    )
    if amounts_match:
        score += FUZZY_WEIGHTS["amounts"]

    if _norm_status(str(a["status"])) == _norm_status(str(b["status"])):
        score += FUZZY_WEIGHTS["status"]

    if str(a["client_id"]) == str(b["client_id"]):
        score += FUZZY_WEIGHTS["client_id"]

    if str(a["payment_method"]) == str(b["payment_method"]):
        score += FUZZY_WEIGHTS["payment_method"]

    return round(score, 4)


def _fx_can_handle(i: pd.Series, e: pd.Series, p: pd.Series) -> bool:
    currencies = {str(i["currency"]), str(e["currency"]), str(p["currency"])}
    if len(currencies) == 1:
        return True

    fx_values = [i.get("fx_rate"), e.get("fx_rate"), p.get("fx_rate")]
    if not all(v is not None and str(v) != "nan" for v in fx_values):
        return False

    try:
        return all(float(v) > 0 for v in fx_values)
    except Exception:
        return False


def _month_from_sources(i: pd.Series | None, e: pd.Series | None, p: pd.Series | None) -> str:
    for row in (i, e, p):
        if row is None:
            continue
        raw = str(row.get("transaction_date", "")).strip()
        if not raw:
            continue
        if len(raw) >= 7 and raw[4] == "-":
            return raw[:7]
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m")
        except Exception:
            try:
                return pd.to_datetime(raw, errors="raise").strftime("%Y-%m")
            except Exception:
                continue
    return "unknown"


def reconcile(run_id: str, internal_df: pd.DataFrame, erp_df: pd.DataFrame, psp_df: pd.DataFrame) -> ValidationResult:
    decisions: list[MatchDecision] = []
    exceptions: list[ExceptionCase] = []

    internal_idx = {str(r["merchant_ref"]): r for _, r in internal_df.iterrows()}
    erp_idx = {str(r["merchant_ref"]): r for _, r in erp_df.iterrows()}
    psp_idx = {str(r["merchant_ref"]): r for _, r in psp_df.iterrows()}

    all_refs = sorted(set(psp_idx) | set(erp_idx) | set(internal_idx))

    for merchant_ref in all_refs:
        reasons: list[str] = []
        stage = StageResult()

        i = internal_idx.get(merchant_ref)
        e = erp_idx.get(merchant_ref)
        p = psp_idx.get(merchant_ref)
        transaction_month = _month_from_sources(i, e, p)

        if not (i is not None and e is not None and p is not None):
            reasons.append("MISSING_IN_ONE_OR_MORE_SOURCES")
            stage.three_way = False
            final = FinalStatus.DOUBTFUL
            fuzzy_score = None
            max_gap = None
            fx_detail = "not_applicable_missing_sources"
            trace_json = {
                "sources_present": {
                    "internal": i is not None,
                    "erp": e is not None,
                    "psp": p is not None,
                },
                "exact_hash": {"matched": False, "skipped": True},
                "fuzzy": {"score": None, "threshold": FUZZY_THRESHOLD, "skipped": True},
                "three_way": {
                    "presence_check": False,
                    "amount_check": False,
                    "identity_check": False,
                },
                "backdated": {
                    "window_days": BACKDATE_WINDOW_DAYS,
                    "max_gap_days": None,
                    "pair_gaps_days": {},
                },
                "fx": {"handled": False, "detail": fx_detail, "currencies": [], "rates": {}},
            }
        else:
            # exact hash across all three source rows
            h_i, h_e, h_p = _hash_row(i), _hash_row(e), _hash_row(p)
            stage.exact_hash = h_i == h_e == h_p

            if not stage.exact_hash:
                ie_score = _score_fuzzy(i, e)
                ip_score = _score_fuzzy(i, p)
                ep_score = _score_fuzzy(e, p)
                fuzzy_score = min(ie_score, ip_score, ep_score)
                fuzzy_ok = ie_score >= FUZZY_THRESHOLD and ip_score >= FUZZY_THRESHOLD and ep_score >= FUZZY_THRESHOLD
                stage.fuzzy = fuzzy_ok
            else:
                stage.fuzzy = True
                fuzzy_score = 1.0

            amount_check = (
                float(i["gross_amount"]) == float(e["gross_amount"]) == float(p["gross_amount"])
                and float(i["processing_fee"]) == float(e["processing_fee"]) == float(p["processing_fee"])
                and float(i["net_payout"]) == float(e["net_payout"]) == float(p["net_payout"])
            )
            identity_check = (
                str(i["client_id"]) == str(e["client_id"]) == str(p["client_id"])
                and str(i["currency"]) == str(e["currency"]) == str(p["currency"])
                and str(i["bank_country"]) == str(e["bank_country"]) == str(p["bank_country"])
            )

            stage.three_way = amount_check and identity_check

            gap_ie = date_diff_days(str(i["transaction_date"]), str(e["transaction_date"]))
            gap_ip = date_diff_days(str(i["transaction_date"]), str(p["transaction_date"]))
            gap_ep = date_diff_days(str(e["transaction_date"]), str(p["transaction_date"]))
            max_gap = max(gap_ie, gap_ip, gap_ep)
            stage.backdated = max_gap <= BACKDATE_WINDOW_DAYS
            stage.fx_handled = _fx_can_handle(i, e, p)
            fx_detail = "handled" if stage.fx_handled else "insufficient_fx_data"
            trace_json = {
                "sources_present": {"internal": True, "erp": True, "psp": True},
                "exact_hash": {
                    "matched": stage.exact_hash,
                    "hashes": {
                        "internal": h_i[:12],
                        "erp": h_e[:12],
                        "psp": h_p[:12],
                    },
                    "key_fields": [
                        "merchant_ref",
                        "gross_amount",
                        "currency",
                        "processing_fee",
                        "net_payout",
                        "transaction_date(date-only)",
                        "client_id",
                    ],
                },
                "fuzzy": {
                    "score": fuzzy_score,
                    "threshold": FUZZY_THRESHOLD,
                    "pair_scores": {
                        "internal_vs_erp": _score_fuzzy(i, e),
                        "internal_vs_psp": _score_fuzzy(i, p),
                        "erp_vs_psp": _score_fuzzy(e, p),
                    },
                },
                "three_way": {
                    "presence_check": True,
                    "amount_check": amount_check,
                    "identity_check": identity_check,
                },
                "backdated": {
                    "window_days": BACKDATE_WINDOW_DAYS,
                    "max_gap_days": max_gap,
                    "pair_gaps_days": {
                        "internal_vs_erp": gap_ie,
                        "internal_vs_psp": gap_ip,
                        "erp_vs_psp": gap_ep,
                    },
                },
                "fx": {
                    "handled": stage.fx_handled,
                    "detail": fx_detail,
                    "currencies": [str(i["currency"]), str(e["currency"]), str(p["currency"])],
                    "rates": {
                        "internal": i.get("fx_rate"),
                        "erp": e.get("fx_rate"),
                        "psp": p.get("fx_rate"),
                    },
                },
            }

            if not stage.exact_hash:
                reasons.append("EXACT_HASH_MISMATCH")
            if not stage.fuzzy:
                reasons.append("FUZZY_THRESHOLD_NOT_MET")
            if not stage.three_way:
                reasons.append("THREE_WAY_VALIDATION_FAILED")
            if not stage.backdated:
                reasons.append("BACKDATED_WINDOW_EXCEEDED")
            if not stage.fx_handled:
                reasons.append("FX_DATA_INSUFFICIENT")

            final = FinalStatus.GOOD if (stage.fuzzy and stage.three_way and stage.backdated and stage.fx_handled) else FinalStatus.DOUBTFUL

        decision = MatchDecision(
            run_id=run_id,
            merchant_ref=merchant_ref,
            final_status=final,
            reason_codes=reasons,
            stage_results=stage,
            transaction_month=transaction_month,
            fuzzy_score=fuzzy_score,
            backdated_gap_days=max_gap,
            fx_detail=fx_detail,
            trace_json=trace_json,
        )
        decisions.append(decision)

        if final == FinalStatus.DOUBTFUL:
            exceptions.append(
                ExceptionCase(
                    id=str(uuid.uuid4()),
                    run_id=run_id,
                    merchant_ref=merchant_ref,
                    severity="medium",
                    reason_codes=reasons or ["MANUAL_REVIEW_REQUIRED"],
                    state="open",
                )
            )

    return ValidationResult(decisions=decisions, exceptions=exceptions)
