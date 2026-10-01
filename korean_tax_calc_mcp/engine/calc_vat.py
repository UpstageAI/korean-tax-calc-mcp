"""부가가치세 계산(2016년 제1기 ~ 2026년 과세기간 연도표, 기본값은 2026년 1기) — 국세청 2026년 1기 확정 신고안내 예시로 검증. 작성 Mia(윤승미)
플레이북: knowledge/13_부가가치세_신고안내_조사포인트.md. 가공 세금계산서 가산세율은 calc.fake_invoice_rate(발급일).
"""


# ── 과세기간·연도표 (2016년 제1기 ~ 2026년 제1기, 법제처 연혁본 원문 대조 — knowledge/16 '부가가치세 연도표') ──
# 과세기간 인자: 'YYYY-1' | 'YYYY-2' | 'YYYY-MM-DD'(그 날이 속한 과세기간). None이면 현행(2026년) 값 — 기존 호출 호환.
VAT_FIRST, VAT_LAST = (2016, 1), (2026, 2)


class NoYearTable(ValueError):
    """연도표 범위 밖 과세기간 — 계산하지 않음(추정 금지)."""


def _period(p):
    """→ (연도, 기). 'YYYY-1'/'YYYY-2' 또는 'YYYY-MM-DD'."""
    if p is None: return None
    s = str(p)
    if len(s) >= 10: y, h = int(s[:4]), 1 if int(s[5:7]) <= 6 else 2
    else: y, h = int(s[:4]), int(s.split("-")[1])
    if not (VAT_FIRST <= (y, h) <= VAT_LAST): raise NoYearTable(f"부가가치세 연도표 없음: {p}")
    return (y, h)


def _date(d):
    """날짜 인자('YYYY-MM-DD' 또는 과세기간 'YYYY-h' → 그 과세기간 첫날)."""
    if d is None: return None
    s = str(d)
    if len(s) >= 10: _period(s); return s[:10]
    y, h = _period(s); return f"{y}-{'01' if h == 1 else '07'}-01"


# 간주임대료 정기예금이자율(부가령 제65조①, 부가규칙 제47조). 부칙: "시행일이 속하는 과세기간 신고분부터"
# (2024.3.22.·2025.3.21. 개정은 "시행일이 속하는 과세기간에 임대용역을 공급하는 경우부터") → 해당 연도 제1기부터.
DEEMED_RENT_RATE = {2016: 0.018,   # 2016.3.9. 개정(제546호)
                    2017: 0.016,   # 2017.3.10.(제598호)
                    2018: 0.018,   # 2018.3.19.(제662호)
                    2019: 0.021,   # 2019.3.20.(제718호)
                    2020: 0.018,   # 2020.3.13.(제775호)
                    2021: 0.012, 2022: 0.012,  # 2021.3.16.(제846호), 2022년 개정 없음
                    2023: 0.029,   # 2023.3.20.(제973호) 1,000분의 29
                    2024: 0.035,   # 2024.3.22.(제1055호) 1,000분의 35
                    2025: 0.031, 2026: 0.031}  # 2025.3.21.(제1116호) 1,000분의 31, 2026.9.30. 현재 유지


def deemed_rent(deposit, days, year_days=365, rate=None, period=None):
    """간주임대료(부가령 제65조): 보증금 × 정기예금이자율 × 과세기간 일수/연 일수. 이율은 rate > period 연도표 > 현행 3.1%."""
    if rate is None: rate = DEEMED_RENT_RATE[_period(period)[0]] if period else 0.031
    return int(round(deposit * rate * days / year_days, 6))  # 부동소수 오차(예: 3,257,999.9999) 제거 후 원 미만 절사


def bad_debt_vat(amount_incl_vat):
    """대손세액(부가법 제45조①): 대손금액(부가세 포함) × 10/110 — 2016~2026 산식 변경 없음."""
    return int(amount_incl_vat * 10 / 110)


def bad_debt_eligible(supply_date, confirmed_period):
    """대손세액공제 기간 요건(부가령 제87조②): 공급일부터 N년이 지난 날이 속하는 과세기간 확정신고기한까지 대손 확정.
    N = 5년(2015.2.3.), 10년(2020.2.11. 개정, 부칙 제5조: 2020년 제1기에 대손 확정되는 분부터)."""
    cp = _period(confirmed_period); n = 10 if cp >= (2020, 1) else 5
    last = _period(f"{int(supply_date[:4]) + n}{supply_date[4:10]}") if int(supply_date[:4]) + n <= VAT_LAST[0] else (9999, 2)
    return {"공제가능": cp <= last, "기간(년)": n, "근거": "부가령 제87조②" + (" (2020.2.11. 개정 10년)" if n == 10 else " (5년)")}


# 의제매입세액 공제율(부가법 제42조① 표 — 2017.12.19. 법률 개정 전에는 부가령 제84조① 표)
def deemed_input_rate(industry, period=None, individual=True, base=None, sme=True):
    """→ (분자, 분모). industry: '유흥'|'음식점'|'제조_떡방앗간등'|'제조'|'기타'. base=과세기간 과세표준(음식점 개인 2억 이하 특례).
    - 유흥장소 4/104 → 2/102(2019.12.31. 개정, 부칙 제4조: 2020.1.1. 이후 개시 과세기간부터)
    - 음식점 개인 8/108, 과세표준 2억 이하 9/109(2017.12.19. 신설, 2018.1.1. 시행; 일몰 2019→2021→2023→2026.12.31. 연장)
    - 음식점 법인 6/106
    - 제조 과자점·도정·제분·떡방앗간 개인 6/106(2018.12.31. 신설, 2019.1.1. 시행) / 제조 중소·개인 4/104 / 그 밖 2/102"""
    y, h = _period(period) if period else VAT_LAST
    if industry == "유흥": return (2, 102) if y >= 2020 else (4, 104)
    if industry == "음식점":
        if not individual: return (6, 106)
        if y >= 2018 and base is not None and base <= 200_000_000: return (9, 109)
        return (8, 108)
    if industry == "제조_떡방앗간등" and individual and y >= 2019: return (6, 106)
    if industry in ("제조", "제조_떡방앗간등"): return (4, 104) if (individual or sme) else (2, 102)
    return (2, 102)


# 의제매입세액 한도율(부가령 제84조② 단서 한시 특례). (시작 과세기간, 법인, 음식점 개인[1억↓, 2억↓, 2억↑], 그 밖 개인[2억↓, 2억↑])
DEEMED_INPUT_LIMIT = [
    ((2016, 1), 0.35, (0.60, 0.55, 0.45), (0.50, 0.40)),  # 2016.2.17. 개정(부칙 제6조: 2016.1.1. 이후 개시 과세기간), 2017.2.7.·2018.2.13. 기한만 연장
    ((2018, 2), 0.40, (0.65, 0.60, 0.50), (0.55, 0.45)),  # 2018.9.28. 개정·시행(부칙 제2조: 시행 이후 신고분 → 2018년 제2기부터)
    ((2022, 1), 0.50, (0.75, 0.70, 0.60), (0.65, 0.55)),  # 2022.6.30. 개정, 2022.7.1. 시행(부칙 제3조: 시행 이후 확정신고분 → 2022년 제1기 확정부터)
]  # 일몰: 2019.12.31.→2021.12.31.(2020.2.11.)→2023.12.31.(2022.2.15.)→2025.12.31.(2023.12.26.)→2027.12.31.(2025.11.28.) — 공백 없음


def deemed_input_limit_ratio(period, individual, restaurant, base):
    """한도율: 해당 과세기간 면세농산물 관련 과세표준(base) 구간별."""
    p = _period(period)
    row = [r for r in DEEMED_INPUT_LIMIT if r[0] <= p][-1]
    if not individual: return row[1]
    if restaurant: return row[2][0] if base <= 100_000_000 else row[2][1] if base <= 200_000_000 else row[2][2]
    return row[3][0] if base <= 200_000_000 else row[3][1]


def deemed_input(purchase, base, rate_num=None, rate_den=None, limit_ratio=None, period=None, industry=None, individual=True, sme=True):
    """의제매입세액(부가법 제42조): min(면세농산물 매입, 과세표준 × 한도율) × 공제율.
    공제율·한도율을 직접 주거나, period·industry로 연도표에서 찾음."""
    if rate_num is None: rate_num, rate_den = deemed_input_rate(industry, period, individual, base, sme)
    if limit_ratio is None: limit_ratio = deemed_input_limit_ratio(period, individual, industry == "음식점", base)
    return int(min(purchase, base * limit_ratio) * rate_num / rate_den)


def recycled_scrap(base, invoice_purchase, receipt_purchase):
    """재활용폐자원(조특법 제108조): 한도 = 과세표준 × 80% − 세금계산서 매입, 공제 = min(영수증 매입, 한도) × 3/103."""
    limit = max(0, base * 0.8 - invoice_purchase)
    return {"한도": int(limit), "공제": int(min(receipt_purchase, limit) * 3 / 103)}


# 간이과세 — 2021.7.1. 전후 산식이 다름(법률 제17653호 부칙 제10조: 2021.7.1. 전 공급받은 분 종전, 영 제31445호 부칙 제17조)
def simplified_tax(supply_incl_vat, value_added_rate, invoice_purchase_incl_vat, period=None):
    """간이과세자 납부세액(부가법 제63조).
    2021.7.1. 이후: 공급대가 × 업종별 부가가치율 × 10% − 세금계산서 등 수취 공급대가 × 0.5%.
    2021.6.30. 이전(period 지정): 공급대가 × 부가가치율 × 10% − 세금계산서 등 매입세액(공급대가 × 10/110) × 부가가치율(구 제63조③1호)."""
    tax = int(supply_incl_vat * value_added_rate * 0.1)
    if period and _date(period) < "2021-07-01":
        return tax - int(int(invoice_purchase_incl_vat * 10 / 110) * value_added_rate)
    return tax - int(invoice_purchase_incl_vat * 0.005)


def simplified_threshold(on):
    """간이과세 기준금액(부가법 제61조①, 부가령 제109조①): 직전 연도 공급대가.
    4,800만(~2021.6.30.) → 8,000만(2020.12.22. 법·2021.2.17. 영, 2021.7.1. 적용기간부터) → 1억400만(2024.2.29. 영, 부칙 제10조: 2024.7.1.~ 적용기간부터)."""
    d = _date(on)
    return 48_000_000 if d < "2021-07-01" else 80_000_000 if d < "2024-07-01" else 104_000_000


def simplified_exempt_threshold(year):
    """간이과세자 납부의무 면제 기준(부가법 제69조①, 과세기간 공급대가 미만).
    2,400만(~2017) → 3,000만(2018.12.31. 개정, 부칙 제6조: 시행 이후 신고분 → 2018 과세기간 확정신고부터) → 4,800만(2020.12.22. 개정, 부칙 제13조: 2021 과세기간부터)."""
    _period(f"{year}-1")
    return 24_000_000 if year <= 2017 else 30_000_000 if year <= 2020 else 48_000_000


# 세금계산서 등 가산세율(부가법 제60조). 경과조치가 "공급하는 분"(2016.12.20. 부칙 제5조, 2018.12.31. 부칙 제10조) → 공급일 기준.
def invoice_penalty_rate(kind, supplied_on=None, designated_individual=False):
    """kind: 지연발급·미발급·미발급_종이(전자 의무자가 종이 발급)·지연전송·미전송·지연수취·매출처별합계표_미제출·매출처별합계표_예정분확정제출·
    신용카드매입공제(⑤1호). supplied_on=공급일(없으면 현행). designated_individual=구 제60조②3·4호 단서 '대통령령으로 정하는 개인사업자'(2016년 공급분 0.1%·0.3%)."""
    d = _date(supplied_on) or "2026-12-31"
    if kind == "지연발급": return 0.01                                          # ②1호, 2016~2026 1%
    if kind == "미발급": return 0.02                                            # ②2호
    if kind == "미발급_종이": return 0.01                                       # ②2호 단서(2020~ 가목)
    if kind == "지연전송":
        if d < "2017-01-01" and designated_individual: return 0.001
        return 0.005 if d < "2019-01-01" else 0.003                            # ②3호, 2018.12.31. 개정
    if kind == "미전송":
        if d < "2017-01-01" and designated_individual: return 0.003
        return 0.01 if d < "2019-01-01" else 0.005                             # ②4호
    if kind == "지연수취": return 0.01 if d < "2017-01-01" else 0.005          # ⑦1호, 2016.12.20. 개정
    if kind == "매출처별합계표_미제출": return 0.01 if d < "2017-01-01" else 0.005   # ⑥1·2호
    if kind == "매출처별합계표_예정분확정제출": return 0.005 if d < "2017-01-01" else 0.003  # ⑥3호
    if kind == "신용카드매입공제": return 0.01 if d < "2019-01-01" else 0.005  # ⑤(1호), 2018.12.31. 개정(공급받는 분)
    raise KeyError(kind)


def invoice_penalties(supply, kind, supplied_on=None, designated_individual=False):
    """세금계산서 관련 가산세(부가법 제60조②⑤⑥⑦). 공급일 없으면 현행(지연전송 0.3%, 미전송 0.5%, 지연발급 1%, 지연수취 0.5%, 미발급 2%)."""
    return int(supply * invoice_penalty_rate(kind, supplied_on, designated_individual))


# 신용카드매출전표 등 발행세액공제(부가법 제46조①)
def card_sales_credit(amount, supplied_on, simplified_food_lodging=False, used_this_year=0):
    """공제율: 1.3%(간이 음식·숙박 2.6%) — 간이 음식·숙박 2.6% 구분은 2020.12.22. 삭제(부칙 제8조: 2021.7.1. 이후 공급분 1.3%).
    한시 1.3%·2.6% 일몰 2016.12.31.→2018→2021→2023→2026.12.31. 연장(공백 없음).
    연간 한도: 500만(2016·2017) → 1,000만(2018.12.31. 개정, 부칙 제4조: 시행 이후 신고분 → 2018년 제2기 확정신고분부터, 2026.12.31.까지).
    used_this_year = 같은 연도 이미 공제받은 금액."""
    d = _date(supplied_on); y = int(d[:4])
    rate = 0.026 if (simplified_food_lodging and d < "2021-07-01") else 0.013
    cap = 5_000_000 if (y <= 2017 or (y == 2018 and d < "2018-07-01")) else 10_000_000
    return int(max(0, min(amount * rate, cap - used_this_year)))


def late_payment_rate_segments(start, days):
    """납부지연 1일 이자율(국기령 제27조의4): 1만분의 3(~2019.2.11.) → 10만분의 25(2019.2.12.) → 10만분의 22(2022.2.15.).
    경과조치(2019.2.12. 부칙 제9조, 2022.2.15. 부칙 제6조): 시행일 전 기간분은 종전 이율 → 기간 안분. start=기산일(납부기한 다음 날)."""
    from datetime import date, timedelta
    s = date.fromisoformat(start); e = s + timedelta(days=days)
    cuts = [(date(1900, 1, 1), 0.0003), (date(2019, 2, 12), 0.00025), (date(2022, 2, 15), 0.00022)]
    out = []
    for i, (c, r) in enumerate(cuts):
        nxt = cuts[i + 1][0] if i + 1 < len(cuts) else date(9999, 1, 1)
        a, b = max(s, c), min(e, nxt)
        if b > a: out.append(((b - a).days, r))
    return out


def late_payment(unpaid, days, start=None):
    """국기법 제47조의4 납부지연. start 없으면 1일 0.022%, 있으면 이율 변경일로 기간 안분."""
    if not start: return int(unpaid * 0.00022 * days)
    return int(round(sum(unpaid * r * n for n, r in late_payment_rate_segments(start, days)), 6))  # 부동소수 오차 제거 후 절사


def cash_sales_statement(unreported): return int(unreported * 0.01)  # 부가법 제60조⑧ 현금매출명세서 1%(2016~2026 동일)


# ── 간이과세자 업종별 부가가치율(부가령 제111조②, 2021.2.17. 개정, 2026.6.30. 시행 원문 대조) ──
VALUE_ADDED_RATE = {"소매업": 0.15, "재생용 재료수집 및 판매업": 0.15, "음식점업": 0.15,
                    "제조업": 0.20, "농업·임업 및 어업": 0.20, "소화물 전문 운송업": 0.20,
                    "숙박업": 0.25,
                    "건설업": 0.30, "운수 및 창고업": 0.30, "정보통신업": 0.30,
                    "금융 및 보험 관련 서비스업": 0.40, "전문·과학 및 기술서비스업": 0.40, "사업시설관리·사업지원 및 임대서비스업": 0.40,
                    "부동산 관련 서비스업": 0.40, "부동산임대업": 0.40,
                    "그 밖의 서비스업": 0.30}
# 주의: 전문·과학 및 기술서비스업 중 인물사진 및 행사용 영상 촬영업은 40%에서 제외(→ 그 밖의 서비스업 30%)

# 2021.6.30. 이전 공급분(영 제31445호 부칙 제17조) — 개정 전 부가령 제111조②(2016.1.1.~2021.6.30. 시행본 동일)
VALUE_ADDED_RATE_OLD = {"전기·가스·증기 및 수도 사업": 0.05,
                        "소매업": 0.10, "재생용 재료수집 및 판매업": 0.10, "음식점업": 0.10,
                        "제조업": 0.20, "농업·임업 및 어업": 0.20, "숙박업": 0.20, "운수 및 통신업": 0.20,
                        "건설업": 0.30, "부동산임대업": 0.30, "그 밖의 서비스업": 0.30}


def value_added_rate(industry, period=None):
    if period and _date(period) < "2021-07-01":
        if industry not in VALUE_ADDED_RATE_OLD:
            raise KeyError(f"{industry}: 2021.7.1. 전 부가가치율 표(구 영 제111조②)의 업종 구분이 아님 — 수기 대사 필요")
        return VALUE_ADDED_RATE_OLD[industry]
    if industry in ("인물사진 및 행사용 영상 촬영업",): return 0.30
    return VALUE_ADDED_RATE[industry]


def mixed_value_added_rate(parts):
    """공통사용 재화 공급 시 업종별 실지귀속 불명(부가령 제111조⑤): Σ 업종 부가가치율 × 업종 공급대가/총공급대가. parts=[(업종, 공급대가)]."""
    tot = sum(v for _, v in parts)
    return sum(value_added_rate(k) * v / tot for k, v in parts)


# ── 공통매입세액 안분·정산·재계산(부가법 제40·41조, 부가령 제81~83조, 별지 제22호 3·4·5번) ──
def common_input_allocation(common_tax, total_supply, exempt_supply, no_supply_basis=None):
    """안분(부가령 제81조): 불공제 = 공통매입세액 × 면세공급가액/총공급가액(별지22 ⑭ = ⑪×⑬÷⑫).
    ② 전액 공제: 1호 면세비율 5% 미만(공통매입세액 500만원 이상 제외), 2호 공통매입세액 5만원 미만.
    ④ 과세·면세 중 공급가액이 없으면 no_supply_basis=(기준명, 면세분, 총계) — 매입가액→예정공급가액→예정사용면적 순서
       (건물·구축물로 예정사용면적 구분 가능하면 면적 우선). 확정 과세기간에 제82조 정산."""
    if common_tax < 50_000:
        return {"불공제": 0, "근거": "부가령 제81조②2호: 공통매입세액 5만원 미만 전액 공제"}
    if total_supply and exempt_supply and exempt_supply < total_supply:
        ratio = exempt_supply / total_supply
        if ratio < 0.05 and common_tax < 5_000_000:
            return {"불공제": 0, "면세비율": ratio, "근거": "부가령 제81조②1호: 면세비율 5% 미만(공통매입세액 500만원 미만) 전액 공제"}
        return {"불공제": int(common_tax * ratio), "면세비율": ratio, "근거": "부가령 제81조①"}
    if not no_supply_basis:
        return {"불공제": None, "근거": "부가령 제81조④: 공급가액 한쪽이 없음 — 매입가액·예정공급가액·예정사용면적 기준 필요"}
    name, ex, tot = no_supply_basis
    ratio = ex / tot
    return {"불공제": int(common_tax * ratio), "면세비율": ratio, "근거": f"부가령 제81조④({name} 기준), 확정 시 제82조 정산 대상"}


def common_input_settlement(total_common_tax, final_exempt_ratio, already_disallowed):
    """정산(부가령 제82조, 별지22 ⑮~⑲): 불공제 총액 = 총공통매입세액 × 확정 면세비율, 가산(+)·공제(−) = 총액 − 기불공제."""
    total = int(total_common_tax * final_exempt_ratio)
    return {"불공제 총액": total, "기불공제": already_disallowed, "가산또는공제": total - already_disallowed}


def elapsed_periods(acquired, current):
    """경과된 과세기간 수(부가령 제83조⑤·제66조②): 취득일이 속한 과세기간 개시일에 취득한 것으로 보고 과세기간(반기) 단위로 셈.
    acquired/current = 'YYYY-MM-DD'(current는 재계산하는 과세기간 안의 날짜)."""
    p = lambda s: int(s[:4]) * 2 + (0 if int(s[5:7]) <= 6 else 1)
    return p(current) - p(acquired)


def common_input_recalc(input_tax, asset, acquired, current, prior_ratio, current_ratio):
    """재계산(부가법 제41조, 부가령 제83조, 별지22 ⑳~㉓): 감가상각자산, 면세비율 차이 5% 이상일 때만.
    가산(+)·공제(−) = 매입세액 × [1 − (5% 건물·구축물 | 25% 그 밖) × 경과 과세기간 수] × (당기 면세비율 − 직전 적용 비율).
    경과 과세기간 수 상한: 건물 20, 그 밖 4(제66조② 후단 준용). prior_ratio = 취득 과세기간(또는 마지막 재계산 과세기간) 비율."""
    diff = current_ratio - prior_ratio
    if abs(diff) < 0.05:
        return {"재계산": 0, "근거": "부가령 제83조①: 비율 차이 5% 미만 — 재계산 대상 아님", "차이": diff}
    bldg = asset in ("건물", "구축물")
    n = min(elapsed_periods(acquired, current), 20 if bldg else 4)
    reduce = max(0.0, 1 - (0.05 if bldg else 0.25) * n)
    return {"재계산": int(round(input_tax * reduce * diff, 6)), "경감률": reduce, "경과과세기간": n, "차이": diff,
            "근거": "부가법 제41조, 부가령 제83조②" + ("1호" if bldg else "2호")}
