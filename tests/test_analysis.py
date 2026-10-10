"""Small reproducibility checks for the DECODE analysis pipeline."""
import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class TestDECODEAnalysis(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / "outputs"
        cls.fig = Path(cls.temp.name) / "figures"
        subprocess.run([
            sys.executable, str(ROOT / "src/analyze_decode.py"),
            "--input", str(ROOT / "data/raw_matches.csv"),
            "--output-dir", str(cls.out),
            "--figures-dir", str(cls.fig),
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_row_counts_and_top_ranks(self):
        summary = json.loads((self.out / "summary.json").read_text())
        self.assertEqual((summary["raw_rows"], summary["clean_rows"], summary["teams"]), (109, 108, 18))
        self.assertEqual(summary["overall_top5"][0], "T08")
        self.assertEqual(summary["team_3470_overall_rank"], 6)
        self.assertEqual(summary["team_3470_best_partners"], ["T08", "T14", "T17", "T02", "T06"])

    def test_cleaning_is_traceable(self):
        rows = csv_rows(self.out / "cleaned_matches.csv")
        self.assertEqual(len(rows), 108)
        self.assertEqual(sum(row["match_id"] == "M23-T09-4" for row in rows), 1)
        suspicious = next(row for row in rows if row["match_id"] == "M14-T05-3")
        self.assertEqual(int(suspicious["cl_scored"]), 28)
        self.assertEqual(int(suspicious["analysis_excluded_from_cl"]), 1)

    def test_prefix_ambiguity_and_uncertainty(self):
        prefix = csv_rows(self.out / "match_prefix_audit.csv")
        self.assertEqual(len(prefix), 36)
        self.assertEqual(sum(int(r["same_alliance_score_conflict"]) for r in prefix), 36)
        self.assertGreaterEqual(len(csv_rows(self.out / "ambiguity_uncertainty.csv")), 3)
        self.assertGreaterEqual(len(csv_rows(self.out / "match_strategy_examples.csv")), 3)

    def test_reproduces_published_csv_outputs(self):
        for name in ["team_rankings.csv", "compatibility_ranking_3470.csv",
                     "alliance_picklist.csv", "recommendations_3470.csv",
                     "team_metrics.csv", "match_prefix_audit.csv"]:
            self.assertEqual(
                (self.out / name).read_bytes(), (ROOT / "outputs" / name).read_bytes(),
                msg=f"Published {name} differs from newly generated output",
            )


if __name__ == "__main__":
    unittest.main()
