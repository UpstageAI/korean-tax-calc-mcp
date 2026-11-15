"""verify_workbook — 직접 만든 통합 문서(xlsx)의 금액 칸을 계산 도구 결과와 대조한다.

통합 문서의 틀은 호출자가 직접 짜도 된다. 이 모듈은 그 파일을 고치지 않고, 칸 값을 계산 도구 결과와 견주어 일치·불일치와
"계산 도구 대조를 거치지 않은 금액"을 알려 준다. 판단 문구를 만들지 않는다 — 두 값과 차이, 도구가 돌려준 근거 문자열만 옮긴다.

하는 일
1. 값 읽기: 저장된 값(캐시 값)이 있으면 그 값, 없으면 캐시 값 계산기(workbook_cache)로 계산, 계산하지 못하면 '읽지 못함'.
2. checks마다 계산 도구를 실제로 호출해(같은 tool + args는 한 번) 결과 키의 값과 칸 값을 비교.
3. 검증 범위: 금액으로 보이는 수식 칸 가운데 대조된 칸과 수식으로 이어지지 않은 칸을 모은다(기준은 아래 `_Coverage`).
4. 부가 점검: 저장된 값이 없는 수식 칸, 저장된 값과 다시 계산한 값이 다른 칸, 원 미만 소수가 남은 금액 칸, 오류 칸, 수식 열에 직접 적은 숫자.
5. annotate: 사본에 대조 결과 시트('검산' / 'Tool check')를 붙이고 모든 수식 칸에 값을 채운다 — 원래 시트의 저장된 값은 그대로 보존.
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import json as _json
import os
import re as _re
from typing import Any

from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import Token
from openpyxl.utils import column_index_from_string, get_column_letter

AMOUNT_MIN = 1000          # 이 값 이상인 숫자 칸을 '금액으로 보이는 칸'으로 본다(세율·일수·건수를 거르는 단순한 기준)
MAX_CHECKS, MAX_LIST, MAX_RANGE = 200, 80, 20000
_NO_TOOLS = frozenset({"export_workbook", "verify_workbook", "find_tool"})
_A1 = _re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d{1,7})(?::\$?([A-Za-z]{1,3})\$?(\d{1,7}))?$")
_LINK = _re.compile(r"^=\s*\+?\s*(?:'(?:[^']|'')+'!|[^'!()+\-*/,&<>=^%\s]+!)?\$?[A-Za-z]{1,3}\$?\d{1,7}\s*$")
_SHEET_REF = _re.compile(r"^(?:'((?:[^']|'')+)'|([^'!]+))!(.+)$", _re.S)

_TXT = {
    "sheet": ("검산", "Tool check"),
    "title": ("검산 — 통합 문서의 금액과 계산 도구 결과 대조", "Tool check — workbook figures against the calculation tools"),
    "sub": ("칸 값과 계산 도구 결과를 견준 표. 원래 시트의 값·수식·서식은 그대로. 두 값과 차이만 적으며 원인은 판단하지 않음.",
            "Cell values compared with calculation tool results. The original sheets are unchanged. Only the two values and the difference are shown."),
    "hdr": (("칸", "항목", "통합 문서 값", "도구 값", "차이", "판정", "도구 · 결과 키", "근거(도구가 돌려준 글)"),
            ("Cell", "Item", "Workbook value", "Tool value", "Difference", "Result", "Tool · result key", "Basis (as returned by the tool)")),
    "match": ("일치", "Match"), "diff": ("불일치", "Mismatch"), "unread": ("읽지 못함", "Not readable"), "tool_err": ("도구 오류", "Tool error"),
    "scope": ("검증 범위", "Scope of the check"),
    "scope_line": ("대조 {n}건 — 일치 {a} / 불일치 {b} / 읽지 못함 {c} / 도구 오류 {d}. 계산 도구 대조를 거치지 않은 금액 {u}칸.",
                   "{n} check(s) — match {a} / mismatch {b} / not readable {c} / tool error {d}. Amounts not checked against a calculation tool: {u} cell(s)."),
    "rule": ("대조를 거친 것으로 보는 칸: 일치한 칸, 그 칸의 수식이 가리키는 칸, 입력 숫자, 그런 칸들의 링크·합·차. 그 밖의 수식 칸 가운데 값이 1,000 이상인 칸(날짜·비율 서식 제외)을 아래에 적음.",
             "Treated as checked: matched cells, the cells their formulas refer to, entered numbers, and links, sums and differences of those. Any other formula cell of 1,000 or more (dates and percentages excluded) is listed below."),
    "unchecked": ("계산 도구 대조를 거치지 않은 금액", "Amounts not checked against a calculation tool"),
    "un_hdr": (("칸", "항목", "값"), ("Cell", "Item", "Value")),
    "more": ("… 그 밖 {n}칸", "… and {n} more"),
    "none": ("없음", "None"),
    "extra": ("부가 점검", "Other checks"),
    "x_nocache": ("저장된 값이 없는 수식 칸(휴대폰·미리보기에서 0이나 빈칸으로 보임) — 이 사본에는 값을 채움", "Formula cells with no stored value (blank or 0 in phone viewers and previews) — filled in this copy"),
    "x_stale": ("저장된 값과 다시 계산한 값이 다른 수식 칸", "Formula cells whose stored value differs from the recalculated value"),
    "x_frac": ("원 미만 소수가 남은 금액 칸", "Amount cells with a fraction of a won"),
    "x_error": ("오류 값 칸(#REF! 등)", "Cells holding an error value (#REF! etc.)"),
    "x_hard": ("수식 열에 직접 적은 숫자(어떤 수식도 가리키지 않음)", "Numbers typed into a formula column (no formula refers to them)"),
    "x_skip": ("값을 계산하지 못한 수식 칸(저장된 값도 없음)", "Formula cells that could not be calculated (and hold no stored value)"),
}
LIMITS = [
    "금액 판정은 값이 1,000 이상인 숫자 칸(날짜·비율 서식 제외)이라는 단순한 기준 — 1,000 미만 금액과 글로 적은 금액은 보지 않음",
    "대조를 거친 것으로 보는 범위는 수식의 모양으로 정함(일치한 칸, 그 칸이 가리키는 칸, 입력 숫자, 그런 칸들의 링크·합·차) — 곱셈·반올림이 든 수식 칸은 따로 대조해야 함",
    "입력 숫자(수식이 아닌 칸)가 원자료와 맞는지는 보지 않음",
    "저장된 값이 있는 칸은 그 값을 읽음 — 수식을 고친 뒤 다시 계산하지 않고 저장한 파일은 '저장된 값과 다시 계산한 값이 다른 칸'에 나타남",
    "사본은 openpyxl로 다시 쓰므로 차트·그림·매크로 같은 요소는 원본과 다를 수 있음(칸의 값·수식·서식은 그대로)",
]


def _t(key: str, en: bool, **kw):
    v = _TXT[key][1 if en else 0]
    return v.format(**kw) if kw else v


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class _Book:
    """통합 문서의 값(저장된 값 우선, 없으면 다시 계산)과 수식 참조."""

    def __init__(self, path: str):
        import openpyxl
        from .workbook_cache import XlError, evaluate_workbook
        self.wb = openpyxl.load_workbook(path)
        cached = openpyxl.load_workbook(path, data_only=True)
        calc, skipped = evaluate_workbook(self.wb)
        self.skipped = {(s, c): why for s, c, why in skipped}
        self.cached: dict[tuple[str, str], Any] = {}      # 수식 칸의 저장된 값
        self.calc: dict[tuple[str, str], Any] = {}        # 수식 칸의 다시 계산한 값
        self.formulas: dict[tuple[str, str], str] = {}
        for ws in self.wb.worksheets:
            wc = cached[ws.title]
            for (row, col), c in ws._cells.items():
                if c.data_type != "f":
                    continue
                key = (ws.title, f"{get_column_letter(col)}{row}")
                self.formulas[key] = c.value if isinstance(c.value, str) else ""
                v = wc.cell(row, col).value
                if v is not None:
                    self.cached[key] = v
                x = (calc.get(ws.title) or {}).get(key[1])
                if x is not None:
                    self.calc[key] = x.code if isinstance(x, XlError) else x

    def value(self, sheet: str, coord: str) -> tuple[Any, bool]:
        """→ (값, 읽었는지). 수식 칸은 저장된 값, 없으면 다시 계산한 값."""
        key = (sheet, coord)
        if key in self.formulas:
            if key in self.cached:
                return self.cached[key], True
            if key in self.calc:
                return self.calc[key], True
            return None, False
        return self.wb[sheet][coord].value, True

    def label(self, sheet: str, coord: str) -> str:
        """그 칸의 왼쪽에서 가장 가까운 글(없으면 빈 글)."""
        ws = self.wb[sheet]
        m = _A1.match(coord)
        col, row = column_index_from_string(m.group(1).upper()), int(m.group(2))
        for j in range(col - 1, 0, -1):
            v = ws.cell(row, j).value
            if isinstance(v, str) and v.strip() and not v.startswith("="):
                return v.strip()
        return ""

    def locate(self, cell: str) -> tuple[str, str] | None:
        """'시트!칸'·"'시트 이름'!$B$9"·정의된 이름 → (시트, 칸). 못 찾으면 None."""
        text = str(cell or "").strip()
        dn = self.wb.defined_names.get(text) if "!" not in text else None
        if dn is not None and dn.attr_text:
            text = dn.attr_text
        m = _SHEET_REF.match(text)
        if not m:
            return None
        name = (m.group(1).replace("''", "'") if m.group(1) else m.group(2)).strip()
        a1 = _A1.match(m.group(3).strip())
        if not a1 or a1.group(3):
            return None
        sheet = next((n for n in self.wb.sheetnames if n == name), None) or next((n for n in self.wb.sheetnames if n.casefold() == name.casefold()), None)
        return (sheet, f"{a1.group(1).upper()}{a1.group(2)}") if sheet else None

    def refs(self, sheet: str, coord: str) -> tuple[list[tuple[str, str]], bool]:
        """수식이 가리키는 칸 목록과, 그 수식이 링크·합·차(+, −, SUM, 괄호, 숫자)만으로 된 것인지."""
        f = self.formulas.get((sheet, coord)) or ""
        out: list[tuple[str, str]] = []
        simple = bool(f)
        try:
            items = Tokenizer(f).items
        except Exception:
            return [], False
        for t in items:
            if t.type == Token.OPERAND:
                if t.subtype == Token.RANGE:
                    got = self._expand(sheet, t.value)
                    if got is None:
                        simple = False
                    else:
                        out += got
                elif t.subtype != Token.NUMBER:
                    simple = False
            elif t.type == Token.FUNC:
                if t.subtype == Token.OPEN and t.value[:-1].strip().upper() != "SUM":
                    simple = False
            elif t.type in (Token.OP_IN, Token.OP_PRE):
                if t.value not in ("+", "-"):
                    simple = False
            elif t.type in (Token.OP_POST, Token.ARRAY):
                simple = False
        return out, simple

    def _expand(self, sheet: str, ref: str) -> list[tuple[str, str]] | None:
        m = _SHEET_REF.match(ref)
        if m:
            name = (m.group(1).replace("''", "'") if m.group(1) else m.group(2)).strip()
            sheet2 = next((n for n in self.wb.sheetnames if n.casefold() == name.casefold()), None)
            if sheet2 is None:
                return None
            sheet, ref = sheet2, m.group(3)
        elif ref in self.wb.defined_names and self.wb.defined_names[ref].attr_text:
            return self._expand(sheet, self.wb.defined_names[ref].attr_text)
        a = _A1.match(ref.strip())
        if not a:
            return None
        c1, r1 = column_index_from_string(a.group(1).upper()), int(a.group(2))
        c2, r2 = (column_index_from_string(a.group(3).upper()), int(a.group(4))) if a.group(3) else (c1, r1)
        if (abs(c2 - c1) + 1) * (abs(r2 - r1) + 1) > MAX_RANGE:
            return None
        return [(sheet, f"{get_column_letter(c)}{r}") for r in range(min(r1, r2), max(r1, r2) + 1) for c in range(min(c1, c2), max(c1, c2) + 1)]


def _is_amount(cell, v: Any) -> bool:
    if not _num(v) or abs(v) < AMOUNT_MIN:
        return False
    from openpyxl.styles.numbers import is_date_format
    fmt = str(cell.number_format or "")
    return "%" not in fmt and not is_date_format(fmt) and not isinstance(cell.value, (_dt.date, _dt.datetime))


def _coverage(book: _Book, matched: set[tuple[str, str]], checked: set[tuple[str, str]]) -> list[dict]:
    """계산 도구 대조를 거치지 않은 금액 칸. 대조를 거친 것으로 보는 칸: 일치한 칸, 그 칸의 수식이 (이어서) 가리키는 칸, 입력 숫자(수식이 아닌 칸),
    그런 칸들만 가리키는 링크·합·차 수식. 그 밖의 수식 칸 가운데 금액으로 보이는 칸을 돌려준다(대조했지만 불일치·읽지 못한 칸은 따로 보고되므로 빼고,
    다른 칸 하나를 그대로 가리키는 링크도 뺀다 — 가리키는 칸이 목록에 오른다)."""
    ok: dict[tuple[str, str], bool] = {}
    todo = list(matched)
    while todo:                       # 일치한 칸이 가리키는 칸은 그 값에 쓰인 것 — 함께 대조된 것으로 본다
        k = todo.pop()
        if ok.get(k):
            continue
        ok[k] = True
        if k in book.formulas:
            todo += [r for r in book.refs(*k)[0] if not ok.get(r)]

    def covered(k, active: set) -> bool:
        if k in ok:
            return ok[k]
        if k not in book.formulas:
            return True               # 입력 숫자·글·빈칸
        if k in active:
            return False
        active.add(k)
        refs, simple = book.refs(*k)
        res = simple and all(covered(r, active) for r in refs)
        active.discard(k)
        ok[k] = res
        return res

    out = []
    for ws in book.wb.worksheets:
        for (row, col), c in sorted(ws._cells.items()):
            k = (ws.title, f"{get_column_letter(col)}{row}")
            if k not in book.formulas or k in checked:
                continue
            v, read = book.value(*k)
            if not read or not _is_amount(c, v):
                continue
            if _LINK.match(book.formulas[k]):     # 다른 칸 하나를 그대로 가리키는 링크 — 같은 값을 두 번 적지 않는다(가리키는 칸이 대상)
                continue
            try:
                good = covered(k, set())
            except RecursionError:
                good = False
            if not good:
                out.append({"시트": k[0], "칸": k[1], "항목": book.label(*k), "값": v})
    return out


def _dig(data: dict, key: str):
    """결과에서 점 경로로 값을 찾는다 — '결과' 안을 먼저, 없으면 맨 위에서."""
    for root in (data.get("결과") if isinstance(data.get("결과"), dict) else None, data):
        cur: Any = root
        if cur is None:
            continue
        if isinstance(cur, dict) and key in cur:
            return cur[key], True
        found = True
        for part in str(key).split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                found = False
                break
        if found:
            return cur, True
    return None, False


def _basis_text(data: dict) -> str:
    v = data.get("근거")
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        from .tools_export import _format_basis_short, _is_basis_list, _is_wrapped_basis_list
        if _is_basis_list(v) or _is_wrapped_basis_list(v):
            return _format_basis_short(v)
        return " · ".join(str(x) for x in v)
    return "" if v is None else str(v)


def verify_workbook_impl(path: str, checks, annotate: bool = True, output_dir: str | None = None, filename: str | None = None, lang: str = "ko",
                         labels=None) -> dict:
    from .server import mcp
    from .tools_export import _sanitize_name, _unique_path
    guide = "checks=[{cell: \"시트!칸\" 또는 정의된 이름, tool: 계산 도구 이름, args: {…}, key: 결과에서 대조할 키(점 경로), tolerance: 0, label}]"
    err = lambda msg: {"error": "입력 확인 필요 — " + msg, "안내": guide}
    en = lang == "en"
    # ── labels: 대조 결과 시트의 결과 키·근거 구절 표기를 바꾸는 표 {원래 키·구절: 표시할 글} — export_workbook의 labels와 같은 꼴 ──
    own = None
    if labels not in (None, "", {}, []):
        if isinstance(labels, str):
            try:
                labels = _json.loads(labels)
            except Exception:
                return {"error": "입력 확인 필요 — labels가 올바른 JSON 객체가 아님", "안내": "labels={원래 키·근거 구절: 표시할 글}"}
        if not isinstance(labels, dict) or not all(isinstance(k, str) and isinstance(v, str) and k.strip() and v.strip() for k, v in labels.items()):
            return {"error": "입력 확인 필요 — labels는 {원래 키·근거 구절: 표시할 글} 꼴의 객체(글자 → 글자)", "안내": "예: {\"약정_순액\": \"Agreed net amount\"}"}
        if any(v.strip().startswith("=") for v in labels.values()):
            return {"error": "입력 확인 필요 — labels의 표시할 글은 '='로 시작할 수 없음", "안내": "수식이 아니라 글만 받음"}
        from .workbook_i18n import Labels
        own = Labels(labels, en=en)
    tr = None
    if en:      # 영문 시트: 결과 키는 용어집으로 'Tax base (과세표준)', 근거는 영문 인용 표기. 없는 것은 국문 그대로 + 번역_없음
        from .workbook_i18n import Translator
        tr = Translator(own)
    if isinstance(checks, str):
        try:
            checks = _json.loads(checks)
        except Exception:
            return err("checks가 올바른 JSON 배열이 아님")
    if isinstance(checks, dict):
        checks = [checks]
    if not isinstance(checks, list) or not checks:
        return err("checks가 비어 있음 — 대조할 칸을 하나 이상")
    if len(checks) > MAX_CHECKS:
        return err(f"checks가 {MAX_CHECKS}개를 넘음")
    if not path or not os.path.isfile(path) or not str(path).lower().endswith((".xlsx", ".xlsm")):
        return err(f"path가 xlsx 파일이 아님 — '{path}'")
    out_dir = output_dir or os.path.dirname(os.path.abspath(path))
    if annotate and not os.path.isdir(out_dir):
        return err(f"output_dir이 폴더가 아님 — '{out_dir}'")
    try:
        book = _Book(path)
    except Exception as e:
        return err(f"통합 문서를 열지 못함({type(e).__name__})")

    memo: dict[str, dict] = {}
    rows: list[dict] = []
    for n, ch in enumerate(checks, 1):
        if not isinstance(ch, dict) or not ch.get("cell") or not ch.get("tool") or ch.get("key") in (None, ""):
            return err(f"checks[{n}]는 {{cell, tool, args, key}} 객체")
        tool, args, key = str(ch["tool"]), ch.get("args") or {}, str(ch["key"])
        if isinstance(args, str):
            try:
                args = _json.loads(args)
            except Exception:
                return err(f"checks[{n}].args가 올바른 JSON이 아님")
        if not isinstance(args, dict):
            return err(f"checks[{n}].args는 객체")
        if tool in _NO_TOOLS:
            return err(f"checks[{n}].tool '{tool}'은(는) 대조에 쓸 수 없음 — 계산 도구 이름을 적음")
        tol = ch.get("tolerance", 0)
        if not _num(tol) or tol < 0:
            return err(f"checks[{n}].tolerance는 0 이상의 숫자(원)")
        at = book.locate(ch["cell"])
        if at is None:
            return err(f"checks[{n}].cell '{ch['cell']}'를 통합 문서에서 찾지 못함 — \"시트!칸\"(예: Q3!B9) 또는 정의된 이름. 시트: {', '.join(book.wb.sheetnames)}")
        mk = tool + "\n" + _json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        if mk not in memo:
            try:
                r = asyncio.run(mcp.call_tool(tool, args))
                data = _json.loads(r.content[0].text if hasattr(r, "content") else r[0][0].text)
                if not isinstance(data, dict):
                    data = {"error": "도구 결과가 객체가 아님"}
            except Exception as e:
                data = {"error": f"호출 오류: {e}"}
            memo[mk] = data
        data = memo[mk]
        row = {"칸": f"{at[0]}!{at[1]}", "항목": str(ch.get("label") or book.label(*at)), "도구": tool, "키": key, "_at": at}
        wv, read = book.value(*at)
        if isinstance(wv, (_dt.date, _dt.datetime)):
            wv = wv.isoformat()[:10]
        row["통합_문서_값"] = wv if read else None
        if "error" in data:
            row.update({"판정": "도구 오류", "도구_오류": str(data.get("error"))[:300]})
        else:
            tv, found = _dig(data, key)
            row["근거"] = _basis_text(data)
            if not found:
                have = [k for k, v in (data.get("결과") if isinstance(data.get("결과"), dict) else data).items() if _num(v)]
                row.update({"판정": "도구 오류", "도구_오류": f"결과에 키 '{key}'가 없음 — 숫자 키: {', '.join(have[:30])}"})
            elif not read or wv is None:
                row.update({"도구_값": tv, "판정": "읽지 못함"})
            elif _num(wv) and _num(tv):
                d = wv - tv
                d = int(d) if float(d).is_integer() else round(d, 6)
                row.update({"도구_값": tv, "차이": d, "판정": "일치" if abs(d) <= tol else "불일치"})
            else:
                row.update({"도구_값": tv, "판정": "일치" if str(wv).strip() == str(tv).strip() else "불일치"})
        rows.append(row)

    matched = {r["_at"] for r in rows if r["판정"] == "일치"}
    checked = {r["_at"] for r in rows}
    unchecked = _coverage(book, matched, checked)
    # ── 부가 점검 ──
    no_cache = [k for k in book.formulas if k not in book.cached]
    stale = [k for k in book.formulas if k in book.cached and k in book.calc and _num(book.cached[k]) and _num(book.calc[k])
             and abs(book.cached[k] - book.calc[k]) > 0.5]
    skipped = [k for k in no_cache if k not in book.calc]
    frac, errors, hard = [], [], []
    referenced: set[tuple[str, str]] = set()
    formula_cols: set[tuple[str, int]] = set()
    for k in book.formulas:
        referenced.update(book.refs(*k)[0])
        formula_cols.add((k[0], column_index_from_string(_A1.match(k[1]).group(1))))
    for ws in book.wb.worksheets:
        for (r_, c_), c in sorted(ws._cells.items()):
            k = (ws.title, f"{get_column_letter(c_)}{r_}")
            v, read = book.value(*k)
            if isinstance(v, str) and v.startswith("#") and (k in book.formulas or c.data_type == "e"):
                errors.append(k)
            if read and _is_amount(c, v) and abs(v - round(v)) > 1e-6:
                frac.append(k)
            if (k not in book.formulas and _is_amount(c, v) and k not in referenced and (ws.title, c_) in formula_cols and book.label(*k)
                    and k not in checked):
                hard.append(k)
    cells = lambda ks: [f"{s}!{c}" for s, c in ks[:MAX_LIST]]
    extra = {"저장된_값_없는_수식_칸": len(no_cache), "저장된_값과_다시_계산한_값이_다른_칸": cells(stale), "원_미만_소수_금액_칸": cells(frac),
             "오류_칸": cells(errors), "수식_열에_직접_적은_숫자": cells(hard), "값을_계산하지_못한_수식_칸": cells(skipped)}
    count = lambda s: sum(1 for r in rows if r["판정"] == s)
    summary = {"대조": len(rows), "일치": count("일치"), "불일치": count("불일치"), "읽지_못함": count("읽지 못함"), "도구_오류": count("도구 오류"),
               "대조_안_한_금액": len(unchecked)}
    public = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    result: dict[str, Any] = {
        "요약": summary,
        "불일치": [r for r in public if r["판정"] == "불일치"],
        "읽지_못함·도구_오류": [r for r in public if r["판정"] in ("읽지 못함", "도구 오류")],
        "대조": public,
        "대조_안_한_금액": unchecked[:MAX_LIST],
        "부가_점검": extra,
    }
    if len(unchecked) > MAX_LIST:
        result["대조_안_한_금액_더"] = len(unchecked) - MAX_LIST
    # ── 사본에 대조 결과 시트 ──
    warnings: list[str] = []
    if annotate:
        try:
            result["사본"] = _annotate(book, rows, unchecked, summary, extra, out_dir, filename or (os.path.splitext(os.path.basename(path))[0] + "_verified"),
                                      en, _sanitize_name, _unique_path, tr=tr, own=own)
            result["사본_안내"] = ("원본은 그대로 두고 사본에 대조 결과 시트를 붙임. 사본의 수식 칸에는 값을 채움(원본에 저장된 값은 그대로) — 휴대폰·미리보기에서도 보임. "
                               "The original file is unchanged; the copy carries the check sheet and stored values for every formula cell.")
        except Exception as e:
            warnings.append(f"사본을 만들지 못함({type(e).__name__}: {e}) — 대조 결과는 위와 같음")
    steps = []
    if summary["불일치"]:
        steps.append("불일치 칸을 고쳐 저장한 뒤 다시 호출")
    if summary["읽지_못함"] or summary["도구_오류"]:
        steps.append("읽지 못한 칸·도구 오류는 cell·args·key를 확인해 다시 호출")
    if unchecked:
        steps.append("대조 안 한 금액은 해당 계산 도구를 호출해 checks에 더하거나, 사용자에게 '계산 도구 검증 없음'으로 밝힘")
    result["다음"] = " / ".join(steps) if steps else "대조한 칸은 모두 일치, 대조를 거치지 않은 금액 없음"
    if tr is not None and annotate and "사본" in result:      # lang='ko' 결과는 그대로(키를 더하지 않음)
        result["lang"] = "en"
        result["번역_없음"] = list(tr.missing)
        if tr.missing:
            result["번역_없음_안내"] = ("대조 결과 시트에 국문으로 남은 결과 키·근거 구절 — 영문 표기가 필요하면 labels={원래 키·근거 구절: 영문}에 넣어 다시 호출. "
                                 "Result keys and basis phrases left in Korean on the check sheet: to show them in English, pass labels={Korean key or phrase: English text} and call again.")
    if own is not None and annotate and "사본" in result:
        result["labels_적용"] = sorted(own.used)
        left = own.unused()
        if left:
            warnings.append(("labels: no result key or basis phrase with this name on the check sheet (not applied) — " if en
                             else "labels: 대조 결과 시트에서 이 이름의 결과 키를 찾지 못해 적용하지 않음 — ") + "; ".join(left))
    out = {"결과": result, "근거": "통합 문서의 칸 값과 계산 도구 결과 대조(세무 자문 아님)", "한계": LIMITS}
    if warnings:
        out["warnings"] = warnings
    return out


def _annotate(book: _Book, rows, unchecked, summary, extra, out_dir, base, en, sanitize, unique_path, tr=None, own=None) -> str:
    from openpyxl.styles import Alignment, Font, PatternFill
    from .workbook_blend import BAND, GREY, NAVY, NUM, _sheet_name, as_text
    from .workbook_cache import XlError, fill_cached_values
    wb = book.wb
    face = "Calibri" if en else "맑은 고딕"
    F = lambda **k: Font(name=face, **{"size": 10, **k})
    fill = lambda c: PatternFill("solid", fgColor=c)
    wrap = Alignment(wrap_text=True, vertical="top")
    ws = wb.create_sheet(_sheet_name(wb, _t("sheet", en), set()))
    ws.cell(1, 1, _t("title", en)).font = F(bold=True, size=14)
    ws.cell(2, 1, _t("sub", en)).font = F(italic=True, size=9, color=GREY)
    ws.cell(3, 1, _t("scope_line", en, n=summary["대조"], a=summary["일치"], b=summary["불일치"], c=summary["읽지_못함"], d=summary["도구_오류"],
                     u=summary["대조_안_한_금액"])).font = F(bold=True)

    def heads(r, texts):
        for j, h in enumerate(texts, 1):
            c = ws.cell(r, j, h)
            c.font, c.fill, c.alignment = F(bold=True, color="FFFFFF"), fill(NAVY), Alignment(wrap_text=True, vertical="center")

    def band(r, text):
        ws.cell(r, 1, text).font = F(bold=True)
        for j in range(1, 9):
            ws.cell(r, j).fill = fill(BAND)

    heads(5, _t("hdr", en))
    verdict = {"일치": ("match", "E2EFDA"), "불일치": ("diff", "F8CBAD"), "읽지 못함": ("unread", "FFE699"), "도구 오류": ("tool_err", "FFE699")}
    # 결과 키: 영문은 용어집·labels로 'Tax base (과세표준)'(없으면 국문 그대로), 국문은 labels가 있을 때만 그 글. 근거: 영문은 영문 인용 표기
    key_of = tr.label if tr is not None else (own.label if own is not None else (lambda k: k))
    basis_of = tr.basis if tr is not None else (lambda b: b)
    r = 6
    for x in rows:
        vals = [x["칸"], x["항목"], x.get("통합_문서_값"), x.get("도구_값"), x.get("차이"), _t(verdict[x["판정"]][0], en),
                f"{x['도구']} · {key_of(x['키'])}", x.get("도구_오류") or basis_of(x.get("근거") or "")]
        for j, v in enumerate(vals, 1):
            c = ws.cell(r, j, v if _num(v) or v is None else str(v))
            if isinstance(c.value, str):
                as_text(c)
            c.font, c.alignment = F(), wrap if j in (2, 7, 8) else Alignment(vertical="top")
            if _num(v):
                c.number_format = NUM if float(v).is_integer() else "#,##0.####"
        ws.cell(r, 6).fill = fill(verdict[x["판정"]][1])
        r += 1
    r += 1
    band(r, _t("scope", en))
    ws.cell(r + 1, 1, _t("rule", en)).font = F(italic=True, size=9, color=GREY)
    r += 3
    band(r, f"{_t('unchecked', en)} — {len(unchecked)}")
    r += 1
    if unchecked:
        heads(r, _t("un_hdr", en))
        r += 1
        for x in unchecked[:MAX_LIST]:
            for j, v in enumerate((f"{x['시트']}!{x['칸']}", x["항목"], x["값"]), 1):
                c = ws.cell(r, j, v)
                if isinstance(v, str):
                    as_text(c)
                c.font, c.alignment = F(), wrap if j == 2 else Alignment(vertical="top")
            ws.cell(r, 3).number_format = NUM if float(x["값"]).is_integer() else "#,##0.####"
            r += 1
        if len(unchecked) > MAX_LIST:
            ws.cell(r, 1, _t("more", en, n=len(unchecked) - MAX_LIST)).font = F(italic=True, size=9, color=GREY)
            r += 1
    else:
        ws.cell(r, 1, _t("none", en)).font = F()
        r += 1
    r += 1
    band(r, _t("extra", en))
    r += 1
    for key, v in (("x_nocache", extra["저장된_값_없는_수식_칸"]), ("x_stale", extra["저장된_값과_다시_계산한_값이_다른_칸"]), ("x_frac", extra["원_미만_소수_금액_칸"]),
                   ("x_error", extra["오류_칸"]), ("x_hard", extra["수식_열에_직접_적은_숫자"]), ("x_skip", extra["값을_계산하지_못한_수식_칸"])):
        ws.cell(r, 1, _t(key, en)).font = F()
        n = v if isinstance(v, int) else len(v)
        ws.cell(r, 3, n).font = F()
        if not isinstance(v, int) and v:
            c = as_text(ws.cell(r, 4, ", ".join(v[:12]) + (" …" if len(v) > 12 else "")))
            c.font = F(size=9, color=GREY)
        r += 1
    for j, w in enumerate((30, 44, 18, 18, 14, 14, 44, 60), 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A6"
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = 9
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    fpath = unique_path(out_dir, sanitize(base))
    wb.save(fpath)
    # 원본에 저장돼 있던 값은 그대로 되써 넣고(다른 프로그램이 계산한 값 보존), 값이 없던 수식 칸은 다시 계산한 값으로 채운다
    prefer: dict[str, dict[str, Any]] = {}
    for (sheet, coord), v in book.cached.items():
        if isinstance(v, (_dt.datetime, _dt.date, _dt.time, _dt.timedelta)):
            continue                  # 날짜로 읽힌 값은 다시 계산한 값(일련번호)을 쓴다
        if isinstance(v, str) and v.startswith("#") and wb[sheet][coord].data_type == "f" and _re.fullmatch(r"#[A-Z0-9/!?]+", v):
            v = XlError(v)
        elif _num(v):
            v = float(v)
        prefer.setdefault(sheet, {})[coord] = v
    fill_cached_values(wb, fpath, prefer=prefer)
    return os.path.abspath(fpath)
