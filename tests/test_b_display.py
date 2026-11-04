"""표시·라벨 회귀 테스트 — 실사용 점검에서 나온 엑셀·결과 표기 문제.

- export_workbook 'forms': 서식 틀이 없는 도구(부가·증여·원천징수 등)도 '목록'에 그 사실을 적고, '계산 N'에 항목별 표를 펼친다
- '판단·근거': 금액이 없는 문장 판단은 금액 칸을 비우고, 판단 항목이 없는 도구도 call마다 한 줄 이상 남긴다
- capital_gains_income: 공제율 부동소수 표기, 근거 중복·빈 요지, 설명의 시행령 조문 번호
- financial_income_aggregate: 분리과세 때 합산액 설명 산식
- retirement_income_tax: 환산급여·환산급여공제·과세표준·환산산출세액
- personal_deduction: 퇴직·양도소득금액을 '종합 합산'으로 적지 않음
- unlisted_stock_valuation: 환급금 이자(가산)·벌금(차감)·업무용승용차 손금불산입 항목
- inheritance_gift_valuation: 임대보증금 합산 담보채권액, 임대료 등 환산가액 비교(법 제61조⑤, 영 제50조⑦)
- '계산 N': related_judge 판정, 비상장주식 연도별 순손익액
- assessment_limitation: 원천징수분 기산일
- related_judge: 조문 원문 안내에 환경변수 이름 노출 없음
- 도구 설명 글자(export_workbook company, dominant_shareholder, extract_relations)
"""
import asyncio
import json

import openpyxl
import pytest

from korean_tax_calc_mcp import server


def run(tool, args):
    r = asyncio.run(server.mcp.call_tool(tool, args))
    raw = r.content[0].text if hasattr(r, "content") else r[0][0].text
    return json.loads(raw)


def build(tmp_path, calls, **kw):
    r = server.export_workbook(title="wb", calls=calls, output_dir=str(tmp_path), **kw)
    assert "error" not in r, r
    return r, openpyxl.load_workbook(r["결과"]["파일"])


def rows(ws):
    return [[c for c in row] for row in ws.iter_rows(values_only=True)]


def strings(ws):
    return [c for row in ws.iter_rows(values_only=True) for c in row if isinstance(c, str)]


def tool_desc(name):
    tools = asyncio.run(server.mcp.list_tools())
    return next(t for t in tools if t.name == name).description


def param_desc(name, param):
    tools = asyncio.run(server.mcp.list_tools())
    t = next(t for t in tools if t.name == name)
    schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema")
    return schema["properties"][param].get("description", "")


VAT_CALLS = [
    {"label": "간주공급 항목별", "tool": "vat_deemed_supply_items", "args": {"period": "2025-2", "items": [
        {"항목": "텀블러 고객 증정", "거래": "사업상증여", "매입세액공제": True, "시가": 2_000_000},
        {"항목": "견본", "거래": "사업상증여", "매입세액공제": True, "시가": 300_000, "견본_광고선전물": True}]}},
    {"label": "간주임대료", "tool": "vat_deemed_rent", "args": {"deposit": 200_000_000, "days": 92, "period": "2025-2"}},
    {"label": "카드 발행세액공제", "tool": "vat_card_sales_credit", "args": {
        "amount": 220_000_000, "supplied_on": "2025-12-31", "used_this_year": 8_000_000, "individual": True,
        "prior_year_supply": 600_000_000}},
    {"label": "지연발급 가산세", "tool": "invoice_penalty", "args": {"supply_amount": 4_000_000, "kind": "지연발급", "supplied_on": "2025-08-01"}},
]

WH_CALLS = [
    {"label": "사용료 원천징수", "tool": "nonresident_withholding", "args": {
        "income_kind": "사용료", "amount": 55_000_000, "recipient_type": "법인", "residence_country": "JP", "treaty_rate": 0.1}},
    {"label": "납부지연", "tool": "late_payment_penalty", "args": {"unpaid_tax": 500_000, "due": "2025-04-10", "until": "2026-06-30"}},
    {"label": "제척기간", "tool": "assessment_limitation", "args": {"due_date": "2024-01-10", "offshore": True}},
]


# ── 서식 틀 없는 도구: '목록'에 안내, '계산 N'에 항목별 표 ──
# (부가 간주공급·간주임대료·카드공제·세금계산서 가산세는 이제 서식 시트가 생김 — test_forms_vat_gift_wh.py)
def test_forms_layout_notes_tools_without_form_template(tmp_path):
    r, wb = build(tmp_path, WH_CALLS)
    lst = wb["목록"]
    s = "\n".join(strings(lst))
    for tool in ("late_payment_penalty", "assessment_limitation"):
        assert tool in s, f"목록에 {tool} 안내 없음"
    assert "서식 틀 없음" in s
    # call ↔ 시트 대응표의 서식 시트 칸도 비워 두지 않음
    table = rows(lst)
    hdr = next(i for i, rw in enumerate(table) if rw[:4] == ["call", "label", "계산 시트", "서식 시트"])
    for rw in table[hdr + 1: hdr + 1 + len(WH_CALLS)]:
        assert rw[3], rw


def test_forms_layout_calc_sheet_lists_items(tmp_path):
    r, wb = build(tmp_path, VAT_CALLS)
    s = strings(wb["계산 1"])
    assert "텀블러 고객 증정" in s and "견본" in s, s
    assert any("공급 아님" in x for x in s), s


# ── 판단·근거 ──
def test_judgement_sheet_blank_amount_for_sentence_rows(tmp_path):
    r, wb = build(tmp_path, VAT_CALLS[:1])
    ws = wb["판단·근거"]
    body = rows(ws)[1:]
    assert body, "판단 행 없음"
    for rw in body:
        if rw[1] == "견본":
            assert rw[3] in (None, ""), rw


def test_judgement_sheet_not_empty_without_judgement_key(tmp_path):
    r, wb = build(tmp_path, WH_CALLS)
    body = [rw for rw in rows(wb["판단·근거"])[1:] if any(v not in (None, "") for v in rw)]
    labels = {rw[0] for rw in body}
    for c in WH_CALLS:
        assert c["label"] in labels, (c["label"], body)
    s = "\n".join(strings(wb["판단·근거"]))
    assert "제한세율" in s          # nonresident_withholding 쟁점
    assert "판단 항목 없음" in s     # late_payment_penalty


# ── capital_gains_income ──
CG_ARGS = {"asset_type": "주택", "acquisition_date": "2012-03-15", "transfer_date": "2025-09-30",
           "transfer_price": 2_000_000_000, "acquisition_price": 700_000_000, "acquisition_tax": 23_000_000,
           "capital_expenditure": 30_000_000, "transfer_expenses": 10_000_000, "one_house": True, "exempt_met": True,
           "residence_start": "2017-02-01", "residence_end": "2025-09-30", "apply_basic_deduction": True}


def test_capital_gains_income_ratio_and_basis():
    r = run("capital_gains_income", CG_ARGS)
    res = r["결과"]
    assert res["거주기간_공제율"] == 0.32
    assert res["보유기간_공제율"] == 0.4 and res["공제율"] == 0.72
    assert res["장기보유특별공제액"] == 356_256_000
    keys = [tuple(b[:3]) for b in r["근거"]]
    assert len(keys) == len(set(keys)), keys
    assert not any(str(b[3]).rstrip().endswith("—") for b in r["근거"]), r["근거"]


def test_capital_gains_income_description_article():
    d = tool_desc("capital_gains_income")
    assert "제159조의3(4)" not in d
    assert "제159조의4" in d


# ── financial_income_aggregate ──
def test_financial_income_separate_taxation_text():
    r = run("financial_income_aggregate", {"year": 2025, "items": [{"kind": "예금이자", "amount": 3_000_000}]})
    assert r["결과"]["합산액"] == 0 and r["결과"]["분리과세"] is True
    step = next(s for s in r["계산식"] if s["이름"] == "합산액")
    assert "3,000,000 + 0 + 0 = 0원" not in step["설명"]
    assert "분리과세" in step["설명"] and "= 0원" in step["설명"], step["설명"]
    assert any(j.get("항목") == "종합과세 판정" and "분리과세" in j["결론"] for j in r["판단"]), r["판단"]


# ── retirement_income_tax ──
def test_retirement_income_tax_intermediate_steps():
    r = run("retirement_income_tax", {"income": 120_000_000, "years_of_service": 8, "retire_year": 2025})
    res = r["결과"]
    assert res["퇴직소득세"] == 7_876_000
    assert res["근속연수공제"] == 11_000_000
    assert res["환산급여"] == 163_500_000
    assert res["환산급여공제"] == 90_275_000
    assert res["퇴직소득과세표준"] == 73_225_000
    assert res["환산산출세액"] == 11_814_000


# ── personal_deduction ──
def test_personal_deduction_retirement_not_comprehensive():
    r = run("personal_deduction", {"year": 2025,
                                   "taxpayer": {"sex": "남", "birth_year": 1970, "has_spouse": True, "comprehensive_income": 50_000_000},
                                   "persons": [{"name": "배우자", "relation": "배우자", "birth_year": 1973,
                                                "income_items": [{"kind": "퇴직소득금액", "amount": 120_000_000}]},
                                               {"name": "부친", "relation": "직계존속", "birth_year": 1950,
                                                "income_items": [{"kind": "양도소득금액", "amount": 5_000_000}]}]})
    by = {p["name"]: p for p in r["결과"]["사람별"]}
    for name in ("배우자", "부친"):
        assert by[name]["기본공제"] is False
        proc = by[name]["소득처리내역"][0]
        assert "종합 합산" not in proc["처리"], proc
        assert "제50조" in proc["근거"], proc


# ── unlisted_stock_valuation ──
STOCK = {"valuation_date": "2025-09-30", "shares": 100_000,
         "incomes": [{"사업연도": 2024, "각사업연도소득": 400_000_000, "가산": {},
                      "차감": {"법인세": 56_000_000, "지방소득세": 5_600_000, "기업업무추진비 한도초과": 34_400_000, "벌금": 4_000_000}},
                     {"사업연도": 2023, "각사업연도소득": 260_000_000, "가산": {"국세환급금 이자": 3_000_000},
                      "차감": {"법인세": 29_400_000, "지방소득세": 2_940_000, "기부금 한도초과": 20_660_000}},
                     {"사업연도": 2022, "각사업연도소득": 150_000_000, "가산": {},
                      "차감": {"법인세": 15_000_000, "지방소득세": 1_500_000, "업무용승용차 손금불산입": 13_500_000}}],
         "net_asset": {"자산_장부가액": 7_700_000_000, "자산_평가차액": 100_000_000, "부채_장부가액": 2_800_000_000},
         "real_estate_ratio": 0, "is_max_shareholder": True, "sme": False, "mid_sized": False,
         "business_start": "2010-01-01", "goodwill": 0}


def test_unlisted_stock_items_accepted():
    r = run("unlisted_stock_valuation", STOCK)
    assert "error" not in r, r
    lines = {y["사업연도"]: y["산출"] for y in r["계산"]["순손익액 산출"]}
    final = {y: next(l["금액"] for l in ls if l["구분"].startswith("=")) for y, ls in lines.items()}
    assert final == {2024: 300_000_000, 2023: 210_000_000, 2022: 120_000_000}
    add23 = [l for l in lines[2023] if l["구분"].startswith("+")]
    assert len(add23) == 1 and "환급금" in add23[0]["구분"] and "제18조4호" in add23[0]["근거"] + add23[0]["구분"], add23
    sub24 = [l for l in lines[2024] if "벌금" in l["구분"]]
    assert sub24 and "제21조3호" in sub24[0]["구분"], lines[2024]


def test_unlisted_stock_carried_over_income_not_listed_as_18_4():
    args = json.loads(json.dumps(STOCK))
    args["incomes"][1]["가산"] = {"이월익금": 3_000_000}
    r = run("unlisted_stock_valuation", args)
    # 이월익금(법인세법 제18조2호)은 영 제56조④1호 가산 항목이 아님 — 제18조4호로 표기하지 않음
    text = json.dumps(r, ensure_ascii=False)
    assert "이월익금" in text
    assert not any("이월익금" in l["구분"] and "제18조4호" in l["근거"]
                   for y in (r.get("계산") or {}).get("순손익액 산출", []) for l in y["산출"])


# ── inheritance_gift_valuation ──
def test_valuation_lease_deposit_and_rent_conversion():
    r = run("inheritance_gift_valuation", {
        "kind": "증여", "valuation_date": "2025-11-20", "supplementary_value": 600_000_000,
        "secured_debt": {"채권최고액": 1_200_000_000, "채무액": 400_000_000},
        "lease": {"연간임대료": 72_000_000, "임대보증금": 300_000_000}})
    assert "error" not in r, r
    c = r["계산"]
    assert c["임대료_환산가액"] == 900_000_000      # 72,000,000 ÷ 12% + 300,000,000
    assert c["담보채권액"] == 700_000_000            # 근저당 채권액 400,000,000 + 임대보증금 300,000,000
    assert r["결과"]["평가액"] == 900_000_000
    s = json.dumps(r["판단"], ensure_ascii=False)
    assert "제61조⑤" in s and "제50조⑦" in s and "제63조" in s


def test_valuation_multiple_secured_debts():
    r = run("inheritance_gift_valuation", {
        "kind": "상속", "valuation_date": "2025-03-01", "supplementary_value": 300_000_000,
        "secured_debt": [{"채권최고액": 360_000_000, "채무액": 400_000_000}, {"채무액": 100_000_000}, {"임대보증금": 50_000_000}]})
    assert r["계산"]["담보채권액"] == 510_000_000
    assert r["결과"]["평가액"] == 510_000_000


def test_valuation_unchanged_without_new_inputs():
    r = run("inheritance_gift_valuation", {"kind": "증여", "valuation_date": "2025-11-20", "supplementary_value": 900_000_000,
                                           "secured_debt": {"채권최고액": 1_200_000_000, "채무액": 400_000_000}})
    assert r["결과"]["평가액"] == 900_000_000 and r["계산"]["담보채권액"] == 400_000_000


# ── '계산 N' 시트: related_judge 판정, 연도별 순손익액 ──
RJ = {"a": "갑", "b": "을", "on": "2025-09-30",
      "people": {"갑": {"구분": "개인"}, "을": {"구분": "개인"}, "정": {"구분": "개인"}, "정부": {"구분": "개인"},
                 "고모": {"구분": "개인"}, "조부": {"구분": "개인"}, "(주)태양": {"구분": "법인"}},
      "family": [["갑", "정", "배우자"], ["조부", "정부", "부모자녀"], ["조부", "고모", "부모자녀"],
                 ["정부", "정", "부모자녀"], ["고모", "을", "부모자녀"]],
      "stakes": [["갑", "(주)태양", 0.6]]}


@pytest.mark.parametrize("layout", ["forms", "steps"])
def test_calc_sheets_show_verdict_and_yearly_net_income(tmp_path, layout):
    r, wb = build(tmp_path, [{"label": "비상장주식", "tool": "unlisted_stock_valuation", "args": STOCK},
                             {"label": "특수관계", "tool": "related_judge", "args": RJ}], layout=layout)
    s1 = rows(wb["계산 1"])
    net = [rw for rw in s1 if any(isinstance(v, str) and v.startswith("= 순손익액") for v in rw)]
    amounts = sorted(v for rw in net for v in rw if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 10_000)
    assert amounts == [120_000_000, 210_000_000, 300_000_000], net
    s2 = strings(wb["계산 2"])
    assert any("해당 없음" in x for x in s2), s2
    j = strings(wb["판단·근거"])
    assert any("해당 없음" in x for x in j), "related_judge 판정이 판단·근거에 없음"


# ── assessment_limitation ──
def test_assessment_limitation_withholding_start_date():
    r = run("assessment_limitation", {"due_date": "2024-01-10", "offshore": True, "withholding": True})
    assert r["결과"]["기산일"].startswith("법정납부기한 다음 날"), r
    assert r["결과"]["만료일"] == "2031-01-10"
    assert "제12조의3②1호" in r["결과"]["기산일"] + json.dumps(r, ensure_ascii=False)
    r0 = run("assessment_limitation", {"due_date": "2024-03-31"})
    assert r0["결과"]["기산일"].startswith("법정신고기한 다음 날")


# ── related_judge 조문 안내 ──
def test_related_judge_no_env_var_placeholder(monkeypatch):
    from korean_tax_calc_mcp.audit.agents import related as R
    monkeypatch.delenv("LAW_OC", raising=False)
    R._CITE_CACHE.clear()
    r = run("related_judge", RJ)
    text = json.dumps(r["적용조문"], ensure_ascii=False)
    assert "LAW_OC" not in text, text
    R._CITE_CACHE.clear()


# ── 도구 설명 글자 ──
def test_export_workbook_company_wording():
    d = param_desc("export_workbook", "company")
    assert "성명" in d, d
    assert "company — 법인명(" not in tool_desc("export_workbook")


def test_description_typos():
    assert "Amid" not in tool_desc("dominant_shareholder")
    assert "오 officers" not in tool_desc("extract_relations")


# ── '계산 N' 산식 목록 줄바꿈, gift_tax 판단 칸 나눔 ──
def test_calc_sheet_formula_list_and_gift_judgement_cells(tmp_path):
    r, wb = build(tmp_path, [
        {"label": "퇴직", "tool": "retirement_income_tax", "args": {"income": 120_000_000, "years_of_service": 8, "retire_year": 2025}},
        {"label": "증여", "tool": "gift_tax", "args": {"gift_date": "2025-09-30", "gift_value": 30_000_000, "relation": "기타", "filed": True}}])
    s1 = rows(wb["계산 1"])
    assert any(rw[0] == "환산급여" and rw[1] == 163_500_000 for rw in s1), s1
    산식 = next(rw[1] for rw in s1 if rw[0] == "산식")
    assert not 산식.startswith("[") and "\n" in 산식, 산식
    jrows = [rw for rw in rows(wb["판단·근거"])[1:] if rw[0] == "증여"]
    assert jrows
    assert not any(isinstance(rw[2], str) and rw[2].startswith("{") for rw in jrows), jrows
