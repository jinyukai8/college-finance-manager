from uuid import uuid4

from college_finance_manager.application.file_operations import backup_before_change
from college_finance_manager.application.transactions import TransactionRuleError, _correct_transaction


EDITABLE_FIELDS = frozenset({
    "occurred_on", "direction", "amount_cents", "category_id", "purpose",
    "item", "handler", "payment_method", "note",
})


def edit_transaction(connection, paths, transaction_id, changes, reason):
    if not changes or not changes.keys() <= EDITABLE_FIELDS:
        raise TransactionRuleError("仅可修改业务字段")
    if not reason.strip():
        raise TransactionRuleError("请填写修改原因")
    backup_before_change(connection, paths)
    return _correct_transaction(connection, transaction_id, changes, reason, idempotency_key=str(uuid4()))
