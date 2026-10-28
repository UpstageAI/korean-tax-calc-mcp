"""10/28 연도별 조문 대조 수정(금융소득 원천징수·조문 인용, 연금소득공제 합산, 지정지역 비사업용 토지, 다주택 중과 확인) 회귀 테스트."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp
from korean_tax_calc_mcp.engine import calc_income as I


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def _판단(r, 항목):
    return [h for h in r["판단"] if h["항목"] == 항목]


# ── 금융소득 원천징수세율·조문 인용 ──
def test_court_deposit_interest_withheld_14pct():
    # 소득세법 제129조②1호: 민사집행법상 법원 보증금·경락대금 이자 100분의 14, 제14조③3호 분리과세
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "법원보증금이자", "amount": 1_000_000}]})
    h = _판단(r, "법원보증금이자")[0]
    assert "제129조②1호" in h["근거"] and "140,000원" in h["이유"]
    assert r["결과"]["합산액"] == 0


def test_mutual_aid_excess_return_no_flat_rate_without_years():
    # 제129조①1호다목 기본세율, 제63조① 연분연승 — 납입연수 없으면 세액을 찍지 않음
    r = c("financial_income_aggregate", {"year": 2025, "items": [{"kind": "직장공제회초과반환금", "amount": 10_000_000}]})
    h = _판단(r, "직장공제회초과반환금")[0]
    assert "제16조①10호" in h["근거"] and "제63조" in h["근거"] and "원천징수 2,000,000원" not in h["이유"]
    assert "산출세액" not in h["이유"]


def test_mutual_aid_excess_return_with_years():
    # 제63조①: 1,000만 − 400만(40%) − 400만(10년: 150만+50만×5) = 200만 ÷ 10 = 20만
    # 2025 기본세율 6% → 12,000 × 10 = 120,000
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "직장공제회초과반환금", "amount": 10_000_000, "contribution_years": 10}]})
    assert "산출세액 120,000원" in _판단(r, "직장공제회초과반환금")[0]["이유"]


def test_partner_dividend_withholding_25pct_and_citations():
    # 제17조①8호 출자공동사업자, 제129조①2호가목 25% / 외국법인배당 제17조①6호 / 환매조건부 제16조①8호
    r = c("financial_income_aggregate", {"year": 2025, "items": [
        {"kind": "출자공동사업자배당", "amount": 3_000_000},
        {"kind": "외국법인배당", "amount": 1_000_000},
        {"kind": "환매조건부매매차익", "amount": 1_000_000}]})
    p = _판단(r, "출자공동사업자배당")[0]
    assert "제17조①8호" in p["근거"] and "원천징수 25%" in p["이유"]
    assert "제17조①6호" in _판단(r, "외국법인배당")[0]["근거"]
    assert "제16조①8호" in _판단(r, "환매조건부매매차익")[0]["근거"]


# ── 연금소득공제는 합계에 한 번(제47조의2①) ──
def test_pension_deduction_applied_once_on_sum():
    # 2025: 공적 1,000만 + 사적 2,000만(1,500만 초과 → 종합과세) = 3,000만
    # 공제 630만 + (3,000만 − 1,400만) × 10% = 790만 → 소득 2,210만 (따로 공제하면 550만+690만으로 과소)
    rules = I._load_income_rules()
    r = I._process_income_items(2025, [{"kind": "공적연금", "amount": 10_000_000},
                                       {"kind": "사적연금", "amount": 20_000_000}], rules)
    assert r["income"] == 22_100_000
    assert sum(p["반영금액"] for p in r["processing"]) == 22_100_000


def test_pension_deduction_cap_900man():
    # 공적연금 두 항목 합계 1억: 630만 + 8,600만 × 10% = 1,490만 → 한도 900만 → 9,100만
    rules = I._load_income_rules()
    r = I._process_income_items(2025, [{"kind": "공적연금", "amount": 60_000_000},
                                       {"kind": "공적연금", "amount": 40_000_000}], rules)
    assert r["income"] == 91_000_000


# ── 지정지역 비사업용 토지(제104조④3호) ──
def test_designated_area_nonbusiness_land_plus_20():
    # 2025 양도, 과표 1억: 기본세율 1,536만 + (1억 − 8,800만) × 35% = 1,956만, ④3호 +20%p(2,000만) → 3,956만
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "토지", "acquisition_date": "2015-01-01",
                                "transfer_date": "2025-03-01", "non_business_land": True, "designated_area": True})
    assert r["결과"]["산출세액"] == 39_560_000 and "제104조④3호" in r["근거"]


def test_designated_area_before_2018_no_extra():
    # 2017 양도: ④3호는 제55조① 세율 + 10%p → 제1항제8호와 같음. 2017 기본세율 과표 1억 2,010만 + 1,000만
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "토지", "acquisition_date": "2015-01-01",
                                "transfer_date": "2017-03-01", "non_business_land": True, "designated_area": True})
    assert r["결과"]["산출세액"] == 30_100_000


def test_capital_gains_income_designated_area():
    r = c("capital_gains_income", {"asset_type": "토지", "acquisition_date": "2015-01-01", "transfer_date": "2025-03-01",
                                   "transfer_price": 300_000_000, "acquisition_price": 100_000_000, "non_business_land": True,
                                   "designated_area": True, "apply_basic_deduction": True})
    assert "지정지역" in r["결과"]["적용_세율"]


# ── capital_gains_tax 다주택 중과 확인(제104조⑦, 영 제167조의3①·제167조의10① 12호의2) ──
def test_heavy_multi_home_rejected_in_heavy_period():
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2015-01-01",
                                "transfer_date": "2021-03-01", "heavy_multi_home": True})
    assert r["error"].startswith("입력 확인 필요") and "houses_count" in r["필요 입력"]


def test_heavy_multi_home_temporary_exclusion_computes():
    # 2022.5.10.~2026.5.9. 양도·보유 2년 이상 → 중과 배제, 기본세율 1,956만
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2015-01-01",
                                "transfer_date": "2024-03-01", "heavy_multi_home": True})
    assert r["결과"]["산출세액"] == 19_560_000 and "한시 배제" in r["판단"][0]["결론"]


def test_heavy_multi_home_short_hold_in_exclusion_window_rejected():
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2023-01-01",
                                "transfer_date": "2024-03-01", "heavy_multi_home": True})
    assert "error" in r


def test_heavy_multi_home_after_window_rejected():
    r = c("capital_gains_tax", {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2015-01-01",
                                "transfer_date": "2026-06-01", "heavy_multi_home": True})
    assert "error" in r
