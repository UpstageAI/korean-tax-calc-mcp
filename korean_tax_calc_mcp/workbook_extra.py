"""export_workbook 자유 형식 시트(extra_sheets)와 조치·기한 목록(actions)의 입력 정리.

계산 도구의 결과가 아닌 표(자체 재검산 표, 추정 표, 계약 이자 같은 세금 밖 계산)를 호출자가 준 그대로 시트로 붙인다.
모델이 "담을 곳이 없는 표가 있다"는 이유로 통합 문서를 통째로 직접 만드는 일을 없애기 위한 입력이다.

- 시트 틀은 고정: 1행 제목, 2행 설명, 3행 "호출자가 넣은 표 — 계산 도구의 검증을 거치지 않음" 표시, 4행 머리 행, 5행부터 행, 끝에 합계 행(선택).
  그래서 수식이 가리킬 칸 주소를 호출자가 미리 알 수 있다(첫 열 = A, 첫 행 = 5행).
- 칸 값: 숫자, 글, 날짜(YYYY-MM-DD), '='로 시작하는 수식, 계산 도구 결과 링크({from_call, from_row}).
- 수식은 같은 시트의 표 안 칸(A1 꼴)과 캐시 값 계산기(workbook_cache)가 계산하는 함수만 받는다. 다른 시트·다른 파일 참조, 이름, 모르는 함수,
  배열 수식은 입력 오류 — 수식 주입(DDE·외부 링크·HYPERLINK 등)을 막는다. 받은 수식은 저장 전에 계산해 보고, 계산되지 않거나 오류 값이면 입력 오류.
- 다른 시트의 도구 계산 칸은 주소로 가리킬 수 없고 {from_call: 호출 label 또는 순번, from_row: 결과 줄 이름}으로만 잇는다(통합 문서에서는 그 칸을 가리키는
  수식, 기존 출력에서는 도구 값). 그 칸을 같은 시트의 수식이 다시 가리킬 수 있다.
- 글은 받은 그대로 싣는다. 도구가 판단 문구를 만들지 않는다.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import re as _re
from typing import Any

from openpyxl.formula import Tokenizer
from openpyxl.formula.tokenizer import Token
from openpyxl.utils import column_index_from_string, get_column_letter

from .workbook_cache import FUNCTIONS

HEAD_ROW, FIRST_ROW = 4, 5
MAX_SHEETS, MAX_ROWS, MAX_COLS, MAX_FORMULA, MAX_ACTIONS = 12, 500, 30, 500, 60
FORMATS = {"amount": '#,##0;(#,##0);"-"', "number": "#,##0.####", "percent": "0.0###%", "date": "yyyy-mm-dd", "text": "@", "source": "@"}
_FORMAT_ALIAS = {"금액": "amount", "숫자": "number", "비율": "percent", "율": "percent", "날짜": "date", "글": "text", "출처": "source",
                 "money": "amount", "krw": "amount", "pct": "percent", "%": "percent", "rate": "percent", "note": "source", "메모": "source"}
_KEYS = {"sheet": ("sheet", "시트", "name"), "title": ("title", "제목"), "note": ("note", "설명", "subtitle"),
         "headers": ("headers", "머리", "header", "columns"), "rows": ("rows", "행"), "total": ("total", "합계"),
         "formats": ("formats", "서식", "format"), "source": ("source", "출처")}
_ACTION_KEYS = {"action": ("action", "조치", "Action", "할 일"), "due": ("due", "기한", "by", "By", "Due", "deadline"),
                "owner": ("owner", "담당", "Owner"), "basis": ("basis", "근거", "Basis", "note")}
_ISO = _re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_REF = _re.compile(r"^\$?([A-Z]{1,3})\$?(\d{1,7})(?::\$?([A-Z]{1,3})\$?(\d{1,7}))?$")
_INFIX = frozenset({"+", "-", "*", "/", "^", "=", "<>", "<", ">", "<=", ">=", "&"})
_GUIDE = ("extra_sheets=[{sheet, title, note, headers: [머리글…], rows: [[칸…]…], total, formats, source}] — 칸은 숫자·글·날짜(YYYY-MM-DD)·"
          "'='로 시작하는 수식(같은 시트의 표 안 칸만, 머리 행 4행·첫 행 5행·첫 열 A)·{from_call, from_row}(계산 도구 결과 링크). "
          "수식 함수: " + "·".join(FUNCTIONS))


def _err(msg: str, guide: str = _GUIDE) -> dict:
    return {"error": "입력 확인 필요 — " + msg, "안내": guide}


def _get(d: dict, key: str, keys: dict = _KEYS):
    return next((d[a] for a in keys[key] if d.get(a) not in (None, "")), None)


def _loads(v: Any, name: str):
    """→ (list 또는 None, 오류 글 또는 None)."""
    if v is None or v == "" or v == [] or v == {}:
        return None, None
    if isinstance(v, str):
        try:
            v = _json.loads(v)
        except Exception:
            return None, f"{name}가 올바른 JSON 배열이 아님"
    if isinstance(v, dict):
        v = [v]
    if not isinstance(v, list):
        return None, f"{name}는 목록(JSON 배열)이어야 함"
    return v, None


def check_formula(text: str, ncols: int, last_row: int) -> tuple[str | None, str | None]:
    """호출자가 준 수식을 검사한다. → (다듬은 수식, None) 또는 (None, 이유).

    받는 것: 숫자·글·TRUE/FALSE, 같은 시트 표 안의 칸·범위(A1 꼴, 5행~끝 행, 표의 열), 사칙·거듭제곱·%·비교·&, 괄호, FUNCTIONS의 함수.
    받지 않는 것: 다른 시트·다른 파일 참조, 정의된 이름, 열·행 전체 참조, 그 밖의 함수, 배열 수식, 오류 값."""
    body = text.strip()
    if len(body) > MAX_FORMULA:
        return None, f"수식이 {MAX_FORMULA}자를 넘음"
    try:
        items = Tokenizer(body).items
    except Exception:
        return None, "수식을 읽지 못함"
    out: list[str] = []
    for t in items:
        ty, sub, v = t.type, t.subtype, t.value
        if ty == Token.WSPACE:
            continue
        if ty == Token.OPERAND:
            if sub in (Token.NUMBER, Token.TEXT, Token.LOGICAL):
                out.append(v.upper() if sub == Token.LOGICAL else v)
                continue
            m = _REF.match(v.upper()) if sub == Token.RANGE else None
            if not m:
                return None, (f"'{v}'는 쓸 수 없음 — 같은 시트의 표 안 칸(A{FIRST_ROW} 꼴)만 가리킬 수 있음"
                              "(다른 시트의 계산 도구 결과는 칸 값을 {from_call, from_row}로 적어 잇는다)")
            for col, row in ((m.group(1), m.group(2)), (m.group(3), m.group(4))):
                if col is None:
                    continue
                if not (FIRST_ROW <= int(row) <= last_row and column_index_from_string(col) <= ncols):
                    return None, (f"'{v}'가 표 밖의 칸을 가리킴 — 표는 A{FIRST_ROW}:{get_column_letter(ncols)}{last_row}"
                                  f"(머리 행 {HEAD_ROW}행, 첫 행 {FIRST_ROW}행)")
            out.append(v.upper())
        elif ty == Token.FUNC:
            if sub == Token.OPEN:
                name = v[:-1].strip().upper()
                if name not in FUNCTIONS:
                    return None, f"함수 {name or v}는 쓸 수 없음 — 쓸 수 있는 함수: {'·'.join(FUNCTIONS)}"
                out.append(name + "(")
            else:
                out.append(")")
        elif ty == Token.OP_IN:
            if v not in _INFIX:
                return None, f"연산자 '{v}'는 쓸 수 없음"
            out.append(v)
        elif ty == Token.OP_PRE:
            if v not in ("+", "-"):
                return None, f"연산자 '{v}'는 쓸 수 없음"
            out.append(v)
        elif ty == Token.OP_POST:
            if v != "%":
                return None, f"연산자 '{v}'는 쓸 수 없음"
            out.append(v)
        elif ty == Token.SEP:
            if sub != Token.ARG:
                return None, "배열 구분자(;)는 쓸 수 없음"
            out.append(",")
        elif ty == Token.PAREN:
            out.append(v)
        else:
            return None, f"'{v}'는 쓸 수 없음(배열 수식·그 밖의 문법)"
    if not out:
        return None, "빈 수식"
    return "=" + "".join(out), None


def _format(v: Any) -> str | None:
    if v is None or v == "":
        return ""
    s = str(v).strip()
    s = _FORMAT_ALIAS.get(s.lower(), s.lower())
    return s if s in FORMATS else None


def _cell(v: Any, fmt: str, where: str, ncols: int, last_row: int) -> tuple[tuple | None, str | None]:
    """칸 값 하나 → ((종류, 값), None) 또는 (None, 오류 글)."""
    if v is None or v == "":
        return ("blank", None), None
    if isinstance(v, bool):
        return ("text", "TRUE" if v else "FALSE"), None
    if isinstance(v, (int, float)):
        if v != v or v in (float("inf"), float("-inf")):
            return None, f"{where}: 숫자가 아님(NaN·무한대)"
        return ("num", v), None
    if isinstance(v, dict):
        if v.get("from_call") is None or not v.get("from_row"):
            return None, f"{where}: 객체 칸은 {{from_call: 호출 label 또는 순번, from_row: 결과 줄 이름}}"
        return ("link", {"from_call": v["from_call"], "from_row": str(v["from_row"])}), None
    if isinstance(v, (list, tuple)):
        return None, f"{where}: 칸 값이 목록임 — 칸은 숫자·글·날짜·수식·{{from_call, from_row}}"
    s = str(v)
    if s.lstrip().startswith("="):
        if fmt in ("text", "source"):
            return ("text", s), None
        f, why = check_formula(s, ncols, last_row)
        if why:
            return None, f"{where}: 수식 '{s[:80]}' — {why}"
        return ("formula", f), None
    m = _ISO.match(s.strip())
    if m and fmt not in ("text", "source"):
        try:
            return ("date", _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))), None
        except ValueError:
            pass
    return ("text", s), None


def normalize_extra(extra_sheets: Any) -> tuple[list[dict] | None, dict | None]:
    """extra_sheets를 정리한다. → (시트 설정 목록 또는 None, 오류 dict 또는 None)."""
    sheets, e = _loads(extra_sheets, "extra_sheets")
    if e:
        return None, _err(e)
    if sheets is None:
        return None, None
    if len(sheets) > MAX_SHEETS:
        return None, _err(f"extra_sheets가 {MAX_SHEETS}개를 넘음")
    out: list[dict] = []
    for n, s in enumerate(sheets, 1):
        if not isinstance(s, dict):
            return None, _err(f"extra_sheets[{n}]가 객체가 아님")
        headers, rows_in = _get(s, "headers"), _get(s, "rows")
        if not isinstance(headers, list) or not headers:
            return None, _err(f"extra_sheets[{n}].headers(머리 행)가 비어 있음")
        if not isinstance(rows_in, list) or not rows_in:
            return None, _err(f"extra_sheets[{n}].rows(행)가 비어 있음")
        ncols = len(headers)
        if ncols > MAX_COLS or len(rows_in) > MAX_ROWS:
            return None, _err(f"extra_sheets[{n}]가 너무 큼 — 열 {MAX_COLS}개, 행 {MAX_ROWS}개까지")
        headers = [str(h) if h is not None else "" for h in headers]
        f_in = _get(s, "formats")
        if isinstance(f_in, dict):
            unknown = [k for k in f_in if str(k) not in headers]
            if unknown:
                return None, _err(f"extra_sheets[{n}].formats의 '{unknown[0]}'는 headers에 없는 머리글")
            f_in = [f_in.get(h, next((v for k, v in f_in.items() if str(k) == h), None)) for h in headers]
        if f_in is None:
            f_in = []
        if not isinstance(f_in, list) or len(f_in) > ncols:
            return None, _err(f"extra_sheets[{n}].formats는 headers와 같은 순서의 목록 또는 {{머리글: 서식}} — 서식: {'·'.join(FORMATS)}")
        formats = []
        for j in range(ncols):
            f = _format(f_in[j] if j < len(f_in) else None)
            if f is None:
                return None, _err(f"extra_sheets[{n}].formats의 '{f_in[j]}'는 모르는 서식 — {'·'.join(FORMATS)} 가운데 하나")
            formats.append(f)
        total_in = _get(s, "total")
        has_total = total_in not in (None, False, "", [], {})
        last_row = FIRST_ROW + len(rows_in) - 1 + (1 if has_total else 0)
        rows: list[dict] = []
        for i, r in enumerate(rows_in):
            where = f"extra_sheets[{n}].rows[{i + 1}]({FIRST_ROW + i}행)"
            if isinstance(r, str):        # 글 한 줄 = 구분 띠(소제목)
                rows.append({"band": r})
                continue
            if isinstance(r, dict) and isinstance(r.get("cells"), list):
                r = r["cells"]
            if not isinstance(r, list):
                return None, _err(f"{where}가 목록이 아님 — 행은 칸 목록 또는 구분 띠로 쓸 글 한 줄")
            if len(r) > ncols:
                return None, _err(f"{where}의 칸이 머리 행({ncols}칸)보다 많음")
            cells = []
            for j, v in enumerate(r):
                c, why = _cell(v, formats[j], f"{where} {get_column_letter(j + 1)}열", ncols, last_row)
                if why:
                    return None, _err(why)
                cells.append(c)
            rows.append({"cells": cells})
        total = None
        if has_total:
            label, cols_in = None, None
            if isinstance(total_in, str):
                label = total_in
            elif isinstance(total_in, dict):
                label, cols_in = total_in.get("label") or total_in.get("이름"), total_in.get("columns") or total_in.get("열")
            elif isinstance(total_in, list):
                cols_in = total_in
            cols: list[int] = []
            if cols_in is not None:
                if not isinstance(cols_in, list):
                    return None, _err(f"extra_sheets[{n}].total.columns는 머리글 또는 1부터 세는 열 번호 목록")
                for x in cols_in:
                    j = (x - 1 if isinstance(x, int) and not isinstance(x, bool) and 1 <= x <= ncols
                         else headers.index(str(x)) if str(x) in headers else None)
                    if j is None or j == 0:
                        return None, _err(f"extra_sheets[{n}].total.columns의 '{x}'는 합계를 낼 수 없는 열(첫 열은 합계 이름 자리)")
                    cols.append(j)
            else:       # 금액 열, 서식이 없으면 숫자·수식만 든 열
                for j in range(1, ncols):
                    kinds = [r["cells"][j][0] for r in rows if "cells" in r and j < len(r["cells"]) and r["cells"][j][0] != "blank"]
                    if formats[j] == "amount" and any(k in ("num", "formula", "link") for k in kinds):
                        cols.append(j)
                    elif formats[j] == "" and kinds and all(k in ("num", "formula", "link") for k in kinds):
                        cols.append(j)
            if not cols:
                return None, _err(f"extra_sheets[{n}].total — 합계를 낼 숫자 열이 없음(total.columns로 열을 지정)")
            total = {"label": str(label) if label else None, "cols": sorted(set(cols))}
        out.append({"sheet": str(_get(s, "sheet") or _get(s, "title") or f"Sheet {n}"), "title": str(_get(s, "title") or _get(s, "sheet") or ""),
                    "note": str(_get(s, "note") or ""), "headers": headers, "formats": formats, "rows": rows, "total": total,
                    "source": str(_get(s, "source") or ""), "last_row": last_row})
    return out, None


def normalize_actions(actions: Any) -> tuple[list[dict] | None, dict | None]:
    """actions(조치·기한 목록)를 정리한다. → (행 목록 또는 None, 오류 dict 또는 None). 글은 받은 그대로."""
    guide = "actions=[{action, due, owner, basis}](국문 키 조치·기한·담당·근거도 됨) — action은 필수, 나머지는 선택"
    rows, e = _loads(actions, "actions")
    if e:
        return None, _err(e, guide)
    if rows is None:
        return None, None
    if len(rows) > MAX_ACTIONS:
        return None, _err(f"actions가 {MAX_ACTIONS}개를 넘음", guide)
    out = []
    for n, x in enumerate(rows, 1):
        if isinstance(x, str):
            x = {"action": x}
        if not isinstance(x, dict):
            return None, _err(f"actions[{n}]가 객체가 아님", guide)
        row = {k: _get(x, k, _ACTION_KEYS) for k in _ACTION_KEYS}
        if row["action"] is None:
            return None, _err(f"actions[{n}]에 action(조치)이 없음", guide)
        out.append({k: "" if v is None else (v if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)) for k, v in row.items()})
    return out, None


_TXT = {
    "mark": ("호출자가 넣은 표 — 계산 도구의 검증을 거치지 않음(숫자와 수식은 작성자가 넣은 그대로).",
             "Table supplied by the preparer — not verified by the calculation tools (figures and formulas are as entered)."),
    "mark_link": (" 초록 칸은 계산 도구 결과를 가리키는 링크.", " Green cells link to calculation tool results."),
    "total": ("합계", "Total"),
    "source": ("출처: ", "Source: "),
    "tool_value": ("연결할 칸이 없어 도구 값을 옮김", "tool value copied — no cell to link to"),
}


def draw(wb, cfgs: list[dict], names: list[str], *, en: bool, resolve) -> tuple[list[dict], list[str]]:
    """자유 형식 시트를 그린다(이름은 names — 호출자가 미리 정한 시트 이름). → (시트 정보 목록, warnings).

    resolve(link) → {"ref": "'시트'!$B$9" 또는 None, "value": 도구 값, "fmt": 표시 형식}; 찾지 못하면 ValueError(글).
    ValueError는 그대로 올린다(호출자가 입력 오류로 돌려줌)."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from .workbook_blend import BAND, BLUE, GREEN, GREY, NAVY, as_text
    face = "Calibri" if en else "맑은 고딕"
    F = lambda **k: Font(name=face, **{"size": 10, **k})
    fill = lambda c: PatternFill("solid", fgColor=c)
    wrap = Alignment(wrap_text=True, vertical="top")
    t = lambda k: _TXT[k][1 if en else 0]
    info, warnings = [], []
    for cfg, name in zip(cfgs, names):
        ws = wb.create_sheet(name)
        ncols = len(cfg["headers"])
        as_text(ws.cell(1, 1, cfg["title"] or name)).font = F(bold=True, size=14)
        as_text(ws.cell(2, 1, cfg["note"])).font = F(italic=True, size=9, color=GREY)
        has_link = any(c[0] == "link" for r in cfg["rows"] for c in r.get("cells", ()))
        ws.cell(3, 1, t("mark") + (t("mark_link") if has_link else "")).font = F(bold=True, size=9, color="C00000")
        for j, h in enumerate(cfg["headers"], 1):
            c = as_text(ws.cell(HEAD_ROW, j, h))
            c.font, c.fill, c.alignment = F(bold=True, color="FFFFFF"), fill(NAVY), Alignment(wrap_text=True, vertical="center")
        widths = [max(8, min(60, len(h) + 2)) for h in cfg["headers"]]
        for i, row in enumerate(cfg["rows"]):
            r = FIRST_ROW + i
            if "band" in row:
                as_text(ws.cell(r, 1, row["band"])).font = F(bold=True)
                for j in range(1, ncols + 1):
                    ws.cell(r, j).fill = fill(BAND)
                continue
            for j, (kind, v) in enumerate(row["cells"], 1):
                if kind == "blank":
                    continue
                fmt = cfg["formats"][j - 1]
                c = ws.cell(r, j)
                c.alignment = Alignment(vertical="top")
                if kind == "text":
                    c.value = v
                    as_text(c)
                    c.font = F(italic=True, size=9, color=GREY) if fmt == "source" else F()
                    c.alignment = wrap
                    widths[j - 1] = max(widths[j - 1], min(70 if fmt == "source" else 48, sum(2 if "가" <= ch <= "힣" else 1 for ch in v) + 2))
                elif kind == "num":
                    c.value, c.font = v, F(color=BLUE)
                    c.number_format = FORMATS[fmt] if fmt and fmt not in ("text", "source") else (FORMATS["amount"] if isinstance(v, int) or float(v).is_integer() else FORMATS["number"])
                    widths[j - 1] = max(widths[j - 1], 18)
                elif kind == "date":
                    c.value, c.font, c.number_format = v, F(color=BLUE), FORMATS["date"]
                    widths[j - 1] = max(widths[j - 1], 14)
                elif kind == "formula":
                    c.value, c.font = v, F()
                    if fmt and fmt not in ("text", "source"):
                        c.number_format = FORMATS[fmt]
                    widths[j - 1] = max(widths[j - 1], 18)
                else:       # link — 계산 도구 결과
                    got = resolve(v)
                    if got.get("ref"):
                        c.value, c.font = "=" + got["ref"], F(color=GREEN)
                    else:
                        c.value, c.font = got["value"], F(color=GREY)
                        if isinstance(got["value"], str):
                            as_text(c)
                        warnings.append(f"extra_sheets '{name}' {get_column_letter(j)}{r}: call '{v['from_call']}'의 '{v['from_row']}' — {t('tool_value')}"
                                        "(scenarios·sources·issues·actions와 함께 쓰면 수식으로 이어짐)")
                    c.number_format = FORMATS[fmt] if fmt and fmt not in ("text", "source") else (got.get("fmt") or FORMATS["amount"])
                    widths[j - 1] = max(widths[j - 1], 18)
        last_data = FIRST_ROW + len(cfg["rows"]) - 1
        total_row = None
        if cfg["total"]:
            total_row = last_data + 1
            as_text(ws.cell(total_row, 1, cfg["total"]["label"] or t("total"))).font = F(bold=True)
            for j in cfg["total"]["cols"]:
                col = get_column_letter(j + 1)
                c = ws.cell(total_row, j + 1, f"=SUM({col}{FIRST_ROW}:{col}{last_data})")
                c.font = F(bold=True)
                fmt = cfg["formats"][j]
                c.number_format = FORMATS[fmt] if fmt and fmt not in ("text", "source") else FORMATS["amount"]
            for j in range(1, ncols + 1):
                ws.cell(total_row, j).fill = fill(BAND)
        end = total_row or last_data
        if cfg["source"]:
            as_text(ws.cell(end + 2, 1, t("source") + cfg["source"])).font = F(italic=True, size=9, color=GREY)
        widths[0] = max(widths[0], 24)
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = f"A{FIRST_ROW}"
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = 9
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        item = {"시트": name, "머리_행": HEAD_ROW, "첫_행": FIRST_ROW, "끝_행": last_data, "열": f"A~{get_column_letter(ncols)}"}
        if total_row:
            item["합계_행"] = total_row
        info.append(item)
    return info, warnings


def verify(wb, names: list[str]) -> str | None:
    """자유 형식 시트의 수식을 저장 전에 계산해 본다. 계산되지 않거나(순환 참조 등) 오류 값이면 그 이유(입력 오류로 돌려줄 글), 아니면 None.
    표시 형식을 주지 않은 수식 칸에는 계산 값에 맞는 형식을 붙인다(정수는 금액, 소수는 숫자)."""
    from .workbook_cache import XlError, _Evaluator
    ev = _Evaluator(wb)
    for name in names:
        ws = wb[name]
        for (row, col), c in sorted(ws._cells.items()):
            if c.data_type != "f" or row < FIRST_ROW:
                continue
            ev.run(ws, c)
            key, at = (ws.title, row, col), f"'{name}' {get_column_letter(col)}{row}"
            linked = isinstance(c.value, str) and "!" in c.value      # 계산 도구 결과 링크 — 도구가 만든 칸
            if key not in ev.memo:
                if linked:
                    continue
                return f"extra_sheets {at}의 수식 '{c.value}'을(를) 계산하지 못함 — {ev.failed.get(key, '계산하지 않음')}"
            v = ev.memo[key]
            if isinstance(v, XlError) and not linked:
                return (f"extra_sheets {at}의 수식 '{c.value}'이(가) 오류 값 {v.code} — 가리키는 칸을 확인"
                        f"(머리 행 {HEAD_ROW}행, 첫 행 {FIRST_ROW}행, 첫 열 A; 글이 든 칸이나 0으로 나누기)")
            if c.number_format == "General" and isinstance(v, float):
                c.number_format = FORMATS["amount"] if v.is_integer() else FORMATS["number"]
    return None


_FIG_KEYS = {"label": ("label", "이름", "항목"), "call": ("call", "from_call"), "row": ("row", "from_row", "줄"), "sheet": ("sheet", "시트"),
             "cell": ("cell", "칸"), "highlight": ("highlight", "강조"), "note": ("note", "메모")}


def normalize_key_figures(key_figures: Any) -> tuple[list[dict] | None, dict | None]:
    """key_figures(요약 시트 핵심 숫자 표의 줄)를 정리한다. 가리키는 곳이 실제로 있는지는 시트를 그릴 때 본다."""
    guide = ("key_figures=[{label, call, row, highlight, note}] 또는 [{label, sheet, cell, highlight, note}] — call은 calls의 label 또는 1부터 세는 순번, "
             "row는 그 결과의 줄 이름(예: 합계), sheet·cell은 extra_sheets의 시트 이름과 칸 주소(예: B12)")
    rows, e = _loads(key_figures, "key_figures")
    if e:
        return None, _err(e, guide)
    if rows is None:
        return None, None
    if len(rows) > 40:
        return None, _err("key_figures가 40줄을 넘음", guide)
    out = []
    for n, x in enumerate(rows, 1):
        if not isinstance(x, dict):
            return None, _err(f"key_figures[{n}]가 객체가 아님", guide)
        k = {key: _get(x, key, _FIG_KEYS) for key in _FIG_KEYS}
        by_call, by_cell = k["call"] is not None and k["row"] is not None, k["sheet"] is not None and k["cell"] is not None
        if by_call == by_cell:
            return None, _err(f"key_figures[{n}]는 call·row(계산 도구 결과) 또는 sheet·cell(extra_sheets의 칸) 가운데 한 가지로 가리킴", guide)
        out.append({"label": str(k["label"]) if k["label"] is not None else "", "call": k["call"], "row": str(k["row"]) if by_call else None,
                    "sheet": str(k["sheet"]) if by_cell else None, "cell": str(k["cell"]).replace("$", "").strip().upper() if by_cell else None,
                    "highlight": bool(x.get("highlight") or x.get("강조")), "note": str(k["note"]) if k["note"] is not None else ""})
    return out, None
