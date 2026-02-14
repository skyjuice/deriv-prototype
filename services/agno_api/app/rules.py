from __future__ import annotations

from typing import Iterable

CANONICAL_COLUMNS: list[str] = [
    "psp_txn_id",
    "merchant_ref",
    "gross_amount",
    "currency",
    "processing_fee",
    "net_payout",
    "transaction_date",
    "settlement_date",
    "client_id",
    "client_name",
    "description",
    "status",
    "payment_method",
    "settlement_bank",
    "bank_country",
    "fx_rate",
]

STATUS_NORMALIZATION = {
    "captured": "SUCCESS",
    "confirmed": "SUCCESS",
    "settled": "SUCCESS",
}

HEADER_ALIASES = {
    "txn_id": "psp_txn_id",
    "transaction_id": "psp_txn_id",
    "merchant_reference": "merchant_ref",
    "gross": "gross_amount",
    "fee": "processing_fee",
    "net": "net_payout",
    "txn_date": "transaction_date",
    "settle_date": "settlement_date",
    "client": "client_id",
}

FUZZY_WEIGHTS = {
    "merchant_ref": 0.5,
    "amounts": 0.2,
    "status": 0.1,
    "client_id": 0.1,
    "payment_method": 0.1,
}

FUZZY_THRESHOLD = 0.9
BACKDATE_WINDOW_DAYS = 3


def missing_columns(columns: Iterable[str]) -> list[str]:
    colset = {c.strip() for c in columns}
    return [c for c in CANONICAL_COLUMNS if c not in colset]
