"""0.9.0 입력 단일화(원장형 ledger만 받음)에 맞춰 잠근 정답 테스트의 옛 입력을 원장형으로 옮기는 변환기 (Claude 작성 2026-10-14).
테스트 사례와 기대값은 그대로 두고 호출 직전에만 변환한다. 변환 규칙이 곧 "옛 입력 ↔ 원장 항목" 대응표다.
"""


def _ent(a):
    a = dict(a)
    if "expenses" in a:
        ledger = []
        for i, e in enumerate(a.pop("expenses") or []):
            item = {"항목": f"지출{i + 1}", "금액": e["amount"], "증빙": e.get("evidence", "없음"),
                    "건당기준초과": e.get("over_30k", True)}
            if e.get("congratulatory"):
                item["성격"] = "경조금"
            elif e.get("culture"):
                item["성격"] = "문화"
            ledger.append(item)
        a["ledger"] = ledger
    if "revenue_general" in a or "revenue_related" in a:
        g = int(a.pop("revenue_general", 0) or 0)
        r = int(a.pop("revenue_related", 0) or 0)
        a["revenue"] = {"매출액": g + r, "특수관계매출": r}      # revenue_general = 매출액 − 특수관계매출
    return a


def _simp(a):
    a = dict(a)
    if "supplies" in a or "purchases" in a:
        s = a.pop("supplies", None) or {}
        p = a.pop("purchases", None) or {}
        공급 = []
        card = int(s.get("card_receipt_issued", 0) or 0)
        mile = int(s.get("self_mileage", 0) or 0)
        rest = int(s.get("total", 0) or 0) - card - mile
        if card:
            공급.append({"항목": "신용카드매출전표·현금영수증 발급분", "금액": card})
        if mile:
            공급.append({"항목": "자기적립마일리지 결제분", "금액": mile})
        if rest:
            공급.append({"항목": "영수증 발급분", "금액": rest})
        매입 = []
        for key, name in [("tax_invoice_received", "세금계산서 수취분"), ("invoice_received", "계산서 수취분"),
                          ("no_tax_invoice_from_issuer", "세금계산서 미수취분(발급의무자로부터 매입)"),
                          ("exempt_farm_products", "면세농산물 구입분")]:
            v = int(p.get(key, 0) or 0)
            if v:
                매입.append({"항목": name, "금액": v})
        a["ledger"] = {"공급": 공급, "매입": 매입}
    return a


def _common(a):
    a = dict(a)
    if "input_tax" in a:
        it = a.pop("input_tax") or {}
        ledger = []
        nondeductible = int(it.get("taxable_only_nondeductible", 0) or 0)
        taxable = int(it.get("taxable_only", 0) or 0) - nondeductible      # 옛 taxable_only는 불공제분을 포함한 금액
        if taxable:
            ledger.append({"항목": "과세사업 전용", "매입세액": taxable, "사용처": "과세"})
        if nondeductible:
            ledger.append({"항목": "과세사업 전용(제39조 불공제)", "매입세액": nondeductible, "사용처": "불공제"})
        exempt = int(it.get("exempt_only", 0) or 0)
        if exempt:
            ledger.append({"항목": "면세사업 전용", "매입세액": exempt, "사용처": "면세"})
        for i, x in enumerate(it.get("attributed") or []):
            ledger.append({"항목": f"실지귀속{i + 1}", "매입세액": x["input_tax"], "사용처": "실지귀속", "과세비율": x["taxable_ratio"]})
        common = it.get("common") or {}
        common_has_keys = common.get("예정") is not None or common.get("확정") is not None
        if a.get("filing") == "예정":
            v = int(common.get("예정", 0) or 0)
            if v:
                ledger.append({"항목": "공통매입", "매입세액": v, "사용처": "공통"})
        else:
            v = int(common.get("확정", 0) or 0)
            if v:
                ledger.append({"항목": "공통매입", "매입세액": v, "사용처": "공통"})
            if common.get("예정") is not None:
                a["prior_common_input_tax"] = int(common.get("예정") or 0)
        # common 키가 있는데 ledger에 추가된 항목이 없으면(모두 0), 0원 항목을 하나 남겨 빈 ledger 방지
        if common_has_keys and not ledger:
            ledger.append({"항목": "공통매입", "매입세액": 0, "사용처": "공통"})
        a["ledger"] = ledger
    return a


def to_ledger(tool, a):
    if tool == "entertainment_adjustment":
        return _ent(a)
    if tool == "simplified_vat_return":
        return _simp(a)
    if tool == "common_input_tax":
        return _common(a)
    return a
