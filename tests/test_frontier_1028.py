"""10/28 프론티어 모델 점검에서 나온 수정의 회귀 테스트. 작성 Claude 2026-10-28."""
import asyncio, json, os, tempfile
import openpyxl
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_residential_rental_loss_offsets_other_income():
    r = c("income_loss_offset", {"year": 2026, "incomes": {"부동산임대": -5000000, "주거용임대": -20000000, "근로": 30000000,
                                                          "기타": 5000000, "이자": 15000000, "배당": 10000000},
                                 "business": {"book_income": 10000000, "adjustments": []}})
    assert r["결과"]["종합소득금액"] == 50000000
    assert r["결과"]["이월결손금(다음 연도로)"]["부동산임대"] == 5000000


def test_unwithheld_financial_income_taxed_below_threshold():
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "외국법인배당", "amount": 3000000, "withheld": False},
        {"kind": "비영업대금이익", "amount": 2000000, "withheld": False},
        {"kind": "상장법인현금배당", "amount": 1000000}]})
    assert r["결과"]["합산액"] == 5000000
    assert r["결과"]["이자소득금액"] == 2000000 and r["결과"]["배당소득금액"] == 3000000


def test_withheld_default_keeps_separate_taxation():
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "예금이자", "amount": 5000000}]})
    assert r["결과"]["합산액"] == 0


def test_form_keeps_traditional_market_ratio_with_zero_spending():
    with tempfile.TemporaryDirectory() as d:
        r = c("export_workbook", {"title": "t", "output_dir": d, "calls": [{"label": "x", "tool": "entertainment_adjustment",
              "args": {"year": 2025, "sme": True, "revenue": {"매출액": 15000000000}, "ledger": [{"항목": "카드", "금액": 93000000}]}}]})
        ws = openpyxl.load_workbook(r["결과"]["파일"])["별지23(갑) 기업업무추진비"]
        assert "전통시장등비율" in str(ws["D25"].value)


def test_deemed_input_preliminary_return_skips_limit():
    base = {"period": "2026-1", "industry": "제조", "individual": False, "sme": False, "purchase": 100000000, "base": 40000000}
    final = c("vat_deemed_input_credit", base)
    pre = c("vat_deemed_input_credit", {**base, "filing": "예정"})
    assert pre["결과"]["의제매입세액"] > final["결과"]["의제매입세액"] if "결과" in pre else pre["의제매입세액"] > final["의제매입세액"]
    assert "Infinity" not in json.dumps(pre)


def test_simplified_vat_wording_consistent_above_threshold():
    r = c("simplified_vat_return", {"year": 2026, "business_type": "음식점업", "prior_year_supplies": 75000000,
          "ledger": {"공급": [{"항목": "신용카드매출전표 발행분", "금액": 50000000}],
                     "매입": [{"항목": "조미료(세금계산서)", "금액": 22000000}]}})
    txt = json.dumps(r, ensure_ascii=False)
    assert "< 영수증발급기준" not in txt


def _top(q, n=3):
    return [x["도구"] for x in c("find_tool", {"query": q, "n": n})["결과"]["후보"]]


def test_find_tool_surfaces_tools_models_missed():
    assert _top("해산한 법인 청산소득")[0] == "liquidation_income"
    assert _top("보험차익으로 대체 취득한 기계 일시상각충당금")[0] == "asset_grant_reserve"
    assert _top("당기순이익에서 차가감소득금액")[0] == "income_adjustment_total"
    assert "capital_gains_income" in _top("아파트 팔았을 때 양도세")
    assert _top("업무무관 가지급금 지급이자")[0] == "nonbusiness_interest_disallowance"
    assert "deemed_interest" in _top("unfair transaction deemed interest")


def test_capital_gains_income_now_returns_tax():
    r = c("capital_gains_income", {"asset_type": "주택", "acquisition_date": "2015-03-10", "transfer_date": "2025-06-20",
          "transfer_price": 2000000000, "acquisition_price": 800000000, "transfer_expenses": 20000000,
          "one_house": True, "exempt_met": True, "residence_years": 10, "apply_basic_deduction": True})
    assert r["결과"]["양도소득_과세표준"] == 91900000 and r["결과"]["산출세액"] == 16725000 and r["결과"]["지방소득세"] == 1672500


def test_capital_gains_short_term_vs_nonbusiness_land_takes_larger():
    r = c("capital_gains_income", {"asset_type": "토지", "acquisition_date": "2024-03-01", "transfer_date": "2025-09-01",
          "transfer_price": 500000000, "acquisition_price": 300000000, "one_house": False, "exempt_met": False,
          "apply_basic_deduction": True, "non_business_land": True})
    assert r["결과"]["산출세액"] == 79000000   # 40% 79,000,000 > 기본세율+10%p 74,860,000


def test_capital_gains_tax_housing_short_term_by_transfer_date():
    a = {"base": 100000000, "asset_type": "주택", "acquisition_date": "2020-01-10"}
    assert c("capital_gains_tax", {**a, "transfer_date": "2021-03-01"})["결과"]["산출세액"] == 20100000
    assert c("capital_gains_tax", {**a, "transfer_date": "2021-07-01"})["결과"]["산출세액"] == 60000000
    assert c("capital_gains_tax", {**a, "transfer_date": "2021-07-01", "registered": False})["결과"]["산출세액"] == 70000000


def test_other_income_easement_and_artwork_kinds():
    r = c("other_income_aggregate", {"year": 2017, "items": [
        {"kind": "위약금·배상금", "amount": 1500000}, {"kind": "산업재산권대여", "amount": 1000000},
        {"kind": "공익사업지상권대여", "amount": 2000000}, {"kind": "서화골동품양도", "amount": 10000000, "museum": True},
        {"kind": "일시적인적용역", "amount": 250000}, {"kind": "복권당첨금", "amount": 3000000}, {"kind": "배임수재", "amount": 5000000}]})
    assert r["결과"]["기납부_원천징수세액"] + r["결과"]["분리과세_원천징수세액"] == 1020000
    assert r["결과"]["비과세_합계"] == 10000000


def test_artwork_expense_ratio_tiers():
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "서화골동품양도", "amount": 200000000, "held_years": 3}]})
    assert r["결과"]["분리과세_기타소득금액"] == 200000000 - (90000000 + 80000000)
    r = c("other_income_aggregate", {"year": 2025, "items": [{"kind": "서화골동품양도", "amount": 200000000, "held_years": 12}]})
    assert r["결과"]["분리과세_기타소득금액"] == 20000000


def test_artwork_rules_follow_amendment_dates():
    old = c("other_income_aggregate", {"year": 2019, "items": [{"kind": "서화골동품양도", "amount": 200000000}]})
    assert old["결과"]["분리과세_기타소득금액"] == 40000000            # 2019: 일률 80%
    assert "입력 확인 필요" in json.dumps(c("other_income_aggregate", {"year": 2020, "items": [{"kind": "서화골동품양도", "amount": 200000000}]}), ensure_ascii=False)
    a = c("other_income_aggregate", {"year": 2020, "items": [{"kind": "서화골동품양도", "amount": 200000000, "transfer_date": "2020-02-10"}]})
    b = c("other_income_aggregate", {"year": 2020, "items": [{"kind": "서화골동품양도", "amount": 200000000, "transfer_date": "2020-02-11"}]})
    assert a["결과"]["분리과세_기타소득금액"] == 40000000 and b["결과"]["분리과세_기타소득금액"] == 30000000
    biz = c("other_income_aggregate", {"year": 2022, "items": [{"kind": "서화골동품양도", "amount": 200000000, "business_setup": True}]})
    assert biz["결과"]["분리과세_기타소득금액"] == 0


def test_housing_deemed_rent_three_houses_book():
    r = c("housing_deemed_rent_income", {"year": 2025, "financial_income": 500000, "houses": [
        {"기준시가": 500000000, "면적": 84, "보증금": 200000000}, {"기준시가": 400000000, "면적": 84, "보증금": 200000000},
        {"기준시가": 300000000, "면적": 59, "보증금": 100000000}]})
    assert r["결과"]["총수입금액_산입액"] == 3220000


def test_housing_deemed_rent_two_luxury_houses_from_2026_only():
    hs = [{"기준시가": 2000000000, "면적": 120, "보증금": 700000000}, {"기준시가": 1400000000, "면적": 100, "보증금": 600000000},
          {"기준시가": 150000000, "면적": 35, "보증금": 50000000}]
    r = c("housing_deemed_rent_income", {"year": 2026, "estimated": True, "rate": 0.03, "houses": hs})
    assert r["결과"]["총수입금액_산입액"] == 18000000
    r = c("housing_deemed_rent_income", {"year": 2025, "estimated": True, "rate": 0.03, "houses": hs})
    assert r["결과"]["과세"] is False      # 2025년까지는 3주택 요건만


def test_small_house_threshold_by_year():
    hs = [{"기준시가": 250000000, "면적": 55, "보증금": 200000000}] * 2 + [{"기준시가": 500000000, "면적": 84, "보증금": 200000000}]
    assert c("housing_deemed_rent_income", {"year": 2018, "houses": hs})["결과"]["과세"] is False   # 60㎡·3억 이하 2채 제외 → 1주택
    assert c("housing_deemed_rent_income", {"year": 2019, "houses": hs})["결과"]["과세"] is True    # 40㎡·2억 기준 → 제외 안 됨


def test_retirement_tax_uses_year_tables():
    assert c("retirement_income_tax", {"income": 100000000, "years_of_service": 10, "retire_year": 2025})["결과"]["퇴직소득세"] == 3875000
    assert c("retirement_income_tax", {"income": 100000000, "years_of_service": 10, "retire_year": 2022})["결과"]["퇴직소득세"] == 4982000
    assert c("retirement_income_tax", {"income": 300000000, "years_of_service": 25, "retire_year": 2022})["결과"]["퇴직소득세"] == 17999000
    assert "입력 확인 필요" in json.dumps(c("retirement_income_tax", {"income": 1, "years_of_service": 1, "retire_year": 2018}), ensure_ascii=False)
