"""지방소득세 특별징수 납부지연가산세 — withholding_late_payment_penalty(tax="local") 정답 테스트.

기대값은 아래 조문에서 손으로 계산한 값(구현 결과를 옮기지 않음). 대조한 시행본(법제처, 2026-11-16 조회):
  지방세기본법 제53조의5(2016.1.1.·2016.11.30. 시행본), 제56조(2017.3.28.·2021.1.1.·2023.6.1.·2024.1.1.·2025.1.1.·2026.10.2. 시행본)
    ~2023: 10% 한도로 1호 3% + 2호 세액 × 납부기한 다음 날부터 자진납부일 또는 납세고지일(부과결정일)까지 × 이자율
    2024.1.1.~: 50% 한도(1호·2호 합계 10%), 3호 납세고지서 납부기한이 지난 날부터 1개월이 지날 때마다 × 이자율(60개월 한도), 제2항 45만원 미만은 3호 제외
    2025.1.1.~: 2호의2 납세고지서 납부기한까지 내지 않은 세액 × 1만분의 66
  법률 제17768호 부칙 제1조제5호·제6조(2024.1.1. 전 납세의무 성립분은 종전), 법률 제20629호 부칙 제1조·제3조, 제34조제2항제1호(원천징수하는 때 성립)
  지방세기본법 시행령 제33조(2016.1.1.·2017.1.20. 시행본)·제34조(2017.3.28.·2018.1.1.·2019.1.1.·2022.6.6.·2022.6.7.·2023.6.1.·2024.3.26.·2026.10.2. 시행본)
    1일 1만분의 3 → 2019.1.1. 10만분의 25(대통령령 제29436호 부칙 제2조: 시행 전 사유 발생분은 종전 규정)
    → 2022.6.7. 10만분의 22(대통령령 제32665호 부칙 제2조: 시행일 전 기간분 종전, 이후 기간분 개정) / 제2항 월 1만분의 66(2024.1.1. 시행)
  끝수: 지방세기본법 제59조(2016년 시행본 제75조) — 국고금 관리법 제47조 준용
"""
import asyncio
import json

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.forms_workbook import export_form_inputs
from korean_tax_calc_mcp.server import mcp
from tests._helpers import call as c

M = 1_000_000
T = "withholding_late_payment_penalty"


def loc(**a):
    return c(T, {**a, "tax": "local"})


def text(r):
    return json.dumps(r, ensure_ascii=False)


# ── 종전 규정(2023.12.31.까지 원천징수분): 3% + 일수분, 10% 한도 ─────────────────────────

def test_2016_rate():
    # 2016.5.11.~6.9. 30일 × 1만분의 3: 1,000,000 × 30 × 0.0003 = 9,000, 3% 30,000 → 39,000
    r = loc(unpaid_tax=1 * M, due="2016-05-10", until="2016-06-09")
    assert r["결과"]["일수"] == 30
    assert (r["결과"]["3%분"], r["결과"]["일수분"], r["결과"]["가산세"]) == (30_000, 9_000, 39_000)
    assert r["결과"]["세목"] == "지방소득세 특별징수분"
    assert "제53조의5" in r["근거"] and "제17768호 부칙" in r["근거"]


def test_cause_before_2019_keeps_old_rate_for_whole_period():
    # 납부기한 2018.11.12., 납부 2019.3.12. — 11.13.~3.12. = 18 + 31 + 31 + 28 + 12 = 120일.
    # 대통령령 제29436호 부칙 제2조: 시행(2019.1.1.) 전에 사유가 발생했으므로 전 기간 1만분의 3 → 1,000,000 × 120 × 0.0003 = 36,000, + 30,000 = 66,000
    r = loc(unpaid_tax=1 * M, due="2018-11-12", until="2019-03-12")
    assert r["결과"]["일수"] == 120 and r["결과"]["일수분"] == 36_000 and r["결과"]["가산세"] == 66_000
    assert len(r["결과"]["기간별_이율"]) == 1 and r["결과"]["기간별_이율"][0]["이율"] == "1일 1만분의 3"
    assert "제29436호 부칙 제2조" in text(r)
    # 국세는 2019.2.12.에 기간을 나눈다(91일 × 0.0003 + 29일 × 0.00025 = 27,300 + 7,250 = 34,550 → 64,550) — 지방세와 다름
    assert c(T, dict(unpaid_tax=1 * M, due="2018-11-12", until="2019-03-12"))["결과"]["가산세"] == 64_550


def test_cause_from_2019_uses_new_rate():
    # 납부기한 2019.1.10., 납부 2019.2.9. — 30일 × 10만분의 25 = 7,500, + 30,000 = 37,500 (국세는 2019.2.11.까지 1만분의 3이라 39,000)
    r = loc(unpaid_tax=1 * M, due="2019-01-10", until="2019-02-09")
    assert r["결과"]["가산세"] == 37_500 and r["결과"]["기간별_이율"][0]["이율"] == "1일 10만분의 25"
    assert c(T, dict(unpaid_tax=1 * M, due="2019-01-10", until="2019-02-09"))["결과"]["가산세"] == 39_000


def test_2018_year_end_boundary():
    # 납부기한 2018.12.28.(시행 전 경과) → 30일 × 1만분의 3 = 9,000 → 39,000
    assert loc(unpaid_tax=1 * M, due="2018-12-28", until="2019-01-27")["결과"]["가산세"] == 39_000
    # 납부기한 2018.12.31. — 기한이 지나는 때가 2019.1.1. → 10만분의 25로 계산하고 주의에 밝힘: 30일 × 0.00025 = 7,500 → 37,500
    r = loc(unpaid_tax=1 * M, due="2018-12-31", until="2019-01-30")
    assert r["결과"]["가산세"] == 37_500
    assert "2018.12.31." in text(r["주의"]) and "확인하지 못함" in text(r["주의"])


def test_2022_rate_change_is_split_by_period():
    # 납부기한 2022.5.10., 납부 2022.7.9. — 5.11.~6.6. 27일 × 10만분의 25, 6.7.~7.9. 33일 × 10만분의 22 (부칙 제2조 기간 안분)
    # 2,000,000 × 27 × 0.00025 = 13,500 / 2,000,000 × 33 × 0.00022 = 14,520 → 일수분 28,020, 3% 60,000 → 88,020
    r = loc(unpaid_tax=2 * M, due="2022-05-10", until="2022-07-09")
    seg = r["결과"]["기간별_이율"]
    assert [(s["기간"], s["일수"], s["이율"]) for s in seg] == [("2022-05-11~2022-06-06", 27, "1일 10만분의 25"), ("2022-06-07~2022-07-09", 33, "1일 10만분의 22")]
    assert r["결과"]["일수분"] == 28_020 and r["결과"]["가산세"] == 88_020
    assert "제32665호 부칙 제2조" in text(r)
    assert "27일" in r["산식"] and "33일" in r["산식"]


def test_2022_boundary_days():
    # 2022.6.6. 하루: 1,000,000 × 0.00025 = 250 → 30,250 / 2022.6.7. 하루: 1,000,000 × 0.00022 = 220 → 30,220
    assert loc(unpaid_tax=1 * M, due="2022-06-05", until="2022-06-06")["결과"]["가산세"] == 30_250
    assert loc(unpaid_tax=1 * M, due="2022-06-06", until="2022-06-07")["결과"]["가산세"] == 30_220


def test_old_rule_cap_10_percent_and_no_50_cap():
    # 2020.3.11.~2021.3.10. 365일 × 0.00025 = 9.125% + 3% > 10% → 100,000
    r = loc(unpaid_tax=1 * M, due="2020-03-10", until="2021-03-10")["결과"]
    assert r["가산세"] == 100_000 and r["한도_적용"] is True and r["한도_10%"] == 100_000
    assert r["한도_50%"] is None and r["50%한도_적용"] is False


def test_old_rule_after_notice_not_calculated():
    # 2023.3.11.~5.9. = 21 + 30 + 9 = 60일 × 0.00022 × 1,000,000 = 13,200, + 30,000 = 43,200. 고지 후분은 지방세징수법 가산금 — 계산 안 함
    r = loc(unpaid_tax=1 * M, due="2023-03-10", until="2023-05-09", notice_due="2023-05-31", paid_on="2023-09-15")
    assert r["결과"]["가산세"] == 43_200 and r["결과"]["고지후분"] == 0
    assert "가산금" in text(r["주의"]) and "계산하지 않음" in text(r["주의"])


def test_rounding_floor_of_sum():
    # 333,333원, 2023.3.11.~4.9. 30일: 3% = 9,999.99, 일수분 333,333 × 30 × 0.00022 = 2,199.9978 → 합 12,199.9878 → 12,199(각각 버린 9,999 + 2,199 = 12,198이 아님)
    r = loc(unpaid_tax=333_333, due="2023-03-10", until="2023-04-09")["결과"]
    assert (r["3%분"], r["일수분"], r["가산세"]) == (9_999, 2_199, 12_199)
    # 1,234,567원: 3% = 37,037.01, 일수분 8,148.1422 → 45,185.1522 → 45,185
    assert loc(unpaid_tax=1_234_567, due="2023-03-10", until="2023-04-09")["결과"]["가산세"] == 45_185
    assert "제59조" in r["끝수"] and "국고금 관리법 제47조" in r["끝수"]


# ── 2024.1.1. 전후 가름(법률 제17768호 부칙 제6조 — 원천징수한 날) ─────────────────────────

def test_accrual_date_picks_rule():
    # 납부기한 2024.1.10.(성립일 미입력) → 2023년 원천징수분으로 보고 종전, 주의에 밝힘
    r = loc(unpaid_tax=1 * M, due="2024-01-10", until="2024-02-09")
    assert r["결과"]["적용_규정"]["고지 전"].startswith("종전") and r["결과"]["한도_50%"] is None
    assert "accrued_on" in text(r["주의"])
    # 원천징수한 날을 넣으면 그 날로 가름
    old = loc(unpaid_tax=1 * M, due="2024-02-13", until="2024-03-14", accrued_on="2023-12-29")
    new = loc(unpaid_tax=1 * M, due="2024-02-13", until="2024-03-14", accrued_on="2024-01-25")
    assert old["결과"]["적용_규정"]["고지 전"].startswith("종전") and new["결과"]["적용_규정"]["고지 전"].startswith("개정")
    # 고지 전 금액은 같다: 2.14.~3.14. = 16 + 14 = 30일 × 0.00022 = 6,600 → 36,600
    assert old["결과"]["가산세"] == new["결과"]["가산세"] == 36_600
    assert new["결과"]["한도_50%"] == 500_000


# ── 개정 규정(2024.1.1. 이후 원천징수분) ───────────────────────────────────────────

def test_new_rule_self_payment():
    # 2025.3.11.~4.9. 30일(납부일 포함) × 0.00022 × 1,000,000 = 6,600, + 30,000 = 36,600
    r = loc(unpaid_tax=1 * M, due="2025-03-10", until="2025-04-09")
    assert r["결과"]["일수"] == 30 and r["결과"]["가산세"] == 36_600
    assert "지방세기본법 제56조제1항" in r["근거"] and "시행령 제34조" in r["근거"]
    assert "호출_id" in r


def test_new_rule_after_notice():
    # 납부기한 2025.3.10., 납세고지 2025.5.9.(3.11.~5.9. = 21 + 30 + 9 = 60일, 고지일 포함), 고지서 납부기한 2025.5.31., 납부 2025.8.15.
    # 1호 60,000 + 2호 2,000,000 × 60 × 0.00022 = 26,400 (합 86,400 ≤ 10% 200,000)
    # 2호의2 2,000,000 × 0.0066 = 13,200 / 3호 6.1.부터 6.30.·7.31.에 1개월씩 경과(8.15.까지 2개월) × 13,200 = 26,400 → 126,000
    r = loc(unpaid_tax=2 * M, due="2025-03-10", until="2025-05-09", notice_due="2025-05-31", paid_on="2025-08-15")["결과"]
    assert (r["3%분"], r["일수분"], r["2호의2분"], r["3호분"], r["경과_개월"]) == (60_000, 26_400, 13_200, 26_400, 2)
    assert r["고지후분"] == 39_600 and r["가산세"] == 126_000 and r["한도_50%"] == 1_000_000


def test_month_boundary():
    # 고지서 납부기한 2025.5.31. — 첫 1개월은 6.30.이 끝나야 지남: 6.30. 납부 0개월, 7.1. 납부 1개월
    a = dict(unpaid_tax=2 * M, due="2025-03-10", until="2025-05-09", notice_due="2025-05-31")
    r0 = loc(**a, paid_on="2025-06-30")["결과"]
    r1 = loc(**a, paid_on="2025-07-01")["결과"]
    assert (r0["경과_개월"], r0["가산세"]) == (0, 86_400 + 13_200)
    assert (r1["경과_개월"], r1["가산세"]) == (1, 86_400 + 13_200 + 13_200)
    # 고지서 납부기한 안에 내면 고지 후분 없음
    assert loc(**a, paid_on="2025-05-31")["결과"]["가산세"] == 86_400


def test_item_2_2_only_when_notice_due_from_2025():
    # 납부기한 2024.3.11., 고지 2024.5.10.(3.12.~5.10. = 20 + 30 + 10 = 60일), 고지서 납부기한 2024.5.31., 납부 2024.8.15.
    # 2호의2는 2025.1.1. 시행 — 없음. 60,000 + 26,400 + 3호 2개월 26,400 = 112,800. 넣어 본 금액(13,200)은 주의에
    r = loc(unpaid_tax=2 * M, due="2024-03-11", until="2024-05-10", notice_due="2024-05-31", paid_on="2024-08-15")
    assert r["결과"]["2호의2분"] == 0 and r["결과"]["3호분"] == 26_400 and r["결과"]["가산세"] == 112_800
    assert "13,200" in text(r["주의"]) and "제20629호 부칙 제3조" in text(r["주의"])


def test_small_notice_excludes_item_3_only():
    # 400,000원: 1호 12,000 + 2호 400,000 × 60 × 0.00022 = 5,280 → 17,280. 납세고지서 세액 417,280 < 45만원 → 3호 없음, 2호의2 2,640은 있음 → 19,920
    a = dict(unpaid_tax=400_000, due="2025-03-10", until="2025-05-09", notice_due="2025-05-31", paid_on="2025-08-15")
    r = loc(**a)
    assert r["결과"]["3호분"] == 0 and r["결과"]["2호의2분"] == 2_640 and r["결과"]["가산세"] == 19_920
    assert "45만원" in text(r["판단"])
    # 납세고지서별·세목별 세액이 45만원이면 3호 적용: 2개월 × 2,640 = 5,280 → 25,200
    assert loc(**a, notice_amount=450_000)["결과"]["가산세"] == 25_200
    assert loc(**a, notice_amount=449_999)["결과"]["가산세"] == 19_920


def test_60_months_and_50_percent_cap():
    # 납부기한 2024.3.11., 고지 2025.3.11.(365일 × 0.00022 = 8.03% + 3% > 10% → 100,000), 고지서 납부기한 2025.3.31.
    a = dict(unpaid_tax=1 * M, due="2024-03-11", until="2025-03-11", notice_due="2025-03-31")
    # 2030.3.31. 납부: 4.1. 기산, 60번째 달은 2030.3.31.이 끝나야 지남 → 59개월 × 6,600 = 389,400, + 2호의2 6,600 + 100,000 = 496,000
    r59 = loc(**a, paid_on="2030-03-31")["결과"]
    assert (r59["경과_개월"], r59["가산세"], r59["50%한도_적용"]) == (59, 496_000, False)
    # 2031.1.15. 납부: 60개월 한도 → 396,000 + 6,600 + 100,000 = 502,600 → 50% 한도 500,000
    r60 = loc(**a, paid_on="2031-01-15")["결과"]
    assert (r60["경과_개월"], r60["3호분"], r60["가산세"], r60["50%한도_적용"]) == (60, 396_000, 500_000, True)


def test_paid_on_due_date_is_zero():
    r = loc(unpaid_tax=1 * M, due="2025-03-10", until="2025-03-10")
    assert r["결과"]["가산세"] == 0 and r["결과"]["세목"] == "지방소득세 특별징수분"


# ── 기본값은 종전과 같음 / 모르는 값 거부 ──────────────────────────────────────────

CASES = [dict(unpaid_tax=5 * M, due="2025-07-10", until="2025-08-09"),
         dict(unpaid_tax=1 * M, due="2026-06-10", until="2026-07-20"),
         dict(unpaid_tax=10 * M, due="2026-03-10", until="2026-07-01", notice_due="2026-07-31", paid_on="2026-10-15"),
         dict(unpaid_tax=987_650, due="2022-01-10", until="2022-03-31"),
         dict(unpaid_tax=1 * M, due="2019-03-11", until="2019-06-10", accrued_on="2019-02-25")]


def _strip(r):
    return {k: v for k, v in r.items() if k not in ("호출_id", "엑셀", "안내")}


@pytest.mark.parametrize("a", CASES)
def test_default_equals_national(a):
    base = _strip(c(T, a))
    assert "error" not in base
    assert _strip(c(T, {**a, "tax": "national"})) == base
    assert "세목" not in base["결과"] and "기간별_이율" not in base["결과"] and "지방세" not in text(base)


def test_default_values_from_statute():
    # 국세(국세기본법 제47조의5): 5,000,000 × 3% = 150,000 + 5,000,000 × 30일 × 0.00022 = 33,000 → 183,000
    assert c(T, CASES[0])["결과"]["가산세"] == 183_000
    # 2026.7.1. 이후 납부 — 납부일 전날까지 39일: 30,000 + 1,000,000 × 39 × 0.00022 = 8,580 → 38,580
    assert c(T, CASES[1])["결과"]["가산세"] == 38_580
    # 같은 입력의 지방세분은 납부일까지 40일: 30,000 + 8,800 = 38,800 (국세 금액의 10%가 아님)
    assert loc(**CASES[1])["결과"]["가산세"] == 38_800


def test_schema_default_and_enum():
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == T)
    schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema")
    p = schema["properties"]["tax"]
    assert p["default"] == "national" and p["enum"] == ["national", "local"]
    assert "tax" not in schema.get("required", [])
    assert tool.description.splitlines()[0].startswith("Withholding tax late payment penalty")
    assert "→ tax" in tool.description


def test_unknown_tax_rejected():
    with pytest.raises(Exception):
        c(T, dict(unpaid_tax=1 * M, due="2025-03-10", until="2025-04-09", tax="county"))
    r = S.withholding_late_payment_penalty(unpaid_tax=1 * M, due="2025-03-10", until="2025-04-09", tax="county")
    assert "error" in r and "결과" not in r and "national" in text(r)


def test_local_input_errors():
    # 2016.1.1. 전 — 시행본을 확인하지 못해 계산하지 않음
    r = loc(unpaid_tax=1 * M, due="2015-12-10", until="2016-01-09")
    assert "error" in r and "결과" not in r and "확인하지 못함" in text(r)
    # 독촉비용은 국세에만
    r = loc(unpaid_tax=2 * M, due="2025-03-10", until="2025-05-09", notice_due="2025-05-31", paid_on="2025-08-15", dunning_fee=3_000)
    assert "error" in r and "dunning_fee" in text(r)
    assert "error" in loc(unpaid_tax=1 * M, due="2025-03-10", until="2025-03-09")
    assert "error" in loc(unpaid_tax=1 * M, due="2025-03-10", until="2025-05-09", notice_due="2025-05-31")


# ── 다른 곳과 이어지는 자리 ──────────────────────────────────────────────────

def test_export_does_not_attach_national_formula():
    a = dict(unpaid_tax=1 * M, due="2025-03-10", until="2025-04-09", tax="local")
    data = c(T, a)
    assert export_form_inputs(T, a, data) is data and "계산식" not in data
    nat = {k: v for k, v in a.items() if k != "tax"}
    assert export_form_inputs(T, nat, c(T, nat)).get("계산식")


def test_pointer_from_nonresident_withholding():
    r = c("nonresident_withholding", dict(amount=10 * M, income_kind="사용료", residence_country="미국", recipient_type="법인"))
    assert "withholding_late_payment_penalty" in text(r) and "tax='local'" in text(r)


def test_blend_sheet_copies_tool_values_for_local():
    # 통합 문서 틀: 지방세분은 국세용 수식 틀(국세 이율·근거)을 쓰지 않고 도구 값을 옮긴다
    from korean_tax_calc_mcp import workbook_blend as WB
    a = dict(unpaid_tax=1 * M, due="2025-03-10", until="2025-04-09", tax="local")
    sp = WB._spec(T, a, c(T, a), lambda k: k)
    assert sp.get("plain") is True
    row = next(r for r in sp["rows"] if r["ko"] == "가산세")
    assert row["value"] == 36_600 and row["f"] is None
