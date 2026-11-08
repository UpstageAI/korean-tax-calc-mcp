"""부가세 확정신고 시나리오(2026-2기)에서 나온 결함 4건 정답 — 지연수취·대손 확정 시기·제48조② 감면·합계표 전자 전송 면제."""
import asyncio
import json

import pytest

from korean_tax_calc_mcp.server import mcp


def call(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def R(d):
    return d.get("결과", d)


# ── 1. 지연수취 ─────────────────────────────────────────
def _item(name, supplied, issued, **kw):
    return {"항목": name, "증빙": "세금계산서", "공급가액": 10_000_000, "성격": "일반", "공급시기": supplied, "발급일": issued, **kw}


ITEMS = [
    _item("A 다음해 1/8", "2026-11-20", "2027-01-08"),
    _item("B 다음달 10일", "2026-11-20", "2026-12-10"),
    _item("C 다음달 11일", "2026-11-20", "2026-12-11"),
    _item("D 확정기한 뒤 1년 이내", "2026-10-05", "2027-03-02"),
    _item("E 선발급", "2026-11-20", "2026-11-15"),
    _item("F 특례 아님", "2026-11-20", "2026-11-25", 발급특례=False),
    _item("G 기한 일요일→월요일", "2026-12-05", "2027-01-11"),
]
LATE = {"A 다음해 1/8", "C 다음달 11일", "D 확정기한 뒤 1년 이내", "F 특례 아님"}


def test_late_receipt_flags_and_penalty():
    d = call("vat_input_tax_deduction", {"period": "2026-2", "filing": "확정", "items": ITEMS})
    r = R(d)
    assert r["공제매입세액"] == 7_000_000
    assert r["불공제매입세액"] == 0
    assert r["지연수취_가산세"] == 200_000
    flagged = {j["항목"] for j in d.get("판단", []) + R(d).get("판단", []) if "지연수취" in str(j.get("결론", ""))}
    assert flagged == LATE


def test_no_late_receipt_zero_penalty():
    d = call("vat_input_tax_deduction", {"period": "2026-2", "filing": "확정",
                                         "items": [_item("정상", "2026-11-20", "2026-11-20"), {"항목": "카드", "증빙": "신용카드", "공급대가": 5_500_000, "성격": "일반"}]})
    assert R(d)["지연수취_가산세"] == 0
    assert R(d)["공제매입세액"] == 1_500_000


def test_late_receipt_supply_incl_vat():
    it = {"항목": "공급대가", "증빙": "세금계산서", "공급대가": 11_000_000, "성격": "일반", "공급시기": "2026-11-20", "발급일": "2027-01-08"}
    assert R(call("vat_input_tax_deduction", {"period": "2026-2", "filing": "확정", "items": [it]}))["지연수취_가산세"] == 50_000


# ── 2. 대손 확정 시기 ─────────────────────────────────────
BASE = {"bad_debt_incl_vat": 11_000_000}


def bd(**kw):
    return R(call("vat_bad_debt_credit", {**BASE, **kw}))


def test_bad_debt_legacy_unchanged():
    d = call("vat_bad_debt_credit", BASE)
    assert R(d)["대손세액"] == 1_000_000
    assert "reason" in json.dumps(d, ensure_ascii=False)


def test_bounced_not_yet_6_months():
    r = bd(reason="부도", reason_date="2026-08-20", supply_date="2024-06-20", receivable="외상매출금", sme=True, period="2026-2")
    assert r["대손세액"] == 0 and r["공제가능"] is True
    assert r["대손확정일"] == "2027-02-21" and r["공제_과세기간"] == "2027-1"


def test_bounced_after_6_months():
    r = bd(reason="부도", reason_date="2026-08-20", supply_date="2024-06-20", receivable="외상매출금", sme=True, period="2027-1")
    assert r["대손세액"] == 1_000_000 and r["공제_과세기간"] == "2027-1"


def test_bounced_year_end_boundary():
    r = bd(reason="부도", reason_date="2026-12-31", receivable="어음", sme=False)
    assert r["대손확정일"] == "2027-07-01" and r["공제_과세기간"] == "2027-2"


def test_bounced_receivable_needs_sme():
    r = bd(reason="부도", reason_date="2026-01-10", receivable="외상매출금", sme=False, period="2026-2")
    assert r["공제가능"] is False and r["대손세액"] == 0


def test_bounced_bill_no_sme_limit():
    r = bd(reason="부도", reason_date="2026-01-10", receivable="어음", sme=False, period="2026-2")
    assert r["공제가능"] is True and r["대손세액"] == 1_000_000 and r["공제_과세기간"] == "2026-2"


def test_bounced_with_mortgage():
    r = bd(reason="부도", reason_date="2026-01-10", receivable="어음", mortgage=True, period="2026-2")
    assert r["공제가능"] is False and r["대손세액"] == 0


def test_prescription_same_period():
    r = bd(reason="소멸시효", reason_date="2026-10-05", supply_date="2023-04-01", period="2026-2")
    assert r["대손세액"] == 1_000_000 and r["대손확정일"] == "2026-10-05"


def test_prescription_ten_years_passed():
    r = bd(reason="소멸시효", reason_date="2026-10-05", supply_date="2015-03-01", period="2026-2")
    assert r["공제가능"] is False and r["대손세액"] == 0


def test_period_after_confirmation():
    r = bd(reason="소멸시효", reason_date="2026-03-10", period="2026-2")
    assert r["대손세액"] == 0 and r["공제_과세기간"] == "2026-1"


def test_recovered_unchanged():
    r = bd(recovered=True)
    assert r["대손세액"] == 1_000_000 and r["회수"] is True


# ── 3. 과소신고가산세 감면 ─────────────────────────────────
def up(tax=2_000_000, fraud=False, **kw):
    return R(call("underreporting_penalty", {"additional_tax": tax, "fraud": fraud, **kw}))


def test_underreport_legacy():
    assert up()["가산세"] == 200_000


@pytest.mark.parametrize("due,amended,rate", [
    ("2026-07-27", "2026-08-10", 0.9), ("2026-07-27", "2026-08-27", 0.9), ("2026-07-27", "2026-08-28", 0.75),
    ("2026-03-31", "2026-09-30", 0.5), ("2026-03-31", "2026-10-01", 0.3), ("2026-03-31", "2027-09-30", 0.2),
    ("2026-03-31", "2028-03-31", 0.1), ("2026-03-31", "2028-04-01", 0.0),
    ("2018-03-31", "2018-09-30", 0.5), ("2018-03-31", "2018-10-01", 0.2), ("2018-03-31", "2019-12-31", 0.1),
])
def test_amended_return_table(due, amended, rate):
    r = up(reduction="수정신고", due=due, amended_on=amended)
    assert r["감면율"] == rate
    assert r["감면전_가산세"] == 200_000
    assert r["가산세"] == 200_000 - int(200_000 * rate)


def test_preliminary_fixed_in_final_75():
    r = up(reduction="예정신고_확정수정", due="2026-10-26", amended_on="2027-01-25")
    assert r["감면율"] == 0.75 and r["가산세"] == 50_000


def test_preliminary_floor_50():
    r = up(reduction="예정신고_확정수정", due="2026-04-27", amended_on="2026-12-01")
    assert r["감면율"] == 0.5 and r["가산세"] == 100_000


def test_foreknown_no_reduction():
    r = up(reduction="수정신고", due="2026-07-27", amended_on="2026-08-10", foreknown=True)
    assert r["감면율"] == 0 and r["가산세"] == 200_000


def test_fraud_reduced():
    r = up(tax=1_000_000, fraud=True, reduction="수정신고", due="2026-07-27", amended_on="2026-08-10")
    assert r["감면전_가산세"] == 400_000 and r["가산세"] == 40_000


# ── 4. 합계표 가산세와 전자세금계산서 ─────────────────────────
def ip(kind, **kw):
    return call("invoice_penalty", {"supply_amount": 20_000_000, "kind": kind, "supplied_on": "2026-09-15", **kw})


@pytest.mark.parametrize("kind", ["매출처별합계표_예정분확정제출", "매출처별합계표_미제출"])
def test_summary_exempt_when_e_invoice(kind):
    d = ip(kind, e_invoice_transmitted=True)
    assert R(d)["가산세"] == 0
    assert "제54조②" in json.dumps(d, ensure_ascii=False)


def test_summary_penalty_when_not_transmitted():
    assert R(ip("매출처별합계표_예정분확정제출", e_invoice_transmitted=False))["가산세"] == 60_000


def test_summary_warns_when_unknown():
    d = ip("매출처별합계표_예정분확정제출")
    assert R(d)["가산세"] == 60_000
    s = json.dumps(d, ensure_ascii=False)
    assert "제54조②" in s and "전자세금계산서" in s


def test_other_kind_ignores_flag():
    assert R(ip("지연수취", e_invoice_transmitted=True))["가산세"] == 100_000
