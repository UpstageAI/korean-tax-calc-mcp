"""비역년 특정외국법인 저세율 기준 시점 테스트(Claude 작성, 2026-11-14).
대조: 국제조세조정에 관한 법률 제27조제1항제1호(2022.1.1. 시행본 이후), 법률 제18588호 부칙 제4조,
법인세법 제55조 최고세율(2022 25%, 2023~2025 24%, 2026 25% — 법률 제19193호 부칙 제18조·제21217호 부칙 제5조).
기준 시점을 정한 조문·해석·판례 없음(재검색 보고 대조_CFC최고세율.md) → 개시연도 기준 판정 + 종료연도 기준이 다르면 병기."""
from _helpers import call as c

M = 1_000_000
RE = {"unappropriated_retained_earnings": 3_000 * M, "dividends": 0, "mandatory_reserves": 0, "previously_taxed_undistributed": 0}


def run(year, fy_end, tax):
    return c("cfc_deemed_dividend", {"year": year, "pretax_incomes": [10_000 * M], "taxes_paid": [tax * M],
                                     "ownership_chains": [[1.0]], "distributable": RE, "fy_end": fy_end})


def test_2025_straddle_splits_between_168_and_175():
    g = run(2025, "2026-06-30", 1_700)          # 17.0%: 개시연도 16.8% 초과 → 아님, 종료연도 17.5% 이하 → 해당
    r = g["결과"]
    assert r["특정외국법인_해당"] is False
    assert r["종료연도_기준세율_만분율"] == 1750 and r["저세율_판정_기준시점_갈림"] is True
    assert r["종료연도_기준_특정외국법인_해당"] is True
    assert any("기준 시점에 따라 갈림" in s for s in g["주의"])


def test_2022_straddle_into_2023():
    r = run(2022, "2023-03-31", 1_700)["결과"]     # 개시 2022 17.5% 이하 → 해당, 종료 2023 16.8% 초과 → 아님
    assert r["특정외국법인_해당"] is True and r["저세율_판정_기준시점_갈림"] is True
    assert r["종료연도_기준_특정외국법인_해당"] is False


def test_straddle_but_same_verdict():
    r = run(2025, "2026-06-30", 1_000)["결과"]     # 10%: 두 기준 모두 이하
    assert r["저세율_판정_기준시점_갈림"] is False and "종료연도_기준_특정외국법인_해당" not in r


def test_calendar_year_no_extra_fields():
    r = run(2025, "2025-12-31", 1_700)["결과"]
    assert "종료연도_기준세율_만분율" not in r and "저세율_판정_기준시점_갈림" not in r


def test_same_rate_years_no_extra_fields():
    r = run(2023, "2024-06-30", 1_700)["결과"]     # 2023·2024 모두 16.8%
    assert "저세율_판정_기준시점_갈림" not in r
