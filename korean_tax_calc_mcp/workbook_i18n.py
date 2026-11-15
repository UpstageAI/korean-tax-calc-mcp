"""English rendering of the export_workbook output (lang='en') — 계산 근거 엑셀의 영문 표기.

원칙
- 한국어 워크북을 먼저 그대로 만든 뒤 저장 직전에 이 모듈이 표기만 바꾼다(lang='ko'면 호출하지 않으므로 기존 출력과 같다).
- 번역표는 패키지 안 data/glossary_ko_en.json(docs/glossary_ko_en.md의 사본)이다. 용어집에 없는 국문 라벨은 그대로 두고
  '번역 없음' 목록에 모은다 — 이 서버는 문장을 만들어 내지 않는다(생성형 AI 없음).
- 용어집 비고에 '공식 영문 없음'이나 '확인 필요'가 있는 행은 번역에 쓰지 않는다.
- 법정서식 틀 시트는 한국어 신고 서식이므로 글자를 건드리지 않는다(다른 시트 이름을 가리키는 수식 참조만 새 이름으로 맞춘다).
- 숫자·수식·표시 형식은 그대로다. 도구가 돌려준 문장(판단 근거·주의·한계)은 한국어 그대로 'Notes (Korean original)' 칸에 둔다.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).parent / "data" / "glossary_ko_en.json"
_HANGUL = re.compile(r"[가-힣]")
_UNCERTAIN = "확인 필요"
_NO_OFFICIAL = "공식 영문 없음"     # 영문법령의 해당 조문에 그 용어가 없음을 확인한 행 — 번역에 쓰지 않는다
NOTES_HEADER = "Notes (Korean original)"
UNTRANSLATED_TITLE = "Untranslated labels (번역 없음)"
_HEADER_FILL = "D9E1F2"


# ── 용어집 ────────────────────────────────────────────────────────────────
def parse_glossary_md(text: str) -> list[dict]:
    """docs/glossary_ko_en.md의 표 → [{ko, en, note}] (머리글·구분선 제외)."""
    rows: list[dict] = []
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("국문 용어", "") or set(cells[0]) <= set("-: "):
            continue
        rows.append({"ko": cells[0], "en": cells[1], "note": cells[2] if len(cells) > 2 else ""})
    return rows


def _norm(s: str) -> str:
    """띄어쓰기·밑줄 차이는 같은 용어로 본다('한도 초과액' = '한도초과액' = '한도_초과액')."""
    return re.sub(r"[\s_]+", "", s)


@lru_cache(maxsize=1)
def load_glossary() -> dict[str, str]:
    """번역에 쓰는 {정규화한 국문: English}. '공식 영문 없음'·'확인 필요' 행과 영문이 빈 행은 뺀다."""
    data = json.loads(_DATA.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for row in data["terms"]:
        note = row.get("note") or ""
        if not row.get("en") or _UNCERTAIN in note or _UNCERTAIN in row["en"] or _NO_OFFICIAL in note:
            continue
        out.setdefault(_norm(row["ko"]), row["en"])
    return out


# ── 워크북 틀 문구(세법 용어가 아닌 표 머리글·안내) ────────────────────────────
# 값은 완성된 표기. 세법 용어는 여기 두지 않고 용어집에서 찾는다.
_UI: dict[str, str] = {
    "항목": "Item (항목)", "금액": "Amount (금액)", "값": "Value (값)", "이름": "Name (이름)", "설명": "Description (설명)",
    "단계": "Step (단계)", "수식": "Formula (수식)", "도구 값": "Tool value (도구 값)", "확인": "Check (확인)",
    "구분": "Category (구분)", "조정": "Adjustment (조정)", "세부 항목": "Detail item (세부 항목)",
    "가산 합계": "Additions total (가산 합계)", "차감 합계": "Subtractions total (차감 합계)", "순액": "Net amount (순액)",
    "금액 합계(방향 무관)": "Total amount, either direction (금액 합계)",
    "산식": "Formula in words (산식)", "도구": "Tool (도구)", "오류": "Error (오류)", "안내": "Guidance (안내)",
    "경로": "Path (경로)", "출처": "Source (출처)", "출처(세무조정)": "Source: tax adjustment (출처)",
    "별지50(을) 과목": "Form 50(B) item (별지50(을) 과목)",
    "결론": "Conclusion (결론)", "근거": "Basis (근거)", "이유": "Reason (이유)", "쟁점": "Issue (쟁점)",
    "(판단 항목 없음)": "(No judgement item) (판단 항목 없음)",
    "서식 시트": "Form sheet (서식 시트)", "서식 표기": "Form title / note (서식 표기)", "계산 시트": "Calc sheet (계산 시트)",
    "계산": "Calculation (계산)", "주요 값": "Key values (주요 값)", "번호": "No. (번호)", "과목": "Account (과목)",
    "내용": "Details (내용)", "입력": "Input (입력)",
    "제목": "Title (제목)", "작성일": "Date prepared (작성일)", "call 수": "Number of calls (call 수)",
    "세액 요약": "Tax summary (세액 요약)", "세무조정 항목": "Tax adjustment items (세무조정 항목)",
    "계산 결과 한눈에": "Results at a glance (계산 결과 한눈에)",
    "검토·확인 필요 사항": "Review notes (검토·확인 필요 사항)",
    "결산서상 당기순이익": "Net income per financial statements (결산서상 당기순이익)",
    "같은 서식 여러 call": "Same form, several calls (같은 서식 여러 call)",
    "오류 — 계산 시트 참고": "Error — see the calc sheet (오류)",
    "서식 틀 없음 — 계산 시트 참고": "No form template — see the calc sheet (서식 틀 없음)",
    "입력된 검토 의견 없음 — 각 계산 시트의 주의와 '판단·근거' 시트를 확인":
        "No review notes were entered — see the notes on each calc sheet and the judgements sheet.",
    "이 시트의 금액은 계산 도구 결과를 옮긴 값입니다. 서식 시트의 금액 칸은 수식이고 도구 값과의 대조 칸이 있습니다. 세무 자문이 아니며 신고 전에 세무 전문가와 확인하세요.":
        "Amounts on this sheet are copied from the calculation tool results. Amount cells on the form sheets are formulas with a check column against the tool values. This is not tax advice — confirm with a tax professional before filing.",
    "이 파일은 계산 도구의 결과를 정리한 참고 자료이며 세무 자문이 아닙니다. 판단과 신고는 세무 전문가와 확인하세요.":
        "This file is a reference summary of calculation tool results and is not tax advice. Confirm judgements and filings with a tax professional.",
}

# 시트 이름(31자 이하). 계산 N은 번호를 살린다.
_SHEET_NAMES = {"요약": "Summary (요약)", "목록": "Sheet list (목록)", "입력·가정": "Inputs (입력·가정)",
                "판단·근거": "Judgements (판단·근거)"}
_CALC_RE = re.compile(r"^계산 (\d+)$")

# 수식 안 문자열(확인 칸) — 칸에 보이는 결과 글자
_FORMULA_LITERALS = {'"일치"': '"Match (일치)"', '"확인 필요"': '"Check (확인 필요)"'}

_YES_NO = {"예": "Yes (예)", "아니오": "No (아니오)"}

# 서식 표기 앞의 법령명(법제처 영문법령 제명)
_LAW_EN = (("국제조세조정에 관한 법률", "Adjustment of International Taxes Act"),
           ("상속세 및 증여세법", "Inheritance Tax and Gift Tax Act"),
           ("조세특례제한법", "Restriction of Special Taxation Act"),
           ("부가가치세법", "Value-Added Tax Act"), ("법인세법", "Corporate Tax Act"), ("소득세법", "Income Tax Act"))


def _has_hangul(s: str) -> bool:
    """국문이 섞인 글(사용자가 적은 글·도구 문장)인가 — 그런 칸은 모양을 건드리지 않는다."""
    return bool(_HANGUL.search(s))


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s[:1].islower() else s


class Labels:
    """호출자가 준 라벨 치환 표 {원래 키·라벨: 표시할 글}. 쓰인 키를 적어 두었다가 안 쓰인 키를 warnings로 알린다.
    도구는 글을 지어내지 않는다 — 표에 있는 글만 쓴다."""

    def __init__(self, table: dict[str, str], *, en: bool) -> None:
        self.table = {str(k).strip(): str(v).strip() for k, v in table.items()}
        self.en = en
        self.used: set[str] = set()

    def get(self, key: Any) -> str | None:
        """표시할 글(영문 모드는 '표시 글 (원래 키)' — 원래 키를 잃지 않게). 표에 없으면 None."""
        if not isinstance(key, str):
            return None
        k = key.strip()
        text = self.table.get(k)
        if text is None:
            return None
        self.used.add(k)
        return f"{text} ({k})" if self.en and text != k else text

    def label(self, s: Any) -> Any:
        """국문 모드의 라벨 칸: 전체가 표에 있으면 그 글, 'a.b' 경로는 마디마다."""
        if not isinstance(s, str) or s.startswith("="):
            return s
        hit = self.get(s)
        if hit is not None:
            return hit
        s0 = s.strip()
        if "." in s0 and not re.search(r"\d\.\d|\. ", s0):
            parts = [self.get(p) or p for p in s0.split(".")]
            return ".".join(parts)
        return s

    def unused(self) -> list[str]:
        return [k for k in self.table if k not in self.used]


class Translator:
    """국문 라벨 → 'English (국문)'. 찾지 못한 라벨은 그대로 돌려주고 missing에 모은다.
    custom(호출자가 준 라벨 표)이 있으면 용어집보다 먼저 본다."""

    def __init__(self, custom: "Labels | None" = None) -> None:
        self.terms = load_glossary()
        self.missing: list[str] = []
        self.translated: list[str] = []
        self.custom = custom

    def _lookup(self, s: str) -> str | None:
        if s in _UI:
            return _UI[s]
        en = self.terms.get(_norm(s))
        return f"{_cap(en)} ({s})" if en else None

    def _hit(self, s: str) -> None:
        if s not in self.translated:
            self.translated.append(s)

    def _miss(self, s: str) -> None:
        if s not in self.missing:
            self.missing.append(s)

    def _one(self, s: str) -> str:
        """한 라벨(경로 한 마디)."""
        own = self.custom.get(s) if self.custom else None
        if own is not None:
            self._hit(s)
            return own
        if not _HANGUL.search(s):
            return s
        hit = self._lookup(s)
        if hit:
            self._hit(s)
            return hit
        # 용어집 용어를 '_'·'·'로 이은 키(익금산입_손금불산입) — 마디가 모두 용어집에 있을 때만 잇는다
        parts = [p for p in re.split(r"[_·]", s) if p]
        if len(parts) > 1:
            ens = [self.terms.get(_norm(p)) for p in parts]
            if all(ens):
                self._hit(s)
                return f"{_cap(' / '.join(ens))} ({s})"
        self._miss(s)
        return s

    def label(self, s: Any) -> Any:
        """라벨·결과 키·표 머리글. 'a.b' 경로는 마디마다, '확인 (키)'는 키만 옮긴다."""
        if not isinstance(s, str) or s.startswith("="):
            return s
        if self.custom is not None and s.strip() in self.custom.table:
            return self._one(s.strip())
        if not _HANGUL.search(s):
            return s
        s0 = s.strip()
        if s0 in _UI or _norm(s0) in self.terms:
            return self._one(s0)
        m = re.fullmatch(r"확인 \((.+)\)", s0)
        if m:
            return f"Check (확인): {self._one(m.group(1))}"
        if "." in s0 and not re.search(r"\d\.\d|\. ", s0):
            return ".".join(self._one(p) for p in s0.split("."))
        return self._one(s0)

    def quiet(self, s: Any) -> Any:
        """틀 문구만 바꾼다(없어도 '번역 없음'에 넣지 않음) — 사용자가 쓴 글·시트 이름이 섞이는 칸용."""
        if isinstance(s, str) and s in _UI:
            return _UI[s]
        return s


# ── 워크북 후처리 ──────────────────────────────────────────────────────────
def _is_text(c) -> bool:
    return isinstance(c.value, str) and c.data_type != "f" and c.value != ""


def _is_header(c) -> bool:
    try:
        return c.fill is not None and c.fill.fill_type == "solid" and str(c.fill.fgColor.rgb or "").endswith(_HEADER_FILL)
    except Exception:
        return False


def _copy_style(src, dst) -> None:
    from copy import copy
    dst.font = copy(src.font)
    dst.fill = copy(src.fill)
    dst.alignment = copy(src.alignment)


def _wide(ws, r: int, first_col: int = 1, last_col: int = 7, chars: int = 150) -> None:
    """긴 영문 문장 칸을 옆 칸까지 합쳐 줄바꿈한다(인쇄·PDF에서 잘리지 않게). 이미 합쳐진 칸은 그대로."""
    from openpyxl.styles import Alignment
    c = ws.cell(r, first_col)
    if not isinstance(c.value, str) or any(c.coordinate in m for m in ws.merged_cells.ranges):
        return
    if any(ws.cell(r, j).value is not None for j in range(first_col + 1, last_col + 1)):
        return
    ws.merge_cells(start_row=r, start_column=first_col, end_row=r, end_column=last_col)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    width = sum(2 if _HANGUL.match(ch) else 1 for ch in c.value)      # 한글은 두 칸 너비로 센다
    ws.row_dimensions[r].height = 16 * (width // chars + 1)


def _calc_sheet(ws, T: Translator) -> None:
    """'계산 N' 시트: 머리글·A열 라벨을 옮기고, 항목-값 표의 한국어 문장 값은 C열 'Notes (Korean original)'로."""
    from openpyxl.styles import Alignment
    value_rows = getattr(ws, "_ktc_value_rows", set())   # 세부 표의 자료 행(A열이 값) — _write_detail_blocks가 표시
    state, hdr_row, moved = None, None, False
    for r in range(1, ws.max_row + 1):
        if r in value_rows:
            continue
        a = ws.cell(r, 1)
        if _is_header(a):
            kind = a.value
            for c in ws[r]:
                if _is_text(c) and _is_header(c):
                    c.value = T.label(c.value)
            state, hdr_row = ("kv" if kind in ("항목", "세부 항목") else "other"), r
            continue
        if _is_text(a) and not a.quotePrefix:
            a.value = T.label(a.value)
        if state == "kv":
            b, c3 = ws.cell(r, 2), ws.cell(r, 3)
            if b.value in _YES_NO and b.data_type != "f":
                b.value = _YES_NO[b.value]
            elif _is_text(b) and not b.quotePrefix and _HANGUL.search(b.value) and c3.value is None:
                c3.value, b.value = b.value, None
                c3.alignment = Alignment(wrap_text=True, vertical="top")
                h = ws.cell(hdr_row, 3)
                if h.value is None:
                    h.value = NOTES_HEADER
                    _copy_style(ws.cell(hdr_row, 1), h)
                moved = True
    if moved:
        ws.column_dimensions["C"].width = 70


def apply_labels_ko(wb, labels: Labels) -> None:
    """국문 통합 문서의 '계산 N' 시트: 머리글 줄과 A열 항목 이름을 호출자가 준 글로 바꾼다(값·수식·정의된 이름은 그대로)."""
    for ws in wb.worksheets:
        if not _CALC_RE.match(ws.title):
            continue
        value_rows = getattr(ws, "_ktc_value_rows", set())
        for r in range(1, ws.max_row + 1):
            if r in value_rows:
                continue
            a = ws.cell(r, 1)
            if _is_header(a):
                for c in ws[r]:
                    if _is_text(c) and _is_header(c):
                        c.value = labels.label(c.value)
            elif _is_text(a) and not a.quotePrefix:
                a.value = labels.label(a.value)


def _summary_cells(ws, T: Translator, title: str, layout: str) -> None:
    for row in ws.iter_rows():
        for c in row:
            if not _is_text(c):
                continue
            if _is_header(c):
                c.value = T.label(c.value)
            elif layout == "steps" and c.row >= 5 and c.column >= 3 and c.font is not None and c.font.bold:
                c.value = T.label(c.value)          # steps 요약: 굵은 칸이 결과 키
            elif layout != "steps" and c.column == 1 and _norm(c.value) in T.terms:
                c.value = T.label(c.value)          # 세액 요약의 과세표준·산출세액 등
            else:
                c.value = T.quiet(c.value)
                if layout != "steps" and c.column == 1 and len(c.value) > 60 and not _has_hangul(c.value):
                    _wide(ws, c.row)
    if layout != "steps":
        a1, a2 = ws.cell(1, 1), ws.cell(2, 1)
        from .workbook_blend import as_text       # 제목·회사명이 '='로 시작해도 글 그대로(수식으로 저장하지 않음)
        if isinstance(a1.value, str) and (a1.data_type != "f" or a1.quotePrefix) and a1.value.endswith(" — 요약"):
            a1.value = a1.value[: -len("요약")] + "Summary (요약)"
            as_text(a1)
        if isinstance(a2.value, str) and (a2.data_type != "f" or a2.quotePrefix):
            a2.value = a2.value.replace("단위: 원", "Unit: KRW (단위: 원)")
            as_text(a2)
        for key, en in (("(+) 익금산입·손금불산입", "(+) "), ("(−) 손금산입·익금불산입", "(−) ")):
            for row in ws.iter_rows(min_col=1, max_col=1):
                if row[0].value == key:
                    row[0].value = en + T.label(key[4:])


def _plain_sheet(ws, T: Translator, *, label_col: int | None = None, header_map: dict | None = None) -> None:
    """머리글 줄(색 채움)만 옮기는 시트. label_col을 주면 그 열의 글자도 라벨로 옮긴다."""
    for row in ws.iter_rows():
        for c in row:
            if not _is_text(c):
                continue
            if _is_header(c):
                c.value = (header_map or {}).get(c.value) or T.label(c.value)
            elif label_col is not None and c.column == label_col:
                c.value = T.label(c.value)
            elif c.value.startswith("서식 틀 없음 — ") and c.column == 1:
                c.value = "No form template (서식 틀 없음) — " + c.value.split(" — ", 1)[1]
            else:
                c.value = T.quiet(c.value)


def _rename_sheets(wb, form_sheets: set[str]) -> dict[str, str]:
    """서식 틀이 아닌 시트의 이름을 바꾸고, 그 이름을 가리키는 수식·정의된 이름·안내 글을 맞춘다."""
    ren: dict[str, str] = {}
    for ws in wb.worksheets:
        old = ws.title
        if old in form_sheets:
            continue
        m = _CALC_RE.match(old)
        new = f"Calc {m.group(1)} (계산 {m.group(1)})" if m else _SHEET_NAMES.get(old)
        if new and new not in wb.sheetnames:
            ren[old] = new
    if not ren:
        return ren
    for old, new in ren.items():
        wb[old].title = new
    # 긴 이름부터('계산 12'가 '계산 1'보다 먼저) 바꾼다
    olds = sorted(ren, key=len, reverse=True)
    quoted = re.compile("|".join(re.escape(f"'{o}'") for o in olds))
    bare = re.compile(r"(?<![\w'가-힣·])(" + "|".join(re.escape(o) for o in olds if " " not in o) + r")!")

    def fix_ref(s: str) -> str:
        s = quoted.sub(lambda m: f"'{ren[m.group(0)[1:-1]]}'", s)
        return bare.sub(lambda m: f"'{ren[m.group(1)]}'!", s)

    for dn in wb.defined_names.values():
        if dn.attr_text:
            dn.attr_text = fix_ref(dn.attr_text)
    calc_prefix = re.compile(r"^(계산 \d+)(?= \()")
    new_titles = set(ren.values())
    for ws in wb.worksheets:
        is_form = ws.title not in new_titles
        for row in ws.iter_rows():
            for c in row:
                v = c.value
                if not isinstance(v, str):
                    continue
                if c.data_type == "f":
                    nv = fix_ref(v)
                    if not is_form:
                        for k, lit in _FORMULA_LITERALS.items():
                            nv = nv.replace(k, lit)
                    if nv != v:
                        c.value = nv
                elif not is_form and not c.quotePrefix:
                    if v in ren:
                        c.value = ren[v]
                    else:
                        nv = quoted.sub(lambda m: f"'{ren[m.group(0)[1:-1]]}'", v)
                        nv = calc_prefix.sub(lambda m: ren.get(m.group(1), m.group(1)), nv)
                        if nv != v:
                            c.value = nv
    return ren


def _form_line(sheet: str, form: str) -> str:
    law = next((en for ko, en in _LAW_EN if form.startswith(ko)), None)
    kind = f"statutory form under the {law}" if law else "statutory form"
    return f"Sheet '{sheet}' — {kind}: {form} (Korean filing format, kept in Korean)"


def append_guide(ws, wb, T: Translator, *, form_info: dict[str, str], ren: dict[str, str], results: list[dict],
                 front: dict[str, str] | None = None) -> None:
    """요약 시트 아래: 시트 안내(시트마다 한 줄)와 '번역 없음' 목록. front는 {통합 문서 앞 시트 이름: 안내 한 줄}."""
    from openpyxl.styles import Alignment, Font, PatternFill
    bold, fill = Font(bold=True), PatternFill("solid", fgColor=_HEADER_FILL)
    back = {v: k for k, v in ren.items()}
    r = ws.max_row + 2
    ws.cell(r, 1, "About this workbook (English view)").font = bold
    r += 1
    for line in (
        "Labels are shown as 'English (Korean original)', using the server glossary (docs/glossary_ko_en.md). Numbers, formulas and number formats are the same as in the Korean workbook.",
        f"Free-text notes returned by the tools (basis, cautions, limitations) are not machine-translated: they stay in Korean under '{NOTES_HEADER}'. Review notes are shown as entered.",
        "Statutory form sheets are Korean filing forms and are kept in Korean.",
    ):
        ws.cell(r, 1, line)
        _wide(ws, r)
        r += 1
    r += 1
    ws.cell(r, 1, "Sheets in this workbook").font = bold
    r += 1
    for j, h in enumerate(("No.", "Sheet", "What it contains", "", "", "", ""), 1):
        c = ws.cell(r, j, h or None)
        c.font, c.fill = bold, fill
    r += 1
    for n, sh in enumerate(wb.worksheets, 1):
        name, old = sh.title, back.get(sh.title, sh.title)
        m = _CALC_RE.match(old)
        if front and name in front:
            text = front[name]
        elif name in form_info:
            text = _form_line(name, form_info[name])
        elif m:
            cd = results[int(m.group(1)) - 1] if int(m.group(1)) <= len(results) else {}
            text = (f"Sheet '{name}' — calculation workings for call {m.group(1)} "
                    f"(tool {cd.get('tool', '')}; label as entered: {cd.get('label', '')}): inputs, formula steps with a check column, result keys")
        elif old == "요약":
            text = f"Sheet '{name}' — this sheet: key results per call, review notes, sheet guide and untranslated labels"
        elif old == "목록":
            text = f"Sheet '{name}' — index of statutory form sheets and which call fills which sheet (form names in Korean)"
        elif old == "입력·가정":
            text = f"Sheet '{name}' — inputs passed to each tool call and the named cells the formulas refer to"
        elif old == "판단·근거":
            text = f"Sheet '{name}' — judgements, statutory basis and reasons per call ({NOTES_HEADER})"
        else:
            text = f"Sheet '{name}'"
        ws.cell(r, 1, n)
        ws.cell(r, 2, name)
        ws.cell(r, 3, text)
        _wide(ws, r, 3, 7, chars=115)
        r += 1
    r += 1
    ws.cell(r, 1, UNTRANSLATED_TITLE).font = bold
    r += 1
    if T.missing:
        ws.cell(r, 1, "Korean labels with no glossary entry are left as they are (no translation is invented). Add them to docs/glossary_ko_en.md to have them translated.")
        _wide(ws, r)
        r += 1
        for j, h in enumerate(("No.", "Label (Korean)"), 1):
            c = ws.cell(r, j, h)
            c.font, c.fill = bold, fill
        r += 1
        for n, s in enumerate(T.missing, 1):
            ws.cell(r, 1, n)
            ws.cell(r, 2, s).alignment = Alignment(wrap_text=False)
            r += 1
    else:
        ws.cell(r, 1, "None — every label on the non-form sheets has a glossary entry.")
    ws.column_dimensions["B"].width = max(ws.column_dimensions["B"].width or 0, 34)   # 시트 이름(31자까지)이 잘리지 않게
    # 요약 시트는 가로 한 쪽 너비에 맞춰 인쇄(긴 영문 줄이 쪽 경계에서 잘리지 않게) — 칸 값·표시 형식과 무관
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def apply_english(wb, T: Translator, *, layout: str, title: str, form_info: dict[str, str], results: list[dict],
                  guide: bool = True) -> dict[str, str]:
    """완성된 한국어 워크북을 영문 표기로 바꾼다. 돌려주는 값: {옛 시트 이름: 새 시트 이름}.

    form_info는 {서식 틀 시트 이름: 서식 표기}. 그 시트의 글자는 바꾸지 않는다.
    """
    form_sheets = set(form_info)
    for ws in wb.worksheets:
        name = ws.title
        if name in form_sheets:
            continue
        if name == "요약":
            _summary_cells(ws, T, title, layout)
        elif _CALC_RE.match(name):
            _calc_sheet(ws, T)
        elif name == "판단·근거":
            _plain_sheet(ws, T, label_col=2, header_map={
                "결론": f"{NOTES_HEADER} — conclusion (결론)", "근거": f"{NOTES_HEADER} — basis (근거)",
                "이유": f"{NOTES_HEADER} — reason (이유)"})
        elif name in ("목록", "입력·가정"):
            _plain_sheet(ws, T)
    ren = _rename_sheets(wb, form_sheets)
    summary = next((wb[n] for o, n in ren.items() if o == "요약"), None) or (wb["요약"] if "요약" in wb.sheetnames else None)
    if summary is not None and guide:      # guide=False: 통합 문서가 앞 시트를 더한 뒤에 append_guide를 부름
        append_guide(summary, wb, T, form_info=form_info, ren=ren, results=results)
    return ren


if __name__ == "__main__":   # 용어집 사본 다시 만들기: python -m korean_tax_calc_mcp.workbook_i18n docs/glossary_ko_en.md
    import sys
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/glossary_ko_en.md")
    rows = parse_glossary_md(src.read_text(encoding="utf-8"))
    _DATA.write_text(json.dumps({"source": "docs/glossary_ko_en.md", "terms": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} rows -> {_DATA}")
