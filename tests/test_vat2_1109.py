"""부가세 시나리오 2탄 결함 정답 — 간이과세자 면제·환산·겸영, 세금계산서 가산세 묶음, 간주공급 대상(사업양수·수출), 공통사용재화 매입세액."""
import asyncio
import json

import pytest

from korean_tax_calc_mcp.server import mcp


def call(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def R(d):
    return d.get("결과", d)


S = "vat_simplified_taxpayer"
BASE = {"value_added_rate": 0.15, "invoice_purchase_incl_vat": 22_000_000, "card_cash_receipt_supply_incl_vat": 25_000_000, "year": 2026}


# ── 1. 간이과세자 ──
def test_exempt_means_zero():
    r = R(call(S, {"supply_incl_vat": 40_000_000, "value_added_rate": 0.15, "invoice_purchase_incl_vat": 11_000_000, "year": 2026}))
    assert r["납부의무_면제"] is True and r["차가감_납부세액"] == 0


def test_new_business_annualized_not_exempt():
    r = R(call(S, {**BASE, "supply_incl_vat": 40_000_000, "business_start": "2026-04-10"}))
    assert r["환산_개월수"] == 9
    assert r["면제_판정_공급대가"] == 53_333_333
    assert r["납부의무_면제"] is False
    assert r["차가감_납부세액"] == 165_000


def test_new_business_half_year_exempt():
    r = R(call(S, {"supply_incl_vat": 20_000_000, "value_added_rate": 0.15, "year": 2026, "business_start": "2026-07-01"}))
    assert r["환산_개월수"] == 6 and r["면제_판정_공급대가"] == 40_000_000
    assert r["납부의무_면제"] is True and r["차가감_납부세액"] == 0


def test_closed_mid_year():
    r = R(call(S, {"supply_incl_vat": 30_000_000, "value_added_rate": 0.15, "year": 2026, "closed_on": "2026-06-15"}))
    assert r["환산_개월수"] == 6 and r["면제_판정_공급대가"] == 60_000_000
    assert r["납부의무_면제"] is False and r["차가감_납부세액"] == 450_000


def test_mixed_industries():
    r = R(call(S, {"industries": [{"value_added_rate": 0.15, "supply_incl_vat": 30_000_000},
                                  {"value_added_rate": 0.25, "supply_incl_vat": 20_000_000}], "year": 2026}))
    assert r["납부의무_면제"] is False and r["차가감_납부세액"] == 950_000


def test_mixed_with_single_is_error():
    d = call(S, {"supply_incl_vat": 1, "value_added_rate": 0.15, "industries": [{"value_added_rate": 0.15, "supply_incl_vat": 1}], "year": 2026})
    assert "error" in d


# ── 2. 가산세 묶음 ──
def test_invoice_penalty_bundle_exclusions():
    items = [
        {"deal": "A", "kind": "미발급", "supply_amount": 20_000_000, "supplied_on": "2026-09-15"},
        {"deal": "A", "kind": "매출처별합계표_미제출", "supply_amount": 20_000_000, "supplied_on": "2026-09-15"},
        {"deal": "A", "kind": "미전송", "supply_amount": 20_000_000, "supplied_on": "2026-09-15"},
        {"deal": "B", "kind": "미전송", "supply_amount": 10_000_000, "supplied_on": "2026-10-15"},
        {"deal": "B", "kind": "매출처별합계표_미제출", "supply_amount": 10_000_000, "supplied_on": "2026-10-15"},
        {"deal": "C", "kind": "지연발급", "supply_amount": 10_000_000, "supplied_on": "2026-11-15"},
        {"deal": "C", "kind": "지연전송", "supply_amount": 10_000_000, "supplied_on": "2026-11-15"},
    ]
    d = call("invoice_penalty_bundle", {"items": items})
    r = R(d)
    assert r["가산세_합계"] == 400_000 + 50_000 + 100_000
    rows = (d.get("계산") or {}).get("항목별") or r.get("항목별")
    zero = {(x["deal"], x["kind"]) for x in rows if x["가산세"] == 0}
    assert zero == {("A", "매출처별합계표_미제출"), ("A", "미전송"), ("B", "매출처별합계표_미제출"), ("C", "지연전송")}


def test_single_invoice_penalty_warns():
    d = call("invoice_penalty", {"supply_amount": 10_000_000, "kind": "미전송", "supplied_on": "2026-10-15"})
    assert R(d)["가산세"] == 50_000
    assert "invoice_penalty_bundle" in json.dumps(d, ensure_ascii=False)


# ── 3. 간주공급 대상 재화 ──
def _closing(acq):
    it = {"항목": "양수 비품", "거래": "폐업시잔존", "매입세액공제": False,
          "감가상각": {"구분": "기타", "취득가액": 10_000_000, "취득일": "2025-03-01", "공급일": "2026-09-30"}}
    if acq:
        it["취득구분"] = acq
    return R(call("vat_deemed_supply_items", {"period": "2026-2", "items": [it]}))["과세표준"]


def test_business_transfer_goods_included():
    assert _closing("사업양수") == 2_500_000


def test_export_goods_included():
    assert _closing("수출영세율") == 2_500_000


def test_no_credit_still_excluded():
    assert _closing(None) == 0


# ── 4. 공통사용재화 매입세액 ──
def _cit(acq):
    sale = {"sale_price": 60_000_000, "input_tax": 5_000_000}
    if acq:
        sale["acquired_period"] = acq
    return call("common_input_tax", {"year": 2026, "period": "2기", "filing": "확정",
                                     "supplies": {"예정": {"taxable": 300_000_000, "exempt": 20_000_000},
                                                  "확정": {"taxable": 400_000_000, "exempt": 10_000_000}},
                                     "prior_period_supplies": {"taxable": 700_000_000, "exempt": 30_000_000},
                                     "common_asset_sales": [sale], "ledger": [{"항목": "원재료", "매입세액": 1_000_000, "사용처": "과세"}]})


def test_common_asset_input_tax_other_period_zero():
    d = _cit("2024-2")
    c = d["계산"]
    assert c["공통사용재화_공급_과세표준"] == 57_534_246
    assert c["공통사용재화_매입세액_공제"] == 0
    assert "제54조③" in json.dumps(d, ensure_ascii=False)


def test_common_asset_input_tax_same_period():
    c = _cit("2026-2")["계산"]
    assert c["공통사용재화_매입세액_공제"] == 4_794_520


def test_common_asset_input_tax_unknown_period_warns():
    d = _cit(None)
    assert d["계산"]["공통사용재화_매입세액_공제"] == 4_794_520
    assert "acquired_period" in json.dumps(d, ensure_ascii=False)


# ── 검수 추가 ──
def test_exempt_keeps_invoice_penalty():
    """면제는 제63조② 납부세액만 — 세금계산서 미수취 가산세(제68조의2)는 남음(제69조①②)."""
    r = R(call(S, {"supply_incl_vat": 10_000_000, "value_added_rate": 0.15, "no_invoice_purchase_incl_vat": 1_000_000, "year": 2026}))
    assert r["납부의무_면제"] is True and r["차가감_납부세액"] == 5_000


def test_month_count_boundary():
    a = R(call(S, {"supply_incl_vat": 40_000_000, "value_added_rate": 0.15, "year": 2026, "business_start": "2026-04-10", "closed_on": "2026-12-09"}))
    b = R(call(S, {"supply_incl_vat": 40_000_000, "value_added_rate": 0.15, "year": 2026, "business_start": "2026-04-10", "closed_on": "2026-12-10"}))
    assert a["환산_개월수"] == 8 and b["환산_개월수"] == 9


def test_simplified_vat_return_annualizes():
    d = call("simplified_vat_return", {"year": 2026, "business_type": "소매업", "business_start": "2026-04-10",
                                       "ledger": {"공급": [{"항목": "카드매출", "금액": 40_000_000}], "매입": []}})
    r = R(d)
    assert r["납부의무면제"] is False and r["환산_개월수"] == 9 and r["면제판정_공급대가"] == 53_333_333


def test_bundle_fake_invoice_and_bad_kind():
    d = call("invoice_penalty_bundle", {"items": [
        {"deal": "X", "kind": "가공", "supply_amount": 10_000_000, "supplied_on": "2026-10-01"},
        {"deal": "X", "kind": "매출처별합계표_미제출", "supply_amount": 10_000_000, "supplied_on": "2026-10-01"}]})
    single = R(call("invoice_penalty", {"supply_amount": 10_000_000, "kind": "가공", "supplied_on": "2026-10-01"}))["가산세"]
    assert R(d)["가산세_합계"] == single
    assert "error" in call("invoice_penalty_bundle", {"items": [{"deal": "Y", "kind": "없는종류", "supply_amount": 1}]})


def test_acquisition_kind_typo_rejected():
    it = {"항목": "비품", "거래": "폐업시잔존", "매입세액공제": False, "시가": 1_000_000, "취득구분": "사업 양수"}
    assert "error" in call("vat_deemed_supply_items", {"period": "2026-2", "items": [it]})


def test_exempt_use_acquisition_kind_typo_rejected():
    a = {"구분": "기타", "취득일": "2025-03-01", "취득가액": 10_000_000, "매입세액공제": False, "취득구분": "사업 양수"}
    assert "error" in call("vat_exempt_use_deemed_supply", {"use_date": "2026-08-01", "mode": "전부", "assets": [a]})
