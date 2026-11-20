"""문서 색인 — 공시 원문 1건을 '표준 열쇠 → 자리'로 바꾼다. 읽는 쪽은 원문을 직접 뒤지지 않고 이 색인에만 묻는다. Claude 작성(2026-11-18).

열쇠: '절:<표준 절 제목>' · '표:<DART 표준 표 코드>' · '재무제표:BS|IS|CF|EF' · '주석:<금감원 주석 코드 D…/U… 또는 보조 코드 K…>'
build(key, xml, D) → 색인(dict).  index_of(xml) → 패키지 사전으로 만든 색인(문서마다 한 번만 만듦).  ask(색인, 열쇠) → {'상태': 있음|없음|못 찾았을 수 있음, '확정': bool, '자리': [...], '사유': str}
- 있음: 그 열쇠가 붙은 자리가 있다. 확정 = 원문 표식(코드)이거나 사전에 한 코드로만 쓰인 제목. 아니면 추정.
- 없음: 문서를 빈틈없이 나눴고(번호가 1부터 이어지고, 재무제표가 가리키는 주석 번호가 다 있고, 모든 제목에 코드가 붙음) 그 열쇠가 없다.
- 못 찾았을 수 있음: 나누기에 빈틈이 있어 '없다'고 말할 수 없다. 사유에 빈틈을 적는다."""
import collections
import functools
import re

from . import notecode as N

TOK = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9\-]*)[^>]*>|&cr;")
BREAK = {"P", "TD", "TH", "TE", "TU", "TR", "TITLE", "TABLE", "BR", "PGBRK", "LIBRARY", "TABLE-GROUP", "COVER-TITLE", "TBODY", "THEAD", "SECTION-1", "SECTION-2", "SECTION-3", "PART", "BODY"}
def clean(t):
    return re.sub(r"\s+", " ", t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")).strip()
def flat_lines(s, a=0, b=None):
    """원문 → [(자리, 글, 표 안인가)]. 문단·표 칸·줄바꿈 기호(&cr;)마다 한 줄."""
    b = len(s) if b is None else b
    out, buf, depth, pos, start = [], [], 0, a, a
    def flush():
        if buf:
            t = clean("".join(buf))
            if t: out.append((start, t, depth > 0))
            buf.clear()
    for m in TOK.finditer(s, a, b):
        if m.start() > pos and s[pos:m.start()].strip():
            chunk = s[pos:m.start()]
            for part in NL_HEAD.split(chunk):                       # 문단 안의 줄바꿈 뒤에 번호 제목이 오면 거기서 줄을 나눔
                if part.strip():
                    if buf and part is not chunk and NUM_START.match(part): flush()
                    if not buf: start = pos
                    buf.append(part)
        pos = m.end()
        tag = (m.group(2) or "").upper()
        if not tag or tag in BREAK or (tag == "SPAN" and not m.group(1) and NUM_START.match(s[pos:pos + 40])):
            flush()
        if tag == "TABLE":
            depth = max(0, depth + (-1 if m.group(1) else 1))
    if pos < b and s[pos:b].strip():
        if not buf: start = pos
        buf.append(s[pos:b])
    flush()
    return out

NL_HEAD = re.compile(r"\n(?=\s*\d{1,2}\s*\.\s*[가-힣])")
NUM_START = re.compile(r"\s*\d{1,2}\s*\.\s*[가-힣]")
HEAD0 = re.compile(r"^\s*(?:주석\s*)?(\d{1,2})\s*\.\s*(?!\d)([가-힣A-Za-z].*)$")
GLUED = re.compile(r"(?:(?<=[다\)])|(?<=[^\d\s]\.))\s*(\d{1,2})\s*\.\s*(?!\d)([가-힣A-Za-z].*)$")
GAP_MAX = 3
def split_notes(s, a, b, D):
    """주석 구간 [a,b) → 번호가 차례로 늘어나는 주석 제목 사슬 [{번호, 제목, 자리, 표 안}]. 후보 줄 가운데 '코드가 붙는 제목이 가장 많은' 사슬을 고른다.
    표 칸의 번호 줄과 앞 문장 끝에 붙은 번호는 사전에 있는 제목일 때만 후보."""
    cand = []
    for pos, line, in_tab in flat_lines(s, a, b):
        m = HEAD0.match(line)
        if m:
            t, in_dict = N.cut_title(m.group(2), D, loose=not in_tab)
            if t and (not in_tab or in_dict):
                cand.append((pos, int(m.group(1)), t, in_tab, bool(D.lookup(t)["코드"])))
            continue
        if in_tab:
            continue
        for g in GLUED.finditer(line):
            t, in_dict = N.cut_title(g.group(2), D)
            if t and (in_dict or (len(t) < len(g.group(2)) and D.lookup(t)["코드"])):     # 사전 제목이거나, 본문 시작 앞에서 끊겼고 코드가 붙는 제목
                cand.append((pos, int(g.group(1)), t, False, True))
    if not cand:
        return []
    best, prev = [0.0] * len(cand), [-1] * len(cand)
    for i, (_p, n, _t, tab, known) in enumerate(cand):
        w = 1.0 + (1.0 if known else 0.0) - (0.5 if tab else 0.0)
        best[i] = w - 0.3 * (n - 1) if n <= GAP_MAX else -1e9
        for j in range(i):
            nj = cand[j][1]
            if nj < n <= nj + GAP_MAX and best[j] > -1e8:
                sc = best[j] + w - 0.3 * (n - nj - 1)
                if sc > best[i]: best[i], prev[i] = sc, j
    i = max(range(len(cand)), key=lambda k: best[k])
    if best[i] < -1e8:
        return []
    chain = []
    while i >= 0:
        chain.append(cand[i]); i = prev[i]
    heads = [{"번호": n, "제목": t, "자리": p, "표 안": tab} for p, n, t, tab, _k in reversed(chain)]
    return _fill(s, b, heads, D)

def _find_number(s, a, b, n):
    """[a,b) 안에서 'n. 글자' 꼴의 첫 자리와 그 뒤 글(다음 태그 전까지). 앞이 숫자·쉼표·점이거나 '주석 n.'이면 제목이 아님."""
    for m in re.finditer(r"(?<![\d,\.])%d\s*\.\s*(?=[가-힣A-Za-z])" % n, s[a:b]):
        before = re.sub(r"<[^>]+>", "", s[max(a, a + m.start() - 30):a + m.start()])
        if re.search(r"(주석|주)\s*$", before) or s.rfind("<", a, a + m.start()) > s.rfind(">", a, a + m.start()):
            continue
        rest = clean(re.split(r"<|&cr;", s[a + m.end():a + m.end() + 200])[0])
        if rest:
            return a + m.start(), rest
    return None
def _fill(s, end, heads, D):
    """사슬에서 빠진 번호를 앞뒤 주석 사이에서 다시 찾는다(문장 끝·표 뒤에 붙은 제목). 자리가 앞뒤 주석 사이로 묶여 있어 본문 속 번호와 섞이지 않는다. 끝 번호 뒤도 이어서 찾는다."""
    changed = True
    while changed:
        changed = False
        nums = [h["번호"] for h in heads]
        for n in [x for x in range(1, max(nums) + 2) if x not in nums]:
            lo = max([h["자리"] for h in heads if h["번호"] < n] or [None], key=lambda v: -1 if v is None else v)
            hi = min([h["자리"] for h in heads if h["번호"] > n] or [end])
            if lo is None: continue
            hit = _find_number(s, lo + 1, hi, n)
            if not hit: continue
            t, _in = N.cut_title(hit[1], D, loose=True)
            if not t: t = hit[1][:20]
            heads.append({"번호": n, "제목": t, "자리": hit[0], "표 안": False, "다시 찾음": True}); heads.sort(key=lambda h: h["자리"]); changed = True
            break
    return heads

CITE = re.compile(r"\(\s*주석\s*([\d,\s·ㆍ및]+)\)")
def cited_notes(s, a, b):
    """재무제표 구간의 표 줄에서 '계정(주석 5,12)' → {번호: [계정 이름…]}. 나누기 검사용(독립된 근거)."""
    out = collections.defaultdict(list)
    for _pos, line, in_tab in flat_lines(s, a, b):
        if not in_tab: continue
        for m in CITE.finditer(line):
            acct = re.sub(r"^[\dIVXⅠ-Ⅹ\.\(\)\s]+", "", line[:m.start()]).strip()
            for x in re.findall(r"\d{1,2}", m.group(1)):
                out[int(x)].append(acct)
    return out

def titles(s):
    ts = [(m.start(), clean(re.sub(r"<[^>]+>", "", m.group(1)))) for m in re.finditer(r"<TITLE[^>]*>(.*?)</TITLE>", s, re.S)]
    return [(a, (ts[i + 1][0] if i + 1 < len(ts) else len(s)), t) for i, (a, t) in enumerate(ts)]
def compact(t): return re.sub(r"\s", "", t)

FS_CLASS = [(r"BS", "BS"), (r"IS|CIS", "IS"), (r"CF", "CF"), (r"EF|SCE", "EF")]
def _fs_key(cls):
    c = cls.replace("{XBRL}", "")
    cons = None
    m = re.match(r"(BS|IS|CIS|CF|EF)_([CS])", c)                 # 사업보고서: BS_C, IS_S2 …
    if m: return m.group(1).replace("CIS", "IS"), "연결" if m.group(2) == "C" else "별도"
    m = re.match(r"([PL])(BS|IS|EF|CF)", c)                       # 감사보고서: PBS-2:A, PIS-2:A, PEF-1, PCF-I:A (L…은 연결)
    if m: return m.group(2), "연결" if m.group(1) == "L" else None
    return None, cons

def _note_entries(heads, end, D, scope, s=""):
    out = []
    for i, h in enumerate(heads):
        r = D.lookup(h["제목"])
        e = heads[i + 1]["자리"] if i + 1 < len(heads) else end
        subs = []                                                   # 하위 번호 제목('5.1 매출채권 및 기타수취채권')이 사전에 있으면 그 코드도 이 주석의 열쇠
        if s:
            for _pos, line, tab in flat_lines(s, h["자리"], e):
                m = None if tab else re.match(r"^\s*%d\s*[\.\-]\s*\d{1,2}\.?\s*([가-힣A-Za-z].*)$" % h["번호"], line)
                if m:
                    t, in_dict = N.cut_title(m.group(1), D, loose=True)
                    if t and in_dict:
                        subs.append(t)
                        for c in D.lookup(t)["코드"]:
                            if c not in r["코드"]: r = {"코드": r["코드"] + [c], "방법": (r["방법"] + "+하위 제목") if "하위 제목" not in r["방법"] else r["방법"], "확정": False}
        out.append({"번호": h["번호"], "제목": h["제목"], "다시 찾음": h.get("다시 찾음", False), "열쇠": ["주석:" + c for c in r["코드"]], "방법": r["방법"], "확정": r["확정"], "연결별도": scope,
                    "하위 제목": subs, "자리": [h["자리"], e]})
    return out
def _absent_in_source(s, heads, n):
    """빠진 번호 n이 앞뒤 주석 사이 원문에 'n. 글자' 꼴로 한 번도 안 나오면 회사가 번호를 건너뛴 것."""
    a = max([h["자리"] for h in heads if h["번호"] < n] or [heads[0]["자리"]]); b = min([h["자리"] for h in heads if h["번호"] > n] or [len(s)])
    t = re.sub(r"<[^>]+>|&cr;", " ", s[a:b])
    return not re.search(r"(?<![\d,\.])%d\s*\.\s*[가-힣A-Za-z]" % n, t)
def _note_state(heads, cites, has_region, s=""):
    if not has_region: return {"나눔": "주석 없음", "빠진 번호": [], "가리키는데 없는 번호": []}
    if len(heads) < 3: return {"나눔": "못 나눔", "빠진 번호": [], "가리키는데 없는 번호": sorted(cites)}
    nums = [h["번호"] for h in heads]; have = set(nums)
    gaps = [n for n in range(1, max(nums) + 1) if n not in have]
    skipped = [n for n in gaps if s and _absent_in_source(s, heads, n)]
    gaps = [n for n in gaps if n not in skipped]
    skipped += [n for n in cites if n > max(nums) and s and _absent_in_source(s, heads, n)]
    missing = sorted(n for n in cites if n not in have and n not in skipped)
    return {"나눔": "빈틈없음" if not gaps and not missing else "빈틈 있음", "빠진 번호": gaps, "가리키는데 없는 번호": missing, "원문에 없는 번호": skipped}

def build(key, s, D=None):
    D = D or N.default()
    T = titles(s)
    is_biz = any(re.match(r"II\.\s*사업의\s*내용", t) for _a, _b, t in T)
    std = "K-IFRS" if s.count("한국채택국제회계기준") > s.count("일반기업회계기준") else "일반기업회계기준"
    ix = {"문서": key, "회사": (re.search(r"<COMPANY-NAME[^>]*>(.*?)</COMPANY-NAME>", s[:20000]) or [0, "?"])[1], "종류": "사업보고서" if is_biz else "감사보고서",
          "회계기준": std, "절": [], "표": [], "재무제표": [], "주석": [], "주석 상태": {}}
    for m in re.finditer(r'<TABLE-GROUP[^>]*ACLASS="([^"]+)"', s):
        cls = m.group(1)
        if cls.startswith("{XBRL}NT_") or cls == "COVER": continue
        fk, scope = _fs_key(cls)
        if fk: ix["재무제표"].append({"열쇠": "재무제표:" + fk, "연결별도": scope, "자리": m.start()})
        elif not cls.startswith("{XBRL}"): ix["표"].append({"열쇠": "표:" + cls, "자리": m.start()})
    if is_biz:
        part = ""
        for a, b, t in T:
            if re.match(r"[IVX]+\.\s", t): part = t
            ix["절"].append({"열쇠": "절:" + t, "편": part, "자리": [a, b]})
        coded = [(m.start(), m.group(1), m.group(2), clean(re.sub(r"<[^>]+>", "", m.group(3))), m.end())
                 for m in re.finditer(r'<TABLE-GROUP ACLASS="\{XBRL\}NT_([CS])_([DU]\d{6})"[^>]*>\s*<TITLE[^>]*>(.*?)</TITLE>', s, re.S)]
        if coded:                                                   # 표준 서식: 주석마다 원문에 코드가 있음
            ends = sorted([p for p, *_ in coded] + [a for a, _b, _t in T])
            for p, cs, c, t, te in coded:
                e = next((x for x in ends if x >= te), len(s))        # 그 주석 자신의 제목(te 앞)은 끝이 아님
                ix["주석"].append({"번호": int((re.match(r"\s*(\d+)", t) or [0, 0])[1]), "제목": t, "열쇠": ["주석:" + N.base(c)], "방법": "원문 코드", "확정": True,
                                  "연결별도": "연결" if cs == "C" else "별도", "자리": [p, e]})
            ix["주석 상태"] = {"서식": "표준", "나눔": "빈틈없음", "빠진 번호": [], "가리키는데 없는 번호": []}
        else:                                                       # 자유 서식: 주석 절 안에서 번호 제목으로 나눔
            states = []
            for pat, scope, fs_pat in ((r"\s*3\.\s*연결재무제표\s*주석", "연결", r"\s*2\.\s*연결재무제표"), (r"\s*5\.\s*재무제표\s*주석", "별도", r"\s*4\.\s*재무제표")):
                sec = next(((a, b) for a, b, t in T if re.match(pat, t) and b - a > 3000), None)
                if not sec: continue
                fs = next(((a, b) for a, b, t in T if re.match(fs_pat + r"\s*$", t)), None)
                heads = split_notes(s, sec[0], sec[1], D)
                ix["주석"] += _note_entries(heads, sec[1], D, scope, s)
                states.append(dict(_note_state(heads, cited_notes(s, *fs) if fs else {}, True, s), 구간=scope))
            if not states:
                ix["주석 상태"] = {"서식": "자유", "나눔": "주석 없음", "빠진 번호": [], "가리키는데 없는 번호": []}
            else:
                order = ["못 나눔", "빈틈 있음", "빈틈없음"]
                worst = min(states, key=lambda x: order.index(x["나눔"]))
                ix["주석 상태"] = {"서식": "자유", "나눔": worst["나눔"], "빠진 번호": sorted({n for x in states for n in x["빠진 번호"]}),
                                 "가리키는데 없는 번호": sorted({n for x in states for n in x["가리키는데 없는 번호"]}), "구간별": states}
    else:
        for a, b, t in T:                                           # 감사보고서: 감사의견 자리
            if re.search(r"감사인의감사보고서", compact(t)): ix["절"].append({"열쇠": "절:감사인의 감사보고서", "편": "", "자리": [a, b]})
        nt = [(a, b, t) for a, b, t in T if re.fullmatch(r"(연결)?(재무제표에대한)?주석", compact(t))]
        if not ix["재무제표"]:                                       # 표식이 없는 감사보고서(K-IFRS): 재무제표 이름만 적힌 줄로 찾음
            fa = next((x for x, _y, t in T if re.search(r"\(첨부\)|^(연결)?재무제표$", compact(t))), None)
            if fa is not None:
                fb = nt[-1][0] if nt and nt[-1][0] > fa else len(s)
                for pos, line, _tab in flat_lines(s, fa, fb):
                    c = compact(line)
                    m = re.fullmatch(r"(연결)?(재무상태표|포괄손익계산서|손익계산서|현금흐름표|자본변동표)", c)
                    if m:
                        fk = {"재무상태표": "BS", "포괄손익계산서": "IS", "손익계산서": "IS", "현금흐름표": "CF", "자본변동표": "EF"}[m.group(2)]
                        if not any(x["열쇠"] == "재무제표:" + fk for x in ix["재무제표"]):
                            ix["재무제표"].append({"열쇠": "재무제표:" + fk, "연결별도": "연결" if m.group(1) else None, "자리": pos})
        if nt:
            a = nt[-1][0]
            b = next((x for x, _y, t in T if x > a and re.search(r"외부감사실시내용|내부회계관리제도|감사인의", compact(t))), len(s))
            fs_a = next((x for x, _y, t in T if re.search(r"\(첨부\)|재무제표$", compact(t))), 0)
            has = len(clean(re.sub(r"<[^>]+>", " ", s[a:b]))) > 400
            heads = split_notes(s, a, b, D) if has else []
            ix["주석"] = _note_entries(heads, b, D, "연결" if "연결" in nt[-1][2] else None, s)
            ix["주석 상태"] = dict(_note_state(heads, cited_notes(s, fs_a, a) if has else {}, has, s), 서식="자유")
        else:                                                       # 옛 서식: '주석' 제목이 따로 없음 — 문서 전체에서 사슬을 찾음
            heads = split_notes(s, 0, len(s), D)
            ix["주석"] = _note_entries(heads, len(s), D, None, s)
            ix["주석 상태"] = dict(_note_state(heads, cited_notes(s, 0, heads[0]["자리"]) if heads else {}, True, s), 서식="자유(주석 제목 없음)")
    ix["주석 상태"]["코드 못 붙인 제목"] = [n["제목"] for n in ix["주석"] if not n["열쇠"]]
    return ix

BIZ_ONLY = ("절:", "표:")
def ask(ix, key):
    """색인에 열쇠를 묻는다 — 답은 세 가지 상태 중 하나."""
    if key.startswith("주석:"):
        hits = [n for n in ix["주석"] if key in n["열쇠"]]
        st = ix["주석 상태"]
        if hits:
            sure = any(n["확정"] for n in hits)
            return {"상태": "있음", "확정": sure, "자리": [n["자리"] for n in hits], "사유": "" if sure else "제목으로 추정(" + "·".join(sorted({n["방법"] for n in hits})) + ")"}
        if st["나눔"] == "주석 없음":
            return {"상태": "없음", "확정": True, "자리": [], "사유": "문서에 주석이 없음"}
        why = []
        if st["나눔"] == "못 나눔": why.append("주석을 번호 제목으로 나누지 못함")
        if st["빠진 번호"]: why.append("빠진 주석 번호 " + ",".join(map(str, st["빠진 번호"])))
        if st["가리키는데 없는 번호"]: why.append("재무제표가 가리키는데 못 찾은 주석 " + ",".join(map(str, st["가리키는데 없는 번호"])))
        if st["코드 못 붙인 제목"]: why.append("코드를 못 붙인 제목 " + " / ".join(st["코드 못 붙인 제목"][:5]))
        if why:
            return {"상태": "못 찾았을 수 있음", "확정": False, "자리": [], "사유": "; ".join(why)}
        return {"상태": "없음", "확정": True, "자리": [], "사유": "주석 %d개를 빈틈없이 나눴고 그 코드가 없음" % len(ix["주석"])}
    kind = "재무제표" if key.startswith("재무제표:") else "표" if key.startswith("표:") else "절"
    hits = [x for x in ix[kind] if x["열쇠"] == key]
    if hits:
        return {"상태": "있음", "확정": True, "자리": [x["자리"] for x in hits], "사유": ""}
    if key.startswith(BIZ_ONLY) and ix["종류"] != "사업보고서":
        return {"상태": "없음", "확정": True, "자리": [], "사유": "감사보고서에는 그 자리가 없음(사업보고서에만 있음)"}
    if kind == "절" and not any(re.match(r"\d+\.\s", x["열쇠"][2:]) for x in ix["절"]):
        return {"상태": "못 찾았을 수 있음", "확정": False, "자리": [], "사유": "절 제목이 표준 꼴이 아님"}
    return {"상태": "없음", "확정": True, "자리": [], "사유": "문서의 %s 목록에 없음" % kind}


@functools.lru_cache(maxsize=6)
def index_of(s):
    """원문 → 색인. 같은 원문을 여러 번 물어도 한 번만 만든다."""
    return build("", s)


def notes_for(s, codes, kw_pat=None, biz=False):
    """주석 코드(들)가 붙은 주석 → [(자리 시작, 끝, 제목, 확정)] — 사업보고서는 별도·연결 순, 그 안에서는 제목이 kw_pat에 맞는 것 먼저, 그다음 문서 순서."""
    ix = index_of(s)
    keys = {"주석:" + c for c in codes}
    hits = [n for n in ix["주석"] if keys & set(n["열쇠"])]
    scope = {"별도": 0, "연결": 1, None: 2} if biz else {None: 0, "연결": 0, "별도": 0}
    hits.sort(key=lambda n: (scope.get(n["연결별도"], 3), 0 if kw_pat and re.search(kw_pat, n["제목"]) else 1, n["자리"][0]))
    return [(n["자리"][0], n["자리"][1], n["제목"], n["확정"]) for n in hits]


def state_for(s, codes):
    """코드(들) 가운데 하나라도 있으면 있음, 모두 '없음'이면 없음, 아니면 못 찾았을 수 있음 → (상태, 사유)."""
    ix = index_of(s)
    rs = [ask(ix, "주석:" + c) for c in codes]
    if any(r["상태"] == "있음" for r in rs): return "있음", ""
    if all(r["상태"] == "없음" for r in rs): return "없음", rs[0]["사유"]
    return "못 찾았을 수 있음", next(r["사유"] for r in rs if r["상태"] == "못 찾았을 수 있음")
