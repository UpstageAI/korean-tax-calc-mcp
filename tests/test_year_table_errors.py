"""연도표 없는 해 — 모듈별 NoYearTable이 engine.errors 한 클래스이고, 서버 _guard가 종전과 같은 {"error", "주의"} dict를 돌려주는지."""
from korean_tax_calc_mcp.engine import calc_cit as C, calc_income as I, calc_vat as V
from korean_tax_calc_mcp.engine.errors import NoYearTable
from tests._helpers import call

주의 = "연도표 없는 해는 추정 계산하지 않음"


def _strip(r):
    return {k: v for k, v in r.items() if k != "안내"}   # 같은 입력 반복 호출 안내는 제외


def test_aliases_same_class():
    assert C.NoYearTable is NoYearTable and I.NoYearTable is NoYearTable and V.NoYearTable is NoYearTable
    assert issubclass(NoYearTable, ValueError)


def test_income_missing_year():
    r = call("daily_worker_withholding", {"daily_wage": 230_000, "year": 2015})
    assert _strip(r) == {"error": "소득세 연도표 없음: 2015", "주의": 주의}


def test_vat_missing_period():
    r = call("vat_deemed_rent", {"deposit": 120_000_000, "days": 90, "period": "2015-2"})
    assert _strip(r) == {"error": "부가가치세 연도표 없음: 2015-2", "주의": 주의}


def test_cit_missing_year_through_value_error_wrapper():
    # nonbusiness_interest_disallowance는 (ValueError, KeyError, TypeError)를 따로 잡는다 — 연도표 없음은 종전대로 _guard 형식
    r = call("nonbusiness_interest_disallowance", {"loans": [{"interest": 1_200, "principal": 120_000, "days": 365}],
                                                   "nonbusiness_jeoksu": 1_200, "fiscal_start": "2015-04-01", "fiscal_end": "2016-03-31"})
    assert _strip(r) == {"error": "2015 사업연도 — 2016~2026만 지원(추정 계산 안 함)", "주의": 주의}


def test_tier_float_accumulate_accepts_none_cap():
    """exact.tier: 설명대로 마지막 상한 None도 부동소수 누적 경로에서 받는다(math.inf와 같은 값)."""
    import math
    from korean_tax_calc_mcp.engine import exact
    tiers_none = [(200_000_000, 0.09), (20_000_000_000, 0.19), (None, 0.21)]
    tiers_inf = [(200_000_000, 0.09), (20_000_000_000, 0.19), (math.inf, 0.21)]
    for x in (150_000_000, 200_000_000, 5_000_000_000, 30_000_000_000):
        assert exact.tier(x, tiers_none, float_accumulate=True) == exact.tier(x, tiers_inf, float_accumulate=True)
        assert exact.tier(x, tiers_none) == exact.tier(x, tiers_inf)
