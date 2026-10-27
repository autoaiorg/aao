-- Transport only: no governance ledger or business state. No automatic expiry.
CREATE TABLE receipts (
  delivery_id TEXT PRIMARY KEY,
  digest TEXT NOT NULL,
  body BLOB NOT NULL,
  signature TEXT NOT NULL,
  repository TEXT NOT NULL,
  received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  acknowledged INTEGER NOT NULL DEFAULT 0 CHECK (acknowledged IN (0, 1))
);
CREATE INDEX pending_receipts ON receipts(acknowledged, received_at, delivery_id);
CREATE TRIGGER bound_receipts BEFORE INSERT ON receipts
WHEN NOT EXISTS (SELECT 1 FROM receipts WHERE delivery_id = NEW.delivery_id)
BEGIN
  SELECT CASE WHEN (SELECT count(*) FROM receipts) >= 10000
    OR (SELECT coalesce(sum(length(body)),0) FROM receipts) + length(NEW.body) > 50000000
    THEN RAISE(ABORT, 'relay capacity exceeded') END;
END;
