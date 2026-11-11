"""연도 의존 전수 점검(2026-11-11) — 일감몰아주기 3종·지배주주 친족 범위, 최저한세 이월공제기간, 매입세액 공제(Claude 작성).
조문 확인: 상증법 제45조의3①(20161231·20171231·20180101·20221231·20261111 시행본)과 법률 제15224호 부칙 제10조,
상증령 제34조의2⑤·⑦(20161231·20171231·20180301)·2017.2.7. 개정 부칙 제3조, 국기령 제1조의2①(2023.3.1. 시행),
조특법 제144조①(20161231~20191231 5년·7년·10년, 20211231 10년)·법률 제17759호 부칙 제35조·제51조·서면-2022-법인-1779,
부가령 제75조7호(20190211 없음, 20190212 6개월, 20220215 1년)·부칙, 부가법 제46조③(20210630·20210701)."""
import pytest
from _helpers import call as c

E = 100_000_000
P = lambda k: {"구분": k}


# ── 1. 일감몰아주기: 사업연도별 비율·계산식 ─────────────────────────────────────────
def tg(size, ratio, hold, fy_end=None, fy_start=None, total=1000 * E, profit=100 * E):
    a = {"beneficiary": "수혜", "size": size, "sales_total": total, "sales_by_corp": {"특관": total * ratio},
         "after_tax_op_profit": profit, "people": {"갑": P("개인"), "수혜": P("법인"), "특관": P("법인")}, "family": [],
         "stakes": [["갑", "수혜", hold], ["갑", "특관", 0.60]]}
    if fy_end: a["fiscal_year_end"] = fy_end
    if fy_start: a["fiscal_year_start"] = fy_start
    return c("tunnelling_gift", a)

@pytest.mark.parametrize("size,ratio,hold,fy_end,fy_start,expect", [
    ("일반", 0.40, 0.10, "2016-12-31", None, 1.75 * E),      # (40%−15%)×(10%−3%)
    ("일반", 0.40, 0.10, "2017-12-31", None, 1.75 * E),
    ("일반", 0.40, 0.10, "2018-12-31", None, 3.5 * E),       # (40%−5%)×10%
    ("일반", 0.40, 0.10, "2026-12-31", None, 3.5 * E),
    ("중견", 0.60, 0.20, "2016-12-31", None, 1.0 * E),       # 정상거래비율 50%: (60%−50%)×(20%−10%)
    ("중견", 0.60, 0.20, "2017-12-31", None, 2.0 * E),       # 2017년 개시 사업연도부터 40%: (60%−40%)×(20%−10%)
    ("중견", 0.60, 0.20, "2017-06-30", "2016-07-01", 1.0 * E),   # 2016년 개시 사업연도 → 50%
    ("중견", 0.60, 0.20, "2018-12-31", None, 6.0 * E),       # (60%−20%)×(20%−5%)
    ("중소", 0.60, 0.20, "2016-12-31", None, 1.0 * E),       # 전 기간 (60%−50%)×(20%−10%)
    ("중소", 0.60, 0.20, "2022-12-31", None, 1.0 * E)])
def test_tunnelling_gift_by_fiscal_year(size, ratio, hold, fy_end, fy_start, expect):
    r = tg(size, ratio, hold, fy_end, fy_start)
    assert "error" not in r, r
    assert abs(r["합계"] - expect) < 2, r

def test_general_two_thirds_route_only_from_2018():
    """일반기업 거래비율 25%(정상거래비율 30% 이하, 2/3인 20% 초과)·특수관계법인 매출 1,250억 — 2018.1.1. 이후 종료분만 과세."""
    old = tg("일반", 0.25, 0.10, "2017-12-31", total=5000 * E)
    new = tg("일반", 0.25, 0.10, "2018-12-31", total=5000 * E)
    assert old["합계"] == 0 and "미충족" in old["결론"]
    assert abs(new["합계"] - 2.0 * E) < 2                    # 100억 × (25%−5%) × 10%

def test_tunnelling_gift_basis_and_range():
    assert "제34조의2" in tg("일반", 0.40, 0.10, "2017-12-31")["근거"]
    assert "제34조의2" in tg("일반", 0.40, 0.10, "2019-12-31")["근거"]
    assert "제34조의3" in tg("일반", 0.40, 0.10, "2020-12-31")["근거"]
    assert "error" in tg("일반", 0.40, 0.10, "2015-12-31")
    assert "fiscal_year_end 생략" in str(tg("일반", 0.40, 0.10)["주의"])

@pytest.mark.parametrize("fy_end,expect", [("2017-12-31", 1.75 * E), ("2019-12-31", 3.5 * E), (None, 3.5 * E)])
def test_tunnelling_gift_nts_by_fiscal_year(fy_end, expect):
    a = {"size": "일반", "op_income": 100 * E, "taxable_income": 100 * E, "tax": 0, "sales_total": 1000 * E,
         "sales_by_corp": {"A": 400 * E}, "relations": {"직접": 0.10}}
    if fy_end: a["fiscal_year_end"] = fy_end
    r = c("tunnelling_gift_nts", a)
    assert "error" not in r, r
    assert abs(r["합계"] - expect) < 2, r
    assert r["적용 비율"]["계산식_차감거래비율"] == (0.15 if fy_end == "2017-12-31" else 0.05)

def test_tunnel_intake_reads_fiscal_year():
    from korean_tax_calc_mcp.audit.agents import tunnel_intake as TI
    md = "\n".join(["## 1. 수혜법인", "| 항목 | 값 |", "|---|---|", "| 법인명 | ㈜수혜 |", "| 기업 규모 | 일반 |", "| 사업연도 | 2017.1.1.~2017.12.31. |",
                    "| 세무조정 후 영업손익 | 10,000,000,000 |", "| 각 사업연도 소득금액 | 10,000,000,000 |", "| 법인세 산출세액 | 0 |", "| 매출액 | 100,000,000,000 |",
                    "", "## 2. 수혜법인 주주", "| 주주 | 특수관계 | 지분율 |", "|---|---|---|", "| 김갑 | 본인 | 10% |"])
    j = TI.from_tables(md)
    assert j["사업연도_종료일"] == "2017-12-31" and j["입력"]["on"] == "2017-12-31" and j["입력"]["fiscal_start"] == "2017-01-01"
    j2 = TI.from_tables(md.replace("| 사업연도 | 2017.1.1.~2017.12.31. |\n", ""))
    assert j2["사업연도_종료일"] is None and "on" not in j2["입력"] and any("사업연도 종료일" in n for n in j2["확인 필요"])


# ── 2. 지배주주: 친족 범위(2023.2.28.까지 6촌 혈족·4촌 인척) ───────────────────────────
def test_dominant_shareholder_kin_scope_by_date():
    people = {k: P("개인") for k in ("조부", "부", "나", "숙부", "사촌", "오촌", "남")} | {"수혜": P("법인")}
    family = [["조부", "부", "부모자녀"], ["부", "나", "부모자녀"], ["조부", "숙부", "부모자녀"], ["숙부", "사촌", "부모자녀"], ["사촌", "오촌", "부모자녀"]]
    stakes = [["나", "수혜", 0.30], ["오촌", "수혜", 0.25], ["남", "수혜", 0.40]]
    a = {"corp": "수혜", "people": people, "family": family, "stakes": stakes}
    assert c("dominant_shareholder", {**a, "on": "2022-12-31"})["지배주주"] == "나"       # 나 + 5촌 = 55%
    assert c("dominant_shareholder", {**a, "on": "2023-12-31"})["지배주주"] == "남"       # 5촌은 친족 아님 → 남 40%
    assert c("dominant_shareholder", a)["지배주주"] == "남" and "on 생략" in c("dominant_shareholder", a)["주의"]


# ── 3. 최저한세: 미공제 세액공제 이월공제기간 ────────────────────────────────────────
def mt(year, cy, period=None):
    cf = {"year": cy, "amount": 3_000_000}
    if period: cf["period"] = period
    return c("minimum_tax_adjustment", {"year": year, "sme": True, "net_income": 400_000_000, "income_add": 50_000_000, "income_deduct": 50_000_000,
                                        "credits": [{"code": "13W", "current": 12_000_000, "carryforward": [cf]}]})

@pytest.mark.parametrize("year,cy,period,ok", [
    (2019, 2014, None, True),      # 5년 안
    (2019, 2013, None, False),     # 5년 경과(2018 사업연도까지)
    (2019, 2012, 10, True),        # 창업 중소 제10조 10년
    (2019, 2011, 7, False),        # 7년 경과
    (2020, 2015, None, True),      # 2021.1.1. 이후 신고 — 10년(서면-2022-법인-1779)
    (2020, 2014, None, False),     # 종전 5년이 2019 사업연도로 끝남 — 부칙 제51조
    (2023, 2015, None, True),
    (2023, 2014, None, False),
    (2023, 2013, 10, True),        # 종전 10년(2023까지)이 2021.1.1. 전에 지나지 않음
    (2026, 2015, None, False),     # 10년 경과(2025 사업연도까지)
    (2026, 2016, None, True)])
def test_min_tax_carryforward_period(year, cy, period, ok):
    r = mt(year, cy, period)
    assert ("결과" in r) is ok, r

def test_min_tax_carryforward_messages():
    assert "부칙 제51조" in str(mt(2023, 2014)["문제"])
    assert "5·7·10" in str(mt(2019, 2014, 6)["문제"])


# ── 4. 매입세액 공제: 확정신고기한 뒤 발급분, 간이과세자 발급 신용카드 ──────────────────────
def vi(period, **item):
    r = c("vat_input_tax_deduction", {"period": period, "filing": "확정", "items": [{"항목": "매입", "성격": "일반", "공급가액": 100_000_000, **item}]})
    assert "error" not in r, r
    return r["결과"]["공제매입세액"]

@pytest.mark.parametrize("period,supply,issued,deduct", [
    ("2018-2", "2018-10-15", "2019-03-10", 0),            # 2019.2.11.까지 공급분: 확정신고기한(2019.1.25.) 뒤 발급 → 불공제
    ("2019-1", "2019-02-11", "2019-12-01", 0),
    ("2019-1", "2019-02-12", "2019-12-01", 10_000_000),   # 6개월 이내(2020.1.25.까지)
    ("2020-1", "2020-03-15", "2021-01-20", 10_000_000),
    ("2020-1", "2020-03-15", "2021-03-10", 0),            # 6개월 초과
    ("2022-1", "2022-02-10", "2023-03-10", 0),            # 2022.2.14.까지 공급분은 6개월(2023.1.25.까지)
    ("2022-1", "2022-03-15", "2023-03-10", 10_000_000),   # 1년 이내(2023.7.25.까지)
    ("2022-1", "2022-03-15", "2023-08-01", 0)])
def test_late_invoice_window_by_supply_date(period, supply, issued, deduct):
    assert vi(period, 증빙="세금계산서", 공급시기=supply, 발급일=issued) == deduct

@pytest.mark.parametrize("period,supply,deduct", [("2020-1", None, 0), ("2021-1", None, 0), ("2021-2", None, 10_000_000),
                                                  ("2021-2", "2021-07-01", 10_000_000), ("2021-1", "2021-06-30", 0), ("2025-1", None, 10_000_000)])
def test_simplified_supplier_card_from_july_2021(period, supply, deduct):
    item = {"증빙": "신용카드", "공급자": "간이과세자_세금계산서"}
    if supply: item["공급시기"] = supply
    assert vi(period, **item) == deduct


def test_tunnelling_gift_nts_gates_on_taxation_requirement():
    """과세 요건을 충족하지 않으면 합계 0. 일반기업 2/3·1천억 요건은 2018.1.1. 이후 종료분에서만 과세 대상으로 본다."""
    base = {"size": "일반", "op_income": 100 * E, "taxable_income": 100 * E, "tax": 0, "sales_total": 5000 * E,
            "sales_by_corp": {"A": 1250 * E}, "relations": {"직접": 0.10}}            # 거래비율 25%, 특수관계법인 매출 1,250억
    old = c("tunnelling_gift_nts", {**base, "fiscal_year_end": "2017-12-31"})
    new = c("tunnelling_gift_nts", {**base, "fiscal_year_end": "2018-12-31"})
    assert old["과세 대상"] is False and old["합계"] == 0 and "미충족" in old["결론"]
    assert new["과세 대상"] is True and abs(new["합계"] - 2.0 * E) < 2                # 100억 × (25%−5%) × 10%
    small = c("tunnelling_gift_nts", {**base, "sales_total": 500 * E, "sales_by_corp": {"A": 125 * E}, "fiscal_year_end": "2018-12-31"})
    assert small["과세 대상"] is False and small["합계"] == 0                         # 25%지만 매출 125억 — 1천억 이하
