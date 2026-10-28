"""부동산 양도소득금액 계산 엔진 (capital_gains_income)."""
from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


# ── 날짜 보조 ──────────────────────────────────────────────────────────────

def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def add_years(d: date, n: int) -> date:
    """날짜 d에 n년을 더한다. 2월 29일은 n년 뒤 2월 28일로."""
    y = d.year + n
    try:
        return d.replace(year=y)
    except ValueError:
        # 2월 29일 → 윤년이 아니면 2월 28일
        return d.replace(year=y, day=28)


def full_years(start: date, end: date) -> int:
    """만 보유 년수 (초일 불산입). 취득일의 n년 뒤 같은 날 ≤ 양도일인 최대 n.
    예: 2016-02-29 → 2019-02-28은 3년."""
    n = 0
    while True:
        candidate = add_years(start, n + 1)
        if candidate <= end:
            n += 1
        else:
            break
    return n


# ── vocab 조회 ─────────────────────────────────────────────────────────────

def _vocab_rule_on(name: str, yyyymmdd: int) -> dict:
    """vocab.rule_on을 파이프라인 임포트 없이 직접 쓰고 싶으면 여기서 호출.
    calc_capgains에서는 server 측 함수가 vocab을 감싼 rule_on을 전달하므로
    여기서는 날짜 정수 → dict 조회만 수행한다(어휘 모듈은 서버 측에서 주입)."""
    import korean_tax_calc_mcp.vocab as V
    return V.rule_on(name, yyyymmdd)


def _표1_공제율(보유년: int, 표1: list[list[int | float]]) -> float:
    """표1에서 보유년에 해당하는 공제율. 15년 초과는 15년 행 값(0.30) 사용."""
    best = 0.0
    for yrs, rate in 표1:
        if int(yrs) <= 보유년:
            best = float(rate)
        else:
            break
    return best


def _표2_공제율(보유년: int, 거주년: int, 표2_보유: list[list[int | float]],
                표2_거주: list[list[int | float]] | None) -> float:
    """표2 공제율 = 보유기간 공제율 + 거주기간 공제율."""
    보유율 = 0.0
    for yrs, rate in 표2_보유:
        if int(yrs) <= 보유년:
            보유율 = float(rate)
        else:
            break
    거주율 = 0.0
    if 표2_거주:
        for yrs, rate in 표2_거주:
            if int(yrs) <= 거주년:
                거주율 = float(rate)
            else:
                break
    return 보유율 + 거주율


# ── 메인 계산 ──────────────────────────────────────────────────────────────

def calc_cg(args: dict[str, Any], vocab_on) -> dict:
    """capital_gains_income 계산 본체. vocab_on(date_int) → rule dict.

    반환: 정상이면 {"결과": {...}, "근거": [[...], ...], "판단": [...], "산식": [...]},
          오류면 {"error": ..., "필요 입력": {...}, "문제": [...], ...}.
    """
    # ── 자산 유형 검증 ──
    asset_type = args.get("asset_type")
    if asset_type not in ("토지", "건물", "주택"):
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": [f"asset_type='{asset_type}' 은(는) '토지'|'건물'|'주택' 중 하나여야 함"],
            "필요 입력": {"asset_type": ["토지", "건물", "주택"]},
        }

    # ── 날짜 파싱 ──
    try:
        취득일 = _parse_date(args["acquisition_date"])
        양도일 = _parse_date(args["transfer_date"])
    except (KeyError, ValueError):
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": ["acquisition_date·transfer_date는 YYYY-MM-DD 형식이어야 함"],
            "필요 입력": {"acquisition_date": "str(YYYY-MM-DD)", "transfer_date": "str(YYYY-MM-DD)"},
        }

    if not (date(2017, 1, 1) <= 양도일 <= date(2026, 12, 31)):
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": [f"transfer_date={args['transfer_date']} 은(는) 2017-01-01 ~ 2026-12-31 범위여야 함"],
            "필요 입력": {"transfer_date": "str(2017-01-01 ~ 2026-12-31)"},
        }

    if 양도일 < 취득일:
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": [f"양도일({args['transfer_date']})이 취득일({args['acquisition_date']})보다 앞섬"],
            "필요 입력": {"transfer_date": "str(취득일 이후)", "acquisition_date": "str(양도일 이전)"},
        }

    양도일_int = 양도일.year * 10_000 + 양도일.month * 100 + 양도일.day

    # ── 금액 ──
    양도가액 = int(args["transfer_price"])
    실지거래가액 = int(args["acquisition_price"])
    취득세 = int(args.get("acquisition_tax", 0))
    중개수수료 = int(args.get("acquisition_brokerage", 0))
    보유재산세 = int(args.get("holding_tax_paid", 0))
    자본적지출 = int(args["capital_expenditure"])
    양도비 = int(args["transfer_expenses"])
    등기 = bool(args["registered"])
    환산취득가액_사용 = bool(args.get("환산취득가액_사용", False))
    개산공제 = int(args.get("개산공제", 0))

    # 실지거래가액 사용 시 취득세·중개수수료 합산 (환산취득가액 사용 시 제외)
    if 실지거래가액 > 0 and not 환산취득가액_사용:
        취득가액 = 실지거래가액 + 취득세 + 중개수수료
    elif 환산취득가액_사용:
        # server에서 환산취득가액이 acquisition_price로 전달됨 → 취득가액은 server가 덮어쓰지만
        # 여기서는 취득세·중개수수료를 합산하지 않은 값으로 계산 (일관성)
        환산취득가액 = 실지거래가액  # server가 전달한 환산취득가액
        취득가액 = 환산취득가액 + 개산공제
    else:
        취득가액 = 0

    # ── 주택 분기 ──
    is_주택 = asset_type == "주택"
    one_house = args.get("one_house")
    exempt_met = args.get("exempt_met")
    residence_years = args.get("residence_years")
    heavy_multi_home = args.get("heavy_multi_home")
    houses_count = args.get("houses_count")
    adjusted_area = args.get("adjusted_area")
    exclusion_reason = args.get("exclusion_reason")
    exclusion_basis = args.get("exclusion_basis")
    중과사실 = houses_count is not None or adjusted_area is not None or exclusion_reason is not None
    중과: dict[str, Any] | None = None
    apply_basic = bool(args.get("apply_basic_deduction", False))

    문제목록: list[str] = []
    필요입력: dict[str, Any] = {}

    if is_주택:
        if one_house is None:
            문제목록.append("주택: one_house 입력 필요 — 1세대 1주택 여부")
            필요입력["one_house"] = "bool|None(주택만)"
        elif one_house:
            if exempt_met is None:
                문제목록.append("one_house=True: exempt_met 입력 필요 — 1세대 1주택 비과세 요건 충족 여부")
                필요입력["exempt_met"] = "bool(주택 1주택 비과세 요건 충족 여부)"
            if residence_years is None:
                # 2020.1.1 이전 양도분은 거주 요건 없음(표2_거주요건년=0) → residence_years 불필요
                if 양도일 >= date(2020, 1, 1):
                    문제목록.append("one_house=True: residence_years 입력 필요 — 보유기간 중 거주기간(만 년수)")
                    필요입력["residence_years"] = "int≥0(주택 1주택 거주기간, 만 년수)"
        else:  # one_house=False
            if heavy_multi_home is None and not 중과사실:
                문제목록.append("주택·1세대1주택 아님: 다주택 중과(제104조⑦) 판정 사실 입력 필요 — houses_count·adjusted_area(또는 중과 대상 아님이 확실하면 heavy_multi_home=False)")
                필요입력["heavy_multi_home"] = "bool(주택 1주택 아님, 다주택 중과 대상 여부) — 또는 houses_count·adjusted_area"
                필요입력["houses_count"] = "int≥1(양도일 현재 1세대 주택 수, 조합원입주권·분양권 포함)"
                필요입력["adjusted_area"] = "bool(양도일 현재 조정대상지역 소재 여부)"
            else:
                중과 = 다주택_중과_판정(args["acquisition_date"], args["transfer_date"], houses_count=houses_count,
                                  adjusted_area=adjusted_area, exclusion_reason=exclusion_reason,
                                  exclusion_basis=exclusion_basis, heavy_multi_home=heavy_multi_home)
                if "error" in 중과:
                    return 중과
        if one_house and 중과사실:
            문제목록.append("one_house=True(1세대 1주택)에는 houses_count·adjusted_area·exclusion_reason 입력 불가 — 1세대 1주택 특례 주택은 중과 배제(영 제167조의3①13호 등)")

    # 주택이 아닌 자산에 one_house·exempt_met·residence_years 입력 불가
    if not is_주택:
        if one_house is not None:
            문제목록.append("주택이 아닌 자산(토지·건물)에 one_house 입력 불가")
            필요입력["one_house"] = "bool|None(주택만)"
        if exempt_met is not None:
            문제목록.append("주택이 아닌 자산(토지·건물)에 exempt_met 입력 불가")
            필요입력["exempt_met"] = "bool(주택 1주택 비과세 요건 충족 여부)"
        if residence_years is not None:
            문제목록.append("주택이 아닌 자산(토지·건물)에 residence_years 입력 불가")
            필요입력["residence_years"] = "int≥0(주택 1주택 거주기간, 만 년수)"
        if 중과사실 or heavy_multi_home:
            문제목록.append("다주택 중과(heavy_multi_home·houses_count·adjusted_area·exclusion_reason)는 주택에만 입력")

    if 문제목록:
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": 문제목록,
            "필요 입력": 필요입력,
        }

    # ── 판정 리스트 ──
    판단: list[dict[str, str]] = list(중과["판단"]) if 중과 else []
    중과_적용 = bool(중과 and 중과["적용"])

    # 보유 중 재산세는 필요경비 아님 (소득세법 제97조①)
    if 보유재산세 > 0:
        판단.append({
            "항목": "보유 중 재산세",
            "결론": f"보유 중 재산세 {보유재산세:,}원은 필요경비가 아님(소득세법 제97조①) — 취득가액에 포함하지 않음",
            "근거": "소득세법 제97조①",
        })

    # ── 양도차익 (제97조) ──
    양도차익 = 양도가액 - 취득가액 - 자본적지출 - 양도비
    if 양도차익 < 0:
        양도차익 = 0

    산식목록: list[str] = [f"양도차익 = 양도가액({양도가액:,}원) − 취득가액({취득가액:,}원) − 자본적지출({자본적지출:,}원) − 양도비({양도비:,}원) = {양도차익:,}원 (소득세법 제97조)"]

    # ── 미등기 → 비과세·장기보유특별공제·기본공제 모두 배제 ──
    미등기 = not 등기

    # ── 보유기간(만 년수) 계산 ──
    보유년 = full_years(취득일, 양도일)

    # ── 오류 검증: 서로 안 맞는 입력 ──
    if residence_years is not None and residence_years > 보유년:
        문제목록.append(f"거주기간(residence_years={residence_years}년) > 보유기간(만 {보유년}년) — 서로 안 맞음")
    if not 등기 and exempt_met:
        문제목록.append("미등기양도자산(registered=False)인데 1세대1주택 비과세 요건 충족(exempt_met=True)은 모순")
    if exempt_met and 보유년 < 2:
        문제목록.append(f"exempt_met=True(비과세 요건 충족)인데 보유기간 {보유년}년으로 2년 미만 — 서로 안 맞음")

    if 문제목록:
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": 문제목록,
            "필요 입력": 필요입력,
        }

    # ── 1세대1주택 비과세 / 고가주택 판정 ──
    고가주택_기준 = None
    고가주택_안분비율 = None  # (양도가액 − 기준) / 양도가액, 1 이하
    비과세 = False
    과세대상_양도차익 = 양도차익

    if is_주택 and one_house and exempt_met and not 미등기:
        고가주택_rule = vocab_on("1세대1주택_고가주택", 양도일_int)
        기준금액 = 고가주택_rule.get("기준금액", 900_000_000)
        고가주택_기준 = 기준금액

        if 양도가액 <= 기준금액:
            비과세 = True
            과세대상_양도차익 = 0
            판단.append({
                "항목": "1세대 1주택 비과세",
                "결론": f"비과세(전액) — 양도가액 {양도가액:,}원 ≤ 고가주택 기준 {기준금액:,}원",
                "근거": "소득세법 제89조①3호, 시행령 제154조①",
            })
            산식목록.append(f"양도가액 {양도가액:,}원 ≤ 고가주택 기준 {기준금액:,}원 → 전액 비과세(소득세법 제89조①3호)")
        else:
            고가주택_안분비율 = (양도가액 - 기준금액) / 양도가액
            과세대상_양도차익 = int(양도차익 * 고가주택_안분비율)  # 원 미만 버림
            판단.append({
                "항목": "고가주택 안분",
                "결론": f"고가주택 — 양도가액 {양도가액:,}원 > 기준 {기준금액:,}원, 과세대상 양도차익 {과세대상_양도차익:,}원 (안분비율 {고가주택_안분비율:.4f})",
                "근거": "소득세법 제95조③, 시행령 제156조①·제160조①",
            })
            산식목록.append(f"고가주택 안분: 과세대상 양도차익 = {양도차익:,} × ({양도가액:,} − {기준금액:,}) / {양도가액:,} = {과세대상_양도차익:,}원 (원 미만 버림, 소득세법 시행령 제160조①)")

    # ── 장기보유특별공제 (제95조) ──
    장기보유특별공제_적용표 = None
    공제율 = 0.0
    보유기간_공제율 = 0.0
    거주기간_공제율 = 0.0
    장기보유특별공제액 = 0

    거주년 = residence_years if residence_years is not None else 0

    # 비과세(전액)면 장기보유특별공제 계산하지 않음 (과표 대상 없음)
    if 비과세:
        판단.append({
            "항목": "장기보유특별공제",
            "결론": "1세대 1주택 비과세(전액) — 장기보유특별공제 대상 없음",
            "근거": "소득세법 제89조①3호",
        })
    elif 중과_적용:
        판단.append({
            "항목": "장기보유특별공제",
            "결론": f"조정대상지역 다주택 중과 주택(제104조⑦) — 보유 {보유년}년이어도 장기보유특별공제 배제",
            "근거": "소득세법 제95조② 괄호(제104조⑦ 각 호에 따른 자산 제외, 2018.4.1. 이후 양도분 — 법률 제15225호 부칙 제1조1호)",
        })
    else:
        long_hold_rule = vocab_on("양도소득_장기보유특별공제", 양도일_int)

        if 보유년 >= long_hold_rule.get("최소보유년", 3) and 등기:
            표1 = long_hold_rule.get("표1", [])
            표2_보유 = long_hold_rule.get("표2_보유", [])
            표2_거주 = long_hold_rule.get("표2_거주", None)
            표2_거주요건년 = long_hold_rule.get("표2_거주요건년", 0)

            # 표2 적용 조건: 1세대1주택 & 거주요건 충족 (비과세 요건 exempt_met과 별개)
            # 비과세 미충족(exempt_met=False)이어도 거주 2년 이상이면 표2 적용
            거주요건_충족 = (표2_거주요건년 == 0) or (거주년 >= 표2_거주요건년)
            표2_적용_대상 = is_주택 and one_house and 거주요건_충족

            if 표2_적용_대상:
                공제율 = _표2_공제율(보유년, 거주년, 표2_보유, 표2_거주)
                보유기간_공제율 = _표2_공제율(보유년, 거주년, 표2_보유, None)  # 거주 제외 보유만
                거주기간_공제율 = 공제율 - 보유기간_공제율
                장기보유특별공제_적용표 = "표2"
            else:
                공제율 = _표1_공제율(보유년, 표1)
                보유기간_공제율 = 공제율
                거주기간_공제율 = 0.0
                장기보유특별공제_적용표 = "표1"

            if 고가주택_안분비율 is not None:
                # 고가주택: 표1·표2 모두 양도차익 × 공제율 × (양도가액 − 기준)/양도가액 (시행령 제160조①)
                장기보유특별공제액 = int(양도차익 * 공제율 * 고가주택_안분비율)
                산식목록.append(f"장기보유특별공제({장기보유특별공제_적용표}) = {양도차익:,} × {공제율} × ({양도가액:,} − {고가주택_기준:,}) / {양도가액:,} = {장기보유특별공제액:,}원 (소득세법 제95조②, 시행령 제160조①)")
            else:
                장기보유특별공제액 = int(양도차익 * 공제율)
                산식목록.append(f"장기보유특별공제({장기보유특별공제_적용표}) = {양도차익:,} × {공제율} = {장기보유특별공제액:,}원 (소득세법 제95조②)")

            판단.append({
                "항목": "장기보유특별공제",
                "결론": f"장기보유특별공제 {장기보유특별공제_적용표} 적용 — 보유 {보유년}년{', 거주 '+str(거주년)+'년' if 거주년 else ''} → 공제율 {공제율}, 공제액 {장기보유특별공제액:,}원",
                "근거": "소득세법 제95조②·④ (표1·표2, 보유 3년 이상·등기자산)",
            })
        else:
            if 보유년 < 3:
                판단.append({
                    "항목": "장기보유특별공제",
                    "결론": f"보유 {보유년}년 → 3년 미만으로 장기보유특별공제 미적용",
                    "근거": "소득세법 제95조② (보유 3년 이상)",
                })
            elif not 등기:
                판단.append({
                    "항목": "장기보유특별공제",
                    "결론": "미등기양도자산 — 장기보유특별공제 배제",
                    "근거": "소득세법 제95조②·④ (미등기양도자산 제외)",
                })

    # ── 양도소득금액 ──
    양도소득금액 = 과세대상_양도차익 - 장기보유특별공제액
    if 양도소득금액 < 0:
        양도소득금액 = 0

    산식목록.append(f"양도소득금액 = 과세대상 양도차익 {과세대상_양도차익:,}원 − 장기보유특별공제액 {장기보유특별공제액:,}원 = {양도소득금액:,}원 (소득세법 제95조④)")

    # ── 기본공제·과세표준 ──
    기본공제액 = 0
    과세표준 = 0
    기본공제_적용 = False

    if apply_basic:
        if not 미등기:
            기본공제_rule = vocab_on("양도소득_기본공제", 양도일_int)
            기본공제액 = 기본공제_rule.get("기본공제", 2_500_000)
            과세표준 = 양도소득금액 - 기본공제액
            if 과세표준 < 0:
                과세표준 = 0
            산식목록.append(f"양도소득 기본공제 = {기본공제액:,}원 (연 250만원, 소득세법 제103조①), 과세표준 = {양도소득금액:,} − {기본공제액:,} = {과세표준:,}원 (소득세법 제92조②)")
        else:
            # 미등기: 기본공제 배제, 과세표준 = 양도소득금액
            기본공제액 = 0
            과세표준 = 양도소득금액
            산식목록.append(f"미등기양도자산 — 기본공제 배제(소득세법 제103조①), 과세표준 = 양도소득금액 {양도소득금액:,}원 (소득세법 제92조②)")
        기본공제_적용 = True

    # ── 결과 조립 ──
    결과: dict[str, Any] = {
        "비과세": bool(비과세),
        "양도차익": int(양도차익),
        "과세대상_양도차익": int(과세대상_양도차익),
        "보유기간_년": int(보유년),
        "거주기간_년": int(거주년) if is_주택 and one_house and residence_years is not None else None,
        "장기보유특별공제_적용표": 장기보유특별공제_적용표,
        "공제율": float(공제율),
        "보유기간_공제율": float(보유기간_공제율),
        "거주기간_공제율": float(거주기간_공제율),
        "장기보유특별공제액": int(장기보유특별공제액),
        "양도소득금액": int(양도소득금액),
    }
    if 중과 is not None and (중과["사실입력"] or heavy_multi_home):
        결과["다주택_중과"] = {"적용": 중과_적용, "가산세율": 중과["가산세율"], "구분": 중과["구분"]}

    # 취득가액 구성
    if 환산취득가액_사용:
        # 환산취득가액 경로: 취득세·중개수수료는 합산하지 않고 개산공제로 대체
        # 실지거래가액에는 server가 전달한 환산취득가액 값이 들어있음
        결과["취득가액_구성"] = {
            "실지거래가액": 0,
            "환산취득가액": 실지거래가액,
            "개산공제": 개산공제,
            "취득세": 0,
            "중개수수료": 0,
            "합계": 실지거래가액 + 개산공제,
        }
    elif 실지거래가액 > 0:
        결과["취득가액_구성"] = {
            "실지거래가액": 실지거래가액,
            "취득세": 취득세,
            "중개수수료": 중개수수료,
            "합계": 실지거래가액 + 취득세 + 중개수수료,
        }
    elif 실지거래가액 == 0 and args.get("acquisition_standard_price") is not None:
        # 환산취득가액 사용 시 (실지거래가액 0, 기준시가 있음) — server 우회 호출 대응
        결과["취득가액_구성"] = {
            "실지거래가액": 0,
            "환산취득가액": int(args.get("acquisition_standard_price", 0)),
            "개산공제": 0,
            "합계": 0,
        }

    if 기본공제_적용:
        결과["양도소득_기본공제"] = int(기본공제액)
        결과["양도소득_과세표준"] = int(과세표준)
    else:
        결과["양도소득_기본공제"] = 0
        결과["양도소득_과세표준"] = 0

    # ── 근거 조립 ──
    근거목록: list[list[str]] = [
        ["소득세법", "제97조", "", "양도차익 = 양도가액 − 취득가액 − 자본적지출 − 양도비"],
    ]

    if 장기보유특별공제액 > 0:
        근거목록.append(["소득세법", "제95조", "②", "장기보유특별공제 표1·표2, 보유 3년 이상 등기자산"])
    if 중과_적용:
        근거목록.append(["소득세법", "제104조", "⑦", 중과["근거"]])
        근거목록.append(["소득세법", "제95조", "②", "제104조⑦ 각 호에 따른 자산은 장기보유특별공제 제외"])

    if apply_basic:
        근거목록.append(["소득세법", "제103조", "①", "양도소득 기본공제 연 250만원, 미등기양도자산 제외"])

    if is_주택 and 비과세:
        근거목록.append(["소득세법", "제89조", "①", "3호 1세대 1주택 비과세(고가주택 제외)"])

    if 고가주택_안분비율 is not None:
        근거목록.append(["소득세법", "제95조", "③", "고가주택 양도차익·장기보유특별공제액은 대통령령으로 정함"])
        근거목록.append(["소득세법 시행령", "제160조", "①", "양도차익 × (양도가액 − 기준금액) / 양도가액"])

    근거목록.append(["소득세법", "제92조", "②", "양도소득과세표준 = 양도소득금액 − 양도소득 기본공제"])

    return {
        "결과": 결과,
        "근거": 근거목록,
        "판단": 판단,
        "산식": 산식목록,
    }


# ── 양도소득 산출세액(소득세법 제104조①) ─────────────────────────────────────
# 2021.6.1. 이후 양도분부터 주택(조합원입주권 포함) 단기 세율 인상(법률 제17477호 부칙).
_주택단기_인상일 = date(2021, 6, 1)
# 지정지역 비사업용 토지: 2017.12.19. 개정으로 제104조④ 3호는 제1항제8호 세율(기본세율+10%p)에 10%p를 더함
# (2018.1.1. 시행본부터). 그 전 ④는 제55조① 세율+10%p라 제1항제8호와 같은 세율.
_지정지역_비사업용_가산일 = date(2018, 1, 1)


def _세율_계산식(base: int, yr: int, 기본: int, 후보: list, 세액: int) -> tuple[list, list]:
    """양도소득 세율 후보를 계산식 단계로 — 보유기간·등기·중과 판정은 후보 목록(설명)으로, 세액은 식으로."""
    from .calc_income import income_tax_expr
    입력 = [{"이름": "과세표준", "값": base, "설명": "양도소득 과세표준"}]
    단계 = []
    if any(f[3].startswith("기본세율세액") for f in 후보):
        단계.append({"이름": "기본세율세액", "식": income_tax_expr("과세표준", yr), "값": 기본, "설명": f"제55조① 기본세율({yr}년 구간표)"})
    for k, (라벨, 값, 근거, 식) in enumerate(후보, 1):
        단계.append({"이름": f"후보{k}", "식": 식, "값": 값, "설명": f"{라벨} ({근거})"})
    단계.append({"이름": "산출세액", "식": ("MAX(" + ",".join(f"후보{k}" for k in range(1, len(후보) + 1)) + ")") if len(후보) > 1 else "후보1", "값": 세액,
               "설명": "세율 후보 중 큰 세액(제104조① 각 호 외 단서)"})
    단계.append({"이름": "지방소득세", "식": "ROUNDDOWN(산출세액*0.1,0)", "값": int(세액 * 0.1), "설명": "산출세액의 10%"})
    return 입력, 단계


def capital_gains_tax_amount(base: int, asset_type: str, acquisition_date: str, transfer_date: str,
                             registered: bool, non_business_land: bool, basic_tax,
                             designated_area: bool = False, heavy_surcharge: float = 0.0,
                             heavy_label: str | None = None) -> dict:
    """양도소득 과세표준 → 산출세액. basic_tax(base, year) = 제55조 기본세율 세액.

    후보 세율이 둘 이상이면 큰 세액(제104① 각 호 외 단서). 분양권은 지원하지 않음(호출 쪽에서 거부).
    heavy_surcharge>0(다주택_중과_판정 결과 가산세율)이면 기본세율+가산 후보를 더한다 — 단기 보유 주택은 제104조⑦ 후단에 따라
    제1항제2호·제3호 세액과 비교(이미 후보에 있음)해 큰 세액.
    designated_area=True(지정지역, 제104조의2②)인 비사업용 토지는 2018.1.1. 이후 양도분 기본세율+20%p(제104조④3호)."""
    acq, tr = _parse_date(acquisition_date), _parse_date(transfer_date)
    if tr < acq:
        raise ValueError("transfer_date가 acquisition_date보다 앞섬")
    yr = tr.year
    held = full_years(acq, tr)
    주택 = asset_type == "주택"
    비사업용 = bool(non_business_land and asset_type == "토지")
    지정 = bool(비사업용 and designated_area and tr >= _지정지역_비사업용_가산일)
    # 후보: (세율 표기, 세액, 근거, 세율구분 코드(별지 제84호서식 작성방법), 세율, 누진공제, 가산세율, 엑셀 수식)
    후보: list[tuple[str, int, str, str, float, int, float, str]] = []
    기본 = basic_tax(base, yr)
    한계, 누진 = 한계세율(base, yr)
    if not registered:
        후보.append(("미등기 70%", int(base * 0.70), "소득세법 제104조①10호", "1-30", 0.70, 0, 0.0, "ROUNDDOWN(과세표준*0.7,0)"))
    else:
        if held < 1:
            if 주택:
                r = 0.70 if tr >= _주택단기_인상일 else 0.40
                후보.append((f"주택 1년 미만 {int(r*100)}%", int(base * r), "소득세법 제104조①3호",
                           "1-46" if r == 0.70 else "1-40", r, 0, 0.0, f"ROUNDDOWN(과세표준*{r},0)"))
            else:
                후보.append(("1년 미만 50%", int(base * 0.50), "소득세법 제104조①3호",
                           "1-38" if 지정 else ("1-36" if 비사업용 else "1-20"), 0.50, 0, 0.0, "ROUNDDOWN(과세표준*0.5,0)"))
        elif held < 2:
            if 주택:
                if tr >= _주택단기_인상일:
                    후보.append(("주택 1년 이상 2년 미만 60%", int(base * 0.60), "소득세법 제104조①2호", "1-39", 0.60, 0, 0.0, "ROUNDDOWN(과세표준*0.6,0)"))
                else:
                    후보.append(("주택 1년 이상 2년 미만 — 기본세율(2021.6.1. 전 양도)", 기본, "소득세법 제104조①1호", "1-10", 한계, 누진, 0.0, "기본세율세액"))
            else:
                후보.append(("1년 이상 2년 미만 40%", int(base * 0.40), "소득세법 제104조①2호",
                           "1-37" if 지정 else ("1-35" if 비사업용 else "1-15"), 0.40, 0, 0.0, "ROUNDDOWN(과세표준*0.4,0)"))
        else:
            후보.append(("2년 이상 보유 — 기본세율", 기본, "소득세법 제104조①1호, 제55조①", "1-10", 한계, 누진, 0.0, "기본세율세액"))
        if 비사업용:
            후보.append(("비사업용 토지 — 기본세율 + 10%p", 기본 + int(base * 0.10), "소득세법 제104조①8호", "1-11", 한계, 누진, 0.10, "기본세율세액+ROUNDDOWN(과세표준*0.1,0)"))
            if 지정:
                후보.append(("지정지역 비사업용 토지 — 기본세율 + 20%p(제1항제8호 세율 + 10%p)", 기본 + int(base * 0.20), "소득세법 제104조④3호",
                           "1-31", 한계, 누진, 0.20, "기본세율세액+ROUNDDOWN(과세표준*0.2,0)"))
    if heavy_surcharge and 주택:
        p = int(round(heavy_surcharge * 100))
        후보.append((f"조정대상지역 {heavy_label or '다주택'} 중과 — 기본세율 + {p}%p", 기본 + base * p // 100,
                   "소득세법 제104조⑦" + ("3호·4호" if heavy_label == "3주택 이상" else "1호·2호"),
                   _중과_코드(heavy_label, tr, None), 한계, 누진, p / 100, f"기본세율세액+ROUNDDOWN(과세표준*{p}/100,0)"))
    주의: list[str] = []
    if designated_area:
        if not (non_business_land and asset_type == "토지"):
            주의.append("designated_area는 지정지역의 비사업용 토지(non_business_land=True, 토지)에만 가산(제104조④3호) — 이 자산에는 반영하지 않음")
        elif not registered:
            주의.append("미등기 70%(제104조①10호) 적용 — 지정지역 가산 후보는 비교하지 않음")
        elif tr < _지정지역_비사업용_가산일:
            주의.append("2018.1.1. 전 양도: 제104조④3호 세율이 제55조① 세율+10%p로 제1항제8호(비사업용 토지)와 같아 추가 가산 없음")
        elif tr >= date(2020, 1, 1):
            주의.append("지정지역 공고일 이전에 매매계약을 체결하고 계약금을 받은 사실이 증빙으로 확인되면 ④3호 제외(2020.1.1. 이후 제104조④3호 단서) — 해당하면 designated_area=False")
    best = max(후보, key=lambda x: x[1])
    세액 = best[1]
    코드 = best[3]
    if heavy_surcharge and 주택 and best[3] in ("1-40", "1-46", "1-39"):
        # 중과 주택인데 단기 세율이 더 큰 경우 — 별지 제84호서식 작성방법의 중과 단기 코드(1-53·1-57, 1-82·1-84·1-86·1-88)
        코드 = _중과_코드(heavy_label, tr, best[3])
    return {
        "보유기간_년(세율)": held,
        "적용_세율": best[0],
        "산출세액": 세액,
        "지방소득세": int(세액 * 0.1),
        "세율_후보": [{"세율": a, "세액": b, "근거": c} for a, b, c, *_ in 후보],
        "_계산식": _세율_계산식(base, yr, 기본, [(x[0], x[1], x[2], x[7]) for x in 후보], 세액),
        "근거": best[2] + (", 제104조① 단서(둘 이상이면 큰 세액)" if len(후보) > 1 else ""),
        **({"주의": 주의} if 주의 else {}),
        # 서식(별지 제84호) 칸 계산용 — 호출 쪽에서 계산·계산식_입력으로 옮긴다(결과 키는 그대로)
        "_서식": {"세율구분_코드": 코드, "세율": best[4], "누진공제": best[5], "가산세율": best[6]},
    }


def 한계세율(base: int, year: int) -> tuple[float, int]:
    """제55조① 기본세율의 과세표준 구간 세율과 누진공제액 — 산출세액 = 과세표준 × 세율 − 누진공제.

    구간표는 calc_income.RATES(연도별). 구간 경계값은 낮은 구간(제55조① '초과' 기준)."""
    from .calc_income import RATES, _tier
    tiers = RATES[year]
    prev = 0
    for cap, r in tiers:
        if base <= cap:
            return float(r), int(round(prev * r - _tier(prev, tiers)))
        prev = cap
    return float(tiers[-1][1]), int(round(prev * tiers[-1][1] - _tier(prev, tiers)))


def _중과_코드(heavy_label: str | None, tr: date, 단기코드: str | None) -> str:
    """조정대상지역 다주택 중과 세율구분 코드(별지 제84호서식 작성방법 「과세대상자산 및 세율」).

    2018.4.1.~2021.5.31. 양도: 2주택 1-51(1년 미만 1-53), 3주택 이상 1-55(1년 미만 1-57).
    2021.6.1. 이후 양도: 2주택 1-47(1년 미만 1-84, 1년 이상 2년 미만 1-82), 3주택 이상 1-49(1-88, 1-86).
    조합원입주권·분양권과 합친 경우의 코드(1-52·1-48 등)는 다루지 않는다(도구가 분양권·입주권을 지원하지 않음)."""
    셋 = heavy_label == "3주택 이상"
    if tr < _주택단기_인상일:
        return ("1-57" if 셋 else "1-53") if 단기코드 else ("1-55" if 셋 else "1-51")
    if 단기코드 == "1-46":
        return "1-88" if 셋 else "1-84"
    if 단기코드 == "1-39":
        return "1-86" if 셋 else "1-82"
    return "1-49" if 셋 else "1-47"


# ── 조정대상지역 다주택 중과(소득세법 제104조⑦, 제95조②) ─────────────────────
# 양도일 기준 기간표. 근거 문구는 판단·근거에 그대로 쓴다.
# · 2018.4.1. 이후 양도분부터: 법률 제15225호(2017.12.19.) 부칙 제1조1호(제95조② 본문·제104조⑦ 개정규정 2018.4.1. 시행),
#   제2조②(양도소득 개정규정은 시행 이후 양도하는 자산부터). 2018.4.1. 전에는 지정지역 3주택 이상 +10%p(제104조④1호·2호, 같은 개정으로 삭제).
# · 2021.6.1. 이후 양도분부터 +20%p/+30%p, 보유 2년 미만은 제104조①2호·3호 세액과 비교: 법률 제17477호(2020.8.18.) 부칙 제1조 단서·제3조.
_중과_시행일 = date(2018, 4, 1)
_중과_인상일 = date(2021, 6, 1)
_중과_기간: list[dict[str, Any]] = [
    {"부터": date(2018, 4, 1), "까지": date(2021, 5, 31), "2주택": 0.10, "3주택": 0.20,
     "단기비교": "보유 1년 미만이면 제104조①3호(주택 40%) 세액과 비교",
     "근거": "소득세법 제104조⑦(2017.12.19. 신설) — 법률 제15225호 부칙 제1조1호·제2조②(2018.4.1. 이후 양도분)"},
    {"부터": date(2021, 6, 1), "까지": date(2026, 12, 31), "2주택": 0.20, "3주택": 0.30,
     "단기비교": "보유 2년 미만이면 제104조①2호(60%)·3호(70%) 세액과 비교",
     "근거": "소득세법 제104조⑦(2020.8.18. 개정) — 법률 제17477호 부칙 제1조 단서·제3조(2021.6.1. 이후 양도분)"},
]

# 한시 배제(시행령 제167조의3①·제167조의10①). 보유기간은 법 제95조④(취득일~양도일) 기준.
# · 12호: 보유 10년 이상 주택을 2020.6.30.까지 양도 — 대통령령 제30395호(2020.2.11.) 부칙 제18조: 2019.12.17. 이후 양도분부터.
# · 12호의2: 보유 2년 이상 주택 — 대통령령 제32654호(2022.5.31.) 부칙 제4조: 2022.5.10. 이후 양도분부터.
#   기한: 2023.5.9.(2022.5.31. 영) → 2024.5.9.(2023.2.28. 영) → 2025.5.9.(2024.2.29. 영) → 2026.5.9.(2025.2.28. 영).
#   2026.2.27. 영(2026.4.23. 영으로 다시 개정)으로 가목(2026.5.9.까지 양도) 외에 나목(토지거래허가 대상: 2026.5.9.까지 허가 신청 등,
#   계약일부터 4개월(지정 지역 6개월), 2026.5.10. 이후 계약은 2026.9.9.(지정 지역 2026.11.9.)까지 양도)·
#   다목(허가 대상 아님: 2026.5.9.까지 계약·계약금 수령, 계약일부터 4개월(지정 지역 6개월) 이내 양도) 경과 요건 추가.
_한시배제_12호 = (date(2019, 12, 17), date(2020, 6, 30), 10,
                 "소득세법 시행령 제167조의3①12호·제167조의10①12호(2020.2.11. 개정, 부칙 제18조: 2019.12.17. 이후 양도분) — 보유 10년 이상 주택 2020.6.30.까지 양도")
_한시배제_12호의2: list[tuple[date, date, str]] = [
    (date(2022, 5, 10), date(2023, 5, 9), "2022.5.31. 개정 영 부칙 제4조(2022.5.10. 이후 양도분), 기한 2023.5.9."),
    (date(2023, 5, 10), date(2024, 5, 9), "2023.2.28. 개정 영, 기한 2024.5.9."),
    (date(2024, 5, 10), date(2025, 5, 9), "2024.2.29. 개정 영, 기한 2025.5.9."),
    (date(2025, 5, 10), date(2026, 5, 9), "2025.2.28. 개정 영, 기한 2026.5.9."),
]
_한시배제_경과_마감 = date(2026, 11, 9)   # 나·다목: 2026.5.9.까지 계약(또는 허가 신청) + 최대 6개월 / 나목 단서 2026.11.9.

# 사용자 주장 배제 사유 → (2주택 근거, 3주택 이상 근거). None이면 그 주택 수에는 해당 호 없음.
중과_배제사유: dict[str, tuple[str | None, str | None]] = {
    "지방저가주택": ("영 제167조의10①1호(수도권·광역시·특별자치시 외 기준시가 3억원 이하)", "영 제167조의3①1호(수도권·광역시·특별자치시 외 기준시가 3억원 이하)"),
    "장기임대주택": ("영 제167조의10①2호(영 제167조의3①2호 준용)", "영 제167조의3①2호(장기임대주택)"),
    "감면대상장기임대주택": ("영 제167조의10①2호(영 제167조의3①3호 준용)", "영 제167조의3①3호(감면대상장기임대주택)"),
    "장기사원용주택": ("영 제167조의10①2호(영 제167조의3①4호 준용)", "영 제167조의3①4호(장기사원용주택)"),
    "조특법감면주택": ("영 제167조의10①2호(영 제167조의3①5호 준용)", "영 제167조의3①5호(조세특례제한법상 감면 주택)"),
    "문화재주택": ("영 제167조의10①2호(영 제167조의3①6호 준용)", "영 제167조의3①6호(국가유산·문화재주택)"),
    "상속주택": ("영 제167조의10①2호(영 제167조의3①7호 준용)", "영 제167조의3①7호(상속받은 날부터 5년 이내 상속주택)"),
    "저당권실행취득주택": ("영 제167조의10①2호(영 제167조의3①8호 준용)", "영 제167조의3①8호(저당권 실행 등 취득 3년 이내)"),
    "어린이집주택": ("영 제167조의10①2호(영 제167조의3①8호의2 준용)", "영 제167조의3①8호의2(어린이집 5년 이상 사용)"),
    "취학근무요양": ("영 제167조의10①3호(취학·근무상 형편·질병 요양 등 부득이한 사유)", None),
    "수도권밖주택": ("영 제167조의10①4호(영 제155조⑧ 수도권 밖 주택)", None),
    "소송주택": ("영 제167조의10①7호(소유권 소송 진행 중·판결 확정 3년 이내)", None),
    "기준시가1억이하": ("영 제167조의10①9호(양도 당시 기준시가 1억원 이하, 정비구역 등 제외)", None),
    "일반주택": ("영 제167조의10①10호(제1호~제7호 주택 외 1개 주택만 소유)", "영 제167조의3①10호(제1호~제8호의2 주택 외 1개 주택만 소유)"),
    "조정지역공고전계약": ("영 제167조의10①11호(조정대상지역 공고일 이전 매매계약·계약금 수령)", "영 제167조의3①11호(조정대상지역 공고일 이전 매매계약·계약금 수령)"),
    "1세대1주택특례주택": ("영 제167조의10①15호(2023.2.28. 이후 양도분; 그 전에는 같은 항 5호 동거봉양·6호 혼인·8호 일시적 2주택)", "영 제167조의3①13호(제155조·조특법상 1세대 1주택 특례로 제154조① 적용 주택)"),
    "한시배제_경과": ("영 제167조의10①12호의2 나목·다목(2026.4.23. 개정 시행본)", "영 제167조의3①12호의2 나목·다목(2026.4.23. 개정 시행본)"),
    "기타": ("사용자 제시 근거(exclusion_basis)", "사용자 제시 근거(exclusion_basis)"),
}


def _점(d: date) -> str:
    return f"{d.year}.{d.month}.{d.day}."


def 다주택_중과_판정(acquisition_date: str, transfer_date: str, *, houses_count: int | None = None,
                   adjusted_area: bool | None = None, exclusion_reason: str | None = None,
                   exclusion_basis: str | None = None, heavy_multi_home: bool | None = None,
                   flag_only_ok: bool = False) -> dict:
    """조정대상지역 다주택 중과(제104조⑦) 여부를 양도일 기준으로 판정.

    반환: {"error": ...} 또는 {"적용": bool, "가산세율": float, "구분": str|None, "판단": [...], "근거": str|None, "사실입력": bool}.
    houses_count·adjusted_area가 없으면 heavy_multi_home만으로 판정할 수 있는 경우(flag_only_ok=True: 2018.4.1. 전, 한시 배제)만 계산."""
    acq, tr = _parse_date(acquisition_date), _parse_date(transfer_date)
    보유년 = full_years(acq, tr)   # 법 제95조④ 보유기간(취득일~양도일)
    사실 = houses_count is not None or adjusted_area is not None or exclusion_reason is not None
    없음 = {"적용": False, "가산세율": 0.0, "구분": None, "판단": [], "근거": None, "사실입력": 사실}
    필요 = {"houses_count": "int≥1(양도일 현재 1세대 주택 수 — 조합원입주권·분양권 포함, 영 제167조의3①·제167조의10① 각 호 괄호의 주택 수 제외분은 빼고)",
            "adjusted_area": "bool(양도일 현재 양도 주택이 조정대상지역에 있는지)"}

    if not 사실:
        if not heavy_multi_home:
            return 없음
        if not flag_only_ok:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": ["heavy_multi_home=True만으로는 다주택 중과(제104조⑦) 세율·장기보유특별공제 배제를 정할 수 없음(사실 없이 판정은 지원하지 않음) — houses_count·adjusted_area 입력 필요"],
                    "필요 입력": 필요}
        if tr < _중과_시행일:
            return {**없음, "판단": [{"항목": "다주택 중과", "결론": "조정대상지역 다주택 중과(제104조⑦)는 2018.4.1. 이후 양도분부터 — 이 양도는 일반 세율로 계산",
                                      "근거": _중과_기간[0]["근거"]}]}
        for 부터, 까지, 비고 in _한시배제_12호의2:
            if 부터 <= tr <= 까지 and 보유년 >= 2:
                return {**없음, "판단": [{"항목": "다주택 중과", "결론": f"보유 2년 이상 주택을 {_점(부터)}~{_점(까지)}에 양도 — 중과 한시 배제, 일반 세율로 계산",
                                          "근거": f"소득세법 시행령 제167조의3①12호의2, 제167조의10①12호의2({비고})"}]}
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["heavy_multi_home=True: 중과 기간 양도 — 2주택(+10%p/+20%p)·3주택 이상(+20%p/+30%p) 구분을 위해 houses_count·adjusted_area 입력 필요"],
                "필요 입력": 필요}

    문제: list[str] = []
    if houses_count is None or adjusted_area is None:
        문제.append("다주택 중과 판정에는 houses_count·adjusted_area가 함께 필요")
    elif houses_count < 1:
        문제.append(f"houses_count={houses_count} — 1 이상이어야 함")
    if exclusion_reason is not None and exclusion_reason not in 중과_배제사유:
        문제.append(f"exclusion_reason='{exclusion_reason}' — {list(중과_배제사유)} 중 하나")
    if exclusion_reason == "기타" and not (exclusion_basis or "").strip():
        문제.append("exclusion_reason='기타'는 exclusion_basis(조문·호와 요건 충족 사실)를 함께 입력")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제,
                "필요 입력": {**필요, "exclusion_reason": f"None|{list(중과_배제사유)}"}}

    판단: list[dict[str, str]] = []
    구분 = "3주택 이상" if houses_count >= 3 else ("2주택" if houses_count == 2 else None)

    if tr < _중과_시행일:
        if houses_count >= 3:
            return {"error": "지원하지 않음 — 2018.4.1. 전 양도 3주택 이상",
                    "문제": ["2018.4.1. 전 양도: 지정지역 1세대 3주택 이상 +10%p(제104조④1호·2호, 2017.12.19. 삭제 전) — 지정지역 판정은 지원하지 않음"],
                    "지원하지 않음": "지정지역 다주택 가산(제104조④1호·2호)"}
        판단.append({"항목": "다주택 중과", "결론": "조정대상지역 다주택 중과(제104조⑦)는 2018.4.1. 이후 양도분부터 — 일반 세율, 장기보유특별공제 적용",
                     "근거": _중과_기간[0]["근거"]})
        return {**없음, "판단": 판단}
    if 구분 is None or not adjusted_area:
        사유 = "1세대 주택 수 1개" if 구분 is None else "양도일 현재 조정대상지역 밖 주택"
        if exclusion_reason is not None:
            문제.append(f"{사유}라 중과 대상이 아님 — exclusion_reason은 필요 없음")
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
        판단.append({"항목": "다주택 중과", "결론": f"{사유} — 제104조⑦ 각 호에 해당하지 않아 일반 세율, 장기보유특별공제 적용",
                     "근거": "소득세법 제104조⑦1호~4호(조정대상지역에 있는 주택)"})
        return {**없음, "판단": 판단}

    기간 = next(p for p in _중과_기간 if p["부터"] <= tr <= p["까지"])
    배제근거: str | None = None
    배제결론 = ""
    a12 = _한시배제_12호
    if a12[0] <= tr <= a12[1] and 보유년 >= a12[2]:
        배제근거 = a12[3]
        배제결론 = f"보유 {보유년}년(10년 이상) 주택을 2019.12.17.~2020.6.30.에 양도 — 중과 한시 배제"
    for 부터, 까지, 비고 in _한시배제_12호의2:
        if 배제근거 is None and 부터 <= tr <= 까지 and 보유년 >= 2:
            배제근거 = f"소득세법 시행령 제167조의3①12호의2·제167조의10①12호의2({비고})"
            배제결론 = f"보유 {보유년}년(2년 이상) 주택을 {_점(부터)}~{_점(까지)}에 양도 — 중과 한시 배제"
    if 배제근거 is not None and exclusion_reason not in (None, "한시배제_경과"):
        판단.append({"항목": "중과 배제 사유(사용자 주장)", "결론": f"exclusion_reason='{exclusion_reason}'는 한시 배제로 이미 중과 제외 — 계산에 영향 없음", "근거": 배제근거})
    if 배제근거 is None and exclusion_reason == "한시배제_경과":
        if not (date(2026, 5, 10) <= tr <= _한시배제_경과_마감):
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"exclusion_reason='한시배제_경과'는 2026.5.10.~2026.11.9. 양도분만(영 제167조의3①·제167조의10① 12호의2 나·다목) — 양도일 {transfer_date}"]}
        if 보유년 < 2:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"12호의2는 보유기간 2년 이상 주택만 — 보유 {보유년}년"]}
        배제근거 = 중과_배제사유["한시배제_경과"][1 if 구분 == "3주택 이상" else 0]
        배제결론 = ("2026.5.9.까지 매매계약·계약금 수령(토지거래허가 대상이면 2026.5.9.까지 허가 신청·허가) 후 계약일부터 4개월(지정 지역 6개월, "
                  "나목 2026.5.10. 이후 계약은 2026.9.9./11.9.까지) 이내 양도라는 사용자 주장 — 요건 충족은 사용자 확인, 중과 한시 배제")
    if 배제근거 is None and exclusion_reason is not None:
        근거2, 근거3 = 중과_배제사유[exclusion_reason]
        근거 = 근거3 if 구분 == "3주택 이상" else 근거2
        if 근거 is None:
            return {"error": "입력 확인 필요 — 계산하지 않음",
                    "문제": [f"exclusion_reason='{exclusion_reason}'는 1세대 2주택(영 제167조의10①)에만 있는 배제 사유 — houses_count={houses_count}"]}
        if exclusion_reason == "기타":
            근거 = f"{근거}: {exclusion_basis.strip()}"
        배제근거 = 근거
        배제결론 = f"배제 사유 '{exclusion_reason}' — 사용자 주장(요건 충족은 사용자 확인), 중과 배제"

    if 배제근거 is not None:
        판단.append({"항목": "다주택 중과", "결론": f"조정대상지역 {구분}이나 {배제결론} → 일반 세율, 장기보유특별공제 적용(제95조② 괄호의 제104조⑦ 자산 아님)",
                     "근거": 배제근거})
        return {**없음, "판단": 판단}

    if heavy_multi_home is False:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"heavy_multi_home=False인데 houses_count={houses_count}·adjusted_area=True·배제 사유 없음 → 제104조⑦ 중과 대상 — 서로 안 맞음"]}
    가산 = 기간["3주택" if 구분 == "3주택 이상" else "2주택"]
    호 = "3호·4호" if 구분 == "3주택 이상" else "1호·2호"
    if tr > date(2026, 5, 9) and 보유년 >= 2:
        판단.append({"항목": "한시 배제 경과 요건", "결론": "2026.5.9.까지 계약(토지거래허가 대상은 허가 신청)한 뒤 기한 내 양도했으면 exclusion_reason='한시배제_경과'로 다시 계산",
                     "근거": "소득세법 시행령 제167조의3①12호의2 나목·다목, 제167조의10①12호의2 나목·다목(2026.4.23. 개정)"})
    판단.append({"항목": "다주택 중과", "결론": f"조정대상지역 1세대 {구분}(houses_count={houses_count}) — 기본세율 + {int(round(가산 * 100))}%p, 장기보유특별공제 배제. {기간['단기비교']}",
                 "근거": f"{기간['근거']} 각 호 중 {호}, 제95조② 괄호"})
    return {"적용": True, "가산세율": 가산, "구분": 구분, "판단": 판단, "근거": 기간["근거"], "사실입력": True}
