"""실사용 점검(2026-11-04)에서 나온 세무조정 도구 결함 회귀 테스트.

손계산 근거
- 법인세법 시행령 제19조의2①9의2호: 중소기업의 외상매출금·미수금으로 회수기일이 2년 이상 지난 것(특수관계인 거래분 제외),
  ③2호에 따라 손비로 계상한 사업연도의 손금(결산조정). 2020.2.11. 개정(2020.1.1. 이후 개시 사업연도분부터).
- 대손 사례(손계산):
  갑 파산 9,001,000 인정 / 을 부도어음 5,000,000 중 1,000 부인(유보) / 병 회수기일 2년 미경과 3,999,000 부인(유보) /
  정 전기 장부 대손·부인(유보 20,000,000) 후 당기 소멸시효 완성 → 손금산입 20,000,000(△유보).
  세법상 당기 대손금 = 9,001,000 + 4,999,000 + 20,000,000 = 34,000,000.
  세법상 전기말 채권 = 1,980,000,000 + 20,000,000 = 2,000,000,000 → 실적률 1.7%.
  세법상 당기말 채권 = 2,800,000,000 + 3,999,000 + 1,000 = 2,804,000,000 → 한도 47,668,000, 한도초과 12,332,000.
- 퇴직연금운용자산에서 지급해 퇴직급여충당금과 상계한 6,000,000: 손금불산입 퇴직연금충당금(유보) + 손금산입 퇴직급여충당금(△유보).
"""
import asyncio, json

import pytest

from korean_tax_calc_mcp.server import mcp


def raw(tool, a):
    r = asyncio.run(mcp.call_tool(tool, a))
    return (r.content[0] if hasattr(r, "content") else r[0][0]).text


def c(tool, a):
    return json.loads(raw(tool, a))


def c_or_exc(tool, a):
    try:
        return c(tool, a)
    except Exception as e:  # 스키마 검증 단계 오류
        return {"error": "EXC " + str(e)}


STATUTORY = {"익금산입", "손금불산입", "손금산입", "익금불산입"}
DISPOSITIONS = {"유보", "△유보", "상여", "배당", "기타소득", "기타사외유출", "기타"}


# ── bad_debt_adjustment ─────────────────────────────────────────────────
BOOK = {"opening": 30_000_000, "offset": 18_000_000, "provision": 48_000_000, "closing": 60_000_000}
갑 = {"kind": "파산", "amount": 9_001_000, "arose_in": "당기", "booked": "상계", "account": "외상매출금", "detail": "거래처 갑 파산"}
을 = {"kind": "부도6개월", "amount": 5_000_000, "arose_in": "당기", "instrument": "받을어음", "months_since_default": 9,
     "mortgage": False, "date": "2025-03-10", "booked": "상계", "account": "받을어음", "detail": "거래처 을 부도어음"}
병 = {"kind": "회수기일2년경과", "amount": 3_999_000, "arose_in": "당기", "months_since_due": 18, "related_party": False,
     "booked": "상계", "account": "외상매출금", "detail": "거래처 병(회수기일 2024.6.30.)"}
정 = {"kind": "소멸시효완성", "amount": 20_000_000, "arose_in": "당기", "date": "2025-08-20", "booked": "전기부인",
     "account": "외상매출금", "detail": "거래처 정, 전기 장부 대손·부인(유보 20,000,000)"}
MOCK = {"year": 2025, "sme": True, "prior_excess": 6_000_000, "book": BOOK,
        "receivables_prev_end_book": 1_980_000_000, "receivables_end_book": 2_800_000_000}


def _adj(r):
    return {(x["구분"], x["조정"], x["소득처분"]): x["금액"] for x in r["결과"]["세무조정"]}


def test_bad_debt_overdue_two_years_kind():   # 점검 목록 #39
    base = dict(MOCK, prior_excess=0, book={"opening": 0, "offset": 0, "provision": 0, "closing": 0},
                receivables_prev_end_book=1_000_000_000, receivables_end_book=1_000_000_000)
    w = dict(병, booked="손비")
    r = c("bad_debt_adjustment", dict(base, writeoffs=[w]))
    assert "error" not in r, r
    assert r["계산"]["세법상 당기 대손금"] == 0 and r["계산"]["세법상 당기말 채권"] == 1_003_999_000
    assert sum(v for (g, j, d), v in _adj(r).items() if j == "손금불산입" and d == "유보") == 3_999_000
    assert "9의2" in json.dumps(r["판단"], ensure_ascii=False)
    # 2년 경과 → 인정(결산조정, 비망가액 없음)
    ok = c("bad_debt_adjustment", dict(base, writeoffs=[dict(w, months_since_due=24)]))
    assert ok["계산"]["세법상 당기 대손금"] == 3_999_000 and ok["계산"]["세법상 당기말 채권"] == 1_000_000_000
    # 특수관계인 거래분·중소기업 아님·2019 사업연도(9의2호 신설 전)는 부인
    for args in (dict(base, writeoffs=[dict(w, months_since_due=30, related_party=True)]),
                 dict(base, sme=False, writeoffs=[dict(w, months_since_due=30)]),
                 dict(base, year=2019, writeoffs=[dict(w, months_since_due=30)])):
        x = c("bad_debt_adjustment", args)
        assert x["계산"]["세법상 당기 대손금"] == 0, args


def test_bad_debt_case_matches_hand_calculation():   # 점검 목록 #39·#41
    r = c("bad_debt_adjustment", dict(MOCK, writeoffs=[갑, 을, 병, 정]))
    k = r["계산"]
    assert k["세법상 당기 대손금"] == 34_000_000
    assert k["세법상 전기말 채권"] == 2_000_000_000
    assert k["대손실적률"] == 0.017
    assert k["세법상 당기말 채권"] == 2_804_000_000
    assert r["결과"]["한도"] == 47_668_000 and r["결과"]["한도초과"] == 12_332_000
    a = _adj(r)
    assert a[("대손금 부인(비망가액)", "손금불산입", "유보")] == 1_000
    assert sum(v for (g, j, d), v in a.items() if j == "손금불산입" and d == "유보" and "부인" in g and "비망" not in g) == 3_999_000
    assert sum(v for (g, j, d), v in a.items() if j == "손금산입" and d == "△유보" and "전기 한도초과" not in g) == 20_000_000
    assert a[("한도초과", "손금불산입", "유보")] == 12_332_000
    assert a[("전기 한도초과", "손금산입", "△유보")] == 6_000_000
    # 상계 합계 9,001,000 + 5,000,000 + 3,999,000 = 18,000,000 → 장부 상계와 일치, 경고 없음
    assert "≠" not in json.dumps(r["판단"], ensure_ascii=False)
    rows = r["서식_표"]["34_대손금"]
    for x in rows:
        assert x["상계_시인"] + x["상계_부인"] + x["손비_시인"] + x["손비_부인"] == x["금액"]
    assert not any(x["채권명세"].startswith("거래처 정") and (x["상계_시인"] or x["상계_부인"]) for x in rows)


def test_bad_debt_unexplained_offset_not_attached_to_unbooked_item():   # 점검 목록 #40
    # 실사용 입력 그대로: 병을 넣지 못해 장부 상계 18,000,000 중 3,999,000이 설명되지 않음, 정은 booked 없음
    정_원래 = {"kind": "소멸시효완성", "amount": 20_000_000, "arose_in": "당기", "date": "2025-08-20", "account": "외상매출금",
             "memo_excluded": True, "detail": "거래처 정, 당기 회계처리 없음"}
    r = c("bad_debt_adjustment", dict(MOCK, writeoffs=[갑, 을, 정_원래]))
    row = next(x for x in r["서식_표"]["34_대손금"] if x["채권명세"].startswith("거래처 정"))
    assert row["상계_시인"] == 0 and row["상계_부인"] == 0
    assert "3,999,000" in json.dumps(r["판단"], ensure_ascii=False)


def test_bad_debt_prior_year_cause_never_negative_and_wording():   # 점검 목록 #46·#47
    r = c("bad_debt_adjustment", {"year": 2025, "sme": True, "book": {"opening": 0, "offset": 0, "provision": 0, "closing": 0},
                                  "receivables_prev_end_book": 0, "receivables_end_book": 0,
                                  "writeoffs": [{"kind": "소멸시효완성", "amount": 100_000_000, "arose_in": "전기", "booked": "손비"}]})
    assert r["계산"]["세법상 전기말 채권"] >= 0
    s = json.dumps(r, ensure_ascii=False)
    assert "추심" not in s and "경정" in s


def test_bad_debt_prior_cause_with_prior_disallowed_booking_is_not_double_counted():   # 점검 목록 #42
    r = c("bad_debt_adjustment", dict(MOCK, writeoffs=[갑, 을, dict(정, arose_in="전기")]))
    k = r["계산"]
    assert k["세법상 전기말 채권"] == 1_980_000_000          # 장부에서 이미 지운 채권을 또 빼지 않음
    assert not any(j == "손금불산입" and v == 20_000_000 for (g, j, d), v in _adj(r).items())


def test_bad_debt_labels_and_schema():   # 점검 목록 #43·#44·#45·#48
    w = [{"kind": "파산", "amount": 9_001_000, "arose_in": "당기", "instrument": "외상매출금", "booked": "상계"}]
    r = c("bad_debt_adjustment", dict(MOCK, prior_excess=0, book={"opening": 0, "offset": 9_001_000, "provision": 9_001_000, "closing": 0}, writeoffs=w))
    assert "error" not in r, r
    assert r["판단"][0]["항목"].startswith("파산") and "회수불능" not in r["판단"][0]["항목"]
    assert r["서식_표"]["34_대손금"][0]["사유"] == "파산"
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "bad_debt_adjustment")
    assert "국회초과" not in tool.description
    wdesc = json.dumps(tool.input_schema["properties"]["writeoffs"], ensure_ascii=False)
    for k in ("소멸시효완성", "화해·확정판결", "부도6개월", "회수불능", "파산", "회수기일2년경과", "전기부인"):
        assert k in wdesc, k


def test_bad_debt_negative_amount_rejected():   # 점검 목록 #25
    r = c_or_exc("bad_debt_adjustment", dict(MOCK, writeoffs=[dict(갑, amount=-1_000_000)]))
    assert "error" in r


# ── retirement_allowance_adjustment ──────────────────────────────────────
RET = {"year": 2025, "allowance": {"opening": 80_000_000, "closing": 100_000_000, "provision": 30_000_000, "paid_cash": 4_000_000, "paid_pension": 6_000_000},
       "prior_disallowed": 70_000_000, "estimate": {"lump_sum": 400_000_000, "actuarial": 380_000_000}, "salary": {"total": 500_000_000},
       "conversion_fund": 0, "pension": {"asset_closing": 414_000_000, "prior_deducted": 300_000_000, "book_provision": 0, "book_paid": 0}}


def test_retirement_typo_label_and_judgment():   # 점검 목록 #24·#50·#51·#52
    r = c("retirement_allowance_adjustment", RET)
    s = json.dumps(r, ensure_ascii=False)
    assert "유적" not in s
    a = _adj(r)
    assert a[("퇴직연금충당금(지급 상계)", "손금불산입", "유보")] == 6_000_000
    assert a[("퇴직급여충당금(퇴직연금 지급 대체)", "손금산입", "△유보")] == 6_000_000
    j = next(x for x in r["판단"] if x["항목"] == "퇴직금 지급 상계")["결론"]
    assert r["계산"]["퇴직급여충당금_상계"] == 4_000_000 and r["계산"]["퇴직연금충당금_상계"] == 6_000_000
    assert "4,000,000" in j and "6,000,000" in j and "세무상 충당금 10,000,000원 상계" not in j
    r2 = c("retirement_allowance_adjustment", {"year": 2025, "allowance": {"opening": 100_000_000, "closing": 100_000_000}, "prior_disallowed": 10_000_000,
                                               "estimate": {"lump_sum": 300_000_000}, "salary": {"total": 500_000_000},
                                               "pension": {"asset_closing": 200_000_000, "prior_deducted": 50_000_000, "book_provision": 0}})
    assert "부족 150,000,000원(손금산입·△유보)" in json.dumps(r2["판단"], ensure_ascii=False)


# ── income_adjustment_total ─────────────────────────────────────────────
def test_income_adjustment_statutory_labels():   # 점검 목록 #20·#55
    r = c("income_adjustment_total", {"net_income": 300_000_000, "items": [
        {"항목": "법인세비용", "종류": "법인세비용", "금액": 20_000_000},
        {"항목": "수입배당금 익금불산입", "종류": "수입배당금 익금불산입", "금액": 7_200_000}]})
    adj = {e["구분"]: e["조정"] for e in r["결과"]["세무조정"]}
    assert adj == {"법인세비용": "손금불산입", "수입배당금 익금불산입": "익금불산입"}
    desc = json.dumps(r["계산식_입력"], ensure_ascii=False)
    assert "법인세비용 (손금불산입)" in desc and "(익금불산입)" in desc and "법인세비용 (익금산입)" not in desc
    assert r["결과"]["차가감소득금액"] == 312_800_000
    r = c("income_adjustment_total", {"net_income": 100_000_000, "items": [{"항목": "기부금", "종류": "기부금 한도초과", "금액": 1_000_000}]})
    assert next(e for e in r["결과"]["세무조정"] if e["구분"] == "기부금 한도초과")["조정"] == "손금불산입"


def test_income_adjustment_disposition_closed_set():   # 점검 목록 #55
    r = c("income_adjustment_total", {"net_income": 300_000_000, "items": [
        {"항목": "세무조정 합계", "종류": "기타", "금액": 1_000_000, "방향": "가산", "소득처분": "1~6 합계"}]})
    assert "error" in r and "소득처분" in json.dumps(r, ensure_ascii=False)
    ok = c("income_adjustment_total", {"net_income": 300_000_000, "items": [
        {"항목": "증빙 없음", "종류": "기타", "금액": 1_000_000, "방향": "가산", "소득처분": "대표자상여"}]})
    assert ok["결과"]["세무조정"][0]["소득처분"] == "상여"


@pytest.mark.parametrize("name,disp,조정,dirn", [
    ("기업업무추진비 한도초과액", None, "손금불산입", 1), ("상각부인액", None, "손금불산입", 1),
    ("한도초과", "기타사외유출", "손금불산입", 1), ("퇴직급여충당금 한도초과", None, "손금불산입", 1),
    ("간접외국납부세액 익금산입(Gross-up)", None, "익금산입", 1), ("임대보증금 간주익금", None, "익금산입", 1),
    ("인정이자", "상여", "익금산입", 1), ("대손충당금 한도초과", None, "손금불산입", 1)])
def test_income_adjustment_accepts_upstream_names(name, disp, 조정, dirn):   # 점검 목록 #21
    it = {"항목": name, "종류": name, "금액": 1_000_000}
    if disp: it["소득처분"] = disp
    r = c("income_adjustment_total", {"net_income": 100_000_000, "items": [it]})
    assert "error" not in r, r
    assert r["결과"]["차가감소득금액"] == 100_000_000 + dirn * 1_000_000
    e = r["결과"]["세무조정"][0]
    assert e["조정"] == 조정 and e["소득처분"] in DISPOSITIONS


def test_income_adjustment_takes_upstream_settlements_as_is():   # 점검 목록 #21·#22
    ent = c("entertainment_adjustment", {"year": 2025, "sme": True, "ledger": [
        {"항목": "증빙 없음", "금액": 3_000_000, "증빙": "없음"}, {"항목": "일반", "금액": 52_000_000, "증빙": "적격"}]})
    dep = c("depreciation_adjustment", {"year": 2025, "method": "정률법", "useful_life": 8, "acquisition_cost": 200_000_000,
                                        "booked_depreciation": 25_000_000, "accumulated_dep_begin": 100_000_000, "expensed_capex": 5_500_000,
                                        "prior_book_value": 100_000_000, "prior_disallowed": 8_000_000})
    items = ent["결과"]["세무조정"] + dep["결과"]["세무조정"]
    r = c("income_adjustment_total", {"net_income": 100_000_000, "items": items})
    assert "error" not in r, r
    add = sum(x["금액"] for x in items if x["조정"] in ("익금산입", "손금불산입"))
    sub = sum(x["금액"] for x in items if x["조정"] in ("손금산입", "익금불산입"))
    assert r["결과"]["차가감소득금액"] == 100_000_000 + add - sub


def test_income_adjustment_negative_net_income_and_amount():   # 점검 목록 #19·#25
    r = c_or_exc("income_adjustment_total", {"net_income": -10_000_000, "items": [{"항목": "법인세비용", "종류": "법인세비용", "금액": 1_000_000}]})
    assert "error" not in r and r["결과"]["차가감소득금액"] == -9_000_000
    r = c_or_exc("income_adjustment_total", {"net_income": 100_000_000, "items": [{"항목": "x", "종류": "법인세비용", "금액": -1_000_000}]})
    assert "error" in r


# ── 세무조정 공통 형식 {구분, 조정, 금액, 소득처분} ─────────────────────
def _all_have_convention(entries):
    assert entries, "세무조정 비어 있음"
    for e in entries:
        assert e["조정"] in STATUTORY and e["소득처분"] in DISPOSITIONS and "구분" in e and isinstance(e["금액"], int), e


def test_adjustment_entries_share_convention():   # 점검 목록 #22·#23
    from test_gold_gaps2 import RENTALS
    ent = c("entertainment_adjustment", {"year": 2025, "sme": True, "ledger": [
        {"항목": "증빙 없음", "금액": 3_000_000, "증빙": "없음"}, {"항목": "사적", "금액": 1_000_000, "성격": "사적사용"},
        {"항목": "영수증", "금액": 50_000, "증빙": "영수증 등"}, {"항목": "일반", "금액": 52_000_000, "증빙": "적격"}]})
    _all_have_convention(ent["결과"]["세무조정"])
    assert "대표자상여" not in ent["결과"]["소득처분별_합계"] and ent["결과"]["소득처분별_합계"]["상여"] == 4_000_000
    _all_have_convention(c("bad_debt_adjustment", dict(MOCK, writeoffs=[갑, 을, 병, 정]))["결과"]["세무조정"])
    _all_have_convention(c("depreciation_adjustment", {"year": 2025, "method": "정률법", "useful_life": 8, "acquisition_cost": 200_000_000,
                                                       "booked_depreciation": 25_000_000, "accumulated_dep_begin": 100_000_000,
                                                       "expensed_capex": 5_500_000, "prior_book_value": 100_000_000, "prior_disallowed": 8_000_000})["결과"]["세무조정"])
    _all_have_convention(c("foreign_tax_credit", {"year": 2025, "base": 100_000_000, "base_includes_grossup": False, "method": "세액공제", "countries": [{
        "country": "네덜란드", "foreign_income": 130_000_000, "direct_tax": 2_000_000, "subsidiaries": [{
            "name": "A", "dividend": 100_000_000, "withholding_tax": 1_500_000, "received_on": "2025-03-31", "ownership": 0.15,
            "holding_months": 12, "resource_dev": False, "sub_income": 200_000_000, "sub_tax": 40_000_000, "participation_exempt": False}]}]})["결과"]["세무조정"])
    _all_have_convention(c("corporate_deemed_rent_income", {"year": 2024, "rentals": RENTALS, "financial_income": 100000, "rate": 0.05})["결과"]["세무조정"])
    g = c("asset_grant_reserve", {"year": 2025, "kind": "국고보조금", "received": 100_000_000, "assets": [
        {"asset": "기계", "cost": 200_000_000, "used": 100_000_000, "depreciable": True, "depreciation_this_year": 40_000_000}]})
    _all_have_convention(g["세무조정"])


# ── entertainment_adjustment ────────────────────────────────────────────
def test_entertainment_output_is_strict_json_and_keeps_2025_market_rate():   # 점검 목록 #11·#53·#54
    t = raw("entertainment_adjustment", {"year": 2025, "sme": True, "ledger": [
        {"항목": "일반 접대비", "금액": 52_000_000, "증빙": "적격"}, {"항목": "전통시장", "금액": 4_000_000, "증빙": "적격", "성격": "전통시장"}]})
    assert "Infinity" not in t and "NaN" not in t
    json.dumps(json.loads(t), allow_nan=False)
    r = json.loads(t)
    assert r["계산"]["전통시장등비율"] == 0.2


# ── return_precheck ────────────────────────────────────────────────────
@pytest.mark.parametrize("tax", ["부가", None])
def test_return_precheck_vat_does_not_crash(tax):   # 점검 목록 #12
    a = {"data": {}} if tax is None else {"data": {}, "tax": tax}
    r = c("return_precheck", a)
    assert "자료 부족" in r and "error" not in r
    r = c("return_precheck", dict(a, data={"공통매입원장.과세기간": [{"기간": "2025-1"}], "공통매입원장.자산": [{"이름": "x"}],
                                           "공통매입원장.신고": {"2025-1": {}}}))
    assert "error" not in r


# ── depreciation_adjustment ────────────────────────────────────────────
def test_depreciation_deemed_capex_label_matches_basis():   # 점검 목록 #58
    r = c("depreciation_adjustment", {"year": 2025, "method": "정액법", "useful_life": 40, "acquisition_cost": 800_000_000,
                                      "booked_depreciation": 20_000_000, "accumulated_dep_begin": 100_000_000, "expensed_capex": 40_000_000,
                                      "prior_book_value": 700_000_000, "prior_disallowed": 0})
    j = next(x for x in r["판단"] if x["항목"].startswith("즉시상각의제"))
    assert "제31조②" in j["근거"] and "제31조②" in j["항목"]
    r = c("depreciation_adjustment", {"year": 2025, "method": "정액법", "useful_life": 40, "acquisition_cost": 800_000_000,
                                      "booked_depreciation": 20_000_000, "accumulated_dep_begin": 100_000_000, "expensed_capex": 4_000_000,
                                      "prior_book_value": 700_000_000, "prior_disallowed": 0})
    j = next(x for x in r["판단"] if x["항목"].startswith("즉시상각의제"))
    assert "제31조③" in j["근거"] and "제31조③" in j["항목"]


# ── financial_income_aggregate ─────────────────────────────────────────
def test_financial_unnamed_interest_and_non_grossup_label():   # 점검 목록 #59·#60
    items = [{"kind": "예금이자", "amount": 8_000_000}, {"kind": "비영업대금이익", "amount": 5_000_000},
             {"kind": "비상장법인현금배당", "amount": 12_000_000}, {"kind": "상장법인현금배당", "amount": 6_000_000},
             {"kind": "투자신탁환매이익", "amount": 3_000_000, "components": [{"asset": "채권", "gain": 3_000_000}]},
             {"kind": "외국법인배당", "amount": 4_000_000, "withheld": False}]
    base = c("financial_income_aggregate", {"year": 2025, "items": items})
    d = next(x for x in base["계산식_입력"] if x["이름"] == "배당비대상소득")
    assert d["값"] == 7_000_000 and "출자공동사업자배당" not in d["설명"] and "외국법인배당" in d["설명"]
    r = c("financial_income_aggregate", {"year": 2025, "items": items + [{"kind": "비실명이자", "amount": 2_000_000}]})
    assert "error" not in r, r
    assert r["결과"] == base["결과"]          # 분리과세(제14조③3호) — 합계·합산액 제외
    j = next(x for x in r["판단"] if x["항목"] == "비실명이자")
    assert "제129조②2호" in j["근거"] and "45%" in j["이유"]


# ── common_input_tax ──────────────────────────────────────────────────
CIT = {"year": 2025, "period": "2기", "filing": "확정",
       "supplies": {"예정": {"taxable": 280_000_000, "exempt": 220_000_000}, "확정": {"taxable": 320_000_000, "exempt": 180_000_000}},
       "ledger": [{"항목": "과세사업 원재료", "매입세액": 15_000_000, "사용처": "과세"}, {"항목": "면세사업 포장재", "매입세액": 4_000_000, "사용처": "면세"},
                  {"항목": "거래처 명절선물", "매입세액": 300_000, "사용처": "불공제"}, {"항목": "임원 승용차", "매입세액": 3_000_000, "사용처": "불공제"},
                  {"항목": "공통 비품·용역", "매입세액": 6_000_000, "사용처": "공통"}],
       "prior_common_input_tax": 4_000_000, "prior_nondeductible": 1_760_000}


def test_common_input_tax_labels():   # 점검 목록 #61·#62
    r = c("common_input_tax", CIT)
    s = json.dumps(r["판단"], ensure_ascii=False)
    assert "과세전용(18,300,000" not in s and "18,760,000" in s
    직전 = {x["이름"]: x for x in r["계산식_입력"] if x["이름"].startswith("직전")}
    assert all("입력 없음" in x["설명"] for x in 직전.values()) and len(직전) == 2   # 서식 시트가 참조해 이름은 남기되 입력 안 한 값임을 밝힘
    r = c("common_input_tax", dict(CIT, prior_period_supplies={"taxable": 300_000_000, "exempt": 200_000_000}))
    직전 = {x["이름"]: x for x in r["계산식_입력"] if x["이름"].startswith("직전")}
    assert 직전["직전과세공급가액"]["값"] == 300_000_000 and "입력 없음" not in 직전["직전과세공급가액"]["설명"]
