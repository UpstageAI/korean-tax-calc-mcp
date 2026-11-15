"""끝수 처리 한 곳 — 어느 금액에서 얼마 미만을 버리는지(전 도구 공통 규칙).

원문(법제처 2026-11-15 조회)
  국고금 관리법 제47조(2011.4.4. 전문개정 뒤 그대로 — 2011.10.5.·2026.1.2. 시행본 같은 문언)
    제1항 "국고금의 수입 또는 지출에서 10원 미만의 끝수가 있을 때에는 그 끝수는 계산하지 아니하고,
           전액이 10원 미만일 때에도 그 전액을 계산하지 아니한다" (단서: 분할 징수·수납·지급 때 10원 미만 분할금액·끝수를
           최초의 수입금·지급금에 합산 — 시행령 제109조의2제1항)
    제2항 "국세의 과세표준액을 산정할 때 1원 미만의 끝수가 있으면 이를 계산하지 아니한다"
  지방세기본법 제59조(2017.3.28. 전부개정 법률 제14474호 — 그 전 시행본은 제75조, 문언 같음)
    "지방자치단체의 징수금의 끝수 계산에 관하여는 「국고금 관리법」 제47조를 준용한다"
해석(국세법령정보시스템 2026-11-15 조회)
  원천세과-240(2012.5.2. 등록): 일용근로소득을 일괄지급할 때 원천징수세액은 일용근로자별로 매일 단위로 계산해 더하고,
    더한 세액을 납부하는 때에 10원 미만 끝수를 버림
  법인22601-2481(1989.7.6. 등록): 국고금 단수 계산은 계산 편의에 관한 것 — 인명별·월별(과세기간별) 합계 후 10원 미만을 계산하지 않음

규칙
  1) 과세표준: 1원 미만 버림(제47조제2항).
  2) 세액 계산값(산출세액·공제·감면·가산세·결정세액 등 신고서에 적는 금액): 원 단위. 원 미만 처리 규정이 없어 최종 금액에서만 버림.
  3) 국고(지방세는 지방자치단체)에 실제로 내거나 돌려받는 금액: 10원 미만 버림(제47조제1항).
     신고납부 세목은 신고서의 납부할 세액·환급세액, 원천징수·특별징수는 소득자별·지급분 합계(위 두 해석)가 그 금액이다.
     도구는 2)의 값을 그대로 두고 3)의 값을 결과의 '납부할 금액(10원 미만 버림)'(환급뿐이면 '환급받을 금액(10원 미만 버림)')에 따로 낸다.
     (withholding_tax·nonresident_withholding은 한 소득자·한 번 지급분의 원천징수세액 자체가 3)이라 그 값을 10원 단위로 낸다.)
  4) 따로 정한 규정이 있으면 그 규정: 통고처분 벌금상당액(조세범 처벌절차법 시행령 별표),
     건물 기준시가 ㎡당 금액 1,000원 미만 버림(국세청 고시).
"""
from __future__ import annotations

ROUNDING_BASIS = "국고금 관리법 제47조제1항(수입·지출 10원 미만 끝수 버림)·제2항(과세표준 1원 미만 버림)"
LOCAL_ROUNDING_BASIS = "지방세기본법 제59조(2017.3.27.까지 제75조 — 국고금 관리법 제47조 준용)"
ROUNDING_NOTE = "끝수: 과세표준은 1원 미만, 세액은 원 미만을 버리고 계산 — 납부할 때 10원 미만 끝수는 버림(" + ROUNDING_BASIS + ")"
WITHHOLDING_ROUNDING_BASIS = ("국고금 관리법 제47조제1항 — 원천징수세액은 소득자별·지급분 합계를 납부하는 때에 10원 미만 끝수 버림"
                              "(원천세과-240, 법인22601-2481)")
PAY_KEY = "납부할 금액(10원 미만 버림)"
REFUND_KEY = "환급받을 금액(10원 미만 버림)"   # 결과가 환급세액뿐인 도구(국고금의 지출)


def pay_amount(tax: int) -> int:
    """국고에 내거나(수입) 돌려받는(지출) 금액 — 10원 미만 끝수 버림, 전액이 10원 미만이면 0(제47조제1항). 음수(환급)는 절댓값 기준."""
    tax = int(tax)
    return tax // 10 * 10 if tax >= 0 else -(-tax // 10 * 10)


# 도구 → 결과에서 '그대로 내거나 돌려받는 금액'인 키(국세·지방세는 수납 기관이 달라 키마다 따로 버림).
# 산출세액·감면 후 세액·가산세처럼 다른 금액과 합쳐서 내는 계산값은 넣지 않는다(규칙 2).
PAYABLE_KEYS: dict[str, tuple[str, ...]] = {
    # 원천징수·특별징수(소득자별·지급분)
    "nonresident_capital_gains_withholding": ("원천징수세액", "지방소득세"),
    "daily_worker_withholding": ("원천징수세액",),
    "retirement_income_tax": ("퇴직소득세",),
    "deemed_bonus_resettlement": ("추가원천징수세액",),
    "foreign_worker_flat_tax": ("월_원천징수_단일세율",),
    # 신고납부(신고서의 납부할 세액·환급세액)
    "vat_return_general": ("차가감_납부세액",),
    "simplified_vat_return": ("차가감납부세액", "환급세액"),
    "vat_simplified_taxpayer": ("차가감_납부세액", "환급세액"),
    "vat_reverse_charge": ("대리납부세액_합계",),
    "inheritance_tax": ("납부할세액",),
    "gift_tax": ("납부할세액",),
    "nominee_gift_tax": ("납부할세액",),
    "nonresident_inheritance_gift": ("납부할세액",),
    "rural_special_tax": ("농어촌특별세",),
    "loss_carryback_refund": ("환급세액",),
}
_LOCAL_KEYS = ("지방소득세",)


def attach_pay_amount(tool: str, out):
    """등록된 도구의 결과에 '납부할 금액(10원 미만 버림)'을 더한다 — 계산값은 그대로 둔다."""
    keys = PAYABLE_KEYS.get(tool)
    if not keys or not isinstance(out, dict) or not isinstance(out.get("결과"), dict):
        return out
    res = out["결과"]
    key = REFUND_KEY if all("환급" in k for k in keys) else PAY_KEY
    if key in res:
        return out
    found = {k: pay_amount(res[k]) for k in keys if isinstance(res.get(k), int) and not isinstance(res.get(k), bool)}
    if not any(found.values()):      # 낼 금액도 돌려받을 금액도 없으면 붙이지 않음
        return out
    res[key] = next(iter(found.values())) if len(keys) == 1 else found
    basis = ROUNDING_BASIS + (", " + LOCAL_ROUNDING_BASIS if any(k in _LOCAL_KEYS for k in found) else "")
    out.setdefault("끝수", "세액은 원 단위 계산값(원 미만 처리 규정이 없어 최종 금액에서만 버림), 국고에 내거나 돌려받을 때 10원 미만 끝수를 버림 — " + basis
                   + (". 여러 날·여러 건을 한꺼번에 지급하면 소득자별로 더한 뒤 버림(원천세과-240)" if tool == "daily_worker_withholding" else ""))
    return out
