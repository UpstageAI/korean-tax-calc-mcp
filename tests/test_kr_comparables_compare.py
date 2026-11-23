"""국내 비교기업 프로필 비교 — 정답 20개(tests/data/kr_comparables_gold.json, 원문 공시 대조 값) × 분석대상 2개. Claude 작성(2026-11-16).
분석대상 2개는 테스트 입력용 비율 묶음(특정 회사 아님). 예상 종합 판정은 규칙(engine/kr_comparables/compare.py 머리말)을 손으로 적용해 고정.
네트워크·키 없이 돈다."""
import json
import os

import pytest

from korean_tax_calc_mcp.engine.kr_comparables import (STATUS_NONE, STATUS_OK, STATUS_UNKNOWN, compare_many as _cm,
                                                      compare_profile as _cp, empty_profile, validate_profile, value)
from kr_example_rules import EX_RULES


def compare_profile(t, c, rules=None):          # 예시 기준값을 rules로 넘김(도구에는 관행 기본값 없음)
    return _cp(t, c, {**EX_RULES, **(rules or {})})


def compare_many(t, cs, rules=None):
    return _cm(t, cs, {**EX_RULES, **(rules or {})})

GOLD = json.load(open(os.path.join(os.path.dirname(__file__), "data", "kr_comparables_gold.json"), encoding="utf-8"))["companies"]

# 분석대상(테스트 입력) — 재판매형: 상품 매출 위주, 재고 부담, 광고 일부, 제조·연구 없음
TESTED_RESELLER = {"main_category": "merchandise", "main_share": 0.90, "inventory_basis": "ratio", "inv_to_sales": 0.15,
                   "raw_material_inv": False, "ppe_ratio": 0.05, "rnd_ratio": 0.0, "advert_ratio": 0.02}
# 분석대상(테스트 입력) — 주문 생산형: 제품 매출 위주, 원재료 재고, 연구·광고 거의 없음
TESTED_CONTRACT_MFG = {"main_category": "product", "main_share": 0.95, "inventory_basis": "raw_material", "raw_material_inv": True,
                       "ppe_ratio": 0.35, "rnd_ratio": 0.005, "advert_ratio": 0.0}


def _cell(d):
    return value(d["value"], d["status"], note=d.get("note", ""))


def profile_from_gold(g):
    v = g["values"]
    p = empty_profile(company_id=g["corp_code"], company_name=g["corp_name"], listed=g["listed"], year=g["fiscal_year"],
                      fs_basis=g["fs_basis"], rcept_no=g["rcept_no"])
    mix = g["revenue_mix"]
    if mix["status"] == STATUS_OK:
        p["mix_coverage"] = value(mix["coverage"], rcept_no=g["rcept_no"])
        for k in ("product", "merchandise", "service", "sw_license", "platform_fee", "other"):
            p["mix_" + k] = value(mix["shares"].get(k, 0.0), rcept_no=g["rcept_no"])
    if v["inventory"] is None:
        p["inv_to_sales"] = value(0.0, STATUS_NONE, rcept_no=g["rcept_no"], account="재고자산", note="재무상태표에 재고 계정 없음")
    else:
        p["inv_to_sales"] = value(v["inventory"] / v["revenue"], rcept_no=g["rcept_no"], account="재고자산/매출액")
    p["ppe_ratio"] = value(v["ppe"] / v["total_assets"], rcept_no=g["rcept_no"], account="유형자산/자산총계")
    o = g["profile_other"]
    p["raw_material_inv"] = _cell(o["raw_material_inv"])
    p["rnd_ratio"] = _cell(o["rnd_ratio"])
    p["advert_ratio"] = _cell(o["advert_ratio"])
    p["related_sales_ratio"] = _cell(o["related_sales_ratio"])
    p["max_shareholder_pct"] = _cell(o["max_shareholder_pct"])
    return p


PROFILES = {g["corp_name"]: profile_from_gold(g) for g in GOLD}

# 손으로 적용한 예상 종합 판정
EXPECT_RESELLER = {
    "(주)휴맥스": "제외 후보", "모바일어플라이언스 주식회사": "제외 후보", "(주)유니트론텍": "포함 후보", "(주)누리플렉스": "사람 확인",   # 0.61.0: 원재료 재고 유무만 다름(K5)
    "오브젠 주식회사": "제외 후보", "(주)엠로": "제외 후보", "(주)한컴": "제외 후보", "(주)밸로프": "제외 후보",
    "명성엘엔텍": "제외 후보", "북두엔지니어링": "제외 후보", "남양씨피엠": "제외 후보", "대주기공": "제외 후보",
    "상신코퍼레이션": "포함 후보", "애보트메디칼코리아": "포함 후보", "케이엘페트로": "사람 확인", "천하자동차": "사람 확인",     # 0.61.0: 재고만(K1)·유형자산만(K2) 다름
    "디티씨": "제외 후보", "세창": "제외 후보", "행담도개발": "제외 후보", "참트레이딩": "사람 확인",
}
EXPECT_CONTRACT_MFG = {
    "(주)휴맥스": "사람 확인", "모바일어플라이언스 주식회사": "사람 확인",       # 0.61.0: 유형자산만 다름(K2)
    "(주)유니트론텍": "제외 후보", "(주)누리플렉스": "제외 후보",
    "오브젠 주식회사": "제외 후보", "(주)엠로": "제외 후보", "(주)한컴": "제외 후보", "(주)밸로프": "제외 후보",
    "명성엘엔텍": "포함 후보", "북두엔지니어링": "포함 후보", "남양씨피엠": "포함 후보", "대주기공": "사람 확인",   # 특수관계 매출 42%(I2)
    "상신코퍼레이션": "제외 후보", "애보트메디칼코리아": "제외 후보", "케이엘페트로": "제외 후보", "천하자동차": "제외 후보",
    "디티씨": "제외 후보", "세창": "제외 후보", "행담도개발": "제외 후보", "참트레이딩": "사람 확인",     # 매출 구성 불명(M0)
}


# ---------- 정답 데이터 자체 ----------
def test_gold_shape():
    assert len(GOLD) == 20
    assert sum(1 for g in GOLD if g["listed"]) == 8
    for g in GOLD:
        assert len(g["rcept_no"]) == 14 and g["rcept_no"].isdigit()
        assert set(g["verification"]["result"]) >= {"revenue", "operating_profit", "total_assets", "inventory", "ppe", "revenue_mix"}
        if g["revenue_mix"]["status"] == STATUS_OK:
            rows = g["revenue_mix"]["rows"]
            total = sum(r["amount"] for r in rows)
            assert abs(sum(g["revenue_mix"]["shares"].values()) - 1) < 1e-3
            share = sum(r["amount"] for r in rows if r["category"] == g["revenue_mix"]["main_category"]) / total
            assert share == pytest.approx(g["revenue_mix"]["main_share"], abs=1e-4)


def test_gold_profiles_valid():
    for p in PROFILES.values():
        assert validate_profile(p) == []


# ---------- 정답 20개 × 분석대상 2개 ----------
@pytest.mark.parametrize("name", list(EXPECT_RESELLER))
def test_reseller(name):
    assert compare_profile(TESTED_RESELLER, PROFILES[name])["overall"] == EXPECT_RESELLER[name]


@pytest.mark.parametrize("name", list(EXPECT_CONTRACT_MFG))
def test_contract_mfg(name):
    assert compare_profile(TESTED_CONTRACT_MFG, PROFILES[name])["overall"] == EXPECT_CONTRACT_MFG[name]


def test_counts():
    a = compare_many(TESTED_RESELLER, list(PROFILES.values()))
    b = compare_many(TESTED_CONTRACT_MFG, list(PROFILES.values()))
    assert a["counts"] == {"포함 후보": 3, "사람 확인": 4, "제외 후보": 13}
    assert b["counts"] == {"포함 후보": 3, "사람 확인": 4, "제외 후보": 13}
    assert "rules로 받은 기준만" in a["note"] and all(a["rules_used"][k] == v for k, v in EX_RULES.items())


def test_item_detail_examples():
    r = compare_profile(TESTED_RESELLER, PROFILES["(주)누리플렉스"])
    assert r["items"]["revenue_mix"]["verdict"] == "가까움"          # 상품 0.712, 차이 0.188
    assert r["items"]["raw_material"]["verdict"] == "다름" and r["reasons"][0].startswith("[K5]")   # 원재료 재고 유무만 다름 → 사람 확인
    r = compare_profile(TESTED_RESELLER, PROFILES["케이엘페트로"])
    assert r["items"]["inventory"]["verdict"] == "다름" and r["overall"] == "사람 확인" and r["reasons"][0].startswith("[K1]")
    r = compare_profile(TESTED_CONTRACT_MFG, PROFILES["대주기공"])
    assert r["items"]["ppe"]["verdict"] == "다름" and r["reasons"][0].startswith("[K2]")
    assert r["overall"] == "사람 확인" and not any(x.startswith("[I2]") for x in r["reasons"])   # 0.72.0 — 검토선 기본값 없음
    assert any(x.startswith("[I2]") for x in compare_profile(TESTED_CONTRACT_MFG, PROFILES["대주기공"], {"related_review": 0.20})["reasons"])   # 사용자가 준 검토선
    r = compare_profile(TESTED_RESELLER, PROFILES["참트레이딩"])
    assert r["items"]["revenue_mix"]["verdict"] == "불명" and r["related_shares"]["매출"] == 0.6011
    assert any(x.startswith("[C2]") and "특수관계 매출" in x for x in r["reasons"])   # 의존 50% 이상(법정 준용) — 사람 확인


# ---------- 경계값 ----------
def _cand(**kw):
    p = empty_profile(company_id="T", company_name="경계")
    p["mix_coverage"] = value(1.0)
    for k in ("product", "merchandise", "service", "sw_license", "platform_fee", "other"):
        p["mix_" + k] = value(0.0)
    p["mix_merchandise"] = value(kw.pop("merch", 0.90))
    p["inv_to_sales"] = value(kw.pop("inv", 0.15))
    p["ppe_ratio"] = value(kw.pop("ppe", 0.05))
    p["rnd_ratio"] = value(kw.pop("rnd", 0.0))
    p["advert_ratio"] = value(kw.pop("adv", 0.02))
    p["raw_material_inv"] = value(kw.pop("raw", False))
    for k, v in kw.items():
        p[k] = v
    return p


@pytest.mark.parametrize("merch,expect", [(0.70, "가까움"), (0.6999, "다름"), (1.10, "가까움"), (1.1001, "다름")])
def test_boundary_mix_20pp(merch, expect):
    assert compare_profile(TESTED_RESELLER, _cand(merch=merch))["items"]["revenue_mix"]["verdict"] == expect


@pytest.mark.parametrize("inv,expect", [(0.075, "가까움"), (0.0749, "다름"), (0.30, "가까움"), (0.3001, "다름"), (0.0, "다름")])
def test_boundary_inventory_half_double(inv, expect):
    assert compare_profile(TESTED_RESELLER, _cand(inv=inv))["items"]["inventory"]["verdict"] == expect


@pytest.mark.parametrize("ppe,expect", [(0.175, "가까움"), (0.70, "가까움"), (0.7001, "다름"), (0.30, "가까움"), (0.1749, "다름")])
def test_boundary_ppe_contract_mfg(ppe, expect):
    c = _cand(ppe=ppe)
    c["mix_product"] = value(0.95); c["raw_material_inv"] = value(True)
    assert compare_profile(TESTED_CONTRACT_MFG, c)["items"]["ppe"]["verdict"] == expect


@pytest.mark.parametrize("ppe,expect", [(0.10, "가까움"), (0.1001, "다름"), (0.0, "가까움")])
def test_boundary_ppe_abs_tol(ppe, expect):
    # 분석대상 5%: 0.5~2배(2.5~10%) 또는 차이 ≤ 5%p(0~10%) → 0~10%
    assert compare_profile(TESTED_RESELLER, _cand(ppe=ppe))["items"]["ppe"]["verdict"] == expect


@pytest.mark.parametrize("rnd,expect", [(0.01, "가까움"), (0.0101, "다름")])
def test_boundary_rnd_zero_tested(rnd, expect):
    assert compare_profile(TESTED_RESELLER, _cand(rnd=rnd))["items"]["rnd"]["verdict"] == expect


@pytest.mark.parametrize("cov,expect", [(0.8, "가까움"), (1.2, "가까움"), (0.7999, "불명"), (1.2001, "불명")])
def test_boundary_coverage(cov, expect):
    assert compare_profile(TESTED_RESELLER, _cand(mix_coverage=value(cov)))["items"]["revenue_mix"]["verdict"] == expect


def test_rules_adjustable():
    c = _cand(merch=0.75)
    assert compare_profile(TESTED_RESELLER, c)["items"]["revenue_mix"]["verdict"] == "가까움"
    r = compare_profile(TESTED_RESELLER, c, rules={"mix_max_diff": 0.10})
    assert r["items"]["revenue_mix"]["verdict"] == "다름" and r["overall"] == "제외 후보" and r["rules_used"]["mix_max_diff"] == 0.10
    assert EX_RULES["mix_max_diff"] == 0.20  # 넘긴 값은 바뀌지 않음


# ---------- 불명 처리 ----------
def test_unknown_vs_none_status():
    # 불명-없음(계정 없음)은 0으로 비교, 불명-못찾음은 불명
    c = _cand(adv=None)
    c["advert_ratio"] = value(0.0, STATUS_NONE, account="광고선전비", note="판관비 내역에 계정 없음")
    assert compare_profile(TESTED_RESELLER, c)["items"]["advert"]["verdict"] == "가까움"   # 0 vs 2%(차이 2%p ≤ 3%p)
    c["advert_ratio"] = value(0.0, STATUS_NONE, account="광고선전비", note="판관비 내역에 계정 없음")
    assert compare_profile(TESTED_RESELLER | {"advert_ratio": 0.04}, c)["items"]["advert"]["verdict"] == "다름"   # 0 vs 4%
    c["advert_ratio"] = value(None, STATUS_UNKNOWN)
    assert compare_profile(TESTED_RESELLER, c)["items"]["advert"]["verdict"] == "불명"
    c = _cand()
    c["inv_to_sales"] = value(0.0, STATUS_NONE, note="재무상태표에 재고 계정 없음")
    assert compare_profile(TESTED_RESELLER, c)["items"]["inventory"]["verdict"] == "다름"


def test_core_unknown_needs_review():
    c = _cand(); c["mix_merchandise"] = value()              # 핵심(매출 구성) 불명
    r = compare_profile(TESTED_RESELLER, c)
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[M0]")
    c = _cand(); c["inv_to_sales"] = value()                 # 재고는 핵심 아님 — 불명 1개면 포함
    assert compare_profile(TESTED_RESELLER, c)["overall"] == "포함 후보"


def test_many_unknown_needs_review():
    c = _cand(); c["rnd_ratio"] = value(); c["advert_ratio"] = value(); c["raw_material_inv"] = value()
    assert compare_profile(TESTED_RESELLER, c)["overall"] == "사람 확인"
    c = _cand(); c["rnd_ratio"] = value(); c["advert_ratio"] = value()
    assert compare_profile(TESTED_RESELLER, c)["overall"] == "포함 후보"


def test_core_diff_beats_unknown():
    c = _cand(merch=0.3); c["inv_to_sales"] = value()
    assert compare_profile(TESTED_RESELLER, c)["overall"] == "제외 후보"
    c = _cand(ppe=0.5, inv=0.6)                              # 재고·유형자산 둘 다 다름 → 제외 후보(K3)
    r = compare_profile(TESTED_RESELLER, c)
    assert r["overall"] == "제외 후보" and r["reasons"][0].startswith("[K3]")
    r = compare_profile(TESTED_RESELLER, _cand(ppe=0.5))       # 하나만 → 사람 확인(K2)
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[K2]")


def test_independence():
    c = _cand(max_shareholder_pct=value(50.0))
    r = compare_profile(TESTED_RESELLER, c)
    assert r["overall"] == "제외 후보" and "법정 준용" in r["independence"][0]
    assert compare_profile(TESTED_RESELLER, _cand(max_shareholder_pct=value(49.99)))["overall"] == "포함 후보"
    # 0.72.0 — 특수관계 비중 검토선 기본값 없음: 법정 준용 의존 50%([C2])만 늘 적용, 그 아래는 숫자만
    assert compare_profile(TESTED_RESELLER, _cand(related_sales_ratio=value(0.20)))["overall"] == "포함 후보"
    assert compare_profile(TESTED_RESELLER, _cand(related_sales_ratio=value(0.4999)))["overall"] == "포함 후보"
    r = compare_profile(TESTED_RESELLER, _cand(related_sales_ratio=value(0.50)))
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[C2]") and r["related_shares"] == {"매출": 0.5, "매입": None}
    r = compare_profile(TESTED_RESELLER, _cand(related_purchase_ratio=value(0.53)))      # 매입 의존도 — 사람 확인(제외 아님)
    assert r["overall"] == "사람 확인" and r["reasons"][0].startswith("[C2]") and "법정 준용" in r["reasons"][0]
    r = compare_profile(TESTED_RESELLER, _cand(related_sales_ratio=value(0.20)), {"related_review": 0.20})   # 사용자가 준 검토선
    assert r["overall"] == "사람 확인" and "입력한 검토선" in r["reasons"][0] and "법정 특수관계 판정 아님" in r["reasons"][0]
    assert compare_profile(TESTED_RESELLER, _cand(related_sales_ratio=value(0.22)), rules={"related_sales_review": 0.25})["overall"] == "포함 후보"   # 예전 이름


def test_schema_guards():
    with pytest.raises(ValueError):
        value(None, STATUS_OK)
    with pytest.raises(ValueError):
        value(1.0, "모름")
    p = empty_profile(company_id="X")
    p["unknown_col"] = 1
    p["ppe_ratio"] = {"value": 1, "status": "?"}
    errs = validate_profile(p)
    assert any("모르는 열" in e for e in errs) and any("ppe_ratio" in e for e in errs)
