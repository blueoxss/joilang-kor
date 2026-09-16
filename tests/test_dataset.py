from __future__ import annotations

import json

from joilang_kor.data import check_dataset, parse_connected_devices, parse_reference, select_rows
from joilang_kor.evaluation import gt_code


def test_dataset_contract(repo_root):
    report = check_dataset(repo_root / "datasets/JOICommands-280.csv")
    assert report["ok"], report["problems"]
    assert report["rows"] == 280
    assert report["category_counts"] == {"1": 30, "2": 30, "3": 30, "4": 30, "5": 30, "6": 30, "7": 50, "8": 50}
    assert report["unique_category_index_pairs"] == 280
    assert report["rows_with_connected_devices"] == 140
    assert report["sha256"] == "b6f5a7a2d05a4522f8f27f32ef73997e587bcf5c45a7926cddbeedd0fa1a65ce"


def test_reference_fields_and_context_link(rows):
    for row in rows:
        ref = parse_reference(row["gt"])
        assert set(ref) == {"name", "cron", "period", "script"}
        assert isinstance(ref["period"], int)
        assert gt_code(ref).strip()
        assert row["command_eng"].strip() and row["command_kor"].strip()
        devices = parse_connected_devices(row["connected_devices"])
        for meta in devices.values():
            assert "category" in meta and "tags" in meta


def test_select_rows_uses_physical_row_numbers(rows):
    selected = select_rows(rows, start_row=214, end_row=214)
    assert len(selected) == 1 and selected[0][0] == 214
    assert selected[0][1]["category"] == "7" and selected[0][1]["index"] == "34"
    by_category = select_rows(rows, categories=["7"], limit=3)
    assert [row["category"] for _, row in by_category] == ["7", "7", "7"]


def test_examples_match_dataset(repo_root, rows):
    for name in ("scenario.json", "scenario_siren.json"):
        case = json.loads((repo_root / "examples" / name).read_text(encoding="utf-8"))
        row = rows[case["dataset_row_no"] - 1]
        assert row["command_eng"] == case["command_eng"]
        assert row["gt"] == case["reference"]
        assert row["connected_devices"] == case["connected_devices"]
