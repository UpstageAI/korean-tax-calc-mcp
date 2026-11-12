"""0.32.0 provision_reserve_ledger 정답 테스트(2026-11-12, Claude 손계산).
근거: 법인세법 제40조①(2016·2026 시행본 같음), 제33조~제35조. 해석: 법인세과-1341, 서면인터넷방문상담2팀-1962, 사전-2023-법규법인-0866."""
from korean_tax_calc_mcp import server as S

M = 1_000_000


def f(**k):
    return getattr(S.provision_reserve_ledger, "fn", S.provision_reserve_ledger)(**k)


def rows(r):
    return {x["year"]: x for x in r["계산"]["연도별"]}


def test_three_cohorts_full_provision_half_cost():
    # 적립 1억(2022)·2억(2023)·3억(2024), 유효기간 2년, 사용률 30%·40%·10%(20% 소멸), 설정 사용률 100%, 부담률 50%
    r = f(grants=[{"year": 2022, "amount": 100 * M}, {"year": 2023, "amount": 200 * M}, {"year": 2024, "amount": 300 * M}],
          valid_years=2, usage_pattern=[0.3, 0.4, 0.1], expected_usage_rate=1.0, cost_ratio=0.5)
    y = rows(r)
    # 2022: 설정 5,000만, 사용 1억×30%×50% = 1,500만 → 유보 3,500만
    assert (y[2022]["충당부채_설정_손금불산입"], y[2022]["사용_손금산입"], y[2022]["유보_기말"]) == (50 * M, 15 * M, 35 * M)
    # 2023: 설정 1억, 사용 = 2022분 2,000만 + 2023분 3,000만 → 유보 8,500만
    assert (y[2023]["충당부채_설정_손금불산입"], y[2023]["사용_손금산입"], y[2023]["유보_기말"]) == (100 * M, 50 * M, 85 * M)
    # 2024: 설정 1.5억, 사용 = 500만 + 4,000만 + 4,500만 = 9,000만, 2022분 환입 5,000만−4,000만 = 1,000만, 소멸 적립액 2,000만
    assert (y[2024]["사용_손금산입"], y[2024]["환입_익금불산입"], y[2024]["소멸_적립액"], y[2024]["유보_기말"]) == (90 * M, 10 * M, 20 * M, 135 * M)
    # 2025: 사용 1,000만 + 6,000만, 2023분 환입 2,000만, 소멸 4,000만 → 유보 4,500만, 순액 △9,000만
    assert (y[2025]["사용_손금산입"], y[2025]["환입_익금불산입"], y[2025]["소멸_적립액"], y[2025]["유보_기말"], y[2025]["세무조정_순액"]) == (70 * M, 20 * M, 40 * M, 45 * M, -90 * M)
    # 2026: 사용 1,500만, 2024분 환입 3,000만, 소멸 6,000만 → 유보 0
    assert (y[2026]["사용_손금산입"], y[2026]["환입_익금불산입"], y[2026]["소멸_적립액"], y[2026]["유보_기말"]) == (15 * M, 30 * M, 60 * M, 0)
    t = r["결과"]["합계"]
    assert t["충당부채_설정_손금불산입"] == t["사용_손금산입"] + t["환입_익금불산입"] == 300 * M and r["결과"]["유보_기말"] == 0
    assert t["소멸_적립액"] == 120 * M and "2027년_이후_예정" not in r["계산"]


def test_default_expected_rate_equals_actual_no_reversal():
    # 설정 사용률 생략 = 실제 사용률 합 80% → 환입 없음, 유보는 사용으로만 소멸
    r = f(grants=[{"year": 2023, "amount": 100 * M}], valid_years=2, usage_pattern=[0.3, 0.4, 0.1])
    y = rows(r)
    assert y[2023]["충당부채_설정_손금불산입"] == 80 * M and y[2023]["유보_기말"] == 50 * M
    assert y[2025]["환입_익금불산입"] == 0 and y[2025]["소멸_적립액"] == 20 * M and y[2025]["유보_기말"] == 0
    assert "환입할 충당부채 없음" in r["판단"][2]["결론"]


def test_usage_exceeds_provision_is_current_expense():
    # 설정 사용률 50%인데 실제 80% 사용 → 설정 잔액(5,000만)을 넘는 3,000만은 그해 비용, 세무조정 없음
    r = f(grants=[{"year": 2023, "amount": 100 * M}], valid_years=2, usage_pattern=[0.3, 0.4, 0.1], expected_usage_rate=0.5)
    y = rows(r)
    assert y[2023]["사용_손금산입"] == 30 * M and y[2024]["사용_손금산입"] == 20 * M and y[2024]["설정초과_사용_당기비용"] == 20 * M
    assert y[2025]["사용_손금산입"] == 0 and y[2025]["설정초과_사용_당기비용"] == 10 * M and y[2024]["유보_기말"] == 0
    assert r["결과"]["합계"]["충당부채_설정_손금불산입"] == r["결과"]["합계"]["사용_손금산입"] == 50 * M


def test_events_after_2026_are_listed_not_computed():
    r = f(grants=[{"year": 2025, "amount": 100 * M}], valid_years=3, usage_pattern=[0.2, 0.3, 0.2, 0.1], expected_usage_rate=1.0)
    y = rows(r)
    assert set(y) == {2025, 2026} and y[2026]["유보_기말"] == 100 * M - 20 * M - 30 * M
    later = r["계산"]["2027년_이후_예정"]
    assert [x["연도"] for x in later] == [2027, 2028] and later[1]["환입_예정"] == 20 * M and later[1]["소멸_예정_적립액"] == 20 * M
    assert any("2027년_이후_예정" in s for s in r["주의"])


def test_valid_zero_years_expires_same_year():
    r = f(grants=[{"year": 2024, "amount": 10 * M}], valid_years=0, usage_pattern=[0.6], expected_usage_rate=1.0)
    y = rows(r)[2024]
    assert (y["충당부채_설정_손금불산입"], y["사용_손금산입"], y["환입_익금불산입"], y["소멸_적립액"], y["유보_기말"]) == (10 * M, 6 * M, 4 * M, 4 * M, 0)


def test_warranty_kind_notes_and_basis():
    r = f(grants=[{"year": 2024, "amount": 10 * M}], valid_years=1, usage_pattern=[0.5, 0.5], kind="판매보증")
    assert "제40조①" in r["근거"] and any("법인세과-1341" in s for s in r["해석"])
    assert not any("고객충성제도" in s for s in r["주의"])
    p = f(grants=[{"year": 2024, "amount": 10 * M}], valid_years=1, usage_pattern=[0.5, 0.5])
    assert any("고객충성제도" in s for s in p["주의"])


def test_input_errors():
    g = [{"year": 2024, "amount": 10 * M}]
    assert "error" in f(grants=g, valid_years=1, usage_pattern=[0.7, 0.4])                      # 합 1 초과
    assert "error" in f(grants=g, valid_years=1, usage_pattern=[0.3, 0.3, 0.3])                 # 유효기간보다 김
    assert "error" in f(grants=[{"year": 2015, "amount": 1}], valid_years=1, usage_pattern=[0.5])
    assert "error" in f(grants=[{"year": 2024, "amount": 1}, {"year": 2024, "amount": 2}], valid_years=1, usage_pattern=[0.5])
    assert "error" in f(grants=[], valid_years=1, usage_pattern=[0.5])


def test_find_tool_routes():
    g = getattr(S.find_tool, "fn", S.find_tool)
    for q in ("마일리지충당부채 세무조정 유보", "포인트 유효기간 소멸 법인세", "판매보증충당부채 손금불산입"):
        assert "provision_reserve_ledger" in str(g(q)), q
