"""소득세·원천세 계산(2016~2026 귀속 연도표, 기본 2025 귀속) — 국세청 연말정산·중소기업 취업자 감면 안내 예시로 검증. 작성 Mia(윤승미)
플레이북: knowledge/14_소득세_원천세_연말정산_조사포인트.md. 2026 귀속 변경분은 표 추가 후 적용.
"""
import json
import math
import os

from .. import vocab


def _won(x):
    """원 미만 절사(⌊x⌋)."""
    return int(math.floor(x))

# 쟁점 데이터는 korean_tax_calc_mcp/data/issues.json에서 읽음 (SPEC r1d §1 — 하드코딩 금지)
def _load_issues():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "issues.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)

# 종합소득세 기본세율(소득세법 제55조①) — 귀속연도별(각 개정 부칙: 시행 전 발생 소득·개시 과세기간은 종전). knowledge/16 '소득세 연도표'
_R2016 = [(12_000_000, 0.06), (46_000_000, 0.15), (88_000_000, 0.24), (150_000_000, 0.35), (math.inf, 0.38)]
_R2017 = _R2016[:4] + [(500_000_000, 0.38), (math.inf, 0.40)]                                   # 2016.12.20. 개정: 5억 초과 40%
_R2018 = _R2016[:4] + [(300_000_000, 0.38), (500_000_000, 0.40), (math.inf, 0.42)]             # 2017.12.19. 개정: 3억 40%, 5억 42%
_R2021 = _R2016[:4] + [(300_000_000, 0.38), (500_000_000, 0.40), (1_000_000_000, 0.42), (math.inf, 0.45)]  # 2020.12.29. 개정: 10억 초과 45%
_R2023 = [(14_000_000, 0.06), (50_000_000, 0.15), (88_000_000, 0.24), (150_000_000, 0.35),
          (300_000_000, 0.38), (500_000_000, 0.40), (1_000_000_000, 0.42), (math.inf, 0.45)]   # 2022.12.31. 개정: 1,400만·5,000만
RATES = {2016: _R2016, 2017: _R2017, 2018: _R2018, 2019: _R2018, 2020: _R2018, 2021: _R2021, 2022: _R2021,
         2023: _R2023, 2024: _R2023, 2025: _R2023, 2026: _R2023}  # 2026: 2026.9.30. 시행본까지 변경 없음


class NoYearTable(ValueError):
    """연도표 없는 귀속연도 — 계산하지 않음(추정 금지)."""


def _y(year):
    if year not in RATES: raise NoYearTable(f"소득세 연도표 없음: {year}")
    return year


def _tier(x, tiers):
    out, prev = 0.0, 0
    for cap, r in tiers:
        if x > prev: out += (min(x, cap) - prev) * r
        prev = cap
    return out


def earned_deduction(gross, year=2025):
    """근로소득공제(소득세법 제47조①): 구간표 2016~2026 동일. 한도 2,000만은 2019.12.31. 개정(2020 귀속~), 그 전 한도 없음."""
    t = [(5_000_000, 0.70), (15_000_000, 0.40), (45_000_000, 0.15), (100_000_000, 0.05), (math.inf, 0.02)]
    d = _tier(gross, t)
    return int(min(d, 20_000_000) if _y(year) >= 2020 else d)


def income_tax(base, year=2025): return int(_tier(base, RATES[_y(year)]))


def earned_tax_credit(calc_tax, gross, reduced_tax=0, year=2025):
    """근로소득세액공제(제59조): 산출 130만 이하 55%, 초과 71.5만+30%(2016~2026 동일). 한도는 총급여 구간별.
    한도 ②: 2016~2022 귀속 3구간(7천만 초과 max(50만, 66만 − 초과분/2)), 2023 귀속~ 1억2천만 초과 구간 신설
    (max(20만, 50만 − 초과분/2), 2022.12.31. 개정 부칙 제15조: 시행 전 개시 과세기간 종전).
    감면(중소기업 취업자 등)이 있으면 공제액 × (1 − 감면세액/산출세액)(원 미만 절사)."""
    c = calc_tax * 0.55 if calc_tax <= 1_300_000 else 715_000 + (calc_tax - 1_300_000) * 0.30
    if gross <= 33_000_000: cap = 740_000
    elif gross <= 70_000_000: cap = max(660_000, 740_000 - (gross - 33_000_000) * 0.008)
    elif _y(year) <= 2022: cap = max(500_000, 660_000 - (gross - 70_000_000) * 0.5)
    elif gross <= 120_000_000: cap = max(500_000, 660_000 - (gross - 70_000_000) * 0.5)
    else: cap = max(200_000, 500_000 - (gross - 120_000_000) * 0.5)
    v = min(c, cap)
    return int(v * (1 - reduced_tax / calc_tax)) if reduced_tax and calc_tax else int(v)


def sme_youth_reduction(calc_tax, gross, reduced_gross, rate=0.9, cap=2_000_000):
    """중소기업 취업자 감면(조특법 제30조): 산출세액 × 감면대상 총급여/총급여 × 감면율, 연 200만 한도."""
    return int(min(calc_tax * reduced_gross / gross * rate, cap))


def daily_worker_tax(daily_wage, year=2025):
    """일용근로(제134조③): (일급 − 근로소득공제) × 6%(제129조①4호) × (1 − 55%, 제59조③), 1천원 미만 소액부징수(제86조).
    일용 근로소득공제(제47조②): 1일 10만(~2018) → 15만(2018.12.31. 개정, 2019.1.1. 시행)."""
    ded = 100_000 if _y(year) <= 2018 else 150_000
    t = int(max(0, daily_wage - ded) * 0.06 * 0.45)
    return t if t >= 1_000 else 0


def withholding_late_penalty(unpaid, days, start=None):
    """원천징수 등 납부지연가산세(국기법 제47조의5①): 3% + 일수분, 한도 10%(납부고지 전 기간 기준 — 2020.1.1.~ 고지 후 기간 포함 50%).
    일수분 이율: start(법정납부기한 다음 날) 주면 국기령 제27조의4 이율 변경일로 안분(1만분의 3 → 10만분의 25 → 10만분의 22)."""
    if start:
        from .calc_vat import late_payment_rate_segments
        daily = sum(unpaid * r * n for n, r in late_payment_rate_segments(start, days))
    else:
        daily = unpaid * 0.00022 * days
    return int(min(unpaid * 0.03 + daily, unpaid * 0.10))


def payment_statement_penalty(amount, within_3m=False, due_date=None, daily_worker=False, paid_on=None):
    """지급명세서 미제출(소득세법 제81조의11, 2019년 이전 제81조①).
    - 제출기한이 2018.1.1. 이후: 1%, 기한 후 3개월 내 0.5%(2016.12.20. 개정, 부칙 제7조)
    - 제출기한이 2017.12.31. 이전(due_date 지정): 2%, 3개월 내 1%
    - 일용근로소득 지급명세서(daily_worker, 2021.7.1. 이후 지급분 — 2021.3.16. 개정 부칙 제2조): 0.25%, 기한 후 1개월 내 0.125%(within_3m=기한 후 제출 감면 구간 여부)"""
    if daily_worker and (paid_on is None or paid_on >= "2021-07-01"):
        return int(amount * (0.00125 if within_3m else 0.0025))
    if due_date and due_date < "2018-01-01":
        return int(amount * (0.01 if within_3m else 0.02))
    return int(amount * (0.005 if within_3m else 0.01))


# ── 퇴직소득세(소득세법 제48조·제55조②, 2025.1.1. 이후 퇴직분, 시행 2023.1.1. 개정 공제표) ─────
def retirement_service_deduction(years):
    """근속연수공제(제48조①1호): 5년 이하 100만×n, 10년 이하 500만+200만×(n−5),
    20년 이하 1,500만+250만×(n−10), 초과 4,000만+300만×(n−20). 근속연수는 1년 미만 절상한 정수."""
    n = years
    if n <= 5: return 1_000_000 * n
    if n <= 10: return 5_000_000 + 2_000_000 * (n - 5)
    if n <= 20: return 15_000_000 + 2_500_000 * (n - 10)
    return 40_000_000 + 3_000_000 * (n - 20)


def converted_pay_deduction(conv):
    """환산급여공제(제48조①2호): 800만 이하 100%, 7천만 이하 800만+60%, 1억 이하 4,520만+55%,
    3억 이하 6,170만+45%, 초과 1억5,170만+35%."""
    if conv <= 8_000_000: return conv
    if conv <= 70_000_000: return 8_000_000 + (conv - 8_000_000) * 0.60
    if conv <= 100_000_000: return 45_200_000 + (conv - 70_000_000) * 0.55
    if conv <= 300_000_000: return 61_700_000 + (conv - 100_000_000) * 0.45
    return 151_700_000 + (conv - 300_000_000) * 0.35


def retirement_tax(income, years):
    """퇴직소득 산출세액. income=퇴직소득금액(비과세 제외), years=근속연수(1년 미만 절상).
    ① 근속연수공제(퇴직소득금액 한도, 제48조②) → ② 환산급여 = (금액−①)/근속연수×12
    → ③ 과세표준 = 환산급여 − 환산급여공제 → ④ 산출세액 = 기본세율(제55조①)(과세표준)/12×근속연수(제55조②).
    원 미만 절사만 적용(원천징수 10원 미만 절사는 국고금관리법 — 호출자 처리)."""
    if income <= 0 or years <= 0: return 0
    sd = min(retirement_service_deduction(years), income)
    conv = (income - sd) / years * 12
    base = max(0, conv - converted_pay_deduction(conv))
    return int(_tier(base, RATES[2025]) / 12 * years)


# ── 원천징수세율(소득세법 제129조①②, 2025.1.1. 시행 법률 제20615호 기준) ─────────────────
WITHHOLDING_RATES = {
    "이자": 0.14, "비영업대금": 0.25, "온투업이자": 0.14,          # ①1호 라·나목
    "배당": 0.14, "출자공동사업자배당": 0.25,                        # ①2호 나·가목
    "사업": 0.03, "외국인직업운동가": 0.20,                          # ①3호
    "기타": 0.20, "기타_연금외수령등": 0.15, "기타_복권3억초과분": 0.30,  # ①6호 라·나·가목
    "봉사료": 0.05, "일용근로": 0.06,                                # ①8호·①4호 단서
    "비실명": 0.45,                                                  # ②2호
}


def withholding_rate(kind, year=2025):
    """원천징수세율 지급연도별(소득세법 제129조). 2016~2026 중 변경:
    비실명 38%(~2017) → 40%(2018, 2017.12.19. 개정) → 42%(2019, 2018.12.31. 개정) → 45%(2023, 2022.12.31. 개정) — 모두 '시행 이후 지급분'.
    외국인직업운동가 20%: 2019.1.1. 이후 지급분(2018.12.31. 신설, 그 전은 사업소득 3%).
    온투업이자 14%: 2020.1.1. 이후 지급분(2018.12.31. 신설, 부칙 제14조①; 그 전은 비영업대금 25%).
    이자·배당 14%, 비영업대금 25%, 사업 3%, 기타 20%, 봉사료 5%, 일용 6%는 변동 없음."""
    y = _y(year)
    if kind == "비실명": return 0.38 if y <= 2017 else 0.40 if y == 2018 else 0.42 if y <= 2022 else 0.45
    if kind == "외국인직업운동가" and y <= 2018: return WITHHOLDING_RATES["사업"]
    if kind == "온투업이자" and y <= 2019: return WITHHOLDING_RATES["비영업대금"]
    return WITHHOLDING_RATES[kind]


def withholding_tax(kind, amount, year=2025):
    """분리 세율 원천징수세액(소득세분, 지방소득세 별도). 소득처분 배당 → '배당'(14%), 기타소득 처분 → '기타'(20%,
    필요경비 없음). 상여 처분은 기본세율 재정산(deemed_bonus_resettlement). 10원 미만 절사."""
    return int(amount * withholding_rate(kind, year)) // 10 * 10


# ── 비거주자·외국법인 원천징수(소득세법 제156조 / 법인세법 제98조) ──────────────────
DOMESTIC_WH_RATES = {
    "이자": 0.20, "배당": 0.20, "사용료": 0.20, "인적용역": 0.20, "기타": 0.20,
}
DOMESTIC_WH_BASIS = {
    "이자": "소득세법 제156조①1호 / 법인세법 제98조①1호",
    "배당": "소득세법 제156조①2호 / 법인세법 제98조①2호",
    "사용료": "소득세법 제156조①6호 / 법인세법 제98조①6호",
    "인적용역": "소득세법 제156조①4호 / 법인세법 제98조①4호",
    "기타": "소득세법 제156조①8호 / 법인세법 제98조①8호",
}


def _match(issue_match, *, income_kind, treaty_rate, related_party):
    """issues.json 쟁점의 match 필드와 실제 사실 관계 비교. AND 조건 — 적힌 키는 모두 만족해야 True."""
    if "income_kind" in issue_match:
        ik = issue_match["income_kind"]
        if isinstance(ik, list):
            if income_kind not in ik: return False
        elif income_kind != ik:
            return False
    if "treaty_rate_given" in issue_match:
        if (treaty_rate is not None) != issue_match["treaty_rate_given"]:
            return False
    if "related_party" in issue_match:
        if related_party != issue_match["related_party"]:
            return False
    return True


def nonresident_withholding(income_kind, amount, recipient_type, residence_country,
                            treaty_rate=None, bond_interest=False, related_party=False):
    """비거주자·외국법인 국내원천소득 원천징수. 적용세율 = min(국내세율, 조약 제한세율).
    domestic_rate는 소득세법 제156조(비거주자)·법인세법 제98조(외국법인)에 따르며, 수취인 구분(개인/법인)과
    관계없이 소득 종류 기준 동일 세율. 조약_rate 미지정 시 국내세율만 적용.
    채권이자(bond_interest=True, income_kind='이자')는 국가·지방자치단체·내국법인 발행 채권 이자로
    소득세법 제156조①1호가목·법인세법 제98조①1호가목 특례 14% 적용.
    related_party=True이면 수취인이 국외지배주주일 가능성을 고려하여 과소자본 쟁점(국제조세조정에 관한 법률 제22조)을 함께 표시한다."""
    if bond_interest and income_kind == "이자":
        domestic = 0.14
        basis = "소득세법 제156조①1호가목 / 법인세법 제98조①1호가목 (국가·지방자치단체·내국법인 발행 채권 이자)"
    else:
        domestic = DOMESTIC_WH_RATES[income_kind]
        basis = DOMESTIC_WH_BASIS[income_kind]
    applicable = min(domestic, treaty_rate) if treaty_rate is not None else domestic
    note = ""
    if treaty_rate is not None and treaty_rate > domestic:
        note = " · 조약세율이 국내세율보다 높아 국내세율 적용"
    wh_amount = int(amount * applicable) // 10 * 10
    local_income_tax = int(wh_amount * 0.10) // 10 * 10

    # 쟁점 부착 (issues.json match 필드 기반 — SPEC r1f §1)
    _issues = _load_issues().get("nonresident_withholding", [])
    issues: list[dict] = []
    for it in _issues:
        m = it.get("match")
        if m is None:
            continue  # match 없는 쟁점은 부착하지 않음
        if _match(m, income_kind=income_kind, treaty_rate=treaty_rate, related_party=related_party):
            issues.append(it)

    return {
        "국내세율": domestic,
        "조약세율": treaty_rate,
        "적용세율": applicable,
        "원천징수세액": wh_amount,
        "지방소득세": local_income_tax,
        "합계": wh_amount + local_income_tax,
        "근거": basis + (f" · 조세조약 제한세율 {treaty_rate*100:.0f}%" if treaty_rate else "") + note,
        "쟁점": issues,
    }


# ── 인정상여 귀속연도 연말정산 재정산(소득세법 제135조④·제131조②, 소령 제49조①3호·제196조) ──
def deemed_bonus_resettlement(gross, base, bonus, other_credits=0, prev_decided=None, reduced_tax=0, year=2025):
    """상여 처분액을 귀속연도 총급여에 가산해 연말정산을 다시 한 결정세액과 추가 원천징수세액.
    base=당초 과세표준(근로소득공제 차감 후). 근로소득공제만 총급여 증가분으로 재계산하고, 그 밖의
    소득공제·세액공제(other_credits=근로소득세액공제 외 세액공제 합계)는 당초 금액 유지(총급여 연동
    공제가 있으면 수기 보정). prev_decided 미입력 시 당초 결정세액도 같은 방식으로 재계산."""
    def decided(g, b):
        t = income_tax(b, year)
        return max(0, t - reduced_tax - earned_tax_credit(t, g, reduced_tax, year) - other_credits)
    g2 = gross + bonus
    b2 = base + bonus - (earned_deduction(g2, year) - earned_deduction(gross, year))
    new = decided(g2, b2)
    old = decided(gross, base) if prev_decided is None else prev_decided
    return {"재정산총급여": g2, "재정산과세표준": b2, "재정산결정세액": new, "당초결정세액": old, "추가원천징수세액": max(0, new - old)}


# ── 임원 퇴직소득 한도(소득세법 제22조③④, 소령 제42조의2⑤⑥) ────────────────────────
def _ceil_months(m): return int(math.ceil(m))


def exec_retirement_limit(avg_pay_2019, months_2012_2019, avg_pay_final, months_2020_on):
    """한도 = 2019.12.31.부터 소급 3년 총급여 연평균환산액 × 1/10 × (2012.1.1.~2019.12.31. 근무월수)/12 × 3
           + 퇴직일부터 소급 3년 총급여 연평균환산액 × 1/10 × (2020.1.1. 이후 근무월수)/12 × 2.
    근무월수는 1개월 미만 1개월(제22조④1호). 연평균환산액은 3년 미만이면 해당 근무기간 기준."""
    m1, m2 = _ceil_months(months_2012_2019), _ceil_months(months_2020_on)
    return int(avg_pay_2019 * 0.1 * m1 / 12 * 3 + avg_pay_final * 0.1 * m2 / 12 * 2)


def exec_retirement_excess(retire_income, months_before_2012, months_2012_2019, months_2020_on,
                           avg_pay_2019, avg_pay_final, amount_2011=None):
    """한도초과액(근로소득 간주, 원천징수영수증 ⑮-3). 대상 = 퇴직소득금액(공적연금 일시금 제외) − 2011.12.31. 퇴직 가정액.
    2011 가정액 = 퇴직소득금액 × 2011 이전 근무월수/전체 근무월수(소령§42의2⑥), 임원퇴직급여규정 선택 시 amount_2011."""
    m0, m1, m2 = (_ceil_months(x) for x in (months_before_2012, months_2012_2019, months_2020_on))
    tot = m0 + m1 + m2
    pre = amount_2011 if amount_2011 is not None else (retire_income * m0 / tot if tot else 0)
    lim = exec_retirement_limit(avg_pay_2019, m1, avg_pay_final, m2)
    return int(max(0, retire_income - pre - lim))


# ── 특별세액공제 ────────────────────────────────────────────────────
_KNOWN_KINDS = {
    "보장성보험", "장애인전용보장성보험",
    "의료비", "안경", "산후조리원",
    "미숙아·선천성이상아", "난임시술", "미용성형·건강증진",
    "교육비_취학전", "교육비_초중고", "교복", "체험학습",
    "교육비_대학", "대입전형료", "교육비_대학원",
    "직업훈련", "학자금상환", "직계비속학자금대출지급",
    "특수교육비", "발달재활서비스",
}


# ── persons.relation 허용값 · 동의어 ────────────────────────────────────────
# 특별세액공제에서 인식하는 relation 값. 이 밖은 '문제'로 거부하고 계산하지 않는다.
ALLOWED_RELATIONS = (
    "본인", "배우자", "직계비속", "입양자", "형제자매", "직계존속",
    "위탁아동", "수급자",
)
# 문항 표현 그대로 들어오는 값을 허용값으로 매핑. 매핑에도 없는 값은 거부.
RELATION_SYNONYMS = {
    "자녀": "직계비속",
    "아들": "직계비속",
    "딸": "직계비속",
    "부모": "직계존속",
    "모친": "직계존속",
    "부친": "직계존속",
    "어머님": "직계존속",
    "아버님": "직계존속",
    "엄마": "직계존속",
    "아빠": "직계존속",
}


def _validate_relations(persons):
    """persons 목록의 relation을 검증·정규화한다.

    반환: (문제가 있으면 문제 문자열 목록, 없으면 None).
    동의어는 허용값으로 매핑하고, 매핑에도 없는 값은 거부한다."""
    problems = []
    for p in persons:
        rel = p.get("relation", "")
        if rel in ALLOWED_RELATIONS:
            continue
        canon = RELATION_SYNONYMS.get(rel)
        if canon is not None:
            p["relation"] = canon  # 동의어 → 정식값 치환
            continue
        problems.append(
            f"persons[{persons.index(p)}].relation='{rel}'은(는) 허용값이 아님 "
            f"— 허용: {', '.join(ALLOWED_RELATIONS)}"
        )
    return problems if problems else None


def _is_basic_dependent(p, 기본공제대상자_map):
    """기본공제대상자 판정 (basic_dependent 오버라이드 지원)."""
    if p.get("basic_dependent") is not None:
        return p["basic_dependent"]
    rel = p["relation"]
    if rel == "본인":
        return True
    if not p.get("income_ok", True):
        return False
    if p.get("disabled", False):
        return True
    if rel == "배우자":
        return True
    if rel in ("직계비속", "입양자"):
        return p["age"] <= 20
    if rel == "형제자매":
        return p["age"] <= 20 or p["age"] >= 60
    if rel == "직계존속":
        return p["age"] >= 60
    # 위탁아동·수급자 등: 나이 무관
    return True


def special_tax_credit(
    year: int,
    earner_type: str,
    total_salary: int,
    persons: list,
    expenses: list,
    wage_computed_tax: int = None,
    monthly_rent_credit: int = 0,
    donation_credit: int = 0,
    special_income_deduction: int = 0,
):
    """근로소득자 특별세액공제(보험료·의료비·교육비)와 표준세액공제 비교."""
    problems = []

    # ── 입력 검사 ──────────────────────────────────────────────────────────
    if earner_type != "근로":
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"earner_type='{earner_type}'은(는) 지원하지 않음 — '근로'만 계산"]}

    if year < 2016 or year > 2026:
        problems.append(f"year={year}은(는) 지원 범위(2016~2026) 밖")

    # 본인 수 검사
    본인_list = [p for p in persons if p.get("relation") == "본인"]
    if len(본인_list) == 0:
        problems.append("본인(relation='본인')이 없음")
    elif len(본인_list) > 1:
        problems.append("본인(relation='본인')이 2명 이상")

    # name 중복 검사
    names_seen = {}
    for p in persons:
        n = p.get("name", "")
        if n in names_seen:
            problems.append(f"name 중복: '{n}'")
        names_seen[n] = names_seen.get(n, 0) + 1

    # expense.person 존재 검사 + reimbursed 검증 + 모르는 kind 검사
    person_names = {p["name"] for p in persons}
    for i, e in enumerate(expenses):
        k = e.get("kind", "")
        if k not in _KNOWN_KINDS:
            problems.append(f"지출 {i+1}: kind='{k}'은(는) 지원하지 않음")
            continue
        pn = e.get("person", "")
        if pn not in person_names:
            problems.append(f"지출 {i+1}: person='{pn}'이(가) persons 목록에 없음")
        amt = e.get("amount", 0)
        if isinstance(amt, bool) or not isinstance(amt, int):
            problems.append(f"지출 {i+1}: amount=int 필요, 현재 {amt}")
            continue
        reb = e.get("reimbursed", 0)
        if isinstance(reb, bool) or not isinstance(reb, int):
            problems.append(f"지출 {i+1}: reimbursed=int 필요, 현재 {reb}")
            continue
        if reb > amt:
            problems.append(f"지출 {i+1}: reimbursed({e.get('reimbursed', 0)}) > amount({e.get('amount', 0)})")

    if problems:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": problems}

    # persons.relation 검증·정규화 (동의어 매핑, 허용값 밖은 거부)
    rel_problems = _validate_relations(persons)
    if rel_problems:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": rel_problems}

    persons_dict = {p["name"]: p for p in persons}

    # ── 기본공제대상자 판정 (보험료용) ──────────────────────────────────────
    기본공제대상자 = {}
    for p in persons:
        기본공제대상자[p["name"]] = _is_basic_dependent(p, 기본공제대상자)

    # ── 보험료 (제59조의4①) ──────────────────────────────────────────────
    일반대상 = 0
    장애인전용대상 = 0
    for e in expenses:
        k = e["kind"]
        pn = e["person"]
        if k == "보장성보험":
            if 기본공제대상자.get(pn, False):
                일반대상 += e["amount"]
        elif k == "장애인전용보장성보험":
            p = persons_dict.get(pn, {})
            if not p.get("disabled", False):
                problems.append(f"장애인전용보장성보험: person='{pn}'은(는) 장애인이 아님")
                continue
            if 기본공제대상자.get(pn, False):
                장애인전용대상 += e["amount"]
            else:
                problems.append(f"장애인전용보장성보험: person='{pn}'은(는) 기본공제대상자 아님")

    if problems:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": problems}

    voc_p = vocab.rule("특별세액공제_보험료", year)
    일반한도 = voc_p["그룹_한도"]
    장애인한도 = voc_p["그룹_한도"]
    일반대상 = min(일반대상, 일반한도)
    장애인전용대상 = min(장애인전용대상, 장애인한도)
    일반공제액 = _won(일반대상 * voc_p["일반_율"])
    장애인전용공제액 = _won(장애인전용대상 * voc_p["장애인전용_율"])
    보험료공제 = 일반공제액 + 장애인전용공제액

    # ── 의료비 (제59조의4②) ──────────────────────────────────────────────
    의료비일반 = 0       # 1호 후보 (일반 지출)
    의료비특정 = 0       # 2호 후보 (특정 지출)
    의료미엄숙아 = 0     # 3호 후보 (2022~)
    의료비난임 = 0       # 4호 후보 (2022~), 3호 (2017~2021), 2호 (2016)

    voc_m = vocab.rule("특별세액공제_의료비", year)
    문턱 = total_salary * voc_m["문턱_비율"]
    일반한도_m = voc_m["일반_한도"]
    안경한도 = voc_m["안경_한도"]

    for e in expenses:
        k = e["kind"]
        pn = e["person"]
        amount = max(0, e["amount"] - e.get("reimbursed", 0))

        if k == "의료비":
            p = persons_dict.get(pn, {})
            age = p.get("age", 0)
            disabled = p.get("disabled", False)
            severe = p.get("severe_illness", False)
            is_self = p.get("relation") == "본인"

            # 2호(특정): 본인 / age ≥ 65 / 장애인 / severe_illness(2018~) / 6세 이하(2024~)
            if is_self:
                의료비특정 += amount
            elif voc_m.get("6세이하_특정") and age <= 7:
                의료비특정 += amount
            elif age >= 65 or disabled or severe:
                의료비특정 += amount
            else:
                의료비일반 += amount

        elif k == "안경":
            # 제59조의4② 괄호: persons 목록의 모든 사람이 의료비 공제대상
            의료비일반 += min(amount, 안경한도)

        elif k == "산후조리원":
            if not voc_m.get("산후조리", False):
                continue
            if not 기본공제대상자.get(pn, False):
                continue
            상한 = voc_m.get("산후조리_총급여_상한")
            if 상한 is not None and total_salary > 상한:
                continue
            의료비일반 += min(amount, voc_m["산후조리_한도"])

        elif k == "미숙아·선천성이상아":
            if voc_m.get("미숙아_율", 0) > 0:
                의료비미숙아 += amount

        elif k == "난임시술":
            의료비난임 += amount

        elif k == "미용성형·건강증진":
            pass  # 공제 제외

    # 미달액 순서로 1호→2호→3호→4호 공제대상 계산
    미달액 = max(0, 문턱 - 의료비일반)
    h1_target = min(max(0, 의료비일반 - 문턱), 일반한도_m)

    h2_target = max(0, 의료비특정 - 미달액)
    미달액 = max(0, 미달액 - 의료비특정)

    h3_target = max(0, 의료미엄숙아 - 미달액)
    미달액 = max(0, 미달액 - 의료미엄숙아)

    h4_target = max(0, 의료비난임 - 미달액)

    미숙아율 = voc_m.get("미숙아_율", 0)
    난임율 = voc_m.get("난임_율", 0)
    의료비공제 = _won(h1_target * 0.15 + h2_target * 0.15 +
                       h3_target * 미숙아율 + h4_target * 난임율)

    # ── 교육비 (제59조의4③) ──────────────────────────────────────────────
    교육비대상합계 = 0
    사람별 = []
    voc_e = vocab.rule("특별세액공제_교육비", year)
    체험할아이면 = voc_e.get("체험학습", False)
    학자금상환이면 = voc_e.get("학자금상환", False)
    대입전형료이면 = voc_e.get("대입전형료", False)
    부양가족소득요건 = voc_e.get("부양가족_소득요건", True)  # 2026~ false

    취학전초중고한도 = voc_e["취학전초중고_한도"]
    대학한도 = voc_e["대학_한도"]

    for p in persons:
        name = p["name"]
        rel = p["relation"]
        age = p["age"]
        disabled = p.get("disabled", False)
        income_ok = p.get("income_ok", True)

        person_total = 0
        취학전초중고합 = 0  # 취학전+초중고+교복+체험학습 합산(한도 300만원 적용용)
        for e in expenses:
            if e["person"] != name:
                continue
            kind = e["kind"]
            amount = max(0, e["amount"] - e.get("reimbursed", 0))

            # 본인 외 제외 항목
            if kind in ("교육비_대학원", "직업훈련"):
                if rel == "본인":
                    person_total += amount
                continue
            if kind == "학자금상환":
                if 학자금상환이면 and rel == "본인":
                    person_total += amount
                continue
            if kind == "직계비속학자금대출지급":
                continue  # 2017~ 공제 제외
            if kind == "특수교육비":
                if disabled:
                    person_total += amount
                continue
            if kind == "발달재활서비스":
                if disabled and age < 18:
                    person_total += amount
                continue
            if rel == "직계존속" and kind not in ("특수교육비", "발달재활서비스"):
                continue

            # 부양가족 소득 요건 (2026~ 폐지)
            if rel != "본인" and rel in ("배우자", "직계비속", "입양자", "위탁아동", "형제자매"):
                if 부양가족소득요건 and not income_ok:
                    continue

            _교육종류 = ("교육비_취학전", "교육비_초중고", "교복", "체험학습",
                         "교육비_대학", "대입전형료", "특수교육비", "발달재활서비스")
            if rel == "본인":
                if kind in _교육종류:
                    person_total += amount
            elif rel in ("배우자", "직계비속", "입양자", "위탁아동", "형제자매"):
                if kind in ("교육비_취학전", "교육비_초중고", "교복", "체험학습"):
                    if kind == "교복":
                        amount = min(amount, voc_e["교복_한도"])
                    elif kind == "체험학습":
                        if 체험할아이면:
                            amount = min(amount, voc_e["체험학습_한도"])
                        else:
                            amount = 0
                    취학전초중고합 += amount
                    person_total += amount
                elif kind in ("교육비_대학", "대입전형료"):
                    if kind == "대입전형료" and not 대입전형료이면:
                        continue
                    person_total += min(amount, 대학한도)

        # 취학전+초중고+교복+체험학습 합산 300만원 한도 (본인 외 대상)
        if rel != "본인" and 취학전초중고합 > 취학전초중고한도:
            person_total = person_total - 취학전초중고합 + 취학전초중고한도

        사람별.append({"name": name, "대상액": person_total, "한도": None, "공제대상": person_total})
        교육비대상합계 += person_total

    교육비공제 = _won(교육비대상합계 * voc_e["율"])

    # ── 합계 · 한도 · 표준세액공제 비교 ──────────────────────────────────
    특별합계 = 보험료공제 + 의료비공제 + 교육비공제

    한도초과액 = 0
    한도반영 = 특별합계
    if wage_computed_tax is not None:
        한도초과액 = max(0, 특별합계 + monthly_rent_credit - wage_computed_tax)
        한도반영 = max(0, 특별합계 - 한도초과액)

    항목별합계 = 한도반영 + donation_credit + monthly_rent_credit
    표준세액공제 = 130000
    표준적용가능 = special_income_deduction == 0
    if 표준적용가능:
        선택 = "항목별" if 항목별합계 >= 표준세액공제 else "표준세액공제"
    else:
        선택 = "항목별"

    적용세액공제 = 항목별합계 if 선택 == "항목별" else 표준세액공제

    # ── 판단 목록 ──────────────────────────────────────────────────────────
    판단 = []
    for e in expenses:
        k = e["kind"]
        pn = e["person"]
        p = persons_dict.get(pn, {})

        if k == "보장성보험":
            if not 기본공제대상자.get(pn, False):
                판단.append({"항목": k, "결론": "기본공제대상자 아님 — 보험료 공제 제외",
                             "근거": "소득세법 제50조①"})
        elif k == "장애인전용보장성보험":
            if not p.get("disabled", False):
                판단.append({"항목": k, "결론": "장애인이 아닌 사람의 장애인전용보장성보험 — 오류 처리됨",
                             "근거": "소득세법 제59조의4①1호"})
            elif not 기본공제대상자.get(pn, False):
                판단.append({"항목": k, "결론": "기본공제대상자 아님 — 보험료 공제 제외",
                             "근거": "소득세법 제50조①"})
        elif k == "산후조리원":
            if not voc_m.get("산후조리", False):
                판단.append({"항목": k, "결론": f"{year}년 산후조리원 공제 대상 아님",
                             "근거": "소득세법 시행령 제118조의5①7호"})
            elif voc_m.get("산후조리_총급여_상한") is not None and total_salary > voc_m["산후조리_총급여_상한"]:
                판단.append({"항목": k, "결론": f"총급여 {total_salary:,}원이 상한 {voc_m['산후조리_총급여_상한']:,}원 초과 — 산후조리원 공제 제외",
                             "근거": "소득세법 시행령 제118조의5①7호, 부칙"})
        elif k == "체험학습":
            if not 체험할아이면:
                판단.append({"항목": k, "결론": f"{year}년 체험학습 공제 대상 아님",
                             "근거": "소득세법 시행령 제118조의6①6호"})
        elif k == "학자금상환":
            if not 학자금상환이면:
                판단.append({"항목": k, "결론": f"{year}년 학자금상환 공제 대상 아님",
                             "근거": "소득세법 제59조의4③2호라목"})
        elif k == "대입전형료":
            if not 대입전형료이면:
                판단.append({"항목": k, "결론": f"{year}년 대입전형료 공제 대상 아님",
                             "근거": "소득세법 제59조의4③1호가목, 시행령 제118조의6①7호"})
        elif k == "직계비속학자금대출지급":
            판단.append({"항목": k, "결론": "직계비속등이 학자금 대출로 낸 교육비 — 공제 제외(2017~)",
                         "근거": "소득세법 제59조의4③1호 단서"})
        elif k == "미용성형·건강증진":
            판단.append({"항목": k, "결론": "미용·성형·건강증진 의료비 — 공제 제외",
                         "근거": "소득세법 시행령 제118조의5②"})
        elif k == "의료비":
            if not 기본공제대상자.get(pn, False) and p.get("relation") not in ("본인",):
                pass  # 의료비는 소득·나이 무관 공제대상(제59조의4② 괄호)
        elif k == "교육비_대학원":
            if rel != "본인":
                판단.append({"항목": k, "결론": "본인 외 대학원 교육비 — 공제 제외",
                             "근거": "소득세법 제59조의4③1호 단서·2호나목"})
        elif k == "직업훈련":
            if rel != "본인":
                판단.append({"항목": k, "결론": "본인 외 직업훈련 교육비 — 공제 제외",
                             "근거": "소득세법 제59조의4③2호다목"})
        elif k == "발달재활서비스":
            if disabled and age >= 18:
                판단.append({"항목": k, "결론": "발달재활서비스: 종료일 현재 18세 이상 — 공제 제외",
                             "근거": "소득세법 제59조의4③3호나목"})
        elif k == "특수교육비":
            if not disabled:
                판단.append({"항목": k, "결론": "장애인이 아닌 사람의 특수교육비 — 공제 제외",
                             "근거": "소득세법 제59조의4③3호가·다목"})

    return {
        "결과": {
            "보험료_세액공제": 보험료공제,
            "의료비_세액공제": 의료비공제,
            "교육비_세액공제": 교육비공제,
            "특별세액공제_합계": 특별합계,
            "한도초과액": 한도초과액,
            "특별세액공제_한도반영": 한도반영,
            "표준세액공제": 표준세액공제,
            "항목별_합계": 항목별합계,
            "표준세액공제_적용가능": 표준적용가능,
            "선택": 선택,
            "적용_세액공제": 적용세액공제,
        },
        "계산": {
            "보험료": {
                "일반_대상액": 일반대상,
                "장애인전용_대상액": 장애인전용대상,
                "일반_공제액": 일반공제액,
                "장애인전용_공제액": 장애인전용공제액,
            },
            "의료비": {
                "문턱": 문턱,
                "일반": 의료비일반,
                "특정": 의료비특정,
                "미숙아": 의료미엄숙아,
                "난임": 의료비난임,
                "1호_공제대상": h1_target,
                "2호_공제대상": h2_target,
                "3호_공제대상": h3_target,
                "4호_공제대상": h4_target,
                "공제율": {"1호": 0.15, "2호": 0.15,
                           "3호": 미숙아율 if 미숙아율 else None,
                           "4호": 난임율 if 난임율 else None},
            },
            "교육비": {"사람별": 사람별, "공제대상_합계": 교육비대상합계},
            "기본공제대상자": 기본공제대상자,
        },
        "판단": 판단,
        "근거": "소득세법 제59조의4①②③⑨, 제61조①, 시행령 제118조의4·제118조의5·제118조의6·제119조의3",
    }

