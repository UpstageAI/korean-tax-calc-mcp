"""WP4 원문 대조분(2026-11-15, 법제처 DRF·국세법령정보시스템). Claude 작성. 외부 호출 없음. 값은 조문에서 손으로 계산.

대조한 원문:
- 상속세 및 증여세법 제19조·제20조(2016.9.1. 현재·2017.1.1. 시행본), 시행령 제17조(2016.9.30.~2026.10.1. 현재 시행본 11개), 시행규칙 별지 제9호서식 부표 1·부표 3(2026.3.20.)
- 시행령 제56조제4항(2016.9.30.·2019.12.31.·2020.10.8.·2026.10.1. 현재 시행본)과 대통령령 제30391호 부칙 제9조제3항, 시행규칙 제17조의3(2016.12.27.·2026.3.20.)
- 시행령 제49조제1항제2호(대통령령 제36131호, 부칙 제11조), 시행령 제46조의3제2항·대통령령 제26960호 부칙 제9조
- 국세청 건물 기준시가 계산방법 고시 제11조 표: 2021~2026년 적용 6개 판(법제처), 2016~2020년 적용 5개 판(국세청 누리집 고시 게시판 첨부 고시문 — 제2015-66호·제2016-21호·제2017-37호·제2018-50호·제2019-32호)
- 조세범 처벌절차법 시행령 부칙(제23601호·제27652호·제29539호·제33277호·제36144호), 조세범 처벌법 2016.3.2.·2021.1.1. 시행본
- 해석: 서면-2016-상속증여-5376, 서울고등법원 2016누33027, 조심 2014서5656, 서면-2017-법령해석재산-2641
"""
from datetime import date

from korean_tax_calc_mcp.engine import calc_building as BD
from korean_tax_calc_mcp.engine import calc_gold_gaps6 as G6
from korean_tax_calc_mcp.engine import calc_inhgift as I
from korean_tax_calc_mcp.engine import calc_nominee as N
from korean_tax_calc_mcp.engine import calc_stock_val as V
from korean_tax_calc_mcp.engine import calc_tax_crime_fine as F
from korean_tax_calc_mcp.engine import calc_tax_priority as TP

M = 100_000_000


def test_spouse_limit_includes_presumed_estate_and_subtracts_prior_gift_base():
    kw = dict(year=2024, estate_value=30 * M, children=2)
    sp = {"actual": 25 * M, "legal_share": "3/5"}
    a = I.inheritance_tax(**kw, spouse=dict(sp))
    assert a["계산"]["배우자공제_한도"] == 18 * M and a["계산"]["배우자상속공제"] == 18 * M              # 30억 × 3/5
    # 추정상속재산 = 10억 − min(10억 × 20%, 2억) = 8억 → A = 38억 → 한도 22.8억
    b = I.inheritance_tax(**kw, spouse=dict(sp), presumed_items=[{"kind": "현금·예금·유가증권", "window": "1년", "amount": 10 * M, "unexplained": 10 * M}])
    assert b["결과"]["추정상속재산"] == 8 * M and b["계산"]["배우자공제_한도"] == 2_280_000_000 and b["계산"]["배우자상속공제"] == 2_280_000_000
    # E: 배우자 사전증여재산의 증여세 과세표준 1억 → 18억 − 1억
    c = I.inheritance_tax(**kw, spouse={**sp, "prior_gift_tax_base": 1 * M})
    assert c["계산"]["배우자공제_한도"] == 17 * M
    assert "부표 3" in b["판단"]["배우자공제_한도식"]["근거"] and not any("예규 확인 필요" in x for x in b["판단"]["확인필요"])
    assert "error" in I.inheritance_tax(**kw, spouse={**sp, "prior_gift_tax_base": -1})


def test_2016_year_fraction_shows_both_readings_2017_does_not():
    d = I.inheritance_tax(year=2016, estate_value=30 * M, children=1, minors=[3.5], disabled=[10.2])
    two = d["판단"]["2016년_연수_두_해석"]
    assert two["미성년자·장애인공제_버림"] == 130_000_000 and two["미성년자·장애인공제_올림"] == 150_000_000 and two["차이"] == 20_000_000   # (3+10)·(4+11) × 1천만
    assert "근거 없음" in two["근거"] and not any("충돌" in x for x in d["판단"]["확인필요"])
    assert "2016년_연수_두_해석" not in I.inheritance_tax(year=2017, estate_value=30 * M, children=1, minors=[3.5])["판단"]
    assert "2016년_연수_두_해석" not in I.inheritance_tax(year=2016, estate_value=30 * M, children=1, minors=[3])["판단"]


def test_nominee_aggregation_before_2019_only():
    r = N.nominee_gift_tax(5 * M, deemed_gift_date="2018-06-01", prior_gifts_same_donor=3 * M, prior_gift_tax_paid=50_000_000)["결과"]
    # 과세표준 8억 → 8억 × 30% − 6천만 = 1.8억, 한도 1.8억 × 3/8 = 6,750만, 공제 5천만, 신고세액공제 (1.8억 − 5천만) × 5%(2018)
    assert (r["과세표준"], r["산출세액"], r["납부세액공제_한도"], r["납부세액공제"], r["신고세액공제"], r["납부할세액"]) == \
        (8 * M, 180_000_000, 67_500_000, 50_000_000, 6_500_000, 123_500_000)
    n = N.nominee_gift_tax(5 * M, deemed_gift_date="2019-06-01", prior_gifts_same_donor=3 * M)["결과"]      # 2019.1.1. 이후: 합산배제
    assert n["과세표준"] == 5 * M and n["산출세액"] == 90_000_000 and "납부세액공제" not in n
    s = N.nominee_gift_tax(5 * M, deemed_gift_date="2018-06-01", prior_gifts_same_donor=9_999_999)["결과"]   # 1천만원 미만은 가산 안 함
    assert s["과세표준"] == 5 * M and "1천만원 미만" in s["합산"]
    g = N.nominee_gift_tax(5 * M, deemed_gift_date="2018-06-01", prior_gifts_same_donor=3 * M, prior_gifts_deduction=50_000_000)["결과"]
    assert g["과세표준"] == 750_000_000 and g["가산분_과세표준"] == 250_000_000
    assert "error" in N.nominee_gift_tax(5 * M, deemed_gift_date="2019-06-01", prior_gift_tax_paid=1)
    out = N.nominee_gift_tax(5 * M, deemed_gift_date="2018-06-01")
    assert any("조심 2014서5656" in x for x in out["주의"]) and not any("확인하지 못해" in x for x in out["주의"])


def _adj(year, floors, floor_use, grade=""):
    r = BD.building_standard_price(year, 100, "철근콘크리트조", "근린생활시설", 3_000_000, 2010, purpose="상증세", floors=floors, floor_use=floor_use, safety_grade=grade)
    return r["결과"]["조정률"], " ".join(p["결론"] for p in r["판단"] if p["항목"] in ("개별건물 특성 조정률", "조정률 주의")), r


def test_building_adjustment_table_by_year():
    assert _adj(2026, 3, "지하2층", "C")[0] == 0.504                 # 규모 90 × 지하 2층 이상 70 × 안전진단 C 80
    assert _adj(2026, None, "지하4층")[0] == 0.63                    # 지하 2층 이상 70(종전에는 80으로 계산)
    a, why, _ = _adj(2026, 8, "지하1층")
    assert a == 1.0 and "5층 초과" in why                            # 번호 22·23은 최고층수 5층 이하 건물만
    # 구분 Ⅶ(안전진단 C 80)는 2016~2020년 적용 고시문(국세청 누리집 첨부)에도 있음 — 규모 90 × 지하 1층 80 × 안전진단 80 = 0.576
    for y in (2016, 2019, 2020, 2021):
        a, why, _ = _adj(y, 3, "지하1층", "C")
        assert a == 0.576 and "대조하지 못함" not in why, y
    assert _adj(2020, 3, "지하1층")[0] == 0.72                       # 안전진단 입력이 없으면 규모 90 × 지하 1층 80
    a15, why15, _ = _adj(2015, 3, "지하1층", "C")                    # 2015년 이전 적용 고시는 받지 않음 — 2016년 표로 계산하고 알림
    assert a15 == 0.576 and "대조하지 못함" in why15 and "제2015-66호" in why15
    _, why19, r19 = _adj(2019, 3, "1층")
    assert "제2018-50호" in " ".join(p["근거"] for p in r19["판단"] if p["항목"] == "개별건물 특성 조정률")
    assert not any("확인 필요" in p["근거"] for p in r19["판단"] if p["항목"] == "개별건물 특성 조정률")


def test_net_income_items_by_decree_version():
    v, _, prob = V.net_income_from_statement({"각사업연도소득": 100, "가산": {"기타가산": 5}, "차감": {"징벌적 손해배상": 7}}, date(2020, 2, 10))
    assert v == 100 and len(prob) == 2 and "시행규칙에 정한 조항이 없어" in prob[0] and "2020-02-11" in prob[1]
    assert V.net_income_from_statement({"각사업연도소득": 100, "차감": {"징벌적 손해배상": 7}}, date(2020, 2, 11))[0] == 93
    assert V.net_income_from_statement({"각사업연도소득": 100, "차감": {"기타차감": 7}}, date(2024, 1, 1))[0] == 100


def test_settlement_shows_both_readings():
    o = [{"offense": "제3조제1항본문", "count": 1, "base": 100_000_000, "habitual": True, "impaired": True}]
    r = F.settlement(o, "2026-03-10", act_date="2025-06-01")
    row = r["결과"]["범칙행위별"][0]
    # 차례로: 개별기준 × 1.5 × 0.5, 개별기준에 각각: 개별기준 + 50% − 50%
    assert row["벌금상당액"] == row["개별기준"] * 3 // 4 and row["다른_해석_벌금상당액"] == row["개별기준"]
    assert r["결과"]["다른_기준_결과"]["기준"] == "행위일" and "2019.2.12." in r["결과"]["다른_기준_결과"]["적용_별표"]
    same = F.settlement(o, "2025-03-10", act_date="2024-06-01")
    assert "다른_기준_결과" not in same["결과"]
    one = F.settlement([{"offense": "제3조제1항본문", "count": 1, "base": 100_000_000, "habitual": True}], "2025-03-10")
    assert "다른_해석_벌금상당액" not in one["결과"]["범칙행위별"][0]
    assert not any("실무 확인 필요" in x for x in r["주의"]) and any("근거 없음" in x for x in r["주의"])


def test_valuation_notes_appraisal_exclusions():
    r = G6.inheritance_gift_valuation("증여", "2026-05-01", 5 * M, market_values=[{"대상": "해당재산", "종류": "감정", "가액": 6 * M, "날짜": "2026-04-01"},
                                                                              {"대상": "해당재산", "종류": "감정", "가액": 7 * M, "날짜": "2026-04-10"}])
    assert "제65조제2항" in r["판단"]["감정가액_제외_재산"] and "제36131호" in r["판단"]["감정가액_제외_재산"]
    r2 = G6.inheritance_gift_valuation("증여", "2026-05-01", 5 * M)
    assert "감정가액_제외_재산" not in r2["판단"]


def _dist(claims, sale=50 * M):
    r = TP.distribute(sale, 0, "2021-05-01", "토지", claims)
    return {x["이름"]: x["배분액"] for x in r["결과"]["배분"]}, r


def test_tax_absorption_by_first_seizure():
    """1단계 법정기일·설정일 순 → 2단계 조세끼리 압류선착(국세기본법 제36조, 대법원 2011다47534). 당해세는 제외(대법원 2007두2197)."""
    vat = {"이름": "부가세", "종류": "국세", "금액": 10 * M, "법정기일": "2019-01-25"}
    bank = {"이름": "은행", "종류": "저당권", "금액": 40 * M, "설정일": "2020-03-02"}
    inc = {"이름": "소득세", "종류": "국세", "금액": 10 * M, "법정기일": "2021-05-31"}
    a, ra = _dist([vat, bank, inc])                                             # 압류 없음: 그대로
    assert a == {"부가세": 10 * M, "은행": 40 * M, "소득세": 0}
    b, rb = _dist([vat, bank, {**inc, "압류일": "2020-12-01"}])                  # 소득세가 압류: 부가세가 받은 10억을 흡수
    assert b == {"부가세": 0, "은행": 40 * M, "소득세": 10 * M}
    assert any(p["항목"] == "조세 상호간 흡수(압류선착주의)" and "2011다47534" in p["근거"] for p in rb["판단"])
    c, _ = _dist([vat, bank, {**inc, "금액": 6 * M, "압류일": "2020-12-01"}])     # 압류 조세 6억만 흡수
    assert c == {"부가세": 4 * M, "은행": 40 * M, "소득세": 6 * M}
    d, _ = _dist([{**vat, "압류일": "2020-06-01"}, bank, {**inc, "압류일": "2020-12-01"}])   # 부가세 압류가 먼저: 흡수 없음
    assert d == {"부가세": 10 * M, "은행": 40 * M, "소득세": 0}
    assert sum(b.values()) == sum(a.values()) == 50 * M
