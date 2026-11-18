"""사업보고서 'II. 사업의 내용 > 4. 매출 및 수주상황'에서 판매조직·판매경로·판매방법 및 조건·판매전략·주요 매출처를 나눠 뽑는다.

기능·위험 분석에서 거래단계·판매채널을 볼 때 쓰는 자리. '1. 사업의 개요'에는 채널이 거의 없고 이 절에 있다
(2026-11-18 화장품 업종 상장 32곳: 판매경로가 원문에 31곳, 사업의 개요 앞 1,500자에 2곳).
- 글은 원문 그대로(소제목 아래 문단과 표 행 '셀 | 셀'), 요약하지 않는다.
- 판매경로 표에 비중(%) 열이 있으면 경로별 비중을 숫자로 읽고 합계를 검산한다(100% ± 2). 안 맞으면 숫자를 내지 않고 사유를 낸다.
- 비상장사 감사보고서에는 이 절이 없다 — 부르지 않는다.
Claude 작성(2026-11-18)."""
import re

from .statements import title_sections, txt

TOPICS = (("판매조직", re.compile(r"판매\s*조직|영업\s*조직")),
          ("판매경로", re.compile(r"판매\s*경로|유통\s*경로|판매\s*채널|유통\s*채널")),
          ("판매방법", re.compile(r"판매\s*방법|판매\s*조건|대금\s*(회수|결제)\s*조건")),
          ("판매전략", re.compile(r"판매\s*전략|영업\s*전략|마케팅\s*전략")),
          ("주요 매출처", re.compile(r"주요\s*(매출처|거래처|고객)")),
          ("수주상황", re.compile(r"수주\s*(상황|현황|총액|잔고)")),
          ("매출실적", re.compile(r"매출\s*실적|매출\s*현황")))
_NUM = r"(?:[가-하]\s*[.)]|\(\s*[가-하]\s*\)|\(?\s*\d{1,2}\s*[.)]|[①-⑳])"
_NUMBERING = re.compile(r"^\s*(?:" + _NUM + r"|\[[^\]]{1,12}\]|[-▶■□◆○●※*·]+)\s*")
_INLINE_HEAD = re.compile(_NUM + r"\s*(?=" + "|".join(pat.pattern for _n, pat in TOPICS) + ")")   # 문단 안에 붙은 소제목('… 있습니다.나. 판매경로 …')
_FILLER = re.compile(r"^(?:\s*(?:및|등|현황|상황|에\s*관한\s*사항|별\s*매출액?\s*비중|\(\s*단위[^)]*\)))+")   # 소제목 꼬리말
IMAGE_MARK = "(그림 — 글로 읽을 수 없음)"
HEAD_MAX = 60          # 소제목 줄로 보는 길이
TEXT_MAX = 1500        # 주제마다 넘기는 글 길이
SHARE_TOL = 2.0        # 비중 합계 허용 오차(%p)
_PCT = re.compile(r"^\(?\s*(-?\d{1,3}(?:\.\d+)?)\s*%?\s*\)?$")
_SHARE_HEAD = re.compile(r"비\s*중|비\s*율|구성\s*비|점유")
_TOTAL = re.compile(r"^(합\s*계|총\s*계|계|소\s*계|total)$", re.I)


def _clean(x):
    return re.sub(r"\s+", " ", txt(x)).strip()


def section(s):
    """'4. 매출 및 수주상황' 절의 원문(HTML). 없으면 ''."""
    secs = title_sections(s)
    start = next((i for i, (_a, _b, t) in enumerate(secs) if re.match(r"\s*I{1,2}\.\s*사업의\s*내용", t)), None)
    if start is None:
        return ""
    for a, b, t in secs[start + 1:]:
        if re.match(r"\s*(I{1,3}|IV|V)\.\s", t):
            break
        if re.search(r"매출\s*및\s*수주", t):
            return s[a:b]
    a, b, _t = secs[start]                                # 옛 서식 — 'II. 사업의 내용'이 하위 제목 없이 한 덩어리
    return s[a:b] if b - a > 2000 else ""


def units(sec):
    """절 HTML → 문서 순서의 단위 [{'kind': 'p', 't'} | {'kind': 'table', 'rows': [[셀]]}]."""
    sec = re.sub(r"<TITLE[^>]*>.*?</TITLE>", " ", sec, flags=re.S)
    out = []
    for m in re.finditer(r"<TABLE[^>]*>.*?</TABLE>|<P[^>]*>.*?</P>|<IMG[^>]*>", sec, re.S):
        piece = m.group(0)
        if piece.startswith("<IMG"):
            out.append({"kind": "p", "t": IMAGE_MARK})
            continue
        if piece.startswith("<TABLE"):
            rows = []
            for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", piece, re.S):
                cells = [_clean(c) for c in re.findall(r"<T[DEHU][^>]*>(.*?)</T[DEHU]>", tr, re.S)]
                if any(cells):
                    rows.append(cells)
            if rows:
                out.append({"kind": "table", "rows": rows, "grid": _grid(piece)})
        else:
            t = _clean(piece)
            cuts = [0] + [m.start() for m in _INLINE_HEAD.finditer(t) if m.start() > 0] + [len(t)]
            for a, b in zip(cuts, cuts[1:]):               # 한 문단에 소제목이 여럿 붙어 있으면 소제목마다 나눔
                if t[a:b].strip():
                    out.append({"kind": "p", "t": t[a:b].strip()})
    return out


def _head_topics(t):
    """소제목 줄이 가리키는 주제들 — 번호를 떼고 줄 앞쪽에서 주제 낱말을 찾는다. 반환 (주제 목록, 소제목 뒤에 붙은 본문)."""
    body = t
    for _ in range(3):                                    # '나. (2) 판매경로'처럼 번호가 겹침
        body = _NUMBERING.sub("", body, count=1)
    hits = sorted((m.start(), m.end(), name) for name, pat in TOPICS for m in [pat.search(body[:HEAD_MAX])] if m)
    if not hits or hits[0][0] > 0:                        # 번호를 뗀 줄이 주제 낱말로 시작해야 소제목('당사의 판매조직은 …'은 본문)
        return [], t
    if len(t) <= HEAD_MAX:                                # 짧은 소제목 줄 — '판매경로 및 판매방법 등'처럼 주제가 여럿일 수 있음
        rest = _FILLER.sub("", body[hits[-1][1]:]).strip(" :：-")
        return [h[2] for h in hits], (rest if len(rest) >= 4 else "")
    rest = _FILLER.sub("", body[hits[0][1]:]).strip(" :：-")   # 긴 문단이 주제 낱말로 시작 — '판매전략당사의 …'처럼 소제목이 본문에 붙음
    return [hits[0][2]], rest


def _style(t):
    """소제목 번호 모양 — 같은 모양이 다시 나오면 같은 층의 다음 소제목."""
    t = t.lstrip()
    for name, pat in (("가.", r"[가-하]\s*\."), ("가)", r"[가-하]\s*\)"), ("(가)", r"\(\s*[가-하]\s*\)"), ("(1)", r"\(\s*\d{1,2}\s*\)"),
                      ("1)", r"\d{1,2}\s*\)"), ("1.", r"\d{1,2}\s*\."), ("①", r"[①-⑳]")):
        if re.match(pat, t):
            return name
    return ""


_STYLE_ORDER = ["1.", "가.", "(1)", "1)", "(가)", "가)", "①"]


def split_topics(us):
    """단위를 주제별로 나눈다. 반환 {주제: [단위…]} — 소제목이 나오기 전의 단위는 버린다.
    '판매경로 및 판매방법 등' 아래가 다시 '(1) 판매조직 (2) 판매전략'으로만 나뉘어 판매경로 자리가 비면, 그 윗소제목 아래 전체를 판매경로·판매방법에 넣는다."""
    out, cur = {}, []
    parent = None                                         # [윗소제목 주제들, 번호 모양, 그 아래 단위들]
    parents, seen = [], []

    def not_below(st, pst):                               # st가 pst와 같은 층이거나 위층인가 — 둘 다 이미 나온 모양이면 먼저 나온 쪽이 위층, 아니면 관행 순서
        order = seen if st in seen and pst in seen else _STYLE_ORDER
        return order.index(st) <= order.index(pst)

    for u in us:
        if u["kind"] == "p":
            topics, rest = _head_topics(u["t"])
            st = _style(u["t"])
            if st and (topics or len(u["t"]) <= HEAD_MAX):
                if parent and parent[1] and not_below(st, parent[1]):
                    parent = None                         # 같은 층이나 위층의 다음 소제목 — 윗소제목 범위가 끝남
                    if not topics:
                        cur = []
                if st not in seen:
                    seen.append(st)
            if topics:
                if parent and not st:
                    parent = None
                if parent is None and len(topics) >= 2:
                    parent = [topics, st, []]
                    parents.append(parent)
                cur = topics
                for k in cur:
                    out.setdefault(k, [])
                if rest:
                    for k in cur:
                        out[k].append({"kind": "p", "t": rest})
                    if parent and parent[0] is not topics:
                        parent[2].append({"kind": "p", "t": u["t"]})
                elif parent and parent[0] is not topics:
                    parent[2].append(u)
                continue
        elif not cur or cur == ["매출실적"]:               # 소제목 없이 표 머리행에 '판매경로' 열이 있는 표
            head = " ".join(u["rows"][0])
            hit = [name for name, pat in TOPICS[:5] if pat.search(head)]
            if hit:
                for k in hit:
                    out.setdefault(k, []).append(u)
                continue
        for k in cur:
            out[k].append(u)
        if parent and cur is not parent[0]:
            parent[2].append(u)
    for topics, _st, acc in parents:
        for k in topics:
            if not out.get(k) and acc:
                out[k] = acc
    return out


def _text(us):
    lines = []
    for u in us:
        if u["kind"] == "p":
            lines.append(u["t"])
        else:
            lines += [" | ".join(c for c in r if c) for r in u["rows"]]
    out, n = [], 0
    for ln in lines:                                      # 줄 중간에서 자르지 않음
        if n + len(ln) + 1 > TEXT_MAX:
            break
        out.append(ln)
        n += len(ln) + 1
    return "\n".join(out), len(out) < len(lines)


def _grid(table_html):
    """표 HTML → 칸을 다 채운 격자(세로·가로로 합친 칸은 같은 글을 되풀이)."""
    grid, carry = [], {}                                  # carry: {열: [남은 행 수, 글]}
    for tr in re.findall(r"<TR[^>]*>(.*?)</TR>", table_html, re.S):
        row, j = [], 0
        cells = re.findall(r"<(T[DEHU])([^>]*)>(.*?)</\1>", tr, re.S)
        k = 0
        while k < len(cells) or j in carry:
            if j in carry:
                row.append(carry[j][1])
                carry[j][0] -= 1
                if carry[j][0] <= 0:
                    del carry[j]
                j += 1
                continue
            _tag, attrs, inner = cells[k]
            k += 1
            t = _clean(inner)
            rs = int((re.search(r'ROWSPAN="?(\d+)', attrs, re.I) or [0, 1])[1])
            cs = int((re.search(r'COLSPAN="?(\d+)', attrs, re.I) or [0, 1])[1])
            for _ in range(max(cs, 1)):
                row.append(t)
                if rs > 1:
                    carry[j] = [rs - 1, t]
                j += 1
        if any(row):
            grid.append(row)
    return grid


def _pct(c):
    """칸 → 비중 값. '74%', '17.30', '138,747 (58.7)', '-'."""
    c = c.replace(" ", "")
    if c in ("-", "－", "—"):
        return 0.0
    m = re.match(r"^-?[\d,]+\((-?\d{1,3}(?:\.\d+)?)%?\)$", c) or _PCT.match(c)
    if not m:
        return None
    v = float(m.group(1))
    return v if -0.01 <= v <= 100.01 else None


def _is_total(c):
    return bool(_TOTAL.match(re.sub(r"[\s()*\d주]", "", c)))


def _period_rank(label):
    m = re.findall(r"(?:제\s*)?(\d{1,4})\s*(?:기|년)", label)
    return max((int(x) for x in m), default=-1)


def _table_shares(grid):
    """격자 표 → ({'기간', '행': [{경로, 비중}]} | None, 사유)."""
    if len(grid) < 2:
        return None, "행이 적음"
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    # 가로형: '비중' 행의 값들과 바로 위 행의 이름들
    for i in range(1, len(grid)):
        if _SHARE_HEAD.search(grid[i][0]) and len(grid[i][0]) <= 12:
            vals = [_pct(c) for c in grid[i][1:]]
            if vals and all(v is not None for v in vals) and any("%" in c for c in grid[i][1:]):
                rows = [{"경로": grid[i - 1][j + 1], "비중": v} for j, v in enumerate(vals) if not _is_total(grid[i - 1][j + 1])]
                return {"기간": "", "행": rows}, ""
    # 세로형: 머리행 수 = 처음으로 비중 값이 나오는 행 앞까지
    def data_row(r):
        return any(_pct(c) is not None and re.search(r"\d", c) for c in r)
    first = next((i for i, r in enumerate(grid) if data_row(r) and i > 0), None)
    if first is None:
        return None, "숫자 행 없음"
    heads = [" ".join(dict.fromkeys(grid[i][j] for i in range(first) if grid[i][j])) for j in range(width)]
    body = grid[first:]
    cand = []
    for j in range(width):
        col = [r[j] for r in body]
        vals = [_pct(c) for c in col]
        filled = [v for v, c in zip(vals, col) if v is not None]
        marked = _SHARE_HEAD.search(heads[j]) or sum("%" in c or re.search(r"\(\d", c) is not None for c in col) >= max(2, len(col) // 2)
        if marked and len(filled) >= max(2, len(col) * 2 // 3):
            cand.append(j)
    if not cand:
        return None, "비중 열 없음"
    j = max(cand, key=lambda x: (_period_rank(heads[x]), -x))    # 가장 최근 기간 열(기간 표시가 없으면 맨 왼쪽)
    lab_cols = [k for k in range(min(cand)) if not all(_pct(r[k]) is not None or re.fullmatch(r"[\d,.\-()%\s]*", r[k]) for r in body)]
    rows = []
    for r in body:
        labs = [r[k] for k in lab_cols if r[k] and r[k] != "-" and not re.fullmatch(r"[\d.\s]+", r[k])]
        labs = [x for i, x in enumerate(labs) if i == 0 or x != labs[i - 1]]      # 가로로 합친 칸이 되풀이된 것만 뺌
        v = _pct(r[j])
        if v is None or not labs or any(_is_total(x) for x in labs):
            continue
        rows.append({"경로": " > ".join(labs), "비중": v})
    return {"기간": re.sub(r"\s+", " ", heads[j])[:30], "행": rows}, ""


def _check(rows):
    """비중 검산 — 합계가 100% ± SHARE_TOL이면 통과. 첫 이름 묶음마다 100%인 표(품목별 내수·수출 비중 등)도 통과."""
    if len(rows) < 2:
        return "", "행이 하나뿐"
    total = sum(r["비중"] for r in rows)
    if abs(total - 100) <= SHARE_TOL:
        return f"합계 {total:.1f}%", ""
    depth = max(len(r["경로"].split(" > ")) for r in rows)
    for d in range(1, depth):
        groups = {}
        for r in rows:
            groups.setdefault(" > ".join(r["경로"].split(" > ")[:d]), []).append(r["비중"])
        if len(groups) >= 2 and all(len(v) >= 2 and abs(sum(v) - 100) <= SHARE_TOL for v in groups.values()):
            return f"묶음 {len(groups)}개가 저마다 합계 100%(앞 이름 {d}칸 기준)", ""
    return "", f"비중 합계가 100%가 아님({total:.1f}%) — 숫자를 내지 않음"


_INLINE_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")


def _text_shares(us):
    """글로 적은 비중 — '공장 → 도매상 → 소비자 : 30%', '(매출액 비중 : 8.4%)'. 값 앞의 글을 경로 이름으로."""
    text = "\n".join(u["t"] for u in us if u["kind"] == "p") + "\n" + "\n".join(" | ".join(r) for u in us if u["kind"] == "table" and len(u["rows"][0]) == 1 for r in u["rows"])
    rows, last = [], 0
    for m in _INLINE_PCT.finditer(text):
        lab = re.sub(r"[(（]?\s*(매출액?\s*)?(비중|비율)\s*[:：]?\s*$", "", text[last:m.start()]).strip(" \n:：()（）,.")
        lab = re.sub(_NUM, " ", lab).strip() if lab else lab
        last = m.end()
        if lab:
            rows.append({"경로": re.sub(r"\s+", " ", lab)[-80:], "비중": float(m.group(1))})
    if any(len(r["경로"]) > 50 or re.search(r"습니다|입니다|있으며|하며|다음과|으로\s*구성", r["경로"]) for r in rows):
        return []                                         # 경로 이름이 아니라 문장 — 우연히 합계가 맞는 숫자를 비중으로 읽지 않음
    return rows


def _shares(us):
    """판매경로 단위 → ([{'기간', '묶음', '행': [{경로, 비중}], '검산'}], 사유). 검산을 통과한 표만 낸다."""
    out, why, head = [], "비중이 적힌 표·글 없음", ""
    for u in us:
        if u["kind"] == "p":
            if len(u["t"]) <= 30:                         # '[자전거사업 부문]' 같은 표 앞 줄만 묶음 이름으로
                head = u["t"] if re.search(r"^\[.*\]$|부문$|사업부$|사업$", u["t"]) and not re.match(r"[(（※*]", u["t"]) else head
            continue
        if not any(_SHARE_HEAD.search(c) or "%" in c for r in u["grid"] for c in r):
            continue
        got, note = _table_shares(u["grid"])
        if not got or not got["행"]:
            why = f"비중 표를 읽지 못함({note or '행 없음'})"
            continue
        ok, bad = _check(got["행"])
        if bad:
            why = bad
            continue
        out.append({"기간": got["기간"], "묶음": head, "행": got["행"], "검산": ok})
    if not out:
        rows = _text_shares(us)
        ok, bad = _check(rows) if rows else ("", "")
        if ok:
            out.append({"기간": "", "묶음": "", "행": rows, "검산": ok + "(글에서 읽음)"})
    return out, ("" if out else why)


def extract(s):
    """사업보고서 원문 → {'found': bool, 'topics': {주제: {'text', 'truncated'}}, 'shares': [{경로, 비중}], 'shares_note', 'problems': [..]}."""
    sec = section(s)
    if not sec:
        return {"found": False, "topics": {}, "shares": [], "shares_note": "", "problems": ["매출 및 수주상황 절 없음"]}
    parts = split_topics(units(sec))
    topics = {}
    for name, _pat in TOPICS[:5]:
        if parts.get(name):
            t, cut = _text(parts[name])
            if t:
                topics[name] = {"text": t, "truncated": cut}
    shares, note = _shares(parts.get("판매경로", []))
    problems = []
    plain = _clean(sec)
    for name, pat in TOPICS[:5]:
        if name not in topics and re.search(_NUM + r"\s*(?:" + pat.pattern + ")", plain):
            problems.append(f"절에 '{name}' 소제목이 있으나 내용을 뽑지 못함")
    return {"found": bool(topics), "topics": topics, "shares": shares, "shares_note": note, "problems": problems}
