"""korean-tax-calc-mcp — 한국 세금 계산 MCP 서버(코드 계산, AI 없음).

세율·한도·가산세는 사업연도·과세기간·공급일 기준 연도표(2016~2025, 일부 2026)로 계산하고, 표에 없는 연도는 추정하지 않고 멈춘다.
결과마다 근거 조문을 붙인다. 근거 원문은 korean-tax-mcp(law_article)로 확인.
"""
import os
from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from .engine import calc as K, calc_cit as C, calc_income as I, calc_vat as V

mcp = MCPServer(
    "korean-tax-calc-mcp", title="Korea Tax Calculator (한국 세금 계산)",
    instructions="한국 세금 계산은 반드시 이 도구 결과를 쓰고 직접 계산하지 않는다. 결과의 근거 조문을 함께 제시한다. "
                 "연도표가 없는 해는 오류로 멈추므로 추정하지 않는다. 계산 근거 원문·해석은 korean-tax-mcp로 확인한다.")
CALC = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
YEAR = Annotated[int, Field(description="사업연도·귀속연도(2016~2025)", ge=2016, le=2026)]
WON = Annotated[int, Field(description="금액(원)", ge=0)]


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
def corporate_tax(base: Annotated[int, Field(description="과세표준(원)")], year: YEAR,
                  months: Annotated[int, Field(description="사업연도 월수(1년 미만이면 1~11)", ge=1, le=12)] = 12) -> dict:
    """Corporate income tax on a tax base for a fiscal year. 법인세 산출세액(사업연도 세율표, 1년 미만 사업연도 환산 포함)."""
    return _ok({"산출세액": C.corp_tax(base, year, months), "과세표준": base, "사업연도": year, "월수": months}, "법인세법 제55조(세율)·제55조②(1년 미만)")


@mcp.tool(annotations=CALC)
@_guard
def entertainment_limit(year: YEAR, sme: Annotated[bool, Field(description="중소기업 여부")],
                        general_revenue: Annotated[int, Field(description="일반 수입금액(원)")],
                        expensed: Annotated[int, Field(description="비용 계상 기업업무추진비(원, 증빙 미수취분 포함)")],
                        related_revenue: Annotated[int, Field(description="특수관계인 거래 수입금액(원)")] = 0,
                        culture: Annotated[int, Field(description="문화 기업업무추진비(원)")] = 0,
                        months: Annotated[int, Field(description="사업연도 월수", ge=1, le=12)] = 12) -> dict:
    """Entertainment expense limit and excess. 기업업무추진비(접대비) 한도와 한도초과액(손금불산입·기타사외유출)."""
    return _ok(C.entertain(year, sme, general_revenue, related_revenue, expensed, culture=culture, months=months),
               "법인세법 제25조, 시행령 제42조")


@mcp.tool(annotations=CALC)
@_guard
def deemed_interest(movements: Annotated[list[dict], Field(description="가지급금 증감 [{date:'YYYY-MM-DD', amount:원(대여 +, 회수 -)}]")],
                    year_end: Annotated[str, Field(description="사업연도 종료일 YYYY-MM-DD")],
                    market_rate: Annotated[float, Field(description="시가 이자율(소수). 가중평균차입이자율 원칙, 예외 당좌대출이자율 0.046")] = 0.046,
                    charged_rate: Annotated[float, Field(description="실제 받은 이자율(소수)")] = 0.0) -> dict:
    """Deemed interest on loans to related parties. 가지급금 인정이자 — 적수와 시가 이자, 부당행위 기준(3억·5%) 판정, 익금산입액."""
    mv = [(m["date"], int(m["amount"])) for m in movements]
    j = C.jeoksu(mv, year_end)
    days = 366 if date.fromisoformat(year_end).year % 4 == 0 else 365
    return _ok({"적수": j, **C.deemed_interest_check(market_rate, charged_rate, j, days)},
               "법인세법 제52조, 시행령 제88조③·제89조③, 시행규칙 제43조(이자율)")


@mcp.tool(annotations=CALC)
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
def minimum_tax(base_before_incentives: Annotated[int, Field(description="감면 전 과세표준(원)")], year: YEAR,
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
def retirement_income_tax(income: WON, years_of_service: Annotated[int, Field(description="근속연수", ge=1, le=60)]) -> dict:
    """Retirement income tax. 퇴직소득세(근속연수공제·환산급여 방식)."""
    return _ok({"퇴직소득세": I.retirement_tax(income, years_of_service)}, "소득세법 제48조·제55조②")


@mcp.tool(annotations=CALC)
@_guard
def vat_deemed_rent(deposit: WON, days: Annotated[int, Field(description="과세기간 중 임대 일수", ge=1, le=184)],
                    period: Annotated[str, Field(description="과세기간 'YYYY-1' 또는 'YYYY-2' (정기예금이자율 연도표)")]) -> dict:
    """VAT deemed rent on lease deposits. 간주임대료(보증금 × 정기예금이자율 × 일수/365)."""
    return _ok({"간주임대료": V.deemed_rent(deposit, days, period=period)}, "부가가치세법 시행령 제65조")


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
