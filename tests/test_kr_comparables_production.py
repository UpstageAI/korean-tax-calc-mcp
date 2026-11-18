"""사업보고서 '원재료 및 생산설비'의 직접 생산 단서 추출(2026-11-18). 문장은 화장품 업종 상장사 공시에서 본 것을 줄여 옮김. Claude 작성."""
from korean_tax_calc_mcp.engine.kr_comparables import production as PR


def _doc(body, title="3. 원재료 및 생산설비"):
    return ("<TITLE>II. 사업의 내용</TITLE><TITLE>1. 사업의 개요</TITLE><P>당사는 화장품 제조 및 판매업을 영위합니다.</P>"
            f"<TITLE>{title}</TITLE>" + body + "<TITLE>4. 매출 및 수주상황</TITLE><P>판매경로</P><TITLE>III. 재무에 관한 사항</TITLE>")


def test_no_own_facility_sentences():
    for body in ("<P>당사는 화장품 제조업체들로부터 상품을 주문판매하고 있어 자체 생산공장을 보유하고 있지 않습니다.</P>",
                 "<P>가. 주요 원재료 당사는 자체 생산설비 없이 OEM방식으로 제품을 생산하고 있습니다.</P>",
                 "<P>(1) 생산 능력 당사의 경우 자체 생산시설을 보유하고 있지 않으며, 전 제품을 외주생산방식을 통해 생산하고 있습니다.</P>",
                 "<P>마스크팩 공장을 양도하였습니다. 이후 OEM의 형태로 제품을 생산하고 있습니다.</P>"):
        r = PR.extract(_doc(body))
        assert r["found"] and r["no_own_facility"] and not r["own_production"], body


def test_own_production_needs_numbers_and_skips_void_lines():
    own = PR.extract(_doc("<P>다. 생산능력 및 생산실적 (단위 : 천개)</P><TABLE><TR><TD>시트마스크</TD><TD>44,120</TD><TD>가동률 67.30%</TD></TR></TABLE>"))
    assert own["own_production"] and not own["no_own_facility"]
    heading_only = PR.extract(_doc("<P>나. 생산 및 설비 1) 생산능력 당사는 제품의 기획, 디자인, 마케팅 등에 주력하고 있습니다.</P>"))
    assert not heading_only["own_production"]
    void = PR.extract(_doc("<P>상품을 매입하여 판매하는 사업으로, 생산능력 및 생산실적에 대한 산정은 어렵습니다.</P>"))
    assert not void["own_production"]
    year_only = PR.extract(_doc("<P>생산능력 및 생산설비에 관한 사항 당사는 공장을 2019년 07월 15일 분할하였습니다.</P>"))
    assert not year_only["own_production"]


def test_both_clues_reported_as_problem_without_judging():
    r = PR.extract(_doc("<P>[화장품] 당사의 화장품은 외주 생산을 하고 있어 원재료를 표기하지 않습니다.</P>"
                        "<P>[자회사] (1) 생산능력 (단위 : 백만원) 판넬 횡성공장 67,816</P>"))
    assert r["no_own_facility"] and r["own_production"] and r["problems"]
    assert "판정" not in r and "직접 제조" not in str(r)


def test_section_missing_and_alternate_title():
    assert not PR.extract("<TITLE>II. 사업의 내용</TITLE><TITLE>1. 사업의 개요</TITLE><P>x</P><TITLE>III. 재무에 관한 사항</TITLE>")["found"]
    r = PR.extract(_doc("<P>자체 생산설비 없이 외주가공(OEM) 형태로 생산하고 있습니다.</P>", title="2. 생산 및 설비"))
    assert r["found"] and r["no_own_facility"]


def test_unlisted_machinery_account_presence_only():
    """비상장 감사보고서(2026-11-18): 유형자산 주석에 기계장치 계정이 있는지만 — 없으면 없음, 있으면 있음(금액은 안 읽음), 유형자산 자체를 못 찾으면 불명."""
    none = PR.machinery("<P>8. 유형자산</P><TABLE><TR><TD>비품</TD><TD>12,000</TD></TR><TR><TD>차량운반구</TD><TD>3,000</TD></TR></TABLE>")
    assert none["machinery_account"] == "없음"
    has = PR.machinery("<P>8. 유형자산</P><TABLE><TR><TD>기 계 장 치</TD><TD>2,559,481,818</TD></TR></TABLE>")
    assert has["machinery_account"] == "있음" and "기 계 장 치" in has["evidence"]
    assert PR.machinery("<P>회사의 개요</P>")["machinery_account"] == "불명"
