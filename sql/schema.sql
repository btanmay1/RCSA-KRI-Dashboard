-- RCSA / PRSA and KRI data model (SQLite). Star-style: dimensions for risk, control, KRI; facts for
-- risk-control mapping, monthly KRI values and issues. Scoring logic lives in the views so the same
-- numbers feed Excel, Power BI and the preview charts.

DROP VIEW IF EXISTS v_issue_ageing;
DROP VIEW IF EXISTS v_kri_rag;
DROP VIEW IF EXISTS v_risk_scores;
DROP VIEW IF EXISTS v_control_scores;
DROP TABLE IF EXISTS issue;
DROP TABLE IF EXISTS kri_value;
DROP TABLE IF EXISTS kri;
DROP TABLE IF EXISTS risk_control;
DROP TABLE IF EXISTS control;
DROP TABLE IF EXISTS risk;
DROP TABLE IF EXISTS rating_band;
DROP TABLE IF EXISTS parameter;

CREATE TABLE parameter (name TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE rating_band (band TEXT PRIMARY KEY, min_score REAL NOT NULL, max_score REAL NOT NULL, sort_order INTEGER);

CREATE TABLE risk (
  risk_id      TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  description  TEXT,
  category     TEXT,
  sub_process  TEXT,
  owner        TEXT,
  impact       INTEGER NOT NULL CHECK (impact BETWEEN 1 AND 5),
  likelihood   INTEGER NOT NULL CHECK (likelihood BETWEEN 1 AND 5)
);

CREATE TABLE control (
  control_id         TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  control_type       TEXT CHECK (control_type IN ('Preventive', 'Detective')),
  nature             TEXT,
  frequency          TEXT,
  owner              TEXT,
  design_rating      TEXT CHECK (design_rating IN ('Effective', 'Partially Effective', 'Ineffective')),
  operating_rating   TEXT CHECK (operating_rating IN ('Effective', 'Partially Effective', 'Ineffective'))
);

CREATE TABLE risk_control (
  risk_id    TEXT REFERENCES risk(risk_id),
  control_id TEXT REFERENCES control(control_id),
  PRIMARY KEY (risk_id, control_id)
);

CREATE TABLE kri (
  kri_id       TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  unit         TEXT,
  linked_risks TEXT,             -- semicolon-separated risk ids
  green_max    REAL NOT NULL,
  amber_max    REAL NOT NULL,
  owner        TEXT
);

CREATE TABLE kri_value (
  kri_id TEXT REFERENCES kri(kri_id),
  month  TEXT NOT NULL,          -- YYYY-MM
  value  REAL NOT NULL,
  PRIMARY KEY (kri_id, month)
);

CREATE TABLE issue (
  issue_id     TEXT PRIMARY KEY,
  title        TEXT NOT NULL,
  source       TEXT,             -- 'RCSA control weakness' or 'KRI breach'
  risk_id      TEXT REFERENCES risk(risk_id),
  control_id   TEXT,
  kri_id       TEXT,
  severity     TEXT,
  owner        TEXT,
  raised_date  TEXT NOT NULL,
  due_date     TEXT NOT NULL,
  closed_date  TEXT,
  status       TEXT
);

-- Control score = weaker of design and operating rating (3 = Effective, 2 = Partially, 1 = Ineffective)
CREATE VIEW v_control_scores AS
SELECT c.*,
       CASE design_rating WHEN 'Effective' THEN 3 WHEN 'Partially Effective' THEN 2 ELSE 1 END AS design_score,
       CASE operating_rating WHEN 'Effective' THEN 3 WHEN 'Partially Effective' THEN 2 ELSE 1 END AS operating_score,
       MIN(CASE design_rating WHEN 'Effective' THEN 3 WHEN 'Partially Effective' THEN 2 ELSE 1 END,
           CASE operating_rating WHEN 'Effective' THEN 3 WHEN 'Partially Effective' THEN 2 ELSE 1 END) AS control_score
FROM control c;

-- Inherent = impact x likelihood. Controls reduce likelihood by up to MAX_REDUCTION, scaled by the
-- average score of mapped controls: reduction = (avg_score - 1) / 2 * max_reduction.
-- Residual likelihood is rounded half-up and floored at 1. Residual = impact x residual likelihood.
CREATE VIEW v_risk_scores AS
WITH ce AS (
  SELECT rc.risk_id, COUNT(*) AS mapped_controls, AVG(cs.control_score) AS avg_control_score,
         GROUP_CONCAT(rc.control_id, ', ') AS control_ids
  FROM risk_control rc JOIN v_control_scores cs ON cs.control_id = rc.control_id
  GROUP BY rc.risk_id
), s AS (
  SELECT r.*, ce.mapped_controls, ce.control_ids, ROUND(ce.avg_control_score, 2) AS avg_control_score,
         r.impact * r.likelihood AS inherent_score,
         (ce.avg_control_score - 1) / 2.0 * (SELECT CAST(value AS REAL) FROM parameter WHERE name = 'max_reduction') AS reduction
  FROM risk r JOIN ce ON ce.risk_id = r.risk_id
), s2 AS (
  SELECT s.*, MAX(1, CAST(likelihood * (1 - reduction) + 0.5 AS INTEGER)) AS residual_likelihood FROM s
)
SELECT s2.risk_id, title, category, sub_process, owner, impact, likelihood, inherent_score,
       (SELECT band FROM rating_band b WHERE inherent_score BETWEEN b.min_score AND b.max_score) AS inherent_rating,
       mapped_controls, control_ids, avg_control_score,
       CASE WHEN avg_control_score >= 2.75 THEN 'Effective'
            WHEN avg_control_score >= 1.75 THEN 'Partially Effective' ELSE 'Ineffective' END AS control_effectiveness,
       ROUND(reduction, 3) AS likelihood_reduction,
       residual_likelihood,
       impact * residual_likelihood AS residual_score,
       (SELECT band FROM rating_band b WHERE impact * residual_likelihood BETWEEN b.min_score AND b.max_score) AS residual_rating,
       CASE WHEN impact * residual_likelihood > (SELECT CAST(value AS REAL) FROM parameter WHERE name = 'risk_appetite_residual')
            THEN 'Outside appetite' ELSE 'Within appetite' END AS appetite_status
FROM s2;

CREATE VIEW v_kri_rag AS
SELECT v.kri_id, k.name, k.unit, k.linked_risks, k.owner, v.month, v.value, k.green_max, k.amber_max,
       CASE WHEN v.value <= k.green_max THEN 'Green' WHEN v.value <= k.amber_max THEN 'Amber' ELSE 'Red' END AS rag,
       CASE WHEN v.value > k.amber_max THEN 1 ELSE 0 END AS is_breach
FROM kri_value v JOIN kri k ON k.kri_id = v.kri_id;

CREATE VIEW v_issue_ageing AS
WITH a AS (
  SELECT i.*, (SELECT value FROM parameter WHERE name = 'as_of_date') AS as_of FROM issue i
)
SELECT issue_id, title, source, risk_id, control_id, kri_id, severity, owner, raised_date, due_date, closed_date, status,
       CAST(julianday(COALESCE(closed_date, as_of)) - julianday(raised_date) AS INTEGER) AS age_days,
       CASE WHEN status <> 'Closed' AND due_date < as_of THEN 'Overdue'
            WHEN status = 'Closed' THEN 'Closed' ELSE 'On track' END AS due_status,
       CASE WHEN status = 'Closed' THEN 'Closed'
            WHEN julianday(as_of) - julianday(raised_date) <= 30 THEN '0-30 days'
            WHEN julianday(as_of) - julianday(raised_date) <= 60 THEN '31-60 days'
            WHEN julianday(as_of) - julianday(raised_date) <= 90 THEN '61-90 days'
            ELSE '90+ days' END AS ageing_bucket
FROM a;
