"""export_workbook 본문 — 계산 근거 엑셀 내보내기. 도구 등록(스키마·docstring·_guard)은 server.py의 얇은 래퍼가 맡는다."""
import asyncio
import json as _json
import os
from fractions import Fraction
from datetime import date
from typing import Any

from .forms_workbook import render_form_sheet, _load_form_templates, tool_value, nonbusiness_form_sources, nonbusiness_form_data
from .forms_workbook import export_form_inputs, form_cell_inputs, merged_form_sources, vat_period_text


# ── export_workbook: 계산 근거 엑셀 내보내기 ─────────────────────────────
_INVALID_NAME_CHARS = frozenset("/\\:*?\"<>|")


def _sanitize_name(s: str) -> str:
    return "".join("_" if c in _INVALID_NAME_CHARS else c for c in s)


def _unique_path(dir_path: str, base_name: str, ext: str = ".xlsx") -> str:
    """이미 있으면 (2), (3)… 접미사를 붙여 새 경로 반환."""
    safe = _sanitize_name(base_name)
    candidate = os.path.join(dir_path, safe + ext)
    if not os.path.exists(candidate):
        return candidate
    n = 2
    while True:
        candidate = os.path.join(dir_path, f"{safe} ({n}){ext}")
        if not os.path.exists(candidate):
            return candidate
        n += 1


def _flatten_args(args, prefix: str = "") -> list[tuple[str, Any]]:
    """중첩 dict/list를 경로|값 튜플 목록으로 펼침. 예: revenue.매출액, ledger[0].금액."""
    rows: list[tuple[str, Any]] = []
    if isinstance(args, dict):
        for k, v in args.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, (dict, list)):
                rows.extend(_flatten_args(v, path))
            else:
                rows.append((path, v))
    elif isinstance(args, list):
        for i, v in enumerate(args):
            path = f"{prefix}[{i}]"
            if isinstance(v, (dict, list)):
                rows.extend(_flatten_args(v, path))
            else:
                rows.append((path, v))
    else:
        rows.append((prefix, args))
    return rows


def _numeric_items(d: dict) -> list[tuple[str, Any]]:
    """결과 dict에서 숫자·문자 값을 (키, 값) 튜플로 추출."""
    out: list[tuple[str, Any]] = []
    for k, v in d.items():
        if isinstance(v, (int, float)) or (isinstance(v, str) and v):
            out.append((str(k), v))
    return out


def _cell_value(v: Any) -> Any:
    """엑셀 셀에 쓸 수 있는 스칼라 값으로 변환. 목록·dict는 규칙에 따라 문자열로."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        if _is_basis_list(v):
            return _format_basis(v)
        # 항목마다 한 겹 더 감싼 근거 목록인가? (earned_income_gross_pay)
        if _is_wrapped_basis_list(v):
            return "\n".join(_format_basis(inner) for inner in v if _is_basis_list(inner))
        return _json.dumps(v, ensure_ascii=False)
    if isinstance(v, dict):
        return _json.dumps(v, ensure_ascii=False)
    return str(v)


def _is_basis_list(v: list) -> bool:
    """v가 [법령, 조, 항, 요지] 목록의 목록인가? (근거 목록 판정)"""
    if not v or not isinstance(v, list):
        return False
    for item in v:
        if not isinstance(item, list):
            return False
        if not (3 <= len(item) <= 4):
            return False
        if not all(isinstance(x, str) for x in item):
            return False
        # 둘째 요소가 조 번호인가? (예: "제40조", "제81조①")
        if len(item) >= 2 and not _looks_like_article(item[1]):
            return False
    return True


def _looks_like_article(s: str) -> bool:
    """s가 조 번호처럼 보이는가? (예: "제40조", "제81조①")"""
    if not s.startswith("제"):
        return False
    조_idx = s.find("조")
    if 조_idx <= 1:
        return False
    return s[1:조_idx].isdigit()


def _is_wrapped_basis_list(v: list) -> bool:
    """v가 근거 목록들을 한 겹 더 감싼 목록인가? (earned_income_gross_pay 근거)"""
    if not v or not isinstance(v, list):
        return False
    for item in v:
        if not _is_basis_list(item):
            return False
    return True


def _format_basis(v: list) -> str:
    """근거 목록([법령, 조, 항, 요지] 목록)을 사람이 읽는 문장으로 변환.

    각 항목의 자리(0 법령·1 조·2 항·3 요지)로 먼저 읽고, 빈 값만 생략한다.
    빈 값을 먼저 걸러내면 요지가 항 자리에 붙는 문제(예: 제40조실지귀속)가 생긴다.
    """
    lines = []
    for item in v:
        if not item:
            continue
        law_name = item[0] if len(item) > 0 and item[0] else ""
        article = item[1] if len(item) > 1 and item[1] else ""
        clause = item[2] if len(item) > 2 and item[2] else ""
        gist = item[3] if len(item) > 3 and item[3] else ""
        if not law_name:
            continue

        # 법령 + 조항(+ 항)
        law_article = law_name
        if article:
            law_article += " " + article
        if clause:
            law_article += clause

        # 요지 추가
        if gist:
            lines.append(f"{law_article} — {gist}")
        else:
            lines.append(law_article)

    return "\n".join(lines)


def _format_basis_short(v: list) -> str:
    """근거 목록([법령, 조, 항, 요지] 목록)을 법조문 번호만 중복 없이 `, `로 이어 한 줄로 변환.

    요약 시트용: 요지 문장 없이 법령 조항만 추출하며, 중복 제거 후 한 줄로 연결한다.
    4번째 칸(요지)이 ``N호…``로 시작하면 ``N호``까지만 조항에 붙이고 나머지 문장은 버린다.

    항목별로 한 겹 더 감싼 근거 목록(wrapped basis list)도 같은 규칙으로 펼쳐 한 줄로 만든다.
    """
    import re as _re
    # 항목별로 한 겹 더 감싼 근거 목록이면 내부 항목만 평면화
    if _is_wrapped_basis_list(v):
        v = [inner for wrapper in v for inner in (wrapper if _is_basis_list(wrapper) else [])]
    seen: list[str] = []
    for item in v:
        if not item:
            continue
        law_name = item[0] if len(item) > 0 and item[0] else ""
        article = item[1] if len(item) > 1 and item[1] else ""
        clause = item[2] if len(item) > 2 and item[2] else ""
        gist = item[3] if len(item) > 3 and item[3] else ""
        if not law_name:
            continue
        law_article = law_name
        if article:
            law_article += " " + article
        if clause:
            law_article += clause
        # 요지가 'N호…'로 시작하면 호까지만 조항에 붙이고 나머지 문장은 버림.
        # 항이 비어 있으면 조와 호 사이 한 칸 띄움(예: "제17조의4 1호"), 항이 있으면 바로 붙임(예: "제20조①1호").
        if gist and _re.match(r"^\d+호", gist):
            ho = _re.match(r"^\d+호", gist).group(0)
            if clause:
                law_article += ho
            else:
                law_article += " " + ho
        if law_article not in seen:
            seen.append(law_article)
    return ", ".join(seen)


# ── 계산식 이름 치환 헬퍼 (SPEC_export_workbook_c) ─────────────────────────
import re as _re
from openpyxl.workbook.defined_name import DefinedName

_NAME_RE = _re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9_]*")

_FUNCTIONS = frozenset({"MIN", "MAX", "IF", "ROUNDDOWN", "TRUE", "FALSE"})

_CELL_A1_RE = _re.compile(r"^[A-Za-z]{1,3}[0-9]+$")
_CELL_R1C1_RE = _re.compile(r"^[RrCc]$|^[Rr][0-9]*[Cc][0-9]*$")
_VALID_START_RE = _re.compile(r"^[가-힣A-Za-z_]$")
_SANITIZE_CHAIN = _re.compile(r"[^가-힣A-Za-z0-9_.]+")


def _sanitize_dname(raw: str, *, wb) -> str:
    """Excel 정의 이름 규칙에 맞게 이름 문자열을 정제한다.

    - 허용 문자(한글·영문·숫자·밑줄·마침표)만 남기고 나머지는 '_'로 치환.
    - 연속 '_'를 하나로 압축, 끝 '_' 제거.
    - 첫 글자가 한글·영문·밑줄이 아니면 앞에 '_'.
    - 셀 주소(A1, AB12, R, C, R1C1 등)로 읽히면 앞에 '_'.
    - 255자 초과 시 자름.
    - 이미 등록된 이름과 대소문자 무시로 겹치면 '_2', '_3'… 접미사.
    """
    s = _SANITIZE_CHAIN.sub("_", raw)
    s = _re.sub(r"_+", "_", s)
    s = s.rstrip("_")
    if not s:
        s = "_"
    if not _VALID_START_RE.match(s[0]):
        s = "_" + s
    if _CELL_A1_RE.match(s) or _CELL_R1C1_RE.match(s):
        s = "_" + s
    s = s[:255]
    key = s.lower()
    if key in wb.defined_names:
        base, ext = s, ""
        i = 2
        while f"{base}{ext}".lower() in wb.defined_names:
            ext = f"_{i}"
            i += 1
        s = f"{base}{ext}"
    return s


def _이름_치환(식: str, 이름_맵: dict[str, str]) -> str:
    """엑셀 수식 문법의 식에서 각 이름(식별자)을 정의 이름(호출N_이름)으로 치환한다.

    함수명(MIN/MAX/IF/ROUNDDOWN)과 TRUE/FALSE는 치환하지 않는다.
    괄호·쉼표·연산자·숫자는 그대로 보존하며, Excel이 연산자 우선순위를 해석한다.
    """
    tok: list[str] = []
    i, n = 0, len(식)
    while i < n:
        c = 식[i]
        if c in " \t":
            i += 1
            continue
        if c in "+-*/()":
            tok.append(c); i += 1; continue
        if c == ",":
            tok.append(","); i += 1; continue
        if c.isdigit() or (c == "." and i + 1 < n and 식[i + 1].isdigit()):
            j = i
            # 정수부
            while j < n and 식[j].isdigit():
                j += 1
            # 소수부
            if j < n and 식[j] == "." and j + 1 < n and 식[j + 1].isdigit():
                j += 1
                while j < n and 식[j].isdigit():
                    j += 1
            # 지수부: e/E 뒤에 숫자(또는 부호+숫자)가 있을 때만 포함
            if j < n and 식[j] in "eE":
                k = j + 1
                if k < n and 식[k] in "+-":
                    k += 1
                if k < n and 식[k].isdigit():
                    j = k
                    while j < n and 식[j].isdigit():
                        j += 1
                # e/E 뒤에 숫자(부호+숫자)가 없으면 거기서 숫자를 끝내고
                # e/E부터는 다음 반복에서 이름으로 읽는다
            tok.append(식[i:j]); i = j; continue
        m = _NAME_RE.match(식, i)
        if m:
            name = m.group(0)
            i = m.end()
            if name not in _FUNCTIONS:
                tok.append(이름_맵.get(name, name))
            else:
                tok.append(name)
        else:
            tok.append(c); i += 1
    return "".join(tok)


# ── '계산 N' 세부 표 · '판단·근거' 보충 (서식 틀이 없는 도구도 결과를 다 보이게) ─────────────────
# 위쪽 '항목·금액' 표는 결과·계산의 숫자·문자 한 줄 값만 보인다. 중첩 dict(판정 등)·dict 목록(항목별·연도별 산출)·
# 문자 목록은 여기서 '세부' 블록으로 펼친다. 이미 다른 표로 그린 키는 뺀다.
_DETAIL_SKIP_TOP = frozenset({"세무조정", "판단", "산식", "계산식", "계산식_입력", "계산", "쟁점", "입력 해석"})


def _detail_blocks(res: dict, calc_dict) -> tuple[list[tuple[str, Any]], list[tuple[str, list[str], list[list[Any]]]]]:
    """결과·계산 dict에서 한 줄 값으로 못 보인 것을 (경로, 값) 줄과 (제목, 머리글, 행) 표로 돌려준다."""
    lines: list[tuple[str, Any]] = []
    tables: list[tuple[str, list[str], list[list[Any]]]] = []

    def _scalar(v):
        return v is None or isinstance(v, (str, int, float, bool))

    def _row_dicts(items: list, parent: dict | None = None) -> list[dict]:
        # dict 목록 → 평평한 행. 안쪽 dict 목록(예: 연도별 '산출')은 바깥 칸을 앞에 붙여 행으로 편다
        out: list[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            base = dict(parent or {})
            nested = None
            for k, v in it.items():
                if isinstance(v, list) and v and all(isinstance(x, dict) for x in v) and nested is None:
                    nested = (k, v)
                elif _scalar(v):
                    base[k] = v
                else:
                    base[k] = _cell_value(v)
            if nested:
                out.extend(_row_dicts(nested[1], base))
            else:
                out.append(base)
        return out

    def _walk(d: dict, prefix: str, top: bool):
        for k, v in d.items():
            if top and k in _DETAIL_SKIP_TOP:
                continue
            path = f"{prefix}{k}"
            if _scalar(v):
                if not top and v is not None and v != "":
                    lines.append((path, v))
                continue
            if isinstance(v, dict):
                if v:
                    _walk(v, path + ".", False)
                continue
            if isinstance(v, list):
                if not v:
                    continue
                if all(isinstance(x, dict) for x in v):
                    rws = _row_dicts(v)
                    hdr: list[str] = []
                    for rw in rws:
                        for kk in rw:
                            if kk not in hdr:
                                hdr.append(kk)
                    tables.append((path, hdr, [[rw.get(h) for h in hdr] for rw in rws]))
                elif _is_basis_list(v) or _is_wrapped_basis_list(v):
                    if not top:
                        lines.append((path, _cell_value(v)))
                elif all(_scalar(x) for x in v):
                    lines.append((path, ", ".join("" if x is None else str(x) for x in v)))
                else:
                    lines.append((path, _cell_value(v)))

    if isinstance(res, dict):
        _walk(res, "", True)
    if isinstance(calc_dict, dict) and calc_dict is not res:
        _walk(calc_dict, "", True)
    return lines, tables


# 별지50(을) 과목 묶음: 같은 과목의 유보·△유보를 한 줄로(종류 이름 우선, 없으면 구분 문구·도구로 판단)
_유보_과목명 = {"퇴직연금충당금": "퇴직연금충당금", "퇴직급여충당금": "퇴직급여충당금 한도초과",
               "대손충당금": "대손충당금 한도초과", "대손금": "대손금 부인", "미지급기부금": "미지급기부금"}


def _유보_과목(s: dict, tool: str) -> str | None:
    """세무조정 한 줄의 별지50(을) 과목 묶음 키(없으면 None — 그 줄 이름 그대로)."""
    for text in (str(s.get("종류") or ""), str(s.get("구분") or "")):
        for fam in ("퇴직연금충당금", "퇴직급여충당금", "대손충당금", "대손금", "미지급기부금"):
            if fam in text:
                return fam
    구분 = str(s.get("구분") or "")
    if tool == "bad_debt_adjustment":
        return "대손충당금" if "한도초과" in 구분 else "대손금"
    if tool == "retirement_allowance_adjustment":
        return "퇴직연금충당금" if "연금" in 구분 else "퇴직급여충당금"
    return None


def _유보_기초(last_call, calls: list, 결과들: list) -> dict[str, int]:
    """별지50(을) ②기초잔액 — 전기 유보를 입력으로 받은 call에서(유보 +, △유보 −). 입력이 없는 과목은 넣지 않는다."""
    out: dict[str, int] = {}
    i = last_call("bad_debt_adjustment")
    if i is not None:
        a = (calls[i] or {}).get("args") or {}
        if "prior_excess" in a:
            out["대손충당금"] = int(a.get("prior_excess") or 0)       # 전기 대손충당금 한도초과(유보)
        v = ((결과들[i].get("data") or {}).get("계산") or {}).get("전기부인 유보 채권(전기말 가산)")
        if isinstance(v, (int, float)):
            out["대손금"] = int(v)                                      # 전기 부인 대손금(유보)
    i = last_call("retirement_allowance_adjustment")
    if i is not None:
        a = (calls[i] or {}).get("args") or {}
        if "prior_disallowed" in a:
            out["퇴직급여충당금"] = int(a.get("prior_disallowed") or 0)   # 퇴직급여충당금 부인누계(유보)
        pen = a.get("pension")
        if isinstance(pen, dict) and "prior_deducted" in pen and not (pen.get("book_provision") or 0):
            out["퇴직연금충당금"] = -int(pen.get("prior_deducted") or 0)  # 신고조정 손금산입 누계(△유보)
    return out


def _eq_strings(obj, out: set) -> set:
    """중첩 dict·list에서 '='로 시작하는 문자열을 모은다."""
    if isinstance(obj, str):
        if obj.startswith("="):
            out.add(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _eq_strings(k, out)
            _eq_strings(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _eq_strings(v, out)
    return out


def _labels_as_text(wb, sources) -> int:
    """openpyxl은 '='로 시작하는 문자열을 수식으로 저장한다. 도구 결과·입력에서 온 문구('= 순손익액' 같은 산출 과정 라벨)는
    수식이 아니므로 문자열 칸(앞 따옴표 표시)으로 바꾼다. 서버가 만든 수식은 '=' 뒤에 공백을 두지 않으므로 '= '로 시작하는 칸도 문구로 본다.
    바꾼 칸 수를 돌려준다."""
    texts = _eq_strings(sources, set())
    n = 0
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if c.data_type == "f" and isinstance(v, str) and (v in texts or v.startswith("= ")):
                    c.data_type = "s"
                    c.quotePrefix = True
                    n += 1
    return n


def _write_detail_blocks(ws, start_row: int, res: dict, calc_dict, *, bold, header_fill, money_fmt) -> int:
    """'계산 N' 시트 아래에 세부 블록을 쓴다. 쓴 것이 없으면 start_row를 그대로 돌려준다."""
    from openpyxl.styles import Alignment
    lines, tables = _detail_blocks(res, calc_dict)
    if not lines and not tables:
        return start_row
    행 = start_row

    def _put(r, c, v, key=""):
        cell = ws.cell(r, c)
        if isinstance(v, bool):
            cell.value = "예" if v else "아니오"
        elif isinstance(v, (int, float)):
            cell.value = v
            # 금액만 천 단위 쉼표 — 연도(사업연도 2024)·비율(0.2)은 그대로
            if not ("연도" in key or key.endswith("년")) and (float(v).is_integer() or abs(v) >= 1000):
                cell.number_format = money_fmt
        else:
            cell.value = v
            if isinstance(v, str) and len(v) > 40:
                cell.alignment = Alignment(wrap_text=True, vertical="top")

    if lines:
        for cc, h in enumerate(["세부 항목", "값"], 1):
            c = ws.cell(행, cc, h); c.font = bold; c.fill = header_fill
        행 += 1
        for k, v in lines:
            ws.cell(행, 1, k)
            _put(행, 2, v, k)
            행 += 1
        행 += 1
    for title, hdr, rws in tables:
        ws.cell(행, 1, title).font = bold
        행 += 1
        for cc, h in enumerate(hdr, 1):
            c = ws.cell(행, cc, h); c.font = bold; c.fill = header_fill
        행 += 1
        for rw in rws:
            for cc, v in enumerate(rw, 1):
                _put(행, cc, v, str(hdr[cc - 1]))
            행 += 1
        행 += 1
    return 행


def _judgement_rows(data: dict, calc_sheet: str) -> list[dict]:
    """'판단·근거' 시트에 쓸 행. 도구가 '판단'을 주면 그대로, 없으면 판정·쟁점을, 그것도 없으면 그 사실을 한 줄로."""
    판단목록 = data.get("판단") or []
    if isinstance(판단목록, dict):      # religious_income·inheritance_gift_valuation 등 {항목: 결론} 형태
        # 값이 {결론, 근거} dict면(gift_tax) 칸을 나눠 쓴다 — JSON 문자열로 보이지 않게
        판단목록 = [{"항목": k, **{kk: vv for kk, vv in v.items() if kk in ("결론", "근거", "이유", "금액")}}
                 if isinstance(v, dict) and "결론" in v else {"항목": k, "결론": v}
                 for k, v in 판단목록.items()]
    elif isinstance(판단목록, str):
        판단목록 = [판단목록]
    out = [j if isinstance(j, dict) else {"결론": j} for j in 판단목록]   # 문장 목록인 도구(예: nonbusiness_interest_disallowance)
    if out:
        return out
    판정 = data.get("판정")
    if isinstance(판정, dict):          # related_judge — 법별 판정
        조문 = data.get("적용조문") if isinstance(data.get("적용조문"), dict) else {}
        근거 = data.get("근거") if isinstance(data.get("근거"), dict) else {}
        for k, v in 판정.items():
            g = 근거.get(k) or []
            c = 조문.get(k) or []
            out.append({"항목": f"판정({k})", "결론": v,
                        "근거": ", ".join(map(str, g)) if isinstance(g, list) and g else (" ".join(map(str, c[:2])) if isinstance(c, list) else str(c)),
                        "이유": "; ".join(map(str, data.get("참고") or [])) if isinstance(data.get("참고"), list) else ""})
    for q in data.get("쟁점") or []:     # nonresident_withholding 등 — 확인할 쟁점
        if isinstance(q, dict) and q.get("쟁점"):
            out.append({"항목": "쟁점", "결론": q["쟁점"], "근거": ", ".join(map(str, q.get("참고") or [])),
                        "이유": q.get("판단", "")})
    if out:
        return out
    근거 = data.get("근거", "")
    if isinstance(근거, list) and (_is_basis_list(근거) or _is_wrapped_basis_list(근거)):
        근거 = _format_basis_short(근거)
    return [{"항목": "(판단 항목 없음)", "결론": f"이 도구 결과에는 판단 항목이 없음 — 계산 값은 '{calc_sheet}' 시트",
             "근거": 근거 if isinstance(근거, str) else _cell_value(근거), "이유": data.get("주의", "")}]


def export_workbook_impl(title: str, calls, output_dir: str = ".", filename: str | None = None, layout: str = "forms",
                        company: str = "", period: str = "", biz_no: str = "") -> dict:
    """server.export_workbook의 본문(서명·설명은 그쪽 참조). mcp는 순환 import를 피해 호출 시점에 가져온다."""
    from .server import mcp
    # ── calls가 문자열이면 JSON으로 풀기 ──
    if isinstance(calls, str):
        try:
            parsed = _json.loads(calls)
        except Exception:
            return {"error": "입력 확인 필요 — calls는 [{label, tool, args}] 목록(JSON 배열)", "안내": "calls가 올바른 JSON 배열이 아님"}
        if not isinstance(parsed, list):
            return {"error": "입력 확인 필요 — calls는 [{label, tool, args}] 목록(JSON 배열)", "안내": "calls가 JSON 객체 등으로 넘어옴 — 배열이어야 함"}
        calls = parsed

    # ── 입력 검증 ──
    if not calls:
        return {"error": "입력 확인 필요 — calls가 비어 있음", "안내": "1~30개 call을 주세요"}
    if len(calls) > 30:
        return {"error": "입력 확인 필요 — calls가 30개 초과", "안내": "최대 30개까지"}
    if output_dir is None or output_dir == "":
        return {"error": "입력 확인 필요 — output_dir 없음", "안내": "output_dir을 지정하세요"}
    if not os.path.isdir(output_dir):
        return {"error": "입력 확인 필요 — output_dir이 폴더가 아님", "안내": f"'{output_dir}'은(는) 폴더가 아님"}

    오류_call: list[str] = []
    결과들: list[dict] = []  # 각 call의 (label, tool, result_or_error, basis)

    # ── 각 call 실행 ──
    for call in calls:
        label = call.get("label", "")
        tool = call.get("tool", "")
        args = call.get("args", {})
        if isinstance(args, str):
            try:
                parsed_args = _json.loads(args)
            except Exception:
                오류_call.append(label)
                결과들.append({"label": label, "tool": tool,
                               "error": "입력 확인 필요 — call args가 올바른 JSON이 아님",
                               "basis": "", "result": None})
                continue
            if not isinstance(parsed_args, dict):
                오류_call.append(label)
                결과들.append({"label": label, "tool": tool,
                               "error": "입력 확인 필요 — call args가 JSON 객체(dict)가 아님",
                               "basis": "", "result": None})
                continue
            args = parsed_args
            call["args"] = args  # 뒷부분의 calls[i].get("args", …)도 dict를 받게 갱신

        if not tool or tool == "export_workbook":
            return {"error": "입력 확인 필요 — 도구 이름 없음 또는 export_workbook 재귀 호출 금지",
                    "안내": "calls에서 tool 이름을 확인하세요"}

        try:
            r = asyncio.run(mcp.call_tool(tool, args))
            raw = r.content[0].text if hasattr(r, "content") else r[0][0].text
            data = _json.loads(raw)
        except Exception as e:
            오류_call.append(label)
            결과들.append({"label": label, "tool": tool,
                           "error": f"입력 확인 필요 — 호출 오류: {e}",
                           "basis": "", "result": None})
            continue

        if "error" in data:
            오류_call.append(label)
            결과들.append({"label": label, "tool": tool,
                           "error": data.get("error", str(data)),
                           "basis": data.get("안내") or data.get("문제") and "\n".join(data["문제"]) or "",
                           "result": data,
                           "data": data})
            continue
        else:
            # 부가·증여·원천징수 도구: 서식 칸 수식이 가리킬 '입력·가정' 이름을 내보내기에서만 덧붙임(도구 출력은 그대로)
            data = export_form_inputs(tool, args, data)
            data = form_cell_inputs(tool, args, data)   # 서식 금액 칸이 가리킬 이름(세율 구간·별지8 코드별 금액 등)
            결과들.append({"label": label, "tool": tool,
                           "error": "",
                           "basis": data.get("근거", ""),
                           "result": data.get("결과", data),
                           "data": data})

    # ── 워크북 생성 ──
    import openpyxl
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()

    # 번호 서식
    money_fmt = "#,##0"
    bold = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9E1F2")

    def _set_money(cell, val):
        cell.value = val
        cell.number_format = money_fmt

    # ── 폼 템플릿 로드 ──
    _FORM_TEMPLATES = _load_form_templates()

    시트이름들: list[str] = []

    if layout == "steps":
        # ── 1. 요약 시트 (steps 모드, 기존 동작) ──
        ws_sum = wb.active
        ws_sum.title = "요약"

        오늘 = date.today().isoformat()
        ws_sum["A1"] = "제목"; ws_sum["B1"] = title
        ws_sum["A2"] = "작성일"; ws_sum["B2"] = 오늘
        ws_sum["A3"] = "call 수"; ws_sum["B3"] = len(calls)
        for c in ("A1", "A2", "A3"):
            ws_sum[c].font = bold

        hdr_row = 4
        ws_sum.cell(hdr_row, 1, "label").font = bold
        ws_sum.cell(hdr_row, 2, "도구").font = bold
        첫데이터행 = hdr_row + 1

        for i, cd in enumerate(결과들):
            r = 첫데이터행 + i
            ws_sum.cell(r, 1, cd["label"])
            ws_sum.cell(r, 2, cd["tool"])
            c = 3
            if cd["error"]:
                ws_sum.cell(r, c, cd["error"]); c += 1
            else:
                for k, v in _numeric_items(cd["result"] or {}):
                    kc = ws_sum.cell(r, c, k); kc.font = bold
                    vc = ws_sum.cell(r, c + 1)
                    if isinstance(v, (int, float)):
                        _set_money(vc, v)
                    else:
                        vc.value = _cell_value(v)
                    c += 2
                if cd["basis"]:
                    if isinstance(cd["basis"], list) and (_is_basis_list(cd["basis"]) or _is_wrapped_basis_list(cd["basis"])):
                        bc = ws_sum.cell(r, c, _format_basis_short(cd["basis"]))
                    else:
                        bc = ws_sum.cell(r, c, _cell_value(cd["basis"]))
                    c += 1

        고지행 = 첫데이터행 + len(결과들) + 1
        ws_sum.cell(고지행, 1,
                    "이 파일은 계산 도구의 결과를 정리한 참고 자료이며 세무 자문이 아닙니다. 판단과 신고는 세무 전문가와 확인하세요.")
        ws_sum.cell(고지행, 1).font = Font(italic=True, color="C00000")
        ws_sum.merge_cells(start_row=고지행, start_column=1, end_row=고지행, end_column=8)

        ws_sum.column_dimensions["A"].width = 20
        ws_sum.column_dimensions["B"].width = 28
        for c in range(3, 20):
            ws_sum.column_dimensions[get_column_letter(c)].width = 16
        ws_sum.freeze_panes = "A5"

        시트이름들.append("요약")

        # ── 2. 계산 시트들 (steps 모드) — call마다 한 장, N은 calls 안 순번(오류 call은 오류 내용만) ──
        calc_idx = 0
        for _ci, cd in enumerate(결과들):
            calc_idx = _ci + 1
            sh_name = f"계산 {calc_idx}"
            ws = wb.create_sheet(sh_name)
            시트이름들.append(sh_name)
            if cd["error"] or not cd["result"]:
                for rr, (k, v) in enumerate((("label", cd.get("label", "")), ("도구", cd.get("tool", "")),
                                              ("오류", cd.get("error") or "결과 없음"),
                                              ("안내", _cell_value(cd.get("basis")) if cd.get("basis") else "")), 1):
                    ws.cell(rr, 1, k).font = bold
                    ws.cell(rr, 2, v)
                ws.column_dimensions["A"].width = 16
                ws.column_dimensions["B"].width = 60
                continue
            res = cd["result"] or {}
            calc_dict = (cd.get("data") or {}).get("계산") if isinstance(cd.get("data"), dict) else None
            formula = (cd.get("data") or {}).get("계산식") if isinstance(cd.get("data"), dict) else None

            if formula:
                호출접두사 = f"호출{calc_idx}_"
                dname_map: dict[str, str] = {}
                for inp in (cd.get("data") or {}).get("계산식_입력", []) or []:
                    dname_map[inp["이름"]] = _sanitize_dname(f"{호출접두사}{inp['이름']}", wb=wb)
                for s in formula:
                    dname_map[s["이름"]] = _sanitize_dname(f"{호출접두사}{s['이름']}", wb=wb)

                행 = 1
                for cc, h in enumerate(["이름", "값", "설명"], 1):
                    c = ws.cell(행, cc, h); c.font = bold; c.fill = header_fill
                행 += 1
                for inp in (cd.get("data") or {}).get("계산식_입력", []) or []:
                    ws.cell(행, 1, inp["이름"])
                    vc = ws.cell(행, 2)
                    v = inp["값"]
                    if isinstance(v, bool):
                        vc.value = v
                    elif isinstance(v, (int, float)):
                        _set_money(vc, v)
                    else:
                        vc.value = v
                    _nm = dname_map[inp["이름"]]
                    wb.defined_names[_nm] = DefinedName(
                        name=_nm, attr_text=f"'{sh_name}'!$B${행}")
                    ws.cell(행, 3, inp.get("설명", ""))
                    행 += 1

                calc_hdr_row = 행
                for cc, h in enumerate(["단계", "수식", "도구 값", "확인", "설명"], 1):
                    c = ws.cell(행, cc, h); c.font = bold; c.fill = header_fill
                행 += 1
                for s in formula:
                    단계명 = s["이름"]
                    dname = dname_map[단계명]
                    ws.cell(행, 1, 단계명)
                    수식셀 = ws.cell(행, 2, f"={_이름_치환(s['식'], dname_map)}")
                    수식셀.number_format = money_fmt
                    wb.defined_names[dname] = DefinedName(
                        name=dname, attr_text=f"'{sh_name}'!$B${행}")
                    도구값 = s["값"]
                    vc = ws.cell(행, 3)
                    if isinstance(도구값, (int, float)):
                        _set_money(vc, 도구값)
                    else:
                        vc.value = 도구값
                    ws.cell(행, 4, f'=IF(B{행}=C{행},"일치","확인 필요")')
                    ws.cell(행, 5, s.get("설명", ""))
                    행 += 1
                next_table_row = 행

            행 = next_table_row if formula else 1
            ws.cell(행, 1, "항목").font = bold
            ws.cell(행, 2, "금액").font = bold
            ws.cell(행, 1).fill = header_fill
            ws.cell(행, 2).fill = header_fill
            행 += 1

            all_items: list[tuple[str, Any]] = []
            all_items.extend(_numeric_items(res))
            if isinstance(calc_dict, dict):
                all_items.extend(_numeric_items(calc_dict))

            항목맵: dict[str, Any] = {}
            for k, v in all_items:
                항목맵[k] = v

            for k, v in 항목맵.items():
                ws.cell(행, 1, k)
                if isinstance(v, (int, float)):
                    _set_money(ws.cell(행, 2), v)
                else:
                    ws.cell(행, 2, _cell_value(v))
                행 += 1

            정착_start = 행 + 1
            settlements = res.get("세무조정", [])
            합계_수식행 = None
            if settlements:
                행 = 정착_start
                ws.cell(행, 1, "구분").font = bold
                ws.cell(행, 2, "조정").font = bold
                ws.cell(행, 3, "금액").font = bold
                ws.cell(행, 4, "소득처분").font = bold
                for cc in range(1, 5):
                    ws.cell(행, cc).fill = header_fill
                행 += 1
                처분별: dict[str, int] = {}
                가산first_row = 행
                for s in settlements:
                    raw = s.get("금액", 0)
                    if isinstance(raw, (int, float)):
                        amt = raw; numeric = True
                    else:
                        amt = raw; numeric = False
                    raw_조정 = s.get("조정", "")
                    if s.get("구분") == "기부금 한도초과" and "조정구분" not in s:
                        # income_adjustment_total: 차가감소득금액 뒤에 더하는 줄(별지3 105) — 익금산입_손금불산입 합계 밖
                        조정 = "차가감 후 가산"
                    elif raw_조정 in ("익금산입", "손금불산입"):
                        조정 = "가산"
                    elif raw_조정 in ("손금산입", "익금불산입"):
                        조정 = "차감"
                    elif raw_조정 == "":
                        처분_tmp = s.get("소득처분", "")
                        조정 = "차감" if 처분_tmp.startswith("△") else "가산"
                    else:
                        조정 = raw_조정
                    처분 = s.get("소득처분", "")
                    ws.cell(행, 1, s.get("구분", ""))
                    ws.cell(행, 2, 조정)
                    if numeric:
                        _set_money(ws.cell(행, 3), amt)
                    else:
                        ws.cell(행, 3, amt)
                    ws.cell(행, 4, 처분)
                    if numeric:
                        처분별[처분] = 처분별.get(처분, 0) + amt
                    행 += 1
                처분last_row = 행 - 1

                가산_sumif_cond = f"B{가산first_row}:B{처분last_row}"
                차감_sumif_cond = f"B{가산first_row}:B{처분last_row}"
                금액_sumif_addr = f"C{가산first_row}:C{처분last_row}"

                ws.cell(행, 1, "가산 합계").font = bold
                ws.cell(행, 3, f'=SUMIF({가산_sumif_cond},"가산",{금액_sumif_addr})')
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                가산_수식행 = 행; 행 += 1

                ws.cell(행, 1, "차감 합계").font = bold
                ws.cell(행, 3, f'=SUMIF({차감_sumif_cond},"차감",{금액_sumif_addr})')
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                차감_수식행 = 행; 행 += 1

                ws.cell(행, 1, "순액").font = bold
                ws.cell(행, 3, f"=C{가산_수식행}-C{차감_수식행}")
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                행 += 1

                ws.cell(행, 1, "금액 합계(방향 무관)").font = bold
                ws.cell(행, 3, f"=SUM({금액_sumif_addr})")
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                합계_수식행 = 행; 행 += 1

                ws.cell(행, 1, "소득처분별 합계").font = bold
                ws.cell(행, 2, "소득처분").font = bold
                ws.cell(행, 3, "금액").font = bold
                for cc in range(1, 4):
                    ws.cell(행, cc).fill = header_fill
                행 += 1
                for 처분, tot in 처분별.items():
                    ws.cell(행, 1, "")
                    ws.cell(행, 2, 처분)
                    sumif_cond = f"D{가산first_row}:D{처분last_row}"
                    ws.cell(행, 3, f'=SUMIF({sumif_cond},"{처분}",{금액_sumif_addr})')
                    ws.cell(행, 3).number_format = money_fmt
                    행 += 1

            if 합계_수식행 is not None:
                v_익금 = res.get("익금산입_손금불산입")
                v_손금 = res.get("손금산입_익금불산입")
                if isinstance(v_익금, (int, float)) and isinstance(v_손금, (int, float)):
                    ws.cell(행, 1, "확인 (익금산입_손금불산입)").font = bold
                    ws.cell(행, 3, f'=IF(C{가산_수식행}={v_익금},"일치","확인 필요")')
                    행 += 1
                    ws.cell(행, 1, "확인 (손금산입_익금불산입)").font = bold
                    ws.cell(행, 3, f'=IF(C{차감_수식행}={v_손금},"일치","확인 필요")')
                    행 += 1
                else:
                    도구합계 = None; 도구합계키 = None
                    for key in ("손금불산입_합계", "한도초과", "소득처분별_합계"):
                        v = res.get(key)
                        if isinstance(v, (int, float)):
                            도구합계 = v; 도구합계키 = key; break
                    if 도구합계 is not None:
                        # 손금불산입_합계·한도초과는 가산(손금불산입·익금산입) 줄의 합 — 손금산입(△유보)까지 더한 '금액 합계'와 비교하지 않음
                        ws.cell(행, 1, f"확인 ({도구합계키})").font = bold
                        ws.cell(행, 3, f'=IF(C{가산_수식행}={도구합계},"일치","확인 필요")')
                        행 += 1

            산식 = (cd.get("data") or {}).get("산식") or ""
            if 산식:
                행 += 1
                ws.cell(행, 1, "산식").font = bold
                # 산식이 문장 목록이면 줄바꿈으로(JSON 대괄호·따옴표가 보이지 않게)
                ac = ws.cell(행, 2, "\n".join(산식) if isinstance(산식, list) and all(isinstance(x, str) for x in 산식)
                             else _cell_value(산식))
                ac.alignment = Alignment(wrap_text=True)

            # 세부: 중첩 판정·항목별·연도별 산출 등 위 표에 안 나온 값
            _write_detail_blocks(ws, ws.max_row + 2, res, calc_dict,
                                 bold=bold, header_fill=header_fill, money_fmt=money_fmt)

            ws.column_dimensions["A"].width = 32
            ws.column_dimensions["B"].width = 20
            ws.column_dimensions["C"].width = 16
            ws.freeze_panes = "A2"

    else:  # layout == "forms"
        # ── 1. 틀 템플릿 목록 구축 (call 순서대로, 한 call의 모든 템플릿 포함) ──
        템플릿_목록: list[dict] = []
        _tpl_seen: dict[str, int] = {}
        _cd_by_tool: dict[str, list[int]] = {}  # tool → call 인덱스 목록
        _skipped_tpl: set[str] = set()  # when 조건으로 skipped된 템플릿 키
        for i, cd in enumerate(결과들):
            if cd["error"] or not cd["result"]:
                continue
            tool = cd.get("tool", "")
            tpl_list = _FORM_TEMPLATES.get(tool, [])
            if not tpl_list:
                continue
            _cd_by_tool.setdefault(tool, []).append(i)
            for tpl in tpl_list:
                tkey = tpl["key"]
                # when 조건이 있으면 계산식_입력/결과 값으로 평가하여 거짓이면 렌더하지 않음
                when = tpl.get("when")
                if when:
                    계산식_입력 = (cd.get("data") or {}).get("계산식_입력", [])
                    입력_값 = {inp["이름"]: inp["값"] for inp in 계산식_입력}
                    결과_값 = cd.get("result", {}) or {}
                    # [입력.이름] 구문을 입력_값["이름"]으로, [결과.키] 구문을 결과_값["키"]로 치환
                    # FALSE/TRUE는 Python bool로 변환
                    def _when_repl(m):
                        prefix = m.group(1)  # "입력.이름" 또는 "결과.키"
                        if prefix.startswith("입력."):
                            return f"입력_값[{prefix[3:]!r}]"
                        elif prefix.startswith("결과."):
                            return f"결과_값[{prefix[3:]!r}]"
                        return f"{prefix}"
                    when_py = _re.sub(r"\[([^]]+)\]", _when_repl, when)
                    when_py = when_py.replace("FALSE", "False").replace("TRUE", "True")
                    if not eval(when_py, {"__builtins__": {}}, {"입력_값": 입력_값, "결과_값": 결과_값}):
                        _skipped_tpl.add(tkey)
                        continue
                # requires_args: 그 입력이 있는 call에서만 만든다(예: 공통사용재화 공급이 없으면 부가근거63 없음)
                req = tpl.get("requires_args")
                if req and not ((calls[i] or {}).get("args") or {}).get(req):
                    _skipped_tpl.add(tkey)
                    continue
                # unless_tool: 그 도구 call이 있으면 그 도구의 서식이 같은 칸을 채우므로 만들지 않음(부가22매입 ↔ common_input_tax)
                if tpl.get("unless_tool") and any(not c2["error"] and c2["result"] and c2.get("tool") == tpl["unless_tool"]
                                                  for c2 in 결과들):
                    continue
                템플릿_목록.append({"key": tkey, "sheet": tpl["sheet"], "form": tpl["form"], "tool": tool,
                                   "call_idx": i, "per_return": bool(tpl.get("per_return")),
                                   "one_sheet": bool(tpl.get("one_sheet"))})

        # one_sheet 틀(부동산임대공급가액명세서·가산세액 명세 등): 같은 도구 call을 한 장의 행으로 모은다 — 마지막 call 시트 하나만
        _합친_call: dict[str, list[int]] = {}
        for _k in {t["key"] for t in 템플릿_목록 if t["one_sheet"]}:
            _idx = [t["call_idx"] for t in 템플릿_목록 if t["key"] == _k]
            _합친_call[_k] = _idx
            템플릿_목록 = [t for t in 템플릿_목록 if t["key"] != _k or t["call_idx"] == _idx[-1]]

        # 같은 틀을 여러 call이 채울 때 시트 이름 규칙:
        #  - 신고서 한 부에 한 장인 서식(틀 per_return — 별지3·별지15·별지34 등): 마지막 call이 이름 그대로인 본 시트,
        #    앞선 call은 '<시트> (호출 N)'(N = calls 안 순번)으로 따로 남긴다. 본 시트끼리 교차 참조한다.
        #  - 자산·거래마다 한 장인 서식(별지20·별지84 등): 첫 call이 본 시트, 다음은 '<시트> (2)'…
        _tpl_groups: dict[str, list[dict]] = {}
        for tinfo in 템플릿_목록:
            _tpl_groups.setdefault(tinfo["key"], []).append(tinfo)
        for _lst in _tpl_groups.values():
            if _lst[0]["per_return"]:
                for tinfo in _lst:
                    tinfo["main"] = tinfo is _lst[-1]
                    if not tinfo["main"]:
                        tinfo["sheet"] = f"{tinfo['sheet']} (호출 {tinfo['call_idx'] + 1})"
            else:
                for n, tinfo in enumerate(_lst, 1):
                    tinfo["main"] = n == 1
                    if n > 1:
                        tinfo["sheet"] = f"{tinfo['sheet']} ({n})"
        _tpl_seen = {k: len(v) for k, v in _tpl_groups.items()}

        # 템플릿_목록을 spec 순서(별지3, 별지15, 별지23갑, 별지23을, 별지20정률, 별지16의2, 별지50을,
        # 부가22, 부가근거63, 부가근거64, 종소배당, 종소근로)로 정렬 — 같은 틀은 본 시트 먼저, 그다음 call 순
        _tpl_render_order = {"별지3": 1, "별지15": 2, "별지23갑": 3, "별지23을": 4,
                             "별지34": 4.5,
                             "별지32": 4.6, "별지33": 4.7,
                             "별지20정률": 5, "별지20정액": 5.5, "별지16의2": 6, "별지26갑": 6.1, "별지26을": 6.2, "별지50을": 7,
                             "부가22": 8, "부가근거63": 9, "부가근거64": 10, "종소배당": 11, "종소근로": 12,
                             "별지84": 13, "별지84세액": 14, "별지84부표1": 15,
                             "부가21간주공급": 7.6, "부가21대손": 7.65, "부가21카드": 7.7, "부가21가산세": 7.8, "부가22매입": 8,
                             "부가15": 8.5, "부가15한도없음": 8.5, "부가19": 8.6, "부가25": 8.7,
                             "증여10": 16, "원천23의1": 17, "원천23의1법인": 17, "원천23의1국내": 17.1,
                             "원천23의5": 18, "원천23의5법인": 18,
                             "별지4": 1.5, "별지8갑": 1.6}

        def _tpl_sort_key(t):
            return (_tpl_render_order.get(t["key"], 99), not t.get("main", True), t["call_idx"])
        템플릿_목록.sort(key=_tpl_sort_key)

        # ── 1. 목록 시트 ──
        ws_list = wb.active
        ws_list.title = "목록"
        시트이름들.append("목록")
        행 = 1

        ws_list.cell(행, 1, "서식 시트").font = bold
        ws_list.cell(행, 2, "서식 표기").font = bold
        for cc in range(1, 3):
            ws_list.cell(행, cc).fill = header_fill
        행 += 1

        for tinfo in 템플릿_목록:
            ws_list.cell(행, 1, tinfo["sheet"])
            ws_list.cell(행, 2, tinfo["form"])
            행 += 1

        # 자료 원칙에 따른 줄: 법인세 도구 call이 하나라도 있으면
        has_corp_tool = any(
            cd.get("tool") in ("entertainment_adjustment", "income_adjustment_total",
                                "depreciation_adjustment", "dividend_received_deduction",
                                "nonbusiness_interest_disallowance")
            for cd in 결과들 if not cd.get("error")
        )
        if has_corp_tool:
            ws_list.cell(행, 1, "별지 제50호서식(갑)")
            ws_list.cell(행, 2, "자본금과 적립금조정명세서 — 자료 없음(재무상태표 자본 자료 필요)")
            행 += 1
            ws_list.cell(행, 1, "별지 제50호서식(병)")
            ws_list.cell(행, 2, "해당 없음(해외현지기업 출자)")
            행 += 1

        # 틀의 `목록`([[이름, 설명]]) — 서식 중 이번에 만들지 않은 부분(자료 없음 등)을 렌더된 틀마다 한 번
        _목록_본: set[str] = set()
        for tinfo in 템플릿_목록:
            _t = next((t for t in _FORM_TEMPLATES.get(tinfo["tool"], []) if t["key"] == tinfo["key"]), None)
            for 이름, 설명 in (_t or {}).get("목록", []):
                if 이름 in _목록_본:
                    continue
                _목록_본.add(이름)
                ws_list.cell(행, 1, 이름)
                ws_list.cell(행, 2, 설명)
                행 += 1

        # when 조건으로 만들지 않은 틀에 `목록_생략` 문구가 있으면 그 줄(다른 call에서 만들었으면 쓰지 않음)
        for _tool_tpls in _FORM_TEMPLATES.values():
            for _t in _tool_tpls:
                if (_t["key"] in _skipped_tpl and _t["key"] not in _tpl_groups and _t.get("목록_생략")
                        and _t["sheet"] not in _목록_본):
                    _목록_본.add(_t["sheet"])
                    ws_list.cell(행, 1, _t["sheet"])
                    ws_list.cell(행, 2, _t["목록_생략"])
                    행 += 1

        # 종소배당이 when 조건으로 skipped된 경우 목록 줄에 해당 없음 추가
        if "종소배당" in _skipped_tpl:
            ws_list.cell(행, 1, "종소 배당·이자소득명세서")
            ws_list.cell(행, 2, "❻ 배당소득명세서·❺ 이자소득명세서 — 해당 없음(금융소득 2천만원 이하 분리과세)")
            행 += 1
        _목록_행 = 행  # 확인 메모·call 대응표·고지문은 서식을 다 그린 뒤 이 행부터

        ws_list.column_dimensions["A"].width = 30
        ws_list.column_dimensions["B"].width = 55
        ws_list.freeze_panes = "A2"

        # ── 2. 입력·가정 시트 생성 (템플릿 렌더링 전에 정의된 이름 생성) ──
        ws_inp = wb.create_sheet("입력·가정")
        시트이름들.append("입력·가정")
        행 = 1
        ws_inp.cell(행, 1, "call").font = bold
        ws_inp.cell(행, 2, "경로").font = bold
        ws_inp.cell(행, 3, "값").font = bold
        for cc in range(1, 4):
            ws_inp.cell(행, cc).fill = header_fill
        행 += 1
        for i, cd in enumerate(결과들):
            if cd["error"]:
                continue
            label = cd["label"]
            args = (calls[i] or {}).get("args", {})
            for 경로, 값 in _flatten_args(args):
                ws_inp.cell(행, 1, label)
                ws_inp.cell(행, 2, 경로)
                vc = ws_inp.cell(행, 3)
                if isinstance(값, (int, float)):
                    _set_money(vc, 값)
                else:
                    vc.value = _cell_value(값)
                행 += 1
        # forms 모드: 계산식_입력·계산식 단계별 정의된 이름 생성 (입력·가정 시트 아래)
        행 += 1
        for i, cd in enumerate(결과들):
            if cd["error"]:
                continue
            call_idx = i
            호출접두사 = f"호출{call_idx + 1}_"
            for inp in (cd.get("data") or {}).get("계산식_입력", []) or []:
                ws_inp.cell(행, 1, 호출접두사 + inp["이름"])
                vc = ws_inp.cell(행, 2)
                v = inp["값"]
                if isinstance(v, bool):
                    vc.value = v
                elif isinstance(v, (int, float)):
                    _set_money(vc, v)
                else:
                    vc.value = v
                _nm = _sanitize_dname(f"{호출접두사}{inp['이름']}", wb=wb)
                wb.defined_names[_nm] = DefinedName(
                    name=_nm, attr_text=f"'입력·가정'!$B${행}")
                ws_inp.cell(행, 3, inp.get("설명", ""))
                행 += 1
            for s in (cd.get("data") or {}).get("계산식", []) or []:
                ws_inp.cell(행, 1, 호출접두사 + s["이름"])
                vc = ws_inp.cell(행, 2)
                v = s["값"]
                if isinstance(v, bool):
                    vc.value = v
                elif isinstance(v, (int, float)):
                    _set_money(vc, v)
                else:
                    vc.value = v
                _nm = _sanitize_dname(f"{호출접두사}{s['이름']}", wb=wb)
                wb.defined_names[_nm] = DefinedName(
                    name=_nm, attr_text=f"'입력·가정'!$B${행}")
                ws_inp.cell(행, 3, s.get("설명", ""))
                행 += 1
            # 결과 dict 항목도 정의된 이름으로 등록 (템플릿 [결과.경로] 참조용)
            res = cd.get("result", {}) or {}
            for k, v in res.items():
                if isinstance(v, (int, float)):
                    ws_inp.cell(행, 1, 호출접두사 + "결과_" + k)
                    vc = ws_inp.cell(행, 2)
                    _set_money(vc, v)
                    _nm = _sanitize_dname(f"{호출접두사}결과_{k}", wb=wb)
                    wb.defined_names[_nm] = DefinedName(
                        name=_nm, attr_text=f"'입력·가정'!$B${행}")
                    행 += 1
            # calc_dict(=계산 단계 값) 항목도 정의된 이름으로 등록 (템플릿 [계산.경로] 참조용)
            calc_dict = (cd.get("data") or {}).get("계산") if isinstance((cd.get("data") or {}), dict) else None
            if isinstance(calc_dict, dict):
                for k, v in calc_dict.items():
                    if isinstance(v, (int, float)) and not (isinstance(v, float) and v == float("inf")):
                        ws_inp.cell(행, 1, 호출접두사 + k)
                        vc = ws_inp.cell(행, 2)
                        _set_money(vc, v)
                        _nm = _sanitize_dname(f"{호출접두사}{k}", wb=wb)
                        wb.defined_names[_nm] = DefinedName(
                            name=_nm, attr_text=f"'입력·가정'!$B${행}")
                        ws_inp.cell(행, 3, "")
                        행 += 1

        # ── 3. 틀 시트 렌더링 ──
        sheet_name_map: dict[str, str] = {}
        slot_map_all: dict[str, str] = {}
        _tpl_by_key: dict[str, dict] = {}
        for tinfo in 템플릿_목록:
            if tinfo.get("main", True):
                sheet_name_map[tinfo["key"]] = tinfo["sheet"]
            if tinfo["key"] not in _tpl_by_key:
                for _tpl in _FORM_TEMPLATES.get(tinfo["tool"], []):
                    if _tpl["key"] == tinfo["key"]:
                        _tpl_by_key[tinfo["key"]] = _tpl
                        break
            tpl = _tpl_by_key.get(tinfo["key"])
            if tpl is None:
                continue
            for s in tpl.get("slots", []):
                sid = s["id"]
                cell = s["cell"]
                slot_map_all[sid] = cell

        # slot_map_cross: {(ref_key, ref_id): (sheet, cell)} — cross 참조 lookup용
        # 1단계: 모든 템플릿의 slots 수집 (tkey → {sid: (sheet, cell)})
        # (같은 틀이 여러 시트면 본 시트 — 다른 틀에서 {틀key!id}로 가리키는 시트)
        all_slots: dict[str, dict[str, tuple[str, str]]] = {}
        for tinfo in 템플릿_목록:
            if not tinfo.get("main", True):
                continue
            tpl = _tpl_by_key[tinfo["key"]]
            all_slots[tinfo["key"]] = {}
            for s in tpl.get("slots", []):
                all_slots[tinfo["key"]][s["id"]] = (tinfo["sheet"], s["cell"])

        # tool: "*" (별지50을)는 유보 행이 1개 이상일 때 추가
        # (income_adjustment_total의 세무조정에서 유보 + depreciation 유보 행 포함)
        # 도구별 성공 call 순번(calls 순서). 서식 칸에 들어갈 값은 그 값을 만든 call에서만 가져온다
        # (예전처럼 calls의 몇 번째 자리로 가정하지 않음).
        _ok_calls: dict[str, list[int]] = {}
        for i, cd in enumerate(결과들):
            if not cd.get("error") and cd.get("result"):
                _ok_calls.setdefault(cd.get("tool", ""), []).append(i)

        def _last_call(tool_name: str) -> int | None:
            lst = _ok_calls.get(tool_name) or []
            return lst[-1] if lst else None

        def _세무조정(i: int | None) -> list[dict]:
            if i is None:
                return []
            return [s for s in ((결과들[i].get("result") or {}).get("세무조정") or []) if isinstance(s, dict)]

        # 별지50(을)은 income_adjustment_total 중 유보·△유보가 있는 마지막 call(없으면 마지막 call)로 만든다
        _adj_calls = _ok_calls.get("income_adjustment_total", [])
        _유보_call = next((i for i in reversed(_adj_calls)
                          if any(str(s.get("소득처분", "")).lstrip("△") == "유보" for s in _세무조정(i))),
                         _adj_calls[-1] if _adj_calls else None)
        _dep_keys = ("별지20정률", "별지20정액")

        # tool: "*" (별지50을)는 유보 행이 1개 이상일 때 추가
        # (income_adjustment_total의 세무조정에서 유보 + depreciation 유보 행 포함)
        _has_유보 = any(s.get("소득처분") == "유보" for i in range(len(결과들)) for s in _세무조정(i)) \
            or any(k in all_slots for k in _dep_keys)
        if _FORM_TEMPLATES.get("*", []) and _has_유보 and "별지50을" not in _tpl_seen:
            _tpl_seen["별지50을"] = 1
            별지50_tpl = _FORM_TEMPLATES["*"][0]
            sheet_name = 별지50_tpl["sheet"]
            adj_call_idx = _유보_call if _유보_call is not None else 0
            tinfo_50 = {"key": "별지50을", "sheet": sheet_name, "form": 별지50_tpl["form"],
                       "tool": "*", "call_idx": adj_call_idx, "main": True, "per_return": True}
            템플릿_목록.append(tinfo_50)
            sheet_name_map["별지50을"] = sheet_name
            _tpl_by_key["별지50을"] = 별지50_tpl
            all_slots["별지50을"] = {}
            for s in 별지50_tpl.get("slots", []):
                all_slots["별지50을"][s["id"]] = (sheet_name, s["cell"])
            # 별지50을 추가 후 다시 정렬하여 올바른 순서 유지
            템플릿_목록.sort(key=_tpl_sort_key)

        # adj_slots 구축: adjustment → [(시트명, 셀, check_path, call_idx)] — 시트마다(같은 틀 여러 장이면 각각)
        adj_slots: dict[str, list[tuple[str, str, str, int]]] = {}
        for tinfo in 템플릿_목록:
            tpl = _tpl_by_key[tinfo["key"]]
            for s in tpl.get("slots", []):
                adj = s.get("adjustment")
                if adj:
                    adj_slots.setdefault(adj, []).append((tinfo["sheet"], s["cell"], s.get("adjustment_check", s.get("check", "")),
                                                          tinfo["call_idx"]))

        # 2단계: {틀key!id} cross 참조 파싱 (slot 수식 + table 열 수식)
        cross_refs: set[tuple[str, str]] = set()
        for tinfo in 템플릿_목록:
            tpl = _tpl_by_key[tinfo["key"]]
            for s in tpl.get("slots", []):
                f = s.get("f", "") or ""
                for m in _re.finditer(r"\{([^}]+)\}", f):
                    rest = m.group(1)
                    if "!" in rest:
                        ref_key, ref_id = rest.split("!", 1)
                        cross_refs.add((ref_key, ref_id))
            for tbl in tpl.get("tables", []):
                for col_spec in tbl.get("cols", {}).values():
                    if isinstance(col_spec, str):
                        for m in _re.finditer(r"\{([^}]+)\}", col_spec):
                            rest = m.group(1)
                            if "!" in rest:
                                ref_key, ref_id = rest.split("!", 1)
                                cross_refs.add((ref_key, ref_id))

        # 3단계: slot_map_cross 구성 (대상이 없는 cross 참조는 제외 — 렌더러에서 fallback 처리)
        slot_map_cross: dict[tuple[str, str], tuple[str, str]] = {}
        for ref_key, ref_id in cross_refs:
            if ref_key in all_slots and ref_id in all_slots[ref_key]:
                slot_map_cross[(ref_key, ref_id)] = all_slots[ref_key][ref_id]
            # 대상이 없으면 제외 (render_form_sheet에서 fallback 값 사용)

        # ── source_data 구축 (테이블 소스 + cross fallback용) ──
        # 표 source는 그 값을 만든 call에서 만든다. _call_src[call_idx]는 그 call의 시트에만 쓰는 source,
        # source_data는 본 시트(같은 도구를 여러 번 부르면 마지막 call) 기준 기본값.
        source_data: dict[str, list[dict]] = {}
        _call_src: dict[int, dict[str, list[dict]]] = {}

        def _조정_rows(i: int | None) -> tuple[list[dict], list[dict]]:
            """income_adjustment_total 세무조정 → 별지15 가산·차감 행. 기부금 한도초과(차가감 뒤 가산, 별지3 105)는 빼다."""
            add: list[dict] = []
            sub: list[dict] = []
            for s in _세무조정(i):
                if s.get("구분") == "기부금 한도초과" and "조정구분" not in s:
                    continue
                조정 = s.get("조정", "")
                금액 = s.get("금액", 0)
                if not isinstance(금액, (int, float)):
                    continue
                처분 = s.get("소득처분", "")
                if 조정 in ("익금산입", "손금불산입"):
                    # 별지15 작성방법: 익금산입·손금불산입(가산) — 상여 100·배당 200·기타소득 300·유보 400·기타사외유출 500·기타 600
                    # △유보는 표에 없으나 가산 쪽에 오면 유보와 같은 400; 표에 없는 처분은 ""(잘못된 코드 방지)
                    if 처분 == "상여":
                        코드 = "100"
                    elif 처분 == "배당":
                        코드 = "200"
                    elif 처분 == "기타소득":
                        코드 = "300"
                    elif 처분 in ("유보", "△유보"):
                        코드 = "400"
                    elif 처분 == "기타사외유출":
                        코드 = "500"
                    elif 처분 == "기타":
                        코드 = "600"
                    elif 처분 == "임시유보":      # 국조령 제22조~제25조: 임시유보 700·이전소득 배당 810·출자의 증가 820
                        코드 = "700"
                    elif 처분 == "이전소득 배당":
                        코드 = "810"
                    elif 처분 == "출자의 증가":
                        코드 = "820"
                    else:
                        코드 = ""
                    add.append({"과목": s.get("구분", ""), "금액": 금액, "처분": 처분, "코드": 코드,
                                "종류": s.get("종류", s.get("구분", ""))})
                elif 조정 in ("손금산입", "익금불산입"):
                    # 별지15 작성방법: 손금산입·익금불산입(차감) — 유보·△유보 100·기타 200
                    코드 = "100" if 처분 in ("유보", "△유보") else ("200" if 처분 == "기타" else ("300" if 처분 == "출자의 증가" else ""))
                    sub.append({"과목": s.get("구분", ""), "금액": 금액, "처분": 처분, "코드": 코드,
                                "종류": s.get("종류", s.get("구분", ""))})
            return add, sub

        for i in _adj_calls:
            a, b = _조정_rows(i)
            _call_src.setdefault(i, {}).update({"조정_가산": a, "조정_차감": b})
        source_data["조정_가산"], source_data["조정_차감"] = _조정_rows(_last_call("income_adjustment_total"))

        # 피출자법인 소스: dividend_received_deduction 결과 → SPEC대로 {이름, 지분율(%)=출자비율×100}
        def _피출자_rows(i: int | None) -> list[dict]:
            if i is None:
                return []
            return [{"이름": inv.get("이름", ""), "지분율(%)": inv.get("출자비율", 0) * 100}
                    for inv in (결과들[i].get("result") or {}).get("피출자법인별", [])]
        for i in _ok_calls.get("dividend_received_deduction", []):
            _call_src.setdefault(i, {})["피출자법인"] = _피출자_rows(i)
        source_data["피출자법인"] = _피출자_rows(_last_call("dividend_received_deduction"))

        # 유보 소스(별지50을): 감가상각 서식 시트마다 한 행(그 시트 칸을 가리킴) + income_adjustment_total 유보·△유보
        # (income_adjustment_total이 없으면 각 도구 call의 세무조정 유보)
        _유보_rows: list[dict] = []
        _dep_cols = {"별지20정률": ("⑪", "㉗", "㉖"), "별지20정액": ("㉕", "㉔", "㉓")}
        _dep_vals: set = set()
        for tinfo in 템플릿_목록:
            if tinfo["key"] not in _dep_cols:
                continue
            ids = _dep_cols[tinfo["key"]]
            cells = {s["id"]: s["cell"] for s in _tpl_by_key[tinfo["key"]].get("slots", [])}
            sh = tinfo["sheet"]
            _유보_rows.append({
                "과목": f"감가상각비 한도초과({결과들[tinfo['call_idx']].get('label') or '감가상각자산'})",
                "기초": f"='{sh}'!{cells[ids[0]]}",
                "감소": f"='{sh}'!{cells[ids[1]]}",
                "증가": f"='{sh}'!{cells[ids[2]]}",
                "기말": "=B{r}-C{r}+D{r}",
                "비고": "",
            })
            dres = 결과들[tinfo["call_idx"]].get("result") or {}
            for k in ("상각부인액", "전기부인액_추인"):
                if isinstance(dres.get(k), (int, float)) and dres.get(k):
                    _dep_vals.add(dres[k])
        _유보_src = [_유보_call] if _유보_call is not None else [
            i for i, cd in enumerate(결과들) if cd.get("tool") != "depreciation_adjustment"]
        # 같은 과목(대손충당금·퇴직급여충당금 등)은 한 줄로 모으고, ②기초잔액은 그 과목의 전기 유보를 입력으로 받은 call에서 가져온다.
        # 기초를 준 call이 없으면 0이 아니라 빈칸 + 비고 안내, 감소가 있으면 ⑤기말도 빈칸(기초 없이 감소만 빼 음수가 되지 않게).
        _기초 = _유보_기초(_last_call, calls, 결과들)
        _묶음: dict[str, dict] = {}
        _유보_내역: list[tuple[str, str, int, str]] = []   # (과목, 감소|증가, 금액, 출처) — '입력·가정' 아래 표, ③·④는 이 표의 SUMIFS
        for i in _유보_src:
            _tool_i = 결과들[i].get("tool", "")
            for s in _세무조정(i):
                처분 = s.get("소득처분", "")
                if 처분 not in ("유보", "△유보"):
                    continue
                금액 = s.get("금액", 0)
                if not isinstance(금액, (int, float)):
                    continue
                adj_key = s.get("종류", s.get("구분", ""))
                이름 = s.get("구분", "") or adj_key
                if any(t["key"] in _dep_cols for t in 템플릿_목록):
                    # 감가상각 서식 시트 행과 같은 금액(상각부인액·전기부인액 추인)이면 그 행에서 처리됨
                    if adj_key == "감가상각비 한도초과" or ("상각" in f"{이름}{adj_key}" and 금액 in _dep_vals):
                        continue
                감소 = 처분 == "△유보" or s.get("조정") in ("손금산입", "익금불산입")
                fam = _유보_과목(s, _tool_i)
                key = fam or (이름 if i == _유보_call else adj_key)
                g = _묶음.setdefault(key, {"과목": _유보_과목명.get(fam, key), "가족": fam, "감소": 0, "증가": 0})
                g["감소" if 감소 else "증가"] += int(금액)
                _유보_내역.append((g["과목"], "감소" if 감소 else "증가", int(금액),
                                 f"{결과들[i].get('label') or _tool_i} — {이름} ({s.get('조정', '')}, {처분})"))
        for fam, v in _기초.items():   # 기초만 있고 당기 증감이 없는 과목도 줄로(기말 = 기초)
            if v and fam not in _묶음:
                _묶음[fam] = {"과목": _유보_과목명.get(fam, fam), "가족": fam, "감소": 0, "증가": 0}
        for key, g in _묶음.items():
            기초 = _기초.get(g["가족"]) if g["가족"] else None
            if 기초 is not None:
                _유보_rows.append({"과목": g["과목"], "기초": 기초, "감소": g["감소"], "증가": g["증가"],
                                  "기말": "=B{r}-C{r}+D{r}", "비고": ""})
            elif g["감소"]:
                _유보_rows.append({"과목": g["과목"], "기초": None, "감소": g["감소"], "증가": g["증가"], "기말": None,
                                  "비고": "②기초잔액 자료 없음 — 전기 유보를 넣고 ⑤ = ② − ③ + ④"})
            else:
                _유보_rows.append({"과목": g["과목"], "기초": None, "감소": 0, "증가": g["증가"],
                                  "기말": "=B{r}-C{r}+D{r}", "비고": "②기초잔액 자료 없음(전기 유보가 있으면 ②에 넣음)"})
        # ③감소·④증가: 세무조정 유보·△유보 한 줄씩 '입력·가정' 아래 표에 두고 과목·구분별 SUMIFS(숫자를 박지 않음)
        if any(not str(r.get("감소", "")).startswith("=") for r in _유보_rows):
            r0 = ws_inp.max_row + 2
            for cc, h in enumerate(["별지50(을) 과목", "구분", "출처(세무조정)", "금액"], 1):
                c = ws_inp.cell(r0, cc, h); c.font = bold; c.fill = header_fill
            for k, (과목, 구분, 금액, 출처) in enumerate(_유보_내역, 1):
                ws_inp.cell(r0 + k, 1, 과목); ws_inp.cell(r0 + k, 2, 구분); ws_inp.cell(r0 + k, 3, 출처)
                _set_money(ws_inp.cell(r0 + k, 4), 금액)
            r1, r2 = r0 + 1, r0 + max(1, len(_유보_내역))
            def _sumifs(구분: str) -> str:
                return (f"=SUMIFS('입력·가정'!$D${r1}:$D${r2},'입력·가정'!$A${r1}:$A${r2},A{{r}},"
                        f"'입력·가정'!$B${r1}:$B${r2},\"{구분}\")")
            for r in _유보_rows:
                if str(r.get("감소", "")).startswith("="):
                    continue   # 감가상각 서식 시트 칸을 가리키는 행
                if sum(x[2] for x in _유보_내역 if x[0] == r["과목"] and x[1] == "감소") == (r.get("감소") or 0):
                    r["감소"] = _sumifs("감소")
                if sum(x[2] for x in _유보_내역 if x[0] == r["과목"] and x[1] == "증가") == (r.get("증가") or 0):
                    r["증가"] = _sumifs("증가")
        source_data["유보"] = _유보_rows

        # 공통사용재화 소스: common_input_tax args common_asset_sales → {순번: 1..} (call마다)
        for i in _ok_calls.get("common_input_tax", []):
            args = (calls[i] or {}).get("args", {}) or {}
            _재화_rows = [{"순번": idx, "공급가액": int(sale.get("sale_price", 0))}
                          for idx, sale in enumerate(args.get("common_asset_sales") or [], 1)]
            _call_src.setdefault(i, {})["공통사용재화"] = _재화_rows
            source_data.setdefault("공통사용재화", _재화_rows)

        # 부가 별지22 2.(불공제 사유별): vat_input_tax_deduction 마지막 call — 세금계산서 수취분을 사유(①~⑧)별로 묶음
        _vid = _last_call("vat_input_tax_deduction")
        if _vid is not None:
            _사유행 = {k: {"매수": 0, "공급가액": 0, "매입세액": 0, "항목": []} for k in range(1, 9)}
            _성격행 = {"사업무관": 2, "비영업용승용차": 3, "접대": 4, "면세사업": 5, "토지관련": 6}
            _v_items = ((calls[_vid] or {}).get("args") or {}).get("items") or []
            _v_calc = ((결과들[_vid].get("data") or {}).get("계산") or {}).get("항목별") or []
            for n, row in enumerate(_v_calc):
                it = _v_items[n] if n < len(_v_items) and isinstance(_v_items[n], dict) else {}
                불공제 = (row.get("세액") or 0) - (row.get("공제세액") or 0)
                사유 = row.get("불공제사유") or ""
                if not 사유 or 불공제 <= 0 or it.get("증빙", "세금계산서") != "세금계산서":
                    continue
                k = _성격행.get(it.get("성격", ""))
                if k is None:
                    k = 7 if "①8호" in 사유 else (1 if "①2호" in 사유 or "①1호" in 사유 else None)
                if k is None:
                    continue
                공급가액 = it.get("실제공급가액") or it.get("공급가액")
                if 공급가액 is None and it.get("공급대가") is not None:
                    공급가액 = int(it["공급대가"] * 100 / 110)
                d = _사유행[k]
                d["매수"] += 1
                d["공급가액"] += int(공급가액 or 0)
                d["매입세액"] += int(불공제)
                d["항목"].append(str(row.get("항목", "")))
            _불공제_rows = [{"매수": d["매수"] or None, "공급가액": d["공급가액"] or None,
                            "매입세액": d["매입세액"] or None, "비고": ", ".join(d["항목"])}
                           for d in (_사유행[k] for k in range(1, 9))]
            _불공제_rows.append({"매수": "=SUM(D12:D19)", "공급가액": "=SUM(E12:E19)",
                                "매입세액": "=SUM(F12:F19)", "비고": ""})
            source_data["22_불공제"] = _불공제_rows

        # 부가 별지22 5.(재계산): input_tax_recalculation call마다 당기(마지막 이력) 재계산 한 행
        _재계산_rows: list[dict] = []
        _재계산_calls: list[int] = []
        for i in _ok_calls.get("input_tax_recalculation", []):
            dat = 결과들[i].get("data") or {}
            이력 = dat.get("이력") or []
            last = 이력[-1] if 이력 and isinstance(이력[-1], dict) else None
            if not last or not last.get("재계산"):
                continue
            args = (calls[i] or {}).get("args") or {}
            체감 = 0.05 if args.get("asset_type") == "건물·구축물" else 0.25
            _재계산_calls.append(i)
            _재계산_rows.append({
                "매입세액": (dat.get("결과") or {}).get("매입세액", args.get("input_tax")),
                "경감률": round(max(0.0, 1 - 체감 * int(last.get("경과과세기간수") or 0)), 6),
                "비율": last.get("변동"),
            })
        if _재계산_rows:
            source_data["22_재계산"] = _재계산_rows
        # 배당명세·이자명세 소스: financial_income_aggregate 계산.항목별 → {코드, 일련번호, 항목, 금액, 대상?, 가산?} (call마다)
        def _금융_rows(cd: dict) -> tuple[list[dict], list[dict], list[str]]:
            calc_dict = (cd.get("data") or {}).get("계산", {})
            항목별 = calc_dict.get("항목별", [])
            판단목록 = (cd.get("data") or {}).get("판단", [])
            # 판단목록에서 입력 순서 복구 (계산.항목별은 dict라 순서 없음)
            순서맵 = {h["항목"]: idx for idx, h in enumerate(판단목록)}
            gu_base = calc_dict.get("Gross-up 기준액")          # Gross-up 대상금액(합계 행 ⑥)
            gu_rate = calc_dict.get("가산율")                    # 가산율
            gu_target_sum = sum(it.get("금액", 0) for it in 항목별 if it.get("구분") == "GU대상")
            _배당_rows: list[dict] = []
            _이자_rows: list[dict] = []
            배당_메모: list[str] = []
            # 코드 매핑: 배당 GU대상=21, GU비대상=22, 출자공동=28, 이자=13, 제외는 제외
            코드맵 = {"GU대상": "21", "GU비대상": "22", "출자공동": "28", "이자": "13", "제외": None}
            for item in 항목별:
                구분 = item.get("구분", "")
                코드 = 코드맵.get(구분)
                if 코드 is None:
                    continue  # 제외는 넣지 않음
                항목명 = item.get("항목", "").replace("_", " ")
                금액 = item.get("금액", 0)
                row: dict = {"코드": 코드, "일련번호": 0, "항목": 항목명, "금액": 금액,
                             "_순서": 순서맵.get(item.get("항목", ""), 999)}
                # Gross-up 대상금액이 합계 행에만 있는지 행별 배분 가능한지 판정
                if 구분 == "GU대상" and gu_base is not None and gu_rate is not None \
                        and gu_base == gu_target_sum:
                    # 전액이 가산 대상 → 행별로 대상·가산 채움
                    row["대상"] = 금액
                    row["가산"] = int(Fraction(금액) * Fraction(str(gu_rate)))  # 원 미만 절사(정수 연산)
                if 구분 in ("GU대상", "GU비대상", "출자공동"):
                    _배당_rows.append(row)
                elif 구분 == "이자":
                    _이자_rows.append(row)
            # 코드 오름차순, 같은 코드 안에서는 입력 순서(_순서)로 정렬, 일련번호는 코드별 1부터
            for rows in (_배당_rows, _이자_rows):
                rows.sort(key=lambda r: (r["코드"], r["_순서"]))
                last_code, seq = None, 0
                for r in rows:
                    seq = 1 if r["코드"] != last_code else seq + 1
                    last_code = r["코드"]
                    r["일련번호"] = seq
                    del r["_순서"]
            # Gross-up 대상금액이 합계 행에만 있을 때 배당 시트 메모 안내
            if gu_base is not None and gu_target_sum and gu_base != gu_target_sum \
                    and any(r["코드"] == "21" for r in _배당_rows):
                배당_메모.append("Gross-up 대상금액은 합계 행에만(행별 배분 기준 없음)")
            return _배당_rows, _이자_rows, 배당_메모

        for i in _ok_calls.get("financial_income_aggregate", []):
            b_rows, i_rows, b_memo = _금융_rows(결과들[i])
            _call_src.setdefault(i, {}).update({"배당명세": b_rows, "이자명세": i_rows})
            if b_memo:
                _call_src[i]["배당명세_메모"] = b_memo

        _fid = _last_call("financial_income_aggregate")
        if _fid is not None:
            source_data["배당명세"] = _call_src[_fid]["배당명세"]
            source_data["이자명세"] = _call_src[_fid]["이자명세"]

        # connection: adjustment 소스 행의 금액을 렌더된 서식 slot 참조로 치환(도구 값이 같은 시트만)
        # 1) 종류가 slot adjustment 이름과 같으면 그 칸, 2) 아니면 같은 계정 묶음(기업업무추진비·업무용승용차·기부금 등)
        #    adjustment 칸 중 도구 값이 금액과 같은 칸이 하나뿐일 때 그 칸 — 과목 이름을 자유롭게 적어도 서식 칸을 가리킴
        _가족어 = ("기업업무추진비", "접대비", "업무용승용차", "기부금", "감가상각", "대손", "퇴직", "수입배당금")

        def _adj_tv(call_idx: int, check_path: str):
            res = 결과들[call_idx].get("data") or {}   # cd["data"]에는 nested "결과"가 있음
            paths = check_path.split("+") if check_path else []
            vals = [tool_value(res, p) for p in paths]
            if not vals or any(not isinstance(v, (int, float)) for v in vals):
                return None
            return sum(vals)

        _조정_소스들 = [source_data] + [v for v in _call_src.values() if "조정_가산" in v]
        for src in _조정_소스들:
            _쓴_칸: set = set()   # 한 별지15(소스) 안에서 한 칸을 두 행이 가리키지 않게
            for src_name in ("조정_가산", "조정_차감"):
                for row in src.get(src_name, []):
                    kind = row.get("종류", row.get("과목", ""))
                    amount = row.get("금액", 0)
                    if not isinstance(amount, (int, float)) or not amount:
                        continue
                    hit = None
                    for 시트명, 셀, check_path, call_idx in adj_slots.get(kind, []):
                        if _adj_tv(call_idx, check_path) == amount:
                            hit = (시트명, 셀)
                            break
                    if hit is None:
                        글 = f"{row.get('과목', '')} {row.get('종류', '')}"
                        fam = {w for w in _가족어 if w in 글}
                        cand = [(시트명, 셀) for label, lst in adj_slots.items() if fam & {w for w in _가족어 if w in label}
                                for 시트명, 셀, check_path, call_idx in lst
                                if (시트명, 셀) not in _쓴_칸 and _adj_tv(call_idx, check_path) == amount]
                        if len(set(cand)) == 1:
                            hit = cand[0]
                    if hit is not None:
                        row["금액"] = f"='{hit[0]}'!{hit[1]}"
                        _쓴_칸.add(hit)

        # 서식 머리 개정일: 그 과세기간 신고기한보다 뒤에 개정된 서식이면 개정일 표기를 뺀다
        import datetime as _dt

        def _period_end(i: int) -> "_dt.date | None":
            _gd = str(((calls[i] or {}).get("args") or {}).get("gift_date") or "")
            if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", _gd):   # 증여세: 증여일(신고기한은 _deadline에서)
                return _dt.date.fromisoformat(_gd)
            m = _re.search(r"~\s*(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", period or "")
            if m:
                try:
                    return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                except ValueError:
                    return None
            a = (calls[i] or {}).get("args") or {}
            vp = str(a.get("period", ""))
            m = _re.match(r"^(\d{4})-([12])$", vp)
            if m:
                return _dt.date(int(m.group(1)), 6, 30) if m.group(2) == "1" else _dt.date(int(m.group(1)), 12, 31)
            y = a.get("year")
            if isinstance(y, int) and 1900 < y < 2100:
                if vp == "1기":
                    return _dt.date(y, 6, 30)
                return _dt.date(y, 12, 31)
            return None

        def _deadline(form: str, end: "_dt.date | None") -> "_dt.date | None":
            if end is None:
                return None
            if form.startswith("부가가치세법"):
                return end + _dt.timedelta(days=25)
            if form.startswith("법인세법"):
                y, mth = end.year, end.month + 3
                if mth > 12:
                    y, mth = y + 1, mth - 12
                nxt = _dt.date(y + (mth == 12), 1 if mth == 12 else mth + 1, 1)
                return nxt - _dt.timedelta(days=1)
            if form.startswith("소득세법"):
                return _dt.date(end.year + 1, 5, 31)
            if form.startswith("상속세 및 증여세법"):   # 증여일이 속하는 달의 말일부터 3개월(상증법 제68조①)
                y, mth = end.year + (end.month + 4 > 12), (end.month + 3) % 12 + 1
                return _dt.date(y, mth, 1) - _dt.timedelta(days=1)
            return None

        # 본 별지3에 채울 다른 도구 call: 마지막 corporate_tax call(112 과세표준·115 산출세액),
        # 마지막 minimum_tax_adjustment call(110 비과세소득·111 소득공제 — 없으면 빈칸)
        _other_calls: dict[str, tuple[int, dict]] = {}
        for _t in ("corporate_tax", "minimum_tax_adjustment"):
            _ci = _last_call(_t)
            if _ci is not None:
                _other_calls[_t] = (_ci, 결과들[_ci].get("data") or {})

        _개정일_생략: list[tuple[str, str]] = []
        _시트별_메모: dict[str, list[str]] = {}
        for tinfo in 템플릿_목록:
            cd = 결과들[tinfo["call_idx"]]
            tkey = tinfo["key"]
            tpl = _tpl_by_key.get(tkey)
            if tpl is None:
                continue

            ws = wb.create_sheet(tinfo["sheet"])
            input_map: dict[str, Any] = {}
            for inp in (cd.get("data") or {}).get("계산식_입력", []) or []:
                input_map[inp["이름"]] = inp["값"]
            for s in (cd.get("data") or {}).get("계산식", []) or []:
                input_map[s["이름"]] = s["값"]

            # {{과세기간}} 구성 (부가 틀): 이 시트를 만든 common_input_tax call의 year·period로 "{year}년 제N기 ( ... )"
            과세기간 = ""
            _args = (calls[tinfo["call_idx"]] or {}).get("args") or {}
            if tinfo["tool"] == "common_input_tax":
                _y, _p = _args.get("year", ""), _args.get("period", "")
                if _p == "1기":
                    과세기간 = f"{_y}년 제1기 ( 1월 1일 ~ 6월 30일 )"
                elif _p == "2기":
                    과세기간 = f"{_y}년 제2기 ( 7월 1일 ~ 12월 31일 )"
            elif tinfo.get("form", "").startswith("부가가치세법"):
                과세기간 = vat_period_text(_args)
            _귀속연도 = _args.get("year") if isinstance(_args.get("year"), int) else None

            # 표 source: 본 시트 기준 기본값 + 이 call의 source(별지15·별지16의2·종소배당·부가 등은 그 call 값)
            call_sources = {**source_data, **_call_src.get(tinfo["call_idx"], {})}
            # 배당명세 행별 메모(행별 배분 기준 없음 안내)를 시트별 메모에 추가
            for _m in _call_src.get(tinfo["call_idx"], {}).get("배당명세_메모", []):
                _시트별_메모.setdefault(tinfo["sheet"], []).append(_m)
            form_res = cd.get("data", cd.get("result", {}))
            # 별지26 (갑)·(을): 표 source는 그 call 결과로(같은 도구 call이 여럿이면 call마다 따로)
            if tinfo["tool"] == "nonbusiness_interest_disallowance":
                form_res = nonbusiness_form_data(form_res, (calls[tinfo["call_idx"]] or {}).get("args", {}))
                call_sources = {**call_sources, **nonbusiness_form_sources(form_res)}
            # 서식_표를 table source로 사용 (도구에 관계없이 결과의 서식_표가 있으면 합침)
            서식_표 = form_res.get("서식_표", {}) if isinstance(form_res, dict) else {}
            if 서식_표:
                call_sources = {**call_sources, **서식_표}
            # one_sheet 틀: 같은 도구 call 전부를 표 행으로, 도구 값 합계는 확인 칸용 `계산`에(내보내기 전용)
            if tinfo.get("one_sheet") and tkey in _합친_call:
                _ents = [(j, (calls[j] or {}).get("args") or {}, 결과들[j].get("data") or {}) for j in _합친_call[tkey]]
                _src, _tot, _memo = merged_form_sources(tinfo["tool"], _ents, calls)
                call_sources = {**call_sources, **_src}
                if _tot:
                    form_res = {**form_res, "계산": {**(form_res.get("계산") or {}), **_tot}}
                for _n in _memo:
                    _시트별_메모.setdefault(tinfo["sheet"], []).append("확인 필요 — " + _n)
            # 교차 참조는 같은 call에서 만든 시트를 가리킨다(같은 도구 call이 둘 이상이면 같은 call 시트끼리)
            cross_this = dict(slot_map_cross)
            for (ref_key, ref_id) in slot_map_cross:
                same = next((t for t in 템플릿_목록 if t["key"] == ref_key and t["call_idx"] == tinfo["call_idx"]), None)
                if same is not None:
                    cross_this[(ref_key, ref_id)] = (same["sheet"], all_slots[ref_key][ref_id][1])
            try:
                _info = render_form_sheet(ws, tpl, form_res, input_map,
                                          sheet_name_map, slot_map_all, cross_this, tkey,
                                          call_idx=tinfo["call_idx"], company=company, period=period, biz_no=biz_no,
                                          source_data=call_sources, all_slots=all_slots,
                                          label=cd.get("label", ""), 과세기간=과세기간,
                                          other_calls=_other_calls if tinfo.get("main", True) else {},
                                          form_deadline=_deadline(tinfo.get("form", ""), _period_end(tinfo["call_idx"])),
                                          귀속연도=_귀속연도)
            except ValueError as e:
                if "max_rows" not in str(e):
                    raise
                return {"error": f"입력 확인 필요 — {tpl.get('form', tkey)}의 칸보다 행이 많아 엑셀을 만들지 않음: {e}. 서식 칸에 맞게 묶거나 나눠서 호출하세요"}
            if (_info or {}).get("개정일_생략"):
                _개정일_생략.append((tinfo["sheet"], _info["개정일_생략"]))
            시트이름들.append(tinfo["sheet"])

        # 같은 금액을 두 도구가 따로 계산했는데 값이 다르면(입력이 서로 다름) 서식 시트와 목록에 알린다
        # (서식 도구, 그 결과 키, 같은 금액을 내는 다른 도구, 그 결과 키, 서식 틀, 이름)
        _대조 = [("bad_debt_adjustment", "한도초과", "bad_debt_allowance", "한도초과(유보)", "별지34", "대손충당금 한도초과")]
        for t_form, f_key, t_other, o_key, form_key, 이름 in _대조:
            fi = next((t["call_idx"] for t in 템플릿_목록 if t["key"] == form_key and t.get("main")), None)
            if fi is None:
                continue
            fv = (결과들[fi].get("result") or {}).get(f_key)
            for j in _ok_calls.get(t_other, []):
                ov = (결과들[j].get("result") or {}).get(o_key)
                if isinstance(fv, (int, float)) and isinstance(ov, (int, float)) and fv != ov:
                    sh = sheet_name_map.get(form_key, "")
                    _시트별_메모.setdefault(sh, []).append(
                        f"확인 필요 — 이 서식은 호출 {fi + 1} '{결과들[fi].get('label', '')}' 결과로 채움: "
                        f"{이름} {fv:,}원. 같은 파일의 호출 {j + 1} '{결과들[j].get('label', '')}'는 "
                        f"{ov:,}원 — 두 호출의 입력(채권잔액·설정률 등)이 서로 다름")
        # 부가 별지22 4.절은 영 제81조④ 정산만 적는다(작성방법 3) — 예정→확정 정산은 그 절에 넣지 않고 서식 아래 메모로
        _안내_메모: dict[str, list[str]] = {}
        for tinfo in 템플릿_목록:
            if tinfo["key"] != "부가22":
                continue
            dat = 결과들[tinfo["call_idx"]].get("data") or {}
            k = dat.get("계산") or {}
            if (dat.get("서식_표") or {}).get("22_정산") or not k.get("불공제_확정"):
                continue
            _안내_메모.setdefault(tinfo["sheet"], []).append(
                f"참고 — 예정신고분 확정 정산(영 제81조①·제82조): 과세기간 공통매입세액 {k.get('공통매입세액_과세기간합계', 0):,}원 × "
                f"면세비율 {k.get('면세비율_과세기간', 0):.2%} = {k.get('불공제_과세기간합계', 0):,}원 − 예정신고 불공제 "
                f"{k.get('불공제_예정반영', 0):,}원 = 확정 불공제 {k.get('불공제_확정', 0):,}원. "
                f"4.절(⑮~⑲)은 영 제81조④로 안분한 매입세액의 정산만 적으므로 빈칸")
        for memo, color in ((_시트별_메모, "C00000"), (_안내_메모, "595959")):
            for sh, notes in memo.items():
                if sh not in wb.sheetnames:
                    continue
                _ws = wb[sh]
                _r = (_ws.max_row or 0) + 2
                for n in notes:
                    _ws.cell(_r, 1, n).font = Font(color=color, size=9)
                    _r += 1
        # ── 3b. 계산 N 시트들 — call마다 한 장, N은 calls 안 순번(1부터) ──
        # 서식 틀로 간 call·오류 난 call도 시트를 만든다: 계산 시트 수 = call 수, '계산 N' = N번째 call.
        calc_idx = 0
        _calc_sheets: dict[int, str] = {}
        for _ci, cd in enumerate(결과들):
            calc_idx = _ci + 1
            sh_name = f"계산 {calc_idx}"
            ws = wb.create_sheet(sh_name)
            시트이름들.append(sh_name)
            _calc_sheets[_ci] = sh_name
            if cd["error"] or not cd["result"]:
                for rr, (k, v) in enumerate((("label", cd.get("label", "")), ("도구", cd.get("tool", "")),
                                              ("오류", cd.get("error") or "결과 없음"),
                                              ("안내", _cell_value(cd.get("basis")) if cd.get("basis") else "")), 1):
                    ws.cell(rr, 1, k).font = bold
                    ws.cell(rr, 2, v)
                ws.column_dimensions["A"].width = 16
                ws.column_dimensions["B"].width = 60
                continue
            res = cd.get("result", {}) or {}
            calc_dict = (cd.get("data") or {}).get("계산") if isinstance(cd.get("data"), dict) else None
            formula = (cd.get("data") or {}).get("계산식") if isinstance(cd.get("data"), dict) else None

            # 계산 N 시트 내용 — steps 모드와 동일한 레이아웃:
            #   계산식_입력 표 → 계산식 단계 수식·도구 값·확인 열 → 결과·계산 키-값 →
            #   세무조정 표 → 확인 수식 → 산식
            next_table_row = 1
            if formula:
                호출접두사 = f"호출{calc_idx}_"
                dname_map: dict[str, str] = {}
                for inp in (cd.get("data") or {}).get("계산식_입력", []) or []:
                    dname_map[inp["이름"]] = _sanitize_dname(f"{호출접두사}{inp['이름']}", wb=wb)
                for s in formula:
                    dname_map[s["이름"]] = _sanitize_dname(f"{호출접두사}{s['이름']}", wb=wb)

                행 = 1
                for cc, h in enumerate(["이름", "값", "설명"], 1):
                    c = ws.cell(행, cc, h); c.font = bold; c.fill = header_fill
                행 += 1
                for inp in (cd.get("data") or {}).get("계산식_입력", []) or []:
                    ws.cell(행, 1, inp["이름"])
                    vc = ws.cell(행, 2)
                    v = inp["값"]
                    if isinstance(v, bool):
                        vc.value = v
                    elif isinstance(v, (int, float)):
                        _set_money(vc, v)
                    else:
                        vc.value = v
                    _nm = dname_map[inp["이름"]]
                    wb.defined_names[_nm] = DefinedName(
                        name=_nm, attr_text=f"'{sh_name}'!$B${행}")
                    ws.cell(행, 3, inp.get("설명", ""))
                    행 += 1

                for cc, h in enumerate(["단계", "수식", "도구 값", "확인", "설명"], 1):
                    c = ws.cell(행, cc, h); c.font = bold; c.fill = header_fill
                행 += 1
                for s in formula:
                    단계명 = s["이름"]
                    dname = dname_map[단계명]
                    ws.cell(행, 1, 단계명)
                    수식셀 = ws.cell(행, 2, f"={_이름_치환(s['식'], dname_map)}")
                    수식셀.number_format = money_fmt
                    wb.defined_names[dname] = DefinedName(
                        name=dname, attr_text=f"'{sh_name}'!$B${행}")
                    도구값 = s["값"]
                    vc = ws.cell(행, 3)
                    if isinstance(도구값, (int, float)):
                        _set_money(vc, 도구값)
                    else:
                        vc.value = 도구값
                    ws.cell(행, 4, f'=IF(B{행}=C{행},"일치","확인 필요")')
                    ws.cell(행, 5, s.get("설명", ""))
                    행 += 1
                next_table_row = 행

            행 = next_table_row
            ws.cell(행, 1, "항목").font = bold
            ws.cell(행, 2, "금액").font = bold
            ws.cell(행, 1).fill = header_fill
            ws.cell(행, 2).fill = header_fill
            행 += 1

            all_items: list[tuple[str, Any]] = []
            all_items.extend(_numeric_items(res))
            if isinstance(calc_dict, dict):
                all_items.extend(_numeric_items(calc_dict))

            항목맵: dict[str, Any] = {}
            for k, v in all_items:
                항목맵[k] = v

            for k, v in 항목맵.items():
                ws.cell(행, 1, k)
                if isinstance(v, (int, float)):
                    _set_money(ws.cell(행, 2), v)
                else:
                    ws.cell(행, 2, _cell_value(v))
                행 += 1

            정착_start = 행 + 1
            settlements = res.get("세무조정", [])
            합계_수식행 = None
            if settlements:
                행 = 정착_start
                ws.cell(행, 1, "구분").font = bold
                ws.cell(행, 2, "조정").font = bold
                ws.cell(행, 3, "금액").font = bold
                ws.cell(행, 4, "소득처분").font = bold
                for cc in range(1, 5):
                    ws.cell(행, cc).fill = header_fill
                행 += 1
                처분별: dict[str, int] = {}
                가산first_row = 행
                for s in settlements:
                    raw = s.get("금액", 0)
                    if isinstance(raw, (int, float)):
                        amt = raw; numeric = True
                    else:
                        amt = raw; numeric = False
                    raw_조정 = s.get("조정", "")
                    if s.get("구분") == "기부금 한도초과" and "조정구분" not in s:
                        # income_adjustment_total: 차가감소득금액 뒤에 더하는 줄(별지3 105) — 익금산입_손금불산입 합계 밖
                        조정 = "차가감 후 가산"
                    elif raw_조정 in ("익금산입", "손금불산입"):
                        조정 = "가산"
                    elif raw_조정 in ("손금산입", "익금불산입"):
                        조정 = "차감"
                    elif raw_조정 == "":
                        처분_tmp = s.get("소득처분", "")
                        조정 = "차감" if 처분_tmp.startswith("△") else "가산"
                    else:
                        조정 = raw_조정
                    처분 = s.get("소득처분", "")
                    ws.cell(행, 1, s.get("구분", ""))
                    ws.cell(행, 2, 조정)
                    if numeric:
                        _set_money(ws.cell(행, 3), amt)
                    else:
                        ws.cell(행, 3, amt)
                    ws.cell(행, 4, 처분)
                    if numeric:
                        처분별[처분] = 처분별.get(처분, 0) + amt
                    행 += 1
                처분last_row = 행 - 1

                가산_sumif_cond = f"B{가산first_row}:B{처분last_row}"
                차감_sumif_cond = f"B{가산first_row}:B{처분last_row}"
                금액_sumif_addr = f"C{가산first_row}:C{처분last_row}"

                ws.cell(행, 1, "가산 합계").font = bold
                ws.cell(행, 3, f'=SUMIF({가산_sumif_cond},"가산",{금액_sumif_addr})')
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                가산_수식행 = 행; 행 += 1

                ws.cell(행, 1, "차감 합계").font = bold
                ws.cell(행, 3, f'=SUMIF({차감_sumif_cond},"차감",{금액_sumif_addr})')
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                차감_수식행 = 행; 행 += 1

                ws.cell(행, 1, "순액").font = bold
                ws.cell(행, 3, f"=C{가산_수식행}-C{차감_수식행}")
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                행 += 1

                ws.cell(행, 1, "금액 합계(방향 무관)").font = bold
                ws.cell(행, 3, f"=SUM({금액_sumif_addr})")
                ws.cell(행, 3).number_format = money_fmt
                ws.cell(행, 3).font = bold
                합계_수식행 = 행; 행 += 1

                ws.cell(행, 1, "소득처분별 합계").font = bold
                ws.cell(행, 2, "소득처분").font = bold
                ws.cell(행, 3, "금액").font = bold
                for cc in range(1, 4):
                    ws.cell(행, cc).fill = header_fill
                행 += 1
                for 처분, tot in 처분별.items():
                    ws.cell(행, 1, "")
                    ws.cell(행, 2, 처분)
                    sumif_cond = f"D{가산first_row}:D{처분last_row}"
                    ws.cell(행, 3, f'=SUMIF({sumif_cond},"{처분}",{금액_sumif_addr})')
                    ws.cell(행, 3).number_format = money_fmt
                    행 += 1

            if 합계_수식행 is not None:
                v_익금 = res.get("익금산입_손금불산입")
                v_손금 = res.get("손금산입_익금불산입")
                if isinstance(v_익금, (int, float)) and isinstance(v_손금, (int, float)):
                    ws.cell(행, 1, "확인 (익금산입_손금불산입)").font = bold
                    ws.cell(행, 3, f'=IF(C{가산_수식행}={v_익금},"일치","확인 필요")')
                    행 += 1
                    ws.cell(행, 1, "확인 (손금산입_익금불산입)").font = bold
                    ws.cell(행, 3, f'=IF(C{차감_수식행}={v_손금},"일치","확인 필요")')
                    행 += 1
                else:
                    도구합계 = None; 도구합계키 = None
                    for key in ("손금불산입_합계", "한도초과", "소득처분별_합계"):
                        v = res.get(key)
                        if isinstance(v, (int, float)):
                            도구합계 = v; 도구합계키 = key; break
                    if 도구합계 is not None:
                        # 손금불산입_합계·한도초과는 가산(손금불산입·익금산입) 줄의 합 — 손금산입(△유보)까지 더한 '금액 합계'와 비교하지 않음
                        ws.cell(행, 1, f"확인 ({도구합계키})").font = bold
                        ws.cell(행, 3, f'=IF(C{가산_수식행}={도구합계},"일치","확인 필요")')
                        행 += 1

            산식 = (cd.get("data") or {}).get("산식") or ""
            if 산식:
                행 += 1
                ws.cell(행, 1, "산식").font = bold
                # 산식이 문장 목록이면 줄바꿈으로(JSON 대괄호·따옴표가 보이지 않게)
                ac = ws.cell(행, 2, "\n".join(산식) if isinstance(산식, list) and all(isinstance(x, str) for x in 산식)
                             else _cell_value(산식))
                ac.alignment = Alignment(wrap_text=True)

            # 세부: 중첩 판정·항목별·연도별 산출 등 위 표에 안 나온 값
            _write_detail_blocks(ws, ws.max_row + 2, res, calc_dict,
                                 bold=bold, header_fill=header_fill, money_fmt=money_fmt)

            ws.column_dimensions["A"].width = 32
            ws.column_dimensions["B"].width = 20
            ws.column_dimensions["C"].width = 16
            ws.freeze_panes = "A2"

        # ── 목록 뒷부분: 확인 메모 → call ↔ 시트 대응표 → 고지문 ──
        행 = _목록_행
        for sh, rev in _개정일_생략:
            ws_list.cell(행, 1, sh)
            ws_list.cell(행, 2, f"서식 머리 개정일 표기 생략 — {rev}은 이 과세기간 신고기한 뒤 개정(서식 모양은 현행)")
            행 += 1
        for sh, notes in _시트별_메모.items():
            for n in notes:
                ws_list.cell(행, 1, sh)
                ws_list.cell(행, 2, n).font = Font(color="C00000")
                행 += 1
        if any(len(v) > 1 and v[0]["per_return"] for v in _tpl_groups.values()):
            ws_list.cell(행, 1, "같은 서식 여러 call")
            ws_list.cell(행, 2, "신고서 한 부에 한 장인 서식은 마지막 call이 본 시트(이름 그대로), "
                                       "앞선 call은 '(호출 N)' 시트로 따로 둠")
            행 += 1
        # 다른 도구 시트의 칸·표로 들어간 call(별지3 112·115, 부가 별지22 2.·5.절)
        _들어간_곳: dict[int, list[str]] = {}
        if "corporate_tax" in _other_calls and "별지3" in sheet_name_map:
            _들어간_곳.setdefault(_other_calls["corporate_tax"][0], []).append(sheet_name_map["별지3"] + " 112·115")
        if "minimum_tax_adjustment" in _other_calls and "별지3" in sheet_name_map:
            _들어간_곳.setdefault(_other_calls["minimum_tax_adjustment"][0], []).append(sheet_name_map["별지3"] + " 110·111")
        if "부가22" in sheet_name_map:
            if source_data.get("22_불공제") and _vid is not None:
                _들어간_곳.setdefault(_vid, []).append(sheet_name_map["부가22"] + " 2.절")
            if source_data.get("22_재계산"):
                for _i in _재계산_calls:
                    _들어간_곳.setdefault(_i, []).append(sheet_name_map["부가22"] + " 5.절")
        for _k, _idx in _합친_call.items():   # one_sheet 틀: 앞선 call도 그 한 장의 행으로 들어감
            for _i in _idx[:-1]:
                if _k in sheet_name_map:
                    _들어간_곳.setdefault(_i, []).append(sheet_name_map[_k])
        _서식_곳 = {_ci: [t["sheet"] for t in 템플릿_목록 if t["call_idx"] == _ci and t["tool"] != "*"] + _들어간_곳.get(_ci, [])
                  for _ci in range(len(결과들))}
        # 서식 틀이 없는 도구(부가 공급시기, 일반 납부지연가산세, 제척기간 등) — 서식 시트를 만들지 않은 이유를 적는다
        if not 템플릿_목록:
            ws_list.cell(행, 1, "서식 시트")
            ws_list.cell(행, 2, "이번 call로 만든 서식 시트 없음 — 아래 '서식 틀 없음' 줄과 '계산 N' 시트 참고")
            행 += 1
        _틀없는_도구: dict[str, list[str]] = {}
        for _ci, cd in enumerate(결과들):
            if not cd["error"] and cd.get("result") and not _서식_곳[_ci]:
                _틀없는_도구.setdefault(cd.get("tool", ""), []).append(_calc_sheets.get(_ci, f"계산 {_ci + 1}"))
        for _tool, _sheets in _틀없는_도구.items():
            ws_list.cell(행, 1, f"서식 틀 없음 — {_tool}")
            ws_list.cell(행, 2, "이 도구 결과를 담는 서식 틀이 없음(법정서식이 없거나 아직 만들지 않음) — 값은 "
                         + ", ".join(f"'{x}'" for x in _sheets) + " 시트")
            행 += 1
        행 += 1
        # call ↔ 시트 대응표('계산 N' = N번째 call)
        for cc, h in enumerate(["call", "label", "계산 시트", "서식 시트"], 1):
            c = ws_list.cell(행, cc, h); c.font = bold; c.fill = header_fill
        행 += 1
        for _ci, cd in enumerate(결과들):
            ws_list.cell(행, 1, _ci + 1)
            ws_list.cell(행, 2, cd.get("label", ""))
            ws_list.cell(행, 3, _calc_sheets.get(_ci, ""))
            _곳 = _서식_곳[_ci]
            ws_list.cell(행, 4, ", ".join(_곳) or ("오류" if cd["error"] else "서식 틀 없음 — 계산 시트 참고"))
            행 += 1
        행 += 1
        ws_list.cell(행, 1,
                    "이 파일은 계산 도구의 결과를 정리한 참고 자료이며 세무 자문이 아닙니다. 판단과 신고는 세무 전문가와 확인하세요.")
        ws_list.cell(행, 1).font = Font(italic=True, color="C00000")
        ws_list.merge_cells(start_row=행, start_column=1, end_row=행, end_column=8)

        # ── 4. 시트 순서 조정 (forms 모드: 입력·가정 시트를 틀+계산N 시트들 뒤로) ──
        if layout == "forms":
            sheets = wb._sheets
            inp_idx = None
            for i, s in enumerate(sheets):
                if s.title == "입력·가정":
                    inp_idx = i
                    break
            if inp_idx is not None:
                # 목록(1) + 틀 시트들 + 계산 N 시트들
                틀시트들_끝 = 1 + len(템플릿_목록) + calc_idx
                if inp_idx != 틀시트들_끝:
                    sheet = sheets.pop(inp_idx)
                    sheets.insert(틀시트들_끝, sheet)

    # ── 5. 입력·가정 시트 (steps 모드에서만 생성, forms 모드는 앞에서 생성) ──
    if layout != "forms":
        ws_inp = wb.create_sheet("입력·가정")
        시트이름들.append("입력·가정")
    행 = 1
    ws_inp.cell(행, 1, "call").font = bold
    ws_inp.cell(행, 2, "경로").font = bold
    ws_inp.cell(행, 3, "값").font = bold
    for cc in range(1, 4):
        ws_inp.cell(행, cc).fill = header_fill
    행 += 1
    for i, cd in enumerate(결과들):
        if cd["error"]:
            continue
        label = cd["label"]
        args = (calls[i] or {}).get("args", {})
        for 경로, 값 in _flatten_args(args):
            ws_inp.cell(행, 1, label)
            ws_inp.cell(행, 2, 경로)
            vc = ws_inp.cell(행, 3)
            if isinstance(값, (int, float)):
                _set_money(vc, 값)
            else:
                vc.value = _cell_value(값)
            행 += 1
    ws_inp.column_dimensions["A"].width = 20
    ws_inp.column_dimensions["B"].width = 36
    ws_inp.column_dimensions["C"].width = 18
    ws_inp.freeze_panes = "A2"

    # ── 6. 판단·근거 시트 (두 모드 공통) ──
    ws_jud = wb.create_sheet("판단·근거")
    시트이름들.append("판단·근거")
    행 = 1
    for cc, h in enumerate(["call", "항목", "결론", "금액", "근거", "이유"], 1):
        c = ws_jud.cell(행, cc, h); c.font = bold; c.fill = header_fill
    행 += 1
    for _ci, cd in enumerate(결과들):
        if cd["error"]:
            continue
        label = cd["label"]
        # 판단이 없는 도구(원천징수·가산세·제척기간 등)도 call마다 한 줄 이상 — 판정·쟁점, 없으면 '판단 항목 없음'
        for j in _judgement_rows(cd.get("data") or {}, f"계산 {_ci + 1}"):
            ws_jud.cell(행, 1, label)
            ws_jud.cell(행, 2, j.get("항목", ""))
            con = ws_jud.cell(행, 3, _cell_value(j.get("결론", "")))
            amt = j.get("금액")      # 금액이 없는 문장 판단은 빈칸(0으로 채우지 않음)
            if isinstance(amt, bool):
                ws_jud.cell(행, 4, "예" if amt else "아니오")
            elif isinstance(amt, (int, float)):
                _set_money(ws_jud.cell(행, 4), amt)
            elif amt not in (None, ""):
                ws_jud.cell(행, 4, _cell_value(amt))
            근거_val = j.get("근거", "")
            근거_cell = ws_jud.cell(행, 5, _cell_value(근거_val))
            if isinstance(근거_val, list) and _is_basis_list(근거_val):
                근거_cell.alignment = Alignment(wrap_text=True)
            이유_val = j.get("이유", "")
            이유_cell = ws_jud.cell(행, 6, _cell_value(이유_val))
            if isinstance(이유_val, list) and (_is_basis_list(이유_val) or _is_wrapped_basis_list(이유_val)):
                이유_cell.alignment = Alignment(wrap_text=True)
            행 += 1
    ws_jud.column_dimensions["A"].width = 20
    ws_jud.column_dimensions["B"].width = 16
    ws_jud.column_dimensions["C"].width = 40
    ws_jud.column_dimensions["D"].width = 16
    ws_jud.column_dimensions["E"].width = 30
    ws_jud.column_dimensions["F"].width = 36
    ws_jud.freeze_panes = "A2"
    # ── 결과 문구('= 순손익액' 등)가 수식으로 저장되지 않게 — 도구 결과·call 입력에서 온 '='로 시작하는 문자열은 문자열 칸 ──
    _labels_as_text(wb, [calls, [cd.get("data") or cd.get("result") for cd in 결과들]])
    # ── 저장 ──
    base = filename if filename else title
    fpath = _unique_path(output_dir, base)
    wb.save(fpath)
    return {
        "결과": {
            "파일": os.path.abspath(fpath),
            "시트": 시트이름들,
            "call_수": len(calls),
            "오류_call": 오류_call,
        },
        "근거": "계산 도구 결과 정리(세무 자문 아님)",
    }
