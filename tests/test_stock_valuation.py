"""비상장주식 평가 — 상증법 보충적 평가·소득세법 기준시가 손계산 정답. 작성 Claude 2026-10-30."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


INC = [{"사업연도": 2025, "순손익액": 120_000_000}, {"사업연도": 2024, "순손익액": 90_000_000}, {"사업연도": 2023, "순손익액": 60_000_000}]


def V(**a):
    base = dict(valuation_date="2026-05-01", shares=100_000, incomes=INC, net_asset=800_000_000)
    base.update(a)
    return c("unlisted_stock_valuation", base)


def test_basic_weighted_and_premium():
    r = V(is_max_shareholder=True, sme=False)
    res = r["결과"]
    assert res["순손익가치"] == 10000 and res["순자산가치"] == 8000 and res["가중평균"] == 9200 and res["1주당_평가액"] == 11040 and res["할증률"] == 0.2
    assert V(is_max_shareholder=True, sme=True)["결과"]["1주당_평가액"] == 9200
    assert V(is_max_shareholder=True, sme=False, mid_sized=True)["결과"]["1주당_평가액"] == 9200   # 2023~ 중견 제외
    assert V()["결과"]["할증률"] == 0


def test_real_estate_heavy_and_net_asset_only():
    assert V(real_estate_ratio=0.6)["결과"]["가중평균"] == 8800
    r = V(real_estate_ratio=0.85)   # 2026.5: 부동산 80% 사유지만 가중평균 8,800 ≥ 순자산 8,000 → 가중평균(2026.2.27.~ 한정)
    assert r["결과"]["1주당_평가액"] == 8800
    r = V(valuation_date="2025-05-01", real_estate_ratio=0.85)   # 2025: 순자산가치만
    assert r["결과"]["1주당_평가액"] == 8000 and r["결과"]["평가방법"].startswith("순자산가치만")
    r = V(business_start="2024-01-01")
    assert r["결과"]["1주당_평가액"] == 8000


def test_floor_by_period():
    low = [{"사업연도": 2016, "순손익액": 6_000_000}, {"사업연도": 2015, "순손익액": 6_000_000}, {"사업연도": 2014, "순손익액": 6_000_000}]   # 1주당 순손익 60 → 가치 600
    r = V(valuation_date="2017-10-01", incomes=low)     # (600×3+8000×2)/5 = 3,560 < 8000×70% = 5,600
    assert r["결과"]["1주당_평가액"] == 5600
    r = V(valuation_date="2019-10-01", incomes=low)     # 80%
    assert r["결과"]["1주당_평가액"] == 6400
    r = V(valuation_date="2016-10-01", incomes=low)     # 하한 없음
    assert r["결과"]["1주당_평가액"] == 3560


def test_premium_pre_2020_and_negative_income():
    r = V(valuation_date="2019-06-01", is_max_shareholder=True, sme=False, ratio_over_50=True)
    assert r["결과"]["할증률"] == 0.3 and r["결과"]["1주당_평가액"] == 11960
    r = V(valuation_date="2019-06-01", is_max_shareholder=True, sme=True)
    assert r["결과"]["할증률"] == 0
    neg = [{"사업연도": 2025, "순손익액": -50_000_000}, {"사업연도": 2024, "순손익액": 10_000_000}, {"사업연도": 2023, "순손익액": 5_000_000}]
    r = V(incomes=neg)   # 가중평균 (−500×3+100×2+50)/6 < 0 → 순손익가치 0 → (0×3+8000×2)/5=3200 < 6400 → 하한
    assert r["결과"]["순손익가치"] == 0 and r["결과"]["1주당_평가액"] == 6400


def test_goodwill_from_equity():
    r = V(equity=100_000_000)
    # 3년 가중평균 순손익 1억 × 50% − 자기자본 1억 × 10% = 4천만 → ×3.7908 = 151,631,470 → 순자산가치 (8억+1.516억)/10만 = 9,516.3
    assert abs(r["계산"]["영업권"] - 151_631_470) < 2 and abs(r["결과"]["순자산가치"] - 9516.31) < 0.05


def test_missing_sme_for_max_shareholder():
    e = V(is_max_shareholder=True)
    assert "sme" in e["필요 입력"]


def test_income_tax_basis():
    r = c("stock_basis_income_tax", {"transfer_date": "2026-05-01", "shares": 100_000, "prior_year_income": 50_000_000, "book_net_asset": 700_000_000})
    assert r["결과"]["1주당_기준시가"] == 5800 and any(x["항목"] == "할증" for x in r["판단"])
    r = c("stock_basis_income_tax", {"transfer_date": "2026-05-01", "shares": 100_000, "prior_year_income": 1_000_000, "book_net_asset": 700_000_000})
    assert r["결과"]["1주당_기준시가"] == 5600   # (100×3+7000×2)/5=2,860 < 5,600 하한
    r = c("stock_basis_income_tax", {"transfer_date": "2017-05-01", "shares": 100_000, "prior_year_income": 1_000_000, "book_net_asset": 700_000_000})
    assert r["결과"]["1주당_기준시가"] == 2860   # 2018.3.31.까지 하한 없음
    r = c("stock_basis_income_tax", {"transfer_date": "2026-05-01", "shares": 100_000, "book_net_asset": 700_000_000, "business_start": "2025-10-01"})
    assert r["결과"]["1주당_기준시가"] == 7000


def test_statement_inputs_build_income_and_net_asset():
    inc = [{"사업연도": 2025, "각사업연도소득": 150_000_000, "가산": {"수입배당금 익금불산입": 5_000_000}, "차감": {"법인세": 30_000_000, "지방소득세": 3_000_000, "접대비 한도초과": 2_000_000}},
           {"사업연도": 2024, "순손익액": 90_000_000}, {"사업연도": 2023, "순손익액": 60_000_000}]
    na = {"자산_장부가액": 1_500_000_000, "자산_평가차액": 100_000_000, "부채_장부가액": 800_000_000,
          "자산_차감": {"선급비용": 10_000_000}, "부채_가산": {"퇴직급여추계액": 40_000_000, "미지급 법인세": 30_000_000}, "부채_차감": {"대손충당금": 20_000_000}}
    r = c("unlisted_stock_valuation", {"valuation_date": "2026-05-01", "shares": 100_000, "incomes": inc, "net_asset": na})
    # 2025 순손익액 = 150 + 5 − 30 − 3 − 2 = 120(백만) → 1주당 1,200 → 가중 (1200×3+900×2+600)/6 = 1000 → 10,000
    # 순자산 = (1500+100−10) − (800+40+30−20) = 1590 − 850 = 740(백만) → 7,400/주 → (10000×3+7400×2)/5 = 8,960
    assert r["결과"]["순손익가치"] == 10000 and r["결과"]["순자산가치"] == 7400 and r["결과"]["1주당_평가액"] == 8960
    assert r["계산"]["순손익액 산출"][0]["산출"][-1]["금액"] == 120_000_000 and r["계산"]["순자산가액 산출"][-1]["금액"] == 740_000_000
    e = c("unlisted_stock_valuation", {"valuation_date": "2018-05-01", "shares": 100_000, "net_asset": 800_000_000,
                                       "incomes": [{"사업연도": 2017, "각사업연도소득": 100_000_000, "가산": {"외화평가이익": 1}}, {"사업연도": 2016, "순손익액": 1}, {"사업연도": 2015, "순손익액": 1}]})
    assert "2019-02-12" in e["문제"][0]
    e = c("unlisted_stock_valuation", {"valuation_date": "2026-05-01", "shares": 100_000, "net_asset": {"자산_장부가액": 1, "부채_장부가액": 0, "부채_가산": {"이상한항목": 1}}})
    assert "알 수 없음" in e["문제"][0]


def test_capital_change_adjustment_and_converted_shares():
    # 2025.7.1 유상증자 20,000주 × 5,000원 = 1억 → 2025: +1억×10%×7/12, 2024·2023: +1억×10%; 2024·2023 주식수 80,000 → 80,000×(80,000+20,000)/80,000 = 100,000
    inc = [{"사업연도": 2025, "순손익액": 100_000_000, "주식수": 100_000}, {"사업연도": 2024, "순손익액": 80_000_000, "주식수": 80_000}, {"사업연도": 2023, "순손익액": 60_000_000, "주식수": 80_000}]
    r = c("unlisted_stock_valuation", {"valuation_date": "2026-05-01", "shares": 100_000, "incomes": inc, "net_asset": 800_000_000,
                                       "capital_changes": [{"일자": "2025-07-01", "구분": "증자", "주식수": 20_000, "1주당금액": 5_000}]})
    adj = {(x["사업연도"], x["구분"][:2]): x for x in r["계산"]["증감자 조정"]}
    assert abs(adj[(2025, "증자")]["순손익액 조정"] - 100_000_000 * 0.1 * 7 / 12) < 1 and abs(adj[(2024, "증자")]["순손익액 조정"] - 10_000_000) < 1
    conv = [x for x in r["계산"]["증감자 조정"] if x["구분"] == "환산주식수"]
    assert {x["사업연도"]: x["값"] for x in conv} == {2024: 100_000, 2023: 100_000}
    # 1주당: 2025 (1억+5,833,333)/100,000 = 1,058.33 / 2024 9천만/100,000 = 900 / 2023 7천만/100,000 = 700 → (1058.33×3+900×2+700)/6 = 945.83 → 9,458.3
    assert abs(r["결과"]["순손익가치"] - 9458.33) < 0.1


def test_estimated_profit_requirements():
    base = dict(valuation_date="2026-05-01", shares=100_000, incomes=INC, net_asset=800_000_000)
    ok = {"1주당추정이익평균": 2_000, "사유": "합병", "신고기한": "2026-08-31", "신고일": "2026-08-01", "산정기준일": "2026-04-30", "평가서작성일": "2026-07-01"}
    r = c("unlisted_stock_valuation", {**base, "estimated_profit": ok})
    assert r["결과"]["순손익가치"] == 20000 and r["결과"]["가중평균"] == 15200
    bad = {**ok, "산정기준일": "2025-12-31"}   # 4호: 같은 연도 아님 → 3년 가중평균
    r = c("unlisted_stock_valuation", {**base, "estimated_profit": bad})
    assert r["결과"]["순손익가치"] == 10000 and any("미충족" in x["결론"] for x in r["판단"])
    e = c("unlisted_stock_valuation", {**base, "estimated_profit": {**ok, "사유": "그냥"}})
    assert "허용" in e["문제"][0]


def test_assets_valuation_layer():
    assets = [{"종류": "토지", "명칭": "본사 부지", "장부가액": 300_000_000, "기준시가": 500_000_000},
              {"종류": "상장주식", "장부가액": 50_000_000, "시가": 40_000_000},            # 장부가액보다 낮음 → 장부가액 유지
              {"종류": "상장주식", "명칭": "손상", "장부가액": 50_000_000, "시가": 40_000_000, "하한 예외": True},
              {"종류": "예금", "장부가액": 100_000_000}]
    r = c("unlisted_stock_valuation", {"valuation_date": "2026-05-01", "shares": 100_000, "incomes": INC, "net_asset": 800_000_000, "assets": assets})
    lines = {x["자산"]: x for x in r["계산"]["자산별 평가"]}
    assert lines["본사 부지"]["평가차액"] == 200_000_000 and lines["상장주식"]["평가차액"] == 0 and lines["손상"]["평가차액"] == -10_000_000
    assert r["결과"]["순자산가치"] == (800_000_000 + 190_000_000) / 100_000


def test_goodwill_excluded_for_three_year_loss_company():
    neg = [{"사업연도": 2025, "순손익액": -50_000_000}, {"사업연도": 2024, "순손익액": -10_000_000}, {"사업연도": 2023, "순손익액": -5_000_000}]
    r = c("unlisted_stock_valuation", {"valuation_date": "2026-05-01", "shares": 100_000, "incomes": neg, "net_asset": 800_000_000, "equity": 100_000_000})
    assert r["계산"]["영업권"] == 0 and r["결과"]["순자산가치"] == 8000
