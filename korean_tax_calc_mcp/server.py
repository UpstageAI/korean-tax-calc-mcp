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
    instructions="계산 문제는 먼저 해당 계산 도구가 있는지 확인하고, 문제 자료를 도구 입력으로 옮겨 계산할 것. "
                 "도구 결과의 단계별 값을 그대로 인용할 것. "
                 "한국 세금 계산은 반드시 이 도구 결과를 쓰고 직접 계산하지 않는다. 결과의 근거 조문을 함께 제시한다. "
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


# ── 세무조사 판정 도구 입력 스키마 (SPEC c5 §3) ──
class PersonEntry(BaseModel):
    구분: Literal["개인", "법인"] = "개인"


class FamilyLink(BaseModel):
    a: str
    b: str
    관계: Literal["부모자녀", "배우자"]


class StakeEntry(BaseModel):
    보유자: str
    법인: str
    지분율: Annotated[float, Field(description="직접보유비율(소수, 0~1)")]


class OfficerEntry(BaseModel):
    법인: str
    이름: list[str]


class LivelihoodLink(BaseModel):
    부양자: str
    피부양자: str


class InfluenceEntry(BaseModel):
    영향력자: str
    법인: str


class GroupEntry(BaseModel):
    기업집단: str
    계열회사: list[str]


class GroupExemptEntry(BaseModel):
    법인: str
    통지내용: str


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
                  months: Annotated[int, Field(description="사업연도 월수(1년 미만이면 1~11)")] = 12) -> dict:
    """법인세 산출세액(사업연도 과세표준 × 세율표, 1년 미만 사업연도 월할 환산). 언제: 법인세 신고·세무조정에서 과세표준이 정해졌을 때 산출세액을 구한다.
입력: 과세표준(과세표준, 원) → base, 사업연도(2016~2026) → year, 월수(1~12) → months.
결과: 산출세액·과세표준·사업연도·월수와 근거(법인세법 제55조①·②). Corporate income tax on a tax base for a fiscal year (rate table, prorated for short fiscal years)."""
    return _ok({"산출세액": C.corp_tax(base, year, months), "과세표준": base, "사업연도": year, "월수": months}, "법인세법 제55조(세율)·제55조②(1년 미만)")


@mcp.tool(annotations=CALC)
@_guard
def entertainment_limit(year: YEAR, sme: Annotated[bool, Field(description="중소기업 여부")],
                        general_revenue: WON,
                        expensed: WON,
                        related_revenue: WON = 0,
                        culture: WON = 0,
                        months: Annotated[int, Field(description="사업연도 월수(1~12)")] = 12) -> dict:
    """기업업무추진비(접대비) 한도와 한도초과액. 언제: 법인세 세무조정에서 기업업무추진비 손금불산입액을 구할 때.
입력: 수입금액(일반) → general_revenue, 특수관계인 수입 → related_revenue, 중소기업 여부 → sme, 지출액(접대비) → expensed, 문화비 → culture, 사업연도 월수 → months.
결과: 한도·한도초과액(손금불산입)·근거(법인세법 제25조, 시행령 제42조). 기업업무추진비 한도와 한도초과액 계산; 접대비가 한도를 넘는가 확인할 때 쓴다."""
    return _ok(C.entertain(year, sme, general_revenue, related_revenue, expensed, culture=culture, months=months),
               "법인세법 제25조, 시행령 제42조")


@mcp.tool(annotations=CALC)
@_guard
def deemed_interest(movements: Annotated[list[Movement], Field(description="가지급금 증감 목록 [{date:'YYYY-MM-DD', amount:원(대여 +, 회수 -)}]")],
                    year_end: Annotated[str, Field(description="사업연도 종료일(YYYY-MM-DD)")],
                    market_rate: Annotated[float, Field(description="시가 이자율(소수, 예: 0.046 = 4.6%). 가중평균차입이자율 원칙, 예외 시 당좌대출이자율 0.046")] = 0.046,
                    charged_rate: Annotated[float, Field(description="실제 받은 이자율(소수, 예: 0.0 = 무수익)")] = 0.0) -> dict:
    """가지급금 인정이자(적수 × 시가 이자율)와 부당행위계산 여부. 언제: 특수관계인 가지급금 이자와 부당행위 3억·5% 판정을 함께 구할 때.
입력: 가지급금 증감 [{date, amount(원, 대여 +, 회수 -)}] → movements, 사업연도 종료일(YYYY-MM-DD) → year_end, 시가 이자율(소수) → market_rate, 실제 이자율(소수) → charged_rate.
결과: 적수·시가이자·실제이자·차액·익금산입액·부당행위 여부, 근거(법인세법 제52조, 시행령 제88조③·제89조③, 시행규칙 제43조)."""
    mv = [(m.date, int(m.amount)) for m in movements]
    j = C.jeoksu(mv, year_end)
    days = 366 if date.fromisoformat(year_end).year % 4 == 0 else 365
    return _ok({"적수": j, **C.deemed_interest_check(market_rate, charged_rate, j, days)},
               "법인세법 제52조, 시행령 제88조③·제89조③, 시행규칙 제43조(이자율)")


@mcp.tool(annotations=CALC)
@_guard
def unfair_transaction(market_price: Annotated[float, Field(description="시가(단가, 원)")], actual_price: Annotated[float, Field(description="실제 거래 단가(원)")],
                       quantity: Annotated[int, Field(description="수량")]) -> dict:
    """부당행위계산 기준(시가와 실제 거래가 차이 3억 원 이상 또는 5% 이상). 언제: 특수관계인 거래 prices가 시가와 크게 차이 나 부당행위계산 부인 대상인지 확인할 때.
입력: 시가(단가, 원) → market_price, 실제 거래 단가(원) → actual_price, 수량 → quantity.
결과: 시가총액·차액·차액비율·부당행위계산 여부, 근거(법인세법 제52조, 시행령 제88조③). 부당행위계산 기준(시가와 실제 거래가 차액이 3억 원 이상 또는 5% 이상이면 부인 대상)."""
    gap = abs(market_price - actual_price) * quantity; base = market_price * quantity
    return _ok({"시가총액": int(base), "차액": int(gap), "차액비율": round(gap / base, 4) if base else None,
                "부당행위계산": bool(gap >= 300_000_000 or (base and gap >= base * 0.05))}, "법인세법 제52조, 시행령 제88조③")


@mcp.tool(annotations=CALC)
@_guard
def loss_carryforward_limit(year: YEAR, sme: Annotated[bool, Field(description="중소기업 등 여부")]) -> dict:
    """이월결손금 공제 한도율(사업연도 개시일 기준). 언제: 이월결손금이 있을 때 해당 사업연도에 얼마까지 공제되는지 한도율을 확인한다.
입력: 사업연도(2016~2026) → year, 중소기업 등 여부 → sme.
결과: 한도율(소수)과 근거(법인세법 제13조① 단서). Limit on using loss carryforwards in a year; returns the deduction limit ratio by fiscal year start."""
    return _ok({"한도율": C.loss_limit_ratio(year, sme)}, "법인세법 제13조① 단서")


@mcp.tool(annotations=CALC)
@_guard
def minimum_tax(base_before_incentives: WON, year: YEAR,
                sme: Annotated[bool, Field(description="중소기업 여부")] = True,
                grace_year: Annotated[int, Field(description="중소기업 졸업 후 경과 연차(0=해당 없음, 0~5)")] = 0) -> dict:
    """최저한세(감면 전 과세표준 × 최저한세율). 언제: 세액감면·공제를 받은 뒤에도 납부해야 할 최저한세를 확인할 때(중소기업 졸업 유예 연차 포함).
입력: 감면 전 과세표준(원) → base_before_incentives, 사업연도(2016~2026) → year, 중소기업 여부 → sme, 졸업 후 경과 연차(0~5) → grace_year.
결과: 최저한세액, 근거(조세특례제한법 제132조①). Minimum corporate tax = base before incentives × minimum tax rate."""
    return _ok({"최저한세": C.min_tax(base_before_incentives, sme=sme, grace_year=grace_year, year=year)}, "조세특례제한법 제132조①")


@mcp.tool(annotations=CALC)
def underreporting_penalty(additional_tax: WON, fraud: Annotated[bool, Field(description="부정행위로 인한 과소신고 여부")]) -> dict:
    """과소신고가산세(일반 과소신고 10%, 부정행위 40%). 언제: 신고한 세액보다 실제 세액이 더 클 때 가산세 금액을 구한다.
입력: 과소신고한 세액(원) → additional_tax, 부정행위 여부 → fraud.
결과: 가산세·적용 세율, 근거(국세기본법 제47조의3). Under-reporting penalty: 10% general, 40% for fraud."""
    return _ok({"가산세": K.penalty_underreport(additional_tax, fraud), "세율": 0.4 if fraud else 0.1}, "국세기본법 제47조의3")


@mcp.tool(annotations=CALC)
@_guard
def late_payment_penalty(unpaid_tax: WON, due: Annotated[str, Field(description="법정납부기한(YYYY-MM-DD)")],
                         until: Annotated[str, Field(description="납부일·고지일(YYYY-MM-DD)")]) -> dict:
    """납부지연가산세(미납 세액 × 일수 × 이율, 이율 변경일 기준 기간 안분). 언제: 세금을 법정납부기한보다 늦게 납부했을 때 일수분 가산세를 계산한다.
입력: 미납 세액(원) → unpaid_tax, 법정납부기한(YYYY-MM-DD) → due, 납부일·고지일(YYYY-MM-DD) → until.
결과: 가산세 총액, 근거(국세기본법 제47조의4, 시행령 제27조의4). Late payment penalty with daily rate split at rate-change dates."""
    return _ok(C.late_payment_penalty(unpaid_tax, due, until), "국세기본법 제47조의4, 시행령 제27조의4")


@mcp.tool(annotations=CALC)
@_guard
def invoice_penalty(supply_amount: WON, kind: Annotated[Literal["가공", "지연발급", "미발급", "미발급_종이", "지연전송", "미전송", "지연수취",
                                                               "매출처별합계표_미제출", "매출처별합계표_예정분확정제출", "신용카드매입공제"],
                                                       Field(description="가산세 유형 — 가공=실물 없는 발급·수취")],
                    supplied_on: Annotated[str, Field(description="공급일(발급·수취일) YYYY-MM-DD — 세율 기준 연도")] = "") -> dict:
    """세금계산서 가산세(가공 2%·3%·4%, 미발급 2%, 지연발급 1% 등, 공급일 기준 세율 적용). 언제: 세금계산서 발급·수취 의무를 위반했을 때 가산세 금액을 구한다.
입력: 공급가액(원) → supply_amount, 가산세 유형 → kind, 공급일(YYYY-MM-DD, 세율 기준) → supplied_on.
결과: 가산세·적용 세율, 근거(부가가치세법 제60조②⑤⑥⑦, 가공은 제60조③). VAT invoice penalties by type and supply date."""
    if kind == "가공":
        return _ok({"가산세": K.penalty_fake_invoice(supply_amount, supplied_on), "세율": K.fake_invoice_rate(supplied_on)}, "부가가치세법 제60조③")
    return _ok({"가산세": V.invoice_penalties(supply_amount, kind, supplied_on or None), "세율": V.invoice_penalty_rate(kind, supplied_on or None)}, "부가가치세법 제60조②⑤⑥⑦")


@mcp.tool(annotations=CALC)
def assessment_limitation(due_date: Annotated[str, Field(description="법정신고기한(YYYY-MM-DD, 부과할 수 있는 날 = 그 다음 날)")],
                          case: Annotated[Literal["일반", "무신고", "부정행위"], Field(description="일반(과소신고 등) / 무신고 / 부정행위로 포탈·환급")] = "일반",
                          offshore: Annotated[bool, Field(description="역외거래(국제거래 또는 국외 자산·용역 관련 거래) 여부")] = False,
                          inheritance_gift: Annotated[bool, Field(description="상속세·증여세 여부")] = False) -> dict:
    """국세 부과제척기간과 만료일(2020년 이후 부과분 기준 현행 조문). 언제: 어느 과세기간의 세금이든 부과·제척기간이 언제까지인지 역산한다.
입력: 법정신고기한(YYYY-MM-DD) → due_date, 부과 성격(일반·무신고·부정행위) → case, 역외거래 여부 → offshore, 상속세·증여세 여부 → inheritance_gift.
결과: 제척기간(년)·기산일·만료일, 근거(국세기본법 제26조의2①②④). 일반 5년(역외 7년), 무신고 7년(역외 10년), 부정행위 10년(역외 15년), 상속·증여 10년(부정 등 15년)."""
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
    """종합소득세 산출세액(귀속연도 세율표). 언제: 종합소득 과세표준이 정해지면 그에 대한 산출세액을 구한다(근로·사업·기타·이자·배당 등 종합과세 대상).
입력: 종합소득 과세표준(원) → base, 귀속연도(2016~2026) → year.
결과: 산출세액, 근거(소득세법 제55조). Comprehensive income tax on a tax base (year-specific rate table)."""
    return _ok({"산출세액": I.income_tax(base, year)}, "소득세법 제55조")


@mcp.tool(annotations=CALC)
@_guard
def withholding_tax(kind: Annotated[str, Field(description="소득 종류: 이자·배당·비영업대금·사업·기타·봉사료·일용·비실명·외국인직업운동가·온투업이자")],
                    amount: WON, year: Annotated[int, Field(description="지급연도(2016~2026)")] = 2025) -> dict:
    """국내 원천징수세액(소득세분). 언제: 이자·배당·사업·기타소득 등을 지급할 때 원천징수할 소득세액을 구한다.
입력: 소득 종류(이자·배당·비영업대금·사업·기타·봉사료·일용·비실명·외국인직업운동가·온투업이자) → kind, 지급액(원) → amount, 지급연도(2016~2026) → year.
결과: 원천징수세액·적용 세율, 근거(소득세법 제129조). 지방소득세 10% 별도. 비거주자·외국법인은 nonresident_withholding 사용. 국내 withholding tax (소득세분) on interest, dividends, business income, etc."""
    return _ok({"원천징수세액": I.withholding_tax(kind, amount, year), "세율": I.withholding_rate(kind, year)}, "소득세법 제129조",
               주의="지방소득세(소득세의 10%) 별도. 비거주자는 조세조약 제한세율 확인(korean-tax-mcp treaty_withholding_rates)")


@mcp.tool(annotations=CALC)
@_guard
def nonresident_withholding(income_kind: Annotated[Literal["이자", "배당", "사용료", "인적용역", "기타"],
                                                   Field(description="소득 종류(비거주자·외국법인 국내원천) — 이자·배당·사용료·인적용역·기타")],
                            amount: WON,
                            recipient_type: Annotated[Literal["개인", "법인"], Field(description="수취인 구분 — 개인(비거주자) / 법인(외국법인)")],
                            residence_country: Annotated[str, Field(description="거주지국(ISO 2자 코드 또는 국명)")],
                            treaty_rate: Annotated[float | None, Field(description="조세조약 제한세율(소수, 예: 0.15 = 15%). 생략 시 국내세율 적용")] = None,
                            bond_interest: Annotated[bool, Field(description="채권 이자 여부 — 이자 소득에서만 의미, 특례 적용 필요 시 별도 확인")] = False,
                            related_party: Annotated[bool, Field(description="수취인이 국외지배주주일 가능성 — 이자 소득에서 과소자본 쟁점 표시 시 사용")] = False) -> dict:
    """비거주자·외국법인 국내원천소득 원천징수(소득세법 제156조 / 법인세법 제98조). 언제: 비거주자·외국법인에 이자·배당·사용료·인적용역·기타 소득을 지급할 때 원천징수세액을 구한다.
입력: 소득 종류(이자·배당·사용료·인적용역·기타) → income_kind, 지급액(원) → amount, 수취인 구분(개인/법인) → recipient_type, 거주지국(ISO 2자 또는 국명) → residence_country, 조세조약 제한세율(소수) → treaty_rate, 채권 이자 여부 → bond_interest, 국외지배주주 가능성 → related_party.
결과: 원천징수세액·지방소득세·적용 세율·국내세율, 근거(소득세법 제156조 / 법인세법 제98조). 적용세율 = min(국내세율, 조약 제한세율), 지방소득세 10% 별도. Non-resident/foreign corporation withholding tax on Korean-source income."""
    r = I.nonresident_withholding(income_kind, amount, recipient_type, residence_country, treaty_rate, bond_interest, related_party)
    return _ok({k: v for k, v in r.items() if k != "쟁점"}, r["근거"], 쟁점=r["쟁점"])


@mcp.tool(annotations=CALC)
@_guard
def retirement_income_tax(income: Annotated[int, Field(description="퇴직소득금액(퇴직급여, 비과세 제외, 원)")],
                          years_of_service: Annotated[int, Field(description="근속연수(1~60년)")]) -> dict:
    """퇴직소득세(근속연수공제·환산급여 방식). 언제: 퇴직금(퇴직급여)을 지급할 때 퇴직소득세를 계산한다.
입력: 퇴직소득금액(퇴직급여, 비과세 제외, 원) → income, 근속연수(1~60년) → years_of_service.
결과: 퇴직소득세, 근거(소득세법 제48조·제55조②). Retirement income tax (근속연수공제·환산급여 방식)."""
    return _ok({"퇴직소득세": I.retirement_tax(income, years_of_service)}, "소득세법 제48조·제55조②")


@mcp.tool(annotations=CALC)
@_guard
def vat_deemed_rent(deposit: WON, days: Annotated[int, Field(description="과세기간 중 임대 일수(1~184)")],
                    period: Annotated[str, Field(description="과세기간('YYYY-1' 또는 'YYYY-2', 정기예금이자율 연도표 기준)")]) -> dict:
    """간주임대료(보증금 × 정기예금이자율 × 일수/365). 언제: 상가·오피스텔 등 임대 보증금을 받을 때 부가가치세 간주임대료를 계산한다.
입력: 보증금(원) → deposit, 과세기간 중 임대 일수(1~184) → days, 과세기간('YYYY-1' 또는 'YYYY-2') → period.
결과: 간주임대료, 근거(부가가치세법 시행령 제65조). VAT deemed rent on lease deposits."""
    return _ok({"간주임대료": V.deemed_rent(deposit, days, period=period)}, "부가가치세법 시행령 제65조")


# ───────── 0.2 추가: 법인세 세무조정 ─────────
@mcp.tool(annotations=CALC)
@_guard
def nonbusiness_interest_disallowance(loans: Annotated[list[Loan], Field(description="차입금별 [{interest: 지급이자(원), jeoksu: 차입금 적수(원·일)}]")],
                                      nonbusiness_jeoksu: Annotated[int, Field(description="업무무관자산·가지급금 적수 합(원·일)", ge=0)]) -> dict:
    """업무무관자산·가지급금 관련 지급이자 손금불산입. 언제: 업무무관자산이나 가지급금이 있을 때 지급이자 중 얼마를 손금불산입하는지 구한다.
입력: 차입금별 [{interest: 지급이자(원), jeoksu: 차입금 적수(원·일)}] → loans, 업무무관 적수 합(원·일) → nonbusiness_jeoksu.
결과: 손금불산입 이자, 근거(법인세법 제28조①4호, 시행령 제53조). 산식: 지급이자 × min(1, 업무무관 적수 ÷ 총 차입금 적수)."""
    r = C.nonbusiness_interest([(int(l.interest), int(l.jeoksu)) for l in loans])(nonbusiness_jeoksu)
    return _ok(r, "법인세법 제28조①4호, 시행령 제53조", 산식="지급이자 × min(1, 업무무관 적수 ÷ 차입금 적수)")


@mcp.tool(annotations=CALC)
@_guard
def business_car_expense(year: YEAR, upkeep: Annotated[int, Field(description="유지비(유류·보험·수선 등, 원)")],
                         depreciation: Annotated[int, Field(description="세법상 감가상각비(5년 정액, 원)")],
                         booked_depreciation: Annotated[int, Field(description="장부상 감가상각비(원)")],
                         log_kept: Annotated[bool, Field(description="운행기록부 작성 여부")],
                         business_ratio: Annotated[float | None, Field(description="운행기록상 업무사용비율(소수, 작성 시, 0~1)")] = None,
                         months: Annotated[int, Field(description="보유 월수(1~12)")] = 12,
                         rental_corp: Annotated[bool, Field(description="부동산임대업 주업 등 특정법인")] = False,
                         plate_ok: Annotated[bool, Field(description="법인 전용번호판 부착(2024년 이후 요건)")] = True) -> dict:
    """업무용승용차 관련비용 손금불산입(업무사용비율·사적사용·미작성 시 기준비율·감가상각 연 800만 원 한도). 언제: 임원·직원이 사용하는 승용차 관련비용을 어디까지 손금으로 인정할지 계산할 때.
입력: 사업연도(2016~2026) → year, 유지비(유류·보험·수선 등, 원) → upkeep, 세법상 감가상각비(5년 정액, 원) → depreciation, 장부상 감가상각비(원) → booked_depreciation, 운행기록부 작성 여부 → log_kept, 업무사용비율(소수, 작성 시) → business_ratio, 보유 월수(1~12) → months, 부동산임대업 주업 등 특정법인 여부 → rental_corp, 법인 전용번호판 부착 여부 → plate_ok.
결과: 업무사용비율·손금불산입·감가상각 한도 등, 근거(법인세법 제27조의2, 시행령 제50조의2)."""
    return _ok(C.business_car(year, upkeep, depreciation, booked_depreciation, log_kept, business_ratio, months, rental_corp, plate_ok),
               "법인세법 제27조의2, 시행령 제50조의2", 산식="미작성 시 업무사용비율 = min(1, 기준금액 ÷ 총비용), 감가상각 업무사용분 연 800만원 한도")


@mcp.tool(annotations=CALC)
@_guard
def donation_limit(year: YEAR, base_income: WON,
                   special: WON = 0, general: WON = 0,
                   carried_loss: WON = 0,
                   special_carry: WON = 0, general_carry: WON = 0,
                   sme: Annotated[bool, Field(description="중소기업 여부")] = True,
                   social_enterprise: Annotated[bool, Field(description="사회적기업 여부(일반한도 20% 적용)")] = False) -> dict:
    """기부금 손금산입 한도(특례기부금 50%, 일반기부금 10%)와 한도초과·이월. 언제: 기부금을 손금산입할 때 한도와 한도초과액을 구한다.
입력: 기준소득(과세표준 계산 전 소득금액, 원) → base_income, 특례기부금 지출액(원) → special, 일반기부금 지출액(원) → general, 결손금(원) → carried_loss, 특례 이월액(원) → special_carry, 일반 이월액(원) → general_carry, 중소기업 여부 → sme, 사회적기업 여부 → social_enterprise, 사업연도(2016~2026) → year.
결과: 한도·한도초과·이월 손금산입, 근거(법인세법 제24조)."""
    return _ok(C.donation(base_income, carried_loss, special, general, special_carry, general_carry, sme, social_enterprise, year=year),
               "법인세법 제24조", 산식="특례 = (기준소득 − 결손금) × 50%, 일반 = (기준소득 − 결손금 − 특례 손금산입) × 10%(사회적기업 20%)")


@mcp.tool(annotations=CALC)
def bad_debt_allowance(receivables: WON, loss_rate: Annotated[float, Field(description="대손실적률(소수, 예: 0.02 = 2%)", ge=0, le=1)],
                       set_amount: WON, prior_disallowed: WON = 0) -> dict:
    """대손충당금 한도(채권잔액 × max(1%, 대손실적률))와 한도초과. 언제: 매출채권 등에 대해 대손충당금을 설정할 때 손금산입 한도를 구한다.
입력: 채권잔액(원) → receivables, 대손실적률(소수, 예: 0.02 = 2%) → loss_rate, 설정할 대손충당금(원) → set_amount, 이전 disallowed(원) → prior_disallowed.
결과: 한도·한도초과, 근거(법인세법 제34조, 시행령 제61조②). Bad debt allowance limit."""
    return _ok(C.bad_debt_allowance(receivables, loss_rate, set_amount, prior_disallowed), "법인세법 제34조, 시행령 제61조②")


@mcp.tool(annotations=CALC)
@_guard
def thin_capitalization(equity: WON,
                        borrowings: WON,
                        total_interest: WON,
                        ratio: Annotated[float | int, Field(description="적용 배수(기본적으로 2, 금융업 등 업종 배수는 별도 확인)")] = 2,
                        year: YEAR = 2026,
                        recipient_residence_country: Annotated[str | None, Field(description="수취인 거주지국(ISO 2자 코드 또는 국명). 지정 시 배당 처분에 따른 원천징수 재계산 제공")] = None,
                        interest_treaty_rate: Annotated[float | None, Field(description="이자 조세조약 제한세율(소수, 예: 0.12 = 12%). 생략 시 국내세율 적용")] = None,
                        dividend_treaty_rate: Annotated[float | None, Field(description="배당 조세조약 제한세율(소수, 예: 0.15 = 15%). 생략 시 국내세율 적용")] = None,
                        recipient_type: Annotated[Literal['개인', '법인'], Field(description="수취인 구분 — 개인(비거주자) / 법인(외국법인)")] = '개인') -> dict:
    """과소자본 손금불산입(국제조세조정에 관한 법률 제22조). 언제: 국외지배주주로부터 차입한 금액이 출자금액의 기준 배수(기본 2배)를 초과할 때 초과분 지급이자를 손금불산입한다.
입력: 국외지배주주 출자금액(원) → equity, 차입금액(원) → borrowings, 지급이자 총액(원) → total_interest, 적용 배수(기본 2) → ratio, 사업연도(2016~2026) → year, 수취인 거주지국 → recipient_residence_country, 이자 조세조약 제한세율(소수) → interest_treaty_rate, 배당 조세조약 제한세율(소수) → dividend_treaty_rate, 수취인 구분(개인/법인) → recipient_type.
결과: 초과차입금·손금불산입 이자·처분(배당/기타사외유출), recipient_residence_country 지정 시 원천징수 재계산 결과 포함, 근거(국제조세조정에 관한 법률 제22조, 시행령 제34조). Thin capitalization disallowance."""
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
def missing_receipt_disallowance(year: YEAR, items: Annotated[list[ReceiptItem], Field(description="[{amount: 1회 지출액(원), qualified: 적격증빙 여부, congratulatory: 경조금 여부}]")]) -> dict:
    """적격증빙 미수취 기업업무추진비 손금불산입(건당 3만 원, 경조금 20만 원 초과 + 적격증빙 없음). 언제: 접대비 등을 지출했는데 적격증빙을 받지 못한 건이 있으면 손금불산입액을 구한다.
입력: 사업연도(2016~2026) → year, 지출 건 목록 [{amount: 1회 지출액(원), qualified: 적격증빙 여부, congratulatory: 경조금 여부}] → items.
결과: 손금불산입 합계액, 근거(법인세법 제25조②, 시행령 제41조①). 적격증빙 미수취 기업업무추진비 손금불산입."""
    return _ok({"손금불산입": C.receipt_disallowed(year, [(int(i.amount), bool(i.qualified), bool(i.congratulatory)) for i in items])},
               "법인세법 제25조②, 시행령 제41조①")


# ───────── 0.2 추가: 부가가치세 ─────────
@mcp.tool(annotations=CALC)
@_guard
def vat_deemed_input_credit(period: Annotated[str, Field(description="과세기간('YYYY-1' 또는 'YYYY-2')")],
                            industry: Annotated[Literal["음식점", "유흥", "제조", "제조_떡방앗간등", "기타"], Field(description="업종")],
                            purchase: Annotated[int, Field(description="면세농산물 등 매입가액(원)")] = 0,
                            base: Annotated[int, Field(description="해당 과세기간 과세표준(원). 없으면 taxable_supply 사용")] = 0,
                            individual: Annotated[bool, Field(description="개인사업자 여부")] = True, sme: Annotated[bool, Field(description="중소기업 여부(제조 법인)")] = True,
                            purchase_total: Annotated[int, Field(description="면세농산물 등 총 구입액( 운반비 포함 가능, 원)")] = 0,
                            freight_included: Annotated[int, Field(description="구입액에 포함된 채취 운반비(원) — 있으면 매입가액에서 제외")] = 0,
                            used_taxable: Annotated[int, Field(description="과세사업 사용·소비액(원)")] = 0,
                            used_exempt: Annotated[int, Field(description="면세사업 사용·판매액(원)")] = 0,
                            ending_inventory_common: Annotated[int, Field(description="실지귀속 불분명 기말재고(원)")] = 0,
                            taxable_supply: Annotated[int, Field(description="해당 기간 과세 공급가액(원)")] = 0,
                            exempt_supply: Annotated[int, Field(description="해당 기간 면세 공급가액(원)")] = 0) -> dict:
    """의제매입세액공제(면세농산물 등 매입가액 × 공제율, 연장·운반비율 제외·공통분 안분). 언제: 음식점·제조업 등에서 면세농산물 등을 매입할 때 의제매입세액공제를 계산한다.
입력: 과세기간('YYYY-1' 또는 'YYYY-2') → period, 업종 → industry, 면세농산물 등 매입가액(원) → purchase, 해당 과세기간 과세표준(원) → base, 개인사업자 여부 → individual, 중소기업 여부(제조 법인) → sme, 면세농산물 등 총 구입액(원) → purchase_total, 구입액에 포함된 운반비(원) → freight_included, 과세사업 사용·소비액(원) → used_taxable, 면세사업 사용·판매액(원) → used_exempt, 실지귀속 불분명 기말재고(원) → ending_inventory_common, 해당 기간 과세 공급가액(원) → taxable_supply, 해당 기간 면세 공급가액(원) → exempt_supply.
결과: 공제대상 매입가액·의제매입세액·공제율·한도율·과세비율·단계별 계산, 근거(부가가치세법 제42조, 시행령 제81조·제84조)."""
    from .engine.calc_vat import deemed_input, deemed_input_rate, deemed_input_limit_ratio
    from .engine.calc_vat import deemed_input, deemed_input_rate, deemed_input_limit_ratio

    # base가 없으면 taxable_supply를 base로 사용 (명세서 검산 예시 호환)
    effective_base = base if base > 0 else taxable_supply

    # 운반비 제외 비율 계산: 구입액 대비 운반비 비율 → 매입가액 비율로 걷어냄
    if purchase_total > 0 and freight_included > 0:
        freight_ratio = freight_included / purchase_total
        # 각 금액에 운반비 제외 비율 적용 (1 - freight_ratio)
        non_freight_factor = 1 - freight_ratio
        used_taxable_adj = int(used_taxable * non_freight_factor)
        used_exempt_adj = int(used_exempt * non_freight_factor)
        inventory_adj = int(ending_inventory_common * non_freight_factor)
    else:
        used_taxable_adj = used_taxable
        used_exempt_adj = used_exempt
        inventory_adj = ending_inventory_common

    # 과세 공급가액 비율 계산
    if taxable_supply > 0 and exempt_supply > 0:
        taxable_ratio = taxable_supply / (taxable_supply + exempt_supply)
    else:
        taxable_ratio = 1.0  # 과세만 있는 경우

    # 공제대상 매입가액 = 과세 사용분 + 공통 재고 × 과세 공급가액 비율
    eligible_purchase = used_taxable_adj + int(inventory_adj * taxable_ratio)

    # 기존 방식(purchase, base 사용)의 공제율·한도율
    num, den = deemed_input_rate(industry, period, individual, effective_base, sme)
    limit_ratio = deemed_input_limit_ratio(period, individual, industry == "음식점", effective_base)

    # 의제매입세액 계산
    deemed_tax = deemed_input(
        eligible_purchase if eligible_purchase > 0 else purchase,
        effective_base,
        rate_num=num, rate_den=den, limit_ratio=limit_ratio,
        period=period, industry=industry, individual=individual, sme=sme
    )

    # 운반비율 적용 결과
    freight_exclusion = {
        "총_구입액": purchase_total,
        "운반비": freight_included,
        "운반비_비율": freight_ratio if purchase_total > 0 else 0,
        "운반비_제외_계수": non_freight_factor if purchase_total > 0 else 1,
        "과세_사용분_조정": used_taxable_adj,
        "면세_사용분_조정": used_exempt_adj,
        "공통_재고_조정": inventory_adj,
    } if purchase_total > 0 else {}

    # 과세 공급가액 비율
    allocation = {
        "과세_공급가액": taxable_supply,
        "면세_공급가액": exempt_supply,
        "과세_공급가액_비율": taxable_ratio,
    } if taxable_supply > 0 else {}

    steps = [
        {"항목": "총 구입액(운반비 포함)", "금액": purchase_total, "근거": "부가가치세법 제42조"},
        {"항목": "채취 운반비", "금액": freight_included, "근거": "부가가치세법 제42조"},
        {"항목": "운반비 제외 비율", "금액": freight_ratio if purchase_total > 0 else 0, "근거": "부가가치세법 제42조"},
    ]
    if purchase_total > 0:
        steps.extend([
            {"항목": "운송비 제외 계수 (1 − 운반비 비율)", "금액": non_freight_factor, "근거": "부가가치세법 제42조"},
            {"항목": "과세 사용·소비액(운반비 제외)", "금액": used_taxable_adj, "근거": "부가가치세법 제42조"},
            {"항목": "면세 사용·판매액(운반비 제외)", "금액": used_exempt_adj, "근거": "부가가치세법 제42조"},
            {"항목": "공통 기말재고(실지귀속 불분명, 운반비 제외)", "금액": inventory_adj, "근거": "부가가치세법 제42조"},
        ])

    steps.extend([
        {"항목": "과세 공급가액", "금액": taxable_supply, "근거": "부가가치세법 시행령 제81조"},
        {"항목": "면세 공급가액", "금액": exempt_supply, "근거": "부가가치세법 시행령 제81조"},
        {"항목": "과세 공급가액 비율", "금액": taxable_ratio, "근거": "부가가치세법 시행령 제81조"},
    ])

    steps.extend([
        {"항목": "공제대상 매입가액 = 과세 사용분 + 공통 재고 × 과세비율", "금액": eligible_purchase, "근거": "부가가치세법 제42조, 시행령 제84조, 제81조"},
        {"항목": f"공제율 ({num}/{den})", "금액": f"{num}/{den}", "근거": "부가가치세법 제42조"},
        {"항목": f"한도율 ({limit_ratio})", "금액": limit_ratio, "근거": "부가가치세법 시행령 제84조"},
        {"항목": "의제매입세액 = min(공제대상 매입, 과세표준 × 한도율) × 공제율", "금액": deemed_tax, "근거": "부가가치세법 제42조"},
    ])

    result = {
        "공제대상_매입가액": eligible_purchase,
        "의제매입세액": deemed_tax,
        "공제율_분자": num,
        "공제율_분모": den,
        "한도율": limit_ratio,
        "과세_공급가액_비율": taxable_ratio,
        "운반비율_적용": freight_exclusion,
        "안분_정보": allocation,
        "단계별_계산": steps,
    }
    return _ok(result, "부가가치세법 제42조, 시행령 제81조·제84조",
               산식="공제대상 매입 = 과세 사용분 + 공통 재고 × 과세비율(운반비 제외 후), 의제매입세액 = min(공제대상 매입, 과세표준 × 한도율) × 공제율")


@mcp.tool(annotations=CALC)
@_guard
def vat_common_input_allocation(common_tax: WON, total_supply: WON, exempt_supply: WON) -> dict:
    """겸영사업자 공통매입세액 안분(불공제분 계산). 언제: 과세·면세 사업을 겸영할 때 공통 매입세액 중 얼마가 불공제인지 계산한다.
입력: 공통매입세액(원) → common_tax, 총공급가액(원) → total_supply, 면세공급가액(원) → exempt_supply.
결과: 불공제 매입세액, 근거(부가가치세법 시행령 제81조). 면세비율 5% 미만·공통매입세액 5만 원 미만이면 전액 공제. 불공제 = 공통매입세액 × 면세공급가액 ÷ 총공급가액. 겸영사업자 공통매입세액 안분(불공제분 계산)."""
    return _ok(V.common_input_allocation(common_tax, total_supply, exempt_supply), "부가가치세법 시행령 제81조", 산식="불공제 = 공통매입세액 × 면세공급가액 ÷ 총공급가액")


@mcp.tool(annotations=CALC)
@_guard
def vat_simplified_taxpayer(supply_incl_vat: Annotated[int, Field(description="공급대가(부가세 포함, 원)")],
                            value_added_rate: Annotated[float, Field(description="업종별 부가가치율(소수, 예: 0.15 = 15%, 0 초과 1 미만)")],
                            invoice_purchase_incl_vat: Annotated[int, Field(description="세금계산서 등 수취 매입 공급대가(원)")] = 0,
                            mileage_supply_incl_vat: Annotated[int, Field(description="자기적립마일리지 등 결제분 공급대가(원) — 과세표준에서 제외")] = 0,
                            card_cash_receipt_supply_incl_vat: Annotated[int, Field(description="신용카드매출전표·현금영수증 등 발급분 공급대가(원)")] = 0,
                            no_invoice_purchase_incl_vat: Annotated[int, Field(description="세금계산서 발급 의무자로부터 미수취한 매입 공급대가(원)")] = 0,
                            prior_year_supply_incl_vat: Annotated[int, Field(description="직전 연도 공급대가(원) — 납부의무 면제 판정 참조")] = 0,
                            prepaid_tax: Annotated[int, Field(description="예정부과 고지·수시부과세액(원)")] = 0,
                            year: Annotated[int, Field(description="적용 연도(2016~2026)")] = 2026) -> dict:
    """간이과세자 납부세액 전 과정(과세표준·납부세액·매입공제·카드 발행세액공제·가산세·납부의무 면제 판정·차가감 납부세액). 언제: 간이과세자 부가가치세 신고 시 납부세액을 단계별로 계산한다.
입력: 공급대가(부가세 포함, 원) → supply_incl_vat, 업종별 부가가치율(소수, 예: 0.15 = 15%) → value_added_rate, 세금계산서 등 수취 매입 공급대가(원) → invoice_purchase_incl_vat, 자기적립마일리지 등 결제분 공급대가(원) → mileage_supply_incl_vat, 신용카드매출전표·현금영수증 등 발급분 공급대가(원) → card_cash_receipt_supply_incl_vat, 세금계산서 미수취 매입 공급대가(원) → no_invoice_purchase_incl_vat, 직전 연도 공급대가(원) → prior_year_supply_incl_vat, 예정부과 고지·수시부과세액(원) → prepaid_tax, 적용 연도(2016~2026) → year.
결과: 과세표준·납부세액·매입공제·카드공제·가산세·공제합계·차가감 납부세액·납부의무 면제 여부·단계별 계산, 근거(부가가치세법 제46조·제63조·제68조의2·제69조)."""
    from .engine.calc_vat import simplified_exempt_threshold, card_sales_credit
    from .engine.calc_vat import simplified_exempt_threshold, card_sales_credit

    # 과세표준 = 공급대가 − 마일리지
    tax_base = supply_incl_vat - mileage_supply_incl_vat

    # 납부세액 = 과세표준 × 부가가치율 × 10%
    tax_due = int(tax_base * value_added_rate * 0.1)

    # 매입세금계산서 등 공제 = 수취 매입 × 0.5%
    input_credit = int(invoice_purchase_incl_vat * 0.005)

    # 신용카드매출전표등 발행세액공제 (제46조, 1.3%, 연 한도 1,000만원)
    card_credit = card_sales_credit(card_cash_receipt_supply_incl_vat, f"{year}-01-01")

    # 세금계산서 미수취 가산세 (제68조의2, 0.5%)
    no_invoice_penalty = int(no_invoice_purchase_incl_vat * 0.005)

    # 공제 합계 (납부세액 한도)
    total_credits = min(input_credit + card_credit, tax_due)

    # 가산세 합계
    total_penalties = no_invoice_penalty

    # 차가감 납부세액 = 납부세액 − 공제 합계 + 가산세 (공제는 납부세액 한도, 음수이면 0)
    net_tax = max(0, tax_due - total_credits) + total_penalties

    # 납부의무 면제 여부 (제69조, 과세기간 공급대가 4,800만원 미만)
    exempt_threshold = simplified_exempt_threshold(year)
    exempt = supply_incl_vat < exempt_threshold

    steps = [
        {"항목": "공급대가(부가세 포함)", "금액": supply_incl_vat, "근거": "부가법 제63조"},
        {"항목": "자기적립마일리지 등 차감", "금액": mileage_supply_incl_vat, "근거": "부가가치세법 제63조"},
        {"항목": "과세표준(공급대가 − 마일리지)", "금액": tax_base, "근거": "부가법 제63조"},
        {"항목": f"납부세액(과세표준 × 부가가치율 {value_added_rate} × 10%)", "금액": tax_due, "근거": "부가가치세법 제63조"},
        {"항목": "매입세금계산서 등 공제(수취 매입 × 0.5%)", "금액": input_credit, "근거": "부가가치세법 제63조"},
        {"항목": "신용카드매출전표등 발행세액공제(1.3%, 한도 1,000만원)", "금액": card_credit, "근거": "부가가치세법 제46조"},
        {"항목": "공제 합계(납부세액 한도)", "금액": total_credits, "근거": "부가가치세법 제63조"},
        {"항목": "세금계산서 미수취 가산세(0.5%)", "금액": no_invoice_penalty, "근거": "부가가치세법 제68조의2"},
        {"항목": "가산세 합계", "금액": total_penalties, "근거": "부가가치세법 제68조의2"},
        {"항목": "차가감 납부세액(납부세액 − 공제 + 가산세, 음수 0)", "금액": net_tax, "근거": "부가가치세법 제63조"},
        {"항목": f"납부의무 면제 여부(해당 과세기간 공급대가 {supply_incl_vat:,}원, 기준 {exempt_threshold:,}원 미만)", "금액": "면제" if exempt else "해당없음", "근거": "부가가치세법 제69조"},
    ]

    result = {
        "과세표준": tax_base,
        "납부세액": tax_due,
        "매입세금계산서등_공제": input_credit,
        "카드발행세액공제": card_credit,
        "가산세": total_penalties,
        "공제_합계": total_credits,
        "차가감_납부세액": net_tax,
        "납부의무_면제": exempt,
        "직전_연도_공급대가": prior_year_supply_incl_vat,
        "면제_기준": exempt_threshold,
        "단계별_계산": steps,
    }
    return _ok(result, "부가가치세법 제46조·제63조·제68조의2·제69조",
               산식="과세표준 = 공급대가 − 마일리지, 납부세액 = 과세표준 × 부가가치율 × 10%, 차가감 = max(0, 납부세액 − min(매입공제+카드공제, 납부세액)) + 가산세")


@mcp.tool(annotations=CALC)
@_guard
def vat_card_sales_credit(amount: Annotated[int, Field(description="신용카드·현금영수증 발급분 공급대가(원)")], supplied_on: Annotated[str, Field(description="공급일 YYYY-MM-DD")],
                          used_this_year: Annotated[int, Field(description="같은 해 이미 공제받은 금액(원)")] = 0) -> dict:
    """신용카드매출전표 등 발행세액공제(공제율 1.3%, 연 한도 1,000만 원). 언제: 개인사업자가 신용카드·현금영수증 매출에 대해 발행세액공제를 얼마나 받는지 계산한다.
입력: 신용카드·현금영수증 발급분 공급대가(원) → amount, 공급일(YYYY-MM-DD, 세율·한도 연도표 기준) → supplied_on, 같은 해 이미 공제받은 금액(원) → used_this_year.
결과: 공제액, 근거(부가가치세법 제46조). 신용카드매출전표 등 발행세액공제; 공제율 1.3%(간이 음식·숙박 2.6%는 2021.7.1. 전), 연 한도 1,000만 원(2018년 제2기 확정부터)."""
    return _ok({"공제액": V.card_sales_credit(amount, supplied_on, used_this_year=used_this_year)}, "부가가치세법 제46조")


@mcp.tool(annotations=CALC)
def vat_bad_debt_credit(bad_debt_incl_vat: Annotated[int, Field(description="대손금액(부가세 포함, 원)")]) -> dict:
    """대손세액공제(대손금액 × 10/110). 언제: 외상 매출이 대손되었을 때 부가가치세 대손세액공제를 계산한다.
입력: 대손금액(부가세 포함, 원) → bad_debt_incl_vat.
결과: 대손세액, 근거(부가가치세법 제45조①). VAT bad debt credit."""
    return _ok({"대손세액": V.bad_debt_vat(bad_debt_incl_vat)}, "부가가치세법 제45조①")


# ───────── 0.2 추가: 근로·원천 ─────────
@mcp.tool(annotations=CALC)
@_guard
def wage_income_tax(gross_pay: Annotated[int, Field(description="총급여(원, 비과세 제외)")], tax_base: Annotated[int, Field(description="종합소득 과세표준(원)")], year: YEAR) -> dict:
    """근로소득공제·산출세액·근로소득세액공제. 언제: 근로소득만 있는 근로자의 연말정산에서 근로소득공제, 산출세액, 근로소득 세액공제를 계산한다.
입력: 총급여(원, 비과세 제외) → gross_pay, 종합소득 과세표준(원) → tax_base, 귀속연도(2016~2026) → year.
결과: 근로소득공제·산출세액·근로소득세액공제, 근거(소득세법 제47조①·제55조·제59조). Wage income: employment income deduction, computed tax and wage tax credit."""
    t = I.income_tax(tax_base, year)
    return _ok({"근로소득공제": I.earned_deduction(gross_pay, year), "산출세액": t, "근로소득세액공제": I.earned_tax_credit(t, gross_pay, year=year)},
               "소득세법 제47조①·제55조·제59조", 주의="그 밖의 소득공제·세액공제는 별도")


@mcp.tool(annotations=CALC)
@_guard
def daily_worker_withholding(daily_wage: Annotated[int, Field(description="일급(원)")], year: Annotated[int, Field(description="지급연도(2016~2026)")] = 2025) -> dict:
    """일용근로자 원천징수세액((일급 − 15만 원) × 6% × (1 − 55%), 1천 원 미만 소액부징수). 언제: 일용근로자에게 일급을 지급할 때 원천징수할 세액을 계산한다.
입력: 일급(원) → daily_wage, 지급연도(2016~2026) → year.
결과: 원천징수세액, 근거(소득세법 제134조③·제129조①4호·제86조). Withholding on daily workers' wages."""
    return _ok({"원천징수세액": I.daily_worker_tax(daily_wage, year)}, "소득세법 제134조③·제129조①4호·제86조",
               산식="(일급 − 15만원) × 6% × (1 − 55%), 1천원 미만 부징수")


@mcp.tool(annotations=CALC)
@_guard
def deemed_bonus_resettlement(gross_pay: Annotated[int, Field(description="귀속연도 당초 총급여(원)")], tax_base: Annotated[int, Field(description="당초 과세표준(원)")],
                              bonus: Annotated[int, Field(description="소득처분 상여(원)")], year: YEAR,
                              other_credits: Annotated[int, Field(description="근로소득세액공제 외 세액공제 합계(원)")] = 0,
                              prev_decided: Annotated[int | None, Field(description="당초 결정세액(원). 모르면 생략")] = None) -> dict:
    """소득처분 상여 연말정산 재정산(추가 원천징수세액). 언제: 법인세 소득금액 변동으로 상여 처분이 발생했을 때 해당 근로자의 연말정산을 재정산해 추가 원천징수세액을 구한다.
입력: 귀속연도 당초 총급여(원) → gross_pay, 당초 과세표준(원) → tax_base, 소득처분 상여(원) → bonus, 귀속연도(2016~2026) → year, 근로소득세액공제 외 세액공제 합계(원) → other_credits, 당초 결정세액(원, 모르면 생략) → prev_decided.
결과: 추가 원천징수세액, 근거(법인세법 제67조, 소득세법 시행령 제192조, 소득세법 제137조). Year-end resettlement after a deemed bonus (income disposition) is added to wages."""
    return _ok(I.deemed_bonus_resettlement(gross_pay, tax_base, bonus, other_credits, prev_decided, year=year),
               "법인세법 제67조, 소득세법 시행령 제192조, 소득세법 제137조",
               주의="총급여 연동 소득·세액공제(신용카드 공제 등)는 수기 보정 필요")


# ───────── 세무조사 판정 도구 11개 ─────────
@mcp.tool(description="""두 당사자의 특수관계 여부·호수를 국세기본법·법인세법·상증법 기준으로 판정한다. 언제: 세무조사·증여의제 검토에서 두 사람·법인 간 특수관계와 적용 호수를 확인할 때.
입력: 당사자 a(이름) → a, 당사자 b(이름) → b, 사실관계 시점(YYYY-MM-DD, 필수) → on, people={이름: {구분: "개인"|"법인"}} → people, family=[[a, b, "부모자녀"|"배우자"]] → family, stakes=[[보유자, 법인, 지분율(0~1)]] → stakes, officers={법인: [이름]} → officers, employees={법인: [이름]} → employees, livelihood=[[부양자, 피부양자]] → livelihood, influence=[[사실상 영향력자, 법인]] → influence, group={기업집단: [계열회사]} → group, group_exempt={법인: 공정위 통지 내용} → group_exempt, 법령 인용 포함 여부 → with_citation.
결과: 특수관계 여부·적용 호수와 근거 조문(기준일 시행 법령 위치), 근거. 두 당사자의 특수관계 여부와 적용 호수를 국세기본법·법인세법·상증법 기준으로 판정한다(두 사람·법인 간 특수관계와 적용 호수 확인).""")
def related_judge(a: Annotated[str, Field(description='당사자 a(이름)')], b: Annotated[str, Field(description='당사자 b(이름)')],
                  on: Annotated[str, Field(description='사실관계 시점 YYYY-MM-DD(필수, 친족 범위·조문 위치가 시점마다 다름)')],
                  people: Annotated[dict, Field(description='사람·법인 목록 {이름: {"구분": "개인"|"법인"}. 예: {"김갑": {"구분": "개인"}, "㈜대한": {"구분": "법인"}}')],
                  family: Annotated[list, Field(description='친족 관계 목록 [[a, b, "부모자녀"|"배우자"]]. 예: [["김갑", "김을", "부모자녀"]] — 부모자녀는 [부모, 자녀] 순서')],
                  stakes: Annotated[list, Field(description='직접보유비율 목록 [[보유자, 법인, 지분율(0~1)]]. 예: [["김갑", "㈜대한", 0.30]]')],
                  officers: Annotated[dict | None, Field(description='임원 목록 {법인: [이름]}. 예: {"㈜대한": ["김갑"]}')] = None,
                  employees: Annotated[dict | None, Field(description='직원 목록 {법인: [이름]}. 예: {"㈜대한": ["김을"]}')] = None,
                  livelihood: Annotated[list | None, Field(description='부양 관계 [[부양자, 피부양자]]. 예: [["김갑", "김이쁜"]]')] = None,
                  influence: Annotated[list | None, Field(description='사실상 영향력 [[사실상 영향력자, 법인]]. 예: [["김갑", "㈜대한"]]')] = None,
                  group: Annotated[dict | None, Field(description='기업집단 {기업집단: [계열회사]}. 예: {"XX그룹": ["㈜대한", "㈜민국"]}')] = None,
                  group_exempt: Annotated[dict | None, Field(description='공정위 계열편입 유예·제외 통지 {법인: 통지 내용}. 예: {"㈜대한": "유예 통지"}')] = None,
                  with_citation: Annotated[bool, Field(description='법령 인용 포함 여부(기본 True)')] = True) -> dict:
    from .audit.agents.related_intake import normalize, to_case
    case = to_case(normalize({"people": people, "family": family, "stakes": stakes, "officers": officers, "employees": employees,
                              "livelihood": livelihood, "influence": influence, "group": group}))
    case["group_exempt"] = {norm_name(k): v for k, v in (group_exempt or {}).items()}
    a, b = norm_name(a), norm_name(b)
    return _R.judge_all_at(case, a, b, on) if with_citation else _R.judge_all(case, a, b, on)


@mcp.tool(description="""두 개인의 친족관계(혈족·인척 촌수, 배우자)와 기준일 친족 범위 해당 여부. 언제: 두 사람이 친족인지, 국세기본법·상증법상 친족 범위에 들어가는지 확인할 때.
입력: 당사자 a(이름) → a, 당사자 b(이름) → b, 기준일(YYYY-MM-DD) → on, family=[[a, b, "부모자녀"|"배우자"]] → family(related_judge와 동일 형식).
결과: 관계(촌수·배우자)·기준일·친족 범위·국기법 친족 여부·상증법 친족(사돈 포함) 여부. 두 개인의 친족관계(혈족·인척 촌수, 배우자)와 기준일 친족 범위 해당 여부를 확인한다.""")
def kinship_check(a: Annotated[str, Field(description='당사자 a(이름)')], b: Annotated[str, Field(description='당사자 b(이름)')],
                  on: Annotated[str, Field(description='기준일 YYYY-MM-DD')],
                  family: Annotated[list, Field(description='친족 관계 목록 [[a, b, "부모자녀"|"배우자"]]. 예: [["김갑", "김을", "부모자녀"]] — related_judge와 동일 형식')]) -> dict:
    fam = [tuple(x) for x in family]
    blood, inlaw = _R.kin_limits(on)
    k = _R.kinship(fam, a, b)
    return {"관계": k, "기준일": on, "범위": f"혈족 {blood}촌·인척 {inlaw}촌·배우자",
            "국기법_친족": _R.is_kin(fam, a, b, "국기", on), "상증법_친족(사돈 포함)": _R.is_kin(fam, a, b, "상증", on)}


@mcp.tool(description="""보유자→법인 직접·간접 보유비율(경로별 곱 합산, 순환출자 반영). 언제: 일감몰아주기·지배주주 판정에서 특정인이 법인에 얼마나 간접 보유하는지 계산할 때.
입력: 보유자(이름) → holder, 대상 법인(이름) → target, stakes=[[보유자, 법인, 지분율(0~1)]] → stakes(직접보유비율, related_judge와 동일).
결과: 직접비율·경로별 비율·합계·순환출자 여부, 근거(상증법 시행령 제34조의3②). 보유자→법인 직접·간접 보유비율을 계산한다(간접은 단계별 직접보유비율의 곱, 경로별 합산, 순환출자는 단계별 모두 반영).""")
def ownership_ratio(holder: Annotated[str, Field(description='보유자(이름)')], target: Annotated[str, Field(description='대상 법인(이름)')],
                    stakes: Annotated[list, Field(description='직접보유비율 목록 [[보유자, 법인, 지분율(0~1)]]. 예: [["김갑", "㈜대한", 0.30]]')]) -> dict:
    st = [(h, c, float(r)) for h, c, r in stakes]
    ps = _R.paths(st, holder, target)
    return {"직접": _R.direct(st, holder, target), "경로": [{"경로": " → ".join(p), "비율": r} for p, r in ps],
            "합계": sum(r for _, r in ps), "순환출자": _R.has_cycle(st)}


@mcp.tool(description="""수혜법인의 지배주주 판정(상증법 시행령 제34조의3①). 언제: 일감몰아주기 증여의제이익 계산에서 수혜법인의 지배주주가 누구인지 판정할 때.
입력: 수혜법인(이름) → corp, people={이름: {구분: "개인"|"법인"}} → people, family=[[a, b, "부모자녀"|"배우자"]] → family, stakes=[[보유자, 법인, 지분율(0~1)]] → stakes(related_judge와 동일 형식).
결과: 지배주주(이름)·판정 이유. 수혜법인의 지배주주를 판정한다Amid(중견기업 중 직접보유 최고자 / 법인이면 직접+간접 최고 개인).""")
def dominant_shareholder(corp: Annotated[str, Field(description='수혜법인(이름)')],
                         people: Annotated[dict, Field(description='사람·법인 목록 {이름: {"구분": "개인"|"법인"}}. 예: {"김갑": {"구분": "개인"}}')],
                         family: Annotated[list, Field(description='친족 관계 [[a, b, "부모자녀"|"배우자"]]. 예: [["김갑", "김을", "부모자녀"]]')],
                         stakes: Annotated[list, Field(description='직접보유비율 [[보유자, 법인, 지분율(0~1)]]. 예: [["김갑", "㈜대한", 0.30]]')]) -> dict:
    who, why = _R.dominant_shareholder(people, [tuple(x) for x in family], [(h, c, float(r)) for h, c, r in stakes], corp)
    return {"지배주주": who, "판정": why}


@mcp.tool(description="""일감몰아주기 증여의제이익(상증법 제45조의3, ⑩항 과세제외매출액 직접 입력, ⑭·⑮ 미반영). 언제: 일감몰아주기 검토에서 증여의제이익을 간단히 계산할 때(국세청 신고안내 전체 산식은 tunnelling_gift_nts 사용).
입력: 수혜자(이름) → beneficiary, 기업 규모(중소|중견|일반) → size, 총 매출액 → sales_total, sales_by_corp={거래처 법인: 매출액} → sales_by_corp, 세후영업이익 → after_tax_op_profit, people={이름: {구분: "개인"|"법인"}} → people, family=[[a, b, "부모자녀"|"배우자"]] → family, stakes=[[보유자, 법인, 지분율(0~1)]] → stakes, ⑩·⑭항 과세제외매출액 → excluded_sales.
결과: 증여의제이익, 근거(상증법 제45조의3, 시행령 제34조의3). 일감몰아주기 증여의제이익(상증법 제45조의3).""")
def tunnelling_gift(beneficiary: Annotated[str, Field(description='수혜자(이름)')],
                    size: Annotated[str, Field(description="기업 규모('중소'|'중견'|'일반')")],
                    sales_total: Annotated[float, Field(description="총 매출액(원)")],
                    sales_by_corp: Annotated[dict, Field(description='거래처 법인별 매출액 {법인: 매출액(원)}. 예: {"A": 300000000}')],
                    after_tax_op_profit: Annotated[float, Field(description="세후영업이익(원)")],
                    people: Annotated[dict, Field(description='사람·법인 목록 {이름: {"구분": "개인"|"법인"}}')],
                    family: Annotated[list, Field(description='친족 관계 [[a, b, "부모자녀"|"배우자"]]')],
                    stakes: Annotated[list, Field(description='직접보유비율 [[보유자, 법인, 지분율(0~1)]]')],
                    excluded_sales: Annotated[float, Field(description="⑩·⑭항 과세제외매출액(원)")] = 0) -> dict:
    return _R.tunnelling(people, [tuple(x) for x in family], [(h, c, float(r)) for h, c, r in stakes], beneficiary,
                        sales_total, sales_by_corp, after_tax_op_profit, size, excluded_sales)


@mcp.tool(description="""일감몰아주기 증여의제이익 — 국세청 2026 신고안내 산식(세후영업이익 ⑫, 출자관계별 추가 과세제외 ⑭1·3호, 한계보유 ⑬, 배당공제 ⑮). 언제: 국세청 신고안내 공식에 따라 일감몰아주기 증여의제이익을 정확히 계산할 때.
입력: 기업 규모(중소|중견|일반) → size, 수혜법인(이름, 고정) → '수혜법인', 세후영업이익 ⑫(원) → op_income, 과세표준(원) → taxable_income, 법인세 산출세액(원) → tax, 총 매출액(원) → sales_total, sales_by_corp={거래처 법인: 매출액(원)} → sales_by_corp, relations={관계명: 보유비율(소수)}(예: {'직접':0.2,'A경유':0.18}) → relations, 기본 과세제외매출액(⑩항, 원) → base_excluded, holdings_in_related={특관법인: 지배주주등 보유비율(소수)} → holdings_in_related, indirect_corp_of={관계명: 그 경로 간접출자법인} → indirect_corp_of, excluded_by_corp={특관법인: ⑩항 과세제외액(원)} → excluded_by_corp, dividends={관계명: [배당소득(원), 분모]}(⑮항) → dividends, 토지등 양도소득 법인세(차감, 원) → land_tax, 공제·감면세액(차감, 원) → credits, 미환류소득 법인세(원, tax에 포함이 맞음) → unreturned_tax.
결과: 증여의제이익·단계별 계산, 근거(상증법 제45조의3, 시행령 제34조의3, 국세청 2026 신고안내). 일감몰아주기 증여의제이익 — 국세청 2026 신고안내 산식.""")
def tunnelling_gift_nts(size: Annotated[str, Field(description="기업 규모('중소'|'중견'|'일반')")],
                        op_income: Annotated[float, Field(description="세후영업이익 ⑫(원)")],
                        taxable_income: Annotated[float, Field(description="과세표준(원)")],
                        tax: Annotated[float, Field(description="법인세법 제55조 산출세액(원)")],
                        sales_total: Annotated[float, Field(description="총 매출액(원)")],
                        sales_by_corp: Annotated[dict, Field(description='거래처 법인별 매출액 {법인: 매출액(원)}. 예: {"A": 300000000}')],
                        relations: Annotated[dict, Field(description="관계명별 보유비율(소수). 예: {'직접': 0.2, 'A경유': 0.18}")],
                        base_excluded: Annotated[float, Field(description="기본 ⑩항 과세제외매출액(원)")] = 0,
                        holdings_in_related: Annotated[dict | None, Field(description='특관법인별 지배주주등 보유비율(소수). 예: {"A": 0.3}')] = None,
                        indirect_corp_of: Annotated[dict | None, Field(description='관계명별 간접출자법인. 예: {"A경유": "B법인"}')] = None,
                        excluded_by_corp: Annotated[dict | None, Field(description='특관법인별 ⑩항 과세제외액(원). 예: {"A": 10000000}')] = None,
                        dividends: Annotated[dict | None, Field(description='관계명별 [배당소득(원), 분모]. 예: {"직접": [10000000, 300000000]}')] = None,
                        land_tax: Annotated[float, Field(description="토지등 양도소득 법인세(차감, 원)")] = 0,
                        credits: Annotated[float, Field(description="공제·감면세액(차감, 원)")] = 0,
                        unreturned_tax: Annotated[float, Field(description="미환류소득 법인세(원, tax에 포함이 맞음)")] = 0) -> dict:
    return _R.tunnelling_nts("수혜법인", size, op_income, taxable_income, tax, sales_total, sales_by_corp, relations,
                            base_excluded, holdings_in_related, indirect_corp_of,
                            excluded_by_corp,
                            {k: tuple(v) for k, v in (dividends or {}).items()},
                            land_tax, credits, unreturned_tax)


@mcp.tool(description="""특수관계인 범위 조문이 기준일에 어느 법령에 있었는지 확인. 언제: 특수관계 판정 결과를 근거로 인용할 때 해당 기준일 시행 조문의 위치를 확인한다.
입력: 법령 구분(국기|법인|상증) → law, 기준일(YYYY-MM-DD) → on. 예: law='법인', on='2019-02-11' → 법인세 시행령 제87조①.
결과: 법령명·조항·원문·기준일. 특수관계인 범위 조문이 기준일에 어디 있었는지 확인한다(law=국기|법인|상증).""")
def related_provision_at(law: Annotated[str, Field(description="법령 구분('국기'|'법인'|'상증')")],
                         on: Annotated[str, Field(description="기준일 YYYY-MM-DD")]) -> dict:
    name, jo, head = _R.cite_at(law, on)
    return {"법령": name, "조항": jo, "원문": head, "기준일": on}


@mcp.tool(description="""주주명부·가족관계·임원명단 PDF에서 관계표(people/family/stakes/officers)를 추출한다. 언제: 세무조사·의료법인 친족확인 등에서 PDF 문서에 있는 관계표를 도구 입력으로 정리할 때.
입력: PDF 파일 경로 → pdf_path.
결과: people·family·stakes·오 officers 추출 결과(초안) + AI 생성 표시(필요 시). related_judge에 넣기 전에 사람이 확인한다. UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 정리 가능(기본), 키 설정 시 Document Parse + Solar Pro 4로 더 정교한 표 추출. 주주명부·가족관계·임원명단 PDF에서 관계표를 뽑는다.""")
@_pdf_guard
def extract_relations(pdf_path: Annotated[str, Field(description="PDF 파일 경로")]) -> dict:
    from .audit.agents import related_intake
    return _add_ai_mark(related_intake.from_pdf(pdf_path))


@mcp.tool(description="""일감몰아주기 검토 자료 PDF → 표 추출 → 코드가 지배주주·출자관계·증여의제이익 계산. 언제: PDF로 된 일감몰아주기 검토 자료에서 관계표를 추출해 tunnelling_gift_nts 입력으로 정리할 때.
입력: PDF 파일 경로 → pdf_path.
결과: 지배주주·출자관계·증여의제이익 계산 결과(초안) + AI 생성 표시(필요 시). UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 정리 가능(기본), 키 설정 시 Document Parse + Solar Pro 4로 더 정교한 표 추출. 결과는 사람 확인. 일감몰아주기 검토 자료 PDF에서 표를 뽑는다.""")
@_pdf_guard
def tunnelling_from_pdf(pdf_path: Annotated[str, Field(description="PDF 파일 경로")]) -> dict:
    from .audit.agents import tunnel_intake
    return _add_ai_mark(tunnel_intake.from_pdf(pdf_path))


@mcp.tool(description="""신고서 사전검토(조사 착수 전 오류 의심 목록). 언제: 세무조사 착수 전에 신고서 값으로 오류 의심 항목을 미리 점검할 때. 입력: data={입력키: 값}, tax=법인|부가|소득(생략 시 전체) — 입력키는 precheck_schema로 먼저 확인. 결과: 오류 의심·이상 없음·자료 부족·사실 확인 필요.""")
def return_precheck(data: Annotated[dict, Field(description='신고서 입력키·값 사전(dictionary). 입력키는 precheck_schema로 확인')], tax: Annotated[str | None, Field(description="세목('법인'|'부가'|'소득'), 생략 시 전체")] = None) -> dict:
    return _precheck_run(data, tax)


@mcp.tool(description="""신고서 사전검토 입력스키마. 언제: return_precheck·영어로 된 신고서 PDF 도구 입력 전에 어떤 키를 넣어야 하는지 확인할 때. 입력: tax=법인|부가|소득. 결과: 각 입력키의 의미·단위·필수 여부를 목록으로 반환한다.""")
def precheck_schema(tax: Annotated[Literal["법인", "부가", "소득"], Field(description="사전검토 세목('법인'|'부가'|'소득')")] ) -> dict:
    from .audit.agents.precheck import REGISTRY
    from .audit.agents.precheck import corp as _c, vat as _v, income as _i

    schema_map = {"법인": _c.SCHEMA, "부가": _v.SCHEMA, "소득": _i.SCHEMA}
    schema = schema_map[tax]

    # 해당 세목 규칙의 needs에 등장하는 키 → '요건별 필수'로 표시
    needed = set()
    prefix = {"법인": "법인", "부가": "부가", "소득": "소득"}[tax]
    for r in REGISTRY:
        if r.세목 != prefix: continue
        for k in r.needs:
            needed.add(k)

    rows = []
    for k, desc in schema.items():
        unit = _infer_unit(desc)
        required = "요건별 필수" if k in needed else "선택"
        rows.append({"키": k, "의미": desc, "단위": unit, "필수": required})
    return {"세목": tax, "입력스키마": rows, "총_입력키": len(rows)}


def _infer_unit(desc: str) -> str:
    """SCHEMA 설명에서 단서를 읽어 단위를 추론한다."""
    if "bool" in desc or "여부" in desc: return "bool"
    if "YYYY-MM-DD" in desc or "제출일" in desc or "개시일" in desc or "종료일" in desc or "일" in desc: return "YYYY-MM-DD/string"
    if "리스트" in desc or "[" in desc: return "list[dict]/list"
    if "원" in desc: return "원 (int)"
    if "소수" in desc or "비율" in desc: return "소수 (float)"
    if "string" in desc or "구분" in desc or "코드" in desc: return "문자열"
    if "명" in desc or "수" in desc: return "int (명/수)"
    return "문맥 참조"


@mcp.tool(description="""법인세 신고서 PDF(별지 1·3·50호) → 표 추출 → 사전검토(오류 의심 목록). 언제: 법인세 신고서 PDF에서 값을 추출해 return_precheck 입력으로 정리할 때.
입력: PDF 파일 경로 → pdf_path.
결과: 오류 의심·이상 없음·자료 부족·사실 확인 필요 목록 + 서식 간 대사·세액 체인 재계산 + AI 생성 표시(필요 시). UPSTAGE_API_KEY 없이도 pypdf 로컬 추출 후 return_precheck 입력으로 정리 가능(기본), 키 설정 시 Document Parse + Solar Pro 4로 더 정교한 표 추출. 법인세 신고서 PDF에서 표를 추출해 사전검토한다.""")
@_pdf_guard
def return_precheck_pdf(pdf_path: Annotated[str, Field(description="PDF 파일 경로")]) -> dict:
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
