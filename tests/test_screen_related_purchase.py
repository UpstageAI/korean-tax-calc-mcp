"""tp_comparable_screen·kr_comparable_candidates·kr_comparable_profile_compare — 특수관계 매입 비중(특수관계자로부터의 매입 ÷ 매출원가).
가상 회사. Claude 작성(2026-11-20). 배경: 선별은 특수관계 매출만 봐서, 관계사에서 사 와 파는 판매 자회사(특수관계 매출 0%대·매입 대부분)가 걸리지 않았음.
기준값은 조문 MCP가 줌 — 이 도구에 기본값 없음(키를 안 주면 꺼짐)."""
from korean_tax_calc_mcp.engine import calc_tp_screen as T
from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import compare as P
from korean_tax_calc_mcp.engine.kr_comparables.schema import value

YEARS = [2022, 2023, 2024]


def _rows(cid, name, om=0.05, last=None, **extra):
    out = [{"company_id": cid, "company_name": name, "country": "KR", "industry_code": "46539", "currency": "KRW", "year": y,
            "revenue": 1000, "cogs": 800, "operating_profit": 1000 * om, "total_assets": 800, "max_shareholder_pct": 10, **extra} for y in YEARS]
    out[-1].update(last or {})
    return out


def _tp():
    return {"name": "분석대상", "is_resident": True, "years": {y: {"revenue": 100, "operating_profit": 3} for y in YEARS}}


def run(rows, screens=None):
    return T.comparable_screen(rows=rows, tested_party=_tp(), analysis_years=YEARS, tested_year=2024, screens=screens,
                               multi_year_reason={"code": 1, "text": "경기 변동"}, search_log={"db": "가상"})


def _mx(r):
    return {m["company_id"]: m for m in r["탈락_매트릭스"]}


BASE = _rows("A", "가나", 0.04) + _rows("B", "다라", 0.05) + _rows("C", "마바", 0.06)


def test_related_purchase_over_limit_is_dropped():
    rows = BASE + _rows("S", "사아", 0.07, last={"related_party_purchase": 720, "related_party_revenue": 10})   # 매입 720/800 = 90%, 매출 1%
    r = run(rows, {"related_max": 0.25, "related_purchase_max": 0.25})
    m = _mx(r)
    assert m["S"]["S9"] == "통과"
    assert m["S"]["S9b"].startswith("탈락") and "90" in m["S"]["S9b"] and "25" in m["S"]["S9b"] and "매출원가" in m["S"]["S9b"]
    assert m["S"]["최종"] != "선정" and r["결과"]["최종_수"] == 3
    step = [x for x in r["보고서_부록"]["단계별_탈락"] if x["단계"].startswith("S9b")]
    assert step and step[0]["탈락"] == 1 and "특수관계 매입" in step[0]["단계"]


def test_related_purchase_under_limit_passes_and_missing_data_is_skipped():
    rows = (BASE + _rows("U", "자차", 0.07, last={"related_party_purchase": 100})          # 100/800 = 12.5%
            + _rows("N", "카타", 0.08))                                                    # 매입 금액 없음
    m = _mx(run(rows, {"related_purchase_max": 0.25}))
    assert m["U"]["S9b"] == "통과" and m["U"]["최종"] == "선정"
    assert m["N"]["S9b"].startswith("건너뜀") and "자료 없음" in m["N"]["S9b"] and m["N"]["최종"] == "선정"


def test_no_key_means_screen_is_off_and_result_is_unchanged():
    rows = BASE + _rows("S", "사아", 0.07, last={"related_party_purchase": 720})
    a = run(rows, {"related_max": 0.25})
    plain = run(BASE + _rows("S", "사아", 0.07), {"related_max": 0.25})
    assert _mx(a)["S"]["S9b"].startswith("건너뜀") and "꺼짐" in _mx(a)["S"]["S9b"]
    assert a["결과"]["범위"] == plain["결과"]["범위"] and a["결과"]["최종_수"] == plain["결과"]["최종_수"] == 4
    assert T.DEFAULT_SCREENS["related_purchase_max"] is None        # 관행 기본값을 두지 않음


def test_purchase_without_cogs_is_skipped_not_guessed():
    rows = BASE + [{**r, "cogs": None} for r in _rows("X", "파하", 0.07, last={"related_party_purchase": 720})]
    m = _mx(run(rows, {"related_purchase_max": 0.25}))
    assert m["X"]["S9b"].startswith("건너뜀") and m["X"]["최종"] == "선정"


def test_criteria_table_lists_the_new_screen():
    r = run(BASE, {"related_purchase_max": 0.25})
    row = [c for c in r["보고서_부록"]["탐색_조건"]["적용_기준"] if c["기준"].startswith("S9b")]
    assert row and row[0]["값"] == 0.25 and row[0]["입력"] == "사용자 입력"


def _detail(ratio=None, base_kind=None, amount=None, base=None, why="x"):
    return {"ratio": ratio, "amount": amount, "base": base, "base_kind": base_kind, "unit": 1, "where": "", "kind": "", "why": why}


def test_row_amount_from_read_result():
    """후보 행의 매입·매출 금액은 읽기 결과의 칸(비율·분모 종류)에서 — 근거 문구가 어떻게 적혀 있든 상관없다. 분모를 모르면 비움."""
    row = {"cogs": 800, "revenue": 1000}
    assert C.related_amount(_detail(0.9, "매출원가", 720, 800), row) == 720
    assert C.related_amount(_detail(0.5, "매출", 500, 1000), {"cogs": None, "revenue": 1000}) == 500
    assert C.related_amount(_detail(0.9, "매출원가", 720, 800, why="문구를 다듬어 '÷' 글자가 없어도"), row) == 720
    assert C.related_amount(_detail(why="매입 열 못 찾음"), row) is None            # 비율 없음
    assert C.related_amount(None, row) is None and C.related_amount({}, row) is None   # 원문이 없어 읽지 않음
    assert C.related_amount(_detail(0.9, None, 720, 800), row) is None             # 분모 종류 모름
    assert C.related_amount(_detail(0.9, "매출원가", 720, 800), {"cogs": None, "revenue": 1000}) is None   # 행에 그 분모가 없음
    assert C.related_amount(_detail(0.0, "매출원가", 0, 800, why="특수관계자 거래 없음 문장"), row) == 0
    assert C.related_amount(_detail(0.9, "매출원가", 721, 800), row) == 720         # 원문 금액과 비율 × 분모가 다르면 종전 값(비율 × 분모)
    assert "related_party_purchase" in C.CANDIDATE_COLS


def test_row_amount_survives_evidence_wording():
    """원문 → 읽기 결과 → 후보 행 금액까지. 근거 문구를 바꿔도(되읽지 않으므로) 금액이 비지 않는다."""
    from korean_tax_calc_mcp.engine.kr_comparables import statements as ST
    tr = lambda *c: "<TR>" + "".join(f"<TD>{x}</TD>" for x in c) + "</TR>"
    s = ("<P>9. 특수관계자</P><P>(단위:천원)</P><TABLE><TR><TH>회사명</TH><TH>매출</TH><TH>상품매입</TH></TR>"
         + tr("A", "1,234", "300") + tr("B", "0", "33") + "</TABLE><P>10. 유형자산</P>")
    row = {"cogs": 1_000_000, "revenue": 3_000_000}
    d = ST.related_purchases_detail(s, False, row["cogs"], row["revenue"])
    assert C.related_amount(d, row) == 333_000 and C.related_amount({**d, "why": "다듬은 문구"}, row) == 333_000
    assert C.related_amount(ST.related_sales_detail(s, False, row["revenue"]), row) == 1_234_000
    cell = C._related_cell(d, "20250101000001")
    assert cell["value"] == d["ratio"] and cell["status"] == "확보" and cell["evidence"] == {"rcept_no": "20250101000001", "account": d["why"]}
    miss = C._related_cell(ST.related_purchases_detail("<P>1. 일반</P>", False, 1, 1), "20250101000001")
    assert miss["value"] is None and miss["evidence"] == {} and miss["note"] == "특수관계자 절 못 찾음"


def _cand(**kw):
    base = {"company_id": "S", "company_name": "사아", "max_shareholder_pct": value(10.0, account="x"),
            "related_sales_ratio": value(0.01, account="x"), "related_purchase_ratio": value(0.4, account="x")}
    base.update(kw)
    return base


def test_compare_purchase_review_key_overrides_only_purchase_side():
    t = {"main_category": "merchandise", "main_share": 0.9, "inventory_basis": "ratio", "inv_to_sales": 0.15}
    def reasons(rules):
        import json
        return json.dumps(P.run_tool(t, [_cand()], rules), ensure_ascii=False, default=str)
    a = reasons({"related_sales_review": 0.5})                                   # 매입 40% < 50% — 종전처럼 매출 기준을 매입에도 씀
    b = reasons({"related_sales_review": 0.5, "related_purchase_review": 0.25})  # 매입 기준을 따로 주면 그것으로
    assert "[I2] 특수관계 매입" not in a and "[I2] 특수관계 매입 40% ≥ 25%" in b
    assert "related_purchase_review" in P.RULE_KEYS and P.merged_rules(None)["related_purchase_review"] is None


def test_related_amount_zero_ratio_without_base_is_zero():
    from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
    zero = {"ratio": 0.0, "amount": 0, "base": None, "base_kind": None, "unit": None, "where": "", "kind": "", "why": "특수관계자 거래 없음 문장"}
    assert C.related_amount(zero, {"revenue": None, "cogs": None}) == 0          # 거래 없음은 분모가 없어도 0(종전 동작)
    none = {"ratio": None, "amount": None, "base": None, "base_kind": None, "unit": None, "where": "", "kind": "", "why": "못 읽음"}
    assert C.related_amount(none, {"revenue": 100, "cogs": 80}) is None
    part = {"ratio": 0.25, "amount": 20, "base": 80, "base_kind": "매출원가", "unit": 1, "where": "", "kind": "재고 매입", "why": "x"}
    assert C.related_amount(part, {"revenue": 100, "cogs": 80}) == 20
    assert C.related_amount(part, {"revenue": 100, "cogs": None}) is None       # 분모 금액이 행에 없으면 추정하지 않음
