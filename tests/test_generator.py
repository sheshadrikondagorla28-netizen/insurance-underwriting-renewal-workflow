"""Acceptance and negative tests for the insurance workflow project.

Run from the project root:
    python -m unittest discover -s tests -v
"""
import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from insurance_workflow.generator import generate
from insurance_workflow.validator import validate


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class InsuranceWorkflowAcceptanceTests(unittest.TestCase):
    """Tests for generated outputs and documented workflow requirements."""

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.data_dir = Path(cls._temp.name) / "baseline"
        generate(cls.data_dir, seed=20261022, scale=1, anomalies=True)
        cls.validation = validate(cls.data_dir)

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def read_rows(self, filename):
        with (self.data_dir / filename).open("r", newline="", encoding="utf-8") as file:
            return list(csv.DictReader(file))

    def test_01_baseline_dataset_passes_validation(self):
        self.assertEqual(self.validation["status"], "PASS", self.validation["errors"])

    def test_02_required_entity_csv_files_exist(self):
        required = [
            "applicants.csv", "insured_assets.csv", "products.csv",
            "coverage_options.csv", "risk_factors.csv", "quotes.csv",
            "policies.csv", "endorsements.csv", "renewals.csv",
            "underwriting_decisions.csv", "ground_truth.csv",
        ]
        for filename in required:
            with self.subTest(filename=filename):
                self.assertTrue((self.data_dir / filename).is_file())

    def test_03_default_record_counts_match_requirements(self):
        expected = {
            "applicants": 3000, "insured_assets": 3000, "products": 3,
            "coverage_options": 6, "risk_factors": 4, "quotes": 4000,
            "policies": 2000, "endorsements": 200, "renewals": 1200,
        }
        for table, count in expected.items():
            with self.subTest(table=table):
                self.assertEqual(self.validation["row_counts"][table], count)

    def test_04_ids_follow_required_naming_conventions(self):
        for row in self.read_rows("applicants.csv"):
            self.assertRegex(row["applicant_id"], r"^APP-2026-\d{6}$")
        for row in self.read_rows("quotes.csv"):
            self.assertRegex(row["quote_id"], r"^QTE-2026-\d{6}$")
        for row in self.read_rows("policies.csv"):
            self.assertRegex(row["policy_id"], r"^POL-2026-\d{6}$")

    def test_05_three_product_lines_are_present(self):
        lines = {row["product_line"] for row in self.read_rows("products.csv")}
        self.assertEqual(lines, {"motor", "property", "business"})

    def test_06_all_quote_parent_references_exist(self):
        applicants = {r["applicant_id"] for r in self.read_rows("applicants.csv")}
        assets = {r["asset_id"] for r in self.read_rows("insured_assets.csv")}
        products = {r["product_id"] for r in self.read_rows("products.csv")}
        coverages = {r["coverage_option_id"] for r in self.read_rows("coverage_options.csv")}
        for quote in self.read_rows("quotes.csv"):
            self.assertIn(quote["applicant_id"], applicants)
            self.assertIn(quote["asset_id"], assets)
            self.assertIn(quote["product_id"], products)
            self.assertIn(quote["coverage_option_id"], coverages)

    def test_07_policy_issuance_has_acceptance_and_payment_except_labelled_anomaly(self):
        anomalies = {(r["entity_type"], r["entity_id"]) for r in self.read_rows("ground_truth.csv")}
        for policy in self.read_rows("policies.csv"):
            if ("Policy", policy["policy_id"]) not in anomalies:
                self.assertEqual(policy["acceptance_status"], "accepted")
                self.assertEqual(policy["payment_status"], "paid")

    def test_08_missing_risk_data_is_referred_without_premium(self):
        quotes = self.read_rows("quotes.csv")
        missing = [q for q in quotes if q["risk_data_missing"].lower() == "true"]
        self.assertTrue(missing, "Expected missing-risk-data scenarios")
        self.assertTrue(all(q["quote_status"] == "referred" for q in missing))
        self.assertTrue(all(q["calculated_premium"] == "" for q in missing))

    def test_09_renewal_premiums_reconcile_to_policy_premium(self):
        policies = {p["policy_id"]: p for p in self.read_rows("policies.csv")}
        for renewal in self.read_rows("renewals.csv"):
            policy = policies[renewal["policy_id"]]
            expected = round(float(policy["premium_amount"]) * 1.04, 2)
            self.assertAlmostEqual(float(renewal["renewal_premium"]), expected, places=2)

    def test_10_endorsement_records_preserve_change_history(self):
        endorsements = self.read_rows("endorsements.csv")
        self.assertEqual(len(endorsements), 200)
        for endorsement in endorsements:
            self.assertEqual(endorsement["endorsement_type"], "asset_change")
            self.assertNotEqual(endorsement["previous_asset_value"], endorsement["new_asset_value"])
            self.assertTrue(endorsement["endorsement_id"].startswith("END-"))

    def test_11_ground_truth_contains_all_five_required_anomaly_types(self):
        expected = {
            "policy_issued_without_acceptance",
            "premium_outside_defined_rate_formula",
            "endorsement_exceeds_product_limit",
            "renewal_generated_for_cancelled_policy",
            "overlapping_policy_periods_without_permitted_reason",
        }
        rows = self.read_rows("ground_truth.csv")
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["issue_type"] for row in rows}, expected)
        self.assertTrue(all(row["ground_truth_label"] == "invalid" for row in rows))

    def test_12_json_exports_and_data_dictionary_exist(self):
        for name in ("applicants", "quotes", "policies", "renewals", "underwriting_decisions"):
            path = self.data_dir / f"{name}.json"
            self.assertTrue(path.is_file())
            with path.open(encoding="utf-8") as file:
                self.assertIsInstance(json.load(file), list)
        dictionary = self.data_dir / "data_dictionary.json"
        self.assertTrue(dictionary.is_file())
        json.loads(dictionary.read_text(encoding="utf-8"))

    def test_13_sql_seed_schema_manifest_and_validation_report_exist(self):
        for filename in ("schema.sql", "seed_data.sql", "source_manifest.json", "validation_summary.json"):
            with self.subTest(filename=filename):
                self.assertTrue((self.data_dir / filename).is_file())

    def test_14_same_seed_generates_identical_core_csv_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            second = Path(tmp) / "second"
            generate(second, seed=20261022, scale=1, anomalies=True)
            for filename in ("applicants.csv", "quotes.csv", "policies.csv", "ground_truth.csv"):
                with self.subTest(filename=filename):
                    first_hash = hashlib.sha256((self.data_dir / filename).read_bytes()).hexdigest()
                    second_hash = hashlib.sha256((second / filename).read_bytes()).hexdigest()
                    self.assertEqual(first_hash, second_hash)

    def test_15_different_seed_changes_generated_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            different = Path(tmp) / "different"
            generate(different, seed=12345, scale=1, anomalies=True)
            self.assertNotEqual(
                hashlib.sha256((self.data_dir / "applicants.csv").read_bytes()).hexdigest(),
                hashlib.sha256((different / "applicants.csv").read_bytes()).hexdigest(),
            )


class InsuranceWorkflowValidatorNegativeTests(unittest.TestCase):
    """Ensure validator rejects common accidental data corruption."""

    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.baseline = Path(cls._temp.name) / "baseline"
        generate(cls.baseline, seed=20261022, scale=1, anomalies=True)

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def corrupted_copy(self, name):
        target = Path(tempfile.mkdtemp()) / "data"
        shutil.copytree(self.baseline, target)
        self.addCleanup(shutil.rmtree, target.parent, ignore_errors=True)
        return target

    @staticmethod
    def load_csv(path):
        with path.open("r", newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            return reader.fieldnames, list(reader)

    @staticmethod
    def save_csv(path, fieldnames, rows):
        with path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_16_missing_required_file_fails_validation(self):
        data = self.corrupted_copy("missing")
        (data / "applicants.csv").unlink()
        result = validate(data)
        self.assertEqual(result["status"], "FAIL")

    def test_17_duplicate_primary_key_fails_validation(self):
        data = self.corrupted_copy("duplicate")
        path = data / "applicants.csv"
        fields, rows = self.load_csv(path)
        rows.append(rows[0].copy())
        self.save_csv(path, fields, rows)
        result = validate(data)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("primary keys" in error for error in result["errors"]))

    def test_18_invalid_foreign_key_fails_validation(self):
        data = self.corrupted_copy("bad_fk")
        path = data / "quotes.csv"
        fields, rows = self.load_csv(path)
        rows[0]["applicant_id"] = "APP-DOES-NOT-EXIST"
        self.save_csv(path, fields, rows)
        result = validate(data)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(any("invalid references" in error for error in result["errors"]))

    def test_19_invalid_enum_fails_validation(self):
        data = self.corrupted_copy("bad_enum")
        path = data / "products.csv"
        fields, rows = self.load_csv(path)
        rows[0]["product_line"] = "unknown_line"
        self.save_csv(path, fields, rows)
        result = validate(data)
        self.assertEqual(result["status"], "FAIL")

    def test_20_tampered_premium_fails_validation(self):
        data = self.corrupted_copy("bad_premium")
        path = data / "quotes.csv"
        fields, rows = self.load_csv(path)
        target = next(row for row in rows if row["calculated_premium"] not in ("", "None"))
        target["calculated_premium"] = str(round(float(target["calculated_premium"]) + 999.0, 2))
        self.save_csv(path, fields, rows)
        result = validate(data)
        self.assertEqual(result["status"], "FAIL")

    def test_21_missing_ground_truth_fails_validation(self):
        data = self.corrupted_copy("missing_truth")
        (data / "ground_truth.csv").unlink()
        result = validate(data)
        self.assertEqual(result["status"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
