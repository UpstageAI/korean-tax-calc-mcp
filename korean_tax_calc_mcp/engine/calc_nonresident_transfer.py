"""비거주자·외국법인 국내 부동산·주식 등 양도소득 원천징수, 비거주자 상속세·증여세 (2016~2026).

대조한 원문(법제처 DRF 연말 시행본, 2026-11-14 조회 — 원자료 raw_foreign_b):
- 소득세법 제119조·제121조·제126조·제156조·제156조의2: 2016.9.1.(법률 제13796호)·2017.7.1.·2018.9.21.·2019.1.1.(법률 제16104호)·
  2020.8.28.·2021.12.8.·2022.7.1.·2023.7.1.·2024.7.1.·2025.10.1.·2026.7.1.(법률 제21221호) 시행본
- 소득세법 시행령 제179조제11항(2016.12.5.·2026.10.1. 시행본), 법인세법 시행령 제132조제8항(2016.11.29.·2026.10.1. 시행본)
- 법인세법 제91조·제92조·제93조·제97조·제98조·제98조의4: 2016.1.25.·2018.11.1.·2019.1.1.(법률 제16096호)·2021.12.30.·2023.7.1.·2025.10.1.·2026.7.1. 시행본
- 상속세 및 증여세법 제3조·제4조의2·제13조·제14조·제18조~제23조의2·제53조·제53조의2·제67조·제68조: 2016.9.1.~2026.1.2. 연말 시행본 11개
- 지방세법 제103조의13·제103조의52: 2026.7.1. 시행본만
"""
from __future__ import annotations

from datetime import date
from fractions import Fraction
import math

from . import calc_inhgift as IG
from . import calc_deadline as DL

M = 1_000_000
_LISTED_THRESHOLD = Fraction(25, 100)   # 소득령 제179조⑪1호 단서·법인령 제132조⑧2호 단서 — 100분의 25 미만(2016·2026 시행본 같음)


def _err(*msgs):
    return {"error": "입력 확인 필요 — 계산하지 않음", "문제": list(msgs)}


def _ho(seller_type: str, asset_kind: str, year: int):
    """원천징수 근거 조·호와 국내원천소득 근거. 2018.12.31./2018.12.24. 개정(2019.1.1. 시행)으로 호 번호가 바뀜(세율·산식 문언은 같음)."""
    부동산 = asset_kind == "부동산등"
    if seller_type == "개인":
        ho = (4 if 부동산 else 5) if year <= 2018 else (5 if 부동산 else 7)
        return (f"소득세법 제156조제1항제{ho}호", "소득세법 제119조제9호" if 부동산 else "소득세법 제119조제11호",
                "소득세법 제156조의2")
    ho = (4 if 부동산 else 5) if year <= 2018 else (5 if 부동산 else 7)
    return (f"법인세법 제98조제1항제{ho}호", "법인세법 제93조제7호" if 부동산 else "법인세법 제93조제9호", "법인세법 제98조의4")


def capital_gains_withholding(seller_type, asset_kind, year, gross_price, acquisition_cost=None, transfer_expenses=0,
                              normal_price=None, payer_is_individual=False, attributable_to_pe=False, has_domestic_pe=False,
                              listed_via_exchange=False, max_ownership_ratio=None, treaty_exempt=False, residence_country=None):
    if seller_type not in ("개인", "법인"):
        return _err(f"seller_type={seller_type!r} — 개인(비거주자) 또는 법인(외국법인)")
    if asset_kind not in ("부동산등", "주식", "기타유가증권"):
        return _err(f"asset_kind={asset_kind!r} — 부동산등·주식·기타유가증권")
    if not isinstance(year, int) or isinstance(year, bool) or not 2016 <= year <= 2026:
        return _err(f"year={year!r} — 지급 연도 2016~2026")
    for n, v in (("gross_price", gross_price), ("transfer_expenses", transfer_expenses)):
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            return _err(f"{n}={v!r} — 0 이상 정수(원)")
    if acquisition_cost is not None and (isinstance(acquisition_cost, bool) or not isinstance(acquisition_cost, int) or acquisition_cost < 0):
        return _err(f"acquisition_cost={acquisition_cost!r} — 0 이상 정수(원), 확인되지 않으면 비움")
    if transfer_expenses and acquisition_cost is None:
        return _err("transfer_expenses는 취득가액이 확인될 때(acquisition_cost)만 — 단서는 '취득가액 및 양도비용이 확인되는 경우'")
    if normal_price is not None:
        if asset_kind == "부동산등":
            return _err("normal_price(정상가격)는 유가증권 양도소득에만 — 소득세법 제126조제6항·법인세법 제92조제2항제2호")
        if has_domestic_pe:
            return _err("normal_price(정상가격)는 국내사업장이 없는 비거주자·외국법인의 특수관계인 간 저가 거래만 — has_domestic_pe=true와 함께 쓸 수 없음")
        if isinstance(normal_price, bool) or not isinstance(normal_price, int) or normal_price <= gross_price:
            return _err(f"normal_price={normal_price!r} — 거래가격(gross_price {gross_price:,}원)보다 높은 정상가격일 때만 넣음(요건: 거래가격이 정상가격에 미달)")
    if payer_is_individual and asset_kind != "부동산등":
        return _err("payer_is_individual(지급자가 개인)은 부동산등양도소득에만 의미 — 유가증권 양도소득은 개인 지급자도 원천징수의무가 있음(제156조제1항 괄호·제98조제1항 괄호는 부동산등양도소득만 제외)")
    ratio = None
    if listed_via_exchange:
        if asset_kind != "주식":
            return _err("listed_via_exchange는 주식(상장주식을 증권시장을 통해 양도)에만")
        if max_ownership_ratio is None:
            return _err("listed_via_exchange=true면 max_ownership_ratio(양도자+특수관계인의 양도일이 속하는 연도와 직전 5년 중 최대 지분율, 소수) 필요")
    if max_ownership_ratio is not None:
        ratio = Fraction(str(max_ownership_ratio))
        if not 0 <= ratio <= 1:
            return _err(f"max_ownership_ratio={max_ownership_ratio!r} — 0~1 소수(예: 0.1 = 10%)")

    wh_art, src_art, treaty_art = _ho(seller_type, asset_kind, year)
    국세 = "소득세" if seller_type == "개인" else "법인세"
    판단, 한계, 신고안내 = [], [], []
    근거 = [wh_art, src_art]

    def zero(reason, basis):
        판단.append({"항목": "원천징수 대상", "결론": reason, "근거": basis})
        return True

    stop = None
    if attributable_to_pe:
        stop = zero("국내사업장에 실질적으로 관련되거나 귀속되는 소득 — 제156조제1항·제98조제1항 원천징수 대상 아님(국내사업장 소득과 합산해 신고)",
                    "소득세법 제156조제1항·제121조제2항" if seller_type == "개인" else "법인세법 제98조제1항·제91조제1항")
    elif asset_kind == "부동산등" and payer_is_individual:
        stop = zero("지급자가 개인(거주자·비거주자) — 부동산등양도소득은 개인 지급자가 원천징수하지 않음(양도자가 직접 신고·납부)",
                    ("소득세법 제156조제1항 괄호" if seller_type == "개인" else "법인세법 제98조제1항 괄호") + "(2016~2026 시행본 같음)")
    elif listed_via_exchange and ratio < _LISTED_THRESHOLD and (seller_type == "개인" or not has_domestic_pe):
        stop = zero(f"증권시장을 통한 상장주식 양도로 양도자·특수관계인 지분이 양도일이 속하는 연도와 직전 5년 동안 계속 25% 미만(입력 최대 {float(ratio)*100:g}%) — 국내원천소득 아님",
                    "소득세법 시행령 제179조제11항제1호 단서" if seller_type == "개인" else "법인세법 시행령 제132조제8항제2호 단서(국내사업장이 없는 외국법인만)")
    elif treaty_exempt:
        stop = zero(f"조세조약상 비과세·면제(입력 — 거주지국 {residence_country or '미입력'}) — 실질귀속자가 비과세·면제신청서(와 실질귀속자 증명서류)를 지급자에게 내야 하고, "
                    "내지 않거나 실질귀속자를 알 수 없으면 지급자는 원천징수해야 함", f"{treaty_art}제1항·제3항")
    if listed_via_exchange and ratio < _LISTED_THRESHOLD and seller_type == "법인" and has_domestic_pe and not attributable_to_pe:
        판단.append({"항목": "상장주식 소액주주", "결론": "국내사업장이 있는 외국법인의 주식 양도소득은 지분율과 관계없이 국내원천소득(25% 미만 제외는 국내사업장이 없는 외국법인만)",
                   "근거": "법인세법 시행령 제132조제8항제1호·제2호"})

    결과 = {"원천징수세액": 0, "지방소득세": 0, "합계": 0}
    계산 = {}
    if stop is None:
        base = normal_price if normal_price is not None else gross_price
        a = Fraction(base, 10)
        계산["지급금액"] = base
        계산["지급금액x10%"] = math.floor(a)
        적용 = "지급금액 × 10%"
        tax_f = a
        if acquisition_cost is not None:
            gain = base - acquisition_cost - transfer_expenses
            gain_pos = max(0, gain)
            b = Fraction(gain_pos, 5)
            계산.update({"취득가액": acquisition_cost, "양도비용": transfer_expenses, "양도차익": gain, "양도차익x20%": math.floor(b)})
            if b < a:
                tax_f, 적용 = b, "양도차익 × 20%"
            if gain < 0:
                판단.append({"항목": "양도차손", "결론": f"양도차익 {gain:,}원(손실) — 20% 쪽이 0원이라 원천징수세액 0", "근거": wh_art + " 단서"})
        tax = math.floor(tax_f)
        local = math.floor(Fraction(tax, 10))
        결과 = {"원천징수세액": tax, "지방소득세": local, "합계": tax + local, "적용": 적용}
        판단.append({"항목": "원천징수세액", "결론": (f"min(지급금액 × 10% = {계산['지급금액x10%']:,}, 양도차익 × 20% = {계산['양도차익x20%']:,}) = {tax:,}원"
                                                  if acquisition_cost is not None else f"취득가액·양도비용 미확인 — 지급금액 {base:,} × 10% = {tax:,}원"),
                   "근거": wh_art + (" 본문·단서" if acquisition_cost is not None else " 본문")})
        if normal_price is not None:
            판단.append({"항목": "정상가격", "결론": f"특수관계인 간 저가 거래 — 정상가격 {normal_price:,}원을 지급금액(수입금액)으로 봄(입력 기준, 요건 판단은 하지 않음)",
                       "근거": "소득세법 제126조제6항" if seller_type == "개인" else "법인세법 제92조제2항제2호"})
        if seller_type == "개인":
            판단.append({"항목": "지방소득세", "결론": f"원천징수 소득세의 10% = {local:,}원(개인지방소득세 특별징수)",
                       "근거": "지방세법 제103조의13제1항은 '거주자로부터' 원천징수하는 경우로 규정 — 비거주자 특별징수 근거 조문은 확인 필요"})
            한계.append("비거주자 개인지방소득세 특별징수 근거 조문 확인 필요(지방세법 제103조의13제1항 문언은 거주자) — 10%로 계산")
        else:
            판단.append({"항목": "지방소득세", "결론": f"원천징수 법인세의 10% = {local:,}원(법인지방소득세 특별징수)",
                       "근거": "지방세법 제103조의52제1항(2026.7.1. 시행본 대조, 그 전 연도 문언은 확인 필요)"})
        근거.append("지방세법 제103조의52제1항" if seller_type == "법인" else "지방세법 제103조의13제1항(거주자 문언 — 확인 필요)")

    # 신고 안내(계산하지 않음)
    if seller_type == "개인":
        if asset_kind == "부동산등":
            신고안내.append({"내용": "국내원천 부동산등양도소득은 거주자와 같은 방법으로 분류과세 — 원천징수와 별개로 양도소득 과세표준 신고가 필요한지 거주자 신고 규정으로 확인(원천징수세액의 기납부 공제 포함). "
                                     "대통령령으로 정하는 비거주자에게는 1세대1주택 비과세(제89조제1항제3호)·장기보유특별공제 표 외 부분 단서를 적용하지 않음",
                         "근거": "소득세법 제121조제2항(2026 시행본은 제89조제1항제3호·제4호, 2016 시행본은 제3호만)"})
        else:
            신고안내.append({"내용": "국내사업장이 없는 비거주자는 소득별 분리과세(제121조제3항), 국내사업장이 있어도 귀속되지 않는 원천징수 소득은 분리과세(제121조제4항) — 원천징수로 과세가 끝나는 구조. "
                                     "국내사업장에 귀속되면 종합과세(제121조제2항)",
                         "근거": "소득세법 제121조제2항~제4항, 제126조제1항·제2항"})
    else:
        if asset_kind == "부동산등":
            신고안내.append({"내용": "국내원천 부동산등양도소득이 있는 외국법인은 각 사업연도 소득에 대한 법인세 신고 규정을 준용해 신고 — "
                                     "2021.12.30. 이후 시행본은 제98조제1항제5호로 원천징수된 세액을 기납부세액으로 공제한다고 명시(그 전 시행본은 제98조제8항만 — 확인 필요)",
                         "근거": "법인세법 제97조제1항, 제92조제3항(양도가액 − 취득가액 − 직접 지출 비용)"})
        else:
            신고안내.append({"내용": "국내사업장이 없는 외국법인은 국내원천소득별 과세표준(제91조제2항), 국내사업장이 있어도 원천징수되는 소득은 소득별 과세표준(제91조제3항) — 원천징수로 과세가 끝나는 구조",
                         "근거": "법인세법 제91조제2항·제3항, 제92조제2항"})
    신고안내.append({"내용": "조세조약상 양도소득 면제·과세 여부는 거주지국 조약의 양도소득 조항으로 확인 — korean-tax-mcp(조문 MCP)의 tax_treaty·treaty_withholding_rates 도구",
                 "근거": treaty_art})

    if year <= 2018:
        한계.append(f"{year}년 지급분: 원천징수 호는 2019.1.1. 시행 개정 전 번호({wh_art}) — 세율·산식 문언은 2019년 이후와 같음")
    한계 += [
        "양도차익은 지급금액 − 취득가액 − 양도비용으로 계산(입력 기준). 확인되는 취득가액·양도비용의 범위(소득세법 시행령·법인세법 시행령 위임)는 판단하지 않음 — 확인 필요",
        "원 미만: 조문에 끝수 규정이 없어 최종 세액(원천징수세액·지방소득세)만 원 미만 버림. 납부 때 국고금 끝수 처리는 별도",
        "국내원천소득 해당 여부(부동산주식등 50% 판정, 기타유가증권의 양수자 요건 등)는 입력(asset_kind)으로 받음 — 판단하지 않음",
        "조세조약 면제(treaty_exempt)는 입력값 — 조약 요건은 판단하지 않음",
    ]
    return {"결과": 결과, "계산": 계산, "판단": 판단, "신고안내": 신고안내, "근거": 근거, "한계": 한계,
            "입력": {"seller_type": seller_type, "asset_kind": asset_kind, "year": year}}


def _deadline(d: date, months: int):
    last = DL.month_end_plus(d, months)
    try:
        r = DL.roll(last)
        return last, r["날짜"], r.get("건너뜀", [])
    except Exception:   # 공휴일표 밖이면 말일 그대로
        return last, last, []


def inheritance_gift(kind, event_date, value, **kw):
    try:
        d = date.fromisoformat(str(event_date)[:10])
    except ValueError:
        return _err(f"event_date={event_date!r} — 상속개시일·증여일 YYYY-MM-DD")
    if not 2016 <= d.year <= 2026:
        return _err(f"event_date={event_date} — 2016~2026 상속개시·증여분만")
    if kind == "상속":
        foreign = kw.pop("foreign_address", True)
        r = IG.inheritance_tax(year=d.year, estate_value=value, resident=False, **kw)
        if "error" in r:
            return r
        months = 9 if foreign else 6
        last, due, skipped = _deadline(d, months)
        r["판단"]["신고기한"] = {"결론": f"상속개시일이 속하는 달의 말일부터 {months}개월 — {last.isoformat()}"
                                    + (f"(공휴일·토요일·일요일이라 {due.isoformat()})" if due != last else "")
                                    + (" — 피상속인이나 상속인이 외국에 주소를 둔 경우 9개월" if foreign else " — 피상속인·상속인 모두 국내 주소면 6개월"),
                              "근거": "상속세 및 증여세법 제67조제1항·제4항(2016~2026 같음), 국세기본법 제5조(기한이 공휴일 등이면 다음 날)"}
        r["결과"]["신고기한"] = due.isoformat()
        r["한계"] = ["상속재산·사전증여·공과금·채무는 국내 소재분·제14조제2항 해당분만 입력(제3조제2호·제13조제2항) — 국내 소재 판정(제5조)은 하지 않음",
                    "추정상속재산(제15조)·재해손실공제·세대생략 할증 계산은 이 도구에서 받지 않음 — 할증은 generation_skip_surcharge 입력값",
                    "원 미만: 산출세액 등 기존 상속세 계산과 같은 처리(세율 곱의 원 미만 버림)",
                    "'외국에 주소'(제67조제4항)와 비거주자 판정은 별개 — foreign_address 입력값"]
        return r
    if kind == "증여":
        r = IG.gift_tax(gift_date=d.isoformat(), gift_value=value, recipient_resident=False, **kw)
        if "error" in r:
            return r
        last, due, skipped = _deadline(d, 3)
        판단 = r["판단"]
        판단["비거주자_수증자"] = {"결론": "비거주자 수증자 — 증여재산공제(제53조)·혼인·출산 증여재산공제(제53조의2) 없음: 두 조문 모두 '거주자가' 증여받는 경우(2016~2026 같음)",
                              "근거": "상속세 및 증여세법 제53조·제53조의2"}
        if d.year == 2016:
            판단["과세대상"] = {"결론": "2016년 증여: 국내에 있는 모든 증여재산 + 거주자로부터 받은 국외 예금·적금 등 대통령령으로 정하는 재산(2017.1.1. 이후 증여분부터 국내재산만 — 법률 제14388호 부칙 제2조)",
                             "근거": "구 상속세 및 증여세법 제4조의2제1항제2호(2016.9.1. 시행본)"}
            연대 = "제4조의2제5항제3호"
        else:
            판단["과세대상"] = {"결론": "국내에 있는 모든 증여재산", "근거": "상속세 및 증여세법 제4조의2제1항제2호"}
            연대 = "제4조의2제5항제3호" if d.year <= 2018 else "제4조의2제6항제3호"
        판단["연대납부"] = {"결론": "수증자가 비거주자면 증여자가 증여세를 연대하여 납부할 의무 — 같은 항 단서에 열거된 증여 예시·의제 조문(제4조제1항제2호·제3호, 제35조~제42조의3 일부, 제45조의3~제45조의5 등)에 해당하면 제외",
                         "근거": f"상속세 및 증여세법 {연대}(2019.1.1. 시행 법률 제16102호로 제5항 → 제6항)"}
        판단["신고기한"] = {"결론": f"증여받은 날이 속하는 달의 말일부터 3개월 — {last.isoformat()}" + (f"(공휴일·토요일·일요일이라 {due.isoformat()})" if due != last else "")
                                + ". 비거주자 연장 규정 없음(제68조에 제67조제4항 같은 조항 없음)",
                         "근거": "상속세 및 증여세법 제68조제1항, 국세기본법 제5조"}
        r["결과"]["신고기한"] = due.isoformat()
        r["근거"] = [["상속세 및 증여세법", "제4조의2", "①2호", "비거주자 수증자 과세대상"],
                   ["상속세 및 증여세법", "제4조의2", "⑥3호" if d.year >= 2019 else "⑤3호", "증여자 연대납부"]] + \
                  [x for x in r["근거"] if x[1] not in ("제53조", "제53조의2")] + [["상속세 및 증여세법", "제68조", "①", "신고기한"]]
        r["한계"] = ["국외 재산을 거주자가 비거주자에게 증여한 경우의 증여자 과세(국제조세조정에 관한 법률 특례)는 계산하지 않음 — 조문 번호·요건 확인 필요",
                    "국내 소재 판정(제5조)은 하지 않음 — gift_value는 과세대상 재산만",
                    "원 미만: 기존 증여세 계산과 같은 처리(세율 곱의 원 미만 버림)"]
        return r
    return _err(f"kind={kind!r} — 상속 또는 증여")
