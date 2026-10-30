"""개인사업자 기부금 필요경비 산입(소득세법 제34조, 시행령 제79조④·제81조③⑤, 조세특례제한법 제58조①단서·제76조①단서). 작성 Claude 2026-10-30.
순서(영 제81조④): 정치자금·고향사랑 기부금 10만원 초과분 → 특례기부금(한도 = 기준소득금액 − 이월결손금) → 일반기부금(종교 있으면 10% + min(20%, 종교 외), 없으면 30%).
이월기부금은 같은 구분 안에서 먼저 산입(영 제79조④). 현물은 시가(시가 < 장부가액이면 장부가액)(영 제81조③). 자원봉사용역 = 봉사일수(8시간 단위, 올림)×8만원 + 부수 유류비(이동 유류비 제외)·재료비(영 제81조⑤, 본인분만)."""
from __future__ import annotations
import math
from typing import Any

PER_DAY = 80_000
SMALL = 100_000


def volunteer_value(hours: float, fuel: int = 0, transport_fuel: int = 0, materials: int = 0, own_hours_only: bool = True) -> dict:
    days = math.ceil(hours / 8) if hours > 0 else 0
    labor = days * PER_DAY
    direct = max(0, fuel - transport_fuel) + materials
    return {"봉사일수": days, "용역가액_일수분": labor, "직접비용": direct, "가액": labor + direct,
            "근거": "소득세법 시행령 제81조⑤ — 봉사일수(총 봉사시간÷8시간, 소수점은 1일)×8만원 + 부수 유류비(이동 유류비 제외)·재료비; 개인사업자는 본인 봉사분만"}


def in_kind_value(book: int, market: int | None) -> int:
    if market is None:
        return book
    return book if market < book else market


def individual_donation(year: int, base_income: int, carried_loss: int = 0, political: int = 0, hometown: int = 0,
                        special: int = 0, general: int = 0, religious: int = 0, carried_special: int = 0, carried_general: int = 0,
                        volunteer: dict | None = None, in_kind: list | None = None) -> dict[str, Any]:
    판단: list[dict] = []
    # 1) 현물·자원봉사 가액
    sp, ge, re = int(special), int(general), int(religious)
    for item in in_kind or []:
        v = in_kind_value(int(item.get("book", item.get("장부가액", 0)) or 0), item.get("market", item.get("시가")))
        kind = item.get("kind", item.get("구분", "일반"))
        if kind in ("특례",): sp += v
        elif kind in ("종교", "종교단체"): re += v
        else: ge += v
        판단.append({"항목": f"현물 기부({kind})", "결론": f"{v:,}원 — 시가(시가가 장부가액보다 낮으면 장부가액)", "근거": "소득세법 시행령 제81조③"})
    vol = None
    if volunteer:
        vol = volunteer_value(float(volunteer.get("hours", 0) or 0), int(volunteer.get("fuel", 0) or 0), int(volunteer.get("transport_fuel", 0) or 0), int(volunteer.get("materials", 0) or 0))
        sp += vol["가액"]
        판단.append({"항목": "특별재난지역 자원봉사용역", "결론": f"{vol['가액']:,}원 = {vol['봉사일수']}일×80,000 + 직접비용 {vol['직접비용']:,} → 특례기부금", "근거": "소득세법 제34조②1호나목, 시행령 제81조⑤"})
    # 2) 정치자금·고향사랑: 10만원까지 세액공제(100/110), 초과분은 사업자 필요경비(이월결손금 뺀 소득금액 한도)
    pol_credit = min(political, SMALL); pol_exp = max(0, political - SMALL)
    home_credit = min(hometown, SMALL); home_exp = max(0, hometown - SMALL)
    room = max(0, base_income - carried_loss)
    first = min(pol_exp + home_exp, room)
    판단.append({"항목": "정치자금·고향사랑 기부금", "결론": f"10만원 이하 {pol_credit + home_credit:,}원은 세액공제(기부금×100/110), 초과분 {pol_exp + home_exp:,}원은 필요경비(소득금액−이월결손금 {room:,}원 한도) → {first:,}원 산입", "근거": "조세특례제한법 제76조①단서, 제58조①단서·②"})
    # 3) 특례기부금: 한도 = 기준소득금액 − 이월결손금 (정치·고향 산입분 차감 후 잔여), 이월분 먼저
    sp_limit = max(0, room - first)
    sp_carry_used = min(carried_special, sp_limit); sp_cur_used = min(sp, sp_limit - sp_carry_used)
    sp_used = sp_carry_used + sp_cur_used; sp_over = sp - sp_cur_used
    판단.append({"항목": "특례기부금", "결론": f"한도 {sp_limit:,}원(기준소득 {base_income:,} − 이월결손금 {carried_loss:,} − 정치·고향 산입 {first:,}) → 이월분 {sp_carry_used:,} + 당기 {sp_cur_used:,} = {sp_used:,}원 산입, 당기 한도초과 {sp_over:,}원", "근거": "소득세법 제34조②, 시행령 제79조④(이월분 먼저)"})
    # 4) 일반기부금
    base_after = max(0, base_income - carried_loss - first - sp_used)   # A − (B + C): B = 특례 산입(정치·고향 포함)
    if re > 0:
        ge_limit = int(base_after * 0.10 + min(base_after * 0.20, ge + carried_general))
        formula = f"({base_after:,} × 10%) + min({base_after:,} × 20% = {int(base_after*0.2):,}, 종교단체 외 {ge + carried_general:,}) = {ge_limit:,}"
        basis = "소득세법 제34조③2호가목(종교단체 기부가 있는 경우)"
    else:
        ge_limit = int(base_after * 0.30)
        formula = f"{base_after:,} × 30% = {ge_limit:,}"
        basis = "소득세법 제34조③2호나목"
    total_general = ge + re
    ge_carry_used = min(carried_general, ge_limit); ge_cur_used = min(total_general, ge_limit - ge_carry_used)
    ge_used = ge_carry_used + ge_cur_used; ge_over = total_general - ge_cur_used
    판단.append({"항목": "일반기부금", "결론": f"한도 {formula} → 이월분 {ge_carry_used:,} + 당기 {ge_cur_used:,} = {ge_used:,}원 산입, 당기 한도초과 {ge_over:,}원(10년 이월)", "근거": basis + ", 제34조⑤"})
    total = first + sp_used + ge_used
    판단.append({"항목": "세액공제로 넘어가는 몫", "결론": f"필요경비에 산입하지 않은 특례 {sp_over:,}·일반 {ge_over:,}원은 사업자가 세액공제(제59조의4④)를 택하지 않으면 이월. 정치·고향 10만원 이하분 {pol_credit + home_credit:,}원은 세액공제", "근거": "소득세법 제34조⑤, 제59조의4④, 조세특례제한법 제58조·제76조"})
    return {"결과": {"필요경비_산입_합계": total, "정치·고향_초과분_산입": first, "특례기부금_산입": sp_used, "일반기부금_산입": ge_used, "특례_한도초과_이월": sp_over, "일반_한도초과_이월": ge_over,
                   "기부금_산입_후_사업소득금액": base_income - total, "정치·고향_세액공제_대상(10만원_이하)": pol_credit + home_credit},
            "계산": {"기준소득금액": base_income, "이월결손금": carried_loss, "특례기부금_당기(현물·자원봉사 포함)": sp, "일반기부금_당기(종교 외)": ge, "종교단체_기부금": re, "특례_한도": sp_limit, "일반_한도": ge_limit, "자원봉사용역": vol},
            "판단": 판단, "근거": "소득세법 제34조②③⑤, 시행령 제79조④·제81조③④⑤; 조세특례제한법 제58조·제76조"}
