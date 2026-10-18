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
    취득가액 = int(args["acquisition_price"])
    자본적지출 = int(args["capital_expenditure"])
    양도비 = int(args["transfer_expenses"])
    등기 = bool(args["registered"])

    # ── 주택 분기 ──
    is_주택 = asset_type == "주택"
    one_house = args.get("one_house")
    exempt_met = args.get("exempt_met")
    residence_years = args.get("residence_years")
    heavy_multi_home = args.get("heavy_multi_home")
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
            if heavy_multi_home is None:
                문제목록.append("주택·1세대1주택 아님: heavy_multi_home 입력 필요 — 다주택 중과 대상 여부")
                필요입력["heavy_multi_home"] = "bool(주택 1주택 아님, 다주택 중과 대상 여부)"
            elif heavy_multi_home:
                return {
                    "error": "지원하지 않음 — 다주택 중과(제104조⑦) 대상 자산",
                    "문제": ["heavy_multi_home=True: 다주택 중과 대상 — 지원하지 않음"],
                    "지원하지 않음": "다주택·조정대상지역 중과(제104조⑦)",
                    "필요 입력": 필요입력,
                }

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

    if 문제목록:
        return {
            "error": "입력 확인 필요 — 계산하지 않음",
            "문제": 문제목록,
            "필요 입력": 필요입력,
        }

    # ── 판정 리스트 ──
    판단: list[dict[str, str]] = []

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
