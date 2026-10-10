"""특수관계인 판정 · 지분율(직접·간접) · 일감몰아주기(상증법 제45조의3) 증여의제이익. 작성 Mia(윤승미)
조문 문언을 코드로 고정한다. Solar는 쓰지 않는다(자료에서 관계·지분 표를 뽑는 단계만 Solar/Studio).

입력 구조
  people:  {"이름": {"구분": "개인"|"법인", "중소": bool, "중견": bool}}
  family:  [(a, b, "부모자녀"|"배우자")]   — 부모자녀는 (부모, 자녀)
  stakes:  [(보유자, 법인, 지분율 0~1)]     — 직접보유비율(자기주식 제외 기준)
  officers:{법인: [임원 이름]}
"""
from collections import defaultdict
from itertools import count


# ── 친족 (국세기본법 시행령 제1조의2①, 상증령 제2조의2①1호) ──
def _kin_graph(family):
    g = defaultdict(list)
    for a, b, t in family:
        g[a].append((b, t)); g[b].append((a, t))
    return g


def kinship(family, a, b, max_blood=6):
    """a와 b의 친족관계 → ("혈족", 촌수) | ("인척", 촌수) | ("배우자", 0) | None.
    민법 제769조: 인척 = 혈족의 배우자, 배우자의 혈족, 배우자의 혈족의 배우자."""
    if a == b: return None
    g, best = _kin_graph(family), None
    stack = [(a, 0, [], {a})]  # (현재, 혈족 촌수, 배우자 간선 위치들, 방문)
    while stack:
        cur, deg, sp, seen = stack.pop()
        if deg > max_blood: continue
        for nx, t in g[cur]:
            if nx in seen: continue
            d2, sp2 = (deg + 1, sp) if t == "부모자녀" else (deg, sp + [deg])
            if len(sp2) > 2: continue
            if nx == b:
                if not sp2: cand = ("혈족", d2)
                elif sp2 == [0] and d2 == 0: cand = ("배우자", 0)
                elif len(sp2) == 1 and sp2[0] in (0, d2): cand = ("인척", d2)          # 배우자의 혈족 / 혈족의 배우자
                elif len(sp2) == 2 and sp2[0] == 0 and sp2[1] == d2: cand = ("인척", d2)  # 배우자의 혈족의 배우자
                else: cand = None
                if cand and (best is None or cand[1] < best[1]): best = cand
            else:
                stack.append((nx, d2, sp2, seen | {nx}))
    return best


def kin_limits(on="2099-12-31"):
    """친족 범위는 판정 시점 법령으로: 2023.3.1. 이후 4촌 혈족·3촌 인척, 그 전 6촌 혈족·4촌 인척
    (국세기본법 시행령 제1조의2① 2023.2.28. 개정. 예: 국세청 상속증여세과-256, 2013.6.20. '6촌 이내 혈족, 4촌 이내 인척')."""
    return (4, 3) if on >= "2023-03-01" else (6, 4)


def is_kin(family, a, b, law="국기", on="2099-12-31"):
    blood, inlaw = kin_limits(on)
    k = kinship(family, a, b, max_blood=blood)
    ok = bool(k) and (k[0] == "배우자" or (k[0] == "혈족" and k[1] <= blood) or (k[0] == "인척" and k[1] <= inlaw))
    if ok or law != "상증": return ok
    # 상증령 제2조의2①1호 확장: 직계비속의 배우자의 2촌 이내 혈족과 그 배우자
    g = _kin_graph(family)
    for child in _desc(family, a):
        for sp, t in g[child]:
            if t == "배우자":
                k2 = kinship(family, sp, b)
                if k2 and ((k2[0] == "혈족" and k2[1] <= 2) or (k2[0] == "인척" and k2[1] <= 2 and _spouse_of_blood(family, sp, b))): return True
    return False


def _desc(family, a):
    out, todo = set(), [a]
    while todo:
        x = todo.pop()
        for p, c, t in family:
            if t == "부모자녀" and p == x and c not in out: out.add(c); todo.append(c)
    return out


def _spouse_of_blood(family, x, b):
    return any(t == "배우자" and b in (p, c) and ((kinship(family, x, c if p == b else p) or ("", 9))[0] == "혈족") for p, c, t in family)


# ── 지분율: 직접·간접 (상증령 제34조의3②, 법인령 제2조⑦ 같은 곱셈 구조) ──
def paths(stakes, holder, target, min_ratio=0.0):
    """holder → target 출자 경로별 [(경로, 비율)]. 간접은 단계별 직접보유비율의 곱."""
    g = defaultdict(list)
    for h, c, r in stakes: g[h].append((c, r))
    out = []
    def go(node, ratio, path):
        for c, r in g[node]:
            nr = ratio * r
            if nr < 1e-7 or len(path) > 30 or c == holder: continue
            if c == target: out.append((path + [c], nr))
            # 순환·상호출자는 같은 법인을 다시 지나는 경로도 합산(국세청 상속증여세과-256: 각 단계별 보유비율 모두 고려)
            if c != target or any(h == target for h, _, _ in stakes): go(c, nr, path + [c])
    go(holder, 1.0, [holder])
    return [(p, r) for p, r in out if r >= min_ratio]


def has_cycle(stakes):
    g = defaultdict(list)
    for h, c, _ in stakes: g[h].append(c)
    seen, stack = set(), set()
    def dfs(u):
        seen.add(u); stack.add(u)
        for v in g[u]:
            if v in stack or (v not in seen and dfs(v)): return True
        stack.discard(u); return False
    return any(dfs(u) for u in list(g) if u not in seen)


def direct(stakes, holder, target):
    return sum(r for h, c, r in stakes if h == holder and c == target)


def total_ratio(stakes, holder, target, min_indirect=0.0):
    ps = paths(stakes, holder, target)
    return sum(r for p, r in ps if len(p) == 2) + sum(r for p, r in ps if len(p) > 2 and r >= min_indirect)


# ── 특수관계법인: 상증령 제2조의2①6호·7호 (30% / 50%) ──
def controlled(people, family, stakes, person, law="상증"):
    """person과 친족(1호)이 30% 이상(6호) → 그 법인과 함께 50% 이상(7호)인 법인. 반복 확장."""
    group = {person} | {p for p, v in people.items() if v.get("구분") == "개인" and is_kin(family, person, p, law)}
    corps = {c for _, c, _ in stakes}
    got, changed = {}, True
    while changed:
        changed = False
        for c in corps - set(got) - group:
            share = sum(r for h, cc, r in stakes if cc == c and (h in group or h in got))
            base = sum(r for h, cc, r in stakes if cc == c and h in group)
            if base >= 0.30: got[c] = "6호(30% 이상 출자)"; changed = True
            elif share >= 0.50: got[c] = "7호(6호 법인 등과 50% 이상 출자)"; changed = True
    return group, got


# ── 최대주주등·지배주주 (상증령 제19조②, 제34조의3①) ──
def largest_group(people, family, stakes, corp):
    holders = {h: r for h, c, r in stakes if c == corp}
    clusters = []
    for h in holders:
        base = h if people.get(h, {}).get("구분") == "개인" else h
        grp = {x for x in holders if x == h or (people.get(x, {}).get("구분") == "개인" and people.get(h, {}).get("구분") == "개인" and is_kin(family, h, x, "상증"))}
        if people.get(h, {}).get("구분") == "개인":
            _, ctl = controlled(people, family, stakes, h)
            grp |= {x for x in holders if x in ctl}
        clusters.append((sum(holders[x] for x in grp), grp))
    return max(clusters, key=lambda t: t[0]) if clusters else (0, set())


def dominant_shareholder(people, family, stakes, corp):
    """지배주주: 최대주주등 중 직접보유비율 최고자가 개인이면 그 개인, 법인이면 직접+간접 합계 최고 개인(①1·2호)."""
    _, grp = largest_group(people, family, stakes, corp)
    if not grp: return None, "주주 자료 없음"
    top = max(grp, key=lambda x: direct(stakes, x, corp))
    if people.get(top, {}).get("구분") == "개인":
        return top, f"최대주주등 중 직접보유비율 최고자({direct(stakes, top, corp):.2%})가 개인 — 제34조의3①1호"
    indiv = {p for p, v in people.items() if v.get("구분") == "개인"}
    # 최대주주등의 범위: 직접 주주 그룹 + 그룹 안 개인의 친족 + (친족과 합해) 그룹 안 법인을 30% 이상 지배하는 개인
    members = set(grp)
    corps_in = {x for x in grp if people.get(x, {}).get("구분") == "법인"}
    for p in indiv:
        kin = {q for q in indiv if q != p and is_kin(family, p, q, "상증")}
        if any(q in grp for q in kin) or any(sum(r for h, c, r in stakes if c == k and h in kin | {p}) >= 0.30 for k in corps_in):
            members.add(p)
    # ①2호 단서 가·나목: 최대주주등이 아닌 자(수혜법인 주주·직접보유 최고 법인의 주주 포함)는 제외
    cand = {p: total_ratio(stakes, p, corp) for p in indiv & members if total_ratio(stakes, p, corp) > 0}
    if not cand: return None, f"직접보유 최고자가 법인({top})이나 개인 간접보유자 확인 안 됨"
    who = max(cand, key=cand.get)
    return who, f"직접보유 최고자가 법인({top}) — 직접+간접 합계 최고 개인 {who}({cand[who]:.2%}), 제34조의3①2호"


# ── 일감몰아주기 증여의제이익 (상증법 제45조의3, 시행령 제34조의3) ──
def size_rates(size, on="2099-12-31"):
    """(정상거래비율, 한계보유비율, 계산식 배수) — 사실관계(수혜법인 사업연도) 시점 규정.
    2012 사업연도: 30%·3%, 계산식도 정상거래비율 전부 차감(배수 1.0) / 2013 사업연도: 계산식은 정상거래비율의 1/2(배수 0.5)
    (이성태·최기호·윤성만, 회계저널 24(5), 2015 — 당시 상증령 제34조의2). 2014 이후는 현행(⑦·⑨항, 법 ①2호)으로 둠.
    ※ 2014~2022 사이 중소·중견 비율 변동은 확인 필요."""
    if on < "2013-01-01": return 0.30, 0.03, 1.0
    if on < "2014-01-01": return 0.30, 0.03, 0.5
    if size == "중소": return 0.50, 0.10, 1.0
    if size == "중견": return 0.40, 0.10, 0.5
    return 0.30, 0.03, None  # 일반: 5% 초과 거래비율 × 주식보유비율


def split_limit(relations, limit):
    """⑬항: 한계보유비율을 간접보유비율에서 먼저, 작은 것부터 뺀 뒤 남으면 직접에서 뺀다."""
    left, out = limit, {}
    for k, r in sorted([(k, r) for k, r in relations.items() if k != "직접"], key=lambda t: t[1]) + [("직접", relations.get("직접", 0))]:
        cut = min(r, left); out[k] = r - cut; left -= cut
    return out


def tunnelling(people, family, stakes, beneficiary, sales_total, sales_by_corp, after_tax_op_profit, size, excluded_sales=0, on="2099-12-31"):
    """반환: 판정·계산 과정 전체(검증 가능하게 수식 문자열 포함). excluded_sales는 ⑩항 과세제외매출액(입력)."""
    ctrl, why = dominant_shareholder(people, family, stakes, beneficiary)
    if not ctrl: return {"결론": "지배주주 판정 불가", "사유": why}
    group, related_corps = controlled(people, family, stakes, ctrl)
    rel_sales = {c: v for c, v in sales_by_corp.items() if c in related_corps}
    ratio = sum(rel_sales.values()) / sales_total if sales_total else 0
    normal, limit, mult = size_rates(size, on)
    taxable_ratio = 1 - (excluded_sales / sales_total if sales_total else 0)
    profit = after_tax_op_profit * taxable_ratio
    rel_amt = sum(rel_sales.values())
    # 과세 요건(법 ①1호): 중소·중견은 정상거래비율 초과, 일반은 그 초과 또는 (정상거래비율의 2/3 초과 & 특관매출 1천억 초과)
    hit = ratio > normal or (mult is None and ratio > normal * 2 / 3 and rel_amt > 100_000_000_000)
    # 계산식(법 ①2호): 중소 = 정상거래비율·한계보유비율 초과분, 중견 = 각 50% 초과분, 일반 = 5% 초과 거래비율 × 주식보유비율 전부
    ex_ratio = ratio - normal * mult if mult is not None else ratio - 0.05
    res = {"수혜법인": beneficiary, "기업규모": size, "지배주주": ctrl, "지배주주판정": why, "지배주주등(친족)": sorted(group),
           "특수관계법인": related_corps, "특수관계법인매출": rel_sales, "특수관계법인거래비율": ratio,
           "정상거래비율": normal, "한계보유비율": limit, "계산식_차감거래비율": normal * mult if mult is not None else 0.05,
           "계산식_차감보유비율": limit * mult if mult is not None else 0,
           "세후영업이익(과세매출비율 반영)": round(profit), "주주별": [], "합계": 0}
    if not hit:
        res["결론"] = f"과세 요건 미충족 — 특수관계법인거래비율 {ratio:.2%} ≤ 정상거래비율 {normal:.0%}"; return res
    for p in sorted(group):
        rel = {}
        for path, r in paths(stakes, p, beneficiary):
            if len(path) == 2: rel["직접"] = rel.get("직접", 0) + r
            elif r >= 0.001 and _qualified_indirect(people, family, stakes, group, path[1]):  # ⑬ 1천분의1 미만 제외, ⑱ 간접출자법인
                rel["→".join(path[1:-1])] = r
        tot = sum(rel.values())
        if tot <= limit: continue  # 법 ①: 주식보유비율이 한계보유비율 이하인 주주 제외(중견도 10% 기준)
        net = split_limit(rel, limit * mult) if mult is not None else rel
        adj = {}
        if on < "2014-01-01" and ratio:
            for k in net:
                if k == "직접": continue
                first = k.split("→")[0]
                up = sales_by_corp.get(first, 0) / sales_total if first in rel_sales and sales_total else 0
                if up: adj[k] = (ratio - up) / ratio  # 상증령(당시) 제34조의2⑩ 상향매출 조정
        gain = {k: round(profit * ex_ratio * v * adj.get(k, 1)) for k, v in net.items() if v > 0}
        res["주주별"].append({"주주": p, "출자관계": rel, "한계차감후": net, "증여의제이익": gain,
                           "산식": f"{round(profit):,} × {ex_ratio:.4%} × 출자관계별(보유비율−한계)", "소계": sum(gain.values())})
        res["합계"] += sum(gain.values())
    res["결론"] = f"과세 — 증여의제이익 합계 {res['합계']:,}원(증여시기: 수혜법인 사업연도 종료일, 법 ③)" if res["합계"] else "과세 대상 주주 없음(한계보유비율 이하)"
    res["미반영"] = ["⑭항 출자관계별 과세제외매출액 가산", "⑮항 배당소득 공제", "⑫항 세후영업이익 세무조정 계산(입력값 사용)"]
    return res


def _qualified_indirect(people, family, stakes, group, first_corp):
    """⑱항: 지배주주등이 30% 이상 출자(1호) 또는 1호 법인 등과 50% 이상(2호), 그 아래 개재 법인(3호)."""
    s = sum(r for h, c, r in stakes if c == first_corp and h in group)
    if s >= 0.30: return True
    s2 = sum(r for h, c, r in stakes if c == first_corp and (h in group or sum(r2 for h2, c2, r2 in stakes if c2 == h and h2 in group) >= 0.30))
    return s2 >= 0.50


# ── 특수관계인 판독기: A와 B가 어느 세법 기준으로, 몇 호로 특수관계인지 ──
# case = {"people": {이름: {"구분": "개인"|"법인", "영리": True}}, "family": [...], "stakes": [...],
#         "officers": {법인: [임원]}, "employees": {법인: [직원]}, "livelihood": [(부양자, 피부양자)],
#         "influence": [(영향력자, 법인)], "group": {기업집단명: [계열회사]},
#         "group_exempt": {법인: "계열편입 유예통지 2022.11.~7년"}}
def _is_corp(case, x): return case["people"].get(x, {}).get("구분") == "법인"


def _share(case, holders, corp):
    return sum(r for h, c, r in case["stakes"] if c == corp and h in holders)


def _dominates(case, who, corp, via=(), depth=0):
    """국기령 제1조의2③·④: 본인이 직접 또는 친족·경제적 연관관계에 있는 자, 그리고 그렇게 지배하는 법인을 통해
    30% 이상 출자하거나 사실상 영향력을 행사하면 지배적 영향력."""
    holders = {who, *via}
    if depth < 3:  # 본인 그룹이 지배하는 다른 법인(가목 법인)도 출자자로 합산 → 나목
        for c in {c for _, c, _ in case["stakes"]} - {corp} - holders:
            if _is_corp(case, c) and _dominates(case, who, c, via, depth + 1): holders.add(c)
    sh = _share(case, holders, corp)
    who_has = sorted(h for h in holders if direct(case["stakes"], h, corp) > 0)
    if sh >= 0.30:
        parts = ', '.join(f'{h} {direct(case["stakes"], h, corp):.1%}' for h in who_has)
        return f"{parts} — 합계 {sh:.1%}(30% 이상)"
    infl = [i for i, c in case.get("influence", []) if c == corp and i in holders]
    if infl: return f"{', '.join(infl)}의 사실상 영향력(임원 임면·사업방침 결정)"
    return ""


def _kin_set(case, x, law, on):
    return {p for p, v in case["people"].items() if v.get("구분") == "개인" and p != x and is_kin(case["family"], x, p, law, on)}


def _econ(case, a, b):
    """경제적 연관관계: 임원·사용인, 생계유지자(국기령 제1조의2②)."""
    for corp, xs in {**case.get("officers", {}), **{k: v for k, v in case.get("employees", {}).items()}}.items():
        if (a == corp and b in xs) or (b == corp and a in xs): return f"{corp}의 임원·사용인"
    for giver, taker in case.get("livelihood", []):
        if {a, b} == {giver, taker}: return f"{taker}이(가) {giver}의 재산으로 생계 유지"
    return ""


def judge_pair(case, a, b, law="국기", on="2099-12-31"):
    """반환: [{"근거": 조문, "내용": 설명}] — 비어 있으면 특수관계 아님(주어진 자료 기준)."""
    hits = []
    def hit(ref, why): hits.append({"근거": ref, "내용": why})
    blood, inlaw = kin_limits(on)
    fam = case["family"]

    # 1) 친족 (개인-개인)
    if not _is_corp(case, a) and not _is_corp(case, b):
        k = kinship(fam, a, b, max_blood=blood)
        if is_kin(fam, a, b, "상증" if law == "상증" else "국기", on):
            desc = f"{k[0]} {k[1]}촌" if k and k[0] != "배우자" else ("배우자" if k else "직계비속의 배우자의 2촌 이내 혈족·그 배우자(사돈)")
            hit({"국기": "국세기본법 시행령 제1조의2①", "법인": "국세기본법 시행령 제1조의2①(법인세법 시행령 제2조⑧ 각 호의 '친족')",
                 "상증": "상속세 및 증여세법 시행령 제2조의2①1호"}[law], f"{desc} — 기준일 {on[:10]} 범위(혈족 {blood}촌·인척 {inlaw}촌)")
        elif k:
            hits_note = f"{k[0]} {k[1]}촌은 기준일 범위 밖(혈족 {blood}촌·인척 {inlaw}촌)"
            case.setdefault("_notes", []).append(hits_note)

    # 2) 경제적 연관관계
    e = _econ(case, a, b)
    if e:
        hit({"국기": "국세기본법 시행령 제1조의2②", "법인": "법인세법 시행령 제2조⑧3호", "상증": "상속세 및 증여세법 시행령 제2조의2①2호"}[law], e)

    # 3) 지배관계 (개인/법인 → 법인)
    for x, y in ((a, b), (b, a)):
        if not _is_corp(case, y): continue
        if law == "법인":
            # 법인세법: y(법인) 기준으로 x가 특수관계인인지 — 1호 영향력자·친족, 2호 비소액주주(1% 이상)·친족, 6호 30%×30%
            infl = [i for i, c in case.get("influence", []) if c == y]
            if x in infl or any(is_kin(fam, i, x, "국기", on) for i in infl if not _is_corp(case, i)):
                hit("법인세법 시행령 제2조⑧1호", f"{y}의 경영에 사실상 영향력을 행사하는 자 또는 그 친족")
            big = [h for h, c, r in case["stakes"] if c == y and r >= 0.01]
            if x in big: hit("법인세법 시행령 제2조⑧2호", f"{y}의 비소액주주({direct(case['stakes'], x, y):.2%}, 1% 이상)")
            elif any(is_kin(fam, h, x, "국기", on) for h in big if not _is_corp(case, h) and not _is_corp(case, x)):
                hit("법인세법 시행령 제2조⑧2호", f"{y}의 비소액주주의 친족")
            for mid in {h for h, c, r in case["stakes"] if c == y and r >= 0.30}:
                if direct(case["stakes"], x, mid) >= 0.30:
                    hit("법인세법 시행령 제2조⑧6호", f"{y}에 30% 이상 출자한 {mid}에 30% 이상 출자({direct(case['stakes'], x, mid):.1%})")
            if _is_corp(case, x):
                d = _dominates(case, y, x)
                if d: hit("법인세법 시행령 제2조⑧4호", f"{y}가 {x}의 경영에 지배적 영향력: {d}")
        else:
            via = _kin_set(case, x, law, on) if not _is_corp(case, x) else set()
            d = _dominates(case, x, y, via)
            if d:
                if law == "상증":
                    ref = "상속세 및 증여세법 시행령 제2조의2①6호" if "30%" in d else "상속세 및 증여세법 시행령 제2조의2①3호"
                else:
                    ref = "국세기본법 시행령 제1조의2③1호가목" if not _is_corp(case, x) else "국세기본법 시행령 제1조의2③2호나목"
                hit(ref, f"{x}(친족 포함)가 {y}의 경영에 지배적 영향력: {d}")
            elif law == "상증" and not _is_corp(case, x):
                _, ctl = controlled(case["people"], fam, case["stakes"], x)
                if y in ctl: hit(f"상속세 및 증여세법 시행령 제2조의2①{ctl[y][:2]}", f"{x}와 그 친족·지배법인이 {y}에 {ctl[y]}")

    # 3-2) 법인↔법인: 한 법인을 지배하는 개인(친족 포함)이 다른 법인도 지배 (국기령 ③2호가·다목, 법인령 특관 4·5호, 상증령 6·7호)
    if _is_corp(case, a) and _is_corp(case, b):
        indiv = [p for p, v in case["people"].items() if v.get("구분") == "개인"]
        for p in indiv:
            kin = _kin_set(case, p, law if law == "상증" else "국기", on)
            da, db = _dominates(case, p, a, kin), _dominates(case, p, b, kin)
            if da and db:
                ref = {"국기": "국세기본법 시행령 제1조의2③2호가목·다목", "법인": "법인세 특수관계인 4호·5호", "상증": "상속세 및 증여세법 시행령 제2조의2①6호·7호"}[law]
                hit(ref, f"{p}(친족 포함)가 {a}와 {b}를 모두 지배 — {a}: {da} / {b}: {db}"); break

    # 4) 기업집단 계열회사
    exempt = case.get("group_exempt", {})  # {법인: 사유} — 공정위 계열편입 유예·제외 통지(사전-2023-법규법인-0184)
    for g, members in case.get("group", {}).items():
        if a in members and b in members and (a in exempt or b in exempt):
            x = a if a in exempt else b
            case.setdefault("_notes", []).append(f"{x}: {exempt[x]} → 기업집단({g}) 계열회사로 보지 않음(사전-2023-법규법인-0184, 공정거래법상 소속 여부로 판정)")
            continue
        if a in members and b in members:
            hit({"국기": "국세기본법 시행령 제1조의2③2호라목", "법인": "법인세법 시행령 제2조⑧7호", "상증": "상속세 및 증여세법 시행령 제2조의2①3호"}[law], f"같은 기업집단({g}) 계열회사")

    seen, out = set(), []
    for h in hits:
        if (h["근거"], h["내용"]) not in seen: seen.add((h["근거"], h["내용"])); out.append(h)
    return out


def judge_all(case, a, b, on="2099-12-31"):
    """세 세법 기준을 한 번에: 세법마다 범위가 달라 결과가 갈릴 수 있음."""
    case["_notes"] = []
    res = {law: judge_pair(case, a, b, law, on) for law in ("국기", "법인", "상증")}
    return {"대상": f"{a} ↔ {b}", "기준일": on, "판정": {k: ("특수관계 해당" if v else "해당 없음(주어진 자료 기준)") for k, v in res.items()},
            "근거": res, "참고": sorted(set(case["_notes"])), "순환출자": has_cycle(case["stakes"])}


# ── 사실관계 시점의 법: 기준일에 시행 중이던 특수관계인 조문 위치 ──
_CITE_CACHE = {}


def cite_at(law, on):
    """law: 국기|법인|상증, on: YYYY-MM-DD → (법령, 조항, 원문 첫머리). 법제처에서 그 시점 버전을 받아 확인.
    확인된 이동: 법인령 제87조① → (2019.2.12.) 제2조⑤ → 이후 제2조⑧ / 상증령 제12조의2① → (2016.2.5.) 제2조의2①."""
    import re
    from . import law as law_api
    key = (law, on)
    if key in _CITE_CACHE: return _CITE_CACHE[key]
    d = on.replace("-", "")
    if law == "국기":
        name, cands = "국세기본법 시행령", ["제1조의2"]
    elif law == "법인":
        name, cands = "법인세법 시행령", ["제2조", "제87조"]
    else:
        name, cands = "상속세 및 증여세법 시행령", ["제2조의2", "제12조의2"]
    try:
        for jo in cands:
            t = law_api.article(name, jo, as_of=d)
            if not t or ("특수관계인" not in t and "제2조제12호" not in t): continue
            if law == "법인" and jo == "제2조":
                m = re.search(r"([①-⑳])\s*법 제2조제12호", t)
                if not m: continue
                out = (name, f"{jo}{m.group(1)}", t[m.start():m.start() + 120])
            else:
                head = t.splitlines()[0]
                if "특수관계인의 범위" not in head: continue
                out = (name, f"{jo}①", head)
            _CITE_CACHE[key] = out
            return out
    except law_api.NoKey:
        pass  # LAW_OC 없음 → 아래 고정 이동표로 fallback
    except Exception:
        pass  # 법제처 API 오류 등 → 아래 고정 이동표로 fallback
    # LAW_OC 없이 법제처 API 호출 실패 → 코드에 고정된 이동표로 답
    _CITE_CACHE[key] = _cite_fixed(law, on)
    return _CITE_CACHE[key]


def _cite_fixed(law, on):
    """LAW_OC 미설정 또는 법제처 조회 실패 시 사용할 고정 이동표.
    원문확인 필요 플래그와 함께 반환."""
    d = on[:10] if len(on) >= 10 else on
    if law == "국기":
        return ("국세기본법 시행령", "제1조의2①",
                f"국세기본법 시행령 제1조의2① — 기준일 {d} 시행본에서 특수관계인 범위 확인(원문확인: LAW_OC 설정 시 법제처 원문 대조)")
    if law == "법인":
        # 확인된 이동: ~2019.2.11. 제87조① → 2019.2.12.~2023.12.31. 제2조⑤ → 2024.1.1.~ 제2조⑧
        if on < "2019-02-12":
            return ("법인세법 시행령", "제87조①",
                    f"법인세법 시행령 제87조① — 기준일 {d} 시행본에서 특수관계인 범위 확인(원문확인: LAW_OC 설정 시 법제처 원문 대조)")
        if on < "2024-01-01":
            return ("법인세법 시행령", "제2조⑤",
                    f"법인세법 시행령 제2조⑤ — 기준일 {d} 시행본에서 특수관계인 범위 확인(원문확인: LAW_OC 설정 시 법제처 원문 대조)")
        return ("법인세법 시행령", "제2조⑧",
                f"법인세법 시행령 제2조⑧ — 기준일 {d} 시행본에서 특수관계인 범위 확인(원문확인: LAW_OC 설정 시 법제처 원문 대조)")
    # 상증
    if on < "2016-02-05":
        return ("상속세 및 증여세법 시행령", "제12조의2①",
                f"상속세 및 증여세법 시행령 제12조의2① — 기준일 {d} 시행본에서 특수관계인 범위 확인(원문확인: LAW_OC 설정 시 법제처 원문 대조)")
    return ("상속세 및 증여세법 시행령", "제2조의2①",
            f"상속세 및 증여세법 시행령 제2조의2① — 기준일 {d} 시행본에서 특수관계인 범위 확인(원문확인: LAW_OC 설정 시 법제처 원문 대조)")


def judge_all_at(case, a, b, on):
    """judge_all + 기준일 시행 조문 위치로 근거 표기를 바꿔 씀(호 번호는 유지)."""
    import re
    j = judge_all(case, a, b, on)
    j["적용조문"] = {law: cite_at(law, on) for law in ("국기", "법인", "상증")}
    for law, hs in j["근거"].items():
        name, jo, _ = j["적용조문"][law]
        for h in hs:
            if law == "법인":
                h["근거"] = re.sub(r"법인세법 시행령 제2조⑧|법인세 특수관계인", f"{name} {jo}", h["근거"])
            if law == "상증":
                h["근거"] = h["근거"].replace("상속세 및 증여세법 시행령 제2조의2①", f"{name} {jo}")
    return j


# ── 현행(2014~) 일감몰아주기 — 국세청 「2026년 일감몰아주기·일감떼어주기 증여세 신고안내」 산식 그대로 ──
def op_tax_base(calc_tax, land_tax=0.0, credits=0.0, unreturned_tax=0.0):
    """⑫2호 가목 세액: 법인세법 제55조 산출세액 − 제55조의2 토지등 양도소득 법인세 − 공제·감면세액.
    unreturned_tax: 미환류소득 법인세 — calc_tax에 빠져 있으면 더한다(기준-2023-법규재산-0125: 포함).
    2018년 이후 투자·상생협력촉진세제(조특법 제100조의32)분은 사업연도별 시점 확인."""
    return calc_tax + unreturned_tax - land_tax - credits


def after_tax_op_profit(op_income, taxable_income, tax, taxable_sales_ratio):
    """상증령 제34조의3⑫: [세무조정후 영업손익 − 법인세×min(영업손익/각사업연도소득, 1)] × 과세매출비율"""
    share = min(op_income / taxable_income, 1) if taxable_income else 1
    return (op_income - tax * share) * taxable_sales_ratio


def tunnelling_nts(beneficiary, size, op_income, taxable_income, tax, sales_total, sales_by_corp, relations,
                   base_excluded=0.0, holdings_in_related=None, indirect_corp_of=None, dividends=None, excluded_by_corp=None,
                   land_tax=0.0, credits=0.0, unreturned_tax=0.0):
    """출자관계별 증여의제이익(책자 제2장 5).
    relations: {관계명: 보유비율} — 예: {"직접": 0.20, "A법인 경유": 0.18}
    base_excluded: ⑩항 과세제외매출액(모든 관계 공통, 예: 중소-중소 거래)
    holdings_in_related: {특관법인: 지배주주등의 그 법인 보유비율} → ⑭3호(직접·다른 간접 관계)
    indirect_corp_of: {관계명: 그 경로의 간접출자법인명} → 그 관계에서만 ⑭1호(간접출자법인 매출 전액 제외)
    dividends: {관계명: (배당소득, 분모)} → ⑮항 공제 (분모 = 배당가능이익×보유비율 등 책자 산식)
    excluded_by_corp: {특관법인: ⑩항 과세제외액} — ⑩항으로 이미 빠진 매출에는 ⑭항을 적용하지 않음(⑭항 본문)"""
    tax = op_tax_base(tax, land_tax, credits, unreturned_tax)
    normal, limit, mult = size_rates(size)
    sub_ratio = normal * mult if mult is not None else 0.05
    sub_hold = limit * mult if mult is not None else 0.0
    rel_amt = sum(sales_by_corp.values())
    holdings_in_related = holdings_in_related or {}
    indirect_corp_of = indirect_corp_of or {}
    excluded_by_corp = excluded_by_corp or {}
    base_excluded = (base_excluded or 0.0) + sum(excluded_by_corp.values())
    # 한계보유비율은 간접에서 먼저, 작은 것부터 (⑬, 중소·중견만)
    net_hold = split_limit(relations, sub_hold) if sub_hold else dict(relations)
    out, total = {}, 0
    for rel, hold in relations.items():
        if rel != "직접" and hold < 0.001: continue  # ⑬ 0.1% 미만 간접 제외
        # ⑭항 추가 과세제외매출액(출자관계별): 특관법인마다 1호(이 경로의 간접출자법인 매출 전액)와
        # 3호(매출 × 지배주주등의 그 특관법인 보유비율) 중 해당하는 것, 둘 다면 큰 금액
        extra = 0.0
        for c, v in sales_by_corp.items():
            if c in excluded_by_corp: continue  # ⑩항에 해당하는 매출처는 ⑭항 적용 안 함(⑭항 본문, 책자 작성사례[2] ㈜순천)
            by1 = v if indirect_corp_of.get(rel) == c else 0.0
            by3 = v * holdings_in_related.get(c, 0)
            extra += max(by1, by3)
        excl = base_excluded + extra
        ratio = (rel_amt - excl) / (sales_total - excl) if sales_total - excl else 0
        profit = after_tax_op_profit(op_income, taxable_income, tax, 1 - excl / sales_total)
        gain = profit * max(ratio - sub_ratio, 0) * max(net_hold.get(rel, 0), 0)
        ded = 0
        if dividends and rel in dividends:
            d, denom = dividends[rel]
            ded = __import__("math").floor(d * gain / denom) if denom else 0  # 원 미만 절사(책자 작성사례[2])
        g = max(gain - ded, 0)
        out[rel] = {"과세제외매출액": excl, "특수관계법인거래비율": ratio, "과세매출비율": 1 - excl / sales_total,
                    "세후영업이익": profit, "보유비율(한계차감후)": net_hold.get(rel, 0), "증여의제이익": g, "배당공제": ded}
        total += g
    hit = (rel_amt - base_excluded) / (sales_total - base_excluded) > normal if sales_total > base_excluded else False
    return {"수혜법인": beneficiary, "과세요건(정상거래비율 초과)": hit, "출자관계별": out, "합계": total}


def dividend_deduction(gain, dividend, dividend_capacity, holding, via_capacity=None, via_holding=None):
    """상증령 제34조의3⑮(2023.2.28. 이후 신고분): 배당소득 × 증여의제이익 / 분모, 음수면 0.
    직접: 분모 = 수혜법인 배당가능이익 × 직접보유비율
    간접: 분모 = [간접출자법인 배당가능이익 + 수혜법인 배당가능이익 × 간접출자법인의 수혜법인 보유비율] × 지배주주등의 간접출자법인 보유비율"""
    if via_capacity is None:
        denom = dividend_capacity * holding
    else:
        denom = (via_capacity + dividend_capacity * via_holding) * holding
    return max(gain - __import__("math").floor(dividend * gain / denom), 0) if denom else gain
