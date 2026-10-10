"""korean-tax-calc-mcp — 한국어 세금 계산 MCP 서버(코드 계산, AI 없음).

세율·한도·가산세는 사업연도·과세기간·공급일 기준 연도표(2016~2026)로 계산하고, 표에 없는 연도는 추정하지 않고 멈춘다.
결과마다 근거 조문을 붙인다. 근거 원문은 korean-tax-mcp(law_article)로 확인한다.
"""
import functools
import os
from datetime import date
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .engine import calc as K, calc_cit as C, calc_income as I, calc_vat as V

# ── 세무조사 판정 도구 (audit 패키지) ──
from .audit.agents import related as _R
from .audit.agents.related_intake import norm_name
from .audit.agents.tunnel_intake import upstage as _tunnel_upstage
from .audit.agents.return_intake import upstage as _return_upstage
from .audit.agents.precheck import corp as _precheck_corp, vat as _precheck_vat, income as _precheck_income, run as _precheck_run
from .audit.agents.precheck.needs import guide as _precheck_guide
from .audit.agents.precheck import REGISTRY as _AUDIT_REGISTRY, Data as _AuditData, Missing as _AuditMissing
from .audit.agents import calc as _audit_calc, related as _audit_related

AUDIT_INSTRUCTIONS = (
    "한국 세무조사 판정 도구. 특수관계인 판정은 반드시 기준일(사실관계 시점, YYYY-MM-DD)을 넣는다 — "
    "친족 범위(2023.3.1. 전 6촌·4촌, 이후 4촌·3촌)와 조문 위치가 시점마다 다르다. "
    "결과의 '근거'를 그대로 인용하고, 도구가 '확인 필요'라고 한 부분은 추측으로 채우지 않는다. "
    "PDF에서 표를 뽑는 도구만 Upstage(Document Parse + Solar Pro 4)로 전송하며, 나머지는 로컬 계산이다.")

AI_GENERATED = "이 결과의 표 추출·정리는 생성형 AI(Upstage Solar Pro 4)가 수행했습니다. 사람이 원본과 대조해 확인하세요."
AI_GENERATED_EN = "Table extraction and organization in this result was performed by generative AI (Upstage Solar Pro 4). Please verify against the original document."

def _upstage_key():
    import os
    return os.environ.get("UPSTAGE_API_KEY")

def _pdf_guard(fn):
    """PDF 도구용 가드: 키 없으면 mode=host_ai로 로컬 추출, 있으면 solar_cloud."""
    @functools.wraps(fn)
    def w(*a, **k):
        if not _upstage_key():
            return _host_ai_response(k.get("pdf_path", ""), fn.__name__)
        try:
            return fn(*a, **k)
        except Exception as e:
            return {"error": str(e), "안내": "PDF 처리 중 오류 — 문서 형식·내용을 확인하세요"}
    return w


HOST_AI_CLEANUP = (
    "정리 안내 — 추출한 텍스트를 아래 형식으로 다듬어 다음 도구에 넣으세요.\n"
    "■ 추출 텍스트: pypdf로 PDF에서 로컬 추출한 텍스트(위 '추출 텍스트' 필드). 페이지 순서로 붙어 있으며 표·그림은 포함되지 않을 수 있습니다.\n"
    "※ 이 결과는 설치한 컴퓨터의 pypdf가 추출한 것입니다 — 사용자에게 보여 줄 때 AI가 추출한 것임을 표시하세요.\n"
    "※ UPSTAGE_API_KEY를 설정하면 Document Parse + Solar Pro 4로 더 정교한 표 추출이 가능합니다(선택 사항).\n"
)

_SCAN_GUIDE = (
    "이 PDF는 텍스트가 거의 없는 스캔 이미지로 보입니다. "
    "지금 쓰는 AI에게 이 PDF를 직접 첨부해 읽게 한 뒤, 아래 정리 안내 형식으로 다음 도구에 넣으세요. "
    "다음 도구 호출 예시도 정리 안내 안에 함께 들어 있습니다."
)

_NEXT_TOOLS = {
    "extract_relations": "related_judge — 사람·가족·지분 관계를 판정으로 연결",
    "tunnelling_from_pdf": "tunnelling_gift_nts — 일감몰아주기 증여의제이익 계산",
    "return_precheck_pdf": "return_precheck — 신고서 사전검토(오류 의심 목록)",
}

_TOOL_CASE_DOC = (
    "people: {이름: {\"구분\": \"개인\"|\"법인\"}}\n"
    "family: [[a, b, \"부모자녀\"|\"배우자\"]] — 부모자녀는 [부모, 자녀]\n"
    "stakes: [[보유자, 법인, 지분율(0~1)]] — 직접보유비율\n"
    "officers/employees: {법인: [이름]}, livelihood: [[부양자, 피부양자]], "
    "influence: [[사실상 영향력자, 법인]], group: {기업집단: [계열회사]}"
)

_TOOL_TUNNEL_GUIDE = (
    "size=중소|중견|일반, sales_by_corp={거래처 법인: 매출액}, "
    "excluded_sales=⑩항 과세제외매출액(입력). relations={관계명: 보유비율}(예: {'직접':0.2,'A경유':0.18}), "
    "holdings_in_related={특관법인: 지배주주등 보유비율}, "
    "indirect_corp_of={관계명: 그 경로 간접출자법인}, "
    "excluded_by_corp={특관법인: ⑩항 과세제외액}. "
    " 국세청 2026 신고안내 작성사례 원 단위 검증."
)

_TOOL_PRECCHECK_GUIDE = (
    "data={입력키: 값} — 입력키는 agents/precheck/{corp,vat,income}.py SCHEMA. "
    "tax=법인|부가|소득(생략 시 전체). 예: {\"신고서.수입금액\": 5000000000, \"조정계산서.산출세액\": 50000000}"
)


def _host_ai_response(pdf_path: str, tool_name: str | None = None) -> dict:
    """UPSTAGE_API_KEY 없이 PDF 도구 호출 → mode=host_ai 응답자."""
    from .audit.agents import upstage
    raw = upstage.extract_text_local(pdf_path)
    text = raw.strip()
    scanned = len(text) < 200  # 텍스트 거의 없음 → 스캔 PDF

    extraction_text = text[:20000] if text else ""
    next_tool_fn = _NEXT_TOOLS.get(tool_name, "해당 도구")

    if scanned:
        guidance = _SCAN_GUIDE + "\n\n" + _cleanup_guide(tool_name)
        extraction_text = "(스캔 PDF — pypdf 텍스트 추출 결과 없음. PDF를 지금 쓰는 AI에 첨부해 읽게 한 뒤 아래 형식으로 정리하세요.)"
    else:
        guidance = _cleanup_guide(tool_name)

    return {
        "mode": "host_ai",
        "추출 텍스트": extraction_text,
        "정리 안내": guidance + f"\n다음 도구: {next_tool_fn}",
        "다음 도구": next_tool_fn,
        "선택": ("UPSTAGE_API_KEY를 설정하면 Document Parse + Solar Pro 4로 더 정교한 표 추출이 가능합니다." if not scanned else
                 "UPSTAGE_API_KEY를 설정하면 Document Parse + Solar Pro 4로 OCR·표 추출이 가능합니다."),
    }


def _cleanup_guide(tool_name: str) -> str:
    """도구별 정리 안내 텍스트(다음 도구 입력 형식 + 예시)."""
    common = "※ 이 결과는 설치한 컴퓨터의 pypdf가 추출한 것입니다 — 사용자에게 보여 줄 때 AI가 추출한 것임을 표시하세요.\n"
    if tool_name == "extract_relations":
        return (common +
                "INPUT 포맷(CASE_DOC):\n" + _TOOL_CASE_DOC + "\n\n"
                "예시:\n"
                "people: {\"김갑\": {\"구분\": \"개인\"}, \"㈜대한\": {\"구분\": \"법인\"}}\n"
                "family: [[\"김갑\", \"김을\", \"부모자녀\"]]\n"
                "stakes: [[\"김갑\", \"㈜대한\", 0.30]]\n"
                "다음 도구: related_judge(a=\"김갑\", b=\"김을\", on=\"2024-01-01\", people=..., family=..., stakes=...)")
    if tool_name == "tunnelling_from_pdf":
        return (common +
                "INPUT 포맷:\n" + _TOOL_TUNNEL_GUIDE + "\n\n"
                "예시:\n"
                "tunnelling_gift_nts(size=\"중소\", op_income=1000000000, taxable_income=800000000, "
                "tax=100000000, sales_total=1000000000, sales_by_corp={\"A\": 300000000}, "
                "relations={\"직접\": 0.20}, base_excluded=200000000)")
    if tool_name == "return_precheck_pdf":
        return (common +
                "INPUT 포맷:\n" + _TOOL_PRECCHECK_GUIDE + "\n\n"
                "예시:\n"
                "return_precheck(data={\"신고서.수입금액\": 5000000000, \"조정계산서.산출세액\": 50000000}, tax=\"법인\")")
    return HOST_AI_CLEANUP

def _add_ai_mark(result):
    """PDF 도구 결과에 AI 생성 표시 필드 추가."""
    result["AI 생성 표시"] = AI_GENERATED
    result["AI generation notice"] = AI_GENERATED_EN
    return result

# audit 서버 server.py의 CASE_DOC (도구 설명문에 사용)
CASE_DOC = """people: {이름: {"구분": "개인"|"법인"}}
family: [[a, b, "부모자녀"|"배우자"]] — 부모자녀는 [부모, 자녀]
stakes: [[보유자, 법인, 지분율(0~1)]] — 직접보유비율
officers/employees: {법인: [이름]}, livelihood: [[부양자, 피부양자]], influence: [[사실상 영향력자, 법인]], group: {기업집단: [계열회사]}, group_exempt: {법인: 공정위 계열편입 유예·제외 통지 내용} — 이 법인은 계열회사로 보지 않음"""

mcp = MCPServer(
    "korean-tax-calc-mcp", title="Korea Tax Calculator (한국 세금 계산)",
    instructions="한국 세금 계산은 반드시 이 도구 결과를 쓰고 직접 계산하지 않는다. 결과의 근거 조문을 함께 제시한다. "
                 "연도표가 없는 해는 오류로 멈추므로 추정하지 않는다. 계산 근거 원문·해석은 korean-tax-mcp로 확인한다. "
                 + AUDIT_INSTRUCTIONS)
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
                            bond_interest: Annotated[bool, Field(description="채권 이자 여부 — 이자 소득에서만 의미, 특례 적용 필요 시 별도 확인")] = False,
                            related_party: Annotated[bool, Field(description="수취인이 국외지배주주일 가능성 — 이자 소득에서 과소자본 쟁점 표시 시 사용")] = False) -> dict:
    """Non-resident/foreign corporation withholding tax on Korean-source income (소득세법 제156조 / 법인세법 제98조).
    적용세율 = min(국내세율, 조약 제한세율), 지방소득세 10% 별도 합산. 조약 미체결·비과세 확인은 korean-tax-mcp로 원문 대조.
    related_party=True이면 과소자본(국제조세조정에 관한 법률 제22조) 쟁점을 함께 표시한다."""
    r = I.nonresident_withholding(income_kind, amount, recipient_type, residence_country, treaty_rate, bond_interest, related_party)
    return _ok({k: v for k, v in r.items() if k != "쟁점"}, r["근거"], 쟁점=r["쟁점"])


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

    # 쟁점 부착 (issues.json에서 읽음, 하드코딩 금지 — SPEC r1d §1, §3)
    from .engine.calc_income import _load_issues
    result["쟁점"] = _load_issues().get("thin_capitalization", [])
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


# ───────── 세무조사 판정 도구 11개 ─────────
@mcp.tool(description="두 당사자가 국세기본법·법인세법·상증법 기준으로 특수관계인지, 몇 호인지 판정한다. "
                      "on=사실관계 시점(YYYY-MM-DD). 그 시점 시행 조문 위치를 법제처에서 받아 근거로 붙인다.\n" + CASE_DOC)
def related_judge(a: str, b: str, on: str, people: dict, family: list, stakes: list, officers: dict | None = None,
                  employees: dict | None = None, livelihood: list | None = None, influence: list | None = None,
                  group: dict | None = None, group_exempt: dict | None = None, with_citation: bool = True) -> dict:
    from .audit.agents.related_intake import normalize, to_case
    case = to_case(normalize({"people": people, "family": family, "stakes": stakes, "officers": officers, "employees": employees,
                              "livelihood": livelihood, "influence": influence, "group": group}))
    case["group_exempt"] = {norm_name(k): v for k, v in (group_exempt or {}).items()}
    a, b = norm_name(a), norm_name(b)
    return _R.judge_all_at(case, a, b, on) if with_citation else _R.judge_all(case, a, b, on)


@mcp.tool(description="두 개인의 친족관계(혈족·인척 촌수, 배우자)와 기준일 친족 범위 해당 여부. family 형식은 related_judge와 같음.")
def kinship_check(a: str, b: str, on: str, family: list) -> dict:
    fam = [tuple(x) for x in family]
    blood, inlaw = _R.kin_limits(on)
    k = _R.kinship(fam, a, b)
    return {"관계": k, "기준일": on, "범위": f"혈족 {blood}촌·인척 {inlaw}촌·배우자",
            "국기법_친족": _R.is_kin(fam, a, b, "국기", on), "상증법_친족(사돈 포함)": _R.is_kin(fam, a, b, "상증", on)}


@mcp.tool(description="보유자→법인 직접·간접 보유비율. 간접은 단계별 직접보유비율의 곱, 경로별 합산, 순환출자는 단계별 모두 반영(상증령 제34조의3②).")
def ownership_ratio(holder: str, target: str, stakes: list) -> dict:
    st = [(h, c, float(r)) for h, c, r in stakes]
    ps = _R.paths(st, holder, target)
    return {"직접": _R.direct(st, holder, target), "경로": [{"경로": " → ".join(p), "비율": r} for p, r in ps],
            "합계": sum(r for _, r in ps), "순환출자": _R.has_cycle(st)}


@mcp.tool(description="수혜법인의 지배주주 판정(상증령 제34조의3①). " + CASE_DOC)
def dominant_shareholder(corp: str, people: dict, family: list, stakes: list) -> dict:
    who, why = _R.dominant_shareholder(people, [tuple(x) for x in family], [(h, c, float(r)) for h, c, r in stakes], corp)
    return {"지배주주": who, "판정": why}


@mcp.tool(description="일감몰아주기 증여의제이익(상증법 제45조의3). size=중소|중견|일반, sales_by_corp={거래처 법인: 매출액}, "
                      "excluded_sales=과세제외매출액(⑩·⑭, 직접 계산해 입력). ⑮ 배당공제는 미반영.")
def tunnelling_gift(beneficiary: str, size: str, sales_total: float, sales_by_corp: dict, after_tax_op_profit: float,
                    people: dict, family: list, stakes: list, excluded_sales: float = 0) -> dict:
    return _R.tunnelling(people, [tuple(x) for x in family], [(h, c, float(r)) for h, c, r in stakes], beneficiary,
                        sales_total, sales_by_corp, after_tax_op_profit, size, excluded_sales)


@mcp.tool(description="일감몰아주기 증여의제이익 — 국세청 2026 신고안내 산식(세후영업이익 ⑫, 출자관계별 추가 과세제외 ⑭1·3호, 한계보유 ⑬). "
                      "size=중소|중견|일반. relations={관계명: 보유비율}(예: {'직접':0.2,'A경유':0.18}), indirect_corp_of={관계명: 그 경로 간접출자법인}, "
                      "holdings_in_related={특관법인: 지배주주등 보유비율}, excluded_by_corp={특관법인: ⑩항 과세제외액}(이 법인엔 ⑭항 미적용), "
                      "dividends={관계명: [배당소득, 분모]}(⑮항, 원 미만 절사). tax=법인세법 제55조 산출세액, land_tax=토지등 양도소득 법인세(차감), "
                      "credits=공제·감면세액(차감), unreturned_tax=미환류소득 법인세(tax에 빠져 있으면 입력, 포함이 맞음 — 기준-2023-법규재산-0125). 국세청 2026 신고안내 작성사례[1][2] 원 단위 검증.")
def tunnelling_gift_nts(size: str, op_income: float, taxable_income: float, tax: float, sales_total: float, sales_by_corp: dict,
                        relations: dict, base_excluded: float = 0, holdings_in_related: dict | None = None,
                        indirect_corp_of: dict | None = None, excluded_by_corp: dict | None = None,
                        dividends: dict | None = None, land_tax: float = 0, credits: float = 0,
                        unreturned_tax: float = 0) -> dict:
    return _R.tunnelling_nts("수혜법인", size, op_income, taxable_income, tax, sales_total, sales_by_corp, relations,
                            base_excluded, holdings_in_related, indirect_corp_of,
                            excluded_by_corp,
                            {k: tuple(v) for k, v in (dividends or {}).items()},
                            land_tax, credits, unreturned_tax)


@mcp.tool(description="특수관계인 범위 조문이 기준일에 어디 있었는지(law=국기|법인|상증). 예: 법인세 2019.2.11.까지 시행령 제87조①.")
def related_provision_at(law: str, on: str) -> dict:
    name, jo, head = _R.cite_at(law, on)
    return {"법령": name, "조항": jo, "원문": head, "기준일": on}


@mcp.tool(description="주주명부·가족관계·임원명단 PDF에서 관계표(people/family/stakes/officers)를 뽑는다. "
                      "UPSTAGE_API_KEY 없이도 pypdf로 로컬 텍스트 추출 후 related_judge 입력으로 정리 가능(기본). "
                      "키를 설정하면 Document Parse + Solar Pro 4로 더 정교한 표 추출. 결과는 초안 — related_judge에 넣기 전에 사람이 확인.")
@_pdf_guard
def extract_relations(pdf_path: str) -> dict:
    from .audit.agents import related_intake
    return _add_ai_mark(related_intake.from_pdf(pdf_path))


@mcp.tool(description="일감몰아주기 검토 자료 PDF → 표 추출 → 코드가 지배주주·출자관계·증여의제이익 계산. "
                      "UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 입력 정리 가능(기본). "
                      "키를 설정하면 Document Parse + Solar Pro 4로 더 정교한 표 추출. 결과는 사람 확인.")
@_pdf_guard
def tunnelling_from_pdf(pdf_path: str) -> dict:
    from .audit.agents import tunnel_intake
    return _add_ai_mark(tunnel_intake.from_pdf(pdf_path))


@mcp.tool(description="신고서 사전검토(조사 착수 전 오류 의심 목록): data={입력키: 값}, tax=법인|부가|소득(생략 시 전체). "
                      "입력키는 agents/precheck/{corp,vat,income}.py SCHEMA. 결과: 오류 의심·이상 없음·자료 부족·사실 확인 필요.")
def return_precheck(data: dict, tax: str | None = None) -> dict:
    return _precheck_run(data, tax)


@mcp.tool(description="법인세 신고서 PDF(별지 1·3·50호) → 표 추출 → 사전검토(오류 의심 목록). "
                      "UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 return_precheck 입력으로 정리 가능(기본). "
                      "키를 설정하면 Document Parse + Solar Pro 4로 더 정교한 표 추출. 결과는 서식 간 대사·세액 체인 재계산 포함.")
@_pdf_guard
def return_precheck_pdf(pdf_path: str) -> dict:
    from .audit.agents import return_intake
    return _add_ai_mark(return_intake.precheck_pdf(pdf_path))


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
