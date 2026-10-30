"""공시가격 조회 — 가짜 브이월드 응답으로 주소→PNU, 토지·아파트·단독 파싱과 안내 검사(네트워크 없음). 작성 Claude 2026-10-30."""
from korean_tax_calc_mcp.engine.calc_official_price import official_price

PNU = "1168010100107370000"


def fake(path, params):
    if path == "/req/search":
        if params["category"] == "parcel":
            return {"response": {"status": "OK", "result": {"items": [{"id": PNU, "address": {"parcel": "서울특별시 강남구 역삼동 737", "road": "서울특별시 강남구 테헤란로 7길 22"}}]}}}
        return {"response": {"status": "NOT_FOUND"}}
    if path == "/ned/data/getIndvdLandPriceAttr":
        return {"indvdLandPrices": {"field": [{"pnu": PNU, "stdrYear": "2024", "pblntfPclnd": "15000000", "pblntfDe": "20240531", "mnnmSlno": "737", "ldCodeNm": "서울특별시 강남구 역삼동", "lndpclAr": "500"},
                                              {"pnu": PNU, "stdrYear": "2025", "pblntfPclnd": "16000000", "pblntfDe": "20250530", "mnnmSlno": "737", "ldCodeNm": "서울특별시 강남구 역삼동", "lndpclAr": "500"}]}}
    if path == "/ned/data/getApartHousingPriceAttr":
        return {"apartHousingPrices": {"field": [{"pnu": PNU, "stdrYear": "2025", "aphusNm": "가상아파트", "dongNm": "101", "hoNm": "1203", "prvuseAr": "84.9", "pblntfPc": "1200000000", "pblntfDe": "20250430"},
                                                 {"pnu": PNU, "stdrYear": "2025", "aphusNm": "가상아파트", "dongNm": "101", "hoNm": "1204", "prvuseAr": "84.9", "pblntfPc": "1190000000", "pblntfDe": "20250430"}]}}
    if path == "/ned/data/getIndvdHousingPriceAttr":
        return {"indvdHousingPrices": {"field": [{"pnu": PNU, "stdrYear": "2025", "housePc": "900000000", "pblntfDe": "20250530", "lndpclAr": "200", "buldCalcAr": "150"}]}}
    return {}


def test_land_from_address_with_area():
    r = official_price(address="서울 강남구 역삼동 737", kind="토지", area_m2=500, fetch=fake)
    assert r["결과"]["pnu"] == PNU and r["결과"]["기준연도"] == "2025" and r["결과"]["공시지가_원_㎡"] == 16_000_000 and r["결과"]["공시지가_총액_원"] == 8_000_000_000
    assert any("PNU" in x["결론"] for x in r["판단"])
    r24 = official_price(pnu=PNU, kind="땅", year=2024, fetch=fake)
    assert r24["결과"]["기준연도"] == "2025"   # 가짜는 연도 필터를 안 하므로 최신이 옴 — 실제 API는 stdrYear로 거름


def test_apartment_dong_ho_filter():
    r = official_price(pnu=PNU, kind="아파트", dong="101", ho="1203", fetch=fake)
    assert r["결과"]["공동주택가격_원"] == 1_200_000_000 and r["결과"]["호"] == "1203"
    e = official_price(pnu=PNU, kind="아파트", dong="102", ho="1", fetch=fake)
    assert "error" in e


def test_house_and_bad_kind_and_no_key():
    r = official_price(pnu=PNU, kind="단독주택", fetch=fake)
    assert r["결과"]["개별주택가격_원"] == 900_000_000
    e = official_price(pnu=PNU, kind="상가", fetch=fake)
    assert e["error"].startswith("입력 확인 필요")
    def nokey(path, params):
        raise RuntimeError("VWORLD_KEY가 없음 — 안내")
    e = official_price(address="서울 강남구 역삼동 737", fetch=nokey)
    assert "VWORLD_KEY" in e["error"] and "대안" in e
