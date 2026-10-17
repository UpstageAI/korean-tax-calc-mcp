"""증여세 계산(gift_tax) 정답 테스트 — 손계산·조문 대조 사례."""
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


# 상증법 제47조②(직계존속은 그 배우자 포함 동일인 10년 합산)·제53조2호·제58조·제69조②(3%)
# 과세가액 3억 + 1억 = 4억, 공제 5천만 → 과세표준 3.5억 → 산출 1천만 + 2.5억×20% = 60,000,000
# 신고 (6천만 − 500만) × 3% = 1,650,000 → 납부 53,350,000
def test_recombined_gift_from_parents_2025():
    r = c("gift_tax", {"gift_date": "2025-06-01", "gift_value": 300 * M, "relation": "직계존속",
                       "prior_gifts_same_donor": 100 * M, "prior_gift_tax_paid": 5 * M})
    res = r["결과"]
    assert r["판단"]["합산여부"] is True
    assert res["과세가액"] == 400 * M
    assert res["증여재산공제"] == 50 * M
    assert res["과세표준"] == 350 * M
    assert res["산출세액"] == 60 * M
    assert res["기납부세액공제"] == 5 * M
    assert res["신고세액공제"] == 1_650_000
    assert res["납부할세액"] == 53_350_000
    assert r["판단"]["남은_공제한도"] == 0


# 상증법 제47조①(부담부증여 인수채무)·제53조1호(배우자 6억)·영 제46조의2→제20조의3③(감정수수료 500만 한도)
# 과세가액 10억 − 3억 = 7억, 과세표준 7억 − 6억 − 500만 = 95,000,000 → 산출 9,500,000, 신고 285,000, 납부 9,215,000
def test_spouse_gift_with_assumed_debt_2024():
    r = c("gift_tax", {"gift_date": "2024-03-10", "gift_value": 1000 * M, "relation": "배우자",
                       "assumed_debt": 300 * M, "appraisal_fee": 6 * M})
    res = r["결과"]
    assert res["과세가액"] == 700 * M
    assert res["증여재산공제"] == 600 * M
    assert res["감정평가수수료"] == 5 * M
    assert res["과세표준"] == 95 * M
    assert res["산출세액"] == 9_500_000
    assert res["신고세액공제"] == 285_000
    assert res["납부할세액"] == 9_215_000


# 상증법 제53조의2①(혼인 증여재산공제 1억, 2024.1.1 이후 증여분, 부칙 제19932호 제3조)
# 2억 − 5천만 − 1억 = 5천만 → 산출 5,000,000, 신고 150,000, 납부 4,850,000
def test_marriage_deduction_2024():
    r = c("gift_tax", {"gift_date": "2024-05-01", "gift_value": 200 * M, "relation": "직계존속",
                       "marriage_birth": True})
    res = r["결과"]
    assert res["증여재산공제"] == 50 * M
    assert res["혼인출산_증여재산공제"] == 100 * M
    assert res["과세표준"] == 50 * M
    assert res["산출세액"] == 5 * M
    assert res["신고세액공제"] == 150_000
    assert res["납부할세액"] == 4_850_000
    assert r["판단"]["혼인출산_남은_한도"] == 0


# 혼인·출산 공제는 2024.1.1 전 증여에는 없음 → 계산하지 않음
def test_marriage_deduction_before_2024_is_error():
    r = c("gift_tax", {"gift_date": "2023-12-01", "gift_value": 200 * M, "relation": "직계존속",
                       "marriage_birth": True})
    assert is_err(r)


# 혼인·출산 공제는 직계존속 증여만
def test_marriage_deduction_non_ascendant_is_error():
    r = c("gift_tax", {"gift_date": "2025-05-01", "gift_value": 200 * M, "relation": "배우자",
                       "marriage_birth": True})
    assert is_err(r)


# 상증법 제57조①(자녀 아닌 직계비속 30%, 미성년·20억 초과 40%)·제53조2호(미성년 2천만)
# 미성년: 21억 − 2천만 = 20.8억 → 산출 2.4억 + 10.8억×40% = 672,000,000, 할증 268,800,000, 신고 28,224,000
# 성년: 21억 − 5천만 = 20.5억 → 산출 660,000,000, 할증 198,000,000, 신고 25,740,000
@pytest.mark.parametrize("minor,deduction,tax,surcharge,credit,payable", [
    (True, 20 * M, 672 * M, 268_800_000, 28_224_000, 912_576_000),
    (False, 50 * M, 660 * M, 198 * M, 25_740_000, 832_260_000),
])
def test_generation_skip_surcharge(minor, deduction, tax, surcharge, credit, payable):
    r = c("gift_tax", {"gift_date": "2025-01-15", "gift_value": 2100 * M, "relation": "직계존속",
                       "recipient_minor": minor, "generation_skip": True})
    res = r["결과"]
    assert res["증여재산공제"] == deduction
    assert res["산출세액"] == tax
    assert res["할증세액"] == surcharge
    assert res["신고세액공제"] == credit
    assert res["납부할세액"] == payable


# 상증법 제69조② 신고세액공제율(증여일 기준): 2016 10%, 2017 7%, 2018 5%(2017.12.19 개정 부칙 제8조), 2019~ 3%
# 직계비속 증여 1.5억 − 5천만 = 1억 → 산출 10,000,000
@pytest.mark.parametrize("day,credit,payable", [
    ("2016-07-01", 1_000_000, 9_000_000),
    ("2017-07-01", 700_000, 9_300_000),
    ("2018-07-01", 500_000, 9_500_000),
    ("2019-07-01", 300_000, 9_700_000),
])
def test_report_credit_rate_by_gift_date(day, credit, payable):
    r = c("gift_tax", {"gift_date": day, "gift_value": 150 * M, "relation": "직계비속"})
    res = r["결과"]
    assert res["과세표준"] == 100 * M
    assert res["산출세액"] == 10 * M
    assert res["신고세액공제"] == credit
    assert res["납부할세액"] == payable


# 상증법 제53조4호(기타친족 1천만)·제55조②(과세표준 50만 미만 과세 안 함): 10,400,000 − 1천만 = 400,000
def test_other_relative_minimum_threshold():
    r = c("gift_tax", {"gift_date": "2022-08-01", "gift_value": 10_400_000, "relation": "기타친족"})
    res = r["결과"]
    assert res["증여재산공제"] == 10 * M
    assert res["과세표준"] == 400_000
    assert res["산출세액"] == 0
    assert res["납부할세액"] == 0
    assert r["판단"]["과세최저한"] is True


# 상증법 제53조 후단(수증자 기준 10년 내 공제 합계 한도): 조부 증여에서 3천만 공제 → 이번 부 증여 공제 2천만
# 4천만 − 2천만 = 2천만 → 산출 2,000,000, 신고 60,000, 납부 1,940,000 / 1천만 증여는 공제 1천만·남은 한도 4천만
@pytest.mark.parametrize("value,used,deduction,base,payable,left", [
    (40 * M, 30 * M, 20 * M, 20 * M, 1_940_000, 0),
    (10 * M, 0, 10 * M, 0, 0, 40 * M),
])
def test_ten_year_deduction_limit(value, used, deduction, base, payable, left):
    r = c("gift_tax", {"gift_date": "2025-02-01", "gift_value": value, "relation": "직계존속",
                       "prior_deduction_used": used})
    res = r["결과"]
    assert res["증여재산공제"] == deduction
    assert res["과세표준"] == base
    assert res["납부할세액"] == payable
    assert r["판단"]["남은_공제한도"] == left


# 정의되지 않은 인자 거부(공통)
def test_unknown_arg_rejected():
    s = c_or_exc("gift_tax", {"gift_date": "2025-02-01", "gift_value": 10 * M, "relation": "직계존속",
                              "year": 2025})
    assert "year" in s
