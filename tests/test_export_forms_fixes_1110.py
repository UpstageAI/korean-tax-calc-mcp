"""기존 도구 4개 보강 정답 테스트(수정 금지, Claude 작성 2026-11-10) — 수출 형태별 공급시기, 해외 인적용역 제공 장소, 100% 자회사 증자, 해외 무상 반출.
근거: 부가가치세법 시행령 제28조제6항·제31조제1항, 소득세법 제119조제6호·제156조제1항제4호, 서이46012-12126, 부가가치세법 제21조제2항제1호.
"""
from _helpers import call as c

M = 1_000_000


# ── B1 수출 형태별 공급시기 ──────────────────────────────────────────────────
def test_consignment_export_timing_is_price_fixing_date():
    r = c("vat_supply_timing", {"business": "일반", "transactions": [
        {"이름": "FBA 위탁판매", "종류": "위탁판매수출", "선적일": "2026-03-20", "확정일": "2026-05-31", "공급가액": 138 * M}]})
    assert "error" not in r, r
    t = r["거래별"][0]
    assert t["공급시기별"][0]["공급시기"] == "2026-05-31" and "확정" in t["공급시기별"][0]["신고기간"]
    assert r["결과"]["기간별_과세표준"].get("2026-1기 확정(4.1~6.30)") == 138 * M


def test_foreign_delivery_and_processing_exports_use_delivery_date():
    r = c("vat_supply_timing", {"business": "일반", "transactions": [
        {"이름": "외국인도", "종류": "외국인도수출", "인도일": "2026-07-10", "공급가액": 50 * M},
        {"이름": "위탁가공", "종류": "위탁가공무역", "인도일": "2026-11-02", "공급가액": 30 * M}]})
    assert "error" not in r, r
    ts = r["거래별"]
    assert ts[0]["공급시기별"][0]["공급시기"] == "2026-07-10" and ts[1]["공급시기별"][0]["공급시기"] == "2026-11-02"
    assert sum(r["결과"]["기간별_과세표준"].values()) == 80 * M


def test_intermediary_trade_uses_shipping_date_and_direct_export_unchanged():
    r = c("vat_supply_timing", {"business": "일반", "period": "2026-1기 예정", "transactions": [
        {"이름": "중계무역", "종류": "중계무역", "선적일": "2026-02-10", "공급가액": 20 * M},
        {"이름": "직수출", "종류": "수출", "선적일": "2026-03-05", "공급가액": 10 * M}]})
    assert "error" not in r, r
    assert r["결과"]["조회기간_과세표준"] == 30 * M


def test_consignment_export_needs_fixing_date():
    r = c("vat_supply_timing", {"transactions": [{"종류": "위탁판매수출", "선적일": "2026-03-20", "공급가액": 1}]})
    assert "error" in r and "확정일" in json_dump(r)


def json_dump(r):
    import json
    return json.dumps(r, ensure_ascii=False)


# ── B2 해외 인적용역 제공 장소 ────────────────────────────────────────────────
NR = {"income_kind": "인적용역", "amount": 28 * M, "recipient_type": "개인", "residence_country": "미국"}


def test_personal_service_abroad_is_not_korean_source():
    r = c("nonresident_withholding", {**NR, "service_location": "국외"})
    g = r["결과"]
    assert g["적용세율"] == 0 and g["원천징수세액"] == 0 and g["지방소득세"] == 0 and g["합계"] == 0
    assert "제119조" in r["근거"] and any("3%" in str(j) or "단서" in str(j) for j in r["판단"])


def test_personal_service_in_korea_and_default_unchanged():
    assert c("nonresident_withholding", {**NR, "service_location": "국내"})["결과"]["원천징수세액"] == 5_600_000
    assert c("nonresident_withholding", NR)["결과"]["원천징수세액"] == 5_600_000


def test_service_location_ignored_for_royalty():
    r = c("nonresident_withholding", {"income_kind": "사용료", "amount": 100 * M, "recipient_type": "법인", "residence_country": "미국", "service_location": "국외"})
    assert r["결과"]["원천징수세액"] == 20 * M


# ── B3 100% 자회사 증자 ─────────────────────────────────────────────────────
def test_wholly_owned_capital_increase_not_unfair():
    r = c("unfair_transaction", {"market_price": 0, "actual_price": 500 * M, "quantity": 1, "wholly_owned_capital_increase": True})
    assert r["결과"]["부당행위계산"] is False and any("46012-12126" in str(j) for j in r.get("판단", []))
    assert c("unfair_transaction", {"market_price": 0, "actual_price": 500 * M, "quantity": 1})["결과"]["부당행위계산"] is True


# ── B4 해외 무상 반출 ───────────────────────────────────────────────────────
def test_free_shipment_abroad_is_zero_rated():
    r = c("vat_deemed_supply_items", {"period": "2026-1", "items": [
        {"항목": "국내 인플루언서 제품", "거래": "사업상증여", "매입세액공제": True, "시가": 6 * M},
        {"항목": "해외 인플루언서 발송", "거래": "사업상증여", "매입세액공제": True, "시가": 15 * M, "반출": "국외"}]})
    assert "error" not in r, r
    assert r["결과"]["과세표준"] == 6 * M and r["결과"]["영세율_과세표준"] == 15 * M
    items = {x["항목"]: x for x in r["계산"]["항목별"]}
    assert items["해외 인플루언서 발송"].get("영세율") is True
    assert any("제21조" in str(j) for j in r["판단"])


def test_domestic_default_unchanged_and_sample_exclusion_first():
    r = c("vat_deemed_supply_items", {"period": "2026-1", "items": [
        {"항목": "견본품 해외 발송", "거래": "사업상증여", "매입세액공제": True, "시가": 2 * M, "견본_광고선전물": True, "반출": "국외"}]})
    assert r["결과"]["과세표준"] == 0 and r["결과"]["영세율_과세표준"] == 0
