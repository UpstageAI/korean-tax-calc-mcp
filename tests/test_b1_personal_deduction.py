"""종합소득 인적공제(기본공제·추가공제) — 소득세법 제50조·제51조·제53조."""
import pytest
from korean_tax_calc_mcp import server


def _fn():
    t = server.personal_deduction
    return getattr(t, "fn", t)


def call(**kw):
    return _fn()(**kw)


def total(r):
    return r["결과"]["인적공제"]


def test_basic_family_with_elderly():
    # 2023: 본인(남), 배우자(소득 0), 부친 1950년생(73세, 경로우대), 아들 2005년생(18), 딸 2002년생(21 → 제외), 형 1960년생(63, 동거)
    r = call(year=2023, taxpayer={"sex": "남", "birth_year": 1980, "has_spouse": True, "comprehensive_income": 50_000_000},
             persons=[{"name": "배우자", "relation": "배우자", "birth_year": 1985},
                      {"name": "부친", "relation": "직계존속", "birth_year": 1950},
                      {"name": "아들", "relation": "직계비속", "birth_year": 2005},
                      {"name": "딸", "relation": "직계비속", "birth_year": 2002},
                      {"name": "형", "relation": "형제자매", "birth_year": 1960}])
    assert r["결과"]["기본공제"] == 7_500_000          # 본인·배우자·부친·아들·형
    assert r["결과"]["추가공제"] == 1_000_000          # 부친 경로우대
    assert total(r) == 8_500_000
    by = {p["name"]: p for p in r["사람별"]}
    assert by["딸"]["기본공제"] is False and "20세" in by["딸"]["사유"]


def test_single_parent_beats_woman_deduction():
    r = call(year=2023, taxpayer={"sex": "여", "birth_year": 1985, "has_spouse": False, "household_head": True, "comprehensive_income": 25_000_000},
             persons=[{"name": "아들", "relation": "직계비속", "birth_year": 2015}])
    assert total(r) == 4_000_000                         # 기본 2명 300만 + 한부모 100만(부녀자 50만 대신)
    names = [a["항목"] for a in r["사람별"][0]["추가공제"]] if r["사람별"][0]["name"] == "본인" else []
    assert "부녀자" not in names


def test_woman_with_spouse_spouse_over_income():
    r = call(year=2023, taxpayer={"sex": "여", "birth_year": 1982, "has_spouse": True, "comprehensive_income": 28_000_000},
             persons=[{"name": "배우자", "relation": "배우자", "birth_year": 1980, "income_items": [{"kind": "사업소득금액", "amount": 1_200_000}]}])
    assert r["결과"]["기본공제"] == 1_500_000
    assert r["결과"]["추가공제"] == 500_000              # 부녀자(배우자 있는 여성, 종합소득금액 3천만 이하)
    assert total(r) == 2_000_000


def test_woman_deduction_income_limit():
    r = call(year=2023, taxpayer={"sex": "여", "birth_year": 1982, "has_spouse": True, "comprehensive_income": 30_000_001},
             persons=[])
    assert total(r) == 1_500_000


def test_wage_only_dependents_and_disabled_sibling():
    r = call(year=2023, taxpayer={"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 40_000_000},
             persons=[{"name": "모친", "relation": "직계존속", "birth_year": 1958, "income_items": [{"kind": "근로_총급여", "amount": 4_800_000}]},
                      {"name": "부친", "relation": "직계존속", "birth_year": 1956, "income_items": [{"kind": "근로_총급여", "amount": 5_200_000}]},
                      {"name": "동생", "relation": "형제자매", "birth_year": 1990, "disabled": True}])
    by = {p["name"]: p for p in r["사람별"]}
    assert by["모친"]["기본공제"] is True                 # 근로소득만 총급여 500만 이하
    assert by["부친"]["기본공제"] is False
    assert by["동생"]["기본공제"] is True                 # 장애인은 나이 제한 없음
    assert r["결과"]["기본공제"] == 4_500_000
    assert r["결과"]["추가공제"] == 2_000_000             # 장애인
    assert total(r) == 6_500_000


def test_cap_at_comprehensive_income():
    r = call(year=2023, taxpayer={"sex": "남", "birth_year": 1980, "has_spouse": True, "comprehensive_income": 3_000_000},
             persons=[{"name": "배우자", "relation": "배우자", "birth_year": 1981},
                      {"name": "아들", "relation": "직계비속", "birth_year": 2010},
                      {"name": "딸", "relation": "직계비속", "birth_year": 2012}])
    assert r["결과"]["공제 전 합계"] == 6_000_000
    assert total(r) == 3_000_000                         # 제51조④


def test_age_boundary_20_and_60():
    r = call(year=2021, taxpayer={"sex": "남", "birth_year": 1970, "has_spouse": True, "comprehensive_income": 50_000_000},
             persons=[{"name": "아들", "relation": "직계비속", "birth_year": 2001},      # 2021년에 20세 → 대상
                      {"name": "모친", "relation": "직계존속", "birth_year": 1961},      # 60세 → 대상
                      {"name": "부친", "relation": "직계존속", "birth_year": 1962}])     # 59세 → 제외
    by = {p["name"]: p for p in r["사람별"]}
    assert by["아들"]["기본공제"] and by["모친"]["기본공제"] and not by["부친"]["기본공제"]


def test_cohabitation_rules():
    r = call(year=2023, taxpayer={"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 50_000_000},
             persons=[{"name": "모친", "relation": "직계존속", "birth_year": 1950, "cohabiting": False},   # 직계존속 별거 → 인정(제53조③)
                      {"name": "누나", "relation": "형제자매", "birth_year": 1960, "cohabiting": False}])  # 형제자매 별거 → 제외
    by = {p["name"]: p for p in r["사람별"]}
    assert by["모친"]["기본공제"] is True and by["누나"]["기본공제"] is False


def test_basis_and_errors():
    r = call(year=2023, taxpayer={"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 10_000_000}, persons=[])
    assert "제50조" in str(r["근거"]) and "제51조" in str(r["근거"])
    bad = call(year=2023, taxpayer={"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 10_000_000},
               persons=[{"name": "친구", "relation": "친구", "birth_year": 1980}])
    assert "error" in bad
