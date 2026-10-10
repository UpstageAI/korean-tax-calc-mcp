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
_REV_OLD = [(10_000_000_000, 0.002), (50_000_000_000, 0.001), (math.inf, 0.0003)]                          # 제25조 2019까지
_REV_NEW = [(10_000_000_000, 0.003), (50_000_000_000, 0.002), (math.inf, 0.0003)]                          # 2020~(법률 16833 부칙§2)
_REV_2020 = [(10_000_000_000, 0.0035), (50_000_000_000, 0.0025), (math.inf, 0.0006)]                       # 조특법 제136조④ 2020 지출분
_MIN_TAX = {"중소": 0.07, "유예1_3": 0.08, "유예4_5": 0.09,
            "일반": [(10_000_000_000, 0.10), (100_000_000_000, 0.12), (math.inf, 0.17)]}                   # 조특법 제132조① 2016~2025 동일


def _year(y):
    """사업연도 y의 표. 각 값의 조문·부칙 근거는 knowledge/16 '법인 연도표' 표."""
    d = {"세율": _T_OLD if y <= 2017 else _T_25 if y <= 2022 else _T_24,
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
    if y >= 2025: d["세율_소규모"] = [(20_000_000_000, 0.19), (300_000_000_000, 0.21), (math.inf, 0.24)]  # 제55조①2호, 법률 20613 부칙§5
    return d


YEAR = {y: _year(y) for y in range(2016, 2026)}


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
    year 지정: 연도표(YEAR[year]['최저한세']) 사용 — 2016~2025 원문 동일. year=None은 같은 값(종전 호출 유지)."""
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
