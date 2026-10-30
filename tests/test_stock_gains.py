"""주식등 양도소득 — 대주주 판정·세율 (시행령 제157조·제167조의8, 법 제104조①11호·12호). 손계산 정답. 작성 Claude 2026-10-30."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def M(**a):
    return c("stock_major_shareholder", a)


def T(**a):
    return c("stock_capital_gains_tax", a)


def test_major_2026_kospi_by_mcap_and_ratio():
    r = M(transfer_date="2026-03-10", market="코스피", own_ratio=0.005, own_mcap=6_000_000_000)
    assert r["결과"]["판정"] == "대주주" and r["결과"]["기준_시가총액"] == 5_000_000_000
    r = M(transfer_date="2026-03-10", market="유가증권시장", own_ratio=1.2)   # 퍼센트 입력
    assert r["결과"]["판정"] == "대주주" and any("퍼센트" in x for x in r["입력 해석"])
    r = M(transfer_date="2026-03-10", market="코스피", own_ratio=0.009, own_mcap=4_900_000_000)
    assert r["결과"]["판정"] == "대주주 아님"


def test_major_2023_self_unless_max_group():
    base = dict(transfer_date="2023-06-01", market="코스피", own_ratio=0.005, own_mcap=500_000_000, related_ratio=0.008)
    assert M(**base, is_max_group=False)["결과"]["판정"] == "대주주 아님"
    assert M(**base, is_max_group=True)["결과"]["판정"] == "대주주"
    assert M(**base)["결과"]["판정"] == "확인 필요"


def test_major_thresholds_by_period():
    assert M(transfer_date="2019-06-01", market="코스닥", own_ratio=0.01, own_mcap=1_200_000_000)["결과"]["판정"] == "대주주 아님"   # 2%/15억
    assert M(transfer_date="2020-06-01", market="코스닥", own_ratio=0.01, own_mcap=1_200_000_000)["결과"]["판정"] == "대주주"       # 10억
    assert M(transfer_date="2026-06-01", market="비상장", own_ratio=0.03, own_mcap=2_000_000_000)["결과"]["판정"] == "대주주"       # 비상장 10억 유지
    assert M(transfer_date="2026-06-01", market="비상장", own_ratio=0.03, own_mcap=2_000_000_000, venture=True)["결과"]["판정"] == "대주주 아님"  # 벤처 40억
    assert M(transfer_date="2016-02-15", market="코스피", own_ratio=0.015, own_mcap=1_000_000_000)["결과"]["판정"] == "대주주 아님"  # 2%/50억
    assert M(transfer_date="2016-05-01", market="코스피", own_ratio=0.015, own_mcap=1_000_000_000)["결과"]["판정"] == "대주주"      # 1%/25억


def test_major_corporation_and_after_acquisition():
    assert M(transfer_date="2026-03-10", market="코스피", own_ratio=0.02, is_corporation=True)["결과"]["판정"] == "대상 아님"
    assert M(transfer_date="2024-03-10", market="코스피", own_ratio=0.02, is_corporation=True)["결과"]["판정"] == "대주주"
    r = M(transfer_date="2026-03-10", market="코스피", own_ratio=0.005, acquired_to_threshold=True)
    assert r["결과"]["판정"] == "대주주" and any(x["항목"] == "사후 취득" for x in r["판단"])


def test_tax_major_non_sme_2026():
    r = T(transfer_date="2026-03-10", market="코스피", major_shareholder=True, sme=False, transfer_price=1_000_000_000, acquisition_price=400_000_000, expenses=1_000_000, acquisition_date="2020-01-01")
    res = r["결과"]
    assert res["양도차익"] == 599_000_000 and res["기본공제"] == 2_500_000 and res["과세표준"] == 596_500_000
    assert res["산출세액"] == 134_125_000 and res["지방소득세"] == 13_412_500 and res["예정신고기한"] == "2026-08-31"


def test_tax_minor_listed_not_taxable_and_otc():
    r = T(transfer_date="2026-03-10", market="코스피", major_shareholder=False, sme=False, gain=10_000_000)
    assert r["결과"]["과세대상"] is False and r["결과"]["산출세액"] == 0
    r = T(transfer_date="2026-03-10", market="코스피", major_shareholder=False, sme=False, gain=10_000_000, otc_trade=True)
    assert r["결과"]["과세대상"] is True and r["결과"]["산출세액"] == 1_500_000   # (1천만−250만)×20%


def test_tax_unlisted_sme_minor_and_kotc():
    r = T(transfer_date="2026-03-10", market="비상장", major_shareholder=False, sme=True, gain=10_000_000)
    assert r["결과"]["산출세액"] == 750_000
    r = T(transfer_date="2026-03-10", market="K-OTC", major_shareholder=False, sme=True, gain=10_000_000)
    assert r["결과"]["과세대상"] is False
    r = T(transfer_date="2017-03-10", market="K-OTC", major_shareholder=False, sme=True, gain=10_000_000)
    assert r["결과"]["과세대상"] is True   # 단서는 2018~


def test_tax_under_one_year_tiebreak():
    r = T(transfer_date="2026-03-01", market="코스피", major_shareholder=True, sme=False, gain=100_000_000, acquisition_date="2025-10-01")
    assert r["결과"]["산출세액"] == 29_250_000 and any(x["항목"] == "세율 경합" for x in r["판단"])
    r = T(transfer_date="2026-03-01", market="코스피", major_shareholder=True, sme=False, gain=100_000_000, acquisition_date="2025-03-01")
    assert r["결과"]["산출세액"] == 19_500_000


def test_tax_sme_major_rate_change_2020():
    assert T(transfer_date="2019-09-01", market="비상장", major_shareholder=True, sme=True, gain=402_500_000)["결과"]["산출세액"] == 80_000_000
    assert T(transfer_date="2020-09-01", market="비상장", major_shareholder=True, sme=True, gain=402_500_000)["결과"]["산출세액"] == 85_000_000
    assert T(transfer_date="2017-09-01", market="비상장", major_shareholder=True, sme=True, gain=402_500_000)["결과"]["산출세액"] == 80_000_000


def test_tax_foreign_and_prelim():
    e = T(transfer_date="2018-05-01", market="미국 주식", sme=False, gain=10_000_000)
    assert e["error"].startswith("지원하지 않음")
    r = T(transfer_date="2026-05-01", market="미국 주식", sme=False, gain=10_000_000)
    assert r["결과"]["산출세액"] == 1_500_000 and r["결과"]["예정신고기한"] is None
    r = T(transfer_date="2017-05-01", market="비상장", major_shareholder=False, sme=False, gain=10_000_000)
    assert r["결과"]["예정신고기한"] == "2017-08-31"   # 분기(6/30)+2개월
    r = T(transfer_date="2026-11-20", market="비상장", major_shareholder=False, sme=False, gain=10_000_000)
    assert r["결과"]["예정신고기한"] == "2027-02-28"   # 반기(12/31)+2개월


def test_tax_missing_facts_and_loss():
    e = T(transfer_date="2026-03-10", market="코스피", gain=1_000_000)
    assert e["error"].startswith("입력 확인 필요") and "major_shareholder" in e["필요 입력"]
    e = T(transfer_date="2026-03-10", market="코스피", major_shareholder=True, sme=False, gain=1_000_000)
    assert "acquisition_date" in e["필요 입력"]
    r = T(transfer_date="2026-03-10", market="비상장", major_shareholder=False, sme=True, gain=-5_000_000)
    assert r["결과"]["산출세액"] == 0 and any(x["항목"] == "양도차손" for x in r["판단"])
