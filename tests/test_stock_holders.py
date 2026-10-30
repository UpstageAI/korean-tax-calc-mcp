"""주주 명부 → 지분율·합산 범위 → 대주주 판정 (영 제157조 구간별 합산 방식). 손계산 정답. 작성 Claude 2026-10-30."""
import asyncio, json
from korean_tax_calc_mcp.server import mcp
from korean_tax_calc_mcp.engine.calc_stock import parse_relation


def M(**a):
    r = asyncio.run(mcp.call_tool("stock_major_shareholder", a))
    return json.loads((r.content[0] if hasattr(r, "content") else r[0][0]).text)


def test_parse_relation_words():
    assert parse_relation("아들")[:3] == ("혈족", 1, True)
    assert parse_relation("처남")[:3] == ("인척", 2, False)
    assert parse_relation("사촌 형")[:3] == ("혈족", 4, False)
    assert parse_relation("사촌 동생")[:3] == ("혈족", 4, False)
    assert parse_relation("외삼촌")[:3] == ("혈족", 3, False)
    assert parse_relation("5촌 당숙")[:3] == ("혈족", 5, False)
    assert parse_relation("혈족 6촌")[:3] == ("혈족", 6, False)
    assert parse_relation("내가 60% 가진 법인")[0] == "경영지배"
    assert parse_relation("옆집") is None


HOLDERS = [{"이름": "배우자", "관계": "배우자", "주식수": 3000}, {"이름": "아들", "관계": "아들", "주식수": 2000},
           {"이름": "처남", "관계": "처남", "주식수": 4000}, {"이름": "5촌", "관계": "5촌 당숙", "주식수": 5000}]


def test_listed_2026_self_unless_max():
    base = dict(transfer_date="2026-03-10", market="코스피", total_shares=1_000_000, own_shares=5000, holders=HOLDERS, price=1000)
    r = M(**base, is_max_group=False)
    assert r["결과"]["판정"] == "대주주 아님" and abs(r["계산"]["본인_지분율"] - 0.005) < 1e-9
    assert {x["주주"]: x["판정"] for x in r["주주별"]} == {"배우자": "제외", "아들": "제외", "처남": "제외", "5촌": "제외"}
    r = M(**base, is_max_group=True)   # 배우자·아들·처남(인척 2촌 ≤ 3) 합산, 5촌 혈족은 4촌 밖
    assert {x["주주"]: x["판정"] for x in r["주주별"]} == {"배우자": "합산", "아들": "합산", "처남": "합산", "5촌": "제외"}
    assert abs(r["계산"]["합산_지분율"] - 0.014) < 1e-9 and r["결과"]["판정"] == "대주주"
    r = M(**base)   # 최대주주군 모름 → 조건부 합산으로 충족 → 확인 필요
    assert r["결과"]["판정"] == "확인 필요"


def test_unlisted_2026_nonmax_still_aggregates_lineal_and_spouse():
    base = dict(transfer_date="2026-03-10", market="비상장", total_shares=100_000, own_shares=3000, holders=HOLDERS)
    r = M(**base, is_max_group=False)   # 본인 3% + 배우자 3% + 아들 2% = 8% ≥ 4%; 처남·5촌 제외
    assert {x["주주"]: x["판정"] for x in r["주주별"]} == {"배우자": "합산", "아들": "합산", "처남": "제외", "5촌": "제외"}
    assert r["결과"]["판정"] == "대주주" and abs(r["계산"]["합산_지분율"] - 0.08) < 1e-9
    assert any("시가총액 기준은 판정하지 않음" in x["결론"] for x in r["판단"])


def test_2019_max_group_split_six_chon():
    base = dict(transfer_date="2019-06-01", market="코스피", total_shares=1_000_000, own_shares=5000, holders=HOLDERS, price=1000)
    r = M(**base, is_max_group=True)    # 2022까지 6촌 혈족·4촌 인척 → 5촌도 합산: 0.5+0.3+0.2+0.4+0.5 = 1.9% ≥ 1%
    assert {x["주주"]: x["판정"] for x in r["주주별"]} == {"배우자": "합산", "아들": "합산", "처남": "합산", "5촌": "합산"}
    assert r["결과"]["판정"] == "대주주"
    r = M(**base, is_max_group=False)   # 직계존비속·배우자만: 1.0% ≥ 1% → 대주주
    assert {x["주주"]: x["판정"] for x in r["주주별"]}["처남"] == "제외" and r["결과"]["판정"] == "대주주"


def test_lent_and_pef_shares_and_controlled_corp():
    r = M(transfer_date="2026-03-10", market="코스닥", total_shares=1_000_000, own_shares=10_000, lent_shares=5_000, pef_shares=6_000,
          holders=[{"이름": "㈜내법인", "관계": "경영지배", "주식수": 0}], price=1000, is_max_group=False)
    assert abs(r["계산"]["본인_지분율"] - 0.021) < 1e-9 and r["결과"]["판정"] == "대주주"   # 2.1% ≥ 2%
    assert any("대여" in x["결론"] and "사모" in x["결론"] for x in r["판단"])


def test_unknown_relation_and_missing_total():
    e = M(transfer_date="2026-03-10", market="코스피", total_shares=1000, own_shares=10, holders=[{"이름": "x", "관계": "옆집", "주식수": 1}])
    assert e["error"].startswith("입력 확인 필요") and "허용값" in e
    e = M(transfer_date="2026-03-10", market="코스피", own_shares=10)
    assert "total_shares" in e["문제"][0]
    e = M(transfer_date="2026-03-10", market="코스피", total_shares=1000, own_shares=10, own_ratio=0.5)
    assert "함께 주지" in e["문제"][0]
