"""상속세·증여세 계산 (2016~2026 상속개시일·증여일 기준) — 손계산·조문 대조. 작성 Mia(윤승미)"""
import math
from datetime import date
from typing import Literal

from .. import vocab

M = 1_000_000


def _won(x):
    return int(math.floor(x))


def _parse_legal_share(s):
    """'분자/분모' 또는 0 초과 1 이하 소수 → (분자, 분모)."""
    from fractions import Fraction
    if isinstance(s, str):
        parts = s.split("/")
        if len(parts) != 2:
            raise ValueError("spouse.legal_share는 '3/5' 같은 분수 문자열 또는 0 초과 1 이하 소수")
        num, den = int(parts[0]), int(parts[1])
        if den <= 0 or num <= 0 or num > den:
            raise ValueError("spouse.legal_share는 '3/5' 같은 분수 문자열 또는 0 초과 1 이하 소수")
        return num, den
    # 숫자(소수)
    x = float(s)
    if x <= 0 or x > 1:
        raise ValueError("spouse.legal_share는 '3/5' 같은 분수 문자열 또는 0 초과 1 이하 소수")
    f = Fraction(x).limit_denominator(100)
    return f.numerator, f.denominator


def _rate_table(year):
    """상속세·증여세 공통 세율표(법 제26조 준용)."""
    return [(100 * M, 0.10), (500 * M, 0.20), (1_000 * M, 0.30), (3_000 * M, 0.40), (None, 0.50)]


def _tier(amount, tiers):
    out, prev = 0.0, 0
    for cap, r in tiers:
        if amount > prev:
            if cap is None:
                out += (amount - prev) * r
            else:
                out += (min(amount, cap) - prev) * r
        prev = cap
    return _won(out)


def _calc_tax(amount, year):
    return _tier(amount, _rate_table(year))


def _장례비용(funeral_cost, enshrinement_cost):
    """영 제9조②: clamp(funeral_cost, 500만, 1,000만) + min(enshrinement_cost, 500만)."""
    voc = vocab.rule("상속_장례비용", 2025)  # 연도별 변동 없음
    lower, upper, enshr = voc["하한"], voc["상한"], voc["봉안"]
    return _won(max(lower, min(funeral_cost, upper))) + _won(min(enshrinement_cost, enshr))


def _인적공제(year, children, minors, seniors, disabled, spouse, sole_spouse_heir, filed):
    """기초공제 + 그밖의인적공제 + 일괄공제 선택."""
    voc = vocab.rule("상속세_인적공제", year)
    기초 = voc["기초공제"]  # 2억
    자녀 = voc["자녀공제"]  # 5천만
    미성년 = voc["미성년공제"]  # 1천만
    연로 = voc["연로공제"]  # 5천만
    장애 = voc["장애공제"]  # 1천만
    일괄 = voc["일괄공제"]  # 5억

    연수_끝수 = voc.get("연수_끝수", "올림")

    # 그밖의인적공제
    other = children * 자녀
    for m in minors:
        if 연수_끝수 == "버림":
            y = int(m) if m >= 1 else 1  # 1 미만이면 1
        else:
            y = math.ceil(m)
        other += 미성년 * y
    other += seniors * 연로
    for d in disabled:
        if 연수_끝수 == "버림":
            y = int(d) if d >= 1 else 1
        else:
            y = math.ceil(d)
        other += 장애 * y

    인적 = 기초 + other

    # 배우자 단독상속
    if sole_spouse_heir:
        return 인적, False  # 일괄공제 적용 안 함

    # 무신고
    if not filed:
        return 일괄, True  # 일괄공제 강제

    # 일괄공제 vs 인적공제 중 큰 것
    적용 = max(인적, 일괄)
    return 적용, 적용 == 일괄


def _배우자공제(year, estate_value, deemed_estate, nontaxable, public_charges, debts, excluded,
                bequest_to_non_heirs, prior_gifts_heirs, spouse):
    """법 제19조, 영 제17조①."""
    if spouse is None:
        return 0, None

    voc = vocab.rule("배우자상속공제", year)
    최소, 최대 = voc["최소"], voc["최대"]

    A = estate_value + deemed_estate - nontaxable - public_charges - debts - excluded
    num, den = _parse_legal_share(spouse["legal_share"])
    한도 = _won((A - bequest_to_non_heirs + prior_gifts_heirs) * num / den)
    한도 = max(0, 한도)

    actual = spouse["actual"]
    공제 = max(최소, min(actual, 한도, 최대))
    return 공제, 한도


def _금융재산공제(year, net_financial_assets):
    """법 제22조①."""
    voc = vocab.rule("금융재산상속공제", year)
    기준 = voc["전액기준"]  # 2천만
    율 = voc["율"]  # 0.2
    최소 = voc["최소"]  # 2천만
    한도 = voc["한도"]  # 2억
    if net_financial_assets <= 기준:
        return net_financial_assets
    return min(max(_won(net_financial_assets * 율), 최소), 한도)


def _동거주택공제(year, cohabiting_house):
    """법 제23조의2①."""
    if cohabiting_house is None:
        return 0
    voc = vocab.rule("동거주택상속공제", year)
    율 = voc["율"]
    한도 = voc["한도"]
    차감 = voc.get("담보채무차감", False)
    value = cohabiting_house["value"]
    secured = cohabiting_house.get("secured_debt", 0)
    if 차감:
        base = value - secured
    else:
        base = value
    return min(_won(base * 율), 한도)


def _감정평가수수료(year, appraisal_fee, share_appraisal_fee, share_appraisal_count):
    """영 제20조의3③."""
    voc = vocab.rule("상증_감정평가수수료", year)
    한도1 = voc["1호"]  # 500만
    한도2 = voc["2호"]  # 1천만
    return _won(min(appraisal_fee, 한도1)) + _won(min(share_appraisal_fee, 한도2 * share_appraisal_count))


def _추정상속재산(year, presumed_items):
    """법 제15조①, 영 제11조④."""
    voc = vocab.rule("상속_추정상속재산", year)
    기준1 = voc["1년_기준"]  # 2억
    기준2 = voc["2년_기준"]  # 5억
    율 = voc["율"]  # 0.2
    한도 = voc["한도"]  # 2억

    total = 0
    details = []
    for _pi, item in enumerate(presumed_items):
        window = item["window"]
        amount = item["amount"]
        if isinstance(amount, bool) or not isinstance(amount, int):
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"presumed_items[{_pi}].amount: 금액(원)을 넣으세요 — true/false 아님"]}
        unexplained = item["unexplained"]
        if isinstance(unexplained, bool) or not isinstance(unexplained, int):
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"presumed_items[{_pi}].unexplained: 금액(원)을 넣으세요 — true/false 아님"]}
        kind = item["kind"]

        if window == "1년":
            기준 = 기준1
        else:
            기준 = 기준2

        if amount < 기준:
            details.append({"요건충족": False, "차감액": 0, "추정액": 0,
                           "사유": f"요건 미충족({'1년 2억' if window == '1년' else '2년 5억'} 미만)"})
            continue

        차감 = _won(amount * 율)
        차감 = min(차감, 한도)
        if unexplained < 차감:
            추정 = 0
        else:
            추정 = unexplained - 차감

        details.append({"요건충족": True, "차감액": 차감, "추정액": 추정})
        total += 추정

    return total, details


def 상속세율_산출세액(amount):
    """법 제26조 누진표."""
    return _calc_tax(amount, 2025)


def inheritance_tax(
    year: int,
    estate_value: int,
    deemed_estate: int = 0,
    presumed_items: list = None,
    nontaxable: int = 0,
    excluded: int = 0,
    public_charges: int = 0,
    funeral_cost: int = 0,
    enshrinement_cost: int = 0,
    debts: int = 0,
    prior_gifts_heirs: int = 0,
    prior_gifts_others: int = 0,
    prior_gift_deductions: int = 0,
    bequest_to_non_heirs: int = 0,
    renounced_to_next: int = 0,
    spouse: dict = None,
    sole_spouse_heir: bool = False,
    children: int = 0,
    minors: list = None,
    seniors: int = 0,
    disabled: list = None,
    net_financial_assets: int = 0,
    cohabiting_house: dict = None,
    business_farm_deduction: int = 0,
    appraisal_fee: int = 0,
    share_appraisal_fee: int = 0,
    share_appraisal_count: int = 1,
    generation_skip_surcharge: int = 0,
    gift_tax_credit: int = 0,
    other_credits: int = 0,
    filed: bool = True,
):
    """상속세 과세가액·공제·과세표준·산출세액·납부할세액 계산."""
    if spouse is None and sole_spouse_heir:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["배우자 단독상속인데 spouse 입력 없음"]}

    if spouse is not None:
        try:
            _parse_legal_share(spouse["legal_share"])
        except ValueError as e:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [str(e)]}

    if prior_gift_deductions > prior_gifts_heirs + prior_gifts_others:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["사전증여 공제액이 사전증여재산가액보다 큼"]}

    if cohabiting_house is not None:
        if cohabiting_house.get("secured_debt", 0) > cohabiting_house["value"]:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["동거주택 담보채무가 주택가액보다 큼"]}

    presumed_items = presumed_items or []
    minors = minors or []
    disabled = disabled or []

    # 1. 추정상속재산
    추정_합계, 추정_내역 = _추정상속재산(year, presumed_items)

    # 2. 상속재산가액 합계
    상속재산가액 = estate_value + deemed_estate + 추정_합계

    # 3. 장례비용
    장례 = _장례비용(funeral_cost, enshrinement_cost)

    # 4. 차감액
    차감 = public_charges + 장례 + debts

    # 5. 과세가액
    과세가액 = max(0, 상속재산가액 - nontaxable - excluded - 차감) + prior_gifts_heirs + prior_gifts_others

    # 6. 인적공제
    인적적용액, 일괄적용 = _인적공제(year, children, minors, seniors, disabled, spouse, sole_spouse_heir, filed)

    # 7. 배우자공제
    배우자공제, 배우자한도 = _배우자공제(year, estate_value, deemed_estate, nontaxable,
                                          public_charges, debts, excluded, bequest_to_non_heirs,
                                          prior_gifts_heirs, spouse)

    # 8. 금융재산공제
    금융공제 = _금융재산공제(year, net_financial_assets)

    # 9. 동거주택공제
    동거주택공제 = _동거주택공제(year, cohabiting_house)

    # 10. 상속공제 한도 전 합계
    공제한도전 = 인적적용액 + 배우자공제 + 금융공제 + 동거주택공제 + business_farm_deduction

    # 11. 공제적용한도
    if 과세가액 > 500 * M:
        제24조3호 = max(0, prior_gifts_heirs + prior_gifts_others - prior_gift_deductions)
    else:
        제24조3호 = 0
    공제적용한도 = max(0, 과세가액 - bequest_to_non_heirs - renounced_to_next - 제24조3호)

    # 12. 상속공제 합계
    상속공제합계 = min(공제한도전, 공제적용한도)

    # 13. 감정평가수수료
    감정수수료 = _감정평가수수료(year, appraisal_fee, share_appraisal_fee, share_appraisal_count)

    # 14. 과세표준
    과세표준 = max(0, 과세가액 - 상속공제합계 - 감정수수료)

    # 15. 과세최저한
    voc = vocab.rule("상증_과세최저한", year)
    최저한 = voc["금액"]  # 50만
    과세최저한 = 과세표준 < 최저한

    if 과세최저한:
        산출세액 = 0
    else:
        산출세액 = _calc_tax(과세표준, year)

    # 16. 신고세액공제
    신고율 = vocab.rule_on("상증_신고세액공제율", year * 10000 + 101 if year >= 2016 else 20160101)["율"]
    if filed:
        신고공제 = _won(max(0, 산출세액 + generation_skip_surcharge - gift_tax_credit - other_credits) * 신고율)
    else:
        신고공제 = 0

    # 17. 납부할세액
    납부할세액 = max(0, 산출세액 + generation_skip_surcharge - gift_tax_credit - other_credits - 신고공제)

    근거 = [
        ["상속세 및 증여세법", "제13조", "①", "과세가액"],
        ["상속세 및 증여세법", "제14조", "①", "공과금·장례비용·채무 차감"],
        ["상속세 및 증여세법", "제15조", "①", "추정상속재산"],
        ["상속세 및 증여세법", "제18조", "①", "기초공제"],
        ["상속세 및 증여세법", "제20조", "①", "그밖의 인적공제"],
        ["상속세 및 증여세법", "제21조", "①", "일괄공제"],
        ["상속세 및 증여세법", "제19조", "①", "배우자상속공제"],
        ["상속세 및 증여세법", "제22조", "①", "금융재산 상속공제"],
        ["상속세 및 증여세법", "제23조의2", "①", "동거주택 상속공제"],
        ["상속세 및 증여세법", "제24조", "", "공제 적용 한도"],
        ["상속세 및 증여세법", "제25조", "①", "과세표준"],
        ["상속세 및 증여세법", "제26조", "①", "세율"],
        ["상속세 및 증여세법", "제69조", "①", "신고세액공제"],
    ]

    판단 = {
        "과세최저한": 과세최저한,
        "배우자단독상속": sole_spouse_heir,
        "신고여부": filed,
        "입력값_사용": [],
        "확인필요": [],
    }
    if 일괄적용:
        판단["일괄공제_적용"] = True
    if business_farm_deduction:
        판단["입력값_사용"].append("가업·영농상속공제: 입력값 사용")
    if generation_skip_surcharge:
        판단["입력값_사용"].append("세대생략 할증: 입력값 사용")
    if gift_tax_credit:
        판단["입력값_사용"].append("증여세액공제: 입력값 사용")
    if year == 2016:
        판단["확인필요"].append("2016년 미성년자·장애인 연수: 제20조①2호(버림)와 제20조③(1년 미만 1년) 충돌 — 확인 필요")
    if spouse is not None:
        판단["확인필요"].append("배우자공제 한도식 A(영 제17조①): 추정상속재산 제외 — 예규 확인 필요")
    if 신고율 != 0.03:
        판단["확인필요"].append(f"신고세액공제율 {신고율*100:.0f}%: 2017~2018년 특례 적용 여부 확인")

    계산 = {
        "장례비용": 장례,
        "공과금_장례비용_채무": 차감,
        "기초공제": vocab.rule("상속세_인적공제", year)["기초공제"],
        "그밖의인적공제": 인적적용액 - vocab.rule("상속세_인적공제", year)["기초공제"],
        "인적공제_적용액": 인적적용액,
        "일괄공제_적용": 일괄적용,
        "배우자상속공제": 배우자공제,
        "배우자공제_한도": 배우자한도,
        "금융재산상속공제": 금융공제,
        "동거주택상속공제": 동거주택공제,
        "가업영농상속공제": business_farm_deduction,
        "상속공제_한도전": 공제한도전,
        "공제적용한도": 공제적용한도,
        "추정상속_내역": 추정_내역,
        "신고세액공제율": 신고율,
    }

    결과 = {
        "상속재산가액": 상속재산가액,
        "추정상속재산": 추정_합계,
        "과세가액": 과세가액,
        "상속공제_합계": 상속공제합계,
        "감정평가수수료": 감정수수료,
        "과세표준": 과세표준,
        "산출세액": 산출세액,
        "세대생략할증": generation_skip_surcharge,
        "증여세액공제": gift_tax_credit,
        "신고세액공제": 신고공제,
        "납부할세액": 납부할세액,
    }

    return {"결과": 결과, "계산": 계산, "판단": 판단, "근거": 근거}


def 증여세_산출세액(amount, year):
    """법 제56조 → 제26조 준용."""
    return _calc_tax(amount, year)


def gift_tax(
    gift_date: str,
    gift_value: int,
    relation: Literal["배우자", "직계존속", "직계비속", "기타친족", "기타"],
    recipient_minor: bool = False,
    prior_gifts_same_donor: int = 0,
    nontaxable: int = 0,
    excluded: int = 0,
    assumed_debt: int = 0,
    prior_deduction_used: int = 0,
    marriage_birth: bool = False,
    marriage_birth_used: int = 0,
    appraisal_fee: int = 0,
    share_appraisal_fee: int = 0,
    share_appraisal_count: int = 1,
    generation_skip: bool = False,
    prior_gift_tax_paid: int = 0,
    other_credits: int = 0,
    filed: bool = True,
):
    """증여세 과세가액·증여재산공제·과세표준·산출세액·납부할세액 계산."""
    gift_date_dt = date.fromisoformat(gift_date)
    연도 = gift_date_dt.year
    연도_int = 연도 * 10000 + gift_date_dt.month * 100 + gift_date_dt.day

    # 오류 검사
    if marriage_birth and gift_date < "2024-01-01":
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["혼인·출산 증여재산공제는 2024.1.1 이후 증여분부터(법 제53조의2, 부칙 제19932호 제3조)"]}
    if marriage_birth and relation != "직계존속":
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["혼인·출산 증여재산공제는 직계존속으로부터 받은 증여만"]}
    if assumed_debt > gift_value:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["인수채무가 증여재산가액보다 큼"]}

    # 1. 합산 여부
    합산여부 = (gift_value + prior_gifts_same_donor) >= 10 * M

    # 2. 과세가액
    과세가액 = max(0, gift_value - nontaxable - excluded - assumed_debt)
    if 합산여부:
        과세가액 += prior_gifts_same_donor

    # 3. 증여재산공제
    voc = vocab.rule("증여재산공제", 연도_int)
    if relation == "직계존속" and recipient_minor:
        한도 = voc.get("직계존속_미성년", 0)
    else:
        한도 = voc.get(relation, 0)
    증여공제 = min(max(0, 한도 - prior_deduction_used), 과세가액)

    # 4. 혼인·출산 공제
    혼인출산공제 = 0
    혼인출산_남은한도 = None
    if marriage_birth and relation == "직계존속":
        voc2 = vocab.rule("혼인출산_증여재산공제", 연도_int)
        혼인출산공제 = min(max(0, voc2["한도"] - marriage_birth_used), 과세가액 - 증여공제)
        혼인출산_남은한도 = voc2["한도"] - marriage_birth_used - 혼인출산공제
        if 혼인출산_남은한도 < 0:
            혼인출산_남은한도 = 0

    # 5. 감정평가수수료
    감정수수료 = _감정평가수수료(연도, appraisal_fee, share_appraisal_fee, share_appraisal_count)

    # 6. 과세표준
    과세표준 = max(0, 과세가액 - 증여공제 - 혼인출산공제 - 감정수수료)

    # 7. 과세최저한
    voc3 = vocab.rule("상증_과세최저한", 연도)
    과세최저한 = 과세표준 < voc3["금액"]
    if 과세최저한:
        산출세액 = 0
    else:
        산출세액 = 증여세_산출세액(과세표준, 연도)

    # 8. 할증세액
    할증율 = 0
    if generation_skip:
        if recipient_minor and (gift_value + (prior_gifts_same_donor if 합산여부 else 0)) > 20 * M:
            할증율 = 0.4
        else:
            할증율 = 0.3
    할증세액 = _won(산출세액 * 할증율) if 할증율 > 0 else 0

    # 9. 신고세액공제
    신고율 = vocab.rule_on("상증_신고세액공제율", 연도_int)["율"]
    if filed:
        신고공제 = _won(max(0, 산출세액 + 할증세액 - prior_gift_tax_paid - other_credits) * 신고율)
    else:
        신고공제 = 0

    # 10. 납부할세액
    납부할세액 = max(0, 산출세액 + 할증세액 - prior_gift_tax_paid - other_credits - 신고공제)

    # 남은 공제한도
    남은한도 = 한도 - prior_deduction_used - 증여공제
    if 남은한도 < 0:
        남은한도 = 0

    voc_relation = vocab.rule("증여재산공제", 연도_int)
    기타친족_범위 = voc_relation.get("기타친족_범위", "")

    판단 = [
        {"항목": "관계", "결론": relation, "근거": "상속세 및 증여세법 제53조"},
        {"항목": "합산여부", "결론": f"{'합산' if 합산여부 else '미합산'}(10년 내 동일 증여자 합계 {'1천만원 이상' if 합산여부 else '1천만원 미만'})", "근거": "상속세 및 증여세법 제47조②"},
    ]
    if relation == "기타":
        판단.append({"항목": "친족 아님", "결론": "기타 — 증여재산공제 없음", "근거": "상속세 및 증여세법 제53조"})
    if not 합산여부:
        판단.append({"항목": "합산미대상", "결론": "10년 내 동일 증여자 증여재산가액 합계 1천만원 미만 — 합산 안 함", "근거": "상속세 및 증여세법 제47조②"})
    if marriage_birth:
        판단.append({"항목": "혼인출산공제", "결론": f"혼인·출산 증여재산공제 {혼인출산공제:,}원 적용", "근거": "상속세 및 증여세법 제53조의2"})
    if generation_skip:
        판단.append({"항목": "할증", "결론": f"세대생략 할증 {할증율*100:.0f}% 적용", "근거": "상속세 및 증여세법 제57조①"})
    if prior_gift_tax_paid > 0:
        판단.append({"항목": "기납부세액공제", "결론": "납부세액공제는 입력값 사용(한도 계산하지 않음)", "근거": "상속세 및 증여세법 제58조"})

    근거 = [
        ["상속세 및 증여세법", "제47조", "①②", "과세가액·합산"],
        ["상속세 및 증여세법", "제53조", "", "증여재산공제"],
        ["상속세 및 증여세법", "제53조의2", "①", "혼인·출산 증여재산공제(2024.1.1. 이후)"],
        ["상속세 및 증여세법", "제55조", "①", "과세표준"],
        ["상속세 및 증여세법", "제56조", "", "세율(법 제26조 준용)"],
        ["상속세 및 증여세법", "제57조", "①", "세대생략 할증"],
        ["상속세 및 증여세법", "제69조", "②", "신고세액공제"],
    ]

    결과 = {
        "과세가액": 과세가액,
        "증여재산공제": 증여공제,
        "혼인출산_증여재산공제": 혼인출산공제,
        "감정평가수수료": 감정수수료,
        "과세표준": 과세표준,
        "산출세액": 산출세액,
        "할증세액": 할증세액,
        "기납부세액공제": prior_gift_tax_paid,
        "신고세액공제": 신고공제,
        "납부할세액": 납부할세액,
    }

    계산 = {
        "합산_증여재산가액": gift_value + (prior_gifts_same_donor if 합산여부 else 0),
        "인수채무": assumed_debt,
        "할증율": 할증율,
        "신고세액공제율": 신고율,
    }

    판단 = {
        "관계": {"결론": relation, "근거": "상속세 및 증여세법 제53조"},
        "합산여부": 합산여부,
        "증여재산공제_한도": {"결론": f"{한도:,}원", "근거": "상속세 및 증여세법 제53조"},
        "기공제액": {"결론": f"{prior_deduction_used:,}원", "근거": "상속세 및 증여세법 제53조(10년 합산)"},
        "남은_공제한도": 남은한도,
        "혼인출산_남은_한도": 혼인출산_남은한도,
        "과세최저한": 과세최저한,
        "기타친족_범위": 기타친족_범위,
    }

    return {"결과": 결과, "계산": 계산, "판단": 판단, "근거": 근거}
