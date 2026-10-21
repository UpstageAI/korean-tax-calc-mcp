"""항목형 입력 2차 — 모델이 실제로 보낸 형태를 받아들이고, 틀린 형태면 한국어로 예시와 함께 알린다. 작성 Claude 2026-10-21.
근거: 실측에서 모델이 items.usage를 {"구분": "재판매", "비율": 30} 꼴로 보냈고 도구는 "invalid literal for int()"라는 파이썬 오류를 그대로 돌려줬다."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


BASE = {"period": "2021-1", "industry": "제조", "individual": False, "sme": True}


def test_usage_accepts_list_of_objects():
    items = [{"name": "돼지고기", "purchase_price": 26000000,
              "usage": [{"구분": "제조", "비율": 60}, {"구분": "재판매", "비율": 30}, {"구분": "재고", "비율": 10}]},
             {"name": "밀가루", "purchase_price": 22100000, "imported": True, "customs_value": 20800000, "customs_duty": 1300000,
              "usage": [{"구분": "제조", "비율": 100}]}]
    r = c("vat_deemed_input_credit", {**BASE, "items": items})
    assert r["결과"]["공제대상_매입가액"] == 18200000 + 20800000


def test_same_item_split_across_rows_is_merged():
    """모델이 같은 품목을 용도별로 여러 행에 나눠 보내도(같은 purchase_price) 한 품목으로 합쳐 계산."""
    items = [{"name": "돼지고기", "purchase_price": 26000000, "usage": {"제조": 60}},
             {"name": "돼지고기", "purchase_price": 26000000, "usage": {"재판매": 30}},
             {"name": "돼지고기", "purchase_price": 26000000, "usage": {"재고": 10}}]
    r = c("vat_deemed_input_credit", {**BASE, "items": items})
    assert r["결과"]["공제대상_매입가액"] == 18200000


def test_bad_usage_gets_korean_message_with_example():
    items = [{"name": "돼지고기", "purchase_price": 26000000, "usage": {"구분": "재판매"}}]
    r = c("vat_deemed_input_credit", {**BASE, "items": items})
    assert "error" in r
    txt = json.dumps(r, ensure_ascii=False)
    assert "invalid literal" not in txt and "usage" in txt and "제조" in txt and "비율" in txt   # 파이썬 오류 노출 금지, 형식 예시 포함


def test_usage_ratio_not_100_is_reported():
    items = [{"name": "돼지고기", "purchase_price": 26000000, "usage": {"제조": 60, "재판매": 30}}]
    r = c("vat_deemed_input_credit", {**BASE, "items": items})
    assert "error" in r and "100" in json.dumps(r, ensure_ascii=False)


def test_education_result_always_states_subsidy_rule():
    """학자금 보조 필드를 안 넣어도, 교육비_대학 항목이 있으면 결과 '판단'에 차감 규칙을 적어 모델이 스스로 차감하지 않게 한다."""
    a = {"year": 2021, "earner_type": "근로", "total_salary": 60000000,
         "persons": [{"name": "본인", "relation": "본인", "age": 50, "income_ok": True}, {"name": "아들", "relation": "직계비속", "age": 22, "income_ok": True}],
         "expenses": [{"kind": "교육비_대학", "amount": 10000000, "person": "아들"}]}
    r = c("special_tax_credit", a)
    txt = json.dumps(r.get("판단", []), ensure_ascii=False)
    assert "학자금" in txt and "차감" in txt and "비과세" in txt


def test_converted_acquisition_breakdown_excludes_tax_and_brokerage():
    """환산취득가액 경로에서는 취득가액_구성이 환산취득가액+개산공제로 표시되고 취득세·중개수수료는 합산되지 않는다 (리뷰 반영)."""
    r = c("capital_gains_income", {"asset_type": "주택", "acquisition_date": "1987-07-07", "transfer_date": "2022-08-08", "transfer_price": 500000000,
                                   "acquisition_price": 0, "acquisition_standard_price": 100000000, "transfer_standard_price": 400000000,
                                   "acquisition_tax": 5000000, "acquisition_brokerage": 2000000,
                                   "capital_expenditure": 120000000, "transfer_expenses": 10000000, "registered": True, "one_house": False, "heavy_multi_home": False})
    res = r["결과"]
    assert res["양도차익"] == 370000000                                   # 계산 결과는 기존과 동일
    comp = res["취득가액_구성"]
    assert comp.get("환산취득가액") == 125000000 and comp.get("개산공제") == 3000000
    assert comp.get("취득세", 0) == 0 and comp.get("중개수수료", 0) == 0 and "실지거래가액" in comp
    assert "취득세" in json.dumps(r.get("판단", []), ensure_ascii=False)   # 부대비용을 합산하지 않은 이유를 판단에 명시
