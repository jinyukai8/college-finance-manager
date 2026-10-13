ALTER TABLE transactions
ADD COLUMN item TEXT CHECK(item IS NULL OR length(trim(item)) > 0);
