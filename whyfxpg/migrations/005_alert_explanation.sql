-- Add explainability column to alert_records for rule engine outcomes.
ALTER TABLE alert_records ADD COLUMN explanation_json TEXT;
