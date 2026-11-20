"""문서 색인(docindex)·주석 제목 사전(notecode) — 2026-11-18 감사보고서 788건·사업보고서 56건 전수에서 나온 모양을 지어낸 원문으로 고정. 회사 자료 없음."""
import re

from korean_tax_calc_mcp.engine.kr_comparables import docindex as X
from korean_tax_calc_mcp.engine.kr_comparables import notecode as N
from korean_tax_calc_mcp.engine.kr_comparables import statements as ST

D = N.default()
PAD = "<P>" + "당기말 현재 내역은 다음과 같습니다 " * 30 + "</P>"


def audit(notes_html, fs=""):
    return ("<TITLE>독립된 감사인의 감사보고서</TITLE><P>감사보고서 본문</P><TITLE>(첨부)재 무 제 표</TITLE>" + fs +
            "<TITLE>주석</TITLE>" + notes_html + PAD + "<TITLE>외부감사 실시내용</TITLE><P>1. 감사대상업무</P>")


def nums(ix):
    return [(n["번호"], n["제목"]) for n in ix["주석"]]


def test_lookup_exact_title_is_confirmed():
    r = D.lookup("12. 재고자산")
    assert r == {"코드": ["D826380"], "방법": "같음", "확정": True}


def test_lookup_combined_title_gets_both_codes_as_estimate():
    r = D.lookup("유형자산 및 무형자산")
    assert {"D822100", "D823180"} <= set(r["코드"]) and not r["확정"]


def test_lookup_keyword_safeguard_adds_code():
    assert "D827580" in D.lookup("우발부채와 약정사항의 내용")["코드"]
    assert "K110" in D.lookup("부가가치계산에 필요한 사항제조원가 및 판매비와관리비에 포함된")["코드"]
    assert "D827580" not in D.lookup("임차보증금")["코드"]


def test_title_is_not_cut_inside_a_longer_title():
    assert N.cut_title("금융부채의 유동성위험 관리 방법 및 종류별 만기분석", D)[0].startswith("금융부채의 유동성위험")
    assert N.cut_title("매출, 매출원가 및 판매비와관리비(1) 매출", D)[0] == "매출, 매출원가 및 판매비와관리비"


def test_title_glued_to_body_is_cut():
    assert N.cut_title("재고자산당기말과 전기말 현재 재고자산의 내역은 다음과 같습니다.", D) == ("재고자산", True)
    assert N.cut_title("특수관계자와의 거래(1) 당기말 현재", D)[0] == "특수관계자와의 거래"


def test_notes_split_on_line_break_marks_inside_one_paragraph():
    ix = X.build("t", audit("<P>1. 회사의 개요&cr;&cr;회사는 제조업을 합니다.&cr;2. 중요한 회계정책&cr;(1) 수익&cr;3. 재고자산&cr;내역</P><P>4. 특수관계자</P>"), D)
    assert [n for n, _ in nums(ix)] == [1, 2, 3, 4] and ix["주석 상태"]["나눔"] == "빈틈없음"


def test_heading_in_table_cell_counts_only_when_in_dictionary():
    html = ("<TABLE><TR><TD>1. 회사의 개요</TD></TR></TABLE><P>본문</P><TABLE><TR><TD>2. 급여</TD></TR></TABLE>"
            "<P>2. 중요한 회계정책</P><P>3. 재고자산</P><P>4. 특수관계자</P>")
    assert nums(X.build("t", audit(html), D)) == [(1, "회사의 개요"), (2, "중요한 회계정책"), (3, "재고자산"), (4, "특수관계자")]


def test_sub_numbered_policy_heading_is_not_a_note():
    html = "<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>2.3.5. 재고자산 재고자산은 저가법으로 평가합니다.</P><P>3. 현금및현금성자산</P><P>4. 재고자산</P><P>5. 특수관계자</P>"
    ix = X.build("t", audit(html), D)
    assert [n for n, _ in nums(ix)] == [1, 2, 3, 4, 5]
    assert [n["번호"] for n in ix["주석"] if "주석:D826380" in n["열쇠"]] == [4]


def test_missing_number_is_found_again_between_neighbours():
    html = "<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>3. 재고자산</P><P>질권 설정금액은 990백만원입니다.  4. 가나다라 명세(1) 당기말 현재 내역</P><P>5. 특수관계자</P>"
    ix = X.build("t", audit(html), D)
    assert [n for n, _ in nums(ix)] == [1, 2, 3, 4, 5] and ix["주석"][3]["다시 찾음"]


def test_number_absent_in_source_is_not_a_gap():
    ix = X.build("t", audit("<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>4. 재고자산</P><P>5. 특수관계자</P>"), D)
    assert ix["주석 상태"]["나눔"] == "빈틈없음" and ix["주석 상태"]["원문에 없는 번호"] == [3]


def test_ask_three_states():
    ix = X.build("t", audit("<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>3. 재고자산</P><P>4. 특수관계자</P>"), D)
    assert X.ask(ix, "주석:D826380")["상태"] == "있음" and X.ask(ix, "주석:D826380")["확정"]
    r = X.ask(ix, "주석:D871100")
    assert r["상태"] == "없음" and "빈틈없이" in r["사유"]
    assert X.ask(ix, "절:4. 매출 및 수주상황") == {"상태": "없음", "확정": True, "자리": [], "사유": "감사보고서에는 그 자리가 없음(사업보고서에만 있음)"}
    ix2 = X.build("t", audit("<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>3. 가나다라 명세</P><P>4. 특수관계자</P>"), D)
    r2 = X.ask(ix2, "주석:D871100")
    assert r2["상태"] == "못 찾았을 수 있음" and "가나다라 명세" in r2["사유"]


def test_report_without_notes_says_absent():
    ix = X.build("t", "<TITLE>독립된 감사인의 감사보고서</TITLE><P>의견거절</P><TITLE>(첨부)재 무 제 표</TITLE><TITLE>주석</TITLE><TITLE>외부감사 실시내용</TITLE>", D)
    assert ix["주석 상태"]["나눔"] == "주석 없음" and X.ask(ix, "주석:D818000")["사유"] == "문서에 주석이 없음"


def test_cited_note_number_missing_makes_a_gap():
    fs = "<TABLE><TR><TD>재고자산(주석 3,7)</TD><TD>100</TD></TR></TABLE>"
    html = "<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>3. 재고자산</P><P>4. 특수관계자</P><TABLE><TR><TD>" + "7. 가" * 1 + "</TD></TR></TABLE><P>(주1) 7. 나머지 설명</P>"
    ix = X.build("t", audit(html, fs), D)
    assert 7 in ix["주석 상태"]["가리키는데 없는 번호"] or 7 in [n["번호"] for n in ix["주석"]]


def test_business_report_coded_notes_use_markup_code_and_span_covers_the_note():
    s = ('<TITLE>II. 사업의 내용</TITLE><TITLE>4. 매출 및 수주상황</TITLE><P>판매</P><TITLE>III. 재무에 관한 사항</TITLE>'
         '<TABLE-GROUP ACLASS="{XBRL}NT_C_D818000"><TITLE>주석 37. 특수관계자 (연결)</TITLE><TABLE><TR><TD>연결 매출</TD></TR></TABLE></TABLE-GROUP>'
         '<TABLE-GROUP ACLASS="{XBRL}NT_S_D818005"><TITLE>주석 32. 특수관계자 거래</TITLE><TABLE><TR><TD>별도 매출</TD></TR></TABLE></TABLE-GROUP>'
         '<TITLE>IV. 이사의 경영진단 및 분석의견</TITLE><P>끝</P>')
    ix = X.build("t", s, D)
    assert ix["종류"] == "사업보고서" and X.ask(ix, "절:4. 매출 및 수주상황")["상태"] == "있음"
    hits = X.notes_for(s, ("D818000",), biz=True)
    assert [h[2] for h in hits] == ["주석 32. 특수관계자 거래", "주석 37. 특수관계자 (연결)"]
    assert "별도 매출" in s[hits[0][0]:hits[0][1]] and "연결 매출" not in s[hits[0][0]:hits[0][1]]


def test_find_note_uses_index_and_does_not_run_into_the_next_note():
    s = audit("<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>3. 특수관계자와의 거래</P><P>해당사항 없습니다.</P><P>4. 재고자산</P><TABLE><TR><TD>상품</TD><TD>100</TD></TR></TABLE>")
    sec, t, st = ST.find_note(s, ST.REL, r"특수\s*관계", False)
    assert (t, st) == ("특수관계자와의 거래", "있음") and "재고자산" not in sec
    assert ST.find_note(s, ("D871100",), r"부문", False) == ("", "", "없음")


def test_find_note_falls_back_to_keyword_search_only_when_index_is_unsure():
    s = "<P>감사보고서</P><P>12. 재고자산</P><P>본문</P><P>27. 특수관계자</P><TABLE><TR><TD>x</TD></TR></TABLE><P>28. 우발부채</P>"
    sec, t, st = ST.find_note(s, ST.REL, r"특수\s*관계", False)
    assert t == "특수관계자" and st == "있음" and re.search(r"x", sec)


# ---- 2026-11-18 색인으로 새로 읽힌 특수관계자 표 127개를 Solar가 따로 읽은 값·원문 표와 대조해 나온 모양(숫자는 지어낸 것) ----
def _tr(*cells, tag="TD"):
    return "<TR>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</TR>"


def _rel_note(table_rows, pre="(단위: 천원)"):
    return audit("<P>1. 회사의 개요</P><P>2. 중요한 회계정책</P><P>3. 특수관계자와의 거래</P><P>" + pre + "</P><TABLE>" + "".join(table_rows) + "</TABLE><P>4. 재고자산</P>")


def test_total_row_named_with_suffix_is_not_added_twice():
    s = _rel_note([_tr("구분", "회사명", "매출등", "매입등", tag="TH"), _tr("종속기업", "가나", "100", "10"), _tr("종속기업", "다라", "200", "20"),
                   _tr("전체특수관계자합계", "전체특수관계자합계", "300", "30")])
    assert ST.related_sales(s, False, 1e9)[0] == 300 * 1000 / 1e9
    assert ST.related_purchases(s, False, cogs=1e9)[0] == 30 * 1000 / 1e9


def test_prior_period_end_column_is_not_added():
    s = _rel_note([_tr("특수관계자명칭", "매출등", "매출등", tag="TH"), _tr("특수관계자명칭", "당기말", "전기말", tag="TH"), _tr("가나", "100", "70"), _tr("합계", "100", "70")])
    assert ST.related_sales(s, False, 1e9)[0] == 100 * 1000 / 1e9


def test_company_named_jusikhoesa_is_not_a_share_purchase_and_group_label_is_not_the_kind():
    s = _rel_note([_tr("특수관계자명", "구분", "거래내용", "당기", "전기", tag="TH"), _tr("주식회사가나", "종속기업", "매출등", "100", "90"), _tr("주식회사가나", "종속기업", "매입등", "40", "30"),
                   _tr("주식회사다라", "지분법피투자회사", "매출등", "50", "20"), _tr("주식회사다라", "지분법피투자회사", "매입등", "5", "2")])
    assert ST.related_sales(s, False, 1e9)[0] == 150 * 1000 / 1e9
    assert ST.related_purchases(s, False, cogs=1e9)[0] == 45 * 1000 / 1e9


def test_asset_purchase_row_and_rent_row_under_a_group_label_are_left_out():
    s = _rel_note([_tr("구분", "특수관계자", "거래내용", "거래내용", "당기", "전기", tag="TH"), _tr("관계회사", "가나", "매출거래", "재고자산매각", "500", "0"),
                   _tr("관계회사", "가나", "매출거래", "유형자산매각", "300", "0"), _tr("관계회사", "가나", "매출거래", "임대료수입", "40", "0"),
                   _tr("관계회사", "가나", "매입거래", "재고자산매입", "900", "0")])
    assert ST.related_sales(s, False, 1e9)[0] == 500 * 1000 / 1e9


def test_group_label_with_deung_suffix_is_not_the_kind():
    """'매출등 | 회사 | 기타수익' — 묶음 이름(매출등·매입등)이 아니라 거래 내용 칸으로 판단(2026-11-20: 기타수익·임대수익을 매출로 더하던 모양)."""
    s = _rel_note([_tr("구분", "기업명", "거래내용", "당기", "전기", tag="TH"), _tr("매출등", "가나", "매출", "3", "4"), _tr("매출등", "가나", "기타수익", "150", "15"),
                   _tr("매출등합계", "매출등합계", "매출등합계", "153", "19"), _tr("매입등", "가나", "포장재매입", "200", "180"), _tr("매입등", "다라", "기타비용", "50", "50"),
                   _tr("매입등합계", "매입등합계", "매입등합계", "250", "230")])
    assert ST.related_sales(s, False, 1e9)[0] == 3 * 1000 / 1e9
    assert ST.related_purchases(s, False, cogs=1e9)[0] == 200 * 1000 / 1e9


def test_period_header_with_parenthesised_current_and_prior_reads_current_only():
    """'제50(당)기 | 제49(전)기' 머리글 아래 매출·매입 열 — 당기 열만 더한다(2026-11-20: '당기'·'전기'로 적힌 머리글만 기간으로 알아봐 두 기간을 더하던 모양)."""
    s = _rel_note([_tr("구분", "특수관계자명", "제50(당)기", "제50(당)기", "제50(당)기", "제49(전)기", "제49(전)기", "제49(전)기", tag="TH"),
                   _tr("구분", "특수관계자명", "매출", "기타수익", "매입", "매출", "기타수익", "매입", tag="TH"),
                   _tr("기타", "가나", "780", "350", "7800", "1200", "40", "5900"), _tr("기타", "다라", "3", "28", "1600", "1", "8", "1200"),
                   _tr("합계", "합계", "783", "378", "9400", "1201", "48", "7100")])
    assert ST.related_sales(s, False, 1e9)[0] == 783 * 1000 / 1e9
    assert ST.related_purchases(s, False, cogs=1e9)[0] == 9400 * 1000 / 1e9


def test_period_header_variants_are_recognised():
    for cur, pri in (("(당)기", "(전)기"), ("제50기(당기)", "제49기(전기)"), ("제50(당)기말", "제49(전)기말"), ("당기", "전기")):
        s = _rel_note([_tr("회사명", cur, cur, pri, pri, tag="TH"), _tr("회사명", "매출", "매입", "매출", "매입", tag="TH"),
                       _tr("가나", "100", "40", "70", "30"), _tr("합계", "100", "40", "70", "30")])
        assert ST.related_sales(s, False, 1e9)[0] == 100 * 1000 / 1e9, cur
        assert ST.related_purchases(s, False, cogs=1e9)[0] == 40 * 1000 / 1e9, cur


def test_prior_only_table_with_parenthesised_label_is_not_read():
    s = _rel_note([_tr("회사명", "제49(전)기", "제49(전)기", tag="TH"), _tr("회사명", "매출", "매입", tag="TH"), _tr("가나", "70", "30"), _tr("합계", "70", "30")])
    assert ST.related_sales(s, False, 1e9)[0] is None
