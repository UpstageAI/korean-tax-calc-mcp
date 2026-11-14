"""외국인근로자 단일세율 과세특례(조특법 제18조의2)·외국인기술자 소득세 감면(조특법 제18조) 계산.

원문 대조(법제처 DRF eflaw, 2026-11-14 조회 — 원자료 통합테스트/고도화_1114/raw_foreign_a/):
  조세특례제한법 연말 시행본
    2016 시행 2016.10.04.(법률 제13560호 시행본, 제18조·제18조의2 최종 개정 2014.12.23. 법률 제12853호)
    2017 시행 2017.09.12.  2018 시행 2018.12.24.  2019 시행 2019.12.31.  2020 시행 2020.12.10.
    2021 시행 2021.12.30.  2022 시행 2022.12.08.  2023 시행 2023.12.21.  2024 시행 2024.07.10.
    2025 시행 2025.11.11.  2026 시행 2026.09.18.
  개정·부칙
    법률 제12173호(2014.1.1. 시행) 부칙 제59조 — 2014.1.1. 전에 근무를 시작한 외국인근로자는 종전 규정(특수관계기업 근로는 제외)
    법률 제12853호(2015.1.1. 시행) 부칙 제8조 — 제18조의2제2항 본문 개정규정을 위 부칙 제59조 적용자에게도 적용
    법률 제12853호 부칙 제61조 — 그 시행 당시 근로 중인 외국인기술자는 종전 제18조제2항
    법률 제14390호(2017.1.1. 시행) — 세율 17% → 19%, 최초 근로 시작 기한 2018.12.31.
        부칙 제10조 ① 2014.1.1. 전 근무 시작자는 2018.12.31.까지만, 19%
                     ② 적용기한 규정은 2014.1.1. 이후 근무 시작자부터
                     ③ 시행 전 발생 소득분은 종전 세율(17%)
    법률 제16009호(2019.1.1. 시행) — 제18조 감면기간 2년 → 5년(최초 근로 2021.12.31.까지), 제18조의2 시작 기한 2021.12.31.
        부칙 제7조(감면기간은 시행 이후 최초 근로 제공분부터)·제40조(시행 전 근무 시작자는 종전 감면기간)
    법률 제16835호(2020.1.1. 시행) — 제18조제1항 단서 소재·부품·장비 70%(3년)+50%(2년), 최초 근로 2022.12.31.까지,
        제18조제3항 원천징수 "징수할 소득세에서 감면세액을 제외한 금액". 부칙 제11조(시행 이후 최초 근로 제공분부터)
    법률 제18634호(2022.1.1. 시행) — 제18조·제18조의2 시작 기한 2023.12.31.(개별 적용례 없음, 부칙 제2조① 일반적 적용례)
    법률 제19199호(2023.1.1. 시행) — 제18조 감면기간 10년, 제18조의2 적용기간 20년
        부칙 제9조(시행 당시 최초 근로일부터 5년이 지나지 아니한 외국인기술자에도 적용)
        부칙 제10조(시행 당시 최초 근로일부터 20년이 지나지 아니한 외국인근로자에도 적용)
    법률 제19936호(2024.1.1. 시행) — 제18조·제18조의2 시작 기한 2026.12.31., 제18조의2제3항 괄호(복리후생 비과세 중
        대통령령으로 정하는 소득은 비과세 유지). 부칙 제6조(시행 이후 소득을 지급받는 경우부터)
  조세특례제한법 시행령 제16조(외국인기술자 범위)·제16조의2(특수관계기업·지역본부·신청·⑤ 대통령령으로 정하는 소득 =
    소득세법 시행령 제17조의4제1호 — 사택 제공 이익)
  지방세특례제한법 제106조의2(외국인근로자 개인지방소득세 — 제18조의2제2항 세율의 100분의 10), 제106조(외국인기술자) —
    현행본(2026.6.2. 시행, 법률 제21738호)만 대조
  소득세법 제59조의5(세액의 감면: 산출세액 × 감면대상 소득금액 / 종합소득금액) — 현행본(2026.1.1. 시행)만 대조
  해석: 기획재정부 소득세제과-135(2023.2.21.) 인용 서면-2023-국제세원-0193(2023.2.27.) — 법률 제19199호 적용 시
    2014.1.1. 현재 근무 중인 외국인근로자의 '최초로 근로를 제공한 날'은 2014.1.1., 2014.1.1. 이후 재입국한 경우는 재입국 후 최초 근로일

원 미만: 법 문언에 끝수 처리가 없어 최종 금액만 원 미만 절사(중간값은 분수로 유지).
"""
from __future__ import annotations

from datetime import date
from fractions import Fraction

from . import calc_income as I

# ── 제18조의2 연도표(연말 시행본 문언) ──────────────────────────────────────────
# start_deadline: 본문 '○○년 12월 31일 이전에 국내에서 최초로 근로를 제공하기 시작하는 경우'(None = 문언에 없음)
# period: '최초로 근로를 제공한 날부터 N년 이내에 끝나는 과세기간'
# tax_year_limit: 2016 시행본 본문 '(2016년 12월 31일까지만 해당한다)' 과세기간 기한
FLAT_TEXT = {
    2016: {"rate": 17, "start_deadline": None, "period": 5, "tax_year_limit": 2016, "welfare_kept": False,
           "law": "법률 제12853호(2014.12.23. 개정) 문언 — 2016.10.04. 시행본"},
    2017: {"rate": 19, "start_deadline": date(2018, 12, 31), "period": 5, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제14390호(2016.12.20.) — 2017.09.12. 시행본"},
    2018: {"rate": 19, "start_deadline": date(2018, 12, 31), "period": 5, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제14390호(2016.12.20.) — 2018.12.24. 시행본"},
    2019: {"rate": 19, "start_deadline": date(2021, 12, 31), "period": 5, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제16009호(2018.12.24.) — 2019.12.31. 시행본"},
    2020: {"rate": 19, "start_deadline": date(2021, 12, 31), "period": 5, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제16009호(2018.12.24.) — 2020.12.10. 시행본"},
    2021: {"rate": 19, "start_deadline": date(2021, 12, 31), "period": 5, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제16009호(2018.12.24.) — 2021.12.30. 시행본"},
    2022: {"rate": 19, "start_deadline": date(2023, 12, 31), "period": 5, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제18634호(2021.12.28.) — 2022.12.08. 시행본"},
    2023: {"rate": 19, "start_deadline": date(2023, 12, 31), "period": 20, "tax_year_limit": None, "welfare_kept": False,
           "law": "법률 제19199호(2022.12.31.) — 2023.12.21. 시행본"},
    2024: {"rate": 19, "start_deadline": date(2026, 12, 31), "period": 20, "tax_year_limit": None, "welfare_kept": True,
           "law": "법률 제19936호(2023.12.31.) — 2024.07.10. 시행본"},
    2025: {"rate": 19, "start_deadline": date(2026, 12, 31), "period": 20, "tax_year_limit": None, "welfare_kept": True,
           "law": "법률 제19936호(2023.12.31.) — 2025.11.11. 시행본"},
    2026: {"rate": 19, "start_deadline": date(2026, 12, 31), "period": 20, "tax_year_limit": None, "welfare_kept": True,
           "law": "법률 제19936호(2023.12.31.) — 2026.09.18. 시행본"},
}

PRE2014 = date(2014, 1, 1)


def _year_ok(year: int):
    if year not in FLAT_TEXT:
        raise ValueError(f"귀속연도 {year} — 2016~2026만 지원")


def add_years(d: date, n: int) -> date:
    """같은 월·일의 n년 뒤. 2월 29일이 없는 해면 3월 1일(그 전날이 2월 말일이 되도록)."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return date(d.year + n, 3, 1)


def _last_year_within(start: date, n: int) -> int:
    """'최초로 근로를 제공한 날부터 n년 이내에 끝나는 과세기간'의 마지막 귀속연도.
    과세기간 종료일(12.31.)이 기산일부터 n년 이내여야 함 — 기산일이 어느 날이든 마지막 연도는 start.year + n − 1."""
    return start.year + n - 1


def flat_eligibility(year: int, first_work_date: date, *, regional_hq: bool = False, related_party_employer: bool = False,
                     fie_excepted: bool = False, daily_worker: bool = False, korean_national: bool = False,
                     reentry_date: date | None = None) -> dict:
    """제18조의2 단일세율 적용 가능 여부(귀속연도 기준). 반환: {가능, 사유[], 주의[], 기산일, 마지막연도, 세율, 근거[]}."""
    _year_ok(year)
    t = FLAT_TEXT[year]
    reasons, notes, basis = [], [], [f"조세특례제한법 제18조의2제2항({t['law']})"]
    if first_work_date > date(year, 12, 31):
        raise ValueError(f"first_work_date {first_work_date} — 귀속연도 {year}년보다 뒤")
    if daily_worker:
        reasons.append("일용근로자는 외국인근로자에서 제외(제18조의2제2항 괄호)")
    if korean_national:
        reasons.append("과세연도 종료일 현재 대한민국 국적이면 신청 대상 아님(시행령 제16조의2제4항 괄호)")
    if related_party_employer and not fie_excepted:
        reasons.append("특수관계기업(시행령 제16조의2제2항: 국세기본법 시행령 제1조의2제1항·제3항 친족관계·경영지배관계)에 근로 제공 — "
                       "제18조의2제2항 괄호로 제외(같은 조 제1항의 외국인투자기업이면 fie_excepted=true)")
    rate = t["rate"]
    start = first_work_date
    last = None
    if first_work_date < PRE2014:
        basis.append("법률 제12173호 부칙 제59조(2014.1.1. 전 근무 시작자 종전 규정, 특수관계기업 근로는 제외)")
        if year == 2016:
            basis.append("법률 제12853호 부칙 제8조(제18조의2제2항 본문 개정규정을 부칙 제59조 적용자에게도 적용)")
            notes.append("2014.1.1. 전 근무 시작자의 2016 귀속: 종전 규정·법률 제12853호 부칙 제8조로 적용 — 5년 기간을 이들에게도 세는지는 확인 필요(이 도구는 세지 않음)")
            last = 2016
        elif year <= 2018:
            basis.append("법률 제14390호 부칙 제10조제1항(2014.1.1. 전 근무 시작자는 2018.12.31.까지만, 19%)")
            last = 2018
        elif year <= 2022:
            basis.append("법률 제14390호 부칙 제10조제1항(2018.12.31.까지만)")
            reasons.append("2014.1.1. 전 근무 시작자는 2018.12.31.까지만 적용(법률 제14390호 부칙 제10조제1항) — 2019~2022 귀속 적용 불가")
            last = 2018
        else:
            if reentry_date is not None and reentry_date < PRE2014:
                raise ValueError("reentry_date는 2014.1.1. 이후 재입국해 근로를 시작한 날")
            start = reentry_date or PRE2014
            basis.append("법률 제19199호 부칙 제10조, 기획재정부 소득세제과-135(2023.2.21.)·서면-2023-국제세원-0193(2023.2.27.) — "
                         "2014.1.1. 현재 근무 중이면 기산일 2014.1.1., 2014.1.1. 이후 재입국이면 재입국 후 최초 근로일")
            last = _last_year_within(start, t["period"])
            if year > last:
                reasons.append(f"기산일 {start}부터 {t['period']}년 이내에 끝나는 과세기간(~{last}년) 경과")
    else:
        if t["start_deadline"] and not regional_hq and first_work_date > t["start_deadline"]:
            reasons.append(f"최초 근로 시작일 {first_work_date}이 {t['start_deadline']} 이후 — {year} 시행본 본문 시작 기한 초과")
        if t["tax_year_limit"] and not regional_hq and year > t["tax_year_limit"]:
            reasons.append(f"{t['tax_year_limit']}년까지만 해당(본문 괄호)")
        if regional_hq:
            basis.append("제18조의2제2항 단서(시행령 제16조의2제3항 지역본부 — 시작 기한 없음, 기간은 본문과 같음)")
        if year >= 2017:
            basis.append("법률 제14390호 부칙 제10조제2항(적용기한 규정은 2014.1.1. 이후 근무 시작자부터)")
        last = _last_year_within(first_work_date, t["period"])
        if year >= 2023:
            basis.append("법률 제19199호 부칙 제10조(시행 당시 최초 근로일부터 20년이 지나지 아니한 외국인근로자에도 적용)")
            five = _last_year_within(first_work_date, 5)
            if five < 2023 and year <= last:
                notes.append(f"종전 5년 기간은 {five}년 귀속으로 끝났지만 2023.1.1. 현재 20년이 지나지 않아 법률 제19199호 부칙 제10조 문언대로 다시 적용 — "
                             f"2014.1.1. 전 근무 시작자에 대해 같은 취지의 기재부 해석(소득세제과-135)이 있음")
        if year > last:
            reasons.append(f"최초 근로일 {first_work_date}부터 {t['period']}년 이내에 끝나는 과세기간(~{last}년) 경과")
    if year <= 2016:
        basis.append("세율 17%(2016 시행본)")
    else:
        basis.append("세율 19%(법률 제14390호, 부칙 제10조제3항: 2017.1.1. 전 발생 소득은 17%)")
    return {"가능": not reasons, "사유": reasons, "주의": notes, "기산일": start.isoformat(), "마지막연도": last,
            "세율": rate, "근거": basis, "시행본": t["law"]}


def flat_tax(year: int, taxable_pay: int, nontaxable_pay: int = 0, housing_benefit_nontaxable: int = 0) -> dict:
    """제18조의2제2항·제3항: 근로소득(비과세 포함, 2024~ 사택 제공 이익 비과세분 제외) × 세율. 원 미만 절사."""
    _year_ok(year)
    if min(taxable_pay, nontaxable_pay, housing_benefit_nontaxable) < 0:
        raise ValueError("금액은 0 이상")
    if housing_benefit_nontaxable > nontaxable_pay:
        raise ValueError("housing_benefit_nontaxable(사택 제공 이익 비과세분)은 nontaxable_pay(비과세 합계)에 포함된 금액이어야 함")
    t = FLAT_TEXT[year]
    excluded = housing_benefit_nontaxable if t["welfare_kept"] else 0
    base = taxable_pay + nontaxable_pay - excluded
    tax = base * t["rate"] // 100
    local = base * t["rate"] // 1000     # 지특법 제106조의2: 제18조의2제2항 세율의 100분의 10
    return {"과세대상근로소득": base, "비과세포함액": nontaxable_pay - excluded, "사택이익제외액": excluded,
            "세율": t["rate"], "소득세": tax, "지방소득세": local, "합계": tax + local}


def progressive_tax(year: int, gross_pay: int, tax_base: int | None = None, other_credits: int | None = None) -> dict:
    """일반 누진세율 — wage_income_tax와 같은 엔진(소득세법 제47조①·제55조·제59조·제59조의4⑨)."""
    ded = I.earned_deduction(gross_pay, year)
    income_amt = max(0, gross_pay - ded)
    assumed = tax_base is None
    if assumed:
        tax_base = max(0, income_amt - 1_500_000)
    t = I.income_tax(tax_base, year)
    credit = I.earned_tax_credit(t, gross_pay, year=year)
    if other_credits is None:
        others = min(130_000, max(0, t - credit)) if assumed else 0
    else:
        others = min(other_credits, max(0, t - credit))
    decided = max(0, t - credit - others)
    return {"총급여": gross_pay, "근로소득공제": ded, "근로소득금액": income_amt, "과세표준": tax_base, "과세표준추정": assumed,
            "산출세액": t, "근로소득세액공제": credit, "그밖의세액공제": others, "결정세액": decided,
            "지방소득세": decided // 10, "합계": decided + decided // 10}


# ── 제18조 외국인기술자 감면 ──────────────────────────────────────────────────
SOBUJANG_FROM, SOBUJANG_TO = date(2020, 1, 1), date(2022, 12, 31)


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def expert_windows(first_work_date: date, sobujang: bool = False) -> dict:
    """최초 근로일 기준 감면 구간(월 단위). 반환 {구간:[(시작월idx, 끝월idx, 율, 근거)], 주의[], 근거[]}.
    'N년이 되는 날' = 기산일 + N년 − 1일(첫 근로일 산입)로 보고 그 날이 속하는 달까지."""
    D = first_work_date
    notes, basis, windows = [], [], []
    s = _month_index(D)

    def end(n):
        return _month_index(date.fromordinal(add_years(D, n).toordinal() - 1))

    if D.day == 1:
        notes.append("최초 근로일이 1일이면 'N년이 되는 날'을 첫날 산입(N년 뒤 전날)으로 보느냐 불산입(N년 뒤 같은 날)으로 보느냐에 따라 "
                     "마지막 감면 달이 한 달 달라짐 — 이 도구는 첫날 산입, 확인 필요")
    if D < date(2015, 1, 1):
        raise ValueError("최초 근로일이 2015.1.1. 전 — 법률 제12853호 부칙 제61조(종전 제18조제2항) 대상이라 이 도구는 계산하지 않음")
    if D > date(2026, 12, 31):
        raise ValueError("최초 근로일이 2026.12.31. 이후 — 2026 시행본 시작 기한 초과")
    if sobujang:
        if SOBUJANG_FROM <= D <= SOBUJANG_TO:
            windows = [(s, end(3), 70, "제18조제1항 단서(70%, 3년)"), (end(3) + 1, end(5), 50, "제18조제1항 단서(그 다음 달부터 2년, 50%)")]
            basis.append("법률 제16835호 제18조제1항 단서·부칙 제11조(2020.1.1. 이후 최초 근로 제공분부터), 시작 기한 2022.12.31.")
            notes.append("소재·부품·장비 단서에는 법률 제19199호(10년) 개정이 없음 — 단서 대상자가 본문 10년을 대신 고를 수 있는지는 확인 필요")
            return {"구간": windows, "주의": notes, "근거": basis}
        notes.append(f"소재·부품·장비 단서는 최초 근로일 2020.1.1.~2022.12.31.만(법률 제16835호 부칙 제11조·단서 시작 기한) — {D}는 본문으로 계산")
    if D <= date(2018, 12, 31):
        windows.append((s, end(2), 50, "제18조제1항(2년, 50%) — 법률 제16009호 부칙 제40조(2019.1.1. 전 근무 시작자 종전 감면기간)"))
        basis.append("법률 제12853호 문언(2018.12.31. 이전 최초 근로, 2년)·법률 제16009호 부칙 제40조")
        # 법률 제19199호 부칙 제9조: 2023.1.1. 현재 최초 근로일부터 5년이 지나지 아니한 외국인기술자에도 10년 본문 적용
        if date.fromordinal(add_years(D, 5).toordinal() - 1) >= date(2023, 1, 1):
            start23 = _month_index(date(2023, 1, 1))
            if end(10) >= start23:
                windows.append((max(start23, end(2) + 1), end(10), 50, "제18조제1항 본문(10년) — 법률 제19199호 부칙 제9조"))
            basis.append("법률 제19199호 부칙 제9조(시행 당시 최초 근로일부터 5년이 지나지 아니한 외국인기술자에도 적용)")
            notes.append("2018년 최초 근로자: 종전 2년이 끝난 뒤 2023.1.1. 현재 5년이 지나지 않아 부칙 제9조 문언대로 2023년부터 10년 기간까지 다시 감면 — "
                         "이 읽기를 다룬 해석례는 찾지 못함, 확인 필요")
        return {"구간": windows, "주의": notes, "근거": basis}
    # 2019.1.1. 이후 최초 근로: 2022년까지는 5년(법률 제16009호 부칙 제7조), 2023.1.1. 현재 5년이 지나지 않았으므로 10년(부칙 제9조)
    windows.append((s, end(10), 50, "제18조제1항 본문(2022년까지 5년 — 법률 제16009호 부칙 제7조, 2023년부터 10년 — 법률 제19199호 부칙 제9조)"))
    basis.append("법률 제16009호 부칙 제7조·법률 제19199호 제18조제1항·부칙 제9조"
                 + ("·법률 제19936호(시작 기한 2026.12.31.)" if D > date(2023, 12, 31) else ""))
    return {"구간": windows, "주의": notes, "근거": basis}


def expert_months(year: int, windows: list, first_work_date: date) -> dict:
    """귀속연도 안의 감면율별 달 수와 근무 달 수(최초 근로 연도는 최초 근로 달부터)."""
    y0, y1 = year * 12, year * 12 + 11
    work_from = max(y0, _month_index(first_work_date))
    worked = max(0, y1 - work_from + 1)
    by = {70: 0, 50: 0}
    for a, b, r, _ in windows:
        lo, hi = max(a, work_from), min(b, y1)
        if hi >= lo:
            by[r] += hi - lo + 1
    return {"근무달수": worked, "70%달수": by[70], "50%달수": by[50]}


def expert_reduction(year: int, gross_pay: int, wage70: int, wage50: int, calc_tax: int,
                     other_income_amount: int = 0) -> dict:
    """소득세법 제59조의5②·① 준용: 감면세액 = 산출세액 × 감면대상 근로소득금액 / 종합소득금액 × 감면율.
    감면대상 근로소득금액은 근로소득금액을 총급여 비율로 나눔. 최종 금액만 원 미만 절사."""
    if wage70 + wage50 > gross_pay:
        raise ValueError("감면대상 총급여 합계가 gross_pay보다 큼")
    ded = I.earned_deduction(gross_pay, year)
    L = max(0, gross_pay - ded)
    T = L + other_income_amount
    if gross_pay == 0 or T == 0:
        return {"근로소득금액": L, "종합소득금액": T, "감면세액": 0}
    frac = Fraction(calc_tax) * Fraction(L, gross_pay) * (Fraction(7, 10) * wage70 + Fraction(1, 2) * wage50) / T
    return {"근로소득금액": L, "종합소득금액": T, "감면세액": int(frac)}  # int(): 양수 원 미만 절사
