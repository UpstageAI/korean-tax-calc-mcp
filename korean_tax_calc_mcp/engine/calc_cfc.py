"""특정외국법인(CFC) 유보소득 배당간주액 `cfc_deemed_dividend` (0.31.0).

뼈대 Solar Pro 4, 보완 Claude(연도별 근거·주의, 분수 연산, 도매업 단서 뒤 수동소득 판정, 중복 반환 정리).
조문은 korean-tax-mcp로 2016~2026 각 연말 시행본을 받아 대조함(2026-11-11):
- 2016~2019 사업연도: 구 국제조세조정에 관한 법률 제17조·제18조·제18조의2·제19조, 영 제29조~제36조의3
- 2020 사업연도: 법 제17조·제17조의2·제17조의3·제18조·제19조, 영 제29조·제30조·제32조~제34조의2 (2019.12.31. 개정)
- 2021 사업연도~: 법 제27조~제31조, 영 제61조~제67조 (2020.12.22. 전부개정)
전 기간 같은 값: 10퍼센트 보유, 최근 3개 사업연도 합계 비교, 2억원(월할), 50퍼센트·5퍼센트 기준, 종료일 다음 날부터 60일.
연도별로 다른 값: 저세율 기준(_기준세율), 근거 조문 번호(_근거), 수동소득 범위·배당금 제외 범위(_연도별_주의).
"""
from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction

from .exact import trunc_won as _trunc_won

_LISTED_INDUSTRY = ("도매업", "금융 및 보험업", "부동산업", "전문·과학·기술 서비스업", "사업시설관리·사업지원·임대서비스업")
_DIST_KEYS = ("unappropriated_retained_earnings", "dividends", "bonuses_and_outflows", "mandatory_reserves",
              "previously_taxed_undistributed", "pre_cfc_earnings_undistributed", "unrealized_stock_gains")
_허용값 = {"year": "2016~2026", "pretax_incomes": "길이 1~3 (원)", "taxes_paid": "pretax_incomes와 같은 길이 (원, 0 이상)",
          "ownership_chains": "목록의 목록 (각 값 0 초과 1 이하, 곱의 합 1 이하)", "months": "1~12",
          "distributable": {k: "원, 0 이상" for k in _DIST_KEYS}, "listed_industry": list(_LISTED_INDUSTRY),
          "비율 입력": "0 이상 1 이하", "fy_end": "YYYY-MM-DD"}


def _오류(문제: list[str]) -> dict:
    return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제, "허용값": _허용값}


def _F(x) -> Fraction:
    return x if isinstance(x, Fraction) else Fraction(str(x))


def _기준세율(year: int) -> Fraction:
    """저세율 판정 기준. 2021 사업연도까지 15퍼센트(구 법 제17조①·2021년 시행 법 제27조①),
    2022 사업연도부터 법인세법 제55조 최고세율의 70퍼센트(법 제27조①1호, 2021.12.21. 개정):
    최고세율 2022년 25%, 2023~2025년 24%, 2026년 25%."""
    if year <= 2021:
        return Fraction(15, 100)
    top = Fraction(24, 100) if 2023 <= year <= 2025 else Fraction(25, 100)
    return top * Fraction(70, 100)


def _근거(year: int) -> str:
    if year <= 2019:
        return ("구 국제조세조정에 관한 법률(2019.12.31. 개정 전) 제17조①②③·제18조①④⑤·제18조의2·제19조①, "
                "구 시행령 제29조·제30조·제31조①·제34조의2·제35조②·제36조·제36조의2·제36조의3")
    if year == 2020:
        return ("구 국제조세조정에 관한 법률(2020.12.22. 전부개정 전) 제17조①②·제17조의2·제17조의3①②·제18조①②·제19조, "
                "구 시행령 제29조·제30조·제32조①·제33조·제34조①·제34조의2")
    if year == 2021:
        return ("국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, "
                "시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④ (2021년 시행본: 실제부담세액이 실제발생소득의 15퍼센트 이하)")
    return ("국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, "
            "시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조")


def _조문(year: int) -> dict:
    """판정 사유에 쓰는 연도별 조문 이름."""
    if year <= 2019:
        return {"특수관계": "구 법 제17조①", "10퍼센트": "구 법 제17조②", "저세율": "구 법 제17조①, 구 영 제30조",
                "2억": "구 법 제17조③, 구 영 제34조의2", "지주": "구 법 제18조의2", "고정시설": "구 법 제18조①",
                "업종": "구 법 제18조①1호", "수동사업": "구 법 제18조①2호", "수동소득": "구 법 제18조⑤, 구 영 제36조의3",
                "유보소득": "구 영 제31조①", "보유비율": "구 영 제34조의2", "배당간주": "구 법 제17조①", "귀속": "구 법 제19조①"}
    if year == 2020:
        return {"특수관계": "구 법 제17조①", "10퍼센트": "구 법 제17조②", "저세율": "구 법 제17조①, 구 영 제30조",
                "2억": "구 법 제17조의2 1호, 구 영 제32조①", "지주": "구 법 제17조의2 3호", "고정시설": "구 법 제17조의2 2호",
                "업종": "구 법 제17조의3①1호", "수동사업": "구 법 제17조의3①2호", "수동소득": "구 법 제17조의3②, 구 영 제33조④",
                "유보소득": "구 영 제34조①", "보유비율": "구 영 제34조의2①", "배당간주": "구 법 제18조①②", "귀속": "구 법 제19조"}
    return {"특수관계": "법 제27조①2호" if year >= 2022 else "법 제27조①", "10퍼센트": "법 제27조②",
            "저세율": "법 제27조①1호" if year >= 2022 else "법 제27조①, 영 제62조",
            "2억": "법 제28조1호, 영 제64조①", "지주": "법 제28조3호", "고정시설": "법 제28조2호",
            "업종": "법 제29조①1호", "수동사업": "법 제29조①2호", "수동소득": "법 제29조②, 영 제65조④",
            "유보소득": "영 제66조①", "보유비율": "영 제67조①", "배당간주": "법 제30조①②", "귀속": "법 제31조"}


def _연도별_주의(year: int) -> list[str]:
    out = []
    if year <= 2020:
        out.append("수동소득은 주식·채권 보유, 지식재산권 제공, 선박·항공기·장비 임대, 투자신탁·기금 투자에서 생긴 소득만 넣는다. "
                   "관련 자산의 매각손익은 2021년 이후 개시 사업연도부터 수동소득에 들어간다(법 제29조②2호)")
    else:
        out.append("수동소득에는 관련 자산의 매각손익도 넣는다(법 제29조②2호). 2023년부터는 금융 및 보험업 수행과 관련해 보유한 주식·채권의 매각손익은 뺀다")
    if year == 2016:
        out.append("수동소득에서 빼는 배당금: 2016년은 다른 외국법인 주식을 10퍼센트 이상 보유한 경우 그 배당금 전부(구 영 제36조의3① 단서, 2017.2.7. 개정 전). "
                   "개정 적용 시기는 부칙 확인")
    elif year <= 2020:
        out.append("수동소득에서 빼는 배당금: 구 법 제18조① 각 호(수동적 업종) 외의 사업을 하는 외국법인 주식을 10퍼센트 이상 보유한 경우의 배당금(2017.2.7. 개정)")
    else:
        out.append("수동소득에서 빼는 배당금: 법 제29조① 각 호 외의 사업을 하는 외국법인 또는 같은 국가등 판매 요건을 갖춘 도매업 외국법인의 주식을 10퍼센트 이상 보유한 경우의 배당금(영 제65조④ 단서)")
    if year >= 2022:
        out.append("최근 3개 사업연도에는 법 제29조① 각 호의 업종·행위를 한 사업연도만 넣는다(영 제61조②, 2022.2.15. 신설). "
                   "본점·주사무소 외에 실질적 관리장소가 저세율국에 있어도 대상이다")
    if year in (2019, 2020, 2021, 2022):
        out.append("개정 조문이 어느 사업연도부터 적용되는지는 year(사업연도 개시연도) 기준으로 나눴다. 사업연도가 역년과 다르면 개정 부칙의 적용례를 확인한다")
    return out


def cfc_deemed_dividend(
    year: int,
    pretax_incomes: list,
    taxes_paid: list,
    ownership_chains: list,
    ownership_with_related_ratio: float | None = None,
    related_party: bool = True,
    months: int = 12,
    fy_end: str | None = None,
    distributable: dict | None = None,
    fixed_facility_active_business: bool = False,
    holding_company_exemption: bool = False,
    listed_industry: str | None = None,
    listed_industry_share: float | None = None,
    listed_industry_related_share: float | None = None,
    same_country_unrelated_sales_share: float | None = None,
    passive_main_business: bool = False,
    passive_income: int | None = None,
    passive_excluded_dividends: int | None = None,
    total_revenue: int | None = None,
) -> dict:
    """특정외국법인 유보소득 배당간주액. 판정 순서: 특수관계 → 10퍼센트 보유 → 저세율 → 2억원 이하 배제 →
    해외지주회사 배제 → 고정 시설 실질 사업 배제와 그 예외(업종·수동적 사업·수동소득) → 유보소득 × 보유비율."""
    distributable = distributable or {}
    문제: list[str] = []
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)

    if not (isinstance(year, int) and 2016 <= year <= 2026):
        문제.append(f"year={year} — 2016~2026만 지원(연도마다 기준세율·조문이 달라 범위 밖은 계산하지 않음)")
    if not isinstance(pretax_incomes, list) or not 1 <= len(pretax_incomes) <= 3 or not all(num(v) for v in pretax_incomes):
        문제.append("pretax_incomes — 최근 3개 사업연도 이내 세전이익 1~3개(숫자)")
    if not isinstance(taxes_paid, list) or not isinstance(pretax_incomes, list) or len(taxes_paid) != len(pretax_incomes):
        문제.append("taxes_paid — pretax_incomes와 같은 길이여야 함")
    elif not all(num(v) and v >= 0 for v in taxes_paid):
        문제.append("taxes_paid — 0 이상 숫자")
    보유비율 = Fraction(0)
    if not isinstance(ownership_chains, list) or not ownership_chains or not all(isinstance(ch, list) and ch for ch in ownership_chains):
        문제.append("ownership_chains — 비어 있지 않은 목록의 목록")
    elif not all(num(v) and 0 < v <= 1 for ch in ownership_chains for v in ch):
        문제.append("ownership_chains — 각 단계 보유비율은 0 초과 1 이하")
    else:
        for ch in ownership_chains:
            p = Fraction(1)
            for v in ch:
                p *= _F(v)
            보유비율 += p
        if 보유비율 > 1:
            문제.append(f"ownership_chains — 곱의 합이 1을 넘음({보유비율})")
    if not (isinstance(months, int) and not isinstance(months, bool) and 1 <= months <= 12):
        문제.append(f"months={months} — 1~12")
    if not isinstance(distributable, dict):
        문제.append("distributable — dict")
    else:
        for k, v in distributable.items():
            if k not in _DIST_KEYS:
                문제.append(f"distributable['{k}'] — 모르는 키")
            elif v is not None and not (num(v) and v >= 0):
                문제.append(f"distributable['{k}']={v} — 0 이상 숫자")
    if listed_industry is not None and listed_industry not in _LISTED_INDUSTRY:
        문제.append(f"listed_industry='{listed_industry}' — 허용값 밖")
    for 이름, v in (("listed_industry_share", listed_industry_share), ("listed_industry_related_share", listed_industry_related_share),
                    ("same_country_unrelated_sales_share", same_country_unrelated_sales_share),
                    ("ownership_with_related_ratio", ownership_with_related_ratio)):
        if v is not None and not (num(v) and 0 <= v <= 1):
            문제.append(f"{이름}={v} — 0 이상 1 이하")
    for 이름, v in (("passive_income", passive_income), ("passive_excluded_dividends", passive_excluded_dividends), ("total_revenue", total_revenue)):
        if v is not None and not (num(v) and v >= 0):
            문제.append(f"{이름}={v} — 0 이상 숫자")
    기준일 = None
    if fy_end is not None:
        try:
            기준일 = date.fromisoformat(fy_end) + timedelta(days=60)   # 종료일의 다음 날부터 60일이 되는 날
        except (TypeError, ValueError):
            문제.append(f"fy_end='{fy_end}' — YYYY-MM-DD")
    if 문제:
        return _오류(문제)

    조 = _조문(year)
    기준세율 = _기준세율(year)
    만분율 = lambda f: _trunc_won(f * 10000)
    연수 = len(pretax_incomes)
    소득합 = sum(Fraction(max(0, int(v))) for v in pretax_incomes)      # 결손 사업연도는 0
    세액합 = sum(Fraction(int(v)) for v in taxes_paid)
    월할_2억 = _trunc_won(Fraction(200_000_000 * months, 12))

    결과 = {
        "특정외국법인_해당": False, "배당간주_적용": False, "적용방식": "없음", "적용제외_사유": None,
        "실제발생소득_연평균": _trunc_won(소득합 / 연수), "실제부담세액_연평균": _trunc_won(세액합 / 연수),
        "기준세율_만분율": 만분율(기준세율), "실제부담세율_만분율": 만분율(세액합 / 소득합) if 소득합 > 0 else None,
        "주식보유비율_만분율": 만분율(보유비율), "배당가능_유보소득": 0, "배당간주금액": 0,
        "익금귀속_기준일": 기준일.isoformat() if 기준일 else None, "익금귀속_과세연도": 기준일.year if 기준일 else None,
    }
    주의 = [
        "금액은 호출자가 원화로 환산해 넣는다. 배당간주금액은 사업연도 종료일의 다음 날부터 60일이 되는 날의 기준환율·재정환율로 환산(영 제67조③)",
        "실제 배당 때 익금불산입·배당소득 제외(법 제32조), 실제 배당 시 외국납부세액은 경정청구로 공제(법 제33조)",
        "특정외국법인 재무제표·유보소득 계산 명세서 등 제출(법 제34조, 영 제70조)",
        *_연도별_주의(year),
    ]
    if year <= 2020:      # 구법 시기: 실제 배당·자료 제출 조문 번호는 대조하지 않아 번호 없이 안내
        주의[:3] = ["금액은 호출자가 원화로 환산해 넣는다. 배당간주금액은 사업연도 종료일의 다음 날부터 60일이 되는 날의 기준환율·재정환율로 환산",
                   "실제 배당 때는 이미 배당간주로 과세된 금액을 익금·배당소득에서 빼고, 실제 배당 시 외국납부세액은 경정청구로 공제한다(당시 조문 번호는 구법 기준으로 확인)",
                   "특정외국법인 재무제표·유보소득 계산 명세서 등을 신고 때 제출한다(당시 조문 번호는 구법 기준으로 확인)"]
    if holding_company_exemption or fixed_facility_active_business:
        주의.append("해외지주회사·고정 시설 실질 사업 요건 충족 여부는 호출자 판정")
    단계: list[str] = []

    def 끝(사유: str | None = None) -> dict:
        결과["적용제외_사유"] = 사유
        return {"결과": 결과, "근거": _근거(year), "주의": 주의, "단계별_계산": 단계}

    # 1~3. 특정외국법인 해당 여부
    if not related_party:
        return 끝(f"특수관계 없음({조['특수관계']})")
    판정비율 = _F(ownership_with_related_ratio) if ownership_with_related_ratio is not None else 보유비율
    if 판정비율 < Fraction(10, 100):
        return 끝(f"10퍼센트 미만 보유({조['10퍼센트']})")
    단계.append(f"저세율 판정: 최근 {연수}개 사업연도 실제부담세액 합계 {int(세액합):,} ≤ 실제발생소득 합계 {int(소득합):,} × "
                f"{만분율(기준세율) / 100:g}% = {_trunc_won(소득합 * 기준세율):,} ({조['저세율']})")
    if 세액합 > 소득합 * 기준세율:
        return 끝(f"실제부담세액이 기준({만분율(기준세율) / 100:g}%) 초과 — 특정외국법인 아님({조['저세율']})")
    결과["특정외국법인_해당"] = True

    # 4~5. 적용 배제
    if 결과["실제발생소득_연평균"] <= 월할_2억:
        return 끝(f"실제발생소득 2억원 이하({조['2억']})" if months == 12 else f"실제발생소득 2억원 × {months}/12 이하({조['2억']})")
    if holding_company_exemption:
        return 끝(f"해외지주회사({조['지주']})")

    # 6~7. 고정 시설을 둔 실질 사업과 그 예외
    방식 = "전부"
    수동순액 = Fraction(0)
    if fixed_facility_active_business:
        half = Fraction(1, 2)
        업종요건 = (listed_industry is not None and listed_industry_share is not None and listed_industry_related_share is not None
                    and _F(listed_industry_share) > half and _F(listed_industry_related_share) > half)
        도매단서 = (listed_industry == "도매업" and same_country_unrelated_sales_share is not None
                    and _F(same_country_unrelated_sales_share) > half)
        if passive_main_business:
            방식 = "전부"                                                    # 수동적 행위가 주된 사업
        elif 업종요건 and not 도매단서:
            방식 = "전부"                                                    # 업종 요건
        else:                                                               # 고정 시설 배제 또는 도매업 단서 → 수동소득만 다시 본다
            방식 = "없음"
            if passive_income is not None and total_revenue:
                수동순액 = Fraction(int(passive_income)) - Fraction(int(passive_excluded_dividends or 0))
                if 수동순액 > Fraction(int(total_revenue)) * Fraction(5, 100):
                    방식 = "수동소득"
        if 방식 == "없음":
            return 끝(f"고정 시설을 둔 실질 사업({조['고정시설']})")

    # 8~9. 배당 가능한 유보소득, 배당간주금액
    d = {k: int(distributable.get(k) or 0) for k in _DIST_KEYS}
    유보 = max(0, d["unappropriated_retained_earnings"] - sum(d[k] for k in _DIST_KEYS[1:]) - 월할_2억)
    결과.update({"배당간주_적용": True, "적용방식": 방식, "배당가능_유보소득": 유보})
    단계.append("배당 가능한 유보소득 = 처분 전 이익잉여금 " + f"{d['unappropriated_retained_earnings']:,}"
                + "".join(f" − {d[k]:,}" for k in _DIST_KEYS[1:] if d[k]) + f" − {월할_2억:,}(2억원×{months}/12) = {유보:,} ({조['유보소득']})")
    단계.append("주식 보유비율 = " + " + ".join(" × ".join(f"{(_F(v) * 100).numerator}%" if (_F(v) * 100).denominator == 1 else str(_F(v)) for v in ch)
                                              for ch in ownership_chains) + f" = {보유비율.numerator}/{보유비율.denominator} ({조['보유비율']})")
    if 방식 == "전부":
        결과["배당간주금액"] = _trunc_won(유보 * 보유비율)
        단계.append(f"배당간주금액 = {유보:,} × {보유비율.numerator}/{보유비율.denominator} = {결과['배당간주금액']:,} ({조['배당간주']})")
    else:
        결과["배당간주금액"] = _trunc_won(유보 * 보유비율 * 수동순액 / int(total_revenue))
        단계.append(f"배당간주금액 = {유보:,} × {보유비율.numerator}/{보유비율.denominator} × (수동소득 {int(passive_income):,} − 제외 배당금 "
                    f"{int(passive_excluded_dividends or 0):,}) ÷ 총 수입금액 {int(total_revenue):,} = {결과['배당간주금액']:,} ({조['수동소득']})")
    if 기준일:
        단계.append(f"익금 귀속: 사업연도 종료일 {fy_end}의 다음 날부터 60일이 되는 날 {기준일.isoformat()}이 속하는 과세연도({조['귀속']})")
    return 끝()
