"""도구 공백 — 인적공제·연금소득·결손금 공제·재해손실세액공제 이식과 보강의 정답 테스트. 작성 Claude 2026-10-24.
값은 문항을 손으로 푼 결과(docs/SPEC_gold_gaps3.md)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_personal_deduction_divorced_with_pension_not_taxed_and_synonyms():
    r = c("personal_deduction", {"year": 2021,
          "taxpayer": {"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 40000000},
          "persons": [{"name": "부친", "relation": "부친", "birth_year": 1938,
                       "income_items": [{"kind": "공적연금_과세제외", "amount": 30000000}]},
                      {"name": "모친", "relation": "모친", "birth_year": 1943, "disabled": True, "income_items": []},
                      {"name": "아들", "relation": "아들", "birth_year": 2011, "income_items": []}]})
    assert r["결과"]["인적공제"] == 11000000
    assert r["결과"]["기본공제"] == 6000000 and r["결과"]["추가공제"] == 5000000
    부친 = [p for p in r["결과"]["사람별"] if p["name"] == "부친"][0]
    assert 부친["기본공제"] is True


def test_personal_deduction_unknown_relation_rejected():
    r = c("personal_deduction", {"year": 2021, "taxpayer": {"sex": "남", "birth_year": 1980, "has_spouse": False, "comprehensive_income": 1},
                                 "persons": [{"name": "이웃", "relation": "이웃", "birth_year": 1980, "income_items": []}]})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


def test_pension_income_public_ratio_from_detail():
    r = c("pension_income", {"year": 2022, "public_pension_detail": {"수령액": 45000000, "환산소득_2002이후": 380000000, "환산소득_전체": 480000000}})
    assert r["결과"]["총연금액"] == 35625000
    assert r["결과"]["연금소득금액"] == 27162500


def test_pension_income_detail_minus_excluded_contribution_and_conflict():
    r = c("pension_income", {"year": 2022, "public_pension_detail": {"수령액": 45000000, "환산소득_2002이후": 380000000, "환산소득_전체": 480000000, "과세제외기여금": 5625000}})
    assert r["결과"]["총연금액"] == 30000000
    r = c("pension_income", {"year": 2022, "public_pension": 1, "public_pension_detail": {"수령액": 45000000, "환산소득_2002이후": 1, "환산소득_전체": 2}})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


def test_loss_offset_owner_salary_added_back():
    r = c("income_loss_offset", {"year": 2021, "incomes": {"근로": 40000000, "기타": 30000000},
                                 "business": {"book_income": -90000000, "adjustments": [{"kind": "사업주_본인_급여", "amount": 30000000}]}})
    assert r["결과"]["종합소득금액"] == 10000000


def test_loss_offset_history_derives_carryforward():
    r = c("income_loss_offset", {"year": 2023,
          "incomes": {"이자": 25000000, "배당": 16500000, "부동산임대": 15000000, "근로": 5000000, "연금": 6000000, "기타": 0},
          "business": {"book_income": -35000000, "adjustments": []}, "financial_flat_rate": 20000000,
          "history": [{"year": 2022, "incomes": {"이자": 5000000, "배당": 3000000, "부동산임대": -10000000, "근로": 15000000, "연금": 6000000, "기타": 4000000},
                       "business": {"book_income": -30000000, "adjustments": []}, "financial_flat_rate": 8000000}]})
    assert r["결과"]["종합소득금액"] == 27500000
    assert r["결과"]["이월결손금(다음 연도로)"]["부동산임대"] == 10000000
    assert r["결과"]["이월결손금(다음 연도로)"]["사업"] == 0


def test_loss_offset_history_and_carryforwards_conflict():
    r = c("income_loss_offset", {"year": 2023, "incomes": {"근로": 1}, "business": {"book_income": 0, "adjustments": []},
                                 "carryforwards": [{"year": 2022, "kind": "사업", "amount": 1}],
                                 "history": [{"year": 2022, "incomes": {"근로": 1}, "business": {"book_income": -2, "adjustments": []}}]})
    assert "입력 확인 필요" in json.dumps(r, ensure_ascii=False)


def test_disaster_loss_credit_includes_liable_third_party_assets():
    r = c("disaster_loss_credit", {"year": 2023,
          "assets": [{"구분": "사업용", "장부가액": 500000000, "상실액": 140000000},
                     {"구분": "타인소유_변상책임있음", "장부가액": 100000000, "상실액": 100000000}],
          "current_tax": 300000000, "other_credits": 30000000, "penalty": 6000000})
    assert r["결과"]["자산상실비율"] == 0.4 and r["결과"]["재해손실세액공제"] == 110400000


# 재해손실세액공제 공제대상 법인세 항목형 입력(영 제95조③, 법 제58조①) — 10/24 보강
def test_disaster_credit_items_other_law_credit_and_penalty_kinds():
    r = c("disaster_loss_credit", {"year": 2023,
          "assets": [{"구분": "사업용", "장부가액": 500000000, "상실액": 140000000},
                     {"구분": "타인소유_변상책임있음", "장부가액": 100000000, "상실액": 100000000}],
          "current_tax": 300000000,
          "credit_items": [{"종류": "조세특례제한법", "금액": 30000000}],
          "penalty_items": [{"근거": "국세기본법 제47조의5", "금액": 6000000}]})
    assert r["결과"]["공제대상 법인세"] == 276000000 and r["결과"]["재해손실세액공제"] == 110400000


def test_disaster_credit_foreign_tax_credit_not_deducted_book_penalty_included():
    r = c("disaster_loss_credit", {"year": 2025,
          "assets": [{"구분": "사업용", "장부가액": 370000000, "상실액": 190000000},
                     {"구분": "토지", "장부가액": 300000000, "상실액": 0},
                     {"구분": "타인소유_변상책임있음", "장부가액": 30000000, "상실액": 30000000}],
          "current_tax": 20000000, "unpaid_prior_tax": 11000000,
          "credit_items": [{"종류": "법인세법", "금액": 1000000}, {"종류": "조세특례제한법", "금액": 2000000}]})
    assert r["결과"]["자산상실비율"] == 0.55
    assert r["결과"]["공제대상 법인세"] == 29000000 and r["결과"]["재해손실세액공제"] == 15950000


def test_disaster_credit_excluded_penalty_and_input_conflict():
    base = {"year": 2025, "assets": [{"구분": "사업용", "장부가액": 100000000, "상실액": 50000000}], "current_tax": 10000000}
    r = c("disaster_loss_credit", {**base, "penalty_items": [{"근거": "기타", "금액": 1000000}, {"근거": "법인세법 제75조의3", "금액": 500000}]})
    assert r["결과"]["공제대상 법인세"] == 10500000
    assert "입력 확인 필요" in json.dumps(c("disaster_loss_credit", {**base, "other_credits": 1, "credit_items": [{"종류": "조세특례제한법", "금액": 1}]}), ensure_ascii=False)
