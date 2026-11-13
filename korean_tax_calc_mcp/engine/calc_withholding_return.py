"""원천징수이행상황신고서(소득세법 시행규칙 별지 제21호서식 제1쪽) 집계. Claude 작성(2026-11-13).

원문: 소득세법 시행규칙 별지 제21호서식 <개정 2025. 3. 21.> 제1쪽과 작성방법(제2쪽·제3쪽), 소득세법 제128조, 시행령 제185조(2025.12.31. 기준).
- 코드별 ④인원·⑤총지급액·⑥소득세 등·⑦농어촌특별세·⑧가산세를 받아 가감계(A10·A20·A30·A40·A47)와 총합계(A99)를 낸다.
- 환급할 세액(△)은 총합계에 넣지 않고 ⑮일반환급으로 모은다(작성방법 3.나). ⑱조정대상환급세액 = ⑭+⑮+⑯+⑰을
  납부할 세액에 코드 순서(A10, A20, …)대로 충당해 ⑨당월조정환급세액에 적고 남은 금액이 ⑩·⑪ 납부세액(작성방법 3.라).
- 이 도구는 세액을 계산하지 않는다 — 소득별 원천징수세액은 각 계산 도구(withholding_tax·nonresident_withholding 등)로 구해 넣는다.
범위 밖: 2026년(<개정 2026. 5. 22.> 서식에 A27·A28 칸 추가 — 적용 시기를 확인하지 못함), 2024년 이전, 부표(제4쪽 이후), 반기별 납부, 수정신고서의 상·하단 표기."""

BASIS = "소득세법 제128조, 시행령 제185조, 시행규칙 별지 제21호서식(원천징수이행상황신고서) 작성방법"
# (코드, 구분, 항목, 가감계 코드 또는 None)
ROWS = [("A01", "근로소득", "간이세액", "A10"), ("A02", "근로소득", "중도퇴사", "A10"), ("A03", "근로소득", "일용근로", "A10"), ("A04", "근로소득", "연말정산 합계", "A10"),
        ("A05", "근로소득", "연말정산 분납신청", None), ("A06", "근로소득", "연말정산 납부금액", "A10"),
        ("A21", "퇴직소득", "연금계좌", "A20"), ("A22", "퇴직소득", "그 외", "A20"),
        ("A25", "사업소득", "매월징수", "A30"), ("A26", "사업소득", "연말정산", "A30"),
        ("A41", "기타소득", "연금계좌", "A40"), ("A43", "기타소득", "종교인소득 매월징수", "A40"), ("A44", "기타소득", "종교인소득 연말정산", "A40"),
        ("A49", "기타소득", "가상자산", "A40"), ("A59", "기타소득", "인적용역", "A40"), ("A42", "기타소득", "그 외", "A40"),
        ("A48", "연금소득", "연금계좌", "A47"), ("A45", "연금소득", "공적연금(매월)", "A47"), ("A46", "연금소득", "연말정산", "A47"),
        ("A50", "이자소득", "이자소득", None), ("A60", "배당소득", "배당소득", None), ("A69", "저축 등 해지 추징세액 등", "저축 등 해지 추징세액 등", None),
        ("A70", "비거주자 양도소득", "비거주자 양도소득", None), ("A80", "법인", "내ㆍ외국법인원천", None), ("A90", "수정신고(세액)", "수정신고(세액)", None)]
SUBTOTAL = {"A10": "근로소득 가감계", "A20": "퇴직소득 가감계", "A30": "사업소득 가감계", "A40": "기타소득 가감계", "A47": "연금소득 가감계"}
# 납부·환급을 따지는 단위(작성방법 3.라: 근로·사업·기타·연금은 가감계 기준) — 충당 순서
UNITS = ["A10", "A20", "A30", "A40", "A47", "A50", "A60", "A69", "A70", "A80", "A90"]
CODES = {r[0]: r for r in ROWS}
ALIASES = {"근로소득 간이세액": "A01", "일용근로": "A03", "사업소득": "A25", "사업소득 매월징수": "A25", "기타소득": "A42", "기타소득 그 외": "A42", "인적용역 기타소득": "A59",
           "이자소득": "A50", "배당소득": "A60", "법인원천": "A80", "내·외국법인원천": "A80", "비거주자 양도소득": "A70", "퇴직소득": "A22"}
_NUM = ("인원", "총지급액", "소득세", "농어촌특별세", "가산세")


def withholding_return(year, month, lines, paid_month=None, prior_unrefunded=0, prior_refund_claimed=0, trust_refund=0, other_refund=0, refund_claim=0):
    문제 = []
    if year != 2025:
        문제.append(f"year={year} — 2025년 귀속분만 지원(<개정 2025. 3. 21.> 서식 대조). 2026년은 <개정 2026. 5. 22.> 서식에 사업소득 연말정산 분납 칸(A27·A28)이 추가됐고 적용 시기를 확인하지 못함")
    if not isinstance(month, int) or not 1 <= month <= 12:
        문제.append(f"month={month!r} — 귀속월 1~12")
    if paid_month is not None and (not isinstance(paid_month, int) or not 1 <= paid_month <= 12):
        문제.append(f"paid_month={paid_month!r} — 지급월 1~12")
    if not isinstance(lines, list) or not lines:
        문제.append("lines — [{코드, 인원, 총지급액, 소득세, 농어촌특별세?, 가산세?}] 1건 이상")
    vals = {c: dict.fromkeys(_NUM, 0) for c in CODES}
    notes = []
    for i, ln in enumerate(lines if isinstance(lines, list) else []):
        if not isinstance(ln, dict):
            문제.append(f"lines[{i}] — 객체여야 함"); continue
        code = str(ln.get("코드") or ln.get("code") or "").strip().upper()
        if not code:
            code = ALIASES.get(str(ln.get("소득구분") or "").strip(), "")
        if code in ("A27", "A28"):
            문제.append(f"lines[{i}].코드={code} — <개정 2026. 5. 22.> 서식에서 추가된 칸. 2025년 서식에는 없음"); continue
        if code in SUBTOTAL or code == "A99":
            문제.append(f"lines[{i}].코드={code} — 가감계·총합계는 도구가 계산(입력하지 않음)"); continue
        if code not in CODES:
            문제.append(f"lines[{i}] — 코드 {code or ln.get('소득구분')!r}를 모름. 쓸 수 있는 코드: {', '.join(CODES)}"); continue
        for k in _NUM:
            v = ln.get(k, 0)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
                문제.append(f"lines[{i}].{k}={v!r} — 원 단위 정수"); break
            if k in ("인원", "총지급액") and v < 0:
                문제.append(f"lines[{i}].{k}={v} — 0 이상"); break
            vals[code][k] += int(v)
        if ln.get("비거주자") or ln.get("메모"):
            notes.append((code, bool(ln.get("비거주자")), str(ln.get("메모") or "")))
    for k, v in (("prior_unrefunded", prior_unrefunded), ("prior_refund_claimed", prior_refund_claimed), ("trust_refund", trust_refund), ("other_refund", other_refund), ("refund_claim", refund_claim)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            문제.append(f"{k}={v!r} — 0 이상의 정수(원)")
    if not 문제 and prior_refund_claimed > prior_unrefunded:
        문제.append(f"prior_refund_claimed {prior_refund_claimed:,} > prior_unrefunded {prior_unrefunded:,} — ⑬기환급신청세액은 ⑫전월 미환급세액 이내")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    행 = {c: {"구분": CODES[c][1], "항목": CODES[c][2], **vals[c]} for c in CODES}
    # 가감계: 인원·총지급액은 A01+A02+A03+A04, 세액은 A01+A02+A03+A06(작성방법 3.다) — A05 분납신청은 가감계에 넣지 않음
    for sc, name in SUBTOTAL.items():
        members = [c for c in CODES if CODES[c][3] == sc]
        people = [c for c in members if c != "A06"] if sc == "A10" else members
        taxes = [c for c in members if c != "A04"] if sc == "A10" else members
        행[sc] = {"구분": name.split()[0], "항목": "가감계", "인원": sum(vals[c]["인원"] for c in people), "총지급액": sum(vals[c]["총지급액"] for c in people),
                 **{k: sum(vals[c][k] for c in taxes) for k in ("소득세", "농어촌특별세", "가산세")}}
    # 납부·환급: 단위별로 소득세 등(가산세 포함)과 농어촌특별세를 따로 본다
    일반환급 = 0
    납부 = {}
    for u in UNITS:
        r = 행[u]
        inc, rst = r["소득세"] + r["가산세"], r["농어촌특별세"]
        일반환급 += -min(inc, 0) - min(rst, 0)
        납부[u] = [max(inc, 0), max(rst, 0)]
    차감잔액 = prior_unrefunded - prior_refund_claimed
    조정대상 = 차감잔액 + 일반환급 + trust_refund + other_refund
    남은 = 조정대상
    for u in UNITS:
        a = min(남은, 납부[u][0]); 남은 -= a
        b = min(남은, 납부[u][1]); 남은 -= b
        행[u].update({"조정_소득세등": a, "조정_농어촌특별세": b, "당월조정환급세액": a + b, "납부_소득세등": 납부[u][0] - a, "납부_농어촌특별세": 납부[u][1] - b})
    당월조정계 = 조정대상 - 남은
    차월이월 = 남은
    if refund_claim > 차월이월:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"refund_claim {refund_claim:,} > ⑳차월이월 환급세액 {차월이월:,}"]}
    pos = lambda k: sum(max(행[u][k], 0) for u in UNITS)
    행["A99"] = {"구분": "총합계", "항목": "총합계", "인원": sum(행[u]["인원"] for u in UNITS), "총지급액": sum(행[u]["총지급액"] for u in UNITS),
                "소득세": pos("소득세"), "농어촌특별세": pos("농어촌특별세"), "가산세": pos("가산세"), "당월조정환급세액": 당월조정계,
                "납부_소득세등": sum(행[u]["납부_소득세등"] for u in UNITS), "납부_농어촌특별세": sum(행[u]["납부_농어촌특별세"] for u in UNITS)}
    pm = paid_month if paid_month is not None else month
    due_y, due_m = (year + 1, 1) if pm == 12 else (year, pm + 1)
    환급 = {"⑫ 전월 미환급세액": prior_unrefunded, "⑬ 기환급 신청세액": prior_refund_claimed, "⑭ 차감잔액": 차감잔액, "⑮ 일반환급": 일반환급, "⑯ 신탁재산(금융회사 등)": trust_refund,
           "⑰ 그 밖의 환급세액": other_refund, "⑱ 조정대상 환급세액": 조정대상, "⑲ 당월조정 환급세액계": 당월조정계, "⑳ 차월이월 환급세액": 차월이월, "㉑ 환급신청액": refund_claim}
    판단 = [{"항목": "가감계", "결론": "근로·퇴직·사업·기타·연금소득은 코드별 가감계(A10·A20·A30·A40·A47)로 납부·환급을 계산. 근로소득 세액 가감계는 A01+A02+A03+A06(분납신청 A05는 인원·세액만 적고 가감계에 넣지 않음)", "근거": "별지 제21호서식 작성방법 3.다·3.라"},
          {"항목": "총합계", "결론": "환급할 세액(△)은 총합계(A99)에 넣지 않고 ⑮일반환급에 합계", "근거": "별지 제21호서식 작성방법 3.나"}]
    if 조정대상:
        판단.append({"항목": "조정환급", "결론": f"⑱조정대상 환급세액 {조정대상:,}원을 납부할 세액에 코드 순서(A10, A20, …)대로 충당 → ⑲ {당월조정계:,}원, ⑳차월이월 {차월이월:,}원", "근거": "별지 제21호서식 작성방법 3.라3)"})
    for code, nonres, memo in notes:
        if nonres:
            where = "법인원천[A80]란" if code == "A80" else f"{CODES[code][1]}[{code}]란"
            판단.append({"항목": f"비거주자분({code})", "결론": f"비거주자 국내원천소득 중 개인분은 소득 종류별로 거주자분과 합산해 해당 소득란에, 법인분은 법인원천[A80]란에 적음 — {where}에 합산. "
                       "비거주자·외국법인에 국내원천소득을 지급했으면 원천징수이행상황신고서 부표를 반드시 작성" + (f" ({memo})" if memo else ""),
                       "근거": "별지 제21호서식 작성방법 2.사, 참고사항 1."})
    주의 = ["세액은 계산하지 않음 — 소득별 원천징수세액과 가산세는 각 계산 도구로 구해 넣은 값을 그대로 합산",
          "지방소득세는 이 서식에 칸이 없음(국세분만 적음)",
          f"신고·납부기한: 징수일이 속하는 달의 다음 달 10일({due_y}. {due_m}. 10.) — 공휴일·토요일이면 다음 날. 반기별 납부 승인을 받은 경우는 다루지 않음",
          "부표(제4쪽 이후), 원천징수세액환급신청서 부표, 수정신고서의 상·하단 표기는 다루지 않음"]
    결과 = {"귀속연월": f"{year}년 {month}월", "지급연월": f"{year}년 {pm}월", "총지급액": 행["A99"]["총지급액"], "징수세액_소득세등": 행["A99"]["소득세"], "징수세액_농어촌특별세": 행["A99"]["농어촌특별세"],
          "가산세": 행["A99"]["가산세"], "당월조정환급세액": 당월조정계, "납부세액_소득세등": 행["A99"]["납부_소득세등"], "납부세액_농어촌특별세": 행["A99"]["납부_농어촌특별세"], "차월이월_환급세액": 차월이월}
    order = [r[0] for r in ROWS]
    for sc in SUBTOTAL:           # 서식 순서: 가감계는 그 소득의 마지막 줄 뒤
        last = max(order.index(c) for c in CODES if CODES[c][3] == sc)
        order.insert(last + 1, sc)
    order.append("A99")
    inputs = [{"이름": f"{c}_{k}", "값": vals[c][k], "설명": f"{c} {CODES[c][2]} {k}"} for c in CODES for k in _NUM]
    inputs += [{"이름": n, "값": v, "설명": d} for n, v, d in (("전월_미환급세액", prior_unrefunded, "⑫"), ("기환급_신청세액", prior_refund_claimed, "⑬"), ("신탁재산_환급", trust_refund, "⑯"),
                                                           ("그밖의_환급세액", other_refund, "⑰"), ("환급신청액", refund_claim, "㉑"), ("귀속연도", year, "귀속연도"))]
    return {"결과": 결과, "계산": {"행": {c: 행[c] for c in order}, "환급세액_조정": 환급}, "판단": 판단, "근거": BASIS, "주의": 주의, "계산식_입력": inputs}
