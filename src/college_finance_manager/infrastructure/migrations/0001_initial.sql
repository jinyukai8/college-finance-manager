CREATE TABLE ledgers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    opening_date TEXT NOT NULL CHECK(length(opening_date) = 10),
    opening_balance_cents INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE categories (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
    name TEXT NOT NULL CHECK(length(trim(name)) > 0),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(ledger_id, type, name)
);

CREATE TABLE transactions (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    transaction_no TEXT NOT NULL CHECK(length(trim(transaction_no)) > 0),
    occurred_on TEXT NOT NULL CHECK(length(occurred_on) = 10),
    direction TEXT NOT NULL CHECK(direction IN ('income', 'expense')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    category_id TEXT REFERENCES categories(id) ON DELETE RESTRICT,
    category_name_snapshot TEXT CHECK(category_name_snapshot IS NULL OR length(trim(category_name_snapshot)) > 0),
    purpose TEXT NOT NULL CHECK(length(trim(purpose)) > 0),
    handler TEXT,
    payment_method TEXT,
    note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'voided', 'reversed')),
    source TEXT NOT NULL CHECK(source IN ('direct', 'reimbursement', 'advance_payment', 'advance_refund', 'reversal', 'correction')),
    reversal_of_id TEXT REFERENCES transactions(id) ON DELETE RESTRICT,
    idempotency_key TEXT UNIQUE,
    void_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK((status = 'voided' AND length(trim(void_reason)) > 0) OR (status <> 'voided' AND void_reason IS NULL)),
    CHECK((source = 'reversal' AND reversal_of_id IS NOT NULL) OR source <> 'reversal'),
    UNIQUE(ledger_id, transaction_no)
);

CREATE UNIQUE INDEX ux_transactions_reversal_once
ON transactions(reversal_of_id) WHERE reversal_of_id IS NOT NULL;
CREATE INDEX ix_transactions_ledger_date ON transactions(ledger_id, occurred_on);
CREATE INDEX ix_transactions_ledger_direction ON transactions(ledger_id, direction, occurred_on);
CREATE INDEX ix_transactions_category ON transactions(category_id, occurred_on);

CREATE TABLE reimbursements (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    applicant TEXT NOT NULL CHECK(length(trim(applicant)) > 0),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    purpose TEXT NOT NULL CHECK(length(trim(purpose)) > 0),
    applied_on TEXT NOT NULL CHECK(length(applied_on) = 10),
    paid_on TEXT CHECK(paid_on IS NULL OR length(paid_on) = 10),
    status TEXT NOT NULL CHECK(status IN ('pending', 'awaiting_payment', 'completed', 'rejected', 'cancelled')),
    note TEXT,
    decision_reason TEXT,
    payment_transaction_id TEXT REFERENCES transactions(id) ON DELETE RESTRICT,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK((status = 'completed' AND payment_transaction_id IS NOT NULL AND paid_on IS NOT NULL)
       OR (status <> 'completed' AND payment_transaction_id IS NULL)),
    CHECK((status IN ('rejected', 'cancelled') AND length(trim(decision_reason)) > 0)
       OR status NOT IN ('rejected', 'cancelled'))
);

CREATE UNIQUE INDEX ux_reimbursements_payment
ON reimbursements(payment_transaction_id) WHERE payment_transaction_id IS NOT NULL;
CREATE INDEX ix_reimbursements_ledger_status ON reimbursements(ledger_id, status, applied_on);

CREATE TABLE advances (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    recipient TEXT NOT NULL CHECK(length(trim(recipient)) > 0),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    purpose TEXT NOT NULL CHECK(length(trim(purpose)) > 0),
    requested_on TEXT NOT NULL CHECK(length(requested_on) = 10),
    paid_on TEXT CHECK(paid_on IS NULL OR length(paid_on) = 10),
    status TEXT NOT NULL CHECK(status IN ('pending_payment', 'pending_settlement', 'partially_settled', 'settled', 'cancelled')),
    note TEXT,
    cancel_reason TEXT,
    payment_transaction_id TEXT REFERENCES transactions(id) ON DELETE RESTRICT,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK((status IN ('pending_settlement', 'partially_settled', 'settled') AND payment_transaction_id IS NOT NULL AND paid_on IS NOT NULL)
       OR (status IN ('pending_payment', 'cancelled') AND payment_transaction_id IS NULL)),
    CHECK((status = 'cancelled' AND length(trim(cancel_reason)) > 0) OR status <> 'cancelled')
);

CREATE UNIQUE INDEX ux_advances_payment
ON advances(payment_transaction_id) WHERE payment_transaction_id IS NOT NULL;
CREATE INDEX ix_advances_ledger_status ON advances(ledger_id, status, requested_on);

CREATE TABLE advance_events (
    id TEXT PRIMARY KEY,
    advance_id TEXT NOT NULL REFERENCES advances(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK(event_type IN ('settlement', 'refund')),
    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
    occurred_on TEXT NOT NULL CHECK(length(occurred_on) = 10),
    category_id TEXT REFERENCES categories(id) ON DELETE RESTRICT,
    category_name_snapshot TEXT,
    note TEXT,
    refund_transaction_id TEXT REFERENCES transactions(id) ON DELETE RESTRICT,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    CHECK((event_type = 'refund' AND refund_transaction_id IS NOT NULL)
       OR (event_type = 'settlement' AND refund_transaction_id IS NULL))
);

CREATE UNIQUE INDEX ux_advance_events_refund
ON advance_events(refund_transaction_id) WHERE refund_transaction_id IS NOT NULL;
CREATE INDEX ix_advance_events_advance_date ON advance_events(advance_id, occurred_on);

CREATE TABLE attachments (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    entity_type TEXT NOT NULL CHECK(entity_type IN ('transaction', 'reimbursement', 'advance', 'advance_event')),
    entity_id TEXT NOT NULL,
    internal_path TEXT NOT NULL UNIQUE CHECK(length(trim(internal_path)) > 0),
    original_name TEXT NOT NULL CHECK(length(trim(original_name)) > 0),
    media_type TEXT NOT NULL CHECK(media_type IN ('image/jpeg', 'image/png', 'application/pdf')),
    sha256 TEXT NOT NULL CHECK(length(sha256) = 64),
    size_bytes INTEGER NOT NULL CHECK(size_bytes > 0),
    imported_at TEXT NOT NULL
);

CREATE INDEX ix_attachments_entity ON attachments(entity_type, entity_id);

CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    entity_type TEXT NOT NULL CHECK(length(trim(entity_type)) > 0),
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(length(trim(action)) > 0),
    change_summary TEXT NOT NULL CHECK(length(trim(change_summary)) > 0),
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX ix_audit_logs_entity ON audit_logs(entity_type, entity_id, created_at);
CREATE INDEX ix_audit_logs_ledger_time ON audit_logs(ledger_id, created_at);

CREATE TABLE reconciliations (
    id TEXT PRIMARY KEY,
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    reconciled_on TEXT NOT NULL CHECK(length(reconciled_on) = 10),
    book_balance_cents INTEGER NOT NULL,
    actual_balance_cents INTEGER NOT NULL,
    difference_cents INTEGER NOT NULL,
    note TEXT,
    created_at TEXT NOT NULL,
    CHECK(difference_cents = actual_balance_cents - book_balance_cents)
);

CREATE INDEX ix_reconciliations_ledger_date ON reconciliations(ledger_id, reconciled_on);

CREATE TABLE settings (
    ledger_id TEXT NOT NULL REFERENCES ledgers(id) ON DELETE RESTRICT,
    key TEXT NOT NULL CHECK(length(trim(key)) > 0),
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(ledger_id, key)
);
