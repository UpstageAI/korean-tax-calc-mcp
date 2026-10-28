"""생계를 함께하는 친족 — 국세기본법 시행령 제1조의2②3호, 법인세법 시행령 제2조⑧3호(구 제2조⑤3호·제87조①3호).

판정 틀(조사 노트 2026-10-28 (c)·(d), 10/28 보완):
- 1차 기준 동거 불요·생활비 공동 부담: 공동부담, 무소득+정기송금, 수입 상대방 계좌 입금 → 생계 공동
- 안정 소득+따로 거주 또는 별도 세대+생활비 각자+지원 없음, 제3자 지원, 혼인 독립 가구 → 생계 별도
- 주민등록 동일세대는 객관 자료로만 반증(진술서만이면 추정 유지), 동일세대+소득만 → 추정, 그 밖 → 입력 확인 필요
손계산(영 제53조②, 대여일 산입·말일 산입):
- 차입금 이자 10,000,000, 적수 36,500,000,000
- 이배우 가지급금 10,000,000 × 92일(2025-10-01~12-31) = 920,000,000
- 10,000,000 × 920,000,000 ÷ 36,500,000,000 = 252,054.79 → 252,054(원 미만 절사)
"""
import copy

from test_form_templates import c

from korean_tax_calc_mcp.audit.agents import related as R
from korean_tax_calc_mcp.audit.agents.related_intake import normalize, to_case

CO = "㈜가람정밀"
# 김대표는 지분 없는 대표이사(임원) — 지분 1% 이상이면 ⑧2호로 배우자가 이미 특수관계라 ②3호 판정이 드러나지 않는다
BASE = {
    "people": {CO: {"구분": "법인"}, "㈜모회사": {"구분": "법인"}, "김대표": {"구분": "개인"}, "이배우": {"구분": "개인"},
               "김자녀": {"구분": "개인"}, "이직원": {"구분": "개인"}, "박동료": {"구분": "개인"}},
    "family": [["김대표", "이배우", "배우자"], ["김대표", "김자녀", "부모자녀"],
               # 이직원의 5촌 혈족(당숙): 이직원 ← 이부 ← 이조부 ← 이증조 → 이종조 → 이종숙
               ["이부", "이직원", "부모자녀"], ["이조부", "이부", "부모자녀"], ["이증조", "이조부", "부모자녀"],
               ["이증조", "이종조", "부모자녀"], ["이종조", "이종숙", "부모자녀"]],
    "stakes": [["㈜모회사", CO, 1.0]],
    "officers": {CO: ["김대표"]},
    "employees": {CO: ["이직원", "박동료"]},
}


def case_with(*shared):
    j = copy.deepcopy(BASE)
    j["livelihood_shared"] = list(shared)
    return to_case(normalize(j))


def judge(other, on, *shared):
    return R.judge_all_at(case_with(*shared), CO, other, on)


def test_gap_without_facts_spouse_unrelated():
    # 지분 없는 대표의 배우자: 생계 사실관계가 없으면 법인세법상 특수관계 해당 없음(이전 동작 유지)
    j = judge("이배우", "2025-12-31")
    assert j["판정"]["법인"].startswith("해당 없음") and "생계를_함께하는_친족" not in j


def test_shared_expense_spouse_related():
    j = judge("이배우", "2025-12-31", {"친족": "이배우", "상대방": "김대표", "생활비_공동부담": "공동", "동거_사실": "같은집_공유구조"})
    assert j["판정"]["국기"] == "특수관계 해당" and j["판정"]["법인"] == "특수관계 해당"
    refs = [h["근거"] for h in j["근거"]["법인"]]
    assert "법인세법 시행령 제2조⑧3호" in refs
    assert "국세기본법 시행령 제1조의2②3호" in [h["근거"] for h in j["근거"]["국기"]]
    r = next(x for x in j["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r["결론"] == "생계 공동" and r["친족관계"] == "배우자" and "임원·사용인" in r["상대방_관계"]
    assert "징세과-253(2011.03.18)" in r["결정·해석"]
    # 상증법에는 '사용인과 생계를 함께하는 친족' 항목 없음
    assert j["판정"]["상증"].startswith("해당 없음")
    상증 = [x for x in j["생계를_함께하는_친족"] if x["세법"] == "상증"]
    assert 상증 and all(x["근거"] for x in 상증)


def test_independent_adult_child_living_separately_unrelated():
    f = {"친족": "김자녀", "상대방": "김대표", "주민등록_동일세대": False, "동거_사실": "따로거주", "생활비_공동부담": "각자분담_증빙있음",
         "독립생계_소득": "안정소득_있음", "경제적_지원": "없음", "별거_사유": "독립", "별도_임대차": True}
    j = judge("김자녀", "2025-12-31", f)
    assert j["판정"]["법인"].startswith("해당 없음") and j["판정"]["국기"].startswith("해당 없음")
    r = next(x for x in j["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r["결론"] == "생계 별도" and "조심-2012-서-0497(2012.03.21)" in r["결정·해석"]


def test_same_household_only_is_presumption_with_note():
    j = judge("김자녀", "2025-12-31", {"친족": "김자녀", "상대방": "김대표", "주민등록_동일세대": True})
    assert j["판정"]["법인"] == "특수관계 해당"
    r = next(x for x in j["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r["결론"] == "생계 공동 추정"
    assert "반증" in r["판단"] and "국심-2003-중-1871" in r["판단"] and "진술서만" in r["판단"]
    assert "국심-2004-서-4375(2005.08.09)" in r["결정·해석"]
    assert any("생활비_공동부담" in e for e in r["반증_자료"])
    assert any("추정" in h["내용"] for h in j["근거"]["법인"])
    assert any("반증" in n for n in j["참고"])


def test_conflicting_facts_need_input():
    # 주민등록은 동일세대인데 따로 산다고 하고, 소득은 있으나 생활비 분담 증빙 없음
    f = {"친족": "김자녀", "상대방": "김대표", "주민등록_동일세대": True, "동거_사실": "따로거주",
         "독립생계_소득": "안정소득_있음", "생활비_공동부담": "각자분담_증빙없음", "경제적_지원": "모름"}
    j = judge("김자녀", "2025-12-31", f)
    assert j["판정"]["법인"].startswith("입력 확인 필요")
    r = next(x for x in j["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r["결론"] == "입력 확인 필요"
    assert {"주민등록_동일세대", "동거_사실", "경제적_지원"} <= set(r["확인할_항목"])
    assert any("주민등록표" in e for e in r["필요_자료"]) and any("송금" in e for e in r["필요_자료"])
    # 같은 집 공유구조인데 별거 사유를 적은 모순
    j = judge("김자녀", "2025-12-31", {"친족": "김자녀", "상대방": "김대표", "동거_사실": "같은집_공유구조", "별거_사유": "취학"})
    assert j["판정"]["법인"].startswith("입력 확인 필요")


def test_5chon_relative_range_by_date():
    f = {"친족": "이종숙", "상대방": "이직원", "생활비_공동부담": "공동"}
    j22 = judge("이종숙", "2022-12-31", f)
    j24 = judge("이종숙", "2024-06-30", f)
    assert j22["판정"]["법인"] == "특수관계 해당" and j22["판정"]["국기"] == "특수관계 해당"
    r22 = next(x for x in j22["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r22["친족관계"] == "혈족 5촌" and r22["근거"] == "법인세법 시행령 제2조⑤3호"
    assert j24["판정"]["법인"].startswith("해당 없음")
    r24 = next(x for x in j24["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r24["결론"] == "해당 없음" and "범위 밖" in r24["사유"][0]


def test_corporate_article_location_by_date():
    f = {"친족": "이배우", "상대방": "김대표", "생활비_공동부담": "공동"}
    j = judge("이배우", "2018-12-31", f)
    assert "법인세법 시행령 제87조①3호" in [h["근거"] for h in j["근거"]["법인"]]
    j = judge("이배우", "2020-06-30", f)
    assert "법인세법 시행령 제2조⑤3호" in [h["근거"] for h in j["근거"]["법인"]]


def test_prerequisites():
    # 상대방이 임원·사용인·생계유지자가 아니면 ②3호 해당 없음
    j = judge("이배우", "2025-12-31", {"친족": "이배우", "상대방": "김자녀", "생활비_공동부담": "공동"})
    r = next(x for x in j["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r["결론"] == "해당 없음" and "전제 미충족" in r["사유"][0]
    # 무소득 + 정기송금(취학 별거) → 생계 공동
    j = judge("김자녀", "2025-12-31", {"친족": "김자녀", "상대방": "김대표", "동거_사실": "따로거주", "별거_사유": "취학",
                                        "독립생계_소득": "없음", "경제적_지원": "정기송금_있음"})
    r = next(x for x in j["생계를_함께하는_친족"] if x["세법"] == "법인")
    assert r["결론"] == "생계 공동" and "조심-2009-서-2719(2009.09.23)" in r["결정·해석"]
    # 잘못된 값
    r = c("related_judge", {"a": CO, "b": "이배우", "on": "2025-12-31", "people": BASE["people"], "family": BASE["family"],
                            "stakes": BASE["stakes"], "officers": BASE["officers"],
                            "livelihood_shared": [{"친족": "이배우", "상대방": "김대표", "생활비_공동부담": "반반"}]})
    assert "error" in r and "생활비_공동부담" in r["문제"][0]


def test_related_judge_tool():
    r = c("related_judge", {"a": CO, "b": "이배우", "on": "2025-12-31", "people": BASE["people"], "family": BASE["family"],
                            "stakes": BASE["stakes"], "officers": BASE["officers"], "employees": BASE["employees"],
                            "livelihood_shared": [{"친족": "이배우", "상대방": "김대표", "생활비_공동부담": "공동(혼재)"}]})
    assert r["판정"]["법인"] == "특수관계 해당" and r["생계를_함께하는_친족"][0]["결론"] == "생계 공동"


# ── 업무무관 지급이자: 가지급금 상대방 판정까지 그대로 이어짐 ──
LOANS = [{"interest": 10_000_000, "jeoksu": 36_500_000_000}]
ADV = [{"상대방": "이배우", "사유": "업무무관대여", "금액": 10_000_000, "지급일": "2025-10-01"}]


def nb(*shared):
    rel = copy.deepcopy(BASE)
    rel["livelihood_shared"] = list(shared)
    return c("nonbusiness_interest_disallowance", {"loans": LOANS, "advances": ADV, "year": 2025, "company": CO, "relations": rel})


def test_nonbusiness_advance_end_to_end():
    # 사실관계 없음 → 비특수관계인, 손금불산입 0
    r = nb()
    assert r["계산"]["가지급금"][0]["대상"] == "비특수관계인" and r["결과"]["손금불산입(기타사외유출)"] == 0
    # 생활비 공동부담 → ⑧3호 특수관계, 기타특수관계인, 252,054원
    r = nb({"친족": "이배우", "상대방": "김대표", "생활비_공동부담": "공동"})
    row = r["계산"]["가지급금"][0]
    assert row["대상"] == "기타특수관계인" and row["적수"] == 920_000_000
    assert "법인세법 시행령 제2조⑧3호" in row["판단"] and "생계를 함께하는 친족" in row["판단"]
    assert row["특수관계_판정"]["생계를_함께하는_친족"][0]["결론"] == "생계 공동"
    assert r["결과"]["손금불산입(기타사외유출)"] == 10_000_000 * 920_000_000 // 36_500_000_000 == 252_054
    # 사실관계가 모자라면 비특수관계인으로 넘기지 않고 입력 확인 필요
    r = nb({"친족": "이배우", "상대방": "김대표", "별거_사유": "혼인파탄", "동거_사실": "따로거주"})
    assert "error" in r and "입력 확인 필요" in r["문제"][0] and "필요 자료" in r["문제"][0]


def test_rules_table_single_source():
    from korean_tax_calc_mcp.audit.agents import livelihood as L
    assert "국심-2003-중-0866(2003.06.04)" in L.RULINGS["정의"]
    every = [r for v in L.RULES.values() for r in v["결정·해석"]]
    assert not any("2025다200233" in r or "2025-다-200233" in r for r in every)  # 재인용만 된 번호는 넣지 않음
    # 값 조건을 표에서 읽는다 — 표를 바꾸면 결론이 따라 바뀜
    f = L.facts_of({"생활비_공동부담": "각자분담_증빙없음", "동거_사실": "같은집_공유구조"})
    assert L.judge_facts(f)[0] == "생계 공동 추정"
    old = L.RULES["추정"]["생활비_값"]
    try:
        L.RULES["추정"]["생활비_값"] = (None,)
        assert L.judge_facts(f)[0] == "입력 확인 필요"
    finally:
        L.RULES["추정"]["생활비_값"] = old


def _shared(j, law="법인"):
    return next(x for x in j["생계를_함께하는_친족"] if x["세법"] == law)


def test_same_household_income_only_stays_presumption():
    # 주민등록 동일세대 + 친족 본인 안정 소득만 → 소득만으로는 뒤집지 않음
    j = judge("김자녀", "2025-12-31", {"친족": "김자녀", "상대방": "김대표", "주민등록_동일세대": True, "독립생계_소득": "안정소득_있음"})
    r = _shared(j)
    assert r["결론"] == "생계 공동 추정" and j["판정"]["법인"] == "특수관계 해당"
    assert {"국심-2003-중-1720(2003.10.06)", "조심-2008-서-2191(2008.11.28)", "국심-2003-부-2250(2004.02.02)"} <= set(r["결정·해석"])


SEPARATE = {"친족": "김자녀", "상대방": "김대표", "주민등록_동일세대": True, "동거_사실": "따로거주", "생활비_공동부담": "각자분담_증빙있음",
            "독립생계_소득": "안정소득_있음", "경제적_지원": "없음"}


def test_same_household_statement_only_keeps_presumption_with_documents():
    j = judge("김자녀", "2025-12-31", {**SEPARATE, "별거_증빙_유형": ["진술서만"]})
    r = _shared(j)
    assert r["결론"] == "생계 공동 추정" and "진술서만" in r["사유"][0]
    assert any("전화가입 이력" in d for d in r["인정되는_별거_증빙"]) and "사실확인서" in r["배척된_증빙"]
    assert "조심-2008-서-2191(2008.11.28)" in r["결정·해석"]
    # 객관 자료가 있으면 반증 → 생계 별도
    j = judge("김자녀", "2025-12-31", {**SEPARATE, "별거_증빙_유형": ["공과금·관리비_명의", "전화·인터넷_가입"]})
    r = _shared(j)
    assert r["결론"] == "생계 별도" and j["판정"]["법인"].startswith("해당 없음")
    assert "국심-2007-중-1840(2007.12.26)" in r["결정·해석"]


def test_third_party_support_separate():
    f = {"친족": "김자녀", "상대방": "김대표", "동거_사실": "따로거주", "독립생계_소득": "없음", "경제적_지원": "제3자_지원"}
    r = _shared(judge("김자녀", "2025-12-31", f))
    assert r["결론"] == "생계 별도" and r["결정·해석"][0] == "국심-2002-서-0366(2002.04.02)"


def test_year_end_dependent_and_income_deposit():
    # 부양가족 공제 이력만 → 추정, 별도 요건과 함께면 모순 → 입력 확인 필요
    r = _shared(judge("김자녀", "2025-12-31", {"친족": "김자녀", "상대방": "김대표", "연말정산_부양가족_등록": True}))
    assert r["결론"] == "생계 공동 추정" and "서울행정법원-2006-구단-2162(2006.11.24)" in r["결정·해석"]
    f = {**SEPARATE, "주민등록_동일세대": False, "연말정산_부양가족_등록": True}
    assert _shared(judge("김자녀", "2025-12-31", f))["결론"] == "입력 확인 필요"
    # 수입이 상대방 계좌로 입금 → 생계 공동
    r = _shared(judge("김자녀", "2025-12-31", {"친족": "김자녀", "상대방": "김대표", "수입_상대방계좌_입금": True}))
    assert r["결론"] == "생계 공동" and "조심-2025-인-4482(2026.03.19)" in r["결정·해석"]


def test_married_independent_household():
    f = {"친족": "김자녀", "상대방": "김대표", "주민등록_동일세대": False, "동거_사실": "따로거주", "혼인_독립가구": True,
         "독립생계_소득": "소액_일시"}
    r = _shared(judge("김자녀", "2025-12-31", f))
    assert r["결론"] == "생계 별도" and "국심-2001-부-2282(2001.11.13)" in r["결정·해석"]
    # 소득이 없으면 분가·혼인만으로는 별도 아님
    r = _shared(judge("김자녀", "2025-12-31", {**f, "독립생계_소득": "없음"}))
    assert r["결론"] == "입력 확인 필요"
    # 소득을 모르면(미입력·모름) 혼인 독립만으로 생계 별도로 가지 않음
    for g in ({k: v for k, v in f.items() if k != "독립생계_소득"}, {**f, "독립생계_소득": "모름"}):
        assert _shared(judge("김자녀", "2025-12-31", g))["결론"] != "생계 별도"


def test_coworker_is_not_employee_relation():
    # 박동료와 이직원은 같은 법인 직원일 뿐 — 이직원과 생계를 함께하는 친족이라도 박동료와는 ②3호 아님
    j = R.judge_all(case_with({"친족": "이종숙", "상대방": "이직원", "생활비_공동부담": "공동"}), "박동료", "이종숙", "2022-12-31")
    r = _shared(j, "국기")
    assert j["판정"]["국기"].startswith("해당 없음") and r["결론"] == "해당 없음"
    assert "사전-2015-법령해석재산-0207(2015.09.25)" in r["사유"][1]
