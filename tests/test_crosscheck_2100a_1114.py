"""원문 대조 2100-A·B 반영(2026-11-14, Claude). 정답은 아래 시행본 문언에서 손으로 계산.

대조한 시행본
- 소득세법 시행규칙 제67조: 2016.3.16. 시행본(MST 181793)·2020.1.1. 시행본(MST 212941) "3.2(간편장부대상자 2.6)",
  기획재정부령 제781호(2020.3.13. 공포·시행, MST 215577) "3.4(간편장부대상자 2.8)", 부칙 제2조(시행일이 속하는 과세기간 발생 소득분부터)·
  제9조(그 전 과세기간 발생 소득분은 종전).
- 소득세법 시행규칙 별지 제21호서식: 2026.1.1. 시행본(MST 282409) <개정 2025. 3. 21.>, 재정경제부령 제22호(2026.3.20., MST 284987)
  <개정 2026. 3. 20.> 작성방법 3.다2) "징수세액(⑥~⑧)의 가감계(A30) = (A25 + A28)", 부칙 제2조(시행 이후 신고·제출하는 경우부터).
- 법인세법 시행령 2025.2.28. 시행본(대통령령 제35350호): 제24조①2호차목, 제26조①9호(신고 내용연수 경과월수 비례)·④6호(무신고 5년 균등),
  부칙 제6조(시행일이 속하는 사업연도에 감가상각하는 경우부터).
- 조세특례제한법 제104조의27(2026.9.18. 시행본, MST 284389) 제2항 세율표, 법률 제21223호 부칙 제23조(2026.1.1. 이후 받는 배당).
- 상증령 제54조④ — 대통령령 제28638호 부칙 제8조(기획재정부 재산세제과-955: 평가기준일 도래 기준).
"""
from korean_tax_calc_mcp import server as S
from tests._helpers import call

M = 1_000_000


def _fn(t):
    return getattr(t, "fn", t)


# ── 1. 추계 배율: 2019 과세기간까지 2.6/3.2, 2020부터 2.8/3.4 ──
# 기준경비율 소득이 한도보다 크게: 수입 1억, 기준경비율 10%(복식 5%), 단순경비율 90% → 단순경비율 소득 1,000만
_E = {"industry_group": "나", "revenues": [{"구분": "매출", "금액": 100 * M}], "expenses": [], "base_rate": 0.1, "simple_rate": 0.9}


def test_estimated_multiplier_boundary():
    # 간편(직전 4,000만 < 1억5천만): 기준경비율 소득 9,000만 > 한도
    assert call("estimated_business_income", {**_E, "year": 2019, "prior_year_revenue": 40 * M})["결과"]["사업소득금액"] == 26 * M
    assert call("estimated_business_income", {**_E, "year": 2020, "prior_year_revenue": 40 * M})["결과"]["사업소득금액"] == 28 * M
    # 복식(직전 2억): 1억 − 1억×5% = 9,500만 > 한도
    assert call("estimated_business_income", {**_E, "year": 2019, "prior_year_revenue": 200 * M})["결과"]["사업소득금액"] == 32 * M
    assert call("estimated_business_income", {**_E, "year": 2020, "prior_year_revenue": 200 * M})["결과"]["사업소득금액"] == 34 * M


# ── 2. 원천징수이행상황신고서: 신고일로 서식 선택 ──
_L = [{"코드": "A25", "인원": 2, "총지급액": 5 * M, "소득세": 200_000},
      {"코드": "A26", "인원": 3, "총지급액": 40 * M, "소득세": 1_000_000}]
_INST = [{"코드": "A27", "인원": 3, "총지급액": 0, "소득세": 600_000}, {"코드": "A28", "인원": 3, "총지급액": 0, "소득세": 400_000}]


def test_withholding_new_form_a30():
    f = _fn(S.withholding_return)
    r = f(year=2026, month=3, paid_month=3, lines=_L + _INST, filed_on="2026-04-10")
    a30 = r["계산"]["행"]["A30"]
    assert a30["소득세"] == 600_000                       # A25 + A28 = 200,000 + 400,000
    assert a30["인원"] == 5 and a30["총지급액"] == 45 * M  # A25 + A26
    assert r["결과"]["적용서식"] == "<개정 2026. 3. 20.>"
    assert list(r["계산"]["행"]).index("A30") == list(r["계산"]["행"]).index("A28") + 1


def test_withholding_old_form_by_filing_date():
    f = _fn(S.withholding_return)
    old = f(year=2026, month=2, lines=_L, filed_on="2026-03-10")          # 2026 귀속이라도 3.20. 전 신고는 종전 서식
    assert old["계산"]["행"]["A30"]["소득세"] == 1_200_000                 # 옛 식 A25 + A26
    assert old["결과"]["적용서식"] == "<개정 2025. 3. 21.>"
    assert "A27" in f(year=2026, month=2, lines=_L + _INST, filed_on="2026-03-10")["문제"][0]
    # 2025 귀속 수정신고라도 3.20. 이후 신고면 개정 서식
    assert f(year=2025, month=12, lines=_L + _INST, filed_on="2026-04-01")["계산"]["행"]["A30"]["소득세"] == 600_000


def test_withholding_no_filing_date_keeps_old_with_note():
    f = _fn(S.withholding_return)
    r = f(year=2025, month=5, lines=_L)
    assert r["계산"]["행"]["A30"]["소득세"] == 1_200_000
    assert any("신고·제출일" in n and "filed_on" in n for n in r["주의"])
    assert "error" in f(year=2025, month=5, lines=_L + _INST)
    assert "error" in f(year=2025, month=5, lines=_L, filed_on="2025-03-01")   # 2025.3.21. 전 서식은 범위 밖


# ── 3. 감가상각 기타 무형자산(영 제24조①2호차목) ──
_D = {"year": 2025, "acquisition_cost": 100 * M, "accumulated_dep_begin": 0, "asset_class": "기타무형자산"}


def test_other_intangible_amortization():
    r = call("depreciation_adjustment", {**_D, "method": "무신고", "booked_depreciation": 20 * M})
    assert r["결과"]["상각범위액"] == 20 * M                                # 1억 ÷ 5
    r = call("depreciation_adjustment", {**_D, "method": "정액법", "useful_life": 4, "booked_depreciation": 25 * M})
    assert r["결과"]["상각범위액"] == 25 * M and r["결과"]["상각부인액"] == 0   # 1억 × 12/48
    r = call("depreciation_adjustment", {**_D, "method": "정액법", "useful_life": 4, "booked_depreciation": 25 * M, "in_service_date": "2025-07-01"})
    assert r["결과"]["상각범위액"] == 12_500_000 and r["결과"]["상각부인액"] == 12_500_000   # 6/48


def test_other_intangible_effective_fiscal_year():
    # 2025.2.28.이 속하는 사업연도(2024.3.1.~2025.2.28.)는 적용
    r = call("depreciation_adjustment", {**_D, "year": 2024, "fy_start": "2024-03-01", "fy_end": "2025-02-28", "method": "무신고", "booked_depreciation": 20 * M})
    assert r["결과"]["상각범위액"] == 20 * M
    # 2024.1.1.~12.31.은 차목 없음 — 범위 밖
    r = call("depreciation_adjustment", {**_D, "year": 2024, "method": "무신고", "booked_depreciation": 20 * M})
    assert "error" in r and "부칙 제6조" in r["문제"][0]
    # 무신고 사업연도 중 사용개시분의 월할은 원문으로 확정하지 못함 — 계산하지 않음
    assert "error" in call("depreciation_adjustment", {**_D, "method": "무신고", "booked_depreciation": 0, "in_service_date": "2025-07-01"})
    assert "error" in call("depreciation_adjustment", {**_D, "method": "정률법", "useful_life": 4, "booked_depreciation": 0})


# ── 4. 조특법 제104조의27 고배당기업 배당 분리과세 ──
def _hd(amount, paid="2026-04-10", **kw):
    return S.financial_income_aggregate(2026, [{"kind": "고배당기업배당", "amount": amount, "paid_date": paid, "separate_election": True}] + kw.get("more", []))


def test_high_dividend_separate_tax_table():
    for amt, tax in ((20 * M, 2_800_000), (30 * M, 4_800_000), (300 * M, 58_800_000), (400 * M, 83_800_000),
                     (5_000 * M, 1_233_800_000), (6_000 * M, 1_533_800_000)):
        r = _hd(amt)
        assert r["결과"]["특례배당_산출세액"] == tax, amt
        assert r["결과"]["합산액"] == 0 and r["결과"]["Gross-up"] == 0       # 종합소득과세표준·Gross-up에서 제외


def test_high_dividend_threshold_interpretation_shown():
    # 이자 1,000만 + 상장배당 1,500만 + 특례 3,000만
    r = _hd(30 * M, more=[{"kind": "상장법인현금배당", "amount": 15 * M}, {"kind": "예금이자", "amount": 10 * M}])
    assert r["결과"]["Gross-up"] == 500_000 and r["결과"]["합산액"] == 25_500_000    # 특례 제외: (2,500만 − 2,000만) × 10%
    assert r["결과"]["기준금액_포함시"] == {"분리과세": False, "Gross-up": 1_500_000, "합산액": 26_500_000}   # 포함: 1,500만 전부 × 10%
    assert any("해석 미확인" in n for n in r["주의"])


def test_high_dividend_not_before_2026():
    r = S.financial_income_aggregate(2025, [{"kind": "고배당기업배당", "amount": 30 * M, "paid_date": "2025-12-31", "separate_election": True}])
    assert "error" in r and "특례배당_산출세액" not in str(r)
    assert _hd(30 * M, paid="2026-01-01")["결과"]["특례배당_산출세액"] == 4_800_000


# ── B-1. 기한후·수정신고 구간이 갈리면 신고기한 기준 결과를 함께 ──
def test_late_filing_shows_both():
    base = {"year": 2024, "sme": True, "general_revenue": 5_000 * M, "expensed": 80 * M, "market": 20 * M, "fy_end": "2024-12-31"}
    r = call("entertainment_limit", {**base, "filing_date": "2026-02-10"})     # 신고기한 2025.3.31.(10%) → 수정신고 2026.2.(20%)
    assert r["해석_미확인_신고기한기준"]["전통시장등_비율"] == 0.1 and any("해석 미확인" in n for n in r["주의"])
    assert r["해석_미확인_신고기한기준"]["한도"] < r["결과"]["한도"]
    assert "해석_미확인_신고기한기준" not in call("entertainment_limit", {**base, "filing_date": "2025-03-20"})
