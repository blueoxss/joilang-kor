from __future__ import annotations

import json

import pytest

from joilang_kor import evaluation as E


def test_golden_worked_example(parity):
    g = parity["golden"]
    item = E.evaluate_item(g["gt"], g["concise_candidate"])
    assert abs(item["e"] - g["expected_e"]) < 1e-9
    assert item["det_pass"] is True and item["v"] == 1
    exact = E.evaluate_item(g["gt"], g["gt"])
    assert exact["e"] == 1.0 and exact["det_pass"] is True


def test_root_function_matches_frozen_original(parity):
    for case in parity["evaluation"]:
        got = E.original_det_evaluate_row(row={"gt": case["gt"]}, candidate=case["candidate"], row_no=case["row_no"])
        for key, expected in case["expected"].items():
            assert got[key] == expected, (case["row_no"], key)


def test_public_score_equals_root_score_scaled(parity):
    for case in parity["evaluation"]:
        item = E.evaluate_item(case["gt"], case["candidate"])
        assert item["e"] * 100 == pytest.approx(case["expected"]["det_score"], abs=1e-3)
        assert item["v"] == (0 if any(r in case["expected"]["failure_reasons"] for r in E.HARD_GATE_REASONS) else 1)


def test_threshold_boundary_and_gates():
    gt = json.dumps({"name": "", "cron": "", "period": 0, "script": "(#Light).switch_on()"})
    same = json.dumps({"name": "", "cron": "", "period": 0, "code": "(#Light).switch_on()"})
    assert E.evaluate_item(gt, same)["e"] == 1.0
    assert E.evaluate_item(gt, same, threshold=1.0)["det_pass"] is True
    invalid = E.evaluate_item(gt, "not json")
    assert invalid["e"] == 0.0 and invalid["v"] == 0 and "invalid_json" in invalid["failure_reasons"]
    empty_code = E.evaluate_item(gt, json.dumps({"name": "", "cron": "", "period": 0, "code": ""}))
    assert empty_code["v"] == 0 and empty_code["det_pass"] is False
    assert empty_code["components"]["schedule_match"] == 1.0  # 다른 비교값은 남는다
    with pytest.raises(ValueError):
        E.weighted_score([1.0] * 8, (0.5,) * 8)


def test_components_follow_appendix_rules():
    gt = json.dumps({"name": "", "cron": "0 9 * * *", "period": 0, "script": "var x = 1\n(#Kitchen #Light).light_movetorgb(23, 0, 'on')"})
    cand = json.dumps({"name": "", "cron": "0 9 * * *", "period": -1, "code": "(#Kitchen #Light).light_movetorgb(23.0, 0, 'ON')"})
    c = E.evaluate_item(gt, cand)["components"]
    assert c["schedule_match"] == 0.5          # cron 일치, period 불일치
    assert c["numeric_grounding"] == pytest.approx(1 / 3)  # 기준 수치 문자열 '1','23','0' 중 '0'만 포함('23'≠'23.0')
    assert c["string_enum_grounding"] == 1.0   # 소문자 변환 후 비교
    assert c["declaration_count"] == 0.0       # var 선언 1개 기준, 생성 0개
    assert c["receiver_coverage"] == 1.0 and c["required_service_recall"] == 1.0


def test_aggregate():
    results = [{"e": 1.0, "det_pass": True}, {"e": 0.5, "det_pass": False}]
    agg = E.aggregate(results)
    assert agg == {"n": 2, "passed": 1, "detpass": 0.5, "sdet": 0.75}
