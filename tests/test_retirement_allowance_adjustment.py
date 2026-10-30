import asyncio, json

from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def test_tool_registered():
    """retirement_allowance_adjustment가 mcp.list_tools()에 등록되어 있는지 확인."""
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "retirement_allowance_adjustment" in names


def test_no_adjustment_basis_only():
    """사례1: 기초 잔액만 있고 당기 설정·지급 없음 → 세무조정 없음.
    법인세법 제33조①·시행령 제60조①·②: 한도 계산 대상(당기 설정)이 없으므로
    한도초과·손금조정 모두 발생하지 않음. 세무상 잔액은 기초−부인누계."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 100_000_000, "closing": 100_000_000},
        "prior_disallowed": 20_000_000,
    })
    assert r["결과"]["소득금액_순영향"] == 0
    assert r["결과"]["세무조정"] == []
    assert r["계산"]["세무상_설정전잔액"] == 80_000_000  # 100,000,000 − 20,000,000
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 20_000_000


def test_overlimit_disallowance():
    """사례2: 당기 설정액 1억, 한도 0원(2016년 이후 적립비율 0%) → 전액 손금불산입·유보.
    법인세법 제33조①: 손비 계상한 퇴직급여충당금 중 한도를 초과하는 금액은 손금불산입.
    법인세법 시행령 제60조②: 2016.1.1. 이후 개시 사업연도 적립비율 100분의 0 → 추계액 기준 한도 0.
    법인세법 시행령 제60조①: 총급여 기준 한도 = 대상 총급여 × 5%.
      대상 총급여 = 200,000,000 − 0 − 0 = 200,000,000 → 한도 10,000,000.
    min(10,000,000, 0) = 0 → 한도초과 100,000,000원 전액 손금불산입(유보)."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 200_000_000,
            "provision": 100_000_000,
        },
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 500_000_000},
        "salary": {"total": 200_000_000},
    })
    assert r["결과"]["소득금액_순영향"] == 100_000_000
    assert r["결과"]["손금불산입_합계"] == 100_000_000
    assert r["계산"]["퇴직급여충당금_한도"] == 0
    assert r["계산"]["총급여기준_한도"] == 10_000_000  # 200,000,000 × 5%
    assert r["계산"]["추계액기준_한도"] == 0  # 적립비율 0% → 0
    assert len(r["결과"]["세무조정"]) == 1
    assert r["결과"]["세무조정"][0]["소득처분"] == "유보"
    assert r["결과"]["세무조정"][0]["금액"] == 100_000_000


def test_payment_disallowed_recovery():
    """사례3: 퇴직금 현금 지급 시 부인액 추인(△유적).
    법인세법 제33조②: 퇴직금은 퇴직급여충당금에서 먼저 지급한 것으로 봄.
    기본통칙 33-60…5: 지급 시 세무상 충당금과 먼저 상계, 초과분은 부인누계(유보)와 상계 → 손금산입·△유적.
    세무상 충당금 기초 = 100,000,000 − 60,000,000 = 40,000,000원.
    지급액 50,000,000원 중 40,000,000원은 세무상 충당금과 상계, 초과 10,000,000원은
    부인누계 60,000,000원과 상계 → 10,000,000원 추인(△유적).
    당기 설정(provision) 없으므로 세무상 충당금 기말 = 0."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 50_000_000,
            "paid_cash": 50_000_000,
        },
        "prior_disallowed": 60_000_000,
    })
    assert r["결과"]["소득금액_순영향"] == -10_000_000
    assert r["계산"]["부인액_추인"] == 10_000_000
    assert r["계산"]["세무상_퇴직급여충당금_기말"] == 0
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 50_000_000  # 60,000,000 − 10,000,000
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 1
    assert settlements[0]["조정"] == "손금산입"
    assert settlements[0]["소득처분"] == "△유보"
    assert settlements[0]["금액"] == 10_000_000
    assert settlements[0]["구분"] == "퇴직급여충당금(부인액 추인)"


def test_conversion_fund_and_dc_members():
    """사례4: 퇴직금전환금 + DC 설정자·지급대상 외 직원 제외 후 한도 계산.
    법인세법 시행령 제60조①: 확정기여형 설정자·지급대상 아닌 자분은 대상 총급여에서 제외.
    법인세법 시행령 제60조④: 퇴직금전환금은 누적한도에 가산.
    대상 총급여 = 300,000,000 − 50,000,000(DC) − 20,000,000(지급대상 외) = 230,000,000.
    총급여 기준 한도 = 230,000,000 × 5% = 11,500,000.
    2025년 적립비율 0% → 추계액 기준 한도 = max(0, 0 + 5,000,000 − 200,000,000) = 0.
    한도 = min(11,500,000, 0) = 0 → 설정 50,000,000 전액 손금불산입(유보)."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 200_000_000,
            "closing": 250_000_000,
            "provision": 50_000_000,
        },
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 1_000_000_000},
        "salary": {
            "total": 300_000_000,
            "dc_members": 50_000_000,
            "not_eligible": 20_000_000,
        },
        "conversion_fund": 5_000_000,
    })
    assert r["계산"]["대상_총급여"] == 230_000_000
    assert r["계산"]["총급여기준_한도"] == 11_500_000
    assert r["계산"]["추계액기준_한도"] == 0
    assert r["계산"]["퇴직급여충당금_한도"] == 0
    assert r["결과"]["세무조정"][0]["금액"] == 50_000_000


def test_pension_report_adjustment():
    """사례5: 확정급여형 퇴직연금 — 신고조정 손금산입(△유적).
    법인세법 시행령 제44조의2④: 퇴직연금 부담금 한도 = 추계액 − 기말 퇴직급여충당금 − 이전 공제 부담금.
    법인세법 시행규칙 제24조②: 이미 손금산입한 부담금 = 누계 − 당기 수령액.
    이미 손금산입한 부담금 = 50,000,000 − 0(지급 없음) = 50,000,000.
    세무상 퇴직급여충당금 기말 = 90,000,000(설정전) + 0(설정) = 90,000,000.
    추계액기준 연금한도 = 300,000,000 − 90,000,000 − 50,000,000 = 160,000,000.
    운용자산기준 연금한도 = 200,000,000 − 50,000,000 = 150,000,000.
    손금산입범위 = min(160,000,000, 150,000,000) = 150,000,000.
    book_provision=0(신고조정) → 부족 150,000,000원 손금산입·△유적."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 100_000_000, "closing": 100_000_000},
        "prior_disallowed": 10_000_000,
        "estimate": {"lump_sum": 300_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 200_000_000,
            "prior_deducted": 50_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["이미_손금산입한_부담금"] == 50_000_000
    assert r["계산"]["추계액기준_연금한도"] == 160_000_000  # 300,000,000 − 90,000,000 − 50,000,000
    assert r["계산"]["운용자산기준_연금한도"] == 150_000_000  # 200,000,000 − 50,000,000
    assert r["계산"]["퇴직연금_손금산입범위액"] == 150_000_000
    assert r["결과"]["소득금액_순영향"] == -150_000_000
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 1
    assert settlements[0]["조정"] == "손금산입"
    assert settlements[0]["소득처분"] == "△유보"
    assert settlements[0]["금액"] == 150_000_000
    assert settlements[0]["구분"] == "퇴직연금충당금"


def test_pension_payment_setoff():
    """사례6: 퇴직연금운용자산에서 지급 + 퇴직연금충당금 익금산입(유보)·퇴직급여충당금 손금산입(△유적).
    어휘 퇴직연금_지급: 퇴직연금운용자산에서 지급하고 퇴직급여충당금과 상계하면
      퇴직연금충당금 익금산입(유보)·퇴직급여충당금 손금산입(△유적) — 기본통칙 33-60…5.
    또한 퇴직연금 부담금은 신고조정 손금산입(△유적) 별도.

    세무상 충당금 설정전 = 100,000,000 − 10,000,000 = 90,000,000 (운용자산 지급 30,000,000은 세무상 퇴직연금충당금에서 빠지므로 퇴직급여충당금 세무상 잔액은 줄지 않음 — 2026-10-30 수정).
    퇴직연금: 이미 손금산입 = 50,000,000 − 30,000,000 = 20,000,000.
      추계액기준 연금한도 = 300,000,000 − 90,000,000 − 20,000,000 = 190,000,000.
      운용자산기준 연금한도 = 180,000,000 − 20,000,000 = 160,000,000.
      손금산입범위 = min(190,000,000, 160,000,000) = 160,000,000.
      book_provision=0 → 부족 160,000,000 손금산입·△유적.
    퇴직연금 지급 30,000,000원 → 퇴직연금충당금 익금산입(유보) 30,000,000 + 퇴직급여충당금 손금산입(△유적) 30,000,000.
    소득영향 = −160,000,000(연금부담) + 30,000,000(익금) − 30,000,000(충당금손금) = −160,000,000."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 70_000_000,
            "paid_pension": 30_000_000,
        },
        "prior_disallowed": 10_000_000,
        "estimate": {"lump_sum": 300_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 180_000_000,
            "prior_deducted": 50_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["세무상_설정전잔액"] == 90_000_000
    assert r["계산"]["퇴직연금충당금_상계"] == 30_000_000
    assert r["계산"]["이미_손금산입한_부담금"] == 20_000_000
    assert r["계산"]["추계액기준_연금한도"] == 190_000_000  # 300,000,000 − 90,000,000 − 20,000,000
    assert r["계산"]["운용자산기준_연금한도"] == 160_000_000  # 180,000,000 − 20,000,000
    assert r["계산"]["퇴직연금_손금산입범위액"] == 160_000_000
    assert r["계산"]["세무상_퇴직연금충당금_기말"] == 180_000_000  # 20,000,000 + 160,000,000
    assert r["결과"]["소득금액_순영향"] == -160_000_000
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 3
    adjustments = {(s["구분"], s["조정"], s["소득처분"]): s["금액"] for s in settlements}
    assert adjustments[("퇴직연금충당금", "손금산입", "△유보")] == 160_000_000
    assert adjustments[("퇴직연금충당금(지급 상계)", "익금산입", "유보")] == 30_000_000
    assert adjustments[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 30_000_000



def test_book_movement_mismatch_error():
    """사례7: 장부 증감 불일치 → error.
    opening + provision + other_increase − paid_cash − paid_pension = closing 검증.
    100,000,000 + 50,000,000 + 0 − 0 − 0 = 150,000,000 ≠ closing 200,000,000.
    estimate·salary는 provision 필요조건이므로 함께 입력해야 장부 증감 검증까지 도달."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 200_000_000,
            "provision": 50_000_000,
        },
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 500_000_000},
        "salary": {"total": 500_000_000},
    })
    assert "error" in r
    assert any("장부 증감 불일치" in msg for msg in r["문제"])


def test_missing_estimate_error():
    """사례8: provision이 있는데 estimate(lump_sum) 없음 → error, 필요 입력 제시.
    법인세법 시행령 제60조②: 추계액은 한도 계산에 필수(일시퇴직기준·보험수리기준 중 큰 금액)."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 200_000_000,
            "provision": 100_000_000,
        },
        "prior_disallowed": 0,
    })
    assert "error" in r
    assert "estimate" in r["필요 입력"][0]


def test_missing_salary_error():
    """사례9: provision이 있는데 salary(total) 없음 → error, 필요 입력 제시.
    법인세법 시행령 제60조①: 총급여 기준 한도 계산에 총급여 필요."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 200_000_000,
            "provision": 100_000_000,
        },
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 500_000_000},
    })
    assert "error" in r
    assert any("salary" in need for need in r["필요 입력"])


def test_actuarial_greater_than_lump_sum():
    """사례10: 보험수리기준이 일시퇴직기준보다 큰 경우 → 큰 금액(보험수리) 사용.
    법인세법 시행령 제60조②: 추계aab큼 = max(일시퇴직기준, 영 제44조의2④1의2 금액).
    lump_sum=200,000,000, actuarial=300,000,000 → 추계액 = 300,000,000."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 100_000_000, "closing": 100_000_000},
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 200_000_000, "actuarial": 300_000_000},
        "salary": {"total": 500_000_000},
    })
    assert r["계산"]["추계액"] == 300_000_000
    assert r["계산"]["총급여기준_한도"] == 25_000_000  # 500,000,000 × 5%


def test_2016_plus_year_accumulation_ratio_zero():
    """사례11: 2016년 이후 사업연도 적립비율 0% → 추계액 기준 한도 0.
    법인세법 시행령 제60조② 7호: 2016.1.1. 이후 개시 사업연도 100분의 0.
    어휘 '퇴직급여충당금_한도' 적용 블록(20160101~null) 판단 추계액_적립비율=0.0."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 100_000_000, "closing": 100_000_000},
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 500_000_000},
        "salary": {"total": 500_000_000},
    })
    assert r["계산"]["추계액_적립비율"] == 0.0
    assert r["계산"]["추계액기준_한도"] == 0


def test_2016_year_accumulation_ratio_zero():
    """사례12: 2016년 사업연도 적립비율 0% → 추계액 기준 한도 0.
    법인세법 시행령 제60조② 7호(2016.1.1. 이후 개시 사업연도 100분의 0).
    어휘 '퇴직급여충당금_한도' 적용 블록(20160101~null) 판단 추계액_적립비율=0.0.
    SET문 명세: 적립비율은 어휘에서 연도로 읽고 코드 상수로 두지 않는다.
    세무상 설정전잔액이 0일 때 추계액 기준 한도 = 200,000,000 × 0% = 0."""
    r = c("retirement_allowance_adjustment", {
        "year": 2016,
        "allowance": {"opening": 0, "closing": 0},
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 200_000_000},
        "salary": {"total": 500_000_000},
    })
    assert r["계산"]["추계액_적립비율"] == 0.0
    assert r["계산"]["추계액기준_한도"] == 0  # 200,000,000 × 0%
    assert r["계산"]["총급여기준_한도"] == 25_000_000  # 500,000,000 × 5%
    assert r["계산"]["퇴직급여충당금_한도"] == 0  # min(25,000,000, 0)


def test_dc_transferred_allowance_pension_limit():
    """사례13: DC 전환자의 설정 전 기계상 퇴직급여충당금 → 퇴직연금 연금한도 차감.
    확정기여형 전환자의 설정 전 기계상 퇴직급여충당금이 있으면
    추계액기준 연금한도 계산 시 차감(퇴직연금 한도 확대 효과).
    dc_transferred_allowance=20,000,000, 세무상 충당금 기말=90,000,000 →
    연금한도 = 300,000,000 − (90,000,000 − 20,000,000) = 230,000,000."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 100_000_000, "closing": 100_000_000},
        "prior_disallowed": 10_000_000,
        "estimate": {"lump_sum": 300_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 200_000_000,
            "prior_deducted": 50_000_000,
            "book_provision": 0,
            "dc_transferred_allowance": 20_000_000,
        },
    })
    assert r["계산"]["추계액기준_연금한도"] == 180_000_000  # 300,000,000 − (90,000,000 − 20,000,000) − 50,000,000


def test_pension_book_provision_exceed_limit():
    """사례14: 확정급여형 퇴직연금 — 결산 계상이 손금산입범위 초과 → 초과분 손금불산입·유보.
    손금산입범위 = min(추계액기준, 운용자산기준) − 이미 손금산입 부담금.
    book_provision 200,000,000 > 손금산입범위 150,000,000 → 초과 50,000,000 손금불산입·유보.
    세무상 퇴직급여충당금 기말 = 90,000,000(= 100,000,000 − 10,000,000)
      → 추계액기준 연금한도 = 300,000,000 − 90,000,000 − 50,000,000 = 160,000,000.
    운용자산기준 연금한도 = 200,000,000 − 50,000,000 = 150,000,000.
    이미 손금산입 부담금 = 50,000,000 − 0 = 50,000,000.
    손금산입범위 = min(160,000,000, 150,000,000) = 150,000,000.
    초과 = 200,000,000 − 150,000,000 = 50,000,000 → 손금불산입(유보)."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 100_000_000, "closing": 100_000_000},
        "prior_disallowed": 10_000_000,
        "estimate": {"lump_sum": 300_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 200_000_000,
            "prior_deducted": 50_000_000,
            "book_provision": 200_000_000,  # 손금산입범위 150,000,000 초과
        },
    })
    assert r["계산"]["퇴직연금_손금산입범위액"] == 150_000_000
    assert r["계산"]["추계액기준_연금한도"] == 160_000_000  # 300,000,000 − 90,000,000 − 50,000,000
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 1
    over = settlements[0]
    assert over["조정"] == "손금불산입"
    assert over["금액"] == 50_000_000  # 200,000,000 − 150,000,000
    assert over["구분"] == "퇴직연금충당금 한도초과"
    assert over["소득처분"] == "유보"


def test_fix2d_example1_pension_payment_excess():
    """paid_pension 3,000만 > prior_deducted 1,000만, 세무상 잔액 1,200만.
    연금상계 = min(30,000,000, 10,000,000) = 10,000,000 →
      퇴직연금충당금(지급 상계) 익금산입(유보) 10,000,000 +
      퇴직급여충당금(퇴직연금 지급 대체) 손금산입(△유보) 10,000,000.
    충당금 지급액 = 0 + (30,000,000 − 10,000,000) = 20,000,000.
    퇴직급여충당금_상계 = min(20,000,000, 12,000,000) = 12,000,000 (세무조정 없음).
    부인액 추인 = min(20,000,000 − 12,000,000, 20,000,000) = 8,000,000 → 손금산입(△유보).
    퇴직연금: 자산 5,000만, prior_deducted 1,000만, book_provision 0 →
      이미 손금산입 부담금 = 0,chnitt기준 연금한도 = 100,000,000 − 0 − 0 = 100,000,000,
      운용자산기준 연금한도 = 50,000,000 − 0 = 50,000,000,
      손금산입범위 = 50,000,000 → 부족 50,000,000 손금산입·△유보.
    소득영향 = 10,000,000 − (10,000,000 + 8,000,000 + 50,000,000) = −58,000,000.
    퇴직급여충당금_유보_기말 = 20,000,000 + 0 + 0 − 8,000,000 − 10,000,000(연금 지급 대체) = 2,000,000."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 32_000_000,
            "closing": 2_000_000,
            "paid_pension": 30_000_000,
        },
        "prior_disallowed": 20_000_000,
        "estimate": {"lump_sum": 100_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 50_000_000,
            "prior_deducted": 10_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["퇴직연금충당금_상계"] == 10_000_000   # min(30M, 10M)
    assert r["계산"]["퇴직급여충당금_상계"] == 12_000_000  # min(20M, 12M)
    assert r["계산"]["부인액_추인"] == 8_000_000          # min(8M, 20M)
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 2_000_000  # 20M + 0 + 0 − 8M − 10M(연금 대체)
    assert r["결과"]["소득금액_순영향"] == -58_000_000    # 10M − (10M+8M+50M)
    settlements = r["결과"]["세무조정"]
    adjustments = {(s["구분"], s["조정"], s["소득처분"]): s["금액"] for s in settlements}
    assert adjustments[("퇴직연금충당금(지급 상계)", "익금산입", "유보")] == 10_000_000
    assert adjustments[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 10_000_000
    assert adjustments[("퇴직연금충당금", "손금산입", "△유보")] == 50_000_000
    assert adjustments[("퇴직급여충당금(부인액 추인)", "손금산입", "△유보")] == 8_000_000


def test_fix2e_example_pension_payment_setoff():
    """paid_pension 2,500만 > prior_deducted 1,500만, 세무상 잔액 800만.
    세무상 잔액(세무_기초_잔액) = opening − prior_disallowed = 33,000,000 − 25,000,000 = 8,000,000.
    연금상계 = min(25,000,000, 15,000,000) = 15,000,000 →
      퇴직연금충당금(지급 상계) 익금산입(유보) 15,000,000 +
      퇴직급여충당금(퇴직연금 지급 대체) 손금산입(△유보) **15,000,000**.
    충당금 지급액 = 0 + (25,000,000 − 15,000,000) = 10,000,000.
    퇴직급여충당금_상계 = min(10,000,000, 8,000,000) = 8,000,000 (세무조정 없음).
    부인액 추인 = min(10,000,000 − 8,000,000, 25,000,000) = 2,000,000 → 손금산입(△유보).
    퇴직연금 충당금 손금산입(20,000,000)을 포함한 소득금액_순영향 = 15M − (15M+20M+2M) = −22M.
    퇴직급여충당금_상계(800만)는 세무조정이 아니며, 지급 대체 손금산입 금액은 연금상계(1,500만)임."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 33_000_000,
            "closing": 8_000_000,
            "paid_pension": 25_000_000,
        },
        "prior_disallowed": 25_000_000,
        "estimate": {"lump_sum": 500_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 20_000_000,
            "prior_deducted": 15_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["퇴직연금충당금_상계"] == 15_000_000   # min(25M, 15M)
    assert r["계산"]["퇴직급여충당금_상계"] == 8_000_000    # min(10M, 8M)
    assert r["계산"]["부인액_추인"] == 2_000_000           # min(2M, 25M)
    assert r["결과"]["소득금액_순영향"] == -22_000_000     # 15M − (15M+20M+2M)
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 8_000_000  # 25M + 0 + 0 − 2M − 15M(연금 대체)
    settlements = r["결과"]["세무조정"]
    adjustments = {(s["구분"], s["조정"], s["소득처분"]): s["금액"] for s in settlements}
    # 퇴직급여충당금(퇴직연금 지급 대체) 금액이 Ana연금충당금_상계액(1,500만)이어야 함
    assert adjustments[("퇴직연금충당금(지급 상계)", "익금산입", "유보")] == 15_000_000
    assert adjustments[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 15_000_000
    assert adjustments[("퇴직연금충당금", "손금산입", "△유보")] == 20_000_000
    assert adjustments[("퇴직급여충당금(부인액 추인)", "손금산입", "△유보")] == 2_000_000


def test_fix2f_example2_pension_payment_setoff():
    """paid_pension 2,000만, prior_deducted 1,200만, opening 5,000만,
    prior_disallowed 4,500만. 연금상계 1,200만, 부인액 추인 300만.
    근속연수 적립비율 0%(2025) → 추계액기준 한도 기여 없음.
    pension.asset_closing 1억, book_provision 0 →
      이미 손금산입 부담금 = 1,200만 − 1,200만 = 0.
      추계액을_기준으로 연금한도 = 1억 − (3,000만 − 0) − 0 = 7,000만.
      운용자산기준 연금한도 = 1억 − 0 = 1억.
      손금산입범위 = 7,000만 → 부족 7,000만 손금산입·△유보, 기말 7,000만.
    퇴직급여충당금_유보_기말 = 4,500만 + 0 + 0 − 300만 − 1,200만(연금 지급 대체) = 3,000만."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 50_000_000,
            "closing": 30_000_000,   # 50M − 20M(paid_pension)
            "paid_pension": 20_000_000,
        },
        "prior_disallowed": 45_000_000,
        "estimate": {"lump_sum": 100_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 100_000_000,
            "prior_deducted": 12_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["퇴직연금충당금_상계"] == 12_000_000      # min(20M, 12M)
    assert r["계산"]["퇴직급여충당금_상계"] == 5_000_000       # min(8M, 5M)
    assert r["계산"]["부인액_추인"] == 3_000_000              # min(3M, 45M)
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 30_000_000  # 45M + 0 + 0 − 3M − 12M
    assert r["계산"]["퇴직연금_손금산입범위액"] == 100_000_000   # min(100M, 100M) ; dc_조정_기말=0, 이미 손금산입=0
    assert r["계산"]["세무상_퇴직연금충당금_기말"] == 100_000_000  # 0 + 100M
    assert r["결과"]["소득금액_순영향"] == -103_000_000       # 12M − (12M+100M+3M)
    settlements = r["결과"]["세무조정"]
    adjustments = {(s["구분"], s["조정"], s["소득처분"]): s["금액"] for s in settlements}
    assert adjustments[("퇴직연금충당금(지급 상계)", "익금산입", "유보")] == 12_000_000
    assert adjustments[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 12_000_000
    assert adjustments[("퇴직연금충당금", "손금산입", "△유보")] == 100_000_000
    assert adjustments[("퇴직급여충당금(부인액 추인)", "손금산입", "△유보")] == 3_000_000


def test_fix2c_example2_succession_disallowed():
    """합병 승계 부인누계 포함, 한도초과 발생, 부인액 추인 없음.
    prior_disallowed=1,500만, succeeded_disallowed=300만, provision=200만(한도초과),
    paid_cash=0, other_increase=300만(합병 승계). 2025년 적립비율 0% →
    추계액기준 한도=0, 총급여기준 한도=500만 → 한도=0 → 한도초과 200만 손금불산입(유보).
    연금 없으므로 퇴직연금 조정 생략. 부인액 추인 = 0 (지급 없음).
    퇴직급여충당금_유보_기말 = prior_disallowed(15M) + succeeded_disallowed(3M)
      + 한도초과(2M) − 부인액_추인(0) = 20,000,000.
    ※ other_increase 300만 중 succeeded_disallowed 300만 차감되어
      세무상 설정전잔액에 net 0 영향. 장부 closing = 100M+2M+3M = 105M."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 105_000_000,
            "provision": 2_000_000,
            "other_increase": 3_000_000,
        },
        "prior_disallowed": 15_000_000,
        "succeeded_disallowed": 3_000_000,
        "estimate": {"lump_sum": 50_000_000},
        "salary": {"total": 100_000_000},
    })
    assert r["계산"]["총급여기준_한도"] == 5_000_000      # 100M × 5%
    assert r["계산"]["추계액기준_한도"] == 0              # 적립비율 0% → 0
    assert r["계산"]["퇴직급여충당금_한도"] == 0           # min(5M, 0)
    assert r["계산"]["부인액_추인"] == 0
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 20_000_000  # 15M + 3M + 2M − 0
    assert r["결과"]["소득금액_순영향"] == 2_000_000      # 2M 손금불산입
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 1
    assert settlements[0]["구분"] == "퇴직급여충당금 한도초과"
    assert settlements[0]["조정"] == "손금불산입"
    assert settlements[0]["소득처분"] == "유보"
    assert settlements[0]["금액"] == 2_000_000


def test_result_structure():
    """사례15: 출력 계약이 지정한 모든 키가 결과에 포함되는지 확인.
    결과.결과 = {세무조정, 소득처분별_합계, 손금불산입_합계, 소득금액_순영향, 가산조정, 차감조정}.
    결과.계산 = 명세 계산 키 포함."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 200_000_000,
            "provision": 100_000_000,
        },
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 500_000_000},
        "salary": {"total": 200_000_000},
    })
    required_result_keys = {
        "세무조정", "소득처분별_합계", "손금불산입_합계",
        "소득금액_순영향", "가산조정", "차감조정",
    }
    assert required_result_keys <= set(r["결과"].keys())
    required_calc_keys = {
        "세무상_퇴직급여충당금_지급전잔액", "부인액_추인", "세무상_설정전잔액",
        "대상_총급여", "총급여기준_한도", "추계액", "추계액_적립비율",
        "누적한도", "추계액기준_한도", "퇴직급여충당금_한도",
        "세무상_퇴직급여충당금_기말", "퇴직급여충당금_유보_기말",
    }
    assert required_calc_keys <= set(r["계산"].keys())
    assert "근거" in r
    assert "판단" in r
    assert "산식" in r

def test_검증2_추계1억_기말0_prior3000만_asset12000만():
    """검증2: 추계 1억, 세무상 퇴직급여충당금 기말 0, prior_deducted 3,000만, 운용자산 1.2억
    → 추계액을_기준으로_연금한도 7,000만, 운용자산기준_연금한도 9,000만, 범위 7,000만, 기말 1억."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {"opening": 0, "closing": 0},
        "prior_disallowed": 0,
        "estimate": {"lump_sum": 100_000_000},
        "salary": {"total": 1_000_000_000},
        "pension": {
            "asset_closing": 120_000_000,
            "prior_deducted": 30_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["추계액기준_연금한도"] == 70_000_000      # 100,000,000 − 0 − 30,000,000
    assert r["계산"]["운용자산기준_연금한도"] == 90_000_000   # 120,000,000 − 30,000,000
    assert r["계산"]["퇴직연금_손금산입범위액"] == 70_000_000   # min(70,000,000, 90,000,000)
    assert r["계산"]["세무상_퇴직연금충당금_기말"] == 100_000_000  # 30,000,000 + 70,000,000
    assert r["결과"]["소득금액_순영향"] == -70_000_000
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 1
    assert settlements[0]["구분"] == "퇴직연금충당금"
    assert settlements[0]["금액"] == 70_000_000


def test_검증3_기초6000만_부인누계5000만_현금지급1500만_기말4500만():
    """검증3: 기초 6,000만, 부인누계 5,000만, 현금 지급 1,500만, 기말 4,500만.
    → 퇴직급여충당금_상계 1,000만, 세무조정 퇴직급여충당금(부인액 추인) 손금산입 500만 △유보."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 60_000_000,
            "closing": 45_000_000,
            "paid_cash": 15_000_000,
        },
        "prior_disallowed": 50_000_000,
    })
    assert r["계산"]["퇴직급여충당금_상계"] == 10_000_000   # min(15,000,000, 10,000,000)
    assert r["계산"]["부인액_추인"] == 5_000_000          # min(5,000,000, 50,000,000)
    assert r["결과"]["소득금액_순영향"] == -5_000_000
    assert r["계산"]["세무상_퇴직급여충당금_기말"] == 0  # 설정전잔액 10M − 지급상계 10M = 0
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 45_000_000
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 1
    assert settlements[0]["구분"] == "퇴직급여충당금(부인액 추인)"
    assert settlements[0]["조정"] == "손금산입"
    assert settlements[0]["소득처분"] == "△유보"
    assert settlements[0]["금액"] == 5_000_000


def test_퇴직연금_지급_대체_사례():
    """퇴직연금 지급 대체 사례(개정): paid_pension 6,000만 > prior_deducted 5,000만.
    연금상계 = min(60,000,000, 50,000,000) = 50,000,000 →
      퇴직연금충당금(지급 상계) 익금산입(유보) 50,000,000 +
      퇴직급여충당금(퇴직연금 지급 대체) 손금산입(△유보) 50,000,000.
    충당금 지급액 = 0 + (60,000,000 − 50,000,000) = 10,000,000.
    퇴직급여충당금_상계 = min(10,000,000, 50,000,000) = 10,000,000 (세무조정 없음).
    부인액_추인 = min(10,000,000 − 10,000,000, 50,000,000) = 0 (세무조정 없음).
    소득영향 = 50M(익금) − 50M(연금상계 손금) − 200M(연금부담 손금) = −200M.
    퇴직연금: 이미 손금산입=0. 세무상 퇴직급여충당금 설정전 = 50M − 과세 지급 10M = 40M(연금상계 50M은 세무상 퇴직연금충당금에서 빠짐 — 2026-10-30 수정) → 추계액기준 연금한도 = 300M − 40M = 260M, 운용자산기준=200M, 범위=200M, 기말=200M."""
    r = c("retirement_allowance_adjustment", {
        "year": 2025,
        "allowance": {
            "opening": 100_000_000,
            "closing": 40_000_000,
            "paid_pension": 60_000_000,
        },
        "prior_disallowed": 50_000_000,
        "estimate": {"lump_sum": 300_000_000},
        "salary": {"total": 500_000_000},
        "pension": {
            "asset_closing": 200_000_000,
            "prior_deducted": 50_000_000,
            "book_provision": 0,
        },
    })
    assert r["계산"]["퇴직연금충당금_상계"] == 50_000_000     # min(60M, 50M)
    assert r["계산"]["퇴직급여충당금_상계"] == 10_000_000    # min(10M, 50M)
    assert r["계산"]["부인액_추인"] == 0                     # min(0, 50M)
    assert r["계산"]["퇴직급여충당금_유보_기말"] == 0        # 50M + 0 + 0 − 0 − 50M(연금 대체)
    assert r["결과"]["소득금액_순영향"] == -200_000_000     # 50M − 200M − 50M
    assert r["계산"]["이미_손금산입한_부담금"] == 0         # 50,000,000 − 50,000,000
    assert r["계산"]["추계액기준_연금한도"] == 260_000_000  # 300M − 40M − 0
    assert r["계산"]["운용자산기준_연금한도"] == 200_000_000        # 200M − 0
    assert r["계산"]["퇴직연금_손금산입범위액"] == 200_000_000   # min(300M, 200M)
    assert r["계산"]["세무상_퇴직연금충당금_기말"] == 200_000_000  # 0 + 200M
    settlements = r["결과"]["세무조정"]
    assert len(settlements) == 3
    adjustments = {(s["구분"], s["조정"], s["소득처분"]): s["금액"] for s in settlements}
    assert adjustments[("퇴직연금충당금(지급 상계)", "익금산입", "유보")] == 50_000_000
    assert adjustments[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 50_000_000
    assert adjustments[("퇴직연금충당금", "손금산입", "△유보")] == 200_000_000

def test_exam_style_pension_payout_split_between_book_allowances():
    """운용자산에서 250M 지급(장부 연금충당금 150M + 퇴직급여충당금 100M 상계), 세무상 연금충당금 기초 600M(유보 150M), 퇴직급여충당금 기초 100M(유보 20M),
    추계액 990M, 운용자산 기말 930M, 결산 계상 200M → 세무상 연금충당금 감소 250M·이미 손금산입 350M,
    세무상 퇴직급여충당금 기말 80M(장부 지급 100M은 세무상 연금충당금 몫) → 한도 min(990−80, 930) − 350 = 560M → 손금산입 360M(△유보),
    익금산입 연금충당금 100M(유보) + 손금산입 퇴직급여충당금 100M(△유보). 2026-10-30 추가(종전엔 book_paid 입력이 없어 230M으로 나왔음)."""
    r = c("retirement_allowance_adjustment", {"year": 2025, "allowance": {"opening": 100_000_000, "closing": 0, "paid_pension": 100_000_000}, "prior_disallowed": 20_000_000,
                                              "estimate": {"lump_sum": 960_000_000, "actuarial": 990_000_000},
                                              "pension": {"asset_closing": 930_000_000, "prior_deducted": 600_000_000, "book_provision": 200_000_000, "book_paid": 150_000_000}})
    adj = {(x["구분"], x["조정"], x["소득처분"]): x["금액"] for x in r["결과"]["세무조정"]}
    assert adj[("퇴직연금충당금", "손금산입", "△유보")] == 360_000_000
    assert adj[("퇴직연금충당금(지급 상계)", "익금산입", "유보")] == 100_000_000
    assert adj[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 100_000_000
    assert r["계산"]["세무상_퇴직급여충당금_기말"] == 80_000_000 and r["계산"]["이미_손금산입한_부담금"] == 350_000_000
