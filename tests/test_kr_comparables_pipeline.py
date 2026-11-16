"""국내 비교기업 끝까지 연결 — kr_comparable_candidates → kr_comparable_profile_compare → tp_comparable_screen(사분위). Claude 작성(2026-11-16).
네트워크 없이 고정본(tests/data/kr_comparables_fixtures)으로. 각 단계 출력을 손대지 않고 다음 도구 입력에 그대로 넣는다.
분석대상은 비율만 둔 테스트 입력(재판매형 — 상품 매출 위주, 재고 부담, 광고 일부, 제조·연구 없음)."""
import functools
import json

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import revenue_mix as RM
from korean_tax_calc_mcp.engine.kr_comparables.dart import DartClient
from tests.test_kr_comparable_candidates import FAKE_KEY, GOLD, Transport, _gold_solar

TESTED = {"main_category": "merchandise", "main_share": 0.90, "inventory_basis": "ratio", "inv_to_sales": 0.15,
          "raw_material_inv": False, "ppe_ratio": 0.05, "rnd_ratio": 0.0, "advert_ratio": 0.02}
# tp_comparable_screen 분석대상 — 금액 대신 매출 100 기준 비율(영업이익률 3%)
TESTED_PARTY = {"name": "분석대상", "is_resident": True,
                "years": {2024: {"revenue": 100, "operating_profit": 3, "inventory": 15, "receivables": 12, "payables": 8, "total_assets": 60}}}


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DART_API_KEY", FAKE_KEY)
    monkeypatch.setenv("UPSTAGE_API_KEY", "u" * 20)
    tr = Transport()
    monkeypatch.setattr(C, "DartClient", functools.partial(DartClient, transport=tr, interval=0, sleep=lambda s: None))
    monkeypatch.setattr(RM, "solar_http", _gold_solar)
    cand = S.kr_comparable_candidates(industry_codes=["46"], years=[2024], listed="둘 다", limit=10)
    cmp_ = S.kr_comparable_profile_compare(tested=TESTED, candidates=cand)
    return cand, cmp_, tr


def _om(cc):
    v = GOLD[cc]["values"]
    return v["operating_profit"] / v["revenue"]


def _q_inclusive(xs, p):
    xs = sorted(xs)
    h = (len(xs) - 1) * p
    lo = int(h)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (h - lo)


def test_candidates_to_compare(pipeline):
    cand, cmp_, tr = pipeline
    assert "error" not in cand and cand["결과"]["후보_수"] == 5 and tr.urls
    r = cmp_["결과"]
    assert r["후보_수"] == 5
    by = {x["company_id"]: x for x in r["비교표"]}
    name = {cc: g["corp_name"] for cc, g in GOLD.items()}
    got = {name[k]: v["종합"] for k, v in by.items()}
    # 1단계 손 판정과 같되, 유니트론텍은 원문 유형 칸이 없는 매출 행을 모델로 분류(99.8%) → 사람 확인
    assert got == {"(주)유니트론텍": "사람 확인", "(주)휴맥스": "제외 후보", "상신코퍼레이션": "포함 후보",
                   "애보트메디칼코리아": "포함 후보", "케이엘페트로": "제외 후보"}
    rv = r["사람_확인_목록"][0]
    assert any("매출 행 분류 확인 필요" in x for x in rv["사유"]) and rv["매출_행"] and rv["근거"]["매출 구성"]["rcept_no"]
    assert {d["company_id"] for d in r["manual_decisions_초안"]} == {k for k, v in by.items() if v["종합"] == "제외 후보"}
    assert all(d["decision"] == "reject" and d["reason"] and "초안" in d["상태"] for d in r["manual_decisions_초안"])
    assert r["사용_기준"]["mix_max_diff"] == 0.20


def test_end_to_end_quartiles(pipeline):
    cand, cmp_, _ = pipeline
    r = cmp_["결과"]
    # 사람 확인: 검토자가 유니트론텍의 매출 행(반도체·디스플레이 재판매)을 원문으로 확인하고 포함 — 따로 넣을 판단 없음
    # 제외 후보 초안: 검토자가 사유를 확인하고 reviewer를 채워 확정
    decisions = [{k: v for k, v in d.items() if k != "상태"} | {"reviewer": "검토자"} for d in r["manual_decisions_초안"]]
    rows = cand["결과"]["후보_행"]                       # 후보 도구 출력 그대로
    scr = S.tp_comparable_screen(tested_party=TESTED_PARTY, analysis_years=[2024], tested_year=2024, rows=rows,
                                 manual_decisions=decisions, multi_year_reason={"code": 3, "text": "테스트 — 한 해 자료"},
                                 search_log={"db": "OpenDART", "steps": ["업종 46", "프로필 비교"]})
    assert "error" not in scr, scr
    res = scr["결과"]
    expected_ids = {cc for cc, g in GOLD.items() if g["corp_name"] in ("(주)유니트론텍", "상신코퍼레이션", "애보트메디칼코리아")}
    assert res["후보_수"] == 5 and res["최종_수"] == 3
    assert {x["company_id"] for x in scr["최종_비교대상"]} == expected_ids
    # 영업이익률(원문 대조 정답 값) 사분위 — inclusive
    oms = [_om(cc) for cc in expected_ids]
    rng = res["범위"]
    assert rng["계산법"] == "inclusive"
    assert rng["제1사분위%"] == pytest.approx(_q_inclusive(oms, 0.25) * 100, abs=5e-4)
    assert rng["중위값%"] == pytest.approx(_q_inclusive(oms, 0.5) * 100, abs=5e-4)
    assert rng["제3사분위%"] == pytest.approx(_q_inclusive(oms, 0.75) * 100, abs=5e-4)
    assert res["분석대상_값%"] == pytest.approx(3.0) and res["범위_안"] is True
    # 제외 후보는 사람 판단(S12)으로 탈락 사유표에 남는다
    m = json.dumps(scr["탈락_매트릭스"], ensure_ascii=False)
    assert m.count("수동 탈락: 프로필 비교") == 2
    # 다음 단계(arm_length_range)에 그대로 넣을 입력이 나온다
    alr = scr["arm_length_range_입력"]
    assert len(alr["comparables"]) == 3 and alr["tested_value"] == pytest.approx(0.03)
    ar = S.arm_length_range(**{k: v for k, v in alr.items() if not k.endswith("_안내")})
    assert "error" not in ar, ar
    assert ar["결과"]["제1사분위"] == pytest.approx(_q_inclusive(oms, 0.25), abs=1e-6)
    assert ar["결과"]["제3사분위"] == pytest.approx(_q_inclusive(oms, 0.75), abs=1e-6)
    assert ar["결과"]["범위_안"] is True and ar["결과"]["조정액"] == 0

def test_compare_input_guards():
    with pytest.raises(ValueError):
        from korean_tax_calc_mcp.engine.kr_comparables import profile_compare
        profile_compare({"main_category": "x", "main_share": 0.9}, [{}])
    r = S.kr_comparable_profile_compare(tested=TESTED, candidates=[], rules=None)
    assert "error" in r
    r = S.kr_comparable_profile_compare(tested=TESTED, candidates=[{"company_id": "A"}], rules={"없는키": 1})
    assert "error" in r and "없는키" in json.dumps(r, ensure_ascii=False)
