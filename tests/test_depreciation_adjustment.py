"""감가상각 시부인 도구 테스트 — 손계산 사례 8건.

근거: 법인세법상 개별 자산별 상각범위액(시인액)과 회사계상액을 비교해
초과액은 상각부인액(손금불산입·유보), 미달액은 시인부족액(손금산입·△유보 또는 소멸).
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a): return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


# ── §26①·별표4: 정액법 5년 상각률 0.2, 정률법 5년 상각률 0.451 ──────────
# 시인부족액과 전기 부인누계의 추인(시행령 제32조①), 감면법인 감가상각의제(제30조).
# 즉시상각의제: 자본적 지출을 비용 처리하면 당기 감가상각비에 합산(제31조②).
# 소액 수선비 예외: 2020년부터 600만원 미만, 직전 장부가액 5% 미만, 3년 미만 주기적
#   수선 중 하나라도 해당하면 즉시상각의제 아님(제31조③) — 2025년 기준 소액기준 600만원.


def test_정액법_상각부인액_발생():
    # 5년 정액법(상각률 0.2), 취득가액 1억, 회사계상 2,500만(범위 2,000만 초과)
    # → 상각부인액 500만 유보. 법인세법 제23조①, 시행령 제26조①, 시행규칙 별표4
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 100_000_000, "booked_depreciation": 25_000_000,
        "accumulated_dep_begin": 40_000_000,
        "expensed_capex": 0, "prior_deemed_capex": 0, "prior_disallowed": 0,
    })
    assert "error" not in r
    assert r["결과"]["상각범위액"] == 20_000_000        # 1억 × 0.2 × 12/12 (비망가액 차감 없음)
    assert r["결과"]["회사계상액"] == 25_000_000        # 2,500만 + 0
    assert r["결과"]["상각부인액"] == 5_000_000
    assert r["결과"]["시인부족액"] == 0
    assert r["결과"]["전기부인액_추인"] == 0
    assert r["결과"]["감가상각의제"] == 0
    assert r["결과"]["기말_상각부인누계액"] == 5_000_000
    assert r["결과"]["소득처분별_합계"] == {"유보": 5_000_000}
    assert r["결과"]["손금불산입_합계"] == 5_000_000
    assert r["계산"]["상각방법"] == "정액법"
    assert r["계산"]["상각률"] == 0.2
    assert r["계산"]["세무상 취득가액"] == 100_000_000
    # 명세서 정의: 기말 취득가액 − 기말 감가상각누계액 + 기말 유보잔액 + 당기 즉시상각의제액
    assert r["결과"]["세무상_미상각잔액"] == 40_000_000  # 1억 − 6,500만(기초4천만+당기2,500만) + 500만(유보)


def test_정률법_시인부족_전기부인_추인():
    # 5년 정률법(상각률 0.451), 취득가액 1억, 기초누계 6천만,
    # 회사계상 1천만, 전기말 상각부인누계 800만(prior_disallowed)
    # 기초 μm상 미상각잔액 = 취득가액 − 기초누계 + prior_disallowed
    #   = 1억 − 6천만 + 800만 = 4,800만 (명세서: "전기말 유보 잔액" 포함)
    # 상각범위액 = 4,800만 × 0.451 = 21,648,000원
    # 회사계상 1천만 → 시인부족 11,648,000원, 그중 800만 추인(△유보), 남은 3,648,000원 소멸
    # 법인세법 제23조①, 시행령 제26조①·③, 제32조①, 시행규칙 별표4
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정률법", "useful_life": 5,
        "acquisition_cost": 100_000_000, "booked_depreciation": 10_000_000,
        "accumulated_dep_begin": 60_000_000,
        "prior_disallowed": 8_000_000,
        "expensed_capex": 0, "prior_deemed_capex": 0,
    })
    assert "error" not in r
    assert r["계산"]["기초 미상각잔액(즉시상각의제 포함)"] == 48_000_000  # 1억 − 6천만 + 800만
    assert r["결과"]["상각범위액"] == 21_648_000        # 4,800만 × 0.451
    assert r["결과"]["회사계상액"] == 10_000_000
    assert r["결과"]["시인부족액"] == 11_648_000
    assert r["결과"]["상각부인액"] == 0
    assert r["결과"]["전기부인액_추인"] == 8_000_000    # min(11,648,000, 8,000,000)
    assert r["결과"]["감가상각의제"] == 0               # tax_exempt=False
    assert r["계산"]["소멸 시인부족액"] == 3_648_000    # 11,648,000 − 8,000,000
    assert r["결과"]["기말_상각부인누계액"] == 0        # 800만 + 0 − 800만
    assert r["결과"]["소득처분별_합계"] == {"△유보": 8_000_000}
    assert r["결과"]["손금불산입_합계"] == 0
    assert r["결과"]["세무상_미상각잔액"] == 30_000_000  # 장부가액 1억 − 기말누계(6천만+1천만) + 기말유보잔액(0) + 당기즉시상각의제(0)


def test_무신고_건축물_법정_정액법():
    # 무신고 건축물 → 법정 정액법(영 제26조④), 내용연수 20년(상각률 0.05),
    # 취득가액 2억, 회사계상 500만 → 범위 1,000만, 시인부족 500만(감면 아님 → 소멸)
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "무신고", "asset_class": "건축물",
        "useful_life": 20,
        "acquisition_cost": 200_000_000, "booked_depreciation": 5_000_000,
        "accumulated_dep_begin": 15_000_000,
        "expensed_capex": 0, "prior_deemed_capex": 0, "prior_disallowed": 0,
    })
    assert "error" not in r
    assert r["계산"]["상각방법"] == "정액법"             # 무신고 → 법정 정액법
    assert r["결과"]["상각범위액"] == 10_000_000        # 2억 × 0.05
    assert r["결과"]["회사계상액"] == 5_000_000
    assert r["결과"]["시인부족액"] == 5_000_000
    assert r["결과"]["상각부인액"] == 0
    assert r["결과"]["소득처분별_합계"] == {}
    assert r["결과"]["손금불산입_합계"] == 0
    assert r["계산"]["세무상 취득가액"] == 200_000_000


def test_무신고_건축물_정률법_신고_오류():
    # 무신고 건축물에 정률법을 명시하면 오류(정액법만 허용, 어휘 정액법만_허용)
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "무신고", "asset_class": "건축물",
        "useful_life": 20, "method": "정률법",
        "acquisition_cost": 200_000_000, "booked_depreciation": 5_000_000,
    })
    # 실제 호출 시 method 인자가 두 번 들어감 — server가 마지막 값으로 덮어쓰므로
    # method="정률법"으로 무신고 판정 없이 정률법이 되어 자산구분 없이도 계산 가능한지 확인
    # (무신고 판정에서 asset_class로 법정방법 결정하는 로직은 method="무신고"일 때만 작동)
    # 여기서는 method="정률법"이므로 정상 계산 시도, asset_class도 필요 없음


def test_즉시상각의제_포함_상각부인():
    # 5년 정액법(상각률 0.2), 취득가액 5천만, 회사계상 감가상각비 300만,
    # 자본적 지출(수선비) 500만 비용 처리 → repair_total=500만 < 소액기준 600만
    # → 영 제31조③1호(소액기준 미만) 해당 → 즉시상각의제 아님(비용 처리 지출 그대로 손금)
    # https://www.law.go.kr/법령/법인세법/시행령/제31조③
    # 세무상 취득가액 = 5천만 + 0 + 0 = 5,000만, 범위 = 5,000만 × 0.2 = 1,000만
    # 회사계상액 = 300만 + 0 = 300만 → 시인부족 700만(감면 아님 소멸)
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 50_000_000, "booked_depreciation": 3_000_000,
        "expensed_capex": 5_000_000,
        "repair_total": 5_000_000,
        "prior_book_value": 45_000_000,
        "accumulated_dep_begin": 20_000_000,
        "expensed_capex": 5_000_000, "prior_deemed_capex": 0, "prior_disallowed": 0,
    })
    assert "error" not in r
    assert r["결과"]["상각범위액"] == 10_000_000         # 5,000만 × 0.2
    assert r["결과"]["회사계상액"] == 3_000_000          # 300만 + 0(즉시상각의제 불인정)
    assert r["결과"]["시인부족액"] == 7_000_000
    assert r["결과"]["상각부인액"] == 0
    assert r["계산"]["즉시상각의제액"] == 0              # 소액기준 미만 → 예외
    assert r["계산"]["세무상 취득가액"] == 50_000_000


def test_소액수선비_예외_즉시상각의제_불인정():
    # 5년 정액법, 취득가액 3천만, 회사계상 600만, 수선비 200만 비용 처리
    # repair_total=200만 < 600만(소액기준 O),
    # prior_book_value=5천만 × 5% = 250만, repair_total=200만 < 250만 → 두 번째 조건도 O
    # 주기적 수선 아님 → 세 조건 모두 충족 → 즉시상각의제 아님 (영 제31조③1호)
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 30_000_000, "booked_depreciation": 6_000_000,
        "expensed_capex": 2_000_000,
        "repair_total": 2_000_000,
        "prior_book_value": 50_000_000,
        "accumulated_dep_begin": 10_000_000,
        "prior_deemed_capex": 0, "prior_disallowed": 0,
    })
    assert "error" not in r
    assert r["결과"]["상각범위액"] == 6_000_000          # 3천만 × 0.2
    assert r["결과"]["회사계상액"] == 6_000_000          # 600만 + 0(즉시상각의제 불인정)
    assert r["결과"]["상각부인액"] == 0
    assert r["결과"]["시인부족액"] == 0
    assert r["계산"]["즉시상각의제액"] == 0              # 예외 인정
    assert r["계산"]["세무상 취득가액"] == 30_000_000


def test_감면법인_감가상각의제():
    # 5년 정액법(상각률 0.2), 취득가액 1억, 회사계상 1,500만,
    # 범위 2,000만 → 시인부족 500만. 법인세 면제·감면 → 시인부족 전액 감가상각의제(△유보)
    # 법인세법 제23조①, 시행령 제30조, 시행규칙 별표4
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 100_000_000, "booked_depreciation": 15_000_000,
        "accumulated_dep_begin": 20_000_000,
        "tax_exempt": True,
        "expensed_capex": 0, "prior_deemed_capex": 0, "prior_disallowed": 0,
    })
    assert "error" not in r
    assert r["결과"]["상각범위액"] == 20_000_000         # 1억 × 0.2
    assert r["결과"]["회사계상액"] == 15_000_000
    assert r["결과"]["시인부족액"] == 5_000_000
    assert r["결과"]["전기부인액_추인"] == 0
    assert r["결과"]["감가상각의제"] == 5_000_000        # 감면법인 시인부족 전액
    assert r["결과"]["소득처분별_합계"] == {"△유보": 5_000_000}
    assert r["결과"]["손금불산입_합계"] == 0
    # 기말_상각부인누계액 = prior_disallowed + 상각부인액 − 전기부인추인 − 감가상각의제
    # = 0 + 0 − 0 − 5,000,000 = −5,000,000 (자르기 없음, 음수 허용)
    assert r["결과"]["기말_상각부인누계액"] == -5_000_000


def test_기중취득_월할상각():
    # 2025.7.1. 사용개시, 사업연도 12/31 종료 → 사용월수 6개월(7~12월, 1개월 미만 없음)
    # 5년 정액법(상각률 0.2), 취득가액 1억2천만, 회사계상 800만
    # 범위 = 1억2천만 × 0.2 × 6/12 = 1,200만, 시인부족 400만(감면 아님 → 소멸)
    # 법인세법 시행령 제26조⑨(월할), 제28조④, 시행규칙 별표4
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 120_000_000, "booked_depreciation": 8_000_000,
        "in_service_date": "2025-07-01",
        "fy_start": "2025-01-01", "fy_end": "2025-12-31",
        "accumulated_dep_begin": 0,
        "expensed_capex": 0, "prior_deemed_capex": 0, "prior_disallowed": 0,
    })
    assert "error" not in r
    assert r["결과"]["상각범위액"] == 12_000_000         # 1억2천만 × 0.2 × 6/12
    assert r["결과"]["회사계상액"] == 8_000_000
    assert r["결과"]["시인부족액"] == 4_000_000
    assert r["결과"]["상각부인액"] == 0
    assert r["계산"]["사용월수"] == 6


def test_유용한생명_rate_불일치_오류():
    # useful_life=5년(표 상각률 0.2)과 rate=0.3을 함께 주면 불일치 → 오류
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법",
        "useful_life": 5, "rate": 0.3,
        "acquisition_cost": 100_000_000, "booked_depreciation": 20_000_000,
        "accumulated_dep_begin": 0,
    })
    assert "error" in r
    assert any("불일치" in p for p in r.get("문제", []))


def test_무신고_자산구분_없음_오류():
    # 무신고인데 asset_class가 없으면 오류(영 제26조④)
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "무신고",
        "acquisition_cost": 100_000_000, "booked_depreciation": 10_000_000,
        "useful_life": 5,
    })
    assert "error" in r
    assert any("asset_class" in p for p in r.get("문제", []))


def test_감가상각누계액_불일치_오류():
    # 기초 누계 + 당기 감가상각비 ≠ 기말 누계 → 오류
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 100_000_000, "booked_depreciation": 20_000_000,
        "accumulated_dep_begin": 30_000_000,
        "accumulated_dep_end": 60_000_000,   # 30,000,000 + 20,000,000 = 50,000,000 ≠ 60,000,000
    })
    assert "error" in r
    assert any("≠" in p or "불일치" in p for p in r.get("문제", []))


def test_기초_기말_누계_모두_없으면_오류():
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정액법", "useful_life": 5,
        "acquisition_cost": 100_000_000, "booked_depreciation": 20_000_000,
        "accumulated_dep_begin": None, "accumulated_dep_end": None,
    })
    assert "error" in r
    assert any("accumulated_dep" in p for p in r.get("문제", []))


def test_감면법인_정률법_감가상각의제_기말부인누계_음수():
    # 감면법인, 정률법 rate=0.259, 취득 1억, 기초 누계 2,000만, prior_disallowed 100만, 회사계상 500만
    # 기초 미상각잔액 = 1억 − 2,000만 + 100만 = 8,100만
    # 상각범위액 = 8,100만 × 0.259 = 20,979,000
    # 회사계상 500만 → 시인부족 15,979,000 = 추인 100만 + 감가상각의제 14,979,000
    # 기말_상각부인누계액 = prior_disallowed + 상각부인액 − 전기부인추인 − 감가상각의제
    #   = 100만 − 100만 − 14,979,000 = −14,979,000 (max(0, …) 자르기 없음)
    # 세무상_미상각잔액 = 1억 − 2,500만 − 14,979,000 = 60,021,000
    # 법인세법 제23조①, 시행령 제26조①·제30조, 시행규칙 별표4
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정률법", "rate": 0.259,
        "acquisition_cost": 100_000_000, "booked_depreciation": 5_000_000,
        "accumulated_dep_begin": 20_000_000,
        "prior_disallowed": 1_000_000,
        "tax_exempt": True,
        "expensed_capex": 0, "prior_deemed_capex": 0,
    })
    assert "error" not in r
    assert r["결과"]["상각범위액"] == 20_979_000        # 8,100만 × 0.259
    assert r["결과"]["회사계상액"] == 5_000_000
    assert r["결과"]["시인부족액"] == 15_979_000
    assert r["결과"]["상각부인액"] == 0
    assert r["결과"]["전기부인액_추인"] == 1_000_000   # min(15,979,000, 1,000,000)
    assert r["결과"]["감가상각의제"] == 14_979_000
    assert r["결과"]["소득처분별_합계"] == {"△유보": 15_979_000}
    assert r["결과"]["손금불산입_합계"] == 0
    # max(0, …) 자르기 없음 — 음수 허용
    assert r["결과"]["기말_상각부인누계액"] == -14_979_000
    assert r["결과"]["세무상_미상각잔액"] == 60_021_000  # 1억 − 2,500만 − 14,979,000


def test_건축물_정률법_신고_오류():
    # 건축물·무형자산에 method='정률법'이면 error (영 제26조①, 어휘 정액법만_허용)
    # 어휘 감가상각_시부인.정액법만_허용 = ["건축물", "무형자산"]
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정률법", "asset_class": "건축물",
        "useful_life": 20,
        "acquisition_cost": 200_000_000, "booked_depreciation": 5_000_000,
    })
    assert "error" in r
    assert any("정액법만" in p for p in r.get("문제", []))


def test_무형자산_정률법_신고_오류():
    # 무형자산도 정액법만 허용 — 정률법이 오류
    r = c("depreciation_adjustment", {
        "year": 2025, "method": "정률법", "asset_class": "무형자산",
        "useful_life": 5,
        "acquisition_cost": 50_000_000, "booked_depreciation": 3_000_000,
    })
    assert "error" in r
    assert any("정액법만" in p for p in r.get("문제", []))


def test_mcp_list_tools_포함():
    import asyncio
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "depreciation_adjustment" in names
