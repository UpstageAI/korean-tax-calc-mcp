"""capital_gains_income — 부동산 양도소득금액 계산 테스트.

손계산 사례: 소득세법 제97조(양도차익)·제89조(1세대1주택 비과세)·제95조(장기보유특별공제)·
제103조(기본공제), 시행령 제154조·제156조·제159조의3·제159조의4·제160조.
기준일은 facts_vocab.json 적용 블록(부터·까지는 양도일 기준)에서 확인.
"""
import asyncio
import json
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def test_tool_registered():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "capital_gains_income" in names


# ── TEST 1: 토지 기본 (비주택·등기·기본공제X), 보유 7년 → 표1 공제율 14% ──
# 취득일 2018-01-01 → 양도일 2025-01-01: 2019-01-01~2025-01-01 범위, 표1
# 3년 6%·4년 8%·5년 10%·6년 12%·7년 14% → 7년 = 0.14
# 양도차익 = 500,000,000 − 300,000,000 − 0 − 10,000,000 = 190,000,000
# 장기보유특별공제 = 190,000,000 × 0.14 = 26,600,000
# 양도소득금액 = 190,000,000 − 26,600,000 = 163,400,000
def test_토지_표1_보유7년():
    r = c("capital_gains_income", {
        "asset_type": "토지",
        "acquisition_date": "2018-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 10_000_000,
        "registered": True,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["양도차익"] == 190_000_000
    assert r["결과"]["과세대상_양도차익"] == 190_000_000
    assert r["결과"]["보유기간_년"] == 7
    assert r["결과"]["거주기간_년"] is None
    assert r["결과"]["장기보유특별공제_적용표"] == "표1"
    assert r["결과"]["공제율"] == 0.14
    assert r["결과"]["장기보유특별공제액"] == 26_600_000
    assert r["결과"]["양도소득금액"] == 163_400_000
    assert r["결과"]["양도소득_기본공제"] == 0
    assert r["결과"]["양도소득_과세표준"] == 0
    assert r["결과"]["비과세"] is False
    # 근거 제95조② 포함 확인
    근거텍스트 = " ".join(str(x) for row in r["근거"] for x in row)
    assert "제95조" in 근거텍스트
    assert "제97조" in 근거텍스트


# ── TEST 2: 1세대1주택 비과세 (양도가액 8억 ≤ 기준 12억) ──
# 양도일 2025-01-01 → 고가주택 기준 12억 (2021.12.8.~)
# 양도가액 8억 ≤ 12억 → 전액 비과세
# 1세대1주택 비과세 요건: 보유 2년 이상 + 거주 2년 이상 (2020.1.1.~, 시행령 제159조의3)
# 보유 5년(2020-01-01~2025-01-01), 거주 3년 → 요건 충족
def test_1세대1주택_비과세_전액():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 800_000_000,
        "acquisition_price": 400_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 3,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["비과세"] is True
    assert r["결과"]["양도차익"] == 400_000_000  # 8억 − 4억
    assert r["결과"]["과세대상_양도차익"] == 0
    assert r["결과"]["양도소득금액"] == 0
    assert r["결과"]["장기보유특별공제액"] == 0
    assert r["결과"]["장기보유특별공제_적용표"] is None
    assert r["결과"]["공제율"] == 0.0
    근거텍스트 = " ".join(str(x) for row in r["근거"] for x in row)
    assert "제89조" in 근거텍스트


# ── TEST 3: 1세대1주택 고가주택 안분 + 표2 (보유 5년·거주 3년) ──
# 취득일 2020-01-01 → 양도일 2025-01-01, 보유 5년·거주 3년
# 고가주택 기준 12억 (2021.12.8.~), 양도가액 15억 > 12억 → 고가주택
# 안분비율 = (15억 − 12억) / 15억 = 3/15 = 0.2
# 과세대상 양도차익 = 10억 × 0.2 = 2억 (원 미만 버림)
# 표2: 2021.2.19~ 적용 블록 → 보유 연 4%·거주 연 4%
#   보유 5년 = 0.12+0.04+0.04+0.04+0.04 = 0.20 (표2_보유 5년 행)
#   거주 3년 = 0.08+0.04+0.04 = 0.12 (표2_거주 3년 행)
#   공제율 = 0.20 + 0.12 = 0.32
# 장기보유특별공제액 = 10억 × 0.32 × 0.2 = 64,000,000
# 양도소득금액 = 200,000,000 − 64,000,000 = 136,000,000
def test_고가주택_표2_보유5년_거주3년():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 1_500_000_000,
        "acquisition_price": 500_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 3,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["양도차익"] == 1_000_000_000
    assert r["결과"]["과세대상_양도차익"] == 200_000_000
    assert r["결과"]["보유기간_년"] == 5
    assert r["결과"]["거주기간_년"] == 3
    assert r["결과"]["장기보유특별공제_적용표"] == "표2"
    assert r["결과"]["공제율"] == 0.32
    assert r["결과"]["보유기간_공제율"] == 0.20
    assert r["결과"]["거주기간_공제율"] == 0.12
    assert r["결과"]["장기보유특별공제액"] == 64_000_000
    assert r["결과"]["양도소득금액"] == 136_000_000
    assert r["결과"]["비과세"] is False
    근거텍스트 = " ".join(str(x) for row in r["근거"] for x in row)
    assert "제95조" in 근거텍스트
    assert "표2" in str(r["결과"]["장기보유특별공제_적용표"])


# ── TEST 4: 건물(주택 아님·등기), 보유 6년 → 표1 공제율 12% ──
# 취득일 2019-01-01 → 양도일 2025-01-01: 보유 6년
# 표1 6년 = 0.12 (2019.1.1~ 적용 블록: 3년 6%·4년 8%·5년 10%·6년 12%)
# 양도차익 = 300,000,000 − 200,000,000 − 0 − 5,000,000 = 95,000,000
# 장기보유특별공제 = 95,000,000 × 0.12 = 11,400,000
# 양도소득금액 = 95,000,000 − 11,400,000 = 83,600,000
def test_건물_표1_보유6년():
    r = c("capital_gains_income", {
        "asset_type": "건물",
        "acquisition_date": "2019-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 300_000_000,
        "acquisition_price": 200_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 5_000_000,
        "registered": True,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["양도차익"] == 95_000_000
    assert r["결과"]["장기보유특별공제_적용표"] == "표1"
    assert r["결과"]["공제율"] == 0.12
    assert r["결과"]["장기보유특별공제액"] == 11_400_000
    assert r["결과"]["양도소득금액"] == 83_600_000


# ── TEST 5: 미등기 + exempt_met=True → 서로 안 맞는 입력 오류 ──
# 소득세법 제95조②·④, 제103조①: 미등기양도자산은 비과세·장기보유특별공제·기본공제 배제
# 그런데 exempt_met=True(1세대1주택 비과세 요건 충족)라고 입력하면 모순 → error
def test_미등기_주택_배제():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 800_000_000,
        "acquisition_price": 400_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": False,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 3,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert any("모순" in p for p in r.get("문제", []))


# ── TEST 6: 기본공제 적용 (토지·등기, 양도소득금액 163,400,000 − 2,500,000) ──
# TEST 1과 동일 입력 + apply_basic_deduction=True
# 기본공제 250만원 (소득세법 제103조①), 미등기 아니므로 적용
# 과세표준 = 163,400,000 − 2,500,000 = 160,900,000
def test_기본공제_적용():
    r = c("capital_gains_income", {
        "asset_type": "토지",
        "acquisition_date": "2018-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 10_000_000,
        "registered": True,
        "apply_basic_deduction": True,
    })
    assert "error" not in r
    assert r["결과"]["양도소득_기본공제"] == 2_500_000
    assert r["결과"]["양도소득_과세표준"] == 160_900_000
    근거텍스트 = " ".join(str(x) for row in r["근거"] for x in row)
    assert "제103조" in 근거텍스트


# ── TEST 7: 보유 3년 미만 → 장기보유특별공제 미적용 ──
# 취득일 2023-01-01 → 양도일 2025-01-01: 보유 2년
# 표1 적용 불가 (최소보유년 3년), 장기보유특별공제액 0
# 양도차익 = 300,000,000 − 200,000,000 = 100,000,000
def test_보유3년미만_장특공제미적용():
    r = c("capital_gains_income", {
        "asset_type": "토지",
        "acquisition_date": "2023-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 300_000_000,
        "acquisition_price": 200_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["보유기간_년"] == 2
    assert r["결과"]["장기보유특별공제_적용표"] is None
    assert r["결과"]["장기보유특별공제액"] == 0
    assert r["결과"]["양도소득금액"] == 100_000_000


# ── TEST 8: 주택인데 one_house 누락 → 오류 ──
def test_주택_one_house_누락_오류():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert "one_house" in str(r.get("필요 입력", {}))


# ── TEST 9: one_house=True인데 exempt_met 누락 → 오류 ──
def test_one_house_true_exempt_met_누락_오류():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert "exempt_met" in str(r.get("필요 입력", {}))


# ── TEST 10: one_house=False·주택인데 heavy_multi_home 누락 → 오류 ──
def test_주택_one_house_false_heavy_누락_오류():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": False,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert "heavy_multi_home" in str(r.get("필요 입력", {}))


# ── TEST 11: heavy_multi_home=True → 지원하지 않음 오류 ──
def test_다주택중과_지원안함():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": False,
        "heavy_multi_home": True,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert "지원하지 않음" in r["error"]


# ── TEST 12: 2021.12.7 이전 양도 → 고가주택 기준 9억 ──
# 양도일 2021-12-07 → 적용 블록 "부터 20081007 ~ 까지 20211207" → 기준금액 9억
# 양도가액 10억 > 9억 → 고가주택, 안분비율 = (10억 − 9억)/10억 = 0.1
# 과세대상 양도차익 = 5억 × 0.1 = 50,000,000
# 표2: 2021.1.1~2021.2.18 적용 블록, 보유 연 4%·거주 연 4% (이 기간 표2 보유 4%·거주 4%)
#   보유 5년 0.20 + 거주 3년 0.12 = 0.32 ... 아님: 2021.1.1~2.18은 표2_보유 0.12~0.40 (연 4%)
#   보유 5년 = 표2_보유[4]=0.20, 거주 3년 = 표2_거주[2]=0.12 → 공제율 0.32
# 장기보유특별공제액 = 5억 × 0.32 × 0.1 = 16,000,000
# 양도소득금액 = 50,000,000 − 16,000,000 = 34,000,000
def test_2021년12월7일이전_고가주택기준9억():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2016-01-01",  # 보유 5년 이상 확보
        "transfer_date": "2021-12-07",
        "transfer_price": 1_000_000_000,
        "acquisition_price": 500_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 3,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["양도차익"] == 500_000_000
    assert r["결과"]["과세대상_양도차익"] == 50_000_000
    assert r["결과"]["장기보유특별공제_적용표"] == "표2"
    assert r["결과"]["공제율"] == 0.32
    assert r["결과"]["장기보유특별공제액"] == 16_000_000
    assert r["결과"]["양도소득금액"] == 34_000_000


# ── TEST 13: 2020.12.31 이전 양도 → 표2 보유만 8%/년 (거주 요건 없음, 표2_거주=null) ──
# 양도일 2020-12-31 → 적용 블록 "부터 20200101 ~ 까지 20201231"
# 표2_보유: 3년 24%·4년 32%·5년 40%·... (연 8%), 표2_거주 = null, 표2_거주요건년 = 2
# 보유 5년 → 표2 보유 공제율 0.40 (5년 행), 거주 공제율 0
# 공제율 = 0.40 + 0 = 0.40
# 고가주택 기준 9억 (2020.12.31 이전): 안분비율 = (15억 − 9억)/15억 = 6/15 = 0.4
# 과세대상 양도차익 = 10억 × 0.4 = 400,000,000
# 장기보유특별공제액 = 10억 × 0.40 × 0.4 = 160,000,000
# 양도소득금액 = 400,000,000 − 160,000,000 = 240,000,000
def test_2020년12월31일_표2_보유8퍼센트():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2015-01-01",  # 보유 5년 이상 확보
        "transfer_date": "2020-12-31",
        "transfer_price": 1_500_000_000,
        "acquisition_price": 500_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 5,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["양도차익"] == 1_000_000_000
    assert r["결과"]["과세대상_양도차익"] == 400_000_000
    assert r["결과"]["장기보유특별공제_적용표"] == "표2"
    # 2020.12.31 이전: 표2_거주 null → 거주율 0, 공제율 = 보유율만
    assert r["결과"]["공제율"] == 0.40
    assert r["결과"]["거주기간_공제율"] == 0.0
    assert r["결과"]["장기보유특별공제액"] == 160_000_000
    assert r["결과"]["양도소득금액"] == 240_000_000


# ── TEST 14: 1세대1주택이나 거주 2년 미만 → 표2 거주요건 미충족 → 표1으로 대체 ──
# 취득일 2021-01-01 → 양도일 2025-01-01: 보유 4년
# 2025년 적용 블록: 표2_거주요건년=2, 거주 1년 < 2 → 표1으로 대체
# 표1: 2021.2.19~ 적용 블록, 4년 = 0.08
# 고가주택 안분비율 = (15억 − 12억)/15억 = 0.2
# 과세대상 양도차익 = 10억 × 0.2 = 2억
# 장기보유특별공제액 = 10억 × 0.08 × 0.2 = 16,000,000 (표1)
# 양도소득금액 = 200,000,000 − 16,000,000 = 184,000,000
def test_표2_거주요건미충족_표1대체():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2021-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 1_500_000_000,
        "acquisition_price": 500_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 1,  # 거주 2년 미만
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["장기보유특별공제_적용표"] == "표1"
    assert r["결과"]["공제율"] == 0.08
    assert r["결과"]["장기보유특별공제액"] == 16_000_000
    assert r["결과"]["양도소득금액"] == 184_000_000


# ── TEST 15: supported asset_type 외 → 오류 ──
def test_지원하지않는_자산유형_오류():
    r = c("capital_gains_income", {
        "asset_type": "주식",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert "자산" in r["error"] or "asset_type" in str(r)


# ── TEST 16 (Fix 1): 미등기 토지 + apply_basic_deduction=True →
# 기본공제 0, 과세표준 = 양도소득금액 (미등기라 기본공제 배제) ──
# 소득세법 제103조①: 미등기양도자산은 기본공제 제외
# 양도차익 = 5억 − 3억 − 0 − 1천만 = 1억 9천만
# 장기보유특별공제: 미등기 → 0
# 양도소득금액 = 1억 9천만
# 기본공제 = 0 (미등기), 과세표준 = 1억 9천만
def test_미등기_기본공제_과세표준():
    r = c("capital_gains_income", {
        "asset_type": "토지",
        "acquisition_date": "2018-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 10_000_000,
        "registered": False,
        "apply_basic_deduction": True,
    })
    assert "error" not in r
    assert r["결과"]["양도차익"] == 190_000_000
    assert r["결과"]["양도소득금액"] == 190_000_000
    assert r["결과"]["양도소득_기본공제"] == 0
    assert r["결과"]["양도소득_과세표준"] == 190_000_000
    assert r["결과"]["장기보유특별공제액"] == 0
    근거텍스트 = " ".join(str(x) for row in r["근거"] for x in row)
    assert "제103조" in 근거텍스트


# ── TEST 17 (Fix 2): 2019.12.31 이전 양도 → residence_years 없이 표2 적용 ──
# 양도일 2019-12-31 → 2019.1.1~2019.12.31 적용 블록: 표2_거주요건년=0, 표2_거주=null
# residence_years 없이 one_house=True, exempt_met=True 입력 가능 (거주 요건 없음)
# 보유 5년(2014-01-01→2019-12-31): 표2_보유 5년 → 0.40 (연 8%: 3년 24%·4년 32%·5년 40%)
# 고가주택 기준 9억 (2019.12.31 이전): 10억 > 9억 → 안분비율 = (10억−9억)/10억 = 0.1
# 과세대상 양도차익 = 5억 × 0.1 = 50,000,000
# 장기보유특별공제액 = 5억 × 0.40 × 0.1 = 20,000,000
# 양도소득금액 = 50,000,000 − 20,000,000 = 30,000,000
def test_2019년이전_거주기간없이_표2적용():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2014-01-01",
        "transfer_date": "2019-12-31",
        "transfer_price": 1_000_000_000,
        "acquisition_price": 500_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["장기보유특별공제_적용표"] == "표2"
    assert r["결과"]["공제율"] == 0.40
    assert r["결과"]["거주기간_년"] is None  # residence_years 없이 성공
    assert r["결과"]["과세대상_양도차익"] == 50_000_000
    assert r["결과"]["장기보유특별공제액"] == 20_000_000
    assert r["결과"]["양도소득금액"] == 30_000_000


# ── TEST 18 (Fix 3): one_house=True·exempt_met=False·거주 4년 →
# 비과세 요건 미충족이나 거주 2년 이상 → 표2 적용, 양도차익 전액 과세 ──
# 2025년 양도, 보유 8년(2017-01-01→2025-01-01)·거주 4년
# 비과세=False (exempt_met=False), 고가주택 안분 없음
# 과세대상_양도차익 = 양도차익 = 5억 − 2억 = 3억
# 2025년 표2: 보유 8년→0.32, 거주 4년→0.16 → 공제율 = 0.48
# 장기보유특별공제액 = 3억 × 0.48 = 144,000,000
# 양도소득금액 = 300,000,000 − 144,000,000 = 156,000,000
def test_비과세미충족_거주2년이상_표2적용():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2017-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 200_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": False,  # 비과세 요건 미충족
        "residence_years": 4,  # 거주 4년 (≥ 2)
        "apply_basic_deduction": False,
    })
    assert "error" not in r
    assert r["결과"]["비과세"] is False
    assert r["결과"]["양도차익"] == 300_000_000
    assert r["결과"]["과세대상_양도차익"] == 300_000_000
    assert r["결과"]["장기보유특별공제_적용표"] == "표2"
    assert r["결과"]["공제율"] == 0.48
    assert r["결과"]["보유기간_공제율"] == 0.32
    assert abs(r["결과"]["거주기간_공제율"] - 0.16) < 1e-9
    assert r["결과"]["장기보유특별공제액"] == 144_000_000
    assert r["결과"]["양도소득금액"] == 156_000_000


# ── TEST 19 (Fix 4): 거주기간 > 보유기간 → error ──
def test_거주기간_보유기간초과_오류():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",  # 보유 5년
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 6,  # 거주 6년 > 보유 5년 → 오류
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert any("거주기간" in p and "보유기간" in p for p in r.get("문제", []))


# ── TEST 20 (Fix 4): exempt_met=True + 보유 2년 미만 → error ──
def test_비과세충족_보유2년미만_오류():
    r = c("capital_gains_income", {
        "asset_type": "주택",
        "acquisition_date": "2023-06-01",
        "transfer_date": "2025-01-01",  # 보유 1년 (만 1년)
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,
        "exempt_met": True,
        "residence_years": 1,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert any("2년 미만" in p for p in r.get("문제", []))


# ── TEST 21 (Fix 4): 토지 + one_house 입력 → error ──
def test_토지_one_house_입력_오류():
    r = c("capital_gains_income", {
        "asset_type": "토지",
        "acquisition_date": "2020-01-01",
        "transfer_date": "2025-01-01",
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "one_house": True,  # 토지인데 one_house 입력 → 오류
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert any("one_house" in p for p in r.get("문제", []))


# ── TEST 22 (Fix 4): 양도일 < 취득일 → error ──
def test_양도일_취득일_앞섬_오류():
    r = c("capital_gains_income", {
        "asset_type": "토지",
        "acquisition_date": "2025-01-01",
        "transfer_date": "2020-01-01",  # 양도일 < 취득일 → 오류
        "transfer_price": 500_000_000,
        "acquisition_price": 300_000_000,
        "capital_expenditure": 0,
        "transfer_expenses": 0,
        "registered": True,
        "apply_basic_deduction": False,
    })
    assert "error" in r
    assert any("앞섬" in p for p in r.get("문제", []))
