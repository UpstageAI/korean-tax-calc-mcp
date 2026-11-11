"""계산 MCP 0.31.0 — 특정외국법인(CFC) 유보소득 배당간주액 `cfc_deemed_dividend`.

근거: 국제조세조정에 관한 법률 제27조~제31조, 시행령 제61조·제62조·제64조~제67조, 법인세법 제55조(최고세율 연도표).
조문은 korean-tax-mcp 2026 시행본으로 확인함.
"""
from __future__ import annotations

from datetime import date, timedelta
from fractions import Fraction

from .exact import trunc_won as _trunc_won, exact as _exact


_LISTED_INDUSTRY = frozenset({"도매업", "금융 및 보험업", "부동산업", "전문·과학·기술 서비스업", "사업시설관리·사업지원·임대서비스업"})


def _ceiling_div(num: int, den: int) -> int:
    """ceil(num / den), den > 0. Fraction으로 계산 후 원 미만 올림しない — 정수 나눗셈 ceil."""
    if den <= 0:
        raise ValueError("분모 양수 필요")
    if num >= 0:
        return (num + den - 1) // den
    return num // den


def _ceiled_trunc_won_div(num: int, den: int) -> int:
    """ceil(num / den) 을 trunc_won(0방향 절사)와 같은 결과의 정수로 반환.

    수동소득 배당간주 산식: 유보소득 × 보유비율 × (수동소득 − 배제배당) ÷ 총수입금액.
    이 산식은 '÷'가 있으니 trunc_won(0방향 절사)로 처리. 단, 바닥이 음수가 아니면
    ceil = floor+1(remainder 있을 때) 이므로, 분자·분모 부호가 모두 0 이상이면
    int(Fraction 분자/분모)의 0방향 절사와 동일.
    """
    f = Fraction(num, den)
    return _trunc_won(f)


def _ok(result: dict, basis: str, *, 주의=None, 판단=None, 단계별_계산=None) -> dict:
    d: dict = {"결과": result, "근거": basis}
    if 주의:
        d["주의"] = 주의
    if 판단:
        d["판단"] = 판단
    if 단계별_계산:
        d["단계별_계산"] = 단계별_계산
    return d


def _오류(문제: list[str], 허용값: dict | None = None) -> dict:
    d: dict = {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    if 허용값:
        d["허용값"] = 허용값
    return d


# 법인세법 제55조 최고세율 × 70% 기준세율 연도표 (법 제27조①1호)
# 2022~2026: 최고세율 × 70/100, 2016~2021: 실제발생소득의 15퍼센트 이하(구 법 문구에 따른 15/100)
def _기준세율_fraction(year: int) -> Fraction:
    if year <= 2021:
        return Fraction(15, 100)
    if year == 2022:
        return Fraction(25, 100) * Fraction(70, 100)
    if 2023 <= year <= 2025:
        return Fraction(24, 100) * Fraction(70, 100)
    # 2026
    return Fraction(25, 100) * Fraction(70, 100)


def _검증(year: int, pretax_incomes: list, taxes_paid: list, ownership_chains: list,
          months: int, distributable: dict, listed_industry: str | None,
          listed_industry_share: float | None, listed_industry_related_share: float | None,
          same_country_unrelated_sales_share: float | None,
          ownership_with_related_ratio: float | None,
          passive_income: int | None, passive_excluded_dividends: int | None,
          total_revenue: int | None,
          related_party: bool, holding_company_exemption: bool,
          fixed_facility_active_business: bool, passive_main_business: bool) -> dict | None:
    """입력 검증. 문제 있으면 _오류 반환, 없으면 None."""
    문제 = []

    if not (2016 <= year <= 2026):
        문제.append(f"year={year} 은(는) 허용 범위(2016~2026) 밖")

    if not isinstance(pretax_incomes, list) or not (1 <= len(pretax_incomes) <= 3):
        문제.append(f"pretax_incomes 길이 {len(pretax_incomes) if isinstance(pretax_incomes, list) else '오류'} — 1~3 필요")
    if not isinstance(taxes_paid, list) or len(taxes_paid) != len(pretax_incomes):
        문제.append(f"taxes_paid 길이 {len(taxes_paid) if isinstance(taxes_paid, list) else '오류'} — pretax_incomes와 같아야 함({len(pretax_incomes) if isinstance(pretax_incomes, list) else '?'})")

    if taxes_paid:
        for i, t in enumerate(taxes_paid):
            if not isinstance(t, (int, float)) or t < 0:
                문제.append(f"taxes_paid[{i}]={t} — 0 이상 필요")
                break

    if not isinstance(ownership_chains, list) or not ownership_chains:
        문제.append("ownership_chains 이 비어 있음")

    if isinstance(ownership_chains, list) and ownership_chains:
        총보유비율 = 0.0
        for ci, chain in enumerate(ownership_chains):
            if not isinstance(chain, list) or not chain:
                문제.append(f"ownership_chains[{ci}] 이 비어 있음")
                continue
            for ri, v in enumerate(chain):
                if not isinstance(v, (int, float)):
                    문제.append(f"ownership_chains[{ci}][{ri}]={v} — 수 아님")
                    continue
                if not (0 < v <= 1):
                    문제.append(f"ownership_chains[{ci}][{ri}]={v} — 0 초과 1 이하 필요")
            # 체인 곱(Product) 계산 후 총합계에 누적 — 영 제67조①(보유비율 = Σ 각 줄 곱)
            prod = 1.0
            for v in chain:
                if isinstance(v, (int, float)) and 0 < v <= 1:
                    prod *= v
            총보유비율 += prod
        if 총보유비율 > 1:
            문제.append(f"ownership_chains 보유비율(곱의 합) {총보유비율:.4f} > 1")

    if not isinstance(months, int) or not (1 <= months <= 12):
        문제.append(f"months={months} — 1~12 필요")

    if isinstance(distributable, dict):
        for k, v in distributable.items():
            if v is not None and (not isinstance(v, (int, float)) or v < 0):
                문제.append(f"distributable['{k}']={v} — 0 이상 필요")
    else:
        문제.append("distributable dict 필요")

    if listed_industry is not None and listed_industry not in _LISTED_INDUSTRY:
        문제.append(f"listed_industry='{listed_industry}' — 허용값: {sorted(_LISTED_INDUSTRY)}")

    for 이름, val in (("listed_industry_share", listed_industry_share),
                       ("listed_industry_related_share", listed_industry_related_share),
                       ("same_country_unrelated_sales_share", same_country_unrelated_sales_share)):
        if val is not None:
            if not isinstance(val, (int, float)) or not (0 <= val <= 1):
                문제.append(f"{이름}={val} — 0 이상 1 이하 필요")

    if ownership_with_related_ratio is not None:
        if not isinstance(ownership_with_related_ratio, (int, float)) or not (0 <= ownership_with_related_ratio <= 1):
            문제.append(f"ownership_with_related_ratio={ownership_with_related_ratio} — 0 이상 1 이하 필요")

    for 이름, val in (("passive_income", passive_income), ("passive_excluded_dividends", passive_excluded_dividends),
                       ("total_revenue", total_revenue)):
        if val is not None and (not isinstance(val, (int, float)) or val < 0):
            문제.append(f"{이름}={val} — 0 이상 필요")

    if 문제:
        from fractions import Fraction as _F
        return _오류(문제, {"year": "2016~2026", "pretax_incomes": "길이 1~3 (원)", "taxes_paid": "같은 길이 (원, 0 이상)",
                            "ownership_chains": "목록의 목록 (각 값 0 초과 1 이하, 합계 1 이하)",
                            "months": "1~12", "distributable": "dict (키별 0 이상)",
                            "listed_industry": sorted(_LISTED_INDUSTRY),
                            "비율 입력": "0 이상 1 이하"})
    return None


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
    """특정외국법인 유보소득 배당간주액(국제조세조정에 관한 법률 제27조~제31조, 시행령 제61조·제62조·제64조~제67조, 법인세법 제55조).

    언제: 특정외국법인(CFC)의 유보소득을 내국인이 배당받은 것으로 간주해 과세할지 여부와 배당간주금액을 계산할 때.
    입력:
      year — 특정외국법인 사업연도 개시일이 속하는 연도(2016~2026).
      pretax_incomes — 최근 3개 사업연도 이내 조정 후 세전이익(원) 목록(1~3개, 음수=0 처리).
      taxes_paid — 같은 길이 실제 부담 세액(원, 0 이상).
      ownership_chains — 내국인에서 CFC까지 단계별 보유비율 목록의 목록(곱의 합 = 보유비율).
      ownership_with_related_ratio — 10% 판정용 비율(특수관계인 직접 보유 포함, 없으면 보유비율과 같음).
      related_party — 특수관계 요건(법 제27조①2호) 기본 True.
      months — 사업연도 개월 수(1~12, 기본 12).
      fy_end — 특정외국법인 사업연도 종료일(YYYY-MM-DD, 선택).
      distributable — dict: unappropriated_retained_earnings 등 키(모두 원, 0 이상, 없으면 0).
      fixed_facility_active_business — 고정 시설 실질 사업(법 제28조2호) 여부 기본 False.
      holding_company_exemption — 해외지주회사 예외(법 제28조3호) 여부 기본 False(호출자 판정).
      listed_industry — 허용 업종명(선택).
      listed_industry_share / listed_industry_related_share — 그 업종 수입금액·특수관계 비중(선택, 0~1).
      same_country_unrelated_sales_share — 도매업 같은 국가 비특수관계 판매 비중(선택, 0~1).
      passive_main_business — 수동소득 주된 사업(법 제29조①2호) 여부 기본 False.
      passive_income / passive_excluded_dividends / total_revenue — 수동소득·배제배당·총수입금액(원, 선택).
    결과: 특정외국법인_해당·배당간주_적용·적용방식·적용제외_사유·실제발생소득_연평균·실제부담세액_연평균·
          기준세율_만분율·실제부담세율_만분율·주식보유비율_만분율·배당가능_유보소득·배당간주금액·
          익금귀속_기준일·익금귀속_과세연도·단계별_계산.
    """
    distributable = distributable or {}

    err = _검증(year, pretax_incomes, taxes_paid, ownership_chains, months, distributable,
                listed_industry, listed_industry_share, listed_industry_related_share,
                same_country_unrelated_sales_share, ownership_with_related_ratio,
                passive_income, passive_excluded_dividends, total_revenue,
                related_party, holding_company_exemption, fixed_facility_active_business,
                passive_main_business)
    if err is not None:
        return err

    # ── 보유비율 계산(영 제67조①): 각 줄 곱의 합 ──
    total_ownership = Fraction(0)
    for chain in ownership_chains:
        prod = Fraction(1)
        for v in chain:
            prod *= Fraction(str(v))
        total_ownership += prod
    total_ownership_int = _trunc_won(total_ownership * Fraction(10000))   # 만분율(정수)

    # 10% 판정 비율
    if ownership_with_related_ratio is not None:
        ten_pct_ratio = Fraction(str(ownership_with_related_ratio))
    else:
        ten_pct_ratio = total_ownership

    # ── 판정 1: 특수관계 ──
    if not related_party:
        return _ok({
            "특정외국법인_해당": False,
            "배당간주_적용": False,
            "적용방식": "없음",
            "적용제외_사유": "특수관계 없음(법 제27조①2호)",
            "실제발생소득_연평균": 0,
            "실제부담세액_연평균": 0,
            "기준세율_만분율": _trunc_won(_기준세율_fraction(year) * Fraction(10000)),
            "실제부담세율_만분율": None,
            "주식보유비율_만분율": total_ownership_int,
            "배당가능_유보소득": 0,
            "배당간주금액": 0,
            "익금귀속_기준일": _기준일(fy_end) if fy_end else None,
            "익금귀속_과세연도": _과세연도(fy_end) if fy_end else None,
            "단계별_계산": [],
        }, "국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, 시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조",
           주의=_주의목록(holding_company_exemption, fixed_facility_active_business, related_party=False))

    # ── 판정 2: 10% 보유비율 ──
    if ten_pct_ratio < Fraction(10, 100):
        return _ok({
            "특정외국법인_해당": False,
            "배당간주_적용": False,
            "적용방식": "없음",
            "적용제외_사유": "10퍼센트 미만 보유(법 제27조②)",
            "실제발생소득_연평균": 0,
            "실제부담세액_연평균": 0,
            "기준세율_만분율": _trunc_won(_기준세율_fraction(year) * Fraction(10000)),
            "실제부담세율_만분율": None,
            "주식보유비율_만분율": total_ownership_int,
            "배당가능_유보소득": 0,
            "배당간주금액": 0,
            "익금귀속_기준일": _기준일(fy_end) if fy_end else None,
            "익금귀속_과세연도": _과세연도(fy_end) if fy_end else None,
            "단계별_계산": [],
        }, "국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, 시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조",
           주의=_주의목록(holding_company_exemption, fixed_facility_active_business))

    # ── 연평균 계산(영 제61조①·62조): Σ max(0, 세전이익) ÷ 연수, Σ 세액 ÷ 연수(절사) ──
    연수 = len(pretax_incomes)
    총소득_f = Fraction(0)
    총세액_f = Fraction(0)
    for pi, tx in zip(pretax_incomes, taxes_paid):
        총소득_f += Fraction(max(0, int(pi)))
        총세액_f += Fraction(int(tx))
    평균소득_f = 총소득_f / Fraction(연수)
    평균세액_f = 총세액_f / Fraction(연수)
    실제발생소득_연평균 = _trunc_won(평균소득_f)
    실제부담세액_연평균 = _trunc_won(평균세액_f)

    # 판정(절사 전 분수로): Σ세액 ≤ Σ소득 × 기준세율 → 저세율
    기준세율_f = _기준세율_fraction(year)
    기준세율_만분율 = _trunc_won(기준세율_f * Fraction(10000))
    저세율 = 총세액_f <= 총소득_f * 기준세율_f

    if not 저세율:
        실제부담세율_만분율 = _trunc_won(총세액_f / 총소득_f * Fraction(10000)) if 총소득_f > 0 else None
        return _ok({
            "특정외국법인_해당": False,
            "배당간주_적용": False,
            "적용방식": "없음",
            "적용제외_사유": "실제부담세액이 실제발생소득 × 기준세율 초과(법 제27조①1호)",
            "실제발생소득_연평균": 실제발생소득_연평균,
            "실제부담세액_연평균": 실제부담세액_연평균,
            "기준세율_만분율": 기준세율_만분율,
            "실제부담세율_만분율": 실제부담세율_만분율,
            "주식보유비율_만분율": total_ownership_int,
            "배당가능_유보소득": 0,
            "배당간주금액": 0,
            "익금귀속_기준일": _기준일(fy_end) if fy_end else None,
            "익금귀속_과세연도": _과세연도(fy_end) if fy_end else None,
            "단계별_계산": [],
        }, "국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, 시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조",
           주의=_주의목록(holding_company_exemption, fixed_facility_active_business))

    실제부담세율_만분율 = _trunc_won(총세액_f / 총소득_f * Fraction(10000)) if 총소득_f > 0 else None

    # ── 판정 4: 실제발생소득 2억원 이하(법 제28조1호, 영 제64조①) ──
    소득한도액 = int(Fraction(200_000_000) * months / Fraction(12))
    if 실제발생소득_연평균 <= 소득한도액:
        return _ok({
            "특정외국법인_해당": True,
            "배당간주_적용": False,
            "적용방식": "없음",
            "적용제외_사유": "실제발생소득 2억원 이하(법 제28조1호, 영 제64조①)",
            "실제발생소득_연평균": 실제발생소득_연평균,
            "실제부담세액_연평균": 실제부담세액_연평균,
            "기준세율_만분율": 기준세율_만분율,
            "실제부담세율_만분율": 실제부담세율_만분율,
            "주식보유비율_만분율": total_ownership_int,
            "배당가능_유보소득": 0,
            "배당간주금액": 0,
            "익금귀속_기준일": _기준일(fy_end) if fy_end else None,
            "익금귀속_과세연도": _과세연도(fy_end) if fy_end else None,
            "단계별_계산": [],
        }, "국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, 시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조",
           주의=_주의목록(holding_company_exemption, fixed_facility_active_business))

    # ── 판정 5: 해외지주회사 예외 ──
    if holding_company_exemption:
        return _ok({
            "특정외국법인_해당": True,
            "배당간주_적용": False,
            "적용방식": "없음",
            "적용제외_사유": "해외지주회사(법 제28조3호)",
            "실제발생소득_연평균": 실제발생소득_연평균,
            "실제부담세액_연평균": 실제부담세액_연평균,
            "기준세율_만분율": 기준세율_만분율,
            "실제부담세율_만분율": 실제부담세율_만분율,
            "주식보유비율_만분율": total_ownership_int,
            "배당가능_유보소득": 0,
            "배당간주금액": 0,
            "익금귀속_기준일": _기준일(fy_end) if fy_end else None,
            "익금귀속_과세연도": _과세연도(fy_end) if fy_end else None,
            "단계별_계산": [],
        }, "국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, 시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조",
           주의=_주의목록(holding_company_exemption=True, fixed_facility_active_business=fixed_facility_active_business))

    # ── 판정 6·7: 고정 시설 실질 사업 여부 → 적용방식 결정 ──
    적용방식: str
    적용제외_사유: str | None = None
    배당간주_적용: bool = True

    if not fixed_facility_active_business:
        적용방식 = "전부"
    else:
        # 7-1: 수동소득 주된 사업
        if passive_main_business:
            적용방식 = "전부"
        # 7-2: listed_industry 요건(법 제29조①1호)
        elif (listed_industry is not None
              and listed_industry_share is not None and listed_industry_share > Fraction(1, 2)
              and listed_industry_related_share is not None and listed_industry_related_share > Fraction(1, 2)):
            # 도매업이고 같은 국가 비특수관계 판매 비중 > 1/2 → 단서 적용(법 제29조① 단서)
            if listed_industry == "도매업" and same_country_unrelated_sales_share is not None \
                    and same_country_unrelated_sales_share > Fraction(1, 2):
                적용제외_사유 = "고정 시설을 둔 실질 사업(법 제28조2호)"
                적용방식 = "없음"
                배당간주_적용 = False
            else:
                적용방식 = "전부"
        else:
            # 7-3: 수동소득 판정(법 제29조②, 영 제65조④)
            if passive_income is not None and total_revenue is not None and total_revenue > 0:
                수동소득순액 = Fraction(int(passive_income)) - Fraction(int(passive_excluded_dividends or 0))
                비율_f = 수동소득순액 / Fraction(int(total_revenue))
                if 비율_f > Fraction(5, 100):
                    적용방식 = "수동소득"
                else:
                    적용제외_사유 = "고정 시설을 둔 실질 사업(법 제28조2호)"
                    적용방식 = "없음"
                    배당간주_적용 = False
            else:
                적용제외_사유 = "고정 시설을 둔 실질 사업(법 제28조2호)"
                적용방식 = "없음"
                배당간주_적용 = False

    # ── 배당 가능한 유보소득(영 제66조①1~7호) ──
    ure = int(distributable.get("unappropriated_retained_earnings", 0) or 0)
    div = int(distributable.get("dividends", 0) or 0)
    bon = int(distributable.get("bonuses_and_outflows", 0) or 0)
    res = int(distributable.get("mandatory_reserves", 0) or 0)
    prev = int(distributable.get("previously_taxed_undistributed", 0) or 0)
    pre_cfc = int(distributable.get("pre_cfc_earnings_undistributed", 0) or 0)
    unreal = int(distributable.get("unrealized_stock_gains", 0) or 0)
    유보소득차감_2억 = int(Fraction(200_000_000) * months / Fraction(12))
    유보소득_천원 = ure - div - bon - res - prev - pre_cfc - unreal - 유보소득차감_2억
    배당가능_유보소득 = max(0, 유보소득_천원)

    # ── 배당간주금액(법 제30조①②, 영 제67조④) ──
    보유비율_f = total_ownership   # Fraction
    if 적용방식 == "전부":
        배당간주금액 = _trunc_won(배당가능_유보소득 * 보유비율_f)
    elif 적용방식 == "수동소득":
        수동소득순액 = max(0, int(passive_income or 0) - int(passive_excluded_dividends or 0))
        if total_revenue is not None and total_revenue > 0:
            배당간주금액 = _trunc_won(
                Fraction(배당가능_유보소득) * 보유비율_f
                * Fraction(수동소득순액, int(total_revenue)))
        else:
            배당간주금액 = 0
    else:
        배당간주금액 = 0

    # ── 익금귀속 기준일·과세연도(법 제31조) ──
    익금귀속_기준일: str | None = None
    익금귀속_과세연도: int | None = None
    if fy_end:
        종료일 = date.fromisoformat(fy_end)
        기준일 = 종료일 + timedelta(days=60)
        익금귀속_기준일 = 기준일.isoformat()
        익금귀속_과세연도 = 기준일.year

    # ── 단계별 계산 ──
    단계별 = []
    유보소득산식 = (f"배당가능 유보소득 = max(0, {ure:,} − {div:,} − {bon:,} − {res:,} − {prev:,} "
                    f"− {pre_cfc:,} − {unreal:,} − {유보소득차감_2억:,}(2억×{months}÷12)) "
                    f"= {배당가능_유보소득:,}원 (영 제66조①)")
    단계별.append(유보소득산식)
    _chain_strs = [f"({' × '.join(str(int(v)) for v in chain)})" for chain in ownership_chains]
    보유비율산식 = (f"보유비율 = {' + '.join(_chain_strs)} "
                    f"= {float(보유비율_f):.4f} → {total_ownership_int}만분율 (영 제67조①)")
    단계별.append(보유비율산식)
    if 적용방식 == "전부":
        배당산식 = f"배당간주금액 = {배당가능_유보소득:,} × {float(보유비율_f):.4f} = {배당간주금액:,}원 (법 제30조①)"
        단계별.append(배당산식)
    elif 적용방식 == "수동소득":
        수동소득순액_i = max(0, int(passive_income or 0) - int(passive_excluded_dividends or 0))
        배당산식 = (f"배당간주금액 = {배당가능_유보소득:,} × {float(보유비율_f):.4f} "
                    f"× {수동소득순액_i:,} ÷ {int(total_revenue):,} = {배당간주금액:,}원 (법 제30조②, 영 제67조④)")
        단계별.append(배당산식)

    r_body = {
        "특정외국법인_해당": True,
        "배당간주_적용": 배당간주_적용,
        "적용방식": 적용방식 if 배당간주_적용 else "없음",
        "적용제외_사유": 적용제외_사유,
        "실제발생소득_연평균": 실제발생소득_연평균,
        "실제부담세액_연평균": 실제부담세액_연평균,
        "기준세율_만분율": 기준세율_만분율,
        "실제부담세율_만분율": 실제부담세율_만분율,
        "주식보유비율_만분율": total_ownership_int,
        "배당가능_유보소득": 배당가능_유보소득,
        "배당간주금액": 배당간주금액,
        "익금귀속_기준일": 익금귀속_기준일,
        "익금귀속_과세연도": 익금귀속_과세연도,
    }
    return _ok(r_body,
               "국제조세조정에 관한 법률 제27조①②·제28조·제29조①②·제30조①②·제31조, 시행령 제61조·제62조·제64조①·제65조·제66조①·제67조①④, 법인세법 제55조",
               주의=_주의목록(holding_company_exemption, fixed_facility_active_business),
               단계별_계산=단계별)


def _기준일(fy_end: str) -> str:
    종료일 = date.fromisoformat(fy_end)
    return (종료일 + timedelta(days=60)).isoformat()


def _과세연도(fy_end: str) -> int:
    return date.fromisoformat(fy_end).year


def _주의목록(holding_company_exemption: bool, fixed_facility_active_business: bool,
              related_party: bool = True) -> list[str]:
    base = [
        "금액은 호출자가 원화로 환산해 넣는다. 배당간주금액은 사업연도 종료일의 다음 날부터 60일이 되는 날의 기준환율·재정환율로 환산(영 제67조③)",
        "실제 배당 때 익금불산입·배당소득 제외(법 제32조), 실제 배당 시 외국납부세액은 경정청구로 공제(법 제33조)",
        "특정외국법인 재무제표·유보소득 계산 명세서 등 제출(법 제34조, 영 제70조)",
    ]
    if holding_company_exemption or fixed_facility_active_business:
        base.append("요건 충족 여부는 호출자 판정")
    return base
