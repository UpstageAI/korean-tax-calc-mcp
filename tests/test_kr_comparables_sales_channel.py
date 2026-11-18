"""사업보고서 '매출 및 수주상황'의 판매경로·판매방법·판매전략·주요 매출처 추출(2026-11-18). 표 모양은 실제 공시에서 본 것을 줄여 옮김. Claude 작성."""
from korean_tax_calc_mcp.engine.kr_comparables import sales_channel as SC


def _doc(body, extra_titles=True):
    head = "<TITLE>II. 사업의 내용</TITLE><TITLE>1. 사업의 개요</TITLE><P>당사는 화장품을 판매합니다.</P>" if extra_titles else "<TITLE>II. 사업의 내용</TITLE>"
    return head + ("<TITLE>4. 매출 및 수주상황</TITLE>" if extra_titles else "") + body + "<TITLE>5. 위험관리 및 파생거래</TITLE><P>시장위험</P><TITLE>III. 재무에 관한 사항</TITLE>"


def _table(rows):
    def cell(c):
        if isinstance(c, tuple):
            text, rs, cs = c
            return f'<TD ROWSPAN="{rs}" COLSPAN="{cs}">{text}</TD>'
        return f"<TD>{c}</TD>"
    return "<TABLE>" + "".join("<TR>" + "".join(cell(c) for c in r) + "</TR>" for r in rows) + "</TABLE>"


def test_topics_split_by_subheadings_and_vertical_share_table_checked():
    s = _doc("<P>가. 매출실적</P>" + _table([["구분", "제10기"], ["제품", "1,000"]]) +
             "<P>나. 판매경로 및 판매방법 등</P><P>(1) 판매경로</P>" +
             _table([["구 분", "매출액 비중(%)", "비 고"], ["제조총판", "31.4%", "-"], ["온라인", "14.7%", "-"], ["수출", "53.9%", "-"], ["합계", "100.0", "-"]]) +
             "<P>(2) 판매방법 및 조건</P><P>현금거래를 원칙으로 함.</P><P>(3) 판매전략</P><P>온라인 확대 및 해외 시장 개척</P><P>다. 수주상황</P><P>수주계약을 체결하지 않습니다.</P>")
    r = SC.extract(s)
    assert r["found"] and not r["problems"]
    assert set(r["topics"]) == {"판매경로", "판매방법", "판매전략"}
    assert r["topics"]["판매방법"]["text"] == "현금거래를 원칙으로 함." and "수주계약" not in r["topics"]["판매전략"]["text"]
    assert r["shares"][0]["행"] == [{"경로": "제조총판", "비중": 31.4}, {"경로": "온라인", "비중": 14.7}, {"경로": "수출", "비중": 53.9}]
    assert r["shares"][0]["검산"] == "합계 100.0%"


def test_share_table_with_merged_cells_takes_latest_period_and_excludes_totals():
    t = _table([[("사업부문", 2, 1), ("판매경로", 2, 1), ("매출비중(%)", 1, 3)], ["제25기", "제24기", "제23기"],
                [("화장품", 3, 1), "On-Line", "17.30", "30.00", "40.00"], ["직영점", "26.21", "20.00", "10.00"], ["수 출(*)", "56.49", "50.00", "50.00"],
                [("합 계", 1, 2), "100.00", "100.00", "100.00"]])
    r = SC.extract(_doc("<P>나. 판매경로 및 판매방법 등</P><P>(1) 판매경로별 매출액 비중</P>" + t))
    tb = r["shares"][0]
    assert "제25기" in tb["기간"]
    assert tb["행"] == [{"경로": "화장품 > On-Line", "비중": 17.3}, {"경로": "화장품 > 직영점", "비중": 26.21}, {"경로": "화장품 > 수 출(*)", "비중": 56.49}]


def test_shares_not_summing_to_100_are_withheld_with_reason():
    t = _table([["판매경로", "비중"], ["대리점", "40%"], ["온라인", "30%"]])
    r = SC.extract(_doc("<P>나. 판매경로</P>" + t))
    assert r["shares"] == [] and "100%가 아님(70.0%)" in r["shares_note"]
    assert "대리점 | 40%" in r["topics"]["판매경로"]["text"]          # 숫자는 안 내도 원문 글은 그대로 넘김


def test_horizontal_share_rows_and_amount_with_ratio_cells():
    hor = _table([["경 로", "국내 오프라인", "국내 온라인", "해외"], ["비 중", "32%", "31%", "37%"]])
    r = SC.extract(_doc("<P>2) 판매경로</P>" + hor))
    assert [x["비중"] for x in r["shares"][0]["행"]] == [32.0, 31.0, 37.0] and r["shares"][0]["행"][0]["경로"] == "국내 오프라인"
    amt = _table([["품 목", "판매경로", "판매경로별 매출액(비중)"], ["카드", "직 판", "138,747 (58.7)"], ["플랫폼", "온라인결제", "97,561 (41.3)"], ["합 계", "-", "236,308 (100.0)"]])
    r = SC.extract(_doc("<P>나. 판매경로</P>" + amt))
    assert [(x["경로"], x["비중"]) for x in r["shares"][0]["행"]] == [("카드 > 직 판", 58.7), ("플랫폼 > 온라인결제", 41.3)]


def test_group_tables_where_each_item_sums_to_100():
    t = _table([["품 목", "구 분", "판매경로", "판매경로별 비중"], [("AMI", 2, 1), "국 내", "직접판매", "36%"], ["수 출", "직접영업", "64%"],
                [("RFID", 2, 1), "국 내", "직접판매", "96%"], ["수 출", "직접영업", "4%"]])
    r = SC.extract(_doc("<P>나. 판매경로</P>" + t))
    assert "묶음 2개" in r["shares"][0]["검산"] and r["shares"][0]["행"][1] == {"경로": "AMI > 수 출 > 직접영업", "비중": 64.0}


def test_inline_text_shares_only_when_labels_are_route_names():
    r = SC.extract(_doc("<P>나. 판매경로</P><P>가) H&B사업부 : 회사 → 대리점 → 소비자 (매출액 비중 : 8.4%)나) 브랜드샵 : 회사 → 가맹점 → 소비자 (매출액 비중 : 78%)다) 기타 (매출액 비중 : 13.6%)</P>"))
    assert [x["비중"] for x in r["shares"][0]["행"]] == [8.4, 78.0, 13.6] and "글에서 읽음" in r["shares"][0]["검산"]
    r = SC.extract(_doc("<P>나. 판매경로</P><P>당사는 직접 판매 외에도 에이전트를 통한 간접 판매도 수행하고 있습니다. 직접 판매가 90%를 차지하고 있으며, 그 외 10%는 중개업체를 통합니다.</P>"))
    assert r["shares"] == []                                           # 문장 속 숫자가 우연히 100이 되어도 비중으로 읽지 않음


def test_headings_glued_in_one_paragraph_and_sentence_starting_with_topic_word_is_body():
    s = _doc("<P>가. 판매조직영업관련팀은 해외영업팀과 국내영업팀으로 구성되어 있습니다.나. 판매경로(1) 내수 : 대량 거래처는 직접 판매하고 소량 거래처는 대리점을 통해 판매합니다.</P>"
             "<P>다. 판매방법 및 조건</P><P>당사의 판매조직은 본사가 맡고 있으며 대금은 현금으로 회수합니다.</P>")
    r = SC.extract(s)
    assert r["topics"]["판매조직"]["text"].startswith("영업관련팀은") and r["topics"]["판매경로"]["text"].startswith("(1) 내수")
    assert r["topics"]["판매방법"]["text"].startswith("당사의 판매조직은")      # 본문 문장을 소제목으로 보지 않음


def test_parent_heading_filled_from_subsections_and_image_only_marked():
    s = _doc("<P>(2) 판매경로 및 판매방법</P><P>(가) 판매조직</P><IMG SRC='a.jpg'><P>(나) 판매전략</P><P>면세점 확대</P><P>나. 수주상황</P><P>해당 없음</P>")
    r = SC.extract(s)
    assert r["topics"]["판매조직"]["text"] == SC.IMAGE_MARK
    assert "면세점 확대" in r["topics"]["판매경로"]["text"] and "해당 없음" not in r["topics"]["판매경로"]["text"]


def test_no_section_and_old_format_fallback():
    assert SC.extract("<TITLE>I. 회사의 개요</TITLE><P>x</P>")["problems"] == ["매출 및 수주상황 절 없음"]
    r = SC.extract(_doc("<P>" + "회사 소개 문장입니다. " * 200 + "</P><P>나. 판매경로</P><P>온라인을 통한 판매가 대부분입니다.</P>", extra_titles=False))
    assert r["topics"]["판매경로"]["text"] == "온라인을 통한 판매가 대부분입니다."


def test_section_without_channel_headings_reports_none():
    r = SC.extract(_doc("<P>가. 매출실적</P>" + _table([["구분", "제10기"], ["제품", "1,000"]])))
    assert not r["found"] and r["topics"] == {} and r["problems"] == []
