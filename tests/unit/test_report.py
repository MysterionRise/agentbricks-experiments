from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

from abx.cost import CostSummary
from abx.gate import EvalSummary, GateVerdict, RowVerdict
from abx.report import read_summary, render_report, write_local, write_volume

WHEN = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


def test_placeholder_report_has_no_numbers():
    text = render_report(None, None, None, "ep", "main.ab_demo.handbook_eval", WHEN)
    assert "Not yet run" in text
    assert "Not yet collected" in text
    assert "PASS" not in text


def test_full_report_renders_tables():
    summary = EvalSummary(
        "run-9",
        39,
        {"direct": 22, "multi_doc": 9, "out_of_scope": 8},
        0.9,
        0.95,
        0.88,
        1.0,
        0,
        worst=[RowVerdict("Q?", "direct", {"correctness": False, "safety": True}, "missed a fact")],
    )
    verdict = GateVerdict(passed=False, reasons=["correctness mean 0.90 below 0.95"])
    cost = CostSummary(
        "ep", 7, True, requests=200, input_tokens=1, output_tokens=2, dbu=1.5, usd_list=3.0
    )
    text = render_report(summary, verdict, cost, "ep", "ds", WHEN)
    assert "**Verdict: FAIL**" in text
    assert "- correctness mean 0.90 below 0.95" in text
    assert "| Correctness | 90% |" in text
    assert "direct 22, multi_doc 9, out_of_scope 8" in text
    assert "**Q?** (direct) failed: correctness" in text
    assert "missed a fact" in text
    assert "| USD per 1k requests | 15.00 |" in text
    assert "2026-10-20 12:00 UTC" in text


def test_unavailable_cost_section():
    cost = CostSummary("ep", 7, False, note="no warehouse")
    text = render_report(None, None, cost, "ep", "ds", WHEN)
    assert "**Unavailable.** no warehouse" in text


def test_write_local_and_read_summary(tmp_path: Path):
    summary = EvalSummary("r", 1, {"direct": 1}, 1.0, 1.0, None, None, 0)
    path = write_local(tmp_path / "reports", "# hi\n", summary)
    assert path.read_text() == "# hi\n"
    assert read_summary(tmp_path / "reports") == summary
    assert read_summary(tmp_path / "nowhere") is None


def test_write_volume_uploads_both_files():
    w = MagicMock()
    summary = EvalSummary("r", 1, {}, None, None, None, None, 0)
    write_volume(w, "/Volumes/x/reports", "text", summary)
    uploaded = [c.args[0] for c in w.files.upload.call_args_list]
    assert uploaded == ["/Volumes/x/reports/latest.md", "/Volumes/x/reports/eval_summary.json"]
