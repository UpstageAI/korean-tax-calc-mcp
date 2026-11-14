"""통고처분 벌금상당액 — 조세범 처벌절차법 제15조①1호, 시행령 제12조②·[별표] 벌금상당액 부과기준. Claude 작성(2026-11-14).

대조한 원문(국세법령정보시스템 연혁본 HWP — 법제처 Open API 점검 중이라 이쪽으로 받음):
- 별표 <개정 2014.6.30.>(시행령 제25435호, 2016.12.5. 제27652호본도 글자 같음) — 표 T1
- 별표 <개정 2019.2.12.>(제29539호, 2023.2.28. 제33277호본도 같음) — 표 T2: 저목(제15조①)·처목(제16조①) 신설, 경합 1)그룹에 제15·16조 추가,
  다목 근거 제4조③→②, 파목 기준 매입금액→공급가액, 하목 기준 문언 단순화
- 별표 <개정 2026.2.27.>(제36144호) — 표 T3: 비고 제1호 무면허 주류 행위 유형(수출·중개·수출입) 확대, 금액은 같음
부칙: 2012.2.2. 시행령 부칙은 '이 영 시행 후 최초로 부과하는 통고처분부터' 적용했으나 2019·2026 개정 부칙에는 적용례가 없음 →
기본은 통고처분일 기준으로 표를 고르고(해석 가정), 행위일 기준 표와 다르면 경고한다.
상한(자목)은 행위일 시행본 조세범 처벌법의 벌금 상한(tax_crime_guide와 같은 문언)으로 둔다.
"""
import datetime
from fractions import Fraction

M = 10_000
T2_FROM = datetime.date(2019, 2, 12)
T3_FROM = datetime.date(2026, 2, 27)
GROUP1 = {"제7조제1항·제2항", "제7조제3항", "제8조", "제9조제1항", "제9조제2항", "제11조제1항", "제11조제2항", "제15조제1항", "제16조제1항"}   # 바목1) — T1은 제15·16조 없음

# 목, 처벌법 조문, 필요한 금액 키
OFFENSES = {
    "제3조제1항본문": ("가목1)", "base"), "제3조제1항단서": ("가목2)", "base"),
    "제4조제1항": ("나목", "base"), "제4조제2항": ("다목", "base"), "제4조의2": ("라목", None), "제5조": ("마목", "base"),
    "제6조": ("바목", "liquor"), "제7조제1항·제2항": ("사목", "base"), "제7조제3항": ("아목", "base"), "제8조": ("자목", "base"),
    "제9조제1항": ("차목", None), "제9조제2항": ("카목", None), "제10조제1항": ("타목", "base"), "제10조제2항": ("파목", "base"),
    "제10조제3항": ("하목", "base"), "제10조제4항": ("거목", "base"), "제11조제1항": ("너목", "base"), "제11조제2항": ("더목", "base"),
    "제12조제1호~제3호": ("러목", None), "제12조제4호": ("머목", "base"), "제13조제1항": ("버목", "base"), "제13조제2항": ("서목", "base"),
    "제14조": ("어목", "base"), "제15조제1항": ("저목", None), "제16조제1항": ("처목", "base"),
}
BASE_LABEL = {"제3조제1항본문": "포탈세액 또는 환급·공제받은 세액", "제3조제1항단서": "포탈세액 또는 환급·공제받은 세액",
              "제4조제1항": "연간 포탈세액 또는 환급·공제받은 세액", "제4조제2항": "연간 포탈세액 또는 환급·공제받은 세액", "제5조": "포탈세액",
              "제7조제1항·제2항": "체납액", "제7조제3항": "체납액(사목 1차 금액 계산용)", "제8조": "장부 연도와 직전 연도 부가가치세 과세표준의 1년간 평균액",
              "제10조제1항": "공급가액", "제10조제2항": "공급가액(2019.2.11.까지 표는 매입금액)", "제10조제3항": "공급가액(2019.2.11.까지 표는 공급가액 또는 매출·매입금액)",
              "제10조제4항": "알선·중개한 거래의 공급가액", "제11조제1항": "조세를 회피하거나 강제집행을 면탈한 세액(없으면 0)",
              "제11조제2항": "조세를 회피하거나 강제집행을 면탈한 세액(없으면 0)", "제12조제4호": "재사용한 인지세액",
              "제13조제1항": "징수하지 않은 세액", "제13조제2항": "납부하지 않은 세액", "제14조": "근로소득원천징수영수증·지급명세서에 적힌 총급여·총지급액",
              "제16조제1항": "신고의무 위반금액"}
LIQUOR = [(50, (50, 200, 100)), (100, (100, 300, 200)), (500, (200, 700, 400)), (1000, (300, 1000, 600)), (3000, (500, 2000, 1000)),
          (5000, (1000, 3000, 2000)), (10000, (2000, 3000, 3000)), (None, (3000, 3000, 3000))]   # 만원, (탁주, 위스키·브랜디, 그 밖)


def _table(d):
    return "T3" if d >= T3_FROM else "T2" if d >= T2_FROM else "T1"


TABLE_LABEL = {"T1": "별표 <개정 2014.6.30.>", "T2": "별표 <개정 2019.2.12.>", "T3": "별표 <개정 2026.2.27.>"}


def _clamp(x, lo=None, hi=None):
    if lo is not None and x < lo:
        x = Fraction(lo)
    if hi is not None and x > hi:
        x = Fraction(hi)
    return x


def _first(key, base, vat, prop, liquor, prof):
    """1차 위반 금액(사목·너목처럼 다른 목의 1차 금액을 쓰는 목을 위해)."""
    return _amount(key, 1, base, vat, prop, liquor, prof)[0]


def _amount(key, n, base, vat, prop, liquor, prof):
    """개별기준 금액 (금액, 설명). n = 1, 2, 3(3차 이상)."""
    i = min(n, 3) - 1
    b = Fraction(base or 0)
    if key == "제3조제1항본문":
        k = (Fraction(1, 2), 1, 2)[i]; return b * k, f"포탈세액등 {int(b):,} × {k}배"
    if key == "제3조제1항단서":
        k = (Fraction(1, 2), 2, 3)[i]; return b * k, f"포탈세액등 {int(b):,} × {k}배"
    if key in ("제4조제1항", "제4조제2항"):
        if b <= 100_000_000:
            v = b * (1, 2, 2)[i]; return v, f"연간 포탈세액등 {int(b):,}(1억 이하) × {(1, 2, 2)[i]}"
        v = (100_000_000 + (b - 100_000_000) * 3) * (1, 2, 2)[i]
        return v, f"[1억 + (1억 초과분 {int(b - 100_000_000):,} × 3)] × {(1, 2, 2)[i]}"
    if key == "제4조의2":
        v = (500, 1000, 3000)[i] * M; return Fraction(v), f"{v:,}원(정액)"
    if key == "제5조":
        k = (1, 3, 5)[i]; return b * k, f"포탈세액 {int(b):,} × {k}배"
    if key == "제6조":
        kind, liters, act, tax = liquor["kind"], Fraction(str(liquor["liters"])), liquor.get("act", "가"), Fraction(liquor.get("liquor_tax") or 0)
        col = {"탁주": 0, "위스키·브랜디": 1, "그 밖": 2}[kind]
        row = next(v for lim, v in LIQUOR if lim is None or liters <= lim)
        t = Fraction(row[col] * M)
        rate = {"가": 1, "나": Fraction(1, 2), "다": Fraction(3, 10)}[act]
        v = t * rate
        note = f"비고 제1호 {act}목: {kind} {float(liters):g}ℓ 표 금액 {int(t):,}" + (f" × {rate}" if rate != 1 else "")
        if tax * 3 > 30_000_000:
            v = tax * 3; note = f"주세상당액 {int(tax):,}의 3배가 3천만원 초과 → {int(v):,}(비고 제1호 단서)"
        v = v * (1, 2, 2)[i]
        return v, note + (" × 2" if i else "")
    if key == "제7조제1항·제2항":
        p = Fraction(prop) if prop is not None else None
        v = b * (1, 2, 2)[i]
        note = f"체납액 {int(b):,}" + (" × 2" if i else "")
        if p is not None and p < b:
            v = min(p, Fraction(30_000_000)); note = f"재산가액 {int(p):,}이 체납액보다 적어 재산가액(3천만원 한도)"
        return v, note
    if key == "제7조제3항":
        f1 = _first("제7조제1항·제2항", base, vat, prop, liquor, prof)
        k = (Fraction(2, 3), Fraction(4, 3), Fraction(4, 3))[i]
        return min(f1 * k, Fraction(20_000_000)), f"사목 1차 금액 {int(f1):,} × {k}(2천만원 한도)"
    if key == "제8조":
        k = (Fraction(10, 100), Fraction(20, 100), Fraction(20, 100))[i]
        return _clamp(b * k, 5_000_000, 20_000_000), f"평균 과세표준 {int(b):,} × {int(k * 100)}%(500만원~2천만원)"
    if key == "제9조제1항":
        v = (1000, 2000, 2000)[i] * M; return Fraction(v), f"{v:,}원(정액)"
    if key == "제9조제2항":
        v = (500, 1000, 1000)[i] * M; return Fraction(v), f"{v:,}원(정액)"
    if key in ("제10조제1항", "제10조제2항"):
        k = (Fraction(1, 2), 1, 2)[i]; t = b * vat; return t * k, f"공급가액 {int(b):,} × 세율 {float(vat):g} = {int(t):,} × {k}배"
    if key == "제10조제3항":
        k = (1, 2, 3)[i]; t = b * vat; return t * k, f"공급가액 {int(b):,} × 세율 {float(vat):g} = {int(t):,} × {k}배"
    if key == "제10조제4항":
        h1 = _first("제10조제3항", base, vat, prop, liquor, prof)
        k = ((Fraction(3, 2), 3, Fraction(9, 2)) if prof else (1, 2, 3))[i]
        return h1 * k, f"하목 1차 금액 {int(h1):,} × {k}" + ("(세무 대리 세무사·공인회계사·변호사)" if prof else "")
    if key == "제11조제1항":
        v = b * (Fraction(1, 2), 1, 1)[i]
        v = Fraction(500_000) if (b == 0 or v < 500_000) else min(v, Fraction(20_000_000))
        return v, f"회피·면탈 세액 {int(b):,}" + (" × 0.5" if i == 0 else "") + "(50만원~2천만원)"
    if key == "제11조제2항":
        n1 = _first("제11조제1항", base, vat, prop, liquor, prof)
        v = n1 * (Fraction(1, 2), 1, 1)[i]
        v = Fraction(500_000) if (b == 0 or v < 500_000) else min(v, Fraction(10_000_000))
        return v, f"너목 1차 금액 {int(n1):,}" + (" × 1/2" if i == 0 else "") + "(50만원~1천만원)"
    if key == "제12조제1호~제3호":
        return Fraction(20_000_000), "2천만원(정액)"
    if key == "제12조제4호":
        k, floor = ((5, 1_000_000), (10, 2_000_000), (10, 2_000_000))[i]
        return min(max(b * k, Fraction(floor)), Fraction(20_000_000)), f"인지세액 {int(b):,} × {k}와 {floor:,}원 중 큰 금액(2천만원 한도)"
    if key == "제13조제1항":
        return _clamp(b * (1, 2, 2)[i], 500_000, 10_000_000), f"징수하지 않은 세액 {int(b):,}" + (" × 2" if i else "") + "(50만원~1천만원)"
    if key == "제13조제2항":
        return _clamp(b * (1, 2, 2)[i], 1_000_000, 20_000_000), f"납부하지 않은 세액 {int(b):,}" + (" × 2" if i else "") + "(100만원~2천만원)"
    if key == "제14조":
        k = (Fraction(10, 100), Fraction(20, 100), Fraction(20, 100))[i]
        return b * k, f"총급여·총지급액 {int(b):,} × {int(k * 100)}%"
    if key == "제15조제1항":
        v = (1000, 2000, 3000)[i] * M; return Fraction(v), f"{v:,}원(정액)"
    if key == "제16조제1항":
        k = (Fraction(13, 100), Fraction(16, 100), Fraction(20, 100))[i]
        return b * k, f"신고의무 위반금액 {int(b):,} × {int(k * 100)}%"
    raise ValueError(key)


def _cap(key, base, vat, liquor, act_date, prof=False):
    """처벌법 벌금 상한(자목) — 행위일 시행본."""
    b = Fraction(base or 0)
    caps = {"제3조제1항본문": b * 2, "제3조제1항단서": b * 3, "제4조제1항": b * 5, "제4조제2항": b * 5, "제4조의2": Fraction(30_000_000),
            "제5조": b * 5, "제7조제1항·제2항": Fraction(30_000_000), "제7조제3항": Fraction(20_000_000), "제8조": Fraction(20_000_000),
            "제9조제1항": Fraction(20_000_000), "제9조제2항": Fraction(10_000_000), "제10조제1항": b * vat * 2, "제10조제2항": b * vat * 2,
            "제10조제3항": b * vat * 3, "제10조제4항": b * vat * 3, "제11조제1항": Fraction(20_000_000), "제11조제2항": Fraction(10_000_000),
            "제12조제1호~제3호": Fraction(20_000_000), "제12조제4호": Fraction(20_000_000), "제13조제1항": Fraction(10_000_000),
            "제13조제2항": Fraction(20_000_000), "제14조": b * Fraction(20, 100), "제15조제1항": Fraction(30_000_000), "제16조제1항": b * Fraction(20, 100)}
    if key == "제10조제4항" and prof:
        return b * vat * Fraction(9, 2), "세무 대리 세무사·공인회계사·변호사의 알선·중개는 형의 2분의 1 가중(처벌법 제10조④ 후단)"
    if key == "제6조":
        t3 = Fraction(liquor.get("liquor_tax") or 0) * 3
        return max(Fraction(30_000_000), t3), "3천만원(주세상당액 3배가 더 크면 그 금액)"
    return caps[key], None


def _add_months(d, m):
    y, mo = divmod(d.month - 1 + m, 12)
    y += d.year; mo += 1
    import calendar
    return datetime.date(y, mo, min(d.day, calendar.monthrange(y, mo)[1]))


def _voluntary_rate(v):
    """다목 감경률 — v = {type: 수정신고|기한후신고, filed_on, due_date(법정신고기한), before_investigation, additional_tax_paid}."""
    if not v.get("before_investigation") or not v.get("additional_tax_paid"):
        return Fraction(0), "세무조사·조세범칙조사 시작 전 신고이고 추가납부할 세액을 냈어야 함 — 감경 없음"
    due = datetime.date.fromisoformat(v["due_date"]); filed = datetime.date.fromisoformat(v["filed_on"])
    start = due + datetime.timedelta(days=1)
    m1, m6, y1, y2 = (_add_months(start, k) - datetime.timedelta(days=1) for k in (1, 6, 12, 24))
    if v["type"] == "수정신고":
        if filed <= m6: return Fraction(1, 2), f"법정신고기한 다음 날부터 6개월({m6}) 이내 수정신고 — 50% 감경"
        if filed <= y1: return Fraction(1, 5), f"6개월 초과 1년({y1}) 이내 수정신고 — 20% 감경"
        if filed <= y2: return Fraction(1, 10), f"1년 초과 2년({y2}) 이내 수정신고 — 10% 감경"
        return Fraction(0), "2년 넘어 수정신고 — 감경 없음"
    if filed <= m1: return Fraction(1, 2), f"법정신고기한 다음 날부터 1개월({m1}) 이내 기한 후 신고 — 50% 감경"
    if filed <= m6: return Fraction(1, 5), f"1개월 초과 6개월({m6}) 이내 기한 후 신고 — 20% 감경"
    return Fraction(0), "6개월 넘어 기한 후 신고 — 감경 없음"


def settlement(offenses, notice_date, act_date=None, table_basis="통고일"):
    문제 = []
    try:
        nd = datetime.date.fromisoformat(notice_date)
    except (TypeError, ValueError):
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["notice_date — 통고처분일 YYYY-MM-DD"]}
    ad = None
    if act_date:
        try:
            ad = datetime.date.fromisoformat(act_date)
        except ValueError:
            문제.append("act_date — 행위일 YYYY-MM-DD")
    if table_basis not in ("통고일", "행위일") or (table_basis == "행위일" and ad is None):
        문제.append("table_basis — '통고일'(기본) 또는 '행위일'(act_date 필요)")
    if not isinstance(offenses, list) or not offenses:
        문제.append("offenses — [{offense, count, base, ...}] 하나 이상")
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    tdate = nd if table_basis == "통고일" else ad
    tbl = _table(tdate)
    경고 = []
    if ad and _table(ad) != _table(nd):
        경고.append(f"행위일({ad}) 기준 표는 {TABLE_LABEL[_table(ad)]}, 통고일({nd}) 기준 표는 {TABLE_LABEL[_table(nd)]} — 개정 부칙에 적용례가 없어 어느 쪽인지 해석이 필요함(이 계산은 {table_basis} 기준)")
    if ad and datetime.date(2019, 1, 1) <= ad < T2_FROM and any(o.get("offense") in ("제15조제1항", "제16조제1항") for o in offenses if isinstance(o, dict)):
        경고.append("2019.1.1.~2.11. 행위: 처벌법 제15·16조는 범칙행위였지만 별표에는 2019.2.12. 개정 전까지 기준(저·처목)이 없었음")
    rows = []
    for idx, o in enumerate(offenses):
        if not isinstance(o, dict) or o.get("offense") not in OFFENSES:
            문제.append(f"offenses[{idx}].offense — {', '.join(OFFENSES)} 중 하나"); continue
        key = o["offense"]
        if tbl == "T1" and key in ("제15조제1항", "제16조제1항"):
            문제.append(f"offenses[{idx}] — {TABLE_LABEL[tbl]}에는 처벌법 {key}의 기준이 없음"); continue
        n = o.get("count", 1)
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            문제.append(f"offenses[{idx}].count — 1(1차), 2(2차), 3(3차 이상): 행위일 이전 최근 3년간 같은 범칙행위로 통고처분·유죄 확정받은 횟수 + 1"); continue
        need = OFFENSES[key][1]
        base = o.get("base")
        if need == "base" and (isinstance(base, bool) or not isinstance(base, (int, float)) or base < 0):
            문제.append(f"offenses[{idx}].base — {BASE_LABEL.get(key, '기준 금액')}(원)"); continue
        liquor = o.get("liquor")
        if need == "liquor":
            if not isinstance(liquor, dict) or liquor.get("kind") not in ("탁주", "위스키·브랜디", "그 밖") or not isinstance(liquor.get("liters"), (int, float)) \
                    or liquor.get("act", "가") not in ("가", "나", "다"):
                문제.append(f"offenses[{idx}].liquor — {{kind: 탁주|위스키·브랜디|그 밖, liters: 제조·판매량(ℓ), act: 가(무면허 제조 등)|나(면허 주류 무면허 도매·수출입·중개)|다(무면허 소매), liquor_tax: 주세상당액}}"); continue
        vat = Fraction(str(o.get("vat_rate", 0.1)))
        habitual, vol, aid, impaired = bool(o.get("habitual")), o.get("voluntary"), o.get("aiding_reduction"), bool(o.get("impaired"))
        if (habitual or vol) and key not in ("제3조제1항본문", "제3조제1항단서"):
            문제.append(f"offenses[{idx}] — 상습 가중(나목)과 수정신고 감경(다목)은 처벌법 제3조에만"); continue
        if aid is not None:
            try:
                aid = Fraction(str(aid)); assert 0 <= aid < 1
            except (ValueError, AssertionError, ArithmeticError):
                문제.append(f"offenses[{idx}].aiding_reduction — 방조 감경률(0 이상 1 미만, 라목은 재량)"); continue
        if vol is not None:
            try:
                assert vol.get("type") in ("수정신고", "기한후신고")
                datetime.date.fromisoformat(vol["due_date"]); datetime.date.fromisoformat(vol["filed_on"])
            except (AssertionError, KeyError, ValueError, TypeError, AttributeError):
                문제.append(f"offenses[{idx}].voluntary — {{type: 수정신고|기한후신고, due_date: 법정신고기한, filed_on: 신고일, before_investigation: bool, additional_tax_paid: bool}}"); continue
        amt, note = _amount(key, n, base, vat, o.get("property_value"), liquor or {}, bool(o.get("professional")))
        steps = [f"개별기준({OFFENSES[key][0]}, {min(n, 3)}차{' 이상' if n >= 3 else ''}): {note} = {int(amt):,}"]
        cur = amt
        if habitual:
            cur = cur * Fraction(3, 2); steps.append(f"나목 상습 50% 가중 → {int(cur):,}")
        if vol is not None:
            r, why = _voluntary_rate(vol)
            if r:
                cur = cur * (1 - r)
            steps.append(f"다목: {why}" + (f" → {int(cur):,}" if r else ""))
        if aid:
            cur = cur * (1 - aid); steps.append(f"라목 방조 감경 {float(aid):.0%}(재량, 입력값) → {int(cur):,}")
        if impaired:
            cur = cur / 2; steps.append(f"마목 심신미약·청각 및 언어 장애 50% 감경 → {int(cur):,}")
        cap, capnote = _cap(key, base, vat, liquor or {}, ad, bool(o.get("professional")))
        capped = False
        if cur > cap:
            cur, capped = cap, True; steps.append(f"자목: 처벌법 벌금 상한 {int(cap):,}" + (f"({capnote})" if capnote else "") + "을 넘어 상한으로")
        fin = int(cur) // 10 * 10
        steps.append(f"아목: 10원 미만 절사 → {fin:,}")
        rows.append({"offense": key, "목": OFFENSES[key][0], "차수": min(n, 3), "개별기준": int(amt), "벌금상당액": fin, "상한_적용": capped, "단계": steps})
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}
    g1keys = GROUP1 - ({"제15조제1항", "제16조제1항"} if tbl == "T1" else set())
    g1 = [r["벌금상당액"] for r in rows if r["offense"] in g1keys]
    g2 = [r["벌금상당액"] for r in rows if r["offense"] not in g1keys]
    경합 = []
    t1 = 0
    if g1:
        if len(g1) > 1:
            t1 = min(max(g1) + max(g1) // 2, sum(g1))
            경합.append(f"바목1) 그룹({len(g1)}건): 가장 무거운 {max(g1):,} + 1/2 = {max(g1) + max(g1) // 2:,}, 합산액 {sum(g1):,} 한도 → {t1:,}")
        else:
            t1 = g1[0]
    t2 = sum(g2)
    if len(g2) > 1:
        경합.append(f"바목2) 그룹({len(g2)}건): 합산 {t2:,}")
    total = (t1 + t2) // 10 * 10
    if g1 and g2:
        경합.append(f"바목3): 두 그룹을 각각 산정해 합산 {t1:,} + {t2:,} = {total:,}")
    return {"결과": {"벌금상당액_합계": total, "범칙행위별": rows, "경합": 경합, "적용_별표": TABLE_LABEL[tbl], "표_기준일": f"{table_basis} {tdate}"},
            "경고": 경고,
            "근거": "조세범 처벌절차법 제15조①1호·④·⑤, 시행령 제12조②·[별표] 벌금상당액 부과기준(" + TABLE_LABEL[tbl] + "), 조세범 처벌법 해당 조문(벌금 상한)",
            "판단": [{"항목": "납부·고발", "결론": "통고서를 송달받은 날부터 15일 이내에 이행하지 않으면 고발해야 함. 15일이 지났어도 고발 전에 이행하면 고발하지 않음. "
                                            "벌금상당액은 국세징수법 제12조①의 방법으로 납부(2023.1.17. 신설)", "근거": "조세범 처벌절차법 제17조②, 제15조⑤"},
                   {"항목": "통고 이행 효과", "결론": "통고대로 이행하면 같은 사건으로 다시 조사받거나 처벌받지 않음", "근거": "조세범 처벌절차법 제15조③"}],
            "주의": ["가중·감경은 사목 순서(횟수→상습→수정신고→방조→심신미약→경합)로 앞 단계 결과에 차례로 적용함 — 각 목의 문언은 '개별기준에 따른 벌금상당액의 …'이라 "
                   "개별기준 금액에 각각 곱하는 해석도 가능(실무 확인 필요)",
                   "자목 상한은 범칙행위마다 가중·감경 뒤에 적용하고, 경합 가중 뒤 다시 적용하지 않음",
                   "개정 별표의 기준일(행위일·통고처분일)은 부칙 적용례가 없어 해석이 필요함 — 기본은 통고처분일(2012.2.2. 시행령 부칙의 '최초로 부과하는 통고처분부터' 선례)",
                   "범칙행위 해당 여부, 제3조① 단서 해당 여부, 상습·방조 여부, 위반 횟수는 사실 판단 — 요건은 조문 MCP의 tax_crime_guide로 확인",
                   "통고처분·고발·무혐의 같은 처분 선택과 위원회 심의는 계산하지 않음 — 조세범칙조사 절차(조문 MCP)"]}
