"""연도 의존 전수 점검(2026-11-11) — 간이과세자 2021.7.1. 전후, 카드 발행세액공제 2.6%, 사전검토 이월결손금 한도율(Claude 작성).
조문 확인(연도점검 2조 보고): 부가법 제63조③(20210630 매입세액 × 부가가치율 / 20210701 공급대가 × 0.5%), 제68조의2(20201231 없음 / 20210701 0.5%),
제46조①(20161231~20190101 간이 음식·숙박 2.6%, 20210701 삭제; 한도 500만 → 1천만), 법률 제17653호 부칙 제8조·제10조·제12조, 2018.12.31. 개정 부칙 제4조,
법인세법 제13조①(20171231 80%, 20181231 70%(2018 개시)·60%, 20221231 60%, 20230101 80%)."""
import pytest
from _helpers import call as c

M = 1_000_000


def st(**kw):
    return c("vat_simplified_taxpayer", kw)

@pytest.mark.parametrize("year,credit", [(2016, 200_000), (2019, 200_000), (2020, 200_000), (2022, 110_000), (2026, 110_000)])
def test_simplified_input_credit_by_year(year, credit):
    """매입 2,200만: 2021.6.30.까지 = 2,200만 × 10/110 × 부가가치율 10% = 20만 / 이후 = 2,200만 × 0.5% = 11만."""
    r = st(year=year, supply_incl_vat=44 * M, value_added_rate=0.1, invoice_purchase_incl_vat=22 * M)
    assert "error" not in r, r
    assert r["결과"]["매입세금계산서등_공제"] == credit

@pytest.mark.parametrize("year,penalty", [(2019, 0), (2020, 0), (2022, 55_000), (2025, 55_000)])
def test_no_invoice_penalty_only_from_july_2021(year, penalty):
    assert st(year=year, supply_incl_vat=44 * M, value_added_rate=0.1, no_invoice_purchase_incl_vat=11 * M)["결과"]["가산세"] == penalty

@pytest.mark.parametrize("year,food,credit", [(2019, True, 1_040_000), (2019, False, 520_000), (2020, True, 1_040_000), (2022, True, 520_000)])
def test_simplified_card_credit_rate(year, food, credit):
    r = st(year=year, supply_incl_vat=40 * M, value_added_rate=0.2, card_cash_receipt_supply_incl_vat=40 * M, food_lodging=food)["결과"]
    assert r["카드발행세액공제"] == credit
    assert r["공제_합계"] == min(credit, 800_000)            # 납부세액 4,000만 × 20% × 10% = 80만 한도

@pytest.mark.parametrize("year,cap", [(2017, 5 * M), (2018, 10 * M), (2020, 10 * M)])
def test_simplified_card_credit_cap_by_year(year, cap):
    r = st(year=year, supply_incl_vat=500 * M, value_added_rate=0.3, card_cash_receipt_supply_incl_vat=500 * M, food_lodging=True)
    assert r["결과"]["카드발행세액공제"] == cap                 # 5억 × 2.6% = 1,300만 → 한도

def test_simplified_2021_needs_split():
    base = dict(year=2021, supply_incl_vat=44 * M, value_added_rate=0.1, invoice_purchase_incl_vat=22 * M)
    assert "error" in st(**base)
    r = st(**base, invoice_purchase_before_202107=11 * M)
    assert r["결과"]["매입세금계산서등_공제"] == 155_000        # 1,100만 × 10/110 × 10% = 10만 + 1,100만 × 0.5% = 5.5만
    r2 = st(year=2021, supply_incl_vat=44 * M, value_added_rate=0.1, no_invoice_purchase_incl_vat=10 * M, no_invoice_purchase_before_202107=4 * M)
    assert r2["결과"]["가산세"] == 30_000                       # 600만 × 0.5%
    assert "error" in st(**base, invoice_purchase_before_202107=30 * M)
    assert "error" in st(year=2022, supply_incl_vat=44 * M, invoice_purchase_incl_vat=22 * M, invoice_purchase_before_202107=1 * M)
    assert "error" in st(year=2015, supply_incl_vat=44 * M)


def cc(**kw):
    return c("vat_card_sales_credit", kw)

@pytest.mark.parametrize("on,food,amount", [("2019-05-01", True, 1_040_000), ("2019-05-01", False, 520_000), ("2021-06-30", True, 1_040_000),
                                             ("2021-07-01", True, 520_000)])
def test_card_credit_food_lodging_simplified(on, food, amount):
    r = cc(amount=40 * M, supplied_on=on, simplified_food_lodging=food)
    assert r["결과"]["공제액"] == amount

def test_card_credit_cap_timing_for_simplified():
    assert cc(amount=500 * M, supplied_on="2018-03-01")["결과"]["공제액"] == 5 * M                    # 일반과세자 2018년 제1기: 500만 한도
    assert cc(amount=500 * M, supplied_on="2018-03-01", simplified=True)["결과"]["공제액"] == 6_500_000   # 간이과세자 2018년분: 1,000만 한도 안 5억 × 1.3%
    assert "error" in cc(amount=1 * M, supplied_on="2015-05-01")


def loss_cap_rule(end, loss, start=None):
    d = {"기본.종료일": end, "조정계산서.각사업연도소득금액": 1_000 * M, "조정계산서.이월결손금": loss, "이월결손금.100%공제대상": False}
    if start: d["기본.개시일"] = start
    r = c("return_precheck", {"data": d, "tax": "법인"})
    return any(x.get("규칙") == "A8-4" for x in r["오류 의심"])

@pytest.mark.parametrize("end,loss,start,flagged", [
    ("2017-12-31", 800 * M, None, False),      # 80%
    ("2018-12-31", 750 * M, None, True),       # 70%
    ("2018-12-31", 700 * M, None, False),
    ("2020-12-31", 800 * M, None, True),       # 60%
    ("2022-12-31", 600 * M, None, False),
    ("2023-12-31", 800 * M, None, False),      # 80%
    ("2023-12-31", 850 * M, None, True),
    ("2023-03-31", 700 * M, "2022-04-01", True)])   # 2022년 개시 사업연도 → 60%
def test_precheck_loss_cap_by_fiscal_year_start(end, loss, start, flagged):
    assert loss_cap_rule(end, loss, start) is flagged
