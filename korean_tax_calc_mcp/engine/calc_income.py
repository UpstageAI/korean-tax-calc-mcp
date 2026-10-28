"""소득세·원천세 계산(2016~2026 귀속 연도표, 기본 2025 귀속) — 국세청 연말정산·중소기업 취업자 감면 안내 예시로 검증. 작성 Mia(윤승미)
플레이북: knowledge/14_소득세_원천세_연말정산_조사포인트.md. 2026 귀속 변경분은 표 추가 후 적용.
"""
import json
import math
import os

from .. import vocab


def _load_income_rules():
    """personal_income_rules.json 로드. 항목형 소득 입력 처리 규칙."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "personal_income_rules.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _process_income_items(year, income_items, rules):
    """income_items: [{kind, amount}] → 처리 후 소득금액, wage_only_gross, 항목별 처리 내역.

    반환: {"income": Effective 소득금액, "wage_only_gross": 총급여(근로소득만 있을 때) or None,
           "processing": [{kind, amount, 처리, 반영금액, 근거}]}
    """
    if not income_items:
        return {"income": 0, "wage_only_gross": None, "processing": []}

    VALID_KINDS = set(rules["rules"].keys())
    요약 = {k: 0 for k in VALID_KINDS}
    processing = []
    근로소득만_총급여 = None  # 근로소득 항목만 있고 다른 항목 없으면 총급여 저장

    for item in income_items:
        kind = item["kind"]
        amount = int(item["amount"])
        if kind not in VALID_KINDS:
            raise ValueError(f"지원하지 않는 income_items kind='{kind}' — 허용: {sorted(VALID_KINDS)}")
        요약[kind] += amount
        processing.append({"kind": kind, "amount": amount, "처리": "", "반영금액": 0, "근거": ""})

    # 이자·배당 합산 분리과세 판단 (제14조③6호)
    이자합계 = 요약["이자"]
    배당합계 = 요약["배당"]
    이자배당합계 = 이자합계 + 배당합계
    separate_이자배당 = 이자배당합계 > 0 and 이자배당합계 <= rules["rules"]["이자"]["분리과세_기준금액"]

    # 기타소득 분리과세 판단 (제14조③8호)
    기타금액 = 요약["기타소득금액"]
    separate_기타 = 기타금액 > 0 and 기타금액 <= rules["rules"]["기타소득금액"]["분리과세_기준금액"]

    # 사적연금 기준금액 (연도별)
    사적연금금액 = 요약["사적연금"]
    if year <= 2023:
        사적연금한도 = rules["rules"]["사적연금"]["분리과세_기준금액_2023이하"]
    else:
        사적연금한도 = rules["rules"]["사적연금"]["분리과세_기준금액_2024이상"]
    separate_사적연금 = 사적연금금액 > 0 and 사적연금금액 <= 사적연금한도

    # 전통주 비과세 한도 (제12조2호라목, 시행령 제9조의2)
    전통주금액 = 요약["전통주_제조소득_농어촌"]
    전통주한도 = rules["rules"]["전통주_제조소득_농어촌"]["비과세_한도금액"]
    전통주비과세 = 전통주금액 > 0 and 전통주금액 <= 전통주한도

    # 근로소득 공제 — 근로소득만 있는지에 따라 wage_only_gross 판단
    근로소득금액 = 요약["근로_총급여"]
    근로소득공제액 = 0
    근로소득공제후 = 0
    if 근로소득금액 > 0:
        근로소득공제액 = earned_deduction(근로소득금액, year)
        근로소득공제후 = 근로소득금액 - 근로소득공제액
        total_other = sum(요약[k] for k in VALID_KINDS if k not in ("근로_총급여", "이자", "배당", "비과세", "공적연금_과세제외"))
        total_other += (이자합계 if not separate_이자배당 else 0) + (배당합계 if not separate_이자배당 else 0)
        total_other += (사적연금금액 if not separate_사적연금 else 0)
        total_other += (기타금액 if not separate_기타 else 0)
        if total_other == 0:
            근로소득만_총급여 = 근로소득금액  # 근로소득만 있음

    # 소득금액 계산
    소득 = 0

    # 1) 이자·배당
    if separate_이자배당:
        for proc in processing:
            if proc["kind"] in ("이자", "배당"):
                proc["처리"] = f"분리과세(소득세법 제14조③6호, 이자·배당 합계 2천만 이하)"
                proc["반영금액"] = 0
                proc["근거"] = "소득세법 제14조③6호"
        # 소득에는 포함 안 함
    else:
        for proc in processing:
            if proc["kind"] == "이자":
                if 이자합계 > 0:
                    proc["처리"] = "종합과세(이자·배당 합계 2천만 초과)"
                    proc["반영금액"] = proc["amount"]
                    proc["근거"] = "소득세법 제14조③6호"
                    소득 += proc["amount"]
            elif proc["kind"] == "배당":
                if 배당합계 > 0:
                    proc["처리"] = "종합과세(이자·배당 합계 2천만 초과)"
                    proc["반영금액"] = proc["amount"]
                    proc["근거"] = "소득세법 제14조③6호"
                    소득 += proc["amount"]

    # 2) 근로소득
    if 근로소득금액 > 0:
        for proc in processing:
            if proc["kind"] == "근로_총급여":
                proc["처리"] = f"근로소득공제(제47조①) {근로소득공제액:,}원 → 근로소득금액 {근로소득공제후:,}원"
                proc["반영금액"] = 근로소득공제후
                proc["근거"] = "소득세법 제47조①"
                소득 += 근로소득공제후

    # 3) 사업소득
    if 요약["사업소득금액"] > 0:
        for proc in processing:
            if proc["kind"] == "사업소득금액":
                proc["처리"] = "사업소득금액(필요경비 차감 후) 그대로 합산"
                proc["반영금액"] = 요약["사업소득금액"]
                proc["근거"] = "소득세법 제19조"
                소득 += 요약["사업소득금액"]

    # 4)·5) 연금소득 — 연금소득공제는 종합과세되는 연금소득 합계(공적연금 + 종합과세 사적연금)에
    #   한 번만 적용(소득세법 제47조의2①, 한도 900만원). 항목별 반영금액은 금액 비율로 나눔.
    공적연금금액 = 요약["공적연금"]
    종합_사적연금 = 사적연금금액 if (사적연금금액 > 0 and not separate_사적연금) else 0
    연금합계 = 공적연금금액 + 종합_사적연금
    연금공제 = _pension_deduction(연금합계) if 연금합계 > 0 else 0
    연금_대상 = [proc for proc in processing
               if proc["kind"] == "공적연금" or (proc["kind"] == "사적연금" and 종합_사적연금 > 0)]
    남은공제 = 연금공제
    for i, proc in enumerate(연금_대상):
        몫 = 남은공제 if i == len(연금_대상) - 1 else (연금공제 * proc["amount"] // 연금합계 if 연금합계 else 0)
        남은공제 -= 몫
        proc["반영금액"] = proc["amount"] - 몫
        합계문 = (f"연금소득공제(제47조의2①)는 종합과세 연금소득 합계 {연금합계:,}원에 한 번 적용 → 공제 {연금공제:,}원"
                 f"(한도 900만원), 이 항목 몫 {몫:,}원 → {proc['반영금액']:,}원")
        if proc["kind"] == "공적연금":
            proc["처리"] = 합계문
            proc["근거"] = "소득세법 제47조의2①"
        else:
            proc["처리"] = f"종합과세(분리과세 기준 {'1,200만' if year <= 2023 else '1,500만'} 초과) — " + 합계문
            proc["근거"] = "소득세법 제14조③9호다목, 제47조의2①"
    소득 += 연금합계 - 연금공제

    if 사적연금금액 > 0 and separate_사적연금:
        for proc in processing:
            if proc["kind"] == "사적연금":
                proc["처리"] = f"분리과세 선택(기본 분리, {'1,200만' if year <= 2023 else '1,500만'} 이하)"
                proc["반영금액"] = 0
                proc["근거"] = "소득세법 제14조③9호다목"

    # 6) 기타소득
    if 기타금액 > 0:
        if separate_기타:
            for proc in processing:
                if proc["kind"] == "기타소득금액":
                    proc["처리"] = f"분리과세 선택(기본 분리, 300만 이하)"
                    proc["반영금액"] = 0
                    proc["근거"] = "소득세법 제14조③8호"
        else:
            for proc in processing:
                if proc["kind"] == "기타소득금액":
                    proc["처리"] = f"종합과세(300만 초과)"
                    proc["반영금액"] = 기타금액
                    proc["근거"] = "소득세법 제14조③8호"
                    소득 += 기타금액

    # 7) 양도소득금액
    if 요약["양도소득금액"] > 0:
        for proc in processing:
            if proc["kind"] == "양도소득금액":
                proc["처리"] = "양도소득금액 종합 합산"
                proc["반영금액"] = 요약["양도소득금액"]
                proc["근거"] = "소득세법 제14조①"
                소득 += 요약["양도소득금액"]

    # 8) 퇴직소득금액
    if 요약["퇴직소득금액"] > 0:
        for proc in processing:
            if proc["kind"] == "퇴직소득금액":
                proc["처리"] = "퇴직소득금액 종합 합산"
                proc["반영금액"] = 요약["퇴직소득금액"]
                proc["근거"] = "소득세법 제14조①"
                소득 += 요약["퇴직소득금액"]

    # 9) 전통주 제조소득
    if 전통주금액 > 0:
        if 전통주비과세:
            for proc in processing:
                if proc["kind"] == "전통주_제조소득_농어촌":
                    proc["처리"] = f"비과세(수도권 밖 읍·면 제조, 연 {전통주한도//10000}만 이하)"
                    proc["반영금액"] = 0
                    proc["근거"] = "소득세법 제12조2호라목, 시행령 제9조의2"
        else:
            for proc in processing:
                if proc["kind"] == "전통주_제조소득_농어촌":
                    proc["처리"] = f"비과세 한도({전통주한도//10000}만) 초과 → 전액 과세(질의회신 소득세과-1354) — {전통주금액:,}원 전액 종합 합산"
                    proc["반영금액"] = 전통주금액
                    proc["근거"] = "소득세법 제12조2호라목, 시행령 제9조의2, 제14조①, 질의회신 소득세과-1354"
                    소득 += 전통주금액

    # 10) 비과세
    if 요약["비과세"] > 0:
        for proc in processing:
            if proc["kind"] == "비과세":
                proc["처리"] = "비과세 → 소득금액 0"
                proc["반영금액"] = 0
                proc["근거"] = "소득세법 제12조"

    # 11) 공적연금_과세제외 (소득세법 시행령 제40조 — 소득공제 받지 않은 기여금 기초 연금)
    과세제외금액 = 요약.get("공적연금_과세제외", 0)
    if 과세제외금액 > 0:
        for proc in processing:
            if proc["kind"] == "공적연금_과세제외":
                proc["처리"] = "과세 제외 — 소득공제 받지 않은 기여금 기초 연금 (소득세법 시행령 제40조)"
                proc["반영금액"] = 0
                proc["근거"] = "소득세법 시행령 제40조"

    return {
        "income": 소득,
        "wage_only_gross": 근로소득만_총급여,
        "processing": processing,
    }


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


# ── 퇴직소득세(소득세법 제48조·제55조②) — 근속연수공제는 2023.1.1. 시행 개정표, 그 전은 구표 ─────
def retirement_service_deduction(years, retire_year=2025):
    """근속연수공제(제48조①1호). 근속연수는 1년 미만 절상한 정수.
    2023.1.1. 이후 퇴직: 5년 이하 100만×n, 10년 이하 500만+200만×(n−5), 20년 이하 1,500만+250만×(n−10), 초과 4,000만+300만×(n−20).
    2022.12.31. 이전 퇴직: 5년 이하 30만×n, 10년 이하 150만+50만×(n−5), 20년 이하 400만+80만×(n−10), 초과 1,200만+120만×(n−20)."""
    n = years
    if retire_year <= 2022:
        if n <= 5: return 300_000 * n
        if n <= 10: return 1_500_000 + 500_000 * (n - 5)
        if n <= 20: return 4_000_000 + 800_000 * (n - 10)
        return 12_000_000 + 1_200_000 * (n - 20)
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


def retirement_tax(income, years, retire_year=2025):
    """퇴직소득 산출세액. income=퇴직소득금액(비과세 제외), years=근속연수(1년 미만 절상).
    ① 근속연수공제(퇴직소득금액 한도, 제48조②) → ② 환산급여 = (금액−①)/근속연수×12
    → ③ 과세표준 = 환산급여 − 환산급여공제 → ④ 산출세액 = 기본세율(제55조①)(과세표준)/12×근속연수(제55조②).
    원 미만 절사만 적용(원천징수 10원 미만 절사는 국고금관리법 — 호출자 처리)."""
    if income <= 0 or years <= 0: return 0
    sd = min(retirement_service_deduction(years, retire_year), income)
    conv = (income - sd) / years * 12
    base = max(0, conv - converted_pay_deduction(conv))
    return int(_tier(base, RATES[_y(retire_year)]) / 12 * years)   # 기본세율은 퇴직한 해의 표(제55조②1호 "제1항의 세율")


# ── 원천징수세율(소득세법 제129조①②, 2025.1.1. 시행 법률 제20615호 기준) ─────────────────
WITHHOLDING_RATES = {
    "이자": 0.14, "비영업대금": 0.25, "온투업이자": 0.14,          # ①1호 라·나목
    "배당": 0.14, "출자공동사업자배당": 0.25,                        # ①2호 나·가목
    "사업": 0.03, "외국인직업운동가": 0.20,                          # ①3호
    "기타": 0.20, "기타_연금외수령등": 0.15, "기타_복권3억초과분": 0.30,  # ①6호 라·나·가목
    "봉사료": 0.05, "일용근로": 0.06,                                # ①8호·①4호 단서
    "비실명": 0.45,                                                  # ②2호
}

# 도구 설명에 쓰인 짧은 이름 → 세율표 키
WITHHOLDING_ALIASES = {"일용": "일용근로"}


def withholding_rate(kind, year=2025):
    """원천징수세율 지급연도별(소득세법 제129조). 2016~2026 중 변경:
    비실명 38%(~2017) → 40%(2018, 2017.12.19. 개정) → 42%(2019, 2018.12.31. 개정) → 45%(2023, 2022.12.31. 개정) — 모두 '시행 이후 지급분'.
    외국인직업운동가 20%: 2019.1.1. 이후 지급분(2018.12.31. 신설, 그 전은 사업소득 3%).
    온투업이자 14%: 2020.1.1. 이후 지급분(2018.12.31. 신설, 부칙 제14조①; 그 전은 비영업대금 25%).
    이자·배당 14%, 비영업대금 25%, 사업 3%, 기타 20%, 봉사료 5%, 일용 6%는 변동 없음."""
    y = _y(year)
    kind = WITHHOLDING_ALIASES.get(kind, kind)
    if kind not in WITHHOLDING_RATES:
        raise ValueError(f"입력 확인 필요 — 소득 종류 '{kind}'은(는) 지원하지 않음. 허용: {', '.join(list(WITHHOLDING_RATES) + list(WITHHOLDING_ALIASES))}")
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
    "예체능학원_초등저학년",
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


def _age_at_year_start(p, year=None):
    """과세기간 개시일(1월 1일) 현재 만 나이.

    제59조의4②2호나목(2024~)·제12조3호머목2) "과세기간 개시일 현재 6세 이하" 판정용.
    age_at_year_start가 있으면 그 값, birth_date(YYYY-MM-DD)와 year가 있으면 1월 1일 기준 계산,
    둘 다 없으면 age(과세기간 종료일 현재 만 나이)를 그대로 쓴다 — 종료일 6세 이하면 개시일에도 6세 이하,
    8세 이상이면 개시일에도 7세 이상이라 결론이 같다. 종료일 7세는 개시일 6세·7세가 갈리므로
    special_tax_credit 입력 검사에서 age_at_year_start 또는 birth_date를 묻는다.
    """
    if p.get("age_at_year_start") is not None:
        return int(p["age_at_year_start"])
    bd = p.get("birth_date")
    if bd and year:
        by, bm, bdd = (int(x) for x in str(bd)[:10].split("-"))
        return year - by - (1 if (bm, bdd) > (1, 1) else 0)
    return int(p.get("age", 0))


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
    """근로소득자 특별세액공제(보험료·의료비·교육비)와 표준세액공제 비교.

    연도별 한도·대상(소득세법 제59조의4, 시행령 제118조의5·제118조의6):
      의료비 — 일반(1호) 연 700만원. 특정(2호): 본인·종료일 65세 이상·장애인(전 연도),
        중증질환자 등(2018~), 개시일 현재 6세 이하(2024~). 미숙아·선천성이상아 20%(2022~),
        난임 20%(2017~2021)·30%(2022~). 안경·콘택트렌즈 1명당 연 50만원, 산후조리원 출산 1회 200만원(2019~).
      교육비 — 1명당 연 한도(같은 person 지출 합산): 취학전·초중고 300만원(교복 50만원·체험학습
        30만원(2017~) 포함), 대학생 900만원. 대입전형료 2023~. 부양가족 소득요건 2025년까지.
        초등 저학년(종료일 9세 미만·2학년 이하) 예체능학원·체육시설 수강료 2026~(1호마목, 300만원 한도에 합산).
    """
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

    # 6세 이하 의료비(2024~, 제59조의4②2호나목)는 과세기간 개시일 기준 — 종료일 7세는 개시일 6세·7세가 갈림
    if not problems and vocab.rule("특별세액공제_의료비", year).get("6세이하_특정"):
        _pd = {p.get("name"): p for p in persons}
        for i, e in enumerate(expenses):
            if e.get("kind") not in ("의료비", "안경", "미숙아·선천성이상아"):
                continue
            p = _pd.get(e.get("person"), {})
            if (p.get("relation") != "본인" and p.get("age") == 7
                    and p.get("age_at_year_start") is None and not p.get("birth_date")):
                problems.append(
                    f"지출 {i+1}: person='{p.get('name')}' age=7(과세기간 종료일 현재) — 의료비 6세 이하 특정지출"
                    f"(제59조의4②2호나목, 2024~)은 과세기간 개시일 현재 나이로 판정. "
                    f"age_at_year_start(1월 1일 현재 만 나이) 또는 birth_date(YYYY-MM-DD)를 넣을 것")

    # 초등 저학년 예체능학원(2026~, 제59조의4③1호마목): 종료일 현재 9세 미만 또는 2학년 이하
    if not problems and vocab.rule("특별세액공제_교육비", year).get("초등저학년_예체능"):
        _pd = {p.get("name"): p for p in persons}
        for i, e in enumerate(expenses):
            if e.get("kind") != "예체능학원_초등저학년":
                continue
            p = _pd.get(e.get("person"), {})
            if p.get("age", 0) >= 9 and p.get("school_grade") is None:
                problems.append(
                    f"지출 {i+1}: person='{p.get('name')}' age={p.get('age')} — 예체능학원 교육비(제59조의4③1호마목)는 "
                    f"과세기간 종료일 현재 9세 미만 또는 2학년 이하 초등학생만 해당. school_grade(학년)를 넣을 것")

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
    의료비미숙아 = 0     # 3호 후보 (2022~)
    의료비난임 = 0       # 4호 후보 (2022~), 3호 (2017~2021), 2호 (2016)

    voc_m = vocab.rule("특별세액공제_의료비", year)
    문턱 = total_salary * voc_m["문턱_비율"]
    일반한도_m = voc_m["일반_한도"]
    안경한도 = voc_m["안경_한도"]

    def _의료비_특정대상(p):
        """제59조의4②2호 대상자 여부.
        본인 / 과세기간 종료일 현재 65세 이상 / 장애인 / 중증질환자·희귀난치성질환자·결핵환자(2018~,
        2017.12.19 개정) / 과세기간 개시일 현재 6세 이하(2024~). 2016~2017 중증질환자는 1호 일반."""
        if p.get("relation") == "본인":
            return True
        if voc_m.get("6세이하_특정") and _age_at_year_start(p, year) <= 6:
            return True
        severe = p.get("severe_illness", False) and voc_m.get("중증_특정", False)
        return p.get("age", 0) >= 65 or p.get("disabled", False) or severe

    안경_사람별 = {}
    for e in expenses:
        k = e["kind"]
        pn = e["person"]
        amount = max(0, e["amount"] - e.get("reimbursed", 0))

        # 미숙아·선천성이상아 의료비는 2022년부터 3호(20%)로 따로 공제. 그 전에는 일반 의료비와 같이 1·2호로 분류.
        if k == "미숙아·선천성이상아" and not voc_m.get("미숙아_율", 0):
            k = "의료비"

        if k == "의료비":
            if _의료비_특정대상(persons_dict.get(pn, {})):
                의료비특정 += amount
            else:
                의료비일반 += amount

        elif k == "안경":
            # 1명당 연 50만원(영 제118조의5①4호) — 사람별로 모은 뒤 아래에서 한도 적용·분류
            안경_사람별[pn] = 안경_사람별.get(pn, 0) + amount

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
            의료비미숙아 += amount

        elif k == "난임시술":
            의료비난임 += amount

        elif k == "미용성형·건강증진":
            pass  # 공제 제외

    # 안경·콘택트렌즈: 기본공제대상자(나이·소득 무관) 1명당 연 50만원 한도 후, 사람에 따라 1호·2호 분류
    의료비_한도판단 = []
    for pn, 합 in 안경_사람별.items():
        인정 = min(합, 안경한도)
        if 합 > 안경한도:
            의료비_한도판단.append({"항목": "안경", "결론": (
                f"'{pn}' 안경·콘택트렌즈 합계 {합:,}원 → 1명당 연 {안경한도:,}원 한도로 {인정:,}원 인정"
                "(같은 person의 지출을 합산)"), "근거": "소득세법 시행령 제118조의5①4호"})
        if _의료비_특정대상(persons_dict.get(pn, {})):
            의료비특정 += 인정
        else:
            의료비일반 += 인정

    # 미달액 순서로 1호→2호→3호→4호 공제대상 계산
    미달액 = max(0, 문턱 - 의료비일반)
    h1_target = min(max(0, 의료비일반 - 문턱), 일반한도_m)

    h2_target = max(0, 의료비특정 - 미달액)
    미달액 = max(0, 미달액 - 의료비특정)

    h3_target = max(0, 의료비미숙아 - 미달액)
    미달액 = max(0, 미달액 - 의료비미숙아)

    h4_target = max(0, 의료비난임 - 미달액)

    미숙아율 = voc_m.get("미숙아_율", 0)
    난임율 = voc_m.get("난임_율", 0)
    의료비공제 = _won(h1_target * 0.15 + h2_target * 0.15 +
                       h3_target * 미숙아율 + h4_target * 난임율)

    # ── 교육비 (제59조의4③) ──────────────────────────────────────────────
    교육비대상합계 = 0
    사람별 = []
    교육비_한도판단 = []
    voc_e = vocab.rule("특별세액공제_교육비", year)
    체험할아이면 = voc_e.get("체험학습", False)
    학자금상환이면 = voc_e.get("학자금상환", False)
    대입전형료이면 = voc_e.get("대입전형료", False)
    초등저학년예체능이면 = voc_e.get("초등저학년_예체능", False)  # 2026~ 1호마목
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
        취학전초중고합 = 0  # 취학전+초중고 (교복·체험학습은 따로 모아 1명당 한도 적용 후 300만원 한도에 합산)
        교복합 = 0
        체험합 = 0
        대학합 = 0
        for e in expenses:
            if e["person"] != name:
                continue
            kind = e["kind"]
            amount = max(0, e["amount"] - e.get("reimbursed", 0) - e.get("tax_exempt_subsidy", 0))

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
                # 한도는 모두 학생 1명당 연 금액 — 항목별이 아니라 사람별로 합산한 뒤 적용
                if kind == "교복":
                    교복합 += amount
                elif kind == "체험학습":
                    if 체험할아이면:
                        체험합 += amount
                elif kind in ("교육비_취학전", "교육비_초중고"):
                    취학전초중고합 += amount
                elif kind == "예체능학원_초등저학년":
                    if 초등저학년예체능이면 and (age < 9 or (p.get("school_grade") is not None
                                                            and int(p["school_grade"]) <= 2)):
                        취학전초중고합 += amount
                elif kind in ("교육비_대학", "대입전형료"):
                    if kind == "대입전형료" and not 대입전형료이면:
                        continue
                    대학합 += amount

        if rel != "본인":
            # 교복 1명당 연 50만원(영 제118조의6①4호), 체험학습 1명당 연 30만원(같은 항 6호, 2017~)
            교복인정 = min(교복합, voc_e["교복_한도"])
            체험인정 = min(체험합, voc_e["체험학습_한도"])
            # 취학전·초중고(교복·체험학습 포함) 1명당 연 300만원, 대학생 1명당 연 900만원(법 제59조의4③1호 단서)
            초중고인정 = min(취학전초중고합 + 교복인정 + 체험인정, 취학전초중고한도)
            대학인정 = min(대학합, 대학한도)
            person_total += 초중고인정 + 대학인정
            for _항목, _합, _인정, _한도 in (("교복", 교복합, 교복인정, voc_e["교복_한도"]),
                                             ("체험학습", 체험합, 체험인정, voc_e["체험학습_한도"]),
                                             ("교육비_대학", 대학합, 대학인정, 대학한도)):
                if _합 > _한도:
                    교육비_한도판단.append({"항목": _항목, "결론": (
                        f"'{name}' {_항목} 합계 {_합:,}원 → 1명당 연 {_한도:,}원 한도로 {_인정:,}원 인정"
                        "(같은 person의 지출을 합산. person이 같으면 같은 사람으로 봄)"),
                        "근거": "소득세법 제59조의4③1호 단서, 시행령 제118조의6①4·6호"})

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
    판단 = list(교육비_한도판단) + list(의료비_한도판단)
    for e in expenses:
        k = e["kind"]
        pn = e["person"]
        p = persons_dict.get(pn, {})
        rel = p.get("relation")
        age = p.get("age", 0)
        disabled = p.get("disabled", False)

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
        elif k == "예체능학원_초등저학년":
            if not 초등저학년예체능이면:
                판단.append({"항목": k, "결론": f"{year}년 초등학생 예체능학원·체육시설 수강료 공제 대상 아님(2026~)",
                             "근거": "소득세법 제59조의4③1호마목"})
            elif rel not in ("배우자", "직계비속", "입양자", "위탁아동", "형제자매"):
                판단.append({"항목": k, "결론": "직계비속등(1호) 대상 항목 — 공제 제외",
                             "근거": "소득세법 제59조의4③1호마목"})
            elif not (age < 9 or (p.get("school_grade") is not None and int(p["school_grade"]) <= 2)):
                판단.append({"항목": k, "결론": f"'{pn}' 종료일 현재 9세 이상·3학년 이상 — 공제 제외",
                             "근거": "소득세법 제59조의4③1호마목"})
            else:
                판단.append({"항목": k, "결론": (
                    "예능학원(학원법 시행령 별표 2 예능분야)·체육시설의 월 단위·주 1회 이상 교습과정 수강료만 해당. "
                    "취학전·초중고 1명당 연 300만원 한도에 합산"),
                    "근거": "소득세법 제59조의4③1호마목, 시행령 제118조의6⑩"})
        elif k == "직계비속학자금대출지급":
            판단.append({"항목": k, "결론": "직계비속등이 학자금 대출로 낸 교육비 — 공제 제외(2017~)",
                         "근거": "소득세법 제59조의4③1호 단서"})
        elif k == "미용성형·건강증진":
            판단.append({"항목": k, "결론": "미용·성형·건강증진 의료비 — 공제 제외",
                         "근거": "소득세법 시행령 제118조의5②"})
        elif k == "의료비":
            # 의료비는 소득·나이 무관 공제대상(제59조의4② 괄호)
            if (p.get("severe_illness") and not voc_m.get("중증_특정", False) and p.get("relation") != "본인"
                    and not (age >= 65 or disabled)):
                판단.append({"항목": k, "결론": f"{year}년은 중증질환자 등 의료비가 특정의료비(2호)가 아님 — 2018년부터(2017.12.19 개정). 일반 의료비(1호, 연 700만원 한도)로 계산",
                             "근거": "소득세법 제59조의4②1호(2017.12.19 개정 전)"})
            if voc_m.get("6세이하_특정") and p.get("relation") != "본인" and _age_at_year_start(p, year) <= 6 \
                    and not (p.get("age", 0) >= 65 or p.get("disabled") or p.get("severe_illness")):
                판단.append({"항목": k, "결론": f"'{pn}' 과세기간 개시일 현재 {_age_at_year_start(p, year)}세(6세 이하) — 특정의료비(2호, 한도 없음)",
                             "근거": "소득세법 제59조의4②2호나목(2024~)"})
        elif k == "미숙아·선천성이상아":
            if not voc_m.get("미숙아_율", 0):
                판단.append({"항목": k, "결론": f"{year}년은 미숙아·선천성이상아 의료비 별도 공제율(20%) 전 — 일반·특정 의료비(15%)로 분류",
                             "근거": "소득세법 제59조의4②3호(2022~)"})
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
        elif k in ("교육비_취학전", "교육비_초중고", "교육비_대학", "교육비_대학원", "교복", "체험학습", "대입전형료"):
            # company subsidy 판단
            employer_subsidy = e.get("employer_subsidy", 0)
            tax_exempt_subsidy = e.get("tax_exempt_subsidy", 0)
            if employer_subsidy > 0:
                판단.append({"항목": k, "결론": f"회사 지급 학자금 {employer_subsidy:,}원은 근로소득으로 과세되므로 교육비에서 차감하지 않음(시행령 제118조의6②은 소득세·증여세 비과세 학자금·장학금만 제외)",
                             "근거": "소득세법 시행령 제118조의6②"})
            if tax_exempt_subsidy > 0:
                판단.append({"항목": k, "결론": f"비과세 학자금·장학금 {tax_exempt_subsidy:,}원 차감",
                             "근거": "소득세법 시행령 제118조의6②"})

    # 교육비 지출이 하나라도 있으면 employer_subsidy 입력 여부와 무관하게 규칙을 항상 표기
    _교육비_종류 = ("교육비_취학전", "교육비_초중고", "교육비_대학", "교육비_대학원",
                   "교복", "체험학습", "대입전형료", "특수교육비", "발달재활서비스")
    if any(e.get("kind") in _교육비_종류 for e in expenses) and 교육비대상합계 > 0:
        판단.append({"항목": "교육비(일반)", "결론": (
            "회사·학교 등에서 받은 학자금·보조금: 근로소득으로 과세된 것은 교육비에서 차감하지 않음, "
            "소득세·증여세 비과세인 장학금·학자금만 차감(시행령 제118조의6②). "
            "차감 전 금액을 amount에 넣고 보조금은 employer_subsidy/tax_exempt_subsidy에 넣을 것"
        ), "근거": "소득세법 시행령 제118조의6②"})

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
                "미숙아": 의료비미숙아,
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


# ── 종합소득 인적공제(소득세법 제50조·제51조·제53조, 영 제106조) ────────────────────


def personal_deduction(year, taxpayer, persons):
    """종합소득 인적공제(기본공제·추가공제). 소득세법 제50조·제51조·제53조.

    입력:
      year: 귀속연도(2016~2026)
      taxpayer: {sex, birth_year, has_spouse, household_head(False), comprehensive_income, disabled(False)}
      persons: [{name, relation, birth_year, income(0), wage_only_gross(없으면 생략), disabled(False), cohabiting(True),
                 income_items([{kind, amount}])}] — income_items가 있으면 income/wage_only_gross 대신 사용.
        relation: 배우자|직계존속|직계비속|입양자|형제자매|수급자|위탁아동 (동의어: 아들·딸·자녀→직계비속, 부친·모친·부모→직계존속 등)
    결과: {"기본공제", "추가공제", "공제 전 합계", "인적공제", "사람별": [{name, 기본공제(bool), 사유(str|null), 추가공제:[{항목, 금액}], 소득처리내역(선택)}]}
    """
    if year < 2016 or year > 2026:
        return {"error": f"입력 확인 필요 — 계산하지 않음", "문제": [f"year={year}은(는) 지원 범위(2016~2026) 밖"]}

    # main의 RELATION_SYNONYMS로 정규화 후 허용값 검사
    for i, p in enumerate(persons):
        rel = p.get("relation", "")
        if rel in RELATION_SYNONYMS:
            p["relation"] = RELATION_SYNONYMS[rel]  # 동의어 → 정식값 치환
            rel = p["relation"]
        if rel not in ALLOWED_RELATIONS or rel == "본인":
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"persons '{p.get('name', '?')}': relation '{rel}' 허용값 아님 — 허용: {', '.join(a for a in ALLOWED_RELATIONS if a != '본인')}"]}

    # birth_year 누락 검증 — KeyError 대신 명확한 오류 문장
    if "birth_year" not in taxpayer:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"taxpayer: birth_year 필요 — 기본공제 본인 나이 계산용"]}
    for i, p in enumerate(persons):
        if "birth_year" not in p:
            rel = p.get("relation", "?")
            name = p.get("name", "")
            label = f"persons[{i}]" + (f" ({name})" if name else "") + f" ({rel}): birth_year 필요"
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [label]}

    # income_items 처리: rules 로드
    rules = _load_income_rules()

    # 사람별 소득 처리 — 입력 dict를 복사해 내부 값(_effective_income 등)을 덧붙이지 않음
    persons_copy = [dict(p) for p in persons]
    for p in persons_copy:
        income_items = p.get("income_items")
        # income_items 없이 income 또는 wage_only_gross만 오면 오류 (옛 금액 입력 거절)
        if income_items is None:
            if "income" in p or p.get("wage_only_gross") is not None:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"{p['name']}: 부양가족 소득은 income_items로 종류별로 넣어 주세요. "
                                 f"예: [{{\"kind\": \"이자\", \"amount\": 10000000}}] "
                                 f"근로소득만 있으면 {{\"kind\": \"근로_총급여\", ...}}"]}
            p["_effective_income"] = 0
            p["_wage_only_gross"] = None
            p["_income_processing"] = None
        else:
            if "income" in p or p.get("wage_only_gross") is not None:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [f"{p['name']}: income과 income_items를 함께 입력할 수 없음 — 둘 중 하나만 사용"]}
            try:
                result = _process_income_items(year, income_items, rules)
            except ValueError as e:
                return {"error": "입력 확인 필요 — 계산하지 않음",
                        "문제": [str(e)]}
            p["_effective_income"] = result["income"]
            p["_wage_only_gross"] = result["wage_only_gross"]
            p["_income_processing"] = result["processing"]

    # 본인
    본인_name = "본인"

    def age(p):
        return year - p["birth_year"]

    def income_ok(p):
        """소득 요건: _effective_income ≤ 100만. _wage_only_gross가 있으면 추가로 ≤ 500만 필요.
        (근로소득만 있는 경우 총급여 500만원 이하는 소득금액이 0이더라도 요건 충족,
        총급여 500만원 초과는 소득금액이 0이더라도 소득 요건 불충족)"""
        inc = p.get("_effective_income", 0)
        wog = p.get("_wage_only_gross")
        if inc <= 1_000_000:
            # income 요건 충족. wage_only_gross가 있으면 추가 확인
            if wog is not None:
                return wog <= 5_000_000
            return True
        if wog is not None and wog <= 5_000_000:
            return True
        return False

    def age_ok(rel, a, disabled):
        """나이 요건 충족 여부. disabled면 나이 요건 면제."""
        if disabled:
            return True
        if rel == "배우자" or rel == "수급자" or rel == "위탁아동":
            return True  # 나이 요건 없음
        if rel == "직계존속":
            return a >= 60
        if rel in ("직계비속", "입양자"):
            return a <= 20
        if rel == "형제자매":
            return a <= 20 or a >= 60
        return False

    def cohabiting_ok(rel, p):
        """동거 요건: 형제자매·수급자는 cohabiting=True 필요.
        직계존속은 별거해도 인정(제53조③). 그 외 동거 요건 없음."""
        if rel in ("형제자매", "수급자"):
            return bool(p.get("cohabiting", True))
        return True  # 나머지 관계는 동거 요건 없음

    # 기본공제 대상자 판정
    기본공제대상자 = {}  # name → bool
    사람별_detail = []  # 출력 순서: 본인(맨 앞) + persons 순서

    # 본인: 항상 기본공제 대상
    기본공제대상자[본인_name] = True
    사람별_detail.append({
        "name": 본인_name,
        "기본공제": True,
        "사유": None,
        "추가공제": [],
        "_is_self": True,
        "_relation": None,
        "_p": {"birth_year": taxpayer["birth_year"], "disabled": taxpayer.get("disabled", False),
               "income": 0, "wage_only_gross": None},
    })

    for p in persons_copy:
        rel = p["relation"]
        a = age(p)
        ok_income = income_ok(p)
        ok_age = age_ok(rel, a, p.get("disabled", False))
        ok_cohab = cohabiting_ok(rel, p)

        name = p["name"]
        if ok_income and ok_age and ok_cohab:
            기본공제대상자[name] = True
            사유 = None
        else:
            기본공제대상자[name] = False
            # 사유 구성
            사유_parts = []
            if not ok_income:
                inc = p.get("_effective_income", 0)
                wog = p.get("_wage_only_gross")
                if wog is not None:
                    if inc > 1_000_000:
                        사유_parts.append("소득금액 100만원 초과")
                    사유_parts.append(f"총급여 {wog:,}원 > 500만원")
                else:
                    사유_parts.append("소득금액 100만원 초과")
            if not ok_age and not p.get("disabled", False):
                if rel == "직계존속":
                    사유_parts.append(f"직계존속 {a}세(60세 미만)")
                elif rel in ("직계비속", "입양자"):
                    사유_parts.append(f"{rel} {a}세(20세 초과)")
                elif rel == "형제자매":
                    사유_parts.append(f"형제자매 {a}세(20세 초과 & 60세 미만)")
            if not ok_cohab:
                if rel == "형제자매":
                    사유_parts.append("형제자매 동거 아님")
                elif rel == "수급자":
                    사유_parts.append("수급자 동거 아님")
            사유 = ", ".join(사유_parts) if 사유_parts else None

        사람별_detail.append({
            "name": name,
            "기본공제": 기본공제대상자[name],
            "사유": 사유,
            "추가공제": [],
            "_is_self": False,
            "_relation": rel,
            "_p": p,
        })

    # --- 추가공제 ---
    # 경로우대 100만: 기본공제대상자 & 70세 이상
    # 장애인 200만: 기본공제대상자 & disabled (본인도 가능)
    # 부녀자 50만: 본인 여성 & 종합소득 ≤ 3천만 & (has_spouse 또는 (배우자 없음 + household_head + 기본공제대상 부양가족 1명 이상(배우자 제외)))
    # 한부모 100만: 배우자 없음 & 기본공제대상 직계비속/입양자 1명 이상. 부녀자와 중복 시 한부모만.

    추가공제_합계 = 0
    경로우대_대상 = set()
    장애인_대상 = set()
    부녀자_대상 = False
    한부모_대상 = False

    # 경로우대·장애인은 모든 기본공제대상자 대상 (본인 포함)
    for entry in 사람별_detail:
        name = entry["name"]
        if not 기본공제대상자.get(name, False):
            continue
        p = entry["_p"]
        a = age(p) if not entry["_is_self"] else (year - taxpayer["birth_year"])
        disabled = p.get("disabled", False) if not entry["_is_self"] else taxpayer.get("disabled", False)
        if a >= 70:
            경로우대_대상.add(name)
        if disabled:
            장애인_대상.add(name)

    # 부녀자 요건
    spend = taxpayer.get("comprehensive_income", 0)
    sex = taxpayer.get("sex", "남")
    has_spouse = taxpayer.get("has_spouse", False)
    hh = bool(taxpayer.get("household_head", False))

    if sex == "여" and spend <= 30_000_000:
        if has_spouse:
            부녀자_대상 = True
        elif not has_spouse and hh:
            # 배우자 없는 기본공제대상 부양가족(배우자 제외) 1명 이상
            fam_deps = [e for e in 사람별_detail
                        if not e["_is_self"] and e["_relation"] != "배우자" and 기본공제대상자.get(e["name"], False)]
            if len(fam_deps) >= 1:
                부녀자_대상 = True

    # 한부모 요건: 배우자 없음 & 기본공제대상 직계비속/입양자 1명 이상
    if not has_spouse:
        child_deps = [e for e in 사람별_detail
                      if not e["_is_self"] and e["_relation"] in ("직계비속", "입양자") and 기본공제대상자.get(e["name"], False)]
        if len(child_deps) >= 1:
            한부모_대상 = True

    # 사람별 추가공제 구성
    for entry in 사람별_detail:
        name = entry["name"]
        if not 기본공제대상자.get(name, False):
            continue
        extra = []
        if name in 경로우대_대상:
            extra.append({"항목": "경로우대", "금액": 1_000_000})
        if name in 장애인_대상:
            extra.append({"항목": "장애인", "금액": 2_000_000})
        if entry["_is_self"] and 부녀자_대상 and not 한부모_대상:
            extra.append({"항목": "부녀자", "금액": 500_000})
        if entry["_is_self"] and 한부모_대상:
            extra.append({"항목": "한부모", "금액": 1_000_000})
        entry["추가공제"] = extra

    기본공제_금액 = sum(1_500_000 for e in 사람별_detail if 기본공제대상자.get(e["name"], False))
    추가공제_금액 = sum(e["금액"] for entry in 사람별_detail for e in entry["추가공제"])

    공제전합계 = 기본공제_금액 + 추가공제_금액
    인적공제 = min(공제전합계, spend)  # 제51조④: comprehensive_income 초과분 없음

    # 사람별 출력: 본인 맨 앞, 추가공제 항목 정리, 소득처리내역 포함
    결과_사람별 = []
    for entry in 사람별_detail:
        name = entry["name"]
        추가목록 = [{"항목": e["항목"], "금액": e["금액"]} for e in entry["추가공제"]]
        사람별항목 = {
            "name": name,
            "기본공제": 기본공제대상자.get(name, False),
            "사유": entry["사유"],
            "추가공제": 추가목록,
        }
        # 소득처리내역(income_items 사용 시)
        p = entry.get("_p", {})
        if p.get("_income_processing") is not None:
            사람별항목["소득처리내역"] = p["_income_processing"]
        결과_사람별.append(사람별항목)

    return {
        "결과": {
            "기본공제": 기본공제_금액,
            "추가공제": 추가공제_금액,
            "공제 전 합계": 공제전합계,
            "인적공제": 인적공제,
            "사람별": 결과_사람별,
        },
        "근거": "소득세법 제50조·제51조·제53조",
    }


# ── 연금소득금액(소득세법 제20조의3·제14조③9호·제47조의2·제64조의4) ────────────────────


def pension_income(year, public_pension=0, private_pension=0,
                   retirement_source_pension=0, medical_withdrawal=0,
                   private_choice="분리", public_pension_detail=None):
    """연금소득금액 계산. 소득세법 제20조의3·제14조③9호·제47조의2·제64조의4·제40조.

    입력:
      year: 귀속연도(2016~2026)
      public_pension: 공적연금 과세분(2002년 이후 기여분 기준 금액). public_pension_detail 사용 시 0이어야 함.
      private_pension: 연금계좌 연금수령분 중 퇴직소득 재원·의료목적 인출 외
      retirement_source_pension: 퇴직소득 재원 연금수령 (항상 분리과세)
      medical_withdrawal: 의료목적·부득이한 사유 인출 (항상 분리과세)
      private_choice: "분리"|"종합" (기본 "분리")
      public_pension_detail: {수령액, 환산소득_2002이후, 환산소득_전체, 과세제외기여금?(기본 0)}.
        공적연금 과세분 = max(0, int(수령액 × 환산소득_2002이후 ÷ 환산소득_전체) − 과세제외기여금) (소득세법 시행령 제40조①, 국민연금 기준).
    결과: {"총연금액", "분리과세연금소득", "연금소득공제", "연금소득금액", 안내(선택), 근거}
    """
    if year < 2016 or year > 2026:
        return {"error": f"입력 확인 필요 — 계산하지 않음", "문제": [f"year={year}은(는) 지원 범위(2016~2026) 밖"]}

    # public_pension_detail 처리
    if public_pension_detail is not None:
        if public_pension != 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["public_pension과 public_pension_detail을 함께 입력할 수 없음 — 둘 중 하나만 사용"]}
        수령액 = int(public_pension_detail["수령액"])
        환산소득_2002이후 = int(public_pension_detail["환산소득_2002이후"])
        환산소득_전체 = int(public_pension_detail["환산소득_전체"])
        과세제외기여금 = int(public_pension_detail.get("과세제외기여금", 0))
        if 환산소득_전체 <= 0:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["환산소득_전체 ≤ 0 불가능"]}
        if 환산소득_2002이후 > 환산소득_전체:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["환산소득_2002이후 > 환산소득_전체 불가능"]}
        # 공적연금 과세분 = max(0, int(수령액 × 환산소득_2002이후 ÷ 환산소득_전체) − 과세제외기여금) (소득세법 시행령 제40조①)
        public_pension = max(0, int(수령액 * 환산소득_2002이후 / 환산소득_전체) - 과세제외기여금)

    # 분리과세 기준: 2023년 이하 12,000,000, 2024년 이상 15,000,000
    separate_threshold = 12_000_000 if year <= 2023 else 15_000_000

    # 항상 분리과세연금소득: retirement_source_pension, medical_withdrawal
    always_separate = retirement_source_pension + medical_withdrawal

    # private_pension 처리
    included_private = 0
    private_separate = 0
    if private_pension > 0:
        if private_pension <= separate_threshold and private_choice == "분리":
            private_separate = private_pension
        else:
            included_private = private_pension

    # 총연금액 = public_pension + 포함된 private_pension
    총연금액 = public_pension + included_private

    # 분리과세연금소득 = 항상 분리 + 선택된 분리 private
    분리과세연금소득 = always_separate + private_separate

    # 연금소득공제(제47조의2)
    연금소득공제 = _pension_deduction(총연금액)

    연금소득금액 = 총연금액 - 연금소득공제

    # 안내: year ≥ 2023이고 총연금액에 private_pension이 포함되면
    안내 = None
    if year >= 2023 and included_private > 0:
        안내 = f"사적연금 {included_private:,}원은 종합과세 대신 15% 분리 세액계산 선택 가능(제64조의4)"

    return {
        "결과": {
            "총연금액": 총연금액,
            "분리과세연금소득": 분리과세연금소득,
            "연금소득공제": 연금소득공제,
            "연금소득금액": 연금소득금액,
        },
        "안내": 안내,
        "근거": "소득세법 제20조의3·제14조③9호·제47조의2·제64조의4",
    }


def _pension_deduction(total_pension):
    """연금소득공제(제47조의2): 350만 이하 전액 / 700만 이하 350만+(초과분×40%) /
    1,400만 이하 490만+(초과분×20%) / 초과 630만+(초과분×10%), 최대 9,000,000,
    총연금액을 넘지 않음."""
    if total_pension <= 0:
        return 0
    if total_pension <= 3_500_000:
        ded = total_pension
    elif total_pension <= 7_000_000:
        ded = 3_500_000 + (total_pension - 3_500_000) * 0.40
    elif total_pension <= 14_000_000:
        ded = 4_900_000 + (total_pension - 7_000_000) * 0.20
    else:
        ded = 6_300_000 + (total_pension - 14_000_000) * 0.10
    ded = int(ded)
    return min(ded, 9_000_000, total_pension)

