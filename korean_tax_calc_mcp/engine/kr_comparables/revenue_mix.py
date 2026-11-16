"""매출 구성 — 매출 행 고르기(코드)와 6갈래 분류(Solar 또는 규칙). 금액은 언제나 원문 표 칸에서 코드가 읽는다. Claude 작성(2026-11-16).

상장: 사업보고서 'II. 사업의 내용'의 '매출 및 수주상황'·'주요 제품' 표 중 하나 — 주요 매출처 표·부문 재무표·수주 표 제외,
      합계 행과 맞는 층(지역 제외 / 지역 행만 / 라벨 깊이별)을 우선, 소계·합계·중복 행 제거, 당기(첫 금액 칸)만, '-' 칸은 뒤에 숫자 칸이 있으면 건너뜀.
비상장: 감사보고서 손익계산서의 매출 하위 행(매출액 아래 ~ 매출원가 전).
분류: UPSTAGE_API_KEY가 있으면 Solar(solar-pro4)에 행 이름만 보내 6갈래 분류(금액은 보내지 않음), 없으면 이름 규칙 분류 + '정확도 낮음'.
"""
import hashlib
import json
import os
import re
import time
import urllib.request

from .statements import title_sections, txt, unit_of
from .dart import BACKOFF, RETRIES, cache_dir, mask, transient, _ssl_ctx

_sleep = time.sleep   # 테스트에서 바꿔 끼움

CATS = ("product", "merchandise", "service", "sw_license", "platform_fee", "other")
KO = {"제품": "product", "상품": "merchandise", "용역": "service", "SW·라이선스": "sw_license", "플랫폼·중개수수료": "platform_fee", "기타": "other"}
SOLAR_MODEL = "solar-pro4"
SOLAR_URL = "https://api.upstage.ai/v1/chat/completions"

TOTAL = re.compile(r"^(합\s*계|총\s*계|계|매출\s*합계|매출액\s*합계|합계\s*매출액|총\s*매출액?)$")
SUBT = re.compile(r"(^|[\s/])(소\s*계|계)\s*$|합\s*계|총\s*계")
GEO = re.compile(r"내수|수출|국내|해외|지역|미주|유럽|아시아|중국|일본|북미|기타지역")
CUST = re.compile(r"매출처|거래처|고객사|주요\s*고객|^[A-Z]\s*사$|^[가-하]\s*사$")
AMT = re.compile(r"^\(?-?\d{1,3}(,\d{3})+\)?$|^\(?-?\d{4,}\)?$")


def amount_of(cell):
    c = cell.replace(" ", "")
    if "%" in c and not re.match(r"^-?[\d,]+\(", c):
        return None
    m = re.match(r"^(-?[\d,]+)\((-?[\d.]+%?)\)$", c)   # 금액(비율)
    if m:
        c = m.group(1)
    if c in ("-", "－"):
        return 0
    if not AMT.match(c):
        return None
    neg = c.startswith("(") or c.startswith("-")
    v = int(c.strip("()-").replace(",", ""))
    return -v if neg else v


def _row_cells(row):
    labs, amt = [], None
    vals = [(c, amount_of(c)) for c in row]
    for i, (c, v) in enumerate(vals):
        if v is None:
            if re.search(r"[가-힣A-Za-z]", c):
                labs.append(c)
            continue
        if v == 0 and c.strip() in ("-", "－") and any(x is not None and x != 0 for _, x in vals[i + 1:]):
            continue
        amt = v
        break
    return labs, amt


def business_tables(s):
    """사업보고서 '매출 및 수주상황'·'주요 제품' 절의 숫자 표 → [{section, unit, unit_src, rows, ctx}]."""
    out = []
    for a, b, tt in title_sections(s):
        if not re.search(r"매출\s*및\s*수주|주요\s*제품", tt):
            continue
        for m in re.finditer(r"<TABLE([^>]*)>(.*?)</TABLE>", s[a:b], re.S):
            ctxraw = s[a:b][max(0, m.start() - 800):m.start()]
            rows = []
            for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", m.group(2), re.S):
                cells = [re.sub(r"\s+", " ", txt(c)).strip() for _, _, c in re.findall(r"<(TH|TD|TE|TU)([^>]*)>(.*?)</\1>", tr, re.S)]
                if any(cells):
                    rows.append(cells)
            if len(rows) >= 2 and any(re.search(r"\d{1,3}(,\d{3})+", " ".join(r)) for r in rows):
                unit, usrc = unit_of(ctxraw + m.group(0))
                if usrc.startswith("없음"):
                    hm = re.search(r"\(\s*(백\s*만\s*원|천\s*원|원)\s*\)", " ".join(" ".join(r) for r in rows[:3]))
                    if hm:
                        unit, usrc = {"백만원": 1000000, "천원": 1000, "원": 1}[re.sub(r"\s", "", hm.group(1))], "머리행"
                out.append({"section": tt.strip()[:40], "unit": unit, "unit_src": usrc, "rows": rows[:60], "ctx": re.sub(r"\s+", "", txt(ctxraw))[-200:]})
    return out[:8]


SRC_TYPE = {"제품": "product", "제품매출": "product", "상품": "merchandise", "상품매출": "merchandise",
            "용역": "service", "용역매출": "service", "서비스": "service", "서비스매출": "service"}


CONT = re.compile(r"^(내수|수출|국내|해외|직접판매|파트너판매|대리점판매|로컬|직수출|내\s*수|수\s*출)$")


def _src_type(labs):
    """라벨 칸 중 원문 매출유형(제품·상품·용역/서비스) 한 칸 — '제품/상품매출/기타매출'처럼 섞인 칸은 쓰지 않음."""
    hits = {SRC_TYPE[re.sub(r"\s", "", x)] for x in labs if re.sub(r"\s", "", x) in SRC_TYPE}
    return hits.pop() if len(hits) == 1 else None


def _analyze(tb):
    total, items = None, []
    has_type_col = bool(re.search(r"유\s*형", " ".join(tb["rows"][0]) if tb["rows"] else ""))
    cur_type, type_labs = None, set()
    for ri, row in enumerate(tb["rows"]):
        labs, amt = _row_cells(row)
        if has_type_col and labs:
            t = _src_type(labs)
            first = re.sub(r"\s", "", labs[0])
            if t:
                cur_type, type_labs = t, {re.sub(r"\s", "", x) for x in labs}
            elif not (CONT.search(first) or first in type_labs):
                cur_type = None   # 이어지는 행(병합 칸)인지 확실하지 않으면 원문 유형을 쓰지 않음
        if amt is None or not labs:
            continue
        lab = " / ".join(labs)
        if re.search(r"\d{4}\s*년|제\s*\d+\s*기|당기|전기", lab) and len(labs) == 1:
            continue
        if any(TOTAL.match(re.sub(r"\s", "", x)) for x in labs) and total is None and len(labs) <= 2:
            total = amt
            continue
        if any(SUBT.search(x) for x in labs):
            continue
        items.append((ri, lab, amt, bool(any(GEO.search(x) for x in labs)), len(labs), cur_type if has_type_col else None))
    return total, items


def _pick_layer(total, items):
    def dedup(xs):
        seen, out = set(), []
        for x in xs:
            k = (re.sub(r"\s", "", x[1]), x[2])
            if k not in seen:
                seen.add(k)
                out.append(x)
        return out
    cands = [("지역 제외", [x for x in items if not x[3]]), ("지역 행만", [x for x in items if x[3]])]
    for depth in sorted({x[4] for x in items}):
        cands.append((f"라벨 {depth}칸 행", [x for x in items if x[4] == depth and not x[3]]))
    cands = [(n, dedup(xs)) for n, xs in cands if xs]
    if total:
        for n, xs in cands:
            if abs(sum(x[2] for x in xs) - total) <= 0.02 * abs(total):
                return n, xs, True
    return (cands[0][0], cands[0][1], False) if cands else ("", [], False)


def listed_rows(s):
    """사업보고서 원문 → (행 [(라벨, 금액(원), 표 번호, 행 번호)], 표 정보)."""
    tabs = business_tables(s)
    best = None
    for ti, tb in enumerate(tabs):
        head = " ".join(" ".join(r) for r in tb["rows"][:2]) + " " + tb["ctx"][-80:]
        if re.search(r"비금융|조정|수주\s*(총액|잔고)|계약일|납기|매출처|거래처|고객사", head):
            continue
        if sum(1 for r in tb["rows"] if _row_cells(r)[0] and CUST.search(_row_cells(r)[0][0])) >= 2:
            continue
        total, items = _analyze(tb)
        layer, xs, ok = _pick_layer(total, items)
        if not xs:
            continue
        sc = (3 if ok else 0) + (2 if ("매출" in tb["section"] and "수주" in tb["section"]) else 0) + (1 if re.search(r"매출\s*실적|매출액\s*현황|매출\s*현황", head) else 0)
        cand = (sc, -ti, ti, layer, xs, ok)
        if best is None or cand[:2] > best[:2]:
            best = cand
    if not best:
        return [], {"note": "매출 표 못 찾음(사업의 내용에 매출 표 없음 또는 부문 재무표만)"}
    _, _, ti, layer, xs, ok = best
    tb = tabs[ti]
    return [(x[1], x[2] * tb["unit"], ti, x[0], x[5]) for x in xs], {"table": f"{ti}:{tb['section']}", "layer": layer, "total_check": ok, "unit_src": tb["unit_src"]}


def unlisted_rows(is_rows):
    """감사보고서 손익계산서 행 → 매출 하위 행 [(라벨, 금액, 'IS', '')]."""
    out, started = [], False
    for lab, c, p in is_rows:
        if not started:
            if re.match(r"^(매출액|매출|영업수익|수익\(매출액\)|매출및영업수익)$", lab):
                started = True
            continue
        if re.match(r"^(매출원가|영업비용|매출총이익|판매비와관리비|영업원가)", lab):
            break
        if c and lab:
            out.append((lab, c[-1] if len(c) == 1 else c[0], "IS", ""))
    return out


# ---------------- 분류 ----------------
RULES = [("product", r"^(제품|제품매출|제품매출액)$|제품|제조"), ("merchandise", r"^(상품|상품매출|상품매출액)$|상품"),
         ("sw_license", r"소프트웨어|SW|S/W|라이선스|라이센스|솔루션|게임|SaaS|로열티|사용료"),
         ("platform_fee", r"수수료|플랫폼|중개|결제|광고"),
         ("service", r"용역|서비스|유지보수|공사|임대|운송|SI|컨설팅|구축|정비|관리비")]


def classify_rules(labels):
    out = {}
    for i, l in enumerate(labels):
        x = re.sub(r"\s", "", l)
        cat = next((c for c, p in RULES if re.search(p, x)), "other")
        out[i] = (cat, "이름 규칙")
    return out


PROMPT = """다음은 한국 회사 공시의 매출 행 이름 목록이다(금액은 주지 않는다). 각 행을 아래 6개 중 하나로 분류하라.
제품=자기가 제조한 물리적 재화 / 상품=사서 되파는 재화 / 용역=SI·컨설팅·유지보수·공사·운영 대행·임대 등 서비스 제공 /
SW·라이선스=소프트웨어·게임·솔루션 판매나 사용료, SaaS, 로열티 / 플랫폼·중개수수료=플랫폼·앱·결제·중개 수수료, 광고 매출 / 기타.
JSON만 출력: {"rows":[{"id":0,"category":"제품|상품|용역|SW·라이선스|플랫폼·중개수수료|기타","reason":"20자 이내"}]}
회사 업종 참고: {ctx}
행:
"""


def solar_http(body, key):
    req = urllib.request.Request(SOLAR_URL, data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120, context=_ssl_ctx()) as r:
        return json.load(r)


def classify_solar(labels, ctx, key, http=None, stat=None):
    """Solar 분류(캐시). 실패하면 None(호출한 쪽이 규칙 분류로 대체)."""
    text = "\n".join(f"id={i}: {l}" for i, l in enumerate(labels))
    body = {"model": SOLAR_MODEL, "messages": [{"role": "user", "content": PROMPT.replace("{ctx}", ctx[:200]) + text}], "temperature": 0}
    d_dir = os.path.join(cache_dir(), "solar")
    os.makedirs(d_dir, exist_ok=True)
    f = os.path.join(d_dir, "v1_" + hashlib.sha1(json.dumps(body, ensure_ascii=False).encode()).hexdigest()[:16] + ".json")
    stat = stat if stat is not None else {}
    try:
        if os.path.exists(f):
            d = json.load(open(f, encoding="utf-8"))
            stat["solar_cached"] = stat.get("solar_cached", 0) + 1
        else:
            d = None
            for attempt in range(1 + RETRIES):       # 일시 오류만 재시도(1·2·4초), 다 실패하면 아래 except → 규칙 분류
                stat["solar_calls"] = stat.get("solar_calls", 0) + 1
                try:
                    d = (http or solar_http)(body, key)
                    break
                except Exception as e:
                    if not transient(e) or attempt == RETRIES:
                        raise
                    stat["solar_retries"] = stat.get("solar_retries", 0) + 1
                    _sleep(BACKOFF[attempt])
            with open(f, "w", encoding="utf-8") as fh:
                json.dump(d, fh, ensure_ascii=False)
        j = json.loads(re.search(r"\{.*\}", d["choices"][0]["message"]["content"], re.S).group(0))
        return {int(x["id"]): (KO.get(x.get("category"), "other"), (x.get("reason") or "")[:40]) for x in j.get("rows", [])}
    except Exception as e:
        stat.setdefault("solar_errors", []).append(mask(f"{type(e).__name__}: {e}", key))
        return None


FIX = [(r"^(제품|제품매출|제품매출액)$", "product"), (r"^(상품|상품매출|상품매출액)$", "merchandise"),
       (r"^(용역|용역매출|용역수익|공사|공사수익|공사매출|공사수입|분양수익|임대|임대수익|임대매출|임대료수익|운송|운송수입|운송수익|용역수입|임대수입)$", "service")]


def classify(rows, ctx, listed, upstage_key=None, http=None, stat=None):
    """rows → ({i: (갈래, 근거)}, 방법). 비상장의 표준 계정명은 코드로 바로 정함."""
    cls, need = {}, []
    for i, r in enumerate(rows):
        if listed and len(r) > 4 and r[4]:
            cls[i] = (r[4], "원문 매출유형")
            continue
        k = None if listed else next((c for p, c in FIX if re.match(p, re.sub(r"\s", "", r[0]))), None)
        if k:
            cls[i] = (k, "원문 계정명")
        else:
            need.append(i)
    method = "원문 매출유형·계정명"
    if need:
        labels = [rows[i][0] for i in need]
        got = classify_solar(labels, ctx, upstage_key, http, stat) if upstage_key else None
        if got is None:
            got, method = classify_rules(labels), "규칙(정확도 낮음)"
        else:
            method = "Solar(solar-pro4, 행 이름만)"
        for j, i in enumerate(need):
            cls[i] = got.get(j, ("other", "분류 누락"))
    return cls, method


def mix_shares(rows, cls):
    tot = sum(r[1] for r in rows)
    amt = {}
    for i, r in enumerate(rows):
        amt[cls[i][0]] = amt.get(cls[i][0], 0) + r[1]
    return ({k: amt.get(k, 0) / tot for k in CATS} if tot else {}), tot
