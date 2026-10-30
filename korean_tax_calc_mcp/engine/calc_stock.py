"""주식등 양도소득 — 대주주 판정(소득세법 시행령 제157조·제167조의8)과 세율·산출세액(법 제104조①11호·12호).
규칙은 data/stock_gains_rules.json(양도일 구간별). 작성 Claude 2026-10-30, 조문 원문 대조."""
from __future__ import annotations

import calendar
import json
import os
from datetime import date, datetime, timedelta
from typing import Any

_RULES: dict | None = None
_MARKETS = ("코스피", "코스닥", "코넥스", "비상장", "K-OTC", "국외")
_MARKET_SYNONYMS = [
    ("국외", ("국외", "해외", "외국", "미국", "나스닥", "nasdaq", "nyse", "foreign")),
    ("K-OTC", ("k-otc", "kotc", "케이오티씨", "장외시장", "금융투자협회")),
    ("코넥스", ("코넥스", "konex")),
    ("코스닥", ("코스닥", "kosdaq")),
    ("코스피", ("코스피", "kospi", "유가증권", "거래소", "상장")),
    ("비상장", ("비상장", "장외", "비등록", "unlisted")),
]


def _rules() -> dict:
    global _RULES
    if _RULES is None:
        p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "stock_gains_rules.json")
        with open(p, encoding="utf-8") as f:
            _RULES = json.load(f)
    return _RULES


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _period(items: list[dict], d: date) -> dict:
    for it in items:
        if _d(it["from"]) <= d <= _d(it["to"]):
            return it
    raise ValueError(f"{d.isoformat()} — 2016~2026 양도분만 지원")


def normalize_market(market: str) -> tuple[str | None, str | None]:
    """시장 표현을 표준값으로. (표준값, 해석문) — 해석문은 바뀌었을 때만."""
    raw = (market or "").strip()
    if raw in _MARKETS:
        return raw, None
    low = raw.lower().replace(" ", "")
    for std, keys in _MARKET_SYNONYMS:
        if any(k in low for k in keys):
            return std, f"market '{raw}' → '{std}'"
    return None, None


def _ratio(x: float | int | None) -> tuple[float | None, str | None]:
    """지분율: 0~1 비율. 1보다 크면 퍼센트로 본다."""
    if x is None:
        return None, None
    v = float(x)
    if v > 1.0:
        return v / 100.0, f"지분율 {x} → {v / 100.0:.4f}(퍼센트로 해석)"
    return v, None


def _pct(v: float) -> str:
    return f"{v * 100:g}%"


def _won(v: int | float) -> str:
    return f"{int(round(v)):,}원"


# ── 대주주 판정 ──────────────────────────────────────────────────────────────

def major_shareholder(transfer_date: str, market: str, own_ratio=None, own_mcap=None, related_ratio=None, related_mcap=None,
                      is_max_group: bool | None = None, venture: bool = False, is_corporation: bool = False,
                      acquired_to_threshold: bool = False) -> dict[str, Any]:
    R = _rules()
    td = _d(transfer_date)
    해석: list[str] = []
    std, note = normalize_market(market)
    if std is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"market='{market}'은(는) 알 수 없는 시장"],
                "허용값": {"코스피": "유가증권시장 상장", "코스닥": "코스닥 상장", "코넥스": "코넥스 상장", "비상장": "상장되지 않은 법인(장외)", "K-OTC": "금융투자협회 장외시장 거래 비상장주식", "국외": "국외 주식(대주주 판정 없음)"}}
    if note:
        해석.append(note)
    if std == "국외":
        return {"error": "국외주식은 대주주 판정이 없음 — 세율은 중소기업 여부로만 갈림(법 제104조①12호). stock_capital_gains_tax를 바로 부르세요"}
    try:
        P = _period(R["대주주 요건"], td)
    except ValueError as e:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [str(e)]}
    if is_corporation and P.get("법인 제외"):
        return {"결과": {"판정": "대상 아님", "이유": "2025.2.28. 이후 양도분부터 주주 1인은 법인을 제외 — 법인 주주의 주식 양도차익은 법인세로 과세"},
                "근거": "소득세법 시행령 제157조①1호(2025.2.28. 개정)", "판단": [{"항목": "주주 구분", "결론": "법인 주주 — 소득세법 대주주 판정 대상 아님", "근거": P["근거"]}]}
    own_r, n1 = _ratio(own_ratio); rel_r, n2 = _ratio(related_ratio)
    for n in (n1, n2):
        if n:
            해석.append(n)
    own_m = float(own_mcap) if own_mcap is not None else None
    rel_m = float(related_mcap) if related_mcap is not None else None
    if own_r is None and own_m is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["own_ratio(직전 사업연도 종료일 현재 본인 지분율) 또는 own_mcap(본인 보유 시가총액) 중 하나는 필요"],
                "필요 입력": {"own_ratio": "0~1 또는 %", "own_mcap": "원"}}

    if std in ("코스피", "코스닥", "코넥스"):
        thr_r, thr_m = P["상장"][std]; 시장명 = f"{std} 상장법인"
    else:
        thr_r, thr_m = P["비상장_벤처"] if venture else P["비상장"]; 시장명 = "비상장법인" + ("(벤처기업)" if venture else "") + (" — K-OTC 거래" if std == "K-OTC" else "")
    mode = P["합산"]
    판단: list[dict] = []
    판단.append({"항목": "적용 기준", "결론": f"{시장명}: 지분율 {_pct(thr_r)} 이상 또는 시가총액 {_won(thr_m)} 이상(직전 사업연도 종료일 현재), 양도일 {transfer_date} 기준 구간 {P['from']}~{P['to']}", "근거": P["근거"]})

    def meets(r, m):
        hit = []
        if r is not None and r >= thr_r:
            hit.append(f"지분율 {_pct(r)} ≥ {_pct(thr_r)}")
        if m is not None and m >= thr_m:
            hit.append(f"시가총액 {_won(m)} ≥ {_won(thr_m)}")
        return hit

    own_hit = meets(own_r, own_m)
    comb_r = (own_r or 0.0) + (rel_r or 0.0) if (own_r is not None or rel_r is not None) else None
    comb_m = (own_m or 0.0) + (rel_m or 0.0) if (own_m is not None or rel_m is not None) else None
    comb_hit = meets(comb_r, comb_m)
    has_related = (rel_r or 0) > 0 or (rel_m or 0) > 0

    판정 = None; 이유 = ""
    if mode in ("all", "max_group_split"):
        판단.append({"항목": "합산 방식", "결론": P["합산 설명"], "근거": P["근거"]})
        if comb_hit:
            판정, 이유 = "대주주", "본인+특수관계인 합산 기준 충족: " + ", ".join(comb_hit)
        else:
            판정, 이유 = "대주주 아님", f"합산 지분율 {_pct(comb_r) if comb_r is not None else '미입력'}·시가총액 {_won(comb_m) if comb_m is not None else '미입력'} 모두 기준 미달"
            if not has_related:
                판단.append({"항목": "특수관계인", "결론": "특수관계인 지분·시가총액을 주지 않아 0으로 봄 — 있으면 related_ratio·related_mcap에 넣어 다시(이 구간은 합산 판정)", "근거": P["근거"]})
    else:  # self_unless_max
        판단.append({"항목": "합산 방식", "결론": P["합산 설명"], "근거": P["근거"]})
        if own_hit:
            판정, 이유 = "대주주", "본인 단독 기준 충족: " + ", ".join(own_hit)
        elif is_max_group is True:
            if comb_hit:
                판정, 이유 = "대주주", "최대주주군이라 기타주주 합산 — 기준 충족: " + ", ".join(comb_hit)
            else:
                판정, 이유 = "대주주 아님", "최대주주군 합산으로도 기준 미달"
                if not has_related:
                    판단.append({"항목": "특수관계인", "결론": "최대주주군인데 기타주주 지분을 주지 않아 0으로 봄 — 있으면 related_ratio·related_mcap에 넣어 다시", "근거": P["근거"]})
        elif is_max_group is False:
            판정, 이유 = "대주주 아님", "본인 단독 기준 미달이고 최대주주군이 아니므로 합산하지 않음"
        else:
            if comb_hit and has_related:
                판정, 이유 = "확인 필요", "본인 단독으로는 미달이지만 특수관계인과 합하면 충족 — 주주 1인등의 지분 합계가 그 법인에서 최대인지(is_max_group)에 따라 갈림"
            else:
                판정, 이유 = "대주주 아님", "본인 단독 기준 미달(특수관계인 합산으로도 미달이거나 미입력)"
                if not has_related:
                    판단.append({"항목": "특수관계인", "결론": "최대주주군이면 기타주주 지분을 합산 — 해당하면 is_max_group=True와 related_ratio·related_mcap을 넣어 다시", "근거": P["근거"]})
    if 판정 != "대주주" and acquired_to_threshold:
        판정, 이유 = "대주주", "직전 사업연도 종료일에는 미달이었으나 그 뒤 주식 취득으로 지분율 기준에 이름 — 취득일 이후 양도분은 대주주"
        판단.append({"항목": "사후 취득", "결론": 이유, "근거": "소득세법 시행령 제157조⑨(구 ⑫, 2016.4.1.~)"})
    if P.get("확인 필요"):
        판단.append({"항목": "확인 필요", "결론": P["확인 필요"], "근거": P["근거"]})
    판단.append({"항목": "기준일·시가", "결론": R["판정 기준일"] + ". 시가총액은 " + (R["시가총액 기준"]["상장"] if std in ("코스피", "코스닥", "코넥스") else R["시가총액 기준"]["비상장"]), "근거": "소득세법 시행령 제157조"})
    out = {"결과": {"판정": 판정, "이유": 이유, "기준_지분율": thr_r, "기준_시가총액": thr_m, "합산_방식": mode, "시장": std},
           "계산": {"본인_지분율": own_r, "본인_시가총액": own_m, "특수관계인_지분율": rel_r, "특수관계인_시가총액": rel_m, "합산_지분율": comb_r, "합산_시가총액": comb_m, "최대주주군": is_max_group},
           "근거": P["근거"], "판단": 판단}
    if 해석:
        out["입력 해석"] = 해석
    return out


# ── 세율·산출세액 ────────────────────────────────────────────────────────────

def _bracket_tax(base: int, brackets: list) -> tuple[int, str]:
    """[[한도, 세율], [None, 세율]] 누진. 한도 이하는 첫 세율, 초과분은 둘째."""
    cap, r1 = brackets[0]; _, r2 = brackets[1]
    if cap is None or base <= cap:
        return int(base * r1), f"{base:,} × {r1 * 100:g}%"
    t = int(cap * r1 + (base - cap) * r2)
    return t, f"{int(cap * r1):,} + ({base:,} − {cap:,}) × {r2 * 100:g}%"


def _end_of_month(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def _add_months(d: date, n: int) -> date:
    y, m = d.year, d.month + n
    while m > 12:
        y, m = y + 1, m - 12
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def prelim_deadline(td: date, unit: str) -> date:
    if unit == "분기":
        end_m = ((td.month - 1) // 3 + 1) * 3
    else:
        end_m = 6 if td.month <= 6 else 12
    period_end = _end_of_month(date(td.year, end_m, 1))
    return _end_of_month(_add_months(period_end, 2))


def stock_gains_tax(transfer_date: str, market: str, major_shareholder: bool | None = None, sme: bool | None = None, mid_sized: bool = False,
                    otc_trade: bool = False, transfer_price=None, acquisition_price=None, expenses: int = 0, gain=None,
                    acquisition_date: str = "", prior_basic_deduction: int = 0) -> dict[str, Any]:
    R = _rules()
    td = _d(transfer_date)
    해석: list[str] = []
    std, note = normalize_market(market)
    if std is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"market='{market}'은(는) 알 수 없는 시장"], "허용값": list(_MARKETS)}
    if note:
        해석.append(note)
    try:
        RT = _period(R["세율"], td); PR = _period(R["예정신고"], td); SM = _period(R["중소기업 판정"], td)
    except ValueError as e:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [str(e)]}
    판단: list[dict] = []
    # 1. 과세 대상
    if std == "국외":
        if RT["국외"] is None:
            return {"error": "지원하지 않음 — 2019.12.31. 이전 양도 국외주식(소득세법 제118조의2 국외자산 양도소득, 별도 기본공제·세율 제118조의5)", "근거": RT["근거"]}
        판단.append({"항목": "과세 대상", "결론": "국외주식 — 과세(대주주 판정 없음, 중소기업 여부로 세율)", "근거": "소득세법 제94조①3호다목(2020.1.1.~)"})
    elif std in ("코스피", "코스닥", "코넥스"):
        if major_shareholder is None and not otc_trade:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["상장주식은 대주주 양도 또는 장외 양도만 과세 — major_shareholder(대주주 여부, stock_major_shareholder로 판정) 또는 otc_trade(장외 양도)를 주세요"],
                    "필요 입력": {"major_shareholder": "bool", "otc_trade": "bool"}}
        if not major_shareholder and not otc_trade:
            return {"결과": {"과세대상": False, "산출세액": 0, "이유": "대주주가 아닌 자가 증권시장에서 양도한 상장주식 — 양도소득세 과세 대상 아님(증권거래세만)"},
                    "근거": "소득세법 제94조①3호가목", "판단": [{"항목": "과세 대상", "결론": "과세 대상 아님", "근거": R["과세대상"]["상장"]}]}
        판단.append({"항목": "과세 대상", "결론": ("대주주 양도" if major_shareholder else "장외 양도") + " — 과세", "근거": "소득세법 제94조①3호가목"})
    else:  # 비상장·K-OTC
        if std == "K-OTC" and not major_shareholder and (sme or mid_sized) and td >= date(2018, 1, 1):
            return {"결과": {"과세대상": False, "산출세액": 0, "이유": "K-OTC(금융투자협회 장외시장)에서 대주주 아닌 자가 양도한 중소·중견기업 주식 — 과세 제외"},
                    "근거": "소득세법 제94조①3호나목 단서(2018.1.1.~)", "판단": [{"항목": "과세 대상", "결론": "과세 제외", "근거": R["과세대상"]["비상장"]}]}
        판단.append({"항목": "과세 대상", "결론": "비상장주식 — 과세", "근거": "소득세법 제94조①3호나목"})
        if major_shareholder is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["비상장주식 세율은 대주주 여부로 갈림 — major_shareholder를 주세요(stock_major_shareholder로 판정)"], "필요 입력": {"major_shareholder": "bool"}}
    if std != "국외" and sme is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"sme(중소기업 여부)가 필요 — 판정 기준: {SM['기준']}"], "필요 입력": {"sme": "bool"}}
    # 2. 양도차익
    if gain is None:
        if transfer_price is None or acquisition_price is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["gain(양도차익) 또는 transfer_price·acquisition_price(필요경비는 expenses)를 주세요"]}
        gain_v = int(transfer_price) - int(acquisition_price) - int(expenses or 0)
        식 = f"{int(transfer_price):,} − {int(acquisition_price):,} − {int(expenses or 0):,}"
    else:
        gain_v = int(gain); 식 = f"{gain_v:,}(입력)"
    if gain_v <= 0:
        판단.append({"항목": "양도차손", "결론": f"양도차익 {gain_v:,}원 ≤ 0 — 세액 없음. 같은 해 다른 주식등 양도소득과 통산(제102조②)", "근거": "소득세법 제102조"})
        return {"결과": {"과세대상": True, "양도차익": gain_v, "양도소득금액": gain_v, "기본공제": 0, "과세표준": 0, "산출세액": 0, "지방소득세": 0}, "근거": RT["근거"], "판단": 판단, **({"입력 해석": 해석} if 해석 else {})}
    공제 = min(max(0, R["기본공제"]["금액"] - int(prior_basic_deduction or 0)), gain_v)
    base = gain_v - 공제
    # 3. 세율 후보
    후보: list[tuple[str, int, str, str]] = []  # (구분, 세액, 산식, 근거)
    if std == "국외":
        r = RT["국외"]["중소"] if sme else RT["국외"]["그 밖"]
        후보.append((f"국외주식 {'중소기업' if sme else '그 밖'} {r * 100:g}%", int(base * r), f"{base:,} × {r * 100:g}%", "소득세법 제104조①12호"))
    elif major_shareholder:
        under1y = False
        if not sme:
            if not acquisition_date:
                return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["대주주·중소기업 아닌 법인 주식은 1년 미만 보유 여부로 세율이 갈림 — acquisition_date(취득일)를 주세요"], "필요 입력": {"acquisition_date": "YYYY-MM-DD"}}
            ad = _d(acquisition_date)
            one_year = ad.replace(year=ad.year + 1) if not (ad.month == 2 and ad.day == 29) else ad.replace(year=ad.year + 1, day=28)
            under1y = td < one_year
            판단.append({"항목": "보유기간", "결론": f"취득일 {acquisition_date} → 양도일 {transfer_date}: " + ("1년 미만" if under1y else "1년 이상"), "근거": "소득세법 제104조②"})
        br = RT["대주주_중소"] if sme else RT["대주주_비중소"]
        t, s = _bracket_tax(base, br)
        후보.append((f"대주주 {'중소기업' if sme else '그 밖'} " + (f"{br[0][1] * 100:g}%" if br[0][1] == br[1][1] else f"{br[0][1] * 100:g}%·3억 초과 {br[1][1] * 100:g}%"), t, s, "소득세법 제104조①11호가목"))
        if under1y:
            r = RT["대주주_비중소_1년미만"]
            후보.append((f"대주주 1년 미만 보유·중소기업 아님 {r * 100:g}%", int(base * r), f"{base:,} × {r * 100:g}%", "소득세법 제104조①11호가목1)"))
    else:
        r = RT["소액주주_중소"] if sme else RT["소액주주_비중소"]
        후보.append((f"대주주 아닌 자 {'중소기업' if sme else '그 밖'} {r * 100:g}%", int(base * r), f"{base:,} × {r * 100:g}%", "소득세법 제104조①11호나목"))
    적용 = max(후보, key=lambda x: x[1])
    if len(후보) > 1:
        판단.append({"항목": "세율 경합", "결론": "둘 이상 세율에 해당 — 산출세액이 큰 " + 적용[0], "근거": R["세율 경합"]})
    판단.append({"항목": "중소기업 판정 기준", "결론": SM["기준"], "근거": "소득세법 시행령 제157조의2"})
    # 4. 예정신고
    if std == "국외" and td >= date(2020, 1, 1):
        예정 = {"기한": None, "설명": "국외주식은 예정신고 대상 아님 — 다음 해 5월 확정신고", "근거": "소득세법 제105조①2호 괄호(2020.1.1.~)"}
    else:
        dl = prelim_deadline(td, PR["단위"])
        예정 = {"기한": dl.isoformat(), "설명": f"양도일이 속하는 {PR['단위']} 말일부터 2개월", "근거": PR["근거"]}
    out = {"결과": {"과세대상": True, "양도차익": gain_v, "양도소득금액": gain_v, "기본공제": 공제, "과세표준": base, "적용세율": 적용[0], "산출세액": 적용[1],
                   "지방소득세": 적용[1] // 10, "예정신고기한": 예정["기한"]},
           "계산": {"양도차익 산식": 식, "기본공제 산식": f"min(2,500,000 − 기공제 {int(prior_basic_deduction or 0):,}, 양도차익) = {공제:,}", "세율 후보": [{"구분": c, "세액": t, "산식": s, "근거": b} for c, t, s, b in 후보],
                   "예정신고": 예정, "귀속연도": td.year},
           "근거": f"{RT['근거']}; 기본공제 {R['기본공제']['근거']}", "판단": 판단,
           "산식": "양도차익 = 양도가액 − 취득가액 − 필요경비(장기보유특별공제 없음) → 과세표준 = 양도차익 − 기본공제(주식등 그룹 연 250만원) → 세율 후보 중 큰 세액(제104조① 후단) → 지방소득세 10%"}
    if 해석:
        out["입력 해석"] = 해석
    return out
