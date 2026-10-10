"""korean-tax-calc-mcp — 한국어 세금 계산 MCP 서버(코드 계산, AI 없음).

세율·한도·가산세는 사업연도·과세기간·공급일 기준 연도표(2016~2026)로 계산하고, 표에 없는 연도는 추정하지 않고 멈춘다.
결과마다 근거 조문을 붙인다. 근거 원문은 korean-tax-mcp(law_article)로 확인한다.
"""
import os
from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .engine import calc as K, calc_cit as C, calc_income as I, calc_vat as V

mcp = MCPServer(
    "korean-tax-calc-mcp", title="Korea Tax Calculator (한국 세금 계산)",
    instructions="한국 세금 계산은 반드시 이 도구 결과를 쓰고 직접 계산하지 않는다. 결과의 근거 조문을 함께 제시한다. "
                 "연도표가 없는 해는 오류로 멈추므로 추정하지 않는다. 계산 근거 원문·해석은 korean-tax-mcp로 확인한다.")
CALC = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
YEAR = Annotated[int, Field(description="사업연도·귀속연도(2016~2026)", ge=2016, le=2026)]
WON = Annotated[int, Field(description="금액(원)", ge=0)]


# list[dict] 인자용 Pydantic 모델 — 입력 검증 강화 (지시서 4)
class Movement(BaseModel):
    date: str       # YYYY-MM-DD
    amount: int     # 원 (대여 +, 회수 -)


class Loan(BaseModel):
    interest: int   # 지급이자(원)
    jeoksu: int     # 차입금 적수(원·일)


class ReceiptItem(BaseModel):
    amount: int           # 1회 지출액(원)
    qualified: bool = False       # 적격증빙 여부
    congratulatory: bool = False  # 경조금 여부


def _ok(r, basis, **extra):
    return {"결과": r, "근거": basis, **extra}


def _guard(fn):
    import functools

    @functools.wraps(fn)
    def w(*a, **k):
        try: return fn(*a, **k)
        except (C.NoYearTable, getattr(V, "NoYearTable", C.NoYearTable), getattr(I, "NoYearTable", C.NoYearTable)) as e:
            return {"error": str(e), "주의": "연도표 없는 해는 추정 계산하지 않음"}
        except (ValueError, KeyError, TypeError) as e:
            return {"error": f"입력 오류: {e}"}
    return w


@mcp.tool(annotations=CALC)
@_guard
def corporate_tax(base: WON, year: YEAR,
                  months: Annotated[int, Field(description="사업연도 월수(1년 미만이면 1~11)", ge=1, le=12)] = 12) -> dict:
    """Corporate income tax on a tax base for a fiscal year. 법인세 산출세액(사업연도 세율표, 1년 미만 사업연도 환산 포함)."""
    return _ok({"산출세액": C.corp_tax(base, year, months), "과세표준": base, "사업연도": year, "월수": months}, "법인세법 제55조(세율)·제55조②(1년 미만)")


@mcp.tool(annotations=CALC)
@_guard
def entertainment_limit(year: YEAR, sme: Annotated[bool, Field(description="중소기업 여부")],
                        general_revenue: WON,
                        expensed: WON,
                        related_revenue: WON = 0,
                        culture: WON = 0,
                        months: Annotated[int, Field(description="사업연도 월수", ge=1, le=12)] = 12) -> dict:
    """Entertainment expense limit and excess. 기업업무추진비(접대비) 한도와 한도초과액(손금불산입·기타사외유출)."""
    return _ok(C.entertain(year, sme, general_revenue, related_revenue, expensed, culture=culture, months=months),
               "법인세법 제25조, 시행령 제42조")


@mcp.tool(annotations=CALC)
@_guard
def deemed_interest(movements: Annotated[list[Movement], Field(description="가지급금 증감 [{date:'YYYY-MM-DD', amount:원(대여 +, 회수 -)}]")],
                    year_end: Annotated[str, Field(description="사업연도 종료일 YYYY-MM-DD")],
                    market_rate: Annotated[float, Field(description="시가 이자율(소수). 가중평균차입이자율 원칙, 예외 당좌대출이자율 0.046")] = 0.046,
                    charged_rate: Annotated[float, Field(description="실제 받은 이자율(소수)")] = 0.0) -> dict:
    """Deemed interest on loans to related parties. 가지급금 인정이자 — 적수와 시가 이자, 부당행위 기준(3억·5%) 판정, 익금산입액."""
    mv = [(m.date, int(m.amount)) for m in movements]
    j = C.jeoksu(mv, year_end)
    days = 366 if date.fromisoformat(year_end).year % 4 == 0 else 365
    return _ok({"적수": j, **C.deemed_interest_check(market_rate, charged_rate, j, days)},
               "법인세법 제52조, 시행령 제88조③·제89조③, 시행규칙 제43조(이자율)")


@mcp.tool(annotations=CALC)
@_guard
def unfair_transaction(market_price: Annotated[float, Field(description="시가(단가)")], actual_price: Annotated[float, Field(description="실제 거래 단가")],
                       quantity: Annotated[int, Field(description="수량", ge=1)]) -> dict:
    """Related-party transaction at non-arm's-length price: 3억 or 5% threshold. 부당행위계산 기준(시가 차이 3억 이상 또는 5% 이상)."""
    gap = abs(market_price - actual_price) * quantity; base = market_price * quantity
    return _ok({"시가총액": int(base), "차액": int(gap), "차액비율": round(gap / base, 4) if base else None,
                "부당행위계산": bool(gap >= 300_000_000 or (base and gap >= base * 0.05))}, "법인세법 제52조, 시행령 제88조③")


@mcp.tool(annotations=CALC)
@_guard
def loss_carryforward_limit(year: YEAR, sme: Annotated[bool, Field(description="중소기업 등 여부")]) -> dict:
    """Limit on using loss carryforwards in a year. 이월결손금 공제 한도율(사업연도 개시일 기준)."""
    return _ok({"한도율": C.loss_limit_ratio(year, sme)}, "법인세법 제13조① 단서")


@mcp.tool(annotations=CALC)
@_guard
def minimum_tax(base_before_incentives: WON, year: YEAR,
                sme: Annotated[bool, Field(description="중소기업 여부")] = True,
                grace_year: Annotated[int, Field(description="중소기업 졸업 후 경과 연차(0=해당 없음)", ge=0, le=5)] = 0) -> dict:
    """Minimum corporate tax. 최저한세(감면 전 과세표준 × 최저한세율)."""
    return _ok({"최저한세": C.min_tax(base_before_incentives, sme=sme, grace_year=grace_year, year=year)}, "조세특례제한법 제132조①")


@mcp.tool(annotations=CALC)
def underreporting_penalty(additional_tax: WON, fraud: Annotated[bool, Field(description="부정행위로 인한 과소신고 여부")]) -> dict:
    """Under-reporting penalty. 과소신고가산세(일반 10%, 부정행위 40%)."""
    return _ok({"가산세": K.penalty_underreport(additional_tax, fraud), "세율": 0.4 if fraud else 0.1}, "국세기본법 제47조의3")


@mcp.tool(annotations=CALC)
@_guard
def late_payment_penalty(unpaid_tax: WON, due: Annotated[str, Field(description="법정납부기한 YYYY-MM-DD")],
                         until: Annotated[str, Field(description="납부일·고지일 YYYY-MM-DD")]) -> dict:
    """Late payment penalty with rate changes split by period. 납부지연가산세(일수분, 이율 변경일 기준 기간 안분)."""
    return _ok(C.late_payment_penalty(unpaid_tax, due, until), "국세기본법 제47조의4, 시행령 제27조의4")


@mcp.tool(annotations=CALC)
@_guard
def invoice_penalty(supply_amount: WON, kind: Annotated[Literal["가공", "지연발급", "미발급", "미발급_종이", "지연전송", "미전송", "지연수취",
                                                               "매출처별합계표_미제출", "매출처별합계표_예정분확정제출", "신용카드매입공제"],
                                                       Field(description="가산세 유형 — 가공=실물 없는 발급·수취")],
                    supplied_on: Annotated[str, Field(description="공급일(발급·수취일) YYYY-MM-DD — 세율은 이 날짜 기준")] = "") -> dict:
    """VAT invoice penalties by type and supply date. 세금계산서 관련 가산세(가공 2%·3%·4%, 미발급 2%, 지연발급 1% 등 공급일 기준)."""
    if kind == "가공":
        return _ok({"가산세": K.penalty_fake_invoice(supply_amount, supplied_on), "세율": K.fake_invoice_rate(supplied_on)}, "부가가치세법 제60조③")
    return _ok({"가산세": V.invoice_penalties(supply_amount, kind, supplied_on or None), "세율": V.invoice_penalty_rate(kind, supplied_on or None)}, "부가가치세법 제60조②⑤⑥⑦")


@mcp.tool(annotations=CALC)
def assessment_limitation(due_date: Annotated[str, Field(description="법정신고기한 YYYY-MM-DD (부과할 수 있는 날 = 그 다음 날)")],
                          case: Annotated[Literal["일반", "무신고", "부정행위"], Field(description="일반(과소신고 등) / 무신고 / 부정행위로 포탈·환급")] = "일반",
                          offshore: Annotated[bool, Field(description="역외거래(국제거래 또는 국외 자산·용역 관련 거래) 여부")] = False,
                          inheritance_gift: Annotated[bool, Field(description="상속세·증여세 여부")] = False) -> dict:
    """Statute of limitations for tax assessment. 국세 부과제척기간과 만료일(2020년 이후 부과분 기준 현행 조문).
    일반 5년(역외 7년), 무신고 7년(역외 10년), 부정행위 10년(역외 15년), 상속·증여 10년(부정행위·무신고·거짓·누락신고 15년)."""
    if inheritance_gift: n = 10 if case == "일반" else 15
    else: n = {"일반": (5, 7), "무신고": (7, 10), "부정행위": (10, 15)}[case][1 if offshore else 0]
    d = date.fromisoformat(due_date)
    try: end = d.replace(year=d.year + n)
    except ValueError: end = d.replace(year=d.year + n, day=28)
    return _ok({"제척기간(년)": n, "기산일": "법정신고기한 다음 날", "만료일": end.isoformat()},
               "국세기본법 제26조의2" + ("④" if inheritance_gift else ("②" if case != "일반" else "①")),
               주의="2019.12.31. 개정 전 기간·특례(이월결손금 공제 시 ③, 상증세 안 날부터 1년 ⑤, 쟁송 결과 ⑥)는 별도 확인 — 원문은 korean-tax-mcp law_article")


@mcp.tool(annotations=CALC)
@_guard
def income_tax(base: Annotated[int, Field(description="종합소득 과세표준(원)")], year: YEAR) -> dict:
    """Comprehensive income tax on a tax base. 종합소득세 산출세액(귀속연도 세율표)."""
    return _ok({"산출세액": I.income_tax(base, year)}, "소득세법 제55조")


@mcp.tool(annotations=CALC)
@_guard
def withholding_tax(kind: Annotated[str, Field(description="소득 종류: 이자·배당·비영업대금·사업·기타·봉사료·일용·비실명·외국인직업운동가·온투업이자")],
                    amount: WON, year: Annotated[int, Field(description="지급연도", ge=2016, le=2026)] = 2025) -> dict:
    """Domestic withholding tax by income type and payment year (national portion; local income tax 10% separate). 원천징수세액(소득세분, 지방소득세 별도)."""
    return _ok({"원천징수세액": I.withholding_tax(kind, amount, year), "세율": I.withholding_rate(kind, year)}, "소득세법 제129조",
               주의="지방소득세(소득세의 10%) 별도. 비거주자는 조세조약 제한세율 확인(korean-tax-mcp treaty_withholding_rates)")


@mcp.tool(annotations=CALC)
@_guard
def nonresident_withholding(income_kind: Annotated[Literal["이자", "배당", "사용료", "인적용역", "기타"],
                                                   Field(description="소득 종류(비거주자·외국법인 국내원천) — 이자·배당·사용료·인적용역·기타")],
                            amount: WON,
                            recipient_type: Annotated[Literal["개인", "법인"], Field(description="수취인 구분 — 개인(비거주자) / 법인(외국법인)")],
                            residence_country: Annotated[str, Field(description="거주지국(ISO 2자 또는 국명)")],
                            treaty_rate: Annotated[float | None, Field(description="조세조약 제한세율(소수, 예: 0.15). 없으면 국내세율 적용")] = None,
                            bond_interest: Annotated[bool, Field(description="채권 이자 여부 — 이자 소득에서만 의미, 특례 적용 필요 시 별도 확인")] = False) -> dict:
    """Non-resident/foreign corporation withholding tax on Korean-source income (소득세법 제156조 / 법인세법 제98조).
    적용세율 = min(국내세율, 조약 제한세율), 지방소득세 10% 별도 합산. 조약 미체결·비과세 확인은 korean-tax-mcp로 원문 대조."""
    r = I.nonresident_withholding(income_kind, amount, recipient_type, residence_country, treaty_rate, bond_interest)
    return _ok(r, r["근거"])


@mcp.tool(annotations=CALC)
@_guard
def retirement_income_tax(income: WON, years_of_service: Annotated[int, Field(description="근속연수", ge=1, le=60)]) -> dict:
    """Retirement income tax. 퇴직소득세(근속연수공제·환산급여 방식)."""
    return _ok({"퇴직소득세": I.retirement_tax(income, years_of_service)}, "소득세법 제48조·제55조②")


@mcp.tool(annotations=CALC)
@_guard
def vat_deemed_rent(deposit: WON, days: Annotated[int, Field(description="과세기간 중 임대 일수", ge=1, le=184)],
                    period: Annotated[str, Field(description="과세기간 'YYYY-1' 또는 'YYYY-2' (정기예금이자율 연도표)")]) -> dict:
    """VAT deemed rent on lease deposits. 간주임대료(보증금 × 정기예금이자율 × 일수/365)."""
    return _ok({"간주임대료": V.deemed_rent(deposit, days, period=period)}, "부가가치세법 시행령 제65조")


# ───────── 0.2 추가: 법인세 세무조정 ─────────
@mcp.tool(annotations=CALC)
@_guard
def nonbusiness_interest_disallowance(loans: Annotated[list[Loan], Field(description="차입금별 [{interest: 지급이자(원), jeoksu: 차입금 적수(잔액×일수)}]")],
                                      nonbusiness_jeoksu: Annotated[int, Field(description="업무무관자산·가지급금 적수 합(원·일)", ge=0)]) -> dict:
    """Disallowed interest related to non-business assets and related-party loans. 업무무관자산 등 관련 지급이자 손금불산입."""
    r = C.nonbusiness_interest([(int(l.interest), int(l.jeoksu)) for l in loans])(nonbusiness_jeoksu)
    return _ok(r, "법인세법 제28조①4호, 시행령 제53조", 산식="지급이자 × min(1, 업무무관 적수 ÷ 차입금 적수)")


@mcp.tool(annotations=CALC)
@_guard
def business_car_expense(year: YEAR, upkeep: Annotated[int, Field(description="유지비(유류·보험·수선 등, 원)")],
                         depreciation: Annotated[int, Field(description="세법상 감가상각비(5년 정액, 원)")],
                         booked_depreciation: Annotated[int, Field(description="장부상 감가상각비(원)")],
                         log_kept: Annotated[bool, Field(description="운행기록부 작성 여부")],
                         business_ratio: Annotated[float | None, Field(description="운행기록상 업무사용비율(작성 시)", ge=0, le=1)] = None,
                         months: Annotated[int, Field(description="보유 월수", ge=1, le=12)] = 12,
                         rental_corp: Annotated[bool, Field(description="부동산임대업 주업 등 특정법인")] = False,
                         plate_ok: Annotated[bool, Field(description="법인 전용번호판 부착(2024년 이후 요건)")] = True) -> dict:
    """Business-use passenger car expenses: business-use ratio, private use, depreciation cap. 업무용승용차 관련비용 손금불산입."""
    return _ok(C.business_car(year, upkeep, depreciation, booked_depreciation, log_kept, business_ratio, months, rental_corp, plate_ok),
               "법인세법 제27조의2, 시행령 제50조의2", 산식="미작성 시 업무사용비율 = min(1, 기준금액 ÷ 총비용), 감가상각 업무사용분 연 800만원 한도")


@mcp.tool(annotations=CALC)
@_guard
def donation_limit(year: YEAR, base_income: WON,
                   special: WON = 0, general: WON = 0,
                   carried_loss: WON = 0,
                   special_carry: WON = 0, general_carry: WON = 0,
                   sme: Annotated[bool, Field(description="중소기업 여부")] = True,
                   social_enterprise: Annotated[bool, Field(description="사회적기업 여부(일반한도 20%)")] = False) -> dict:
    """Charitable donation deduction limits and carryforwards. 기부금 손금산입 한도(특례 50%, 일반 10%)와 한도초과·이월."""
    return _ok(C.donation(base_income, carried_loss, special, general, special_carry, general_carry, sme, social_enterprise, year=year),
               "법인세법 제24조", 산식="특례 = (기준소득 − 결손금) × 50%, 일반 = (기준소득 − 결손금 − 특례 손금산입) × 10%(사회적기업 20%)")


@mcp.tool(annotations=CALC)
def bad_debt_allowance(receivables: WON, loss_rate: Annotated[float, Field(description="대손실적률(소수)", ge=0, le=1)],
                       set_amount: WON, prior_disallowed: WON = 0) -> dict:
    """Bad debt allowance limit. 대손충당금 한도(채권잔액 × max(1%, 대손실적률))와 한도초과."""
    return _ok(C.bad_debt_allowance(receivables, loss_rate, set_amount, prior_disallowed), "법인세법 제34조, 시행령 제61조②")


@mcp.tool(annotations=CALC)
@_guard
def thin_capitalization(equity: WON,
                        borrowings: WON,
                        total_interest: WON,
                        ratio: Annotated[float | int, Field(description="적용 배수(기본 2, 금융업 등 업종 배수는 별도 확인)")] = 2,
                        year: YEAR = 2026,
                        recipient_residence_country: str | None = None,
                        interest_treaty_rate: float | None = None,
                        dividend_treaty_rate: float | None = None,
                        recipient_type: Literal['개인', '법인'] = '개인') -> dict:
    """Thin capitalization disallowance (국제조세조정에 관한 법률 제22조). 국외지배주주 출자금액 대비 차입금이
    기준 배수(기본 2배)를 초과하는 경우 초과분 지급이자 손금불산입(배당 또는 기타사외유출 처분).
    recipient_residence_country 지정 시 배당 처분에 따른 원천징수 재계산 결과를 함께 제공."""
    base = C.thin_capitalization(equity, borrowings, total_interest, ratio, year)
    result = {"결과": base, "근거": "국제조세조정에 관한 법률 제22조, 시행령 제34조"}
    if recipient_residence_country:
        disallowed_interest = base["손금불산입 이자"]
        if disallowed_interest > 0:
            # 이자 기준 원천징수 (기존 이자소득 처분 가정)
            interest_wh = I.nonresident_withholding("이자", disallowed_interest, recipient_type,
                                                    recipient_residence_country, interest_treaty_rate)
            # 배당 기준 원천징수 (국조법 제22조② 배당 처분)
            dividend_wh = I.nonresident_withholding("배당", disallowed_interest, recipient_type,
                                                    recipient_residence_country, dividend_treaty_rate)
            diff_income = dividend_wh["원천징수세액"] - interest_wh["원천징수세액"]
            diff_local = dividend_wh["지방소득세"] - interest_wh["지방소득세"]
            result["결과"]["원천징수 재계산"] = {
                "대상 금액(손금불산입 이자)": disallowed_interest,
                "이자 기준 원천징수세액": interest_wh["원천징수세액"],
                "이자 기준 지방소득세": interest_wh["지방소득세"],
                "배당 기준 원천징수세액": dividend_wh["원천징수세액"],
                "배당 기준 지방소득세": dividend_wh["지방소득세"],
                "소득세 차액": diff_income,
                "지방소득세 차액": diff_local,
                "근거": "국조법 제22조 ② 배당 처분 → 소득세법 제119조 2호 / 법인세법 제93조 2호 배당소득",
            }
    return result


@mcp.tool(annotations=CALC)
@_guard
def missing_receipt_disallowance(year: YEAR, items: Annotated[list[ReceiptItem], Field(description="[{amount: 1회 지출액, qualified: 적격증빙 여부, congratulatory: 경조금 여부}]")]) -> dict:
    """Entertainment spending without qualified receipts. 적격증빙 미수취 기업업무추진비 손금불산입(건당 3만원·경조금 20만원 초과)."""
    return _ok({"손금불산입": C.receipt_disallowed(year, [(int(i.amount), bool(i.qualified), bool(i.congratulatory)) for i in items])},
               "법인세법 제25조②, 시행령 제41조①")


# ───────── 0.2 추가: 부가가치세 ─────────
@mcp.tool(annotations=CALC)
@_guard
def vat_deemed_input_credit(purchase: Annotated[int, Field(description="면세농산물 등 매입가액(원)")], base: Annotated[int, Field(description="해당 과세기간 과세표준(원)")],
                            period: Annotated[str, Field(description="과세기간 'YYYY-1' 또는 'YYYY-2'")],
                            industry: Annotated[Literal["음식점", "유흥", "제조", "제조_떡방앗간등", "기타"], Field(description="업종")],
                            individual: Annotated[bool, Field(description="개인사업자 여부")] = True, sme: Annotated[bool, Field(description="중소기업 여부(제조 법인)")] = True) -> dict:
    """VAT deemed input tax credit on tax-exempt agricultural purchases. 의제매입세액공제(공제율·한도율 과세기간 연도표)."""
    num, den = V.deemed_input_rate(industry, period, individual, base, sme)
    return _ok({"의제매입세액": V.deemed_input(purchase, base, period=period, industry=industry, individual=individual, sme=sme), "공제율": f"{num}/{den}"},
               "부가가치세법 제42조, 시행령 제84조", 산식="min(매입가액, 과세표준 × 한도율) × 공제율")


@mcp.tool(annotations=CALC)
@_guard
def vat_common_input_allocation(common_tax: WON, total_supply: WON, exempt_supply: WON) -> dict:
    """Non-deductible share of common input VAT for mixed taxable/exempt businesses. 겸영사업자 공통매입세액 안분(면세비율 5% 미만 등 예외 포함)."""
    return _ok(V.common_input_allocation(common_tax, total_supply, exempt_supply), "부가가치세법 시행령 제81조", 산식="불공제 = 공통매입세액 × 면세공급가액 ÷ 총공급가액")


@mcp.tool(annotations=CALC)
@_guard
def vat_simplified_taxpayer(supply_incl_vat: Annotated[int, Field(description="공급대가(부가세 포함, 원)")],
                            value_added_rate: Annotated[float, Field(description="업종별 부가가치율(소수, 예: 소매 0.15)", gt=0, lt=1)],
                            invoice_purchase_incl_vat: Annotated[int, Field(description="세금계산서 등 수취 매입 공급대가(원)")] = 0) -> dict:
    """VAT for simplified taxpayers (post-2021.7). 간이과세자 납부세액."""
    return _ok({"납부세액": V.simplified_tax(supply_incl_vat, value_added_rate, invoice_purchase_incl_vat)}, "부가가치세법 제63조",
               산식="공급대가 × 부가가치율 × 10% − 매입 공급대가 × 0.5%")


@mcp.tool(annotations=CALC)
@_guard
def vat_card_sales_credit(amount: Annotated[int, Field(description="신용카드·현금영수증 매출(원)")], supplied_on: Annotated[str, Field(description="공급일 YYYY-MM-DD")],
                          used_this_year: Annotated[int, Field(description="같은 해 이미 공제받은 금액(원)")] = 0) -> dict:
    """Credit for card/cash-receipt sales by individual businesses. 신용카드매출전표 등 발행세액공제(1.3%, 연간 한도)."""
    return _ok({"공제액": V.card_sales_credit(amount, supplied_on, used_this_year=used_this_year)}, "부가가치세법 제46조")


@mcp.tool(annotations=CALC)
def vat_bad_debt_credit(bad_debt_incl_vat: Annotated[int, Field(description="대손금액(부가세 포함, 원)")]) -> dict:
    """VAT bad debt credit. 대손세액공제(대손금액 × 10/110)."""
    return _ok({"대손세액": V.bad_debt_vat(bad_debt_incl_vat)}, "부가가치세법 제45조①")


# ───────── 0.2 추가: 근로·원천 ─────────
@mcp.tool(annotations=CALC)
@_guard
def wage_income_tax(gross_pay: Annotated[int, Field(description="총급여(원)")], tax_base: Annotated[int, Field(description="종합소득 과세표준(원)")], year: YEAR) -> dict:
    """Wage income: employment income deduction, computed tax and wage tax credit. 근로소득공제·산출세액·근로소득세액공제."""
    t = I.income_tax(tax_base, year)
    return _ok({"근로소득공제": I.earned_deduction(gross_pay, year), "산출세액": t, "근로소득세액공제": I.earned_tax_credit(t, gross_pay, year=year)},
               "소득세법 제47조①·제55조·제59조", 주의="그 밖의 소득공제·세액공제는 별도")


@mcp.tool(annotations=CALC)
@_guard
def daily_worker_withholding(daily_wage: Annotated[int, Field(description="일급(원)")], year: Annotated[int, Field(description="지급연도", ge=2016, le=2026)] = 2025) -> dict:
    """Withholding on daily workers' wages. 일용근로자 원천징수세액(소액부징수 포함)."""
    return _ok({"원천징수세액": I.daily_worker_tax(daily_wage, year)}, "소득세법 제134조③·제129조①4호·제86조",
               산식="(일급 − 15만원) × 6% × (1 − 55%), 1천원 미만 부징수")


@mcp.tool(annotations=CALC)
@_guard
def deemed_bonus_resettlement(gross_pay: Annotated[int, Field(description="귀속연도 당초 총급여(원)")], tax_base: Annotated[int, Field(description="당초 과세표준(원)")],
                              bonus: Annotated[int, Field(description="소득처분 상여(원)")], year: YEAR,
                              other_credits: Annotated[int, Field(description="근로소득세액공제 외 세액공제 합계(원)")] = 0,
                              prev_decided: Annotated[int | None, Field(description="당초 결정세액(원). 모르면 생략 — 재계산")] = None) -> dict:
    """Year-end resettlement after a deemed bonus (income disposition) is added to wages. 소득처분 상여 연말정산 재정산(추가 원천징수세액)."""
    return _ok(I.deemed_bonus_resettlement(gross_pay, tax_base, bonus, other_credits, prev_decided, year=year),
               "법인세법 제67조, 소득세법 시행령 제192조, 소득세법 제137조",
               주의="총급여 연동 소득·세액공제(신용카드 공제 등)는 수기 보정 필요")


def main():
    import argparse
    p = argparse.ArgumentParser(prog="korean-tax-calc-mcp", description="한국 세금 계산 MCP 서버")
    p.add_argument("--http", action="store_true"); p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8001)))
    a = p.parse_args()
    if a.http:
        import uvicorn
        uvicorn.run(mcp.streamable_http_app(streamable_http_path="/mcp", host=a.host), host=a.host, port=a.port)
    else:
        mcp.run("stdio")


if __name__ == "__main__":
    main()
