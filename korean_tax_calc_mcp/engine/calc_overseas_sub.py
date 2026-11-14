"""해외현지법인 명세서·재무상황표 `overseas_subsidiary_statement` — 국조칙 별지 제47호·제48호서식 (Claude 2026-11-14).

조문 대조(국세법령정보시스템·법제처 보관 응답, 각 시행본):
- 국제조세조정에 관한 법률 제58조제1항: 2021.1.1.(법률 제17651호 전부개정)·2022.1.1.·2023.1.1.·2024.1.1.·2025.1.1.·2026.1.2. 시행본 —
  전 기간 "사업연도(과세기간) 종료일이 속하는 달의 말일부터 6개월 이내". 2023.1.1. 시행본부터 주식 양도·청산으로
  해외직접투자에 해당하지 않게 된 경우도 같음(후단 신설).
- 같은 법 부칙(법률 제17651호) 제28조: 시행 전에 개시한 사업연도 자료로서 시행 당시 이미 종전 규정(구 법인세법 제121조의2①,
  구 소득세법 제165조의2①)의 제출기한이 지난 경우에는 종전 규정.
- 같은 법 시행령 제98조제1항: 2021.2.17.·2022.2.15.·2023.2.28.·2024.1.1.·2024.2.29.·2025.2.28.·2025.11.28.·2026.2.27. 시행본 —
  재무상황표 대상(제2호 가목·나목)과 손실거래명세서 대상(제3호 가목 거주자 10억·20억, 나목 내국법인 50억·100억) 문언 같음.
서식: 국조칙 별지 제47호서식(<개정 2026. 1. 2.>)·별지 제48호서식(<개정 2022. 3. 18.>) — 2026.3.20. 시행 시행규칙 HWP.
"""
from __future__ import annotations

import calendar
from datetime import date

_억 = 100_000_000

# 별지 제48호서식 코드(칸 번호) — 서식에 있는 번호만
CODES_BS = ("01", "50", "02", "03", "04", "05", "55", "06", "07", "08", "09", "10", "11", "12", "13",
            "14", "15", "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26")
CODES_PL = ("27", "28", "29", "30", "51", "52", "56", "31", "32", "33", "34", "35", "36", "37", "57",
            "38", "39", "40", "53", "41", "42", "43", "44", "58", "47", "48")
CODES_RE = tuple(f"{n}" for n in range(71, 83))
CODES_DEF = tuple(f"{n}" for n in range(83, 94))
CODES = CODES_BS + CODES_PL + CODES_RE + CODES_DEF

# (왼쪽 코드, [(부호, 코드)…], 설명) — 회계 항등식·서식의 하위 과목 합계. 서식에 산식으로 적혀 있지는 않아 '확인'으로만 씀
IDENTITIES = (
    ("01", ((1, "14"), (1, "21")), "01 자산총계 = 14 부채총계 + 21 자본금총계"),
    ("56", ((1, "27"), (-1, "30")), "56 매출총손익 = 27 매출액 − 30 매출원가"),
    ("57", ((1, "56"), (-1, "31")), "57 영업손익 = 56 매출총손익 − 31 판매비와 일반관리비"),
    ("58", ((1, "57"), (1, "38"), (-1, "42")), "58 법인세비용 차감전손익 = 57 영업손익 + 38 영업외수익 − 42 영업외비용"),
    ("48", ((1, "58"), (-1, "47")), "48 당기순손익 = 58 법인세비용 차감전손익 − 47 법인세비용"),
    ("82", ((1, "71"), (1, "76"), (-1, "77")), "82 차기 이월이익잉여금 = 71 미처분이익잉여금 + 76 임의적립금 등의 이입액 − 77 이익잉여금 처분액"),
    ("08", ((1, "09"), (1, "10"), (1, "11")), "08 유형자산 = 09 + 10 + 11"),
    ("14", tuple((1, c) for c in ("15", "16", "17", "18", "19", "20")), "14 부채총계 = 15 + 16 + 17 + 18 + 19 + 20"),
    ("21", ((1, "22"), (1, "23")), "21 자본금총계 = 22 자본금 + 23 기타 자본금"),
    ("23", ((1, "24"), (1, "25"), (1, "26")), "23 기타 자본금 = 24 + 25 + 26"),
    ("27", ((1, "28"), (1, "29")), "27 매출액 = 28 + 29"),
    ("31", tuple((1, c) for c in ("32", "33", "34", "35", "36", "37")), "31 판매비와 일반관리비 = 32 + 33 + 34 + 35 + 36 + 37"),
    ("38", ((1, "39"), (1, "40"), (1, "53"), (1, "41")), "38 영업외수익 = 39 + 40 + 53 + 41"),
    ("42", ((1, "43"), (1, "44")), "42 영업외비용 = 43 + 44"),
    ("77", ((1, "78"), (1, "79"), (1, "80"), (1, "81")), "77 이익잉여금 처분액 = 78 + 79 + 80 + 81"),
)

_근거 = ("국제조세조정에 관한 법률 제58조제1항, 시행령 제98조제1항·제3항, 시행규칙 별지 제47호서식·별지 제48호서식, "
        "부칙(법률 제17651호) 제28조")


def _오류(문제: list[str]) -> dict:
    return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제,
            "허용값": {"year": "2021~2026", "filer": "법인 | 개인", "비율": "0 이상 1 이하",
                     "financials": "별지 제48호서식 코드 문자열(01~93 중 서식에 있는 번호) → 원"}}


def _month_end_plus(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return date(y, m, calendar.monthrange(y, m)[1])


def statement(year, filer="법인", fy_end=None, subsidiary=None, ownership_direct=0.0, ownership_indirect=0.0,
              equity_investment=0, loan_investment=0, related_party=False, loss_single_year=None,
              loss_cumulative_5y=None, financials=None, provisional=False) -> dict:
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    문제: list[str] = []
    if not (isinstance(year, int) and not isinstance(year, bool) and 2021 <= year <= 2026):
        문제.append(f"year={year} — 2021~2026만(2020 사업연도 이전은 구 법인세법 제121조의2·소득세법 제165조의2 시기 — 서식 번호 미확인, 부칙 제28조)")
    if filer not in ("법인", "개인"):
        문제.append(f"filer='{filer}' — 법인 또는 개인")
    for 이름, v in (("ownership_direct", ownership_direct), ("ownership_indirect", ownership_indirect)):
        if not (num(v) and 0 <= v <= 1):
            문제.append(f"{이름}={v} — 0 이상 1 이하")
    if num(ownership_direct) and num(ownership_indirect) and ownership_direct + ownership_indirect > 1 + 1e-12:
        문제.append("ownership_direct + ownership_indirect — 1 초과")
    for 이름, v in (("equity_investment", equity_investment), ("loan_investment", loan_investment)):
        if not (num(v) and v >= 0):
            문제.append(f"{이름}={v} — 0 이상 원")
    for 이름, v in (("loss_single_year", loss_single_year), ("loss_cumulative_5y", loss_cumulative_5y)):
        if v is not None and not (num(v) and v >= 0):
            문제.append(f"{이름}={v} — 0 이상 원")
    if subsidiary is not None and not isinstance(subsidiary, dict):
        문제.append("subsidiary — dict")
    fin: dict[str, int] = {}
    if financials is not None:
        if not isinstance(financials, dict):
            문제.append("financials — dict(코드 → 원)")
        else:
            for k, v in financials.items():
                kk = str(k).zfill(2) if str(k).isdigit() else str(k)
                if kk not in CODES:
                    문제.append(f"financials['{k}'] — 별지 제48호서식에 없는 코드")
                elif not num(v):
                    문제.append(f"financials['{k}']={v} — 숫자(원, 손실은 음수)")
                else:
                    fin[kk] = v
    end = None
    if fy_end is not None:
        try:
            end = date.fromisoformat(str(fy_end))
        except ValueError:
            문제.append(f"fy_end='{fy_end}' — YYYY-MM-DD")
    if not 문제 and end is not None and not (end.year in (year, year + 1)):
        문제.append(f"fy_end={fy_end} — year({year}) 개시 사업연도의 종료일이 아님")
    if 문제:
        return _오류(문제)
    if end is None:
        end = date(year, 12, 31)

    direct, indirect = float(ownership_direct), float(ownership_indirect)
    total = direct + indirect
    invest = int(equity_investment) + int(loan_investment)
    가목 = direct >= 0.10 and invest >= _억
    나목 = total >= 0.10 and bool(related_party)
    재무 = 가목 or 나목
    사유 = [s for s, ok in (("영 제98조제1항제2호가목(10% 이상 소유·투자금액 1억원 이상)", 가목),
                            ("영 제98조제1항제2호나목(직접·간접 10% 이상·특수관계)", 나목)) if ok]
    단일, 누적 = (10 * _억, 20 * _억) if filer == "개인" else (50 * _억, 100 * _억)
    손실 = None
    if loss_single_year is not None or loss_cumulative_5y is not None:
        손실 = 나목 and ((loss_single_year or 0) >= 단일 or (loss_cumulative_5y or 0) >= 누적)
    기한 = _month_end_plus(end, 6)

    항등식, 우변 = [], {}
    for lhs, terms, 설명 in IDENTITIES:
        codes = [lhs] + [c for _, c in terms]
        if not all(c in fin for c in codes):
            continue
        rhs = sum(s * fin[c] for s, c in terms)
        우변[lhs] = rhs
        항등식.append({"식": 설명, "왼쪽": fin[lhs], "오른쪽": rhs, "차이": fin[lhs] - rhs,
                     "판정": "일치" if fin[lhs] == rhs else "확인 필요"})
    불일치 = sum(1 for x in 항등식 if x["판정"] != "일치")

    결과 = {
        "명세서_제출대상": True, "재무상황표_제출대상": 재무, "재무상황표_사유": 사유,
        "손실거래명세서_제출대상": 손실, "제출기한": 기한.isoformat(),
        "직접지분율": direct, "간접지분율": indirect, "지분율_합계": total, "투자금액": invest,
        "항등식_확인": 항등식, "항등식_불일치": 불일치, "항등식_오른쪽": 우변,
    }
    판단 = [
        "해외현지법인 명세서(별지 제47호서식): 「외국환거래법」 제3조제1항제18호가목의 해외직접투자를 한 거주자·내국법인 모두(영 제98조제1항제1호) — 이 도구는 해외직접투자를 전제로 함",
        ("해외현지법인 재무상황표(별지 제48호서식) 제출 대상: " + "·".join(사유)) if 재무 else
        f"해외현지법인 재무상황표 제출 대상 아님 — 직접 지분율 {direct:.1%}·투자금액 {invest:,}원, 직접·간접 {total:.1%}·특수관계 {'있음' if related_party else '없음'}(영 제98조제1항제2호)",
    ]
    if 손실 is not None:
        판단.append(("손실거래명세서 제출 대상" if 손실 else "손실거래명세서 제출 대상 아님")
                    + f" — {filer} 기준 단일 {단일 // _억}억원·5년 누적 {누적 // _억}억원 이상, 제2호나목 해당자만(영 제98조제1항제3호)")
    판단.append(f"제출기한 {기한.isoformat()} — 사업연도(과세기간) 종료일 {end.isoformat()}이 속하는 달의 말일부터 6개월(법 제58조제1항)")
    if 불일치:
        판단.append(f"재무상황표 금액 확인 필요 {불일치}건 — 항등식_확인의 '확인 필요' 줄(서식에 산식으로 적힌 것은 아니고 회계 항등식·하위 과목 합계)")
    주의 = [
        "투자금액(증권투자+대부투자)의 1억원은 각 투자실행일의 매매기준율로 환산(별지 제48호서식 작성방법). 출자금액은 투자 당시 환율로 적고 이후 환차는 반영하지 않음(별지 제47호서식 작성방법 9)",
        "간접 지분율은 호출자가 계산해 넣음 — 이 도구는 간접소유비율 계산 방법을 다루지 않음",
        "손실거래금액의 '단일 사업연도 50억원(거주자 10억원)'은 입력 loss_single_year를 그대로 비교함(건별 손실금액의 합인지 건별 최대인지는 문언만으로 정하지 않음 — 확인 필요)",
        "2023년 시행본부터 사업연도 중 주식 양도·청산으로 해외직접투자에 해당하지 않게 된 경우에도 같은 기한에 제출(법 제58조제1항 후단)",
        "제출하지 않거나 거짓 제출이면 과태료 대상(2021년 시행본 법 제63조제1항, 10% 이상 직접·간접 소유한 경우) — 이 도구는 과태료를 계산하지 않으며 이후 연도 조문 번호는 대조하지 않음",
        "재무상황표 금액은 원화 환산액: 재무상태표·잉여금은 현지법인 사업연도 종료일 매매기준율(⑩), 손익은 평균환율(⑪)",
    ]
    return {"결과": 결과, "근거": _근거, "판단": 판단, "주의": 주의, "fin": fin, "end": end}
