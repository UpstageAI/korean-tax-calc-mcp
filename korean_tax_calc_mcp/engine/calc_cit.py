"""법인세 세무조정 계산 — 국세청 「법인세 신고안내」 계산 예시로 검증. 작성 Mia(윤승미)
한도·세율은 사업연도별 표(YEAR)에서 고른다(사실관계 시점의 법 적용). 표에 없는 연도는 법령 확인 후 추가.
플레이북: knowledge/07_법인세_신고안내_조사포인트.md
"""
import math
from datetime import date

from .calc import won

# 키 = 사업연도(개시일이 속하는 연도). 값은 모두 법제처 efYd=그해1231 원문 + 개정 부칙 적용시기 대조(2026-09-30, knowledge/16 §법인 연도표).
_T_OLD = [(200_000_000, 0.10), (20_000_000_000, 0.20), (math.inf, 0.22)]                                   # 제55조 2016·2017
_T_25 = [(200_000_000, 0.10), (20_000_000_000, 0.20), (300_000_000_000, 0.22), (math.inf, 0.25)]           # 2018~2022(법률 15222 부칙§2)
_T_24 = [(200_000_000, 0.09), (20_000_000_000, 0.19), (300_000_000_000, 0.21), (math.inf, 0.24)]           # 2023~(법률 19193 부칙§18)
_T_26 = [(200_000_000, 0.10), (20_000_000_000, 0.20), (300_000_000_000, 0.22), (math.inf, 0.25)]             # 2026.1.1. 이후 개시 (법률 21043, 2025.12.23. 개정, 부칙§3 — 법인세법 제55조①)
_REV_OLD = [(10_000_000_000, 0.002), (50_000_000_000, 0.001), (math.inf, 0.0003)]                          # 제25조 2019까지
_REV_NEW = [(10_000_000_000, 0.003), (50_000_000_000, 0.002), (math.inf, 0.0003)]                          # 2020~(법률 16833 부칙§2)
_REV_2020 = [(10_000_000_000, 0.0035), (50_000_000_000, 0.0025), (math.inf, 0.0006)]                       # 조특법 제136조④ 2020 지출분
_MIN_TAX = {"중소": 0.07, "유예1_3": 0.08, "유예4_5": 0.09,
            "일반": [(10_000_000_000, 0.10), (100_000_000_000, 0.12), (math.inf, 0.17)]}                   # 조특법 제132조① 2016~2025 동일


def _year(y):
    """사업연도 y의 표. 각 값의 조문·부칙 근거는 knowledge/16 '법인 연도표' 표."""
    d = {"세율": _T_OLD if y <= 2017 else _T_25 if y <= 2022 else _T_24 if y <= 2025 else _T_26,
         "접대비_명칭": "접대비" if y <= 2023 else "기업업무추진비",                       # 법률 19193 부칙§1 1호(제25조 2024.1.1.)
         "접대비_기본": {"중소": 24_000_000 if y <= 2019 else 36_000_000, "일반": 12_000_000},  # 2016 제25조① 괄호, 2017·2018 조특§136①, 2020~ 법률 16833
         "접대비_수입": _REV_2020 if y == 2020 else (_REV_OLD if y <= 2019 else _REV_NEW),
         "접대비_임대법인_50": y >= 2017,                                                    # 제25조①(2016.12.20.) 법률 14386 부칙§2
         "문화접대비_비율": 0.20,                                                            # 조특§136③ 각 연도 일몰 연장본
         "적격증빙_기준": 10_000 if y <= 2020 else 30_000, "적격증빙_기준_경조금": 200_000,   # 영§41① (영 31443 부칙§9: 2021.1.1. 이후 지출분)
         "승용차_상각한도": 8_000_000,                                                       # 제27조의2③
         "승용차_유지한도": 10_000_000 if y <= 2019 else 15_000_000,                         # 영§50조의2⑦ (영 30396 부칙§2: 2020.1.1. 이후 개시)
         "최저한세": _MIN_TAX,
         "기부금_명칭": ("법정", "지정") if y <= 2022 else ("특례", "일반"),                  # 법률 19193
         "기부금_이월기간": 5 if y <= 2017 else 10,                                          # 제24조⑤ 법률 16008 부칙§4②(2019.1.1. 이후 신고분)
         "기부금_이월우선": y >= 2019,                                                       # 제24조⑥ 법률 16833 부칙§4(2020.1.1. 이후 신고분)
         "기부금_사회적기업_20": y >= 2018,                                                  # 제24조② 표(법률 16008 부칙§4①, 2019.1.1. 이후 신고분)
         "기부금_결손금한도": y >= 2021,                                                     # 제24조②2호(법률 17652 부칙§6: 2021.1.1. 이후 개시 사업연도 지출분)
         }
    if y == 2020: d["접대비_수입_법"] = _REV_NEW                                             # 조특§136⑤ 일할 안분용(법 제25조④2호 표)
    if y >= 2017:                                                                            # 제27조의2⑤(법률 14386), 영§50조의2⑮(영 27828)
        d["승용차_상각한도_임대"] = 4_000_000; d["승용차_유지한도_임대"] = 5_000_000
    if y >= 2023: d["전통시장_비율"] = 0.10                                                  # 조특§136⑥ 법률 19936 부칙§35: 2024.1.1. 이후 신고분 → 2023 사업연도 신고부터
    if y >= 2024: d["승용차_번호판요건"] = True                                               # 영§50조의2④ 단서(영 34266 부칙§7: 2024.1.1. 이후 지출분)
    if y == 2025: d["세율_소규모"] = [(20_000_000_000, 0.19), (300_000_000_000, 0.21), (math.inf, 0.24)]  # 제55조①2호, 법률 20613 부칙§5 (2억 이하 구간은 기본세율 10% 적용, 표에는 2억 초과만 기재)
    if y >= 2026: d["세율_소규모"] = [(200_000_000, 0.10), (20_000_000_000, 0.19), (300_000_000_000, 0.21), (math.inf, 0.24)]  # 제55조①2호, 법률 21043 부칙§3 (2026.1.1. 이후 개시), 기본세율보다 1%p 낮음
    return d


YEAR = {y: _year(y) for y in range(2016, 2027)}  # 2016~2026 (2026: 법률 21043, 2025.12.23. 개정 법인세법 제55조)


def _tier(amount, tiers):
    out, prev = 0.0, 0
    for cap, r in tiers:
        if amount > prev: out += (min(amount, cap) - prev) * r
        prev = cap
    return out


def months_in(start, end):
    """역에 따른 월수, 1월 미만 일수는 1월."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    n, y, m = 0, a.year, a.month
    while True:
        n += 1; m += 1
        if m > 12: y, m = y + 1, 1
        try: nxt = date(y, m, a.day)
        except ValueError: nxt = date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)
        if nxt > b: return n


def corp_tax(base, year, months=12, small_rental=False):
    """법인세 산출세액(제55조). 1년 미만: {(과세표준×12/월수)×세율}×월수/12. small_rental=제60조의2①1호 법인."""
    tiers = YEAR[year]["세율_소규모" if small_rental and "세율_소규모" in YEAR[year] else "세율"]
    return won(_tier(base * 12 / months, tiers) * months / 12)


def entertain(year, sme, general_revenue, related_revenue, expensed, asset_part=0, no_card_over=0, culture=0, months=12,
              market=0, rental_corp=False, gov_invested=False, days_2020=None):
    """접대비 한도초과(법인세법 제25조). expensed=비용 계상 접대비(증빙 미수취분 포함), asset_part=자산(건설가계정 등) 계상분,
    no_card_over=1회 기준금액(YEAR 적격증빙_기준, receipt_disallowed) 초과 적격증빙 미수취분(직부인, 기타사외유출), culture=문화접대비.
    days_2020=(2020년에 속하는 일수, 사업연도 일수): 2020년이 2개 이상 사업연도에 걸친 법인의 수입금액별 한도 일할 안분(조특법 제136조⑤)."""
    y = YEAR[year]
    base = y["접대비_기본"]["중소" if sme else "일반"] * months / 12
    def rev_limit(tiers):
        g = _tier(general_revenue, tiers)
        return g + (_tier(general_revenue + related_revenue, tiers) - g) * 0.10  # 특수관계 수입금액 10%
    if days_2020:
        d20, dt = days_2020
        statute = y.get("접대비_수입_법", y["접대비_수입"])
        rev = rev_limit(_REV_2020) * d20 / dt + rev_limit(statute) * (dt - d20) / dt
    else:
        rev = rev_limit(y["접대비_수입"])
    general_limit = base + rev
    if rental_corp and y.get("접대비_임대법인_50", True): general_limit *= 0.5      # 제25조⑤(2017 이후 개시 사업연도) 부동산임대 등 요건 법인
    if gov_invested: general_limit *= 0.7     # 조특법 제136조② 정부출자기관 등
    culture_limit = min(culture, general_limit * y["문화접대비_비율"])
    market_limit = min(market, general_limit * y.get("전통시장_비율", 0))  # 조특법 제136조⑥(2024~)
    limit = general_limit + culture_limit + market_limit
    total = expensed + asset_part - no_card_over
    over = max(0, total - limit)
    return {"직부인(기타사외유출)": no_card_over, "세무상 접대비": won(total), "일반한도": won(general_limit), "문화한도": won(culture_limit), "전통시장한도": won(market_limit),
            "한도": won(limit), "한도초과(기타사외유출)": won(over),
            "자산감액": won(max(0, over - (expensed - no_card_over)))}


def receipt_disallowed(year, items):
    """적격증빙 미수취 직부인(법인세법 제25조②, 영 제41조①): items=[(1회 지출액, 적격증빙 여부, 경조금 여부)].
    기준금액 초과 + 적격증빙 없음 → 손금불산입. 기준: 경조금 20만원, 그 외 2020 이전 1만원·2021 이후 3만원(2021.1.1. 이후 지출분)."""
    y = YEAR[year]
    return sum(a for a, ok, gift in items
               if not ok and a > (y["적격증빙_기준_경조금"] if gift else y["적격증빙_기준"]))


def jeoksu(movements, year_end):
    """movements=[(날짜, 증감액)] → 잔액×일수 합(일별 잔액, 기말 포함)."""
    mv = sorted(movements); total, bal = 0, 0
    for i, (d, amt) in enumerate(mv):
        bal += amt
        nxt = date.fromisoformat(mv[i + 1][0]) if i + 1 < len(mv) else date.fromordinal(date.fromisoformat(year_end).toordinal() + 1)
        total += bal * (nxt - date.fromisoformat(d)).days
    return total


def nonbusiness_interest(loans, unknown_creditor=None):
    """업무무관자산 등 관련 지급이자(법인세법 제28조①4호). loans=[(이자, 차입금적수)], unknown_creditor=(이자, 적수, 원천세)는 먼저 부인.
    → 지급이자 × min(1, 업무무관 적수 합 ÷ 차입금 적수)"""
    out = {}
    if unknown_creditor:
        i, _, wh = unknown_creditor
        out["채권자불분명 사채이자(상여)"] = i - wh; out["원천세(기타사외유출)"] = wh
    def f(unrelated_jeoksu):
        interest = sum(i for i, _ in loans); borrow = sum(j for _, j in loans)
        return {**out, "지급이자": interest, "차입금적수": borrow, "업무무관적수": unrelated_jeoksu,
                "손금불산입(기타사외유출)": interest * min(unrelated_jeoksu, borrow) // borrow}  # 원 미만 절사(책자 233쪽)
    return f


def depreciation(assets):
    """개별 자산별 시부인(법인세법 제23조). assets={자산: (상각범위액, 회사계상액)} — 자산 간 상계 안 함."""
    rows = {k: c - r for k, (r, c) in assets.items()}
    return {"자산별": rows, "손금불산입(유보)": sum(v for v in rows.values() if v > 0)}


def depreciation_recover(prior_disallowed, limit, booked):
    """전기 부인누계는 당기 시인부족액 한도로 추인(시행령 제32조①)."""
    short = max(0, limit - booked)
    return {"추인(△유보)": min(prior_disallowed, short), "차기이월": prior_disallowed - min(prior_disallowed, short)}


def business_car(year, upkeep, depreciation_amt, booked_depreciation, log_kept, business_ratio=None, months=12, rental_corp=False,
                 plate_ok=True):
    """업무용승용차(법인세법 제27조의2, 2016.1.1. 이후 개시 사업연도). 감가상각 5년 정액 강제.
    운행기록 작성: 업무사용비율 그대로. 미작성: min(1, 기준 ÷ 총비용) — 기준 2019 이전 1,000만·2020 이후 1,500만, 임대법인(2017~) 500만.
    plate_ok=False: 2024.1.1. 이후 지출분은 전용번호판 미부착 시 업무사용금액 0원(영 제50조의2④ 단서)."""
    y = YEAR[year]
    total = upkeep + depreciation_amt
    cap_key = "승용차_유지한도_임대" if rental_corp and "승용차_유지한도_임대" in y else "승용차_유지한도"
    ratio = business_ratio if log_kept else min(1, y[cap_key] * months / 12 / total)
    if not plate_ok and y.get("승용차_번호판요건"): ratio = 0
    out = {"업무사용비율": ratio, "감가상각 미계상 손금산입(유보)": depreciation_amt - booked_depreciation}
    out["유지비 손금불산입(상여)"] = won(upkeep * (1 - ratio))
    out["감가상각 사적사용 손금불산입(상여)"] = won(depreciation_amt * (1 - ratio))
    biz_dep = depreciation_amt * ratio
    cap = y["승용차_상각한도_임대" if rental_corp and "승용차_상각한도_임대" in y else "승용차_상각한도"]
    out["감가상각 한도초과(유보)"] = won(biz_dep - min(biz_dep, cap * months / 12))
    return out


def pension(estimate, book_reserve, reserve_disallowed, deposits_end, prior_reserve, prior_disallowed, withdrawn, booked, dc_reserve=0):
    """퇴직연금부담금 조정(시행령 제44조의2④, 별지 제33호). 신고조정 기준.
    ⑥ 누적한도 = 추계액 − (장부 충당금 − DC 설정분 − 충당금 부인누계)
    ⑦ 이미 손금산입 = 기초 충당금 등 − 부인누계 − 기중 수령·해약
    ⑧ 한도 = ⑥ − ⑦, ⑨ 손금산입대상 = 기말 예치금 − ⑦, ⑩ = min(⑧, ⑨), ⑫ = ⑩ − 회사계상"""
    cum = estimate - (book_reserve - dc_reserve - reserve_disallowed)
    already = prior_reserve - prior_disallowed - withdrawn
    limit, target = cum - already, deposits_end - already
    allowed = max(0, min(limit, target))
    return {"누적한도": cum, "이미손금산입": already, "한도": limit, "손금산입대상": target, "손금산입범위": allowed,
            "조정": allowed - booked,  # 음수 = 손금불산입(유보), 양수 = 추가 손금산입(△유보, 신고조정)
            }


def bad_debt_allowance(receivables, loss_rate, set_amount, prior_disallowed=0):
    """대손충당금 한도(법인세법 제34조, 시행령 제61조②): 채권잔액 × max(1%, 대손실적률). 한도초과 손금불산입(유보).
    전기 한도초과액은 당기 충당금 환입으로 손금 추인(△유보, 총액법 가정)."""
    limit = won(receivables * max(0.01, loss_rate))
    return {"한도": limit, "한도초과(유보)": max(0, set_amount - limit), "전기초과 추인(△유보)": prior_disallowed}


def donation(base_income, carried_loss, special, general, special_carry=0, general_carry=0, sme=True, social_enterprise=False,
             year=None):
    """기부금 손금산입 한도(법인세법 제24조). base_income=기준소득금액(기부금 손금산입 전 소득, 양도손익 제외).
    year=None(종전 호출): 결손금 차감 비중소 기준소득 80% 한도, 이월분 먼저, 사회적기업 20%.
    year 지정: 연도표 — 결손금 차감 한도는 2021 이후 개시 사업연도만(제13조 한도율 60%/80%, 그 전은 전액 차감),
    이월분 먼저 공제는 2019 사업연도부터(그 전은 당기분 먼저, 남은 한도에서 이월분), 사회적기업 20%는 2018 사업연도부터."""
    if year is None:
        cap_ratio, carry_first, social_ok = (1.0 if sme else 0.8), True, True
    else:
        y = YEAR[year]
        cap_ratio = loss_limit_ratio(year, sme) if y["기부금_결손금한도"] else 1.0
        carry_first, social_ok = y["기부금_이월우선"], y["기부금_사회적기업_20"]
    loss = min(carried_loss, base_income * cap_ratio)

    def use(carry, cur, lim):
        if carry_first:
            c = min(carry, lim); return c, min(cur, lim - c)
        u = min(cur, lim); return min(carry, lim - u), u
    sp_limit = max(0, (base_income - loss) * 0.5)
    sp_carry_used, sp_used = use(special_carry, special, sp_limit)
    gen_limit = max(0, (base_income - loss - sp_carry_used - sp_used) * (0.2 if social_enterprise and social_ok else 0.1))
    gen_carry_used, gen_used = use(general_carry, general, gen_limit)
    return {"특례한도": won(sp_limit), "일반한도": won(gen_limit),
            "이월분 손금산입": won(sp_carry_used + gen_carry_used),
            "한도초과(기타사외유출)": won(special - sp_used + general - gen_used),
            "차기이월": {"특례": won(special - sp_used + special_carry - sp_carry_used), "일반": won(general - gen_used + general_carry - gen_carry_used)}}


def min_tax(base_before_incentives, sme=True, grace_year=0, year=None):
    """최저한세(조특법 제132조①): 감면 전 과세표준 × 중소 7%(졸업 후 1~3년 8%, 4~5년 9%), 일반 100억 이하 10%, 1천억 이하 12%, 초과 17%.
    year 지정 시 연도표(YEAR[year]['최저한세']) 사용 — 2016~2025 원문 동일. year=None은 같은 값(종전 호출 유지)."""
    if year is not None: require_year(year)
    t = _MIN_TAX if year is None else YEAR[year]["최저한세"]
    if sme: return won(base_before_incentives * t["중소"])
    if grace_year: return won(base_before_incentives * (t["유예1_3"] if grace_year <= 3 else t["유예4_5"]))
    return won(_tier(base_before_incentives, t["일반"]))


def apply_min_tax(calc_tax, reductions_subject, reductions_exempt, min_tax_amt):
    """감면 적용 후 세액이 최저한세 미달 시 최저한세 대상 감면을 배제. → (인정 감면, 배제액)."""
    after = calc_tax - reductions_subject
    cut = max(0, min_tax_amt - after)
    allowed = max(0, reductions_subject - cut)
    return {"최저한세대상 감면 인정": allowed, "배제": reductions_subject - allowed,
            "결정세액": max(0, calc_tax - allowed - reductions_exempt)}


def deemed_interest_check(rate_market, rate_charged, balance_jeoksu, days=365):
    """가지급금 인정이자(시행령 제89조③, 제88조③): 시가(가중평균차입이자율 원칙, 예외 당좌대출이자율)와의 차액이
    3억 이상 또는 시가의 5% 이상이면 부당행위 → 차액 익금산입."""
    market = balance_jeoksu * rate_market / days; charged = balance_jeoksu * rate_charged / days
    diff = market - charged
    hit = diff >= 300_000_000 or (market and diff >= market * 0.05)
    return {"시가이자": won(market), "수령이자": won(charged), "차액": won(diff), "부당행위": bool(hit), "익금산입": won(diff) if hit else 0}


def loss_limit_ratio(year, sme):
    """이월결손금 공제 한도(법인세법 제13조① 단서, 사업연도 개시일 기준): 중소기업 등 100%.
    그 외 — 2017 이전 80%, 2018 70%, 2019~2022 60%, 2023 이후 80% (법제처 efYd 2016~2025 원문 대조, 2026-09-30)."""
    if sme: return 1.0
    if year <= 2017: return 0.8
    if year == 2018: return 0.7
    if year <= 2022: return 0.6
    return 0.8


def late_payment_penalty(tax, due, until):
    """납부지연가산세 일수분(국세기본법 제47조의4, 영 제27조의4): 1일 10만분의 25 → 2022.2.15.부터 10만분의 22.
    due=법정납부기한, until=납부일·고지일. 기간을 나눠 각각의 율 적용."""
    from datetime import date as _d, timedelta
    a, b = _d.fromisoformat(due) + timedelta(days=1), _d.fromisoformat(until)
    cut = _d(2022, 2, 15)
    d1 = max(0, (min(b, cut - timedelta(days=1)) - a).days + 1) if a < cut else 0
    d2 = max(0, (b - max(a, cut)).days + 1)
    return {"일수": d1 + d2, "0.025%일수": d1, "0.022%일수": d2, "가산세": int(round(tax * (0.00025 * d1 + 0.00022 * d2)))}


class NoYearTable(Exception):
    pass


def require_year(year):
    if year not in YEAR:
        raise NoYearTable(f"{year} 사업연도 세율·한도표 없음 — 법제처 efYd={year}1231 원문 대조 후 calc_cit.YEAR에 추가해야 계산함(추정 계산 안 함)")


QUALIFIED = {"신용카드", "직불카드", "외국신용카드", "기명식선불카드", "직불전자지급수단", "기명식선불전자지급수단", "기명식전자화폐",
             "현금영수증", "세금계산서", "계산서", "매입자발행세금계산서", "매입자발행계산서", "원천징수영수증"}
CARDLIKE = {"신용카드", "직불카드", "외국신용카드", "기명식선불카드", "직불전자지급수단", "기명식선불전자지급수단", "기명식전자화폐"}


def receipt_check(items):
    """기업업무추진비 적격증빙 건별 판정(법인세법 제25조②③, 영 제41조, 지출일 기준).
    items=[{지출일, 금액, 증빙, 법인명의(카드류), 가맹점일치(카드류), 경조금, 국외현금불가피, 농어민송금명세제출, 미등록자용역(원천징수영수증)}]
    - 기준금액(영 §41①): 경조금 20만원, 그 외 3만원 — 2021.1.1. 전 지출분 1만원(영 31443 부칙§9). 초과분만 적격증빙 요구.
    - 신용카드등은 법인 명의(영 §41⑥), 다른 가맹점 명의 매출전표는 불인정(법 §25③, 영 §41⑤).
    - 원천징수영수증은 사업자등록 안 한 자의 용역만(영 §41④). 간이영수증·거래명세서·없음은 불인정.
    - 예외(법 §25② 단서, 영 §41②): 국외 현금 외 수단 없음, 농어민 직접 공급 + 금융회사 지급 + 송금명세서 제출.
    → {'부인합계', '건별': [{지출일, 금액, 판정, 근거}]}"""
    out, total = [], 0
    for it in items:
        amt, day = it["금액"], it["지출일"]
        base = 200_000 if it.get("경조금") else (10_000 if day < "2021-01-01" else 30_000)
        kind = it.get("증빙", "없음")
        if amt <= base:
            r, why = "인정", f"1회 {amt:,}원 ≤ 기준 {base:,}원(영 §41①)"
        elif it.get("국외현금불가피"):
            r, why = "인정", "국외 현금 외 지출수단 없음(영 §41②1호)"
        elif it.get("농어민송금명세제출"):
            r, why = "인정", "농어민 직접 공급·금융회사 지급·송금명세서(영 §41②2호)"
        elif kind not in QUALIFIED:
            r, why = "부인", f"{kind} — 적격증빙 아님(법 §25②)"
        elif kind in CARDLIKE and it.get("법인명의") is False:
            r, why = "부인", "임직원 개인 명의 카드(영 §41⑥ 법인 명의만)"
        elif kind in CARDLIKE and it.get("가맹점일치") is False:
            r, why = "부인", "실제 공급자와 다른 가맹점 명의 매출전표(법 §25③, 영 §41⑤)"
        elif kind == "원천징수영수증" and not it.get("미등록자용역"):
            r, why = "부인", "원천징수영수증은 사업자등록 없는 자의 용역만(영 §41④)"
        else:
            r, why = "인정", f"{kind}(법 §25②)"
        if r == "부인": total += amt
        out.append({"지출일": day, "금액": amt, "증빙": kind, "판정": r, "근거": why})
    return {"부인합계": total, "건별": out}


def thin_capitalization(equity, borrowings, total_interest, ratio=2, year=None):
    """과소자본 손금불산입(국제조세조정에 관한 법률 제22조). 국외지배주주 출자금액 대비 차입금 배수가
    기준비율(기본 2배, 금융업 등은 배수 선택)을 초과하는 경우 초과 차입금에 상당하는 지급이자를 손금불산입.
    borrowings = 직접차입금 + 특수관계인 차입금 + 지급보증으로 인한 차입금 합계.
    → 한도 차입금, 초과 차입금, 손금불산입 이자, 처분(배당/기타사외유출)."""
    limit = equity * ratio
    excess = max(0, borrowings - limit)
    disallowed = int(total_interest * excess / borrowings) if borrowings else 0
    # 직접차입금이 별도 주어지지 않으면 전체 손금불산입을 배당으로 처분(가장 보수적 가정)
    return {
        "출자금액": equity,
        "총차입금": borrowings,
        "적용배수": ratio,
        "한도차입금": limit,
        "초과차입금": excess,
        "지급이자": total_interest,
        "손금불산입 이자": disallowed,
        "처분": "배당" if disallowed else "해당없음",
        "근거": "국제조세조정에 관한 법률 제22조(과소자본 손금불산입), 동법 시행령",
    }


def depreciation_adjustment(year, method, acquisition_cost, booked_depreciation,
                            useful_life=None, rate=None, asset_class=None,
                            accumulated_dep_begin=None, accumulated_dep_end=None,
                            expensed_capex=0, repair_total=None, periodic_repair=False,
                            prior_book_value=None, prior_deemed_capex=0, prior_disallowed=0,
                            in_service_date=None, fy_start=None, fy_end=None, tax_exempt=False):
    """법인세 감가상각 시부인(법인세법 제23조, 시행령 제26조·제28조·제30조·제31조·제32조)."""
    from .. import vocab

    # ── 연도별 판단 규칙 ──────────────────────────────────────────────
    rule_data = vocab.rule("감가상각_시부인", year)
    상각률표 = rule_data["상각률표"]
    무신고_상각방법 = rule_data["무신고_상각방법"]
    정액법만_허용 = rule_data["정액법만_허용"]
    정률법_잔존가액_비율 = rule_data["정률법_잔존가액_비율"]
    상각종료_비망가액 = rule_data["상각종료_비망가액"]
    수선비_장부가액_비율 = rule_data["수선비_장부가액_비율"]
    소액수선비_기준 = rule_data["소액수선비_기준"]

    판단_목록 = []

    # ── 사업연도 기간 ──────────────────────────────────────────────────
    fy_s = fy_start or f"{year}-01-01"
    fy_e = fy_end or f"{year}-12-31"
    총월수 = months_in(fy_s, fy_e)
    if 총월수 != 12:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"사업연도 월수가 {총월수}개월 — 12개월만 지원"],
                "필요 입력": ["사업연도 12개월 확인"]}

    # ── 상각 방법 결정 (무신고) ──────────────────────────────────────
    실제방법 = method
    if method == "무신고":
        if asset_class is None:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["무신고 시 asset_class 필요 (영 제26조④)"],
                    "필요 입력": ["asset_class"]}
        실제방법 = 무신고_상각방법[asset_class]
        판단_목록.append({"항목": "상각방법(무신고)", "결론": f"무신고 → {asset_class} 법정방법 {실제방법} 적용",
                          "근거": "법인세법 시행령 제26조④", "이유": f"자산 구분 '{asset_class}'의 무신고 법정 상각방법"})
    else:
        판단_목록.append({"항목": "상각방법", "결론": f"신고방법 {method} 적용",
                          "근거": "법인세법 제23조①", "이유": "신고한 상각방법"})

    # ── 상각률 결정 ─────────────────────────────────────────────────
    표상각률 = None
    useful_life_key = str(useful_life) if useful_life is not None else None
    if useful_life is not None:
        if useful_life_key not in 상각률표:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"내용연수 {useful_life}년 — 별표4 범위(2~60년) 벗어남"],
                    "필요 입력": ["useful_life (2~60년)"]}
        표상각률 = 상각률표[useful_life_key][실제방법]
        판단_목록.append({"항목": "상각률", "결론": f"별표4 {useful_life}년 {실제방법} 상각률 {표상각률:.4f}",
                          "근거": "법인세법 시행규칙 별표4", "이유": f"내용연수 {useful_life}년"})

    if rate is not None:
        if useful_life is not None and 표상각률 is not None:
            if abs(rate - 표상각률) > 1e-9:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"rate({rate})와 별표4 상각률({표상각률}) 불일치"],
                        "필요 입력": ["rate 또는 useful_life 하나만으로 계산"]}
            판단_목록.append({"항목": "상각률(직접 입력)", "결론": f"직접 입력 rate={rate} ≅ 별표4 {표상각률} (일치 확인)",
                              "근거": "법인세법 시행규칙 별표4", "이유": "useful_life와 rate 모두 주어짐"})
        최종상각률 = rate
    elif 표상각률 is not None:
        최종상각률 = 표상각률
    else:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["useful_life 또는 rate 필요 — 상각률 미확정"],
                "필요 입력": ["useful_life 또는 rate"]}

    # 건축물·무형자산 + 정률법 → 오류 (영 제26조①, 어휘 정액법만_허용)
    if method in ("정률법", "무신고") and asset_class in 정액법만_허용:
        실제방법_확인 = 실제방법 if method == "무신고" else method
        if 실제방법_확인 == "정률법":
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"자산 구분 '{asset_class}'는 정액법만 허용(법인세법 시행령 제26조①, 어휘 감가상각_시부인.정액법만_허용)"],
                    "필요 입력": ["method='정액법'"]}

    # ── 기초/기말 감가상각누계액 ─────────────────────────────────────
    기초누계 = accumulated_dep_begin
    기말누계 = accumulated_dep_end
    if 기초누계 is None and 기말누계 is not None:
        기초누계 = 기말누계 - booked_depreciation
    elif 기초누계 is not None and 기말누계 is None:
        기말누계 = 기초누계 + booked_depreciation
    elif 기초누계 is not None and 기말누계 is not None:
        if 기초누계 + booked_depreciation != 기말누계:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"기초 누계({기초누계}) + 당기 감가상각비({booked_depreciation}) ≠ 기말 누계({기말누계})"],
                    "필요 입력": ["accumulated_dep_begin 또는 accumulated_dep_end — 기초 또는 기말 감가상각누계액 (둘 다 주면 일치해야 함)"]}
    else:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["accumulated_dep_begin 또는 accumulated_dep_end 필요"],
                "필요 입력": ["accumulated_dep_begin 또는 accumulated_dep_end — 기초 또는 기말 감가상각누계액"]}

    # ── 사용월수 ───────────────────────────────────────────────────
    사용월수 = 총월수
    if in_service_date is not None:
        사용개시일 = in_service_date if in_service_date > fy_s else fy_s
        사용월수 = months_in(사용개시일, fy_e)
        판단_목록.append({"항목": "사용월수(월할)", "결론": f"{사용월수}개월 (사용개시일 {사용개시일} ~ 사업연도 종료 {fy_e})",
                          "근거": "법인세법 시행령 제26조⑨·제28조④", "이유": "사업연도 중 취득·사용개시"})

    # ── 즉시상각의제 여부 판단 (영 제31조③) ──────────────────────
    당기즉시상각의제 = expensed_capex
    if repair_total is None:
        repair_total = expensed_capex

    소액기준충족 = repair_total < 소액수선비_기준
    장부가액5퍼센트충족 = (prior_book_value is not None
                            and prior_book_value > 0
                            and repair_total < prior_book_value * 수선비_장부가액_비율)
    주기적수선충족 = periodic_repair  # 3년 미만 주기적 수선

    # 수선비 총액이 소액수선비 기준 이상이고 주기적 수선도 아니며
    #   prior_book_value가 없으면 5% 기준을 판단할 수 없으므로 error
    if not 소액기준충족 and not 주기적수선충족 and prior_book_value is None:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"수선비 총액 {repair_total:,}원 >= 소액수선비 기준 {소액수선비_기준:,}원, "
                         f"prior_book_value 없음 — 수선비 5% 기준 판단 불가 (영 제31조③2호)"],
                "필요 입력": ["prior_book_value — 직전 사업연도말 장부가액(수선비 5% 기준)"]}

    # 영 제31조③: 아래 중 하나라도 해당하면 즉시상각의제 아님(비용 처리 지출 그대로 손금)
    면제사유 = []
    if 소액기준충족:
        면제사유.append(f"수선비 총액 {repair_total:,}원 < 소액수선비 기준 {소액수선비_기준:,}원 (영 제31조③1호)")
    if prior_book_value is not None and prior_book_value > 0 and 장부가액5퍼센트충족:
        면제사유.append(f"수선비 총액 {repair_total:,}원 < 직전 장부가액 {prior_book_value:,}원의 5%({prior_book_value * 수선비_장부가액_비율:,.0f}원) 미만 (영 제31조③2호)")
    if 주기적수선충족:
        면제사유.append("3년 미만 주기적 수선 (영 제31조③3호)")

    if 면제사유:
        당기즉시상각의제 = 0
        판단_목록.append({"항목": "즉시상각의제(영 제31조③)", "결론": "즉시상각의제 아님(비용 처리 지출 그대로 손금)",
                          "근거": "법인세법 시행령 제31조③", "이유": " · ".join(면제사유)})
    elif expensed_capex > 0:
        판단_목록.append({"항목": "즉시상각의제(영 제31조③)", "결론": f"즉시상각의제 해당 → 당기 즉시상각의제액 {당기즉시상각의제:,}원",
                          "근거": "법인세법 시행령 제31조②", "이유": "비용 처리한 자본적 지출은 당기 감가상각비에 합산"})

    # ── 세무상 취득가액 / 기초 미상각잔액 ──────────────────────────
    세무상취득가액 = acquisition_cost + prior_deemed_capex + 당기즉시상각의제

    # 기초 세무상 미상각잔액 (정률법)
    기초세무상미상각 = acquisition_cost - 기초누계 + prior_disallowed + 당기즉시상각의제

    # ── 상각범위액 ─────────────────────────────────────────────────
    월할계수 = 사용월수 / 12.0

    if 실제방법 == "정액법":
        범위액 = max(0, 세무상취득가액 * 최종상각률 * 월할계수)
    else:  # 정률법 — 영 제26조⑥⑦: 잔존가액 5%를 미리 빼지 않음
        비망가액 = min(acquisition_cost * 정률법_잔존가액_비율, 1000)
        # 기본 상각범위액 = 기초 미상각잔액 × 상각률 × 월할 (잔존가액 차감 없음)
        기본범위액 = max(0, 기초세무상미상각 * 최종상각률 * 월할계수)
        # 미상각잔액 − 기본범위액 ≤ 취득가액×5% 가 처음 되는 해 → 잔존가액(5%) 가산 (영 제26조⑥)
        상각후잔액 = 기초세무상미상각 - 기본범위액
        # 미상각잔액 − 기본범위액 ≤ 취득가액×5% 이면 잔존가액(5%) 가산 (영 제26조⑥)
        if 상각후잔액 <= acquisition_cost * 정률법_잔존가액_비율:
            기본범위액 += acquisition_cost * 정률법_잔존가액_비율
        # 상각범위액 상한 = 미상각잔액 − 비망가액 (영 제26조⑦)
        상한 = 기초세무상미상각 - 비망가액
        범위액 = max(0, min(기본범위액, 상한))

    범위액 = int(범위액)  # 원 미만 버림

    # ── 회사계상액 ────────────────────────────────────────────────
    회사계상액 = booked_depreciation + 당기즉시상각의제

    # ── 상각부인액 / 시인부족액 ───────────────────────────────────
    상각부인액 = max(0, 회사계상액 - 범위액)
    시인부족액 = max(0, 범위액 - 회사계상액)

    # ── 전기부인액 추인 (영 제32조①) ─────────────────────────────
    전기부인추인 = 0
    if 시인부족액 > 0 and prior_disallowed > 0:
        전기부인추인 = min(시인부족액, prior_disallowed)

    # 추인 후 남은 시인부족액
    추인후시인부족 = 시인부족액 - 전기부인추인

    # ── 감가상각의제 (영 제30조, 감면법인) ───────────────────────
    감가상각의제액 = 0
    if tax_exempt and 추인후시인부족 > 0:
        감가상각의제액 = 추인후시인부족

    소멸시인부족 = 추인후시인부족 - 감가상각의제액

    # ── 기말 상각부인누계액 ───────────────────────────────────────
    # formula: prior_disallowed + 상각부인액 − 전기부인추인 − 감가상각의제 (max(0, …) 자르기 금지)
    기말부인누계 = prior_disallowed + 상각부인액 - 전기부인추인 - 감가상각의제액

    # ── 세무상 미상각잔액 (명세서 정의) ───────────────────────────
    # 기말_상각부인누계액 = prior_disallowed + 상각부인액 − 전기부인추인 − 감가상각의제 (자르기 금지)
    기말상각부인누계 = prior_disallowed + 상각부인액 - 전기부인추인 - 감가상각의제액
    세무상미상각잔액 = acquisition_cost - 기말누계 + 기말상각부인누계
    # 원 미만 버림, 음수면 0
    세무상미상각잔액 = max(0, int(세무상미상각잔액))

    # ── 세무조정 구성 ────────────────────────────────────────────
    settlements = []
    if 상각부인액 > 0:
        settlements.append({"구분": "상각부인액", "금액": 상각부인액, "소득처분": "유보"})
    if 전기부인추인 > 0:
        settlements.append({"구분": "전기 상각부인액 추인", "금액": 전기부인추인, "소득처분": "△유보"})
    if 감가상각의제액 > 0:
        settlements.append({"구분": "감가상각의제", "금액": 감가상각의제액, "소득처분": "△유보"})

    처분별 = {}
    for s in settlements:
        처분별[s["소득처분"]] = 처분별.get(s["소득처분"], 0) + s["금액"]
    처분별 = {k: v for k, v in 처분별.items() if v != 0}
    손금불산입 = sum(v for k, v in 처분별.items() if k != "△유보")

    # ── 계산 근거 판단 ──────────────────────────────────────────
    계산_근거 = []
    계산_근거.append({"항목": "상각범위액(정액법)" if 실제방법 == "정액법" else "상각범위액(정률법)",
                      "금액": 범위액,
                      "산식": (f"({세무상취득가액:,}) × {최종상각률} × {사용월수}/{12}"
                               if 실제방법 == "정액법" else
                               f"기초 미상각잔액 {기초세무상미상각:,} × 상각률 {최종상각률} × {사용월수}/{12} (잔존가액 5% 사전차감 없음, 상각 종료 시 비망가액 적용, 영 제26조⑥⑦)")})

    # ── 결과 조립 ────────────────────────────────────────────────
    결과 = {
        "세무조정": settlements,
        "소득처분별_합계": 처분별,
        "손금불산입_합계": 손금불산입,
        "상각범위액": 범위액,
        "회사계상액": 회사계상액,
        "상각부인액": 상각부인액,
        "시인부족액": 시인부족액,
        "전기부인액_추인": 전기부인추인,
        "감가상각의제": 감가상각의제액,
        "기말_상각부인누계액": 기말부인누계,
        "세무상_미상각잔액": 세무상미상각잔액,
    }
    계산 = {
        "상각방법": 실제방법,
        "상각률": 최종상각률,
        "사용월수": 사용월수,
        "즉시상각의제액": 당기즉시상각의제,
        "세무상 취득가액": 세무상취득가액,
        "기초 미상각잔액(즉시상각의제 포함)": 기초세무상미상각,
        "기초 감가상각누계액": 기초누계,
        "기말 감가상각누계액": 기말누계,
        "소멸 시인부족액": 소멸시인부족,
    }
    return {"결과": 결과, "계산": 계산, "판단": 판단_목록, "산식": 계산_근거}


def foreign_tax_credit(year, base, base_includes_grossup, method, countries, months=12):
    """법인세 외국납부세액공제(직접·간주·간접, 국가별 한도, 한도초과 이월).

    입력:
      year — 사업연도(2016~2026)
      base — 과세표준(원). base_includes_grossup — base에 Gross-up 포함 여부.
      method — '세액공제'|'손금산입'(2020년까지).
      countries — 국가별 [{country, foreign_income, direct_tax, deemed_tax?, related_costs?, reduction_excluded?,
                             subsidiaries?}]
      months — 사업연도 월수.

    반환: 결과 dict (국가별, 산출세액, 공제액, 이월액 등).
    """
    from .. import vocab

    # ── 입력 검증 ───────────────────────────────────────────────────
    if not countries or len(countries) == 0:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "필요 입력": {"countries": ["국가별 foreign_income, direct_tax 등"]},
                "안내": "최소 1개 이상 국가 정보가 필요합니다"}

    # ── 연도별 규칙·근거 ──────────────────────────────────────────
    fta_rule = vocab.rule("외국납부세액공제", year)       # 방법, 이월공제기간 등
    indirect_rule = vocab.rule("간접외국납부세액", year)  # 지분율, 보유기간, 익금불산입 배당 제외 여부
    fta_basis = vocab.basis("외국납부세액공제", year)
    indirect_basis = vocab.basis("간접외국납부세액", year)

    # ── method 검증 ────────────────────────────────────────────────
    허용방법 = fta_rule.get("방법", ["세액공제"])
    if method not in 허용방법:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "필요 입력": {"method": 허용방법},
                "안내": f"{year} 사업연도부터 손금산입방법은 삭제됨 — method='세액공제' 사용"}

    # 이월공제기간: 발생 사업연도 다음 사업연도부터 10년
    # 2021.1.1. 이후 개시 사업연도 발생분 → 10년 (법 제57조②, 법률 17652)
    # 2020년 이전 개시 사업연도 발생분 중 2021년 이후까지 남은 금액 → 부칙으로 10년
    start_year = year + 1
    end_year = year + 10
    이월공제기간_str = f"{start_year}~{end_year}"

    # ── 1차 패스: 국가별 중간 정보 수집 (Gross-up·간접세액·원천징수세 합산 등) ──
    country_intermediate = []
    총간접외국납부세액 = 0
    총Grossup익금산입액 = 0
    총손금산입대상직접 = 0
    산식목록 = []
    세무조정목록 = []
    오류 = None

    for ci, c in enumerate(countries):
        country = c.get("country", f"국가{ci+1}")
        foreign_income = c.get("foreign_income", 0) or 0
        direct_tax = c.get("direct_tax", 0) or 0
        deemed_tax = c.get("deemed_tax", 0) or 0
        related_costs = c.get("related_costs", 0) or 0
        reduction_excluded = c.get("reduction_excluded", 0) or 0
        subsidiaries = c.get("subsidiaries", []) or []

        # ── 국외원천소득 < 자회사 배당금 합계 검사 (익금불산입 배당 제외) ──
        과세대상배당금합계 = 0
        for si, s in enumerate(subsidiaries):
            dividend = s.get("dividend", 0) or 0
            if dividend <= 0:
                continue
            received_on = s.get("received_on", "")
            pe = s.get("participation_exempt", None)
            if received_on >= "2023-01-01":
                if pe is None:
                    누락키 = f"countries[{ci}].subsidiaries[{si}].participation_exempt"
                    오류 = {
                        "error": "입력 확인 필요 — 계산하지 않음",
                        "필요 입력": {누락키: [
                            "제18조의4 익금불산입 적용 여부 (2023.1.1. 이후 받은 배당 필수)"
                        ]},
                        "안내": "2023년 이후 받은 배당은 participation_exempt(적용 여부) 입력이 필요함"
                    }
                    break
                if not pe:
                    과세대상배당금합계 += dividend
            else:
                과세대상배당금합계 += dividend
        if 오류:
            break
        if subsidiaries and foreign_income < 과세대상배당금합계:
            오류 = {
                "error": "입력 확인 필요 — 계산하지 않음",
                "필요 입력": {f"countries[{ci}].foreign_income": [
                    f"국외원천소득({foreign_income:,}원)이 과세 대상 수입배당금 합({과세대상배당금합계:,}원)보다 작음 (익금불산입 배당 제외)"
                ]},
                "안내": "국외원천소득에 수입배당금이 포함되어야 함 (영 §94②). 익금불산입(participation_exempt) 배당은 제외됨"
            }
            break

        간접외국납부세액_국가 = 0
        Grossup익금산입액_국가 = 0
        국가원천징수세합계 = 0
        자회사결과목록 = []

        for si, sub in enumerate(subsidiaries):
            # ── 자회사 필수 사실 검사 ─────────────────────────────
            name = sub.get("name", f"자회사{si+1}")
            missing = []
            dividend = sub.get("dividend", None)
            if dividend is None or dividend == 0:
                missing.append("dividend — 수입배당금(원천징수 전)")
            dividend = dividend or 0

            received_on = sub.get("received_on", None)
            if not received_on:
                missing.append("received_on — 배당 받은 날")
            received_on = received_on or ""

            ownership = sub.get("ownership", None)
            if ownership is None:
                missing.append("ownership — 직접 보유비율(소수)")
            ownership = ownership or 0

            holding_months = sub.get("holding_months", None)
            if holding_months is None:
                missing.append("holding_months — 배당기준일 현재 보유 개월수")
            holding_months = holding_months or 0

            resource_dev = sub.get("resource_dev", None)
            if resource_dev is None:
                missing.append("resource_dev — 해외자원개발사업 법인 여부")
            resource_dev = bool(resource_dev)

            sub_income = sub.get("sub_income", None)
            if sub_income is None:
                missing.append("sub_income — 자회사 소득금액")
            sub_income = sub_income or 0

            sub_tax = sub.get("sub_tax", None)
            if sub_tax is None:
                missing.append("sub_tax — 자회사 법인세액")
            sub_tax = sub_tax or 0

            withholding_tax = sub.get("withholding_tax", 0) or 0

            participation_exempt = sub.get("participation_exempt", None)
            if received_on >= "2023-01-01":
                participation_exempt = bool(participation_exempt) if participation_exempt is not None else False
            else:
                participation_exempt = bool(participation_exempt) if participation_exempt is not None else False

            if missing:
                오류 = {
                    "error": "입력 확인 필요 — 계산하지 않음",
                    "필요 입력": {f"countries[{ci}].subsidiaries[{si}]": missing},
                    "안내": "자회사 필수 사실이 누락됨 — 계산하지 않음"
                }
                break

            if 오류:
                break

            # ── 요건 판정 ──────────────────────────────────────────
            # 지분율 요건은 배당 받은 날(received_on) 기준(2022.12.31.까지 25%, 2023.1.1.~ 10%)
            if received_on:
                ymd = int(received_on.replace("-", ""))
                date_rule = vocab.rule_on("간접외국납부세액", ymd)
            else:
                date_rule = indirect_rule
            기준지분율 = date_rule.get("지분율", 0.1)
            해외자원지분율 = date_rule.get("해외자원개발_지분율", 0.05)
            보유기간_개월 = date_rule.get("보유기간_개월", 6)
            익금불산입배당공제제외 = date_rule.get("익금불산입배당_공제제외", False)

            요구지분율 = 해외자원지분율 if resource_dev else 기준지분율
            요건충족 = (ownership >= 요구지분율 and holding_months >= 보유기간_개월)

            # participation_exempt 처리
            익금불산입 = False
            if participation_exempt and 익금불산입배당공제제외:
                요건충족 = False
                익금불산입 = True

            간접세액 = 0
            공제대상원천징수세 = 0
            처리 = ""
            산식 = ""

            if sub_income > 0 and sub_tax > 0 and dividend > 0 and (sub_income - sub_tax) > 0:
                if method == "손금산입":
                    # 손금산입 method: 간접세액 0, Gross-up 0
                    처리 = "손금산입 방법 — 간접외국납부세액 공제 대상 아님"
                    산식 = "손금산입 방법 선택 → 간접외국납부세액·Gross-up 없음"
                elif 요건충족:
                    분자 = sub_tax * dividend
                    분모2 = sub_income - sub_tax
                    간접세액 = int(분자 / 분모2)
                    Grossup익금산입액_국가 += 간접세액
                    간접외국납부세액_국가 += 간접세액
                    공제대상원천징수세 = withholding_tax
                    처리 = "간접외국납부세액 공제대상·익금산입(Gross-up)"
                    산식 = f"{sub_tax:,} × {dividend:,} ÷ ({sub_income:,} − {sub_tax:,}) = {간접세액:,}"
                else:
                    처리 = "요건 미충족 — 간접외국납부세액 공제 제외"
                    산식 = f"지분율 {ownership:.0%} < {요구지분율:.0%} 또는 보유 {holding_months}개월 < {보유기간_개월}개월"
                    if participation_exempt and 익금불산입배당공제제외:
                        처리 = "제18조의4 익금불산입 대상 — 간접외국납부세액 공제 제외"
                        산식 = f"수입배당금 익금불산입(법 §18조의4) 적용 → 간접외국납부세액 제외"
                        익금불산입 = True
                    익금불산입 = True
            elif dividend > 0 and sub_income <= 0:
                처리 = "자회사 소득금액 없음 — 간접외국납부세액 계산 불가"
                산식 = "자회사 소득금액 ≤ 0 → 계산 불가"
                익금불산입 = True
            elif sub_tax <= 0:
                처리 = "자회사 법인세액 없음 — 간접외국납부세액 없음"
                산식 = "자회사 법인세액 ≤ 0 → 간접외국납부세액 0"
                익금불산입 = True
            else:
                처리 = "입력 확인 — 간접외국납부세액 계산 불가"
                산식 = "배당금·자회사소득·법인세액 확인 필요"

            # withholding_tax: 간접요건 무관, participation_exempt 여부에 따라 공제 대상 포함
            if participation_exempt and 익금불산입배당공제제외:
                공제대상원천징수세 = 0  # 익금불산입 배당의 원천징수세는 공제 대상 아님
            else:
                공제대상원천징수세 = withholding_tax

            국가원천징수세합계 += 공제대상원천징수세

            자회사결과목록.append({
                "외국자회사": name,
                "수입배당금": dividend,
                "받은날": received_on,
                "요건": f"지분율 {ownership:.0%} (≥{요구지분율:.0%}), 보유 {holding_months}개월 (≥{보유기간_개월}개월)" + (", 해외자원개발" if resource_dev else ""),
                "요건충족": 요건충족,
                "간접외국납부세액": 간접세액,
                "공제대상_원천징수세": 공제대상원천징수세,
                "산식": 산식,
                "처리": 처리,
                "익금불산입": 익금불산입,
            })

        if 오류:
            break

        # ── 국가별 외국납부세액 계 ────────────────────────────────────
        직접세액_합산 = direct_tax + 국가원천징수세합계
        외국납부세액_계 = 직접세액_합산 + deemed_tax + (간접외국납부세액_국가 if method == "세액공제" else 0)

        중간 = {
            "country": country,
            "foreign_income": foreign_income,
            "direct_tax": direct_tax,
            "deemed_tax": deemed_tax,
            "related_costs": related_costs,
            "reduction_excluded": reduction_excluded,
            "간접외국납부세액_국가": 간접외국납부세액_국가,
            "Grossup익금산입액_국가": Grossup익금산입액_국가,
            "국가원천징수세합계": 국가원천징수세합계,
            "직접세액_합산": 직접세액_합산,
            "외국납부세액_계": 외국납부세액_계,
            "자회사결과목록": 자회사결과목록,
        }
        country_intermediate.append(중간)

        총간접외국납부세액 += 간접외국납부세액_국가
        총Grossup익금산입액 += Grossup익금산입액_국가
        총손금산입대상직접 += 직접세액_합산 + deemed_tax if method == "손금산입" else 0

    if 오류:
        return 오류

    # ── 과세표준·산출세액 결정 (방법별) ─────────────────────────────
    if method == "손금산입":
        과세표준 = base
        산출세액 = corp_tax(base, year, months) if base > 0 else 0
        분모 = 과세표준 if 과세표준 > 0 else 1
    else:
        # 세액공제 method: base_includes_grossup=false면 Gross-up합산액을 더함
        과세표준 = base + (총Grossup익금산입액 if not base_includes_grossup else 0)
        산출세액 = corp_tax(과세표준, year, months) if 과세표준 > 0 else 0
        분모 = 과세표준 if 과세표준 > 0 else 1

    # ── 2차 패스: 한도·공제액·이월액 계산 (세액공제 method만) ──────
    국가별결과 = []
    총공제한도 = 0
    총공제액 = 0
    총한도초과이월액 = 0
    총이월배제액 = 0

    for 중간 in country_intermediate:
        country = 중간["country"]
        foreign_income = 중간["foreign_income"]
        related_costs = 중간["related_costs"]
        reduction_excluded = 중간["reduction_excluded"]
        Grossup익금산입액_국가 = 중간["Grossup익금산입액_국가"]
        외국납부세액_계 = 중간["외국납부세액_계"]
        직접세액_합산 = 중간["직접세액_합산"]
        deemed_tax = 중간["deemed_tax"]
        간접외국납부세액_국가 = 중간["간접외국납부세액_국가"]
        국가원천징수세합계 = 중간["국가원천징수세합계"]
        자회사결과목록 = 중간["자회사결과목록"]

        if method == "손금산입":
            # 손금산입: 공제액 0, 한도 0, 모든 이월액 0
            국가별결과.append({
                "국가": country,
                "직접외국납부세액": 직접세액_합산,
                "간주외국납부세액": deemed_tax,
                "간접외국납부세액": 0,
                "Gross-up_익금산입액": 0,
                "외국납부세액_계": 외국납부세액_계,
                "외국자회사": 자회사결과목록,
                "국외원천소득": foreign_income + Grossup익금산입액_국가,
                "공제한도": 0,
                "공제액": 0,
                "한도초과액": 0,
                "이월배제액(대응비용 관련)": 0,
                "한도초과_이월액": 0,
                "손금산입_대상(직접)": 직접세액_합산 + deemed_tax,
            })
            continue

        # ── 한도 계산 ──────────────────────────────────────────────────
        분자 = foreign_income - related_costs - reduction_excluded + Grossup익금산입액_국가
        if 산출세액 > 0 and 분모 > 0:
            공제한도 = (산출세액 * 분자) // 분모
            공제한도 = min(공제한도, 산출세액)  # 비율 1.0 상한 (과세표준 한도)
        else:
            공제한도 = 0

        분자_전 = foreign_income
        if 산출세액 > 0 and 분모 > 0:
            한도_대응비용차감전 = (산출세액 * 분자_전) // 분모
            한도_대응비용차감전 = min(한도_대응비용차감전, 산출세액)
        else:
            한도_대응비용차감전 = 0

        공제액 = min(외국납부세액_계, 공제한도)
        한도초과액 = 외국납부세액_계 - 공제액
        이월배제액_국가 = max(0, min(외국납부세액_계, 한도_대응비용차감전) - 공제액)
        한도초과_이월액 = 한도초과액 - 이월배제액_국가  # 이월배제액을 뺀 나머지만 이월

        국가별결과.append({
            "국가": country,
            "직접외국납부세액": 직접세액_합산,
            "간주외국납부세액": deemed_tax,
            "간접외국납부세액": 간접외국납부세액_국가,
            "Gross-up_익금산입액": Grossup익금산입액_국가,
            "외국납부세액_계": 외국납부세액_계,
            "외국자회사": 자회사결과목록,
            "국외원천소득": foreign_income + Grossup익금산입액_국가,
            "공제한도": 공제한도,
            "공제액": 공제액,
            "한도초과액": 한도초과액,
            "이월배제액(대응비용 관련)": 이월배제액_국가,
            "한도초과_이월액": 한도초과_이월액,
            "손금산입_대상(직접)": 0,
        })

        총공제한도 += 공제한도
        총공제액 += 공제액
        총한도초과이월액 += 한도초과_이월액
        총이월배제액 += 이월배제액_국가

        산식목록.append(
            f"{country}: 한도 = {산출세액:,} × ({foreign_income:,} − {related_costs:,} − {reduction_excluded:,} + {Grossup익금산입액_국가:,}) ÷ {과세표준:,} = {공제한도:,}원, "
            f"공제액 = min({외국납부세액_계:,}, {공제한도:,}) = {공제액:,}원"
        )
        if 한도_대응비용차감전 > 공제한도:
            산식목록.append(
                f"{country}: 대응비용 차감 전 한도 = {산출세액:,} × {foreign_income:,} ÷ {과세표준:,} = {한도_대응비용차감전:,}원, "
                f"이월배제액 = min({외국납부세액_계:,}, {한도_대응비용차감전:,}) − {공제액:,} = {이월배제액_국가:,}원 (영 §94⑮)"
            )

    # ── Gross-up 익금산입 세무조정 ───────────────────────────────────
    if method == "세액공제" and 총Grossup익금산입액 > 0 and not base_includes_grossup:
        세무조정목록.append({
            "구분": "간접외국납부세액 익금산입(Gross-up)",
            "금액": 총Grossup익금산입액,
            "소득처분": "기타사외유출",
        })
        산식목록.insert(0, f"Gross-up 익금산입액 = {총Grossup익금산입액:,}원 (간접외국납부세액, 법 §15②2호·§57④)")

    # ── 결과 조립 ─────────────────────────────────────────────────────
    if method == "손금산입":
        확인필요문장 = "손금산입액은 과세표준 계산 전에 각 사업연도 소득에서 빼야 함 (법 §57②)"
        결과 = {
            "외국납부세액공제액": 0,
            "산출세액": 산출세액,
            "과세표준": base,
            "간접외국납부세액": 0,
            "Gross-up_익금산입액": 0,
            "공제한도_합계": 0,
            "한도초과_이월액": 0,
            "이월배제액": 0,
            "이월공제기간": 이월공제기간_str,
            "국가별": 국가별결과,
            "이월기간경과분": "",
            "산식": 산식목록,
            "세무조정": [],
            "이월공제기간_참고": "발생 당시 5년 — 법률 제17652호 부칙으로 10년",
            "손금산입_대상(직접)": 총손금산입대상직접,
            "확인 필요": 확인필요문장,
        }
    else:
        결과 = {
            "외국납부세액공제액": 총공제액,
            "산출세액": 산출세액,
            "과세표준": 과세표준,
            "간접외국납부세액": 총간접외국납부세액,
            "Gross-up_익금산입액": 총Grossup익금산입액,
            "공제한도_합계": 총공제한도,
            "한도초과_이월액": 총한도초과이월액,
            "이월배제액": 총이월배제액,
            "이월공제기간": 이월공제기간_str,
            "국가별": 국가별결과,
            "이월기간경과분": "",
            "산식": 산식목록,
            "세무조정": 세무조정목록,
            "이월공제기간_참고": "발생 당시 5년 — 법률 제17652호 부칙으로 10년" if year <= 2020 else "10년 (법 제57조②, 법률 제17652호)",
            "손금산입_대상(직접)": 0,
            "확인 필요": "",
        }

    근거목록 = list(fta_basis) + list(indirect_basis)
    _seen = set()
    _uniq = []
    for _x in 근거목록:
        _key = tuple(_x) if isinstance(_x, list) else _x
        if _key not in _seen:
            _seen.add(_key)
            _uniq.append(_x)

    return {
        "결과": 결과,
        "근거": _uniq,
        "연도별_근거": {
            "외국납부세액공제": fta_basis,
        },
    }


# ── 수입배당금 익금불산입 ──────────────────────────────────────────


def _parse_date(s):
    """YYYY-MM-DD 문자열 → (year, month, day) 튜플."""
    y, m, d = map(int, s.split("-"))
    return (y, m, d)


def _date_key(s):
    """YYYY-MM-DD 문자열 → YYYYMMDD 정수."""
    return int(s.replace("-", ""))


def _months_between(start, end):
    """두 날짜 사이의 월수 (초일 산입). start, end는 (y,m,d) 튜플."""
    sy, sm, sd = start
    ey, em, ed = end
    months = (ey - sy) * 12 + (em - sm)
    if ed >= sd:
        months += 1
    return months


def _within_3m_cutoff(record_date):
    """배당기준일(record_date)의 3개월 이전 기준일(YYYYMMDD). 민법 초일 불산입 기준."""
    y, m, d = map(int, record_date.split("-"))
    # 3개월 전: 같은 날짜 - 3개월 (월만 이동)
    nm = m - 3
    ny = y
    if nm <= 0:
        nm += 12
        ny -= 1
    # 경계: record_date가 12-31이면 09-30, 10-01이면 07-01
    # 민법 초일 불산입: record_date 전 3개월 "이내" = record_date부터 역산 3개월
    # 예: record_date 12-31 → 09-30 취득분은 3개월 이상(09-30은 경계, 10-01부터 이내)
    return f"{ny:04d}-{nm:02d}-{d:02d}"


def _calc_ownership_ratio(inv):
    """피출자법인의 출자비율과 3개월 이내 취득분 배당금을 계산.

    inv: Investee dict
    returns: (출자비율 float, 제외배당 int)
    """
    # ratio 방식
    if "ratio" in inv:
        ratio = inv["ratio"]
        within_3m_div = inv.get("within_3m_dividend", 0)
        return ratio, within_3m_div

    # shares 방식
    if "shares" in inv:
        s = inv["shares"]
        issued = s["issued"]
        held = s["held"]
        within_3m = s.get("within_3m", 0)
        ratio = (held - within_3m) / issued if issued > 0 else 0
        # 제외 배당 = floor(dividend × within_3m / held)
        dividend = inv["dividend"]
        if held > 0:
            within_3m_div = int(dividend * within_3m / held)
        else:
            within_3m_div = 0
        return ratio, within_3m_div

    # lots 방식 (선입선출 양도)
    if "lots" in inv:
        lots = sorted(inv["lots"], key=lambda x: x["date"])
        record_date = inv["record_date"]
        shares_issued = inv["shares_issued"]
        record_key = _date_key(record_date)
        cutoff_date = _within_3m_cutoff(record_date)
        cutoff_key = _date_key(cutoff_date)

        # record_date 이하만 반영, 양수(+)는 취득, 음수(-)는 양도
        balance = 0
        lot_balances = []  # [(date, shares)] 남은 취득 묶음
        for lot in lots:
            dk = _date_key(lot["date"])
            if dk > record_key:
                continue  # record_date 이후는 반영 안 함
            shares = lot["shares"]
            if shares > 0:
                lot_balances.append([lot["date"], shares])
                balance += shares
            else:  # 양도 (선입선출: 가장 먼저 취득한 묶음부터 차감)
                to_remove = -shares
                remaining = to_remove
                new_lot_balances = []
                for lb_date, lb_shares in lot_balances:
                    if remaining <= 0:
                        new_lot_balances.append((lb_date, lb_shares))
                        continue
                    if lb_shares <= remaining:
                        remaining -= lb_shares
                        # 해당 묶음 전체 차감
                    else:
                        lb_shares -= remaining
                        new_lot_balances.append((lb_date, lb_shares))
                        remaining = 0
                lot_balances = new_lot_balances
                balance -= to_remove

        # 이제 lot_balances에 남은 묶음으로 3개월 이상/이내 판정
        held_total = balance
        within_3m_shares = 0
        for lb_date, lb_shares in lot_balances:
            if _date_key(lb_date) > cutoff_key:  # 취득일 > cutoff → 3개월 이내
                within_3m_shares += lb_shares

        held_over_3m = held_total - within_3m_shares
        ratio = held_over_3m / shares_issued if shares_issued > 0 else 0

        # 제외 배당 = floor(dividend × within_3m_shares / held)
        dividend = inv["dividend"]
        if held_total > 0:
            within_3m_div = int(dividend * within_3m_shares / held_total)
        else:
            within_3m_div = 0
        return ratio, within_3m_div

    return 0, 0


def _is_exclusion_applicable(exclusion_kind, received_on_key):
    """특정 exclusion kind가 받은 날(received_on_key)에 제외 대상인지 판정.

    returns: (적용됨 bool, 사유 str|None)
    """
    if exclusion_kind is None:
        return False, None

    exclusion_map = {
        "소득공제법인": 19000101,   # 2019.1.1~ (법률 제16833호 부칙 제3조로 2020.12.22 추가)
        "감면법인": 19000101,       # 2019.1.1~ (구 조문 포함 전 기간)
        "신탁재산": 20210101,       # 2021.1.1~ (법률 제17652호 부칙 제3조①)
        "재평가적립금감액": 20240101,  # 2024.1.1~ (법률 제19930호 부칙 제3조)
        "자본준비금감액": 20240101,    # 2024.1.1~ (법률 제19930호 부칙 제3조)
        "감자등의제배당": 20240101,    # 2024.1.1~ (법률 제19930호 부칙 제3조)
    }

    threshold = exclusion_map.get(exclusion_kind)
    if threshold is None:
        return False, f"알 수 없는 제외 종류: {exclusion_kind}"

    if received_on_key >= threshold:
        return True, None
    else:
        return False, f"해당 연도에는 제18조의2② 제외 대상 아님(2024.1.1 이후 받는 분부터)"


def _get_exclusion_rate_and_rule(received_on_key, company_type, holding_legacy_election, is_subsidiary):
    """받은 날 기준 적용 규정과 익금불산입률 조회.

    returns: (적용규정 str, 익금불산입률 float)
    """
    # 2023.1.1 이후: 통합 표 (제18조의2)
    if received_on_key >= 20230101:
        if company_type == "지주회사" and holding_legacy_election and received_on_key <= 20261231:
            # 종전 제18조의3 선택: 자회사 요건 충족 시 지주 표, 아니면 통합 표
            if is_subsidiary:
                # 2020~2022 지주 표 사용
                if is_subsidiary:
                    return _get_holding_rate_2020_2022(received_on_key, company_type)
            # 자회사 아니면 통합 표
            return "법인세법 제18조의2(2023.1.1 이후)", _get_integrated_rate(received_on_key)
        return "법인세법 제18조의2(2023.1.1 이후)", _get_integrated_rate(received_on_key)

    # 2019.1.1 ~ 2022.12.31
    if received_on_key >= 20190101:
        if company_type == "지주회사":
            # 지주회사는 자회사 요건 판정
            return _get_holding_rate_2019_2022(received_on_key, company_type)
        return "법인세법 제18조의2(2019.1.1~2022.12.31)", _get_general_rate_2019_2022(received_on_key)

    # 2016.1.1 ~ 2018.12.31
    if company_type == "지주회사":
        return "구 법인세법 제18조의2(지주회사)", _get_holding_rate_2016_2018(received_on_key)
    return "구 법인세법 제18조의3(일반)", _get_general_rate_2016_2018(received_on_key)


def _get_integrated_rate(received_on_key):
    """2023.1.1 이후 통합 표 익금불산입률."""
    # 상장/비상장 구분 없음: 50% 이상 100%, 20% 이상~50% 미만 80%, 20% 미만 30%
    # (비율 파라미터로 판정)
    return None  # 호출측에서 비율 기준으로 판정


def _get_integrated_exclusion_rate(ratio):
    """2023.1.1 이후 통합 표: 50%↑ 100%, 20~50% 80%, 20%↓ 30%."""
    if ratio >= 0.5:
        return 1.0
    elif ratio >= 0.2:
        return 0.8
    else:
        return 0.3


def _get_general_rate_2019_2022(received_on_key):
    """2019~2022 일반 익금불산입률 (받은 날 기준)."""
    if received_on_key >= 20200101:
        # 2020~2022: 30% 이상~100% 미만 50%, 30% 미만 30% / 상장 구분 없음
        # 상장·비상장 구분: 100% 100%, 50% 이상~100% 미만 50%, 50% 미만 30%
        return None  # 호출측에서 비율 기준으로 판정
    else:
        # 2019: 30% 초과~100% 미만 50%, 30% 이하 30% / 상장·비상장 구분
        return None


def _get_general_exclusion_rate_2019_2022(ratio, listed, received_on_key):
    """2019~2022 일반 익금불산입률."""
    if received_on_key >= 20200101:
        # 2020~2022: 상장 100% 100, 30% 이상~100% 미만 50, 30% 미만 30
        #            비상장 100% 100, 50% 이상~100% 미만 50, 50% 미만 30
        if ratio >= 1.0:
            return 1.0
        elif listed:
            if ratio >= 0.3:  # 30% 이상
                return 0.5
            else:
                return 0.3
        else:
            if ratio >= 0.5:  # 50% 이상
                return 0.5
            else:
                return 0.3
    else:
        # 2019: 100% 100%, 30% 초과~100% 미만 50%, 30% 이하 30%
        # 비상장법인 50% 초과~100% 미만 50%, 50% 이하 30%
        if ratio >= 1.0:
            return 1.0
        elif listed:
            if ratio > 0.3:  # 30% 초과
                return 0.5
            else:
                return 0.3
        else:
            if ratio > 0.5:  # 50% 초과
                return 0.5
            else:
                return 0.3


def _get_general_rate_2016_2018(received_on_key):
    """2016~2018 일반(구 제18조의3) 익금불산입률."""
    return None  # 호출측에서 비율 기준으로 판정


def _get_general_exclusion_rate_2016_2018(ratio, listed):
    """2016~2018 일반(구 제18조의3) 익금불산입률."""
    # 상장: 100% 100%, 30% 초과 50%, 30% 이하 30%
    # 비상장: 100% 100%, 50% 초과 50%, 50% 이하 30%
    if ratio >= 1.0:
        return 1.0
    elif listed:
        if ratio > 0.3:
            return 0.5
        else:
            return 0.3
    else:
        if ratio > 0.5:
            return 0.5
        else:
            return 0.3


def _get_holding_rate_2019_2022(received_on_key, company_type):
    """2019~2022 지주회사 익금불산입률."""
    return None  # 호출측에서 비율 기준으로 판정


def _get_holding_exclusion_rate_2019_2022(ratio, listed, received_on_key, is_subsidiary):
    """2019~2022 지주회사 익금불산입률."""
    if not is_subsidiary:
        # 자회사 아니면 일반 규정 적용 (법 제18조의2)
        if received_on_key >= 20200101:
            if ratio >= 1.0:
                return 1.0
            elif ratio >= 0.5:
                return 0.5
            else:
                return 0.3
        else:
            if ratio >= 1.0:
                return 1.0
            elif ratio > 0.5:
                return 0.5
            else:
                return 0.3

    # 자회사: 법 제18조의3 표
    if received_on_key >= 20200101:
        # 2020~2022: 40% 이상 100%, 30% 이상~40% 미만 90%, 30% 미만 80%
        # 비상장: 80% 이상 100%, 50% 이상~80% 미만 90%, 50% 미만 80%
        if listed:
            if ratio >= 0.4:
                return 1.0
            elif ratio >= 0.3:
                return 0.9
            else:
                return 0.8
        else:
            if ratio >= 0.8:
                return 1.0
            elif ratio >= 0.5:
                return 0.9
            else:
                return 0.8
    else:
        # 2019: 40% 초과 100%, 30% 초과~40% 이하 90%, 30% 이하 80%
        # 비상장: 80% 초과 100%, 50% 초과~80% 이하 90%, 50% 이하 80%
        if listed:
            if ratio > 0.4:
                return 1.0
            elif ratio > 0.3:
                return 0.9
            else:
                return 0.8
        else:
            if ratio > 0.8:
                return 1.0
            elif ratio > 0.5:
                return 0.9
            else:
                return 0.8


def _get_holding_rate_2016_2018(received_on_key):
    """2016~2018 지주회사(구 제18조의2) 익금불산입률."""
    return None


def _get_holding_exclusion_rate_2016_2018(ratio, listed, is_subsidiary):
    """2016~2018 지주회사(구 제18조의2) 익금불산입률."""
    if not is_subsidiary:
        # 자회사 아니면 구 제18조의3(일반) 적용
        return _get_general_exclusion_rate_2016_2018(ratio, listed)

    # 자회사: 구 법 제18조의2①1·2호
    # 상장 자회사: 40% 초과 100%, 이하 80%
    # 비상장 자회사: 80% 초과 100%, 이하 80%
    if listed:
        if ratio > 0.4:
            return 1.0
        else:
            return 0.8
    else:
        if ratio > 0.8:
            return 1.0
        else:
            return 0.8


def _check_subsidiary(ratio, listed, venture, subsidiary_flag):
    """지주회사 자회사 요건 판정.

    구 영 제17조의2②·영 제17조의3②: 직접 발행주식총수의 40%(상장·벤처 20%) 이상 보유
    subsidiary_flag가 있으면 그 값 사용, 없으면 출자비율로 판정
    """
    if subsidiary_flag is not None:
        return subsidiary_flag

    if listed or venture:
        return ratio >= 0.2
    else:
        return ratio >= 0.4


def _build_rule_text(received_on_key, company_type):
    """적용 규정 텍스트 생성."""
    if received_on_key >= 20230101:
        return "법인세법 제18조의2(2023.1.1 이후)"
    elif received_on_key >= 20190101:
        if company_type == "지주회사":
            return "법인세법 제18조의3(지주회사, 2019.1.1~2022.12.31)"
        return "법인세법 제18조의2(2019.1.1~2022.12.31)"
    else:
        if company_type == "지주회사":
            return "구 법인세법 제18조의2(지주회사, 2016.1.1~2018.12.31)"
        return "구 법인세법 제18조의3(일반, 2016.1.1~2018.12.31)"


def dividend_received_deduction(
    year: int,
    investees: list,
    interest_paid: int = 0,
    interest_excluded: int = 0,
    total_assets_jeoksu: int = 0,
    fy_start: str = None,
    fy_end: str = None,
    company_type: str = "일반",
    holding_legacy_election: bool = False,
) -> dict:
    """내국법인 수입배당금액 익금불산입(피출자법인별 익금불산입률·지급이자 차감·세무조정)."""

    # ── 1. 입력 검사 ──
    problems = []
    needed = []

    if year < 2016 or year > 2026:
        problems.append(f"year({year})가 2016~2026 범위 밖")

    if not investees:
        problems.append("investees 목록이 비어 있음")

    # 사업연도 설정
    if fy_start is None:
        fy_start = f"{year}-01-01"
    if fy_end is None:
        fy_end = f"{year}-12-31"

    fy_start_key = _date_key(fy_start)
    fy_end_key = _date_key(fy_end)
    is_calendar_year = (fy_start == f"{year}-01-01" and fy_end == f"{year}-12-31")

    # 차감 이자 계산
    A = max(0, interest_paid - interest_excluded)
    if interest_excluded > interest_paid:
        problems.append(f"interest_excluded({interest_excluded}) > interest_paid({interest_paid})")

    # 사채권자의 이자 등(idx) 계산 필요 여부
    need_total_assets = A > 0

    per_investee_results = []
    대상액_합계 = 0
    차감액_합계 = 0
    산식_목록 = []
    판단_목록 = []

    for i, inv in enumerate(investees):
        name = inv.get("name", f"피출자법인{i+1}")

        # 출자비율 정보 확인
        has_ratio = "ratio" in inv
        has_shares = "shares" in inv
        has_lots = "lots" in inv

        if has_ratio + has_shares + has_lots != 1:
            problems.append(f"{name}: ratio·shares·lots 중 정확히 하나만 필요")
            continue

        dv = inv.get("dividend")
        if dv is not None and (isinstance(dv, bool) or not isinstance(dv, int)):
            problems.append(f"{name}: dividend=int 필요, 현재 {dv}")

        # 배당 받은 날
        received_on = inv.get("received_on")
        if received_on is None:
            if is_calendar_year:
                received_on = f"{year}-06-30"
            else:
                problems.append(f"{name}: received_on 필요 (사업연도가 역년 아님)")
                continue
        received_on_key = _date_key(received_on)

        # 사업연도 밖 배당인지 확인
        if received_on_key < fy_start_key or received_on_key > fy_end_key:
            problems.append(f"{name}: received_on({received_on})이 사업연도 밖")
            continue

        # 출자비율·제외 배당 계산
        ratio, within_3m_dividend = _calc_ownership_ratio(inv)

        if ratio < 0 or ratio > 1:
            problems.append(f"{name}: ratio({ratio})가 0~1 범위 밖")
            continue

        dividend = inv["dividend"]
        if within_3m_dividend > dividend:
            problems.append(f"{name}: within_3m_dividend > dividend")
            continue

        # shares 검증
        if has_shares:
            s = inv["shares"]
            if s["held"] > s["issued"]:
                problems.append(f"{name}: shares.held > issued")
                continue
            if s.get("within_3m", 0) > s["held"]:
                problems.append(f"{name}: within_3m > held")
                continue
            if s["held"] == 0 and dividend > 0:
                problems.append(f"{name}: held=0인데 dividend>0")
                continue

        # lots 검증
        if has_lots:
            if "record_date" not in inv:
                problems.append(f"{name}: lots 입력 시 record_date 필요")
                continue
            if "shares_issued" not in inv:
                problems.append(f"{name}: lots 입력 시 shares_issued 필요")
                continue

        # 차감 이자 관련 검증
        if A > 0 and total_assets_jeoksu <= 0:
            problems.append(f"차감 이자(A={A}) > 0인데 total_assets_jeoksu 없음")
            continue

        exclusion_kind = inv.get("exclusion")
        is_excluded, exclude_reason = _is_exclusion_applicable(exclusion_kind, received_on_key)

        if not is_excluded and A > 0:
            if "book_value_jeoksu" not in inv:
                problems.append(f"{name}: 차감 이자 > 0이고 익금불산입률 적용 대상인데 book_value_jeoksu 없음")
                continue

        # 제외 대상 처리
        if is_excluded:
            대상_배당금 = 0
            제외_배당금 = dividend
            제외_사유 = exclusion_kind
            if exclude_reason:
                판단_목록.append({"항목": f"{name} 제외 대상", "결론": exclude_reason, "근거": "법인세법 제18조의2②"})
        else:
            제외_배당금 = within_3m_dividend
            제외_사유 = "3개월 이내 취득 주식분 배당금" if within_3m_dividend > 0 else None
            대상_배당금 = dividend - 제외_배당금

        # 지주회사 자회사 요건 판정 (2016~2022)
        is_subsidiary = None
        if company_type == "지주회사" and received_on_key < 20230101:
            is_subsidiary = _check_subsidiary(
                ratio,
                inv.get("listed", False),
                inv.get("venture", False),
                inv.get("subsidiary"),
            )

        # 지주회사 종전 선택(holding_legacy_election)이면 subsidiary 여부도 판정
        if company_type == "지주회사" and holding_legacy_election and received_on_key >= 20230101 and received_on_key <= 20261231:
            if is_subsidiary is None:
                is_subsidiary = _check_subsidiary(
                    ratio,
                    inv.get("listed", False),
                    inv.get("venture", False),
                    inv.get("subsidiary"),
                )

        # 적용 규정 텍스트
        rule_text = _build_rule_text(received_on_key, company_type)

        # 익금불산입률 계산
        if is_excluded:
            exclusion_rate = 0
        elif received_on_key >= 20230101:
            if company_type == "지주회사" and holding_legacy_election and received_on_key <= 20261231 and is_subsidiary:
                exclusion_rate = _get_holding_exclusion_rate_2019_2022(ratio, inv.get("listed", False), received_on_key, True)
            else:
                exclusion_rate = _get_integrated_exclusion_rate(ratio)
        elif received_on_key >= 20190101:
            if company_type == "지주회사":
                if is_subsidiary:
                    exclusion_rate = _get_holding_exclusion_rate_2019_2022(ratio, inv.get("listed", False), received_on_key, True)
                else:
                    exclusion_rate = _get_general_exclusion_rate_2019_2022(ratio, inv.get("listed", False), received_on_key)
            else:
                exclusion_rate = _get_general_exclusion_rate_2019_2022(ratio, inv.get("listed", False), received_on_key)
        else:
            if company_type == "지주회사":
                if is_subsidiary:
                    exclusion_rate = _get_holding_exclusion_rate_2016_2018(ratio, inv.get("listed", False), True)
                else:
                    exclusion_rate = _get_general_exclusion_rate_2016_2018(ratio, inv.get("listed", False))
            else:
                exclusion_rate = _get_general_exclusion_rate_2016_2018(ratio, inv.get("listed", False))

        # 익금불산입 대상액 = floor(대상 배당 × 익금불산입률)
        대상액 = int(대상_배당금 * exclusion_rate)
        대상액_합계 += 대상액

        # 차감액 = floor(A × B / C × D)
        book_value = inv.get("book_value_jeoksu", 0)
        if A > 0 and not is_excluded:
            차감액 = int(A * book_value * exclusion_rate / total_assets_jeoksu)
        else:
            차감액 = 0
        차감액_합계 += 차감액

        산식_목록.append(f"{name}: 대상액 = {대상_배당금:,} × {exclusion_rate} = {대상액:,}원, 차감액 = {A:,} × {book_value:,} / {total_assets_jeoksu:,} × {exclusion_rate} = {차감액:,}원")

        per_investee_results.append({
            "이름": name,
            "적용규정": rule_text,
            "출자비율": ratio,
            "익금불산입률": exclusion_rate,
            "수입배당금액": dividend,
            "제외_배당금": 제외_배당금,
            "제외_사유": 제외_사유,
            "대상_배당금": 대상_배당금,
            "익금불산입_대상액": 대상액,
            "차감액": 차감액,
            "익금불산입액": 대상액 - 차감액,
        })

    if problems:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": problems, "필요 입력": needed}

    # ── 8. 합계 익금불산입액 = max(0, Σ대상액 - Σ차감액) ──
    총익금불산입액 = max(0, 대상액_합계 - 차감액_합계)

    # ── 9. 세무조정 ──
    세무조정 = []
    if 총익금불산입액 > 0:
        세무조정.append({
            "구분": "수입배당금 익금불산입",
            "조정": "익금불산입",
            "금액": 총익금불산입액,
            "소득처분": "기타",
            "근거": "법인세법 제18조의2①",
            "이유": f"수입배당금 익금불산입 합계 {총익금불산입액:,}원",
        })

    return {
        "결과": {
            "세무조정": 세무조정,
            "익금불산입액": 총익금불산입액,
            "피출자법인별": per_investee_results,
        },
        "계산": {
            "차입금이자": A,
            "자산총액_적수": total_assets_jeoksu if A > 0 else None,
            "익금불산입_대상액_합계": 대상액_합계,
            "차감액_합계": 차감액_합계,
            "산식": 산식_목록,
        },
        "판단": 판단_목록,
        "근거": "법인세법 제18조의2, 시행령 제17조의2·제17조의3",
    }




# ── 일시상각충당금·압축기장충당금 ──────────────────────────────────

def asset_grant_reserve(
    year: int,
    kind: str,
    received: int,
    assets: list,
    lost_book_value: int = None,
    receipt_year: bool = True,
    planned_use: int = 0,
    expired_unused: int = 0,
    claim_by_return: bool = True,
    kwargs: dict = None,
) -> dict:
    """국고보조금·공사부담금·보험차익 일시상각충당금·압축기장충당금 세무조정."""
    # 입력 검증: 알 수 없는 키는 모델 검증에서 처리됨 (extra='forbid')
    if not assets:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["assets 목록이 비어 있음"]}

    if kind == "보험차익":
        if lost_book_value is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["보험차익은 멸실자산 장부가액(lost_book_value) 필요"]}
        if len(assets) > 1:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["보험차익은 자산 1개만"]}
        보험차익 = max(0, received - lost_book_value)
    else:
        보험차익 = None

    # used > received 검사는 국고보조금·공사부담금에만 적용 (보험차익은 used 개념 없음)
    if kind in ("국고보조금", "공사부담금") and received > 0:
        for ai, a in enumerate(assets):
            used_v = a.get("used", a["cost"])
            if isinstance(used_v, bool) or not isinstance(used_v, int):
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"assets[{ai}].used: 금액(원)을 넣으세요 — true/false 아님"]}
            cost_v = a["cost"]
            if isinstance(cost_v, bool) or not isinstance(cost_v, int) or cost_v < 0:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"assets[{ai}].cost: 금액(원)을 넣으세요 — true/false 아님"]}
        if sum(a.get("used", a["cost"]) for a in assets) > received:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["사용액 합계가 수령액을 넘음"]}

    사용기한 = {"국고보조금": 1, "공사부담금": 1, "보험차익": 2}[kind]

    손금산입한도 = 0
    설정액 = 0
    상계액 = 0
    처분익금 = 0
    사용계획손금 = 0
    미사용익금 = 0
    기말잔액 = 0
    자산별 = []
    세무조정 = []

    for a in assets:
        asset_name = a["asset"]
        cost = a["cost"]
        if isinstance(cost, bool) or not isinstance(cost, int) or cost < 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"assets[{a}].cost: 금액(원)을 넣으세요 — true/false 아님"]}
        used = a.get("used", cost)
        if isinstance(used, bool) or not isinstance(used, int) or used < 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"assets[{a}].used: 금액(원)을 넣으세요 — true/false 아님"]}
        depreciable = a["depreciable"]
        dep_this_year = a.get("depreciation_this_year", 0)
        if isinstance(dep_this_year, bool) or not isinstance(dep_this_year, int) or dep_this_year < 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"assets[{a}].depreciation_this_year: 금액(원)을 넣으세요 — true/false 아님"]}
        disposed = a.get("disposed", False)
        disposed_ratio = a.get("disposed_ratio", 1.0)
        prior_dep = a.get("prior_dep_on_grant", 0)
        book_provision = a.get("book_provision", 0)
        if isinstance(book_provision, bool) or not isinstance(book_provision, int):
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"assets[{a}].book_provision: 금액(원)을 넣으세요 — true/false 아님"]}
        book_reversal = a.get("book_reversal", 0)
        if isinstance(book_reversal, bool) or not isinstance(book_reversal, int):
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"assets[{a}].book_reversal: 금액(원)을 넣으세요 — true/false 아님"]}

        if receipt_year:
            if kind == "보험차익":
                한도 = min(보험차익, max(0, cost - lost_book_value))
                if not depreciable:
                    한도 = 0
            else:
                한도 = max(0, used - prior_dep)

            구분 = "일시상각충당금" if depreciable else "압축기장충당금"

            if book_provision > 한도:
                손금불산입 = book_provision - 한도
                adj = {"과목": f"{구분} 한도초과", "조정": "손금불산입", "금액": 손금불산입,
                                    "소득처분": "유보"}
                세무조정.append(adj)
                설정액 = 한도
            else:
                설정액 = book_provision
                if claim_by_return:
                    추가손금 = 한도 - book_provision
                    if 추가손금 > 0:
                        adj = {"과목": f"{구분} 설정", "조정": "손금산입", "금액": 추가손금,
                                            "소득처분": "△유보"}
                        세무조정.append(adj)
                        설정액 = 한도

            손금산입한도 += 설정액

            # 상계
            if depreciable and cost > 0 and dep_this_year > 0:
                상계액 = min(int(dep_this_year * 설정액 / cost), 설정액)
            else:
                상계액 = 0

            기말 = 설정액 - 상계액 - (처분익금 if disposed else 0)
        else:
            reserve_initial = a.get("reserve_initial", 0)
            reserve_opening = a.get("reserve_opening", 0)
            설정액 = reserve_initial

            if book_provision > 0:
                return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["이후 연도는 book_provision 설정 불가"]}

            구분 = "일시상각충당금" if depreciable else "압축기장충당금"

            if depreciable and cost > 0 and dep_this_year > 0:
                상계액 = min(int(dep_this_year * reserve_initial / cost), reserve_opening)
            else:
                상계액 = 0

            if disposed:
                if depreciable:
                    처분익금 = int((reserve_opening - 상계액) * disposed_ratio)
                else:
                    처분익금 = int(reserve_opening * disposed_ratio)
            else:
                처분익금 = 0

            기말 = reserve_opening - 상계액 - 처분익금

        # 회사 환입과 비교
        세무상환입 = 상계액 + 처분익금
        if book_reversal == 0:
            # 회사가 환입을 계상하지 않은 경우: 세무상 상계액·처분익금을 그대로 익금산입
            if 상계액 > 0:
                adj = {"과목": f"{구분} 환입", "조정": "익금산입", "금액": 상계액,
                                    "소득처분": "유보"}
                세무조정.append(adj)
            if 처분익금 > 0:
                adj = {"과목": f"{구분} 처분", "조정": "익금산입", "금액": 처분익금,
                                    "소득처분": "유보"}
                세무조정.append(adj)
        elif 세무상환입 > book_reversal:
            차액 = 세무상환입 - book_reversal
            adj = {"과목": f"{구분} 환입 차액", "조정": "익금산입", "금액": 차액,
                                "소득처분": "유보"}
            세무조정.append(adj)
        elif 세무상환입 < book_reversal:
            차액 = book_reversal - 세무상환입
            adj = {"과목": f"{구분} 환입 차액", "조정": "익금불산입", "금액": 차액,
                                "소득처분": "△유보"}
            세무조정.append(adj)

        자산별.append({
            "asset": asset_name,
            "구분": 구분,
            "손금산입_한도": 손금산입한도 if receipt_year else 0,
            "세무상_설정액": 설정액,
            "회사_설정액": book_provision,
            "기초_잔액": reserve_opening if not receipt_year else 0,
            "상계액": 상계액,
            "처분_익금산입": 처분익금,
            "회사_환입액": book_reversal,
            "기말_잔액": 기말,
        })

        손금산입한도 = 0

    # 사용계획
    if planned_use > 0:
        자가사용 = received - sum(a.get("used", a["cost"]) for a in assets)
        if kind == "보험차익":
            미사용 = 보험차익 - sum(자산별[i]["손금산입_한도"] for i in range(len(자산별)))
        else:
            미사용 = 자가사용
        사용계획손금 = min(planned_use, 미사용)
        if 사용계획손금 > 0:
            adj = {"과목": "사용계획 손금산입", "조정": "손금산입", "금액": 사용계획손금,
                                "소득처분": "△유보"}
            세무조정.append(adj)
        미사용익금 = 미사용 - 사용계획손금

    # 미사용 익금산입
    if expired_unused > 0:
        adj = {"과목": "사용계획분 미사용 익금산입", "조정": "익금산입", "금액": expired_unused,
                            "소득처분": "유보"}
        세무조정.append(adj)

    # 소득금액 순영향
    익금합계 = sum(t["금액"] for t in 세무조정 if t["조정"] == "익금산입")
    손금합계 = sum(t["금액"] for t in 세무조정 if t["조정"] == "손금산입")
    손금불산입합계 = sum(t["금액"] for t in 세무조정 if t["조정"] == "손금불산입")
    익금불산입합계 = sum(t["금액"] for t in 세무조정 if t["조정"] == "익금불산입")
    순영향 = (익금합계 + 손금불산입합계) - (손금합계 + 익금불산입합계)

    return {
        "결과": {
            "보험차익": 보험차익,
            "손금산입_한도": sum(a["손금산입_한도"] for a in 자산별) if receipt_year else 0,
            "충당금_설정액": sum(a["세무상_설정액"] for a in 자산별) if receipt_year else 0,
            "상계액": sum(a["상계액"] for a in 자산별),
            "처분_익금산입": sum(a["처분_익금산입"] for a in 자산별),
            "사용계획_손금산입": 사용계획손금,
            "미사용_익금산입": 미사용익금,
            "기말_충당금_잔액": sum(a["기말_잔액"] for a in 자산별),
            "사용기한_연": 사용기한,
            "소득금액_순영향": 순영향,
        },
        "세무조정": 세무조정,
        "계산": {"자산별": 자산별},
        "판단": [],
        "근거": "법인세법 제36조·제37조·제38조, 시행령 제64조·제65조·제66조·제98조②",
    }


# ── 재고자산 평가 세무조정 ──────────────────────────────────────
_METHOD_LITERALS = ("개별법", "선입선출법", "후입선출법", "총평균법", "이동평균법", "매출가격환원법")
_CATEGORY_LITERALS = ("제품·상품", "반제품·재공품", "원재료", "저장품", "매매목적부동산")


def _date_sub_months(dt, months):
    """날짜에서 months 개월을 뺀 날짜(일은 그대로, 월만 차감)."""
    m = dt.month - months
    y = dt.year
    while m <= 0:
        m += 12; y -= 1
    return date(y, m, dt.day)


def _date_add_months_last(dt, months):
    """dt + months 개월 후 그 달의 말일."""
    m = dt.month + months
    y = dt.year
    while m > 12:
        m -= 12; y += 1
    import calendar
    last = calendar.monthrange(y, m)[1]
    return date(y, m, last)


def inventory_valuation_adjustment(
    year: int,
    items: list,
    fy_start: str = None,
    fy_end: str = None,
    new_corp: bool = False,
) -> dict:
    """재고자산 평가 세무조정(세법상 평가방법 결정·평가차 유보). 근거: 법인세법 제42조, 시행령 제73조·제74조.

    입력:
      year — 사업연도 개시 연도(2016~2026)
      fy_start/fy_end — 사업연도 개시일·종료일(YYYY-MM-DD). 생략 시 year-01-01/year-12-31
      new_corp — 설립(수익사업 개시) 첫 사업연도인지 (최초 신고기한 적용)
      items — [{'category': '제품·상품'|..., 'name'?, 'reported_method': ...,
                'reported_lcm'?, 'used_method': ..., 'used_lcm'?,
                'change_report'?: {method, lcm?, filed_on}, 'book_value': int,
                'valuations': {방법별: int, 시가?}, 'prior_adjustment'?: int}]
    """
    # ── 입력 검사 ──────────────────────────────────────────────────────────
    if not (2016 <= year <= 2026):
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"year={year}은(는) 2016~2026 범위를 벗어남"]}

    if fy_start is None:
        fy_start = f"{year}-01-01"
    if fy_end is None:
        fy_end = f"{year}-12-31"

    fy_s = date.fromisoformat(fy_start)
    fy_e = date.fromisoformat(fy_end)
    if fy_s > fy_e:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"사업연도 시작일({fy_start})이 종료일({fy_end})보다 늦음"]}
    mos = months_in(fy_start, fy_end)
    if mos > 12:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"사업연도가 {mos}개월로 12개월 초과"]}

    problems = []
    if not isinstance(items, list) or not items:
        problems.append("items가 비어 있음")
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            problems.append(f"항목 {i+1}: dict 아님")
            continue
        cat = it.get("category")
        if cat not in _CATEGORY_LITERALS:
            problems.append(f"항목 {i+1}: category='{cat}' 허용값 아님 "
                            f"({_CATEGORY_LITERALS})")
        rm = it.get("reported_method")
        if rm not in _METHOD_LITERALS + ("무신고",):
            problems.append(f"항목 {i+1}: reported_method='{rm}' 허용값 아님")
        if rm == "무신고" and it.get("reported_lcm") is True:
            problems.append(f"항목 {i+1}: reported_method='무신고'인데 reported_lcm=True")
        um = it.get("used_method")
        if um not in _METHOD_LITERALS:
            problems.append(f"항목 {i+1}: used_method='{um}' 허용값 아님 "
                            f"({_METHOD_LITERALS})")
        cr = it.get("change_report")
        if cr is not None:
            if not isinstance(cr, dict):
                problems.append(f"항목 {i+1}: change_report가 dict 아님")
            else:
                cm = cr.get("method")
                if cm not in _METHOD_LITERALS:
                    problems.append(f"항목 {i+1}: change_report.method='{cm}' 허용값 아님")
                fo = cr.get("filed_on")
                if not isinstance(fo, str):
                    problems.append(f"항목 {i+1}: change_report.filed_on 형식 오류")
                else:
                    try:
                        date.fromisoformat(fo)
                    except Exception:
                        problems.append(f"항목 {i+1}: change_report.filed_on='{fo}' 형식 오류")
        bv = it.get("book_value")
        if isinstance(bv, bool) or not isinstance(bv, int) or bv < 0:
            problems.append(f"항목 {i+1}: book_value=int≥0 필요, 현재 {bv}")
        vals = it.get("valuations")
        if not isinstance(vals, dict):
            problems.append(f"항목 {i+1}: valuations=dict 필요")
        pa = it.get("prior_adjustment")
        if pa is not None and (isinstance(pa, bool) or not isinstance(pa, int)):
            problems.append(f"항목 {i+1}: prior_adjustment=int 필요, 현재 {pa}")

    if problems:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": problems}

    if not isinstance(items, list) or not items:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["items가 비어 있음"]}

    # ── 기한 계산 ──────────────────────────────────────────────────────────
    if fy_e.month == 12 and fy_e.day == 31:
        change_deadline = date(fy_e.year, 9, 30)
    elif fy_e.month == 3 and fy_e.day == 31:
        change_deadline = date(fy_e.year - 1, 12, 31)
    else:
        change_deadline = _date_sub_months(fy_e, 3)

    if new_corp:
        first_deadline = _date_add_months_last(fy_e, 3)
    else:
        first_deadline = None

    change_dl_str = change_deadline.isoformat()
    first_dl_str = first_deadline.isoformat() if first_deadline else None
    fy_start_str = fy_start
    fy_end_str = fy_end

    # ── 구분별 계산 ──────────────────────────────────────────────────────────
    정산 = []
    구분별 = []
    익금합계 = 0
    손금합계 = 0

    for item in items:
        cat = item["category"]
        name = item.get("name", "")
        재고구분 = name if name else cat
        rm = item["reported_method"]
        rlcm = item.get("reported_lcm", False)
        um = item["used_method"]
        ulcm = item.get("used_lcm", False)
        cr = item.get("change_report")
        bv = item["book_value"]
        vals = item["valuations"]
        prior = item.get("prior_adjustment", 0)

        is_realestate = (cat == "매매목적부동산")

        # ── (가) 유효 신고 방법 결정 ──────────────────────────────────────────
        if rm == "무신고":
            # 무신고 + change_report 있는 경우
            if cr is not None and isinstance(cr, dict):
                fo_str = cr.get("filed_on", "")
                try:
                    fo_date = date.fromisoformat(fo_str)
                except Exception:
                    fo_date = None
                if fo_date is not None:
                    if new_corp:
                        on_time = (fo_date <= first_deadline)
                    else:
                        on_time = (fo_date <= change_deadline)
                    filed_ok = on_time
                else:
                    fo_date = None
                    filed_ok = False
            else:
                fo_date = None
                filed_ok = False

            if filed_ok and cr and cr.get("method") in _METHOD_LITERALS:
                # 기한 내 신고 → (나)로 이어짐 (판정=None)
                eff_method = cr["method"]
                eff_lcm = cr.get("lcm", False)
                판정 = None
            else:
                # 무신고 또는 기한 후 신고 → 무신고 판정
                eff_method = None
                eff_lcm = False
                if cr is not None and isinstance(cr, dict) and fo_date is not None:
                    판정 = "기한후신고(무신고 준용)"
                else:
                    판정 = "무신고"
        else:
            # 신고 방법 있음 → (나)로 이어짐 (판정=None)
            eff_method = None
            eff_lcm = False
            판정 = None

        # ── (나) 신고된 방법대로 평가했는지 판정 ──────────────────────────────
        if 판정 is None:
            # 유효 신고 방법 결정 (변경신고 반영)
            is_late = False
            eff_method = rm
            eff_lcm = rlcm
            if cr is not None and isinstance(cr, dict):
                try:
                    fo_date = date.fromisoformat(cr.get("filed_on", ""))
                    if fo_date <= change_deadline:
                        eff_method = cr.get("method", rm)
                        eff_lcm = cr.get("lcm", rlcm)
                        if cr.get("method") == rm and cr.get("lcm", rlcm) == rlcm:
                            판정 = "신고방법"
                        else:
                            판정 = "변경신고(기한 내)"
                    else:
                        eff_method = cr.get("method", rm)
                        eff_lcm = cr.get("lcm", rlcm)
                        판정 = "기한후변경신고(임의변경)"
                        is_late = True
                except Exception:
                    eff_method = cr.get("method", rm) if cr else rm
                    eff_lcm = cr.get("lcm", rlcm) if cr else rlcm
                    판정 = "신고방법"
            else:
                eff_method = rm
                eff_lcm = rlcm
                판정 = "신고방법"
                # 세방법·평가액 결정 (신고방법과 같음)
                세법상방법 = eff_method
                if eff_lcm:
                    if "시가" not in vals:
                        return {"error": "입력 확인 필요 — 계산하지 않음",
                                "문제": [f"{재고구분}: 저가법 판정에 필요한 valuations['시가'] 없음"]}
                    세법상평가액 = min(vals[eff_method], vals["시가"])
                    이유 = f"신고({eff_method}·저가법)대로 평가, min({eff_method} {vals[eff_method]:,}원, 시가 {vals['시가']:,}원) = {세법상평가액:,}원"
                else:
                    if eff_method not in vals:
                        return {"error": "입력 확인 필요 — 계산하지 않음",
                                "문제": [f"{재고구분}: 신고 방법 판정에 필요한 valuations['{eff_method}'] 없음"]}
                    세법상평가액 = vals[eff_method]
                    이유 = f"신고({eff_method})대로 평가"
                근거 = "법인세법 시행령 제74조①·③"

            # ── 세법상 방법·평가액 결정 ────────────────────────────────────────
            if eff_method is None:
                # 무신고 (위 (가)에서 처리됨)
                세법상방법 = "개별법" if is_realestate else "선입선출법"
                key = "개별법" if is_realestate else "선입선출법"
                if key not in vals:
                    return {"error": "입력 확인 필요 — 계산하지 않음",
                            "문제": [f"{재고구분}: 무신고 판정에 필요한 valuations['{key}'] 없음"]}
                세법상평가액 = vals[key]
                근거 = "법인세법 시행령 제74조④1호"
                if 판정 == "기한후신고(무신고 준용)":
                    근거 = "법인세법 시행령 제74조④1호·⑤"
                이유 = f"신고 없음 → {세법상방법} (영 제74조④1호)"
            elif (eff_method == um) and (eff_lcm == ulcm):
                # 신고한 방법대로 평가 → 신고 방법 적용
                세법상방법 = eff_method
                if eff_lcm:
                    if "시가" not in vals:
                        return {"error": "입력 확인 필요 — 계산하지 않음",
                                "문제": [f"{재고구분}: 저가법 판정에 필요한 valuations['시가'] 없음"]}
                    if is_late:
                        old_rm_val = vals.get(rm, 0)
                        eff_val_new = min(vals[eff_method], vals["시가"])
                        세법상평가액 = max(old_rm_val, eff_val_new)
                        이유 = (f"기한 후 변경신고({eff_method}·저가법)대로 평가 → "
                                f"영 제74조④3호·⑤ max(종전{rm} {old_rm_val:,}원, {eff_method} {eff_val_new:,}원) = {세법상평가액:,}원")
                    else:
                        세법상평가액 = min(vals[eff_method], vals["시가"])
                        이유 = (f"신고({eff_method}·저가법)대로 평가, "
                                f"min({eff_method} {vals[eff_method]:,}원, 시가 {vals['시가']:,}원) = {세법상평가액:,}원")
                else:
                    if eff_method not in vals:
                        return {"error": "입력 확인 필요 — 계산하지 않음",
                                "문제": [f"{재고구분}: 신고 방법 판정에 필요한 valuations['{eff_method}'] 없음"]}
                    if is_late:
                        old_rm_val = vals.get(rm, 0)
                        eff_val_new = vals[eff_method]
                        세법상평가액 = max(old_rm_val, eff_val_new)
                        이유 = (f"기한 후 변경신고({eff_method})대로 평가 → "
                                f"영 제74조④3호·⑤ max(종전{rm} {old_rm_val:,}원, {eff_method} {eff_val_new:,}원) = {세법상평가액:,}원")
                    else:
                        세법상평가액 = vals[eff_method]
                        이유 = f"신고({eff_method})대로 평가"
                근거 = "법인세법 시행령 제74조①·③"
            else:
                # 임의변경 → max(선입선출법(부동산 개별법), 유효 신고 방법 평가액)
                ref_method = "개별법" if is_realestate else "선입선출법"
                if ref_method not in vals:
                    return {"error": "입력 확인 필요 — 계산하지 않음",
                            "문제": [f"{재고구분}: 임의변경 판정에 필요한 valuations['{ref_method}'] 없음"]}
                ref_val = vals[ref_method]
                if eff_lcm:
                    if "시가" not in vals:
                        return {"error": "입력 확인 필요 — 계산하지 않음",
                                "문제": [f"{재고구분}: 임의변경·저가법 판정에 필요한 valuations['시가'] 없음"]}
                    eff_val = min(vals[eff_method], vals["시가"])
                else:
                    eff_val = vals[eff_method]
                세법상평가액 = max(ref_val, eff_val)
                세법상방법 = eff_method
                if 판정 == "기한후변경신고(임의변경)":
                    이유 = (f"회사 평가({um}{'+저가' if ulcm else ''}) ≠ 유효 신고({eff_method}{'+저가' if eff_lcm else ''}) → "
                            f"영 제74조④3호·⑤ max({ref_method} {ref_val:,}원, {eff_method} {eff_val:,}원) = {세법상평가액:,}원")
                else:
                    판정 = "임의변경"
                    이유 = (f"회사 평가({um}{'+저가' if ulcm else ''}) ≠ 유효 신고({eff_method}{'+저가' if eff_lcm else ''}) → "
                            f"영 제74조④2호 단서 max({ref_method} {ref_val:,}원, {eff_method} {eff_val:,}원) = {세법상평가액:,}원")
                근거 = "법인세법 시행령 제74조④2·3호 단서"
        else:
            # 무신고 판정 (위 (가)에서 처리)
            세법상방법 = "개별법" if is_realestate else "선입선출법"
            key = "개별법" if is_realestate else "선입선출법"
            if key not in vals:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"{재고구분}: 무신고 판정에 필요한 valuations['{key}'] 없음"]}
            세법상평가액 = vals[key]
            근거 = "법인세법 시행령 제74조④1호"
            if 판정 == "기한후신고(무신고 준용)":
                근거 = "법인세법 시행령 제74조④1호·⑤"
            이유 = f"신고 없음 → {세법상방법} (영 제74조④1호)"

        # ── 조정액 계산 ───────────────────────────────────────────────────────
        조정액 = 세법상평가액 - bv

        # 구분별 결과
        구분별판정 = 판정 if 판정 else "신고방법"
        구분별방법 = 세법상방법
        구분별.append({
            "재고구분": 재고구분,
            "판정": 구분별판정,
            "세법상_방법": 구분별방법,
            "세법상_평가액": 세법상평가액,
            "회사_평가액": bv,
            "조정액": 조정액,
            "이유": 이유,
            "근거": 근거,
        })

        # 세무조정 항목 구성
        if 조정액 > 0:
            정산.append({
                "재고구분": 재고구분,
                "구분": "재고자산평가감",
                "조정": "익금산입",
                "금액": 조정액,
                "소득처분": "유보",
                "근거": 근거,
                "이유": 이유,
            })
            익금합계 += 조정액
        elif 조정액 < 0:
            정산.append({
                "재고구분": 재고구분,
                "구분": "재고자산평가증",
                "조정": "손금산입",
                "금액": -조정액,
                "소득처분": "△유보",
                "근거": 근거,
                "이유": 이유,
            })
            손금합계 += -조정액

    # ── 전기 유보 추인 (세무조정 목록 앞쪽에 추가) ───────────────────────────
    추인목록 = []
    for item in items:
        prior = item.get("prior_adjustment", 0)
        if prior == 0:
            continue
        cat = item["category"]
        name = item.get("name", "")
        재고구분 = name if name else cat
        if prior > 0:
            추인목록.append({
                "재고구분": 재고구분,
                "구분": "전기 재고자산평가감 추인",
                "조정": "손금산입",
                "금액": prior,
                "소득처분": "△유보",
                "근거": "법인세법 시행령 제74조(전기 유보 추인)",
                "이유": f"전기말 재고자산 평가 유보 {prior:,}원 전액 추인(당기 출고 간주)",
            })
            손금합계 += prior
        else:
            추인목록.append({
                "재고구분": 재고구분,
                "구분": "전기 재고자산평가증 추인",
                "조정": "익금산입",
                "금액": -prior,
                "소득처분": "유보",
                "근거": "법인세법 시행령 제74조(전기 유보 추인)",
                "이유": f"전기말 재고자산 평가 유보 {prior:,}원 전액 추인(당기 출고 간주)",
            })
            익금합계 += -prior

    정산 = 추인목록 + 정산
    순조정액 = 익금합계 - 손금합계

    # ── 최종 결과 구성 ────────────────────────────────────────────────────────
    결과 = {
        "세무조정": 정산,
        "구분별": 구분별,
        "익금산입_합계": 익금합계,
        "손금산입_합계": 손금합계,
        "순조정액": 순조정액,
    }
    계산 = {
        "사업연도": f"{fy_start}~{fy_end}",
        "변경신고_기한": change_dl_str,
        "최초신고_기한": first_dl_str,
        "산식": [f"세법상 평가액 − 회사 장부 평가액 = 조정액 (원 단위)"],
    }
    판단 = [
        {"항목": "변경신고 기한", "결론": f"{change_dl_str} (사업연도 종료일 − 3개월, 영 제74조③2호)", "근거": "법인세법 시행령 제74조③2호"},
        {"항목": "최초 신고기한" if new_corp else "최초 신고기한(해당 없음)",
         "결론": first_dl_str if new_corp else "신설법인 아님",
         "근거": "법인세법 제60조①, 시행령 제74조③1호"} if new_corp else
        {"항목": "최초 신고기한(해당 없음)", "결론": "신설법인 아님", "근거": "해당 없음"},
    ]
    return {
        "결과": 결과,
        "계산": 계산,
        "판단": 판단,
        "근거": "법인세법 제42조①2호·②, 시행령 제73조1호·제74조①~⑥",
    }
