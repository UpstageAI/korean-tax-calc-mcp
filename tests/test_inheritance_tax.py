"""상속세 계산(inheritance_tax) 정답 테스트 — 손계산·조문 대조 사례."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def c_or_exc(tool, a):
    """오류가 dict로 오든 예외로 오든 문자열로 돌려준다."""
    try:
        return json.dumps(c(tool, a), ensure_ascii=False)
    except Exception as e:  # 도구 호출 단계 검증 오류
        return "EXC " + str(e)


def is_err(r):
    return isinstance(r, dict) and "error" in r


# 상증법 제13조·제14조·영 제9조②(봉안 500만 한도)·제19조①(한도식, 영 제17조①)·제21조①·제22조①·제24조·제25조·제26조·제69조①(3%)
# 과세가액 = 21억 − (1천만+800만+500만+2억) + 1억 = 1,977,000,000
# 배우자 한도 = (18.9억 + 1억) × 3/7 = 852,857,142 → 실제 8억 / 공제 5억+8억+6천만 = 13.6억
# 과세표준 = 19.77억 − 13.6억 − 300만 = 6.14억 → 산출 9천만 + 1.14억×30% = 124,200,000
# 신고 = (124,200,000 − 5,000,000) × 3% = 3,576,000 → 납부 115,624,000
def test_spouse_children_typical_2025():
    r = c("inheritance_tax", {
        "year": 2025, "estate_value": 2000 * M, "deemed_estate": 100 * M,
        "public_charges": 10 * M, "funeral_cost": 8 * M, "enshrinement_cost": 6 * M, "debts": 200 * M,
        "prior_gifts_heirs": 100 * M, "prior_gift_deductions": 50 * M,
        "spouse": {"actual": 800 * M, "legal_share": "3/7"}, "children": 2,
        "net_financial_assets": 300 * M, "appraisal_fee": 3 * M, "gift_tax_credit": 5 * M})
    res, calc = r["결과"], r["계산"]
    assert res["과세가액"] == 1_977_000_000
    assert calc["장례비용"] == 13 * M
    assert calc["배우자공제_한도"] == 852_857_142
    assert calc["배우자상속공제"] == 800 * M
    assert calc["인적공제_적용액"] == 500 * M and calc["일괄공제_적용"] is True
    assert calc["금융재산상속공제"] == 60 * M
    assert calc["공제적용한도"] == 1_927_000_000
    assert res["상속공제_합계"] == 1_360_000_000
    assert res["과세표준"] == 614_000_000
    assert res["산출세액"] == 124_200_000
    assert res["신고세액공제"] == 3_576_000
    assert res["납부할세액"] == 115_624_000


# 상증법 제69조① 신고세액공제율: 2016 10%, 2017 7%(2016.12.20 개정), 2018 5%(2017.12.19 개정 부칙 제8조), 2019~ 3%
# 과세가액 = 15억 − 장례 최소 500만 = 1,495,000,000, 일괄 5억 → 과세표준 995,000,000 → 산출 9천만 + 4.95억×30% = 238,500,000
@pytest.mark.parametrize("year,credit,payable", [
    (2016, 23_850_000, 214_650_000),
    (2017, 16_695_000, 221_805_000),
    (2018, 11_925_000, 226_575_000),
    (2025, 7_155_000, 231_345_000),
])
def test_report_credit_rate_by_year(year, credit, payable):
    r = c("inheritance_tax", {"year": year, "estate_value": 1500 * M, "children": 1})
    res = r["결과"]
    assert res["과세가액"] == 1_495_000_000
    assert res["과세표준"] == 995_000_000
    assert res["산출세액"] == 238_500_000
    assert res["신고세액공제"] == credit
    assert res["납부할세액"] == payable


# 상증법 제21조②(배우자 단독상속 시 일괄공제 불가)·제19조①(30억 한도)·영 제9조②(장례 1천만 한도)
# 과세가액 = 40억 − 1천만 = 3,990,000,000, 공제 = 기초 2억 + 배우자 min(40억, 40억×1, 30억) = 32억
# 과세표준 7.9억 → 산출 9천만 + 2.9억×30% = 177,000,000, 신고 3% 5,310,000, 납부 171,690,000
def test_sole_spouse_heir_no_lump_sum_2024():
    r = c("inheritance_tax", {
        "year": 2024, "estate_value": 4000 * M, "funeral_cost": 12 * M,
        "spouse": {"actual": 4000 * M, "legal_share": "1/1"}, "sole_spouse_heir": True})
    res, calc = r["결과"], r["계산"]
    assert calc["장례비용"] == 10 * M
    assert calc["인적공제_적용액"] == 200 * M and calc["일괄공제_적용"] is False
    assert calc["배우자상속공제"] == 3000 * M
    assert res["상속공제_합계"] == 3200 * M
    assert res["과세표준"] == 790 * M
    assert res["산출세액"] == 177 * M
    assert res["신고세액공제"] == 5_310_000
    assert res["납부할세액"] == 171_690_000


# 추정상속(상증법 제15조①, 영 제11조④): 부동산 1년 3억 중 용도불명 1억 − min(6천만, 2억) = 4천만, 현금 2년 4억은 5억 미만 → 0
# 인적(제20조①③): 2억 + 자녀 3×5천만 + 미성년 7.3년→8년·12년 = 2억 + 65세 5천만 = 6억 > 5억
# 동거주택(제23조의2, 2020~): (7억 − 담보 6천만) × 100% = 6.4억 → 한도 6억 / 금융 1,500만 전액
CASE_D = {
    "estate_value": 3000 * M,
    "presumed_items": [
        {"kind": "부동산", "window": "1년", "amount": 300 * M, "unexplained": 100 * M},
        {"kind": "현금·예금·유가증권", "window": "2년", "amount": 400 * M, "unexplained": 300 * M},
    ],
    "debts": 100 * M, "children": 3, "minors": [7.3, 12], "seniors": 1,
    "cohabiting_house": {"value": 700 * M, "secured_debt": 60 * M},
    "net_financial_assets": 15 * M,
}


# 과세가액 = 30.4억 − 1.05억 = 2,935,000,000, 공제 6억+6억+1,500만 = 1,215,000,000
# 과세표준 1,720,000,000 → 산출 2.4억 + 7.2억×40% = 528,000,000, 신고 15,840,000, 납부 512,160,000
def test_presumed_assets_cohabiting_house_minors_2023():
    r = c("inheritance_tax", {"year": 2023, **CASE_D})
    res, calc = r["결과"], r["계산"]
    assert res["추정상속재산"] == 40 * M
    assert res["과세가액"] == 2_935_000_000
    assert calc["그밖의인적공제"] == 400 * M
    assert calc["인적공제_적용액"] == 600 * M and calc["일괄공제_적용"] is False
    assert calc["동거주택상속공제"] == 600 * M
    assert calc["금융재산상속공제"] == 15 * M
    assert res["상속공제_합계"] == 1_215_000_000
    assert res["과세표준"] == 1_720_000_000
    assert res["산출세액"] == 528 * M
    assert res["신고세액공제"] == 15_840_000
    assert res["납부할세액"] == 512_160_000


# 동거주택 2017~2019 상속개시분: 80%·한도 5억(2016.12.20 개정) → 6.4억×80% = 5.12억 → 5억
# 공제 1,115,000,000 → 과세표준 1,820,000,000 → 산출 568,000,000, 신고 17,040,000, 납부 550,960,000
def test_cohabiting_house_80pct_cap_2019():
    r = c("inheritance_tax", {"year": 2019, **CASE_D})
    res, calc = r["결과"], r["계산"]
    assert calc["동거주택상속공제"] == 500 * M
    assert res["상속공제_합계"] == 1_115_000_000
    assert res["과세표준"] == 1_820_000_000
    assert res["산출세액"] == 568 * M
    assert res["납부할세액"] == 550_960_000


# 상증법 제21조① 단서: 신고 없으면 5억 공제(인적 6억이어도), 제69조① 신고세액공제 없음
def test_no_filing_forces_lump_sum_and_no_credit():
    r = c("inheritance_tax", {"year": 2023, **CASE_D, "filed": False})
    res, calc = r["결과"], r["계산"]
    assert calc["인적공제_적용액"] == 500 * M
    assert res["상속공제_합계"] == 1_115_000_000
    assert res["산출세액"] == 568 * M
    assert res["신고세액공제"] == 0
    assert res["납부할세액"] == 568 * M


# 상증법 제24조 공제 적용 한도: 11.95억 − 비상속인 유증 3억 − (사전증여 2억 − 공제 5천만) = 745,000,000
# 공제 전 일괄 5억 + 배우자 최소 5억(제19조④) = 10억 → 7.45억으로 제한
# 배우자 한도 = (10억 − 3억 + 0) × 3/5 = 420,000,000 / 과세표준 4.5억 → 산출 1천만 + 3.5억×20% = 80,000,000
# 신고 (8천만 − 2천만) × 3% = 1,800,000 → 납부 58,200,000
def test_deduction_limit_article24_2025():
    r = c("inheritance_tax", {
        "year": 2025, "estate_value": 1000 * M, "funeral_cost": 5 * M,
        "bequest_to_non_heirs": 300 * M, "prior_gifts_others": 200 * M, "prior_gift_deductions": 50 * M,
        "children": 1, "spouse": {"actual": 0, "legal_share": "3/5"}, "gift_tax_credit": 20 * M})
    res, calc = r["결과"], r["계산"]
    assert res["과세가액"] == 1_195_000_000
    assert calc["배우자공제_한도"] == 420 * M
    assert calc["배우자상속공제"] == 500 * M
    assert calc["상속공제_한도전"] == 1000 * M
    assert calc["공제적용한도"] == 745 * M
    assert res["상속공제_합계"] == 745 * M
    assert res["과세표준"] == 450 * M
    assert res["산출세액"] == 80 * M
    assert res["신고세액공제"] == 1_800_000
    assert res["납부할세액"] == 58_200_000


# 상증법 제25조② 과세최저한: 505,400,000 − 장례 500만 − 일괄 5억 = 400,000 < 50만 → 세액 0
def test_minimum_threshold_under_500k():
    r = c("inheritance_tax", {"year": 2025, "estate_value": 505_400_000})
    res = r["결과"]
    assert res["과세표준"] == 400_000
    assert res["산출세액"] == 0
    assert res["납부할세액"] == 0
    assert r["판단"]["과세최저한"] is True


# 상증법 제21조②: 배우자 단독상속인데 배우자 정보 없음 / 제19조①: 법정상속분은 0 초과 1 이하 분수 → 계산하지 않음
@pytest.mark.parametrize("extra,word", [
    ({"sole_spouse_heir": True}, "spouse"),
    ({"spouse": {"actual": 600 * M, "legal_share": "4/3"}, "children": 1}, "legal_share"),
])
def test_invalid_spouse_input_is_error(extra, word):
    r = c("inheritance_tax", {"year": 2025, "estate_value": 1000 * M, **extra})
    assert is_err(r)
    assert word in json.dumps(r, ensure_ascii=False)


# 정의되지 않은 인자 거부(공통)
def test_unknown_arg_rejected():
    s = c_or_exc("inheritance_tax", {"year": 2025, "estate_value": 1000 * M, "lump_sum": True})
    assert "lump_sum" in s
