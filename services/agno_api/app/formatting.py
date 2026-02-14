from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pypdf import PdfReader

from .rules import CANONICAL_COLUMNS, HEADER_ALIASES, missing_columns


@dataclass
class FormatResult:
    ok: bool
    confidence: float
    mapping: dict[str, str]
    reason: str = ""


def _normalize_columns(columns: list[str]) -> list[str]:
    normalized = []
    for col in columns:
        key = col.strip().lower()
        normalized.append(HEADER_ALIASES.get(key, key))
    return normalized


def _coerce_df(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["gross_amount", "processing_fee", "net_payout", "fx_rate"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["transaction_date", "settlement_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S")
    return df


def parse_tabular_bytes(payload: bytes, ext: str) -> pd.DataFrame:
    ext = ext.lower()
    if ext == "csv":
        return pd.read_csv(io.BytesIO(payload))
    if ext == "xlsx":
        return pd.read_excel(io.BytesIO(payload))
    raise ValueError(f"unsupported tabular extension: {ext}")


def parse_pdf_bytes(payload: bytes) -> pd.DataFrame:
    reader = PdfReader(io.BytesIO(payload))
    lines: list[str] = []
    for page in reader.pages:
        text = page.extract_text() or ""
        lines.extend(l.strip() for l in text.splitlines() if l.strip())

    if not lines:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    rows = [line.split(",") for line in lines if "," in line]
    if not rows:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    headers = _normalize_columns(rows[0])
    data_rows = rows[1:]
    df = pd.DataFrame(data_rows, columns=headers)
    return df


def standardize_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, FormatResult]:
    original_cols = [str(c) for c in df.columns]
    normalized_cols = _normalize_columns(original_cols)
    mapping = dict(zip(original_cols, normalized_cols, strict=False))
    df.columns = normalized_cols

    misses = missing_columns(df.columns)
    if misses:
        return df, FormatResult(ok=False, confidence=0.0, mapping=mapping, reason=f"missing_columns:{','.join(misses)}")

    df = df[CANONICAL_COLUMNS].copy()
    df = _coerce_df(df)

    invalid_numerics = df[["gross_amount", "processing_fee", "net_payout"]].isna().any(axis=1).sum()
    invalid_dates = df[["transaction_date", "settlement_date"]].isna().any(axis=1).sum()
    bad = int(invalid_numerics + invalid_dates)

    confidence = 1.0 if bad == 0 else max(0.0, 1.0 - (bad / max(len(df), 1)))
    return df, FormatResult(ok=confidence >= 0.8, confidence=confidence, mapping=mapping)


def parse_any_file(file_path: str, ext: str) -> pd.DataFrame:
    payload = Path(file_path).read_bytes()
    if ext in {"csv", "xlsx"}:
        return parse_tabular_bytes(payload, ext)
    if ext == "pdf":
        return parse_pdf_bytes(payload)
    raise ValueError(f"unsupported extension: {ext}")


def date_diff_days(a: str, b: str) -> int:
    da = datetime.fromisoformat(a)
    db = datetime.fromisoformat(b)
    return abs((da.date() - db.date()).days)
