"""연장근로수당 비과세 판정에서 월정액급여를 같은 호출 항목으로 산정(earned_income_gross_pay).

근거: 소득세법 시행령 제17조① 후단 — 월정액급여는 매월 직급별로 받는 봉급·급료·보수·임금·수당,
그 밖에 이와 유사한 성질의 급여(상여 등 부정기적인 급여, 영 제12조 실비변상적 급여, [2021.2.17 개정~]
영 제17조의4 복리후생적 급여는 제외)의 총액에서 「근로기준법」 연장·야간·휴일근로 급여를 뺀 급여.
한도: 2016~2017 150만, 2018 190만, 2019~2025 210만, 2026 260만(직전 총급여 2,500만→3,000만(2020)→3,700만(2026)).
연장근로수당 비과세 연 240만원(영 제17조② 1호). 근로소득공제는 법 제47조①.
"""
import asyncio
import json
from korean_tax_calc_mcp.server import mcp


def c(a):
    return json.loads(asyncio.run(mcp.call_tool("earned_income_gross_pay", a)).content[0].text)


def 기본항목(prior=30_000_000, **연장facts):
    return [
        {"kind": "급여", "amount": 25_200_000},
        {"kind": "자가운전보조금", "amount": 3_000_000,
         "facts": {"months": 12, "vehicle": "본인소유", "business_use": True, "actual_travel_reimbursed": False}},
        {"kind": "식사대", "amount": 2_400_000, "facts": {"months": 12, "meal_provided": False}},
        {"kind": "연장근로수당", "amount": 4_000_000,
         "facts": {"eligible_occupation": True, "prior_year_gross": prior, **연장facts}},
        {"kind": "상여", "amount": 6_000_000},
        {"kind": "사회보험료_본인부담분_회사대납", "amount": 1_800_000},
    ]


def 연장(r):
    return next(x for x in r["항목별"] if x["kind"] == "연장근로수당")


# 2026: 포함 = 급여 25,200,000 + 자가운전보조금 과세분 600,000(비과세 240만은 영 제12조 실비변상 → 제외)
#        + 식사대 2,400,000(비과세 식사대 근거는 영 제17조의2 — 제외 대상 아님) + 본인부담 사회보험료 대납 1,800,000
#        = 30,000,000 ÷ 12 = 2,500,000 ≤ 2,600,000 → 비과세 min(400만, 240만) = 240만, 과세 160만
#  제외 = 상여 600만(부정기), 연장근로수당 400만(차감)
#  총급여 = 2,520만 + 60만 + 0 + 160만 + 600만 + 180만 = 3,520만
#  근로소득공제 = 350만 + 400만 + (3,520만−1,500만)×15% = 1,053만
def test_2026_월정액급여_항목으로_산정():
    r = c({"year": 2026, "items": 기본항목()})
    assert "error" not in r, r
    판 = r["판단"][0]
    assert "월정액급여 2,500,000원" in 판["결론"]
    assert sum(x["금액"] for x in 판["포함"]) == 30_000_000
    제외 = {(x["kind"], x["금액"]) for x in 판["제외"]}
    assert ("자가운전보조금", 2_400_000) in 제외 and ("상여", 6_000_000) in 제외 and ("연장근로수당", 4_000_000) in 제외
    assert ("식사대", 2_400_000) in {(x["kind"], x["금액"]) for x in 판["포함"]}
    assert 연장(r)["비과세액"] == 2_400_000 and 연장(r)["과세액"] == 1_600_000
    assert r["결과"]["총급여액"] == 35_200_000
    assert r["결과"]["근로소득공제"] == 10_530_000
    # 출력 순서는 입력 순서 유지
    assert [x["kind"] for x in r["항목별"]][3] == "연장근로수당"


# 2020: 한도 210만 — 같은 항목이면 월정액 250만 > 210만 → 연장근로수당 전액 과세
#  식사대 2020 월한도 10만 → 비과세 120만·과세 120만이지만 월정액급여에는 240만 전액 포함
#  총급여 = 2,520만 + 60만 + 120만 + 400만 + 600만 + 180만 = 3,880만
def test_2020_월정액급여_한도초과_과세():
    r = c({"year": 2020, "items": 기본항목(prior=25_000_000)})
    assert "error" not in r, r
    assert "월정액급여 2,500,000원" in r["판단"][0]["결론"]
    assert "복리후생" not in r["판단"][0]["근거"]   # 2020년 영 제17조①에는 제17조의4 제외 문구 없음
    assert 연장(r)["비과세액"] == 0 and 연장(r)["과세액"] == 4_000_000
    assert r["결과"]["총급여액"] == 38_800_000


# 직접 준 monthly_regular_wage는 그대로 사용(항목 산정 안 함)
def test_월정액급여_직접입력_우선():
    r = c({"year": 2020, "items": 기본항목(prior=25_000_000, monthly_regular_wage=2_000_000)})
    assert "판단" not in r
    assert 연장(r)["비과세액"] == 2_400_000


# 직무발명보상금 — 매월 정기 지급인지 알 수 없으면 입력 확인 필요(항목 지목)
def test_지급형태_모호한_항목은_입력확인():
    items = 기본항목() + [{"kind": "직무발명보상금", "amount": 1_000_000, "facts": {"retired": False}}]
    r = c({"year": 2026, "items": items})
    assert "입력 확인 필요" in r["error"]
    assert "regular_monthly" in r["필요 입력"]["직무발명보상금"]
    assert any("직무발명보상금" in m for m in r["문제"])
    # 부정기라고 밝히면 제외 → 월정액 250만 그대로
    items[-1]["facts"]["regular_monthly"] = False
    r = c({"year": 2026, "items": items})
    assert "월정액급여 2,500,000원" in r["판단"][0]["결론"]


# 단체보험료 100만: 2026은 비과세 70만이 영 제17조의4 복리후생 급여(2021~ 제외), 과세 30만은 지급 형태 필요
#  regular_monthly=True면 포함 → (3,000만 + 30만) ÷ 12 = 2,525,000
#  2019는 제17조의4 제외 문구가 없으므로 100만 전체가 지급 형태 확인 대상
def test_복리후생_급여_연도별():
    단체 = {"kind": "단체보험료", "amount": 1_000_000}
    r = c({"year": 2026, "items": 기본항목() + [dict(단체)]})
    assert "regular_monthly" in r["필요 입력"]["단체보험료"]
    r = c({"year": 2026, "items": 기본항목() + [dict(단체, facts={"regular_monthly": True})]})
    assert "월정액급여 2,525,000원" in r["판단"][0]["결론"]
    assert ("단체보험료", 700_000) in {(x["kind"], x["금액"]) for x in r["판단"][0]["제외"]}
    r = c({"year": 2019, "items": 기본항목(prior=25_000_000) + [dict(단체)]})
    assert any("1,000,000원" in m for m in r["문제"])


# 근무월수: 연장근로수당 facts.months 우선 — 급여 2,500만 ÷ 10개월 = 250만
def test_근무월수_연장근로수당_facts():
    r = c({"year": 2026, "items": [
        {"kind": "급여", "amount": 25_000_000},
        {"kind": "연장근로수당", "amount": 1_000_000,
         "facts": {"eligible_occupation": True, "prior_year_gross": 20_000_000, "months": 10}}]})
    assert "월정액급여 2,500,000원" in r["판단"][0]["결론"]
    assert 연장(r)["비과세액"] == 1_000_000


def test_근무월수_항목마다_다르면_입력확인():
    items = 기본항목()
    items[2]["facts"]["months"] = 10
    r = c({"year": 2026, "items": items})
    assert "입력 확인 필요" in r["error"]
    assert "months" in r["필요 입력"]["연장근로수당"]


# 경계: 31,200,000 ÷ 12 = 2,600,000 → 이하(비과세) / 31,200,006 ÷ 12 = 2,600,000.5 → 초과(과세)
def test_한도_경계_절사전_비교():
    def run(급여):
        return c({"year": 2026, "items": [
            {"kind": "급여", "amount": 급여},
            {"kind": "연장근로수당", "amount": 1_000_000,
             "facts": {"eligible_occupation": True, "prior_year_gross": 30_000_000}}]})
    assert 연장(run(31_200_000))["비과세액"] == 1_000_000
    assert 연장(run(31_200_006))["비과세액"] == 0


# 직전연도 총급여는 항목으로 알 수 없음 → 항상 입력 필요
def test_직전연도총급여_누락():
    r = c({"year": 2026, "items": 기본항목(prior=None)})
    assert r["필요 입력"]["연장근로수당"] == ["prior_year_gross"]


# 급여 항목이 없으면 월정액급여를 산정할 수 없음
def test_급여항목_없으면_입력확인():
    r = c({"year": 2026, "items": [
        {"kind": "상여", "amount": 5_000_000},
        {"kind": "연장근로수당", "amount": 1_000_000,
         "facts": {"eligible_occupation": True, "prior_year_gross": 30_000_000}}]})
    assert "monthly_regular_wage" in r["필요 입력"]["연장근로수당"]
