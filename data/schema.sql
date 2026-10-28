-- SQLite schema for generated synthetic insurance data. Load before seed_data.sql.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS applicants (
  "applicant_id" TEXT PRIMARY KEY,
  "applicant_type" TEXT,
  "age" TEXT,
  "region" TEXT,
  "customer_since" TEXT,
  "consent_status" TEXT
);
CREATE TABLE IF NOT EXISTS insured_assets (
  "asset_id" TEXT PRIMARY KEY,
  "applicant_id" TEXT REFERENCES applicants("applicant_id"),
  "asset_type" TEXT,
  "asset_value" TEXT,
  "region" TEXT,
  "acquired_date" TEXT,
  "asset_status" TEXT
);
CREATE TABLE IF NOT EXISTS products (
  "product_id" TEXT PRIMARY KEY,
  "product_name" TEXT,
  "product_line" TEXT,
  "base_rate" TEXT,
  "max_coverage" TEXT,
  "min_age" TEXT,
  "max_risk_score" TEXT,
  "max_asset_value" TEXT,
  "active" TEXT
);
CREATE TABLE IF NOT EXISTS coverage_options (
  "coverage_option_id" TEXT PRIMARY KEY,
  "product_id" TEXT REFERENCES products("product_id"),
  "coverage_name" TEXT,
  "limit_amount" TEXT,
  "deductible_amount" TEXT,
  "active" TEXT
);
CREATE TABLE IF NOT EXISTS risk_factors (
  "risk_factor_id" TEXT PRIMARY KEY,
  "factor_name" TEXT,
  "factor_type" TEXT,
  "factor_value" TEXT,
  "description" TEXT
);
CREATE TABLE IF NOT EXISTS quotes (
  "quote_id" TEXT PRIMARY KEY,
  "applicant_id" TEXT REFERENCES applicants("applicant_id"),
  "asset_id" TEXT REFERENCES insured_assets("asset_id"),
  "product_id" TEXT REFERENCES products("product_id"),
  "coverage_option_id" TEXT REFERENCES coverage_options("coverage_option_id"),
  "submission_date" TEXT,
  "risk_score" TEXT,
  "prior_claims" TEXT,
  "requested_coverage" TEXT,
  "calculated_premium" TEXT,
  "eligibility_status" TEXT,
  "quote_status" TEXT,
  "risk_data_missing" TEXT
);
CREATE TABLE IF NOT EXISTS policies (
  "policy_id" TEXT PRIMARY KEY,
  "quote_id" TEXT REFERENCES quotes("quote_id"),
  "applicant_id" TEXT REFERENCES applicants("applicant_id"),
  "asset_id" TEXT REFERENCES insured_assets("asset_id"),
  "product_id" TEXT REFERENCES products("product_id"),
  "coverage_option_id" TEXT REFERENCES coverage_options("coverage_option_id"),
  "issue_date" TEXT,
  "effective_date" TEXT,
  "expiry_date" TEXT,
  "premium_amount" TEXT,
  "acceptance_status" TEXT,
  "payment_status" TEXT,
  "policy_status" TEXT,
  "permitted_overlap_reason" TEXT
);
CREATE TABLE IF NOT EXISTS endorsements (
  "endorsement_id" TEXT PRIMARY KEY,
  "policy_id" TEXT REFERENCES policies("policy_id"),
  "effective_date" TEXT,
  "endorsement_type" TEXT,
  "asset_id" TEXT REFERENCES insured_assets("asset_id"),
  "previous_asset_value" TEXT,
  "new_asset_value" TEXT,
  "coverage_change" TEXT,
  "resulting_coverage" TEXT,
  "endorsement_status" TEXT,
  "reason" TEXT
);
CREATE TABLE IF NOT EXISTS renewals (
  "renewal_id" TEXT PRIMARY KEY,
  "policy_id" TEXT REFERENCES policies("policy_id"),
  "offer_date" TEXT,
  "proposed_effective_date" TEXT,
  "proposed_expiry_date" TEXT,
  "renewal_premium" TEXT,
  "renewal_status" TEXT,
  "decision_reason" TEXT
);
CREATE TABLE IF NOT EXISTS underwriting_decisions (
  "underwriting_decision_id" TEXT PRIMARY KEY,
  "quote_id" TEXT REFERENCES quotes("quote_id"),
  "decision_date" TEXT,
  "decision" TEXT,
  "reason" TEXT,
  "authority_level" TEXT,
  "rule_version" TEXT
);
