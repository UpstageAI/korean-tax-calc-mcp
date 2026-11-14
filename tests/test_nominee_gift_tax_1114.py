"""nominee_gift_tax — 명의신탁재산 증여의제 증여세. Claude 작성(2026-11-14).

대조한 시행본(국세법령정보시스템 연혁본): 상속세 및 증여세법 법률 제15522호(2018.9.21. 시행, 2018.12.31. 현재)·제16102호(2019.1.1.)·
제16846호(2020.1.1.)·제21219호(2026.1.1.)의 제4조의2·제45조의2·제47조·제55조·제68조, 부칙 제16102호 제3조·제6조.
- 제55조제1항제1호(명의신탁재산의 금액 − 감정평가수수료)는 2018.12.31. 시행본에도 있음 → 종전 규정 의제분도 증여재산공제 없음
  (보고서 G2의 '공제 5천만원'은 원문과 달라 고침)
- 부칙 제16102호 제6조: 2018.12.31. 이전 취득 + 해태로 2019.1.1. 이후 의제되는 분은 종전 규정(보고서 G4·G6을 고침)
세율(제26조): 1억 이하 10%, 5억 이하 20%−1천만, 10억 이하 30%−6천만, 30억 이하 40%−1억6천만, 초과 50%−4억6천만.
신고세액공제율(제69조제2항): 2016 10%, 2017 7%, 2018 5%, 2019~ 3%.
"""
from korean_tax_calc_mcp import server as S

T = S.nominee_gift_tax


def R(**k):
    r = T(**k)
    assert "결과" in r, r
    return r["결과"]


def test_boundary_2018_12_31_vs_2019_03_01():
    a = R(asset_value=500_000_000, deemed_gift_date="2019-03-01")          # G1
    assert (a["과세표준"], a["산출세액"], a["신고세액공제"], a["납부할세액"]) == (500_000_000, 90_000_000, 2_700_000, 87_300_000)
    assert a["납세의무자"] == "실제소유자" and a["적용 규정"] == "2019.1.1. 이후 체계" and a["물적납세의무"].startswith("명의자")
    b = R(asset_value=500_000_000, deemed_gift_date="2018-12-31")          # G2(고침): 공제 없음, 5%
    assert (b["증여재산공제"], b["과세표준"], b["산출세액"], b["신고세액공제"], b["납부할세액"]) == (0, 500_000_000, 90_000_000, 4_500_000, 85_500_000)
    assert b["납세의무자"] == "명의자(수증자)" and b["연대납세의무"].startswith("실제소유자") and b["물적납세의무"] == "없음"


def test_no_filing_limitation_15y():                                         # G3
    a = R(asset_value=500_000_000, deemed_gift_date="2019-03-01", filed=False)
    assert a["산출세액"] == a["납부할세액"] == 90_000_000
    assert a["법정신고기한(이월 전)"] == "2019-06-30"                         # 2019.6.30.(일) → 7.1.(월)
    lim = a["부과제척기간"]
    assert lim["제척기간(년)"] == 15 and lim["만료일(역법)"].startswith("2034-07-01") and lim["만료일"] == "2034-07-03"
    assert R(asset_value=500_000_000, deemed_gift_date="2019-03-01")["부과제척기간"]["제척기간(년)"] == 10


def test_lapse_transition_rule():
    g4 = R(asset_value=300_000_000, trust_type="명의개서해태", acquisition_date="2017-05-10")
    assert g4["증여의제일"] == "2019-01-01" and g4["평가기준일"] == "2017-05-10"
    assert g4["적용 규정"] == "종전 체계" and g4["납세의무자"] == "명의자(수증자)"    # 부칙 제16102호 제6조
    assert (g4["산출세액"], g4["신고세액공제율"], g4["납부할세액"]) == (50_000_000, 0.03, 48_500_000)
    g5 = R(asset_value=100_000_000, trust_type="명의개서해태", acquisition_date="2016-12-31")
    assert g5["증여의제일"] == "2018-01-01" and g5["적용 규정"] == "종전 체계"
    assert (g5["산출세액"], g5["신고세액공제"], g5["납부할세액"]) == (10_000_000, 500_000, 9_500_000)
    g6 = R(asset_value=100_000_000, trust_type="명의개서해태", acquisition_date="2018-06-01")
    assert g6["증여의제일"] == "2020-01-01" and g6["평가기준일"] == "2018-06-01" and g6["적용 규정"] == "종전 체계"
    g6b = R(asset_value=100_000_000, trust_type="명의개서해태", acquisition_date="2019-01-02")
    assert g6b["증여의제일"] == "2021-01-01" and g6b["적용 규정"] == "2019.1.1. 이후 체계" and g6b["납세의무자"] == "실제소유자"


def test_rates_and_fees():
    assert R(asset_value=1_000_000_000, deemed_gift_date="2026-04-01", filed=False)["산출세액"] == 240_000_000     # G7
    g8 = R(asset_value=300_000_000, deemed_gift_date="2022-05-01", appraisal_fee=5_000_000)                     # G8
    assert (g8["감정평가수수료"], g8["과세표준"], g8["산출세액"]) == (5_000_000, 295_000_000, 49_000_000)
    assert R(asset_value=300_000_000, deemed_gift_date="2022-05-01", appraisal_fee=8_000_000)["감정평가수수료"] == 5_000_000   # 한도 500만
    g9 = R(asset_value=400_000, deemed_gift_date="2021-06-01")                                                  # G9
    assert g9["과세최저한"] is True and g9["산출세액"] == 0
    g17 = R(asset_value=200_000_000, deemed_gift_date="2017-07-01")
    assert (g17["산출세액"], g17["신고세액공제"], g17["납부할세액"]) == (30_000_000, 2_100_000, 27_900_000)    # 2017 7%


def test_corporate_nominee_before_2019():
    a = R(asset_value=100_000_000, deemed_gift_date="2018-03-01", nominee_kind="영리법인")
    assert a["납세의무자"].startswith("실제소유자") and a["연대납세의무"] == "해당 없음"


def test_aggregation():
    a = R(asset_value=100_000_000, deemed_gift_date="2020-03-01", prior_gifts_same_donor=50_000_000)
    assert a["산출세액"] == 10_000_000 and "쓰지 않음" in a["합산"]
    r = T(asset_value=100_000_000, deemed_gift_date="2018-03-01", prior_gifts_same_donor=50_000_000)
    assert r["error"].startswith("확인 필요")


def test_errors():
    assert "error" in T(asset_value=100_000_000, deemed_gift_date="2015-12-31")                                  # G19
    assert "error" in T(asset_value=100_000_000, trust_type="명의개서해태")
    assert "error" in T(asset_value=100_000_000, trust_type="명의개서해태", acquisition_date="2017-05-10", deemed_gift_date="2019-02-01")
    assert "error" in T(asset_value=100_000_000, trust_type="명의개서해태", acquisition_date="2025-03-01")       # 의제일 2027-01-01
    assert "error" in T(asset_value=100_000_000)
