"""최저한세 조정(minimum_tax_adjustment)·별지 제4호서식 최저한세조정계산서·별지 제8호서식(갑) 공제감면세액 및 추가납부세액합계표(갑) (Claude 2026-11-06).

서식 원문: 법인세법 시행규칙 별지 제4호서식 <개정 2019. 3. 20.> 2쪽, 별지 제8호서식(갑) <개정 2026. 3. 20.> 5쪽 전부 대조.
조문: 조세특례제한법 제132조제1항(최저한세율, 각 호 감면 등), 제144조(미공제 세액공제 10년 이월, 이월분 먼저 공제),
시행령 제126조제5항(경정 때 배제 순서: 2의2 손금산입·익금불산입 → 3 세액공제(같은 조문 이월분은 나중 발생분부터) → 4 감면 → 5 소득공제·비과세).

손계산(2025 사업연도, 중소기업, 법인세율 9%·19%·21%·24%, 최저한세율 7%):
CASE_A — ⑩1 500,000,000 + ⑩2 120,000,000 − ⑩3 70,000,000(특별상각 30,000,000 포함) = ⑩4 550,000,000.
  ② ⑪0 = 550,000,000 + 10,000,000 − 5,000,000 = 555,000,000, ⑪5 = ⑪8 = 555,000,000 − 55,000,000 = 500,000,000,
  산출세액 18,000,000 + 300,000,000 × 19% = 75,000,000, 감면 20,000,000·공제 20,000,000 → ⑫5 35,000,000.
  ③ ⑩7 = 550,000,000 + 30,000,000 = 580,000,000, ⑪8 = 580,000,000 + 5,000,000 − 55,000,000 = 530,000,000, 최저한세 37,100,000.
  미달 2,100,000 → 경정 순서상 특별상각부터 배제: 산출세액(과세표준 + X) − 40,000,000 ≥ 37,100,000이 되는 가장 작은 X.
  산출세액은 이 도구의 법인세 산출세액(corp_tax)처럼 원 미만 반올림이므로 X = 11,052,629
  (511,052,629 → 18,000,000 + 311,052,629 × 19% = 77,099,999.51 → 77,100,000, X − 1이면 77,099,999.32 → 77,099,999). ⑤ ⑫5 = 37,100,000.
CASE_B — ⑩1 400,000,000(조정 없음), 산출세액 56,000,000, 최저한세 28,000,000.
  대상 감면 112 10,000,000, 대상 공제 14Z(제7조의4) 6,000,000, 13W(제24조) 당기 12,000,000 + 이월 2022년 3,000,000·2023년 4,000,000,
  적용제외 16B(중소기업 일반 연구·인력개발비, 제132조①3호 "중소기업이 아닌 자만") 8,000,000.
  ② ⑫5 = 56,000,000 − 10,000,000 − 25,000,000 = 21,000,000, 미달 7,000,000 → 세액공제를 조문 순서로: 14Z 6,000,000, 13W 당기분 1,000,000.
  ⑤ 감면 10,000,000, 공제 18,000,000, ⑫5 28,000,000. 이월: 14Z 2025년분 6,000,000, 13W 2025년분 1,000,000.
  별지8(갑): 13W ⑤ 7,000,000 ⑥ 12,000,000 ⑦ 18,000,000, 14Z ⑥ 6,000,000 ⑦ 0, 112 ③④ 10,000,000, 16B ③④ 8,000,000,
  261 = 10,000,000 + 18,000,000 = 28,000,000, 262 총계 = 8,000,000 + 28,000,000 = 36,000,000. 적용제외 뒤 세액 20,000,000.
"""
import openpyxl, pytest, shutil
from test_form_templates import build, c, recalc

S4, S8 = "별지4 최저한세조정", "별지8(갑) 공제감면합계"
T = "minimum_tax_adjustment"
CASE_A = {"year": 2025, "sme": True, "net_income": 500_000_000, "income_add": 120_000_000, "income_deduct": 70_000_000,
          "special_depreciation": 30_000_000, "donation_excess": 10_000_000, "donation_carryover": 5_000_000,
          "loss_carryforward": 55_000_000,
          "reductions": [{"code": "112", "amount": 20_000_000}], "credits": [{"code": "13W", "current": 20_000_000}]}
CASE_B = {"year": 2025, "sme": True, "net_income": 400_000_000, "income_add": 50_000_000, "income_deduct": 50_000_000,
          "reductions": [{"code": "112", "amount": 10_000_000}],
          "credits": [{"code": "14Z", "current": 6_000_000},
                      {"code": "13W", "current": 12_000_000, "carryforward": [{"year": 2022, "amount": 3_000_000}, {"year": 2023, "amount": 4_000_000}]},
                      {"code": "16B", "current": 8_000_000}]}


def _r(a):
    r = c(T, a)
    assert "결과" in r, r
    return r["결과"]


def test_case_a_special_depreciation_cut_first():
    r = _r(CASE_A)
    assert r["과세표준"] == {"감면후": 500_000_000, "최저한세": 530_000_000}
    assert r["산출세액"]["감면후"] == 75_000_000 and r["최저한세"] == 37_100_000 and r["산출세액"]["최저한세"] == 37_100_000
    assert (r["감면세액"], r["세액공제"], r["감면후세액"]) == (20_000_000, 20_000_000, 35_000_000)
    assert r["최저한세_미달"] is True
    assert r["조정감"] == {"준비금": 0, "특별상각": 11_052_629, "익금불산입손금산입": 0, "소득공제": 0, "비과세": 0,
                         "세액공제": 0, "감면세액": 0}
    j = r["조정"]
    assert (j["과세표준"], j["산출세액"], j["감면세액"], j["세액공제"], j["차감세액"]) == (511_052_629, 77_100_000, 20_000_000, 20_000_000, 37_100_000)
    assert r["차감세액"] == 37_100_000
    assert r["세율"] == {"감면후": 0.19, "최저한세": 0.07} and j["세율"] == 0.19
    assert r["배제_내역"] == [{"코드": "106", "구분": "특별상각 및 특례자산 감가상각비", "배제액": 11_052_629, "처리": "손금불산입(유보)"}]
    assert r["이월_미공제"] == []


def test_case_b_credits_cut_in_article_order_then_current_first():
    r = _r(CASE_B)
    assert r["산출세액"]["감면후"] == 56_000_000 and r["최저한세"] == 28_000_000
    assert (r["감면세액"], r["세액공제"], r["감면후세액"]) == (10_000_000, 25_000_000, 21_000_000)
    assert r["조정감"]["세액공제"] == 7_000_000 and r["조정감"]["감면세액"] == 0 and r["조정감"]["특별상각"] == 0
    assert (r["조정"]["세액공제"], r["조정"]["감면세액"], r["조정"]["차감세액"]) == (18_000_000, 10_000_000, 28_000_000)
    assert r["배제_내역"] == [{"코드": "14Z", "구분": "상생결제 지급금액에 대한 세액공제", "배제액": 6_000_000, "처리": "이월(조세특례제한법 제144조)"},
                          {"코드": "13W", "구분": "통합투자세액공제(일반)", "배제액": 1_000_000, "처리": "이월(조세특례제한법 제144조)"}]
    assert r["이월_미공제"] == [{"코드": "14Z", "발생연도": 2025, "금액": 6_000_000}, {"코드": "13W", "발생연도": 2025, "금액": 1_000_000}]
    assert r["최저한세_적용제외"] == {"감면세액": 0, "세액공제": 8_000_000}
    assert r["적용제외_차감후세액"] == 20_000_000
    b8 = r["별지8"]
    assert b8["13W"] == {"전기이월액": 7_000_000, "당기발생액": 12_000_000, "공제세액": 18_000_000}
    assert b8["14Z"] == {"전기이월액": 0, "당기발생액": 6_000_000, "공제세액": 0}
    assert b8["112"] == {"대상세액": 10_000_000, "감면세액": 10_000_000}
    assert b8["16B"] == {"대상세액": 8_000_000, "감면세액": 8_000_000}
    assert r["공제감면세액_총계"] == 36_000_000


def test_carryforward_same_article_newest_cut_first():
    # 13W만: 당기 2,000,000 + 이월 2021 3,000,000·2023 4,000,000, 미달 5,000,000 → 당기 2,000,000, 2023분 3,000,000 배제
    a = dict(CASE_B, reductions=[], credits=[{"code": "13W", "current": 2_000_000,
                                              "carryforward": [{"year": 2021, "amount": 3_000_000}, {"year": 2023, "amount": 4_000_000}]}])
    a["net_income"] = 100_000_000  # 산출세액 9,000,000, 최저한세 7,000,000, 감면후 9,000,000 − 9,000,000 = 0 → 미달 7,000,000
    r = _r(a)
    assert r["산출세액"]["감면후"] == 9_000_000 and r["최저한세"] == 7_000_000 and r["조정감"]["세액공제"] == 7_000_000
    assert r["이월_미공제"] == [{"코드": "13W", "발생연도": 2025, "금액": 2_000_000}, {"코드": "13W", "발생연도": 2023, "금액": 4_000_000},
                            {"코드": "13W", "발생연도": 2021, "금액": 1_000_000}]
    assert r["별지8"]["13W"] == {"전기이월액": 7_000_000, "당기발생액": 2_000_000, "공제세액": 2_000_000}


def test_filing_order_reduction_first_is_lost_not_carried():
    r = _r(dict(CASE_B, exclusion_order=["112"]))
    assert r["조정감"]["감면세액"] == 7_000_000 and r["조정감"]["세액공제"] == 0
    assert r["조정"]["차감세액"] == 28_000_000 and r["이월_미공제"] == []
    assert r["배제_내역"] == [{"코드": "112", "구분": "중소기업에 대한 특별세액감면", "배제액": 7_000_000, "처리": "소멸(이월 없음)"}]
    assert r["별지8"]["112"] == {"대상세액": 10_000_000, "감면세액": 3_000_000}


def test_special_cost_fully_cut_then_credits():
    # 106이 5,000,000뿐: ③ 118 505,000,000 → 최저한세 35,350,000, ② 125 = 75,000,000 − 20,000,000 − 30,000,000 = 25,000,000.
    # 106 전부 배제 → 산출세액(505,000,000) 75,950,000, 남은 미달 35,350,000 − 25,950,000 = 9,400,000 → 13W 당기분에서 배제.
    a = dict(CASE_A, special_depreciation=5_000_000, credits=[{"code": "13W", "current": 30_000_000}])
    r = _r(a)
    assert r["최저한세"] == 35_350_000 and r["감면후세액"] == 25_000_000
    assert r["조정감"]["특별상각"] == 5_000_000 and r["조정감"]["세액공제"] == 9_400_000
    assert (r["조정"]["과세표준"], r["조정"]["산출세액"], r["조정"]["세액공제"], r["조정"]["차감세액"]) == (505_000_000, 75_950_000, 20_600_000, 35_350_000)
    assert [x["코드"] for x in r["배제_내역"]] == ["106", "13W"]
    assert r["이월_미공제"] == [{"코드": "13W", "발생연도": 2025, "금액": 9_400_000}]


def test_statutory_order_credits_then_reductions():
    # ② 125 = 56,000,000 − 30,000,000 − 2,000,000 = 24,000,000, 미달 4,000,000 → 14Z 2,000,000(이월), 112 2,000,000(소멸)
    r = _r(dict(CASE_B, reductions=[{"code": "112", "amount": 30_000_000}], credits=[{"code": "14Z", "current": 2_000_000}]))
    assert r["조정감"]["세액공제"] == 2_000_000 and r["조정감"]["감면세액"] == 2_000_000
    assert [(x["코드"], x["배제액"], x["처리"]) for x in r["배제_내역"]] == [("14Z", 2_000_000, "이월(조세특례제한법 제144조)"),
                                                                     ("112", 2_000_000, "소멸(이월 없음)")]
    assert r["별지8"]["112"] == {"대상세액": 30_000_000, "감면세액": 28_000_000} and r["조정"]["차감세액"] == 28_000_000


def test_filing_order_credit_code():
    # 신고 때 13W를 먼저 배제: 당기분 12,000,000 중 7,000,000, 14Z는 그대로
    r = _r(dict(CASE_B, exclusion_order=["13W"]))
    assert r["배제_내역"] == [{"코드": "13W", "구분": "통합투자세액공제(일반)", "배제액": 7_000_000, "처리": "이월(조세특례제한법 제144조)"}]
    assert r["이월_미공제"] == [{"코드": "13W", "발생연도": 2025, "금액": 7_000_000}]
    assert r["별지8"]["13W"]["공제세액"] == 12_000_000 and r["별지8"]["14Z"]["공제세액"] == 6_000_000
    assert any("납세의무자" in j["결론"] for j in c(T, dict(CASE_B, exclusion_order=["13W"]))["판단"])


def test_judgement_list_statutory():
    j = c(T, CASE_B)["판단"]
    assert isinstance(j, list) and all({"항목", "결론", "근거"} <= set(x) for x in j)
    assert any("제126조제5항" in x["근거"] for x in j)


def test_income_item_not_cut_after_shortfall_covered():
    # CASE_A에 준비금 10,000,000 추가(103에 포함): ③ 118 540,000,000 → 최저한세 37,800,000.
    # 106 배제만으로 메워지면 105는 그대로(조정감 0) — 남은 미달이 0이면 다음 소득 항목을 배제하지 않는다.
    a = dict(CASE_A, reserve=10_000_000)
    r = _r(a)
    assert r["최저한세"] == 37_800_000
    assert r["조정감"]["준비금"] == 0 and r["조정감"]["특별상각"] > 0
    assert [x["코드"] for x in r["배제_내역"]] == ["106"]
    assert r["조정"]["차감세액"] >= 37_800_000 and r["조정"]["차감세액"] - 37_800_000 <= 1


def test_income_deduction_cut_after_credits_and_reductions():
    # 116 = 117 = 20,000,000: ② 118 380,000,000 → 산출세액 52,200,000, ③ 118 400,000,000 → 최저한세 28,000,000.
    # 감면 10,000,000·공제 14Z 20,000,000 → ② 125 22,200,000, 미달 5,800,000 → 세액공제(3호)에서 배제, 117(5호)은 그대로.
    a = dict(CASE_B, income_deduction=20_000_000, income_deduction_mt=20_000_000, credits=[{"code": "14Z", "current": 20_000_000}])
    r = _r(a)
    assert r["산출세액"]["감면후"] == 52_200_000 and r["최저한세"] == 28_000_000
    assert r["조정감"]["세액공제"] == 5_800_000 and r["조정감"]["소득공제"] == 0
    assert [x["코드"] for x in r["배제_내역"]] == ["14Z"]


def test_income_deduction_last_when_nothing_else():
    # 116 = 117 = 300,000,000, 감면·공제 없음: ② 118 100,000,000 → 9,000,000, ③ 118 400,000,000 → 28,000,000.
    # 117 배제 X: 산출세액(100,000,000 + X) ≥ 28,000,000인 가장 작은 X = 152,631,577 (반올림 경계, corp_tax 기준).
    a = dict(CASE_B, reductions=[], credits=[], income_deduction=300_000_000, income_deduction_mt=300_000_000)
    r = _r(a)
    assert r["조정감"]["소득공제"] == 152_631_577 and r["조정"]["산출세액"] == 28_000_000
    assert r["배제_내역"] == [{"코드": "117", "구분": "최저한세 적용대상 소득공제", "배제액": 152_631_577, "처리": "과세표준에 포함(적용 배제)"}]


def test_negative_base_everything_cut_in_order():
    # 101 53,000,000 + 102 14,000,000 − 103 65,000,000 = 2,000,000, 116 = 117 = 86,000,000 → ② 118 △84,000,000(산출세액 0).
    # ③ 118 = 2,000,000 + 105 23,000,000 + 106 15,000,000 − 86,000,000 + 86,000,000 = 40,000,000 → 최저한세 2,800,000.
    # 106·105를 다 빼도 과세표준 △46,000,000(세액 0) → 공제 76,000,000·감면 36,000,000 전부 → 117에서
    # 산출세액(△46,000,000 + X) ≥ 2,800,000인 가장 작은 X = 77,111,106 → 과세표준 31,111,106, 산출세액 2,800,000.
    a = {"year": 2025, "sme": True, "net_income": 53_000_000, "income_add": 14_000_000, "income_deduct": 65_000_000,
         "special_depreciation": 15_000_000, "reserve": 23_000_000, "income_deduction": 86_000_000, "income_deduction_mt": 86_000_000,
         "reductions": [{"code": "112", "amount": 36_000_000}],
         "credits": [{"code": "14Z", "current": 2_000_000}, {"code": "13W", "current": 56_000_000, "carryforward": [{"year": 2020, "amount": 18_000_000}]}]}
    r = _r(a)
    assert r["과세표준"] == {"감면후": -84_000_000, "최저한세": 40_000_000} and r["최저한세"] == 2_800_000
    assert r["조정감"] == {"준비금": 23_000_000, "특별상각": 15_000_000, "익금불산입손금산입": 0, "소득공제": 77_111_106, "비과세": 0,
                         "세액공제": 76_000_000, "감면세액": 36_000_000}
    j = r["조정"]
    assert (j["과세표준"], j["산출세액"], j["감면세액"], j["세액공제"], j["차감세액"]) == (31_111_106, 2_800_000, 0, 0, 2_800_000)
    assert [x["코드"] for x in r["배제_내역"]] == ["106", "105", "14Z", "13W", "112", "117"]


def test_not_below_minimum_tax():
    r = _r(dict(CASE_B, reductions=[], credits=[{"code": "13W", "current": 5_000_000}]))
    assert r["최저한세_미달"] is False and r.get("조정") is None
    assert r["감면후세액"] == 51_000_000 and r["차감세액"] == 51_000_000
    assert set(r["조정감"].values()) == {0} and r["배제_내역"] == [] and r["이월_미공제"] == []


def test_general_company_tiers_and_short_year():
    a = {"year": 2025, "sme": False, "net_income": 15_000_000_000, "income_add": 0, "income_deduct": 0}
    assert _r(a)["최저한세"] == 1_600_000_000          # 100억 × 10% + 50억 × 12%
    assert _r(a)["세율"] == {"감면후": 0.19, "최저한세": 0.12}   # 최저한세 표시는 최저한세 구간(법인세율 표가 아님)
    assert _r(dict(a, net_income=7_500_000_000, months=6))["최저한세"] == 800_000_000   # 연 환산 150억 → 16억 × 6/12
    assert _r(dict(a, net_income=1_000_000_000, grace_year=2))["최저한세"] == 80_000_000  # 졸업 후 3년 이내 8%
    assert _r(dict(a, net_income=1_000_000_000, grace_year=5))["최저한세"] == 90_000_000  # 그다음 2년 9%


def test_required_amounts():
    # 101·102·103은 필수 — 빠지면 0으로 계산하지 않는다
    try:
        r = c(T, {"year": 2025})
    except Exception:
        return
    assert "결과" not in r, r


def test_form_inputs_listed():
    i = {x["이름"]: x["값"] for x in c(T, CASE_A)["계산식_입력"]}
    assert i == {"당기순이익": 500_000_000, "익금산입": 120_000_000, "손금산입": 70_000_000, "준비금": 0, "특별상각": 30_000_000,
                 "기부금한도초과": 10_000_000, "기부금이월손금산입": 5_000_000, "이월결손금": 55_000_000, "비과세소득": 0,
                 "최저한세대상_비과세": 0, "최저한세대상_익금불산입손금산입": 0, "소득공제": 0, "최저한세대상_소득공제": 0, "유예연차": 0}


@pytest.mark.parametrize("bad, word", [
    (dict(CASE_B, credits=[{"code": "13M", "current": 1_000_000}]), "중소기업"),          # 중소기업 R&D는 적용제외 코드(16B)
    (dict(CASE_A, special_depreciation=80_000_000), "income_deduct"),                    # 105+106+114 ≤ 103
    (dict(CASE_A, nontaxable_mt=1), "nontaxable"),                                       # 113 ≤ 112
    (dict(CASE_A, income_deduction_mt=1), "income_deduction"),                           # 117 ≤ 116
    (dict(CASE_B, credits=[{"code": "13W", "current": 0, "carryforward": [{"year": 2014, "amount": 1}]}]), "10년"),
    (dict(CASE_B, credits=[{"code": "ZZZ", "current": 1}]), "코드"),
    (dict(CASE_B, reductions=[{"code": "13W", "amount": 1}]), "감면"),                    # 공제 코드를 감면으로
    (dict(CASE_B, exclusion_order=["999"]), "exclusion_order"),
    (dict(CASE_B, exclusion_order=["16B"]), "exclusion_order"),                         # 적용제외 공제는 배제 대상 아님
    (dict(CASE_B, credits=[{"code": "189", "current": 1}]), "101"),                      # 외국납부세액 세부 줄은 101에 합산
])
def test_input_errors(bad, word):
    r = c(T, bad)
    assert "error" in r and any(word in p for p in r["문제"]), r


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_form_sheets_values_and_checks(tmp_path):
    path = build(tmp_path, [{"tool": T, "args": CASE_B}])
    wb = recalc(path, tmp_path)
    w4, w8 = wb[S4], wb[S8]
    want4 = {"D6": 400_000_000, "D9": 400_000_000, "E12": 400_000_000, "D23": 400_000_000, "E23": 400_000_000, "G23": 400_000_000,
             "D27": 56_000_000, "E27": 28_000_000, "G27": 56_000_000, "D28": 10_000_000, "F28": 0, "G28": 10_000_000,
             "D29": 25_000_000, "F29": 7_000_000, "G29": 18_000_000, "D30": 21_000_000, "G30": 28_000_000}
    for addr, v in want4.items():
        assert w4[addr].value == v, addr
    rows = {w8[f"D{r}"].value: r for r in range(1, w8.max_row + 1) if w8[f"D{r}"].value}
    assert (w8[f"E{rows['13W']}"].value, w8[f"F{rows['13W']}"].value, w8[f"G{rows['13W']}"].value) == (7_000_000, 12_000_000, 18_000_000)
    assert (w8[f"E{rows['112']}"].value, w8[f"F{rows['112']}"].value) == (10_000_000, 10_000_000)
    assert (w8[f"E{rows['16B']}"].value, w8[f"F{rows['16B']}"].value) == (8_000_000, 8_000_000)
    assert w8[f"F{rows['130']}"].value == 10_000_000 and w8[f"G{rows['149']}"].value == 18_000_000
    assert w8[f"F{rows['110']}"].value == 8_000_000 and w8[f"G{rows['150']}"].value == 28_000_000 and w8[f"G{rows['151']}"].value == 36_000_000
    for ws in (w4, w8):
        checks = [x.value for row in ws.iter_rows() for x in row if x.value in ("일치", "확인 필요")]
        assert checks and set(checks) == {"일치"}, ws.title


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice 없음")
def test_not_below_leaves_columns_4_5_blank(tmp_path):
    a = dict(CASE_B, reductions=[], credits=[{"code": "13W", "current": 5_000_000}])
    wb = recalc(build(tmp_path, [{"tool": T, "args": a}]), tmp_path)
    w4 = wb[S4]
    assert w4["D30"].value == 51_000_000 and w4["G30"].value in (None, "") and w4["F29"].value in (None, "")


def test_form_sheet_layout(tmp_path):
    wb = openpyxl.load_workbook(build(tmp_path, [{"tool": T, "args": CASE_A}]))
    assert S4 in wb.sheetnames and S8 in wb.sheetnames
    assert wb.sheetnames.index(S8) == wb.sheetnames.index(S4) + 1
    w4, w8 = wb[S4], wb[S8]
    assert w4["C2"].value == "최저한세조정계산서" and w8["C2"].value.startswith("공제감면세액 및")
    assert w4["D30"].value.startswith("=") and w4["G23"].value.startswith("=IF(")
    codes = [w8[f"D{r}"].value for r in range(1, w8.max_row + 1) if w8[f"D{r}"].value and w8[f"D{r}"].value != "코드"]
    assert len(codes) == 165 and len(set(codes)) == 165          # 158줄 + 소계·합계 7줄
    assert w8.page_setup.fitToHeight == 0
