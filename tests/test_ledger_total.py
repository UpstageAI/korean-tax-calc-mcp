"""기업업무추진비 원장 합계 대조 ledger_total (Claude 2026-11-08, 0.22.1).

배경: 원장 행을 직접 더해 한 줄로 넘기다 합계를 틀린 경우(4,644만 7천 원 → 4,620만 원)가 서식 ①에 그대로 나갔다.
원장 합계를 주면 ledger 금액 합계와 대조해 다르면 '확인 필요' 판단을 붙인다(계산은 그대로).
"""
from test_form_templates import c

T = "entertainment_adjustment"
BASE = {"year": 2025, "sme": True, "revenue": {"매출액": 8_500_000_000}}
LEDGER = [{"항목": "법인카드 사용분", "금액": 46_200_000}, {"항목": "간이영수증", "금액": 1_200_000, "증빙": "영수증 등", "건당기준초과": True}]


def test_mismatch_flags():
    r = c(T, {**BASE, "ledger": LEDGER, "ledger_total": 48_000_000})
    assert r["계산"]["원장합계_대조"] == "확인 필요"
    j = [x for x in r["판단"] if x["항목"] == "원장 합계 대조"]
    assert j and "차이 600,000원" in j[0]["결론"]


def test_match_and_default():
    r = c(T, {**BASE, "ledger": LEDGER, "ledger_total": 47_400_000})
    assert r["계산"]["원장합계_대조"] == "일치" and not [x for x in r["판단"] if x["항목"] == "원장 합계 대조"]
    r0 = c(T, {**BASE, "ledger": LEDGER})
    assert "원장합계_대조" not in r0["계산"]
