from datetime import date

import pytest

from college_finance_manager.application.initialize_ledger import InitializeLedgerCommand, initialize_ledger
from college_finance_manager.application.reimbursements import create_reimbursement
from college_finance_manager.infrastructure.attachments import AttachmentError, import_attachment


def test_invalid_attachment_leaves_no_file_or_database_row(database, tmp_path):
    ledger = initialize_ledger(database, InitializeLedgerCommand("账本", date.today(), 0, str(tmp_path)))
    reimbursement = create_reimbursement(
        database, ledger_id=ledger, applicant="张三", amount_cents=100,
        purpose="测试", applied_on=date.today(),
    )
    fake = tmp_path / "fake.png"
    fake.write_text("not an image", encoding="utf-8")
    root = tmp_path / "attachments"
    with pytest.raises(AttachmentError):
        import_attachment(
            database, attachments_root=root, ledger_id=ledger,
            entity_type="reimbursement", entity_id=reimbursement, source_path=fake,
        )
    assert database.execute("SELECT count(*) FROM attachments").fetchone()[0] == 0
    assert not root.exists() or not list(root.iterdir())


def test_valid_png_is_copied_under_uuid_and_hashed(database, tmp_path):
    ledger = initialize_ledger(database, InitializeLedgerCommand("账本", date.today(), 0, str(tmp_path)))
    reimbursement = create_reimbursement(
        database, ledger_id=ledger, applicant="张三", amount_cents=100,
        purpose="测试", applied_on=date.today(),
    )
    source = tmp_path / "凭证.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n" + b"test-payload")
    root = tmp_path / "attachments"
    attachment = import_attachment(
        database, attachments_root=root, ledger_id=ledger,
        entity_type="reimbursement", entity_id=reimbursement, source_path=source,
    )
    row = database.execute("SELECT * FROM attachments WHERE id=?", (attachment,)).fetchone()
    assert row["original_name"] == "凭证.png"
    assert len(row["sha256"]) == 64
    assert (root / row["internal_path"]).read_bytes() == source.read_bytes()
