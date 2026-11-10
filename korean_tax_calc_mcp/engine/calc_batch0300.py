"""계산 MCP 0.30.0 — 개인 외국납부세액공제 · 해외금융계좌 신고 판정 · 양도소득 부당행위계산.

출처: 2026-11-10 뷰티·해외지주사 시나리오에서 계산기가 비어 있던 항목.
조문은 korean-tax-mcp 2026 시행본으로 확인함.

도구:
  individual_foreign_tax_credit  — 거주자 외국납부세액공제(소득세법 제57조, 영 제117조)
  overseas_account_reporting     — 해외금융계좌 신고의무·과태료 판정(국조법 제53조·제54조·제90조, 영 제92조③·제93조·제94조·제147조)
  capital_gains_unfair_transaction — 양도소득 부당행위계산(소득세법 제101조, 영 제167조③④⑤⑥)
"""
from __future__ import annotations

from fractions import Fraction
from datetime import date, timedelta

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
            if 남은한도 <= 0:
                새이월지도항목.append((cf_year, cf_amount))
                continue
            # 이월 가능 기간 확인: year − cf_year > 10 → 기간 경과
            if year - cf_year > 10:
                이월기간경과분 += cf_amount
                산식목록.append(f"{국가} 이월분({cf_year}년 발생 {cf_amount:,}원): year−{cf_year}={year-cf_year}년 > 10 → 이월기간 경과, 필요경비 산입 가능(소득세법 제57조②)")
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
    if 이월기간경과분 > 0:
        판단목록.append(f"이월기간 경과분 {이월기간경과분:,}원(연도 경과, 필요경비 산입 가능)")

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

    # 신고의무: holder가 거주자·내국법인이고 최고잔액 > 5억 (영 제92조③)
    # 5억 정확히면 의무 없음
    신고의무 = holder in ("거주자", "내국법인") and 최고잔액 > 500_000_000

    면제사유 = []
    if not 신고의무 and holder in ("거주자", "내국법인"):
        # 5억 이하라 의무 없음 — 별도 면제사유 아님, 그냥 False
        pass

    # 면제 사유 확인 (제54조)
    면제체크 = False
    if foreigner_resident_years_in_korea_last10 is not None and foreigner_resident_years_in_korea_last10 <= 5:
        면제사유.append("외국인 거주자: 최근 10년 중 국내 주소·거소 기간 5년 이하 → 신고의무 면제(국조법 제54조1호가, 소득세법 제3조① 단서)")
        면제체크 = True
    if overseas_korean_days_in_korea is not None and overseas_korean_days_in_korea <= 182:
        면제사유.append("재외국민: 신고대상 연도 종료일 1년 전부터 국내 거소 일수 182일 이하 → 신고의무 면제(국조법 제54조1호나)")
        면제체크 = True
    if treaty_resident_of_other_country:
        면제사유.append("조세조약상 상대국 거주자 → 신고의무 면제(국조법 제54조7호)")
        면제체크 = True

    if 면제체크:
        신고의무 = False

    신고기한 = f"{year+1}-06-30"

    # 과태료 (의무 있는데 미신고·과소신고)
    과태료 = 0
    위반금액 = 0
    감경비율 = 0
    감경후_과태료 = 0
    과태료_범위 = [0, 0]

    if 신고의무:
        위반금액 = 최고잔액 - reported_amount_krw
        # 과태료 = min(위반금액 × 10%, 10억) (영 제147조①1호), 법 상한 20% (제90조①)
        과태료 = _trunc_won(_exact(위반금액) * _exact(0.10))
        과태료 = min(과태료, 1_000_000_000)
        # 조정 범위 ±50% (영 제147조②)
        과태료_범위 = [_trunc_won(과태료 * 50 / 100), _trunc_won(과태료 * 150 / 100)]

        # 수정신고 감경 (영 제147조④1호): 기한 후 6개월 이내 90%, 1년 이내 70%, 2년 이내 50%, 4년 이내 30%
        if corrected_on:
            corr_date = date.fromisoformat(corrected_on)
            신고기한_date = date(year + 1, 6, 30)
            경과일 = (corr_date - 신고기한_date).days
            if 경과일 <= 180:      # 6개월 이내
                감경비율 = 90
            elif 경과일 <= 365:    # 1년 이내
                감경비율 = 70
            elif 경과일 <= 730:    # 2년 이내
                감경비율 = 50
            elif 경과일 <= 1460:   # 4년 이내
                감경비율 = 30
            else:
                감경비율 = 0
            감경후_과태료 = _trunc_won(과태료 * (100 - 감경비율) / 100)
        else:
            감경비율 = 0
            감경후_과태료 = 과태료

    # 소명 불이행 과태료: unexplained_amount_krw × 20% (제90조②)
    소명불이행_과태료 = 0
    if unexplained_amount_krw is not None and unexplained_amount_krw > 0:
        소명불이행_과태료 = _trunc_won(_exact(unexplained_amount_krw) * _exact(0.20))

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

    결과 = {
        "신고의무": 신고의무,
        "최고잔액": 최고잔액,
        "최고잔액_월": 최고잔액_월,
        "신고기한": 신고기한,
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
               판단=판단목록,
               주의=주의목록)


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
        }, "소득세법 제101조②, 제97조의2", 판단=적용제외_사유)

    # 증여일부터 양도일까지 10년 초과 → 적용 없음 (제97조의2③ 준용: 등기·등록 기준)
    delta_days = (transfer_dt - gift_dt).days
    delta_years = delta_days / 365.0
    if delta_years > 10:
        적용제외_사유 = f"증여일부터 양도일까지 10년 초과(약 {delta_years:.1f}년) → 제101조② 적용 없음(소득세법 제97조의2③ 준용)"
        return _ok({
            "증여자_직접양도_간주": False,
            "수증자_세액합계": donee_gift_tax + donee_capital_gains_tax,
            "증여자_직접양도세액": donor_direct_capital_gains_tax,
            "적용제외_사유": 적용제외_사유,
        }, "소득세법 제101조②, 제97조의2③", 판단=적용제외_사유)

    # income_belongs_to_donee True → 적용 없음(단서)
    if income_belongs_to_donee:
        적용제외_사유 = "소득 귀속분이 수증자에게 실질적으로 귀속 → 제101조② 단서 적용 제외"
        return _ok({
            "증여자_직접양도_간주": False,
            "수증자_세액합계": donee_gift_tax + donee_capital_gains_tax,
            "증여자_직접양도세액": donor_direct_capital_gains_tax,
            "적용제외_사유": 적용제외_사유,
        }, "소득세법 제101조② 단서", 판단=적용제외_사유)

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
    }, "소득세법 제101조①②③",
       판단=판단목록)
