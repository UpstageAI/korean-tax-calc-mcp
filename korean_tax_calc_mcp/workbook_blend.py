"""export_workbook 통합 문서 — 요약(Summary)·입력·출처(Inputs)·시나리오 시트·쟁점 목록(Issues Log).

선택 입력(scenarios·sources·issues) 가운데 하나라도 있을 때만 쓴다. 없으면 이 모듈은 불리지 않고 기존 출력 그대로다.

- 입력·세율은 '입력·출처' 시트 한곳에 두고(값마다 출처 열), 시나리오 시트는 그 칸을 가리키는 수식으로 계산한다.
- 시나리오 시트는 call을 열로 나란히 놓고 오른쪽에 '근거·메모' 열을 둔다. 줄마다 수식이고, 블록 끝에서 도구 값과 대조한다.
- 요약 시트는 시나리오 시트의 핵심 칸을 링크한다.
- 쟁점 목록은 호출자가 준 글을 그대로 표로 싣는다(도구가 판단을 만들지 않음).
- 색 규칙: 파랑 = 입력, 초록 = 다른 시트 링크, 검정 = 수식, 노랑 = 핵심 결과·가정.

뒤 시트는 detail로 고른다 — compact(기본: '계산 상세' 한 장), forms(+ 신고 서식), full(서식·계산 N·판단·근거 전부).

도구별 수식 틀: nonresident_withholding·withholding_late_payment_penalty(납부고지 전·후)는 전용 틀, 결과에 `계산식`이 있는 도구는 그 단계를
수식으로, 그 밖의 도구는 결과 값을 그대로 옮긴다(값 줄은 회색 — 수식 아님).
"""
from __future__ import annotations

import json as _json
import re as _re
from datetime import date as _date, timedelta as _timedelta
from typing import Any

from openpyxl.utils import get_column_letter as _L

NAVY, BAND, BLUE, GREEN, GREY, YELLOW = "1F3864", "D9E1F2", "0000FF", "008000", "555555", "FFFF00"
NUM = '#,##0;(#,##0);"-"'
PCT = "0.0###%"
DATE = "yyyy-mm-dd"
_RISK_FILL = {"high": "F8CBAD", "높음": "F8CBAD", "상": "F8CBAD", "medium": "FFE699", "중간": "FFE699", "보통": "FFE699", "중": "FFE699",
              "low": "E2EFDA", "낮음": "E2EFDA", "하": "E2EFDA", "info": "DDEBF7", "참고": "DDEBF7", "정보": "DDEBF7",
              "none": "EDEDED", "없음": "EDEDED"}
_BAD_SHEET = _re.compile(r"[\[\]:*?/\\]")
_ISSUE_KEYS = {"no": ("no", "번호", "#", "No"), "issue": ("issue", "쟁점", "Issue", "항목"), "finding": ("finding", "발견", "Finding", "내용"),
               "risk": ("risk", "위험도", "Risk"), "action": ("action", "조치", "Action"), "amount": ("amount", "금액", "Amount")}

_TXT = {
    "summary": ("요약", "Summary"), "inputs": ("입력·출처", "Inputs"), "issues": ("쟁점 목록", "Issues Log"),
    "old_summary": ("호출 요약", "Call summary (호출 요약)"), "old_inputs": (None, "Call inputs (입력·가정)"),
    "summary_title": ("{t} — 요약", "{t} — summary"),
    "summary_sub": ("단위: 원. 계산은 뒤 시트의 수식, 입력과 출처는 '{i}' 시트.", "All amounts KRW. Workings on the following tabs; inputs and sources on the '{i}' tab."),
    "inputs_title": ("입력과 출처", "Inputs and sources"),
    "inputs_sub": ("파랑 = 입력값(출처는 C열). 노랑 = 바꿀 수 있는 가정. 계산 시트는 이 칸을 가리키는 수식이라 값을 바꾸면 따라 바뀜.",
                   "Blue = input (source in column C). Yellow = assumption you may change. The workings tabs are formulas on these cells."),
    "item": ("항목", "Item"), "value": ("값", "Value"), "source": ("출처", "Source"),
    "rates": ("법정 세율·이율", "Statutory rates"),
    "note_col": ("근거 · 메모", "Basis / note"),
    "check": ("도구 값 대조(수식 = 계산 도구 결과)", "Check: formulas agree with the calculation tool"),
    "ok": ("일치", "Match (일치)"), "ng": ("확인 필요", "Check (확인 필요)"),
    "key": ("색 규칙: 파랑 = 입력, 초록 = 다른 시트 링크, 검정 = 수식, 노랑 = 핵심 결과·가정.",
            "Colour key: blue = input; green = link to another tab; black = formula; yellow = key result or assumption."),
    "support": ("뒤 시트: 법정서식 틀, call별 도구 결과('계산 N'), 도구가 돌려준 판단·근거.",
                "Supporting tabs after these: statutory form sheets, tool results per call ('Calc N'), and the judgements returned by the tools."),
    "support_compact": ("뒤 시트: '{d}' 한 장 — call별 도구 결과와 판단·근거.", "Supporting tab: '{d}' — tool results and basis per call."),
    "support_forms": ("뒤 시트: '{d}'(call별 도구 결과와 판단·근거), 신고 서식 {n}장.", "Supporting tabs: '{d}' (tool results and basis per call) and {n} statutory form sheet(s)."),
    "forms_hint": ("신고 서식 {n}장은 detail='forms'로 받을 수 있음(call별 개별 시트까지는 detail='full').",
                   "{n} statutory form sheet(s) are available with detail='forms' (per-call sheets as well with detail='full')."),
    "detail": ("계산 상세", "Calc detail"),
    "rest": ("그 밖의 계산", "Other workings"), "rest_only": ("계산", "Workings"),
    "detail_title": ("계산 상세 — call별 도구 결과와 판단·근거", "Calculation detail — tool results and basis per call"),
    "detail_sub": ("계산 도구가 돌려준 값 그대로(앞 시트 수식의 대조 기준). call 순서대로 위에서 아래로.",
                   "Values as returned by the calculation tools (the reference for the formulas on the front tabs), one call after another. Free-text notes from the tools stay in Korean; the statutory basis is shown as English citations."),
    "detail_band": ("{n}. {label} — {tool}", "{n}. {label} — {tool}"),
    "detail_at": ("수식: '{s}' 시트", "Formulas: '{s}' tab"),
    "detail_links": ("서식 연결 칸 — 서식 시트의 수식이 가리키는 호출 입력", "Cells the form sheets refer to — call inputs"),
    "g_summary": (None, "Sheet '{s}' — key figures linked from the scenario sheets, one note per block, issue count and colour key"),
    "g_inputs": (None, "Sheet '{s}' — inputs and statutory rates in one place with a source column; the scenario sheets are formulas on these cells"),
    "g_scenario": (None, "Sheet '{s}' — scenario workings: calls side by side as live formulas, a basis / note column and a check line against the tool values"),
    "g_issues": (None, "Sheet '{s}' — issues log, shown as entered by the preparer"),
    "disclaimer": ("계산 도구 결과를 정리한 참고 자료이며 세무 자문이 아닙니다. 신고 전에 세무 전문가와 확인하세요.",
                   "Reference workings from calculation tool results, not tax advice — confirm with a tax professional before filing."),
    "issues_title": ("쟁점 목록", "Issues log"),
    "issues_sub": ("작성자가 넣은 내용을 그대로 실음 — 계산 도구는 쟁점을 판단하지 않음.", "Entered by the preparer and shown as provided — the calculation tool does not assess issues."),
    "issues_hdr": (("#", "쟁점", "발견", "위험도", "조치"), ("#", "Issue", "Finding", "Risk", "Action")),
    "issues_line": ("쟁점 {n}건 — '{s}' 시트", "{n} issue(s) — see the '{s}' tab"),
    "issues_amount": ("금액", "Amount"),
    "figs_hdr": (("핵심 숫자", "금액(원)", "계산 위치"), ("Key figure", "KRW", "Where it is worked out")),
    "figs_note": ("메모", "Note"),
    "actions_line": ("조치·기한 {n}건", "Actions and deadlines ({n})"),
    "actions_sub": ("작성자가 넣은 내용을 그대로 실음.", "Entered by the preparer and shown as provided."),
    "actions_hdr": (("조치", "기한", "담당", "근거"), ("Action", "By", "Owner", "Basis")),
    "extra_key": ("호출자가 넣은 표(계산 도구의 검증을 거치지 않음): {s}. 그 밖의 시트는 계산 도구 결과.",
                  "Preparer's own tables (not verified by the calculation tools): {s}. All other tabs come from calculation tool results."),
    "g_extra": (None, "Sheet '{s}' — table supplied by the preparer, not verified by the calculation tools"),
    "less": ("차감: 이미 납부한 금액 등", "Less: amount already paid or deducted"),
    "tool_value": ("도구 값(수식 아님)", "Tool value (not a formula)"),
    "tool_value_no_layout": ("도구 값(수식 틀 없음)", "Tool value (no formula layout)"),
    "no_formula": ("이 도구는 수식 틀이 없어 결과 값을 옮김", "No formula layout for this tool — values copied from the tool result"),
}


def _t(key: str, en: bool, **kw) -> Any:
    v = _TXT[key][1 if en else 0]
    return v.format(**kw) if kw and isinstance(v, str) else v


# ── 입력 정리·검증 ─────────────────────────────────────────────────────────
def _as_list(v: Any, name: str) -> tuple[list | None, str | None]:
    if v is None or v == "" or v == []:
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


def _call_ref(ref: Any, calls: list) -> int | None:
    """call 지정 — 1부터 세는 순번 또는 label. 없으면 None."""
    if isinstance(ref, bool):
        return None
    if isinstance(ref, int):
        return ref - 1 if 1 <= ref <= len(calls) else None
    if isinstance(ref, str):
        for i, c in enumerate(calls):
            if isinstance(c, dict) and c.get("label") == ref:
                return i
        if ref.strip().isdigit():
            return _call_ref(int(ref.strip()), calls)
    return None


def normalize(scenarios: Any, sources: Any, issues: Any, calls: list, actions: list | None = None,
              key_figures: list | None = None) -> tuple[dict | None, dict | None]:
    """선택 입력을 정리한다. 돌려주는 값: (cfg 또는 None, 오류 dict 또는 None). 넷 다 비면 (None, None) — 기존 출력.
    actions는 workbook_extra.normalize_actions가 정리한 목록(또는 None)."""
    err = lambda msg: (None, {"error": "입력 확인 필요 — " + msg, "안내": "scenarios=[{sheet, title, heading, columns:[{call, heading}], notes, summary_note}], "
                              "sources=[{call, arg, source, assumption, from_call, from_row, less}], issues=[{no, issue, finding, risk, action}]"})
    sc, e1 = _as_list(scenarios, "scenarios")
    so, e2 = _as_list(sources, "sources")
    iss, e3 = _as_list(issues, "issues")
    for e in (e1, e2, e3):
        if e:
            return err(e)
    if sc is None and so is None and iss is None and not actions and not key_figures:
        return None, None
    blocks: list[dict] = []
    used: set[int] = set()
    notes: list[str] = []          # 오류는 아니지만 알릴 것(결과의 warnings로)
    for n, b in enumerate(sc or [], 1):
        if not isinstance(b, dict):
            return err(f"scenarios[{n}]가 객체가 아님")
        cols_in = b.get("columns") or ([b["call"]] if b.get("call") is not None else [])
        if not isinstance(cols_in, list) or not cols_in:
            return err(f"scenarios[{n}].columns가 비어 있음 — [{{call, heading}}]")
        cols = []
        for c in cols_in:
            ref, heading = (c.get("call"), c.get("heading")) if isinstance(c, dict) else (c, None)
            rec = isinstance(c, dict) and bool(c.get("recommended"))
            idx = _call_ref(ref, calls)
            if idx is None:
                return err(f"scenarios[{n}].columns의 call '{ref}'를 calls에서 찾지 못함(label 또는 1부터 세는 순번)")
            if idx in used:
                return err(f"scenarios[{n}].columns의 call '{ref}'가 두 번 쓰임 — call 하나는 한 열에만")
            used.add(idx)
            cols.append({"idx": idx, "heading": str(heading) if heading else str(calls[idx].get("label") or f"call {idx + 1}"), "recommended": rec})
        if len({calls[c["idx"]].get("tool") for c in cols}) > 1:
            return err(f"scenarios[{n}].columns는 같은 도구의 call이어야 함 — 다른 도구는 블록을 나눔(sheet 이름이 같으면 한 시트에 차례로 놓임)")
        b_notes = b.get("notes") or {}
        if not isinstance(b_notes, dict):
            return err(f"scenarios[{n}].notes는 {{줄 이름: 메모}} 객체")
        blocks.append({"sheet": str(b.get("sheet") or b.get("title") or cols[0]["heading"]), "title": str(b.get("title") or ""),
                       "subtitle": str(b.get("subtitle") or ""), "heading": str(b.get("heading") or b.get("title") or b.get("sheet") or cols[0]["heading"]),
                       "columns": cols, "notes": {str(k): str(v) for k, v in b_notes.items()}, "summary_note": str(b.get("summary_note") or "")})
    src: dict[tuple[int, str], dict] = {}
    for n, s in enumerate(so or [], 1):
        if not isinstance(s, dict) or not s.get("arg"):
            return err(f"sources[{n}]는 {{call, arg, source}} 객체")
        idx = _call_ref(s.get("call"), calls)
        if idx is None:
            return err(f"sources[{n}]의 call '{s.get('call')}'를 calls에서 찾지 못함")
        item = {"source": str(s.get("source") or ""), "assumption": bool(s.get("assumption")), "label": s.get("label")}
        if s.get("less") is not None and s.get("from_call") is None:
            notes.append(f"sources[{n}]: less는 from_call·from_row와 함께 쓸 때만 적용됨 — from_call이 없어 쓰지 않음")
        if s.get("from_call") is not None:      # 이 입력이 다른 call의 결과 줄에서 온 값(예: 가산세의 미납세액 = 정당 세액 − 기납부)
            fidx = _call_ref(s.get("from_call"), calls)
            if fidx is None or fidx == idx or not s.get("from_row"):
                return err(f"sources[{n}]의 from_call '{s.get('from_call')}'·from_row를 확인 — 다른 call의 label(또는 순번)과 그 결과 줄 이름")
            less = s.get("less")
            if less is not None and (isinstance(less, bool) or not isinstance(less, (int, float)) or less < 0):
                return err(f"sources[{n}].less는 0 이상의 숫자(차감할 금액)")
            item.update({"from": fidx, "from_row": str(s["from_row"]), "less": less, "less_label": s.get("less_label"), "less_source": str(s.get("less_source") or "")})
        src[(idx, str(s["arg"]))] = item
    # from_call이 돌아서 자기에게 오면(순환) 엑셀에서 순환 참조가 됨
    edges: dict[int, set[int]] = {}
    for (idx, _), item in src.items():
        if "from" in item:
            edges.setdefault(idx, set()).add(item["from"])
    for start in edges:
        seen, todo = set(), list(edges[start])
        while todo:
            k = todo.pop()
            if k == start:
                return err(f"sources의 from_call이 순환함 — call {start + 1}의 입력이 돌아서 자기 결과를 가리킴(from_call을 한쪽만 남김)")
            if k not in seen:
                seen.add(k)
                todo += list(edges.get(k, ()))
    rows: list[dict] = []
    for n, x in enumerate(iss or [], 1):
        if not isinstance(x, dict):
            return err(f"issues[{n}]가 객체가 아님 — {{no, issue, finding, risk, action}}")
        row = {k: next((x[a] for a in al if x.get(a) not in (None, "")), "") for k, al in _ISSUE_KEYS.items()}
        row["no"] = row["no"] if row["no"] != "" else n
        if isinstance(row["amount"], dict) and (row["amount"].get("from_call") is None or not row["amount"].get("from_row")):
            return err(f"issues[{n}].amount는 숫자·글 또는 {{from_call: 호출 label 또는 순번, from_row: 결과 줄 이름}}")
        rows.append(row)
    return {"blocks": blocks, "sources": src, "issues": rows, "used": used, "warnings": notes, "actions": list(actions or []),
            "key_figures": list(key_figures or [])}, None


# ── 도구별 수식 틀 ─────────────────────────────────────────────────────────
def _inp(id_: str, ko: str, en: str, value: Any, *, fmt: str = NUM, kind: str = "input", arg: str | None = None,
         src_ko: str = "", src_en: str = "", summary: bool = False) -> dict:
    return {"id": id_, "ko": ko, "en": en, "value": value, "fmt": fmt, "kind": kind, "arg": arg, "src_ko": src_ko, "src_en": src_en,
            "summary": summary, "key": False}


def _row(id_: str, ko: str, en: str, f: str | None = None, *, value: Any = None, fmt: str = NUM, check: Any = None, key: bool = False,
         summary: bool = False, note_ko: str = "", note_en: str = "", alias: tuple = ()) -> dict:
    return {"id": id_, "ko": ko, "en": en, "f": f, "value": value, "fmt": fmt, "check": check, "key": key, "summary": summary,
            "note_ko": note_ko, "note_en": note_en, "alias": alias}


def _tool_args(tool: str, args: dict) -> dict:
    """call의 args를 도구가 받는 것과 같은 값으로(숫자·불리언 문자열 → 숫자·불리언). 도구의 입력 모델로 변환하고, 안 되면 그대로."""
    if not isinstance(args, dict) or not args:
        return args if isinstance(args, dict) else {}
    try:
        from .server import mcp
        model = mcp._tool_manager._tools[tool].fn_metadata.arg_model
        m = model.model_validate(args)
        return {k: getattr(m, k, v) for k, v in args.items()}
    except Exception:
        return args


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_STEP_FUNCS = frozenset({"MIN", "MAX", "IF", "ROUND", "ROUNDDOWN", "ROUNDUP", "INT", "ABS", "SUM", "AND", "OR", "NOT", "TRUNC", "TRUE", "FALSE"})
_IDENT = _re.compile(r"[가-힣A-Za-z_][가-힣A-Za-z0-9_.]*")


def _step_formula(expr: Any, names: set[str]) -> str | None:
    """`계산식`의 식이 엑셀 수식으로 쓸 수 있으면 '{이름}' 자리표시가 든 수식, 아니면 None(그 줄은 도구 값을 옮김).
    수식이 아닌 것: 빈 식·"None", 이름을 하나도 가리키지 않는 식(숫자뿐), 이 블록에 없는 이름(예: '결과.…')이 든 식."""
    from .tools_export import _이름_치환
    expr = str(expr if expr is not None else "").strip()
    if not expr or expr == "None" or "{" in expr or "}" in expr:
        return None
    try:
        f = _이름_치환(expr, {k: "{" + k + "}" for k in names})
    except Exception:
        return None
    if not _re.search(r"\{[^{}]+\}", f):
        return None
    rest = _re.sub(r"\{[^{}]+\}", " 0 ", f)
    if '"' in rest or "'" in rest or "!" in rest or any(m.group(0).upper() not in _STEP_FUNCS for m in _IDENT.finditer(rest)):
        return None
    return "=" + f


_KIND_EN = {"이자": "interest", "배당": "dividends", "사용료": "royalties", "인적용역": "personal services", "기타": "other income"}


def _with_ko(en: str, ko: Any) -> str:
    """영문 설명 뒤에 국문 원문을 괄호로 붙인다(근거 조문이 아닌 글 — 근거는 _basis)."""
    ko = str(ko or "").strip()
    return f"{en} ({ko})" if ko else en


class _Basis(str):
    """영문 설명 + 도구가 돌려준 근거(국문). 글 자체는 '영문 (국문)'이고, 영문 통합 문서에 적을 때 _shown_basis가
    근거를 영문 인용 표기(citation_en)로 바꿔 '영문: Corporate Tax Act (법인세법) Art. 98(1)6' 꼴로 적는다."""
    en: str
    ko: str

    def __new__(cls, en: str, ko: Any):
        ko = str(ko or "").strip()
        self = super().__new__(cls, (f"{en} ({ko})" if en else ko) if ko else en)
        self.en, self.ko = en, ko
        return self


def _basis(en: str, ko: Any) -> str:
    """영문 설명과 도구가 돌려준 근거 문자열(영문 모드에서 근거를 영문 인용으로)."""
    return _Basis(en, ko)


def _shown_basis(text: Any, cite) -> Any:
    """_Basis면 근거를 cite(영문 인용 변환)로 바꿔 '영문 설명: 영문 인용'. cite가 없거나 다른 글이면 그대로."""
    if cite is None or not isinstance(text, _Basis) or not text.ko:
        return text
    body = cite(text.ko)
    return f"{text.en}: {body}" if text.en else body


def _spec_nonresident(args: dict, data: dict) -> dict:
    res = data.get("결과") or {}
    kind = str(args.get("income_kind", ""))
    corp = args.get("recipient_type") == "법인"
    treaty = args.get("treaty_rate")
    covered = str(res.get("조약_대상조세_지방소득세", "")).startswith("포함")
    local_bears = bool(args.get("payer_bears_local_tax"))
    net = bool(args.get("net_of_tax")) or local_bears
    basis = str(data.get("근거") or res.get("근거") or "")
    law = basis.split(" · ")[0]
    local_basis = str(res.get("지방소득세_근거") or "")
    gross = res.get("역산") if isinstance(res.get("역산"), dict) else {}
    tax_ko, tax_en = ("법인세", "Corporate tax") if corp else ("소득세", "Income tax")
    inputs = [
        _inp("amount", "지급액(순액 약정이면 약정 순액)", "Payment amount (agreed net amount under a net-of-tax clause)", args.get("amount", 0), arg="amount"),
        _inp("domestic_rate", f"국내 원천징수세율 — {kind}", f"Domestic withholding rate — {_KIND_EN.get(kind, kind)}", res.get("국내세율"),
             fmt=PCT, kind="rate", src_ko=law, src_en=_basis("Statutory rate", law)),
    ]
    if treaty is not None:
        inputs.append(_inp("treaty_rate", "조세조약 제한세율", "Treaty limited rate", treaty, fmt=PCT, arg="treaty_rate",
                           src_ko="입력값 — 조약 조문은 korean-tax-mcp treaty_withholding_rates·tax_treaty로 확인",
                           src_en="As entered — confirm the treaty article with korean-tax-mcp treaty_withholding_rates / tax_treaty"))
    inputs.append(_inp("local_ratio", "지방소득세 비율(원천징수세액 대비)", "Local income tax as % of tax withheld", 0.1, fmt=PCT, kind="rate",
                       src_ko=local_basis, src_en=_basis("Special collection of local income tax", local_basis)))
    if covered:
        inputs.append(_inp("local_factor", "조약 대상조세에 지방소득세 포함 — 국세분 = 합계 상한 ÷ 1.1", "Treaty covers local income tax — national portion = cap ÷ 1.1",
                           1.1, fmt="0.0", kind="rate", src_ko=local_basis, src_en=_basis("Treaty cap applies to national + local tax", local_basis)))
    bearing = (("지급자 부담 — 순액 약정(법인세·소득세와 지방소득세까지 역산)", "Payer bears the tax — net-of-tax clause, gross-up including local income tax") if local_bears else
               ("지급자 부담 — 순액 약정(국세분만 역산)", "Payer bears the national tax — net-of-tax clause, gross-up on national tax only") if net else
               ("수취인 부담 — 지급액에서 원천징수", "Recipient bears the tax — withheld from the payment"))
    rows = [_row("bearing", "세금 부담", "Who bears the Korean tax", value=bearing, fmt="@")]
    if treaty is None:
        f_app = "={domestic_rate}"
    elif covered:
        f_app = "=MIN({treaty_rate},{domestic_rate}*{local_factor})"
    else:
        f_app = "=MIN({domestic_rate},{treaty_rate})"
    rows.append(_row("applicable", "적용세율", "Rate applied (lower of domestic and treaty rate)", f_app, fmt=PCT, check=res.get("적용세율"),
                     note_ko=basis, note_en=_basis("Basis returned by the tool", basis), alias=("적용세율",)))
    nat = "applicable"
    if covered:
        nat = "national"
        rows.append(_row("national", "국세분 세율(합계 상한 ÷ 1.1)", "National tax portion of the rate (cap ÷ 1.1)", "={applicable}/{local_factor}", fmt=PCT))
    gross_basis = str(gross.get("근거") or "법인세법 기본통칙 98-0…2")
    if net:
        rows.append(_row("gross_rate", "역산에 쓴 세율", "Gross-up rate",
                         "={" + nat + "}*(1+{local_ratio})" if local_bears else "={" + nat + "}", fmt=PCT, check=gross.get("역산에_쓴_세율"),
                         note_ko=f"{gross.get('세율_구성', '')} — {gross.get('확신도', '')}".strip(" —"),
                         note_en=_with_ko("National tax rate, plus the local income tax portion when the payer bears it", gross.get("확신도", "")),
                         alias=("역산에_쓴_세율",)))
        rows.append(_row("base", "과세표준", "Withholding tax base", "=ROUNDDOWN(ROUND({amount}/(1-{gross_rate}),4),0)", check=res.get("과세표준"), summary=True,
                         note_ko=f"순액 약정이면 약정 순액 ÷ (1 − 역산 세율), 아니면 지급액 — {gross_basis}",
                         note_en=_basis("Agreed net amount ÷ (1 − gross-up rate) under a net-of-tax clause; otherwise the payment amount", gross_basis),
                         alias=("과세표준",)))
        f_tax = "=ROUNDDOWN(ROUND({amount}/(1-{gross_rate})*{" + nat + "},4),-1)"
    else:
        rows.append(_row("base", "과세표준", "Withholding tax base", "={amount}", summary=True,
                         note_ko=f"순액 약정이면 약정 순액 ÷ (1 − 역산 세율), 아니면 지급액 — {gross_basis}",
                         note_en=_basis("Agreed net amount ÷ (1 − gross-up rate) under a net-of-tax clause; otherwise the payment amount", gross_basis),
                         alias=("과세표준",)))
        f_tax = "=ROUNDDOWN(ROUND({amount}*{" + nat + "},4),-1)"
    rows += [
        _row("tax", f"원천징수세액({tax_ko})", f"{tax_en} to withhold", f_tax, check=res.get("원천징수세액"), key=True, summary=True,
             note_ko="과세표준 × 국세분 세율, 10원 미만 절사(도구 방식 — 역산은 절사 전 과세표준으로 계산)",
             note_en="Tax base × national rate, truncated to KRW 10 (tool convention; computed on the tax base before rounding)", alias=("원천징수세액",)),
        _row("local", "지방소득세(특별징수)", "Local income tax to withhold", "=ROUNDDOWN(ROUND({tax}*{local_ratio},4),-1)", check=res.get("지방소득세"),
             key=True, summary=True, note_ko=local_basis, note_en=_basis("Local income tax on the tax withheld", local_basis), alias=("지방소득세",)),
        _row("total", "합계", "Total Korean tax", "={tax}+{local}", check=res.get("합계"), key=True, summary=True, alias=("합계",)),
        _row("net_paid", "수취인 송금액(과세표준 − 합계)", "Net amount remitted (tax base − total tax)", "={base}-{total}", summary=True),
    ]
    return {"inputs": inputs, "rows": rows, "links": {"지급액": "base", "적용세율": "applicable"}}


def _spec_wh_penalty(args: dict, data: dict) -> dict | None:
    """원천징수 납부지연가산세 — 납부고지 전(자진납부) 경로. 납부고지가 있으면 None(_spec_wh_penalty_notice로)."""
    from .engine.calc_vat import late_payment_rate_segments
    res = data.get("결과") or {}
    if args.get("notice_due") or args.get("paid_on") or res.get("고지후분") or "일수" not in res:
        return None
    try:
        d0, d1 = _date.fromisoformat(str(args.get("due"))), _date.fromisoformat(str(args.get("until")))
    except ValueError:
        return None
    days = int(res.get("일수") or 0)
    judge = next((j for j in data.get("판단") or [] if isinstance(j, dict)), {})
    j_ko = " — ".join(str(x) for x in (_re.sub(r"^\d+일 — ", "", str(judge.get("결론") or "")), judge.get("근거")) if x)
    off = (d1 - d0).days - days          # 0 = 납부일까지, 1 = 납부일 전날까지(2026.7.1. 개정)
    if off not in (0, 1):
        return None
    segs = late_payment_rate_segments((d0 + _timedelta(days=1)).isoformat(), days) or [(0, 0.00022)]
    inputs = [
        _inp("unpaid", "미납·과소납부 세액", "Tax not paid or underpaid", args.get("unpaid_tax", 0), arg="unpaid_tax", summary=True),
        _inp("due", "법정납부기한", "Statutory due date", d0, fmt=DATE, kind="date", arg="due"),
        _inp("until", "납부일", "Payment date", d1, fmt=DATE, kind="date", arg="until"),
        _inp("rate3", "원천징수 납부지연가산세 — 미납세액의 3%", "Withholding late-payment penalty — fixed portion", 0.03, fmt=PCT, kind="rate",
             src_ko="국세기본법 제47조의5제1항제1호", src_en=_basis("", "국세기본법 제47조의5제1항제1호")),
    ]
    rows: list[dict] = []
    end_ko, end_en = (("납부일의 전날까지", "the day before payment") if off else ("납부일까지", "the payment date"))
    if len(segs) == 1:
        inputs.append(_inp("daily", "원천징수 납부지연가산세 — 1일 이율", "Withholding late-payment penalty — daily rate", segs[0][1], fmt=PCT, kind="rate",
                           src_ko="국세기본법 시행령 제27조의4", src_en=_basis("", "국세기본법 시행령 제27조의4")))
        days_id = "days_prev" if off else "days"      # 끝날 규정이 다르면 다른 줄(같은 블록에 종전·개정이 섞여도 줄 이름이 맞게)
        rows.append(_row(days_id, f"일수(법정납부기한 다음 날부터 {end_ko})", f"Days (day after the statutory due date to {end_en})",
                         "=MAX(0,{until}-{due}" + ("-1)" if off else ")"), fmt="0", check=days, summary=True, note_ko=j_ko,
                         note_en=_basis("Period counted under Art. 47-5(1)2", j_ko), alias=("일수",)))
        daily_expr = "{unpaid}*{" + days_id + "}*{daily}"
    else:
        terms = []
        for i, (n, r) in enumerate(segs, 1):
            inputs.append(_inp(f"daily{i}", f"원천징수 납부지연가산세 — 1일 이율(기간 {i})", f"Withholding late-payment penalty — daily rate (period {i})", r,
                               fmt=PCT, kind="rate", src_ko="국세기본법 시행령 제27조의4(이율 변경일 기준 기간 안분)",
                               src_en="Enforcement Decree of the Framework Act on National Taxes Art. 27-4 (period split at the rate change date)"))
            rows.append(_row(f"days{i}", f"일수 — 기간 {i}(이율 변경일 기준, 도구 값)", f"Days — period {i} (split at the rate change date, tool value)",
                             value=n, fmt="0", note_ko=j_ko, note_en=_basis("Period counted under Art. 47-5(1)2", j_ko)))
            terms.append(f"{{days{i}}}*{{daily{i}}}")
        daily_expr = "{unpaid}*(" + "+".join(terms) + ")"
    inputs.append(_inp("cap10", "납부고지 전 한도(1호 + 2호)", "Cap before a payment notice (fixed + daily portions)", 0.10, fmt=PCT, kind="rate",
                       src_ko="국세기본법 제47조의5제1항 각 호 외의 부분 괄호", src_en="Framework Act on National Taxes Art. 47-5(1), parenthetical"))
    rows += [
        _row("fixed", "1호 — 미납세액의 3%", "Fixed 3% portion", "=IF({until}>{due},ROUNDDOWN(ROUND({unpaid}*{rate3},4),0),0)", check=res.get("3%분"),
             note_ko="국세기본법 제47조의5제1항제1호", note_en="Art. 47-5(1)1", alias=("3%분",)),
        _row("daily_amt", "2호 — 일수분", "Daily portion", f"=ROUNDDOWN(ROUND({daily_expr},4),0)", check=res.get("일수분"),
             note_ko="미납세액 × 일수 × 1일 이율 — 국세기본법 제47조의5제1항제2호", note_en="Unpaid tax × days × daily rate — Art. 47-5(1)2", alias=("일수분",)),
        _row("cap", "한도(미납세액의 10%)", "Cap (10% of the unpaid tax)", "=ROUNDDOWN(ROUND({unpaid}*{cap10},4),0)", check=res.get("한도_10%"), alias=("한도_10%",)),
        _row("penalty", "가산세", "Penalty", "=IF({until}>{due},ROUNDDOWN(ROUND(MIN({unpaid}*{rate3}+" + daily_expr + ",{unpaid}*{cap10}),4),0),0)",
             check=res.get("가산세"), key=True, summary=True, note_ko="min(1호 + 2호, 10% 한도), 원 미만 절사",
             note_en="Lower of (fixed + daily portions) and the 10% cap, truncated to KRW 1", alias=("가산세",)),
    ]
    return {"inputs": inputs, "rows": rows, "links": {}}


def _spec_wh_penalty_notice(args: dict, data: dict) -> dict | None:
    """원천징수 납부지연가산세 — 납부고지가 있는 경로: 고지 전(1호·2호, 10% 한도) + 고지 후(종전 2호 일수분 또는 개정 3호·4호) + 전체 50% 한도.

    숫자·근거는 도구(engine.calc_income.withholding_late_penalty_full, server.withholding_late_payment_penalty)가 쓰는 것 그대로.
    이 틀에 맞지 않는 경우(2019년 이전 성립분, 제5항 소액 기준 경과조치로 기간을 나눈 경우, 제4항 5년 한도에 걸린 경우)는 None(일반 틀)."""
    from .engine.calc_vat import late_payment_rate_segments
    res = data.get("결과") or {}
    rule = res.get("적용_규정") if isinstance(res.get("적용_규정"), dict) else {}
    judges = {str(j.get("항목")): j for j in data.get("판단") or [] if isinstance(j, dict)}
    if "일수" not in res or not args.get("notice_due") or not args.get("paid_on") or rule.get("고지 전") not in ("종전", "개정"):
        return None
    if "제5항 소액 기준 경과조치" in judges:
        return None
    try:
        d0, d1 = _date.fromisoformat(str(args.get("due"))), _date.fromisoformat(str(args.get("until")))
        nd, pd = _date.fromisoformat(str(args.get("notice_due"))), _date.fromisoformat(str(args.get("paid_on")))
    except ValueError:
        return None
    days = int(res.get("일수") or 0)
    if days != max(0, (d1 - d0).days - 1):
        return None
    post_rule = rule.get("고지 후")
    excluded = "⑤ 소액 체납" in judges
    jt = lambda k: " — ".join(str(x) for x in ((judges.get(k) or {}).get("결론"), (judges.get(k) or {}).get("근거")) if x)
    start = (d0 + _timedelta(days=1)).isoformat()
    segs = late_payment_rate_segments(start, days) or late_payment_rate_segments(start, 1)
    decree = "국세기본법 시행령 제27조의4"
    decree_en = _basis("", decree)
    inputs = [
        _inp("unpaid", "미납·과소납부 세액", "Tax not paid or underpaid", args.get("unpaid_tax", 0), arg="unpaid_tax", summary=True),
        _inp("due", "법정납부기한", "Statutory due date", d0, fmt=DATE, kind="date", arg="due"),
        _inp("notice_date", "납부고지일", "Date of the payment notice", d1, fmt=DATE, kind="date", arg="until"),
        _inp("notice_due", "지정납부기한(납부고지서에 따른 납부기한)", "Due date stated in the payment notice", nd, fmt=DATE, kind="date", arg="notice_due"),
        _inp("paid_on", "납부고지 후 실제 납부일", "Date actually paid after the notice", pd, fmt=DATE, kind="date", arg="paid_on"),
        _inp("rate3", "원천징수 납부지연가산세 — 미납세액의 3%", "Withholding late-payment penalty — fixed portion", 0.03, fmt=PCT, kind="rate",
             src_ko="국세기본법 제47조의5제1항제1호", src_en=_basis("", "국세기본법 제47조의5제1항제1호")),
    ]
    rows: list[dict] = []
    if len(segs) == 1:
        inputs.append(_inp("daily", "원천징수 납부지연가산세 — 1일 이율", "Withholding late-payment penalty — daily rate", segs[0][1], fmt=PCT, kind="rate",
                           src_ko=decree, src_en=decree_en))
        rows.append(_row("days_notice", "일수(법정납부기한 다음 날부터 납부고지일의 전날까지)", "Days (day after the statutory due date to the day before the notice)",
                         "=MAX(0,{notice_date}-{due}-1)", fmt="0", check=days, summary=True, note_ko=jt("고지 전 일수"),
                         note_en=_basis("Period counted under Art. 47-5(1)2", jt("고지 전 일수")), alias=("일수",)))
        daily_expr = "{unpaid}*{days_notice}*{daily}"
    else:
        terms = []
        for i, (n, r) in enumerate(segs, 1):
            inputs.append(_inp(f"daily{i}", f"원천징수 납부지연가산세 — 1일 이율(기간 {i})", f"Withholding late-payment penalty — daily rate (period {i})", r,
                               fmt=PCT, kind="rate", src_ko=decree + "(이율 변경일 기준 기간 안분)", src_en="Enforcement Decree of the Framework Act on National Taxes (국세기본법 시행령) Art. 27-4 (period split at the rate change date)"))
            rows.append(_row(f"days{i}", f"일수 — 기간 {i}(이율 변경일 기준, 도구 값)", f"Days — period {i} (split at the rate change date, tool value)",
                             value=n, fmt="0", note_ko=jt("고지 전 일수"), note_en=_basis("Period counted under Art. 47-5(1)2", jt("고지 전 일수"))))
            terms.append(f"{{days{i}}}*{{daily{i}}}")
        daily_expr = "{unpaid}*(" + "+".join(terms) + ")"
    inputs.append(_inp("cap10", "납부고지 전 한도(1호 + 2호)", "Cap before a payment notice (fixed + daily portions)", 0.10, fmt=PCT, kind="rate",
                       src_ko="국세기본법 제47조의5제1항 각 호 외의 부분 괄호", src_en="Framework Act on National Taxes Art. 47-5(1), parenthetical"))
    pre_expr = "MIN({unpaid}*{rate3}+" + daily_expr + ",{unpaid}*{cap10})"
    rows += [
        _row("fixed", "1호 — 미납세액의 3%", "Fixed 3% portion", "=ROUNDDOWN(ROUND({unpaid}*{rate3},4),0)", check=res.get("3%분"),
             note_ko="국세기본법 제47조의5제1항제1호", note_en="Art. 47-5(1)1", alias=("3%분",)),
        _row("daily_amt", "2호 — 일수분", "Daily portion", f"=ROUNDDOWN(ROUND({daily_expr},4),0)", check=res.get("일수분"),
             note_ko="미납세액 × 일수 × 1일 이율 — 국세기본법 제47조의5제1항제2호", note_en="Unpaid tax × days × daily rate — Art. 47-5(1)2", alias=("일수분",)),
        _row("cap", "한도(미납세액의 10%)", "Cap (10% of the unpaid tax)", "=ROUNDDOWN(ROUND({unpaid}*{cap10},4),0)", check=res.get("한도_10%"), alias=("한도_10%",)),
        _row("pre_amt", "납부고지 전 가산세 — min(1호 + 2호, 10% 한도)", "Penalty before the notice — lower of (fixed + daily) and the 10% cap",
             f"=ROUNDDOWN(ROUND({pre_expr},4),0)"),
    ]
    post_inner = ""
    if post_rule in ("종전", "개정"):
        old_small = nd < _date(2022, 1, 1)            # 도구와 같은 기준 — 제5항 소액 기준(2021.12.31.까지 100만원, 2022.1.1.부터 150만원: 법률 제18586호)
        inputs.append(_inp("small", "소액 기준 — 납부고지서별·세목별 세액이 이 금액 미만이면 고지 후분 없음",
                           "Small-amount threshold per notice and tax item — no post-notice portion below it", 1_000_000 if old_small else 1_500_000,
                           kind="rate", src_ko="국세기본법 제47조의5제5항" + ("(2021.12.31.까지 100만원 — 법률 제18586호 부칙 제7조)" if old_small else ""),
                           src_en="Framework Act on National Taxes Art. 47-5(5)" + (" (KRW 1,000,000 until 2021-12-31 — Act No. 18586, Addenda Art. 7)" if old_small else "")))
        if args.get("notice_amount") is not None:
            na = "notice_amt_in"       # 입력 줄과 계산 줄의 id가 겹치지 않게(한 블록에 두 경우가 섞여도 줄이 따로)
            inputs.append(_inp(na, "납부고지서별·세목별 세액", "Tax per notice and tax item", args["notice_amount"], arg="notice_amount"))
        else:
            na = "notice_amt"
            rows.append(_row("notice_amt", "납부고지서별·세목별 세액(미납세액 + 납부고지 전 가산세로 봄)", "Tax per notice and tax item (taken as unpaid tax + penalty before the notice)",
                             "={unpaid}+{pre_amt}", note_ko=jt("⑤ 소액 체납") or "다르면 도구의 notice_amount에 넣는다 — 국세기본법 제47조의5제5항",
                             note_en=_basis("Art. 47-5(5); enter notice_amount in the tool if different", jt("⑤ 소액 체납"))))
        plus = ""
        if post_rule == "종전":
            span = (pd - nd).days
            if not excluded and int(res.get("고지후_일수") or 0) != span:      # 제4항 5년 한도에 걸림
                return None
            segs2 = late_payment_rate_segments((nd + _timedelta(days=1)).isoformat(), span)
            if len(segs2) == 1:
                inputs.append(_inp("daily_post", "원천징수 납부지연가산세 — 1일 이율(납부고지 후)", "Withholding late-payment penalty — daily rate after the notice",
                                   segs2[0][1], fmt=PCT, kind="rate", src_ko=decree, src_en=decree_en))
                rows.append(_row("post_days", "납부고지 후 일수(지정납부기한 다음 날부터 납부일까지)", "Days after the notice (day after the notice due date to the payment date)",
                                 "=MAX(0,{paid_on}-{notice_due})", fmt="0", check=None if excluded else res.get("고지후_일수"), summary=True,
                                 note_ko=jt("고지 후"), note_en=_basis("Daily portion after the notice (rule before 2026-07-01); five-year limit under Art. 47-5(4)", jt("고지 후")),
                                 alias=("고지후_일수",)))
                post_expr = "{unpaid}*{post_days}*{daily_post}"
            else:
                terms = []
                for i, (n, r) in enumerate(segs2, 1):
                    inputs.append(_inp(f"daily_post{i}", f"원천징수 납부지연가산세 — 1일 이율(납부고지 후, 기간 {i})",
                                       f"Withholding late-payment penalty — daily rate after the notice (period {i})", r, fmt=PCT, kind="rate",
                                       src_ko=decree + "(이율 변경일 기준 기간 안분)", src_en="Enforcement Decree of the Framework Act on National Taxes (국세기본법 시행령) Art. 27-4 (period split at the rate change date)"))
                    rows.append(_row(f"post_days{i}", f"납부고지 후 일수 — 기간 {i}(이율 변경일 기준, 도구 값)", f"Days after the notice — period {i} (split at the rate change date, tool value)",
                                     value=n, fmt="0", note_ko=jt("고지 후"), note_en=_basis("Daily portion after the notice", jt("고지 후"))))
                    terms.append(f"{{post_days{i}}}*{{daily_post{i}}}")
                post_expr = "{unpaid}*(" + "+".join(terms) + ")"
        else:
            inputs.append(_inp("monthly", "납부고지 후 — 경과 개월마다의 이율(월 1만분의 67)", "After the notice — rate per month elapsed", 0.0067, fmt=PCT, kind="rate",
                               src_ko="국세기본법 제47조의5제1항제3호 · 시행령 제27조의4제2항", src_en="Framework Act on National Taxes Art. 47-5(1)3; Enforcement Decree Art. 27-4(2)"))
            m_note = "지정납부기한 다음 날부터 납부일 전날까지 경과 개월 수, 60개월 한도(제47조의5제4항)"
            if (nd + _timedelta(days=1)).day <= 28:
                rows.append(_row("months", "경과 개월 수(지정납부기한 다음 날부터 납부일 전날까지)", "Months elapsed (day after the notice due date to the day before payment)",
                                 '=MIN(60,DATEDIF({notice_due}+1,{paid_on},"m"))', fmt="0", check=None if excluded else res.get("경과_개월"), summary=True,
                                 note_ko=" — ".join(x for x in (jt("고지 후"), m_note) if x),
                                 note_en=_basis("Whole months elapsed, capped at 60 months under Art. 47-5(4)", jt("고지 후")), alias=("경과_개월",)))
            else:           # 기산일이 29~31일이면 말일 만료 규칙(도구의 개월 계산)이 엑셀 DATEDIF와 달라질 수 있어 도구 값을 둠
                rows.append(_row("months", "경과 개월 수(지정납부기한 다음 날부터 납부일 전날까지, 도구 값)", "Months elapsed (day after the notice due date to the day before payment, tool value)",
                                 value=int(res.get("경과_개월") or 0), fmt="0", summary=True, note_ko=" — ".join(x for x in (jt("고지 후"), m_note) if x),
                                 note_en=_basis("Whole months elapsed, capped at 60 months under Art. 47-5(4)", jt("고지 후")), alias=("경과_개월",)))
            post_expr = "{unpaid}*{months}*{monthly}"
            if args.get("dunning_fee"):
                inputs.append(_inp("dunning", "독촉비용(4호)", "Cost of the demand notice", args["dunning_fee"], arg="dunning_fee",
                                   src_ko="국세기본법 제47조의5제1항제4호 · 시행령 제27조의4제3항", src_en="Framework Act on National Taxes Art. 47-5(1)4; Enforcement Decree Art. 27-4(3)"))
                plus = "+{dunning}"
        rows.append(_row("post_amt", "납부고지 후분" + ("(종전 2호 일수분)" if post_rule == "종전" else "(3호)"),
                         "Portion after the notice" + (" (daily portion, rule before 2026-07-01)" if post_rule == "종전" else " (monthly portion)"),
                         f"=IF({{{na}}}<{{small}},0,ROUNDDOWN(ROUND({post_expr},4),0))", check=res.get("고지후분"), summary=True,
                         note_ko="소액 기준 미만이면 0 — 국세기본법 제47조의5제5항", note_en="Nil below the small-amount threshold — Art. 47-5(5)", alias=("고지후분",)))
        post_inner = f"+IF({{{na}}}<{{small}},0,{post_expr}{plus})"
    inputs.append(_inp("cap50", "전체 한도(미납세액의 50%)", "Overall cap (50% of the unpaid tax)", 0.50, fmt=PCT, kind="rate",
                       src_ko="국세기본법 제47조의5제1항(전체 50% 한도)", src_en="Framework Act on National Taxes Art. 47-5(1), overall 50% cap"))
    rows += [
        _row("cap50_amt", "전체 한도(미납세액의 50%)", "Overall cap (50% of the unpaid tax)", "=ROUNDDOWN(ROUND({unpaid}*{cap50},4),0)", check=res.get("한도_50%"), alias=("한도_50%",)),
        _row("penalty", "가산세", "Penalty", f"=ROUNDDOWN(ROUND(MIN({pre_expr}{post_inner},{{unpaid}}*{{cap50}}),4),0)", check=res.get("가산세"), key=True, summary=True,
             note_ko="min(납부고지 전 가산세 + 납부고지 후분, 50% 한도), 원 미만 절사", note_en="Lower of (penalty before the notice + portion after it) and the 50% cap, truncated to KRW 1",
             alias=("가산세",)),
    ]
    return {"inputs": inputs, "rows": rows, "links": {}}


def _spec_generic(args: dict, data: dict, label, *, steps_ok: bool = True, plain_note: str = "tool_value") -> dict:
    """`계산식`이 있으면 그 단계를 수식으로(수식으로 쓸 수 없는 단계는 도구 값), 없으면 결과의 숫자 값을 그대로(수식 아님).
    steps_ok=False면 `계산식`을 쓰지 않고 결과 값만 옮긴다."""
    res = data.get("결과") if isinstance(data.get("결과"), dict) else {}
    steps = [s for s in data.get("계산식") or [] if isinstance(s, dict) and s.get("이름") and s.get("식") is not None] if steps_ok else []
    if steps:
        inputs, links = [], {}
        for i in data.get("계산식_입력") or []:
            if not isinstance(i, dict) or not i.get("이름"):
                continue
            v = i.get("값")
            if isinstance(v, float) and v in (float("inf"), float("-inf")):
                continue
            num = _is_num(v)
            inputs.append(_inp(i["이름"], str(i["이름"]), label(i["이름"]), v, fmt=NUM if num and (isinstance(v, int) or abs(v) >= 10) else ("0.0#####" if num else "@"),
                               kind="input" if num else "text", arg=i["이름"], src_ko=str(i.get("설명") or ""), src_en=str(i.get("설명") or "")))
            if num:
                links[i["이름"]] = i["이름"]
        num_names = {x["id"] for x in inputs if _is_num(x["value"])}
        rows, n_formula = [], 0
        for n, s in enumerate(steps):
            v = s.get("값")
            num = _is_num(v)
            last = n == len(steps) - 1
            fmt = NUM if not num or isinstance(v, int) or abs(v) >= 10 else "0.0#####"
            f = _step_formula(s["식"], num_names | {x["id"] for x in rows if x["f"] is not None or _is_num(x["value"])})
            if f is None:           # 수식으로 쓸 수 없는 단계 — 도구 값을 옮김(값이 없으면 줄을 만들지 않음)
                if v is None or isinstance(v, (dict, list)):
                    continue
                rows.append(_row(s["이름"], str(s["이름"]), label(s["이름"]), value=v, fmt=fmt if num else "@", key=last,
                                 summary=num and (last or s["이름"] in res), alias=(s["이름"],),
                                 note_ko=" — ".join(x for x in (_t("tool_value", False), str(s.get("설명") or "")) if x),
                                 note_en=" — ".join(x for x in (_t("tool_value", True), str(s.get("설명") or "")) if x)))
                continue
            n_formula += 1
            rows.append(_row(s["이름"], str(s["이름"]), label(s["이름"]), f, fmt=fmt, check=v if num else None, key=last,
                             summary=last or s["이름"] in res, note_ko=str(s.get("설명") or ""), note_en=str(s.get("설명") or ""), alias=(s["이름"],)))
        if rows:
            return {"inputs": inputs, "rows": rows, "links": links, "plain": n_formula == 0}
    inputs = [_inp(k, k, k, v, kind="input", arg=k, fmt=NUM if isinstance(v, int) or abs(v) >= 10 else "0.0#####")
              for k, v in (args or {}).items() if _is_num(v)]
    items = [(k, v) for k, v in res.items() if _is_num(v)]
    rows = [_row(f"r_{k}", str(k), label(k), value=v, fmt=NUM if isinstance(v, int) or abs(v) >= 10 else "0.0#####", summary=n < 4,
                 note_ko=_t(plain_note, False), note_en=_t(plain_note, True), alias=(k,)) for n, (k, v) in enumerate(items)]
    return {"inputs": inputs, "rows": rows, "links": {}, "plain": True}


def _spec(tool: str, args: dict, data: dict, label) -> dict:
    args = _tool_args(tool, args)
    if tool == "nonresident_withholding":
        return _spec_nonresident(args, data)
    if tool == "withholding_late_payment_penalty":
        res = data.get("결과") if isinstance(data.get("결과"), dict) else {}
        sp = _spec_wh_penalty(args, data) or _spec_wh_penalty_notice(args, data)
        if sp:
            return sp
        # 전용 틀에 맞지 않는 납부고지 건(제4항 5년 한도, 제5항 소액 기준 경과조치, 2019년 이전 성립분 등): 도구의 `계산식`은 납부고지 전
        # 부분만이라 수식으로 쓰면 가산세가 틀린다 — 도구 값을 그대로 옮긴다.
        if args.get("notice_due") or args.get("paid_on") or res.get("고지후분"):
            return _spec_generic(args, data, label, steps_ok=False, plain_note="tool_value_no_layout")
    return _spec_generic(args, data, label)


def _extra_cell(cfg: dict, cell: str) -> tuple[str | None, str]:
    """자유 형식 시트 설정에서 칸 주소(A1 꼴)가 숫자·수식·링크 칸인지 본다. → (오류 글 또는 None, 표시 형식)."""
    from openpyxl.utils import column_index_from_string
    from .workbook_extra import FIRST_ROW, FORMATS
    m = _re.fullmatch(r"([A-Z]{1,3})(\d{1,7})", cell)
    col, row = (column_index_from_string(m.group(1)), int(m.group(2))) if m else (0, 0)
    ncols, last = len(cfg["headers"]), cfg["last_row"]
    where = f"'{cfg['sheet']}' 시트의 표는 A{FIRST_ROW}:{_L(ncols)}{last}(머리 행 4행, 첫 행 5행)"
    if not m or not (FIRST_ROW <= row <= last and col <= ncols):
        return f"cell '{cell}'가 표 밖 — {where}", ""
    fmt = cfg["formats"][col - 1]
    fmt = FORMATS[fmt] if fmt and fmt not in ("text", "source") else NUM
    i = row - FIRST_ROW
    if i == len(cfg["rows"]):      # 합계 행
        return (None, fmt) if cfg["total"] and col - 1 in cfg["total"]["cols"] else (f"cell '{cell}'는 합계가 없는 칸 — {where}", "")
    r = cfg["rows"][i]
    kind = r["cells"][col - 1][0] if "cells" in r and col - 1 < len(r["cells"]) else "blank"
    if kind not in ("num", "formula", "link"):
        return f"cell '{cell}'는 숫자·수식 칸이 아님 — {where}", ""
    return None, fmt


def make_resolver(calls: list, results: list[dict], spec_of, cell_of: dict | None, cell_label: dict | None = None):
    """{from_call, from_row} → 그 call의 결과 줄(또는 입력)이 놓인 칸. 자유 형식 시트·쟁점 금액이 계산 도구 결과를 가리킬 때 쓴다.

    spec_of(순번) → 그 call의 수식 틀(없으면 None), cell_of → {(순번, 줄 id): "'시트'!$B$9"}(기존 출력에는 없음 — 그러면 ref 없이 도구 값만).
    돌려주는 함수: resolve(link) → {"ref": 칸 주소 또는 None, "value": 도구 값, "fmt": 표시 형식}. 찾지 못하면 ValueError(글)."""
    def resolve(link: dict) -> dict:
        idx = _call_ref(link.get("from_call"), calls)
        if idx is None:
            raise ValueError(f"from_call '{link.get('from_call')}'를 calls에서 찾지 못함(label 또는 1부터 세는 순번)")
        cd = results[idx] if idx < len(results) else {}
        spec = None if cd.get("error") or not cd.get("result") else spec_of(idx)
        if not spec:
            raise ValueError(f"from_call '{link.get('from_call')}'는 오류가 난 call이라 가리킬 수 없음")
        name = str(link.get("from_row"))
        y = next((y for y in spec.get("rows", []) if name in (y["id"], y["ko"], y["en"], *y.get("alias", ()))), None)
        is_row = y is not None
        if y is None:
            y = next((i for i in spec.get("inputs", []) if name in (i["id"], i["ko"], i["en"], i.get("arg"))), None)
        if y is None:
            have = [x["ko"] for x in spec.get("rows", [])] + [i["arg"] for i in spec.get("inputs", []) if i.get("arg")]
            raise ValueError(f"from_row '{name}'를 call {idx + 1}에서 찾지 못함 — 쓸 수 있는 줄: {', '.join(str(h) for h in have)}")
        value = (y.get("check") if y["f"] is not None else y["value"]) if is_row else y["value"]
        if isinstance(value, tuple):
            value = value[0]
        ref = (cell_of or {}).get((idx, y["id"]))
        if ref and cell_label is not None and cell_label.get((idx, y["id"])) != y["ko"]:
            ref = None
        if value is None and not (ref and is_row and y["f"] is not None):      # 도구 값 없이 수식으로만 있는 줄(예: 송금액)은 칸이 있을 때만
            raise ValueError(f"from_row '{name}'(call {idx + 1})에는 도구 값이 없어 가리킬 수 없음")
        return {"ref": ref, "value": value, "fmt": y["fmt"], "idx": idx, "item": y}
    return resolve


# ── 시트 그리기 ────────────────────────────────────────────────────────────
def as_text(cell):
    """글을 적은 칸이 수식으로 저장되지 않게 한다 — openpyxl은 '='로 시작하는 문자열을 수식으로 저장하므로 문자열 칸(앞 따옴표)으로 바꾼다.
    호출자가 준 글(제목·회사·머리글·메모·출처·쟁점)과 도구가 돌려준 글을 적을 때 쓴다. 칸을 그대로 돌려준다."""
    if cell.data_type == "f":
        cell.data_type, cell.quotePrefix = "s", True
    return cell


def _sheet_name(wb, raw: str, taken: set[str]) -> str:
    """시트 이름으로 쓸 수 있게 다듬는다 — 금지 문자 제거, 31자, 앞뒤 작은따옴표 없음(자른 뒤에도), 대소문자만 다른 이름은 같은 이름으로 봄(엑셀 규칙)."""
    clean = lambda x: x.strip().strip("'").strip()
    s = clean(clean(_BAD_SHEET.sub(" ", str(raw)))[:31]) or "Sheet"
    have = {x.casefold() for x in wb.sheetnames} | {x.casefold() for x in taken}
    base, n = s, 2
    while s.casefold() in have:
        suf = f" ({n})"
        s, n = clean(base[:31 - len(suf)]) + suf, n + 1
    taken.add(s)
    return s


def _q(sheet: str) -> str:
    return "'" + sheet.replace("'", "''") + "'"


def rename_sheets(wb, ren: dict[str, str]) -> None:
    """시트 이름을 바꾸고, 그 이름을 가리키는 수식·정의된 이름·시트 이름만 적힌 칸을 맞춘다."""
    ren = {o: n for o, n in ren.items() if n and o in wb.sheetnames and n not in wb.sheetnames}
    if not ren:
        return
    for o, n in ren.items():
        wb[o].title = n
    quoted = _re.compile("|".join(_re.escape(f"'{o}'") for o in sorted(ren, key=len, reverse=True)))
    bare_names = [o for o in ren if " " not in o and "(" not in o]
    bare = _re.compile(r"(?<![\w'가-힣·])(" + "|".join(_re.escape(o) for o in bare_names) + r")!") if bare_names else None

    def fix(s: str) -> str:
        s = quoted.sub(lambda m: _q(ren[m.group(0)[1:-1]]), s)
        return bare.sub(lambda m: _q(ren[m.group(1)]) + "!", s) if bare else s

    for dn in wb.defined_names.values():
        if dn.attr_text:
            dn.attr_text = fix(dn.attr_text)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not isinstance(v, str):
                    continue
                nv = fix(v) if c.data_type == "f" else (ren[v] if v in ren else quoted.sub(lambda m: _q(ren[m.group(0)[1:-1]]), v))
                if nv != v:
                    c.value = nv


# ── 뒤 시트 줄이기(detail) — 계산 N·판단·근거를 '계산 상세' 한 장으로 ─────────────────
_CELL = r"\$?[A-Z]{1,3}\$?\d+"
_A1 = _re.compile(rf"{_CELL}(?::{_CELL})?")
_A1_PART = _re.compile(r"(\$?[A-Z]{1,3}\$?)(\d+)")


def _shift_rows(ref: str, off: int) -> str:
    return _A1_PART.sub(lambda m: f"{m.group(1)}{int(m.group(2)) + off}", ref)


def _retarget(formula: str, moved: dict[str, tuple[str, int]], own_off: int = 0) -> str:
    """수식 속 칸 주소를 옮긴다 — 시트 이름이 붙은 주소는 moved({옛 시트: (새 시트, 행 이동)})에 있으면 새 시트로,
    시트 이름이 없는 주소는 own_off만큼 아래로(시트를 통째로 옮겨 붙일 때). 이름(정의된 이름)·함수·문자열은 그대로."""
    from openpyxl.formula import Tokenizer
    try:
        items = Tokenizer(formula).items
    except Exception:
        return formula
    out = []
    for t in items:
        v = t.value
        if t.type == "OPERAND" and t.subtype == "RANGE":
            if "!" in v:
                sh, _, ref = v.rpartition("!")
                name = sh[1:-1].replace("''", "'") if sh.startswith("'") and sh.endswith("'") else sh
                if name in moved and _A1.fullmatch(ref):
                    v = f"{_q(moved[name][0])}!{_shift_rows(ref, moved[name][1])}"
            elif own_off and _A1.fullmatch(v):
                v = _shift_rows(v, own_off)
        out.append(v)
    return "=" + "".join(out)


def _stack(dst, src, at: int) -> int:
    """src 시트의 칸(값·수식·서식·병합·행 높이)을 dst의 at행부터 옮겨 붙인다. 돌려주는 값: 다음 빈 행."""
    from copy import copy
    off = at - 1
    for row in src.iter_rows():
        for c in row:
            if c.value is None and not c.has_style:
                continue
            d = dst.cell(c.row + off, c.column)
            d.value = _retarget(c.value, {}, off) if c.data_type == "f" and isinstance(c.value, str) else c.value
            if c.has_style:
                d._style = copy(c._style)
            if c.data_type != "f" and isinstance(c.value, str) and c.value.startswith("="):
                d.data_type, d.quotePrefix = "s", True
    for rng in src.merged_cells.ranges:
        dst.merge_cells(start_row=rng.min_row + off, start_column=rng.min_col, end_row=rng.max_row + off, end_column=rng.max_col)
    for r, dim in src.row_dimensions.items():
        if dim.height:
            dst.row_dimensions[r + off].height = dim.height
    return src.max_row + off + 1


def _sheet_of_name(dn) -> str | None:
    m = _re.match(r"'((?:[^']|'')+)'!|([^'!]+)!", dn.attr_text or "")
    return (m.group(1).replace("''", "'") if m.group(1) else m.group(2)) if m else None


def add_sheets(wb, cfg: dict, *, lang: str, title: str, company: str, period: str, calls: list, results: list[dict],
               label=None, cite=None, detail: str = "full", roles: dict | None = None, judgement_counts: dict[int, int] | None = None,
               labels=None, extra: list[dict] | None = None) -> dict:
    """통합 문서 시트를 워크북 맨 앞에 넣는다. 돌려주는 값: {"시트": 새 시트 이름(순서대로), "이름_바꿈": {옛: 새}, "warnings": [...],
    "서식_수": 신고 서식 시트 수, "안내": {앞 시트 이름: 영문 한 줄}, "자유_시트": 자유 형식 시트에 쓸 이름, "자유_위치": 그 시트가 들어갈 자리,
    "resolve": {from_call, from_row} → 칸}.

    extra — 자유 형식 시트 설정(workbook_extra.normalize_extra). 여기서는 이름을 정하고 요약 범례에 적기만 한다(그리기는 호출자 — 글을 문자열 칸으로
    바꾸는 마지막 정리 뒤에 그려야 호출자가 준 수식이 글로 바뀌지 않는다).

    detail — 뒤 시트: 'full'(기존 시트 전부), 'forms'('계산 상세' + 신고 서식), 'compact'('계산 상세' 한 장).
    roles — 기존 시트의 구실({"calc": {call 순번: 시트}, "jud": 시트, "inputs": 시트, "list": 시트, "summary": 시트, "forms": [시트]}), compact·forms에서 필요.
    judgement_counts — {call 순번: 판단·근거 시트의 줄 수}(오류 call 제외, 시트에 적힌 순서)."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter as L
    en = lang == "en"
    label = label or (labels.label if labels is not None else (lambda s: s))

    def shown(x: dict) -> str:
        """줄·입력 이름 — 호출자가 준 라벨 표(labels)에 그 줄의 이름(찍히는 글 또는 국문 줄 이름)이 있으면 그 글.
        결과 키 별칭으로는 바꾸지 않는다(시나리오 줄에는 이미 제 이름이 있음 — 결과 키는 '계산 상세'·'계산 N'에서 바뀜)."""
        text = x["en"] if en else x["ko"]
        if labels is None:
            return text
        if en and x["ko"] and f"({x['ko']})" in text:      # 이미 '표시 글 (원래 키)' 꼴(결과 키를 옮긴 줄)
            return text
        for k in (text, x["ko"]):
            if isinstance(k, str) and k.strip() in labels.table:
                own = labels.table[k.strip()]
                labels.used.add(k.strip())
                return f"{own} ({k.strip()})" if en and k != x["en"] and k != text and own != k else own
        return text

    face = "Calibri" if en else "맑은 고딕"
    F = lambda **k: Font(name=face, **{"size": 10, **k})
    f_title, f_sub = F(bold=True, size=14), F(italic=True, size=9, color=GREY)
    f_band, f_head = F(bold=True), F(bold=True, color="FFFFFF")
    fill = lambda c: PatternFill("solid", fgColor=c)
    wrap = Alignment(wrap_text=True, vertical="top")
    warnings: list[str] = list(cfg.get("warnings") or [])

    # 이름이 겹치는 기존 시트는 '호출 …'로
    ren = {}
    if en:
        ren = {"Summary (요약)": _t("old_summary", True), "Inputs (입력·가정)": _t("old_inputs", True), "요약": _t("old_summary", True)}
    else:
        ren = {"요약": _t("old_summary", False)}
    ren = {o: n for o, n in ren.items() if o in wb.sheetnames}
    rename_sheets(wb, ren)

    # 블록: 시나리오에 없는 성공 call은 call마다 한 블록(한 열) — full은 call마다 한 시트, compact·forms는 한 시트에 차례로
    if roles is None:
        detail = "full"
    blocks = [dict(b) for b in cfg["blocks"]]
    rest = _t("rest" if blocks else "rest_only", en)
    for i, cd in enumerate(results):
        if i in cfg["used"] or cd.get("error") or not cd.get("result"):
            continue
        lab = str(cd.get("label") or f"call {i + 1}")
        blocks.append({"sheet": lab if detail == "full" else rest, "title": lab if detail == "full" else rest, "subtitle": "", "heading": lab,
                       "columns": [{"idx": i, "heading": lab}], "notes": {}, "summary_note": ""})
    for b in blocks:
        for c in b["columns"]:
            cd = results[c["idx"]]
            c["error"] = cd.get("error") or ("" if cd.get("result") else "결과 없음")
            c["spec"] = None if c["error"] else _spec(cd.get("tool", ""), (calls[c["idx"]] or {}).get("args") or {}, cd.get("data") or {}, label)

    taken: set[str] = set()
    n_sum, n_inp = _sheet_name(wb, _t("summary", en), taken), _sheet_name(wb, _t("inputs", en), taken)
    sheet_of: dict[str, str] = {}
    for b in blocks:
        if b["sheet"] not in sheet_of:
            sheet_of[b["sheet"]] = _sheet_name(wb, b["sheet"], taken)
    n_iss = _sheet_name(wb, _t("issues", en), taken) if cfg["issues"] else None
    n_extra = [_sheet_name(wb, x["sheet"], taken) for x in extra or []]
    n_forms = len((roles or {}).get("forms") or [])
    n_det = _sheet_name(wb, _t("detail", en), taken) if detail != "full" else None

    def page(ws, widths: list[float], freeze: str = "A4") -> None:
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[L(j)].width = w
        ws.freeze_panes = freeze
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = 9
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True

    def band(ws, r: int, text: str, last_col: int) -> None:
        as_text(ws.cell(r, 1, text)).font = f_band
        for j in range(1, last_col + 1):
            ws.cell(r, j).fill = fill(BAND)

    def heads(ws, r: int, texts: list[str], first_col: int = 1) -> None:
        for j, h in enumerate(texts, first_col):
            c = as_text(ws.cell(r, j, h))
            c.font, c.fill, c.alignment = f_head, fill(NAVY), Alignment(wrap_text=True, vertical="center")

    def lines(text: Any, width: float, small: bool = False) -> int:
        """그 너비 칸에서 줄바꿈될 줄 수(대략) — 한글은 두 칸, 9pt 기울임(메모·출처)은 한 줄에 더 들어감."""
        w = sum(2 if "가" <= ch <= "힣" else 1 for ch in str(text or ""))
        return max(1, -(-w // max(8, int(width * (1.4 if small else 1.05)))))

    # ── 입력·출처 ──
    ws_i = wb.create_sheet(n_inp)
    ws_i.cell(1, 1, _t("inputs_title", en)).font = f_title
    ws_i.cell(2, 1, _t("inputs_sub", en)).font = f_sub
    heads(ws_i, 4, [_t("item", en), _t("value", en), _t("source", en)])
    ri = 5
    in_ref: dict[tuple[int, str], str] = {}      # (call 순번, 입력 id) → 'Inputs'!$B$n

    def put_input(inp: dict, text: str, src: str, assumption: bool) -> str:
        nonlocal ri
        as_text(ws_i.cell(ri, 1, text)).font = F()
        ws_i.cell(ri, 1).alignment = wrap
        c = ws_i.cell(ri, 2, inp["value"])
        if isinstance(inp["value"], str):
            as_text(c)
        c.font, c.number_format = F(color=BLUE), inp["fmt"]
        c.alignment = Alignment(horizontal="right" if isinstance(inp["value"], str) else None, vertical="top")
        if assumption:
            c.fill = fill(YELLOW)
        s = as_text(ws_i.cell(ri, 3, _shown_basis(src, cite) if en else src))     # 도구가 만든 근거는 영문 인용으로(호출자가 준 출처는 그대로)
        s.font, s.alignment = f_sub, wrap
        ws_i.row_dimensions[ri].height = 14 * max(lines(text, 52), lines(src, 80, True))
        ri += 1
        return f"{_q(n_inp)}!$B${ri - 1}"

    cols_all = [(b, c) for b in blocks for c in b["columns"] if c["spec"]]
    pending: list[tuple[int, dict, str, int, Any, Any]] = []     # (입력 칸 행, 출처 항목, 차감 칸 주소, call 순번, 입력 값) — 시나리오 시트를 그린 뒤 수식으로
    rate_rows: dict[tuple, str] = {}
    if any(i["kind"] == "rate" for _, c in cols_all for i in c["spec"]["inputs"]):
        band(ws_i, ri, _t("rates", en), 3)
        ri += 1
        for _, c in cols_all:
            for inp in c["spec"]["inputs"]:
                if inp["kind"] != "rate":
                    continue
                k = (inp["ko"], inp["value"])
                if k not in rate_rows:
                    rate_rows[k] = put_input(inp, shown(inp), inp["src_en"] if en else inp["src_ko"], False)
                in_ref[(c["idx"], inp["id"])] = rate_rows[k]
        ri += 1
    for b in blocks:
        cols = [c for c in b["columns"] if c["spec"] and any(i["kind"] != "rate" for i in c["spec"]["inputs"])]
        if not cols:
            continue
        band(ws_i, ri, b["heading"] if b["heading"] == sheet_of[b["sheet"]] else f"{sheet_of[b['sheet']]} — {b['heading']}", 3)
        ri += 1
        ids: list[str] = []
        for c in cols:
            ids += [i["id"] for i in c["spec"]["inputs"] if i["kind"] != "rate" and i["id"] not in ids]
        for id_ in ids:
            have = [(c, next(i for i in c["spec"]["inputs"] if i["id"] == id_)) for c in cols if any(i["id"] == id_ for i in c["spec"]["inputs"])]
            many = (len({str(i["value"]) for _, i in have}) > 1 or len({(cfg["sources"].get((c["idx"], i["arg"])) or {}).get("source") for c, i in have}) > 1
                    or any("from" in (cfg["sources"].get((c["idx"], i["arg"])) or {}) for c, i in have))
            done: dict[str, str] = {}
            for c, inp in have:
                s = cfg["sources"].get((c["idx"], inp["arg"])) or {}
                if not many and done:
                    in_ref[(c["idx"], id_)] = next(iter(done.values()))
                    continue
                text = str(s.get("label") or shown(inp)) + (f" — {c['heading']}" if many and len(have) > 1 else "")
                less_ref = ""
                if s.get("less") is not None:
                    less_ref = put_input(_inp("less", "", "", s["less"]), str(s.get("less_label") or _t("less", en)), s.get("less_source", ""), False)
                done[c["heading"]] = in_ref[(c["idx"], id_)] = put_input(inp, text, s.get("source") or (inp["src_en"] if en else inp["src_ko"]), bool(s.get("assumption")))
                if "from" in s:
                    pending.append((ri - 1, s, less_ref, c["idx"], inp["value"], inp["arg"]))
        ri += 1
    for (idx, arg), s in cfg["sources"].items():
        cd = next((c for _, c in cols_all if c["idx"] == idx), None)
        if cd is None or not any(i["arg"] == arg for i in cd["spec"]["inputs"]):
            warnings.append(f"sources: call {idx + 1}의 입력 '{arg}'는 '{n_inp}' 시트에 실린 입력이 아니라 출처를 싣지 못함")
    page(ws_i, [52, 20, 80], "A5")

    # ── 시나리오 시트 ──
    cell_of: dict[tuple[int, str], str] = {}     # (call 순번, 줄 id) → 'Sheet'!$B$n
    cell_label: dict[tuple[int, str], str] = {}  # (call 순번, 줄 id) → 그 칸이 놓인 줄의 이름
    summary_rows: list[tuple[dict, list[tuple[str, dict]]]] = []
    rows_at: dict[str, int] = {}
    sheet_ncol: dict[str, int] = {}              # 시트마다 가장 넓은 블록의 열 수 — '근거 · 메모' 열을 한 자리에
    for b in blocks:
        sheet_ncol[sheet_of[b["sheet"]]] = max(sheet_ncol.get(sheet_of[b["sheet"]], 1), len(b["columns"]))
    for b in blocks:
        name = sheet_of[b["sheet"]]
        new = name not in wb.sheetnames
        ws = wb.create_sheet(name) if new else wb[name]
        ncol = len(b["columns"])
        if new:
            as_text(ws.cell(1, 1, b["title"] or name)).font = f_title
            as_text(ws.cell(2, 1, b["subtitle"])).font = f_sub
            rows_at[name] = 4
        r = rows_at[name]
        last = sheet_ncol[name] + 2
        band(ws, r, b["heading"], last)
        r += 1
        heads(ws, r, [c["heading"] for c in b["columns"]] + [""] * (sheet_ncol[name] - ncol) + [_t("note_col", en)], 2)
        ws.row_dimensions[r].height = 15 * max(lines(c["heading"], 16) for c in b["columns"])     # 굵은 글씨라 한 줄에 덜 들어감
        r += 1
        specs = [c["spec"] for c in b["columns"]]
        if not any(specs):
            for j, c in enumerate(b["columns"], 2):
                as_text(ws.cell(r, j, c["error"])).font = F(color="C00000")
            rows_at[name] = r + 2
            continue
        # 줄 순서: 입력(링크) 먼저, 이어서 계산 줄 — 열마다 있는 줄을 차례로 합친다.
        # 같은 id라도 줄 이름이 다르면(예: 종전·개정 규정이 섞인 블록) 다른 줄 — 열마다 제 줄 이름 아래에 놓인다
        rk = lambda x: (x["id"], x["ko"])

        def merged(kind: str) -> list[dict]:
            out: list[dict] = []
            for sp in specs:
                prev = -1
                for x in (sp or {}).get(kind, []):
                    at = next((k for k, y in enumerate(out) if rk(y) == rk(x)), None)
                    if at is None:
                        out.insert(prev + 1, x)
                        at = prev + 1
                    prev = at
            return out
        in_rows, calc_rows = merged("inputs"), merged("rows")
        row_at = {(kind, rk(x)): r + k for k, (kind, x) in enumerate([("inputs", x) for x in in_rows] + [("rows", x) for x in calc_rows])}
        col_rows: dict[int, dict[str, int]] = {}         # 열(call 순번)마다 {줄 id: 행} — 그 열의 수식이 가리키는 행
        for c in b["columns"]:
            col_rows[c["idx"]] = {y["id"]: row_at[(kind, rk(y))] for kind in ("inputs", "rows") for y in (c["spec"] or {}).get(kind, [])}
        notes = dict(b["notes"])
        for kind, x in [("inputs", x) for x in in_rows] + [("rows", x) for x in calc_rows]:
            rr = row_at[(kind, rk(x))]
            is_input = kind == "inputs"
            as_text(ws.cell(rr, 1, shown(x))).font = F()
            ws.cell(rr, 1).alignment = wrap
            for j, c in enumerate(b["columns"], 2):
                sp = c["spec"]
                mine = next((y for y in (sp or {}).get(kind, []) if rk(y) == rk(x)), None)
                if mine is None:
                    continue
                cell = ws.cell(rr, j)
                cell.number_format = mine["fmt"]
                cell.alignment = Alignment(vertical="top")
                if is_input:
                    cell.value, cell.font = "=" + in_ref[(c["idx"], x["id"])], F(color=GREEN)
                elif mine["f"] is None:
                    v = mine["value"]
                    cell.value = v[1 if en else 0] if isinstance(v, tuple) else v
                    as_text(cell)
                    cell.font = F(color=GREY) if sp.get("plain") or isinstance(cell.value, (int, float)) else F()
                    if isinstance(cell.value, str):
                        cell.alignment = wrap
                else:
                    cell.value = _re.sub(r"\{([^{}]+)\}", lambda m: f"{L(j)}{col_rows[c['idx']][m.group(1)]}", mine["f"])
                    cell.font = F()
                    if mine["key"]:
                        cell.fill = fill(YELLOW)
                cell_of[(c["idx"], x["id"])] = f"{_q(name)}!${L(j)}${rr}"
                cell_label[(c["idx"], x["id"])] = x["ko"]
            note = (_shown_basis(x["note_en"], cite) if en else x["note_ko"]) if not is_input else ""
            more = next((notes.pop(k) for k in (x["id"], x["ko"], x["en"], *x.get("alias", ())) if k in notes), "")
            text = " — ".join(t for t in (more, note) if t)
            nc = as_text(ws.cell(rr, last, text))
            nc.font, nc.alignment = f_sub, wrap
            ws.row_dimensions[rr].height = 14 * max(lines(ws.cell(rr, 1).value, 58), lines(text, 70, True),
                                                     *(lines(ws.cell(rr, j).value, 20) for j in range(2, last) if isinstance(ws.cell(rr, j).value, str) and ws.cell(rr, j).data_type != "f"))
        r += len(in_rows) + len(calc_rows)
        for k in notes:
            warnings.append(f"scenarios notes: '{k}'에 맞는 줄이 '{name}' 시트 '{b['heading']}' 블록에 없음 — 줄 이름(시트 A열)이나 결과 키로 적음")
        # 도구 값 대조 — 블록마다 한 줄
        checks_any = False
        for j, c in enumerate(b["columns"], 2):
            sp = c["spec"]
            conds = []
            for y in (sp or {}).get("rows", []):
                v = y.get("check")
                if y["f"] is None or not isinstance(v, (int, float)) or isinstance(v, bool):
                    continue
                d = 0 if isinstance(v, int) else 6
                conds.append(f"ROUND({L(j)}{col_rows[c['idx']][y['id']]},{d})={round(v, d)!r}")
            if conds:
                checks_any = True
                cc = ws.cell(r, j, f'=IF(AND({",".join(conds)}),"{_t("ok", en)}","{_t("ng", en)}")')
                cc.font, cc.alignment = F(size=9, color=GREY), Alignment(horizontal="right")
        if checks_any:
            ws.cell(r, 1, _t("check", en)).font = F(size=9, color=GREY)
            r += 1
        elif all((c["spec"] or {}).get("plain") for c in b["columns"]):
            ws.cell(r, 1, _t("no_formula", en)).font = f_sub
            r += 1
        rows_at[name] = r + 1
        summary_rows.append((b, [(c["heading"], c) for c in b["columns"]]))
        b["_rows"] = [x for x in in_rows if x.get("summary")] + ([x for x in calc_rows if x["summary"]] or calc_rows[-1:])
    for name in set(sheet_of.values()):
        page(wb[name], [58] + [22] * sheet_ncol[name] + [70])

    # ── 다른 call의 결과 줄에서 온 입력(sources의 from_call·from_row·less) — 값이 맞을 때만 수식으로 연결 ──
    for row_i, s, less_ref, idx, value, arg in pending:
        fc = next((c for _, c in cols_all if c["idx"] == s["from"]), None)
        y = next((y for y in (fc["spec"]["rows"] if fc else []) if s["from_row"] in (y["id"], y["ko"], y["en"], *y.get("alias", ()))), None)
        ref = cell_of.get((s["from"], y["id"])) if y else None
        tool_v = y.get("check") if y else None
        if tool_v is None and y is not None and y["f"] is None:
            tool_v = y["value"]
        if not ref or not isinstance(tool_v, (int, float)) or isinstance(tool_v, bool):
            warnings.append(f"sources: call {idx + 1}의 from_row '{s['from_row']}'를 call {s['from'] + 1}의 줄에서 찾지 못해 연결하지 않음(값은 입력 그대로)")
            continue
        if not _is_num(value):
            warnings.append(f"sources: call {idx + 1}의 입력 '{arg}'는 숫자가 아니라(날짜·글) from_call로 연결하지 않음(값은 입력 그대로)")
            continue
        if tool_v - (s.get("less") or 0) != value:
            warnings.append(f"sources: call {idx + 1} 입력 {value:,}이(가) call {s['from'] + 1}의 '{s['from_row']}' {tool_v:,}"
                            + (f" − {s['less']:,}" if s.get("less") is not None else "") + "과 달라 연결하지 않음(값은 입력 그대로)")
            continue
        cell = ws_i.cell(row_i, 2)
        cell.value = "=" + ref + (f"-{less_ref.split('!')[1]}" if less_ref else "")
        cell.font = F(color=GREEN)

    # ── 서식 칸이 가리키는 이름(입력·가정)을 새 칸에 연결 — 입력을 바꾸면 서식 시트도 따라 바뀜 ──
    for _, c in cols_all:
        for nm, id_ in (c["spec"].get("links") or {}).items():
            target = cell_of.get((c["idx"], id_)) or in_ref.get((c["idx"], id_))
            dn = wb.defined_names.get(_re.sub(r"_+", "_", _re.sub(r"[^가-힣A-Za-z0-9_.]+", "_", f"호출{c['idx'] + 1}_{nm}")).rstrip("_"))
            m = _re.fullmatch(r"'?(.+?)'?!\$([A-Z]+)\$(\d+)", (dn.attr_text or "") if dn is not None else "")
            if not target or not m or m.group(1).replace("''", "'") not in wb.sheetnames:
                continue
            cell = wb[m.group(1).replace("''", "'")][f"{m.group(2)}{m.group(3)}"]
            if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                cell.value = "=" + target
                cell.font = Font(color=GREEN)

    resolve = make_resolver(calls, results, lambda i: next((c["spec"] for _, c in cols_all if c["idx"] == i), None), cell_of, cell_label)

    # ── 요약 — 한 화면에 "얼마를, 언제까지, 어디서 계산했나": 핵심 숫자 표 → 조치·기한 → 쟁점 한 줄 → 범례 ──
    # 시나리오 블록을 되풀이하지 않는다(시나리오 시트가 그 표다). 금액 칸은 시나리오 시트의 칸을 가리키는 수식.
    from openpyxl.worksheet.hyperlink import Hyperlink
    ws_s = wb.create_sheet(n_sum)
    as_text(ws_s.cell(1, 1, _t("summary_title", en, t=title))).font = f_title
    as_text(ws_s.cell(2, 1, " | ".join(str(x) for x in (company, period, _t("summary_sub", en, i=n_inp)) if x))).font = f_sub
    figs: list[dict] = []        # {label, ref, fmt, hl, note}
    if cfg.get("key_figures"):   # 호출자가 고른 줄 — 순서·글·강조 그대로
        for n, k in enumerate(cfg["key_figures"], 1):
            if k.get("cell"):
                ex = next((i for i, x in enumerate(extra or []) if x["sheet"].casefold() == str(k["sheet"]).casefold()), None)
                if ex is None:
                    raise ValueError(f"key_figures[{n}].sheet '{k['sheet']}'는 extra_sheets에 없는 시트 — 쓸 수 있는 이름: "
                                     + (", ".join(x["sheet"] for x in extra or []) or "(extra_sheets 없음)"))
                why, fmt = _extra_cell(extra[ex], k["cell"])
                if why:
                    raise ValueError(f"key_figures[{n}] — {why}")
                col, row = _re.fullmatch(r"([A-Z]+)(\d+)", k["cell"]).groups()
                figs.append({"label": k["label"] or f"{n_extra[ex]} {k['cell']}", "ref": f"{_q(n_extra[ex])}!${col}${row}", "fmt": fmt, "hl": k["highlight"], "note": k["note"]})
            else:
                try:
                    got = resolve({"from_call": k["call"], "from_row": k["row"]})
                except ValueError as e:
                    raise ValueError(f"key_figures[{n}] — {str(e).replace('from_call', 'call').replace('from_row', 'row')}") from None
                if not got["ref"] or (got["value"] is not None and not _is_num(got["value"])):
                    raise ValueError(f"key_figures[{n}] — call '{k['call']}'의 '{k['row']}'는 숫자 칸이 아니라 핵심 숫자로 올릴 수 없음")
                head = next((c["heading"] for _, c in cols_all if c["idx"] == got["idx"]), "")
                figs.append({"label": k["label"] or f"{shown(got['item'])} ({head})", "ref": got["ref"], "fmt": got["fmt"], "hl": k["highlight"], "note": k["note"]})
    else:                        # 기본: 블록마다 권고 열(없으면 첫 열)의 결과 줄을 한 줄씩, 그 아래 나머지 열의 강조 줄(합계·가산세)
        for b, cols in summary_rows:
            name = sheet_of[b["sheet"]]
            block = b["heading"] if b["heading"] == name else f"{name} — {b['heading']}"
            main = next((c for _, c in cols if c.get("recommended")), cols[0][1])
            rows_b = [x for x in b["_rows"] if cell_of.get((main["idx"], x["id"])) and cell_label.get((main["idx"], x["id"])) == x["ko"]
                      and not isinstance(x.get("value"), (str, tuple))]
            top = next((x for x in reversed(rows_b) if x.get("key")), rows_b[-1] if rows_b else None)
            first = len(figs)
            for x in rows_b:
                figs.append({"label": f"{block} — {shown(x)}" + (f" ({main['heading']})" if len(cols) > 1 else ""), "ref": cell_of[(main["idx"], x["id"])],
                             "fmt": x["fmt"], "hl": x is top, "note": ""})
            for _, c in cols:
                if c is main or top is None:
                    continue
                y = next((y for y in (c["spec"] or {}).get("rows", []) + (c["spec"] or {}).get("inputs", []) if y["id"] == top["id"]), None)
                ref = cell_of.get((c["idx"], top["id"]))
                if y is not None and ref and cell_label.get((c["idx"], top["id"])) == y["ko"]:
                    figs.append({"label": f"{block} — {shown(y)} ({c['heading']})", "ref": ref, "fmt": y["fmt"], "hl": False, "note": ""})
            if b["summary_note"] and len(figs) > first:
                figs[first]["note"] = b["summary_note"]
    with_note = any(f["note"] for f in figs)
    r = 4
    if figs:
        heads(ws_s, r, list(_t("figs_hdr", en)) + ([_t("figs_note", en)] if with_note else []))
        r += 1
        for f in figs:
            a = as_text(ws_s.cell(r, 1, f["label"]))
            a.font, a.alignment = F(bold=bool(f["hl"])), wrap
            v = ws_s.cell(r, 2, "=" + f["ref"])
            v.font, v.number_format, v.alignment = F(color=GREEN, bold=bool(f["hl"])), f["fmt"], Alignment(vertical="top")
            m = _re.fullmatch(r"'((?:[^']|'')+)'!\$?([A-Z]+)\$?(\d+)", f["ref"])
            w = as_text(ws_s.cell(r, 3, m.group(1).replace("''", "'")))
            w.font, w.alignment = F(size=9, color=GREY, underline="single"), Alignment(vertical="top")
            w.hyperlink = Hyperlink(ref=w.coordinate, location=f"{_q(m.group(1).replace(chr(39) * 2, chr(39)))}!{m.group(2)}{m.group(3)}")
            if f["hl"]:
                a.fill = v.fill = fill(YELLOW)
            if f["note"]:
                nc = as_text(ws_s.cell(r, 4, f["note"]))
                nc.font, nc.alignment = f_sub, wrap
            ws_s.row_dimensions[r].height = 14 * max(lines(f["label"], 62), lines(f["note"], 56, True))
            r += 1
        r += 1
    acts = cfg.get("actions") or []
    if acts:      # 조치·기한 — 받은 글 그대로(도구가 조치나 기한을 만들지 않음)
        band(ws_s, r, _t("actions_line", en, n=len(acts)), 4)
        r += 1
        hdr = list(_t("actions_hdr", en))
        owner = any(str(a["owner"]).strip() for a in acts)      # 담당을 아무도 안 적었으면 그 열 없이 근거를 넓게(C:D)
        heads(ws_s, r, hdr if owner else [hdr[0], hdr[1], hdr[3], ""])
        if not owner:
            ws_s.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
        r += 1
        for a in acts:
            for j, key in enumerate(("action", "due", "owner", "basis") if owner else ("action", "due", "basis"), 1):
                c = as_text(ws_s.cell(r, j, a[key] if _is_num(a[key]) else str(a[key])))
                c.font, c.alignment = F(), wrap
            if not owner:
                ws_s.merge_cells(start_row=r, start_column=3, end_row=r, end_column=4)
            ws_s.row_dimensions[r].height = 14 * max(lines(a["action"], 62), lines(a["due"], 26), lines(a["owner"], 24) if owner else 1,
                                                     lines(a["basis"], 56 if owner else 82))
            r += 1
        r += 1
    if n_iss:
        band(ws_s, r, _t("issues_line", en, n=len(cfg["issues"]), s=n_iss), 4)
        r += 1
        counts: dict[str, int] = {}
        for x in cfg["issues"]:
            if str(x["risk"]).strip():
                counts[str(x["risk"]).strip()] = counts.get(str(x["risk"]).strip(), 0) + 1
        if counts:
            as_text(ws_s.cell(r, 1, " · ".join(f"{k} {v}" for k, v in counts.items()))).font = F()
            r += 1
        r += 1
    support = (_t("support", en) if detail == "full" else _t("support_forms", en, d=n_det, n=n_forms) if detail == "forms" and n_forms
               else _t("support_compact", en, d=n_det))
    # 읽는 사람에게 하는 말만 시트에 둔다(색 범례, 작성자가 넣은 표 표시, 참고 자료 문구). 뒤 시트 구성과 detail 안내는 호출자에게 하는 말이라
    # 시트에 찍지 않고 결과의 시트_안내·서식_안내로만 돌려준다(0.57.0).
    tail = [_t("key", en), _t("disclaimer", en)]
    if n_extra:
        tail.insert(1, _t("extra_key", en, s=", ".join(f"'{n}'" for n in n_extra)))
    for text in tail:
        ws_s.cell(r, 1, text).font = f_sub
        r += 1
    page(ws_s, [64, 26, 26, 58], "A5" if figs else "A4")
    ws_s.page_setup.fitToHeight = 1          # A4 가로 한 쪽
    ws_s.print_area = f"A1:D{r - 1}"

    # ── 쟁점 목록 ──
    if n_iss:
        ws_x = wb.create_sheet(n_iss)
        ws_x.cell(1, 1, _t("issues_title", en)).font = f_title
        ws_x.cell(2, 1, _t("issues_sub", en)).font = f_sub
        with_amount = any(x.get("amount") not in (None, "") for x in cfg["issues"])      # 금액 열 — 준 쟁점이 있을 때만(없으면 기존 표 그대로)
        heads(ws_x, 4, list(_t("issues_hdr", en)) + ([_t("issues_amount", en)] if with_amount else []))
        for k, x in enumerate(cfg["issues"], 5):
            amt = x.get("amount")
            if isinstance(amt, dict):
                try:
                    got = resolve(amt)
                except ValueError as e:
                    raise ValueError(f"issues[{k - 4}].amount — {e}") from None
                c = ws_x.cell(k, 6, "=" + got["ref"] if got["ref"] else got["value"])
                c.font, c.number_format, c.alignment = F(color=GREEN if got["ref"] else GREY), got["fmt"], Alignment(vertical="top")
            elif amt not in (None, ""):
                c = as_text(ws_x.cell(k, 6, amt if _is_num(amt) else str(amt)))
                c.font, c.number_format, c.alignment = F(), NUM if _is_num(amt) else "General", Alignment(vertical="top", horizontal="right")
            for j, key in enumerate(("no", "issue", "finding", "risk", "action"), 1):
                v = x[key]
                c = as_text(ws_x.cell(k, j, v if _is_num(v) else str(v)))      # '='로 시작하는 글이 수식으로 저장되지 않게
                c.font, c.alignment = F(), wrap
            rk = str(x["risk"]).strip().lower()
            if rk in _RISK_FILL:
                ws_x.cell(k, 4).fill = fill(_RISK_FILL[rk])
            ws_x.row_dimensions[k].height = 14 * max(lines(x["issue"], 34), lines(x["finding"], 66), lines(x["action"], 60))
        page(ws_x, [5, 34, 66, 12, 60] + ([20] if with_amount else []), "A5")

    # ── 순서: 요약 → 입력·출처 → 시나리오 시트 → 쟁점 목록 → 기존 시트 ──
    scen = list(dict.fromkeys(sheet_of[b["sheet"]] for b in blocks))
    front = [n_sum, n_inp] + scen + ([n_iss] if n_iss else [])
    guide = {n_sum: _t("g_summary", True, s=n_sum), n_inp: _t("g_inputs", True, s=n_inp), **{n: _t("g_scenario", True, s=n) for n in scen}}
    if n_iss:
        guide[n_iss] = _t("g_issues", True, s=n_iss)
    guide.update({n: _t("g_extra", True, s=n) for n in n_extra})

    # ── 뒤 시트 줄이기: 계산 N·판단·근거 → '계산 상세' 한 장, 서식은 detail='forms'일 때만 ──
    if n_det:
        ws_d = wb.create_sheet(n_det)
        ws_d.cell(1, 1, _t("detail_title", en)).font = f_title
        ws_d.cell(2, 1, _t("detail_sub", en)).font = f_sub
        scen_of = {c["idx"]: sheet_of[b["sheet"]] for b in blocks for c in b["columns"]}
        ws_j = roles.get("jud")
        counts = judgement_counts or {}
        j_ok = ws_j is not None and sum(counts.values()) == ws_j.max_row - 1
        j_at, j_rows = 2, {}
        for i in sorted(counts):
            j_rows[i] = (j_at, j_at + counts[i])
            j_at += counts[i]
        j_map = ((2, 1), (4, 2), (3, 3), (5, 5), (6, 6))          # 판단·근거 시트의 (항목, 금액, 결론, 근거, 이유) 열 → 계산 상세의 열
        moved: dict[str, tuple[str, int]] = {}
        r = 4
        for i in sorted(roles.get("calc") or {}):
            ws_c = roles["calc"][i]
            cd = results[i] if i < len(results) else {}
            band(ws_d, r, _t("detail_band", en, n=i + 1, label=cd.get("label") or f"call {i + 1}", tool=cd.get("tool", "")), 6)
            if i in scen_of:
                as_text(ws_d.cell(r, 3, _t("detail_at", en, s=scen_of[i]))).font = f_sub
            moved[ws_c.title] = (n_det, r)
            r = _stack(ws_d, ws_c, r + 1)
            if j_ok and i in j_rows and j_rows[i][1] > j_rows[i][0]:
                r += 1
                for src_col, dst_col in j_map:
                    h = ws_d.cell(r, dst_col, ws_j.cell(1, src_col).value)
                    h.font, h.fill = F(bold=True), fill(BAND)
                r += 1
                for k in range(*j_rows[i]):
                    for src_col, dst_col in j_map:
                        v = ws_j.cell(k, src_col)
                        d = ws_d.cell(r, dst_col, v.value)
                        d.font, d.number_format = F(), v.number_format
                        d.alignment = wrap if dst_col != 2 else Alignment(vertical="top")
                        if isinstance(v.value, str) and v.value.startswith("="):
                            d.data_type, d.quotePrefix = "s", True
                    ws_d.row_dimensions[r].height = min(160, 14 * max(lines(ws_d.cell(r, 1).value, 34), lines(ws_d.cell(r, 3).value, 60),
                                                                      lines(ws_d.cell(r, 5).value, 44), lines(ws_d.cell(r, 6).value, 40)))
                    r += 1
            r += 1
        if ws_j is not None and not j_ok and ws_j.max_row > 1:      # 줄 수가 맞지 않으면 판단·근거를 통째로 아래에
            band(ws_d, r, ws_j.title, 6)
            r = _stack(ws_d, ws_j, r + 1) + 1
        drop = [ws for ws in list((roles.get("calc") or {}).values()) + [roles.get("jud"), roles.get("list"), roles.get("summary")] if ws is not None]
        ws_in = roles.get("inputs")
        forms = [ws for ws in roles.get("forms") or []]
        keep_inputs = detail == "forms" and bool(forms)
        if detail == "compact":
            drop += forms
        if not keep_inputs and ws_in is not None:
            # 계산 시트의 수식이 '입력·가정'의 이름을 가리키면(드묾) 그 칸도 옮겨 붙인다
            gone = {nm for nm, dn in wb.defined_names.items() if _sheet_of_name(dn) == ws_in.title}
            if gone:
                pat = _re.compile(r"(?<![\w가-힣.])(" + "|".join(_re.escape(n) for n in sorted(gone, key=len, reverse=True)) + r")(?![\w가-힣.])")
                keep_inputs = any(c.data_type == "f" and isinstance(c.value, str) and pat.search(c.value) for row in ws_d.iter_rows() for c in row)
        if ws_in is not None:
            if keep_inputs:
                band(ws_d, r, _t("detail_links", en), 6)
                moved[ws_in.title] = (n_det, r)
                r = _stack(ws_d, ws_in, r + 1) + 1
            drop.append(ws_in)
        drop_names = {ws.title for ws in drop}
        for nm in list(wb.defined_names):
            sh = _sheet_of_name(wb.defined_names[nm])
            if sh in moved:
                wb.defined_names[nm].attr_text = _retarget("=" + wb.defined_names[nm].attr_text, moved)[1:]
            elif sh in drop_names:
                del wb.defined_names[nm]
        for ws in drop:
            wb.remove(ws)
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if c.data_type == "f" and isinstance(c.value, str) and "!" in c.value:
                        nv = _retarget(c.value, moved)
                        if nv != c.value:
                            c.value = nv
        page(ws_d, [34, 20, 60, 16, 44, 40])
        wb._sheets = [wb[n] for n in front] + [ws_d] + [s for s in wb._sheets if s.title not in front and s is not ws_d]
    else:
        wb._sheets = [wb[n] for n in front] + [s for s in wb._sheets if s.title not in front]
    wb.active = 0
    return {"시트": front, "이름_바꿈": ren, "warnings": warnings, "서식_수": n_forms, "안내": guide, "상세": n_det, "시트_안내": support,
            "자유_시트": n_extra, "자유_위치": len(front) - (1 if n_iss else 0), "resolve": resolve}
