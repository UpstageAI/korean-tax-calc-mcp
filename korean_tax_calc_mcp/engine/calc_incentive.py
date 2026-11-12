"""중소기업 조세지원 계산 — 창업중소기업 세액감면, 중소기업 특별세액감면, 결손금 소급공제 환급. Claude 작성(2026-11-12).

창업중소기업 등 세액감면(조세특례제한법 제6조 — 2016~2026 각 시행본, 시행령 제5조, 시행규칙 제4조의2 대조):
  · 감면기간: 최초로 소득이 발생한 과세연도(사업 개시일부터 5년이 되는 날이 속하는 과세연도까지 소득이 없으면 그 과세연도)부터 5개 과세연도
  · 감면율(창업일 기준 — 법률 제14390호 부칙 제3조, 제15227호 부칙 제4조·제39조, 제15623호 부칙 제4조: 시행 전 창업은 종전 규정)
      2016년 창업: 수도권과밀억제권역 밖 50%
      2017년 창업: 수도권과밀억제권역 밖 50%, 청년창업은 처음 3개 과세연도 75%·다음 2개 과세연도 50%
      2018.5.29.~2025.12.31. 창업: 과밀억제권역 밖 청년 100%, 과밀억제권역 안 청년·밖 일반 50%
      2026.1.1. 이후 창업: 청년 — 수도권 밖·수도권 인구감소지역 100%, 수도권(과밀억제권역·인구감소지역 제외) 75%, 과밀억제권역 50%
                           일반 — 수도권 밖·수도권 인구감소지역 50%, 수도권(과밀억제권역·인구감소지역 제외) 25%
      2018.1.1.~5.28. 창업: 그 기간 시행본을 대조하지 못해 계산하지 않음
  · 업종(제3항): 제조업(2017년부터 위탁제조 포함 — 국내 제조업체에 맡기고 직접 기획·자기 명의 제조·자기 책임 직접 판매, 시행규칙 제4조의2),
      통신판매업은 2018.5.29. 이후 창업부터. 도매업·소매업은 대상이 아님
  · 창업벤처중소기업(제2항): 창업 후 3년 안에 벤처기업 확인, 확인 후 최초 소득 과세연도부터 5개 과세연도 50%(제1항을 적용받으면 제외)
  · 감면세액 합계 한도 5억원(제13항): 2025.1.1. 이후 창업부터(법률 제20617호 부칙 제2조)
  · 최저한세(제132조제1항제4호): 제6조 감면은 대상. 100% 감면받는 과세연도는 제외
중소기업 특별세액감면(조세특례제한법 제7조 — 2016·2018·2020·2022·2024·2026 시행본, 시행령 제6조 대조):
  · 감면율: 소기업 도매업등(도매·소매·의료) 10%, 소기업 그 밖 업종 수도권 20%·수도권 밖 30%, 중기업 수도권 밖 도매업등 5%·그 밖 15%
    (중기업 수도권은 지식기반산업·일반 서적 출판업 등 시행본마다 다른 예외만 10% — 계산하지 않음). 본점이 수도권이면 모든 사업장을 수도권으로 봄
  · 한도(2018년부터): 1억원 − 상시근로자 감소 인원 × 500만원
  · 제6조 등과 같은 과세연도에 함께 적용할 수 있으면 하나만 선택(제127조제4항). 최저한세 대상
결손금 소급공제(법인세법 제72조 — 2016·2020·2021·2026 시행본, 시행령 제110조 대조):
  · 환급세액 = 직전 사업연도 산출세액 − (직전 과세표준 − 소급공제 결손금) × 직전 사업연도 세율, 한도 = 직전 산출세액 − 공제·감면세액
  · 중소기업만, 결손 사업연도와 직전 사업연도를 모두 기한 안에 신고한 경우"""
import math
from datetime import date

from . import calc_cit as CC

YEAR_MIN, YEAR_MAX = 2016, 2026
REGIONS = ("수도권과밀억제권역", "수도권", "수도권 인구감소지역", "수도권 밖")
STARTUP_INDUSTRIES = ("제조업", "위탁제조", "통신판매업", "그 밖의 대상 업종", "도매업", "소매업")
_OEM_KEYS = {"domestic_maker": "국내(개성공업지구 포함) 제조업체에 맡겨 제조", "own_planning": "생산할 제품을 직접 기획(고안·디자인·견본 제작 등)",
             "own_name": "자기 명의로 제조", "own_sale": "제품을 인수해 자기 책임으로 직접 판매"}


def _d(s, name, 문제):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        문제.append(f"{name}={s!r} — YYYY-MM-DD")
        return None


def _won(v, name, 문제, allow_zero=True):
    if isinstance(v, bool) or not isinstance(v, int) or v < 0 or (v == 0 and not allow_zero):
        문제.append(f"{name} — 원 단위 {'0 이상' if allow_zero else '양의'} 정수")
        return False
    return True


def _startup_rate(founded, region, youth, k):
    """(감면율 또는 None, 근거 문구). k = 감면기간 중 몇 번째 과세연도(1~5)."""
    outside = region != "수도권과밀억제권역"
    if founded <= date(2016, 12, 31):
        return (0.5, "2016년 창업 — 수도권과밀억제권역 밖 50%") if outside else (None, "2016년 창업은 수도권과밀억제권역 밖에서 창업한 경우만 제1항 대상")
    if founded <= date(2017, 12, 31):
        if not outside:
            return None, "2017년 창업은 수도권과밀억제권역 밖에서 창업한 경우만 제1항 대상"
        if youth:
            return (0.75, "2017년 청년창업 — 처음 3개 과세연도 75%") if k <= 3 else (0.5, "2017년 청년창업 — 4·5번째 과세연도 50%")
        return 0.5, "2017년 창업 — 수도권과밀억제권역 밖 50%"
    if founded <= date(2025, 12, 31):
        if youth:
            return (1.0, "과밀억제권역 밖 청년창업 100%") if outside else (0.5, "과밀억제권역 안 청년창업 50%")
        return (0.5, "과밀억제권역 밖 창업 50%") if outside else (None, "2025.12.31. 이전에 수도권과밀억제권역 안에서 창업한 일반(청년이 아닌) 창업중소기업은 제1항에 감면율이 없음")
    far = region in ("수도권 밖", "수도권 인구감소지역")
    if youth:
        return (1.0, "수도권 밖·수도권 인구감소지역 청년창업 100%") if far else (0.75, "수도권(과밀억제권역·인구감소지역 제외) 청년창업 75%") if outside else (0.5, "과밀억제권역 청년창업 50%")
    return (0.5, "수도권 밖·수도권 인구감소지역 창업 50%") if far else (0.25, "수도권(과밀억제권역·인구감소지역 제외) 창업 25%") if outside else (None, "2026.1.1. 이후 수도권과밀억제권역 안에서 창업한 일반(청년이 아닌) 창업중소기업은 제1항에 감면율이 없음")


def startup_tax_reduction(founded_on, region, year, first_income_year, tax, taxable_base, eligible_income=None, youth=False,
                          industry="제조업", oem=None, venture_confirmed_on="", business_started_on=""):
    문제 = []
    founded = _d(founded_on, "founded_on", 문제)
    started = _d(business_started_on, "business_started_on", 문제) if business_started_on else founded
    venture = _d(venture_confirmed_on, "venture_confirmed_on", 문제) if venture_confirmed_on else None
    if region not in REGIONS:
        문제.append(f"region={region!r} — {' | '.join(REGIONS)} (수도권 = 과밀억제권역도 인구감소지역도 아닌 수도권)")
    if industry not in STARTUP_INDUSTRIES:
        문제.append(f"industry={industry!r} — {' | '.join(STARTUP_INDUSTRIES)}")
    if not isinstance(year, int) or not YEAR_MIN <= year <= YEAR_MAX:
        문제.append(f"year={year!r} — {YEAR_MIN}~{YEAR_MAX}")
    if not isinstance(first_income_year, int) or isinstance(first_income_year, bool):
        문제.append("first_income_year — 해당 사업에서 최초로 소득이 발생한 과세연도(정수)")
    _won(tax, "tax(산출세액)", 문제); ok_b = _won(taxable_base, "taxable_base(과세표준)", 문제, allow_zero=False)
    if eligible_income is not None and _won(eligible_income, "eligible_income(감면 대상 사업의 소득)", 문제) and ok_b and eligible_income > taxable_base:
        문제.append("eligible_income — 과세표준을 넘을 수 없음(감면세액 = 산출세액 × 감면 대상 소득 ÷ 과세표준 × 감면율)")
    if industry == "위탁제조":
        bad = [k for k in _OEM_KEYS if not isinstance((oem or {}).get(k), bool)]
        if bad:
            문제.append("oem — 위탁제조는 네 가지를 true/false로: " + ", ".join(f"{k}({_OEM_KEYS[k]})" for k in _OEM_KEYS))
    if founded:
        if founded < date(2016, 1, 1) or founded > date(2026, 12, 31):
            문제.append("founded_on — 2016.1.1.~2026.12.31. 창업만 지원(그 전 창업은 당시 시행본을 대조하지 않음)")
        elif date(2018, 1, 1) <= founded <= date(2018, 5, 28):
            문제.append("founded_on — 2018.1.1.~5.28. 창업은 그 기간에 시행된 제6조(법률 제15227호)를 대조하지 못해 계산하지 않음. 조문 도구로 그 기간 시행본을 확인")
        if isinstance(first_income_year, int) and first_income_year < founded.year:
            문제.append("first_income_year — 창업한 해보다 앞설 수 없음")
        if started and started < founded:
            문제.append("business_started_on — 창업일보다 앞설 수 없음")
        if venture and venture < founded:
            문제.append("venture_confirmed_on — 창업일보다 앞설 수 없음")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    판단, 주의 = [], []
    근거 = ["조세특례제한법 제6조제1항·제3항", "조세특례제한법 시행령 제5조"]
    elig = taxable_base if eligible_income is None else eligible_income

    # 1. 업종
    업종_가능, 업종_사유 = True, ""
    if industry in ("도매업", "소매업"):
        업종_가능, 업종_사유 = False, f"{industry}은 제6조제3항 업종에 없음(통신판매업·제조업 등만 대상). 온라인 판매가 주된 사업이면 통신판매업, 위탁생산 요건을 갖추면 제조업으로 판정"
    elif industry == "통신판매업" and founded < date(2018, 5, 29):
        업종_가능, 업종_사유 = False, "통신판매업은 2018.5.29. 이후 창업부터 대상(법률 제15623호 부칙 제4조 — 시행 전 창업은 종전 규정)"
    elif industry == "위탁제조":
        근거.append("조세특례제한법 시행규칙 제4조의2")
        if founded < date(2017, 1, 1):
            return {"error": "계산하지 않음", "문제": ["위탁제조를 제조업으로 보는 규정(시행령 제5조제6항)은 2017.2.7. 신설 — 2016년 창업 기업에 적용되는지 적용례를 확인하지 못함"]}
        miss = [v for k, v in _OEM_KEYS.items() if not oem[k]]
        if miss:
            업종_가능, 업종_사유 = False, "위탁제조 요건 미충족: " + "; ".join(miss) + " — 제조업으로 보지 않음(해외 제조업체에 맡기는 경우 포함)"
        else:
            판단.append("위탁제조: 국내 제조업체 위탁·직접 기획·자기 명의 제조·자기 책임 직접 판매를 모두 갖춰 제조업으로 봄(시행규칙 제4조의2)")

    # 2. 적용 조항·감면기간
    route, start = None, None
    cap = started.year + 5
    if 업종_가능:
        start1 = min(first_income_year, cap)
        k1 = year - start1 + 1
        r1, why1 = _startup_rate(founded, region, bool(youth), min(max(k1, 1), 5))
        if r1 is not None:
            route, start, rate, why = "제1항(창업중소기업)", start1, r1, why1
            if first_income_year > cap:
                판단.append(f"사업 개시일부터 5년이 되는 날이 속하는 {cap} 과세연도까지 소득이 없어 감면기간을 {cap} 과세연도부터 계산")
        else:
            판단.append("제1항: " + why1)
            if venture:
                lim = date(founded.year + 3, founded.month, min(founded.day, 28) if founded.month == 2 else founded.day)
                if venture > lim:
                    판단.append(f"제2항: 벤처기업 확인일 {venture}이 창업 후 3년({lim}) 뒤 — 창업벤처중소기업 아님")
                elif venture > date(2027, 12, 31):
                    판단.append("제2항: 벤처기업 확인 기한(2027.12.31.) 뒤")
                else:
                    vcap = venture.year + 5
                    if first_income_year < venture.year:
                        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["제2항(창업벤처중소기업)은 first_income_year에 벤처기업 확인일 이후 최초로 소득이 발생한 과세연도를 넣음"]}
                    route, start, rate, why = "제2항(창업벤처중소기업)", min(first_income_year, vcap), 0.5, "창업 후 3년 안에 벤처기업 확인 — 확인 후 최초 소득 과세연도부터 5개 과세연도 50%"
                    근거.append("조세특례제한법 제6조제2항")
                    주의.append("제2항 대상 벤처기업은 시행령 제5조제4항의 유형(벤처투자 유형 등 또는 연구개발비가 수입금액의 5% 이상)이어야 하고, 확인이 취소되거나 유효기간이 끝나 재확인받지 못하면 그 과세연도부터 감면하지 않음")
    else:
        판단.append("업종: " + 업종_사유)

    if route is None:
        return {"결과": {"감면세액": 0, "적용": "대상 아님"}, "계산": {"창업일": str(founded), "지역": region, "청년창업": bool(youth), "업종": industry},
                "판단": 판단 + ["창업중소기업 감면 대상이 아니면 중소기업 특별세액감면(sme_special_tax_reduction)을 검토"], "근거": 근거,
                "주의": ["제10항: 합병·분할·현물출자·사업 양수, 개인사업의 법인 전환, 폐업 후 같은 사업 재개, 사업 확장·업종 추가는 창업으로 보지 않음"]}

    k = year - start + 1
    계산 = {"창업일": str(founded), "지역": region, "청년창업": bool(youth), "업종": industry, "적용": route,
          "감면기간": f"{start}~{start + 4} 과세연도", "감면_연차": k if 1 <= k <= 5 else None}
    if not 1 <= k <= 5:
        판단.append(f"{year} 과세연도는 감면기간({start}~{start + 4}) 밖")
        return {"결과": {"감면세액": 0, "적용": "감면기간 아님"}, "계산": 계산, "판단": 판단, "근거": 근거, "주의": []}
    if route.startswith("제1항"):
        rate, why = _startup_rate(founded, region, bool(youth), k)
    대상세액 = math.floor(tax * elig / taxable_base)
    감면 = math.floor(대상세액 * rate)
    계산.update({"감면율": rate, "감면율_사유": why, "감면_대상_세액": 대상세액, "산식": "산출세액 × 감면 대상 소득 ÷ 과세표준 × 감면율", "한도_전_감면세액": 감면})
    if founded >= date(2025, 1, 1) and 감면 > 500_000_000:
        판단.append("감면세액 합계 한도 5억원 적용(제13항 — 2025.1.1. 이후 창업)")
        근거.append("조세특례제한법 제6조제13항, 법률 제20617호 부칙 제2조")
        감면 = 500_000_000
    최저한세 = CC.min_tax(taxable_base, sme=True, grace_year=0, year=year)
    if rate == 1.0:
        적용액 = 감면
        판단.append("100% 감면받는 과세연도 — 최저한세 적용 대상에서 제외(제132조제1항제4호)")
    else:
        적용액 = max(0, min(감면, tax - 최저한세))
        if 적용액 < 감면:
            판단.append(f"최저한세 {최저한세:,}원(과세표준 × 7%) 때문에 감면 {감면 - 적용액:,}원은 적용하지 못함 — 세액감면은 이월되지 않음")
        계산["최저한세"] = 최저한세
    근거.append("조세특례제한법 제132조제1항제4호")
    판단.insert(0, f"{route} — {why}, 감면기간 {k}번째 과세연도")
    주의 += ["제10항: 합병·분할·현물출자·사업 양수, 개인사업의 법인 전환, 폐업 후 같은 사업 재개, 사업 확장·업종 추가는 창업으로 보지 않음",
           "같은 과세연도에 중소기업 특별세액감면(제7조)이나 통합투자·고용 관련 세액공제 등과 함께 적용할 수 있으면 하나만 선택(제127조제4항)",
           "과세표준 신고와 함께 세액감면신청서를 내야 함(제12항). 최저한세 계산은 다른 공제·감면이 없다고 보고 한 것",
           "수입금액이 작은 창업기업 감면(제6항)과 상시근로자 증가에 따른 추가 감면(제7항)은 계산하지 않음"]
    if youth:
        주의.append("청년창업: 대표자가 창업 당시 15~34세(병역 기간은 6년 한도로 뺌)이고 법인은 최대주주여야 함. 감면기간 중 최대주주가 아니게 되면 그 과세연도부터 감면율이 낮아짐(시행령 제5조제1항·제2항)")
    return {"결과": {"감면세액": 적용액, "적용": route, "감면율": rate, "납부할_세액_감면_후": tax - 적용액}, "계산": 계산, "판단": 판단, "근거": 근거, "주의": 주의}


SME_GROUPS = ("도매업등", "그 밖의 감면 업종")


def sme_special_tax_reduction(year, size, hq_in_capital_area, industry_group, tax, taxable_base, eligible_income=None,
                              employees_prev=None, employees_now=None):
    문제 = []
    if not isinstance(year, int) or not YEAR_MIN <= year <= YEAR_MAX:
        문제.append(f"year={year!r} — {YEAR_MIN}~{YEAR_MAX}")
    if size not in ("소기업", "중기업"):
        문제.append("size — 소기업 | 중기업(중소기업 중 소기업이 아닌 기업)")
    if not isinstance(hq_in_capital_area, bool):
        문제.append("hq_in_capital_area — 본점(사업장)이 수도권이면 true")
    if industry_group not in SME_GROUPS:
        문제.append(f"industry_group={industry_group!r} — {' | '.join(SME_GROUPS)} (도매업등 = 도매·소매·의료업)")
    _won(tax, "tax(산출세액)", 문제); ok_b = _won(taxable_base, "taxable_base(과세표준)", 문제, allow_zero=False)
    if eligible_income is not None and _won(eligible_income, "eligible_income", 문제) and ok_b and eligible_income > taxable_base:
        문제.append("eligible_income — 과세표준을 넘을 수 없음")
    emp = (employees_prev, employees_now)
    if any(e is not None for e in emp):
        if any(isinstance(e, bool) or not isinstance(e, (int, float)) or e < 0 for e in emp):
            문제.append("employees_prev·employees_now — 직전·해당 과세연도 상시근로자 수를 둘 다(0 이상)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    wholesale = industry_group == "도매업등"
    if size == "소기업":
        rate = 0.10 if wholesale else 0.20 if hq_in_capital_area else 0.30
    else:
        rate = 0.0 if hq_in_capital_area else 0.05 if wholesale else 0.15
    why = f"{size} · {'수도권' if hq_in_capital_area else '수도권 밖'} · {industry_group}"
    elig = taxable_base if eligible_income is None else eligible_income
    대상세액 = math.floor(tax * elig / taxable_base)
    감면 = math.floor(대상세액 * rate)
    계산 = {"구분": why, "감면율": rate, "감면_대상_세액": 대상세액, "산식": "산출세액 × 감면 대상 소득 ÷ 과세표준 × 감면율", "한도_전_감면세액": 감면}
    판단 = [f"{why} — 감면율 {rate:.0%}"]
    주의 = []
    if rate == 0.0:
        판단.append("수도권 중기업은 감면율이 없음. 예외(2016~2022 시행본의 지식기반산업, 2026 시행본의 일반 서적 출판업 10%)는 시행본마다 달라 계산하지 않음 — 조문 도구로 그 해 제7조제1항제2호 마목을 확인")
    if year >= 2018:
        한도 = 100_000_000
        if employees_prev is not None and employees_now < employees_prev:
            한도 = max(0, 100_000_000 - math.floor((employees_prev - employees_now) * 5_000_000))
            판단.append(f"상시근로자 {employees_prev - employees_now:g}명 감소 — 한도 1억원에서 1명당 500만원 차감")
        elif employees_prev is None:
            주의.append("상시근로자 수를 넣지 않아 한도를 1억원으로 계산 — 직전 과세연도보다 줄었으면 1명당 500만원씩 한도가 줄어듦")
        계산["감면한도"] = 한도
        if 감면 > 한도:
            판단.append(f"감면한도 {한도:,}원 적용")
            감면 = 한도
    else:
        판단.append("2017년까지는 감면한도 없음(한도는 2018년 시행본부터)")
    최저한세 = CC.min_tax(taxable_base, sme=True, grace_year=0, year=year)
    적용액 = max(0, min(감면, tax - 최저한세))
    계산["최저한세"] = 최저한세
    if 적용액 < 감면:
        판단.append(f"최저한세 {최저한세:,}원(과세표준 × 7%) 때문에 감면 {감면 - 적용액:,}원은 적용하지 못함 — 세액감면은 이월되지 않음")
    주의 += ["소기업 여부: 매출액이 업종별 「중소기업기본법 시행령」 별표 3 기준 이내(시행령 제6조제4항) — 기준 금액은 이 도구가 판정하지 않음",
           "본점이 수도권이면 모든 사업장이 수도권에 있는 것으로 봄(제7조제1항 단서)",
           "창업중소기업 감면(제6조) 등과 같은 과세연도에 함께 적용할 수 있으면 하나만 선택(제127조제4항)",
           "2028.12.31. 이전에 끝나는 과세연도까지. 과세표준 신고와 함께 세액감면신청서 제출. 최저한세 계산은 다른 공제·감면이 없다고 보고 한 것",
           "성실사업자 110% 특례(제2항), 전기·수소차 자동차 임대업 50% 축소, 알뜰주유소 특례(제3항)는 계산하지 않음"]
    return {"결과": {"감면세액": 적용액, "감면율": rate, "납부할_세액_감면_후": tax - 적용액}, "계산": 계산, "판단": 판단,
            "근거": ["조세특례제한법 제7조제1항", "조세특례제한법 시행령 제6조", "조세특례제한법 제127조제4항", "조세특례제한법 제132조제1항제4호"], "주의": 주의}


def loss_carryback_refund(year, loss, prior_base, prior_credits=0, carryback=None):
    문제 = []
    if not isinstance(year, int) or not YEAR_MIN + 1 <= year <= YEAR_MAX:
        문제.append(f"year={year!r} — 결손금이 발생한 사업연도 {YEAR_MIN + 1}~{YEAR_MAX}(직전 사업연도 세율표가 {YEAR_MIN}년부터)")
    _won(loss, "loss(결손금)", 문제, allow_zero=False); _won(prior_base, "prior_base(직전 사업연도 과세표준)", 문제)
    _won(prior_credits, "prior_credits(직전 사업연도 공제·감면세액)", 문제)
    if carryback is not None:
        _won(carryback, "carryback(소급공제 받으려는 결손금)", 문제, allow_zero=False)
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    if carryback is not None and (carryback > loss or carryback > prior_base):
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["carryback — 해당 사업연도 결손금과 직전 사업연도 과세표준을 넘을 수 없음(시행령 제110조제5항)"]}
    py = year - 1
    직전세액 = CC.corp_tax(prior_base, py)
    한도 = max(0, 직전세액 - prior_credits)
    근거 = ["법인세법 제72조제1항", "법인세법 시행령 제110조제1항"]
    if prior_base == 0 or 한도 == 0:
        return {"결과": {"환급세액": 0, "소급공제_결손금": 0, "이월할_결손금": loss}, "계산": {"직전_산출세액": 직전세액, "한도": 한도},
                "판단": ["직전 사업연도에 과세된 법인세액(산출세액 − 공제·감면세액)이 없어 환급할 세액이 없음 — 결손금은 전부 이월"], "근거": 근거, "주의": []}
    x = min(loss, prior_base) if carryback is None else carryback
    f = lambda v: 직전세액 - CC.corp_tax(prior_base - v, py)
    차액 = f(x)
    환급 = min(차액, 한도)
    판단 = [f"{py} 사업연도 산출세액 {직전세액:,}원 − (과세표준 {prior_base:,} − 소급공제 {x:,})에 {py}년 세율을 적용한 {직전세액 - 차액:,}원 = {차액:,}원"]
    계산 = {"직전_사업연도": py, "직전_산출세액": 직전세액, "소급공제_결손금": x, "소급공제_후_세액": 직전세액 - 차액, "차액": 차액, "한도": 한도,
          "산식": "직전 산출세액 − (직전 과세표준 − 소급공제 결손금) × 직전 사업연도 세율, 한도 = 직전 산출세액 − 공제·감면세액"}
    if 차액 > 한도:
        lo, hi = 0, x          # 한도만큼 환급받는 가장 작은 소급공제액
        while lo < hi:
            mid = (lo + hi) // 2
            lo, hi = (lo, mid) if f(mid) >= 한도 else (mid + 1, hi)
        판단.append(f"환급은 직전 사업연도 법인세액(산출세액 − 공제·감면세액) {한도:,}원이 한도 — 소급공제는 {lo:,}원만 신청하고 나머지 {loss - lo:,}원을 이월하면 환급액은 같고 이월결손금이 더 남음")
        계산["한도만큼_환급받는_최소_소급공제액"] = lo
    주의 = ["중소기업만 신청. 결손 사업연도와 직전 사업연도 법인세를 모두 신고기한 안에 신고하고, 신고기한까지 소급공제법인세액환급신청서를 내야 함(제72조제2항·제4항)",
          "소급공제받은 결손금은 이월결손금 공제에서 이미 공제받은 것으로 봄 — 남은 금액만 이월",
          "뒤에 결손금이 줄거나 직전 사업연도 세액이 경정되면 환급세액에 이자상당액을 더해 징수(제72조제5항)",
          "1년 미만 사업연도, 토지등 양도소득에 대한 법인세는 계산하지 않음"]
    if year == 2021:
        주의.append("2021.12.31.이 속하는 과세연도의 결손금은 직전 2개 과세연도까지 소급공제하는 특례가 있음(조세특례제한법 제8조의4) — 이 도구는 직전 1개 사업연도만 계산")
    if year == 2020:
        주의.append("2020.12.31.이 속하는 과세연도는 상반기 결손금을 미리 환급받는 특례가 있었음(당시 조세특례제한법 제8조의4) — 이 도구는 계산하지 않음")
    return {"결과": {"환급세액": 환급, "소급공제_결손금": x, "이월할_결손금": loss - x}, "계산": 계산, "판단": 판단, "근거": 근거, "주의": 주의}
