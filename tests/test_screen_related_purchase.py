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


def test_row_amount_from_profile_ratio():
    """후보 행의 매입 금액 = 프로필 비율 × 그 비율의 분모. 분모가 무엇인지 근거에서 못 읽으면 비움."""
    ok = {"related_purchase_ratio": value(0.9, rcept_no="1", account="특수관계자 주석 표(열 매입) 재고 매입 ÷ 매출원가: 특수관계자")}
    assert C.related_purchase_amount(ok, {"cogs": 800, "revenue": 1000}) == 720
    rev = {"related_purchase_ratio": value(0.5, rcept_no="1", account="특수관계자 주석 표(열 매입) 매입 ÷ 매출: 특수관계자")}
    assert C.related_purchase_amount(rev, {"cogs": None, "revenue": 1000}) == 500
    assert C.related_purchase_amount({"related_purchase_ratio": value(note="매입 열 못 찾음")}, {"cogs": 800, "revenue": 1000}) is None
    assert C.related_purchase_amount({"related_purchase_ratio": value(0.9, rcept_no="1", account="근거 문구 없음")}, {"cogs": 800, "revenue": 1000}) is None
    assert C.related_purchase_amount(ok, {"cogs": None, "revenue": 1000}) is None
    assert C.related_purchase_amount({"related_purchase_ratio": value(0.0, rcept_no="1", account="특수관계자 거래 없음 문장")}, {"cogs": 800, "revenue": 1000}) == 0
    assert "related_party_purchase" in C.CANDIDATE_COLS


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
