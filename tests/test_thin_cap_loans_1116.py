"""thin_capitalization 차입금별 계산(0.59.0) — 이자율 순 배정, 직접·보증 처분 분리, 적수, 종전 결과 동일, 법인·개인 키.

대조한 원문(조문 MCP law_article, 2026-11-16):
- 국제조세조정에 관한 법률 제22조제2항·제5항·제6항(2026.1.2. 시행본), 시행령 제47조·제48조·제49조·제50조·제51조(2026.2.27. 시행본),
  시행령 제48조·제49조·제50조(2021.2.17. 시행본) — 같은 이자율이면 차입시기가 늦은 것부터, 둘 다 같으면 차입금 비율로 안분.
- 구 국제조세조정에 관한 법률 제14조(2016.1.1.·2020.6.9. 시행본), 구 시행령 제25조제1항·제6항·제26조(2016.9.1.·2020.8.12. 시행본)
  — 이자율이 높은 차입금부터, 같은 이자율이면 차입시기가 늦은 것부터. 이자율·차입시기가 모두 같은 경우의 규정 없음.
- 시행규칙 별지 제24호서식(갑)(2026.3.20. 시행본): 손금불산입액 = 차입금 이자율 × 차입금 적수 ÷ 연중 일수.
기대값은 모두 손계산(산식 주석). 금액은 지어낸 둥근 숫자.
"""
import json

from tests._helpers import call as c

ISSUES = json.load(open("korean_tax_calc_mcp/data/issues.json", encoding="utf-8"))["thin_capitalization"]


def _rows(r):
    return {x["이름"]: x for x in r["결과"]["차입금별"]}


# ── 1. 초과분이 차입금 하나 안에서 끝나는 경우 ─────────────────────────────────
def test_excess_ends_inside_first_loan():
    # 출자 10억 × 2 = 한도 20억. 차입 A(직접 6%) 15억 + B(보증 4%) 10억 + C(직접 5%) 5억 = 30억 → 초과 10억
    # 이자율 순서 A(6%) → C(5%) → B(4%). 초과 10억은 A(15억) 안에서 끝남 → A 10억 × 6% = 60,000,000(배당), B·C 0
    r = c("thin_capitalization", {"equity": 1_000_000_000, "year": 2025, "loans": [
        {"name": "A", "kind": "직접", "rate": 0.06, "average_balance": 1_500_000_000},
        {"name": "B", "kind": "보증", "rate": 0.04, "average_balance": 1_000_000_000},
        {"name": "C", "kind": "직접", "rate": 0.05, "average_balance": 500_000_000}]})
    res = r["결과"]
    assert res["초과차입금(평균잔액)"] == 1_000_000_000
    assert res["초과차입금적수"] == 1_000_000_000 * 365
    rows = _rows(r)
    assert rows["A"]["손금불산입 이자"] == 60_000_000 and rows["A"]["소득처분"] == "배당"
    assert rows["B"]["손금불산입 이자"] == 0 and rows["C"]["손금불산입 이자"] == 0
    assert [rows[k]["배정 순위"] for k in "ACB"] == [1, 2, 3]
    assert res["손금불산입 이자"] == 60_000_000 and res["배당 처분"] == 60_000_000 and res["기타사외유출 처분"] == 0
    assert res["처분"] == "배당"
    assert r["세무조정"] == [{"구분": "과소자본 지급이자(국외지배주주 차입분)", "조정": "손금불산입", "금액": 60_000_000,
                          "소득처분": "배당", "근거": "국제조세조정에 관한 법률 제22조제2항·제6항, 시행령 제49조"}]
    # 평균 이자율 방식이면 (총이자 ÷ 30억) × 10억 — 이자율 순 배정과 다름(종전 방식의 한계)


# ── 2. 여러 차입금에 걸치고, 직접·보증 처분이 나뉘는 경우(적수 입력, 윤년) ──────────
def test_excess_spans_loans_and_splits_disposition_jeoksu_leap_year():
    # 2024 사업연도(366일). 출자 5억 × 2 = 한도 10억 → 적수 3,660억
    # G(보증 7%) 4억, A(직접 6%) 8억, B(직접 3%) 6억 → 적수 합계 18억 × 366 = 6,588억, 초과적수 8억 × 366 = 2,928억
    # G 적수 1,464억 전부 → 1,464억 × 7% ÷ 366 = 28,000,000(기타사외유출)
    # A 남은 1,464억 → 1,464억 × 6% ÷ 366 = 24,000,000(배당), B 0 → 합계 52,000,000
    d = 366
    r = c("thin_capitalization", {"equity": 500_000_000, "year": 2024, "loans": [
        {"name": "B", "kind": "직접", "rate": 0.03, "jeoksu": 600_000_000 * d},
        {"name": "A", "kind": "직접", "rate": 0.06, "jeoksu": 800_000_000 * d},
        {"name": "G", "kind": "보증", "rate": 0.07, "jeoksu": 400_000_000 * d}]})
    res, rows = r["결과"], _rows(r)
    assert res["연중 일수"] == 366
    assert res["초과차입금적수"] == 800_000_000 * d
    assert rows["G"]["손금불산입 이자"] == 28_000_000 and rows["G"]["소득처분"] == "기타사외유출"
    assert rows["A"]["손금불산입 이자"] == 24_000_000 and rows["A"]["소득처분"] == "배당"
    assert rows["A"]["초과차입금적수 배정"] == 400_000_000 * d
    assert rows["B"]["손금불산입 이자"] == 0
    assert (res["배당 처분"], res["기타사외유출 처분"], res["손금불산입 이자"]) == (24_000_000, 28_000_000, 52_000_000)
    assert res["처분"] == "배당·기타사외유출"
    assert [(a["금액"], a["소득처분"]) for a in r["세무조정"]] == [(24_000_000, "배당"), (28_000_000, "기타사외유출")]
    # income_adjustment_total에 그대로 넣을 수 있음: 순이익 1억 + 손금불산입 52,000,000 = 152,000,000
    t = c("income_adjustment_total", {"net_income": 100_000_000, "items": r["세무조정"]})
    assert "error" not in t, t
    assert json.dumps(t, ensure_ascii=False).count("152000000") >= 1


def test_jeoksu_rounds_down_per_loan():
    # 출자 0 → 전액 초과. 적수 1,000,000,007 × 5% ÷ 365 = 136,986.30… → 136,986(원 미만 버림)
    r = c("thin_capitalization", {"equity": 0, "year": 2025, "loans": [
        {"name": "X", "kind": "직접", "rate": 0.05, "jeoksu": 1_000_000_007}]})
    assert r["결과"]["손금불산입 이자"] == 136_986


def test_days_in_year_input():
    # 사업연도 6개월(181일)인 경우: 출자 1억 × 2 = 2억, 평균잔액 3억 → 초과 1억 → 1억 × 181 × 8% ÷ 181 = 8,000,000
    r = c("thin_capitalization", {"equity": 100_000_000, "year": 2025, "days_in_year": 181, "loans": [
        {"name": "X", "kind": "직접", "rate": 0.08, "jeoksu": 300_000_000 * 181}]})
    assert r["결과"]["손금불산입 이자"] == 8_000_000 and r["결과"]["연중 일수"] == 181
    assert not any("연중 일수를" in x for x in r["주의"])


def test_balance_input_warns_no_change_assumed():
    # 잔액 3억(변동 없다고 봄), 출자 1억 → 초과 1억 × 5% = 5,000,000
    r = c("thin_capitalization", {"equity": 100_000_000, "year": 2025, "loans": [
        {"name": "X", "kind": "직접", "rate": 0.05, "balance": 300_000_000}]})
    assert r["결과"]["손금불산입 이자"] == 5_000_000
    assert any("변동이 없다고 보고" in x for x in r["주의"])


# ── 3. 같은 이자율 — 차입시기, 안분, 2020년 이전 ───────────────────────────
TIE = [{"name": "D", "kind": "직접", "rate": 0.05, "average_balance": 600_000_000, "borrowed_on": "2019-03-04"},
       {"name": "E", "kind": "직접", "rate": 0.05, "average_balance": 300_000_000, "borrowed_on": "2019-03-04"}]


def test_same_rate_later_borrowing_first():
    # 출자 3억 × 2 = 6억, 합계 9억 → 초과 3억. E가 늦게 차입 → E 3억 전부 × 5% = 15,000,000, D 0
    loans = [dict(TIE[0]), dict(TIE[1], borrowed_on="2020-07-01")]
    r = c("thin_capitalization", {"equity": 300_000_000, "year": 2022, "loans": loans})
    rows = _rows(r)
    assert rows["E"]["손금불산입 이자"] == 15_000_000 and rows["D"]["손금불산입 이자"] == 0


def test_same_rate_same_date_prorated_from_2021():
    # 이자율·차입일 모두 같음 → 차입금 비율(6:3)로 초과 3억 안분: D 2억 × 5% = 10,000,000, E 1억 × 5% = 5,000,000
    r = c("thin_capitalization", {"equity": 300_000_000, "year": 2022, "loans": TIE})
    rows = _rows(r)
    assert rows["D"]["손금불산입 이자"] == 10_000_000 and rows["E"]["손금불산입 이자"] == 5_000_000
    assert "안분" in r["계산"]


def test_same_rate_same_date_2020_input_order_with_note():
    # 구 시행령 제25조제1항에는 안분 규정 없음 → 입력 순서(D 먼저): D 3억 × 5% = 15,000,000, E 0, 주의
    r = c("thin_capitalization", {"equity": 300_000_000, "year": 2020, "loans": TIE})
    rows = _rows(r)
    assert rows["D"]["손금불산입 이자"] == 15_000_000 and rows["E"]["손금불산입 이자"] == 0
    assert any("구 시행령 제25조제1항" in x and "입력 순서" in x for x in r["주의"])


def test_same_rate_without_date_rejected():
    loans = [{k: v for k, v in x.items() if k != "borrowed_on"} for x in TIE]
    r = c("thin_capitalization", {"equity": 300_000_000, "year": 2022, "loans": loans})
    assert r.get("error") and "borrowed_on" in json.dumps(r, ensure_ascii=False)


# ── 4. 배당 처분분만 원천징수 재계산, 법인·개인 키 ─────────────────────────────
def test_withholding_recalc_only_on_dividend_part_corporate():
    # 출자 5억, G(보증 7%) 4억·A(직접 6%) 8억·B(직접 3%) 6억(2025, 평균잔액) → 배당 24,000,000, 기타사외유출 28,000,000
    # 수취인 외국법인, 이자 조약 10%, 배당 조약 5%: 이자 기준 2,400,000 / 배당 기준 1,200,000 → 법인세 차액 −1,200,000
    # 지방소득세: 240,000 / 120,000 → 차액 −120,000
    r = c("thin_capitalization", {"equity": 500_000_000, "year": 2025, "recipient_type": "법인",
                                  "recipient_residence_country": "US", "interest_treaty_rate": 0.10, "dividend_treaty_rate": 0.05,
                                  "loans": [{"name": "G", "kind": "보증", "rate": 0.07, "average_balance": 400_000_000},
                                            {"name": "A", "kind": "직접", "rate": 0.06, "average_balance": 800_000_000},
                                            {"name": "B", "kind": "직접", "rate": 0.03, "average_balance": 600_000_000}]})
    w = r["결과"]["원천징수 재계산"]
    assert w["대상 금액(손금불산입 이자)"] == 24_000_000
    assert (w["이자 기준 원천징수세액"], w["배당 기준 원천징수세액"]) == (2_400_000, 1_200_000)
    assert w["법인세 차액"] == -1_200_000 and "소득세 차액" not in w
    assert w["지방소득세 차액"] == -120_000
    assert "제22조제5항" in w["근거"]
    assert any("기타사외유출 처분분" in x for x in r["주의"])


def test_guarantee_only_no_recalc():
    # 보증 차입만 초과 → 전부 기타사외유출, 원천징수 재계산 없음. 출자 1억, 보증 3억 6% → 초과 1억 × 6% = 6,000,000
    r = c("thin_capitalization", {"equity": 100_000_000, "year": 2025, "recipient_residence_country": "US",
                                  "loans": [{"name": "G", "kind": "guarantee", "rate": 0.06, "average_balance": 300_000_000}]})
    assert r["결과"]["기타사외유출 처분"] == 6_000_000 and r["결과"]["처분"] == "기타사외유출"
    assert "원천징수 재계산" not in r["결과"]
    assert r["세무조정"][0]["소득처분"] == "기타사외유출"


def test_legacy_corporate_key_is_corporate_tax():
    # loans 없이 법인 수취인: 출자 10억, 차입 30억, 이자 1.5억 → 초과 10억, 손금불산입 1.5억 × 10/30 = 50,000,000
    # 이자 10% 5,000,000 / 배당 5% 2,500,000 → 법인세 차액 −2,500,000, 지방 −250,000
    r = c("thin_capitalization", {"equity": 1_000_000_000, "borrowings": 3_000_000_000, "total_interest": 150_000_000,
                                  "year": 2025, "recipient_type": "법인", "recipient_residence_country": "US",
                                  "interest_treaty_rate": 0.10, "dividend_treaty_rate": 0.05})
    w = r["결과"]["원천징수 재계산"]
    assert w["법인세 차액"] == -2_500_000 and "소득세 차액" not in w and w["지방소득세 차액"] == -250_000


def test_legacy_individual_key_unchanged():
    r = c("thin_capitalization", {"equity": 1_000_000_000, "borrowings": 3_000_000_000, "total_interest": 150_000_000,
                                  "year": 2025, "recipient_residence_country": "US", "interest_treaty_rate": 0.10,
                                  "dividend_treaty_rate": 0.05})
    w = r["결과"]["원천징수 재계산"]
    assert w["소득세 차액"] == -2_500_000 and "법인세 차액" not in w


# ── 5. loans 없을 때 종전 결과와 같음(결과 전체 대조) ───────────────────────────
def _strip(r):
    return {k: v for k, v in r.items() if k not in ("호출_id", "엑셀")}


def test_legacy_full_result_2026():
    # 출자 20억, 차입 50억, 이자 3억 → 한도 40억, 초과 10억, 손금불산입 3억 × 10/50 = 60,000,000
    r = c("thin_capitalization", {"equity": 2_000_000_000, "borrowings": 5_000_000_000, "total_interest": 300_000_000})
    exp = {"결과": {"출자금액": 2_000_000_000, "총차입금": 5_000_000_000, "적용배수": 2, "한도차입금": 4_000_000_000,
                  "초과차입금": 1_000_000_000, "지급이자": 300_000_000, "손금불산입 이자": 60_000_000, "처분": "배당",
                  "근거": "국제조세조정에 관한 법률 제22조(과소자본 손금불산입), 동법 시행령 제46조~제50조"},
           "근거": "국제조세조정에 관한 법률 제22조, 시행령 제46조~제50조", "쟁점": ISSUES}
    assert _strip(r) == exp
    assert list(_strip(r)) == list(exp) and list(r["결과"]) == list(exp["결과"])


def test_legacy_full_result_2018_individual_recalc():
    # 출자 10억, 차입 30억, 이자 1.5억(2018) → 초과 10억, 손금불산입 50,000,000
    # 개인·미국: 이자 12% 6,000,000(지방 600,000), 배당 15% 7,500,000(지방 750,000) → 소득세 차액 1,500,000, 지방 150,000
    r = c("thin_capitalization", {"equity": 1_000_000_000, "borrowings": 3_000_000_000, "total_interest": 150_000_000,
                                  "year": 2018, "recipient_residence_country": "미국", "interest_treaty_rate": 0.12,
                                  "dividend_treaty_rate": 0.15})
    exp = {"결과": {"출자금액": 1_000_000_000, "총차입금": 3_000_000_000, "적용배수": 2, "한도차입금": 2_000_000_000,
                  "초과차입금": 1_000_000_000, "지급이자": 150_000_000, "손금불산입 이자": 50_000_000, "처분": "배당",
                  "근거": "국제조세조정에 관한 법률 제14조(과소자본 손금불산입), 동법 시행령 제24조~제26조",
                  "원천징수 재계산": {"대상 금액(손금불산입 이자)": 50_000_000, "이자 기준 원천징수세액": 6_000_000,
                                "이자 기준 지방소득세": 600_000, "배당 기준 원천징수세액": 7_500_000, "배당 기준 지방소득세": 750_000,
                                "소득세 차액": 1_500_000, "지방소득세 차액": 150_000,
                                "근거": "국조법 제14조 ① 배당 처분 → 소득세법 제119조 2호 / 법인세법 제93조 2호 배당소득"}},
           "근거": "국제조세조정에 관한 법률 제14조, 시행령 제24조~제26조", "쟁점": ISSUES}
    assert _strip(r) == exp
    assert list(r["결과"]["원천징수 재계산"]) == list(exp["결과"]["원천징수 재계산"])


def test_legacy_full_result_no_excess():
    # 출자 30억 × 2 = 60억 ≥ 차입 50억 → 초과 0, 손금불산입 0, 해당없음, 재계산 없음
    r = c("thin_capitalization", {"equity": 3_000_000_000, "borrowings": 5_000_000_000, "total_interest": 300_000_000,
                                  "year": 2021, "ratio": 2, "recipient_residence_country": "US"})
    exp = {"결과": {"출자금액": 3_000_000_000, "총차입금": 5_000_000_000, "적용배수": 2, "한도차입금": 6_000_000_000,
                  "초과차입금": 0, "지급이자": 300_000_000, "손금불산입 이자": 0, "처분": "해당없음",
                  "근거": "국제조세조정에 관한 법률 제22조(과소자본 손금불산입), 동법 시행령 제46조~제50조"},
           "근거": "국제조세조정에 관한 법률 제22조, 시행령 제46조~제50조", "쟁점": ISSUES}
    assert _strip(r) == exp


def test_legacy_financial_ratio_6():
    # 금융업 6배: 출자 1억 × 6 = 6억, 차입 9억 → 초과 3억, 이자 4,500만 × 3/9 = 15,000,000
    r = c("thin_capitalization", {"equity": 100_000_000, "borrowings": 900_000_000, "total_interest": 45_000_000, "ratio": 6})
    assert r["결과"]["한도차입금"] == 600_000_000 and r["결과"]["손금불산입 이자"] == 15_000_000
    assert "세무조정" not in r and "주의" not in r and "계산" not in r


# ── 6. 2020·2021 조문 번호 ──────────────────────────────────────────────────
L1 = [{"name": "A", "kind": "직접", "rate": 0.05, "average_balance": 300_000_000},
      {"name": "G", "kind": "보증", "rate": 0.06, "average_balance": 100_000_000}]


def test_article_numbers_2020_vs_2021():
    old = c("thin_capitalization", {"equity": 100_000_000, "year": 2020, "loans": L1})
    new = c("thin_capitalization", {"equity": 100_000_000, "year": 2021, "loans": L1})
    assert "구 국제조세조정에 관한 법률 제14조제1항" in old["근거"] and "구 시행령 제25조" in old["근거"] and "제22조" not in old["근거"]
    assert "제22조" in new["근거"] and "시행령 제48조" in new["근거"] and "시행령 제49조" in new["근거"] and "제14조" not in new["근거"]
    assert "구 시행령 제25조제6항" in old["세무조정"][0]["근거"]
    # 과다이자 규정 관계: 2020은 구 제16조, 2021은 제26조
    assert "구 같은 법 제16조제1항" in old["주의"][0] and "제26조제1항" in new["주의"][0]
    # 같은 계산: 출자 1억 × 2 = 2억, 합계 4억 → 초과 2억: G(6%) 1억 6,000,000 + A(5%) 1억 5,000,000
    for r in (old, new):
        assert (r["결과"]["배당 처분"], r["결과"]["기타사외유출 처분"]) == (5_000_000, 6_000_000)


def test_2018_no_income_based_rule():
    r = c("thin_capitalization", {"equity": 100_000_000, "year": 2018, "loans": L1})
    assert "2019.1.1. 이후 개시" in r["주의"][0]


# ── 7. 모르는 값 거부 ───────────────────────────────────────────────────────
def _err(args):
    r = c("thin_capitalization", args)
    assert "error" in r, r
    return json.dumps(r, ensure_ascii=False)


def test_rejects_unknown_values():
    base = {"equity": 100_000_000, "year": 2025}
    assert "허용값" in _err(dict(base, loans=[{"kind": "기타", "rate": 0.05, "balance": 1}]))
    assert "0 초과 1 미만" in _err(dict(base, loans=[{"kind": "직접", "rate": 5, "balance": 1}]))
    assert "하나만" in _err(dict(base, loans=[{"kind": "직접", "rate": 0.05, "balance": 1, "average_balance": 1}]))
    assert "하나만" in _err(dict(base, loans=[{"kind": "직접", "rate": 0.05}]))
    import asyncio
    import pytest
    from mcp.server.mcpserver.exceptions import ToolError
    from korean_tax_calc_mcp.server import mcp
    with pytest.raises(ToolError):      # 모르는 키는 스키마 검증에서 거부(extra='forbid')
        asyncio.run(mcp.call_tool("thin_capitalization", dict(base, loans=[{"kind": "직접", "rate": 0.05, "balance": 1, "모르는키": 1}])))
    assert "YYYY-MM-DD" in _err(dict(base, loans=[{"kind": "직접", "rate": 0.05, "balance": 1, "borrowed_on": "작년"}]))
    # borrowings·total_interest가 loans와 맞지 않으면 거부
    assert "borrowings" in _err(dict(base, borrowings=999, loans=[{"kind": "직접", "rate": 0.05, "balance": 300_000_000}]))
    assert "total_interest" in _err(dict(base, total_interest=1, loans=[{"kind": "직접", "rate": 0.05, "balance": 300_000_000, "interest": 2}]))
    # loans도 borrowings도 없으면 거부
    assert "borrowings" in _err(base)


def test_matching_totals_accepted_and_interest_check():
    # borrowings·total_interest가 loans와 같으면 계산. 출자 1억, 3억 5% → 5,000,000 > 입력 이자 4,000,000이면 주의
    r = c("thin_capitalization", {"equity": 100_000_000, "year": 2025, "borrowings": 300_000_000, "total_interest": 4_000_000,
                                  "loans": [{"name": "X", "kind": "직접", "rate": 0.05, "balance": 300_000_000, "interest": 4_000_000}]})
    assert r["결과"]["손금불산입 이자"] == 5_000_000
    assert any("입력한 지급이자" in x for x in r["주의"])
