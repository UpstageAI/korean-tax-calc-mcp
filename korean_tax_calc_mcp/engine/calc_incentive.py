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
           "같은 과세연도에 중소기업 특별세액감면(제7조)이나 통합투자세액공제(제24조) 등 제127조제4항에 적힌 세액공제와 함께 적용할 수 있으면 하나만 선택. 연구인력개발비 세액공제(제10조)는 2024·2025 시행본의 같은 항에 없음",
              "고용증대·통합고용세액공제(제29조의7·제29조의8): 2024.12.31.까지 창업한 기업은 제7항 추가 감면을 받는 경우에만 함께 적용하지 못하고, 2025.1.1. 이후 창업한 기업은 제6조 감면과 함께 적용하지 못함(제127조제4항 단서, 법률 제20617호 부칙 제2조). 2018년 이전 시행본의 단서는 대조하지 않음",
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
           "위탁제조: 직접 만들지 않고 국내 제조업체에 맡겨 만드는 사업은 직접 기획·자기명의 제조·자기책임 직접 판매 요건을 갖추면 이 감면에서도 제조업으로 다룬 결정례가 있음(조심2023서10448, 2024.2.16. — 시행규칙 제4조의2 요건 / 조심2010중3890, 2011.9.14. — 당시 시행규칙 제2조제1항). "
           "요건을 못 갖추면 도매업으로 보아 industry_group='도매업등'과 도매업 소기업 기준을 적용. 거래처 상표를 붙여 납품하면 자기명의 제조가 아니라고 봄(조심2023서10448) — 요건 충족 여부는 이 도구가 판정하지 않음",
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


# ── 중소기업·소기업 해당 여부(조세특례제한법 시행령 제2조·제6조제4항, 중소기업기본법 시행령 별표 1·별표 3) ──
# 별표는 2017.10.17. 개정본(2018~2024 시행본 동일)과 2025.9.1. 개정본(2025.10.1. 개정본과 업종 묶음·금액 동일)을 원문에서 뽑아 대조.
# 2025.9.1. 개정으로 기준이 낮아진 업종은 없음 — 12월 결산 2025 과세연도부터 새 기준(시행령 제2조제1항제1호는 과세연도 종료일 현재 별표, 제5항).
_EOK = 100_000_000
_SIZE_TABLES = {
    "old": {
        "중소": {1500: "C14 C15 C17 C24 C28 C32", 1000: "A B C10 C12 C13 C16 C19 C20 C22 C25 C26 C29 C30 C31 D E36 F G",
               800: "C11 C18 C21 C23 C27 C33 E H J", 600: "C34 M N Q R S", 400: "I K L N76 P"},
        "소": {120: "C10 C11 C14 C15 C19 C20 C21 C23 C24 C25 C26 C28 C29 C30 C32 D E36", 80: "A B C12 C13 C16 C17 C18 C22 C27 C31 C33 F H K",
              50: "G J", 30: "E L M N R", 10: "C34 I P Q S"}},
    "new": {
        "중소": {1800: "C17 C24 C28", 1500: "C14 C15 C32", 1200: "C10 C20 C22 C25 C29 C30 C31 F G", 1000: "A B C12 C13 C16 C19 C26 C33 D E36 H J",
               800: "C11 C18 C21 C23 C27 E N", 600: "C34 M Q R S", 400: "I K L N76 P"},
        "소": {140: "C19 C24", 120: "C10 C11 C14 C15 C20 C21 C23 C25 C26 C28 C29 C30 C32 D E36", 100: "H K",
              80: "A B C12 C13 C16 C17 C18 C22 C27 C31 C33 F", 60: "G", 50: "J", 40: "E L", 30: "M N R", 15: "C34 I P Q S"}},
}
SIZE_CODES = sorted({c for t in _SIZE_TABLES.values() for g in t["중소"].values() for c in g.split()})


def _size_limit(code, year, kind):
    table = _SIZE_TABLES["new" if year >= 2025 else "old"][kind]
    key = "N" if (kind == "소" and code == "N76") else code      # 별표 3은 N 전체가 한 줄
    for eok, codes in table.items():
        if key in codes.split():
            return eok * _EOK
    return None


def sme_status(year, industry_code, revenue, total_assets, domestic_affiliates=None, in_disclosure_group=False, large_corp_owner=False,
               excluded_business=False, first_exceeded_year=None, founded_on=""):
    문제 = []
    if not isinstance(year, int) or not 2018 <= year <= YEAR_MAX:
        문제.append(f"year={year!r} — 2018~{YEAR_MAX}(2017년까지는 종전 산업분류 기준 별표라 지원하지 않음)")
    code = (industry_code or "").strip().upper() if isinstance(industry_code, str) else ""
    if code not in SIZE_CODES:
        문제.append(f"industry_code={industry_code!r} — 주된 업종의 한국표준산업분류 기호: " + " ".join(SIZE_CODES) + " (제조업은 중분류 C10~C34, 수도업 E36, 임대업 N76)")
    _won(revenue, "revenue(해당 과세연도 손익계산서 매출액)", 문제); _won(total_assets, "total_assets(과세연도 종료일 자산총액)", 문제)
    for i, a in enumerate(domestic_affiliates or []):
        rv, own = (a or {}).get("revenue"), (a or {}).get("ownership")
        if isinstance(rv, bool) or not isinstance(rv, int) or rv < 0:
            문제.append(f"domestic_affiliates[{i}].revenue — 그 국내기업의 매출액(원)")
        if isinstance(own, bool) or not isinstance(own, (int, float)) or not 0.3 <= own <= 1:
            문제.append(f"domestic_affiliates[{i}].ownership — 주식등 소유비율 0.3~1(30% 이상 소유하면서 최다출자자인 관계만 관계기업)")
    founded = _d(founded_on, "founded_on", 문제) if founded_on else None
    if first_exceeded_year is not None and (not isinstance(first_exceeded_year, int) or isinstance(year, int) and first_exceeded_year > year):
        문제.append("first_exceeded_year — 규모 기준을 처음 넘은 과세연도(해당 과세연도 이전)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    한도, 소한도 = _size_limit(code, year, "중소"), _size_limit(code, year, "소")
    합산 = revenue + sum(a["revenue"] if a["ownership"] >= 0.5 else math.floor(a["revenue"] * a["ownership"]) for a in domestic_affiliates or [])
    판단, 주의 = [], []
    근거 = ["조세특례제한법 시행령 제2조제1항", "중소기업기본법 시행령 별표 1" + ("(2025.9.1. 개정)" if year >= 2025 else "(2017.10.17. 개정)")]
    계산 = {"주된_업종": code, "매출액": revenue, "관계기업_합산_매출액": 합산, "중소기업_매출_기준": 한도, "자산총액": total_assets, "자산총액_기준": 5_000 * _EOK,
          "소기업_매출_기준": 소한도}
    매출초과, 자산초과 = 합산 > 한도, total_assets >= 5_000 * _EOK
    if domestic_affiliates:
        근거.append("중소기업기본법 시행령 제3조의2·제7조의4·별표 2")
        판단.append(f"관계기업 합산: 50% 이상 소유는 전액, 50% 미만은 소유비율만큼 더해 {합산:,}원")
    구분, 중소 = None, False
    if in_disclosure_group or large_corp_owner or excluded_business:
        why = "공시대상기업집단 소속" if in_disclosure_group else "자산총액 5천억원 이상 법인이 30% 이상 소유한 최다출자자" if large_corp_owner else "부동산임대업 또는 소비성서비스업이 주된 사업"
        구분 = "중소기업 아님"
        판단.append(f"{why} — 중소기업이 아님" + ("" if excluded_business else ". 독립성 요건을 잃은 경우에는 유예기간도 적용하지 않음(제2조제2항제3호)"))
    elif not 매출초과 and not 자산초과:
        중소 = True
        구분 = "소기업" if revenue <= 소한도 else "중기업"
        판단.append(f"매출액 {합산:,}원 ≤ 기준 {한도:,}원, 자산총액 5천억원 미만 — 중소기업")
        판단.append(f"소기업 기준 {소한도:,}원 " + ("이내 — 소기업" if 구분 == "소기업" else "초과 — 중기업(특별세액감면 감면율이 달라짐)"))
        근거.append("조세특례제한법 시행령 제6조제4항, 중소기업기본법 시행령 별표 3")
    else:
        why = " · ".join(x for x in (f"매출액 {합산:,}원 > 기준 {한도:,}원" if 매출초과 else "", "자산총액 5천억원 이상" if 자산초과 else "") if x)
        fy = first_exceeded_year or year
        n = 5 if fy >= 2024 else 3
        근거.append("조세특례제한법 시행령 제2조제2항" + (", 대통령령(2024.11.12.) 부칙 제2조" if fy >= 2024 else ""))
        계산.update({"최초_초과_과세연도": fy, "유예기간": f"{fy}~{fy + n} 과세연도"})
        if founded and fy <= founded.year + 2:
            구분 = "중소기업 아님"
            판단.append(f"{why}. 창업일이 속하는 과세연도 종료일부터 2년 이내({founded.year}~{founded.year + 2})에 기준을 넘어 유예기간을 적용하지 않음(제2조제2항제4호)")
        elif year <= fy + n:
            중소, 구분 = True, "유예기간 중"
            판단.append(f"{why}. 처음 넘은 {fy} 과세연도와 그 다음 {n}개 과세연도({fy + n}까지)는 중소기업으로 봄 — {year}은 유예기간 중")
        else:
            구분 = "중소기업 아님"
            판단.append(f"{why}. 유예기간({fy}~{fy + n})이 지나 {year} 과세연도는 중소기업이 아님")
        주의.append("유예기간: 2024.11.12.이 속하는 과세연도 이후 처음 사유가 생기면 5개 과세연도(그 전은 3개). 상장법인 7개 과세연도 특례, 중소기업 아닌 기업과의 합병은 계산하지 않음")
        주의.append("유예기간 중 기업은 창업감면·최저한세 7% 등 중소기업 규정을 적용받지만 소기업은 아님")
    주의 += ["주된 업종: 둘 이상의 사업을 하면 사업수입금액이 큰 사업(시행령 제2조제3항). 업종 분류는 한국표준산업분류 — 위탁생산 회사가 제조업인지 도매업인지는 이 도구가 판정하지 않음",
           "위탁생산의 업종 분류: 조심2023서10448(2024.2.16.)이 인용한 제10차 한국표준산업분류 기준은 직접 기획한 제품을 자기 계정으로 구입한 원재료를 제조 사업자에게 제공해 자기 명의로 만들게 하고, 인수해 자기 책임으로 직접 판매하는 사업체를 제조업으로 분류. "
           "제조사가 원재료를 조달하는 구조면 도매업 기준(industry_code='G')으로도 판정해 볼 것 — 세액감면의 제조업 요건(시행규칙 제4조의2)에는 원재료 제공 요건이 없어 감면과 규모 판정이 달라질 수 있음",
           "매출액은 과세연도 종료일 현재 기업회계기준 손익계산서 기준. 창업·분할·합병한 과세연도는 연간으로 환산(시행규칙 제2조제4항)",
           "관계기업은 국내기업만 — 해외 자회사 매출은 합산하지 않음(중소기업기본법 시행령 제3조의2제1항). 손자기업 간접 지배, 개인 최다출자자를 통한 합산은 계산하지 않음",
           "별표 비고의 예외(자동차·철도·항공기용 의자 제조업)와 벤처투자회사 등 관계기업 제외는 반영하지 않음"]
    return {"결과": {"중소기업": 중소, "구분": 구분}, "계산": 계산, "판단": 판단, "근거": 근거, "주의": 주의}


# ── 구분경리: 감면 사업과 그 밖의 사업을 함께 할 때 감면 대상 소득 ──────────────────────────────────────────
# 근거(2016·2025 시행본 대조 — 아래 조문은 두 시행본의 내용이 같음):
#   조세특례제한법 제143조①(감면대상사업과 그 밖의 사업 겸영 시 구분경리)·③(결손 사업의 결손금은 소득이 난 사업의 소득금액에 비례해 안분해 공제),
#   시행령 제136조(법인세법 제113조 준용), 법인세법 시행규칙 제75조②(감면 사업 겸영 법인은 제76조⑥⑦ 준용, 업종 구분은 한국표준산업분류 소분류),
#   제76조⑥(공통익금은 수입금액 비례, 공통손금은 업종이 같으면 수입금액 비례·다르면 개별손금 비례)·⑦,
#   법인세법 제59조②(감면세액 = 산출세액 × 감면소득 ÷ 과세표준, 100% 한도), 시행령 제96조(공제한 이월결손금 등: 감면사업 발생분은 전액, 불분명하면 소득금액 비례),
#   조세특례제한법 시행령 제2조③(둘 이상 사업이면 사업수입금액이 큰 사업이 주된 사업).
def _split(total, weights):
    """total을 weights 비율로 나눔(원 미만 버림, 남는 원은 마지막 0 아닌 몫에)."""
    s = sum(weights)
    parts = [total * w // s for w in weights]
    rest = total - sum(parts)
    for i in range(len(weights) - 1, -1, -1):
        if weights[i]:
            parts[i] += rest
            break
    return parts


def reduction_income_segments(segments, common_income=0, common_expenses=0, same_industry=False, deductions=None):
    문제 = []
    if not isinstance(segments, list) or len(segments) < 2:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["segments — 사업 2개 이상 [{name, eligible(감면 대상이면 true), revenue, direct_expenses, direct_income?}]"]}
    names = set()
    for i, s in enumerate(segments):
        s = s or {}
        if not s.get("name") or s.get("name") in names:
            문제.append(f"segments[{i}].name — 사업 이름(겹치지 않게)")
        names.add(s.get("name"))
        if not isinstance(s.get("eligible"), bool):
            문제.append(f"segments[{i}].eligible — 감면 대상 사업이면 true, 아니면 false")
        _won(s.get("revenue"), f"segments[{i}].revenue(수입금액)", 문제)
        _won(s.get("direct_expenses"), f"segments[{i}].direct_expenses(개별손금)", 문제)
        if s.get("direct_income") is not None:
            _won(s.get("direct_income"), f"segments[{i}].direct_income(수입금액 외 개별익금)", 문제)
    _won(common_income, "common_income(공통익금)", 문제)
    _won(common_expenses, "common_expenses(공통손금)", 문제)
    ded = {"eligible": 0, "other": 0, "unclear": 0}
    for k, v in (deductions or {}).items():
        if k not in ded:
            문제.append(f"deductions.{k} — eligible(감면 사업에서 발생) | other(그 밖의 사업에서 발생) | unclear(어느 사업인지 불분명)")
        elif _won(v, f"deductions.{k}", 문제):
            ded[k] = v
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    rev = [s["revenue"] for s in segments]
    dexp = [s["direct_expenses"] for s in segments]
    if common_income and not sum(rev):
        return {"error": "계산하지 않음", "문제": ["공통익금을 나눌 수입금액이 없음 — 시행규칙 제76조⑥ 단서(국세청장이 정하는 작업시간·사용시간·사용면적 등 기준)는 계산하지 않음"]}
    exp_w = rev if same_industry else dexp
    if common_expenses and not sum(exp_w):
        return {"error": "계산하지 않음", "문제": [("수입금액" if same_industry else "개별손금") + "이 없어 공통손금을 나눌 수 없음 — 시행규칙 제76조⑥ 단서(국세청장이 정하는 작업시간·사용시간·사용면적 등 기준)는 계산하지 않음"]}
    ci = _split(common_income, rev) if common_income else [0] * len(segments)
    ce = _split(common_expenses, exp_w) if common_expenses else [0] * len(segments)
    inc = [s["revenue"] + (s.get("direct_income") or 0) - s["direct_expenses"] + a - b for s, a, b in zip(segments, ci, ce)]
    loss_total = -sum(x for x in inc if x < 0)
    pos_total = sum(x for x in inc if x > 0)
    total = pos_total - loss_total
    판단, rows, elig_sum = [], [], 0
    for s, r, d, a, b, x in zip(segments, rev, dexp, ci, ce, inc):
        cut = loss_total * x // pos_total if (x > 0 and loss_total) else 0
        after = max(0, x - cut) if x > 0 else 0
        rows.append({"사업": s["name"], "감면_대상": s["eligible"], "수입금액": r, "개별익금_외": s.get("direct_income") or 0, "개별손금": d, "공통익금_배분": a, "공통손금_배분": b,
                     "소득금액": x, "결손금_안분_공제": cut, "공제_후_소득금액": after})
        if s["eligible"]:
            elig_sum += after
    if loss_total:
        판단.append(f"결손이 난 사업의 결손금 합계 {loss_total:,}원을 소득이 난 사업의 소득금액에 비례해 나눠 공제(조세특례제한법 제143조③)")
    ded_total = ded["eligible"] + ded["other"] + ded["unclear"]
    unclear_cut = ded["unclear"] * elig_sum // total if (ded["unclear"] and total > 0) else 0
    base = max(0, total - ded_total)
    elig = max(0, elig_sum - ded["eligible"] - unclear_cut)
    if ded_total:
        판단.append(f"과세표준 계산에서 공제한 이월결손금 등 {ded_total:,}원 가운데 감면 사업 발생분 {ded['eligible']:,}원은 전액, 불분명한 {ded['unclear']:,}원은 소득금액 비례로 {unclear_cut:,}원을 감면 대상 소득에서 뺌(법인세법 시행령 제96조)")
    capped = min(elig, base)
    if elig > base:
        판단.append("감면 대상 소득이 과세표준보다 커 비율을 100%로 제한(법인세법 제59조②)")
    top = max(range(len(segments)), key=lambda i: rev[i])
    tie = [s["name"] for s, r in zip(segments, rev) if r == rev[top]]
    판단.append(f"주된 사업: {segments[top]['name']}(사업수입금액 {rev[top]:,}원이 가장 큼 — 조세특례제한법 시행령 제2조③)" if len(tie) == 1
              else f"사업수입금액이 같은 사업이 여럿({', '.join(tie)}) — 주된 사업을 정하지 않음")
    판단.append("공통손금은 " + ("업종이 같아 수입금액에 비례해" if same_industry else "업종이 달라 개별손금에 비례해") + " 나눔(법인세법 시행규칙 제76조⑥)")
    결과 = {"감면_대상_소득": capped, "과세표준": base, "감면_소득_비율": (capped / base if base else 0.0), "각사업연도소득": total,
           "주된_사업": segments[top]["name"] if len(tie) == 1 else None}
    계산 = {"사업별": rows, "공통익금": common_income, "공통손금": common_expenses, "공통손금_기준": "수입금액" if same_industry else "개별손금",
           "결손_사업_결손금_합계": loss_total, "감면_사업_소득금액_합계": elig_sum, "공제액등": ded, "불분명_공제액_안분": unclear_cut, "한도_전_감면_대상_소득": elig}
    return {"결과": 결과, "계산": 계산, "판단": 판단,
            "근거": ["조세특례제한법 제143조제1항·제3항", "조세특례제한법 시행령 제136조", "법인세법 시행규칙 제75조제2항·제76조제6항·제7항", "법인세법 제59조제2항", "법인세법 시행령 제96조", "조세특례제한법 시행령 제2조제3항"],
            "주의": ["감면_대상_소득을 startup_tax_reduction·sme_special_tax_reduction의 eligible_income에, 과세표준을 taxable_base에 넣어 감면세액을 계산",
                   "업종이 같은지는 한국표준산업분류 소분류(없으면 중분류)로 구분(시행규칙 제75조제2항) — 온라인 직접 판매(무점포 소매업)와 도매업은 서로 다른 업종. 분류 자체는 이 도구가 판정하지 않음",
                   "수입금액·개별손금은 세무조정을 사업별로 반영한 금액을 넣는다. 공통익금은 과세표준이 되는 것, 공통손금은 익금에 대응하는 것만(시행규칙 제76조제7항)",
                   "개별손금이 없거나 위 기준을 쓰기 불합리한 경우의 작업시간·사용시간·사용면적 기준(제76조제6항 단서), 감면율이 다른 감면 사업이 여럿일 때 사업별 감면세액, 비과세소득·소득공제의 사업별 귀속 판단은 계산하지 않음",
                   "주된 사업은 중소기업 해당 업종·규모 기준을 볼 때 쓰는 기준(시행령 제2조제3항). 세액감면은 주된 사업과 관계없이 감면 대상 사업에서 생긴 소득에 적용"]}


# ── 농어촌특별세: 조세특례제한법에 따른 법인세·소득세 감면세액 × 20% ────────────────────────────────────────
# 근거(2016~2025 각 연말과 2026.11.12. 시행본 대조): 농어촌특별세법 제2조①(감면 = 비과세·세액면제·세액감면·세액공제·소득공제), 제3조1호, 제5조①1호(감면세액의 20%),
#   제4조(비과세) 3호·3의3호·11의2호·11의3호·11의4호·12호, 시행령 제4조(법 제4조제12호의 목록 — 2022년까지 제6항, 2023년부터 제7항)제1호.
# 비과세 목록의 연도별 변화(각 연말 시행본):
#   법 제4조 3의3호(조특법 제16조 소득공제): 2017년 시행본부터.
#   시행령 목록 2016~2018: 제10조, 제10조의2, 제11조, 제12조, 제12조의2, 제13조, 제14조, 제18조, 제18조의2, 제29조의6, 제30조, 제30조의3, 제33조, 제63조, 제63조의2, 제64조,
#     제76조①, 제95조의2, 제98조의3, 제98조의5, 제104조의8①③, 제104조의21, 제104조의28, 제121조의2~제121조의4, 제121조의13, 제126조의2, 제126조의6, 제126조의7⑨
#   2019: + 제19조②, 제99조의9, 제104조의24 / 2020: + 제18조의3, 제25조①, 제99조의11, 제118조의2, − 제11조 / 2021: − 제25조① / 2022: + 제104조의31
#   2023: + 제16조의2 / 2025: + 제92조 / 2024·2026: 변화 없음
_RST_LAW = {"제6조": "제3호", "제7조": "제3호", "제20조": "제11호의2", "제100조": "제11호의2", "제140조": "제11호의2", "제141조": "제11호의2",
            "제30조의2": "제11호의3", "제30조의4": "제11호의3", "제121조의24": "제11호의4"}
_RST_DECREE_BASE = {"제10조": None, "제10조의2": None, "제11조": None, "제12조": None, "제12조의2": None, "제13조": None, "제14조": None, "제18조": None, "제18조의2": None,
                    "제29조의6": None, "제30조": None, "제30조의3": None, "제33조": None, "제63조": None, "제63조의2": None, "제64조": None, "제76조": "제1항",
                    "제95조의2": None, "제98조의3": None, "제98조의5": None, "제104조의8": "제1항·제3항", "제104조의21": None, "제104조의28": None,
                    "제121조의2": None, "제121조의3": None, "제121조의4": None, "제121조의13": None, "제126조의2": None, "제126조의6": None, "제126조의7": "제9항"}
_RST_DECREE_CHANGES = {2019: ({"제19조": "제2항", "제99조의9": None, "제104조의24": None}, ()),
                       2020: ({"제18조의3": None, "제25조": "제1항", "제99조의11": None, "제118조의2": None}, ("제11조",)),
                       2021: ({}, ("제25조",)), 2022: ({"제104조의31": None}, ()), 2023: ({"제16조의2": None}, ()), 2025: ({"제92조": None}, ())}
_RST_SAVINGS = range(86, 92)       # 제86조의3~제91조의…: 저축·이자·배당 감면(세율 10%, 법 제5조①2호) — 계산하지 않음


def _rst_decree(year):
    cur, changed = dict(_RST_DECREE_BASE), {}
    for y in sorted(_RST_DECREE_CHANGES):
        if y > year:
            break
        add, rem = _RST_DECREE_CHANGES[y]
        cur.update(add)
        for r in rem:
            cur.pop(r, None)
        if y == year:
            changed = {**{a: "추가" for a in add}, **{r: "삭제" for r in rem}}
    return cur, changed


def _rst_article(s):
    import re
    m = re.fullmatch(r"\s*(?:조세특례제한법\s*)?제?\s*(\d+)\s*조?(?:\s*의\s*(\d+))?\s*(?:제?\s*(\d+)\s*항)?\s*", str(s or ""))
    if not m:
        return None, None, None
    return f"제{m.group(1)}조" + (f"의{m.group(2)}" if m.group(2) else ""), int(m.group(1)), (f"제{m.group(3)}항" if m.group(3) else None)


def rural_special_tax(year, items):
    문제 = []
    if not isinstance(year, int) or isinstance(year, bool) or not YEAR_MIN <= year <= YEAR_MAX:
        문제.append(f"year={year!r} — {YEAR_MIN}~{YEAR_MAX} 과세연도")
    if not isinstance(items, list) or not items:
        문제.append("items — [{article('제24조'처럼 조세특례제한법 조문), amount(그 조문으로 실제 적용받은 감면세액, 원), name?}] 1건 이상")
    parsed = []
    for i, it in enumerate(items if isinstance(items, list) else []):
        it = it or {}
        art, num, para = _rst_article(it.get("article"))
        if art is None:
            문제.append(f"items[{i}].article={it.get('article')!r} — 조세특례제한법 조문을 '제24조'·'제29조의8'·'제76조제1항'처럼")
        ok = _won(it.get("amount"), f"items[{i}].amount(감면세액)", 문제)
        if art and ok and num in _RST_SAVINGS:
            문제.append(f"items[{i}].article={art} — 저축·이자소득·배당소득 감면(제86조의3~제91조의…)은 세율과 비과세 범위가 달라 계산하지 않음(농어촌특별세법 제5조①2호·④, 제4조4호)")
        parsed.append((art, para, it.get("amount"), it.get("name")))
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    decree, changed = _rst_decree(year)
    항_번호 = "제6항" if year <= 2022 else "제7항"
    rows, 판단, total_base, total_tax = [], [], 0, 0
    for art, para, amt, name in parsed:
        row = {"조문": art + (para or ""), **({"이름": name} if name else {}), "감면세액": amt}
        exempt, why = False, ""
        if art in _RST_LAW:
            exempt, why = True, f"농어촌특별세법 제4조{_RST_LAW[art]}"
        elif art == "제16조" and year >= 2017:
            exempt, why = True, "농어촌특별세법 제4조제3호의3"
        elif art in decree:
            limit = decree[art]
            exempt, why = True, f"농어촌특별세법 제4조제12호, 시행령 제4조{항_번호}제1호"
            if limit and (para is None or para not in limit):
                row["확인"] = f"시행령 목록은 {art}{limit}만 — 적용받은 항이 맞는지 확인"
                판단.append(f"{art}: 비과세 목록에는 {limit}만 있음. 다른 항의 감면이면 과세(20%)")
        if art in changed:
            판단.append(f"{art}: {year}년 시행령 개정으로 비과세 목록에 {changed[art]} — 어느 과세연도·감면분부터 적용하는지는 그 개정 부칙을 확인")
            row["확인"] = f"{year}년 개정으로 {changed[art]} — 부칙 적용례 확인"
        if art == "제21조":
            row["확인"] = "비거주자·외국법인에 대한 감면이면 비과세(법 제4조제5호) — 이 도구는 과세로 계산"
        if exempt:
            row.update({"과세": False, "농어촌특별세": 0, "근거": why})
        else:
            tax = amt * 20 // 100
            row.update({"과세": True, "세율": 0.2, "농어촌특별세": tax, "근거": "농어촌특별세법 제5조제1항제1호"})
            total_base += amt
            total_tax += tax
        rows.append(row)
    if total_tax:
        판단.append(f"과세 대상 감면세액 {total_base:,}원 × 20% = {total_tax:,}원")
    else:
        판단.append("입력한 감면은 모두 비과세 — 농어촌특별세 없음")
    return {"결과": {"농어촌특별세": total_tax, "과세_대상_감면세액": total_base, "비과세_감면세액": sum(r["감면세액"] for r in rows if not r["과세"])},
            "계산": {"항목별": rows, "세율": 0.2},
            "판단": 판단,
            "근거": ["농어촌특별세법 제2조제1항·제3조제1호", "농어촌특별세법 제4조", "농어촌특별세법 제5조제1항제1호", f"농어촌특별세법 시행령 제4조{항_번호}"],
            "주의": ["감면세액은 한도·최저한세를 적용한 뒤 그 과세연도에 실제로 적용받은 금액(이월되어 공제받는 해에 과세). 세액공제·세액감면만 넣는다 — 소득공제·비과세의 감면세액 환산은 계산하지 않음",
                   "비과세 목록은 그 과세연도 말 시행본 기준. 연중 개정으로 들어오거나 빠진 조문은 부칙 적용례에 따라 달라질 수 있음",
                   "창업중소기업 감면(제6조)·중소기업 특별세액감면(제7조)·연구인력개발비 세액공제(제10조)는 비과세. 통합투자세액공제(제24조)·통합고용세액공제(제29조의8)처럼 목록에 없는 공제는 20% 과세",
                   "농어촌특별세는 본세(법인세·소득세)와 함께 신고·납부. 저축·이자·배당 감면, 관세·취득세·등록면허세 감면, 지방세특례제한법 감면은 계산하지 않음"]}
