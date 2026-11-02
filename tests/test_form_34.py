"""별지 제34호서식 대손충당금 및 대손금조정명세서 (Claude 2026-11-02).

서식 원문: 법인세법 시행규칙 별지 제34호서식 <개정 2026. 1. 2.> 3쪽 전부 대조. 1쪽만 시트로 만듦.
손계산:
- 받을어음 부도 3,000,000: 손비로 계상할 수 있는 금액은 1천원을 뺀 금액(법인세법 시행령 제19조의2②) → 시인 2,999,000, 부인 1,000.
- ⑱ = 1,000, ⑲ = ㉑ = ① = 1,300,001,000. 실적률 (8,000,000 + 2,999,000) ÷ 1,000,000,000 = 1.0999% → 소수 셋째 자리 절사 1.0%.
- ③ = 1,300,001,000 × 1% = 13,000,010. ⑥ = 42,000,000. ⑦ = 28,999,990.
- ⑬ = 30,000,000 − 0 − 5,000,000 − 8,000,000 − 22,000,000 = △5,000,000 = ⑮ (전기 한도초과 추인).
"""
import openpyxl, pytest, shutil
from test_form_templates import build, c, recalc

SHEET = "별지34 대손충당금·대손금"
ARGS = {"year": 2025, "sme": True, "prior_excess": 5_000_000,
        "book": {"opening": 30_000_000, "offset": 8_000_000, "provision": 20_000_000, "closing": 42_000_000},
        "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_300_000_000,
        "writeoffs": [{"kind": "소멸시효완성", "amount": 8_000_000, "arose_in": "당기", "date": "2025-03-31", "account": "외상매출금", "detail": "가나상사", "booked": "상계"},
                      {"kind": "부도6개월", "amount": 3_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 7, "date": "2025-12-31", "account": "받을어음", "detail": "다라상사", "booked": "손비"}]}


def test_memo_is_disallowed_when_booked_in_full():
    r = c("bad_debt_adjustment", ARGS)
    adj = {x["구분"]: x for x in r["세무조정"]}
    assert adj["대손금 부인(비망가액)"]["금액"] == 1_000 and adj["대손금 부인(비망가액)"]["소득처분"] == "유보"
    assert r["결과"]["손금불산입_합계"] == 29_000_990
    assert r["결과"]["과소환입_과다환입"] == -5_000_000


def test_memo_excluded_amount_keeps_book_as_is():
    # 회사가 1천원을 남기고 처리: 금액 전부 시인, 장부 채권에 1천원이 이미 있어 세법상 채권·세무조정에 더하지 않음
    a = dict(ARGS, writeoffs=[{"kind": "부도6개월", "amount": 10_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 7, "memo_excluded": True}],
             book={"opening": 30_000_000, "offset": 10_000_000, "provision": 22_000_000, "closing": 42_000_000})
    r = c("bad_debt_adjustment", a)
    assert r["계산"]["세법상 당기 대손금"] == 10_000_000 and r["계산"]["세법상 당기말 채권"] == 1_300_000_000
    assert "대손금 부인(비망가액)" not in {x["구분"] for x in r["세무조정"]}


def test_form_rows_from_tool():
    r = c("bad_debt_adjustment", ARGS)
    rows = r["서식_표"]["34_대손금"]
    assert rows[0] == {"일자": "2025-03-31", "계정과목": "외상매출금", "채권명세": "가나상사", "사유": "소멸시효완성", "금액": 8_000_000,
                       "상계_시인": 8_000_000, "상계_부인": 0, "손비_시인": 0, "손비_부인": 0, "비고": ""}
    assert rows[1]["손비_시인"] == 2_999_000 and rows[1]["손비_부인"] == 1_000 and "1천원" in rows[1]["비고"]
    assert r["서식_표"]["34_채권잔액"] == [{"계정과목": "설정대상 채권", "장부가액": 1_300_000_000, "부인누계": 1_000, "설정제외": 0}]


def test_booked_defaults_to_offset_until_used_up():
    a = dict(ARGS); a["writeoffs"] = [dict(x) for x in ARGS["writeoffs"]]
    for w in a["writeoffs"]: w.pop("booked")
    rows = c("bad_debt_adjustment", a)["서식_표"]["34_대손금"]
    assert rows[0]["상계_시인"] == 8_000_000 and rows[1]["손비_시인"] == 2_999_000


def test_offset_mismatch_is_flagged():
    a = dict(ARGS, book=dict(ARGS["book"], offset=9_000_000, closing=41_000_000))
    assert "상계" in str(c("bad_debt_adjustment", a)["판단"])


BASE = dict(year=2025, sme=False, prior_excess=0, book={"opening": 30_000_000, "offset": 10_000_000, "provision": 0, "closing": 20_000_000},
            receivables_prev_end_book=1_000_000_000, receivables_end_book=1_000_000_000)


def _rows(writeoffs):
    return c("bad_debt_adjustment", dict(BASE, writeoffs=writeoffs))["서식_표"]["34_대손금"]


def test_denied_offset_item_shows_in_offset_denied():
    rows = _rows([{"kind": "부도6개월", "amount": 4_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 3, "booked": "상계"},
                  {"kind": "소멸시효완성", "amount": 6_000_000, "arose_in": "당기", "booked": "상계"}])
    assert rows[0]["상계_부인"] == 4_000_000 and rows[0]["상계_시인"] == 0 and rows[0]["비고"]
    assert rows[1]["상계_시인"] == 6_000_000


def test_prior_year_item_is_denied_in_full():
    rows = _rows([{"kind": "소멸시효완성", "amount": 10_000_000, "arose_in": "전기", "booked": "상계"}])
    assert rows[0]["상계_부인"] == 10_000_000 and rows[0]["비고"] == "전기 사유분"


def test_amount_is_split_between_offset_and_expense():
    rows = _rows([{"kind": "소멸시효완성", "amount": 15_000_000, "arose_in": "당기"}])
    assert rows[0]["상계_시인"] == 10_000_000 and rows[0]["손비_시인"] == 5_000_000


def test_memo_follows_where_it_was_booked():
    rows = _rows([{"kind": "부도6개월", "amount": 3_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 7, "booked": "상계"}])
    assert rows[0]["상계_시인"] == 2_999_000 and rows[0]["상계_부인"] == 1_000 and rows[0]["손비_부인"] == 0


def test_every_row_adds_up_and_recognized_matches_tool():
    w = [{"kind": "부도6개월", "amount": 3_000_000, "arose_in": "당기", "instrument": "외상매출금", "months_since_default": 7},
         {"kind": "부도6개월", "amount": 2_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 8, "mortgage": True},
         {"kind": "소멸시효완성", "amount": 8_000_000, "arose_in": "당기"}, {"kind": "회수불능", "amount": 1_000_000, "arose_in": "당기"}]
    r = c("bad_debt_adjustment", dict(BASE, sme=True, writeoffs=w))
    rows = r["서식_표"]["34_대손금"]
    for x in rows:
        assert x["상계_시인"] + x["상계_부인"] + x["손비_시인"] + x["손비_부인"] == x["금액"]
    assert sum(x["상계_시인"] + x["손비_시인"] for x in rows) == r["계산"]["세법상 당기 대손금"]
    assert sum(x["상계_부인"] + x["손비_부인"] for x in rows) == r["결과"]["비망가액_합계"] + 2_000_000


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_form_sheet_values_and_checks(tmp_path):
    path = build(tmp_path, [{"tool": "bad_debt_adjustment", "args": ARGS}])
    ws = recalc(path, tmp_path)[SHEET]
    want = {"B7": 1_300_001_000, "F7": 13_000_010, "G7": 20_000_000, "H7": 22_000_000, "I7": 42_000_000, "J7": 28_999_990,
            "B9": 30_000_000, "C9": 0, "D9": 5_000_000, "E9": 8_000_000, "F9": 22_000_000, "G9": -5_000_000, "H9": 0, "I9": -5_000_000,
            "C16": 1_300_000_000, "D16": 1_000, "E16": 1_300_001_000, "F16": 0, "G16": 1_300_001_000,
            "E26": 11_000_000, "F26": 8_000_000, "G26": 8_000_000, "H26": 0, "I26": 3_000_000, "J26": 2_999_000, "K26": 1_000}
    for addr, v in want.items():
        assert ws[addr].value == v, addr
    assert ws["C7"].value == 0.01 and ws["D7"].value == 0.01
    assert ws["A20"].value == "2025-03-31" and ws["C21"].value == "다라상사"
    checks = [c2.value for row in ws.iter_rows() for c2 in row if c2.value in ("일치", "확인 필요")]
    assert checks and set(checks) == {"일치"}


def test_form_sheet_layout(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": "bad_debt_adjustment", "args": ARGS}]))
    assert SHEET in wb.sheetnames
    ws = wb[SHEET]
    assert ws.print_area and ws["D2"].value == "대손충당금 및 대손금조정명세서"
    assert ws["J7"].value.startswith("=") and ws["G9"].value.startswith("=")
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert {"J7:L7", "I9:L9", "H11:L11", "A26:D26"} <= merged
