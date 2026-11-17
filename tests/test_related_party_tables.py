"""특수관계자 거래 주석 표 읽기 — 가로형·세로형(당기/전기)·회사별 열+계·단위 표기 섞임·'거래 없음' 문장.
표 모양과 숫자는 2025년 공시 감사보고서·사업보고서 원문(화장품·화학 업종) 그대로. Claude 작성(2026-11-17)."""
import pytest

from korean_tax_calc_mcp.engine.kr_comparables import statements as ST


def _tr(*cells, th=False):
    tag = "TH" if th else "TD"
    return "<TR>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</TR>"


def _doc(title_no, title, tables, after="(4) 당기 중 발생한 특수관계자와의 자금거래 내역은 없습니다."):
    body = "".join(f"<P>{unit}</P><TABLE>{''.join(rows)}</TABLE>" for unit, rows in tables)
    return f"<P>{title_no}. {title}</P>{body}<P>{after}</P><P>{title_no + 1}. 유형자산</P>"


LONG_KOSE = [_tr("특수관계구분", "특수관계자명", "거래내용", "당 기", "전 기", th=True),
             _tr("지배회사", "KOSE CO., LTD.", "상품매입", "9,392,071", "17,030,137"),
             _tr("기타매입", "158,759", "64,254"), _tr("기타수익", "464", "91,945"), _tr("배당금 지급", "3,090,555", "21,932,671")]


def test_long_table_takes_current_year_and_skips_merged_cells():
    """세로형(거래 종류 행 × 당기·전기). 앞 두 칸이 병합되어 둘째 행부터 칸이 밀려도 당기 금액만 — 종전엔 전기·배당금을 더해 234%."""
    s = _doc(3, "특수관계자와의 주요거래", [("(단위:천원)", LONG_KOSE)])
    r, why = ST.related_purchases(s, False, cogs=9_437_000_000)
    assert r == pytest.approx((9_392_071 + 158_759) * 1000 / 9_437_000_000)
    assert "거래 종류 행" in why


def test_header_detected_only_in_header_rows():
    """첫 데이터 행의 '상품매입' 글자를 열 제목으로 잡지 않음."""
    trs = [r[4:-5] for r in LONG_KOSE]
    assert ST._header_col(trs, ST.PURCHASE_HDR) is None


def test_long_table_sales_with_operating_revenue_rows():
    rows = [_tr("구분", "특수관계자명", "거래내용", "당기", "전기", th=True),
            _tr("종속기업", "Baram Italia S.R.L", "영업수익", "722,356", "519,512"), _tr("BARAM USA INC", "영업수익", "339,749", "239,058"),
            _tr("DEAR DAHLIA TAIWAN LIMITED", "영업수익", "414,321", "124,844"), _tr("위다이브 주식회사", "영업비용", "1,184,474", "61,859"),
            _tr("영업외수익", "909,091", "-")]
    s = _doc(6, "특수관계자", [("(단위: 천원)", rows)])
    r, _ = ST.related_sales(s, False, revenue=20_000_000_000)
    assert r == pytest.approx((722_356 + 339_749 + 414_321) * 1000 / 20_000_000_000)   # 영업외수익·영업비용 제외


def test_party_columns_with_total_column():
    rows = [_tr("구분", "BMK-YT", "BMK-SC", "BMK-F&B", "주주임원", "계", th=True),
            _tr("상품매출", "0", "87,450", "14,412", "0", "101,862"), _tr("임대수입", "100,802", "0", "0", "0", "100,802"),
            _tr("임차료", "0", "0", "0", "100,000", "100,000")]
    s = _doc(20, "특수관계자와의 거래", [("(단위:천원)", rows)])
    r, _ = ST.related_sales(s, False, revenue=11_000_000_000)
    assert r == pytest.approx(101_862 * 1000 / 11_000_000_000)


def test_unit_label_mismatch_goes_to_human():
    """거래 표는 '(단위 : 원)'인데 같은 절의 채권·채무 표는 천원 — 원문 단위 표기 오류일 수 있어 숫자를 내지 않음."""
    tx = [_tr("특수관계구분", "특수관계자명", "거래내용", "거래금액", th=True), _tr("당기", "전기", th=True),
          _tr("관계기업", "㈜메이포레", "제품매출", "2,020,988", "885,628"), _tr("관계기업", "㈜메이포레", "상품매입", "2,808", "5,392")]
    bal = [_tr("특수관계구분", "특수관계자명", "매출채권", "기타채권", "매입채무", "기타채무", th=True),
           _tr("관계기업", "㈜메이포레", "4,321,191", "2,655", "-", "30,000")]
    bal2 = [_tr("특수관계구분", "특수관계자명", "매출채권", "기타채권", "매입채무", "기타채무", th=True),
            _tr("관계기업", "㈜메이포레", "3,215,553", "7,572", "-", "30,000")]
    s = _doc(17, "특수관계자의 명칭과 주요거래내용", [("(단위 : 원)", tx), ("(단위:천원)", bal), ("(단위:천원)", bal2)])
    assert ST.related_purchases(s, False, cogs=16_723_814_580) == (None, "주석 표마다 단위 표기가 다름(원·천원 등) — 사람 확인")
    assert ST.related_sales(s, False, revenue=24_536_745_670)[0] is None


def test_other_no_transaction_sentences_do_not_mean_zero():
    """'자금거래 내역은 없습니다'는 특수관계자 거래가 없다는 뜻이 아님."""
    s = _doc(6, "특수관계자", [("(단위: 천원)", [_tr("구분", "특수관계자명", th=True), _tr("종속기업", "X")])])
    assert ST.related_sales(s, False, revenue=1)[0] is None
    s2 = _doc(6, "특수관계자", [], after="당기와 전기 중 특수관계자와의 거래 내역은 없습니다.")
    assert ST.related_sales(s2, False, revenue=1) == (0.0, "특수관계자 거래 없음 문장")
    assert ST.related_purchases(s2, False, cogs=1) == (0.0, "특수관계자 거래 없음 문장")


def test_wide_table_unchanged():
    rows = [_tr("구분", "회사명", "매출", "매입", th=True), _tr("종속기업", "A", "1,000", "200"), _tr("관계기업", "B", "500", "300"), _tr("합계", "", "1,500", "500")]
    s = _doc(12, "특수관계자 거래", [("(단위:백만원)", rows)])
    assert ST.related_sales(s, False, revenue=15_000_000_000)[0] == pytest.approx(0.1)
    assert ST.related_purchases(s, False, cogs=10_000_000_000)[0] == pytest.approx(0.05)


# ---- 주석 제목 뒤에 본문이 붙은 원문(2026-11-17 화장품 업종 72개 중 '특수관계자 절 못 찾음' 18개 대부분) ----
GLUED = [
    ("특수관계자와의 거래27-1. 당기말과 전기말 현재 당사의 특수관계자 현황은 다음과 같습니다", "특수관계자와의 거래"),
    ("특수관계자(1) 당기말 및 전기말 현재 당사의 특수관계자 등의 현황은 다음과 같습니다.", "특수관계자"),
    ("특수관계자 공시22.1 지배ㆍ종속기업간의 특수관계보고기간종료일 현재 당사와 특수관계에 있는", "특수관계자 공시"),
    ("특수관계자와의 거래36.1  보고기간말 현재 당사의 특수관계자 내역은 다음과 같습니다.", "특수관계자와의 거래"),
    ("특수관계자 (1)  당기말 현재 당사의 지배기업은 (주)", "특수관계자"),
]


@pytest.mark.parametrize("raw,title", GLUED)
def test_glued_heading_title_is_cut_before_body(raw, title):
    assert ST._heading_title(raw) == title
    s = f"<P>12. 재고자산</P><P>본문</P><P>27. {raw}</P><TABLE><TR><TD>x</TD></TR></TABLE><P>28. 우발부채</P>"
    sec, t = ST.find_section(s, r"특수\s*관계", False)
    assert t == title and sec.startswith(">27.") and "우발부채" not in sec


def test_sub_item_sentence_is_not_a_heading():
    """'36. 2 당기와 전기 중 특수관계자와의 거래 내역은…'(하위 항목 36.2)을 절 제목으로 잡지 않음."""
    s = "<P>36. 2 당기와 전기 중 특수관계자와의 거래 내역은 다음과 같습니다.</P><P>37. 특수관계자</P><P>본문</P><P>38. 기타</P>"
    sec, t = ST.find_section(s, r"특수\s*관계", False)
    assert t == "특수관계자" and sec.startswith(">37.")


def test_long_sentence_mentioning_keyword_is_not_a_heading():
    s = "<P>1. 회사는 특수관계자와의 거래에 대하여 이사회의 승인을 받도록 정관에 정하고 있으며 그 내역은 주석에 기재하였습니다</P>"
    assert ST.find_section(s, r"특수\s*관계", False) == ("", "")


# ---- 2026-11-17 전수 대조(화장품 74개·도매 47개, 도구 값 ↔ Solar가 따로 읽은 값 ↔ 원문)에서 나온 표 모양. 숫자는 원문 그대로 ----
def c(text, cs=1, rs=1, th=False):
    tag = "TH" if th else "TD"
    return f'<{tag}' + (f' COLSPAN="{cs}"' if cs > 1 else "") + (f' ROWSPAN="{rs}"' if rs > 1 else "") + f'>{text}</{tag}>'


def row(*cells):
    return "<TR>" + "".join(x if x.startswith("<T") else c(x) for x in cells) + "</TR>"


def test_two_row_header_and_balance_table_first():
    """머리글 두 줄(특수관계자 | 당기 3칸 | 전기 3칸 / 상품매출·기타매출·판매수수료)과 그 앞의 채권 표('매출채권').
    종전: 채권 표의 '매출채권'을 매출 열로 잡고 열이 한 칸 밀려 0%."""
    bal = [row(c("특수관계자", rs=2), c("당기말", cs=3), c("전기말", cs=3)), row("매출채권", "선수금", "보증금", "매출채권", "선수금", "보증금"),
           row("한국주철관공업㈜", "224,711", "6,458", "100,000", "397,426", "26,667", "120,000")]
    tx = [row(c("특수관계자", rs=2), c("당기", cs=3), c("전기", cs=3)), row("상품매출", "기타매출", "판매수수료", "상품매출", "기타매출", "판매수수료"),
          row("한국주철관공업㈜", "5,130,758", "20,208", "2,320,562", "6,088,525", "31,875", "2,412,152")]
    s = _doc(22, "특수관계자 공시", [("(단위:천원)", bal), ("(단위:천원)", tx)])
    r, why = ST.related_sales(s, False, revenue=60_000_000_000)
    assert r == pytest.approx((5_130_758 + 20_208) * 1000 / 60_000_000_000) and "상품매출+기타매출" in why


def test_three_row_header_sales_and_purchases():
    rows = [row(c("특수관계자명", rs=3), c("당기", cs=4)), row(c("매출등", cs=2), c("매입등", cs=2)), row("매출", "기타", "매입", "기타"),
            row("콜마홀딩스(주)", "-", "-", "-", "102,864"), row("한국콜마(주)", "11,560,213", "-", "1,838,126", "10,053"),
            row("콜마스크(주)", "1,363,833", "-", "-", "-"), row("에치엔지(주)", "433,895", "-", "4,515", "-"),
            row("(주)연우", "-", "-", "14,820", "-"), row("콜마비앤에이치(주)", "-", "-", "5,780", "-"), row("합계", "13,357,941", "-", "1,863,241", "112,917")]
    s = _doc(27, "특수관계자와의 거래", [("(단위 : 천원)", rows)])
    assert ST.related_sales(s, False, revenue=100_000_000_000)[0] == pytest.approx(13_357_941_000 / 100_000_000_000)
    assert ST.related_purchases(s, False, cogs=80_000_000_000)[0] == pytest.approx(1_863_241_000 / 80_000_000_000)


def test_long_table_does_not_add_total_rows():
    """세로형 표 아래 '합계 | 합계 | 매출등' 행까지 더해 두 배가 되던 것."""
    rows = [_tr("특수관계구분", "특수관계자명", "거래내용", "당기", "전기", th=True),
            _tr("관계기업", "아시아첨가제(주)", "매출", "93,664", "92,560"), _tr("관계기업", "아시아첨가제(주)", "매입", "14,128,094", "20,917,155"),
            _tr("기타특수관계자", "미성통상(주)", "매출", "3,133,180", "2,842,134"),
            _tr("합계", "합계", "매출등", "3,226,844", "2,934,694"), _tr("합계", "합계", "매입등", "14,128,094", "20,917,155")]
    s = _doc(30, "특수관계자", [("(단위:천원)", rows)])
    assert ST.related_sales(s, False, revenue=400_000_000_000)[0] == pytest.approx(3_226_844_000 / 400_000_000_000)
    assert ST.related_purchases(s, False, cogs=300_000_000_000)[0] == pytest.approx(14_128_094_000 / 300_000_000_000)


def test_long_table_merged_account_cell():
    """과목 칸이 세로로 병합(상품매출 3행) — 종전: 첫 행만 읽음."""
    rows = [row("과목", "구분", "당기", "전기"), row(c("상품매출", rs=3), "BMK-LTD", "53,624", "129,093"), row("BMK-SC", "313,789", "134,416"),
            row("BMK-F&B", "21,645", "1,708"), row("임대수익", "BMK-SC", "76,000", "0"), row(c("이자수익", rs=2), "BMK-LTD", "75,000", "0"), row("BMK-SC", "5,500", "0")]
    s = _doc(10, "특수관계자와의 거래", [("(단위 : 천원)", rows)])
    assert ST.related_sales(s, False, revenue=30_000_000_000)[0] == pytest.approx((53_624 + 313_789 + 21_645) * 1000 / 30_000_000_000)


def test_prior_year_table_is_not_used_when_current_has_no_column():
    """당기 표에 매입 열이 없는데 '② 전기' 표의 매입을 가져오던 것 — 값을 내지 않는다."""
    cur = [row("구분", "특수관계자명", "매출", "기타수익", "기타비용"), row("종속기업", "A", "195,291", "36,771", "-"), row("합계", "합계", "195,291", "36,771", "-")]
    pri = [row("구분", "특수관계자명", "매출", "매입", "기타비용"), row("종속기업", "A", "269,218", "55,008", "25,273"), row("합계", "합계", "269,218", "55,008", "25,273")]
    s = _doc(34, "특수관계자", [("① 당기 (단위:천원)", cur), ("② 전기 (단위:천원)", pri)])
    assert ST.related_sales(s, False, revenue=10_000_000_000)[0] == pytest.approx(195_291_000 / 10_000_000_000)
    assert ST.related_purchases(s, False, cogs=5_000_000_000) == (None, "매입 열 못 찾음")


def test_two_total_blocks_in_one_table_go_to_human():
    """한 표에 당기·전기 묶음이 위아래로 있고 구분 표시가 없음(합계 행 둘) — 종전: 아래(전기) 합계를 씀."""
    rows = [row("특수관계구분", "회사명등", "매출", "매입"), row("관계기업", "A", "276,382", "5,805"), row("합계", "합계", "276,382", "5,805"),
            row("관계기업", "A", "899,375", "810,435"), row("합계", "합계", "899,375", "810,435")]
    s = _doc(31, "특수관계자", [("(단위:천원)", rows)])
    assert ST.related_sales(s, False, revenue=100_000_000_000) == (None, "합계 행이 둘 이상(당기·전기 묶음 구분 없음) — 사람 확인")


def test_slash_joined_label_uses_transaction_part():
    rows = [row(c("관계", rs=2), c("특수관계자명", rs=2), c("거래구분", rs=2), c("수익(비용)", cs=2), c("채권(채무)", cs=2)), row("당기", "전기", "당기말", "전기말"),
            row("종속기업", "(주)바이오비쥬", "용역매출", "64,991", "51,161", "-", "-"), row("종속기업", "(주)바이오비쥬", "잡이익등/미수금등", "59,267", "5,959", "8,384", "6,379"),
            row("종속기업", "QINGDAO", "상품매출/매출채권등", "2,896,661", "91,437", "4,160,197", "85,272")]
    s = _doc(33, "특수관계자와의 거래", [("(단위: 천원)", rows)])
    assert ST.related_sales(s, False, revenue=200_000_000_000)[0] == pytest.approx((64_991 + 2_896_661) * 1000 / 200_000_000_000)


def test_asset_purchase_column_is_not_purchases():
    rows = [row(c("특수관계구분", rs=2), c("회사명", rs=2), c("매출등", cs=3), c("매입등", cs=2), c("자산매입", rs=2)), row("상품", "용역", "기타", "용역", "기타"),
            row("종속기업", "(주)다우기술", "368,042", "1,163,582", "-", "120,464", "31,189", "3,700"), row("합계", "합계", "368,042", "1,163,582", "-", "120,464", "31,189", "3,700")]
    s = _doc(30, "특수관계자 거래", [("(단위: 천원)", rows)])
    assert ST.related_purchases(s, False, cogs=10_000_000_000)[0] == pytest.approx(120_464_000 / 10_000_000_000)
    assert ST.related_sales(s, False, revenue=10_000_000_000)[0] == pytest.approx((368_042 + 1_163_582) * 1000 / 10_000_000_000)


def test_column_without_any_amount_is_not_zero():
    rows = [row("회사명", "매출", "비고"), row("A", "해당사항 없음", ""), row("B", "", "")]
    s = _doc(12, "특수관계자 거래", [("(단위:천원)", rows)])
    assert ST.related_sales(s, False, revenue=1_000_000_000) == (None, "매출 열 못 찾음")
