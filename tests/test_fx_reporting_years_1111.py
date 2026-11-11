"""외국환 신고 도구 날짜별 규정(Claude 작성 2026-11-11).
외국환거래규정(기획재정부 고시) 제9-5조·제9-9조를 법제처 등록 연혁 2015~2026 전 판(31개)에서 뽑아 대조:
제2017-40호(2018.1.1.), 제2018-28호(2019.1.1.), 제2019-12호(2019.5.3.), 제2021-11호(2021.6.18.), 제2021-37호(2022.1.3.),
제2023-26호(2023.7.4.), 제2025-4호(2025.2.10.). 원자료: 통합테스트/연도점검_1111/v10_fx_versions_raw.json."""
import pytest
from _helpers import call as c


def fx(**kw):
    r = c("foreign_exchange_reporting", kw)
    assert "error" not in r, r
    return r["결과"]

# 유보금 증액투자
@pytest.mark.parametrize("on,largest,kind,due", [
    ("2019-05-02", None, "사전신고", "거래 전(사전)"),
    ("2019-05-02", False, "사후보고", "사후(기한 규정 없음)"),
    ("2019-05-03", None, "사후보고", "사후(기한 규정 없음)"),
    ("2023-07-03", True, "사후보고", "사후(기한 규정 없음)"),
    ("2023-07-04", None, "사후보고", "2023-10-04"),
    ("2026-03-01", None, "사후보고", "2026-06-01")])
def test_retained_earnings_increase(on, largest, kind, due):
    a = {"event": "유보금증자", "ownership_ratio_after": 1.0, "amount_usd": 2_000_000, "event_date": on}
    if largest is not None: a["largest_shareholder"] = largest
    g = fx(**a)["신고"]
    assert (g["구분"], g["기한"]) == (kind, due)

# 거주자로부터 지분 양수
@pytest.mark.parametrize("on,kind", [("2020-09-01", "사전신고"), ("2023-07-03", "사전신고"), ("2023-07-04", "사후보고"), ("2025-06-01", "사후보고")])
def test_share_acquisition_from_resident(on, kind):
    g = fx(event="지분양수", ownership_ratio_after=0.5, amount_usd=2_000_000, event_date=on, counterparty_resident=True)["신고"]
    assert g["구분"] == kind

# 누적 50만불 이내 — 사후보고 선택지
@pytest.mark.parametrize("on,due", [("2017-03-10", "2017-04-10"), ("2023-07-03", "2023-08-03"), ("2023-07-04", "2023-10-04"),
                                    ("2025-02-09", "2025-05-09"), ("2025-02-10", None), ("2026-05-01", None)])
def test_small_investment_post_report_option(on, due):
    g = fx(event="신설출자", ownership_ratio_after=1.0, amount_usd=300_000, event_date=on)["신고"]
    assert g["구분"] == "사전신고"
    assert (g.get("사후보고_가능") or {}).get("기한") == due
    big = fx(event="신설출자", ownership_ratio_after=1.0, amount_usd=600_000, event_date=on)["신고"]
    assert "사후보고_가능" not in big

# 연간사업실적보고서 기준(회계기간 종료 후 5월 = 제출기한 당시 규정)
def annual(on, cum):
    rows = fx(event="증액출자", ownership_ratio_after=1.0, amount_usd=cum, cumulative_usd=cum, event_date=on)["사후관리"]
    return next(r for r in rows if r["보고서"] == "연간사업실적보고서")

@pytest.mark.parametrize("on,cum,due,note", [
    ("2017-06-01", 400_000, "면제 가능", "50만불"),
    ("2017-06-01", 800_000, "2018-05-31", "100만불"),       # 투자현황표 갈음
    ("2017-06-01", 1_500_000, "2018-05-31", None),
    ("2019-06-01", 800_000, "면제 가능", "100만불"),
    ("2019-06-01", 1_500_000, "2020-05-31", "200만불"),
    ("2022-06-01", 1_500_000, "면제 가능", "200만불"),
    ("2022-06-01", 2_500_000, "2023-05-31", "300만불"),
    ("2022-06-01", 3_500_000, "2023-05-31", None),
    ("2025-06-01", 2_500_000, "대상 아님", None),
    ("2025-06-01", 3_500_000, "2026-05-31", None)])
def test_annual_report_threshold_by_year(on, cum, due, note):
    r = annual(on, cum)
    assert r["기한"] == due
    assert (note in r.get("비고", "")) if note else ("비고" not in r)

def test_annual_report_straddling_amendment_is_flagged():
    r = annual("2018-06-01", 800_000)            # 2018 회계기간, 제출기한 2019.5.31. — 2019.1.1. 기준(100만·200만)으로 면제 가능
    assert r["기한"] == "면제 가능" and "주의" in r

# 신고 내용 변경
@pytest.mark.parametrize("on,due,basis", [("2017-06-01", "변경 전(사전)", "제9-5조②"), ("2018-01-01", "2018-04-01", "제9-5조②"),
                                          ("2023-07-03", "2023-10-03", "제9-5조②"), ("2023-07-04", "2024-05-31", "제9-9조① 제8호")])
def test_change_report(on, due, basis):
    rows = fx(event="내용변경", ownership_ratio_after=1.0, event_date=on)["사후관리"]
    r = next(x for x in rows if "변경" in x["보고서"])
    assert r["기한"] == due and basis in r["근거"]

# 다른 거주자에게 지분 매각
@pytest.mark.parametrize("on,due", [("2017-06-01", "변경 전(사전)"), ("2018-01-01", "즉시"), ("2021-06-17", "즉시"), ("2021-06-18", "7영업일 이내"),
                                    ("2022-01-02", "7영업일 이내"), ("2022-01-03", "2022-04-03"), ("2024-05-01", "2024-08-01")])
def test_share_sale_to_resident(on, due):
    rows = fx(event="지분매각", ownership_ratio_after=0.0, event_date=on, counterparty_resident=True)["사후관리"]
    assert rows[-1]["기한"] == due

def test_event_date_range():
    for d in ("2015-12-31", "2027-01-01"):
        assert "error" in c("foreign_exchange_reporting", {"event": "신설출자", "ownership_ratio_after": 1.0, "amount_usd": 1, "event_date": d})


# ── 해외 파견 인건비: 국외근로 비과세(건설·선박) 300만원 → 2024년부터 500만원 ─────────────────
@pytest.mark.parametrize("year,kind,amount", [(2016, "건설·선박", 36_000_000), (2023, "건설·선박", 36_000_000), (2024, "건설·선박", 60_000_000),
                                              (2026, "건설·선박", 60_000_000), (2023, "일반", 12_000_000), (2025, "일반", 12_000_000)])
def test_overseas_work_exemption_by_year(year, kind, amount):
    r = c("expat_cost_recharge", {"year": year, "items": [{"이름": "갑", "급여": 100_000_000, "귀속": "현지법인", "청구액": 105_000_000,
                                                            "국외근로_개월": 12, "국외근로_유형": kind}]})
    assert "error" not in r, r
    assert r["결과"]["항목별"][0]["근로자_비과세"] == amount


def test_foreign_subsidiary_dividend_date_range():
    base = {"ownership_ratio": 0.5, "held_months": 12, "dividend": 100_000_000, "subsidiary_tax": 20_000_000, "subsidiary_income": 100_000_000}
    assert "error" in c("foreign_subsidiary_dividend", {**base, "received_on": "2015-06-30"})
    assert "error" not in c("foreign_subsidiary_dividend", {**base, "received_on": "2024-06-30"})
