"""항목형(사실관계 단위) 입력 정답 테스트 — 모델은 문항 표 라벨을 그대로 옮기고, 합산·제외·차감 판단은 도구가 한다. 작성 Claude 2026-10-21.
근거: 10/21 오답 분류에서 값 오추출이 가장 많은 세 도구. 기존 입력 방식은 그대로 동작해야 한다(하위 호환)."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def _schema(tool):
    t = next(x for x in asyncio.run(mcp.list_tools()) if x.name == tool)
    return t.input_schema["properties"]


# ── 1. capital_gains_income: 취득 부대비용·거주기간을 사실 단위로 ─────────────────────
CG_BASE = {"asset_type": "주택", "acquisition_date": "2014-05-05", "transfer_date": "2021-04-04", "transfer_price": 1000000000,
           "registered": True, "one_house": True, "exempt_met": True, "apply_basic_deduction": False}


def test_capital_gains_fact_fields_sum_into_acquisition_cost():
    r = c("capital_gains_income", {**CG_BASE, "acquisition_price": 500000000, "acquisition_tax": 5000000, "acquisition_brokerage": 2000000,
                                   "holding_tax_paid": 1000000, "capital_expenditure": 0, "transfer_expenses": 3000000,
                                   "residence_start": "2016-06-06", "residence_end": "2021-04-04"})
    res = r["결과"]
    assert res["양도차익"] == 490000000 and res["거주기간_년"] == 4 and res["양도소득금액"] == 29400000
    txt = json.dumps(r, ensure_ascii=False)
    assert "재산세" in txt and "필요경비" in txt                         # 보유 중 재산세는 필요경비 아님을 결과에 명시


def test_capital_gains_legacy_inputs_unchanged():
    r = c("capital_gains_income", {**CG_BASE, "acquisition_price": 507000000, "capital_expenditure": 0, "transfer_expenses": 3000000, "residence_years": 4})
    assert r["결과"]["양도소득금액"] == 29400000


def test_capital_gains_schema_names_fact_fields():
    p = _schema("capital_gains_income")
    for k in ("acquisition_tax", "acquisition_brokerage", "holding_tax_paid", "residence_start", "residence_end"):
        assert k in p, k
    assert "취득세" in p["acquisition_tax"]["description"]


# ── 2. vat_deemed_input_credit: 품목별 items로 넣으면 도구가 공제대상 매입가액을 계산 ─────
ITEMS = [
    {"name": "돼지고기", "purchase_price": 26000000, "usage": {"제조": 60, "재판매": 30, "재고": 10}},
    {"name": "밀가루", "purchase_price": 22100000, "imported": True, "customs_value": 20800000, "customs_duty": 1300000, "usage": {"제조": 100}},
    {"name": "소금", "purchase_price": 10920000, "freight_included": 520000, "usage": {"제조": 100}},
    {"name": "치즈", "purchase_price": 5200000, "taxable_goods": True, "usage": {"제조": 100}},
    {"name": "김치", "purchase_price": 3900000, "usage": {"종업원제공": 100}},
]


def test_deemed_input_items_compute_eligible_purchase():
    r = c("vat_deemed_input_credit", {"period": "2021-1", "industry": "제조", "individual": False, "sme": True, "items": ITEMS})
    res = r["결과"]
    assert res["공제대상_매입가액"] == 49400000 and res["의제매입세액"] == 1900000
    per = {x["name"]: x for x in r["계산"]["품목별"]}
    assert per["돼지고기"]["공제대상"] == 18200000           # 재판매 30% 제외, 재고 10% 포함
    assert per["밀가루"]["공제대상"] == 20800000             # 수입분은 관세의 과세가격
    assert per["소금"]["공제대상"] == 10400000               # 운임 제외
    assert per["치즈"]["공제대상"] == 0 and per["김치"]["공제대상"] == 0   # 과세 물품·종업원 제공 제외
    assert "재판매" in per["돼지고기"]["판단"]


def test_deemed_input_legacy_purchase_unchanged():
    r = c("vat_deemed_input_credit", {"period": "2021-1", "industry": "제조", "individual": False, "sme": True, "purchase": 49400000})
    assert r["결과"]["의제매입세액"] == 1900000


# ── 3. special_tax_credit: 회사 지급 학자금을 사실로 넣으면 도구가 차감 여부를 판단 ───────
STC = {"year": 2021, "earner_type": "근로", "total_salary": 60000000,
       "persons": [{"name": "본인", "relation": "본인", "age": 50, "income_ok": True},
                   {"name": "아들", "relation": "직계비속", "age": 22, "income_ok": True},
                   {"name": "딸", "relation": "직계비속", "age": 16, "income_ok": True},
                   {"name": "모친", "relation": "직계존속", "age": 75, "income_ok": True}]}


def test_education_employer_subsidy_taxed_not_subtracted():
    exp = [{"kind": "교육비_대학원", "amount": 4000000, "person": "본인"},
           {"kind": "교육비_대학", "amount": 10000000, "person": "아들", "employer_subsidy": 2000000},
           {"kind": "교육비_초중고", "amount": 100000, "person": "딸"}, {"kind": "교복", "amount": 300000, "person": "딸"},
           {"kind": "교육비_대학", "amount": 500000, "person": "모친"}]
    r = c("special_tax_credit", {**STC, "expenses": exp})
    assert r["결과"]["교육비_세액공제"] == 2010000
    txt = json.dumps(r.get("판단", []), ensure_ascii=False)
    assert "학자금" in txt and "차감하지 않" in txt                 # 과세 근로소득으로 받은 보조는 차감 안 함을 결과에 명시


def test_education_tax_exempt_scholarship_is_subtracted():
    exp = [{"kind": "교육비_대학", "amount": 10000000, "person": "아들", "tax_exempt_subsidy": 2000000}]
    r = c("special_tax_credit", {**STC, "expenses": exp})
    assert r["결과"]["교육비_세액공제"] == 1200000               # (10M − 2M) × 15%
