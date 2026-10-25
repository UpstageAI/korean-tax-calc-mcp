"""엑셀 법정서식 틀 렌더러 — template JSON → openpyxl 시트.

SPEC_form_templates.md 3절: 틀 JSON 형식·렌더 규칙.
"""
from __future__ import annotations

import re as _re
from typing import Any

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

# ── 공통 서식 ──
MONEY_FMT = "#,##0"
AL_MAP = {"l": "left", "c": "center", "r": "right"}


# ── 셀 주소 / 범위 파싱 ──
def _parse_cell(addr: str) -> tuple[int, int]:
    """'D13' → (13, 4)."""
    m = _re.match(r"([A-Z]+)(\d+)", addr)
    if not m:
        raise ValueError(f"잘못된 셀 주소: {addr}")
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return (int(m.group(2)), col)


def _col_letter(ci: int) -> str:
    """1-based 열 번호 → 'A' 형태."""
    s = ""
    while ci > 0:
        ci, rem = divmod(ci - 1, 26)
        s = chr(65 + rem) + s
    return s


def _parse_range(rng_s: str) -> tuple[int, int, int, int]:
    """'A2:D3' → (1, 4, 2, 3). 'Sheet!A2:D3'이면 rng 부분만 사용."""
    rng_s = rng_s.split("!")[-1]
    if ":" not in rng_s:
        r, c = _parse_cell(rng_s)
        return (c, c, r, r)
    c1_s, c2_s = rng_s.split(":")
    r1, c1 = _parse_cell(c1_s)
    r2, c2 = _parse_cell(c2_s)
    return (min(c1, c2), max(c1, c2), min(r1, r2), max(r1, r2))


# ── 도구 값 조회 (순수 함수) ──
def tool_value(res: dict | None, path: str) -> Any:
    """'결과.키'→res['결과'][키], '계산.키'→res['계산'][키] (점으로 더 깊이 가능). 없으면 None.

    SPEC_form_resolver 3절: 렌더러에서 도구 결과 값을 조회할 때 쓰는 순수 함수.
    """
    if not path or not isinstance(res, dict):
        return None
    parts = path.split(".")
    prefix = parts[0]
    if prefix in ("결과", "계산") and prefix in res:
        parts = parts[1:]
        cur = res.get(prefix)
    else:
        cur = res
    for p in parts:
        if isinstance(cur, dict):
            cur = cur.get(p)
        else:
            return None
        if cur is None:
            return None
    return cur


# cross 참조 대상이 없을 때 반환되는 Sentinel (렌더러에서 fallback 값으로 치환)
CROSS_FALLBACK = object()


def _fmt_val(v: Any) -> str:
    """도구 값을 엑셀 수식용 숫자 문자열로 변환."""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v):
            return str(int(v))
        return str(v)
    return str(v)


def _cross_fallback_value(ref_key: str, ref_id: str, tkey: str,
                          source_data: dict[str, list[dict]] | None,
                          all_slots: dict[str, dict[str, tuple[str, str]]] | None,
                          sheet_name_map: dict[str, str] | None) -> Any:
    """교차 참조 대상이 이번 내보내기에 없을 때 fallback 값 조회.

    source_data{조정_가산|조정_차감}에서 ref_id가 금액 키면 해당 값, 아니면 None.
    """
    # source_data의 adjustment 소스에서 ref_id가 금액이면 해당 값 반환
    for src_name in ("조정_가산", "조정_차감"):
        rows = (source_data or {}).get(src_name, [])
        for row in rows:
            # ref_id가 source 행의 키 중 하나이고 값이 숫자면 반환
            if ref_id in row and isinstance(row[ref_id], (int, float)):
                return row[ref_id]
    # 별지3 102·103 등은 별지15가 항상 같이 렌더되므로 해당 없음
    return None


def resolve_formula(f: str, *, res: dict | None, call_idx: int,
                    local: dict[str, str], cross: dict[tuple[str, str], tuple[str, str]],
                    sheet_name_map: dict[str, str] | None = None,
                    all_slots: dict[str, dict[str, tuple[str, str]]] | None = None) -> str:
    """서식 틀 수식 토큰의 토큰을 해석한 엑셀 수식 문자열을 반환한다.

    SPEC_form_resolver 3절:
    - [입력.이름] → 호출{call_idx+1}_이름 (계산식_입력에 있고 무한대 아닐 때만).
      [입력.이름|d]는 없으면 d. 기본값 없이 없으면 KeyError.
    - [계산.경로]·[결과.경로] → tool_value 값을 숫자 문자열로(정수는 정수, bool은 TRUE/FALSE).
      |d 기본값 규칙 같음. 없으면 KeyError.
    - {id} → local[id], {틀key!id} → '시트이름'!셀 (cross[(틀key,id)] = (시트이름, 셀)).
      없으면 KeyError.
    - 그 밖 문자는 그대로.
    """
    if not isinstance(res, dict):
        res = {}

    calc_inputs = res.get("계산식_입력", [])
    # 입력 이름 → 값 맵 (무한대 아닌 것만)
    input_map: dict[str, Any] = {}
    for inp in calc_inputs:
        name = inp.get("이름", "")
        val = inp.get("값")
        if name and not (isinstance(val, float) and val == float("inf")):
            input_map[name] = val

    calc_dict = res.get("계산", {})
    result_dict = res.get("결과", {})

    def _fmt_val(v: Any) -> str:
        """도구 값을 엑셀 수식용 숫자 문자열로 변환."""
        if isinstance(v, bool):
            return "TRUE" if v else "FALSE"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            if v == int(v):
                return str(int(v))
            return str(v)
        return str(v)

    def _replace_input(m: _re.Match) -> str:
        full = m.group(1)
        if "|" in full:
            name, default = full.split("|", 1)
        else:
            name, default = full, None
        if name in input_map:
            return f"호출{call_idx + 1}_{name}"
        if default is not None:
            return default
        raise KeyError(f"입력 이름 '{name}' 없음 (기본값 없음)")

    def _replace_calc_result(m: _re.Match) -> str:
        prefix = m.group(1)       # "계산" 또는 "결과"
        path_part = m.group(2)    # "기본한도" 등 (기본값 포함 가능)
        if "|" in path_part:
            key, default = path_part.split("|", 1)
            path = f"{prefix}.{key}"
        else:
            path = f"{prefix}.{path_part}"
            default = None
        v = tool_value(res, path)
        if v is not None:
            return _fmt_val(v)
        if default is not None:
            return default
        raise KeyError(f"경로 '{path}' 값 없음 (기본값 없음)")

    out = f
    # {id}·{틀key!id}를 먼저 치환 ({i} 등 → resolve_formula의 local 치환)
    def _replace_slot(m: _re.Match) -> str:
        rest = m.group(1)
        if "!" in rest:
            ref_key, ref_id = rest.split("!", 1)
            key = (ref_key, ref_id)
            if key in cross:
                sheet_name, cell = cross[key]
                return f"'{sheet_name}'!{cell}"
            # cross에 없지만 all_slots에 있으면 직접 조회 (source_data 등 두 번째 패스 참조용)
            if all_slots is not None and ref_key in all_slots and ref_id in all_slots[ref_key]:
                sheet_name, cell = all_slots[ref_key][ref_id]
                return f"'{sheet_name}'!{cell}"
            # 대상 틀이 이번 내보기에 없음 → fallback sentinel
            if all_slots is not None and ref_key not in all_slots:
                return "CROSS_FALLBACK"
            # ref_key가 all_slots에 있지만 ref_id가 해당 틀에 정의되지 않음 → 오류
            if all_slots is not None and ref_id not in all_slots.get(ref_key, {}):
                raise KeyError(f"교차 참조 '{rest}': '{ref_key}' 틀에 슬롯 id '{ref_id}' 정의 없음")
            if sheet_name_map is not None and ref_key in sheet_name_map:
                raise KeyError(f"교차 참조 '{rest}': '{ref_key}' 틀에 슬롯 id '{ref_id}' 정의 없음")
            raise KeyError(f"교차 참조 '{rest}': 알 수 없는 틀 '{ref_key}'")
        if rest not in local:
            raise KeyError(f"알 수 없는 slot id '{rest}' (local에 없음)")
        return local[rest]

    out = _re.sub(r"\{([^}]+)\}", _replace_slot, out)
    # 그다음 [입력...]·[계산...]·[결과...] 치환
    out = _re.sub(r"\[입력\.([^]]+)\]", _replace_input, out)
    out = _re.sub(r"\[(계산|결과)\.([^]]+)\]", _replace_calc_result, out)
    return out


def fill_text(t: str | None, *, res: dict | None, meta: dict[str, Any]) -> str:
    """문구 placeholder 치환: {{키}}→meta[키], {{입력.이름}}→계산식_입력 값(정수면 정수).
    없으면 빈 문자열. {{계정과목}}은 meta에 없으면 '기업업무추진비'.

    SPEC_form_resolver 3절.
    """
    if not t:
        return t or ""

    if not isinstance(res, dict):
        res = {}

    calc_inputs = res.get("계산식_입력", [])
    input_map: dict[str, Any] = {}
    for inp in calc_inputs:
        name = inp.get("이름", "")
        val = inp.get("값")
        if name:
            input_map[name] = val

    def _fmt_input_val(v: Any) -> str:
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            if v == int(v):
                return str(int(v))
            return str(v)
        return str(v) if v is not None else ""

    out = t

    # {{법인명}}·{{사업자등록번호}}·{{기간_시작}}·{{기간_끝}} → meta 값
    for key in ("법인명", "사업자등록번호", "기간_시작", "기간_끝"):
        out = out.replace(f"{{{{{key}}}}}", str(meta.get(key, "")))

    # {{계정과목}} → meta 또는 기본 '기업업무추진비'
    out = out.replace("{{계정과목}}", str(meta.get("계정과목", "기업업무추진비")))

    # {{입력.이름}} → 계산식_입력 값
    def _replace_input_text(m: _re.Match) -> str:
        name = m.group(1)
        val = input_map.get(name)
        if val is None:
            return ""
        return _fmt_input_val(val)

    out = _re.sub(r"\{\{입력\.([^}]+)\}\}", _replace_input_text, out)

    # 그 외 {{키}} → meta[키] (빈 문자열)
    def _replace_meta(m: _re.Match) -> str:
        key = m.group(1)
        return str(meta.get(key, ""))

    out = _re.sub(r"\{\{(\w+)\}\}", _replace_meta, out)

    return out


# ── 메인 렌더러 ──
def render_form_sheet(ws, tpl: dict, res: dict | None, input_map: dict[str, Any],
                      sheet_name_map: dict[str, str],
                      slot_map_all: dict[str, str] | None = None,
                      slot_map_cross: dict[tuple[str, str], tuple[str, str]] | None = None,
                      tkey_override: str | None = None,
                      call_idx: int | None = None,
                      company: str = "",
                      period: str = "",
                      biz_no: str = "",
                      source_data: dict[str, list[dict]] | None = None,
                      all_slots: dict[str, dict[str, tuple[str, str]]] | None = None) -> None:
    """폼 템플릿 JSON을 엑셀 시트로 렌더링한다. (SPEC_form_templates 3절)

    렌더러의 slot 수식·table 열 수식·문구·검증 값은 모두 tool_value·resolve_formula·fill_text
    세 함수만 써서 처리한다. (SPEC_form_resolver)
    """
    tkey = tpl["key"] if tkey_override is None else tkey_override
    local_slot_map = {s["id"]: s["cell"] for s in tpl.get("slots", [])}

    ws.title = tpl["sheet"]

    # ── 기간 파싱 (fill_text용 meta 구성) ──
    d1, d2 = "", ""
    if period:
        parts = period.split(" ~ ")
        if len(parts) == 2:
            d1, d2 = parts[0].strip(), parts[1].strip()

    meta: dict[str, Any] = {
        "법인명": company,
        "사업자등록번호": biz_no,
        "기간_시작": d1,
        "기간_끝": d2,
        "계정과목": "기업업무추진비",
    }

    # ── 열 너비 ──
    for col, w in tpl.get("widths", {}).items():
        ws.column_dimensions[col].width = w

    # ── 행 높이: default_row_height → print_area 모든 행 → row_heights 덮어쓰기 ──
    if tpl.get("default_row_height"):
        pa = tpl.get("print_area", "")
        if pa:
            _, _, pa_rs, pa_re = _parse_range(pa)
            for ri in range(pa_rs, pa_re + 1):
                ws.row_dimensions[ri].height = tpl["default_row_height"]
    for row_s, h in tpl.get("row_heights", {}).items():
        ws.row_dimensions[int(row_s)].height = h

    # ── 셀 채우기 (문구) — fill_text 사용 ──
    for mc in tpl.get("cells", []):
        rng_s = mc["r"]
        txt = fill_text(mc.get("t"), res=res, meta=meta)
        al = AL_MAP.get(mc.get("al", "l"), mc.get("al", "l"))
        font = Font(name="맑은 고딕",
                    size=mc.get("size") if mc.get("size") else 10,
                    bold=mc.get("bold", False))
        if ":" in rng_s:
            c1, c2 = rng_s.split(":")
            ws.merge_cells(rng_s)
            ws[c1].value = txt
            ws[c1].alignment = Alignment(horizontal=al, vertical="center", wrap_text=True)
            ws[c1].font = font
        else:
            ws[rng_s].value = txt
            ws[rng_s].alignment = Alignment(horizontal=al, vertical="center", wrap_text=True)
            ws[rng_s].font = font

    # ── 괘선(box) — 모든 칸 얇은 선 ──
    thin = Side(style="thin")
    medium = Side(style="medium")
    for rng_s in tpl.get("box", []):
        cs, ce, rs, re_ = _parse_range(rng_s)
        for ci in range(cs, ce + 1):
            for ri in range(rs, re_ + 1):
                cell = ws.cell(ri, ci)
                cell.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # ── 바깥 테두리(outer) — 굵은 선 ──
    for rng_s in tpl.get("outer", []):
        cs, ce, rs, re_ = _parse_range(rng_s)
        for ci in range(cs, ce + 1):
            for ri in range(rs, re_ + 1):
                cell = ws.cell(ri, ci)
                left_b = medium if ci == cs else cell.border.left
                right_b = medium if ci == ce else cell.border.right
                top_b = medium if ri == rs else cell.border.top
                bottom_b = medium if ri == re_ else cell.border.bottom
                cell.border = Border(left=left_b, right=right_b, top=top_b, bottom=bottom_b)

    # ── 틀 fill(회색 칸) 적용 ──
    for rng_s, color in tpl.get("fill", {}).items():
        cs, ce, rs, re_ = _parse_range(rng_s)
        fill = color if isinstance(color, PatternFill) else PatternFill("solid", fgColor=color)
        for ci in range(cs, ce + 1):
            for ri in range(rs, re_ + 1):
                ws.cell(ri, ci).fill = fill

    # ── 슬롯(수식) 처리 — resolve_formula 사용 ──
    cross_map: dict[tuple[str, str], tuple[str, str]] = dict(slot_map_cross) if slot_map_cross else {}

    for s in tpl.get("slots", []):
        cell_addr = s["cell"]
        f = s.get("f", "")
        if not f:
            continue
        if call_idx is not None:
            f_rendered = resolve_formula(f, res=res, call_idx=call_idx,
                                         local=local_slot_map, cross=cross_map,
                                         sheet_name_map=sheet_name_map, all_slots=all_slots)
            # cross 참조 대상이 없을 때 fallback 값 치환
            if f_rendered == "CROSS_FALLBACK":
                ref_key, ref_id = f.strip("{}").split("!", 1)
                # source_data에서 해당 slot의 도구 값 또는 source 숫자 조회
                fallback_val = _cross_fallback_value(ref_key, ref_id, tkey, source_data, all_slots, sheet_name_map)
                f_rendered = _fmt_val(fallback_val)
        else:
            # call_idx 없으면 {id}만 치환 (local_slot_map 사용)
            def _local_only(m: _re.Match) -> str:
                rest = m.group(1)
                if rest in local_slot_map:
                    return local_slot_map[rest]
                raise KeyError(f"알 수 없는 slot id '{rest}' (call_idx 없음)")
            f_rendered = _re.sub(r"\{([^}]+)\}", _local_only, f)
        ws[cell_addr].value = f_rendered
        ws[cell_addr].font = Font(name="맑은 고딕", size=10)

    # ── 반복 행 tables 렌더링 ──
    for tbl in tpl.get("tables", []):
        tbl_id = tbl["id"]
        source_name = tbl["source"]
        first_row = tbl["first_row"]
        max_rows = tbl["max_rows"]
        cols = tbl["cols"]
        center_cols = set(tbl.get("center", []))
        source_rows = (source_data or {}).get(source_name, [])
        if len(source_rows) > max_rows:
            raise ValueError(f"table '{tbl_id}': source 행 {len(source_rows)}개 > max_rows {max_rows}")
        for ri, src_row in enumerate(source_rows):
            row_num = first_row + ri
            for col_letter, col_spec in cols.items():
                ci = ord(col_letter) - 64
                cell_addr = f"{_col_letter(ci)}{row_num}"
                if isinstance(col_spec, str) and col_spec.startswith("="):
                    # 수식 열: {r}→row_num(문자열), {i}→ri+1(문자열), resolve_formula
                    formula_tpl = col_spec
                    local_tbl = {"r": str(row_num), "i": str(ri + 1)}
                    f_resolved = resolve_formula(formula_tpl, res=res, call_idx=call_idx if call_idx is not None else 0,
                                                 local=local_tbl, cross=cross_map,
                                                 sheet_name_map=sheet_name_map, all_slots=all_slots)
                    if f_resolved == "CROSS_FALLBACK":
                        # cross fallback: {틀key!id} 부분을 source_data 수치로 치환
                        def _fallback_cross(m2: _re.Match) -> str:
                            rk, rid = m2.group(1).split("!", 1)
                            if all_slots is not None and rk not in all_slots:
                                sv = _cross_fallback_value(rk, rid, tkey, source_data, all_slots, sheet_name_map)
                                return str(sv) if sv is not None else "0"
                            raise KeyError(f"교차 참조 '{m2.group(1)}' 해석 불가")
                        f_resolved = _re.sub(r"\{([^}]+)\}", _fallback_cross, formula_tpl)
                        # {r}, {i} 치환
                        f_resolved = f_resolved.replace("{r}", str(row_num)).replace("{i}", str(ri + 1))
                    ws[cell_addr].value = f_resolved
                else:
                    # 값 열: source 행의 키 값
                    key = col_spec
                    val = src_row.get(key)
                    if isinstance(val, (int, float)):
                        ws[cell_addr].value = val
                    elif isinstance(val, str) and val.startswith("="):
                        # source 값이 수식 문자열: resolve_formula
                        local_tbl2 = {"r": str(row_num), "i": str(ri + 1)}
                        f_resolved = resolve_formula(val, res=res, call_idx=call_idx if call_idx is not None else 0,
                                                     local=local_tbl2, cross=cross_map,
                                                     sheet_name_map=sheet_name_map, all_slots=all_slots)
                        if f_resolved == "CROSS_FALLBACK":
                            def _fb2(m2: _re.Match) -> str:
                                rk, rid = m2.group(1).split("!", 1)
                                if all_slots is not None and rk not in all_slots:
                                    sv = _cross_fallback_value(rk, rid, tkey, source_data, all_slots, sheet_name_map)
                                    return str(sv) if sv is not None else "0"
                                raise KeyError(f"교차 참조 '{m2.group(1)}' 해석 불가")
                            f_resolved = _re.sub(r"\{([^}]+)\}", _fb2, val)
                            f_resolved = f_resolved.replace("{r}", str(row_num)).replace("{i}", str(ri + 1))
                        ws[cell_addr].value = f_resolved
                    else:
                        ws[cell_addr].value = val if val is not None else ""
                # center 정렬 적용
                if col_letter in center_cols or (isinstance(col_spec, str) and col_spec in center_cols):
                    ws[cell_addr].alignment = Alignment(horizontal="center", vertical="center")
                else:
                    ws[cell_addr].alignment = Alignment(horizontal="left", vertical="center")
                ws[cell_addr].font = Font(name="맑은 고딕", size=10)

    # ── 금액 열 서식 — slots 작성 후 적용, formats{셀:서식} 우선 ──
    formats = tpl.get("formats", {})
    for col_l in tpl.get("amount_cols", []):
        ci = ord(col_l) - 64
        pa = tpl.get("print_area", "")
        if pa:
            _, _, pa_rs, pa_re = _parse_range(pa)
            for ri in range(pa_rs, pa_re + 1):
                c = ws.cell(ri, ci)
                if c.value is not None:
                    cell_addr = f"{_col_letter(ci)}{ri}"
                    if cell_addr in formats:
                        c.number_format = formats[cell_addr]
                    else:
                        c.number_format = MONEY_FMT
                    c.alignment = Alignment(horizontal="right", vertical="center")

    # ── 검증 칸(check_col) — tool_value 사용 ──
    # slot별 check_col: slot에 check_col이 있으면 그 열, 없으면 틀의 check_col.
    # 각 check_col 위치마다 "도구 값"/"확인" 헤더와 검증 수식을 작성.
    tpl_check_col = tpl.get("check_col", "")
    check_rows = [s for s in tpl["slots"] if s.get("check")]
    if check_rows and (tpl_check_col or any(s.get("check_col") for s in check_rows)):
        # slot별 check_col 수집 (중복 제거, 정렬)
        check_col_positions: list[str] = []
        for s in check_rows:
            cc = s.get("check_col") or tpl_check_col
            if cc and cc not in check_col_positions:
                check_col_positions.append(cc)
        check_col_positions.sort(key=lambda c: ord(c) - 64)
        # 각 check_col 위치마다 헤더 작성
        for cc in check_col_positions:
            cci = ord(cc) - 64
            first_r = min(_parse_cell(s["cell"])[0] for s in check_rows
                         if (s.get("check_col") or tpl_check_col) == cc)
            ws.cell(first_r - 1, cci, "도구 값").font = Font(name="맑은 고딕", size=9, bold=True)
            ws.cell(first_r - 1, cci).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(first_r - 1, cci + 1, "확인").font = Font(name="맑은 고딕", size=9, bold=True)
            ws.cell(first_r - 1, cci + 1).alignment = Alignment(horizontal="center", vertical="center")
        # 각 슬롯마다 해당 check_col 위치에 도구 값·확인 수식 작성
        for s in check_rows:
            cell_addr = s["cell"]
            r = _parse_cell(cell_addr)[0]
            check_path = s["check"]
            cc = s.get("check_col") or tpl_check_col
            cci = ord(cc) - 64
            tool_val = tool_value(res, check_path)
            tv_cell = ws.cell(r, cci)
            tv_cell.font = Font(name="맑은 고딕", size=9, color="808080")
            tv_cell.alignment = Alignment(horizontal="right", vertical="center")
            if tool_val is None:
                tv_cell.value = None
            elif isinstance(tool_val, float) and tool_val == float("inf"):
                tv_cell.value = "상한 없음"
            else:
                tv_cell.value = tool_val
                tv_cell.number_format = MONEY_FMT
            amt_col_letter = _col_letter(_parse_cell(cell_addr)[1])
            ws.cell(r, cci + 1,
                    f'=IF(ROUND({amt_col_letter}{r},0)=ROUND(IF(ISNUMBER({cc}{r}),{cc}{r},0),0),"일치","확인 필요")')
            ws.cell(r, cci + 1).font = Font(name="맑은 고딕", size=9)
            ws.cell(r, cci + 1).alignment = Alignment(horizontal="center", vertical="center")

    # ── 인쇄 영역, 눈금선, 페이지 설정 ──
    if tpl.get("print_area"):
        ws.print_area = tpl["print_area"]
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 1
    ws.page_setup.paperSize = 9  # A4


def _load_form_templates() -> dict[str, list[dict]]:
    """form_templates JSON 디렉터리에서 도구별 템플릿 목록을 로드한다 (모듈 수준 캐시)."""
    import json as _json
    import os as _os
    tpl_dir = _os.path.join(_os.path.dirname(__file__), "data", "form_templates")
    result: dict[str, list[dict]] = {}
    if not _os.path.isdir(tpl_dir):
        return result
    for fname in sorted(_os.listdir(tpl_dir)):
        if not fname.endswith(".json"):
            continue
        path = _os.path.join(tpl_dir, fname)
        with open(path, encoding="utf-8") as f:
            tpl = _json.load(f)
        tool = tpl.get("tool", "")
        if tool:
            result.setdefault(tool, []).append(tpl)
    return result
