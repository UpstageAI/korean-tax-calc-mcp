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
