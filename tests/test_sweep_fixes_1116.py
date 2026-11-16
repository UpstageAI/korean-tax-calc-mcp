"""전 도구 점검(2026-11-16, 0.57.2 기준) 결함 수정 — 0.58.1.

기대값은 YYYY-MM-DD로 넣은 같은 입력의 결과(날짜 형식 결함 A2~A9)이거나 손계산(아래 주석)이다. 구현 결과를 옮겨 적지 않았다.
원문 대조(법제처, 2026-11-16 조회):
  소득세법 제48조(2017.1.1. 시행본) 제2항 — 퇴직소득금액이 근속연수공제에 미달하면 퇴직소득금액을 공제액으로 → 퇴직소득 0이면 과세표준 0 (A1)
  상속세 및 증여세법 제45조의3제1항(2024.9.15. 시행본) — 제2호의 '이익'(세후영업이익 × 비율 × 비율)을 증여받은 것으로 봄 (A10)
  같은 법 시행령 제34조의3제12항·제13항 — 세후영업이익·출자관계별 계산(음수 처리 명문 없음)
  소득세법 제45조제1항(2025.1.1. 시행본) — 결손금은 사업소득금액 계산에서 생겨 근로·연금·기타·이자·배당소득금액에서 공제 ((b)4 income_loss_offset)
  부가가치세법 제45조제1항 — 대손세액 = 대손금액 × 10/110, 회수분은 회수한 대손금액 기준 ((b)4 vat_bad_debt_credit)
"""
import asyncio
import copy
import json
import os
import re

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine import inputs as chk

HERE = os.path.dirname(os.path.abspath(__file__))


def call(tool, args):
    S._reset_call_memo()
    r = asyncio.run(S.mcp.call_tool(tool, copy.deepcopy(args)))   # 도구가 입력 dict를 고쳐 쓰는 경우가 있어 호출마다 사본
    return json.loads(r.content[0].text)


def strip(d):
    """호출마다 달라지는 꼬리(호출_id·엑셀·안내)를 뺀 결과."""
    if isinstance(d, dict):
        return {k: strip(v) for k, v in d.items() if k not in ("호출_id", "엑셀", "안내")}
    if isinstance(d, list):
        return [strip(v) for v in d]
    return d


ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")


def to_form(o, form):
    """모든 YYYY-MM-DD 문자열을 다른 꼴로 바꾼 사본."""
    if isinstance(o, str):
        m = ISO.match(o)
        if not m:
            return o
        y, mo, d = m.groups()
        return {"compact": f"{y}{mo}{d}", "dot": f"{y}.{mo}.{d}", "slash": f"{y}/{mo}/{d}",
                "dot_short": f"{y}. {int(mo)}. {int(d)}.", "korean": f"{y}년 {int(mo)}월 {int(d)}일"}[form]
    if isinstance(o, dict):
        return {k: to_form(v, form) for k, v in o.items()}
    if isinstance(o, list):
        return [to_form(v, form) for v in o]
    return o


# ── 날짜 정규화 단위 ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, want", [
    ("20250131", "2025-01-31"), ("2025.01.31", "2025-01-31"), ("2025. 1. 31.", "2025-01-31"), ("2025/1/31", "2025-01-31"),
    ("2025-1-31", "2025-01-31"), ("2025년 1월 31일", "2025-01-31"), ("2025-01-31", "2025-01-31"),
])
def test_normalize_date_forms(raw, want):
    assert chk.normalize_date_str("d", raw) == want


@pytest.mark.parametrize("raw", ["2025-1", "2025-2", "2025-06", "13W", "101", "", "bad-date", "2025-01-31T09:00", "2025.01/31"])
def test_normalize_leaves_non_dates(raw):
    assert chk.normalize_date_str("d", raw) == raw          # 연도-기수·연월·코드·시각 붙은 값·섞인 구분자는 그대로


def test_normalize_by_name_only():
    args = {"transfer_date": "20250101", "period": "2025-1", "code": "20250101", "amount": "20250101",
            "items": [{"공급시기": "2025.03.02", "코드": "20250302", "on": "2025/3/2"}], "notice_due": "20260731"}
    out = chk.normalize_date_args(args)
    assert out["transfer_date"] == "2025-01-01" and out["notice_due"] == "2026-07-31"
    assert out["period"] == "2025-1" and out["code"] == "20250101" and out["amount"] == "20250101"   # 날짜 자리가 아니면 그대로
    assert out["items"][0] == {"공급시기": "2025-03-02", "코드": "20250302", "on": "2025-03-02"}


def test_not_a_real_date_is_input_error():
    r = call("vat_return_general", {"year": 2025, "period": "2", "sales_invoice": 100_000_000, "e_filing": True, "filed_on": "20260230"})
    assert "error" in r and "filed_on" in r["error"] and "YYYY-MM-DD" in r["error"] and "예:" in r["error"]


def test_to_date_same_on_every_python():
    # date.fromisoformat은 3.11부터 '20250101'도 받는다 — to_date는 판과 무관하게 YYYY-MM-DD만
    assert chk.to_date("d", "2025-01-01").isoformat() == "2025-01-01"
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        chk.to_date("d", "20250101")


# ── A2~A9: YYYYMMDD로 넣어도 YYYY-MM-DD와 같은 결과 + 손계산 ─────────────────────

DATE_CASES = {
    # A2 정액법 5년, 2025.7.1. 사용 개시 → 120,000,000 ÷ 5 × 6/12 = 12,000,000, 시인부족 12,000,000 − 8,000,000 = 4,000,000
    "A2": ("depreciation_adjustment", {"year": 2025, "method": "정액법", "useful_life": 5, "acquisition_cost": 120_000_000,
                                       "booked_depreciation": 8_000_000, "accumulated_dep_begin": 0, "in_service_date": "2025-07-01",
                                       "fy_start": "2025-01-01"}, {"상각범위액": 12_000_000, "시인부족액": 4_000_000}),
    # A3 건물 2022년 제2기 취득 → 2024년 제2기 면세전용: 경과 4기 × 5% → 40,000,000 × 80% = 32,000,000
    "A3": ("vat_exempt_use_deemed_supply", {"use_date": "2024-10-01", "mode": "전부",
                                            "assets": [{"구분": "건물", "취득일": "2022-10-05", "취득가액": 40_000_000}]}, {"과세표준": 32_000_000}),
    # A4 기타 감가상각자산 2025년 제1기 취득 → 제2기 공급: 경과 1기 × 25% → 2,000,000 × 75% = 1,500,000
    "A4": ("vat_deemed_supply_items", {"period": "2025-2", "items": [{"항목": "공기청정기", "거래": "개인적공급", "매입세액공제": True,
                                       "감가상각": {"구분": "기타", "취득가액": 2_000_000, "취득일": "2025-02-10", "공급일": "2025-09-01"}}]},
           {"과세표준": 1_500_000}),
    # A5 간이과세자 신용카드 매입 2021.6.30. 공급 → 2021.7.1. 전이라 불공제 10,000,000
    "A5": ("vat_input_tax_deduction", {"period": "2021-1", "filing": "확정", "items": [{"항목": "매입", "성격": "일반", "공급가액": 100_000_000,
                                       "증빙": "신용카드", "공급자": "간이과세자_세금계산서", "공급시기": "2021-06-30"}]},
           {"공제매입세액": 0, "불공제매입세액": 10_000_000}),
    # A6 채무보증 구상채권 대손 500,000,000 손금불산입(기타사외유출)
    "A6a": ("bad_debt_adjustment", {"year": 2026, "sme": True, "book": {"opening": 20_000_000, "offset": 0, "provision": 10_000_000, "closing": 30_000_000},
                                    "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_200_000_000,
                                    "writeoffs": [{"kind": "회수불능", "amount": 500_000_000, "arose_in": "당기", "booked": "손비",
                                                   "excluded_reason": "채무보증구상채권", "recipient": "법인", "guarantee_item": 8, "date": "2026-02-20"}]},
            {"소득처분별_합계": {"기타사외유출": 500_000_000, "유보": 18_000_000}}),
    # A6 화해·확정판결 2019.1.15. — 2019.2.12. 전이라 대손 사유 아님 → 10,000,000 부인(유보)
    "A6b": ("bad_debt_adjustment", {"year": 2018, "sme": True, "book": {"opening": 0, "offset": 10_000_000, "provision": 0, "closing": 0},
                                    "receivables_prev_end_book": 1_000_000_000, "receivables_end_book": 1_000_000_000,
                                    "writeoffs": [{"kind": "화해·확정판결", "amount": 10_000_000, "arose_in": "당기", "date": "2019-01-15"}],
                                    "fy_start": "2018-07-01"}, {"소득처분별_합계": {"유보": 10_000_000}}),
    # A7 슬롯머신 당첨금 2016.6.30. 발생 — 2016.7.1. 경계 앞쪽(도구 기준) → YYYY-MM-DD 입력 결과 0
    "A7": ("other_income_aggregate", {"year": 2016, "items": [{"kind": "슬롯머신당첨금", "amount": 3_000_000, "occurred_on": "2016-06-30"}]},
           {"분리과세_기타소득금액": 0, "분리과세_원천징수세액": 0}),
    # A8 2025년 제2기 확정 전자신고(2026.1.25.) → YYYY-MM-DD 입력 결과: 경감공제 10,000원, 납부세액 10,000,000 − 10,000
    "A8": ("vat_return_general", {"year": 2025, "period": "2", "sales_invoice": 100_000_000, "e_filing": True, "filed_on": "2026-01-25"},
           {"경감공제세액": 10_000, "납부세액": 9_990_000}),
    # A9 특별재난지역 자원봉사 16시간 = 2일(8시간 1일), 2024.2.28. 봉사 → 도구 기준 1일 5만원 × 2 = 100,000(YYYY-MM-DD 입력 결과와 같음)
    "A9": ("individual_donation_expense", {"year": 2024, "base_income": 100_000_000, "volunteer": {"hours": 16, "served_on": "2024-02-28"}},
           {"특례기부금_산입": 100_000}),
}


@pytest.mark.parametrize("key", sorted(DATE_CASES))
@pytest.mark.parametrize("form", ["compact", "dot", "slash", "dot_short", "korean"])
def test_date_forms_same_result(key, form):
    tool, args, hand = DATE_CASES[key]
    base = call(tool, args)
    assert "결과" in base, base
    for k, v in hand.items():
        assert base["결과"][k] == v, (k, base["결과"][k])
    other = call(tool, to_form(args, form))
    assert strip(other) == strip(base)


# ── 140개 도구: 점검 원자료의 날짜 든 정상 입력 전부를 YYYYMMDD로 바꿔도 결과가 같다 ──

with open(os.path.join(HERE, "data", "date_format_cases_1116.json"), encoding="utf-8") as _f:
    _SWEEP = json.load(_f)["cases"]


def test_sweep_date_cases_cover_tools():
    assert len(_SWEEP) == 1132 and len({c["tool"] for c in _SWEEP}) == 80


@pytest.mark.parametrize("i", range(len(_SWEEP)))
def test_sweep_date_cases_compact_same(i):
    c = _SWEEP[i]
    base = call(c["tool"], c["args"])
    other = call(c["tool"], to_form(c["args"], "compact"))
    assert strip(other) == strip(base), c["tool"]


# ── 파이썬 원문 날짜 오류 → 고칠 방법 ───────────────────────────────────────────

@pytest.mark.parametrize("tool, args, where", [
    ("underreporting_penalty", {"additional_tax": 1_000_000, "reduction": "수정신고", "due": "bad-date", "amended_on": "2024-01-01"}, "due"),
    ("vat_bad_debt_credit", {"bad_debt_incl_vat": 1_100_000, "reason": "부도", "reason_date": "bad-date"}, "reason_date"),
    ("capital_gains_tax", {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2009-01-01", "transfer_date": "2019-12월"}, "transfer_date"),
])
def test_raw_date_errors_explained(tool, args, where):
    r = call(tool, args)
    msg = json.dumps(r, ensure_ascii=False)
    assert "error" in r and "Invalid isoformat" not in msg and "does not match format" not in msg
    assert where in msg and "YYYY-MM-DD" in msg and "예:" in msg


@pytest.mark.parametrize("tool, args", [
    ("capital_gains_tax", {"base": 100_000_000, "asset_type": "주택", "acquisition_date": "2009-01-01", "transfer_date": "20191217",
                           "houses_count": 3, "adjusted_area": True}),
    ("stock_capital_gains_tax", {"transfer_date": "20260310", "market": "코스피", "major_shareholder": True, "sme": False,
                                 "transfer_price": 1_000_000_000, "acquisition_price": 400_000_000, "expenses": 1_000_000, "acquisition_date": "2020-01-01"}),
    ("unlisted_stock_valuation", {"valuation_date": "20260501", "shares": 100_000, "incomes": [{"사업연도": 2025, "순손익액": 120_000_000},
                                  {"사업연도": 2024, "순손익액": 90_000_000}, {"사업연도": 2023, "순손익액": 60_000_000}],
                                  "net_asset": 800_000_000, "is_max_shareholder": True, "sme": True}),
    ("stock_basis_income_tax", {"transfer_date": "20260501", "shares": 100_000, "book_net_asset": 700_000_000, "business_start": "2025-10-01"}),
])
def test_strptime_tools_take_compact(tool, args):
    # 전에는 strptime 원문 오류로 거절 — 이제 YYYY-MM-DD와 같은 결과
    iso = {k: (f"{v[:4]}-{v[4:6]}-{v[6:]}" if isinstance(v, str) and re.fullmatch(r"\d{8}", v) else v) for k, v in args.items()}
    a, b = call(tool, args), call(tool, iso)
    assert "결과" in b, b
    assert strip(a) == strip(b)


# ── A1 퇴직소득세: 2016~2019년 퇴직·퇴직소득 0 ─────────────────────────────────

@pytest.mark.parametrize("retire_year", [2016, 2017, 2018, 2019, 2020, 2025])
def test_a1_zero_income_zero_tax(retire_year):
    r = call("retirement_income_tax", {"income": 0, "years_of_service": 10, "retire_year": retire_year, "years_before_2013": 4 if retire_year < 2020 else 0})
    assert "결과" in r, r
    assert r["결과"]["퇴직소득세"] == 0                  # 제48조②: 공제는 퇴직소득금액 한도 → 과세표준 0


def test_a1_negative_income_error():
    r = call("retirement_income_tax", {"income": -5_000_000, "years_of_service": 10, "retire_year": 2017})
    assert "error" in r and "income" in r["문제"][0] and "0" in r["문제"][0] and "연평균과세표준" not in json.dumps(r, ensure_ascii=False)


# ── A10·A11 일감몰아주기 ───────────────────────────────────────────────────────

TUNNEL = {"beneficiary": "수혜", "size": "중견", "sales_total": 100_000_000_000, "sales_by_corp": {"특관": 60_000_000_000},
          "people": {"갑": {"구분": "개인"}, "수혜": {"구분": "법인"}, "특관": {"구분": "법인"}}, "family": [],
          "stakes": [["갑", "수혜", 0.2], ["갑", "특관", 0.6]], "fiscal_year_end": "2025-12-31"}


def test_a10_negative_profit_no_gift():
    r = call("tunnelling_gift", {**TUNNEL, "after_tax_op_profit": -500_000_000})
    assert r["합계"] == 0
    assert all(v >= 0 for p in r["주주별"] for v in p["증여의제이익"].values())
    assert r["결론"].startswith("과세 없음") and "제45조의3" in r["결론"]


def test_a10_positive_profit_unchanged():
    # 중견: 거래비율 60% − 정상거래비율의 50%(20%) = 40%, 보유 20% − 한계보유비율의 50%(5%) = 15%
    # 500,000,000 × 40% × 15% = 30,000,000
    r = call("tunnelling_gift", {**TUNNEL, "after_tax_op_profit": 500_000_000})
    assert r["합계"] == 30_000_000 and r["결론"].startswith("과세")


def test_a11_nts_gain_whole_won():
    # 일반: 세후영업이익 10,000,000,000 × (40% − 5%) × 10% = 350,000,000
    r = call("tunnelling_gift_nts", {"size": "일반", "op_income": 10_000_000_000, "taxable_income": 10_000_000_000, "tax": 0,
                                     "sales_total": 100_000_000_000, "sales_by_corp": {"A": 40_000_000_000}, "relations": {"직접": 0.1}})
    g = r["출자관계별"]["직접"]["증여의제이익"]
    assert g == 350_000_000 and isinstance(g, int) and r["합계"] == 350_000_000 and isinstance(r["합계"], int)


def test_nts_negative_profit_still_zero():
    r = call("tunnelling_gift_nts", {"size": "중소", "op_income": -1_000_000_000, "taxable_income": -800_000_000, "tax": 0,
                                     "sales_total": 1_000_000_000, "sales_by_corp": {"A": 600_000_000}, "relations": {"직접": 0.5}})
    assert r["합계"] == 0


# ── A12 대주주 판정: 보유 주식 > 발행주식총수 ──────────────────────────────────

SMS = {"transfer_date": "2025-06-01", "market": "코스피", "total_shares": 1_000_000, "price": 1000}


def test_a12_own_over_total():
    r = call("stock_major_shareholder", {**SMS, "own_shares": 5_000_000})
    assert "error" in r and "total_shares" in r["문제"][0] and "5,000,000" in r["문제"][0]


def test_a12_holders_over_total():
    r = call("stock_major_shareholder", {**SMS, "own_shares": 5_000, "is_max_group": True,
                                         "holders": [{"이름": "배우자", "관계": "배우자", "주식수": 2_000_000}]})
    assert "error" in r and "2,005,000" in r["문제"][0]


def test_a12_ratio_rule():
    base = {"transfer_date": "2025-06-01", "market": "코스피"}
    r = call("stock_major_shareholder", {**base, "own_ratio": 500})
    assert "error" in r and "100%" in r["error"] + json.dumps(r, ensure_ascii=False)
    pct, dec = call("stock_major_shareholder", {**base, "own_ratio": 5}), call("stock_major_shareholder", {**base, "own_ratio": 0.05})
    assert pct["결과"]["판정"] == dec["결과"]["판정"] == "대주주"      # 도구 설명: 0~1 비율 또는 %(1.5) — 5 = 5%


def test_a12_ledger_within_total_unchanged():
    # 1,000,000주 중 본인 15,000주 = 1.5% ≥ 코스피 1%(2025) → 대주주
    r = call("stock_major_shareholder", {**SMS, "own_shares": 15_000})
    assert r["결과"]["판정"] == "대주주"


# ── A13 비거주자 원천징수 제한세율 범위 ─────────────────────────────────────────

NRW = {"income_kind": "배당", "recipient_type": "법인", "residence_country": "일본", "year": 2025, "amount": 10_000_000}


@pytest.mark.parametrize("rate, hint", [(-0.1, "0.15"), (15, "0.15"), (1.5, "0.015")])
def test_a13_treaty_rate_range(rate, hint):
    r = call("nonresident_withholding", {**NRW, "treaty_rate": rate})
    assert "error" in r and "treaty_rate" in r["문제"][0] and hint in r["문제"][0]


def test_a13_treaty_rate_valid():
    # 배당 10,000,000 × 제한세율 15% = 1,500,000(국내 22%보다 낮음)
    r = call("nonresident_withholding", {**NRW, "treaty_rate": 0.15, "treaty_includes_local_tax": False})
    assert r["결과"]["원천징수세액"] == 1_500_000


# ── A14 세금계산서 가산세 묶음: 음수 공급가액 ──────────────────────────────────

def test_a14_negative_supply_amount():
    r = call("invoice_penalty_bundle", {"items": [
        {"deal": "A", "kind": "미발급", "supply_amount": -10_000_000, "supplied_on": "2026-09-15"},
        {"deal": "B", "kind": "미발급", "supply_amount": 5_000_000, "supplied_on": "2026-09-15"}]})
    assert "error" in r and "items[0].supply_amount" in r["문제"][0]


def test_a14_positive_unchanged():
    # 미발급 2%: 5,000,000 × 2% = 100,000
    r = call("invoice_penalty_bundle", {"items": [{"deal": "B", "kind": "미발급", "supply_amount": 5_000_000, "supplied_on": "2026-09-15"}]})
    assert r["결과"]["가산세_합계"] == 100_000


# ── (b)1 최저한세 조정 오류 안내가 문장 ─────────────────────────────────────────

MT = {"year": 2025, "sme": True, "net_income": 500_000_000, "income_add": 0, "income_deduct": 0}


@pytest.mark.parametrize("bad, must", [
    ({"credits": [{"code": "ZZZ", "current": 1}]}, "ZZZ"),
    ({"credits": [{"code": "13W", "current": 0, "carryforward": [{"year": 2014, "amount": 1}]}]}, "2015~2024"),
    ({"credits": [{"code": "189", "current": 1}]}, "101"),
    ({"credits": [{"code": "13M", "current": 1}]}, "16B"),
    ({"exclusion_order": ["999"]}, "999"),
    ({"income_deduct": 0, "special_depreciation": 1}, "income_deduct"),
])
def test_b1_min_tax_messages(bad, must):
    r = call("minimum_tax_adjustment", {**MT, **bad})
    assert "error" in r
    p = r["문제"][0]
    assert must in p and len(p) > 20 and "넣" in p + "".join(r["문제"])   # 무엇이 틀렸고 무엇을 넣는지


# ── (b)2 파이썬 원문 오류(지분 문자열·배당 꼴) ───────────────────────────────────

STAKE_X = [["김갑", "㈜대한", "x"]]


@pytest.mark.parametrize("tool, args", [
    ("related_judge", {"a": "김갑", "b": "김을", "on": "2024-01-01", "people": {"김갑": {"구분": "개인"}, "김을": {"구분": "개인"}},
                       "family": [], "stakes": STAKE_X, "with_citation": False}),
    ("ownership_ratio", {"holder": "김갑", "target": "㈜대한", "stakes": STAKE_X}),
    ("dominant_shareholder", {"corp": "㈜대한", "people": {"김갑": {"구분": "개인"}}, "family": [], "stakes": STAKE_X}),
    ("tunnelling_gift", {"beneficiary": "김갑", "size": "중소", "sales_total": 1, "sales_by_corp": {}, "after_tax_op_profit": 1,
                         "people": {"김갑": {"구분": "개인"}}, "family": [], "stakes": STAKE_X}),
])
def test_b2_stake_not_number(tool, args):
    r = call(tool, args)
    msg = json.dumps(r, ensure_ascii=False)
    assert "error" in r and "could not convert" not in msg and "stakes[0]" in msg and "0.3" in msg


def test_b2_nts_dividends_shape():
    r = call("tunnelling_gift_nts", {"size": "중소", "op_income": 1, "taxable_income": 1, "tax": 1, "sales_total": 1,
                                     "sales_by_corp": {}, "relations": {}, "dividends": {"직접": 5}})
    msg = json.dumps(r, ensure_ascii=False)
    assert "error" in r and "not iterable" not in msg and "배당소득" in msg and "분모" in msg


# ── (b)4 음수가 법적으로 의미 없는 입력 ─────────────────────────────────────────

NEG_CASES = [
    ("vat_simplified_taxpayer", {"supply_incl_vat": -1_000_000, "value_added_rate": 0.15, "year": 2025}, "supply_incl_vat"),
    ("vat_simplified_taxpayer", {"supply_incl_vat": 1_000_000, "value_added_rate": 0.15, "year": 2025, "card_cash_receipt_supply_incl_vat": -1}, "card_cash_receipt_supply_incl_vat"),
    ("vat_bad_debt_credit", {"bad_debt_incl_vat": -11_000_000}, "bad_debt_incl_vat"),
    ("vat_deemed_input_credit", {"period": "2025-1", "industry": "음식점", "purchase": -1_000_000, "base": 100_000_000}, "purchase"),
    ("deemed_dividend_bonus_shares", {"year": 2025, "source": "이익잉여금", "capitalized_amount": 10_000_000, "par_value": 5000,
                                      "shareholders": [{"name": "갑", "shares": -1000}], "self_stock_allotment": "미교부", "shareholder_type": "개인"}, "shareholders[0].shares"),
    ("unfair_transaction", {"market_price": -1000, "actual_price": 500, "quantity": 10}, "market_price"),
    ("liquidation_income", {"assets_realized": [{"항목": "토지", "금액": -1_000_000}], "liabilities_paid": 0, "capital": 0, "surplus": 0}, "assets_realized[0]"),
    ("business_car_expense", {"year": 2025, "upkeep": 1_000_000, "depreciation": -1_000_000, "booked_depreciation": 0, "log_kept": False}, "depreciation"),
    ("capital_gains_unfair_transaction", {"mode": "증여후양도", "gift_date": "2020-06-01", "transfer_date": "2024-06-01", "donee_relation": "기타특수관계인",
                                          "donee_gift_tax": -10_000_000, "donee_capital_gains_tax": 20_000_000, "donor_direct_capital_gains_tax": 100_000_000}, "donee_gift_tax"),
    ("income_loss_offset", {"year": 2025, "incomes": {"근로": 10_000_000}, "financial_flat_rate": -1_000_000}, "financial_flat_rate"),
    ("income_loss_offset", {"year": 2025, "incomes": {"근로": -10_000_000}}, "incomes.근로"),
    ("input_tax_recalculation", {"asset_type": "건물·구축물", "acquired": {"year": 2024, "period": 1},
                                 "ratios": [{"year": 2024, "period": 1, "exempt_ratio": 0.1}, {"year": 2024, "period": 2, "exempt_ratio": 0.2}],
                                 "input_tax": -1_000_000}, "input_tax"),
    ("common_input_tax", {"year": 2025, "period": "1기", "filing": "확정", "supplies": {"확정": {"taxable": 100, "exempt": 100}},
                          "ledger": [], "prior_nondeductible": -1}, "prior_nondeductible"),
    ("bundled_supply_split", {"total_price": 1_000_000_000, "vat_included": False, "standard_value": {"building": 300_000_000, "land": -1}}, "standard_value.land"),
    ("asset_grant_reserve", {"year": 2025, "kind": "국고보조금", "received": -1_000_000, "assets": []}, "received"),
    ("retirement_allowance_adjustment", {"year": 2025, "allowance": {"opening": 0, "closing": 0}, "prior_disallowed": 0, "pension": {"asset_closing": 100, "prior_deducted": -1}}, "pension.prior_deducted"),
    ("tunnelling_gift_nts", {"size": "중소", "op_income": 1, "taxable_income": 1, "tax": 0, "sales_total": -1_000_000,
                             "sales_by_corp": {}, "relations": {"직접": 0.5}}, "sales_total"),
    ("tunnelling_gift", {**TUNNEL, "after_tax_op_profit": 1, "sales_by_corp": {"특관": -1}}, "sales_by_corp"),
]


@pytest.mark.parametrize("tool, args, where", NEG_CASES)
def test_b4_negative_rejected(tool, args, where):
    r = call(tool, args)
    assert "error" in r, (tool, r)
    msg = json.dumps(r, ensure_ascii=False)
    assert where in msg and "음수" in msg and "0 이상" in msg


@pytest.mark.parametrize("tool", ["tunnelling_gift_nts", "tunnelling_gift"])
def test_b4_related_sales_over_total(tool):
    args = ({"size": "중소", "op_income": 1, "taxable_income": 1, "tax": 0, "sales_total": 1_000, "sales_by_corp": {"A": 2_000},
             "relations": {"직접": 0.5}} if tool == "tunnelling_gift_nts" else {**TUNNEL, "after_tax_op_profit": 1, "sales_total": 1_000,
                                                                              "sales_by_corp": {"특관": 2_000}})
    r = call(tool, args)
    assert "error" in r and "sales_total" in r["문제"][0]


def test_b4_negative_still_allowed_where_meaningful():
    # 결손금(사업·부동산임대 소득)·△유보·음수 세후영업이익은 그대로 받는다
    r = call("income_loss_offset", {"year": 2025, "incomes": {"근로": 30_000_000}, "business": {"book_income": -10_000_000, "adjustments": []}})
    assert "결과" in r, r
    r = call("liquidation_income", {"assets_realized": 1_000_000_000, "liabilities_paid": 0, "capital": 100_000_000, "surplus": 0, "yubo": -5_000_000})
    assert "결과" in r, r
    assert "error" not in call("tunnelling_gift", {**TUNNEL, "after_tax_op_profit": -1})
