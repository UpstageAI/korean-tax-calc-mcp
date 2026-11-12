"""충당부채(포인트·마일리지, 판매보증 등) 세무조정 다기간 추적. Claude 작성(2026-11-12).

법인세법은 손금으로 인정하는 충당금을 따로 정하고(제33조 퇴직급여충당금, 제34조 대손충당금, 제35조 구상채권상각충당금 등),
그 밖의 충당부채 전입액은 손금이 확정되지 않았으므로(제40조① — 확정된 날이 속하는 사업연도) 손금불산입(유보)하고 실제 사용·지출한
사업연도에 손금산입(△유보)한다. 조문은 2016·2026 시행본 대조(제40조① 문언 같음). 해석: 법인세과-1341(2009.11.30., 마일리지충당부채 유보),
서면인터넷방문상담2팀-1962(2005.11.30., 손금불산입된 충당금 사용액은 손금산입), 사전-2023-법규법인-0866(2024.4.2.).

모형(적립 연도별 묶음): 적립액 A, 유효기간 N년(적립한 해 + N년까지 사용 가능), 경과연수 k의 실제 사용률 r_k, 회계 설정 사용률 e, 부담률 c.
  적립한 해: 충당부채 설정 A×e×c → 손금불산입(유보)
  경과 k년: 사용 A×r_k×c → 충당부채와 상계, 손금산입(△유보). 설정 잔액보다 많이 쓰면 초과분은 그해 비용(세무조정 없음)
  적립 후 N년 되는 해 말: 남은 설정 잔액을 환입(회계 수익) → 익금불산입(△유보). 미사용 적립액 A×(1−Σr)는 소멸
"""
from fractions import Fraction

YEAR_MIN, YEAR_MAX = 2016, 2026
BASIS = "법인세법 제40조①(손익은 확정된 날이 속하는 사업연도), 제33조~제35조(손금으로 인정하는 충당금은 따로 정한 것만)"
RULINGS = ["법인세과-1341(2009.11.30.) — 마일리지충당부채는 세무조정으로 손금에 산입하지 않고 유보",
           "서면인터넷방문상담2팀-1962(2005.11.30.) — 손금불산입된 충당금을 사용한 금액은 손금산입",
           "사전-2023-법규법인-0866(2024.4.2.) — 충당부채는 실제 비용이 지출되어 상계되는 시점에 손금산입(△유보)"]


def _fr(x):
    return Fraction(str(x))


def provision_reserve_ledger(grants, valid_years, usage_pattern, expected_usage_rate=None, cost_ratio=1.0, kind="포인트"):
    문제 = []
    if kind not in ("포인트", "판매보증", "기타"):
        문제.append(f"kind={kind!r} — 허용값: 포인트·판매보증·기타")
    if not isinstance(valid_years, int) or not 0 <= valid_years <= 10:
        문제.append("valid_years — 유효기간(년, 0~10 정수). 0이면 적립한 해 안에만 사용")
    if not isinstance(usage_pattern, list) or not usage_pattern:
        문제.append("usage_pattern — 경과연수별 실제 사용률 목록(적립한 해부터), 예: [0.3, 0.4, 0.1]")
    else:
        for i, r in enumerate(usage_pattern):
            if not isinstance(r, (int, float)) or isinstance(r, bool) or r < 0:
                문제.append(f"usage_pattern[{i}] — 0 이상의 비율")
        if not 문제 and sum(_fr(r) for r in usage_pattern) > 1:
            문제.append(f"usage_pattern 합계 {float(sum(_fr(r) for r in usage_pattern)):.4f} — 1을 넘을 수 없음(적립액보다 많이 사용)")
        if isinstance(valid_years, int) and len(usage_pattern) > valid_years + 1:
            문제.append(f"usage_pattern 길이 {len(usage_pattern)} — 유효기간 {valid_years}년이면 경과 0~{valid_years}년, 최대 {valid_years + 1}개")
    if expected_usage_rate is not None and not (isinstance(expected_usage_rate, (int, float)) and 0 <= expected_usage_rate <= 1):
        문제.append("expected_usage_rate — 회계가 충당부채를 설정할 때 본 사용률(0~1)")
    if not (isinstance(cost_ratio, (int, float)) and 0 < cost_ratio <= 1):
        문제.append("cost_ratio — 적립액 1원을 쓸 때 회사가 부담하는 금액의 비율(0 초과 1 이하)")
    if not isinstance(grants, list) or not grants:
        문제.append("grants — [{year, amount}] 연도별 적립액(1건 이상)")
    else:
        seen = set()
        for i, g in enumerate(grants):
            y, a = (g or {}).get("year"), (g or {}).get("amount")
            if not isinstance(y, int) or not YEAR_MIN <= y <= YEAR_MAX:
                문제.append(f"grants[{i}].year={y!r} — {YEAR_MIN}~{YEAR_MAX}")
            elif y in seen:
                문제.append(f"grants[{i}].year={y} — 같은 연도가 두 번(연도별로 합쳐 입력)")
            seen.add(y)
            if not isinstance(a, int) or isinstance(a, bool) or a < 0:
                문제.append(f"grants[{i}].amount — 원(0 이상 정수)")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    rates = [_fr(r) for r in usage_pattern] + [Fraction(0)] * (valid_years + 1 - len(usage_pattern))
    used_rate = sum(rates)
    e = _fr(expected_usage_rate) if expected_usage_rate is not None else used_rate
    c = _fr(cost_ratio)
    first = min(g["year"] for g in grants)
    last = YEAR_MAX
    rows = {y: {"year": y, "적립액": 0, "충당부채_설정_손금불산입": 0, "사용_손금산입": 0, "환입_익금불산입": 0,
                "설정초과_사용_당기비용": 0, "소멸_적립액": 0} for y in range(first, last + 1)}
    later = []          # 2027년 이후에 일어날 일(연도표 밖)
    for g in sorted(grants, key=lambda x: x["year"]):
        t, A = g["year"], g["amount"]
        prov = int(A * e * c)                       # 원 미만 절사
        rows[t]["적립액"] += A
        rows[t]["충당부채_설정_손금불산입"] += prov
        bal, used_face = prov, 0
        for k in range(valid_years + 1):
            y = t + k
            use_face = int(A * rates[k])
            use_cost = int(A * rates[k] * c)
            offset = min(use_cost, bal)
            used_face += use_face
            if y > last:
                if use_cost or (k == valid_years and (bal or A - used_face)):
                    later.append({"적립연도": t, "연도": y, "사용_예정": use_cost,
                                  **({"환입_예정": bal - offset, "소멸_예정_적립액": A - used_face} if k == valid_years else {})})
                bal -= offset
                continue
            rows[y]["사용_손금산입"] += offset
            rows[y]["설정초과_사용_당기비용"] += use_cost - offset
            bal -= offset
            if k == valid_years:
                rows[y]["환입_익금불산입"] += bal
                rows[y]["소멸_적립액"] += A - used_face
                bal = 0
    유보, 연도별 = 0, []
    for y in range(first, last + 1):
        r = rows[y]
        유보 += r["충당부채_설정_손금불산입"] - r["사용_손금산입"] - r["환입_익금불산입"]
        r["유보_기말"] = 유보
        r["세무조정_순액"] = r["충당부채_설정_손금불산입"] - r["사용_손금산입"] - r["환입_익금불산입"]
        연도별.append(r)
    합계 = {k: sum(r[k] for r in 연도별) for k in ("적립액", "충당부채_설정_손금불산입", "사용_손금산입", "환입_익금불산입", "설정초과_사용_당기비용", "소멸_적립액")}
    판단 = [{"항목": "설정", "결론": f"적립한 해에 충당부채 = 적립액 × 설정 사용률 {float(e):.2%} × 부담률 {float(c):.2%} — 손금이 확정되지 않아 손금불산입(유보)", "근거": BASIS},
           {"항목": "사용", "결론": "실제 사용한 해에 충당부채와 상계한 금액을 손금산입(△유보). 설정 잔액을 넘는 사용분은 그해 비용이라 세무조정 없음", "근거": RULINGS[1]},
           {"항목": "소멸", "결론": (f"유효기간 {valid_years}년 — 적립 후 {valid_years}년 되는 해 말에 미사용 적립액 소멸(적립액의 {float(1 - used_rate):.2%}). "
                                 + ("설정 사용률이 실제 사용률보다 높아 남은 충당부채를 환입(회계 수익) → 익금불산입(△유보)" if e > used_rate else
                                    "설정 사용률이 실제 사용률과 같거나 낮아 소멸 때 환입할 충당부채 없음")), "근거": BASIS}]
    if kind == "포인트":
        주의 = ["매출의 일부를 이연수익(계약부채)으로 잡는 방식(K-IFRS 제1115호 고객충성제도)의 세무조정은 이 도구 범위 밖 — 해석례를 대조하지 못함",
               "부가가치세는 적립·소멸과 무관하게 포인트를 결제에 쓴 거래의 공급가액으로 정함(vat_tax_base_adjustments)"]
    else:
        주의 = ["실제 보증 수리·교환에 지출한 금액을 사용액으로 본 모형 — 지출 시기가 사용률과 다르면 연도별 금액을 조정"]
    주의.append("회사가 실제 계상한 충당부채 전입·환입액이 이 모형(설정 사용률 × 부담률)과 다르면 세무조정 금액도 다름 — 장부 금액으로 대사")
    out = {"결과": {"유보_기말": 유보, "합계": 합계}, "계산": {"연도별": 연도별}, "판단": 판단, "근거": BASIS, "해석": RULINGS, "주의": 주의}
    if later:
        out["계산"]["2027년_이후_예정"] = later
        out["주의"].append(f"{YEAR_MAX}년까지만 계산 — 그 뒤 사용·환입·소멸 예정분은 계산.2027년_이후_예정에 따로 표시(확정 금액 아님)")
    return out
