ALTER TABLE attachments ADD COLUMN archived_at TEXT;

CREATE TABLE transaction_attachment_history (
    transaction_id TEXT NOT NULL REFERENCES transactions(id) ON DELETE RESTRICT,
    attachment_id TEXT NOT NULL REFERENCES attachments(id) ON DELETE RESTRICT,
    PRIMARY KEY (transaction_id, attachment_id)
);
