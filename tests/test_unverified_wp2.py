"""원문 대조로 닫은 항목의 정답 테스트(2026-11-15, Claude 작성). 외부 호출 없음. 손 계산 값.

대조한 시행본·부칙(법제처, 2026-11-15 조회):
  소득세법 시행령 제122조의2 2020.8.28.·2020.10.7. 시행본, 대통령령 제31083호 부칙 전문
  소득세법 시행규칙 제23조제1항 2016.3.16.~2025.3.21. 개정본 9개와 2026.7.1. 시행본, 각 부칙
  소득세법 제48조·제55조 2015.7.1. 시행본, 제55조제2항 2012.8.2. 시행본, 법률 제12852호 부칙 제25조, 법률 제11611호 부칙 제22조,
    시행규칙 별지 제24호서식(2) <개정 2016.3.16.> 작성방법
  소득세법 제118조의9~제118조의18 2026.7.1. 시행본·2027.1.1. 시행 예정본(법률 제21221호 부칙 제1조제2호·제8조),
    시행령 제178조의8~제178조의12 2027.1.1. 시행 예정본(대통령령 제36129호), 제102조제2항·시행령 제167조의2제1항(2019.12.31.·2027.1.1.)
  소득세법 시행규칙 별지 제21호서식 제1쪽·작성방법 — 2016.1.1.~2025.3.21. 시행본 17개
  국고금 관리법 제47조 2011.10.5.·2026.1.2. 시행본
  국세기본법 부칙 제16097호 제11조·제21212호 제1조~제4조, 지방세법 제103조의18·제103조의52 2016.9.1.·2026.7.1. 시행본
"""
import json
from pathlib import Path

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import calc_branch_exit as BX
from korean_tax_calc_mcp.engine import calc_vat as V
from korean_tax_calc_mcp.engine import calc_withholding_return as WR

M = 1_000_000


def _fn(t):
    return getattr(t, "fn", t)


# ── 정기예금이자율(소득세법 시행규칙 제23조제1항) ──────────────────────────────
def test_income_rule_deposit_rate_table():
    assert S.주택간주임대료_이자율 == {2016: 0.018, 2017: 0.016, 2018: 0.018, 2019: 0.021, 2020: 0.018, 2021: 0.012, 2022: 0.012,
                                2023: 0.029, 2024: 0.035, 2025: 0.031, 2026: 0.031}
    assert S.주택간주임대료_이자율 == V.DEEMED_RENT_RATE          # 부가가치세법 시행규칙 제47조 표와 같은 값(따로 대조)


# ── 퇴직소득세 2016~2019 특례 ───────────────────────────────────────────────
def test_retirement_transition_ratio_by_year():
    f = _fn(S.retirement_income_tax)
    a = dict(income=100 * M, years_of_service=10)
    # 종전: 1억 − 40% 4,000만 − 근속연수공제 400만 = 5,600만 → ÷10 × 5 = 2,800만 → 72만 + 1,600만 × 15% = 312만 → ÷5 × 10 = 6,240,000
    # 개정: (1억 − 400만) ÷ 10 × 12 = 1억1,520만 − 환산급여공제 6,854만 = 4,666만 → 582만 + 66만 × 24% = 5,978,400 → ÷12 × 10 = 4,982,000
    want = {2016: 5_988_400, 2017: 5_736_800, 2018: 5_485_200, 2019: 5_233_600}     # 80:20, 60:40, 40:60, 20:80
    for y, w in want.items():
        r = f(retire_year=y, **a)
        assert r["결과"]["퇴직소득세"] == w, (y, r["결과"]["퇴직소득세"])
        assert r["결과"]["종전규정_산출세액"] == 6_240_000 and r["결과"]["개정규정_산출세액"] == 4_982_000
    assert f(retire_year=2020, **a)["결과"]["퇴직소득세"] == 4_982_000              # 2020년 퇴직부터 개정규정만


def test_retirement_transition_pre_2013_service():
    f = _fn(S.retirement_income_tax)
    # 2012.12.31. 이전 4년: 연평균과세표준 560만 × 6% × 4 = 1,344,000 / 2013 이후 6년: 624,000 × 6 = 3,744,000 → 종전 5,088,000
    r = f(income=100 * M, years_of_service=10, retire_year=2019, years_before_2013=4)
    assert r["결과"]["종전규정"]["산출세액_2012이전분"] == 1_344_000 and r["결과"]["종전규정"]["산출세액_2013이후분"] == 3_744_000
    assert r["결과"]["퇴직소득세"] == 5_003_200                                     # 5,088,000 × 20% + 4,982,000 × 80%
    assert "error" in f(income=100 * M, years_of_service=10, retire_year=2019, years_before_2013=11)


# ── 국외전출세 ─────────────────────────────────────────────────────────────
def _ex(d, holdings, **kw):
    return BX.emigration_exit_tax(d, 10, True, holdings, **kw)


def test_exit_2019_loss_offsets_other_rate_group():
    # 그 밖의 주식등 +4억, 중소기업 주식등 −1억 → 차손을 다른 세율 주식등에서 공제(제102조제2항, 영 제167조의2제1항제2호): (3억 − 250만) × 20% = 59,500,000
    r = _ex("2019-06-01", [{"market_value": 500 * M, "acquisition_cost": 100 * M}, {"market_value": 100 * M, "acquisition_cost": 200 * M, "sme": True}])
    assert r["결과"]["과세표준"] == 297_500_000 and r["결과"]["산출세액"] == 59_500_000


def test_exit_2019_mixed_deduction_order_range():
    # 그 밖 5억, 중소 1억. 250만원을 그 밖에서 먼저: 6천만 + 1.975억 × 25% + 1억 × 20% = 129,375,000 / 중소에서 먼저: 1.1억 + 9,750만 × 20% = 129,500,000
    r = _ex("2019-06-01", [{"market_value": 500 * M, "acquisition_cost": 0}, {"market_value": 100 * M, "acquisition_cost": 0, "sme": True}])
    assert r["결과"]["산출세액"] == 129_375_000
    assert r["결과"]["기본공제 순서에 따른 산출세액 범위"] == {"최소": 129_375_000, "최대": 129_500_000}
    assert any("근거 없음" in x and "서면질의" in x for x in r["한계"])
    # 2020년 출국분은 한 세율 — 범위 없음
    r20 = _ex("2020-06-01", [{"market_value": 500 * M, "acquisition_cost": 0}, {"market_value": 100 * M, "acquisition_cost": 0, "sme": True}])
    assert "기본공제 순서에 따른 산출세액 범위" not in r20["결과"] and r20["결과"]["산출세액"] == 60 * M + (597_500_000 - 300 * M) * 25 // 100


def test_exit_2027_foreign_shares():
    dom = {"name": "국내", "market_value": 400 * M, "acquisition_cost": 0}
    fo = {"name": "국외", "market_value": 600 * M, "acquisition_cost": 100 * M, "foreign": True}
    # 2026.12.31. 출국: 국외주식등은 대상 아님 → (4억 − 250만): 6천만 + 9,750만 × 25% = 84,375,000
    r26 = _ex("2026-12-31", [dom, fo])
    assert r26["결과"]["산출세액"] == 84_375_000 and any("2027.1.1." in x for x in r26["주의"])
    # 2027.1.1. 출국: 국외 그 밖의 주식등 5억 × 20% = 1억을 더함 → 184,375,000 (250만원을 국외 쪽에서 빼면 8,500만 + 9,950만 = 184,500,000)
    r27 = _ex("2027-01-01", [dom, fo])
    assert r27["결과"]["산출세액"] == 184_375_000
    assert r27["결과"]["기본공제 순서에 따른 산출세액 범위"] == {"최소": 184_375_000, "최대": 184_500_000}
    # 국외 중소기업 주식등은 10%: 84,375,000 + 5억 × 10%
    assert _ex("2027-01-01", [dom, {**fo, "sme": True}])["결과"]["산출세액"] == 134_375_000
    # 양도가액 합계 5억원 이하인 국외주식등은 제외(시행령 제178조의8제2항제1호) — 5억은 제외, 5억 1원은 포함
    at = _ex("2027-01-01", [dom, {"market_value": 500 * M, "acquisition_cost": 0, "foreign": True}])
    assert at["결과"]["산출세액"] == 84_375_000
    over = _ex("2027-01-01", [dom, {"market_value": 500 * M + 1, "acquisition_cost": 0, "foreign": True}])
    assert over["결과"]["산출세액"] == 84_375_000 + (500 * M + 1) * 20 // 100
    # 외국인근로자 소유 국외주식등 제외(같은 항 제2호·제3호, 입력값)
    assert _ex("2027-01-01", [dom, fo], foreign_worker_exempt=True)["결과"]["산출세액"] == 84_375_000


def test_rounding_treasury_act():
    # 과세표준 123원 × 20% = 24.6 → 24원, 납부할 때 10원 미만 버림 → 20원(국고금 관리법 제47조제1항)
    r = _ex("2023-05-01", [{"market_value": 2_500_123, "acquisition_cost": 0}])
    assert r["결과"]["산출세액"] == 24 and r["결과"]["납부할 금액(10원 미만 버림)"] == 20
    assert BX.pay_amount(9) == 0 and BX.pay_amount(10) == 10 and BX.pay_amount(35_925_009) == 35_925_000
    b = S.branch_profits_tax(2025, pe_income=1000 * M, corporate_tax=170 * M, credits_reductions=10 * M, penalties_additional=5 * M,
                             local_income_tax=16_500_000, capital_begin=2000 * M, capital_end=2100 * M, treaty_allows_branch_tax=True, treaty_branch_rate=0.05)
    assert b["결과"]["지점세"] == 35_925_000 and b["결과"]["납부할 금액(10원 미만 버림)"] == 35_925_000
    assert any("국고금 관리법 제47조" in x for x in b["한계"])


# ── 원천징수이행상황신고서 서식 연혁 ───────────────────────────────────────────
def _wr(code, filed_on, year=None, month=1):
    y = year or int(filed_on[:4])
    return WR.withholding_return(y, month, [{"코드": code, "인원": 1, "총지급액": 1_000_000, "소득세": 30_000}], filed_on=filed_on)


def test_form21_code_boundaries_by_filing_date():
    pairs = [("A05", "2016-02-24", "2016-02-25"), ("A43", "2017-12-31", "2018-01-01"), ("A49", "2021-03-15", "2021-03-16"),
             ("A71", "2022-03-17", "2022-03-18"), ("A59", "2023-12-28", "2023-12-29")]
    for code, before, after in pairs:
        m = 1 if before[5:7] <= "02" else 3 if before[5:7] == "03" else 12
        assert "error" in _wr(code, before, month=m if before[:4] == after[:4] else 12), (code, before)
        assert "error" not in _wr(code, after, year=int(before[:4]), month=m if before[:4] == after[:4] else 12), (code, after)
    # 금융투자소득 A71은 2025.1.1. 시행 서식에서 삭제
    assert "error" not in _wr("A71", "2024-12-31", month=11)
    assert "error" in _wr("A71", "2025-01-01", year=2024, month=12)


def test_form21_labels_and_subtotal_2016():
    assert _wr("A01", "2016-01-10")["결과"]["적용서식"] == "<개정 2015. 3. 13.>"
    assert _wr("A01", "2016-03-16", month=2)["결과"]["적용서식"] == "<개정 2016. 3. 16.>"
    assert _wr("A01", "2019-03-20", month=2)["결과"]["적용서식"] == "<개정 2019. 3. 20.>"
    assert _wr("A01", "2023-01-10", year=2022, month=12)["결과"]["적용서식"] == "<개정 2022. 12. 31.>"
    assert _wr("A01", "2025-03-20", month=2)["결과"]["적용서식"] == "<개정 2024. 12. 31.>"
    # <개정 2015. 3. 13.> 서식은 분납 칸이 없어 세액 가감계 A10 = A01 + A02 + A03 + A04
    lines = [{"코드": "A01", "인원": 10, "총지급액": 30 * M, "소득세": 500_000}, {"코드": "A04", "인원": 10, "총지급액": 300 * M, "소득세": 200_000}]
    old = WR.withholding_return(2016, 1, lines, filed_on="2016-02-10")
    assert old["계산"]["행"]["A10"]["소득세"] == 700_000
    # <개정 2016. 3. 16.> 서식부터 세액 가감계 A10 = A01 + A02 + A03 + A06 (연말정산 합계 A04는 세액 가감계에 넣지 않음)
    new = WR.withholding_return(2016, 2, lines + [{"코드": "A06", "인원": 0, "총지급액": 0, "소득세": 200_000}], filed_on="2016-03-16")
    assert new["계산"]["행"]["A10"]["소득세"] == 700_000 and new["계산"]["행"]["A10"]["인원"] == 20
    # 신고일을 생략하면 법정 신고기한(다음 달 10일)으로 서식을 고름
    auto = WR.withholding_return(2021, 3, lines)
    assert auto["결과"]["적용서식"] == "<개정 2021. 3. 16.>" and any("filed_on" in x for x in auto["주의"])
    assert "error" in WR.withholding_return(2016, 1, lines, filed_on="2015-12-31")


# ── 납부지연가산세: 2020.1.1. 전 성립분을 2026.7.1. 이후 납부 ────────────────────
def test_late_payment_pre2020_after_2026_07_shows_both():
    f = _fn(S.late_payment_penalty)
    r = f(unpaid_tax=10 * M, due="2019-05-31", until="2026-07-10", notice=False)
    alt = r["결과"]["달리_볼_때"]
    assert alt["일수"] == r["결과"]["일수"] - 1 and alt["가산세"] < r["결과"]["가산세"]
    assert "근거 없음" in json.dumps(r, ensure_ascii=False)
    assert "달리_볼_때" not in f(unpaid_tax=10 * M, due="2019-05-31", until="2026-06-30", notice=False)["결과"]


# ── 비거주자 양도 원천징수·증여 문구 ──────────────────────────────────────────
def test_nonresident_local_tax_basis_and_gift_article():
    r = S.nonresident_capital_gains_withholding("개인", "부동산등", 2016, 1_000_000_000, acquisition_cost=700_000_000)
    s = json.dumps(r, ensure_ascii=False)
    assert "지방세법 제103조의18제1항" in s and "제103조의13" not in s
    g20 = json.dumps(S.nonresident_inheritance_gift(kind="증여", event_date="2020-06-01", value=500 * M), ensure_ascii=False)
    g21 = json.dumps(S.nonresident_inheritance_gift(kind="증여", event_date="2021-06-01", value=500 * M), ensure_ascii=False)
    assert "제21조 국외 증여" in g20 and "제35조 국외 증여" in g21


# ── 대조로 닫은 문구가 '확인 필요'로 남지 않았는지 ───────────────────────────────
def test_closed_labels_removed():
    rules = json.loads((Path(S.__file__).parent / "data" / "stock_gains_rules.json").read_text(encoding="utf-8"))
    assert "미확인" not in json.dumps(rules, ensure_ascii=False) and "구조 해석" not in json.dumps(rules, ensure_ascii=False)
    fw = S.foreign_worker_flat_tax(year=2016, first_work_date="2015-03-01", taxable_pay=50_000_000)
    assert any("제106조의2" in x and "개정 없음" in x for x in fw["대조"])
    assert not any("현행본만" in x for x in fw["한계"])
    fe = S.foreign_expert_income_reduction(category="연구원", category_requirements_met=True, year=2023, first_work_date="2021-03-01", gross_pay=60_000_000)
    assert any("제132조제2항" in x for x in fe["대조"]) and any("부칙 제3조" in x for x in fe["한계"])
    assert not any("대조하지 않음" in x for x in fe["한계"])
