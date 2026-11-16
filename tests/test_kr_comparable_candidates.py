"""kr_comparable_candidates — 네트워크 없이 고정본(tests/data/kr_comparables_fixtures: 상장 2·비상장 3건의 API 응답·원문 일부)으로. Claude 작성(2026-11-16).
재무·매출 구성 값은 tests/data/kr_comparables_gold.json(원문 대조 정답)과 같아야 한다. 실제 API 호출은 금지(transport 모킹)."""
import io
import json
import os
import re
import urllib.parse
import zipfile

import pytest

from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import revenue_mix as RM
from korean_tax_calc_mcp.engine.kr_comparables.dart import DartClient, DartStop, mask

HERE = os.path.dirname(__file__)
FX = os.path.join(HERE, "data", "kr_comparables_fixtures")
API = json.load(open(os.path.join(FX, "api.json"), encoding="utf-8"))
GOLD = {g["corp_code"]: g for g in json.load(open(os.path.join(HERE, "data", "kr_comparables_gold.json"), encoding="utf-8"))["companies"]}
FAKE_KEY = "f" * 8 + "0123456789abcdef0123456789abcdef"   # 40자 — 실제 키 아님


def _zip(name, data):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, data)
    return b.getvalue()


def _corp_xml():
    rows = "".join(f"<list><corp_code>{c['corp_code']}</corp_code><corp_name>{c['corp_name']}</corp_name><stock_code>{c['stock_code']}</stock_code></list>" for c in API["corps"])
    return _zip("CORPCODE.xml", f"<?xml version='1.0' encoding='UTF-8'?><result>{rows}</result>")


class Transport:
    """OpenDART를 흉내 낸다. 받은 URL을 모두 기록(키 가림 검사용)."""

    def __init__(self):
        self.urls = []

    def __call__(self, url, timeout=60):
        self.urls.append(url)
        u = urllib.parse.urlparse(url)
        ep = u.path.rsplit("/", 1)[-1]
        q = dict(urllib.parse.parse_qsl(u.query))
        assert q.get("crtfc_key") == FAKE_KEY
        J = lambda d: json.dumps(d, ensure_ascii=False).encode()
        if ep == "corpCode.xml":
            return _corp_xml()
        if ep == "company.json":
            return J(API["company"].get(q["corp_code"], {"status": "013", "message": "없음"}))
        if ep == "fnlttSinglAcntAll.json":
            return J(API["fnltt"].get(f"{q['corp_code']}_{q['bsns_year']}_{q['fs_div']}", {"status": "013", "message": "조회된 데이타가 없습니다."}))
        if ep == "hyslrSttus.json":
            return J(API["hyslr"].get(q["corp_code"], {"status": "013"}))
        if ep == "list.json":
            if "corp_code" in q:
                return J(API["list_corp"].get(f"{q['corp_code']}_{q['pblntf_ty']}", {"status": "013", "list": []}))
            return J(API["pool"])
        if ep == "document.xml":
            rc = q["rcept_no"]
            return _zip(rc + ".xml", open(os.path.join(FX, rc + ".xml"), encoding="utf-8").read())
        raise AssertionError("모르는 요청 " + ep)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DART_API_KEY", FAKE_KEY)
    monkeypatch.delenv("UPSTAGE_API_KEY", raising=False)
    monkeypatch.delenv("KR_COMPARABLES_DAILY_CAP", raising=False)
    return tmp_path


def _client(tr, **kw):
    return DartClient(key=FAKE_KEY, transport=tr, interval=0, sleep=lambda s: None, **kw)


def _gold_solar(body, key):
    """Solar 흉내 — 행 이름을 정답 데이터의 분류로 돌려줌(금액은 보내지 않았는지도 확인)."""
    content = body["messages"][0]["content"]
    assert key == "u" * 20
    labels = re.findall(r"^id=(\d+): (.*)$", content, re.M)
    lab2cat = {r["label"]: r["category"] for g in GOLD.values() if g["revenue_mix"]["status"] == "확보" for r in g["revenue_mix"]["rows"]}
    ko = {"product": "재화", "merchandise": "재화", "service": "용역", "sw_license": "SW·라이선스", "platform_fee": "플랫폼·중개수수료", "other": "기타"}
    assert "제조 여부" in content and "회사 맥락" in content       # 제품/상품은 모델에 묻지 않음
    rows = [{"id": int(i), "category": ko.get(lab2cat.get(l, "other"), "기타"), "reason": "테스트"} for i, l in labels]
    for _, l in labels:
        assert not re.search(r"\d{1,3}(,\d{3}){2,}", l)   # 금액이 들어가지 않음
    return {"choices": [{"message": {"content": json.dumps({"rows": rows}, ensure_ascii=False)}}], "usage": {"prompt_tokens": 1, "completion_tokens": 1}}


def run(tr, **kw):
    a = dict(industry_codes=["46"], years=[2024], listed="둘 다", limit=10, client=_client(tr))
    a.update(kw)
    return C.run(**a)


# ---------- 재무·매출 구성·프로필 정답 ----------
def test_financials_match_gold(env):
    tr = Transport()
    r = run(tr, upstage_key="u" * 20, solar_http=_gold_solar)["결과"]
    assert r["후보_수"] == 5 and r["멈춤"] == ""
    names = {x["company_id"] for x in r["후보_행"]}
    assert names == set(GOLD) & names and len(names) == 5
    for row in r["후보_행"]:
        g = GOLD[row["company_id"]]["values"]
        for k in ("revenue", "operating_profit", "total_assets", "inventory"):
            assert row[k] == g[k], (row["company_name"], k, row[k], g[k])
        assert row["fs_div"] == "별도" and row["year"] == 2024 and len(row["rcept_no"]) == 14
    # 업종 거르기: 582 회사는 빠짐
    assert all(not p["industry_code"].startswith("58") for p in r["후보_프로필"])


def test_revenue_mix_and_profile_match_gold(env):
    r = run(Transport(), upstage_key="u" * 20, solar_http=_gold_solar)["결과"]
    assert r["정확도_낮음"] is False and any("Solar" in m for m in r["매출_분류_방법"])
    for p in r["후보_프로필"]:
        g = GOLD[p["company_id"]]
        mix = g["revenue_mix"]
        main = mix["main_category"]
        assert p["mix_coverage"]["status"] == "확보", p["company_name"]
        ev = p["mix_coverage"]["evidence"]
        rows = ev["rows"]
        goods = [x for x in rows if x["category"] == "goods"]
        if goods:   # 모델은 '재화'까지만 — 제품/상품은 회계 비율로 배분
            m, tot = ev["accounting"]["merch_ratio"], sum(x["amount"] for x in rows)
            G = sum(x["amount"] for x in goods)
            assert all(x["reason"].startswith("회계 기준 배분") for x in goods)
            assert p["mix_merchandise"]["value"] == pytest.approx(G * m / tot, rel=1e-9)
            assert p["mix_product"]["value"] == pytest.approx(G * (1 - m) / tot, rel=1e-9)
            assert p["mix_product"]["note"] == "회계 기준 배분" and ev["accounting"]["rcept_no"] == ev["rcept_no"]
        else:       # 원문 계정명(제품매출·상품매출) — 정답 그대로
            assert p["mix_" + main]["value"] == pytest.approx(mix["main_share"], abs=1e-3), (p["company_name"], main)
        assert sorted(x["amount"] for x in rows) == sorted(x["amount"] for x in mix["rows"])   # 금액은 원문 그대로
        v = g["values"]
        assert p["ppe_ratio"]["value"] == pytest.approx(v["ppe"] / v["total_assets"], rel=1e-9)
        assert p["inv_to_sales"]["value"] == pytest.approx(v["inventory"] / v["revenue"], rel=1e-9)
        assert p["inv_to_sales"]["evidence"]["rcept_no"] == p["rcept_no"]
    listed = [p for p in r["후보_프로필"] if p["listed"]]
    assert len(listed) == 2 and all(p["max_shareholder_pct"]["status"] == "확보" for p in listed)
    by = {p["company_name"]: p for p in listed}
    u = by["(주)유니트론텍"]          # 매출원가에 상품만(상품매출원가) — 원문 숫자로 상품
    assert u["mix_coverage"]["evidence"]["accounting"]["source"] == "매출원가 상품:제품" and u["mix_merchandise"]["value"] == pytest.approx(0.998, abs=1e-3)
    h = by["(주)휴맥스"]              # 재고 상품 26억 : 제품·원재료 171억 → 제품 위주
    assert h["mix_coverage"]["evidence"]["accounting"]["source"].startswith("재고") and h["mix_product"]["value"] > 0.8
    assert all(p["max_shareholder_pct"]["status"] == "불명-못찾음" for p in r["후보_프로필"] if not p["listed"])


def test_rule_classification_marks_low_accuracy(env):
    r = run(Transport())["결과"]
    assert r["정확도_낮음"] is True and any("정확도 낮음" in m for m in r["매출_분류_방법"])
    unl = {p["company_id"]: p for p in r["후보_프로필"] if not p["listed"]}
    for cc, p in unl.items():   # 비상장 '상품매출' 행은 계정명 그대로 → 정답과 같음
        g = GOLD[cc]["revenue_mix"]
        assert p["mix_merchandise"]["value"] == pytest.approx(g["shares"]["merchandise"], abs=1e-3)


def test_listed_only_and_limit(env):
    r = run(Transport(), listed="상장", limit=1)["결과"]
    assert r["후보_수"] == 1 and all(p["listed"] for p in r["후보_프로필"])
    r = run(Transport(), listed="비상장")["결과"]
    assert r["후보_수"] == 3 and not any(p["listed"] for p in r["후보_프로필"])


def test_revenue_filter(env):
    r = run(Transport(), revenue_min=100_000_000_000)["결과"]
    kept = {p["company_name"] for p in r["후보_프로필"]}
    assert all(GOLD[p["company_id"]]["values"]["revenue"] >= 100_000_000_000 for p in r["후보_프로필"])
    assert len(r["제외_목록"]) == 5 - len(kept)


def test_cache_reuse(env):
    tr = Transport()
    run(tr)
    n = len(tr.urls)
    tr2 = Transport()
    r = run(tr2)["결과"]
    assert n > 0 and len(tr2.urls) == 0 and r["호출"]["OpenDART_실호출"] == 0 and r["호출"]["OpenDART_캐시"] > 0


# ---------- 키 없음·키 노출·상한 ----------
def test_no_key_guidance(monkeypatch, tmp_path):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path))
    r = C.run(industry_codes=["4651"], years=[2024])
    assert "꺼짐" in r["결과"]["상태"] and "opendart.fss.or.kr" in r["결과"]["안내"] and "본인" in r["결과"]["안내"]


def test_no_key_in_outputs(env, capsys):
    tr = Transport()
    r = run(tr, upstage_key="u" * 20, solar_http=_gold_solar)
    s = json.dumps(r, ensure_ascii=False) + capsys.readouterr().out
    assert FAKE_KEY not in s and "u" * 20 not in s and "crtfc_key" not in s
    for root, _, files in os.walk(os.environ["KR_COMPARABLES_CACHE_DIR"]):
        for f in files:
            assert FAKE_KEY.encode() not in open(os.path.join(root, f), "rb").read()


def test_error_message_masks_key(env):
    def boom(url, timeout=60):
        raise OSError("connect failed for " + url)
    dc = _client(boom)
    d = dc.get("company.json", {"corp_code": "00000001"})
    assert d["status"] == "NET" and FAKE_KEY not in d["message"] and "crtfc_key=***" in d["message"]
    assert mask("x crtfc_key=abc&y=1", "") == "x crtfc_key=***&y=1"


def test_consecutive_errors_stop(env):
    def boom(url, timeout=60):
        raise OSError("down")
    dc = _client(boom)
    with pytest.raises(DartStop, match="연속 오류 5회"):
        for i in range(10):
            dc.get("company.json", {"corp_code": f"{i:08d}"})
    assert dc.calls == 5 * 4            # 요청 5건 × (처음 1 + 재시도 3)


# ---------- 재시도(일시 오류만, 1·2·4초) ----------
class Flaky:
    def __init__(self, fails, exc):
        self.n, self.fails, self.exc, self.inner = 0, fails, exc, Transport()

    def __call__(self, url, timeout=60):
        self.n += 1
        if self.n <= self.fails:
            raise self.exc(url)
        return self.inner(url)


def _http_error(code):
    import urllib.error
    return lambda url: urllib.error.HTTPError(url, code, f"HTTP {code}", {}, None)


def test_retry_then_success(env):
    waits = []
    tr = Flaky(2, lambda url: TimeoutError("timed out " + url))
    dc = DartClient(key=FAKE_KEY, transport=tr, interval=0, sleep=waits.append)
    d = dc.get("company.json", {"corp_code": "00879020"})
    assert d["status"] == "000" and dc.calls == 3 and dc.retries == 2 and waits == [1.0, 2.0]
    assert dc._day_count() == 3                       # 재시도도 하루 상한에 셈


def test_retry_exhausted(env):
    waits = []
    tr = Flaky(99, lambda url: ConnectionResetError("reset " + url))
    dc = DartClient(key=FAKE_KEY, transport=tr, interval=0, sleep=waits.append)
    d = dc.get("company.json", {"corp_code": "00879020"})
    assert d["status"] == "NET" and dc.calls == 4 and waits == [1.0, 2.0, 4.0]
    assert "재시도 후 실패" in d["message"] and FAKE_KEY not in d["message"] and dc._consec == 1


@pytest.mark.parametrize("code,calls", [(500, 4), (503, 4), (429, 4), (404, 1), (401, 1)])
def test_retry_only_transient_http(env, code, calls):
    tr = Flaky(99, _http_error(code))
    dc = DartClient(key=FAKE_KEY, transport=tr, interval=0, sleep=lambda s: None)
    assert dc.get("company.json", {"corp_code": "00879020"})["status"] == "NET"
    assert dc.calls == calls


def test_no_retry_on_020_and_013(env):
    n = {"k": 0}

    def t020(url, timeout=60):
        n["k"] += 1
        return json.dumps({"status": "020", "message": "한도 초과"}).encode()
    dc = _client(t020)
    with pytest.raises(DartStop, match="020"):
        dc.get("company.json", {"corp_code": "00000001"})
    assert n["k"] == 1 and dc.retries == 0
    dc = _client(lambda url, timeout=60: json.dumps({"status": "013", "message": "없음"}).encode())
    assert dc.get("company.json", {"corp_code": "00000002"})["status"] == "013" and dc.calls == 1


def test_retry_counts_toward_run_cap(env):
    tr = Flaky(99, lambda url: TimeoutError("t"))
    dc = DartClient(key=FAKE_KEY, transport=tr, interval=0, sleep=lambda s: None, max_calls=2)
    with pytest.raises(DartStop, match="호출 상한"):
        dc.get("company.json", {"corp_code": "00879020"})
    assert dc.calls == 2


def test_solar_timeout_falls_back_to_rules(env, monkeypatch):
    calls = {"n": 0}

    def slow(body, key):
        calls["n"] += 1
        raise TimeoutError("read timed out")
    monkeypatch.setattr(RM, "_sleep", lambda s: None)
    r = run(Transport(), upstage_key="u" * 20, solar_http=slow)["결과"]
    assert r["정확도_낮음"] is True and any("정확도 낮음" in m for m in r["매출_분류_방법"])
    assert r["후보_수"] == 5 and calls["n"] % 4 == 0 and r["호출"]["오류"]
    assert "u" * 20 not in json.dumps(r, ensure_ascii=False)


def test_solar_retry_then_success(env, monkeypatch):
    calls = {"n": 0}

    def flaky(body, key):
        calls["n"] += 1
        if calls["n"] % 3:                 # 요청마다 두 번 실패 후 성공
            raise TimeoutError("t")
        return _gold_solar(body, key)
    monkeypatch.setattr(RM, "_sleep", lambda s: None)
    r = run(Transport(), upstage_key="u" * 20, solar_http=flaky)["결과"]
    assert r["정확도_낮음"] is False and any("Solar" in m for m in r["매출_분류_방법"])


def test_status_020_stops(env):
    dc = _client(lambda url, timeout=60: json.dumps({"status": "020", "message": "한도 초과"}).encode())
    with pytest.raises(DartStop, match="020"):
        dc.get("company.json", {"corp_code": "00000001"})


def test_run_call_cap(env):
    r = run(Transport(), client=_client(Transport(), max_calls=3))["결과"]
    assert "호출 상한(3건)" in r["멈춤"] and r["호출"]["OpenDART_실호출"] == 3
    assert r["남은_회사_수"] > 0 and "이어서 계속" in r["이어서"]


def test_resume_after_cap(env):
    tr = Transport()
    first = run(tr, client=_client(tr, max_calls=8))["결과"]
    assert first["멈춤"] and first["남은_회사_수"] > 0
    second = run(Transport())["결과"]       # 상한 없이 다시 부름 — 캐시로 이어서 끝까지
    assert second["멈춤"] == "" and second["후보_수"] == 5 and second["남은_회사_수"] == 0


def test_daily_cap(env, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_DAILY_CAP", "2")
    dc = _client(Transport())
    dc.get("company.json", {"corp_code": "00879020"})
    dc.get("company.json", {"corp_code": "00297934"})
    with pytest.raises(DartStop, match="오늘 호출 상한"):
        dc.get("company.json", {"corp_code": "00110884"})
    assert dc.get("company.json", {"corp_code": "00879020"})["status"] == "000"   # 캐시는 상한과 무관


def test_input_guards(env):
    with pytest.raises(ValueError):
        run(Transport(), listed="전부")
    r = run(Transport(), limit=10_000)["결과"]
    assert r["입력"]["limit"] == C.LIMIT_MAX


# ---------- 도구 등록·찾기 ----------
def test_tool_registered_and_findable(monkeypatch, tmp_path):
    from korean_tax_calc_mcp import server as S
    t = next(t for t in S.mcp._tool_manager.list_tools() if t.name == "kr_comparable_candidates")
    assert t.annotations.open_world_hint is True and t.annotations.read_only_hint is True
    d = t.description
    assert d.splitlines()[0].startswith("Korean comparable company candidates") and "언제:" in d and "입력:" in d and "DART_API_KEY" in d
    for p in t.parameters["properties"]:
        assert p in d, p
    top = lambda q: [c["도구"] for c in S.find_tool(query=q)["결과"]["후보"][:3]]
    assert "kr_comparable_candidates" in top("국내 비교기업 후보")
    assert "kr_comparable_candidates" in top("comparable companies korea dart filings")
    monkeypatch.delenv("DART_API_KEY", raising=False)
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path))
    r = S.kr_comparable_candidates(industry_codes=["4651"], years=[2024])
    assert "꺼짐" in r["결과"]["상태"]
