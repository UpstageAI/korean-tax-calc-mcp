"""신고의무 판정 연도표(Claude 작성 2026-11-11).
조문 확인: 구 외감령 제2조①(20171231)·신 영 제5조(20181231·20261111)·대통령령 제29269호 부칙 제2조, 법인령 제97조의2①(20161231·20261111),
구 국조령 제7조①(2016~2020)·구 시행규칙 제6조②(2016~2020)·영 제36조(20211231·20221231·20231231·20261111)·대통령령 제33272호 부칙 제2조,
구 법인세법 제121조의2①(20161231·20201231)·국조법 제58조①(20211231)·법률 제17651호 부칙 제17조."""
import pytest
from _helpers import call as c

E = 100_000_000


def fo(**kw):
    r = c("corporate_filing_obligations", kw)
    assert "error" not in r, r
    return r["결과"]

# ── 외부감사 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("year,kw,target", [
    (2017, dict(assets=130 * E), True),                                         # 구 기준: 자산 120억 이상
    (2019, dict(assets=130 * E), True),                                         # 2019.10.31. 이전 개시 사업연도까지 구 기준
    (2020, dict(assets=130 * E), False),                                        # 신 기준: 4개 중 1개뿐
    (2020, dict(assets=130 * E, liabilities=80 * E), True),                     # 4개 중 2개
    (2017, dict(assets=80 * E, liabilities=75 * E), True),                      # 구: 부채 70억 + 자산 70억
    (2017, dict(assets=80 * E, employees=300), True),                           # 구: 종업원 300명 + 자산 70억
    (2017, dict(assets=60 * E, liabilities=75 * E, employees=400), False),      # 구: 자산 70억 미만
    (2018, dict(assets=100 * E, revenue_prev=600 * E), False),                  # 매출 500억만 — 신 기준은 2019.11.1. 이후 시작 사업연도부터
    (2020, dict(assets=100 * E, revenue_prev=600 * E), True),
    (2020, dict(assets=100 * E, revenue=600 * E), False),                       # 당기 매출은 기준 아님(직전 사업연도 매출액)
    (2017, dict(assets=10 * E, listed=True), True),
    (2019, dict(corp_type="유한회사", assets=600 * E), False),                   # 유한회사는 2019.11.1. 이후 시작 사업연도부터
    (2020, dict(corp_type="유한회사", assets=130 * E, liabilities=80 * E), False),   # 유한회사 5개 중 3개 필요
    (2020, dict(corp_type="유한회사", assets=130 * E, liabilities=80 * E, members=60), True)])
def test_external_audit_by_year(year, kw, target):
    assert fo(year=year, **kw)["외부감사"]["대상"] is target

def test_external_audit_chains_to_tax_adjustment():
    old = fo(year=2017, assets=130 * E)["외부세무조정"]
    new = fo(year=2020, assets=130 * E)["외부세무조정"]
    assert old["대상"] is True and any("제1호" in x for x in old["사유"])
    assert new["대상"] is False

# ── 외부세무조정 제2호·제3호: 직전 사업연도 수입금액 3억 ────────────────────────────
def test_tax_adjustment_items_2_and_3_use_prior_year_revenue():
    assert fo(year=2024, revenue=5 * E, revenue_prev=2 * E, tax_incentive=True)["외부세무조정"]["대상"] is False
    assert fo(year=2024, revenue=1 * E, revenue_prev=4 * E, tax_incentive=True)["외부세무조정"]["대상"] is True
    assert fo(year=2024, revenue_prev=2 * E, reserve_balance=5 * E)["외부세무조정"]["대상"] is False
    assert fo(year=2024, revenue_prev=4 * E, reserve_balance=5 * E)["외부세무조정"]["대상"] is True

# ── 국제거래 자료 ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("year,goods,target", [(2016, 3 * E, True), (2020, 3 * E, True), (2022, 3 * E, True), (2023, 3 * E, False),
                                               (2023, 6 * E, True), (2026, 3 * E, False), (2022, 0, False)])
def test_transaction_statement_exemption_from_2023(year, goods, target):
    assert fo(year=year, related_goods=goods)["국제거래명세서"] is target

@pytest.mark.parametrize("year,target", [(2016, False), (2021, False), (2022, False), (2023, True), (2026, True)])
def test_intangibles_threshold_from_2023(year, target):
    r = fo(year=year, related_intangibles=5 * E, party_max_intangibles=5 * E)
    assert r["요약손익계산서"] is target

@pytest.mark.parametrize("year,target", [(2018, False), (2022, False), (2023, True)])
def test_transfer_pricing_form_intangibles(year, target):
    r = fo(year=year, related_goods=5 * E, related_intangibles=20 * E, party_max_goods=5 * E, party_max_intangibles=20 * E)
    assert r["정상가격산출방법신고서"] is target

@pytest.mark.parametrize("year", [2016, 2019, 2022, 2025])
def test_goods_and_services_thresholds_same_all_years(year):
    over = fo(year=year, related_goods=60 * E, party_max_goods=20 * E)
    under = fo(year=year, related_goods=60 * E, party_max_goods=8 * E)       # 상대별 10억 이하 → 면제
    assert over["정상가격산출방법신고서"] is True and under["정상가격산출방법신고서"] is False
    assert fo(year=year, related_goods=11 * E)["요약손익계산서"] is True and fo(year=year, related_goods=9 * E)["요약손익계산서"] is False

# ── 해외현지법인 명세서등 기한 ───────────────────────────────────────────────
@pytest.mark.parametrize("year,due", [(2016, "2017-03-31"), (2019, "2020-03-31"), (2020, "2021-06-30"), (2021, "2022-06-30"), (2026, "2027-06-30")])
def test_overseas_investment_statement_deadline(year, due):
    assert fo(year=year, foreign_direct_investment=True)["해외직접투자명세"]["기한"] == due
