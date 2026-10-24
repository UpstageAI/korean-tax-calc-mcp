"""연금계좌 인출(연금수령한도·인출순서) · 상속·증여재산 평가 도구. 작성 Claude 2026-10-24.
근거: 소득세법 시행령 제40조의2·제40조의3(2024.1.1. 시행본), 상속세 및 증여세법 제60조·제66조, 시행령 제49조·제63조."""

import math
from datetime import date, timedelta
from typing import Literal

M = 1_000_000


# ── helpers ──────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        raise ValueError(f"날짜 형식 오류: '{s}' — YYYY-MM-DD 형식으로 입력하세요")


def _floor_won(x: float) -> int:
    """원 미만 버림."""
    return int(math.floor(x))


def _add_years(d: date, n: int) -> date:
    """날짜에 n년을 더한다(윤년 2월 29일 처리)."""
    try:
        return d.replace(year=d.year + n)
    except ValueError:
        return d.replace(year=d.year + n, day=28)


# ── pension_account_withdrawal ──────────────────────────────────────────

def pension_account_withdrawal(
    year: int,
    birth_date: str,
    join_date: str,
    start_request_date: str,
    balance_at_period_start: int,
    withdrawal: int,
    contributions_total: int,
    contributions_not_deducted: int,
    deferred_retirement_income: int,
    investment_income: int,
):
    """연금계좌 연금수령한도·인출순서 계산(소득세법 시행령 제40조의2·제40조의3)."""
    # ── 입력 검증 ──
    if contributions_not_deducted > contributions_total:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["contributions_not_deducted(세액공제 받지 못한 납입액)가 contributions_total(납입액 합계)보다 큼"]}

    if any(v < 0 for v in [balance_at_period_start, withdrawal, contributions_total,
                            contributions_not_deducted, deferred_retirement_income, investment_income]):
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["금액 항목에 음수가 있음"]}

    bd = _parse_date(birth_date)
    jd = _parse_date(join_date)
    srd = _parse_date(start_request_date)

    # 날짜 순서 검증 (다른 검사보다 먼저)
    문제목록 = []
    if jd > srd:
        문제목록.append(f"join_date({jd.isoformat()})가 start_request_date({srd.isoformat()})보다 늦습니다")
    if bd > jd:
        문제목록.append(f"birth_date({bd.isoformat()})가 join_date({jd.isoformat()})보다 늦습니다")
    if 문제목록:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제목록}

    #総잔액 (인출순서 나누기의 기준)
    잔액_과세제외 = contributions_not_deducted
    잔액_이연퇴직 = deferred_retirement_income
    잔액_그밖 = contributions_total - contributions_not_deducted + investment_income
    총잔액 = 잔액_과세제외 + 잔액_이연퇴직 + 잔액_그밖

    if withdrawal > 총잔액:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"인출액({withdrawal:,}원)이 재원 잔액 합계({총잔액:,}원)를 초과"]}

    # ── 연금수령 요건 (영 제40조의2③) ──
    # 55세 이후 개시 신청 + 가입일부터 5년 경과(이연퇴직소득 있으면 5년 요건 없음)
    나이55세되는날 = _add_years(bd, 55)
    가입대상5년경과일 = _add_years(jd, 5) if deferred_retirement_income == 0 else None

    연금수령요건충족 = False
    요건사유 = []

    if srd >= 나이55세되는날:
        if deferred_retirement_income > 0:
            연금수령요건충족 = True
            요건사유.append("이연퇴직소득 있어 가입 5년 요건 미적용(영 제40조의2③ 단서)")
        elif 가입대상5년경과일 is not None and srd >= 가입대상5년경과일:
            연금수령요건충족 = True
            요건사유.append(f"가입일({jd.isoformat()})부터 5년 경과({가입대상5년경과일.isoformat()}) 및 55세 이후 개시 신청")
        else:
            요건사유.append(f"가입일부터 5년 미경과(가입일 {jd.isoformat()}, 5년 경과일 {가입대상5년경과일.isoformat() if 가입대상5년경과일 else '해당 없음'})")
    else:
        요건사유.append(f"55세 되는 날({나이55세되는날.isoformat()}) 이전 개시 신청({srd.isoformat()})")

    # ── 연금수령연차 (영 제40조의2④) ──
    # 최초로 연금수령할 수 있는 날 = max(55세 되는 날, 가입 5년 경과일(이연퇴직소득 있으면 생략), 개시 신청일)
    최초연금수령가능일 = max(나이55세되는날, srd)
    if 가입대상5년경과일 is not None:
        최초연금수령가능일 = max(최초연금수령가능일, 가입대상5년경과일)

    # 기산연차연도 = 최초연금수령가능일이 속하는 과세연도
    기산연차연도 = 최초연금수령가능일.year
    # 2013.3.1. 전 가입 계좌는 기산연차 6, 그 외는 1
    base_연차 = 6 if jd < date(2013, 3, 1) else 1
    # 연금수령연차 = base_연차 + (당해연도 - 기산연차연도)
    연금수령연차 = base_연차 + (year - 기산연차연도)

    if 연금수령연차 < 1:
        요건사유.append(f"당해 {year}년은 최초 연금수령 가능일({최초연금수령가능일.isoformat()}) 이전 — 연금수령연차 미도달(연금수령분 없음)")
        연금수령연차 = 0

    # ── 연금수령한도 ──
    if 연금수령연차 >= 11:
        연금수령한도 = None
    else:
        연금수령한도 = _floor_won(balance_at_period_start / (11 - 연금수령연차) * 1.2)

    # ── 인출순서 (영 제40조의3①③) ──
    # 한도 이내 = 연금수령분, 한도 초과 = 연금외수령분
    # 연금수령분이 먼저 인출된 것으로 봄
    #
    # 순서: ① 과세제외금액 → ② 이연퇴직소득 → ③ 그밖
    #
    # 요건 미충족 연도는 전부 연금외수령
    연금수령총액 = 0
    연금외수령총액 = 0

    if 연금수령요건충족 and 연금수령연차 >= 1:
        # 연금수령분: 한도 이내
        한도 = 연금수령한도 if 연금수령한도 is not None else withdrawal  # 연차 11 이상은 한도 없음 → 전부 연금수령
        if 한도 is not None:
            연금수령총액 = min(withdrawal, 한도)
            연금외수령총액 = withdrawal - 연금수령총액
        else:
            연금수령총액 = withdrawal
            연금외수령총액 = 0
    else:
        연금수령총액 = 0
        연금외수령총액 = withdrawal

    # 재원별로 나누기
    # ① 먼저 연금수령분(한도 이내)을 과세제외→이연퇴직→그밖 순으로 채움
    # ② 나머지 인출액은 연금외수령분(그밖)으로
    연금수령분 = {"과세제외금액": 0, "이연퇴직소득": 0, "그밖": 0}
    연금외수령분 = {"과세제외금액": 0, "이연퇴직소득": 0, "그밖": 0}

    남은연금수령 = 연금수령총액
    남은인출액 = withdrawal

    for key, 잔액 in [("과세제외금액", 잔액_과세제외),
                      ("이연퇴직소득", 잔액_이연퇴직),
                      ("그밖", 잔액_그밖)]:
        if 남은연금수령 > 0:
            취함 = min(남은연금수령, 잔액)
            연금수령분[key] = 취함
            남은연금수령 -= 취함
            남은인출액 -= 취함

    # 연금외수령분도 같은 순서로 남은 잔액을 분할 (영 제40조의3①③)
    for key, 잔액 in [("과세제외금액", 잔액_과세제외),
                      ("이연퇴직소득", 잔액_이연퇴직),
                      ("그밖", 잔액_그밖)]:
        if 남은인출액 > 0:
            이미택함 = 연금수령분[key]
            남은잔액 = 잔액 - 이미택함
            취함 = min(남은인출액, 남은잔액)
            연금외수령분[key] = 취함
            남은인출액 -= 취함

    사적연금_총연금액 = 연금수령분["그밖"]  # 종합과세 대상 사적연금
    이연퇴직_연금수령 = 연금수령분["이연퇴직소득"]
    이연퇴직_연금외수령 = 연금외수령분["이연퇴직소득"]
    기타소득_연금외수령 = 연금외수령분["그밖"]

    # ── 판단 문장 ──
    판단문 = []
    if not 연금수령요건충족:
        판단문.append("연금수령 요건 미충족(영 제40조의2③): 55세 이후 개시 신청 및 가입일부터 5년 경과 요건 중 하나 미충족 — 당해 연도 인출 전액 연금외수령")
    else:
        판단문.append("연금수령 요건 충족(영 제40조의2③): 55세 이후 연금수령 개시 신청 + 가입일부터 5년 경과(이연퇴직소득 있는 경우 5년 요건 생략)")

    if 연금수령연차 >= 1:
        기산사유 = []
        if jd < date(2013, 3, 1):
            기산사유.append("2013.3.1. 전 가입 계좌로 기산연차 6")
        기산사유.append(f"최초 연금수령 가능일({최초연금수령가능일.isoformat()})이 속하는 과세기간({최초연금수령가능일.year}년)이 기산연차")
        기산사유.append(f"당해 {year}년은 기산연차로부터 {연금수령연차 - (1 if jd >= date(2013, 3, 1) else 6)}년째 → 연금수령연차 {연금수령연차}")
        판단문.append("연금수령연차 산정(영 제40조의2④): " + "; ".join(기산사유))
    else:
        판단문.append(f"당해 {year}년은 최초 연금수령 가능일({최초연금수령가능일.isoformat()}) 이전 과세기간 — 연금수령연차 미도달")

    if 연금수령한도 is None:
        판단문.append(f"연금수령연차 {연금수령연차}년차로 한도 없음(영 제40조의2④: 연차 11 이상)")
    else:
        판단문.append(f"연금수령한도 = 평가액 {balance_at_period_start:,}원 ÷ (11 − {연금수령연차}) × 120% = {연금수령한도:,}원(원 미만 버림, 영 제40조의2④)")

    판단문.append(f"인출순서(영 제40조의3①③): ① 과세제외금액 {잔액_과세제외:,}원 → ② 이연퇴직소득 {잔액_이연퇴직:,}원 → ③ 그밖(세액공제 받은 납입액 + 운용수익) {잔액_그밖:,}원")
    판단문.append(f"연금수령분 {연금수령총액:,}원(한도 이내), 연금외수령분 {연금외수령총액:,}원(한도 초과)")
    if 연금외수령총액 > 0:
        판단문.append(f"연금외수령분 내역: 과세제외 {연금외수령분['과세제외금액']:,}원 + 이연퇴직 {연금외수령분['이연퇴직소득']:,}원(퇴직소득 과세, 소득세법 제22조①3호) + 그밖 {연금외수령분['그밖']:,}원(기타소득)")

    판단 = {
        "연금수령요건": "충족" if 연금수령요건충족 else "미충족",
        "요건사유": 요건사유,
        "연금수령연차_기산": " ".join(기산사유) if 연금수령연차 >= 1 else f"당해 {year}년은 기산연차 이전",
        "인출순서": f"과세제외금액 {잔액_과세제외:,}원 → 이연퇴직소득 {잔액_이연퇴직:,}원 → 그밖 {잔액_그밖:,}원",
        "근거": "소득세법 시행령 제40조의2③(연금수령 요건)·제40조의2④(연금수령연차·한도), 제40조의3①③(인출순서)",
    }

    계산 = {
        "연금수령연차": 연금수령연차,
        "연금수령한도": 연금수령한도,
    }

    결과 = {
        "연금수령분": 연금수령분,
        "연금외수령분": 연금외수령분,
        "사적연금_총연금액": 사적연금_총연금액,
        "이연퇴직_연금수령": 이연퇴직_연금수령,
        "이연퇴직_연금외수령": 이연퇴직_연금외수령,
        "기타소득_연금외수령": 기타소득_연금외수령,
    }

    return {"결과": 결과, "계산": 계산, "판단": 판단}


# ── inheritance_gift_valuation ──────────────────────────────────────────

def inheritance_gift_valuation(
    kind: Literal["상속", "증여"],
    valuation_date: str,
    supplementary_value: int,
    market_values: list | None = None,
    secured_debt: dict | None = None,
):
    """상속·증여재산 평가: 시가 우선 → 보충적 평가 → 담보 특례(상증법 제60조·제66조, 영 제49조·제63조)."""
    vd = _parse_date(valuation_date)

    # 보충적 평가액 유효성
    if supplementary_value < 0:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["supplementary_value(보충적 평가액)가 음수"]}

    # 평가기간
    if kind == "상속":
        평가기간_전후 = 6  # 전 6개월 ~ 후 6개월
        평가기간_start = vd - timedelta(days=평가기간_전후 * 30)  # 월 단위 근사
        평가기간_end = vd + timedelta(days=평가기간_전후 * 30)
        # 정확한 월 계산: 전 6개월 = vd에서 6개월 뺀 날, 후 6개월 = vd에서 6개월 더한 날
        평가기간_start = _add_months(vd, -6)
        평가기간_end = _add_months(vd, 6)
        기간라벨 = f"평가기준일({vd.isoformat()}) 전 6개월 ~ 후 6개월"
    else:
        평가기간_start = _add_months(vd, -6)
        평가기간_end = _add_months(vd, 3)
        기간라벨 = f"평가기준일({vd.isoformat()}) 전 6개월 ~ 후 3개월"

    def _in_window(d: date) -> bool:
        return 평가기간_start <= d <= 평가기간_end

    # market_values 정리
    if market_values is None:
        market_values = []

    # 해당재산 / 유사재산 분리 + 기간 내 필터링
    해당재산_가액들 = []  # [(종류, 가액, 날짜, 우선일자)]
    유사재산_가액들 = []

    for mv in market_values:
        대상 = mv.get("대상")
        종류 = mv.get("종류")
        가액 = mv.get("가액")
        날짜 = mv.get("날짜")

        if 대상 not in ("해당재산", "유사재산"):
            continue
        if 종류 not in ("매매", "감정", "수용", "경매", "공매"):
            continue
        if not isinstance(가액, (int, float)) or 가액 < 0:
            continue

        dt = _parse_date(날짜) if isinstance(날짜, str) else 날짜
        if not _in_window(dt):
            continue

        기록 = {"종류": 종류, "가액": int(가액), "날짜": dt}
        if 대상 == "해당재산":
            해당재산_가액들.append(기록)
        else:
            유사재산_가액들.append(기록)

    # 시가 결정
    시가 = None
    적용근거 = ""

    def _최선의가액(가액들: list) -> int | None:
        """가액 목록에서 최선 가액 결정: 감정이 둘 이상이면 평균, 종류가 여럿이면 평가기준일 가장 가까운 날짜 값(감정 여럿이면 그 평균)."""
        if not 가액들:
            return None

        # 감정가액만 모으기
        감정들 = [g for g in 가액들 if g["종류"] == "감정"]
        비감정들 = [g for g in 가액들 if g["종류"] != "감정"]

        # 감정이 둘 이상 → 평균 (영 제49①2호)
        if len(감정들) >= 2:
            avg = sum(g["가액"] for g in 감정들) / len(감정들)
            # 평균값에서 날짜는 감정들의 날짜 중 평가기준일과 가장 가까운 것
            closest_dt = min(감정들, key=lambda g: abs((g["날짜"] - vd).days))["날짜"]
            return int(round(avg)), closest_dt, "감정 평균"

        # 감정이 하나 + 비감정이 여럿 → 감정 우선 (영 제49②: 종류가 여럿이면 평가기준일 가장 가까운 날짜)
        # 비감정만 있으면 가장 가까운 날짜
        모두 = 감정들 + 비감정들
        closest = min(모두, key=lambda g: abs((g["날짜"] - vd).days))
        return closest["가액"], closest["날짜"], closest["종류"]

    # 1) 해당재산 가액이 있으면 그것이 시가
    해당결과 = _최선의가액(해당재산_가액들)
    if 해당결과 is not None:
        시가, 시가날짜, 적용종류 = 해당결과
        적용근거 = f"해당재산 {적용종류}가액"
    else:
        # 2) 해당재산 없으면 유사재산
        유사결과 = _최선의가액(유사재산_가액들)
        if 유사결과 is not None:
            시가, 시가날짜, 적용종류 = 유사결과
            적용근거 = f"유사재산 {적용종류}가액"
        else:
            시가 = None
            적용근거 = "시가 없음 — 보충적 평가액 적용(법 제61조)"

    # 담보 특례(법 제66조, 영 제63조)
    담보채권액 = 0
    if secured_debt:
        최대 = secured_debt.get("채권최고액")
        채무 = secured_debt.get("채무액", 0)
        if 최대 is not None:
            담보채권액 = min(int(최대), int(채무))
        else:
            담보채권액 = int(채무)

    평가액 = supplementary_value
    if 시가 is not None:
        평가액 = max(시가, 담보채권액) if 담보채권액 > 0 else 시가
    else:
        평가액 = max(supplementary_value, 담보채권액) if 담보채권액 > 0 else supplementary_value

    # 판단
    판단사항 = []
    if market_values and (해당재산_가액들 or 유사재산_가액들):
        판단사항.append(f"평가기간: {기간라벨} — 기간 내 가액만 시가로 인정(영 제49①)")
    elif market_values:
        기간밖사유 = []
        for mv in market_values:
            dt = _parse_date(mv["날짜"]) if isinstance(mv["날짜"], str) else mv["날짜"]
            if not _in_window(dt):
                기간밖사유.append(f"{mv.get('대상')} {mv.get('종류')}가액({mv['가액']:,}원, {mv['날짜']})은 평가기간 밖")
        if 기간밖사유:
            판단사항.append("기간 밖 가액 제외: " + "; ".join(기간밖사유))
        else:
            판단사항.append(f"평가기간: {기간라벨} — 해당 없음")

    if 시가 is not None:
        판단사항.append(f"시가 = {적용근거} = {시가:,}원")
    else:
        판단사항.append("해당재산·유사재산 시가 모두 없음 → 보충적 평가액(법 제61조) 적용")

    if 담보채권액 > 0:
        판단사항.append(f"담보특약(법 제66조, 영 제63조): 담보채권액 = {'min(채권최고액, 채무액)' if secured_debt.get('채권최고액') is not None else '채무액'} = {담보채권액:,}원, 평가액 = max(시가·보충액, 담보채권액) = {평가액:,}원")
    else:
        판단사항.append(f"담보 없음 → 평가액 = {'시가' if 시가 is not None else '보충적 평가액'} = {평가액:,}원")

    판단 = {
        "평가기간": 기간라벨,
        "시가_결정": 적용근거,
        "담보특례": f"담보채권액 {담보채권액:,}원" if 담보채권액 > 0 else "해당 없음",
        "근거": "상속세 및 증여세법 제60조(평가원칙)·제66조(담보 부동산 등)·시행령 제49조(시가)·제63조(저당권 등 담보재산)",
    }

    계산 = {
        "시가": 시가,
        "적용": 적용근거,
        "담보채권액": 담보채권액,
    }

    결과 = {
        "평가액": 평가액,
    }

    return {"결과": 결과, "계산": 계산, "판단": 판단}


# ── 월 더하기/빼기 헬퍼 ──────────────────────────────────────────────────

def _add_months(d: date, months: int) -> date:
    """날짜에 months(음수 가능)를 더한다.

    평가기간 계산용: 상속=전후 6개월, 증여=전 6개월~후 3개월.
    월 단위 이동 후 일은 원본 일 유지, 말일인 경우 말일로 조정.
    """
    total_months = d.year * 12 + d.month - 1 + months
    new_year = total_months // 12
    new_month = total_months % 12 + 1
    new_day = min(d.day, _days_in_month(new_year, new_month))
    return date(new_year, new_month, new_day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    import calendar
    return calendar.monthrange(year, month)[1]
