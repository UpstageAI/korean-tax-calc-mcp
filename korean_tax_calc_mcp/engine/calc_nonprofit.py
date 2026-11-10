"""비영리내국법인 고유목적사업준비금 손금산입 한도 계산 — 법인세법 제29조(2026.7.1 시행본).
작성 Solar Pro 4(뼈대) → Claude 검수. 조문 원문은 korean-tax-mcp로 확인.
"""
from fractions import Fraction as _Fr

from .exact import trunc_won as _trunc


def nonprofit_reserve_limit(year, interest_income, dividend_income, welfare_loan_interest=0,
                            other_income=0, reserve_booked=0, entity="일반", interest_separate_tax=False):
    """비영리내국법인 고유목적사업준비금 손금산입 한도(법인세법 제29조제1항·제5항제4호·제7항, 조세특례제한법 제74조제1항).
    year: 사업연도(2016~2026). interest_income: 이자소득(비영업대금 이익 제외, 원). dividend_income: 배당소득(원).
    welfare_loan_interest: 특별법 비영리법인 복지사업 융자이자(기본 0). other_income: 그 밖의 수익사업 소득(결손이면 음수).
    reserve_booked: 계상액(원, ≥0). entity: '일반'|'공익법인_장학'|'조특법74'(기본 '일반').
    interest_separate_tax: True면 제62조 분리과세 선택으로 이자소득을 한도에서 제외.
    반환: {이자배당등_합계, 기타수익사업_소득, 적용률, 기타분_한도, 한도, 계상액, 손금산입액, 한도초과액, 판단, 근거}"""
    if interest_income < 0:
        raise ValueError(f"interest_income={interest_income} — 음수 불가")
    if dividend_income < 0:
        raise ValueError(f"dividend_income={dividend_income} — 음수 불가")
    if welfare_loan_interest < 0:
        raise ValueError(f"welfare_loan_interest={welfare_loan_interest} — 음수 불가")
    if reserve_booked < 0:
        raise ValueError(f"reserve_booked={reserve_booked} — 음수 불가")
    if entity not in ("일반", "공익법인_장학", "조특법74"):
        raise ValueError(f"entity='{entity}' — 허용값: '일반', '공익법인_장학', '조특법74'")

    # year는 2016 이상(상한 없음 — 조특법 제74조 일몰 뒤 연도도 계산)
    if year < 2016:
        raise ValueError(f"year={year} — 2016 이상 필요")

    # 1호 합계 (제29조제1항 1호)
    이자배당등 = interest_income if not interest_separate_tax else 0
    이자배당등 += dividend_income
    이자배당등 += welfare_loan_interest

    # 적용률
    만약_조특법74 = (entity == "조특법74")
    if entity == "공익법인_장학":
        적용률 = _Fr(4, 5)
    elif 만약_조특법74 and year <= 2028:
        적용률 = _Fr(1)
    else:
        적용률 = _Fr(1, 2)

    판단 = []
    주의 = []

    # 2호분 (그 밖의 수익사업 소득)
    if other_income >= 0:
        기타분_한도 = _trunc(other_income, 적용률)
        한도 = 이자배당등 + 기타분_한도
    else:  # 결손
        기타분_한도 = 0
        한도 = max(이자배당등 - abs(other_income), 0)
        판단.append(f"결손 상당액 차감(제29조제1항 괄호): 1호 합계 {이자배당등:,}원 − |기타소득 {abs(other_income):,}| = {한도:,}원")

    if 만약_조특법74 and year > 2028:
        적용률_표시 = 0.5
        주의.append("조세특례제한법 제74조 일몰(2028.12.31 이전 사업연도): 2029년 이후는 50% 적용")
    else:
        적용률_표시 = float(적용률)

    손금산입액 = min(reserve_booked, 한도)
    한도초과액 = max(reserve_booked - 한도, 0)

    if interest_separate_tax:
        판단.append("이자소득 분리과세 선택(제62조): 이자소득을 한도 계산에서 제외")

    판단.append("손금산입 사업연도 종료일 이후 5년 내 미사용 잔액은 익금산입 + 이자상당액(제29조제5항제4호·제7항)")

    근거 = "법인세법 제29조제1항"
    if 만약_조특법74:
        근거 += ", 조세특례제한법 제74조"

    return {
        "결과": {
            "이자배당등_합계": 이자배당등,
            "기타수익사업_소득": other_income,
            "적용률": 적용률_표시,
            "기타분_한도": 기타분_한도,
            "한도": 한도,
            "계상액": reserve_booked,
            "손금산입액": 손금산입액,
            "한도초과액": 한도초과액,
        },
        "판단": 판단,
        "근거": 근거,
        **({"주의": 주의} if 주의 else {}),
    }
