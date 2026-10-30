"""비상장주식 평가 — (A) 상증법 보충적 평가(법 제63조①1호나목, 영 제54조~제56조·제53조 할증) (B) 소득세법 기준시가(법 제99조①4호, 영 제165조④).
구간별 값은 조문 원문 대조(2026-10-30, law.go.kr 조문 연혁). 작성 Claude."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _d(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _won(v) -> str:
    return f"{v:,.0f}원"



# ── 재무제표 → 순손익액·순자산가액 (영 제56조④, 제55조·규칙 제17조의2) ──────────────────

_INC_ADD = {   # 가산(각 사업연도소득에 더함): 키워드 → (표준명, 근거, 적용 시작일)
    "이월익금": ("이월익금", "법인세법 제18조4호 — 영 제56조④1호가목", None),
    "수입배당금": ("수입배당금 익금불산입액", "법인세법 제18조의2·제18조의3(2023~ 제18조의4) — 영 제56조④1호", None),
    "기부금이월": ("기부금 한도초과 이월액 손금산입", "법인세법 제24조④(→⑤) — 영 제56조④1호", None),
    "기부금 이월": ("기부금 한도초과 이월액 손금산입", "법인세법 제24조④(→⑤) — 영 제56조④1호", None),
    "외화평가이익": ("화폐성외화자산등 평가이익(미평가분)", "영 제56조④1호(2019.2.12.~, 부칙 제10조 시행 이후 상속·증여분)", "2019-02-12"),
    "외화 평가이익": ("화폐성외화자산등 평가이익(미평가분)", "영 제56조④1호(2019.2.12.~)", "2019-02-12"),
    "27조의2 손금산입": ("업무용승용차 관련비용 손금산입액(제27조의2③④)", "영 제56조④1호(2020.2.11.~)", "2020-02-11"),
    "기타가산": ("기획재정부령으로 정하는 가산액", "영 제56조④1호 — 규칙 제17조의3", None),
}
_INC_SUB = {   # 차감
    "법인세": ("법인세액(외국납부세액 포함)", "영 제56조④2호가목", None),
    "감면세액": ("법인세 감면세액", "영 제56조④2호가목", None),
    "농특세": ("농어촌특별세", "영 제56조④2호가목", None),
    "지방소득세": ("법인지방소득세", "영 제56조④2호가목", None),
    "벌과금": ("벌금·과료·과태료·가산금 손금불산입(제21조3·4호)", "영 제56조④2호나목", None),
    "업무무관": ("업무무관 비용 손금불산입(제27조)", "영 제56조④2호나목", None),
    "업무용승용차 한도초과": ("업무용승용차 관련비용 손금불산입(제27조의2)", "영 제56조④2호다목(2020.2.11.~)", "2020-02-11"),
    "징수불이행": ("징수불이행 세액", "영 제56조④2호나목", None),
    "기부금 한도초과": ("기부금 한도초과액 손금불산입(제24조)", "영 제56조④2호다목", None),
    "기부금한도초과": ("기부금 한도초과액 손금불산입(제24조)", "영 제56조④2호다목", None),
    "접대비 한도초과": ("기업업무추진비 한도초과액(제25조)", "영 제56조④2호다목", None),
    "기업업무추진비 한도초과": ("기업업무추진비 한도초과액(제25조)", "영 제56조④2호다목", None),
    "과다경비": ("과다경비 등 손금불산입(제26조)", "영 제56조④2호다목", None),
    "지급이자 손금불산입": ("업무무관자산 등 지급이자 손금불산입(제28조)", "영 제56조④2호다목", None),
    "감가상각 시인부족": ("감가상각 시인부족액 중 상각부인액 추인액(시인부족액−상각부인액 손금산입분)", "영 제56조④2호라목", None),
    "외화평가손실": ("화폐성외화자산등 평가손실", "영 제56조④2호마목(2019.2.12.~)", "2019-02-12"),
    "외화 평가손실": ("화폐성외화자산등 평가손실", "영 제56조④2호마목(2019.2.12.~)", "2019-02-12"),
    "기타차감": ("기획재정부령으로 정하는 차감액", "영 제56조④2호 — 규칙 제17조의3", None),
}


def _match(table: dict, name: str):
    low = name.replace(" ", "")
    best = None
    for k, v in table.items():
        kk = k.replace(" ", "")
        if kk in low and (best is None or len(kk) > len(best[0])):
            best = (kk, v)
    return best[1] if best else None


def net_income_from_statement(item: dict, vd: date) -> tuple[float | None, list[dict], list[str]]:
    """{각사업연도소득, 가산:{항목:금액}, 차감:{항목:금액}} → 순손익액. (값, 계산 줄, 문제)"""
    base = item.get("각사업연도소득")
    if base is None:
        return None, [], []
    lines = [{"구분": "각 사업연도 소득금액", "금액": float(base), "근거": "법인세법 제14조 — 영 제56조④ 본문"}]
    total = float(base); problems: list[str] = []
    for key, table, sign in (("가산", _INC_ADD, 1), ("차감", _INC_SUB, -1)):
        for name, amt in (item.get(key) or {}).items():
            m = _match(table, str(name))
            if m is None:
                problems.append(f"{key} 항목 '{name}'을(를) 알 수 없음 — 허용: {', '.join(table)}")
                continue
            std, basis, start = m
            if start and vd < _d(start):
                problems.append(f"{key} '{name}'({std})은 {start} 이후 평가분부터 — 평가기준일 {vd.isoformat()}에는 반영하지 않음")
                continue
            total += sign * float(amt)
            lines.append({"구분": ("+ " if sign > 0 else "− ") + std, "금액": float(amt), "근거": basis})
    lines.append({"구분": "= 순손익액", "금액": total, "근거": "영 제56조④"})
    return total, lines, problems


_NA_ADD_ASSET = {"지급받을 권리": ("평가기준일 현재 지급받을 권리가 확정된 가액", "규칙 제17조의2 1호"), "미수": ("평가기준일 현재 지급받을 권리가 확정된 가액", "규칙 제17조의2 1호"), "확정 채권": ("평가기준일 현재 지급받을 권리가 확정된 가액", "규칙 제17조의2 1호")}
_NA_SUB_ASSET = {"선급비용": ("선급비용(비용 확정분)", "규칙 제17조의2 2호"), "영업권": ("무형자산(영업권 — 별도 평가해 합산, 영 제55조③)", "규칙 제17조의2 2호·법인세령 제24조①2호바목"), "무형자산": ("무형자산(영업권)", "규칙 제17조의2 2호"), "이연법인세자산": ("이연법인세자산(확인 필요 — 조문 명시 없음, 실무상 제외)", "확인 필요")}
_NA_ADD_LIAB = {"미지급 법인세": ("평가기준일까지 발생한 소득에 대한 법인세·감면세액·농특세·지방소득세", "규칙 제17조의2 3호가목"), "법인세": ("평가기준일까지 발생한 소득에 대한 법인세 등", "규칙 제17조의2 3호가목"), "확정 배당": ("이익처분으로 확정된 배당금·상여금 등", "규칙 제17조의2 3호나목"), "배당금": ("이익처분으로 확정된 배당금", "규칙 제17조의2 3호나목"), "상여금": ("이익처분으로 확정된 상여금", "규칙 제17조의2 3호나목"), "퇴직급여추계액": ("전원 퇴직 시 퇴직급여 추계액", "규칙 제17조의2 3호다목"), "퇴직금 추계": ("전원 퇴직 시 퇴직급여 추계액", "규칙 제17조의2 3호다목")}
_NA_SUB_LIAB = {"충당금": ("제충당금(비용으로 확정된 것 제외)", "규칙 제17조의2 4호"), "준비금": ("조특법·기타 법률 제준비금(보험 책임·비상위험·해약환급금준비금 제외)", "규칙 제17조의2 4호"), "이연법인세부채": ("이연법인세부채(확인 필요 — 조문 명시 없음)", "확인 필요")}


def net_asset_from_statement(d: dict) -> tuple[float, list[dict], list[str]]:
    """{자산_장부가액, 자산_평가차액?, 부채_장부가액, 자산_가산:{}, 자산_차감:{}, 부채_가산:{}, 부채_차감:{}} → 순자산가액."""
    problems: list[str] = []
    assets = float(d.get("자산_장부가액") or 0); liab = float(d.get("부채_장부가액") or 0)
    lines = [{"구분": "자산 장부가액", "금액": assets, "근거": "영 제55조①"}]
    if d.get("자산_평가차액") is not None:
        diff = float(d["자산_평가차액"]); assets += diff
        lines.append({"구분": "+ 자산 평가차액(상증법 평가액 − 장부가액; 평가액이 장부가액보다 낮으면 장부가액 유지 — 정당한 사유 예외)", "금액": diff, "근거": "영 제55조① 후단, 법 제60조~제66조"})
    for key, table, sign, label in (("자산_가산", _NA_ADD_ASSET, 1, "자산"), ("자산_차감", _NA_SUB_ASSET, -1, "자산"), ("부채_가산", _NA_ADD_LIAB, 1, "부채"), ("부채_차감", _NA_SUB_LIAB, -1, "부채")):
        for name, amt in (d.get(key) or {}).items():
            m = _match(table, str(name))
            if m is None:
                problems.append(f"{key} 항목 '{name}'을(를) 알 수 없음 — 허용: {', '.join(table)}")
                continue
            std, basis = m
            if label == "자산":
                assets += sign * float(amt)
            else:
                liab += sign * float(amt)
            lines.append({"구분": f"{label} {'+' if sign > 0 else '−'} {std}", "금액": float(amt), "근거": basis})
    lines.append({"구분": "부채 장부가액(가감 후)", "금액": liab, "근거": "영 제55조①, 규칙 제17조의2 3·4호"})
    net = assets - liab
    lines.append({"구분": "= 순자산가액(자산 − 부채)", "금액": net, "근거": "영 제55조①"})
    return net, lines, problems



# ── 증감자 조정(영 제56조⑤·규칙 제17조의3⑤), 추정이익(영 제56조②), 자산별 평가(법 제60조~제66조) ────────

def _months_in_year(fy_start: date, when: date) -> int:
    """사업연도 개시일부터 증감자일까지 월수(1개월 미만은 1개월)."""
    m = (when.year - fy_start.year) * 12 + (when.month - fy_start.month) + (1 if when.day >= fy_start.day else 0)
    return max(1, m)


def apply_capital_changes(items: list[dict], changes: list[dict], rate: float = 0.10) -> tuple[list[dict], list[dict], list[str]]:
    """3년 내 유상증자·감자 → 각 연도 순손익액 가산·차감(영 제56조⑤)과 환산주식수(규칙 제17조의3⑤).
    items: [{사업연도, 순손익액, 주식수(그 연도 말)}] 최근 연도부터. changes: [{일자, 구분:'증자'|'감자', 주식수, 1주당금액}]."""
    out = [dict(it) for it in items]; lines = []; problems = []
    by_year = {int(it.get("사업연도")): it for it in out if it.get("사업연도") is not None}
    for ch in changes or []:
        try:
            when = _d(ch["일자"]); kind = ch.get("구분") or ch.get("kind"); n = int(ch.get("주식수") or ch.get("shares")); amt = float(ch.get("1주당금액") or ch.get("price") or 0)
        except Exception as e:
            problems.append(f"증감자 항목 형식 오류 {ch} — {{일자 YYYY-MM-DD, 구분 증자|감자, 주식수, 1주당금액}}"); continue
        if kind not in ("증자", "감자"):
            problems.append(f"증감자 구분 '{kind}' — 증자|감자"); continue
        sign = 1 if kind == "증자" else -1
        yr = when.year
        total = n * amt
        prev0 = by_year.get(yr - 1) or by_year.get(yr)   # 증자 직전 사업연도 말 주식수 — 다른 연도를 환산하기 전 값으로 고정
        base = int((prev0 or {}).get("주식수") or 0)
        for y, it in by_year.items():
            if y > yr:
                continue
            fy_start = date(y, 1, 1)
            months = _months_in_year(fy_start, when) if y == yr else 12
            adj = sign * total * rate * months / 12
            it["순손익액"] = float(it.get("순손익액") or 0) + adj
            lines.append({"사업연도": y, "구분": f"{kind} {when.isoformat()} {n:,}주 × {amt:,.0f}원", "순손익액 조정": adj,
                          "산식": f"{'+' if sign > 0 else '−'} {total:,.0f} × {rate*100:g}% × {months}/12", "근거": "상증법 시행령 제56조⑤, 시행규칙 제17조의3⑥"})
            if y < yr and it.get("주식수"):
                if base > 0:
                    before = int(it["주식수"]); it["주식수"] = int(round(before * (base + sign * n) / base))
                    lines.append({"사업연도": y, "구분": "환산주식수", "값": it["주식수"], "산식": f"{before:,} × ({base:,} {'+' if sign > 0 else '−'} {n:,}) ÷ {base:,}", "근거": "상증법 시행규칙 제17조의3⑤"})
    return out, lines, problems


_EST_REASONS = {
    "자산수증이익": "자산수증이익·채무면제이익·보험차익·재해손실 합계의 3년 가중평균이 (세전손익−동 금액) 가중평균의 50% 초과(규칙 제17조의3①2호)",
    "합병": "3년 내 합병·분할·주요 업종 변경(①3호)", "분할": "3년 내 합병·분할·주요 업종 변경(①3호)", "업종 변경": "3년 내 합병·분할·주요 업종 변경(①3호)",
    "합병이익": "법 제38조 합병이익 산정(①4호)", "휴업": "3개 사업연도 중 1년 이상 휴업(①5호)",
    "처분손익": "유가증권·유형자산 처분손익+자산수증이익등 가중평균이 세전손익 가중평균의 50% 초과(①6호)",
    "매출 3년 미만": "주요 업종 정상 매출 발생 기간 3년 미만(①7호)", "고시": "기획재정부장관 고시 사유(①8호)",
}


def estimated_profit_check(est: dict, valuation_date: str, kind: str) -> tuple[float | None, list[dict], list[str]]:
    """추정이익 평가 요건(영 제56조② 1~4호) 판정 → 통과하면 1주당 추정이익 평균가액."""
    vd = _d(valuation_date); 판단 = []; problems = []
    avg = est.get("1주당추정이익평균") or est.get("avg")
    if avg is None:
        return None, [], ["estimated_profit에 1주당추정이익평균(둘 이상 신용평가전문기관·회계법인·세무법인 산출 평균)이 필요"]
    reason = str(est.get("사유") or "")
    m = _match(_EST_REASONS, reason) if reason else None
    if not m:
        return None, [], [f"estimated_profit 사유 '{reason}' — 허용: {', '.join(_EST_REASONS)}"]
    판단.append({"항목": "추정이익 사유(1호)", "결론": m, "근거": "상증법 시행규칙 제17조의3①"})
    due = est.get("신고기한"); filed = est.get("신고일"); calc = est.get("산정기준일"); made = est.get("평가서작성일")
    ok = True
    if due and filed and _d(filed) > _d(due):
        ok = False; 판단.append({"항목": "요건 2호", "결론": f"신고일 {filed}이 신고기한 {due} 뒤 — 요건 미충족", "근거": "영 제56조②2호"})
    else:
        판단.append({"항목": "요건 2호", "결론": "법정신고기한까지 신고" + ("(신고일·신고기한 미입력 — 확인)" if not (due and filed) else ""), "근거": "영 제56조②2호"})
    if due and ((calc and _d(calc) > _d(due)) or (made and _d(made) > _d(due))):
        ok = False; 판단.append({"항목": "요건 3호", "결론": "산정기준일·평가서작성일이 신고기한 뒤 — 요건 미충족", "근거": "영 제56조②3호"})
    else:
        판단.append({"항목": "요건 3호", "결론": "산정기준일·평가서작성일이 신고기한 이내" + ("(미입력 — 확인)" if not (calc and made) else ""), "근거": "영 제56조②3호"})
    if calc and _d(calc).year != vd.year:
        ok = False; 판단.append({"항목": "요건 4호", "결론": f"산정기준일 {calc}과 {kind} 기준일 {valuation_date}이 같은 연도가 아님 — 요건 미충족", "근거": "영 제56조②4호"})
    else:
        판단.append({"항목": "요건 4호", "결론": "산정기준일과 상속개시일·증여일이 같은 연도" + ("(산정기준일 미입력 — 확인)" if not calc else ""), "근거": "영 제56조②4호"})
    if not ok:
        return None, 판단, []
    return float(avg), 판단, []


_ASSET_RULES = {   # 종류 → (우선순위 설명, 근거)
    "토지": ("시가(매매·감정·수용·경매·공매 사례가액, 평가기간 내) → 없으면 개별공시지가(제61조①1호)", "상증법 제60조·제61조①1호"),
    "건물": ("시가 → 없으면 국세청 기준시가·건물기준시가(제61조①2~4호)", "상증법 제60조·제61조①"),
    "주택": ("시가 → 없으면 개별·공동주택가격(제61조①4호)", "상증법 제60조·제61조①4호"),
    "상장주식": ("평가기준일 전후 2개월 종가 평균(제63조①1호가목, stock_price_lookup avg_2m)", "상증법 제63조①1호가목"),
    "비상장주식": ("보충적 평가(제63조①1호나목, unlisted_stock_valuation) — 10% 이하 출자는 취득가액 가능(영 제54조③)", "상증법 제63조①1호나목, 영 제54조③"),
    "예금": ("원본 + 평가기준일까지 미수이자 − 원천징수세액(영 제58조①)", "상증법 시행령 제58조①"),
    "채권": ("원본 + 미수이자(영 제58조①); 국채·공채 등은 제63조①2호", "상증법 제63조①2호, 영 제58조"),
    "매출채권": ("원본 — 회수 불가능분은 제외(영 제58조②)", "상증법 시행령 제58조②"),
    "기타": ("시가 → 없으면 장부가액·보충적 평가", "상증법 제60조③·제65조"),
}


def value_assets(assets: list[dict]) -> tuple[float, list[dict], list[str]]:
    """자산 목록 → 평가차액 합계(평가액 − 장부가액). 각 자산은 {종류, 명칭?, 장부가액, 시가?, 기준시가?, 평가액?}.
    선택: 평가액 > 시가 > 기준시가 > 장부가액. 평가액이 장부가액보다 낮으면 장부가액(영 제55조① 후단, 정당한 사유 있으면 '하한 예외'=true)."""
    total = 0.0; lines = []; problems = []
    for a in assets or []:
        kind = str(a.get("종류") or "기타"); rule = _match(_ASSET_RULES, kind) or _ASSET_RULES["기타"]
        book = float(a.get("장부가액") or 0)
        src = None; val = None
        for key in ("평가액", "시가", "기준시가"):
            if a.get(key) is not None:
                src, val = key, float(a[key]); break
        if val is None:
            src, val = "장부가액", book
        floor_note = ""
        if val < book and not a.get("하한 예외"):
            floor_note = f" → 평가액 {val:,.0f} < 장부가액 {book:,.0f}라 장부가액 적용(정당한 사유가 있으면 '하한 예외': true)"
            val = book
        diff = val - book; total += diff
        lines.append({"자산": a.get("명칭") or kind, "종류": kind, "장부가액": book, "적용가액": val, "근거값": src, "평가차액": diff,
                      "규칙": rule[0] + floor_note, "근거": rule[1] + ", 영 제55조①"})
    return total, lines, problems


# ── (A) 상증법 보충적 평가 ────────────────────────────────────────────────────

def _floor_ratio_inh(vd: date) -> tuple[float | None, str]:
    if vd < date(2017, 4, 1):
        return None, "영 제54조① 2017.3.31.까지 하한 없음"
    if vd < date(2018, 4, 1):
        return 0.70, "영 제54조① 단서(순자산가치 80%)를 대통령령 제27835호 부칙 제7조가 2017.4.1.~2018.3.31. 상속·증여분은 70%로"
    return 0.80, "영 제54조① 단서(2018.4.1.~ 순자산가치의 80%)"


def _net_asset_only_rule(vd: date) -> tuple[list[str], str, bool]:
    """(사유 목록, 근거, 부동산·주식 80% 사유에 '가중평균 < 순자산가치' 한정 여부)"""
    if vd < date(2017, 2, 7):
        return ["청산", "개시3년미만", "휴폐업", "3년연속결손"], "영 제54조④(2015.2.3.본): 청산 진행·사업 계속 곤란, 사업개시 전·개시 후 3년 미만·휴폐업, 직전 3년 연속 결손", False
    if vd < date(2018, 2, 13):
        return ["청산", "개시3년미만", "휴폐업", "3년연속결손", "주식80", "존속3년"], "영 제54조④(2017.2.7.): + 자산 중 주식등 80% 이상, 잔여 존속기한 3년 이내", False
    if vd < date(2026, 2, 27):
        return ["청산", "개시3년미만", "휴폐업", "부동산80", "주식80", "존속3년"], "영 제54조④(2018.2.13., 부칙 제8조 시행 이후 평가분): 3년 연속 결손 사유 삭제, 자산 중 부동산 80% 이상 신설", False
    return ["청산", "개시3년미만", "휴폐업", "부동산80", "주식80", "존속3년"], "영 제54조④(2026.2.27., 부칙 제11조): 부동산·주식 80% 사유는 가중평균이 순자산가치보다 낮은 경우로 한정", True


def _premium(vd: date, is_max: bool, ratio_over_50: bool | None, sme: bool, mid_sized: bool, exclusion: str | None) -> tuple[float, str, list[str]]:
    notes: list[str] = []
    if not is_max:
        return 0.0, "최대주주등이 아님 — 할증 없음(법 제63조③)", notes
    if exclusion:
        return 0.0, f"할증 제외 사유 '{exclusion}'(영 제53조⑧(구 ⑥·⑦) 각 호)", notes
    if vd < date(2020, 1, 1):
        if sme:
            return 0.0, "중소기업 최대주주 — 조세특례제한법 제101조로 2019.12.31.까지 상속·증여분 할증 미적용(법문 10%/15%는 적용되지 않음)", notes
        if ratio_over_50 is None:
            notes.append("최대주주등 지분이 50%(2017~ 의결권 있는 주식 기준)를 초과하는지 몰라 20%로 계산 — 초과하면 30%(ratio_over_50=True)")
            return 0.20, "법 제63조③(2019.12.31.까지): 20%, 50% 초과 보유 시 30%", notes
        return (0.30 if ratio_over_50 else 0.20), "법 제63조③(2019.12.31.까지): 20%, 50% 초과 보유 시 30%", notes
    if sme:
        return 0.0, "중소기업 제외(법 제63조③, 영 제53조⑥·2020.1.1.~)", notes
    if mid_sized and vd >= date(2023, 1, 1):
        return 0.0, "중견기업(직전 3개 사업연도 매출액 평균 5천억 미만) 제외(영 제53조⑦, 2023.1.1.~ 상속·증여분)", notes
    return 0.20, "법 제63조③(2020.1.1.~): 20% 단일", notes


def goodwill_value(avg_income_3y: float, equity: float, rate: float = 0.10, years: int = 5) -> tuple[float, str]:
    """영 제59조②·규칙 제19조①: [3년 순손익 가중평균×50% − 자기자본×10%]를 5년간 10%로 현가 합산."""
    excess = avg_income_3y * 0.5 - equity * rate
    if excess <= 0:
        return 0.0, f"초과이익 {excess:,.0f} ≤ 0 → 영업권 0"
    pv = sum(excess / (1 + rate) ** n for n in range(1, years + 1))
    return pv, f"초과이익 {excess:,.0f} × Σ1/(1.1)^n(n=1..5)={sum(1/(1+rate)**n for n in range(1, years+1)):.4f}"


def unlisted_valuation(valuation_date: str, shares: int, incomes: list | None = None, net_asset=None, equity=None,
                       goodwill=None, real_estate_ratio=None, stock_asset_ratio=None, business_start: str = "", status: str = "",
                       is_max_shareholder: bool = False, ratio_over_50: bool | None = None, sme: bool | None = None, mid_sized: bool = False,
                       premium_exclusion: str | None = None, cap_rate: float = 0.10, capital_changes: list | None = None,
                       estimated_profit: dict | None = None, assets: list | None = None, kind: str = "증여") -> dict[str, Any]:
    vd = _d(valuation_date)
    if shares is None or int(shares) <= 0:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["shares(평가기준일 현재 발행주식총수)가 필요"]}
    shares = int(shares)
    판단: list[dict] = []
    계산_상세: dict = {}
    # 자산별 평가 → 평가차액(net_asset이 항목형일 때 자산_평가차액에 더함)
    if assets:
        diff_sum, asset_lines, a_probs = value_assets(assets)
        if a_probs:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": a_probs}
        계산_상세["자산별 평가"] = asset_lines
        if isinstance(net_asset, dict):
            net_asset = {**net_asset, "자산_평가차액": float(net_asset.get("자산_평가차액") or 0) + diff_sum}
        elif net_asset is not None:
            net_asset = float(net_asset) + diff_sum
    # 순자산가치 — 숫자 또는 재무제표 항목형
    if isinstance(net_asset, dict):
        net_asset, na_lines, na_problems = net_asset_from_statement(net_asset)
        if na_problems:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": na_problems}
        계산_상세["순자산가액 산출"] = na_lines
    if net_asset is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["net_asset(평가기준일 현재 순자산가액, 또는 {자산_장부가액, 자산_평가차액, 부채_장부가액, 자산_가산, 자산_차감, 부채_가산, 부채_차감})이 필요"]}
    na = max(0.0, float(net_asset))
    if float(net_asset) < 0:
        판단.append({"항목": "순자산가액", "결론": "0보다 작아 0으로 봄", "근거": "상증법 시행령 제55조①"})
    # 순손익가치
    inc_items = incomes or []
    if inc_items and len(inc_items) not in (1, 2, 3):
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["incomes는 최근 3개 사업연도 [{사업연도, 순손익액, 주식수?}] 최근 연도부터"]}
    per_share = []
    inc_lines_all = []
    if capital_changes and inc_items:
        prepared = []
        for it in inc_items:
            if it.get("순손익액") is None and it.get("각사업연도소득") is not None:
                n_calc, lines, probs = net_income_from_statement(it, vd)
                if probs:
                    return {"error": "입력 확인 필요 — 계산하지 않음", "문제": probs}
                inc_lines_all.append({"사업연도": it.get("사업연도") or it.get("year"), "산출": lines}); it = {**it, "순손익액": n_calc}
            prepared.append(it)
        inc_items, cc_lines, cc_probs = apply_capital_changes(prepared, capital_changes, cap_rate)
        if cc_probs:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": cc_probs}
        계산_상세["증감자 조정"] = cc_lines
    for it in inc_items:
        if it.get("순손익액") is None and it.get("각사업연도소득") is not None:
            n_calc, lines, probs = net_income_from_statement(it, vd)
            if probs:
                return {"error": "입력 확인 필요 — 계산하지 않음", "문제": probs}
            it = {**it, "순손익액": n_calc}
            inc_lines_all.append({"사업연도": it.get("사업연도") or it.get("year"), "산출": lines})
        n = float(it.get("순손익액") if it.get("순손익액") is not None else it.get("net_income", 0))
        sh = int(it.get("주식수") or it.get("shares") or shares)
        per_share.append((it.get("사업연도") or it.get("year"), n / sh))
    reasons, basis_na, limited = _net_asset_only_rule(vd)
    사유 = None
    if status in ("청산", "휴폐업", "존속3년"):
        사유 = status
    if business_start:
        bs = _d(business_start)
        yrs = (vd - bs).days / 365.25
        if yrs < 3 and "개시3년미만" in reasons:
            사유 = 사유 or "개시3년미만"
            판단.append({"항목": "사업 개시", "결론": f"개시일 {business_start} → 평가기준일까지 {yrs:.1f}년(3년 미만)", "근거": "상증법 시행령 제54조④2호"})
    if 사유 is None and per_share and len(per_share) == 3 and all(v < 0 for _, v in per_share) and "3년연속결손" in reasons:
        사유 = "3년연속결손"
    if 사유 is None and real_estate_ratio is not None and float(real_estate_ratio) >= 0.8 and "부동산80" in reasons:
        사유 = "부동산80"
    if 사유 is None and stock_asset_ratio is not None and float(stock_asset_ratio) >= 0.8 and "주식80" in reasons:
        사유 = "주식80"
    ev_per = None; ev_calc = ""
    if per_share:
        w = [3, 2, 1][:len(per_share)]
        if len(per_share) < 3:
            판단.append({"항목": "순손익 자료", "결론": f"{len(per_share)}개 연도만 주어짐 — 3년 가중평균(3:2:1)에 못 미쳐 참고 계산. 사업 개시 3년 미만이면 순자산가치만 평가", "근거": "상증법 시행령 제56조①"})
        avg = sum(v * k for (_, v), k in zip(per_share, w)) / 6 if len(per_share) == 3 else sum(v * k for (_, v), k in zip(per_share, w)) / sum(w)
        avg0 = max(0.0, avg)
        ev_per = avg0 / cap_rate
        ev_calc = f"가중평균 1주당 순손익액 {avg:,.2f}(음수면 0) ÷ 환원율 {cap_rate*100:g}% = {ev_per:,.2f}"
    if estimated_profit:
        est_avg, est_판단, est_probs = estimated_profit_check(estimated_profit, valuation_date, kind)
        if est_probs:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": est_probs}
        판단.extend(est_판단)
        if est_avg is not None:
            ev_per = max(0.0, est_avg) / cap_rate
            ev_calc = f"1주당 추정이익 평균 {est_avg:,.2f} ÷ 환원율 {cap_rate*100:g}% = {ev_per:,.2f} (3년 가중평균 대신 적용)"
            판단.append({"항목": "순손익가치", "결론": "추정이익 평가 요건 충족 — 1주당 추정이익 평균가액으로 순손익가치 계산", "근거": "상증법 시행령 제56조②"})
        else:
            판단.append({"항목": "순손익가치", "결론": "추정이익 요건 미충족 — 3년 가중평균으로 계산", "근거": "상증법 시행령 제56조②"})
        if avg < 0:
            판단.append({"항목": "순손익가치", "결론": "가중평균 순손익액이 음수 → 0", "근거": "상증법 시행령 제56조① 후단"})
    # 영업권
    gw = 0.0; gw_note = "영업권 미반영(goodwill·equity 미입력)"
    if goodwill is not None:
        gw = float(goodwill); gw_note = f"영업권 {gw:,.0f}원(입력값) 자산에 가산"
    elif equity is not None and len(per_share) == 3:
        avg_total = sum(v * sh_ * k for (_, v), sh_, k in zip(per_share, [int(it.get('주식수') or it.get('shares') or shares) for it in inc_items], [3, 2, 1])) / 6
        gw, gw_note = goodwill_value(avg_total, float(equity), cap_rate)
        gw_note = f"영업권 {gw:,.0f}원 — {gw_note}"
    excl_gw = 사유 in ("청산", "휴폐업", "부동산80", "주식80", "3년연속결손") or (사유 == "개시3년미만")
    if excl_gw and gw:
        gw_note += " → 순자산가치만 평가하는 법인이라 영업권 합산 제외(영 제55조③ 단서)"; gw = 0.0
    nav_per = (na + gw) / shares
    판단.append({"항목": "순자산가치", "결론": f"({_won(na)} + 영업권 {_won(gw)}) ÷ {shares:,}주 = {nav_per:,.2f}원/주. {gw_note}", "근거": "상증법 시행령 제54조②·제55조·제59조②"})
    # 가중평균
    heavy = real_estate_ratio is not None and float(real_estate_ratio) >= 0.5
    w_e, w_n = (2, 3) if heavy else (3, 2)
    if ev_per is not None:
        weighted = (ev_per * w_e + nav_per * w_n) / 5
        판단.append({"항목": "가중평균", "결론": f"(순손익가치 {ev_per:,.2f}×{w_e} + 순자산가치 {nav_per:,.2f}×{w_n}) ÷ 5 = {weighted:,.2f}" + (" — 부동산 과다보유법인(자산 중 부동산 50% 이상) 2:3" if heavy else " — 3:2"), "근거": "상증법 시행령 제54조①" + (", 소득세법 제94조①4호다목" if heavy else "")})
    else:
        weighted = None
    floor_r, floor_basis = _floor_ratio_inh(vd)
    value = None; method = ""
    if 사유 and not (limited and 사유 in ("부동산80", "주식80") and weighted is not None and weighted >= nav_per):
        value = nav_per; method = f"순자산가치만 평가 — 사유 '{사유}'"
        판단.append({"항목": "평가 방법", "결론": method, "근거": basis_na})
    elif weighted is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["incomes(최근 3개 사업연도 순손익액)가 없고 순자산가치만 평가하는 사유도 없음"], "판단": 판단}
    else:
        if 사유 and limited:
            판단.append({"항목": "평가 방법", "결론": f"사유 '{사유}'지만 가중평균 {weighted:,.2f} ≥ 순자산가치 {nav_per:,.2f}라 가중평균 적용(2026.2.27.~ 한정 규정)", "근거": basis_na})
        value = weighted; method = "가중평균"
        if floor_r is not None and weighted < nav_per * floor_r:
            value = nav_per * floor_r; method = f"하한 적용 — 순자산가치 × {floor_r*100:g}%"
            판단.append({"항목": "하한", "결론": f"가중평균 {weighted:,.2f} < 순자산가치 {nav_per:,.2f} × {floor_r*100:g}% = {value:,.2f} → 하한 적용", "근거": floor_basis})
        elif floor_r is not None:
            판단.append({"항목": "하한", "결론": f"가중평균 ≥ 순자산가치 × {floor_r*100:g}% — 하한 미적용", "근거": floor_basis})
        else:
            판단.append({"항목": "하한", "결론": "하한 규정 없는 구간", "근거": floor_basis})
    # 할증
    if is_max_shareholder and sme is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["최대주주 할증 판정에 sme(중소기업 여부)가 필요(2023~ 중견기업은 mid_sized)"], "필요 입력": {"sme": "bool"}}
    prem, prem_basis, notes = _premium(vd, is_max_shareholder, ratio_over_50, bool(sme), mid_sized, premium_exclusion)
    final = value * (1 + prem)
    판단.append({"항목": "최대주주 할증", "결론": f"{prem*100:g}% → 1주당 {final:,.2f}원. {prem_basis}", "근거": "상속세 및 증여세법 제63조③, 시행령 제53조"})
    for n in notes:
        판단.append({"항목": "확인 필요", "결론": n, "근거": "상속세 및 증여세법 제63조③"})
    판단.append({"항목": "확인 필요", "결론": "순자산가액은 상증법 평가액 기준으로 사용자가 가감(지급 확정 권리 +, 선급비용·무형자산 −, 미지급 법인세·확정 배당·퇴직급여추계액 +, 충당금·준비금 −)을 끝낸 값을 넣어야 함. 발행주식총수의 자기주식 포함 여부는 조문에 명시 없음(통칙 확인)", "근거": "상증법 시행령 제55조, 시행규칙 제17조의2"})
    return {"결과": {"1주당_평가액": round(final, 2), "1주당_할증전": round(value, 2), "순손익가치": round(ev_per, 2) if ev_per is not None else None, "순자산가치": round(nav_per, 2), "가중평균": round(weighted, 2) if weighted is not None else None,
                   "평가방법": method, "할증률": prem, "총평가액(보유주식×)": None},
            "계산": {"순손익가치 산식": ev_calc, "연도별 1주당 순손익액": [{"사업연도": y, "1주당": round(v, 2)} for y, v in per_share], "가중치": f"{w_e}:{w_n}", "하한율": floor_r, "영업권": round(gw, 0), "환원율": cap_rate,
                   **({"순손익액 산출": inc_lines_all} if inc_lines_all else {}), **계산_상세},
            "근거": "상속세 및 증여세법 제63조①1호나목·③, 시행령 제53조·제54조·제55조·제56조·제59조②, 시행규칙 제17조·제17조의2·제17조의3·제19조", "판단": 판단,
            "산식": "순손익가치 = (1년전×3+2년전×2+3년전×1)/6 ÷ 10% / 순자산가치 = (순자산가액+영업권) ÷ 발행주식총수 / 가중평균 3:2(부동산 과다 2:3), 하한 순자산가치×80%(2017.4~2018.3은 70%), 순자산가치만 평가 사유 있으면 순자산가치 / 최대주주 할증 20%(2019까지 50% 초과 30%, 중소 제외·2023~ 중견 제외)"}


# ── (B) 소득세법 기준시가(영 제165조④) — 양도세 기준시가·대주주 시가총액 ──────────────

def income_tax_unlisted_basis(transfer_date: str, shares: int, prior_year_income=None, book_net_asset=None, real_estate_ratio=None,
                              business_start: str = "", status: str = "", stock_asset_ratio=None, rate: float = 0.10) -> dict[str, Any]:
    td = _d(transfer_date)
    if shares is None or int(shares) <= 0 or book_net_asset is None:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["shares(직전 사업연도 종료일 발행주식총수)와 book_net_asset(직전 사업연도 종료일 장부가액 순자산, 토지는 기준시가)이 필요"]}
    shares = int(shares)
    판단: list[dict] = []
    nav = max(0.0, float(book_net_asset)) / shares
    ev = None
    if prior_year_income is not None:
        ev = max(0.0, float(prior_year_income)) / shares / rate
        판단.append({"항목": "순손익가치", "결론": f"직전 사업연도 순손익액 {float(prior_year_income):,.0f} ÷ {shares:,}주 ÷ 이자율 {rate*100:g}% = {ev:,.2f}(3년 가중평균 아님)", "근거": "소득세법 시행령 제165조④1호가목"})
    사유 = None
    if status in ("청산", "휴폐업", "존속3년"):
        사유 = status if not (status == "존속3년" and td < date(2023, 2, 28)) else None
    if business_start and (td - _d(business_start)).days < 365:
        사유 = 사유 or "개시1년미만"
    if 사유 is None and td >= date(2023, 2, 28) and stock_asset_ratio is not None and float(stock_asset_ratio) >= 0.8:
        사유 = "주식80"
    heavy = real_estate_ratio is not None and float(real_estate_ratio) >= 0.5
    w_e, w_n = (2, 3) if heavy else (3, 2)
    if 사유:
        value = nav; method = f"순자산가치만 — 사유 '{사유}'"
        판단.append({"항목": "평가 방법", "결론": method, "근거": "소득세법 시행령 제165조④3호(청산·사업개시 1년 미만·휴폐업·(2023.2.28.~) 주식 80%·존속 3년 이내; 2023.2.27.까지는 3년 연속 결손)"})
    else:
        if ev is None:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["prior_year_income(직전 사업연도 순손익액)이 필요"]}
        weighted = (ev * w_e + nav * w_n) / 5
        value = weighted; method = "가중평균 " + f"{w_e}:{w_n}"
        if td >= date(2018, 4, 1) and weighted < nav * 0.8:
            value = nav * 0.8; method = "하한 — 장부 순자산가치 × 80%"
            판단.append({"항목": "하한", "결론": f"가중평균 {weighted:,.2f} < 순자산가치 {nav:,.2f}×80% → {value:,.2f}", "근거": "소득세법 시행령 제165조④ 단서(2018.4.1. 이후 양도분, 제28637호 부칙 제1조)"})
        판단.append({"항목": "가중평균", "결론": f"({ev:,.2f}×{w_e} + {nav:,.2f}×{w_n}) ÷ 5 = {weighted:,.2f}", "근거": "소득세법 시행령 제165조④1호"})
    판단.append({"항목": "할증", "결론": "양도세 기준시가·대주주 시가총액에는 최대주주 할증을 적용하지 않음(법 제99조①4호는 상증법 제63조①1호나목만 준용, 영 제165조④·제157조에 할증 규정 없음)", "근거": "소득세법 제99조①4호, 시행령 제157조④·제165조④"})
    판단.append({"항목": "확인 필요", "결론": "이자율은 2023.2.27.까지 기획재정부 고시, 이후 시행규칙 — 이 도구는 10%로 계산(값 재확인). 상속·증여 평가(3년 가중·상증법 평가액·할증)와 다른 산식임", "근거": "소득세법 시행령 제165조④"})
    return {"결과": {"1주당_기준시가": round(value, 2), "순손익가치": round(ev, 2) if ev is not None else None, "순자산가치(장부)": round(nav, 2), "평가방법": method},
            "근거": "소득세법 제99조①4호, 시행령 제165조④(2016~2026; 하한 2018.4.1.~, 사유 개정 2023.2.28.)", "판단": 판단,
            "산식": "순손익가치 = 직전 사업연도 1주당 순손익액 ÷ 10% / 순자산가치 = 직전 사업연도 말 장부가 순자산 ÷ 발행주식총수 / 가중평균 3:2(부동산 과다 2:3), 2018.4.1.~ 하한 순자산가치×80%, 할증 없음"}
