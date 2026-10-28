"""Validate the 10 core insurance entities and separately check ground-truth labels."""

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


# Exactly the ten business entities required by the project statement.
TABLES = [
    "applicants",
    "insured_assets",
    "products",
    "coverage_options",
    "risk_factors",
    "quotes",
    "policies",
    "endorsements",
    "renewals",
    "underwriting_decisions",
]

PRIMARY_KEYS = {
    "applicants": "applicant_id",
    "insured_assets": "asset_id",
    "products": "product_id",
    "coverage_options": "coverage_option_id",
    "risk_factors": "risk_factor_id",
    "quotes": "quote_id",
    "policies": "policy_id",
    "endorsements": "endorsement_id",
    "renewals": "renewal_id",
    "underwriting_decisions": "underwriting_decision_id",
}

FOREIGN_KEYS = [
    ("insured_assets", "applicant_id", "applicants", "applicant_id"),
    ("coverage_options", "product_id", "products", "product_id"),
    ("quotes", "applicant_id", "applicants", "applicant_id"),
    ("quotes", "asset_id", "insured_assets", "asset_id"),
    ("quotes", "product_id", "products", "product_id"),
    ("quotes", "coverage_option_id", "coverage_options", "coverage_option_id"),
    ("policies", "quote_id", "quotes", "quote_id"),
    ("policies", "applicant_id", "applicants", "applicant_id"),
    ("policies", "asset_id", "insured_assets", "asset_id"),
    ("policies", "product_id", "products", "product_id"),
    ("policies", "coverage_option_id", "coverage_options", "coverage_option_id"),
    ("endorsements", "policy_id", "policies", "policy_id"),
    ("endorsements", "asset_id", "insured_assets", "asset_id"),
    ("renewals", "policy_id", "policies", "policy_id"),
    ("underwriting_decisions", "quote_id", "quotes", "quote_id"),
]

ALLOWED_ENUMS = {
    "applicants": {
        "applicant_type": {"individual", "small_business"},
        "region": {"north", "south", "east", "west", "central"},
        "consent_status": {"synthetic_not_applicable"},
    },
    "insured_assets": {
        "asset_type": {"vehicle", "property", "business_premises"},
        "region": {"north", "south", "east", "west", "central"},
        "asset_status": {"active"},
    },
    "products": {
        "product_line": {"motor", "property", "business"},
        "active": {"True", "False"},
    },
    "coverage_options": {"active": {"True", "False"}},
    "risk_factors": {"factor_type": {"multiplier", "referral"}},
    "quotes": {
        "eligibility_status": {"eligible", "ineligible"},
        "quote_status": {"offered", "referred", "declined"},
        "risk_data_missing": {"True", "False"},
    },
    "policies": {
        "acceptance_status": {"accepted", "pending"},
        "payment_status": {"paid", "pending", "unpaid"},
        "policy_status": {"active", "cancelled"},
    },
    "endorsements": {
        "endorsement_type": {"asset_change"},
        "endorsement_status": {"approved"},
    },
    "renewals": {"renewal_status": {"offered", "accepted", "declined"}},
    "underwriting_decisions": {
        "decision": {"refer", "decline"},
        "authority_level": {"senior_underwriter", "automated_rules"},
    },
}

REQUIRED_ANOMALIES = {
    "policy_issued_without_acceptance",
    "premium_outside_defined_rate_formula",
    "endorsement_exceeds_product_limit",
    "renewal_generated_for_cancelled_policy",
    "overlapping_policy_periods_without_permitted_reason",
}


def read_csv(path):
    """Read a CSV file into dictionaries."""
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def parse_date(value):
    """Parse a required ISO date."""
    if not value:
        raise ValueError("Date is empty")
    return date.fromisoformat(value)


def validate(data_dir):
    """Run Step 8 checks on ten entities and separate ground-truth labels."""
    data_dir = Path(data_dir)
    errors, warnings, checks = [], [], {}
    tables = {}

    # Load exactly the ten core entities.
    for name in TABLES:
        path = data_dir / f"{name}.csv"
        if not path.exists():
            errors.append(f"Missing required entity file: {path}")
            continue
        try:
            tables[name] = read_csv(path)
        except (OSError, csv.Error, UnicodeError) as exc:
            errors.append(f"Cannot read {path}: {exc}")

    # Ground truth is a separate required deliverable, not an entity/table.
    ground_truth_path = data_dir / "ground_truth.csv"
    ground_truth = []
    if not ground_truth_path.exists():
        errors.append(f"Missing required ground-truth file: {ground_truth_path}")
    else:
        try:
            ground_truth = read_csv(ground_truth_path)
        except (OSError, csv.Error, UnicodeError) as exc:
            errors.append(f"Cannot read {ground_truth_path}: {exc}")

    if errors:
        return {
            "status": "FAIL",
            "row_counts": {name: len(rows) for name, rows in tables.items()},
            "checks": checks,
            "errors": errors,
            "warnings": warnings,
            "ground_truth_cases": ground_truth,
        }

    # 1. Primary-key uniqueness (core entities only).
    for name, key in PRIMARY_KEYS.items():
        values = [row.get(key, "") for row in tables[name]]
        duplicates = [value for value, count in Counter(values).items()
                      if not value or count > 1]
        checks[f"{name}.primary_key_unique"] = not duplicates
        if duplicates:
            errors.append(f"{name}: empty or duplicate primary keys: {duplicates[:5]}")

    # Ground-truth case IDs are checked separately from entity primary keys.
    gt_ids = [row.get("case_id", "") for row in ground_truth]
    duplicate_gt_ids = [value for value, count in Counter(gt_ids).items()
                        if not value or count > 1]
    checks["ground_truth.case_id_unique"] = not duplicate_gt_ids
    if duplicate_gt_ids:
        errors.append(f"ground_truth: empty or duplicate case IDs: {duplicate_gt_ids[:5]}")

    # 2. Foreign-key integrity.
    for child, field, parent, parent_key in FOREIGN_KEYS:
        allowed = {row.get(parent_key, "") for row in tables[parent]}
        invalid = [row.get(field, "") for row in tables[child]
                   if not row.get(field, "") or row.get(field) not in allowed]
        checks[f"{child}.{field}_fk_valid"] = not invalid
        if invalid:
            errors.append(f"{child}.{field}: {len(invalid)} invalid references; examples={invalid[:5]}")

    # 3. Allowed enumerated values.
    for table_name, fields in ALLOWED_ENUMS.items():
        for field, allowed_values in fields.items():
            invalid = [row.get(field, "") for row in tables[table_name]
                       if row.get(field, "") not in allowed_values]
            checks[f"{table_name}.{field}_allowed_enum"] = not invalid
            if invalid:
                errors.append(f"{table_name}.{field}: invalid values {invalid[:5]}; allowed={sorted(allowed_values)}")

    truth = {
        (row.get("entity_type", ""), row.get("entity_id", "")): row.get("issue_type", "")
        for row in ground_truth
    }
    quotes = {row["quote_id"]: row for row in tables["quotes"]}
    applicants = {row["applicant_id"]: row for row in tables["applicants"]}
    products = {row["product_id"]: row for row in tables["products"]}
    coverages = {row["coverage_option_id"]: row for row in tables["coverage_options"]}
    policies = {row["policy_id"]: row for row in tables["policies"]}

    # 4. Date formats and date ordering. The known overlap anomaly intentionally
    # moves effective_date before issue_date; exempt only that labelled policy.
    date_rules = [
        ("policies", "issue_date", "effective_date"),
        ("policies", "effective_date", "expiry_date"),
        ("endorsements", "effective_date", None),
        ("renewals", "offer_date", "proposed_effective_date"),
        ("renewals", "proposed_effective_date", "proposed_expiry_date"),
        ("underwriting_decisions", "decision_date", None),
        ("quotes", "submission_date", None),
        ("applicants", "customer_since", None),
        ("insured_assets", "acquired_date", None),
    ]
    for table_name, first_field, second_field in date_rules:
        invalid = []
        for row in tables[table_name]:
            record_id = row.get(PRIMARY_KEYS[table_name], "")
            try:
                first_date = parse_date(row[first_field])
                if second_field and first_date > parse_date(row[second_field]):
                    injected_overlap = (
                        table_name == "policies"
                        and truth.get(("Policy", record_id))
                        == "overlapping_policy_periods_without_permitted_reason"
                    )
                    if not injected_overlap:
                        invalid.append(record_id)
            except (ValueError, TypeError, KeyError):
                invalid.append(record_id)
        check_name = f"{table_name}.{first_field}" + (f"_before_{second_field}" if second_field else "_valid")
        checks[check_name] = not invalid
        if invalid:
            errors.append(f"{table_name}: invalid date or date ordering; records={invalid[:5]}")

    invalid_renewal_dates = []
    for renewal in tables["renewals"]:
        policy = policies.get(renewal.get("policy_id"))
        if not policy:
            continue
        try:
            if parse_date(renewal["offer_date"]) >= parse_date(policy["expiry_date"]):
                invalid_renewal_dates.append(renewal["renewal_id"])
        except (ValueError, TypeError, KeyError):
            invalid_renewal_dates.append(renewal["renewal_id"])
    checks["renewals.offer_before_policy_expiry"] = not invalid_renewal_dates
    if invalid_renewal_dates:
        errors.append(f"Renewal offers must precede policy expiry: {invalid_renewal_dates[:5]}")

    # 5. Arithmetic reconciliation: premium formula, policy/quote match, renewals.
    invalid_premiums, invalid_policy_premiums, invalid_renewal_premiums = [], [], []
    for quote in tables["quotes"]:
        premium = quote.get("calculated_premium", "")
        if premium in ("", None):
            if quote.get("risk_data_missing") != "True":
                invalid_premiums.append(quote["quote_id"])
            continue
        try:
            applicant = applicants[quote["applicant_id"]]
            product = products[quote["product_id"]]
            coverage = coverages[quote["coverage_option_id"]]
            expected = round(max(50.0, float(coverage["limit_amount"]) * float(product["base_rate"]) * (
                1 + 0.08 * int(quote["prior_claims"])
                + (0.35 if int(quote["risk_score"]) >= 70 else 0)
                + (0.12 if int(applicant["age"]) < 25 else 0)
            )), 2)
            actual = round(float(premium), 2)
            injected_premium = truth.get(("Quote", quote["quote_id"])) == "premium_outside_defined_rate_formula"
            if abs(actual - expected) > 0.011 and not injected_premium:
                invalid_premiums.append(quote["quote_id"])
        except (ValueError, TypeError, KeyError):
            invalid_premiums.append(quote["quote_id"])
    checks["quotes.premium_formula_valid"] = not invalid_premiums
    if invalid_premiums:
        errors.append(f"Quote premium formula mismatch: {invalid_premiums[:5]}")

    for policy in tables["policies"]:
        quote = quotes.get(policy.get("quote_id"))
        if not quote:
            continue
        try:
            mismatch = abs(float(policy["premium_amount"]) - float(quote["calculated_premium"])) > 0.011
            quote_has_injected_premium = truth.get(("Quote", quote["quote_id"])) == "premium_outside_defined_rate_formula"
            if mismatch and not quote_has_injected_premium:
                invalid_policy_premiums.append(policy["policy_id"])
        except (ValueError, TypeError, KeyError):
            invalid_policy_premiums.append(policy["policy_id"])
    checks["policies.premium_matches_quote"] = not invalid_policy_premiums
    if invalid_policy_premiums:
        errors.append(f"Policy premium does not match linked quote: {invalid_policy_premiums[:5]}")

    for renewal in tables["renewals"]:
        policy = policies.get(renewal.get("policy_id"))
        if not policy:
            continue
        try:
            expected = round(float(policy["premium_amount"]) * 1.04, 2)
            if abs(float(renewal["renewal_premium"]) - expected) > 0.011:
                invalid_renewal_premiums.append(renewal["renewal_id"])
        except (ValueError, TypeError, KeyError):
            invalid_renewal_premiums.append(renewal["renewal_id"])
    checks["renewals.premium_formula_valid"] = not invalid_renewal_premiums
    if invalid_renewal_premiums:
        errors.append(f"Renewal premium calculation mismatch: {invalid_renewal_premiums[:5]}")

    # 6. Lifecycle transitions and cross-entity consistency.
    invalid_quote_lifecycle, invalid_policy_lifecycle, invalid_acceptance = [], [], []
    for quote in tables["quotes"]:
        if quote.get("risk_data_missing") == "True" and quote.get("quote_status") != "referred":
            invalid_quote_lifecycle.append(quote["quote_id"])
        if quote.get("quote_status") == "offered" and quote.get("eligibility_status") != "eligible":
            invalid_quote_lifecycle.append(quote["quote_id"])
    checks["quotes.lifecycle_consistent"] = not invalid_quote_lifecycle
    if invalid_quote_lifecycle:
        errors.append(f"Inconsistent quote lifecycle: {invalid_quote_lifecycle[:5]}")

    for policy in tables["policies"]:
        policy_id = policy["policy_id"]
        issue = policy.get("acceptance_status") != "accepted" or policy.get("payment_status") != "paid"
        if issue and truth.get(("Policy", policy_id)) != "policy_issued_without_acceptance":
            invalid_acceptance.append(policy_id)
        quote = quotes.get(policy.get("quote_id"))
        if quote:
            consistent = all(policy.get(pf) == quote.get(qf) for pf, qf in [
                ("applicant_id", "applicant_id"), ("asset_id", "asset_id"),
                ("product_id", "product_id"), ("coverage_option_id", "coverage_option_id")
            ])
            injected_overlap = truth.get(("Policy", policy_id)) == "overlapping_policy_periods_without_permitted_reason"
            if not consistent and not injected_overlap:
                invalid_policy_lifecycle.append(policy_id)
            if quote.get("eligibility_status") != "eligible" or quote.get("quote_status") != "offered":
                if not injected_overlap:
                    invalid_policy_lifecycle.append(policy_id)
    checks["policies.acceptance_payment_valid"] = not invalid_acceptance
    checks["policies.lifecycle_consistent"] = not invalid_policy_lifecycle
    if invalid_acceptance:
        errors.append(f"Policy issued without acceptance/payment: {invalid_acceptance[:5]}")
    if invalid_policy_lifecycle:
        errors.append(f"Policy does not match linked quote or quote is not eligible and offered: {invalid_policy_lifecycle[:5]}")

    invalid_endorsements = []
    for endorsement in tables["endorsements"]:
        policy = policies.get(endorsement.get("policy_id"))
        if not policy:
            continue
        product = products.get(policy.get("product_id"))
        if not product:
            continue
        try:
            resulting = float(endorsement["resulting_coverage"])
            limit = float(product["max_coverage"])
            injected_limit = truth.get(("Endorsement", endorsement["endorsement_id"])) == "endorsement_exceeds_product_limit"
            if resulting > limit and not injected_limit:
                invalid_endorsements.append(endorsement["endorsement_id"])
            if parse_date(endorsement["effective_date"]) < parse_date(policy["effective_date"]):
                invalid_endorsements.append(endorsement["endorsement_id"])
            if endorsement.get("endorsement_type") == "asset_change":
                previous_value = float(endorsement["previous_asset_value"])
                new_value = float(endorsement["new_asset_value"])
                if previous_value <= 0 or new_value <= 0 or previous_value == new_value:
                    invalid_endorsements.append(endorsement["endorsement_id"])
                if endorsement.get("asset_id") not in {a["asset_id"] for a in tables["insured_assets"]}:
                    invalid_endorsements.append(endorsement["endorsement_id"])
        except (ValueError, TypeError, KeyError):
            invalid_endorsements.append(endorsement["endorsement_id"])
    checks["endorsements.lifecycle_and_limit_valid"] = not invalid_endorsements
    if invalid_endorsements:
        errors.append(f"Invalid endorsement date or product coverage limit: {invalid_endorsements[:5]}")

    invalid_cancelled_renewals = []
    for renewal in tables["renewals"]:
        policy = policies.get(renewal.get("policy_id"))
        if not policy:
            continue
        if (policy.get("policy_status") == "cancelled"
                and renewal.get("renewal_status") in ("offered", "accepted")
                and truth.get(("Renewal", renewal["renewal_id"])) != "renewal_generated_for_cancelled_policy"):
            invalid_cancelled_renewals.append(renewal["renewal_id"])
    checks["renewals.cancelled_policy_valid"] = not invalid_cancelled_renewals
    if invalid_cancelled_renewals:
        errors.append(f"Renewal offered for cancelled policy: {invalid_cancelled_renewals[:5]}")

    # 7. Duplicate business-record checks (in addition to primary keys).
    duplicate_rules = [
        ("policies", ("quote_id",)),
        ("endorsements", ("policy_id", "effective_date", "endorsement_type")),
        ("renewals", ("policy_id", "proposed_effective_date")),
        ("underwriting_decisions", ("quote_id", "decision_date", "decision")),
    ]
    for table_name, fields in duplicate_rules:
        keys = [tuple(row.get(field, "") for field in fields) for row in tables[table_name]]
        duplicates = [key for key, count in Counter(keys).items() if count > 1]
        checks[f"{table_name}.business_duplicates_absent"] = not duplicates
        if duplicates:
            errors.append(f"{table_name}: duplicate business records for {fields}: {duplicates[:5]}")

    # 8. Overlapping policy periods, except the explicitly labelled anomaly.
    grouped = {}
    for policy in tables["policies"]:
        grouped.setdefault((policy["applicant_id"], policy["asset_id"]), []).append(policy)
    invalid_overlaps = []
    for group in grouped.values():
        group.sort(key=lambda row: row["effective_date"])
        for index, first in enumerate(group):
            for second in group[index + 1:]:
                if first["expiry_date"] < second["effective_date"]:
                    continue
                if first.get("permitted_overlap_reason") or second.get("permitted_overlap_reason"):
                    continue
                first_injected = truth.get(("Policy", first["policy_id"])) == "overlapping_policy_periods_without_permitted_reason"
                second_injected = truth.get(("Policy", second["policy_id"])) == "overlapping_policy_periods_without_permitted_reason"
                if not first_injected and not second_injected:
                    invalid_overlaps.append((first["policy_id"], second["policy_id"]))
    checks["policies.period_overlap_valid"] = not invalid_overlaps
    if invalid_overlaps:
        errors.append(f"Overlapping policy periods without permitted reason: {invalid_overlaps[:5]}")

    # 9. Validate separate ground truth without counting it as an entity.
    actual_anomalies = {row.get("issue_type", "") for row in ground_truth}
    checks["required_anomaly_count"] = len(ground_truth) == 5
    checks["required_anomaly_types_present"] = actual_anomalies == REQUIRED_ANOMALIES
    if len(ground_truth) != 5:
        errors.append(f"Expected 5 ground-truth cases, found {len(ground_truth)}")
    if actual_anomalies != REQUIRED_ANOMALIES:
        errors.append(f"Ground-truth anomaly types do not match requirements. Found: {sorted(actual_anomalies)}")
    for row in ground_truth:
        if row.get("ground_truth_label") != "invalid" or row.get("injected") not in ("True", "true", "1"):
            errors.append(f"Ground-truth case {row.get('case_id', '<missing>')} has invalid label/injected flag")
            break
        if (row.get("entity_type", ""), row.get("entity_id", "")) not in truth:
            errors.append(f"Ground-truth case {row.get('case_id', '<missing>')} is missing entity identity")
            break

    # The row-count report deliberately contains exactly the ten core entities.
    summary = {
        "status": "PASS" if not errors else "FAIL",
        "row_counts": {name: len(rows) for name, rows in tables.items()},
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "ground_truth_cases": ground_truth,
    }
    (data_dir / "validation_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Validate insurance workflow datasets.")
    parser.add_argument("--data", default="data")
    args = parser.parse_args()
    result = validate(args.data)
    print(json.dumps({"status": result["status"], "row_counts": result["row_counts"], "checks": result["checks"], "errors": result["errors"]}, indent=2))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
