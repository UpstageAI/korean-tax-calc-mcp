"""근로소득자 특별세액공제(보험료·의료비·교육비)·표준세액공제 비교 정답 테스트 — 손계산·조문 대조 사례."""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp

M = 1_000_000
TOOL = "special_tax_credit"


def c(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def c_or_exc(tool, a):
    """오류가 dict로 오든 예외로 오든 문자열로 돌려준다."""
    try:
        return json.dumps(c(tool, a), ensure_ascii=False)
    except Exception as e:  # 도구 호출 단계 검증 오류
        return "EXC " + str(e)


def is_err(r):
    return isinstance(r, dict) and "error" in r


ME = {"name": "본인", "relation": "본인", "age": 40}


def call(year, salary, persons, expenses, **kw):
    return c(TOOL, {"year": year, "earner_type": "근로", "total_salary": salary,
                    "persons": persons, "expenses": expenses, **kw})


# 소득세법 제59조의4②1호·2호·4호 단서(미달액은 1호→2호→4호 순서로 뺌)
# 문턱 5,000만×3%=150만, 1호 100만−150만→0(미달 50만), 2호 200만−50만=150만, 4호 300만 → 150만×15%+300만×30% = 1,125,000
def test_medical_shortfall_order_2025():
    r = call(2025, 50 * M,
             [ME, {"name": "배우자", "relation": "배우자", "age": 40}],
             [{"kind": "의료비", "amount": 1 * M, "person": "배우자"},
              {"kind": "의료비", "amount": 2 * M, "person": "본인"},
              {"kind": "난임시술", "amount": 3 * M, "person": "배우자"}])
    m = r["계산"]["의료비"]
    assert m["1호_공제대상"] == 0
    assert m["2호_공제대상"] == 1_500_000
    assert m["4호_공제대상"] == 3 * M
    assert r["결과"]["의료비_세액공제"] == 1_125_000


# 제59조의4②1호 700만 한도, 영 제118조의5①4호 안경 1명당 50만, ①괄호 실손보험금 제외
# 문턱 120만, 일반 1,000만+50만−120만=930만→700만, 2호 본인 300만−실손 100만=200만 → (700만+200만)×15% = 1,350,000
def test_medical_general_cap_glasses_reimbursed_2025():
    r = call(2025, 40 * M,
             [ME, {"name": "부친", "relation": "직계존속", "age": 60},
              {"name": "모친", "relation": "직계존속", "age": 58}],
             [{"kind": "의료비", "amount": 10 * M, "person": "부친"},
              {"kind": "안경", "amount": 800_000, "person": "모친"},
              {"kind": "의료비", "amount": 3 * M, "person": "본인", "reimbursed": 1 * M}])
    m = r["계산"]["의료비"]
    assert m["일반"] == 10_500_000
    assert m["1호_공제대상"] == 7 * M
    assert m["2호_공제대상"] == 2 * M
    assert r["결과"]["의료비_세액공제"] == 1_350_000


# 난임시술: 2021 시행본 ②3호 20%, 2022 시행본(법 2021.12.8 개정, 2022.1.1 이후 지출분) ②4호 30%
# 문턱 90만 → (500만−90만)=410만 × 20% = 820,000 / × 30% = 1,230,000
@pytest.mark.parametrize("year,expected", [(2021, 820_000), (2022, 1_230_000)])
def test_infertility_rate_by_year(year, expected):
    r = call(year, 30 * M,
             [ME, {"name": "배우자", "relation": "배우자", "age": 35}],
             [{"kind": "난임시술", "amount": 5 * M, "person": "배우자"}])
    assert r["결과"]["의료비_세액공제"] == expected


# 6세 이하(개시일 현재) 2호 편입: 법 2023.12.31 개정, 2024.1.1 이후 지급분
# 2023: 일반 1,200만−180만=1,020만→700만 ×15% = 1,050,000
# 2024: 1호 min(900만−180만, 700만)=700만, 2호 300만 → 1,000만×15% = 1,500,000
@pytest.mark.parametrize("year,expected", [(2023, 1_050_000), (2024, 1_500_000)])
def test_child_six_or_under_by_year(year, expected):
    r = call(year, 60 * M,
             [ME, {"name": "배우자", "relation": "배우자", "age": 38},
              {"name": "자녀", "relation": "직계비속", "age": 5}],
             [{"kind": "의료비", "amount": 9 * M, "person": "배우자"},
              {"kind": "의료비", "amount": 3 * M, "person": "자녀"}])
    assert r["결과"]["의료비_세액공제"] == expected


# 제59조의4① 보험료: 일반 100만 한도 12%, 장애인전용 100만 한도 15%, 기본공제대상자(제50조①3호가 60세 이상) 아닌 부친 제외
# 일반 80만+50만=130만→100만×12%=120,000, 장애인전용 120만→100만×15%=150,000 → 270,000
def test_insurance_premium_2025():
    r = call(2025, 40 * M,
             [ME, {"name": "자녀", "relation": "직계비속", "age": 10},
              {"name": "배우자", "relation": "배우자", "age": 40, "disabled": True},
              {"name": "부친", "relation": "직계존속", "age": 55}],
             [{"kind": "보장성보험", "amount": 800_000, "person": "본인"},
              {"kind": "보장성보험", "amount": 500_000, "person": "자녀"},
              {"kind": "장애인전용보장성보험", "amount": 1_200_000, "person": "배우자"},
              {"kind": "보장성보험", "amount": 300_000, "person": "부친"}])
    assert r["계산"]["기본공제대상자"]["부친"] is False
    assert r["계산"]["보험료"]["일반_공제액"] == 120_000
    assert r["계산"]["보험료"]["장애인전용_공제액"] == 150_000
    assert r["결과"]["보험료_세액공제"] == 270_000


EDU_PERSONS = [ME, {"name": "자녀A", "relation": "직계비속", "age": 17},
               {"name": "자녀B", "relation": "직계비속", "age": 20},
               {"name": "모친", "relation": "직계존속", "age": 65}]
EDU_EXP = [{"kind": "교육비_대학원", "amount": 6 * M, "person": "본인"},
           {"kind": "교육비_초중고", "amount": 2_600_000, "person": "자녀A"},
           {"kind": "교복", "amount": 700_000, "person": "자녀A"},
           {"kind": "체험학습", "amount": 400_000, "person": "자녀A"},
           {"kind": "교육비_대학", "amount": 10 * M, "person": "자녀B", "reimbursed": 500_000},
           {"kind": "교육비_대학", "amount": 2 * M, "person": "모친"}]


# 제59조의4③: 본인 한도 없음, 초중고 1명당 300만(교복 50만·체험학습 30만, 영 제118조의6①4·6호), 대학 900만, 직계존속 일반 교육비 제외, 장학금 차감
# 600만 + min(260만+50만+30만, 300만) + min(950만, 900만) + 0 = 1,800만 × 15% = 2,700,000
def test_education_limits_2025():
    r = call(2025, 80 * M, EDU_PERSONS, EDU_EXP)
    assert r["계산"]["교육비"]["공제대상_합계"] == 18 * M
    assert r["결과"]["교육비_세액공제"] == 2_700_000


# 제61조①·영 제119조의3①: ①~③ 합계가 근로소득 산출세액 200만을 넘는 70만은 없는 것으로 함
def test_wage_tax_limit_2025():
    r = call(2025, 80 * M, EDU_PERSONS, EDU_EXP, wage_computed_tax=2 * M)
    assert r["결과"]["특별세액공제_합계"] == 2_700_000
    assert r["결과"]["한도초과액"] == 700_000
    assert r["결과"]["특별세액공제_한도반영"] == 2 * M


# 제59조의4⑨1호: 항목별 60,000(보장성 50만×12%) < 130,000 → 표준세액공제. 특별소득공제 신청 시 표준세액공제 불가
def test_standard_credit_comparison_2025():
    base = dict(year=2025, salary=30 * M, persons=[ME],
                expenses=[{"kind": "보장성보험", "amount": 500_000, "person": "본인"}])
    r = call(base["year"], base["salary"], base["persons"], base["expenses"])
    assert r["결과"]["항목별_합계"] == 60_000
    assert r["결과"]["표준세액공제"] == 130_000
    assert r["결과"]["선택"] == "표준세액공제"
    assert r["결과"]["적용_세액공제"] == 130_000
    r2 = call(base["year"], base["salary"], base["persons"], base["expenses"], special_income_deduction=1 * M)
    assert r2["결과"]["표준세액공제_적용가능"] is False
    assert r2["결과"]["선택"] == "항목별"
    assert r2["결과"]["적용_세액공제"] == 60_000


# 제59조의4① 괄호: 일용근로자 제외 — 계산하지 않음
def test_daily_worker_rejected():
    r = c(TOOL, {"year": 2025, "earner_type": "일용근로", "total_salary": 10 * M,
                 "persons": [ME], "expenses": [{"kind": "의료비", "amount": 1 * M, "person": "본인"}]})
    assert is_err(r)


# 지출의 person이 공제대상자 목록에 없으면 계산하지 않음, 정의되지 않은 인자는 거부
def test_unknown_person_and_extra_arg_rejected():
    r = call(2025, 30 * M, [ME], [{"kind": "의료비", "amount": 1 * M, "person": "없는사람"}])
    assert is_err(r)
    s = c_or_exc(TOOL, {"year": 2025, "earner_type": "근로", "total_salary": 30 * M,
                        "persons": [ME], "expenses": [], "bonus_rate": 1})
    assert "bonus_rate" in s
