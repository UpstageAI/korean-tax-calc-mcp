"""여러 사업연도에 걸친 계산 — 이월결손금 추적, 해외 자회사 청산 손익. Claude 작성(2026-11-12).

이월결손금(법인세법 제13조①1호, 시행령 제10조② — 2016·2019·2020·2021·2022·2023·2026 시행본 대조):
  · 공제기간: 2020.1.1. 전에 개시한 사업연도에 발생한 결손금은 10년, 2020.1.1. 이후 개시한 사업연도에 발생한 결손금은 15년
    (법률 제17652호 부칙 제4조·제15조). "각 사업연도의 개시일 전 N년 이내에 개시한 사업연도에서 발생한 결손금".
  · 한도: 각 사업연도 소득 × 한도율(중소기업 등 100%, 그 외 2017년까지 80%·2018년 70%·2019~2022년 60%·2023년부터 80% — calc_cit.loss_limit_ratio)
  · 순서: 먼저 발생한 사업연도의 결손금부터(시행령 제10조②)
해외 자회사 청산(법인세법 제16조①4호, 해석 법인46012-442·사전-2015-법령해석법인-0057·사전-2021-법령해석법인-1372):
  · 잔여재산 분배액이 주식 취득가액을 넘으면 그 초과액은 의제배당
  · 못 미치면 그 차액은 청산이 끝나 잔여재산 분배가 완료된(배분 가능한 잔여재산이 없음이 확인된) 날이 속하는 사업연도의 손금"""
from datetime import date

from . import calc_cit as CC

YEAR_MIN, YEAR_MAX = 2016, 2026


def _carry_years(loss_year):
    return 15 if loss_year >= 2020 else 10


def loss_carryforward_ledger(years, sme=True, opening_losses=None):
    문제 = []
    if not isinstance(years, list) or not years:
        문제.append("years — [{year, income}] 사업연도별 각 사업연도 소득(결손이면 음수), 1건 이상")
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    seen = []
    for i, y in enumerate(years):
        yr, inc = (y or {}).get("year"), (y or {}).get("income")
        if not isinstance(yr, int) or not YEAR_MIN <= yr <= YEAR_MAX:
            문제.append(f"years[{i}].year={yr!r} — {YEAR_MIN}~{YEAR_MAX}")
        if isinstance(inc, bool) or not isinstance(inc, int):
            문제.append(f"years[{i}].income — 각 사업연도 소득(원, 정수. 결손이면 음수)")
        if "sme" in (y or {}) and not isinstance(y["sme"], bool):
            문제.append(f"years[{i}].sme — true/false")
        seen.append(yr)
    ok_years = [s for s in seen if isinstance(s, int)]
    if ok_years != sorted(ok_years) or len(set(ok_years)) != len(ok_years):
        문제.append("years — 연도 오름차순, 같은 연도는 한 번만")
    elif ok_years and ok_years != list(range(ok_years[0], ok_years[-1] + 1)):
        문제.append(f"years — {ok_years[0]}~{ok_years[-1]} 사이에 빠진 연도가 있음(소득이 0인 해도 넣어야 잔액·소멸을 맞게 계산)")
    for i, o in enumerate(opening_losses or []):
        yr, amt = (o or {}).get("year"), (o or {}).get("amount")
        if not isinstance(yr, int) or not 2009 <= yr < (ok_years[0] if ok_years else YEAR_MAX):
            문제.append(f"opening_losses[{i}].year={yr!r} — 2009년부터 첫 사업연도 전까지(2008년 이전 발생분은 당시 공제기간 부칙을 대조하지 않아 지원하지 않음)")
        if isinstance(amt, bool) or not isinstance(amt, int) or amt <= 0:
            문제.append(f"opening_losses[{i}].amount — 미공제 결손금 잔액(원, 양의 정수)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    pool = {}          # 발생연도 → 잔액
    for o in opening_losses or []:
        pool[o["year"]] = pool.get(o["year"], 0) + o["amount"]
    rows, 판단 = [], []
    for y in years:
        yr, inc = y["year"], y["income"]
        is_sme = y.get("sme", sme)
        # 공제기간이 지난 결손금 소멸: 발생연도 L은 L + N년에 개시하는 사업연도까지 공제
        expired = {L: a for L, a in pool.items() if a > 0 and yr > L + _carry_years(L)}
        for L in expired:
            pool[L] = 0
        row = {"year": yr, "각사업연도소득": inc, "소멸": [{"발생연도": L, "금액": a, "공제기간": f"{_carry_years(L)}년"} for L, a in sorted(expired.items())]}
        if inc < 0:
            pool[yr] = pool.get(yr, 0) - inc
            row.update({"한도율": None, "공제한도": 0, "공제": [], "공제액": 0, "과세표준": 0, "당기결손금": -inc})
        else:
            ratio = CC.loss_limit_ratio(yr, is_sme)
            limit = int(inc * ratio) if ratio < 1 else inc
            left, used = limit, []
            for L in sorted(pool):
                if left <= 0: break
                if pool[L] <= 0: continue
                take = min(pool[L], left)
                pool[L] -= take; left -= take
                used.append({"발생연도": L, "금액": take})
            ded = limit - left
            row.update({"한도율": ratio, "공제한도": limit, "공제": used, "공제액": ded, "과세표준": inc - ded, "당기결손금": 0})
            if ded and ratio < 1 and ded == limit and any(a > 0 for a in pool.values()):
                판단.append({"항목": f"{yr}년", "결론": f"공제 한도 {limit:,}원(소득의 {ratio:.0%})까지만 공제 — 남은 결손금은 다음 사업연도로", "근거": "법인세법 제13조① 단서"})
        row["결손금_잔액"] = [{"발생연도": L, "금액": a, "공제기한": f"{L + _carry_years(L)}년 개시 사업연도까지"} for L, a in sorted(pool.items()) if a > 0]
        row["결손금_잔액_합계"] = sum(a for a in pool.values())
        rows.append(row)
    tot = {"공제액": sum(r["공제액"] for r in rows), "과세표준": sum(r["과세표준"] for r in rows), "소멸": sum(x["금액"] for r in rows for x in r["소멸"]),
           "기말_결손금_잔액": rows[-1]["결손금_잔액_합계"]}
    판단.insert(0, {"항목": "순서·기간", "결론": "먼저 발생한 사업연도의 결손금부터 공제. 2019년까지 발생분은 10년, 2020년부터 발생분은 15년 안에 개시한 사업연도까지", "근거": "법인세법 시행령 제10조②, 법 제13조①1호 가목, 법률 제17652호 부칙 제4조·제15조"})
    return {"결과": tot, "계산": {"연도별": rows}, "판단": 판단, "근거": "법인세법 제13조①, 시행령 제10조②",
            "주의": ["각 사업연도 소득은 세무조정 후 금액 — 결손금은 신고·결정·경정·수정신고한 과세표준에 포함된 것만(법 제13조①1호 나목)",
                   "채무면제이익 충당, 결손금 소급공제, 합병·분할 승계 결손금, 사업연도가 1년 미만인 경우는 반영하지 않음",
                   "한도율은 중소기업 등 100% — 회생계획 이행 법인 등 시행령 제10조①의 법인도 100%이므로 해당하면 sme=true로 입력"]}


def foreign_subsidiary_liquidation(tax_basis, distribution, completed_on="", fy_end="", ownership_ratio=1.0, book_value=None):
    문제 = []
    for nm, v in (("tax_basis", tax_basis), ("distribution", distribution)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            문제.append(f"{nm} — 원(0 이상 정수)")
    if book_value is not None and (isinstance(book_value, bool) or not isinstance(book_value, int) or book_value < 0):
        문제.append("book_value — 회계 장부가액(원, 0 이상 정수)")
    comp = None
    if completed_on:
        try:
            comp = date.fromisoformat(completed_on)
            if not YEAR_MIN <= comp.year <= YEAR_MAX: raise ValueError
        except ValueError:
            문제.append(f"completed_on={completed_on!r} — YYYY-MM-DD({YEAR_MIN}~{YEAR_MAX})")
    fe = None
    if fy_end:
        try: fe = date.fromisoformat(fy_end)
        except ValueError: 문제.append(f"fy_end={fy_end!r} — YYYY-MM-DD")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    diff = distribution - tax_basis
    결과 = {"세무상_취득가액": tax_basis, "잔여재산_분배액": distribution}
    판단 = []
    if diff > 0:
        결과.update({"구분": "의제배당", "의제배당": diff, "청산손실": 0})
        판단.append({"항목": "의제배당", "결론": f"잔여재산 분배액 {distribution:,}원이 주식 취득가액 {tax_basis:,}원을 넘음 — 초과액 {diff:,}원은 배당으로 봄", "근거": "법인세법 제16조①4호"})
        판단.append({"항목": "익금불산입", "결론": "외국자회사 수입배당금 익금불산입(제18조의4) 대상인지는 지분율·보유기간 요건으로 따로 판정(foreign_subsidiary_dividend)", "근거": "법인세법 제18조의4"})
    else:
        loss = -diff
        결과.update({"구분": "청산손실" if loss else "손익 없음", "의제배당": 0, "청산손실": loss})
        if loss:
            if comp is None:
                결과["손금_귀속"] = None
                판단.append({"항목": "손금 귀속", "결론": "청산 종결·잔여재산 분배 완료일(completed_on)을 입력하지 않음 — 청산이 끝나 손실이 확정되기 전에는 손금에 넣을 수 없음", "근거": "법인46012-442(2000.2.16.)"})
            else:
                if fe is None:
                    fe = date(comp.year, 12, 31)
                while fe < comp:
                    fe = date(fe.year + 1, fe.month, fe.day)
                결과["손금_귀속"] = {"사업연도_종료일": fe.isoformat(), "기준일": comp.isoformat()}
                판단.append({"항목": "손금 귀속", "결론": f"청산이 끝나 잔여재산 분배가 완료된(배분 가능한 잔여재산이 없음이 확인된) {comp.isoformat()}이 속하는 사업연도({fe.isoformat()} 종료)에 {loss:,}원 손금",
                           "근거": "법인46012-442(2000.2.16.), 사전-2015-법령해석법인-0057(2015.6.11.), 사전-2021-법령해석법인-1372(2021.10.27.)"})
    if book_value is not None and book_value != tax_basis:
        gap = tax_basis - book_value
        결과["유보_정리"] = gap
        판단.append({"항목": "유보", "결론": (f"세무상 취득가액이 회계 장부가액보다 {gap:,}원 큼(손금불산입된 평가손실·지분법손실 등 유보) — 청산 손익을 인식하는 사업연도에 손금산입(△유보)으로 정리" if gap > 0
                                       else f"세무상 취득가액이 회계 장부가액보다 {-gap:,}원 작음 — 청산 손익을 인식하는 사업연도에 익금산입으로 정리"),
                   "근거": "유보로 남긴 세무조정의 정리(자본금과 적립금 조정명세서(을))"})
    return {"결과": 결과, "판단": 판단, "근거": "법인세법 제16조①4호·제19조·제40조",
            "주의": ["세무상 취득가액은 출자액에 손금불산입된 평가손실·지분법손실 등 유보를 반영한 금액 — 대여금을 출자전환한 주식은 출자전환 때의 취득가액 판정이 먼저",
                   "거래의 실질이 주식을 시가로 평가하려는 것이면 손금으로 보지 않음(사전-2021-법령해석법인-1372). 회수할 수 있는 재산을 남기고 청산하면 손금 부인·가지급금 위험",
                   "자회사에 대한 대여금·미수금을 못 받은 금액은 이 계산에 넣지 않음 — 대손 요건(법 제19조의2)과 채권 포기의 부당행위·기부금 여부를 따로 판정(업무와 관련 없는 가지급금인지는 사실 판단, 법인세과-568)",
                   "외국환거래규정의 청산보고는 foreign_exchange_reporting(event='청산')"]}


# ── 연도별 세무조정 묶음: 결산서상 순손익 → 각 사업연도 소득 → 이월결손금 → 과세표준 → 산출세액, 유보 잔액 ──────────
# 근거(2016·2026 시행본 대조): 법인세법 제14조(각 사업연도 소득 = 익금 총액 − 손금 총액), 제67조(소득처분), 제13조①, 제55조.
# 서식: 소득금액조정합계표(시행규칙 별지 제15호), 자본금과 적립금조정명세서(을)(별지 제50호).
# 출자의 증가(0.37.1): 국조법에 따라 익금에 산입한 금액이 반환된 것으로 확인되지 않고 상대방이 내국법인이 출자한 법인이면 「법인세법」 제67조에도 불구하고 출자의 증가로 조정.
#   2016~2020 시행본: 구 국조법 제9조①, 구 시행령 제16조①2호 / 2021 시행본부터: 국조법 제13조①, 시행령 제23조①1호(각 시행본 대조). 유보·사외유출과 따로 누계만 보여 줌.
_ADD = ("익금산입", "손금불산입")
_SUB = ("손금산입", "익금불산입")
_DISP_ADD = ("유보", "상여", "배당", "기타소득", "기타사외유출", "기타", "출자의 증가")
_EQUITY = "출자의 증가"
_DISP_SUB = ("유보", "기타")


def tax_adjustment_schedule(years, sme=True, opening_reserves=None, opening_losses=None):
    문제 = []
    if not isinstance(years, list) or not years:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["years — [{year, book_income, adjustments: [{name, amount, kind, disposition}]}] 1건 이상"]}
    for i, y in enumerate(years):
        yr, bi = (y or {}).get("year"), (y or {}).get("book_income")
        if not isinstance(yr, int) or not YEAR_MIN <= yr <= YEAR_MAX:
            문제.append(f"years[{i}].year={yr!r} — {YEAR_MIN}~{YEAR_MAX}")
        if isinstance(bi, bool) or not isinstance(bi, int):
            문제.append(f"years[{i}].book_income — 결산서상 당기순손익(원, 정수. 손실이면 음수)")
        for j, a in enumerate((y or {}).get("adjustments") or []):
            nm, amt, kind, disp = a.get("name"), a.get("amount"), a.get("kind"), a.get("disposition")
            if not nm: 문제.append(f"years[{i}].adjustments[{j}].name — 조정 항목 이름")
            if isinstance(amt, bool) or not isinstance(amt, int) or amt < 0:
                문제.append(f"years[{i}].adjustments[{j}].amount — 원(0 이상 정수)")
            if kind not in _ADD + _SUB:
                문제.append(f"years[{i}].adjustments[{j}].kind={kind!r} — {list(_ADD + _SUB)}")
            elif disp not in (_DISP_ADD if kind in _ADD else _DISP_SUB):
                문제.append(f"years[{i}].adjustments[{j}].disposition={disp!r} — {kind}은 {list(_DISP_ADD if kind in _ADD else _DISP_SUB)}"
                          + ("(손금산입·익금불산입의 '유보'는 △유보)" if kind in _SUB else ""))
    for i, o in enumerate(opening_reserves or []):
        if not (o or {}).get("name") or isinstance(o.get("amount"), bool) or not isinstance(o.get("amount"), int):
            문제.append(f"opening_reserves[{i}] — {{name, amount(원, △유보 잔액이면 음수)}}")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    reserves = {}
    for o in opening_reserves or []:
        reserves[o["name"]] = reserves.get(o["name"], 0) + o["amount"]
    rows, incomes, 판단 = [], [], []
    equity_cum = {}
    for y in years:
        yr, bi = y["year"], y["book_income"]
        begin = dict(reserves)
        add = sub_ = 0
        disp_tot, inc, dec, eq = {}, {}, {}, {}
        for a in y.get("adjustments") or []:
            nm, amt, kind, disp = a["name"], a["amount"], a["kind"], a["disposition"]
            if kind in _ADD:
                add += amt
                if disp == "유보":
                    reserves[nm] = reserves.get(nm, 0) + amt; inc[nm] = inc.get(nm, 0) + amt
                elif disp == _EQUITY:
                    eq[nm] = eq.get(nm, 0) + amt; equity_cum[nm] = equity_cum.get(nm, 0) + amt
                elif disp != "기타":
                    disp_tot[disp] = disp_tot.get(disp, 0) + amt
            else:
                sub_ += amt
                if disp == "유보":
                    before = reserves.get(nm, 0)
                    reserves[nm] = before - amt; dec[nm] = dec.get(nm, 0) + amt
                    if before > 0 and amt > before:
                        판단.append({"항목": f"{yr}년 {nm}", "결론": f"유보 잔액 {before:,}원보다 많은 {amt:,}원을 △유보로 정리 — 항목 이름·금액 확인(새로 생긴 △유보면 그대로)", "근거": "자본금과 적립금조정명세서(을)"})
        income = bi + add - sub_
        incomes.append({"year": yr, "income": income, **({"sme": y["sme"]} if "sme" in y else {})})
        names = sorted(set(begin) | set(reserves))
        rows.append({"year": yr, "결산서상_당기순손익": bi, "익금산입_손금불산입": add, "손금산입_익금불산입": sub_, "각사업연도소득": income,
                     "소득처분_사외유출": disp_tot,
                     "유보": [{"항목": n, "기초": begin.get(n, 0), "증가": inc.get(n, 0), "감소": dec.get(n, 0), "기말": reserves.get(n, 0)} for n in names if begin.get(n, 0) or inc.get(n, 0) or dec.get(n, 0) or reserves.get(n, 0)],
                     "유보_기말_합계": sum(reserves.values())})
        if equity_cum:
            rows[-1]["출자의_증가"] = [{"항목": n, "당기": eq.get(n, 0), "누계": equity_cum[n]} for n in sorted(equity_cum)]
            rows[-1]["출자의_증가_누계"] = sum(equity_cum.values())
        if eq:
            old = yr <= 2020
            판단.append({"항목": f"{yr}년 출자의 증가", "결론": f"{sum(eq.values()):,}원 — 국외특수관계인(내국법인이 출자한 법인)에게서 반환받은 것으로 확인되지 않은 익금산입액은 그 법인에 대한 출자의 증가로 조정. 사외유출이 아니어서 원천징수 대상 처분이 아니고, 유보 표와 따로 누계로 보여 줌",
                       "근거": "구 국제조세조정에 관한 법률 제9조①, 구 시행령 제16조①2호" if old else "국제조세조정에 관한 법률 제13조①, 시행령 제23조①1호"})
    led = loss_carryforward_ledger(incomes, sme, opening_losses)
    if "error" in led:
        return led
    for r, lr in zip(rows, led["계산"]["연도별"]):
        base = lr["과세표준"]
        r.update({"이월결손금_공제": lr["공제액"], "이월결손금_공제_내역": lr["공제"], "과세표준": base,
                  "산출세액": CC.corp_tax(base, r["year"], 12) if base > 0 else 0,
                  "결손금_잔액": lr["결손금_잔액_합계"], "결손금_소멸": sum(x["금액"] for x in lr["소멸"])})
        if any(k in r["소득처분_사외유출"] for k in ("상여", "배당", "기타소득")):
            판단.append({"항목": f"{r['year']}년 소득처분", "결론": "상여·배당·기타소득 처분액은 원천징수와 귀속자의 소득세 신고가 따름(상여는 deemed_bonus_resettlement)", "근거": "법인세법 제67조, 시행령 제106조"})
    판단 = led["판단"] + 판단
    tot = {"각사업연도소득": sum(r["각사업연도소득"] for r in rows), "과세표준": sum(r["과세표준"] for r in rows), "산출세액": sum(r["산출세액"] for r in rows),
           "기말_유보": rows[-1]["유보_기말_합계"], "기말_결손금_잔액": rows[-1]["결손금_잔액"]}
    주의_출자 = []
    if equity_cum:
        tot["기말_출자의_증가_누계"] = sum(equity_cum.values())
        주의_출자 = ["출자의 증가: 이전소득금액 반환 확인서를 시행령이 정한 기한(90일) 안에 내면 이 조정을 하지 않음. 상대방이 내국법인의 주주이거나 그 밖의 자이면 출자의 증가가 아니라 배당. "
                  "출자의 증가 누계를 자본금과 적립금조정명세서에서 어떻게 관리하는지, 그 주식을 처분·청산할 때 세무상 취득가액에 더하는지는 이 도구가 판단하지 않음(해석 확인 필요)"]
    return {"결과": tot, "계산": {"연도별": rows}, "판단": 판단, "근거": "법인세법 제14조·제13조①·제55조·제67조, 시행령 제10조②·제106조",
            "서식": "소득금액조정합계표(법인세법 시행규칙 별지 제15호), 자본금과 적립금조정명세서(을)(별지 제50호)",
            "주의": ["조정 금액은 이미 계산한 값을 넣는다 — 이 도구는 연도별로 합치고 유보·결손금·세액을 이어 줄 뿐, 각 조정이 맞는지는 판단하지 않음",
                   "결산서상 당기순손익은 법인세비용을 뺀 뒤 금액 — 법인세비용은 손금불산입(기타사외유출) 조정으로 넣는다",
                   "산출세액은 과세표준 × 그 해 세율(12개월 사업연도). 세액공제·감면, 최저한세, 토지등 양도소득 법인세, 미환류소득은 반영하지 않음",
                   "기부금·기업업무추진비 한도처럼 다른 조정 뒤의 소득으로 한도를 다시 계산하는 순서는 반영하지 않음 — 한도 조정은 각 도구로 따로 계산해 넣는다"] + 주의_출자}
