"""부동산 공시가격 조회 — 주소 → 필지번호(PNU) → 개별공시지가(토지)·공동주택가격(아파트)·개별주택가격(단독).
출처: 국토교통부 국가공간정보(브이월드 NED API, 인증키 VWORLD_KEY). 외부로 나가는 정보는 주소·PNU·연도뿐.
상증법 평가(법 제61조①: 토지 개별공시지가, 주택 개별·공동주택가격)와 양도세 기준시가(소득세법 제99조①1호)에 쓴다.
응답 필드명은 브이월드 안내 기준(개별공시지가 pblntfPclnd 원/㎡, 공동주택 pblntfPc 원, 개별주택 housePc 원) — 처음 라이브 호출 때 확인. 작성 Claude 2026-10-30."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable

VWORLD = "https://api.vworld.kr"
Fetcher = Callable[[str, dict], dict]   # (path, params) -> json


def _key() -> str | None:
    k = os.environ.get("VWORLD_KEY")
    if k:
        return k
    for p in (os.path.join(os.getcwd(), ".env"), os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")):
        try:
            for ln in open(p, encoding="utf-8"):
                if ln.startswith("VWORLD_KEY="):
                    v = ln.split("=", 1)[1].strip()
                    if v:
                        return v
        except OSError:
            pass
    return None


def vworld_fetch(path: str, params: dict) -> dict:
    key = _key()
    if not key:
        raise RuntimeError("VWORLD_KEY가 없음 — vworld.kr 회원가입 → 오픈API → 인증키 발급(활용 API에 '국가중점API' 포함) 뒤 .env에 VWORLD_KEY= 로 넣으세요. 키 없이 쓰려면 공시가격을 직접 넣으세요(unlisted_stock_valuation의 assets 기준시가)")
    q = {**params, "key": key}
    url = f"{VWORLD}{path}?" + urllib.parse.urlencode(q, safe=":,")
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def _walk(o, pred):
    if isinstance(o, dict):
        if pred(o):
            yield o
        for v in o.values():
            yield from _walk(v, pred)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v, pred)


def address_to_pnu(address: str, fetch: Fetcher = vworld_fetch) -> dict[str, Any]:
    """브이월드 주소 검색(지번·도로명 모두) → PNU(19자리)·지번."""
    out = {"query": address, "candidates": []}
    for cat in ("parcel", "road"):
        d = fetch("/req/search", {"service": "search", "request": "search", "version": "2.0", "crs": "EPSG:4326", "size": "10", "page": "1",
                                  "query": address, "type": "address", "category": cat, "format": "json"})
        items = list(_walk(d, lambda x: "id" in x and ("address" in x or "jibun" in str(x).lower())))
        for it in items:
            pnu = str(it.get("id") or "")
            addr = it.get("address") or {}
            parcel = addr.get("parcel") if isinstance(addr, dict) else None
            if pnu and len(pnu) == 19 and pnu.isdigit():
                out["candidates"].append({"pnu": pnu, "지번주소": parcel or "", "도로명주소": (addr.get("road") if isinstance(addr, dict) else "") or "", "구분": cat})
        if out["candidates"]:
            break
    if not out["candidates"]:
        return {"error": f"'{address}'에 맞는 필지를 찾지 못함 — 지번(시군구 동 번지) 또는 도로명 주소를 더 정확히"}
    return out


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def land_price(pnu: str, year: int | None, fetch: Fetcher = vworld_fetch) -> dict[str, Any]:
    params = {"pnu": pnu, "format": "json", "numOfRows": "100", "pageNo": "1"}
    if year:
        params["stdrYear"] = str(year)
    d = fetch("/ned/data/getIndvdLandPriceAttr", params)
    rows = [r for r in _walk(d, lambda x: any(k.lower() == "pblntfpclnd" for k in x))]
    if not rows:
        return {"error": f"PNU {pnu}의 개별공시지가 자료 없음(연도 {year or '전체'}) — 토지가 아니거나 미공시 필지일 수 있음"}
    out = []; seen = set()
    for r in rows:
        g = {k.lower(): v for k, v in r.items()}
        key = (g.get("stdryear"), g.get("pblntfde"), g.get("pblntfpclnd"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"기준연도": g.get("stdryear"), "공시일": g.get("pblntfde"), "공시지가_원_㎡": _num(g.get("pblntfpclnd")), "지번": g.get("mnnmslno"), "법정동": g.get("ldcodenm"), "표준지": g.get("stdlandat")})
    out.sort(key=lambda x: (str(x["기준연도"] or ""), str(x["공시일"] or "")), reverse=True)
    return {"pnu": pnu, "종류": "토지(개별공시지가)", "연도별": out, "근거": "부동산 가격공시에 관한 법률 제10조(개별공시지가) — 상증법 제61조①1호, 소득세법 제99조①1호가목"}


def apartment_price(pnu: str, year: int | None, dong: str = "", ho: str = "", fetch: Fetcher = vworld_fetch, page_size: int = 1000, max_pages: int = 20) -> dict[str, Any]:
    """공동주택가격 — 한 필지(단지)에 세대가 수천 건이라 페이지를 넘기며 동·호를 찾는다. 동·호가 없으면 단지 요약."""
    def norm(x):
        return str(x or "").replace(" ", "").replace("동", "").replace("호", "").lstrip("0")
    want_d, want_h = norm(dong), norm(ho)
    rows_all = []; total = None; found = None
    for page in range(1, max_pages + 1):
        params = {"pnu": pnu, "format": "json", "numOfRows": str(page_size), "pageNo": str(page)}
        if year:
            params["stdrYear"] = str(year)
        d = fetch("/ned/data/getApartHousingPriceAttr", params)
        top = d.get("apartHousingPrices", d) if isinstance(d, dict) else {}
        try:
            total = int(top.get("totalCount")) if isinstance(top, dict) and top.get("totalCount") is not None else total
        except (TypeError, ValueError):
            pass
        rows = [r for r in _walk(d, lambda x: any(k.lower() == "pblntfpc" for k in x))]
        if not rows:
            break
        rows_all.extend(rows)
        if want_d or want_h:
            for r in rows:
                g = {k.lower(): v for k, v in r.items()}
                if (not want_d or norm(g.get("dongnm")) == want_d) and (not want_h or norm(g.get("honm")) == want_h):
                    found = g if (found is None or str(g.get("stdryear", "")) > str(found.get("stdryear", ""))) else found
            if found and (year or page * page_size >= (total or 0)):
                break
        if total is not None and page * page_size >= total:
            break
    if not rows_all:
        return {"error": f"PNU {pnu}의 공동주택가격 자료 없음(연도 {year or '전체'})"}
    def row(g):
        return {"기준연도": g.get("stdryear"), "공시일": g.get("pblntfde"), "단지": g.get("aphusnm"), "동": g.get("dongnm"), "호": g.get("honm"), "층": g.get("floornm"), "전용면적_㎡": _num(g.get("prvusear")), "공동주택가격_원": _num(g.get("pblntfpc"))}
    근거 = "부동산 가격공시에 관한 법률 제18조(공동주택가격) — 상증법 제61조①4호, 소득세법 제99조①1호라목"
    if want_d or want_h:
        if not found:
            return {"error": f"PNU {pnu}에서 동 '{dong}' 호 '{ho}'를 찾지 못함(조회 {len(rows_all):,}건/{total or '?'}건) — 동은 '28', 호는 '1207'처럼 자료 표기로", "단지": {k.lower(): v for k, v in rows_all[0].items()}.get("aphusnm")}
        return {"pnu": pnu, "종류": "공동주택(공동주택가격)", "연도별": [row(found)], "건수": len({(({k.lower(): v for k, v in r.items()}).get("dongnm"), ({k.lower(): v for k, v in r.items()}).get("honm")) for r in rows_all}), "근거": 근거}
    gs = []; seen = set()
    for r in rows_all:   # 같은 세대·연도·공시일 중복 행 제거(API가 두 번씩 주는 경우가 있음)
        g = {k.lower(): v for k, v in r.items()}
        key = (g.get("dongnm"), g.get("honm"), g.get("stdryear"), g.get("pblntfde"))
        if key in seen:
            continue
        seen.add(key); gs.append(g)
    prices = [p for p in (_num(g.get("pblntfpc")) for g in gs) if p]
    areas = sorted({_num(g.get("prvusear")) for g in gs if _num(g.get("prvusear"))})
    summary = {"기준연도": max(str(g.get("stdryear", "")) for g in gs), "단지": gs[0].get("aphusnm"), "세대수(조회분)": len(gs), "자료행수": total, "공시가격_최저_원": min(prices) if prices else None, "공시가격_최고_원": max(prices) if prices else None, "전용면적_종류_㎡": areas[:12], "안내": "동·호(dong·ho)를 주면 그 세대의 공시가격을 돌려줌"}
    return {"pnu": pnu, "종류": "공동주택(공동주택가격)", "연도별": [summary], "건수": total or len(gs), "근거": 근거, "요약": True}


def house_price(pnu: str, year: int | None, fetch: Fetcher = vworld_fetch) -> dict[str, Any]:
    params = {"pnu": pnu, "format": "json", "numOfRows": "100", "pageNo": "1"}
    if year:
        params["stdrYear"] = str(year)
    d = fetch("/ned/data/getIndvdHousingPriceAttr", params)
    rows = [r for r in _walk(d, lambda x: any(k.lower() == "housepc" for k in x))]
    if not rows:
        return {"error": f"PNU {pnu}의 개별주택가격 자료 없음(연도 {year or '전체'})"}
    out = []
    for r in rows:
        g = {k.lower(): v for k, v in r.items()}
        out.append({"기준연도": g.get("stdryear"), "공시일": g.get("pblntfde"), "개별주택가격_원": _num(g.get("housepc")), "대지면적_㎡": _num(g.get("lndpclar") or g.get("calcprcar")), "건물면적_㎡": _num(g.get("buldcalcar"))})
    out.sort(key=lambda x: str(x["기준연도"] or ""), reverse=True)
    return {"pnu": pnu, "종류": "단독주택(개별주택가격)", "연도별": out, "근거": "부동산 가격공시에 관한 법률 제17조(개별주택가격) — 상증법 제61조①4호, 소득세법 제99조①1호라목"}


def official_price(address: str = "", pnu: str = "", kind: str = "토지", year: int | None = None, area_m2: float | None = None,
                   dong: str = "", ho: str = "", fetch: Fetcher = vworld_fetch) -> dict[str, Any]:
    판단: list[dict] = []
    try:
        if not pnu:
            if not address:
                return {"error": "입력 확인 필요 — 계산하지 않음", "문제": ["address(지번 또는 도로명 주소) 또는 pnu(19자리 필지번호)가 필요"]}
            a = address_to_pnu(address, fetch)
            if "error" in a:
                return a
            pnu = a["candidates"][0]["pnu"]
            판단.append({"항목": "필지", "결론": f"'{address}' → PNU {pnu} ({a['candidates'][0].get('지번주소') or a['candidates'][0].get('도로명주소')})" + (f" — 후보 {len(a['candidates'])}건 중 첫째, 다르면 pnu로 지정" if len(a["candidates"]) > 1 else ""), "근거": "브이월드 주소검색(국토교통부)"})
        k = (kind or "토지").strip()
        if k in ("토지", "땅", "대지", "임야", "전", "답"):
            r = land_price(pnu, year, fetch)
            if "error" in r:
                return {**r, "판단": 판단}
            latest = r["연도별"][0]
            total = (latest["공시지가_원_㎡"] or 0) * float(area_m2) if area_m2 and latest["공시지가_원_㎡"] else None
            res = {"pnu": pnu, "기준연도": latest["기준연도"], "공시일": latest["공시일"], "공시지가_원_㎡": latest["공시지가_원_㎡"], "면적_㎡": area_m2, "공시지가_총액_원": total}
            판단.append({"항목": "평가 사용", "결론": "상속·증여 재산 평가에서 토지의 보충적 평가액 = 개별공시지가 × 면적(법 제61조①1호). 시가(매매·감정 사례)가 있으면 시가 우선(법 제60조). 양도세 기준시가도 같은 공시지가(소득세법 제99조①1호가목)", "근거": r["근거"]})
            if total is None:
                판단.append({"항목": "확인 필요", "결론": "면적(area_m2, 등기부·토지대장 면적)을 주면 공시지가 × 면적 총액을 계산 — 이 API는 면적을 주지 않음", "근거": "—"})
        elif k in ("아파트", "공동주택", "연립", "다세대", "오피스텔"):
            r = apartment_price(pnu, year, dong, ho, fetch)
            if "error" in r:
                return {**r, "판단": 판단}
            latest = r["연도별"][0]
            res = {"pnu": pnu, **latest, "같은 필지 세대수": r["건수"]} if r.get("요약") else {"pnu": pnu, "기준연도": latest["기준연도"], "단지": latest["단지"], "동": latest["동"], "호": latest["호"], "층": latest.get("층"), "전용면적_㎡": latest["전용면적_㎡"], "공동주택가격_원": latest["공동주택가격_원"], "같은 필지 세대수": r["건수"]}
            판단.append({"항목": "평가 사용", "결론": "공동주택가격이 상속·증여 보충적 평가액(법 제61조①4호)·양도세 기준시가(소득세법 제99조①1호라목). 다만 아파트는 유사매매사례가액이 시가로 잡히는 경우가 많아(영 제49조④) 시가 확인이 먼저", "근거": r["근거"]})
        elif k in ("단독", "단독주택", "다가구", "주택"):
            r = house_price(pnu, year, fetch)
            if "error" in r:
                return {**r, "판단": 판단}
            latest = r["연도별"][0]
            res = {"pnu": pnu, "기준연도": latest["기준연도"], "개별주택가격_원": latest["개별주택가격_원"], "대지면적_㎡": latest["대지면적_㎡"], "건물면적_㎡": latest["건물면적_㎡"]}
            판단.append({"항목": "평가 사용", "결론": "개별주택가격(토지+건물 일괄)이 상속·증여 보충적 평가액(법 제61조①4호)·양도세 기준시가(소득세법 제99조①1호라목)", "근거": r["근거"]})
        else:
            return {"error": "입력 확인 필요 — 계산하지 않음", "문제": [f"kind='{kind}' — 토지|아파트(공동주택)|단독주택"], "허용값": ["토지", "아파트", "단독주택"]}
        판단.append({"항목": "기준일", "결론": f"공시가격은 매년 1월 1일 기준으로 공시(토지·단독 5월 말, 공동주택 4월 말 공시). 평가기준일이 그 해 공시 전이면 전년도 가격을 쓰는 것이 원칙(상증법 시행령 제50조③·소득세법 시행령 제164조) — 연도 선택은 year로", "근거": "부동산 가격공시에 관한 법률 제3조·제16조~제18조"})
        return {"결과": res, "연도별": r["연도별"][:10], "판단": 판단, "근거": r["근거"], "출처": "국토교통부 국가공간정보(브이월드 NED) — 외부로 나간 정보: 주소·PNU·연도"}
    except RuntimeError as e:
        return {"error": str(e), "대안": "공시가격을 알면 unlisted_stock_valuation의 assets에 기준시가로, 또는 inheritance_gift_valuation의 supplementary_value로 직접"}
