"""lang='en'일 때 export_workbook·verify_workbook 결과 JSON의 키와 고정 문구를 영어로 (0.59.1).

계산 도구 결과(금액)는 건드리지 않는다. 바꾸는 것은 두 도구가 만드는 결과 틀의 키와, 도구가 정해 둔 고정 문구뿐이다.
- 키: KEY_EN 표에 있는 키만 바꾼다. 값이 숫자(건수)일 때와 목록일 때 이름이 다른 키는 COUNT_EN을 먼저 본다.
- 값: VALUE_EN 표에 있는 고정 문구는 영어로. '국문 — English'처럼 영어 문장이 함께 든 안내는 영어 부분만 남긴다.
- 사용자가 넣은 글(시트 이름, 라벨, 항목 이름)과 용어집에 없어 국문 그대로 둔 라벨(번역_없음 목록)은 그대로 둔다.
"""
from __future__ import annotations

import re

KEY_EN = {
    # 공통
    "결과": "result", "근거": "basis", "한계": "limits", "안내": "note", "주의": "caution", "문제": "problems",
    "허용값": "allowed_values", "필요 입력": "required_inputs",
    # export_workbook
    "파일": "file", "파일_안내": "file_note", "call_수": "call_count", "오류_call": "failed_calls",
    "시트_안내": "sheet_note", "서식_안내": "form_note", "통합_시트": "combined_sheets",
    "자유_시트": "free_sheets", "자유_시트_안내": "free_sheet_note", "머리_행": "header_row", "첫_행": "first_row",
    "끝_행": "last_row", "열": "columns", "합계_행": "total_row",
    "labels_적용": "labels_applied", "번역_라벨_수": "translated_label_count", "번역_없음": "untranslated",
    "번역_없음_안내": "untranslated_note",
    # verify_workbook
    "요약": "summary", "대조": "checks", "일치": "matched", "불일치": "mismatches", "읽지_못함": "unreadable",
    "도구_오류": "tool_error", "자동_일치": "auto_matched", "자동_불일치": "auto_mismatched",
    "대조_안_한_금액": "unchecked_amounts", "대조_안_한_금액_시트별": "unchecked_amounts_by_sheet",
    "대조_안_한_금액_더": "unchecked_amounts_more", "자동_대조_더": "auto_checks_more",
    "읽지_못함·도구_오류": "unreadable_or_tool_error", "부가_점검": "extra_checks",
    "저장된_값_없는_수식_칸": "formula_cells_without_stored_value",
    "저장된_값과_다시_계산한_값이_다른_칸": "cells_where_stored_and_recalculated_values_differ",
    "원_미만_소수_금액_칸": "amount_cells_with_fractions_below_one_won", "오류_칸": "error_cells",
    "수식_열에_직접_적은_숫자": "numbers_typed_into_formula_columns", "값을_계산하지_못한_수식_칸": "formula_cells_not_evaluated",
    "다음": "next_step", "사본": "copy", "사본_안내": "copy_note", "자동_대조_안내": "auto_check_note",
    "칸": "cell", "항목": "item", "방식": "method", "도구": "tool", "호출": "call", "키": "key",
    "통합_문서_값": "workbook_value", "도구_값": "tool_value", "차이": "difference", "판정": "verdict",
    "후보": "candidates", "같은_값_키": "same_value_keys", "알림": "notice", "값": "value",
}
# 값이 건수(숫자)일 때의 이름 — 같은 키가 목록이면 KEY_EN
COUNT_EN = {"대조": "checked", "불일치": "mismatched", "도구_오류": "tool_errors"}
# 아래 키의 값은 사용자 글이 키인 dict(시트 이름 → 칸 수 등) — 그 안의 키는 바꾸지 않는다
_KEEP_CHILD_KEYS = frozenset({"대조_안_한_금액_시트별", "detail", "labels_적용", "번역_없음"})

VALUE_EN = {
    "계산 도구 결과 정리(세무 자문 아님)": "Summary of calculation tool results (not tax advice)",
    "통합 문서의 칸 값과 계산 도구 결과 대조(세무 자문 아님)": "Workbook cell values checked against calculation tool results (not tax advice)",
    "일치": "match", "불일치": "mismatch", "읽지 못함": "unreadable", "도구 오류": "tool error",
    "자동(값 일치)": "auto (value match)", "명시": "explicit",
    "대조한 칸은 모두 일치, 대조를 거치지 않은 금액 없음": "All checked cells match; no amount left unchecked",
    "불일치 칸을 고쳐 저장한 뒤 다시 호출": "Fix the mismatched cells, save, and call again",
    "읽지 못한 칸·도구 오류는 cell·call(또는 tool+args)·key를 확인해 다시 호출":
        "For unreadable cells and tool errors, check cell, call (or tool+args) and key, then call again",
    "자동(값 일치)으로 맞춘 칸은 우연히 같은 숫자일 수 있음 — 중요한 칸은 {cell, call}로 명시":
        "Cells matched automatically (by value) may match by coincidence — name important cells explicitly with {cell, call}",
    "대조 안 한 금액은 해당 계산 도구를 호출해 checks에 더하거나, 사용자에게 '계산 도구 검증 없음'으로 밝힘":
        "For unchecked amounts, call the calculation tool and add them to checks, or tell the user they were not verified by a calculation tool",
    "보관된 도구 호출 기록 없음 — 계산 도구를 먼저 호출하거나 tool+args를 적음":
        "No stored tool call record — call the calculation tool first or give tool+args",
    "칸 값이 숫자가 아님 — 자동 대조는 숫자 칸만(call과 key를 적음)": "The cell value is not a number — auto check covers number cells only (give call and key)",
    "칸 값이 숫자가 아님 — key를 적음": "The cell value is not a number — give key",
    "결과에 숫자 값이 없음": "The result has no numeric value",
    "이 호출 결과에 같은 값의 키가 없음 — 가장 가까운 키와 차이": "No key in this call result has the same value — difference from the closest key",
    # verify_workbook LIMITS
    "금액 판정은 값이 1,000 이상인 숫자 칸(날짜·비율 서식 제외)이라는 단순한 기준 — 1,000 미만 금액과 글로 적은 금액은 보지 않음":
        "An amount cell is simply a number cell of 1,000 or more (date and percentage formats excluded) — amounts under 1,000 and amounts written as text are not examined",
    "대조를 거친 것으로 보는 범위는 수식의 모양으로 정함(일치한 칸, 그 칸이 가리키는 칸, 입력 숫자, 그런 칸들의 링크·합·차) — 곱셈·반올림이 든 수식 칸은 따로 대조해야 함":
        "What counts as checked is decided by formula shape (matched cells, cells they point to, input numbers, and links, sums and differences of those) — formula cells with multiplication or rounding need their own check",
    "입력 숫자(수식이 아닌 칸)가 원자료와 맞는지는 보지 않음": "Whether input numbers (non-formula cells) match the source records is not examined",
    "저장된 값이 있는 칸은 그 값을 읽음 — 수식을 고친 뒤 다시 계산하지 않고 저장한 파일은 '저장된 값과 다시 계산한 값이 다른 칸'에 나타남":
        "Cells with a stored value are read as stored — a file saved after editing formulas without recalculating shows up under cells_where_stored_and_recalculated_values_differ",
    "호출_id(call)는 서버 프로세스 안에서만 살아 있음(최근 호출 수백 건) — 서버를 다시 시작했거나 오래된 호출은 tool+args로 대조":
        "Call ids (call) live only inside the server process (the last few hundred calls) — after a restart or for old calls, check with tool+args",
    "자동(값 일치) 대조는 보관된 호출 결과에서 같은 숫자를 찾는 것 — 우연히 같은 숫자일 수 있어 명시 대조와 따로 세고, 입력을 그대로 되돌려준 값은 뺌":
        "Auto (value match) checks look for the same number in stored call results — it may match by coincidence, so it is counted apart from explicit checks, and echoed inputs are left out",
    "사본은 openpyxl로 다시 쓰므로 차트·그림·매크로 같은 요소는 원본과 다를 수 있음(칸의 값·수식·서식은 그대로)":
        "The copy is rewritten with openpyxl, so charts, pictures and macros may differ from the original (cell values, formulas and formats are kept)",
}

_HANGUL = re.compile(r"[가-힣]")
# '국문 안내. English sentence…' / '국문 안내 — English sentence…'에서 영어 문장이 시작하는 자리
_EN_START = re.compile(r"(?:(?<=\. )|(?<=— )|(?<=\.\s))(?=[A-Z][A-Za-z'’,() -]{12,})")


def _english_part(s: str) -> str:
    """영어 문장이 함께 든 안내에서 영어 부분만. 영어 부분이 없거나 그 뒤에도 국문이 많으면 원문 그대로."""
    for m in _EN_START.finditer(s):
        tail = s[m.start():].strip()
        bare = re.sub(r"\([^)]*\)|\{[^}]*\}|'[^']*'", "", tail)
        if bare and len(_HANGUL.findall(bare)) <= max(2, len(bare) // 50):
            return tail
    return s


def english_value(v):
    if isinstance(v, str):
        if v in VALUE_EN:
            return VALUE_EN[v]
        if " / " in v and all(p in VALUE_EN for p in v.split(" / ")):
            return " / ".join(VALUE_EN[p] for p in v.split(" / "))
        return _english_part(v) if _HANGUL.search(v) else v
    return v


def english_result(obj, _parent: str = ""):
    """결과 dict의 키(표에 있는 것)와 고정 문구를 영어로 바꾼 사본."""
    if isinstance(obj, dict):
        if _parent in _KEEP_CHILD_KEYS:
            return obj
        out = {}
        for k, v in obj.items():
            ks = str(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool) and ks in COUNT_EN:
                nk = COUNT_EN[ks]
            elif ks == "시트":
                nk = "sheets" if isinstance(v, list) else "sheet"
            else:
                nk = KEY_EN.get(ks, k)
            out[nk] = v if ks in _KEEP_CHILD_KEYS else english_result(v, ks)
        return out
    if isinstance(obj, list):
        return [english_result(v, _parent) for v in obj]
    if _parent in ("판정", "방식", "근거", "다음", "한계", "도구_오류", "알림", "파일_안내", "사본_안내", "번역_없음_안내",
                   "자동_대조_안내", "자유_시트_안내", "안내"):
        return english_value(obj)
    return obj
