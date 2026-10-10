"""소득세·원천세 계산(2016~2026 귀속 연도표, 기본 2025 귀속) — 국세청 연말정산·중소기업 취업자 감면 안내 예시로 검증. 작성 Mia(윤승미)
플레이북: knowledge/14_소득세_원천세_연말정산_조사포인트.md. 2026 귀속 변경분은 표 추가 후 적용.
"""
import json
import math
import os

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

    # 쟁점 부착 (issues.json에서 읽음, 하드코딩 금지 — SPEC r1d §1)
    _issues = _load_issues().get("nonresident_withholding", [])
    issues: list[dict] = []
    for it in _issues:
        ok = True
        cond = it["조건"]
        if cond.startswith('income_kind="사용료"'): ok = income_kind == "사용료"
        elif cond.startswith('income_kind="이자"'): ok = income_kind == "이자"
        elif cond.startswith('income_kind="인적용역"'): ok = income_kind == "인적용역"
        elif cond.startswith('treaty_rate 주어짐'):
            ok = treaty_rate is not None
            if cond.startswith('income_kind="사용료" and treaty_rate'):
                ok = ok and income_kind == "사용료"
        elif cond.startswith('treaty_rate 주어짐 (모든 소득)'):
            ok = treaty_rate is not None
        elif cond.startswith('income_kind="이자" and recipient가 지배주주'):
            ok = income_kind == "이자" and related_party
        if ok:
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
