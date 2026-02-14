from __future__ import annotations

from tempfile import TemporaryDirectory

from app.schemas import SourceType
from app.storage import Storage
from app.storage import settings as storage_settings


def _source_csv(merchant_ref: str, gross: float, fee: float, net: float) -> bytes:
    return (
        "psp_txn_id,merchant_ref,gross_amount,currency,processing_fee,net_payout,transaction_date,settlement_date,"
        "client_id,client_name,description,status,payment_method,settlement_bank,bank_country,fx_rate\n"
        f"TXN-{merchant_ref},{merchant_ref},{gross},USD,{fee},{net},2026-02-12T00:00:00,2026-02-13T00:00:00,"
        "C-100,Client A,Sample,SUCCESS,CARD,BANK-1,SG,1.0\n"
    ).encode()


def test_transaction_source_snapshot_returns_key_fields_and_consistency() -> None:
    original_storage_dir = storage_settings.storage_dir
    with TemporaryDirectory() as temp_dir:
        object.__setattr__(storage_settings, "storage_dir", temp_dir)
        try:
            storage = Storage()
            run = storage.create_run("analyst")
            merchant_ref = "REF-001"

            storage.save_source_file(run.id, SourceType.INTERNAL, "internal.csv", _source_csv(merchant_ref, 100.0, 2.0, 98.0))
            storage.save_source_file(run.id, SourceType.ERP, "erp.csv", _source_csv(merchant_ref, 100.0, 2.0, 97.5))
            storage.save_source_file(run.id, SourceType.PSP, "psp.csv", _source_csv(merchant_ref, 100.0, 2.0, 98.0))

            snapshot = storage.get_transaction_source_snapshot(run.id, merchant_ref)

            assert snapshot["run_id"] == run.id
            assert snapshot["merchant_ref"] == merchant_ref
            assert snapshot["checks"]["compared_sources"] == 3
            assert snapshot["checks"]["amount_consistency"] is False
            assert snapshot["checks"]["identity_consistency"] is True

            assert snapshot["sources"]["internal"]["found"] is True
            assert snapshot["sources"]["erp"]["found"] is True
            assert snapshot["sources"]["psp"]["found"] is True
            assert snapshot["sources"]["internal"]["row"]["gross_amount"] == 100.0
            assert snapshot["sources"]["erp"]["row"]["net_payout"] == 97.5
            assert snapshot["sources"]["psp"]["row"]["client_id"] == "C-100"
        finally:
            object.__setattr__(storage_settings, "storage_dir", original_storage_dir)
