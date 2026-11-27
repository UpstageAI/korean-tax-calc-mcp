"""초과인출금 지급이자 필요경비불산입(소득세법 제33조제1항제5호, 시행령 제61조제1항제2호·제78조의2, 시행규칙 제27조).

개인사업자의 부채 합계가 사업용 자산 합계를 넘는 금액(초과인출금)에 상당하는 지급이자를 가사관련경비로 보아 필요경비에 넣지 않는다.
- 초과인출금 = 부채(필요경비에 산입한 충당금·준비금 제외, 규칙 제27조제3항) − 사업용 자산. 0 미만이면 0.
- 산식(규칙 제27조제1항): 지급이자 × 초과인출금 적수 ÷ 차입금 적수. 초과인출금 적수가 차입금 적수를 넘으면 넘는 부분은 없는 것으로 본다(제2항).
- 순서(영 제78조의2제1항): 채권자불분명 차입금 이자 → 건설자금 이자 → 이 계산 → 업무무관 지급이자. 앞 순서로 이미 부인된 이자와 그 차입금 적수는 뺀다.
- 이자율이 여럿이면 높은 이자율부터 부인한다(영 제78조의2제2항) — 초과인출금 적수를 높은 이자율 차입금 적수에 먼저 채운다.
2016~2026 연말 시행본의 산식·순서 문언이 같다(2025.12.30. 개정은 '기획재정부령' → '재정경제부령' 명칭뿐).
"""
from fractions import Fraction

_BASIS = [["소득세법", "제33조", "①5호", "가사의 경비와 이에 관련되는 경비는 필요경비에 산입하지 아니한다"],
          ["소득세법 시행령", "제61조", "①2호", "사업용 자산의 합계액이 부채의 합계액에 미달하는 경우 그 미달하는 금액에 상당하는 부채의 지급이자"],
          ["소득세법 시행규칙", "제27조", "①~③", "지급이자 × 초과인출금 적수 ÷ 차입금 적수. 초과인출금 적수가 차입금 적수를 넘는 부분은 없는 것으로 봄. 부채에서 필요경비에 산입한 충당금·준비금 제외"],
          ["소득세법 시행령", "제78조의2", "①②", "지급이자 필요경비불산입 순서 — 채권자불분명, 건설자금, 초과인출금, 업무무관. 이자율이 다르면 높은 이자율부터"]]


def _int(v, what):
    if isinstance(v, bool) or v is None:
        raise ValueError(what)
    try:
        f = Fraction(str(v))
    except (ValueError, ZeroDivisionError):
        raise ValueError(what)
    if f.denominator != 1 or f < 0:
        raise ValueError(what)
    return int(f)


def excess_withdrawal_interest(borrowings, excess_jeoksu=None, months=None):
    if not isinstance(borrowings, list) or not borrowings:
        return {"error": "입력 확인 필요 — borrowings에 차입금을 1개 이상 넣는다"}
    if (excess_jeoksu is None) == (months is None):
        return {"error": "입력 확인 필요 — 초과인출금 적수(excess_jeoksu)와 월별 자산·부채(months) 중 하나만 넣는다"}
    월별 = []
    try:
        if months is not None:
            if not isinstance(months, list) or not months:
                return {"error": "입력 확인 필요 — months에 기간을 1개 이상 넣는다"}
            total = 0
            for i, m in enumerate(months):
                if not isinstance(m, dict):
                    return {"error": f"입력 확인 필요 — months[{i}]는 객체여야 함"}
                name = str(m.get("기간") or f"기간{i + 1}")
                자산 = _int(m.get("자산"), f"'{name}': 자산(원, 0 이상 정수)")
                부채 = _int(m.get("부채"), f"'{name}': 부채(원, 0 이상 정수)")
                충당 = _int(m.get("충당금준비금", 0), f"'{name}': 충당금준비금(원, 0 이상 정수)")
                일수 = _int(m.get("일수"), f"'{name}': 일수(1 이상 정수)")
                if 일수 < 1:
                    raise ValueError(f"'{name}': 일수(1 이상 정수)")
                if 충당 > 부채:
                    raise ValueError(f"'{name}': 충당금준비금은 부채에 포함된 금액이라 부채보다 클 수 없음")
                초과 = max(0, 부채 - 충당 - 자산)
                월별.append({"기간": name, "자산": 자산, "부채": 부채, "충당금준비금": 충당, "초과인출금": 초과, "일수": 일수, "적수": 초과 * 일수})
                total += 초과 * 일수
            excess = total
        else:
            excess = _int(excess_jeoksu, "excess_jeoksu(원·일, 0 이상 정수)")
        rows = []
        for i, b in enumerate(borrowings):
            if not isinstance(b, dict):
                return {"error": f"입력 확인 필요 — borrowings[{i}]는 객체여야 함"}
            name = str(b.get("차입금") or f"차입금{i + 1}")
            이자 = _int(b.get("지급이자"), f"'{name}': 지급이자(원, 0 이상 정수)")
            적수 = _int(b.get("적수"), f"'{name}': 적수(차입금 적수, 원·일, 0 이상 정수)")
            불분명 = _int(b.get("채권자불분명_이자", 0), f"'{name}': 채권자불분명_이자(원, 0 이상 정수)")
            건설 = _int(b.get("건설자금_이자", 0), f"'{name}': 건설자금_이자(원, 0 이상 정수)")
            if 불분명 + 건설 > 이자:
                raise ValueError(f"'{name}': 채권자불분명_이자 + 건설자금_이자가 지급이자보다 큼")
            if 이자 > 0 and 적수 == 0:
                raise ValueError(f"'{name}': 지급이자가 있으면 적수가 0일 수 없음")
            rate = b.get("이자율")
            if rate is not None:
                try:
                    rate = Fraction(str(rate))
                except (ValueError, ZeroDivisionError):
                    raise ValueError(f"'{name}': 이자율(연 %, 숫자)")
                if rate < 0:
                    raise ValueError(f"'{name}': 이자율(연 %, 0 이상)")
            if b.get("제외_적수") is not None:
                제외 = Fraction(_int(b.get("제외_적수"), f"'{name}': 제외_적수(원·일, 0 이상 정수)"))
                if 제외 > 적수:
                    raise ValueError(f"'{name}': 제외_적수가 적수보다 큼")
            else:
                제외 = Fraction(적수) * (불분명 + 건설) / 이자 if 이자 else Fraction(0)
            rows.append({"name": name, "rate": rate, "이자": 이자, "적수": 적수, "불분명": 불분명, "건설": 건설,
                         "남은이자": 이자 - 불분명 - 건설, "남은적수": Fraction(적수) - 제외})
    except ValueError as e:
        return {"error": f"입력 확인 필요 — {e}"}
    if len(rows) > 1 and any(r["rate"] is None for r in rows):
        return {"error": "입력 확인 필요 — 차입금이 둘 이상이면 각각 이자율(연 %)이 필요함(높은 이자율부터 부인, 시행령 제78조의2제2항)"}
    order = sorted(range(len(rows)), key=lambda i: (-(rows[i]["rate"] or 0), i))
    차입적수 = sum(r["남은적수"] for r in rows)
    적용 = min(Fraction(excess), 차입적수)
    remaining, total, 배분 = 적용, Fraction(0), []
    for i in order:
        r = rows[i]
        used = min(remaining, r["남은적수"])
        amt = Fraction(r["남은이자"]) * used / r["남은적수"] if r["남은적수"] else Fraction(0)
        remaining -= used
        total += amt
        배분.append({"차입금": r["name"], "이자율": (float(r["rate"]) if r["rate"] is not None else None), "지급이자": r["이자"],
                     "선순위_부인_이자": r["불분명"] + r["건설"], "대상_지급이자": r["남은이자"], "대상_차입금_적수": float(r["남은적수"]),
                     "배분된_초과인출금_적수": float(used), "필요경비불산입": round(float(amt), 2)})
    불산입 = int(total)   # 원 미만 절사는 합계에서 한 번
    불분명합, 건설합 = sum(r["불분명"] for r in rows), sum(r["건설"] for r in rows)
    주의 = ["초과인출금 지급이자(시행령 제78조의2제1항제3호)만 계산함. 채권자불분명 차입금 이자·건설자금 이자는 입력한 금액을 앞 순서로 보아 대상에서 빼기만 했고, 업무무관 지급이자(제4호)는 계산하지 않음",
            "원 미만 절사 시점은 규정이 없어 이자율별 금액은 자르지 않고 합계에서 한 번 절사함"]
    if Fraction(excess) > 차입적수:
        주의.append("초과인출금 적수가 차입금 적수를 넘어 넘는 부분은 없는 것으로 봄(시행규칙 제27조제2항) — 대상 지급이자 전액 불산입")
    if months is not None:
        주의.append("적수를 기간 말 잔액 × 일수로 계산함(시행규칙 제27조제1항 후단 — 매월 말 잔액에 경과일수를 곱해 계산할 수 있음)")
    if any(b.get("제외_적수") is None and (r["불분명"] + r["건설"]) for b, r in zip(borrowings, rows)):
        주의.append("앞 순서로 부인된 이자의 차입금 적수는 그 차입금 적수 × (부인 이자 ÷ 지급이자)로 봄 — 실제 적수가 다르면 제외_적수로 직접 넣는다")
    산식 = " + ".join(f"{x['대상_지급이자']:,} × {x['배분된_초과인출금_적수']:,.0f} ÷ {x['대상_차입금_적수']:,.0f}" for x in 배분 if x["배분된_초과인출금_적수"]) or "0"
    return {"결과": {"필요경비불산입액": 불산입, "선순위_채권자불분명_이자": 불분명합, "선순위_건설자금_이자": 건설합},
            "계산": {"초과인출금_적수": excess, "대상_차입금_적수": float(차입적수), "적용_적수": float(적용), "이자율별": 배분, **({"기간별": 월별} if 월별 else {})},
            "판단": [{"항목": "초과인출금 지급이자", "결론": f"필요경비불산입 {불산입:,}원" + (" (초과인출금 없음)" if excess == 0 else ""),
                      "근거": "소득세법 시행령 제61조①2호, 시행규칙 제27조, 시행령 제78조의2"}],
            "근거": _BASIS, "주의": 주의, "산식": f"{산식} = {불산입:,}원(원 미만 절사)"}
