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
                      post_acquisition_ratio=None, total_shares=None, own_shares=None, holders=None, price=None,
                      lent_shares: int = 0, pef_shares: int = 0) -> dict[str, Any]:
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
    listed = std in ("코스피", "코스닥", "코넥스")
    명부 = None
    if total_shares is not None or own_shares is not None or holders:
        if any(v is not None for v in (own_ratio, own_mcap, related_ratio, related_mcap)):   # 리뷰 반영: 명부와 직접 입력이 섞이면 조용히 덮어쓰지 않음
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["주주 명부(total_shares·own_shares·holders)와 직접 입력(own_ratio·own_mcap·related_ratio·related_mcap)을 함께 주지 마세요 — 명부를 주면 지분율·시가총액은 도구가 계산합니다. 둘 중 하나만"]}
        if own_shares is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["own_shares(직전 사업연도 종료일 현재 본인 보유 주식 수)가 필요"]}
        명부 = holdings_to_inputs(P, listed, td, is_max_group, int(total_shares or 0), int(own_shares), holders, price, int(lent_shares or 0), int(pef_shares or 0))
        if "error" in 명부:
            return 명부
        own_ratio, related_ratio, own_mcap, related_mcap = 명부["own_ratio"], 명부["related_ratio"], 명부["own_mcap"], 명부["related_mcap"]
        해석.append("지분율·시가총액을 주주 명부(total_shares·own_shares·holders·price)에서 계산")
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
    comb_r = ((own_r if own_r is not None else 0.0) + (rel_r if rel_r is not None else 0.0)) if (own_r is not None or rel_r is not None) else None
    comb_m = ((own_m if own_m is not None else 0.0) + (rel_m if rel_m is not None else 0.0)) if (own_m is not None or rel_m is not None) else None
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
    elif 명부:   # self_unless_max + 명부: 합산 대상은 주주별 판정(scope_decision)에서 이미 걸러짐
        판단.append({"항목": "합산 방식", "결론": P["합산 설명"], "근거": P["근거"]})
        if own_hit:
            판정, 이유 = "대주주", "본인 단독 기준 충족: " + ", ".join(own_hit)
        elif comb_hit:
            판정, 이유 = "대주주", "합산 대상 주주(주주별 참조)와 합해 기준 충족: " + ", ".join(comb_hit)
        else:
            판정, 이유 = "대주주 아님", f"본인 {_pct(own_r) if own_r is not None else '-'} + 합산 대상 {_pct(rel_r or 0)} = {_pct(comb_r) if comb_r is not None else '-'} — 기준 미달" + ("(최대주주군이면 합산될 주주는 아래 '확인 필요' 참조)" if 명부["조건부"] else "")
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
    if 명부:
        판단 = 명부["판단"] + 판단
        if 명부["조건부"] and 판정 != "대주주":
            cr = (comb_r if comb_r is not None else 0.0) + 명부["cond_ratio"]; cm = (comb_m + (명부["cond_mcap"] if 명부["cond_mcap"] is not None else 0.0)) if comb_m is not None else None
            if meets(cr, cm):
                판정, 이유 = "확인 필요", f"최대주주군이면 합산되는 주주({'·'.join(명부['조건부'])})까지 합하면 기준 충족(지분율 {_pct(cr)}) — 주주 1인등의 지분 합계가 그 법인에서 최대인지(is_max_group) 확인 필요"
    if 판정 != "대주주" and post_acquisition_ratio is not None:
        pr, n3 = _ratio(post_acquisition_ratio)
        if n3:
            해석.append(n3.replace("지분율", "취득 후 지분율"))
        if pr >= thr_r:
            판정, 이유 = "대주주", f"직전 사업연도 종료일에는 미달이었으나 그 뒤 주식 취득으로 지분율 {_pct(pr)} ≥ {_pct(thr_r)} — 취득일 이후 양도분은 대주주(시가총액 기준은 사후 취득에 적용되지 않음)"
            판단.append({"항목": "사후 취득", "결론": 이유, "근거": "소득세법 시행령 제157조⑨(구 ⑫, 2016.4.1.~) — 지분율 기준만"})
        else:
            판단.append({"항목": "사후 취득", "결론": f"취득 후 지분율 {_pct(pr)}도 {_pct(thr_r)} 미달 — 사후 취득으로 대주주가 되지 않음(시가총액 기준은 사후 취득에 적용되지 않음)", "근거": "소득세법 시행령 제157조⑨"})
    if P.get("확인 필요"):
        판단.append({"항목": "확인 필요", "결론": P["확인 필요"], "근거": P["근거"]})
    판단.append({"항목": "기준일·시가", "결론": R["판정 기준일"] + ". 시가총액은 " + (R["시가총액 기준"]["상장"] if std in ("코스피", "코스닥", "코넥스") else R["시가총액 기준"]["비상장"]), "근거": "소득세법 시행령 제157조"})
    out = {"결과": {"판정": 판정, "이유": 이유, "기준_지분율": thr_r, "기준_시가총액": thr_m, "합산_방식": mode, "시장": std},
           "계산": {"본인_지분율": own_r, "본인_시가총액": own_m, "특수관계인_지분율": rel_r, "특수관계인_시가총액": rel_m, "합산_지분율": comb_r, "합산_시가총액": comb_m, "최대주주군": is_max_group},
           "근거": P["근거"], "판단": 판단}
    if 명부:
        out["주주별"] = 명부["주주별"]
    if 해석:
        out["입력 해석"] = 해석
    return out



# ── 주주 명부(관계) → 합산 범위 ───────────────────────────────────────────────
import re as _re

_REL_TABLE: list[tuple[tuple[str, ...], str, int, bool]] = [   # (표현들, 종류, 촌수, 직계 여부)
    (("배우자", "남편", "아내", "처", "부인", "와이프", "사실혼"), "배우자", 0, False),
    (("직계존속", "직계비속", "부모", "부모님", "아버지", "어머니", "아빠", "엄마", "부친", "모친", "자녀", "자식", "아들", "딸", "친생자", "양자", "양녀"), "혈족", 1, True),
    (("조부모", "할아버지", "할머니", "외할아버지", "외할머니", "조부", "조모", "손자", "손녀", "손자녀", "외손"), "혈족", 2, True),
    (("증조", "증손"), "혈족", 3, True),
    (("형제", "자매", "형제자매", "형", "누나", "오빠", "언니", "동생", "남매"), "혈족", 2, False),
    (("삼촌", "고모", "이모", "외삼촌", "큰아버지", "작은아버지", "백부", "숙부", "조카", "질녀"), "혈족", 3, False),
    (("사촌", "종형제", "종자매", "고종", "이종", "외사촌"), "혈족", 4, False),
    (("오촌", "당숙", "당고모", "당이모"), "혈족", 5, False),
    (("육촌", "재종"), "혈족", 6, False),
    (("장인", "장모", "시부모", "시아버지", "시어머니", "사위", "며느리", "계부", "계모", "의붓"), "인척", 1, False),
    (("처남", "처형", "처제", "시동생", "시누이", "시아주버니", "매형", "매제", "매부", "형수", "제수", "형부", "제부", "올케", "동서", "처남댁"), "인척", 2, False),
    (("처조카", "조카사위", "조카며느리", "시조카", "처삼촌", "처고모", "처이모", "시삼촌", "시고모"), "인척", 3, False),
    (("경영지배", "지배 법인", "지배법인", "지배하는 법인", "계열", "관계회사", "관계 회사", "특수관계법인", "법인"), "경영지배", 0, False),
    (("본인", "나"), "본인", 0, False),
]


def parse_relation(text: str) -> tuple[str, int, bool, str] | None:
    """관계 표현 → (종류, 촌수, 직계, 해석문). '혈족 4촌'·'3촌 인척' 같은 명시도 받는다."""
    raw = (text or "").strip()
    low = raw.replace(" ", "")
    m = _re.search(r"(혈족|인척)(\d+)촌|(\d+)촌(혈족|인척)", low)
    if m:
        kind = m.group(1) or m.group(4); chon = int(m.group(2) or m.group(3))
        return kind, chon, False, f"'{raw}' → {kind} {chon}촌"
    best = None   # 가장 긴 표현이 이김('처남'은 '처'(배우자)가 아니라 '처남'(인척 2촌), '시어머니'는 '어머니'가 아님)
    for keys, kind, chon, lineal in _REL_TABLE:
        for k in keys:
            if k in low and (best is None or len(k) > len(best[0])):
                best = (k, kind, chon, lineal)
    if best:
        _, kind, chon, lineal = best
        return kind, chon, lineal, (f"'{raw}' → {kind}" + (f" {chon}촌" if kind in ("혈족", "인척") else "") + (" (직계)" if lineal else ""))
    return None


def _kin_limits(td: date) -> tuple[int, int]:
    """친족 범위 — 2023.1.1. 이후 양도분은 4촌 혈족·3촌 인척(영 제157조 2022.12.31. 개정이 직접 열거, 국기령은 2023.3.1.), 그 전 6촌·4촌."""
    return (4, 3) if td >= date(2023, 1, 1) else (6, 4)


def scope_decision(mode: str, listed: bool, is_max: bool | None, kind: str, chon: int, lineal: bool, td: date) -> tuple[str, str]:
    """한 주주를 합산할지 → ('합산'|'제외'|'최대주주군이면 합산', 이유)."""
    blood, inlaw = _kin_limits(td)
    if kind == "본인":
        return "제외", "본인 보유분은 본인 몫에 포함"
    in_kin = kind == "배우자" or (kind == "혈족" and chon <= blood) or (kind == "인척" and chon <= inlaw)
    kin_txt = f"{kind}" + (f" {chon}촌" if kind in ("혈족", "인척") else "")
    if kind == "경영지배":
        return "합산", "경영지배 관계 법인(국세기본법 시행령 제1조의2③1호, 사용자 진술) — 모든 구간 합산"
    if mode == "all":
        return ("합산", f"{kin_txt} — 친족 범위({blood}촌 혈족·{inlaw}촌 인척·배우자) 안, 2016.3.31. 이전은 전부 합산") if in_kin else ("제외", f"{kin_txt} — 친족 범위 밖")
    narrow = kind == "배우자" or (kind == "혈족" and lineal)
    if mode == "max_group_split":
        if is_max is True:
            return ("합산", f"{kin_txt} — 최대주주군, 친족 범위({blood}촌 혈족·{inlaw}촌 인척·배우자) 안") if in_kin else ("제외", f"{kin_txt} — 친족 범위 밖")
        if is_max is False:
            return ("합산", f"{kin_txt} — 최대주주군 아님, 직계존비속·배우자만 합산") if narrow else ("제외", f"{kin_txt} — 최대주주군이 아니면 직계존비속·배우자만 합산")
        if narrow:
            return "합산", f"{kin_txt} — 최대주주군 여부와 무관하게 합산(직계존비속·배우자)"
        return ("최대주주군이면 합산", f"{kin_txt} — 최대주주군이면 합산, 아니면 제외") if in_kin else ("제외", f"{kin_txt} — 친족 범위 밖")
    # self_unless_max (2023.1.1.~)
    if listed:
        if not in_kin:
            return "제외", f"{kin_txt} — 친족 범위({blood}촌 혈족·{inlaw}촌 인척·배우자) 밖"
        if is_max is True:
            return "합산", f"{kin_txt} — 최대주주군이라 기타주주로 합산"
        if is_max is False:
            return "제외", f"{kin_txt} — 2023.1.1.~ 상장법인은 최대주주군이 아니면 본인 단독 판정"
        return "최대주주군이면 합산", f"{kin_txt} — 최대주주군이면 합산, 아니면 본인 단독(2023.1.1.~)"
    if is_max is True:
        return ("합산", f"{kin_txt} — 최대주주군, 친족 범위 안") if in_kin else ("제외", f"{kin_txt} — 친족 범위 밖")
    if is_max is False:
        return ("합산", f"{kin_txt} — 비상장·최대주주군 아님: 직계존비속·배우자 합산(영 제157조③2호)") if narrow else ("제외", f"{kin_txt} — 비상장·최대주주군 아니면 직계존비속·배우자만")
    if narrow:
        return "합산", f"{kin_txt} — 비상장은 최대주주군 여부와 무관하게 직계존비속·배우자 합산"
    return ("최대주주군이면 합산", f"{kin_txt} — 최대주주군이면 합산, 아니면 제외") if in_kin else ("제외", f"{kin_txt} — 친족 범위 밖")


def holdings_to_inputs(P: dict, listed: bool, td: date, is_max: bool | None, total_shares: int, own_shares: int, holders: list | None,
                       price, lent_shares: int = 0, pef_shares: int = 0) -> dict[str, Any]:
    """주주 명부 → 본인·합산 지분율·시가총액과 주주별 판단."""
    if not total_shares or total_shares <= 0:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["total_shares(해당 법인 주식등 합계 — 보통주·우선주·자기주식 포함, 신주인수권증권·출자지분 포함)가 필요"]}
    own_total = int(own_shares or 0) + int(lent_shares or 0) + int(pef_shares or 0)
    판단 = [{"항목": "본인 보유", "결론": f"본인 {int(own_shares or 0):,}주" + (f" + 대여 중 {int(lent_shares):,}주(영 제157조⑦ 대여자 소유로 봄)" if lent_shares else "") + (f" + 사모집합투자기구 간접 보유 안분 {int(pef_shares):,}주(영 제157조⑧)" if pef_shares else "") + f" = {own_total:,}주 / 합계 {int(total_shares):,}주 = {own_total / total_shares * 100:.4f}%", "근거": "소득세법 시행령 제157조①·⑦·⑧, 법 제88조2호(주식등: 주식·출자지분·신주인수권·증권예탁증권)"}]
    rel_shares = 0; cond_shares = 0; 주주별 = []; 조건부 = []
    for h in holders or []:
        name = h.get("이름") or h.get("name") or ""
        rel = h.get("관계") or h.get("relation") or ""
        sh = int(h.get("주식수") or h.get("shares") or 0)
        pr = parse_relation(rel)
        if pr is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"holders '{name or rel}'의 관계 '{rel}'을(를) 알 수 없음"],
                    "허용값": "배우자·부모·자녀·조부모·손자녀·형제자매·삼촌·조카·사촌·장인·장모·사위·며느리·처남·시동생 등 평소 말, 또는 '혈족 4촌'·'인척 3촌', 경영지배 관계 법인은 '경영지배' 또는 '법인'"}
        kind, chon, lineal, note = pr
        dec, why = scope_decision(P["합산"], listed, is_max, kind, chon, lineal, td)
        row = {"주주": name or rel, "관계": note, "주식수": sh, "지분율": round(sh / total_shares, 6), "판정": dec, "이유": why}
        주주별.append(row)
        if dec == "합산":
            rel_shares += sh
        elif dec == "최대주주군이면 합산":
            cond_shares += sh; 조건부.append(row["주주"])
    out = {"own_ratio": own_total / total_shares, "related_ratio": rel_shares / total_shares, "cond_ratio": cond_shares / total_shares,
           "own_mcap": None, "related_mcap": None, "cond_mcap": None, "판단": 판단, "주주별": 주주별, "조건부": 조건부}
    if price is not None:
        p = float(price)
        out.update({"own_mcap": own_total * p, "related_mcap": rel_shares * p, "cond_mcap": cond_shares * p})
        out["판단"].append({"항목": "시가총액", "결론": f"1주당 {p:,.0f}원 × 보유 주식 수 — " + ("직전 사업연도 종료일 최종시세가액(없으면 직전거래일)" if listed else "소득세법 시행령 제165조④ 기준시가(stock_basis_income_tax로 산정 — 상증법 평가와 다른 산식, 할증 없음)"), "근거": "소득세법 시행령 제157조④(구 ⑥·⑦)"})
    else:
        out["판단"].append({"항목": "시가총액", "결론": "price(1주당 가액)를 주지 않아 시가총액 기준은 판정하지 않음 — 지분율 기준만", "근거": "소득세법 시행령 제157조④"})
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
    if sme is None:   # 국외주식도 중소기업 여부로 세율이 갈림(제104조①12호) — 기본값을 두지 않고 묻는다(리뷰 반영)
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"sme(중소기업 여부)가 필요 — 판정 기준: {SM['기준']}" + (" (국외주식도 중소기업 10%·그 밖 20%)" if std == "국외" else "")], "필요 입력": {"sme": "bool"}}
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
