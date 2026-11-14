"""tp_comparable_screen — 합성 후보 20개사(tests/data/tp_screen_candidates_1114.csv, 가상 회사). Claude 작성(2026-11-14).
기댓값은 레포 밖 원형 스크립트로 먼저 계산한 값(A·B·C·E·F·G 시나리오)과 같아야 한다."""
import copy
import os

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_tp_screen as T

CSV = os.path.join(os.path.dirname(__file__), "data", "tp_screen_candidates_1114.csv")
YEARS = [2022, 2023, 2024]


def _tp(**kw):
    ys = {}
    for y, rev, om in ((2022, 36e6, 0.024), (2023, 38e6, 0.019), (2024, 40e6, 0.018)):
        ys[y] = {"revenue": rev, "operating_profit": om * rev, "inventory": 0.30 * rev, "receivables": 0.20 * rev, "payables": 0.05 * rev}
    d = {"name": "US Sub", "is_resident": False, "years": ys}
    d.update(kw)
    return d


BASE = {"industry_codes": ["424210"], "size_min": 5e6, "size_max": 1e9}


def run(**kw):
    a = dict(file_path=CSV, tested_party=_tp(), analysis_years=YEARS, tested_year=2025, screens=dict(BASE),
             multi_year_reason={"code": 1, "text": "경기 변동"}, search_log={"db": "가상"})
    a.update(kw)
    return T.comparable_screen(**a)


def test_funnel_and_final():
    r = run()
    assert r["결과"]["후보_수"] == 20 and r["결과"]["최종_수"] == 8
    left = [f["남음"] for f in r["보고서_부록"]["단계별_탈락"]]
    assert left == [20, 19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 9, 8]
    fin = {m["company_id"]: m["최종"] for m in r["탈락_매트릭스"]}
    assert all(fin[f"C0{i}"] == "선정" for i in range(1, 9))
    exp = {"C09": "S1a", "C10": "S1b", "C11": "S2", "C12": "S3", "C13": "S4", "C14": "S5", "C15": "S6", "C16": "S7",
           "C17": "S9", "C18": "S10", "C19": "S11", "C20": "S12"}
    for cid, sc in exp.items():
        assert fin[cid] == f"탈락({sc})", cid


def test_range_and_weighted_average():
    r = run()
    g = r["결과"]["범위"]
    assert (g["제1사분위%"], g["중위값%"], g["제3사분위%"]) == (2.284, 3.091, 4.432)
    assert r["결과"]["분석대상_값%"] == 2.023 and r["결과"]["범위_안"] is False
    w = {f["company_id"]: f["가중평균%"] for f in r["최종_비교대상"]}
    assert w["C01"] == 2.483 and w["C08"] == 13.583
    assert r["결과"]["이상치_표시"] == ["C08"]


def test_sensitivity_flips():
    r = run()
    sc = {s["시나리오"][0]: s for s in r["민감도"]}
    assert (sc["B"]["최종_수"], sc["B"]["제3사분위%"]) == (9, 4.999)
    assert sc["C"]["범위_안"] is True and sc["C"]["제1사분위%"] == 1.687
    assert (sc["E"]["제1사분위%"], sc["E"]["제3사분위%"]) == (3.334, 6.032)
    assert sc["F"]["범위_안"] is True and sc["F"]["제1사분위%"] == 1.886
    assert (sc["G"]["최종_수"], sc["G"]["제3사분위%"]) == (7, 3.772)
    assert r["경고"][0].startswith("선정 기준에 민감")


def test_feeds_arm_length_range_same_quartiles():
    r = run()
    a = r["arm_length_range_입력"]
    out = S.arm_length_range(a["comparables"], a["tested_value"], tested_is_resident=a["tested_is_resident"], quartile_method=a["quartile_method"], year=a["year"])
    assert round(out["결과"]["제1사분위"] * 100, 3) == 2.284 and round(out["결과"]["제3사분위"] * 100, 3) == 4.432
    assert out["결과"]["거주자_소득"] == "과다"


def test_independence_over_50_is_error():
    r = run(screens={**BASE, "independence_pct": 60})
    assert "error" in r and any("50 이하" in p for p in r["문제"])


def test_manual_reason_required():
    r = run(manual_decisions=[{"company_id": "C01", "decision": "reject", "reason": ""}])
    assert "error" in r


def test_manual_accept_cannot_override_legal_50():
    r = run(manual_decisions=[{"company_id": "C09", "decision": "accept", "reason": "검토"}, {"company_id": "C10", "decision": "accept", "reason": "실질 독립 확인"}])
    fin = {m["company_id"]: m["최종"] for m in r["탈락_매트릭스"]}
    assert fin["C09"] == "탈락(S1a)" and fin["C10"] == "선정"


def test_warnings_multi_year_and_period_mismatch():
    r = run(multi_year_reason=None, tested_years=[2024])
    assert any("multi_year_reason" in w for w in r["경고"]) and any("기간" in w for w in r["경고"])


def test_too_few_is_error():
    r = run(screens={**BASE, "rnd_max": 0.0, "adv_max": 0.0})
    assert "error" in r and "둘 미만" in r["error"]


def test_crisis_exception_marks_review():
    r = run(screens={**BASE, "crisis_exception": True})
    m = {x["company_id"]: x for x in r["탈락_매트릭스"]}
    assert m["C14"]["S5"].startswith("검토 필요") and m["C14"]["최종"] == "선정"


def test_basis_by_period():
    assert "구 시행령 제4조" in run(tested_year=2019)["근거"]
    b = run(tested_year=2023)["근거"]
    assert "시행령 제8조①" in b and "별지 제1호서식 작성방법 10" in b and "⑦" in b
    assert "별지 제1호서식" not in run(tested_year=2021)["근거"]


def test_op_reconciliation_flag():
    import csv
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    rows = copy.deepcopy(rows)
    rows[0]["operating_profit"] = str(float(rows[0]["operating_profit"]) + 0.01 * float(rows[0]["revenue"]))
    r = run(file_path=None, rows=rows)
    assert any(d["company_id"] == "C01" and d["연도"] == 2022 for d in r["영업이익_대사"])


def test_mixed_currency_skips_size():
    import csv
    rows = list(csv.DictReader(open(CSV, encoding="utf-8")))
    for x in rows:
        if x["company_id"] == "C02":
            x["currency"] = "EUR"
    r = run(file_path=None, rows=rows)
    assert any("환율" in w for w in r["경고"])
    m = {x["company_id"]: x for x in r["탈락_매트릭스"]}
    assert m["C13"]["S4"].startswith("건너뜀")


def test_server_tool():
    r = S.tp_comparable_screen(tested_party=_tp(), analysis_years=YEARS, tested_year=2025, file_path=CSV, screens=dict(BASE))
    assert r["결과"]["최종_수"] == 8 and "탈락_매트릭스" in r


def test_wca_requires_basis():
    assert "error" in run(wca={"rate": 0.05})
    r = run(wca={"rate": 0.05, "rate_basis": "예시"})
    assert r["결과"]["범위"]["제1사분위%"] == 3.334
