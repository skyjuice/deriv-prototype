from __future__ import annotations

from pathlib import Path

import pandas as pd

from app.reconciliation import reconcile


DATASET_DIR = Path(__file__).resolve().parents[3] / "sample_data" / "scenario3"


def test_scenario3_counts_and_refs() -> None:
    internal_df = pd.read_csv(DATASET_DIR / "scenario3_internal_10.csv")
    erp_df = pd.read_csv(DATASET_DIR / "scenario3_erp_10.csv")
    psp_df = pd.read_csv(DATASET_DIR / "scenario3_psp_10.csv")

    result = reconcile("run-s3", internal_df, erp_df, psp_df)

    good = [d for d in result.decisions if d.final_status.value == "good_transaction"]
    doubtful = [d for d in result.decisions if d.final_status.value == "doubtful_transaction"]

    assert len(good) == 8
    assert len(doubtful) == 2

    refs = sorted([d.merchant_ref for d in doubtful])
    assert refs == ["SCENARIO3-REF-001", "SCENARIO3-REF-010"]


def test_backdated_refs_pass() -> None:
    internal_df = pd.read_csv(DATASET_DIR / "scenario3_internal_10.csv")
    erp_df = pd.read_csv(DATASET_DIR / "scenario3_erp_10.csv")
    psp_df = pd.read_csv(DATASET_DIR / "scenario3_psp_10.csv")

    result = reconcile("run-s3", internal_df, erp_df, psp_df)
    by_ref = {d.merchant_ref: d for d in result.decisions}

    for ref in ["SCENARIO3-REF-006", "SCENARIO3-REF-007", "SCENARIO3-REF-008"]:
        assert by_ref[ref].stage_results.backdated is True
        assert by_ref[ref].final_status.value == "good_transaction"
