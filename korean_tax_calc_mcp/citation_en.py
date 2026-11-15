"""근거 조문 인용의 영문 표기 — 규칙으로 바꾸는 결정적 변환(문장을 만들어 내지 않는다).

영문 모드(lang='en')의 엑셀에서 도구가 돌려준 근거 문자열을 읽을 수 있게 세 가지만 바꾼다.

1. 법령명: data/law_names_ko_en.json의 표(법제처 영문법령의 영문 제명)에 있는 이름만. 처음 나올 때 'Corporate Tax Act (법인세법)',
   같은 글 안에서 되풀이되면 영문만. 표에 없는 법령(영문본이 없는 시행규칙 등)은 국문 그대로 두고 missing에 올린다.
2. 조문 번호: '제98조①6호' → 'Art. 98(1)6', '제98조의7제1항제1호' → 'Art. 98-7(1)1', '별표 3' → 'Table 3',
   '부칙 제1조' → 'Addenda Art. 1', '법률 제21212호' → 'Act No. 21212'. 기본통칙 번호(98-0…2)는 그대로.
3. 서술 구절: 용어집(data/glossary_ko_en.json)에 통째로 있는 구절만('{n}'은 숫자, '{d}'는 날짜 자리). 없는 구절은 국문 그대로 두고 missing에 올린다.

호출자가 준 글에는 쓰지 않는다 — 도구가 만든 근거 문자열에만 쓴다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_LAWS = Path(__file__).parent / "data" / "law_names_ko_en.json"
_HANGUL = re.compile(r"[가-힣]")
_CIRCLED = {chr(0x2460 + i): i + 1 for i in range(20)}          # ①~⑳
_MOK = "가나다라마바사아자차카타파하"                                  # 목 → (a)~(n)
_QUALIFIER = {"단서": "proviso", "본문": "main clause", "전단": "former part", "후단": "latter part", "후문": "latter part",
              "각 호 외의 부분": "with the exception of the subparagraphs"}
# 법령명 없이 쓰는 지칭(법제처 영문법령의 일반 용어)
_GENERIC = {"시행령": "Enforcement Decree", "시행규칙": "Enforcement Rule", "부칙": "Addenda", "같은 법": "the same Act",
            "같은 법 시행령": "Enforcement Decree of the same Act", "기본통칙": "Basic Rulings", "통칙": "Basic Rulings"}
_SHORT = {"법": "Act", "영": "Decree", "규칙": "Rule"}              # '법 제42조'·'영 제53조'·'규칙 제44조'
_PROMULGATED = {"법률": "Act", "대통령령": "Presidential Decree"}


@lru_cache(maxsize=1)
def law_table() -> dict[str, str]:
    """{국문 법령명·약칭: 영문 제명} — 영문 제명을 확인한 법령만."""
    data = json.loads(_LAWS.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in data["laws"]:
        out[row["ko"]] = row["en"]
        for a in row.get("abbr") or ():
            out[a] = row["en"]
    return out


@lru_cache(maxsize=1)
def unconfirmed_laws() -> tuple[str, ...]:
    """영문본이 없어 국문 그대로 두는 법령명."""
    return tuple(json.loads(_LAWS.read_text(encoding="utf-8")).get("no_official_english") or ())


def law_name_en(ko: str) -> str | None:
    return law_table().get(ko.strip())


# ── 조문 번호 ─────────────────────────────────────────────────────────────
_HANG = r"(?:제\s?(\d{1,2})항|([①-⑳]))"
_HO = (r"(?:제\s?(\d{1,3})(?:의(\d{1,2}))?호(?:의(\d{1,2}))?(?!\s?서식)"
       rf"|(?<!\d)(\d{{1,3}})(?:의(\d{{1,2}}))?호(?:의(\d{{1,2}}))?(?!\s?서식)(?:(?=[{_MOK}]목)|(?![가-힣])))")
_MOK_RE = rf"(?:([{_MOK}])목)"
_TAIL = re.compile(rf"(\s?){_HANG}|{_HO}|{_MOK_RE}")
_JO = re.compile(r"(?:제\s?(\d{1,4})조(?:의\s?(\d{1,3}))?|§\s?(\d{1,4})(?:의(\d{1,3}))?)")
_QUAL = re.compile(r"\s?(" + "|".join(sorted(map(re.escape, _QUALIFIER), key=len, reverse=True)) + r")(?![가-힣])")
_NOT_SUBPARA = re.compile(r"(?:부령|총리령|고시|훈령|예규|조례|규정|별지)\s?$")      # '기획재정부령 제123호'·'별지 제15호'의 호는 조문의 호가 아님


def _tail(text: str, pos: int, *, after_article: bool) -> tuple[str, int]:
    """pos부터 이어지는 항·호·목(과 단서·본문 등)을 읽어 영문 꼬리와 끝 위치를 돌려준다.
    조 뒤: '(1)6(c)' / 조 없이: 'para. (1)6(c)'·'subpara. 6(c)'·'item (c)'."""
    out, had_para, had_sub, had_item, first = "", False, False, False, True
    while True:
        m = _TAIL.match(text, pos)
        if not m:
            break
        space, para_no, circled = m.group(1), m.group(2), m.group(3)
        para = para_no or (str(_CIRCLED[circled]) if circled else None)
        sub = m.group(4) or m.group(7)
        if para:
            if had_sub or had_item or (space and not (first and after_article)) or (circled and first and not after_article):
                break
            out += f"({para})" if (after_article or not first) else f"para. ({para})"
            had_para = True
        elif sub:
            if had_sub or had_item:
                break
            no = sub + "".join(f"-{x}" for x in (m.group(5) or m.group(8), m.group(6) or m.group(9)) if x)
            out += no if had_para else ((" " if after_article else "") + f"subpara. {no}")
            had_sub = True
        else:
            if had_item:
                break
            letter = f"({chr(ord('a') + _MOK.index(m.group(10)))})"
            out += letter if (had_sub or had_para) else ((" " if after_article else "") + f"item {letter}")
            had_item = True
        pos, first = m.end(), False
    q = _QUAL.match(text, pos) if (out or after_article) else None
    if q:
        out += ", " + _QUALIFIER[q.group(1)]
        pos = q.end()
    return out, pos


def _article(text: str, pos: int) -> tuple[str, int] | None:
    m = _JO.match(text, pos)
    if not m:
        return None
    no, sub = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
    tail, end = _tail(text, m.end(), after_article=True)
    return f"Art. {no}" + (f"-{sub}" if sub else "") + tail, end


_TABLE = re.compile(r"\[?별표\s?(?:(\d{1,2})(?:의(\d{1,2}))?)?\]?(?![가-힣])")
_PROM = re.compile(r"(법률|대통령령)\s?제\s?(\d{3,6})호")
_STANDALONE = re.compile(rf"제\s?\d{{1,2}}항|제\s?\d{{1,3}}(?:의\d{{1,2}})?호(?!\s?서식)|(?<![\d가-힣A-Za-z.,])\d{{1,2}}호(?:(?=[{_MOK}]목)|(?![가-힣]))|(?<![가-힣])[{_MOK}]목(?![가-힣])")
_CITE_AHEAD = r"(?=\s?(?:제\s?\d|§|\[?별표|부칙|\d{1,3}(?:의\d{1,2})?-\d{1,3}…))"


def convert_articles(text: str) -> str:
    """법령명은 건드리지 않고 조문 번호만 영문 표기로(표 기반 단위 테스트용 — Citer.convert가 같은 규칙을 쓴다)."""
    return Citer(laws=False, phrases=False).convert(text)


# ── 구절(용어집) ──────────────────────────────────────────────────────────
_SLOT = {"{n}": r"(\d[\d,]*(?:\.\d+)?)", "{d}": r"(\d{4}\.\d{1,2}\.\d{1,2}\.?)", "{t}": r"([A-Za-z_][A-Za-z0-9_\-]*)"}
_SPLIT = re.compile(r"(\s[·—→+×=/]\s|[,;:]\s|[()\[\]]|\s—$|^—\s)")
_IDENT = re.compile(r"^[가-힣]{1,12}(?:-[가-힣]{1,8})*-?\d[\w\-.]*$")     # 예규·판례 번호(국이22601-403, 대법원-2021-두-59908 …)


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


@lru_cache(maxsize=1)
def _phrases() -> tuple[dict[str, str], tuple[tuple[re.Pattern, str], ...]]:
    """용어집의 (통째 구절 {공백 없앤 국문: 영문}, 숫자·날짜 자리가 든 구절 [(정규식, 영문 틀)])."""
    from .workbook_i18n import _DATA, _NO_OFFICIAL, _UNCERTAIN
    plain: dict[str, str] = {}
    slots: list[tuple[re.Pattern, str]] = []
    for row in json.loads(_DATA.read_text(encoding="utf-8"))["terms"]:
        note = row.get("note") or ""
        ko, en = row.get("ko") or "", row.get("en") or ""
        if not en or _UNCERTAIN in note or _UNCERTAIN in en or _NO_OFFICIAL in note:
            continue
        if any(slot in ko for slot in _SLOT):
            pat = re.escape(_squash(ko))
            for slot, rx in _SLOT.items():
                pat = pat.replace(re.escape(slot), rx)
            slots.append((re.compile(pat), en))
        else:
            plain.setdefault(re.sub(r"[\s_]+", "", ko), en)
    return plain, tuple(slots)


class Citer:
    """근거 문자열 → 영문 표기. 바꾸지 못한 법령명·구절은 국문 그대로 두고 missing에 모은다.
    custom(호출자가 준 labels 표)에 그 구절이 있으면 용어집보다 먼저 쓴다."""

    def __init__(self, custom: Any = None, *, laws: bool = True, phrases: bool = True, missing: list[str] | None = None) -> None:
        self.custom = custom
        self.laws, self.phrases = laws, phrases
        self.missing: list[str] = [] if missing is None else missing      # 라벨의 '번역 없음' 목록과 한 목록으로 쓸 수 있다
        self._known = {_squash(k): v for k, v in law_table().items()}
        names = sorted(set(law_table()) | set(unconfirmed_laws()), key=len, reverse=True)
        self._law = re.compile(r"(구 )?(" + "|".join(re.escape(x).replace(r"\ ", r"\s?") for x in names) + r")(\s?시행령|\s?시행규칙)?(\s?기본통칙)?"
                               + _CITE_AHEAD)
        self._generic = re.compile(r"(구 )?(" + "|".join(sorted(map(re.escape, _GENERIC), key=len, reverse=True)) + r")" + _CITE_AHEAD)
        self._short = re.compile(r"(구 )?(법|영|규칙)\s(?=제\s?\d{1,4}조)")

    def _miss(self, s: str) -> None:
        s = s.strip()
        if s and s not in self.missing:
            self.missing.append(s)

    # ── 구절 ──
    def _phrase(self, piece: str) -> str:
        """토큰 사이에 남은 글 한 토막. 용어집에 통째로 있으면 영문, 없으면 그대로(missing)."""
        core = piece.strip(" ·")
        if not core or not _HANGUL.search(core):
            return piece
        lead, trail = piece[: len(piece) - len(piece.lstrip(" ·"))], piece[len(piece.rstrip(" ·")):]
        if self.custom is not None and core in self.custom.table:
            self.custom.used.add(core)
            return lead + self.custom.table[core] + trail
        plain, slots = _phrases()
        key = _squash(core)
        en = plain.get(key.replace("_", ""))
        if en is None:
            for pat, tmpl in slots:
                m = pat.fullmatch(key)
                if m:
                    en, vals = tmpl, list(m.groups())
                    for slot in re.findall(r"\{[ndt]\}", tmpl):
                        en = en.replace(slot, vals.pop(0) if vals else "", 1)
                    break
        if en is not None:
            return lead + en + trail
        if not _IDENT.match(core):
            self._miss(core)
        return piece

    def _rest(self, s: str) -> str:
        if not self.phrases or not _HANGUL.search(s):
            return s
        parts = _SPLIT.split(s)
        out: list[str] = []
        for i, p in enumerate(parts):
            if i % 2:                                   # 구분 기호
                if p == "(" and out and out[-1] != parts[i - 1] and not out[-1].endswith(" "):
                    out.append(" ")                     # 영문으로 바꾼 구절 바로 뒤의 '('는 한 칸 띄운다
                out.append(p)
            else:
                out.append(self._phrase(p))
        return "".join(out)

    # ── 본문 ──
    def convert(self, text: Any) -> Any:
        if not isinstance(text, str) or not (_HANGUL.search(text) or "§" in text):
            return text
        out: list[str] = []
        buf = ""                      # 토큰 사이에 남은 글
        seen: set[str] = set()        # 이 글에서 이미 병기한 법령명
        i, n = 0, len(text)

        def flush() -> None:
            nonlocal buf
            if buf:
                rest = self._rest(buf)
                if buf[0] == "(" and out and not out[-1].endswith(" "):
                    rest = " " + rest                   # 조문 바로 뒤에 붙은 설명 괄호 — 'Art. 103-52(1) (special collection …)'로 항 번호와 구별
                out.append(rest)
                buf = ""

        last: tuple[int, str] = (-1, "")      # 바로 앞 조문 토큰의 (끝 위치, 끝난 단위 'para'|'sub')

        def emit(s: str, end: int, *, gap: bool = False) -> int:
            flush()
            out.append(s + (" " if gap and end < n and text[end] != " " else ""))
            return end

        def unit(start: int, end: int) -> str:
            """그 조문 토큰이 무엇으로 끝났는지 — 뒤에 '·제4항'처럼 이어질 때 'para.'를 되풀이하지 않게."""
            piece = text[start:end]
            if re.search(r"호(?:의\d+)?$", piece):
                return "sub"
            return "para" if re.search(r"(?:항|[①-⑳])$", piece) else ""

        while i < n:
            ch = text[i]
            free = not i or not _HANGUL.match(text[i - 1])       # 앞 글자가 한글이면 낱말 중간 — 법령명·지칭으로 보지 않는다
            if free:
                m = self._law.match(text, i) if self.laws else None
                if m:
                    whole = re.sub(r"\s+", " ", text[i:m.end()].strip())
                    name = re.sub(r"\s+", " ", (m.group(2) + (m.group(3) or "")).strip())
                    en = self._known.get(_squash(name))
                    if en is None:                       # 영문 제명을 확인하지 못한 법령 — 국문 그대로
                        self._miss(name)
                        flush()
                        out.append(text[i:m.end()])
                        i = m.end()
                        continue
                    shown = ("former " if m.group(1) else "") + en + (" Basic Rulings" if m.group(4) else "")
                    i = emit(shown if whole in seen else f"{shown} ({whole})", m.end(), gap=True)
                    seen.add(whole)
                    continue
                m = self._generic.match(text, i)
                if m:
                    i = emit(("former " if m.group(1) else "") + _GENERIC[m.group(2)], m.end(), gap=True)
                    continue
                m = self._short.match(text, i)
                if m and (i == 0 or text[i - 1] in " (·,"):
                    i = emit(("former " if m.group(1) else "") + _SHORT[m.group(2)] + " ", m.end())
                    continue
            if ch in "법대" and free:
                m = _PROM.match(text, i)
                if m:
                    i = emit(f"{_PROMULGATED[m.group(1)]} No. {m.group(2)}", m.end())
                    continue
            if ch in "제§":
                got = _article(text, i)
                if got:
                    if ch == "§" and i and _HANGUL.match(text[i - 1]):
                        buf += " "                       # '법칙§44' → '법칙 Art. 44'
                    last = (got[1], unit(i, got[1]))
                    i = emit(*got)
                    continue
            if ch in "[별" and free:
                m = _TABLE.match(text, i)
                if m and "별표" in m.group(0):
                    i = emit("Table" + (f" {m.group(1)}" + (f"-{m.group(2)}" if m.group(2) else "") if m.group(1) else ""), m.end())
                    continue
            if (ch == "제" or ch.isdigit() or ch in _MOK) and _STANDALONE.match(text, i) and not _NOT_SUBPARA.search(text[max(0, i - 8):i]):
                tail, end = _tail(text, i, after_article=False)
                if tail:
                    if last[1] and text[last[0]:i] in ("·", "~", "∼", ", "):      # '제3항·제4항' → '(3)·(4)', '1호·2호' → 'subpara. 1·2'
                        if last[1] == "para" and tail.startswith("para. "):
                            tail = tail[len("para. "):]
                        elif last[1] == "sub" and tail.startswith("subpara. "):
                            tail = tail[len("subpara. "):]
                    last = (end, unit(i, end))
                    i = emit(tail, end)
                    continue
            buf += ch
            i += 1
        flush()
        return re.sub(r" {2,}", " ", "".join(out))


def cite_en(text: Any, citer: "Citer | None" = None) -> Any:
    """근거 문자열 하나를 영문 표기로(citer를 주지 않으면 한 번 쓰고 버리는 Citer)."""
    return (citer or Citer()).convert(text)
