ALTER TABLE transactions
ADD COLUMN correction_of_id TEXT REFERENCES transactions(id) ON DELETE RESTRICT;

CREATE UNIQUE INDEX ux_transactions_correction_once
ON transactions(correction_of_id) WHERE correction_of_id IS NOT NULL;
