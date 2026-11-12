"""부가가치세 계산(2016년 제1기 ~ 2026년 과세기간 연도표, 기본값은 2026년 1기) — 국세청 2026년 1기 확정 신고안내 예시로 검증. 작성 Mia(윤승미)
플레이북: knowledge/13_부가가치세_신고안내_조사포인트.md. 가공 세금계산서 가산세율은 calc.fake_invoice_rate(발급일).
"""

import calendar

from .errors import NoYearTable
from .exact import exact as _x, floor_won as _floor, trunc_won as _trunc


# ── 과세기간·연도표 (2016년 제1기 ~ 2026년 제1기, 법제처 연혁본 원문 대조 — knowledge/16 '부가가치세 연도표') ──
# 과세기간 인자: 'YYYY-1' | 'YYYY-2' | 'YYYY-MM-DD'(그 날이 속한 과세기간). None이면 현행(2026년) 값 — 기존 호출 호환.
VAT_FIRST, VAT_LAST = (2016, 1), (2026, 2)


def _period(p):
    """→ (연도, 기). 'YYYY-1'/'YYYY-2' 또는 'YYYY-MM-DD'."""
    if p is None: return None
    s = str(p).strip()
    try:
        if len(s) >= 10: y, h = int(s[:4]), 1 if int(s[5:7]) <= 6 else 2
        else:
            a, b = s.split("-")
            y, h = int(a), int(b)
            if len(a) != 4 or h not in (1, 2): raise ValueError
    except ValueError:
        raise ValueError(f"과세기간 {p!r} — 'YYYY-1'(제1기)·'YYYY-2'(제2기) 또는 그 기간의 날짜 'YYYY-MM-DD'") from None
    if not (VAT_FIRST <= (y, h) <= VAT_LAST): raise NoYearTable(f"부가가치세 연도표 없음: {p}")
    return (y, h)


def _validate_period(period):
    """period가 'YYYY-1'·'YYYY-2' 형식인지 검증. 아니면 error dict 반환, 맞으면 None."""
    import re
    if not isinstance(period, str) or not re.fullmatch(r"\d{4}-(1|2)", period):
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"period '{period}' — 'YYYY-1' 또는 'YYYY-2' 형식(4자리 연도)으로 입력 필요"]}
    return None


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


def deemed_rent(deposit, days, year_days=None, rate=None, period=None):
    """간주임대료(부가령 제65조): 보증금 × 정기예금이자율 × 과세기간 일수/연 일수. 연 일수는 윤년이면 366, 아니면 365(부가령 제65조①). 이율은 rate > period 연도표 > 현행 3.1%."""
    y = _period(period)[0] if period else 2026
    if year_days is None:
        year_days = 366 if calendar.isleap(y) else 365
    if rate is None: rate = DEEMED_RENT_RATE[y] if period else 0.031
    return _floor(deposit, rate, days, div=year_days)  # 원 미만 절사(분수 계산이라 3,257,999.9999 같은 오차 없음)


def bad_debt_vat(amount_incl_vat):
    """대손세액(부가법 제45조①): 대손금액(부가세 포함) × 10/110 — 2016~2026 산식 변경 없음."""
    return int(amount_incl_vat * 10 / 110)


def bad_debt_eligible(supply_date, confirmed_period):
    """대손세액공제 기간 요건(부가령 제87조②): 공급일부터 N년이 지난 날이 속하는 과세기간 확정신고기한까지 대손 확정.
    N = 5년(2015.2.3.), 10년(2020.2.11. 개정, 부칙 제5조: 2020년 제1기에 대손 확정되는 분부터)."""
    # confirmed_period를 파싱(연도표 범위 검사 없이)
    s = str(confirmed_period).strip()
    if len(s) >= 10:
        cp_y, cp_h = int(s[:4]), 1 if int(s[5:7]) <= 6 else 2
    else:
        a, b = s.split("-")
        cp_y, cp_h = int(a), int(b)
    n = 10 if (cp_y, cp_h) >= (2020, 1) else 5
    last_y = int(supply_date[:4]) + n
    last = (last_y, _period(f"{last_y}{supply_date[4:10]}")[1]) if last_y <= VAT_LAST[0] else (9999, 2)
    return {"공제가능": (cp_y, cp_h) <= last, "기간(년)": n, "근거": "부가령 제87조②" + (" (2020.2.11. 개정 10년)" if n == 10 else " (5년)")}


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
    공제율·한도율을 직접 주거나, period·industry로 연도표에서 찾음.
    limit_ratio=None이고 base=0이면 한도 없이 purchase 전체를 사용."""
    if rate_num is None: rate_num, rate_den = deemed_input_rate(industry, period, individual, base, sme)
    if limit_ratio is None:
        if base == 0:
            limit_ratio = float('inf')  # 한도 없음
        else:
            limit_ratio = deemed_input_limit_ratio(period, individual, industry == "음식점", base)
    cap = purchase if limit_ratio == float('inf') else min(_x(purchase), _x(base) * _x(limit_ratio))
    return _floor(cap, rate_num, div=rate_den)


def recycled_scrap(base, invoice_purchase, receipt_purchase):
    """재활용폐자원(조특법 제108조): 한도 = 과세표준 × 80% − 세금계산서 매입, 공제 = min(영수증 매입, 한도) × 3/103."""
    limit = max(0, _x(base) * _x(0.8) - invoice_purchase)
    return {"한도": _floor(limit), "공제": _floor(min(receipt_purchase, limit), 3, div=103)}


# 간이과세 — 2021.7.1. 전후 산식이 다름(법률 제17653호 부칙 제10조: 2021.7.1. 전 공급받은 분 종전, 영 제31445호 부칙 제17조)
def simplified_tax(supply_incl_vat, value_added_rate, invoice_purchase_incl_vat, period=None):
    """간이과세자 납부세액(부가법 제63조).
    2021.7.1. 이후: 공급대가 × 업종별 부가가치율 × 10% − 세금계산서 등 수취 공급대가 × 0.5%.
    2021.6.30. 이전(period 지정): 공급대가 × 부가가치율 × 10% − 세금계산서 등 매입세액(공급대가 × 10/110) × 부가가치율(구 제63조③1호)."""
    tax = _floor(supply_incl_vat, value_added_rate, 0.1)
    if period and _date(period) < "2021-07-01":
        return tax - _floor(_floor(invoice_purchase_incl_vat, 10, div=110), value_added_rate)
    return tax - _floor(invoice_purchase_incl_vat, 0.005)


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
    return _floor(supply, invoice_penalty_rate(kind, supplied_on, designated_individual))


# 신용카드매출전표 등 발행세액공제(부가법 제46조①)
def card_sales_credit(amount, supplied_on, simplified_food_lodging=False, used_this_year=0):
    """공제율: 1.3%(간이 음식·숙박 2.6%) — 간이 음식·숙박 2.6% 구분은 2020.12.22. 삭제(부칙 제8조: 2021.7.1. 이후 공급분 1.3%).
    한시 1.3%·2.6% 일몰 2016.12.31.→2018→2021→2023→2026.12.31. 연장(공백 없음).
    연간 한도: 500만(2016·2017) → 1,000만(2018.12.31. 개정, 부칙 제4조: 시행 이후 신고분 → 2018년 제2기 확정신고분부터, 2026.12.31.까지).
    used_this_year = 같은 연도 이미 공제받은 금액."""
    d = _date(supplied_on); y = int(d[:4])
    rate = 0.026 if (simplified_food_lodging and d < "2021-07-01") else 0.013
    cap = 5_000_000 if (y <= 2017 or (y == 2018 and d < "2018-07-01")) else 10_000_000
    return _floor(max(0, min(_x(amount) * _x(rate), cap - used_this_year)))


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
    if not start: return _floor(unpaid, 0.00022, days)
    return _floor(sum(_x(unpaid) * _x(r) * n for n, r in late_payment_rate_segments(start, days)))  # 분수로 합한 뒤 원 미만 절사


def cash_sales_statement(unreported): return _floor(unreported, 0.01)  # 부가법 제60조⑧ 현금매출명세서 1%(2016~2026 동일)


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
        return {"불공제": _floor(common_tax, exempt_supply, div=total_supply), "면세비율": ratio, "근거": "부가령 제81조①"}
    if not no_supply_basis:
        return {"불공제": None, "근거": "부가령 제81조④: 공급가액 한쪽이 없음 — 매입가액·예정공급가액·예정사용면적 기준 필요"}
    name, ex, tot = no_supply_basis
    ratio = ex / tot
    return {"불공제": _floor(common_tax, ex, div=tot), "면세비율": ratio, "근거": f"부가령 제81조④({name} 기준), 확정 시 제82조 정산 대상"}


def common_input_settlement(total_common_tax, final_exempt_ratio, already_disallowed):
    """정산(부가령 제82조, 별지22 ⑮~⑲): 불공제 총액 = 총공통매입세액 × 확정 면세비율, 가산(+)·공제(−) = 총액 − 기불공제."""
    total = _floor(total_common_tax, final_exempt_ratio)
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
    return {"재계산": _trunc(input_tax, 1 - (_x(0.05) if bldg else _x(0.25)) * n, round(diff, 10)) if reduce > 0 else 0, "경감률": reduce, "경과과세기간": n, "차이": diff,
            "근거": "부가법 제41조, 부가령 제83조②" + ("1호" if bldg else "2호")}


# ── 부가세 판정 도구: 매입세액 공제 판정(부가법 제38조·제39조·제46조, 영 제75조) ──

_VALID_NATURE = {"일반", "접대", "비영업용승용차", "토지관련", "면세사업", "사업무관"}
_VALID_EVIDENCE = {"세금계산서", "신용카드", "현금영수증", "영수증"}
_VALID_SUPPLIER = {"일반과세자", "간이과세자_세금계산서", "간이과세자_영수증"}


def _is_late_invoice_deduction(supply_date, issue_date, period, filing, 발급특례=True):
    """발급일 기준 공제 여부 판정(영 제75조3호·7호).
    supply_date·issue_date는 'YYYY-MM-DD'. period='YYYY-1'|'YYYY-2', filing='예정'|'확정'.
    발급특례=True면 발급기한=공급시기 다음 달 10일(법 제34조③), False면 공급시기 당일.
    반환: (공제여부, 판단메시지, 지연수취여부)."""
    from datetime import date
    from .calc_deadline import roll as _roll

    sd = date.fromisoformat(supply_date)
    id_ = date.fromisoformat(issue_date)

    # 발급기한 계산
    if 발급특례:
        # 공급시기의 다음 달 10일
        m = sd.month + 1
        y = sd.year
        if m > 12:
            m = 1
            y += 1
        발급기한 = date(y, m, 10)
    else:
        # 공급시기 당일
        발급기한 = sd

    # 발급기한이 토·일·공휴일이면 다음 날로 이월(국세기본법 제5조①)
    rolled = _roll(발급기한)
    발급기한 = rolled["날짜"]

    # 확정신고기한 — 공급시기가 속하는 과세기간의 확정신고기한(예정신고에서도 같음, 영 제75조3호·7호)
    확정신고기한 = date(sd.year, 7, 25) if sd.month <= 6 else date(sd.year + 1, 1, 25)

    # 확정신고기한 뒤 발급분(영 제75조7호)은 공급시기별로 다름:
    #  - 2019.2.11.까지 공급분: 7호 없음 → 확정신고기한 뒤 발급분은 불공제
    #  - 2019.2.12.~2022.2.14. 공급분: 확정신고기한 다음 날부터 6개월 이내(2019.2.12. 신설, 영 제29535호 부칙 제2조 — 시행 이후 공급받는 분부터)
    #  - 2022.2.15. 이후 공급분: 1년 이내(영 제32419호 부칙 제10조 — 시행 전 공급분은 종전)
    if sd < date(2019, 2, 12):
        oya, 기간 = 확정신고기한, None
    elif sd < date(2022, 2, 15):
        oya = date(확정신고기한.year + 1, 1, 25) if 확정신고기한.month == 7 else date(확정신고기한.year, 7, 25)
        기간 = "6개월"
    else:
        oya, 기간 = 확정신고기한.replace(year=확정신고기한.year + 1), "1년"

    if id_ <= sd or id_ <= 발급기한:
        # 정상: 발급일 ≤ 공급시기(선발급 포함) 또는 발급일 ≤ 발급기한
        return True, None, False
    elif 발급기한 < id_ <= 확정신고기한:
        # 지연수취(법 제60조⑦1호, 영 제75조3호): 발급기한 < 발급일 ≤ 확정신고기한
        return True, f"지연수취 — 가산세 대상(법 제60조⑦1호, 영 제75조3호)", True
    elif 확정신고기한 < id_ <= oya:
        # 지연수취(영 제75조7호): 확정신고기한 < 발급일 ≤ 확정신고기한 + 6개월(2022.2.15. 이후 공급분 1년) — 공제는 수정신고·경정청구서 제출 또는 결정·경정이 있어야(7호 각 목)
        return True, f"지연수취 — 가산세 대상(법 제60조⑦), 확정신고기한 뒤 {기간} 이내 발급분 공제는 수정신고·경정청구 또는 결정·경정이 있는 경우에 한함(영 제75조7호)", True
    elif 기간 is None:
        return False, (f"발급일이 확정신고기한({확정신고기한.isoformat()}) 뒤 — 불공제(법 제39조①2호). 확정신고기한 뒤 발급분을 공제하는 영 제75조7호는 "
                       "2019.2.12. 이후 공급받는 분부터(영 제29535호 부칙 제2조)"), False
    else:
        # 불공제(법 제39조①2호, 영 제75조)
        return False, (f"발급일이 확정신고기한({확정신고기한.isoformat()})으로부터 {기간} 초과 — 불공제(법 제39조①2호, 영 제75조7호"
                       + ("; 2022.2.14.까지 공급분은 6개월, 영 제32419호 부칙 제10조" if 기간 == "6개월" else "") + ")"), False


def vat_input_tax_deduction(period, filing, items):
    """매입세액 공제 판정(부가법 제38조·제39조·제46조, 영 제75조).
    입력: period='YYYY-1'|'YYYY-2', filing='예정'|'확정', items=[{항목, 증빙, 공급가액?|공급대가?, 성격,
           공급자?, 공급시기?, 발급일?, 발급특례?, 실제공급가액?}].
    결과: {공제매입세액, 불공제매입세액, 지연수취_가산세}, 계산.항목별: [{항목, 세액, 공제세액, 불공제사유?}], 판단: [{항목, 결론, 근거}]."""
    if filing not in ("예정", "확정"):
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"filing='{filing}'은(는) 지원하지 않음 — '예정' 또는 '확정'"]}
    pv = _validate_period(period)
    if pv: return pv
    _period(period)

    항목들 = []
    for it in items:
        항목 = it.get("항목", "")
        증빙 = it.get("증빙", "")
        성격 = it.get("성격", "")
        공급자 = it.get("공급자", "일반과세자")
        공급시기 = it.get("공급시기")
        발급일 = it.get("발급일")
        발급특례 = it.get("발급특례", True)
        실제공급가액 = it.get("실제공급가액")
        공급가액 = it.get("공급가액")
        공급대가 = it.get("공급대가")

        문제 = []
        # 음수 금액 검증
        for key, val in (("공급가액", 공급가액), ("공급대가", 공급대가), ("실제공급가액", 실제공급가액)):
            if val is not None and val < 0:
                문제.append(f"항목 '{항목}': {key}={val} — 음수 입력 불가")
        if 증빙 not in _VALID_EVIDENCE:
            문제.append(f"증빙='{증빙}'은(는) 허용값이 아님 — 허용: {sorted(_VALID_EVIDENCE)}")
        if 성격 not in _VALID_NATURE:
            문제.append(f"성격='{성격}'은(는) 허용값이 아님 — 허용: {sorted(_VALID_NATURE)}")
        if 공급자 not in _VALID_SUPPLIER:
            문제.append(f"공급자='{공급자}'은(는) 허용값이 아님 — 허용: {sorted(_VALID_SUPPLIER)}")
        if 공급가액 is None and 공급대가 is None:
            문제.append("공급가액·공급대가 모두 없음 — 하나 이상 입력 필요")
        if 문제:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
        항목들.append(it)

    calc_items = []
    판단 = []
    주의 = []
    공제합계 = 0
    불공제합계 = 0
    지연수취_가산세_합계 = 0

    for it in 항목들:
        항목 = it["항목"]
        증빙 = it["증빙"]
        성격 = it["성격"]
        공급자 = it.get("공급자", "일반과세자")
        공급시기 = it.get("공급시기")
        발급일 = it.get("발급일")
        발급특례 = it.get("발급특례", True)
        실제공급가액 = it.get("실제공급가액")
        공급가액 = it.get("공급가액")
        공급대가 = it.get("공급대가")

        불공제사유 = None
        판단문 = ""
        지연수취 = False
        항목_공급가액 = None  # 지연수취 가산세 계산을 위한 공급가액

        # 1. 성격별 불공제
        if 성격 == "접대":
            불공제사유 = "법 제39조①6호: 접대비 — 매입세액 불공제"
        elif 성격 == "비영업용승용차":
            불공제사유 = "법 제39조①5호: 비영업용 소형승용차(사업용 제외) 관련 매입세액 불공제"
        elif 성격 == "토지관련":
            불공제사유 = "법 제39조①7호·영 제80조: 토지 조성·형질변경 및 철거 목적 건물 취득·철거비 관련 매입세액 불공제"
        elif 성격 == "면세사업":
            불공제사유 = "법 제39조①7호: 면세사업 관련 매입세액 불공제"
        elif 성격 == "사업무관":
            불공제사유 = "법 제39조①4호: 사업과 직접 관련 없는 지출에 대한 매입세액 불공제"

        # 2. 증빙 '영수증'
        if not 불공제사유 and 증빙 == "영수증":
            불공제사유 = "법 제39조①2호 취지: 적격증빙 아닌 영수증 — 매입세액 불공제"

        # 3. 신용카드·현금영수증 + 간이과세자_영수증
        if not 불공제사유 and 증빙 in ("신용카드", "현금영수증") and 공급자 == "간이과세자_영수증":
            불공제사유 = "법 제46조③ 단서·영 제88조⑤: 신규 간이과세자 영수증 발급분 — 매입세액 불공제"
        # 3-2. 간이과세자가 발급한 신용카드매출전표·현금영수증: 2021.6.30.까지 공급분은 전부 불공제
        #      (법 제46조③ 2020.12.22. 개정 전 "일반과세자로부터", 2021.7.1. 시행 — 법률 제17653호 부칙 제1조)
        if not 불공제사유 and 증빙 in ("신용카드", "현금영수증") and 공급자 == "간이과세자_세금계산서":
            if 공급시기:
                전 = 공급시기 < "2021-07-01"
            else:
                전 = period <= "2021-1"      # 공급시기가 없으면 과세기간으로: 2021년 제1기까지는 2021.6.30. 이전 공급
            if 전:
                불공제사유 = ("법 제46조③(2020.12.22. 개정 전): 2021.6.30.까지 공급분은 일반과세자가 발급한 신용카드매출전표·현금영수증만 공제 — "
                          "간이과세자 발급분 매입세액 불공제")

        # 4. 세금계산서 + 공급시기·발급일 있는 경우
        if not 불공제사유 and 증빙 == "세금계산서" and 공급시기 and 발급일:
            공제, msg, 지연수취 = _is_late_invoice_deduction(공급시기, 발급일, period, filing, 발급특례)
            if not 공제:
                불공제사유 = msg
            elif msg:
                판단문 = msg
                if "영 제75조7호" in msg:
                    주의.append(f"'{항목}': 확정신고기한 뒤 {'6개월' if 공급시기 < '2022-02-15' else '1년'} 안에 발급받은 세금계산서 — 매입세액 공제는 수정신고·경정청구서를 낼 때 함께 제출하거나 "
                              "결정·경정이 있는 경우에 한함(영 제75조7호). 그 절차 없이 해당 신고에서 바로 공제하지 못함. 지연수취 가산세(법 제60조⑦)는 별도")

        # 세액 계산
        if 실제공급가액 is not None:
            세액 = 실제공급가액 * 10 // 100
            if 불공제사유:
                # 다른 불공제 사유가 우선 — 공제세액 0, 착오 기재 문장은 결론 문구로 쓰지 않음
                공제세액 = 0
            else:
                # 실제공급가액으로 공제되는 착오 기재 항목 — 불공제사유는 None, 판단문만 그 문장
                판단문 = "착오 기재 — 그 밖의 증빙으로 실제 거래 확인 시 실제분 공제 (영 제75조2호)"
                공제세액 = 실제공급가액 * 10 // 100
                항목_공급가액 = 실제공급가액
        elif 공급가액 is not None:
            세액 = 공급가액 * 10 // 100
            공제세액 = 세액 if not 불공제사유 else 0
            항목_공급가액 = 공급가액
        else:
            세액 = int(공급대가 * 10 / 110)
            공제세액 = 세액 if not 불공제사유 else 0
            # 공급대가인 경우 공급가액 = 공급대가 × 100/110 (원 미만 버림)
            항목_공급가액 = int(공급대가 * 100 / 110)

        if 불공제사유:
            불공제합계 += 세액 - 공제세액

        공제합계 += 공제세액

        # 지연수취 가산세 계산
        if 지연수취 and 항목_공급가액 is not None:
            rate = invoice_penalty_rate("지연수취", 공급시기)
            지연수취_가산세_합계 += _floor(항목_공급가액, rate)

        calc_items.append({
            "항목": 항목,
            "세액": 세액,
            "공제세액": 공제세액,
            "불공제사유": 불공제사유,
        })
        if 불공제사유 or 판단문:
            if 불공제사유:
                결론 = "불공제"
            else:
                결론 = "공제 — " + 판단문
            판단.append({"항목": 항목, "결론": 결론, "근거": 불공제사유 or 판단문})

    계산 = {
        "항목별": 계산_항목별(calc_items),
    }
    return {"공제매입세액": 공제합계, "불공제매입세액": 불공제합계, "지연수취_가산세": 지연수취_가산세_합계, "계산": 계산, "판단": 판단,
            **({"주의": 주의} if 주의 else {})}


def 계산_항목별(items):
    """계산.항목별 리스트 정리."""
    return [{"항목": it["항목"], "세액": it["세액"], "공제세액": it["공제세액"],
             "불공제사유": it["불공제사유"]} for it in items]


# ── 부가세 판정 도구: 간주공급·판매 과세표준 판정(부가법 제10조, 영 제19조의2·제20조·제66조) ──

_VALID_TRADE = {"판매", "면세전용", "비영업용승용차전용", "타사업장반출", "개인적공급", "사업상증여", "폐업시잔존"}


def _deemed_market_value(자산, period):
    """감가상각 간주시가 = 취득가액 × (1 − 체감률 × 경과과세기간수), 0 미만 0.
    자산: {구분:'건물'|'구축물'|'기타', 취득가액, 취득일, 공급일}. period: 'YYYY-1'|'YYYY-2'."""
    체감률 = 0.05 if 자산["구분"] in ("건물", "구축물") else 0.25
    n = elapsed_periods(자산["취득일"], 자산["공급일"])
    간주시가 = _floor(자산["취득가액"], 1 - _x(체감률) * n)
    return max(0, 간주시가)


# 영 제19조의2 3호 사용인 선물 구분(평소 말 → 구분)
_GIFT_CAT = {"경조사": "경조사", "설날·추석": "설날·추석", "설날추석": "설날·추석", "명절": "설날·추석", "설날": "설날·추석",
             "추석": "설날·추석", "설": "설날·추석", "창립기념일·생일": "창립기념일·생일", "창립기념일생일": "창립기념일·생일",
             "창립기념일": "창립기념일·생일", "생일": "창립기념일·생일", "기념일": "창립기념일·생일"}


def _gift_group(cat, yh):
    """사용인 1명당 연간 10만원 한도를 따로 세는 묶음(영 제19조의2 3호 각 목).
    2020.10.7. 개정(대통령령 제31087호 부칙 제2조, 시행일이 속하는 과세기간 공급분부터 → 2020년 제2기~): 가목 경조사 / 나목 설날·추석·창립기념일·생일 등.
    2024.11.12. 개정(대통령령 제34993호 부칙 제2조, 시행일이 속하는 과세기간 제공분부터 → 2024년 제2기~): 나목 설날·추석 / 다목 창립기념일·생일 등."""
    if cat == "경조사":
        return "가목(경조사)"
    if yh >= (2024, 2):
        return "나목(설날·추석)" if cat == "설날·추석" else "다목(창립기념일·생일 등)"
    return "나목(설날·추석·창립기념일·생일 등)"


def vat_deemed_supply_items(period, items):
    """간주공급·판매 과세표준 판정(부가법 제10조, 영 제19조의2·제20조·제66조).
    입력: period, items=[{항목, 거래, 매입세액공제(bool), 금액?|시가?|감가상각?, 사용인_구분?, 인원?, 1인당_연간금액?, 견본_광고선전물?, 취득구분?}].
      취득구분(선택): '자기매입'(기본) | '사업양수'(사업양도로 취득, 양도자가 매입세액 공제받은 재화 — 제10조①2호) | '수출영세율'(영세율 적용받은 재화 — 제10조①3호).
        '사업양수'·'수출영세율'이면 매입세액공제가 False여도 간주공급 대상(시가·감가상각 간주시가 그대로). 양수 재화의 경과 과세기간은 입력한 취득일 기준.
    개인적공급의 10만원 한도는 사용인에게 준 경조사·설날·추석·창립기념일·생일 등 재화(영 제19조의2 3호)에만 — 목별로 사용인 1명당 연간 10만원,
    초과액만 공급. 사용인_구분·인원·1인당_연간금액이 모두 없으면 사업자 본인 사용 등으로 보고 시가 전액 과세.
    결과: {과세표준}, 계산.항목별: [{항목, 거래, 과세표준, 제외사유?}]."""
    pv = _validate_period(period)
    if pv: return pv
    yh = _period(period)

    항목들 = []
    for it in items:
        항목 = it.get("항목", "")
        거래 = it.get("거래", "")
        금액 = it.get("금액")
        시가 = it.get("시가")
        감가상각 = it.get("감가상각")
        인당연액 = it.get("1인당_연간금액")
        반출 = it.get("반출", "국내")  # B4 선택 입력 — '국내'(기본) | '국외'
        if 반출 not in ("국내", "국외"):
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"항목 '{항목}': 반출='{반출}' — 허용값: '국내' 또는 '국외'"],
                    "허용값": {"반출": ["국내", "국외"]}}
        문제 = []
        # 음수 금액 검증
        for key, val in (("금액", 금액), ("시가", 시가), ("1인당_연간금액", 인당연액)):
            if val is not None and val < 0:
                문제.append(f"항목 '{항목}': {key}={val} — 음수 입력 불가")
        if 감가상각 is not None:
            if not isinstance(감가상각, dict) or 감가상각.get("취득가액") is not None and 감가상각["취득가액"] < 0:
                문제.append(f"항목 '{항목}': 감가상각.취득가액={감가상각.get('취득가액')} — 음수 입력 불가")
        인원 = it.get("인원")
        if 인원 is not None and (isinstance(인원, bool) or not isinstance(인원, int) or 인원 < 1):
            문제.append(f"항목 '{항목}': 인원={인원} — 1 이상의 정수(선물 받은 사용인 수)")
        구분 = it.get("사용인_구분")
        if 구분 is not None and _GIFT_CAT.get(str(구분).replace(" ", "")) is None:
            문제.append(f"항목 '{항목}': 사용인_구분='{구분}' — '경조사'|'설날·추석'|'창립기념일·생일' 중 하나(영 제19조의2 3호 각 목)")
        if 거래 == "개인적공급" and (구분 is not None or 인원 is not None or 인당연액 is not None) and yh < (2020, 2):
            문제.append(f"항목 '{항목}': 사용인 선물 10만원 한도 — 2020.10.7. 개정(초과액만 공급, 목별 한도) 전 과세기간({period})은 "
                      "'10만원 이하의 재화' 문언이라 지원하지 않음(영 제19조의2 3호, 대통령령 제31087호 부칙 제2조)")
        if 문제:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
        if 거래 not in _VALID_TRADE:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"항목 '{항목}': 거래='{거래}'은(는) 지원하지 않음 — 허용: {sorted(_VALID_TRADE)}"]}
        if 거래 == "판매" and it.get("금액") is None:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"항목 '{항목}'(판매): '금액' 입력 필요"]}
        if 거래 == "타사업장반출" and it.get("금액") is None:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"항목 '{항목}'(타사업장반출): '금액' 입력 필요"]}
        if 거래 in ("면세전용", "비영업용승용차전용", "개인적공급", "사업상증여", "폐업시잔존"):
            if it.get("매입세액공제") is None:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"항목 '{항목}'({거래}): '매입세액공제' 입력 필요"]}
            if it.get("시가") is None and it.get("감가상각") is None:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"항목 '{항목}'({거래}): '시가' 또는 '감가상각' 입력 필요"]}
        항목들.append(it)

    calc_items = []
    과세표준합계 = 0
    영세율_과세표준 = 0    # B4: 국외 반출 사업상은 과세거래에서 제외, 영세율 과세표준
    판단 = []
    누계: dict = {}   # 목 → (인원, 이번까지 1인당 연간 누계) — 1인당_연간금액이 없을 때 같은 목 선물을 입력 순서대로 쌓음

    for it in 항목들:
        항목 = it["항목"]
        거래 = it["거래"]
        매입세액공제 = it.get("매입세액공제")
        금액 = it.get("금액")
        시가 = it.get("시가")
        감가상각 = it.get("감가상각")
        인당연액 = it.get("1인당_연간금액")
        견본 = it.get("견본_광고선전물")
        반출 = it.get("반출", "국내")  # B4: '국내'(기본) | '국외'

        과세표준 = 0
        제외사유 = None
        계산항목_영세율 = False  # B4: 반출='국외' + 사업상증여 시 True

        if 거래 == "판매":
            과세표준 = 금액
        elif 거래 == "타사업장반출":
            과세표준 = 금액
        elif 거래 in ("면세전용", "비영업용승용차전용", "개인적공급", "사업상증여", "폐업시잔존"):
            취득구분 = it.get("취득구분", "자기매입")  # 기본: 자기매입
            if 취득구분 not in ("자기매입", "사업양수", "수출영세율"):
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"항목 '{항목}': 취득구분 '{취득구분}' — 허용값: 자기매입, 사업양수, 수출영세율"]}

            # 사업양수·수출영세율은 매입세액공제가 False여도 간주공급 대상 (제10조①2호·3호)
            if not 매입세액공제 and 취득구분 == "자기매입":
                제외사유 = "매입세액 공제받지 않은 재화 — 간주공급 아님 (법 제10조 괄호)"
            else:
                if 감가상각:
                    과세표준 = _deemed_market_value(감가상각, period)
                else:
                    과세표준 = 시가
                구분 = it.get("사용인_구분")
                인원 = it.get("인원")
                # 취득구분에 따른 근거 표시
                if 취득구분 == "사업양수":
                    판단.append({"항목": 항목, "결론": "사업양수 재화 — 양도자가 매입세액 공제받은 재화(제10조①2호), 양수 재화 취득일 기준 — 해석 확인 필요",
                               "근거": "부가가치세법 제10조①2호"})
                elif 취득구분 == "수출영세율":
                    판단.append({"항목": 항목, "결론": "수출영세율 재화 — 영세율 적용받은 재화(제10조①3호)",
                               "근거": "부가가치세법 제10조①3호"})

                if 거래 == "개인적공급" and (구분 is not None or 인원 is not None or 인당연액 is not None):
                    # 영 제19조의2 3호: 각 목별로 사용인 1명당 연간 10만원 한도, 초과액만 재화의 공급
                    n = 인원 or 1
                    목 = _gift_group(_GIFT_CAT[str(구분).replace(" ", "")], yh) if 구분 is not None else f"목 미입력({항목})"
                    pp = _x(과세표준) / n                       # 이번 선물 1인분
                    if 인당연액 is not None:
                        after = _x(인당연액)
                        if after < pp:
                            return {"error": "입력 확인 필요 — 계산하지 않음",
                                    "문제": [f"항목 '{항목}': 1인당_연간금액 {인당연액:,}원 < 이번 선물 1인분 {float(pp):,.0f}원(시가 ÷ 인원 {n}) — "
                                           "여러 사람 몫 합계면 인원을 넣고, 1인당_연간금액은 이 선물을 포함한 그 목의 1인당 연간 누계"]}
                    else:
                        if 목 in 누계 and 누계[목][0] != n:
                            return {"error": "입력 확인 필요 — 계산하지 않음",
                                    "문제": [f"항목 '{항목}': 같은 목({목}) 선물의 인원이 다름 — 사람별 연간 누계를 1인당_연간금액으로 항목마다 넣어 주세요"]}
                        after = (누계[목][1] if 목 in 누계 else 0) + pp
                    누계[목] = (n, after)
                    before = after - pp
                    면제_1인 = min(pp, max(_x(0), 100_000 - before))
                    과세표준 = _floor(_x(과세표준) - 면제_1인 * n)
                    식 = (f"1인 연간 누계 {float(before):,.0f} → {float(after):,.0f}원, 10만원 넘는 부분 "
                         f"{float(pp - 면제_1인):,.0f}원 × {n}명")
                    if 과세표준 == 0:
                        제외사유 = f"사용인 1명당 연간 10만원 이하({목}) — 공급 아님 (영 제19조의2 3호; {식})"
                    else:
                        판단.append({"항목": 항목, "결론": f"10만원 초과액만 공급 — {식}",
                                   "근거": f"부가가치세법 시행령 제19조의2 3호 {목}(각 목별 사용인 1명당 연간 10만원)"})
                    if 구분 is None:
                        판단.append({"항목": 항목, "결론": "사용인_구분 미입력 — 이 항목만으로 한도 계산(같은 목 다른 선물과 합산하지 않음)",
                                   "근거": "부가가치세법 시행령 제19조의2 3호(경조사 / 설날·추석 / 창립기념일·생일 등 목별 한도)"})
                elif 거래 == "개인적공급":
                    판단.append({"항목": 항목, "결론": "10만원 한도 적용 안 함 — 사용인에게 준 경조사·설날·추석·창립기념일·생일 등 재화가 아님(사업자 본인·가사 사용 등). "
                                                   "사용인 선물이면 사용인_구분·인원·1인당_연간금액을 넣으세요",
                               "근거": "부가가치세법 제10조④, 시행령 제19조의2 3호"})
                # 견본·광고선전물 제외가 먼저 적용(영 제20조 1호) — 반출='국외'이어도 견본품이면 공급 자체가 아님
                if 거래 == "사업상증여" and 견본:
                    과세표준 = 0
                    제외사유 = "견본·광고선전물 — 공급 아님 (법 제10조⑤ 단서)"

                # B4: 해외 무상 반출 — 사업상증여 + 반출='국외'이고 견본 제외가 아니면 수출로 영세율(법 제21조제2항제1호)
                if 거래 == "사업상증여" and 반출 == "국외" and 제외사유 is None:
                    영세율_과세표준 += 과세표준
                    과세표준 = 0
                    계산항목_영세율 = True
                    판단.append({"항목": 항목, "결론": "외국 반출 — 수출로 영세율(세액 0), 수출신고 필요(법 제21조제2항제1호)",
                               "근거": "부가가치세법 제21조제2항제1호, 시행령 제20조"})

        과세표준합계 += 과세표준
        계산항목 = {"항목": 항목, "거래": 거래, "과세표준": 과세표준}
        if 계산항목_영세율:
            계산항목["영세율"] = True
        if 제외사유:
            계산항목["제외사유"] = 제외사유
            판단.append({"항목": 항목, "결론": "공급 아님(제외)", "근거": 제외사유})
        else:
            판단.append({"항목": 항목, "결론": f"과세표준 {과세표준:,}원", "근거": f"{거래} — 과세표준"})
        calc_items.append(계산항목)

    계산 = {"항목별": calc_items}
    if 판단:
        계산["판단"] = 판단
    return {"과세표준": 과세표준합계, "영세율_과세표준": 영세율_과세표준, "계산": 계산, "판단": 판단}


# ── 일반과세자 부가가치세 신고서(별지 제21호서식) 집계 ──────────────────────────────────────────
# 부품 도구(vat_input_tax_deduction·common_input_tax·vat_bad_debt_credit·vat_card_sales_credit·
# invoice_penalty_bundle·late_payment_penalty)의 결과를 받아 별지 제21호서식 제1쪽 ① 신고내용 순서로 합산.
# 새 세법 판단은 하지 않음 — 불공제·대손·안분·가산세는 입력값을 그대로 사용.

E_FILING_CREDIT = [  # 조세특례제한법 제104조의8②·시행령 제104조의5④: 확정신고·전자신고 시 공제액
    ("2010-02-18", 10_000),  # 2010.2.18.~2026.2.26. 1만원
    ("2026-02-27", 5_000),   # 2026.2.27.~ 5천원
]


def e_filing_credit_amount(filed_on: str, kind: str) -> int:
    """전자신고세액공제액(조세특례제한법 제104조의8②, 시행령 제104조의5③④).
    kind='예정'이면 0(③: 확정신고·제67조 신고만), filed_on이 표 범위 이전이면 NoYearTable.
    filed_on = YYYY-MM-DD(신고일). 확정신고 기한 기본값 서버-side에서 넣어 호출."""
    if kind == "예정":
        return 0
    s = str(filed_on)
    last = None
    for threshold, amount in E_FILING_CREDIT:
        if s >= threshold:
            last = amount
    if last is None:
        raise NoYearTable(f"전자신고세액공제 연도표 없음: filed_on={s}(2010-02-18 이전)")
    return last


def default_filed_on(year: int, period: str) -> str:
    """filed_on 생략 시 확정신고 기한(1기 YYYY-07-25, 2기 YYYY+1-01-25)."""
    if period == "1":
        return f"{year}-07-25"
    return f"{year + 1}-01-25"


# 원장형 입력 허용 항목 — 공급·매입·세액 각 항목명(명세 1-3 표, 가운뎃점 U+00B7)
_LEDGER_SUPPLY = {  # 공급 항목 → 입력 키
    "세금계산서 발급분": "sales_invoice",
    "매입자발행 세금계산서": "sales_buyer_invoice",
    "신용카드·현금영수증 발행분": "sales_card_cash",
    "기타 매출": "sales_other",
    "간주공급": "deemed_supply",
    "영세율 세금계산서 발급분": "sales_zero_invoice",
    "영세율 기타": "sales_zero_other",
    "예정신고 누락 매출": "prelim_omitted_sales",
}
_LEDGER_PURCHASE = {  # 매입 항목 → 입력 키
    "세금계산서 수취분 일반매입": "purchase_invoice",
    "세금계산서 수취분 고정자산": "purchase_invoice_fixed",
    "예정신고 누락 매입": "prelim_omitted_purchase",
    "매입자발행 세금계산서 수취": "purchase_buyer_invoice",
    "신용카드·현금영수증 수취분": "purchase_card_cash",
}
_LEDGER_TAX = {  # 세액 항목 → 입력 키
    "의제매입세액": "purchase_deemed",
    "그 밖의 공제매입세액": "purchase_other_credit",
    "변제대손세액": "recovered_input",
    "공제받지 못할 매입세액": "nondeductible",
    "공통매입세액 면세사업분": "common_nondeductible",
    "대손세액": "bad_debt_credit",
    "수입분 납부유예": "import_vat_deferred",
}
_LEDGER_ALLOWED = {
    "공급": _LEDGER_SUPPLY,
    "매입": _LEDGER_PURCHASE,
    "세액": _LEDGER_TAX,
}


def validate_ledger_entries(ledger: dict):
    """원장형 입력 항목 검사(명세서 1-3).
    문제 없으면 (집계된 금액 dict, None) 반환, 모르는 항목이 있으면 (None, 오류 dict) 반환.
    오류 dict에는 "문제"(문제 항목 목록)와 "허용값"(공급·매입·세액 각 허용 항목)이 있다."""
    문제_항목 = []
    집계 = {"공급": {}, "매입": {}, "세액": {}}

    for 구분, 허용표 in _LEDGER_ALLOWED.items():
        항목합 = {}
        for 행 in ledger.get(구분, []):
            항목명 = str((행 or {}).get("항목", "")).strip()
            금액 = int((행 or {}).get("금액", 0))
            if 항목명 not in 허용표:
                문제_항목.append(항목명)
                continue
            입력키 = 허용표[항목명]
            항목합[입력키] = 항목합.get(입력키, 0) + 금액
        집계[구분] = 항목합

    if 문제_항목:
        return (None, {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": [f"어휘에 없는 원장 항목: {', '.join(문제_항목)}"],
            "허용값": {g: list(m.keys()) for g, m in _LEDGER_ALLOWED.items()},
        })
    return (집계, None)


def vat_return_general(inputs: dict) -> dict:
    """일반과세자 부가가치세 신고서(별지 제21호서식 제1쪽 ① 신고내용) 집계.
    부품 도구 결과를 받아 (30) 차감ㆍ가감하여 납부할 세액(환급세액)까지 합산. 새 세법 판단은 하지 않음."""
    # ── 입력 추출(기본 0) ──
    year = int(inputs.get("year", 0))
    period = str(inputs.get("period", "1"))
    kind = str(inputs.get("kind", "확정"))
    e_filing_credit_given = int(inputs.get("e_filing_credit", 0))
    sales_invoice = int(inputs.get("sales_invoice", 0))
    sbi_amount = int(inputs.get("sales_buyer_invoice", 0))
    sales_card_cash = int(inputs.get("sales_card_cash", 0))
    sales_other = int(inputs.get("sales_other", 0))
    deemed_supply = int(inputs.get("deemed_supply", 0))
    sales_zero_invoice = int(inputs.get("sales_zero_invoice", 0))
    sales_zero_other = int(inputs.get("sales_zero_other", 0))
    prelim_omitted_sales = int(inputs.get("prelim_omitted_sales", 0))
    bad_debt_credit = int(inputs.get("bad_debt_credit", 0))
    purchase_invoice = int(inputs.get("purchase_invoice", 0))
    import_vat_deferred = int(inputs.get("import_vat_deferred", 0))
    purchase_invoice_fixed = int(inputs.get("purchase_invoice_fixed", 0))
    prelim_omitted_purchase = int(inputs.get("prelim_omitted_purchase", 0))
    pbi_amount = int(inputs.get("purchase_buyer_invoice", 0))
    purchase_card_cash = int(inputs.get("purchase_card_cash", 0))
    purchase_deemed = int(inputs.get("purchase_deemed", 0))
    purchase_other_credit = int(inputs.get("purchase_other_credit", 0))
    recovered_input = int(inputs.get("recovered_input", 0))
    nondeductible = int(inputs.get("nondeductible", 0))
    common_nondeductible = int(inputs.get("common_nondeductible", 0))
    other_credit = int(inputs.get("other_credit", 0))
    card_sales_credit_val = int(inputs.get("card_sales_credit", 0))
    small_biz_reduction = int(inputs.get("small_biz_reduction", 0))
    prelim_refund_pending = int(inputs.get("prepaid_refund_pending", 0))
    prepaid_assessed = int(inputs.get("prepaid_assessed", 0))
    occasional_assessed = int(inputs.get("occasional_assessed", 0))
    prepaid_by_transferee = int(inputs.get("prepaid_by_transferee", 0))
    prepaid_buyer_special = int(inputs.get("prepaid_buyer_special", 0))
    prepaid_by_card_company = int(inputs.get("prepaid_by_card_company", 0))
    penalties = list(inputs.get("penalties", []))
    ledger = inputs.get("ledger")

    # ── ledger 집계(있으면) ──
    if ledger is not None:
        집계, 검증오류 = validate_ledger_entries(ledger)
        if 검증오류:
            return 검증오류
        # ledger로 들어오는 입력 키
        sales_invoice = 집계["공급"].get("sales_invoice", 0)
        sbi_amount = 집계["공급"].get("sales_buyer_invoice", 0)
        sales_card_cash = 집계["공급"].get("sales_card_cash", 0)
        sales_other = 집계["공급"].get("sales_other", 0)
        deemed_supply = 집계["공급"].get("deemed_supply", 0)
        sales_zero_invoice = 집계["공급"].get("sales_zero_invoice", 0)
        sales_zero_other = 집계["공급"].get("sales_zero_other", 0)
        prelim_omitted_sales = 집계["공급"].get("prelim_omitted_sales", 0)
        purchase_invoice = 집계["매입"].get("purchase_invoice", 0)
        purchase_invoice_fixed = 집계["매입"].get("purchase_invoice_fixed", 0)
        prelim_omitted_purchase = 집계["매입"].get("prelim_omitted_purchase", 0)
        pbi_amount = 집계["매입"].get("purchase_buyer_invoice", 0)
        purchase_card_cash = 집계["매입"].get("purchase_card_cash", 0)
        purchase_deemed = 집계["세액"].get("purchase_deemed", 0)
        purchase_other_credit = 집계["세액"].get("purchase_other_credit", 0)
        recovered_input = 집계["세액"].get("recovered_input", 0)
        nondeductible = 집계["세액"].get("nondeductible", 0)
        common_nondeductible = 집계["세액"].get("common_nondeductible", 0)
        bad_debt_credit = 집계["세액"].get("bad_debt_credit", 0)
        import_vat_deferred = 집계["세액"].get("import_vat_deferred", 0)

    # ── 입력 검증 ──
    음수검증대상 = {
        "sales_invoice": sales_invoice, "sales_buyer_invoice": sbi_amount,
        "sales_card_cash": sales_card_cash, "sales_other": sales_other,
        "deemed_supply": deemed_supply, "sales_zero_invoice": sales_zero_invoice,
        "sales_zero_other": sales_zero_other, "prelim_omitted_sales": prelim_omitted_sales,
        "purchase_invoice": purchase_invoice, "purchase_invoice_fixed": purchase_invoice_fixed,
        "prelim_omitted_purchase": prelim_omitted_purchase, "purchase_buyer_invoice": pbi_amount,
        "purchase_card_cash": purchase_card_cash, "purchase_deemed": purchase_deemed,
        "purchase_other_credit": purchase_other_credit, "recovered_input": recovered_input,
        "nondeductible": nondeductible, "common_nondeductible": common_nondeductible,
        "import_vat_deferred": import_vat_deferred, "other_credit": other_credit, "card_sales_credit": card_sales_credit_val,
        "small_biz_reduction": small_biz_reduction, "prepaid_refund_pending": prelim_refund_pending,
        "prepaid_assessed": prepaid_assessed, "occasional_assessed": occasional_assessed,
        "prepaid_by_transferee": prepaid_by_transferee, "prepaid_buyer_special": prepaid_buyer_special,
        "prepaid_by_card_company": prepaid_by_card_company,
    }
    for key, val in 음수검증대상.items():
        if val < 0:
            raise ValueError(f"{key}: 음수 입력 불가({val}) — bad_debt_credit만 음수 허용(회수분)")

    if kind == "예정":
        if prelim_refund_pending != 0 or prepaid_assessed != 0 or occasional_assessed != 0:
            raise ValueError("예정신고에는 예정신고 미환급세액·예정고지세액·수시부과세액을 넣지 않음")

    for p in penalties:
        if not isinstance(p, dict) or "kind" not in p or "amount" not in p:
            raise ValueError("penalties 각 항목에 kind와 amount(int≥0)가 필요")
        if not isinstance(p.get("amount"), int) or p["amount"] < 0:
            raise ValueError("penalties amount는 int≥0")

    # ── 계산 ──
    # 매출 과세표준: (1)~(4)+(7)
    과세표준 = sales_invoice + sbi_amount + sales_card_cash + sales_other + deemed_supply + prelim_omitted_sales
    영세율_과세표준 = sales_zero_invoice + sales_zero_other

    # (1)~(7) 세액
    세액_1 = sales_invoice * 10 // 100
    세액_2 = sbi_amount * 10 // 100
    세액_3 = sales_card_cash * 10 // 100
    세액_4 = (sales_other + deemed_supply) * 10 // 100
    세액_5 = 0  # 영세율
    세액_6 = 0  # 영세율
    세액_7 = prelim_omitted_sales * 10 // 100
    매출세액_합계 = 세액_1 + 세액_2 + 세액_3 + 세액_4 + 세액_5 + 세액_6 + 세액_7 + (-bad_debt_credit)
    대손세액_가감 = -bad_debt_credit

    # (10)~(14) 매입
    세액_10 = purchase_invoice * 10 // 100
    세액_11 = import_vat_deferred
    세액_12 = purchase_invoice_fixed * 10 // 100
    세액_13 = prelim_omitted_purchase * 10 // 100
    세액_14 = pbi_amount * 10 // 100
    세액_15 = purchase_card_cash * 10 // 100 + purchase_deemed + purchase_other_credit + recovered_input
    매입세액 = 세액_10 - 세액_11 + 세액_12 + 세액_13 + 세액_14 + 세액_15   # (16) = 칸별 세액의 합(서식 산식 그대로)

    # (17) 공제받지 못할 매입세액
    공제받지못할_매입세액 = nondeductible + common_nondeductible
    매입세액_차감계 = 매입세액 - 공제받지못할_매입세액

    납부환급세액 = 매출세액_합계 - 매입세액_차감계

    # (19) 전자신고세액공제
    if e_filing_credit_given:
        efc = e_filing_credit_given
    else:
        efc = 0
    # (1)~(7) 합 = sales_invoice + sbi_amount + sales_card_cash + sales_other + deemed_supply + prelim_omitted_sales + sales_zero_invoice + sales_zero_other
    매출_금액합 = sales_invoice + sbi_amount + sales_card_cash + sales_other + deemed_supply + prelim_omitted_sales + sales_zero_invoice + sales_zero_other
    매입_금액합 = purchase_invoice + purchase_invoice_fixed + prelim_omitted_purchase + pbi_amount + purchase_card_cash
    if 매출_금액합 == 0 and 매입_금액합 == 0 and efc > 0:
        efc = 0
        주의_목록 = ["조세특례제한법 제104조의8② 단서 — 매출가액과 매입가액이 없는 일반과세자는 전자신고세액공제 없음"]
    else:
        주의_목록 = []

    경감공제세액 = other_credit + efc

    # (20) 카드매출전표 발행공제
    카드공제 = card_sales_credit_val

    # (21) 합계
    경감공제_합계 = 경감공제세액 + 카드공제

    # (29) 가산세액 계
    가산세_합계 = sum(int(p["amount"]) for p in penalties)

    # (30) 차감ㆍ가감하여 납부할 세액(환급받을 세액)
    차감_가감_납부세액 = 납부환급세액 - 경감공제_합계 - small_biz_reduction - prelim_refund_pending \
        - prepaid_assessed - occasional_assessed - prepaid_by_transferee - prepaid_buyer_special - prepaid_by_card_company \
        + 가산세_합계
    납부세액 = max(0, 차감_가감_납부세액)
    환급세액 = max(0, -차감_가감_납부세액)

    # ── 결과 ──
    결과 = {
        "과세표준": 과세표준,
        "영세율_과세표준": 영세율_과세표준,
        "매출세액": 세액_1 + 세액_2 + 세액_3 + 세액_4 + 세액_5 + 세액_6 + 세액_7,
        "대손세액_가감": 대손세액_가감,
        "매출세액_합계": 매출세액_합계,
        "매입세액": 매입세액,
        "공제받지못할_매입세액": 공제받지못할_매입세액,
        "매입세액_차감계": 매입세액_차감계,
        "납부환급세액": 납부환급세액,
        "경감공제세액": 경감공제세액,
        "소규모감면세액": small_biz_reduction,
        "예정신고미환급세액": prelim_refund_pending,
        "예정고지세액": prepaid_assessed,
        "수시부과세액": occasional_assessed,
        "기납부세액_기타": prepaid_by_transferee + prepaid_buyer_special + prepaid_by_card_company,
        "가산세액계": 가산세_합계,
        "차가감_납부세액": 차감_가감_납부세액,
        "납부세액": 납부세액,
        "환급세액": 환급세액,
    }

    # ── 서식(0절 표 원문 이름 그대로, ㆍ는 U+318D) ──
    서식 = {
        "(1) 세금계산서 발급분": {"금액": sales_invoice, "세액": 세액_1},
        "(2) 매입자발행 세금계산서": {"금액": sbi_amount, "세액": 세액_2},
        "(3) 신용카드ㆍ현금영수증 발행분": {"금액": sales_card_cash, "세액": 세액_3},
        "(4) 기타(정규영수증 외 매출분)": {"금액": sales_other + deemed_supply, "세액": 세액_4},
        "(5) 영세율 세금계산서 발급분": {"금액": sales_zero_invoice, "세액": 세액_5},
        "(6) 영세율 기타": {"금액": sales_zero_other, "세액": 세액_6},
        "(7) 예정신고 누락분": {"금액": prelim_omitted_sales, "세액": 세액_7},
        "(8) 대손세액 가감": 대손세액_가감,
        "(9) 합계": 매출세액_합계,
        "(10) 일반매입": {"금액": purchase_invoice, "세액": 세액_10},
        "(11) 수출기업 수입분 납부유예": 세액_11,
        "(12) 고정자산매입": {"금액": purchase_invoice_fixed, "세액": 세액_12},
        "(13) 예정신고 누락분": {"금액": prelim_omitted_purchase, "세액": 세액_13},
        "(14) 매입자발행 세금계산서": {"금액": pbi_amount, "세액": 세액_14},
        "(15) 그 밖의 공제매입세액": 세액_15,
        "(16) 합계": 매입세액,
        "(17) 공제받지 못할 매입세액": 공제받지못할_매입세액,
        "(18) 차감계": 매입세액_차감계,
        "납부(환급)세액": 납부환급세액,
        "(19) 그 밖의 경감ㆍ공제세액": 경감공제세액,
        "(20) 신용카드매출전표등 발행공제 등": 카드공제,
        "(21) 합계": 경감공제_합계,
        "(22) 소규모 개인사업자 부가가치세 감면세액": small_biz_reduction,
        "(23) 예정신고 미환급세액": prelim_refund_pending,
        "(24) 예정고지세액": prepaid_assessed,
        "(25) 수시부과세액": occasional_assessed,
        "(26) 사업양수자가 대리납부한 세액": prepaid_by_transferee,
        "(27) 매입자 납부특례에 따라 납부한 세액": prepaid_buyer_special,
        "(28) 신용카드업자가 대리납부한 세액": prepaid_by_card_company,
        "(29) 가산세액 계": 가산세_합계,
        "(30) 차감ㆍ가감하여 납부할 세액(환급받을 세액)": 차감_가감_납부세액,
    }

    단계별 = [
        {"항목": "과세표준((1)~(4)+(7))", "금액": 과세표준,
         "근거": "별지 제21호서식 (1) 세금계산서 발급분 + (2) 매입자발행 + (3) 신용카드·현금영수증 + (4) 기타 + (7) 예정신고 누락분"},
        {"항목": "영세율 과세표준((5)+(6))", "금액": 영세율_과세표준,
         "근거": "별지 제21호서식 (5) 영세율 세금계산서 발급분 + (6) 영세율 기타"},
        {"항목": "매출세액((1)~(7) 세액)", "금액": 세액_1 + 세액_2 + 세액_3 + 세액_4 + 세액_5 + 세액_6 + 세액_7,
         "근거": "각 매출란 공급가액 × 10%(영세율 0%) — 부가가치세법 제37조"},
        {"항목": "대손세액 가감((8))", "금액": 대손세액_가감,
         "근거": "부가가치세법 제45조① 대손세액공제 — 공제분 음수, 회수분 양수"},
        {"항목": "매출세액 합계(㉮ = (1)~(7)+(8))", "금액": 매출세액_합계,
         "근거": "부가가치세법 제37조"},
        {"항목": "매입세액((16) = (10)−(11)+(12)+(13)+(14)+(15))", "금액": 매입세액,
         "근거": "부가가치세법 제38조·제39조"},
        {"항목": "공제받지 못할 매입세액((17))", "금액": 공제받지못할_매입세액,
         "근거": "부가가치세법 제39조 — 부품 도구 판정 결과 그대로"},
        {"항목": "매입세액 차감계(㉯ = (16)−(17))", "금액": 매입세액_차감계,
         "근거": "부가가치세법 제38조"},
        {"항목": "납부(환급)세액(㉰ = ㉮−㉯)", "금액": 납부환급세액,
         "근거": "부가가치세법 제45조·제48조·제49조"},
        {"항목": "경감ㆍ공제세액((19)+(20) = ㉱)", "금액": 경감공제_합계,
         "근거": "부가가치세법 제46조·제48조, 조세특례제한법 제104조의8②"},
        {"항목": "차감ㆍ가감하여 납부할 세액(환급액)((30))", "금액": 차감_가감_납부세액,
         "근거": "부가가치세법 제48조·제49조·제60조, 국고금 관리법 제47조"},
    ]

    근거 = ("부가가치세법 제37조·제38조·제39조·제45조·제46조·제48조·제49조·제60조, "
            "조세특례제한법 제104조의8②, 국고금 관리법 제47조, 별지 제21호서식(2026.3.20.)")

    # ── 원장대조(ledger 있는 경우만) ──
    if ledger is not None:
        대조_항목 = []
        for 구분, 매핑 in _LEDGER_ALLOWED.items():
            for 항목명, 입력키 in 매핑.items():
                원장금액 = 집계[구분].get(입력키, 0)
                대조_항목.append({"항목": 항목명, "금액": 원장금액, "입력키": 입력키})
        원장대조 = {"판정": "일치", "항목": 대조_항목}
    else:
        원장대조 = None

    raw = {
        "결과": 결과,
        "서식": 서식,
        "단계별_계산": 단계별,
        "근거": 근거,
    }
    if 주의_목록:
        raw["주의"] = 주의_목록
    if 원장대조:
        raw["원장대조"] = 원장대조
    return raw


# ── 외화 대가 부가가치세 과세표준 환산 (영 제59조·제95조제3항) ──

def vat_foreign_currency_base(context, items):
    """외화 대가의 부가가치세 과세표준 환산(부가가치세법 제29조제3항제1호 단서, 시행령 제59조 1호·2호 / 대리납부 시행령 제95조제3항 1호·2호).
    context='공급'(기본, 영 제59조)｜'대리납부'(영 제95조제3항). 환율은 사용자 입력(조회하지 않음), 통화 단위 자유.
    반환: {과세표준_합계, 항목별: [{이름, 통화, 외화금액, 환가분: {외화, 원화}, 미환가분: {외화, 환율, 원화}, 과세표준, 적용}], 판단, 근거}"""
    from .exact import trunc_won as _trunc

    if context not in ("공급", "대리납부"):
        raise ValueError(f"context='{context}' — '공급' 또는 '대리납부' 필요")

    결과_항목별 = []
    합계 = 0
    판단 = []

    for idx, item in enumerate(items):
        이름 = item.get("이름")
        외화금액 = item["외화금액"]
        통화 = item.get("통화", "USD")

        if 외화금액 <= 0:
            raise ValueError(f"항목 {idx+1}({이름}): 외화금액({외화금액})은 0보다 커야 함")
        if 통화 is None or 통화 == "":
            통화 = "USD"

        if context == "공급":
            공급시기 = item["공급시기"]
            공급시기_환율 = item.get("공급시기_환율")
            환가 = item.get("환가", [])

            # 환가분: 환가일 < 공급시기인 것만 1호
            환가_원화_합 = 0
            환가_외화_합 = 0
            환가_목록 = []
            미환가_처리 = False

            for h in 환가:
                환가일 = h["환가일"]
                h_외화 = h["외화금액"]
                h_원화 = h["원화금액"]
                if h_외화 <= 0 or h_원화 < 0:
                    raise ValueError(f"항목 {idx+1}({이름}): 환가 항목의 외화금액·원화금액이 음수")
                if 환가일 < 공급시기:
                    # 1호: 공급시기 전 환가 → 환가액 그대로
                    환가_원화_합 += h_원화
                    환가_외화_합 += h_외화
                    환가_목록.append({"외화": h_외화, "원화": h_원화})
                else:
                    # 환가일 >= 공급시기 → 1호 아님, 미환가분으로 처리
                    미환가_처리 = True

            # 환가 외화 합 > 외화금액 → 오류
            if 환가_외화_합 > 외화금액:
                raise ValueError(f"항목 {idx+1}({이름}): 환가 외화 합계({환가_외화_합})가 외화금액({외화금액})보다 큼")

            미환가_외화 = 외화금액 - 환가_외화_합
            미환가_원화 = 0
            적용 = "시행령 제59조 1호"
            미환가_환율 = None

            if 미환가_외화 > 0:
                if 공급시기_환율 is None:
                    raise ValueError(f"항목 {idx+1}({이름}): 미환가분이 있어 공급시기_환율 필요")
                if 공급시기_환율 < 0:
                    raise ValueError(f"항목 {idx+1}({이름}): 공급시기_환율({공급시기_환율}) 음수 불가")
                미환가_원화 = _trunc(미환가_외화, 공급시기_환율)
                미환가_환율 = 공급시기_환율
                if 환가_목록:
                    적용 = "시행령 제59조 1호·2호"
                else:
                    적용 = "시행령 제59조 2호"
                if 미환가_처리:
                    판단.append(f"'{이름}': 공급시기 이후 환가 — 영 제59조 2호(공급시기 환율)")
            elif 환가_목록 and 미환가_외화 == 0:
                if 미환가_처리:
                    적용 = "시행령 제59조 2호"
                    판단.append(f"'{이름}': 공급시기 이후 환가 — 영 제59조 2호(공급시기 환율)")
                else:
                    적용 = "시행령 제59조 1호"

            과세표준 = 환가_원화_합 + 미환가_원화
            결과_항목별.append({
                "이름": 이름,
                "통화": 통화,
                "외화금액": 외화금액,
                "환가분": {"외화": 환가_외화_합, "원화": 환가_원화_합} if 환가_목록 else None,
                "미환가분": {"외화": 미환가_외화, "환율": 미환가_환율, "원화": 미환가_원화} if 미환가_외화 > 0 else None,
                "과세표준": 과세표준,
                "적용": 적용,
            })
            합계 += 과세표준

        else:  # 대리납부 (영 제95조제3항)
            지급일 = item["지급일"]
            지급방식 = item.get("지급방식")
            지급일_환율 = item.get("지급일_환율")

            if 지급방식 not in ("원화매입", "보유외화"):
                raise ValueError(f"항목 {idx+1}({이름}): 지급방식='{지급방식}' — '원화매입' 또는 '보유외화' 필요")
            if 지급일_환율 is None:
                raise ValueError(f"항목 {idx+1}({이름}): 지급일_환율 필요")
            if 지급일_환율 < 0:
                raise ValueError(f"항목 {idx+1}({이름}): 지급일_환율({지급일_환율}) 음수 불가")

            과세표준 = _trunc(외화금액, 지급일_환율)
            if 지급방식 == "원화매입":
                적용 = "시행령 제95조 제3항 1호"
            else:
                적용 = "시행령 제95조 제3항 2호"

            결과_항목별.append({
                "이름": 이름,
                "통화": 통화,
                "외화금액": 외화금액,
                "환가분": None,
                "미환가분": None,
                "과세표준": 과세표준,
                "적용": 적용,
            })
            합계 += 과세표준

    근거 = ("부가가치세법 제29조제3항, 시행령 제59조" if context == "공급" else
             "부가가치세법 제29조제3항, 시행령 제95조제3항")
    return {"결과": {"과세표준_합계": 합계, "항목별": 결과_항목별}, "근거": 근거, "판단": 판단}


# ── 국외사업자 용역등 대리납부 (법 제52조) ──

from fractions import Fraction as _Fr
_VAT_RATE = _Fr(1, 10)  # 부가가치세율 10% (float 금지 — 정확한 분수)


def _신고납부기한(지급일):
    """지급일 기준 신고납부기한(법 제52조②·제48조②·제49조② 준용).
    1.1~3.31 → 같은 해 4.25, 4.1~6.30 → 7.25, 7.1~9.30 → 10.25, 10.1~12.31 → 다음 해 1.25.
    기한이 토·일요일이면 다음 월요일(국세기본법 제5조①), 공휴일은 확인하지 않음.
    반환: (기한_법정, 기한_적용) — 기한_법정은 원래 기한, 기한_적용은 토·일요일 다음 월요일."""
    from datetime import date, timedelta
    y, m, d = map(int, 지급일.split("-"))
    지급 = date(y, m, d)
    if 지급.month <= 3:
        기한 = date(y, 4, 25)
    elif 지급.month <= 6:
        기한 = date(y, 7, 25)
    elif 지급.month <= 9:
        기한 = date(y, 10, 25)
    else:
        기한 = date(y + 1, 1, 25)

    # 토·일요일이면 다음 월요일
    wd = 기한.weekday()
    if wd == 5:  # 토요일
        적용 = 기한 + timedelta(days=2)
    elif wd == 6:  # 일요일
        적용 = 기한 + timedelta(days=1)
    else:
        적용 = 기한
    return 기한.isoformat(), 적용.isoformat()


def vat_reverse_charge(year, items, taxable_supply=None, exempt_supply=None):
    """국외사업자 용역등 대리납부(부가가치세법 제52조제1항·제2항, 시행령 제95조제1항·제2항).
    year: 사업연도·귀속연도(2016~2026). items: [{이름, 공급자, 대가, 지급일, 용도, ...}].
    taxable_supply·exempt_supply: 용도 '공통' 안분용 과세기간 공급가액.
    반환: {대리납부세액_합계, 항목별: [{이름, 대상, 사유, 과세표준, 세액, 기한_법정, 기한_적용}], 판단, 주의, 근거}"""
    from .exact import trunc_won as _trunc

    if not (2016 <= year <= 2026):
        raise ValueError(f"year={year} — 2016~2026 필요")

    결과_항목별 = []
    합계 = 0
    판단 = []
    주의 = ["전자적 용역(부가가치세법 제53조의2 간편사업자등록)은 범위 밖 — 별도 확인"]

    for idx, item in enumerate(items):
        이름 = item.get("이름")
        공급자 = item["공급자"]
        대가 = item["대가"]
        지급일 = item["지급일"]
        용도 = item["용도"]

        if 대가 < 0:
            raise ValueError(f"항목 {idx+1}({이름}): 대가({대가}) 음수 불가")
        if 용도 not in ("면세", "과세", "불공제", "공통", "비사업"):
            raise ValueError(f"항목 {idx+1}({이름}): 용도='{용도}' — 허용값: '면세', '과세', '불공제', '공통', '비사업'")

        대상 = True
        사유 = ""
        과세표준 = 대가

        if 공급자 == "국내사업장_있음_귀속":
            대상 = False
            사유 = "국내사업장에 귀속 — 대리납부 대상 아님(제52조제1항제2호 반대해석)"
        elif 공급자 not in ("국내사업장_없음", "국내사업장_있음_비귀속"):
            raise ValueError(f"항목 {idx+1}({이름}): 공급자='{공급자}' — 허용값: '국내사업장_없음', '국내사업장_있음_비귀속', '국내사업장_있음_귀속'")
        elif 용도 == "과세":
            대상 = False
            사유 = "과세사업에 제공 — 대리납부 대상 아님(제52조제1항 괄호)"
        elif 용도 == "면세" or 용도 == "비사업":
            대상 = True
            사유 = "면세사업(비사업) 제공 — 대가 전액 대리납부 대상"
        elif 용도 == "불공제":
            대상 = True
            사유 = "제39조에 따라 매입세액 공제되지 않는 용역등 — 대가 전액 대리납부 대상(제52조제1항)"
        elif 용도 == "공통":
            if taxable_supply is None or exempt_supply is None:
                raise ValueError("공통 사용 안분에 taxable_supply·exempt_supply 필요")
            총공급 = taxable_supply + exempt_supply
            if 총공급 == 0:
                raise ValueError("공통 사용 안분: 총공급가액(taxable_supply + exempt_supply)이 0")
            과세표준 = _trunc(대가, exempt_supply, div=총공급)
            대상 = True
            사유 = f"공통 사용 안분(시행령 제95조제2항): 대가 {대가:,}원 × 면세공급가액 {exempt_supply:,}원 ÷ 총공급가액 {총공급:,}원 = {과세표준:,}원"
            판단.append(f"'{이름}': 공통 사용 안분 — 대가 × 면세공급가액 ÷ (과세+면세 공급가액) = {과세표준:,}원 (시행령 제95조제2항)")
        else:
            raise ValueError(f"항목 {idx+1}({이름}): 용도='{용도}' — 허용값: '면세', '과세', '불공제', '공통', '비사업'")

        if 대상:
            세액 = _trunc(과세표준, _VAT_RATE)
        else:
            세액 = 0

        기한_법정, 기한_적용 = _신고납부기한(지급일)

        결과_항목별.append({
            "이름": 이름,
            "대상": 대상,
            "사유": 사유,
            "과세표준": 과세표준,
            "세액": 세액,
            "기한_법정": 기한_법정,
            "기한_적용": 기한_적용,
        })
        합계 += 세액

    근거 = "부가가치세법 제52조제1항·제2항, 시행령 제95조제1항·제2항"
    return {
        "결과": {"대리납부세액_합계": 합계, "항목별": 결과_항목별},
        "판단": 판단,
        "주의": 주의,
        "근거": 근거,
    }


# ── 과세표준 조정: 에누리·환입·할인·장려금·대손, 마일리지등 결제(부가가치세법 제29조③6호·⑤·⑥, 시행령 제61조) ──────────
# 조문 대조(Claude 2026-11-12): 법 제29조⑤⑥은 2016·2017·2026 시행본 동일. 마일리지등 결제 공급가액은 2017.2.7. 개정 영 제61조①9호·10호
# (2017.4.1. 시행 — 대통령령 제27838호 부칙 제1조 단서, 시행 이후 공급분), 2018.2.13.부터 제61조②9호·10호로 이동(내용 같음).
# 2017.3.31.까지는 구 영 제61조④(마일리지 상당액을 공급가액에 포함) — 판례와 문언이 갈려 계산하지 않음.
TAX_BASE_ADJ = {
    "매출에누리": (True, "공급조건에 따라 통상의 대가에서 직접 깎아 준 금액 — 공급가액에 포함하지 않음", "부가가치세법 제29조⑤1호"),
    "환입": (True, "환입된 재화의 가액 — 공급가액에 포함하지 않음(환입된 날이 속하는 과세기간에 차감, 수정세금계산서 작성일 = 환입된 날)",
            "부가가치세법 제29조⑤2호, 시행령 제70조①1호"),
    "도달전파손": (True, "공급받는 자에게 도달하기 전에 파손·훼손·멸실한 재화의 가액 — 공급가액에 포함하지 않음", "부가가치세법 제29조⑤3호"),
    "매출할인": (True, "대가를 약정기일 전에 받아 당초 공급가액에서 할인해 준 금액 — 공급가액에 포함하지 않음", "부가가치세법 제29조⑤6호"),
    "연체이자": (True, "대가 지급 지체로 받는 연체이자 — 공급가액에 포함하지 않음(sales에 들어 있는 금액을 뺌)", "부가가치세법 제29조⑤5호"),
    "보조금": (True, "공급과 직접 관련되지 않는 국고보조금·공공보조금 — 공급가액에 포함하지 않음(sales에 들어 있는 금액을 뺌)", "부가가치세법 제29조⑤4호"),
    "판매장려금": (False, "공급받는 자에게 지급하는 장려금이나 이와 유사한 금액 — 과세표준에서 공제하지 않음", "부가가치세법 제29조⑥"),
    "대손금": (False, "대손금액 — 과세표준에서 공제하지 않음(요건을 갖추면 대손세액공제, 제45조)", "부가가치세법 제29조⑥·제45조①"),
}
_MILEAGE_FROM = "2017-04-01"


def _won_ex_vat(v, vat_included):
    return _floor(v, 100, div=110) if vat_included else int(v)


def vat_tax_base_adjustments(period, sales=0, adjustments=None, mileage_sales=None, vat_included=False):
    """과세기간 과세표준 = sales − (공급가액에 포함하지 않는 금액) + 마일리지등 결제 거래의 공급가액.
    sales·adjustments 금액은 공급가액(부가세 제외). mileage_sales의 금액은 vat_included=True면 부가세 포함 결제액(×100/110).
    mileage_sales 항목: {이름?, 공급일, 현금등, 자기적립마일리지, 그외마일리지, 보전금액, 시가?, 자기생산취득재화?, 특수관계_저가보전?}."""
    문제 = []
    try:
        y, h = _period(period)
        if len(str(period)) != 6: raise ValueError
    except ValueError:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"period {period!r} — 'YYYY-1' 또는 'YYYY-2'(2016-1~2026-2)"]}
    p_start, p_end = (f"{y}-01-01", f"{y}-06-30") if h == 1 else (f"{y}-07-01", f"{y}-12-31")
    if not isinstance(sales, int) or sales < 0:
        문제.append("sales — 조정 전 매출 공급가액(원, 0 이상 정수)")
    adjustments, mileage_sales = adjustments or [], mileage_sales or []
    for i, a in enumerate(adjustments):
        k, amt = a.get("종류"), a.get("금액")
        if k not in TAX_BASE_ADJ:
            문제.append(f"adjustments[{i}].종류={k!r} — 허용값: {list(TAX_BASE_ADJ)}")
        if not isinstance(amt, int) or amt < 0:
            문제.append(f"adjustments[{i}].금액 — 원(0 이상 정수, 공급가액 기준)")
        d = a.get("발생일")
        if d is not None:
            try:
                _date(d)
                if len(str(d)) != 10: raise ValueError
            except ValueError:
                문제.append(f"adjustments[{i}].발생일={d!r} — YYYY-MM-DD(2016~2026)")
    for i, m in enumerate(mileage_sales):
        d = m.get("공급일")
        try:
            if d is None or len(str(d)) != 10: raise ValueError
            _date(d)
        except ValueError:
            문제.append(f"mileage_sales[{i}].공급일={d!r} — YYYY-MM-DD(2016~2026) 필요(마일리지등 규정이 2017.4.1. 공급분부터 달라짐)"); continue
        if str(d) < _MILEAGE_FROM:
            문제.append(f"mileage_sales[{i}].공급일={d} — 2017.3.31.까지 공급분은 구 시행령 제61조④(마일리지 상당액을 공급가액에 포함) 적용 시기라 계산하지 않음(판례 확인)")
        if not (p_start <= str(d) <= p_end):
            문제.append(f"mileage_sales[{i}].공급일={d} — 과세기간 {period}({p_start}~{p_end}) 밖")
        for key in ("현금등", "자기적립마일리지", "그외마일리지", "보전금액", "시가"):
            v = m.get(key, 0)
            if v is not None and (not isinstance(v, int) or v < 0):
                문제.append(f"mileage_sales[{i}].{key} — 원(0 이상 정수)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    항목별, 판단, 차감 = [], [], 0
    for a in adjustments:
        k, amt = a["종류"], a["금액"]
        빼기, 설명, 근거 = TAX_BASE_ADJ[k]
        row = {"종류": k, "이름": a.get("이름", k), "금액": amt, "과세표준_차감": amt if 빼기 else 0, "근거": 근거}
        d = a.get("발생일")
        if 빼기 and d is not None and not (p_start <= str(d) <= p_end):
            row["과세표준_차감"] = 0
            row["사유"] = f"발생일 {d}이 과세기간 {period} 밖 — 그 날이 속하는 과세기간에서 차감"
        else:
            row["사유"] = 설명
        차감 += row["과세표준_차감"]
        항목별.append(row)
        판단.append({"항목": row["이름"], "결론": row["사유"], "근거": 근거})
    마일_근거 = "부가가치세법 시행령 제61조" + ("①" if y == 2017 else "②") + "9호·10호" + ("" if y == 2017 else ", 법 제29조③6호")
    마일리지, 마일합 = [], 0
    for m in mileage_sales:
        cash, own, other = m.get("현금등", 0) or 0, m.get("자기적립마일리지", 0) or 0, m.get("그외마일리지", 0) or 0
        comp, fmv = m.get("보전금액", 0) or 0, m.get("시가")
        name = m.get("이름", "마일리지등 결제 거래")
        시가과세 = None
        if m.get("특수관계_저가보전"):
            시가과세 = "특수관계인에게서 부당하게 낮은 금액을 보전받거나 보전받지 않음 — 공급한 재화·용역의 시가(10호 나목)"
        elif other > 0 and comp == 0 and m.get("자기생산취득재화"):
            시가과세 = "자기적립 외 마일리지등 결제분을 보전받지 않고 자기생산·취득재화를 공급 — 공급한 재화의 시가(10호 가목)"
        if 시가과세:
            if fmv is None:
                return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"'{name}': {시가과세} — 시가 입력 필요"]}
            base = _won_ex_vat(fmv, vat_included)
            사유 = 시가과세
        else:
            base = _won_ex_vat(cash + comp, vat_included)
            사유 = ("마일리지등 외 결제액 + 자기적립 외 마일리지등 결제분에 대해 제3자에게서 보전받는 금액(9호). "
                    "자기적립마일리지등 결제분은 공급가액에 포함하지 않음")
            if other > 0 and comp == 0:
                사유 += " — 자기적립 외 마일리지등 결제분을 보전받지 않음(자기생산·취득재화 공급이면 자기생산취득재화=True로 시가 과세 확인)"
        마일합 += base
        마일리지.append({"이름": name, "공급일": m["공급일"], "현금등": cash, "자기적립마일리지": own, "그외마일리지": other, "보전금액": comp,
                       "공급가액": base, "사유": 사유})
        판단.append({"항목": name, "결론": f"공급가액 {base:,}원 — {사유}", "근거": 마일_근거})
    과세표준 = sales - 차감 + 마일합
    if 과세표준 < 0:
        판단.append({"항목": "과세표준", "결론": "차감액이 매출보다 커서 음수 — 환입·에누리가 당기 매출보다 큰 과세기간(음수 그대로 신고)", "근거": "부가가치세법 제29조①⑤"})
    근거 = "부가가치세법 제29조①·⑤·⑥" + (", 시행령 제70조①1호" if any(a["종류"] == "환입" for a in adjustments) else "") + (f", {마일_근거}" if mileage_sales else "")
    return {"결과": {"과세표준": 과세표준, "조정전_매출": sales, "차감_합계": 차감, "마일리지등_거래_공급가액": 마일합, "매출세액": _floor(과세표준, 0.1) if 과세표준 > 0 else 0},
            "계산": {"조정_항목별": 항목별, "마일리지등_거래": 마일리지}, "판단": 판단, "근거": 근거,
            "주의": ["장려금을 금전이 아닌 재화로 주면 사업상 증여 여부를 따로 판정(vat_deemed_supply_items)",
                    "자기적립마일리지등 = 당초 공급하고 마일리지등을 적립해 준 그 사업자에게 사용한 것. 여러 사업자가 함께 쓰는 마일리지등은 적립·사용 실적 구분 관리 + 제3자 보전 없음 요건을 모두 갖춰야 함(영 제61조 9호 나목)",
                    "마일리지등 거래의 금액은 sales에 넣지 않는다(이 도구가 공급가액을 따로 계산해 더함)"]}
