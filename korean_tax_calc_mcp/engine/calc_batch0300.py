"""계산 MCP 0.30.0 — 개인 외국납부세액공제 · 해외금융계좌 신고 판정 · 양도소득 부당행위계산.

출처: 2026-11-10 해외지주사 시나리오에서 계산기가 비어 있던 항목.
조문은 korean-tax-mcp 2026 시행본으로 확인함.

도구:
  individual_foreign_tax_credit  — 거주자 외국납부세액공제(소득세법 제57조, 영 제117조)
  overseas_account_reporting     — 해외금융계좌 신고의무·과태료 판정(국조법 제53조·제54조·제90조, 영 제92조③·제93조·제94조·제147조)
  capital_gains_unfair_transaction — 양도소득 부당행위계산(소득세법 제101조, 영 제167조③④⑤⑥)
"""
from __future__ import annotations

from fractions import Fraction
from datetime import date

from .exact import trunc_won as _trunc_won, exact as _exact


def _ok(result, basis, *, 주의=None, 판단=None):
    d = {"결과": result, "근거": basis}
    if 주의:
        d["주의"] = 주의
    if 판단:
        d["판단"] = 판단
    return d


def _오류(문제, 허용값=None):
    d = {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    if 허용값:
        d["허용값"] = 허용값
    return d


# ═══════════════════════════════════════════════════════════════════════════════
# 도구 1 — individual_foreign_tax_credit (소득세법 제57조, 시행령 제117조)
# ═══════════════════════════════════════════════════════════════════════════════

def individual_foreign_tax_credit(
    year: int,
    calculated_tax: int,
    total_income: int,
    countries: list,
    income_kind: str = "종합",
    carryforward: list | None = None,
) -> dict:
    """거주자 외국납부세액공제(소득세법 제57조①②, 시행령 제117조①②⑦).

    언제: 거주자가 국외원천소득에 대해 외국에 납부한 세액이 있을 때 종합소득 또는 퇴직소득
    산출세액에서 국가별 한도 이내로 공제하고, 한도 초과분은 이월할 수 있는지 계산한다.
    입력:
      year — 귀속연도(2016~2026).
      income_kind — '종합'(기본) 또는 '퇴직'.
      calculated_tax — 종합소득산출세액 또는 퇴직소득산출세액(원, A).
      total_income — 종합소득금액 또는 퇴직소득금액(원, C). 0이면 오류.
      countries — [{country, foreign_income, foreign_tax, treaty_rate?, gross_amount?, russia_override?}].
      carryforward — [{country, year, amount}] (종합소득만, 이월된 미공제 외국소득세액).
    결과: 외국납부세액공제액·공제한도_합계·이월액·이월기간경과분·국가별 내역·산식.
    """
    # 허용값 검증
    if income_kind not in ("종합", "퇴직"):
        return _오류([f"income_kind='{income_kind}' 은(는) 허용값이 아님",
                       "허용 income_kind: 종합, 퇴직"],
                      {"income_kind": ["종합", "퇴직"]})
    if total_income <= 0:
        return _오류(["total_income이 0 이하 — 공제한도 계산 불가(국외원천소득 ÷ 총소득)"],
                      {"total_income": "0 초과 (원)"})
    if not isinstance(countries, list) or not countries:
        return _오류(["countries 목록이 비어 있음"], {"countries": "[{country, foreign_income, foreign_tax, …}]"})
    for i, c in enumerate(countries):
        if c.get("foreign_income", 0) < 0:
            return _오류([f"countries[{i}].foreign_income 이 음수 — 국외원천소득은 0 이상"],
                          {"foreign_income": "0 이상 (원)"})
        if c.get("foreign_tax", 0) < 0:
            return _오류([f"countries[{i}].foreign_tax 가 음수 — 외국소득세액은 0 이상"],
                          {"foreign_tax": "0 이상 (원)"})

    A = calculated_tax          # 산출세액
    C = total_income            # 총소득
    이월기간경과분 = 0
    국가별결과 = []
    공제한도_합계 = 0
    총공제액 = 0
    총이월액 = 0
    산식목록 = []

    # 이월분 사전 정리: country → [(year, amount)] 오래된 순서
    이월지도 = {}
    if carryforward:
        for cf in carryforward:
            국가 = cf.get("country")
            이월지도.setdefault(국가, []).append((cf.get("year", 0), cf.get("amount", 0)))
    for 국가 in 이월지도:
        이월지도[국가] = sorted(이월지도[국가], key=lambda x: x[0])

    for c in countries:
        국가 = c["country"]
        foreign_income = c["foreign_income"]
        foreign_tax = c.get("foreign_tax", 0)
        treaty_rate = c.get("treaty_rate")        # 선택
        gross_amount = c.get("gross_amount")      # 선택
        russia_override = c.get("russia_override", False)

        # 국가별 한도 = A × foreign_income ÷ C (영 제117조⑦; trunc_won 절사)
        한도 = _trunc_won(_exact(A) * _exact(foreign_income) / _exact(C))
        공제한도_합계 += 한도

        # 인정 외국소득세액
        if treaty_rate is not None and gross_amount is not None:
            # min(foreign_tax, gross_amount × treaty_rate) — 영 제117조① 단서
            treaty_cap = _trunc_won(_exact(gross_amount) * _exact(treaty_rate))
            if russia_override:
                인정액 = foreign_tax          # 초과분 포함
            else:
                인정액 = min(foreign_tax, treaty_cap)
        else:
            인정액 = foreign_tax

        # 해당 국가 이월분 (오래된 연도부터)
        국가이월잔고 = list(이월지도.get(국가, []))  # [(year, amount), ...] 오래된 순

        # 당기 인정액 중 한도에 들어가는 부분(당기공제)
        당기공제 = min(인정액, 한도)
        당해연도_초과분 = max(0, 인정액 - 당기공제)   # = max(0, 인정액 − 한도)
        남은한도 = 한도 - 당기공제

        # 이월분 적용: 남은 한도 내에서 오래된 연도부터
        이월공제 = 0
        미사용_이월잔액 = 0
        새이월지도항목 = []
        for cf_year, cf_amount in 국가이월잔고:
            # 이월공제기간 연도표(소득세법 제57조②): 2020년 과세기간까지 5년, 2021년부터 10년(2020.12.29. 개정).
            # 부칙 제11조는 2021.1.1. 직전까지 남아 있는 금액에 10년을 적용 — 2015년 이전 발생분은 2020년에 5년이 끝나 2021년부터 기간 경과.
            # 기간 경과는 한도와 무관하게 먼저 판정한다.
            if year <= 2020:
                경과 = year - cf_year > 5
                경과_설명 = f"{year}−{cf_year}={year-cf_year}년 > 5(2020년 과세기간까지 5년) → 이월기간 경과"
            elif cf_year <= 2015:
                경과 = True
                경과_설명 = f"{cf_year}년 발생분은 2020년에 5년이 끝남(2020.12.29. 개정 부칙 제11조: 남아 있는 금액만 10년) → 이월기간 경과, 필요경비 산입 가능"
            else:
                경과 = year - cf_year > 10
                경과_설명 = f"{year}−{cf_year}={year-cf_year}년 > 10 → 이월기간 경과, 필요경비 산입 가능"
            if 경과:
                이월기간경과분 += cf_amount
                산식목록.append(f"{국가} 이월분({cf_year}년 발생 {cf_amount:,}원): {경과_설명}(소득세법 제57조②)")
                continue
            if 남은한도 <= 0:
                새이월지도항목.append((cf_year, cf_amount))
                미사용_이월잔액 += cf_amount
                continue
            적용 = min(cf_amount, 남은한도)
            이월공제 += 적용
            남은한도 -= 적용
            남은이월 = cf_amount - 적용
            if 남은이월 > 0:
                새이월지도항목.append((cf_year, 남은이월))
                미사용_이월잔액 += 남은이월
            산식목록.append(f"{국가} 이월분({cf_year}년 발생 {cf_amount:,}원): 당기분 먼저 쓰고 남은 한도 {남은한도+적용:,}원 중 {적용:,}원 공제")
        이월지도[국가] = 새이월지도항목

        공제액 = 당기공제 + 이월공제
        총공제액 += 공제액

        # 국가별 이월액 = 당해연도 인정액 중 한도 초과분 + 사용하지 못한 이전 이월잔액
        국가별_이월액 = 당해연도_초과분 + 미사용_이월잔액
        총이월액 += 국가별_이월액

        국가별결과.append({
            "국가": 국가,
            "국외원천소득": foreign_income,
            "외국소득세액": foreign_tax,
            "인정_외국소득세액": 인정액,
            "공제한도": 한도,
            "당기공제": 당기공제,
            "이월공제": 이월공제,
            "공제액": 공제액,
            "이월액": 국가별_이월액,
        })

    # 이월액(종합소득만): 국가별 이월액 합계 = 당해연도 인정액 중 한도 초과분 + 미사용 이전 이월잔액
    if income_kind == "종합":
        이월액 = 총이월액
        이월기간 = f"{year+1}~{year+10}"
        산식목록.append(f"종합소득: 당기 인정액 중 공제한도 초과분 및 미사용 이월분 합계 {이월액:,}원 → {이월기간}년 이월(소득세법 제57조②)")
    else:
        이월액 = 0
        이월기간 = ""
        산식목록.append("퇴직소득: 이월 없음(소득세법 제57조②, 퇴직소득은 이월공제 대상 아님)")

    주의목록 = [
        "외국납부세액공제신청서를 확정신고 때 제출(시행령 제117조③)",
        "국외원천소득은 대응비용(직접비용·배분비용)을 뺀 금액(시행령 제117조②)",
    ]
    if income_kind == "퇴직":
        주의목록.append("퇴직소득은 외국납부세액공제 한도 계산은 되나 이월공제 대상이 아님(소득세법 제57조②)")

    판단목록 = []
    무시된_이월국가 = [k for k in 이월지도 if k not in {c["country"] for c in countries}]
    if 무시된_이월국가:
        주의목록.append(f"carryforward의 국가 {무시된_이월국가}는 countries에 없어 이번 과세기간에 공제하지 않음(해당 국가 국외원천소득이 없으면 한도 0)")
    if year <= 2020 and income_kind == "종합":
        주의목록.append("이 과세기간의 조문은 이월공제기간 5년. 2020.12.29. 개정 부칙 제11조로 2021년 이후 과세기간을 계산할 때부터 남아 있는 금액에 10년 적용")
    if 이월기간경과분 > 0:
        판단목록.append(f"이월기간 경과분 {이월기간경과분:,}원(연도 경과" + (", 필요경비 산입 가능)" if year >= 2021 else ")"))

    결과 = {
        "외국납부세액공제액": 총공제액,
        "공제한도_합계": 공제한도_합계,
        "이월액": 이월액,
        "이월기간경과분": 이월기간경과분,
        "국가별": 국가별결과,
        "산식": 산식목록,
    }
    if 이월기간:
        결과["이월기간"] = 이월기간

    return _ok(결과,
               "소득세법 제57조①②, 시행령 제117조①②⑦",
               주의=주의목록,
               판단=판단목록)


# ═══════════════════════════════════════════════════════════════════════════════
# 도구 2 — overseas_account_reporting (국조법 제53조·제54조·제90조, 영 제92조③·제93조·제94조·제147조)
# ═══════════════════════════════════════════════════════════════════════════════

def 해외금융계좌월별합산(month_end_totals_krw: list | None, accounts: list | None):
    """ month_end_totals_krw 또는 accounts의 12개월 합산값을 계산. 둘 다 있으면 오류, 둘 다 없으면 오류. """
    if month_end_totals_krw is not None and accounts is not None:
        raise ValueError("month_end_totals_krw와 accounts를 모두 줄 수 없음")
    if month_end_totals_krw is None and accounts is None:
        raise ValueError("month_end_totals_krw 또는 accounts 중 하나는 필요")
    if month_end_totals_krw is not None:
        if not isinstance(month_end_totals_krw, list) or len(month_end_totals_krw) != 12:
            raise ValueError("month_end_totals_krw는 길이 12 목록이어야 함")
        return list(month_end_totals_krw)
    # accounts 합산
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("accounts 목록이 비어 있음")
    합산 = [0] * 12
    for acc in accounts:
        m = acc.get("month_end_krw", [])
        if not isinstance(m, list) or len(m) != 12:
            raise ValueError(f"accounts의 month_end_krw는 길이 12 목록이어야 함 (계정 '{acc.get('name','?')}')")
        for i in range(12):
            합산[i] += m[i]
    return 합산


def overseas_account_reporting(
    year: int,
    month_end_totals_krw: list | None = None,
    accounts: list | None = None,
    holder: str = "거주자",
    foreigner_resident_years_in_korea_last10: int | None = None,
    overseas_korean_days_in_korea: int | None = None,
    treaty_resident_of_other_country: bool = False,
    reported_amount_krw: int = 0,
    corrected_on: str | None = None,
    unexplained_amount_krw: int | None = None,
    assessed_on: str | None = None,
) -> dict:
    """해외금융계좌 신고의무·과태료 판정(국조법 제53조①②·제54조·제90조①②, 시행령 제92조③·제93조①·제94조·제147조①②④).

    언제: 거주자·내국법인이 보유한 해외금융계좌의 매월 말일 잔액 합계가 5억 원을 초과하는지,
    신고의무 유무, 신고기한, 미신고·과소신고 시 과태료, 수정신고 감경, 소명 불이행 과태료를 계산한다.
    입력:
      year — 신고대상 연도(2016~2026).
      month_end_totals_krw — 1~12월 말일 합산 잔액(원) 목록(길이 12). 또는 accounts.
      accounts — [{name, month_end_krw: 길이 12}] (둘 다 주면 오류, 둘 다 없어도 오류).
      holder — '거주자'(기본) | '내국법인'.
      foreigner_resident_years_in_korea_last10 — 외국인 거주자로서 최근 10년 중 국내 주소·거소 기간(년). 5 이하면 면제.
      overseas_korean_days_in_korea — 재외국민의 신고대상 연도 종료일 1년 전부터 국내 거소 일수. 182 이하면 면제.
      treaty_resident_of_other_country — 조세조약상 상대국 거주자면 면제.
      reported_amount_krw — 기한 내 신고한 금액(기본 0 = 미신고).
      corrected_on — 수정신고일(YYYY-MM-DD).
      unexplained_amount_krw — 소명 불이행 과태료 계산용(선택).
    결과: 신고의무·최고잔액·최고잔액_월·신고기한·위반금액·과태료·과태료_범위·감경비율·감경후_과태료·소명불이행_과태료·면제사유.
    """
    if holder not in ("거주자", "내국법인"):
        return _오류([f"holder='{holder}' 은(는) 허용값이 아님", "허용 holder: 거주자, 내국법인"],
                      {"holder": ["거주자", "내국법인"]})

    try:
        월별 = 해외금융계좌월별합산(month_end_totals_krw, accounts)
    except ValueError as e:
        return _오류([str(e)],
                      {"month_end_totals_krw": "길이 12 목록(원)", "accounts": "[{name, month_end_krw: 길이 12}] 중 하나"})

    최고잔액 = max(월별)
    최고잔액_월 = 월별.index(최고잔액) + 1    # 1-based

    # 신고 기준금액 연도표: 2017년 보유분까지 10억원(구 영 제49조①, 2018.2.13. 개정 전), 2018년 보유분부터 5억원(현행 영 제92조③). "초과".
    기준금액 = 1_000_000_000 if year <= 2017 else 500_000_000
    신고의무 = holder in ("거주자", "내국법인") and 최고잔액 > 기준금액
    연도_주의 = []
    연도_판단 = [f"신고 기준금액 {기준금액 // 100_000_000}억원 초과" + ("(2017년 보유분까지 10억원 — 구 시행령 제49조①)" if year <= 2017 else "(2018년 보유분부터 5억원)")]

    면제사유 = []
    if not 신고의무 and holder in ("거주자", "내국법인"):
        # 5억 이하라 의무 없음 — 별도 면제사유 아님, 그냥 False
        pass

    # 면제 사유 확인 (제54조)
    면제체크 = False
    if foreigner_resident_years_in_korea_last10 is not None and foreigner_resident_years_in_korea_last10 <= 5:
        면제사유.append("외국인 거주자: 최근 10년 중 국내 주소·거소 기간 5년 이하 → 신고의무 면제(국조법 제54조1호가, 소득세법 제3조① 단서)")
        면제체크 = True
    # 재외국민 면제 연도표: 2018년 보유분까지 "종료일 2년 전부터 183일 이하"(구 법 제34조⑤1호), 2019~2024년 "1년 전부터 183일 이하",
    # 2025년 보유분부터 "182일 이하"(법 제54조1호나목, 2024.12.31. 개정 부칙 제5조).
    if overseas_korean_days_in_korea is not None:
        면제일수 = 182 if year >= 2025 else 183
        창 = "2년 전" if year <= 2018 else "1년 전"
        if year <= 2018:
            연도_주의.append("2018년 보유분까지 재외국민 면제는 신고대상 연도 종료일 2년 전부터의 국내 거소 일수 합계(183일 이하)로 판정 — overseas_korean_days_in_korea에 2년치 일수를 넣는다")
        if overseas_korean_days_in_korea <= 면제일수:
            면제사유.append(f"재외국민: 신고대상 연도 종료일 {창}부터 국내 거소 일수 {면제일수}일 이하 → 신고의무 면제"
                        + ("(국조법 제54조1호나목)" if year >= 2025 else "(국조법 제54조1호)" if year >= 2021 else "(구 국조법 제34조⑤1호)"))
            면제체크 = True
    # 조세조약 상대국 거주자 면제는 2025.1.1. 이후 개시 과세기간 보유분부터(법 제54조7호, 2024.12.31. 개정 부칙 제5조)
    if treaty_resident_of_other_country:
        if year >= 2025:
            면제사유.append("조세조약상 상대국 거주자 → 신고의무 면제(국조법 제54조7호)")
            면제체크 = True
        else:
            연도_판단.append("조세조약 상대국 거주자 면제는 2025년 보유분부터(국조법 제54조7호, 부칙 제5조) — 이 연도는 면제 사유 아님")

    if 면제체크:
        신고의무 = False

    신고기한 = f"{year+1}-06-30"

    # 과태료 부과기준은 부과일로 나눈다: 2025.2.28. 이후 부과분은 개정 기준(보유연도와 무관). assessed_on이 없으면 지금 부과하는 것으로 본다.
    구기준 = False
    if assessed_on is not None:
        try:
            부과일 = date.fromisoformat(assessed_on)
        except (TypeError, ValueError):
            return _오류([f"assessed_on='{assessed_on}' — YYYY-MM-DD"], {"assessed_on": "YYYY-MM-DD"})
        if 부과일 < date(2021, 1, 1):
            return _오류([f"assessed_on={assessed_on} — 2021.1.1. 전 부과분의 과태료 기준은 지원하지 않음(당시 시행령 대조 전)"],
                         {"assessed_on": "2021-01-01 이후 또는 생략(현행 기준)"})
        구기준 = 부과일 < date(2025, 2, 28)

    # 과태료 (의무 있는데 미신고·과소신고)
    과태료 = 0
    위반금액 = 0
    감경비율 = 0
    감경후_과태료 = 0
    과태료_범위 = [0, 0]

    if 신고의무:
        위반금액 = max(0, 최고잔액 - reported_amount_krw)   # 신고액이 최고잔액 이상이면 위반 없음
        if 구기준:
            # 2025.2.28. 전 부과분 — 누진표(영 제147조① 2024.12.31. 시행본): 20억 이하 10%, 20억 초과 50억 이하 2억 + 초과분 15%,
            # 50억 초과 6억5천만 + 초과분 20%(20억원 한도)
            if 위반금액 <= 2_000_000_000:
                과태료 = _trunc_won(_exact(위반금액) * Fraction(1, 10))
            elif 위반금액 <= 5_000_000_000:
                과태료 = 200_000_000 + _trunc_won(_exact(위반금액 - 2_000_000_000) * Fraction(15, 100))
            else:
                과태료 = min(650_000_000 + _trunc_won(_exact(위반금액 - 5_000_000_000) * Fraction(1, 5)), 2_000_000_000)
        else:
            # 2025.2.28. 이후 부과분 — min(위반금액 × 10%, 10억)(영 제147조①1호), 법 상한 20%(제90조①)
            과태료 = min(_trunc_won(_exact(위반금액) * Fraction(1, 10)), 1_000_000_000)
        # 조정 범위 ±50% (영 제147조②)
        과태료_범위 = [_trunc_won(_exact(과태료) * Fraction(1, 2)), _trunc_won(_exact(과태료) * Fraction(3, 2))]

        # 수정신고 감경(영 제147조④1호, 구 영 제51조): 6개월 이내 / 1년 이내 / 2년 이내 / 4년 이내.
        # 수정신고일 2020.2.11. 전은 70·50·20·10, 이후는 90·70·50·30(2020.2.11. 개정). 기간은 달력으로 센다(기한 6.30. → 12.30., 다음 해 6.30. …).
        if corrected_on:
            corr_date = date.fromisoformat(corrected_on)
            y1 = year + 1
            경계 = [date(y1, 12, 30), date(y1 + 1, 6, 30), date(y1 + 2, 6, 30), date(y1 + 4, 6, 30)]
            표 = (70, 50, 20, 10) if corr_date < date(2020, 2, 11) else (90, 70, 50, 30)
            감경비율 = 0
            if corr_date <= date(y1, 6, 30):
                연도_주의.append("corrected_on이 신고기한 이전 — 수정신고 감경 대상 아님(기한 내 정정)")
            else:
                for 끝, 율 in zip(경계, 표):
                    if corr_date <= 끝:
                        감경비율 = 율
                        break
            if corr_date < date(2020, 2, 11):
                연도_주의.append("수정신고일이 2020.2.11. 전 — 종전 감경표(70·50·20·10%, 구 시행령 제51조⑤) 적용")
            감경후_과태료 = _trunc_won(_exact(과태료) * Fraction(100 - 감경비율, 100))
        else:
            감경비율 = 0
            감경후_과태료 = 과태료

    # 소명 불이행 과태료: 법 제90조② 20%. 부과기준(영 제147조①2호)은 2025.2.28. 개정으로 20% → 10%.
    # 적용 시기: 시행일(2025.2.28.) 이후 "부과하는 분부터"(기획재정부 국제조세제도과-80, 2026.2.11.; 기준-2025-법규국조-0110) — 보유연도가 아니라 부과일 기준.
    소명불이행_과태료 = 0
    소명율 = Fraction(1, 5) if 구기준 else Fraction(1, 10)
    if unexplained_amount_krw is not None and unexplained_amount_krw > 0:
        소명불이행_과태료 = _trunc_won(_exact(unexplained_amount_krw) * 소명율)

    # 판단: 실질적 소유자 안내
    판단목록 = [
        "명의와 무관하게 사실상 관리하는 자가 보유자(시행령 제94조①)",
        "내국인이 의결권 100% 직·간접 보유한 외국법인 계좌는 비조약국이면 내국인이 실질적 소유자(시행령 제94조②)",
        "공동명의자는 각자 전체 잔액 보유로 봄(제53조②2호)",
    ]

    주의목록 = [
        f"신고기한 {신고기한}은 공휴일 조정 없음(국조법 제53조①)",
        "기한 후 신고 감경은 영 제147조④2호 표 확인(미신고자 대상)",
    ]
    주의목록.append(
        ("과태료는 2025.2.28. 전 부과 기준(누진표 10%·15%·20%, 20억원 한도, 소명 불이행 20%)으로 계산 — assessed_on이 2025.2.28. 전"
         if 구기준 else
         "과태료는 2025.2.28. 개정 기준(미신고·과소신고 10%·10억원 한도, 소명 불이행 10%)으로 계산 — 보유연도와 무관하게 2025.2.28. 이후 부과하는 분부터 적용"
         "(기획재정부 국제조세제도과-80, 2026.2.11.; 기준-2025-법규국조-0110). 그 전에 부과된 건은 assessed_on에 부과일을 넣는다"))

    결과 = {
        "신고의무": 신고의무,
        "최고잔액": 최고잔액,
        "최고잔액_월": 최고잔액_월,
        "신고기한": 신고기한,
        "기준금액": 기준금액,
        "위반금액": 위반금액,
        "과태료": 과태료,
        "과태료_범위": 과태료_범위,
        "감경비율": 감경비율,
        "감경후_과태료": 감경후_과태료,
        "소명불이행_과태료": 소명불이행_과태료,
        "면제사유": 면제사유,
    }

    return _ok(결과,
               "국제조세조정에 관한 법률 제53조①②·제54조·제90조①②, 시행령 제92조③·제93조①·제94조·제147조①②④",
               판단=연도_판단 + 판단목록,
               주의=주의목록 + 연도_주의)


# ═══════════════════════════════════════════════════════════════════════════════
# 도구 3 — capital_gains_unfair_transaction (소득세법 제101조, 시행령 제167조③④⑤⑥)
# ═══════════════════════════════════════════════════════════════════════════════

def capital_gains_unfair_transaction(
    mode: str = "저가고가",
    *,
    transaction: str = "양도",
    market_value: int,
    price: int,
    related_party: bool,
    counterparty_is_corporation: bool = False,
    corporate_tax_market_value_applies: bool = False,
    fraud: bool = False,
    gift_date: str | None = None,
    transfer_date: str | None = None,
    donee_relation: str | None = None,
    donee_gift_tax: int = 0,
    donee_capital_gains_tax: int = 0,
    donor_direct_capital_gains_tax: int = 0,
    income_belongs_to_donee: bool = False,
) -> dict:
    """양도소득 부당행위계산(소득세법 제101조①②③, 시행령 제98조①·제167조③④⑤⑥).

    언제: 특수관계인 간 자산 양도·취득이 시가와 현저히 차이가 나 부당행위계산 부인 대상인지,
    또는 증여 후 수증자가 양도할 때 증여자가 직접 양도한 것으로 볼지 계산한다.
    입력:
      mode — '저가고가'(기본) | '증여후양도'.
      [저가고가] transaction — '양도' | '취득'. market_value — 시가(원). price — 거래가액.
        related_party — 특수관계인 여부. counterparty_is_corporation, corporate_tax_market_value_applies,
        fraud — 법인 상대 거래 예외·영 제167조⑥ 관련.
      [증여후양도] gift_date, transfer_date — YYYY-MM-DD. donee_relation — '배우자' | '직계존비속' | '기타특수관계인'.
        donee_gift_tax, donee_capital_gains_tax, donor_direct_capital_gains_tax — 각 세액(원).
        income_belongs_to_donee — 수증자 귀속분이면 적용 제외.
    결과: [저가고가] 부당행위계산·차액·차액비율(정수 만분율)·기준_3억_충족·기준_5퍼센트_충족·조정후_양도가액|조정후_취득가액.
      [증여후양도] 증여자_직접양도_간주·수증자_세액합계·증여자_직접양도세액·적용제외_사유.
    """
    if mode == "저가고가":
        return _capital_gains_unfair_low_high(
            transaction=transaction,
            market_value=market_value,
            price=price,
            related_party=related_party,
            counterparty_is_corporation=counterparty_is_corporation,
            corporate_tax_market_value_applies=corporate_tax_market_value_applies,
            fraud=fraud,
        )
    elif mode == "증여후양도":
        return _capital_gains_unfair_gift_then_transfer(
            gift_date=gift_date,
            transfer_date=transfer_date,
            donee_relation=donee_relation,
            donee_gift_tax=donee_gift_tax,
            donee_capital_gains_tax=donee_capital_gains_tax,
            donor_direct_capital_gains_tax=donor_direct_capital_gains_tax,
            income_belongs_to_donee=income_belongs_to_donee,
        )
    else:
        return _오류([f"mode='{mode}' 은(는) 허용값이 아님", "허용 mode: 저가고가, 증여후양도"],
                      {"mode": ["저가고가", "증여후양도"]})


def _capital_gains_unfair_low_high(
    transaction: str,
    market_value: int,
    price: int,
    related_party: bool,
    counterparty_is_corporation: bool,
    corporate_tax_market_value_applies: bool,
    fraud: bool,
) -> dict:
    """저가고가 모드 — 특수관계 거래 시 시가와 차이가 현저하면 부당행위계산."""
    if transaction not in ("양도", "취득"):
        return _오류([f"transaction='{transaction}' 은(는) 허용값이 아님", "허용 transaction: 양도, 취득"],
                      {"transaction": ["양도", "취득"]})
    if market_value <= 0:
        return _오류(["market_value(시가)가 0 이하 — 시가 필요"], {"market_value": "0 초과 (원)"})
    if price < 0:
        return _오류(["price(거래가액)가 음수"], {"price": "0 이상 (원)"})

    # related_party False → 부당행위 아님
    if not related_party:
        return _ok({
            "부당행위계산": False,
            "차액": abs(market_value - price),
            "차액비율": 0,
            "기준_3억_충족": False,
            "기준_5퍼센트_충족": False,
            "조정후_양도가액" if transaction == "양도" else "조정후_취득가액": price,
        }, "소득세법 제101조①, 시행령 제167조③",
           판단=["특수관계인 아님 — 제101조 적용 없음"])

    차액 = abs(market_value - price)
    # 차액비율 = 차액 / market_value × 10000 (정수 만분율, 분모 10000)
    차액비율 = _trunc_won(Fraction(차액, 1) * Fraction(10000, 1) / Fraction(market_value, 1))

    기준_3억_충족 = 차액 >= 300_000_000
    기준_5퍼센트_충족 = 차액 >= _trunc_won(Fraction(market_value, 1) * Fraction(5, 100))

    # 부당행위 조건: (양도이고 가격 < 시가) 또는 (취득이고 가격 > 시가) 그리고 (3억 이상 또는 5% 이상)
    부당행위조건 = (
        (transaction == "양도" and price < market_value) or
        (transaction == "취득" and price > market_value)
    ) and (기준_3억_충족 or 기준_5퍼센트_충족)

    # 법인 상대 거래 예외 (영 제167조⑥): counterparty_is_corporation and corporate_tax_market_value_applies and not fraud
    if counterparty_is_corporation and corporate_tax_market_value_applies and not fraud:
        부당행위조건 = False

    부당행위계산 = 부당행위조건

    if 부당행위계산:
        조정값 = market_value
        if transaction == "양도":
            결과키 = "조정후_양도가액"
        else:
            결과키 = "조정후_취득가액"
    else:
        조정값 = price
        결과키 = "조정후_양도가액" if transaction == "양도" else "조정후_취득가액"

    근거 = "소득세법 제101조①, 시행령 제167조③④"
    if counterparty_is_corporation and corporate_tax_market_value_applies:
        근거 += "·⑥"
    판단목록 = []
    if fraud and counterparty_is_corporation and corporate_tax_market_value_applies:
        판단목록.append("fraud=True → 영 제167조⑥ 예외 미적용")
    if not 부당행위계산 and related_party:
        판단목록.append("특수관계인이나 시가와의 차액이 현저하지 않아 부당행위계산 아님(시행령 제167조③ 단서)")

    return _ok({
        "부당행위계산": 부당행위계산,
        "차액": 차액,
        "차액비율": 차액비율,   # 정수 만분율(분자/10000)
        "기준_3억_충족": 기준_3억_충족,
        "기준_5퍼센트_충족": 기준_5퍼센트_충족,
        결과키: 조정값,
    }, 근거, 판단=판단목록)


def _capital_gains_unfair_gift_then_transfer(
    gift_date: str | None,
    transfer_date: str | None,
    donee_relation: str | None,
    donee_gift_tax: int,
    donee_capital_gains_tax: int,
    donor_direct_capital_gains_tax: int,
    income_belongs_to_donee: bool,
) -> dict:
    """증여후양도 모드 — 증여 후 수증자가 양도할 때 증여자 직접 양도 간주 여부."""
    if gift_date is None or transfer_date is None:
        return _오류(["증여후양도 mode: gift_date와 transfer_date 필요"],
                      {"gift_date": "YYYY-MM-DD", "transfer_date": "YYYY-MM-DD"})
    if donee_relation not in ("배우자", "직계존비속", "기타특수관계인"):
        return _오류([f"donee_relation='{donee_relation}' 은(는) 허용값이 아님",
                       "허용 donee_relation: 배우자, 직계존비속, 기타특수관계인"],
                      {"donee_relation": ["배우자", "직계존비속", "기타특수관계인"]})
    if transfer_date < gift_date:
        return _오류(["transfer_date가 gift_date보다 앞섬 — 증여 후 양수가 아님"],
                      {"transfer_date": "gift_date 이후 (YYYY-MM-DD)"})

    gift_dt = date.fromisoformat(gift_date)
    transfer_dt = date.fromisoformat(transfer_date)

    적용제외_사유 = ""

    # 배우자·직계존비속 → 제97조의2 이월과세 대상 → 제101조② 적용 없음
    if donee_relation in ("배우자", "직계존비속"):
        적용제외_사유 = "제97조의2 이월과세 검토 — 배우자·직계존비속은 제101조② 적용 대상 아님(소득세법 제97조의2)"
        return _ok({
            "증여자_직접양도_간주": False,
            "수증자_세액합계": donee_gift_tax + donee_capital_gains_tax,
            "증여자_직접양도세액": donor_direct_capital_gains_tax,
            "적용제외_사유": 적용제외_사유,
        }, "소득세법 제101조②, 제97조의2", 판단=[적용제외_사유])

    # 적용기간 연도표(소득세법 제101조②): 2023.1.1. 전 증여받은 자산은 5년(2022.12.31. 개정 부칙 제18조: 종전 규정), 이후 증여분은 10년.
    # 달력 연수로 계산(제97조의2③ 준용: 등기·등록 기준).
    적용기간_년 = 5 if gift_dt < date(2023, 1, 1) else 10
    try:
        십년_기한 = gift_dt.replace(year=gift_dt.year + 적용기간_년)
    except ValueError:  # 2월 29일
        십년_기한 = gift_dt.replace(year=gift_dt.year + 적용기간_년, day=28)
    if transfer_dt > 십년_기한:
        적용제외_사유 = (f"증여일부터 양도일까지 {적용기간_년}년 초과(증여 {gift_date}, {적용기간_년}년 기한 {십년_기한.isoformat()}, 양도 {transfer_date}) → 제101조② 적용 없음"
                     + ("(2023.1.1. 전 증여분은 5년 — 2022.12.31. 개정 부칙 제18조)" if 적용기간_년 == 5 else "(소득세법 제97조의2③ 준용)"))
        return _ok({
            "증여자_직접양도_간주": False,
            "수증자_세액합계": donee_gift_tax + donee_capital_gains_tax,
            "증여자_직접양도세액": donor_direct_capital_gains_tax,
            "적용제외_사유": 적용제외_사유,
            "적용기간_년": 적용기간_년,
        }, "소득세법 제101조②, 제97조의2③", 판단=[적용제외_사유])

    # income_belongs_to_donee True → 적용 없음(단서)
    if income_belongs_to_donee:
        적용제외_사유 = "소득 귀속분이 수증자에게 실질적으로 귀속 → 제101조② 단서 적용 제외"
        return _ok({
            "증여자_직접양도_간주": False,
            "수증자_세액합계": donee_gift_tax + donee_capital_gains_tax,
            "증여자_직접양도세액": donor_direct_capital_gains_tax,
            "적용제외_사유": 적용제외_사유,
            "적용기간_년": 적용기간_년,
        }, "소득세법 제101조② 단서", 판단=[적용제외_사유])

    # 합계 = donee_gift_tax + donee_capital_gains_tax; 합계 < donor_direct_capital_gains_tax → 증여자 직접 양도 간주
    합계 = donee_gift_tax + donee_capital_gains_tax
    증여자직접양도_간주 = 합계 < donor_direct_capital_gains_tax

    판단목록 = []
    if 증여자직접양도_간주:
        판단목록.append("증여자가 직접 양도한 것으로 봄 — 증여세는 부과하지 않음(소득세법 제101조③)")

    return _ok({
        "증여자_직접양도_간주": 증여자직접양도_간주,
        "수증자_세액합계": 합계,
        "증여자_직접양도세액": donor_direct_capital_gains_tax,
        "적용제외_사유": 적용제외_사유,
        "적용기간_년": 적용기간_년,
    }, "소득세법 제101조①②③",
       판단=판단목록)
