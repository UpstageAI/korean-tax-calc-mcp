"""0.38.0 rural_special_tax 정답 테스트(2026-11-12, Claude 손계산).
근거: 농어촌특별세법 제2조①·제3조1호·제4조·제5조①1호, 시행령 제4조(2016~2025 각 연말과 2026.11.12. 시행본)."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.rural_special_tax, "fn", S.rural_special_tax)(**k)


def rows(r):
    return {x["조문"]: x for x in r["계산"]["항목별"]}


def test_startup_reduction_and_rnd_credit_are_exempt_investment_and_employment_taxed():
    # 창업감면 2.75억·연구인력개발비 5,000만은 비과세, 통합투자 3,000만·통합고용 1,450만은 20% → 600만 + 290만
    r = f(year=2024, items=[{"article": "제6조", "amount": 275 * M}, {"article": "제10조", "amount": 50 * M},
                            {"article": "제24조", "amount": 30 * M}, {"article": "조세특례제한법 제29조의8", "amount": 14_500_000}])
    y = rows(r)
    assert r["결과"] == {"농어촌특별세": 8_900_000, "과세_대상_감면세액": 44_500_000, "비과세_감면세액": 325 * M}
    assert y["제6조"]["과세"] is False and "제4조제3호" in y["제6조"]["근거"]
    assert y["제10조"]["과세"] is False and "제7항" in y["제10조"]["근거"]
    assert y["제24조"]["농어촌특별세"] == 6 * M and y["제29조의8"]["농어촌특별세"] == 2_900_000


def test_decree_paragraph_number_by_year():
    assert "제6항" in rows(f(year=2022, items=[{"article": "제10조", "amount": M}]))["제10조"]["근거"]
    assert "제7항" in rows(f(year=2023, items=[{"article": "제10조", "amount": M}]))["제10조"]["근거"]


def test_list_changes_by_year():
    one = lambda y, a: f(year=y, items=[{"article": a, "amount": 10 * M}])
    # 제11조: 2019년까지 목록에 있고 2020년 삭제
    assert one(2019, "제11조")["결과"]["농어촌특별세"] == 0 and one(2020, "제11조")["결과"]["농어촌특별세"] == 2 * M
    # 제25조제1항: 2020년 한 해만 목록에 있음
    assert one(2019, "제25조제1항")["결과"]["농어촌특별세"] == 2 * M and one(2020, "제25조제1항")["결과"]["농어촌특별세"] == 0 and one(2021, "제25조제1항")["결과"]["농어촌특별세"] == 2 * M
    # 제104조의31은 2022년, 제16조의2는 2023년, 제92조는 2025년부터
    assert one(2021, "제104조의31")["결과"]["농어촌특별세"] == 2 * M and one(2022, "제104조의31")["결과"]["농어촌특별세"] == 0
    assert one(2022, "제16조의2")["결과"]["농어촌특별세"] == 2 * M and one(2023, "제16조의2")["결과"]["농어촌특별세"] == 0
    assert one(2024, "제92조")["결과"]["농어촌특별세"] == 2 * M and one(2025, "제92조")["결과"]["농어촌특별세"] == 0
    # 개정 연도에는 부칙 확인 안내
    r = one(2020, "제25조제1항")
    assert "부칙" in rows(r)["제25조제1항"]["확인"] and any("부칙" in p for p in r["판단"])
    # 법 제4조 3의3호(제16조)는 2017년 시행본부터
    assert one(2016, "제16조")["결과"]["농어촌특별세"] == 2 * M and one(2017, "제16조")["결과"]["농어촌특별세"] == 0


def test_paragraph_limited_entries_flagged():
    r = f(year=2024, items=[{"article": "제76조", "amount": M}, {"article": "제76조제1항", "amount": M}, {"article": "제104조의8제3항", "amount": M}])
    y = rows(r)
    assert "제1항만" in y["제76조"]["확인"] and "확인" not in y["제76조제1항"] and "확인" not in y["제104조의8제3항"]
    assert r["결과"]["농어촌특별세"] == 0


def test_other_law_level_exemptions():
    r = f(year=2025, items=[{"article": a, "amount": M} for a in ("제7조", "제30조의4", "제100조", "제121조의24")])
    assert r["결과"]["농어촌특별세"] == 0 and any("모두 비과세" in p for p in r["판단"])


def test_rounding_down_per_item():
    # 감면세액 1,234,567원 × 20% = 246,913.4 → 246,913
    assert f(year=2025, items=[{"article": "제24조", "amount": 1_234_567}])["결과"]["농어촌특별세"] == 246_913


def test_input_errors():
    assert "error" in f(year=2015, items=[{"article": "제24조", "amount": 1}])
    assert "error" in f(year=2024, items=[])
    assert "error" in f(year=2024, items=[{"article": "통합투자", "amount": 1}])
    assert "error" in f(year=2024, items=[{"article": "제87조", "amount": 1}])       # 저축·이자·배당 감면은 계산하지 않음
    assert "error" in f(year=2024, items=[{"article": "제24조", "amount": -1}])


def test_startup_reduction_notice_on_employment_credit():
    # 제127조④ 단서: 2024.12.31.까지 창업은 제7항 추가 감면만 고용 공제와 배제, 2025.1.1. 이후 창업은 제6조 전체(법률 제20617호 부칙 제2조)
    s = getattr(S.startup_tax_reduction, "fn", S.startup_tax_reduction)(founded_on="2021-03-02", region="수도권과밀억제권역", year=2024, first_income_year=2023, tax=550 * M,
                                                                       taxable_base=3_000 * M, youth=True, industry="통신판매업")
    assert s["결과"]["감면세액"] == 275 * M
    assert any("제29조의8" in x and "부칙 제2조" in x and "2025.1.1. 이후 창업" in x for x in s["주의"]) and any("제24조" in x and "제10조" in x for x in s["주의"])
