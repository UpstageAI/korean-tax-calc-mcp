"""국제거래명세서(국조칙 별지 제16호서식(갑)) 칸 집계와 제출 의무·함께 낼 서식 판정. Claude 작성(2026-11-14).

대조한 원문(국세법령정보시스템 — 법제처 Open API 점검 중이라 이쪽으로 받음):
- 국제조세조정에 관한 법률 2026.1.2. 시행본 제16조제2항(국외특수관계인과 국제거래를 하는 납세의무자 — 사업연도 종료일이 속하는 달의 말일부터 6개월,
  대통령령 요건이면 제1호~제3호 서류 면제)
- 시행령 2026.2.27. 시행본 제36조: 1호(국제거래명세서 면제 — 재화 5억·용역 1억·무형자산 1억 모두 이하), 2호(요약손익계산서), 3호(정상가격 산출방법 신고서)
- 시행규칙 2024.3.22. 시행본 제27조: ①국제거래명세서는 별지 제16호서식(갑), 영 제12조제5항 지급보증 용역거래가 있으면 별지 제16호서식(을)을 함께 제출.
  ③정상가격 산출방법 신고서 — 용역거래 별지 제18호, 무형자산거래 별지 제19호, 그 밖의 국제거래 별지 제20호
- 시행규칙 부칙(2023.3.20.) 서식에 관한 적용례 ②: 별지 제16호서식(갑)·제17호~제20호서식 개정규정은 2023.1.1. 이후 개시 과세연도 자료 제출분부터
- 시행규칙 부칙(2024.3.22.) 서식에 관한 적용례: 서식 개정규정은 시행 이후 신고·신청·제출분부터(개정서식으로 종전 법령에 따른 신고를 할 수 없으면 종전 서식)
- 별지 제16호서식(갑) <개정 2024. 3. 22.> 작성방법 5·9·10: ⑨ = ⑩~㉑ 합계(⑰ 제외), ㉚ = ㉛~㊷ 합계(㊳ 제외),
  ⑰·㊳ = Σ(금액 × 일수) — 예시 (100원×60일)+(200원×180일) = 42,000원, ⑱·㊴ = ⑰·㊳ ÷ 사업연도 일수[365(366)] — 예시 42,000 ÷ 365 = 115원
- 별지 제20호서식 <개정 2024. 3. 22.> 작성방법 4: 국외특수관계인·거래대상별로 다른 방법을 쓰면 각각 별지로 작성

제출 의무(면제 금액·연도표)는 corporate_filing_obligations(engine/calc_cit.py)를 그대로 불러 같은 판정을 쓴다.

2016~2020 개시 사업연도의 서식 판(법제처 시행본별 별지 서식 PDF, 2026-11-15 대조 — 원자료 raw_wp6/forms):
- 구 시행규칙 제6조①(2015.12.2.~2020.3.13. 시행본): 국제거래명세서는 별지 제8호서식(갑), 제2조의4①3호(2020.3.13.부터 제2조의5①3호): 무형자산·용역 외의 국제거래는 별지 제1호의3서식.
- 별지 제8호서식(갑): <개정 2016.4.6.>(기획재정부령 제559호 — ⑯ 합계·⑰~㊳, 제출현황 칸 없음), <개정 2017. 3. 17.>(제613호 — ⑦~⑨ 제출현황 신설, ⑲ 합계·⑳~㊶),
  <개정 2018. 3. 19.>(제663호 — 칸 배치는 2017판과 같고 작성방법 5만 바뀜). 2021.3.16. 전부개정(제840호)으로 별지 제16호서식(갑)(칸 번호는 2017판과 같음, 문구 일부 다름),
  <개정 2022. 3. 18.>(제901호)에서 무형자산거래를 따로 떼어 칸 번호가 바뀜.
- 별지 제1호의3서식: <개정 2015.3.13.>, <개정 2020. 3. 13.>(제772호) — 칸 배치 같음. 2021.3.16.부터 별지 제20호서식(⑪ 순서가 지배·피지배로 바뀜).
- 적용: 제613호 부칙 제2조·제717호 부칙 제3조·제772호 부칙 제2조①·제840호 부칙 제3조·제901호 부칙 제4조 "시행 이후 제출하는 분부터". 제559호·제663호 부칙에는 서식 적용례가 없어 시행일(공포일)부터로 봄.
  → 제출기한 날 시행 중인 서식 판을 고른다(기한 전에 낸 경우는 그때 시행 중이던 판).
"""
import calendar
from datetime import date

from . import calc_cit as C

# (서식 칸 번호 매출, 매입, 입력 키, 이름, 거래 유형)
FIELDS = [
    ("⑩", "㉛", "inventory", "재고자산", "재화"),
    ("⑪", "㉜", "other_tangible", "기타 유형자산", "재화"),
    ("⑫", "㉝", "royalty", "무형자산 사용료", "무형"),
    ("⑬", "㉞", "intangible_sale", "무형자산 매매 등", "무형"),
    ("⑭", "㉟", "guarantee", "지급보증", "용역"),
    ("⑮", "㊱", "other_services", "기타 용역", "용역"),
    ("⑯", "㊲", "tangible_rental", "유형자산 사용료", "용역"),
    ("⑲", "㊵", "interest", "이자", "금전대차"),
    ("⑳", "㊶", "virtual_assets", "가상자산", "기타"),
    ("㉑", "㊷", "other", "가상자산 외 기타", "기타"),
]
AMOUNT_KEYS = [f[2] for f in FIELDS]
SIDE_KEYS = set(AMOUNT_KEYS) | {"loans"}
RELATIONS = ("지배", "피지배", "자매", "실질 지배", "본점ㆍ지점")
REL_ALIASES = {"본점·지점": "본점ㆍ지점", "본점지점": "본점ㆍ지점", "해외타지점": "본점ㆍ지점", "실질지배": "실질 지배"}
PARTY_TEXT = ("name", "country", "local_id", "tax_id", "fiscal_year", "industry_code", "established", "relationship",
              "representative", "industry", "address")


# 국제거래명세서 서식 판 — (그 날부터 시행, 판 번호 = 시행일 YYYYMMDD)
STATEMENT_EDITIONS = ((date(2023, 3, 20), 20230320), (date(2022, 3, 18), 20220318), (date(2021, 3, 16), 20210316),
                      (date(2018, 3, 19), 20180319), (date(2017, 3, 17), 20170317), (date(2016, 4, 6), 20160406))
# 정상가격 산출방법 신고서(무형자산·용역 외) 서식 판 — 구 별지 제1호의3서식 → 2021.3.16. 별지 제20호서식
TP_FORM_EDITIONS = ((date(2023, 3, 20), 20230320), (date(2021, 3, 16), 20210316), (date(2020, 3, 13), 20200313), (date(2015, 3, 13), 20150313))
OLD_FORM_MAX = 5          # 구 서식(국외특수관계인별 한 장) 틀을 만드는 최대 장수


def _edition(table, d):
    if d is None:
        return 0
    return next((code for start, code in table if d >= start), 0)


def _month_end_plus(d: date, months: int) -> date:
    y, m = d.year, d.month + months
    while m > 12:
        y, m = y + 1, m - 12
    return date(y, m, calendar.monthrange(y, m)[1])


def _amt(v, where, 문제):
    if v is None:
        return 0
    if isinstance(v, bool) or not isinstance(v, int) or v < 0:
        문제.append(f"{where} — 원 단위 0 이상 정수")
        return 0
    return v


def _side(raw, where, fy_days, 문제):
    raw = raw or {}
    if not isinstance(raw, dict):
        문제.append(f"{where} — 거래 금액 dict")
        return None
    unknown = set(raw) - SIDE_KEYS
    if unknown:
        문제.append(f"{where} — 모르는 키 {sorted(unknown)} (허용: {sorted(SIDE_KEYS)})")
    out = {k: _amt(raw.get(k), f"{where}.{k}", 문제) for k in AMOUNT_KEYS}
    loans = []
    for i, l in enumerate(raw.get("loans") or []):
        if not isinstance(l, dict) or set(l) - {"amount", "days"}:
            문제.append(f"{where}.loans[{i}] — {{amount, days}}")
            continue
        a = _amt(l.get("amount"), f"{where}.loans[{i}].amount", 문제)
        d = l.get("days")
        if isinstance(d, bool) or not isinstance(d, int) or d < 0 or d > fy_days:
            문제.append(f"{where}.loans[{i}].days — 0 이상 사업연도 일수({fy_days}) 이하 정수(해당 사업연도 중 대여·차입 기간)")
            continue
        loans.append((a, d))
    out["loans"] = loans
    out["적수"] = sum(a * d for a, d in loans)
    out["평균"] = out["적수"] // fy_days if fy_days else 0          # 원 미만 절사(서식 예시 115.07 → 115, 반올림과 같은 값 — 원 미만 처리 규정은 없음)
    out["계"] = sum(out[k] for k in AMOUNT_KEYS) + out["평균"]     # ⑨ = ⑩~㉑(⑰ 제외) — ⑱ 평균 대여금·⑲ 이자 포함
    out["재화"] = out["inventory"] + out["other_tangible"]
    out["무형"] = out["royalty"] + out["intangible_sale"]
    out["용역"] = out["guarantee"] + out["other_services"] + out["tangible_rental"]
    out["금전대차"] = out["적수"] > 0 or out["interest"] > 0
    out["기타"] = out["virtual_assets"] + out["other"]
    return out


def _form_row(p, s):
    """별지16(갑) 표 한 행(서식_표). 금액 칸은 입력 금액, ⑨·⑱은 서식 산식(수식), ⑰은 Σ금액×일수 값.
    (⑰을 '=100*60+…' 문자열로 넘기면 엑셀 내보내기가 도구 결과의 '=' 문자열을 문구로 바꿔 ⑱·⑨가 0으로 계산됨 — 값으로 넘긴다)"""
    row = {"법인명": p.get("name") or "", "소재국가": p.get("country") or "", "고유번호": p.get("local_id") or "",
           "납세자번호": p.get("tax_id") or "", "사업연도": p.get("fiscal_year") or "", "업종코드": p.get("industry_code") or "",
           "설립일": p.get("established") or "", "관계": p.get("relationship") or "",
           "계": "=SUM(J{r}:P{r})+SUM(R{r}:U{r})",
           "적수": s["적수"] or None,
           "평균": "=ROUNDDOWN(N(Q{r})/[입력.사업연도일수],0)"}
    for k in AMOUNT_KEYS:
        row[k] = s[k] or None
    return row


def statement(args: dict) -> dict:
    문제: list[str] = []
    year = args.get("year")
    if isinstance(year, bool) or not isinstance(year, int) or not 2016 <= year <= 2026:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["year — 사업연도(개시일이 속하는 해) 2016~2026"]}
    try:
        fy_start = date.fromisoformat(args.get("fy_start") or f"{year}-01-01")
        fy_end = date.fromisoformat(args.get("fy_end") or f"{year}-12-31")
    except (TypeError, ValueError):
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["fy_start·fy_end — YYYY-MM-DD"]}
    if fy_start.year != year or fy_end < fy_start or (fy_end - fy_start).days > 365:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["fy_start는 year 안, fy_end는 fy_start 뒤 1년 이내"]}
    fy_days = (fy_end - fy_start).days + 1
    parties = args.get("parties")
    if not isinstance(parties, list) or not parties:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["parties — 국외특수관계인별 거래 목록(하나 이상)"]}
    rows = []
    for i, p in enumerate(parties):
        if not isinstance(p, dict):
            문제.append(f"parties[{i}] — dict")
            continue
        unknown = set(p) - set(PARTY_TEXT) - {"sales", "purchases", "transfer_pricing"}
        if unknown:
            문제.append(f"parties[{i}] — 모르는 키 {sorted(unknown)}")
        if not p.get("name"):
            문제.append(f"parties[{i}].name — 국외특수관계인 법인명(상호)")
        rel = p.get("relationship")
        if rel is not None:
            rel = REL_ALIASES.get(rel, rel)
            if rel not in RELATIONS:
                문제.append(f"parties[{i}].relationship — {list(RELATIONS)} 중 하나(별지 제16호서식(갑) 작성방법 4)")
        tp = p.get("transfer_pricing")
        if tp is not None and (not isinstance(tp, dict) or set(tp) - {"transaction", "method", "reason"}):
            문제.append(f"parties[{i}].transfer_pricing — {{transaction, method, reason}}")
        sa = _side(p.get("sales"), f"parties[{i}].sales", fy_days, 문제)
        pu = _side(p.get("purchases"), f"parties[{i}].purchases", fy_days, 문제)
        rows.append((dict(p, relationship=rel), sa, pu))
    revenue = args.get("revenue") or 0
    if isinstance(revenue, bool) or not isinstance(revenue, int) or revenue < 0:
        문제.append("revenue — 원 단위 0 이상 정수")
    third = args.get("third_party")
    if third is not None and (not isinstance(third, dict) or set(third) - {"goods", "services", "intangibles"}):
        문제.append("third_party — {goods, services, intangibles}(국외특수관계 없는 자와의 국제거래 금액, 원)")
        third = None
    third = {k: _amt((third or {}).get(k), f"third_party.{k}", 문제) for k in ("goods", "services", "intangibles")}
    if 문제:
        return {"error": "입력 확인 필요 — 계산하지 않음", "문제": 문제}

    tot = lambda side, k: sum(r[side][k] for r in rows)          # noqa: E731
    rows = [{"p": p, 1: sa, 2: pu} for p, sa, pu in rows]
    by_type = {t: sum(r[1][t] + r[2][t] for r in rows) for t in ("재화", "용역", "무형")}
    party_max = {t: max(r[1][t] + r[2][t] for r in rows) for t in ("재화", "용역", "무형")}

    # 제출 의무 — corporate_filing_obligations와 같은 판정(영 제36조 연도표, 통합·개별기업보고서 제출자 관계)
    ob = C.corporate_filing_obligations({"year": year, "revenue": revenue, "fy_start": fy_start.isoformat(), "fy_end": fy_end.isoformat(),
                                         "related_goods": by_type["재화"], "related_services": by_type["용역"],
                                         "related_intangibles": by_type["무형"], "party_max_goods": party_max["재화"],
                                         "party_max_services": party_max["용역"], "party_max_intangibles": party_max["무형"],
                                         "third_party_goods": third["goods"], "third_party_services": third["services"],
                                         "third_party_intangibles": third["intangibles"]})
    obr = ob["결과"]
    keep = ("국제거래명세서", "요약손익계산서", "정상가격산출방법신고서", "정상가격산출방법신고서 가목 금액", "무형자산 거래", "통합·개별기업보고서 제출자", "국제거래정보통합보고서")
    판단 = [j for j in ob["판단"] if j["항목"] in keep]
    stmt, summ, tpdoc = obr["국제거래명세서"], obr["요약손익계산서"], obr["정상가격산출방법신고서"]
    anyobl = stmt or summ or tpdoc
    # 제출기한: 2021.1.1. 이후 개시 사업연도는 6개월(법 제16조②). 그 전 개시 사업연도는 종전 기한(법인세 신고기한 = 종료일이 속하는 달의 말일부터 3개월)이
    #   2021.1.1. 현재 지나지 않았으면 6개월(법률 제17651호 부칙 제5조①), 이미 지났으면 종전 기한(부칙 제23조①).
    종전기한 = _month_end_plus(fy_end, 3)
    six = fy_start >= date(2021, 1, 1) or 종전기한 >= date(2021, 1, 1)
    deadline = (_month_end_plus(fy_end, 6) if six else 종전기한) if anyobl else None
    if deadline:
        판단.append({"항목": "제출기한", "결론": f"{deadline.isoformat()} — " + ("사업연도 종료일이 속하는 달의 말일부터 6개월" if six
                                                                       else "법인세 신고기한(사업연도 종료일이 속하는 달의 말일부터 3개월)"),
                   "근거": "국제조세조정에 관한 법률 제16조②" if fy_start >= date(2021, 1, 1) else
                   (f"법률 제17651호 부칙 제5조①(종전 기한 {종전기한.isoformat()}이 2021.1.1. 현재 지나지 않아 6개월 — corporate_filing_obligations와 같음)" if six
                    else f"구 국제조세조정에 관한 법률 제11조①, 법률 제17651호 부칙 제23조①(종전 기한 {종전기한.isoformat()}이 2021.1.1. 전에 지남)")})

    # 함께 낼 서식(시행규칙 제27조, 별지 제16호서식(갑) 작성방법 7·8)
    has = lambda f: any(r[1][f] or r[2][f] for r in rows)           # noqa: E731
    with_forms = []
    if stmt and has("guarantee"):
        with_forms.append({"서식": "별지 제16호서식(을) 지급보증 용역거래 명세서", "사유": "⑭·㉟ 지급보증 용역거래 있음",
                           "근거": "국제조세조정에 관한 법률 시행규칙 제27조①(국제거래명세서와 함께 제출)"})
    if summ:
        with_forms.append({"서식": "별지 제17호서식 국외특수관계인의 요약손익계산서", "사유": "영 제36조제2호 면제 요건에 해당하지 않음(해외현지법인 명세서·재무상황표를 내면 면제 — 같은 호 나목)",
                           "근거": "국제조세조정에 관한 법률 제16조②2호, 시행규칙 제27조②"})
    tp_targets = []
    if tpdoc:
        if has("other_services") or has("tangible_rental"):
            with_forms.append({"서식": "별지 제18호서식 용역거래에 대한 정상가격 산출방법 신고서", "사유": "⑮·⑯·㊱·㊲ 기타 용역·유형자산 사용료 거래 있음",
                               "근거": "시행규칙 제27조③1호, 별지 제16호서식(갑) 작성방법 8"})
        if has("royalty") or has("intangible_sale"):
            with_forms.append({"서식": "별지 제19호서식 무형자산에 대한 정상가격 산출방법 신고서", "사유": "⑫·⑬·㉝·㉞ 무형자산 거래 있음",
                               "근거": "시행규칙 제27조③2호, 별지 제16호서식(갑) 작성방법 7"})
        for r in rows:
            s1, s2 = r[1], r[2]
            if s1["재화"] or s2["재화"] or s1["금전대차"] or s2["금전대차"] or s1["기타"] or s2["기타"]:
                tp_targets.append(r)
        if tp_targets:
            with_forms.append({"서식": "별지 제20호서식 정상가격 산출방법 신고서", "사유": "재화·금전대차·가상자산·기타 거래 — 국외특수관계인: "
                               + ", ".join(r["p"]["name"] for r in tp_targets) + "(국외특수관계인·거래대상별로 방법이 다르면 각각 작성)",
                               "근거": "시행규칙 제27조③3호, 별지 제20호서식 작성방법 4"})
    elif obr.get("통합보고서_제출자_제외") is not True and sum(by_type.values()) > 0:
        판단.append({"항목": "정상가격 산출방법 신고서(별지 제18호~제20호)", "결론": "제출 면제 — 영 제36조제3호(전체 또는 국외특수관계인별 금액 기준 이하). 가목(전체 50억·10억·10억)의 '국제거래'에는 국외특수관계 없는 자와의 국제거래도 들어감(사전-2022-법규국조-0527, 2022.5.27. 요지) — "
                           + ("third_party 금액을 더해 판정함" if any(third.values()) else
                              "third_party를 넣지 않아 국외특수관계인 거래만 더함. 제3자와의 수출입을 더해 가목을 넘으면 나목(국외특수관계인별 10억·2억·2억)에 해당할 때만 면제 — third_party에 그 금액을 넣으면 더해서 판정"),
                   "근거": "국제조세조정에 관한 법률 제16조②3호, 시행령 제36조제3호"})

    # 서식 판 — 제출기한 날 시행 중인 판(머리 주석). 2021.3.16. 전부개정 전이면 구 서식 번호로 바꿔 적는다
    판_명세서, 판_신고서 = _edition(STATEMENT_EDITIONS, deadline), _edition(TP_FORM_EDITIONS, deadline)
    구번호 = deadline is not None and deadline < date(2021, 3, 16)
    if 구번호:
        _old = (("별지 제16호서식(을)", "구 별지 제8호서식(을)"), ("별지 제16호서식(갑)", "구 별지 제8호서식(갑)"), ("별지 제17호서식", "구 별지 제8호의2서식"),
                ("별지 제18호서식", "구 별지 제1호의2서식"), ("별지 제19호서식", "구 별지 제1호서식"), ("별지 제20호서식", "구 별지 제1호의3서식"),
                ("국제조세조정에 관한 법률 시행규칙 제27조①", "구 국제조세조정에 관한 법률 시행규칙 제6조①"),
                ("국제조세조정에 관한 법률 제16조②2호, 시행규칙 제27조②", "구 국제조세조정에 관한 법률 제11조①, 구 시행규칙 제6조②"),
                ("시행규칙 제27조③1호", "구 시행규칙 제2조의4①2호(2020.3.13.부터 제2조의5)"), ("시행규칙 제27조③2호", "구 시행규칙 제2조의4①1호(2020.3.13.부터 제2조의5)"),
                ("시행규칙 제27조③3호", "구 시행규칙 제2조의4①3호(2020.3.13.부터 제2조의5)"),
                ("영 제36조제2호 면제 요건에 해당하지 않음(해외현지법인 명세서·재무상황표를 내면 면제 — 같은 호 나목)", "구 시행규칙 제6조② 단서(재화 10억·용역 2억 이하, 또는 해외현지법인 명세서·재무상황표 제출)에 해당하지 않음"),
                (", 별지 제16호서식(갑) 작성방법 8", ""), (", 별지 제16호서식(갑) 작성방법 7", ""), (", 별지 제20호서식 작성방법 4", ""),
                ("⑭·㉟ ", ""), ("⑮·⑯·㊱·㊲ ", ""), ("⑫·⑬·㉝·㉞ ", ""))
        for f in with_forms:
            for k in ("서식", "사유", "근거"):
                for a, b in _old:
                    f[k] = f[k].replace(a, b)

    # 별지 제20호서식 칸(첫 대상 국외특수관계인 — 산출방법 입력이 있는 쪽을 먼저)
    form20 = {}
    if tp_targets:
        t = next((r for r in tp_targets if r["p"].get("transfer_pricing")), tp_targets[0])
        p, tp = t["p"], t["p"].get("transfer_pricing") or {}
        parts = []
        for side, lab in ((1, "매출"), (2, "매입")):
            s = t[side]
            if s["inventory"]: parts.append(f"재고자산 {lab} {s['inventory']:,}원")
            if s["other_tangible"]: parts.append(f"기타 유형자산 {lab} {s['other_tangible']:,}원")
            if s["금전대차"]: parts.append(f"금전 {'대여' if side == 1 else '차입'}(평균 {s['평균']:,}원, 이자 {s['interest']:,}원)")
            if s["virtual_assets"]: parts.append(f"가상자산 {lab} {s['virtual_assets']:,}원")
            if s["other"]: parts.append(f"기타 {lab} {s['other']:,}원")
        form20 = {"국외_법인명": p.get("name") or "", "국외_소재국가": p.get("country") or "", "국외_대표자": p.get("representative") or "",
                  "국외_업종": p.get("industry") or "", "국외_소재지": p.get("address") or "",
                  "국외_관계표시": "  ".join(("[√] " if p.get("relationship") == x else "[ ] ") + x + (" 등" if x == "본점ㆍ지점" else "") for x in RELATIONS),
                  # 구 별지 제1호의3서식 ⑪은 피지배·지배 순(<개정 2015.3.13.>·<개정 2020. 3. 13.>)
                  "국외_관계표시_구": "  ".join(("[√] " if p.get("relationship") == x else "[ ] ") + x + (" 등" if x == "본점ㆍ지점" else "")
                                          for x in ("피지배", "지배", "자매", "실질 지배", "본점ㆍ지점")),
                  "대상거래": tp.get("transaction") or ", ".join(parts),
                  "산출방법": tp.get("method") or "", "선택이유": tp.get("reason") or ""}

    def _sum(side):
        return {"계": tot(side, "계"), "적수": tot(side, "적수"), "평균": tot(side, "평균"), "이자": tot(side, "interest")}
    s1, s2 = _sum(1), _sum(2)
    결과 = {
        "사업연도": f"{fy_start.isoformat()} ~ {fy_end.isoformat()}", "사업연도_일수": fy_days, "국외특수관계인_수": len(rows),
        "매출_계": s1["계"], "매출_대여금적수": s1["적수"], "매출_평균대여금": s1["평균"], "매출_수입이자": s1["이자"],
        "매입_계": s2["계"], "매입_차입금적수": s2["적수"], "매입_평균차입금": s2["평균"], "매입_지급이자": s2["이자"],
        "재화거래_합계": by_type["재화"], "용역거래_합계": by_type["용역"], "무형자산거래_합계": by_type["무형"],
        "국외특수관계인별_최대": party_max,
        "국제거래명세서_제출": stmt, "요약손익계산서_제출": summ, "정상가격산출방법신고서_제출": tpdoc,
        "제출기한": deadline.isoformat() if deadline else None,
        "함께_낼_서식": with_forms, "별지20_작성": bool(form20),
    }
    if obr.get("통합보고서_제출자_제외"):
        결과["통합보고서_제출자_제외"] = True

    def _calc_row(r, side):
        s, idx = r[side], (0 if side == 1 else 1)
        d = {"국외특수관계인": r["p"]["name"]}
        d[("⑨ 계" if side == 1 else "㉚ 계")] = s["계"]
        for f in FIELDS:
            d[f"{f[idx]} {f[3]}"] = s[f[2]]
        d["⑰ 대여금 적수" if side == 1 else "㊳ 차입금 적수"] = s["적수"]
        d["⑱ 평균 대여금" if side == 1 else "㊴ 평균 차입금"] = s["평균"]
        return d
    계산 = {"매출거래": [_calc_row(r, 1) for r in rows if r[1]["계"] or r[1]["적수"]],
           "매입거래": [_calc_row(r, 2) for r in rows if r[2]["계"] or r[2]["적수"]],
           "산식": ["⑨ = ⑩+⑪+⑫+⑬+⑭+⑮+⑯+⑱+⑲+⑳+㉑ (⑰ 제외 — 작성방법 5), ㉚도 같은 방식(㊳ 제외)",
                  "⑰·㊳ = Σ(금액 × 해당 사업연도 중 대여·차입 일수) (작성방법 9)",
                  f"⑱·㊴ = ⑰·㊳ ÷ 사업연도 일수 {fy_days}일, 원 미만 절사 (작성방법 10)",
                  "면제 판정 금액: 재화 = ⑩+⑪+㉛+㉜, 용역 = ⑭+⑮+⑯+㉟+㊱+㊲, 무형자산 = ⑫+⑬+㉝+㉞ (매출·매입 합계)"]}
    서식_표 = {"16갑_매출": [_form_row(r["p"], r[1]) for r in rows if r[1]["계"] or r[1]["적수"]],
              "16갑_매입": [_form_row(r["p"], r[2]) for r in rows if r[2]["계"] or r[2]["적수"]]}
    # 구 서식(2022.3.17.까지 제출분 — 국외특수관계인별 한 장): 가. 재화(재고·유형·무형자산 매매), 나. 용역(일반용역·지급보증·사용료), 다. 대여 및 차입, 라. 그 밖의 거래
    #   사용료 칸은 유형·무형자산 사용료(2017판 작성방법 11), 무형자산 칸은 매매·원가분담금액(작성방법 9)
    구서식, 구장 = {}, ([r for r in rows if r[1]["계"] or r[1]["적수"] or r[2]["계"] or r[2]["적수"]] if year <= 2020 else [])
    for i, r in enumerate(구장, 1):
        pp, s1, s2 = r["p"], r[1], r[2]
        재화 = s1["inventory"] + s1["other_tangible"] + s1["intangible_sale"] + s2["inventory"] + s2["other_tangible"] + s2["intangible_sale"]
        용역 = sum(x[k] for x in (s1, s2) for k in ("other_services", "guarantee", "royalty", "tangible_rental"))
        대차 = s2["평균"] + s2["interest"] + s1["평균"] + s1["interest"]
        기타 = s1["other"] + s2["other"]
        구서식[f"p{i}"] = {"국외특수관계인": pp["name"], "재화소계": 재화, "용역소계": 용역, "대차소계": 대차, "기타소계": 기타, "합계": 재화 + 용역 + 대차}
        if i <= OLD_FORM_MAX:
            row = {"법인명": pp.get("name") or "", "소재국가": pp.get("country") or "", "고유번호": pp.get("local_id") or "", "납세자번호": pp.get("tax_id") or "",
                   "사업연도": pp.get("fiscal_year") or "", "업종코드": f"({pp.get('industry_code') or '      '})", "설립일": pp.get("established") or "",
                   "관계": pp.get("relationship") or "", "소재지": pp.get("address") or "",
                   "차입_적수": s2["적수"] or None, "차입_평균": "=ROUNDDOWN(N(F{p})/[입력.사업연도일수],0)" if s2["loans"] else None,
                   "대여_적수": s1["적수"] or None, "대여_평균": "=ROUNDDOWN(N(F{p})/[입력.사업연도일수],0)" if s1["loans"] else None,
                   "지급이자": s2["interest"] or None, "수입이자": s1["interest"] or None, "기타_매출": s1["other"] or None, "기타_매입": s2["other"] or None}
            for lab, x in (("매출", s1), ("매입", s2)):
                row.update({f"{lab}_재고": x["inventory"] or None, f"{lab}_유형": x["other_tangible"] or None, f"{lab}_무형": x["intangible_sale"] or None,
                            f"{lab}_일반용역": x["other_services"] or None, f"{lab}_지급보증": x["guarantee"] or None,
                            f"{lab}_사용료": (x["royalty"] + x["tangible_rental"]) or None})
            서식_표[f"구명세서_{i}"] = [row]
    판_이름 = {20160406: "구 시행규칙 별지 제8호서식(갑) <개정 2016.4.6.>", 20170317: "구 시행규칙 별지 제8호서식(갑) <개정 2017. 3. 17.>",
            20180319: "구 시행규칙 별지 제8호서식(갑) <개정 2018. 3. 19.>", 20210316: "시행규칙 별지 제16호서식(갑)(2021.3.16. 전부개정본)",
            20220318: "시행규칙 별지 제16호서식(갑) <개정 2022. 3. 18.>"}.get(판_명세서)
    if year <= 2020:
        결과["구서식"] = {**구서식, "장수": len(구장), "거래금액_총계": sum(v["합계"] for v in 구서식.values()), "서식": 판_이름}
    계산식_입력 = [{"이름": "사업연도", "값": year, "설명": "사업연도(개시일이 속하는 해)"},
               {"이름": "사업연도일수", "값": fy_days, "설명": "⑱·㊴ 분모 — 해당 사업연도의 일수[365(366)일]"},
               {"이름": "명세서_서식판", "값": 판_명세서, "설명": "국제거래명세서 서식 판(제출기한 날 시행 중인 시행규칙 서식의 시행일 YYYYMMDD, 제출 의무가 없으면 0)"},
               {"이름": "신고서_서식판", "값": 판_신고서, "설명": "정상가격 산출방법 신고서 서식 판(같은 방식)"},
               {"이름": "구서식_장수", "값": len(구장), "설명": "거래가 있는 국외특수관계인 수(구 서식은 국외특수관계인별 한 장)"},
               {"이름": "구서식_가상자산", "값": sum(r[1]["virtual_assets"] + r[2]["virtual_assets"] for r in rows), "설명": "가상자산 거래 금액 합계(2022년까지 서식에는 칸 없음)"},
               ]
    filer = args.get("filer") or {}
    if form20:
        for k, v in form20.items():
            계산식_입력.append({"이름": k, "값": v, "설명": "별지 제20호서식 칸(서식 칸용)"})
        for k, nm in (("representative", "신고인_대표자"), ("industry", "신고인_업종"), ("phone", "신고인_전화"), ("address", "신고인_소재지")):
            계산식_입력.append({"이름": nm, "값": filer.get(k) or "", "설명": "별지 제20호서식 신고인 칸(서식 칸용)"})
    elif year <= 2020:        # 구 국제거래명세서 1. 제출인 인적사항 ③~⑤ 칸
        for k, nm in (("representative", "신고인_대표자"), ("industry", "신고인_업종"), ("address", "신고인_소재지")):
            계산식_입력.append({"이름": nm, "값": filer.get(k) or "", "설명": "국제거래명세서 제출인 칸(서식 칸용)"})

    주의 = []
    if year == 2019 and not args.get("fy_start") and not args.get("fy_end"):
        주의.append("사업연도를 역년으로 보고 제출기한을 정함 — 2019 개시 사업연도가 2020.10.1. 이후 끝나면(종전 기한이 2021.1.1. 이후) 6개월 기한이라 fy_start·fy_end를 넣는다(법률 제17651호 부칙 제5조①)")
    if year <= 2020:
        if 판_이름:
            주의.append(f"2016~2020 사업연도 서식: 제출기한 {deadline.isoformat()}에 시행 중인 판은 {판_이름} — 국외특수관계인별로 한 장('국제거래 현황' 가. 재화거래, 나. 용역거래, 다. 대여 및 차입거래, 라. 그 밖의 거래). "
                      + ("이 판의 엑셀 틀은 만들지 않음(무형자산거래를 따로 떼어 칸 번호가 다름)" if 판_명세서 >= 20220318 else
                         f"엑셀 서식 틀은 그 판의 칸 번호로 국외특수관계인 {OLD_FORM_MAX}명까지 한 장씩 만들고 값은 결과의 '구서식'과 대조. 기한 전에 냈다면 그때 시행 중이던 판")
                      + ". 결과의 매출_계·매입_계와 '계산'의 칸 번호는 현행 별지 제16호서식(갑) 기준이라 구 서식 합계(재화 + 용역 + 대여·차입, 그 밖의 거래 제외)와 다름")
        if 구번호:
            주의.append("함께 내는 서식 번호(2021.3.16. 전부개정 전): 지급보증 구 별지 제8호서식(을), 요약손익계산서 제8호의2서식, 정상가격 산출방법 신고서 제1호(무형자산)·제1호의2(용역)·제1호의3서식(구 시행규칙 제2조의4①·제6조)")
        if len(구장) > OLD_FORM_MAX:
            주의.append(f"거래가 있는 국외특수관계인이 {len(구장)}명 — 구 서식 엑셀 틀은 앞의 {OLD_FORM_MAX}명만 만듦(나머지는 결과의 '구서식' 값을 같은 서식에 옮겨 적음)")
        if any(r[1]["virtual_assets"] or r[2]["virtual_assets"] for r in rows):
            주의.append("가상자산 거래 금액이 있음 — 2022년까지의 서식에는 가상자산 칸이 없어 구 서식 엑셀 틀을 만들지 않음")
    elif year <= 2022:
        주의.append("2021·2022 사업연도: 시행규칙 부칙(2023.3.20.) 서식에 관한 적용례 ②에 따라 별지 제16호서식(갑)·제17호~제20호서식 개정규정은 2023.1.1. 이후 개시 과세연도분부터 — "
                  "이 사업연도분은 국외특수관계인별로 한 장씩 쓰는 종전 서식(2021.3.16.·2022.3.18. 시행규칙 별지 제16호서식(갑) — 구 제8호서식(갑)과 같은 구성, 가상자산 칸 없음). "
                  "2023.3.20. 이후에 제출하면 같은 부칙 ③의 별지 제16호서식(갑-2)(2024.3.22. 삭제). 칸 번호와 엑셀 틀은 현행 서식 기준이라 금액을 옮겨 적는 용도")
    if len(rows) > 5:
        주의.append("국외특수관계인이 5명을 넘으면 서식을 추가로 작성(별지 제16호서식(갑) 작성방법 머리) — 엑셀 서식 틀은 한 장에 5행이라 나눠서 호출")
    if len(tp_targets) > 1:
        주의.append(f"별지 제20호서식은 국외특수관계인·거래대상별로 따로 작성 — 엑셀 서식 틀은 '{form20['국외_법인명']}' 한 장만 채움")
    한계 = ["⑱·㊴ 원 미만 처리: 규정 없음(서식 예시 42,000원 ÷ 365일 = 115원은 절사·반올림 같은 값) — 절사로 계산",
          "면제 금액 기준의 '재화·용역·무형자산거래'에 금전대차(⑰~⑲)·가상자산·기타(⑳·㉑)를 넣는지: 영 제36조는 재화거래·용역거래·무형자산거래 금액만 들고 있어 넣지 않음 — 이를 다룬 해석은 근거 없음(국세법령정보시스템 '국제거래명세서 제출 면제' 검색, 2026-11-15), 서면질의 필요. 넣어서 기준을 넘는 경우에는 제출하는 쪽이 안전",
          "지급보증만 있는 용역거래의 별지 제18호서식 작성 여부: 서식 작성방법 8은 기타 용역·유형자산 사용료만 들고, 시행규칙 제27조③1호는 '용역거래' 전체 — 작성방법을 따름. 둘 중 어느 쪽인지 다룬 해석은 근거 없음(국세법령정보시스템 검색, 2026-11-15), 서면질의 필요 — 시행규칙 문언대로면 지급보증만 있어도 별지 제18호서식 작성",
          "별지 제16호서식(갑) 가상자산 칸(⑳·㊶, 4. 가상자산 거래)은 2023.3.20. 개정(기획재정부령 제983호)에서 생김 — 부칙 제2조②: 2023.1.1. 이후 개시하는 과세연도 자료부터(2021.3.16.·2022.3.18. 본에는 없음, 시행규칙 대조)",
          "3. 주식 등 취득·양도, 4. 가상자산 거래 명세(제2쪽)와 ②~⑦ 인적사항 중 입력하지 않은 칸은 채우지 않음"]
    if year >= 2021:
        근거 = "국제조세조정에 관한 법률 제16조②, 시행령 제36조, 시행규칙 제27조·별지 제16호서식(갑)(작성방법 5·9·10)"
    else:
        근거 = "구 국제조세조정에 관한 법률 제11조①, 구 시행령 제7조①·제21조의2(2020년은 제21조의3), 구 시행규칙 제6조·별지 제8호서식(갑) — 적수·평균 산식은 구 서식 작성방법(금액 × 일수의 합계, ÷365(366)일)과 현행 별지 제16호서식(갑) 작성방법이 같음"
    return {"결과": 결과, "근거": 근거, "계산": 계산, "판단": 판단, "서식_표": 서식_표, "계산식_입력": 계산식_입력, "주의": 주의, "한계": 한계}
