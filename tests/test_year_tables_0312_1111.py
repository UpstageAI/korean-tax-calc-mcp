"""0.31.2 정답 테스트(Claude 작성) — 0.30.0 세 도구의 연도표.
조문: 구 국조령 제49조①(2016·2017 "10억원", 2018~ "5억원"), 구 영 제51조⑤(2017·2019: 70/50/20/10)·⑥(2020: 90/70/50/30),
구 법 제34조⑤1호(2016~2018 "2년 전부터 183일", 2019~ "1년 전부터 183일")·법 제54조(2025.1.1.: 182일, 7호 조세조약 상대국 거주자, 부칙 제5조),
소득세법 제57조②(2020: 5년, 2021: 10년, 2020.12.29. 부칙 제11조), 제101조②(2022: 5년, 2023: 10년, 2022.12.31. 부칙 제18조)."""
import pytest
from _helpers import call as c

M = 1_000_000


def oar(year, bal, **kw):
    return c("overseas_account_reporting", {"year": year, "month_end_totals_krw": [bal] * 12, **kw})


# ── 1-1 신고 기준금액 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("year,bal,duty", [(2016, 700 * M, False), (2017, 1_000 * M, False), (2017, 1_000 * M + 1, True),
                                           (2018, 700 * M, True), (2018, 500 * M, False), (2022, 500 * M + 1, True), (2026, 700 * M, True)])
def test_reporting_threshold_by_year(year, bal, duty):
    g = oar(year, bal)["결과"]
    assert g["신고의무"] is duty
    assert g["기준금액"] == (1_000 * M if year <= 2017 else 500 * M)
    if not duty:
        assert g["과태료"] == 0


# ── 1-2 수정신고 감경표: 수정신고일 2020.2.11. 전후, 달력 월 ───────────────────────────────
@pytest.mark.parametrize("year,corrected,rate", [
    (2017, "2018-10-01", 70), (2017, "2018-12-30", 70), (2017, "2018-12-31", 50), (2017, "2019-06-30", 50), (2017, "2019-07-01", 20),
    (2016, "2019-07-01", 10),                                                   # 기한 2017-06-30, 2년 초과 4년 이내, 2020.2.11. 전
    (2018, "2020-02-10", 50), (2018, "2020-02-11", 70),                         # 같은 구간(6개월 초과 1년 이내)이라도 수정신고일로 표가 갈림
    (2022, "2023-12-30", 90), (2022, "2023-12-31", 70), (2022, "2024-06-30", 70), (2022, "2024-07-01", 50),
    (2022, "2025-06-30", 50), (2022, "2025-07-01", 30), (2022, "2027-06-30", 30), (2022, "2027-07-01", 0)])
def test_correction_reduction_table(year, corrected, rate):
    g = oar(year, 3_000 * M, corrected_on=corrected)["결과"]
    assert g["감경비율"] == rate
    assert g["감경후_과태료"] == g["과태료"] * (100 - rate) // 100


# ── 1-3 재외국민 면제 일수 ──────────────────────────────────────────────────────
@pytest.mark.parametrize("year,days,exempt", [(2017, 183, True), (2017, 184, False), (2022, 183, True), (2024, 183, True), (2024, 184, False),
                                              (2025, 183, False), (2025, 182, True), (2026, 182, True)])
def test_overseas_korean_days_by_year(year, days, exempt):
    r = oar(year, 3_000 * M, overseas_korean_days_in_korea=days)
    assert r["결과"]["신고의무"] is (not exempt)

def test_overseas_korean_two_year_window_note_until_2018():
    assert any("2년 전" in s for s in oar(2018, 3_000 * M, overseas_korean_days_in_korea=100)["주의"])
    assert not any("2년 전" in s for s in oar(2019, 3_000 * M, overseas_korean_days_in_korea=100)["주의"])


# ── 1-4 조세조약 상대국 거주자 면제는 2025년 보유분부터 ─────────────────────────────────
def test_treaty_resident_exemption_since_2025():
    old = oar(2024, 3_000 * M, treaty_resident_of_other_country=True)
    assert old["결과"]["신고의무"] is True and any("2025년" in s for s in old["판단"])
    assert oar(2025, 3_000 * M, treaty_resident_of_other_country=True)["결과"]["신고의무"] is False


# ── 2 개인 외국납부세액 이월공제기간 ────────────────────────────────────────────────
def ftc(year, carry_year, foreign_tax=0):
    return c("individual_foreign_tax_credit", {"year": year, "calculated_tax": 100 * M, "total_income": 500 * M,
             "countries": [{"country": "미국", "foreign_income": 100 * M, "foreign_tax": foreign_tax}],
             "carryforward": [{"country": "미국", "year": carry_year, "amount": 5 * M}]})

@pytest.mark.parametrize("year,carry_year,usable", [
    (2020, 2015, True), (2020, 2014, False),            # 2020년까지 5년
    (2019, 2014, True), (2019, 2013, False),
    (2021, 2016, True), (2021, 2015, False),            # 2015년 발생분은 2020년에 5년이 끝남(부칙 제11조: 남아 있는 금액만 10년)
    (2026, 2016, True), (2026, 2015, False), (2025, 2015, False)])
def test_carryforward_period_by_year(year, carry_year, usable):
    g = ftc(year, carry_year)["결과"]
    assert g["외국납부세액공제액"] == (5 * M if usable else 0)
    assert g["이월기간경과분"] == (0 if usable else 5 * M)

def test_expired_carryforward_reported_even_when_limit_is_used_up():
    g = ftc(2026, 2010, foreign_tax=30 * M)["결과"]          # 당기분이 한도 20을 다 써도 2010년분은 기간 경과로 잡혀야 함
    assert g["이월기간경과분"] == 5 * M

def test_carryforward_notes_by_year():
    r20 = ftc(2020, 2014); r26 = ftc(2026, 2015)
    assert any("부칙 제11조" in s for s in r20["주의"])
    assert not any("필요경비" in str(x) for x in [*r20.get("판단", []), *r20["결과"].get("산식", [])])
    assert any("필요경비" in str(x) for x in [*r26.get("판단", []), *r26["결과"].get("산식", [])])


# ── 3 증여 후 양도 부당행위: 2023.1.1. 전 증여분은 5년 ────────────────────────────────────
def gift_then_transfer(gift_date, transfer_date):
    return c("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": gift_date, "transfer_date": transfer_date,
             "donee_relation": "기타특수관계인", "donee_gift_tax": 10 * M, "donee_capital_gains_tax": 20 * M, "donor_direct_capital_gains_tax": 100 * M})

@pytest.mark.parametrize("gift,transfer,deemed,years", [
    ("2022-12-31", "2027-12-31", True, 5), ("2022-12-31", "2028-01-01", False, 5), ("2020-06-01", "2026-06-01", False, 5),
    ("2023-01-01", "2028-06-01", True, 10), ("2023-01-01", "2033-01-01", True, 10), ("2023-01-01", "2033-01-02", False, 10)])
def test_gift_then_transfer_period(gift, transfer, deemed, years):
    r = gift_then_transfer(gift, transfer)
    assert "error" not in r, r
    g = r["결과"]
    assert g["증여자_직접양도_간주"] is deemed and g["적용기간_년"] == years
    if not deemed:
        assert f"{years}년" in g["적용제외_사유"]
