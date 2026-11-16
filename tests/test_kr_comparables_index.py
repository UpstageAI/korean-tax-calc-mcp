"""회사 색인·비상장 모집단(하루 단위) — 네트워크 없음. Claude 작성(2026-11-17).
- 한 달 공시가 50쪽(5,000건)을 넘어도 하루씩 쪼개 모든 쪽을 받으므로 빠지는 회사가 없다
- 기업개황을 색인 파일에 쌓고, 다음 실행은 색인으로 업종을 먼저 걸러 업종이 맞는 회사만 재무를 부른다
- build_index_only: 재무 없이 색인만, 상한에 닿으면 '색인 n/N — 이어서'
- 사업부문표 손실 검사: 매출·비중 표만 대상(종속회사 지분율·요약재무 표 제외)"""
import io
import json
import os
import re
import urllib.parse
import zipfile

import pytest

from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import statements as ST
from korean_tax_calc_mcp.engine.kr_comparables.dart import DartClient
from korean_tax_calc_mcp.engine.kr_comparables.index import CorpIndex

KEY = "k" * 40
DAYS = [f"202503{d:02d}" for d in range(1, 32)]
PER_DAY = 230                                     # 31일 × 230 = 7,130건 — 한 번에 받으면 72쪽(50쪽 상한을 넘음)


def _filings():
    out = []
    for di, day in enumerate(DAYS):
        for j in range(PER_DAY):
            n = di * PER_DAY + j
            out.append({"corp_code": f"9{n:07d}", "corp_name": f"테스트회사{n}", "report_nm": "감사보고서 (2024.12)", "rcept_dt": day, "rcept_no": f"{day}{n:06d}"})
    return out


FILINGS = _filings()


def _industry(code):
    n = int(code[1:])
    return "46510" if n % 50 == 0 else ("10101" if n % 2 else "62010")     # 50곳 중 1곳만 도매(4651)


def _zip(name, data):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, data)
    return b.getvalue()


class Fake:
    def __init__(self, company_ok=True):
        self.urls, self.company_ok = [], company_ok

    def __call__(self, url, timeout=60):
        self.urls.append(url)
        u = urllib.parse.urlparse(url)
        ep = u.path.rsplit("/", 1)[-1]
        q = dict(urllib.parse.parse_qsl(u.query))
        J = lambda d: json.dumps(d, ensure_ascii=False).encode()
        if ep == "corpCode.xml":
            return _zip("CORPCODE.xml", "<?xml version='1.0' encoding='UTF-8'?><result></result>")
        if ep == "list.json" and "corp_code" not in q:
            sel = [f for f in FILINGS if q["bgn_de"] <= f["rcept_dt"] <= q["end_de"]]
            pc, pg = int(q["page_count"]), int(q["page_no"])
            if not sel:
                return J({"status": "013", "message": "조회된 데이타가 없습니다."})
            tp = -(-len(sel) // pc)
            return J({"status": "000", "total_count": len(sel), "total_page": tp, "page_no": pg, "list": sel[(pg - 1) * pc: pg * pc]})
        if ep == "company.json":
            assert self.company_ok, "색인이 있으면 기업개황을 다시 부르지 않아야 함"
            c = q["corp_code"]
            return J({"status": "000", "corp_code": c, "corp_name": f"테스트회사{int(c[1:])}", "corp_cls": "E", "induty_code": _industry(c), "acc_mt": "12"})
        if ep == "list.json":                       # 회사별 감사보고서 목록 — 이 테스트에선 없음
            return J({"status": "013", "list": []})
        raise AssertionError("부르면 안 되는 요청: " + ep)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DART_API_KEY", KEY)
    monkeypatch.setenv("KR_COMPARABLES_DAILY_CAP", "100000")
    return tmp_path


def _client(tr, **kw):
    return DartClient(key=KEY, transport=tr, interval=0, sleep=lambda s: None, **kw)


def test_pool_by_day_misses_nothing(env):
    tr = Fake()
    pool = CorpIndex().pool(_client(tr, max_calls=10_000), "20250301", "20250331")
    assert len(pool) == len(FILINGS) == 7130 and len({p["corp_code"] for p in pool}) == 7130   # 누락 0
    qs = [dict(urllib.parse.parse_qsl(urllib.parse.urlparse(u).query)) for u in tr.urls]
    assert all(q["bgn_de"] == q["end_de"] for q in qs)                                         # 하루씩
    assert max(int(q["page_no"]) for q in qs) == 3 and len(qs) == 31 * 3
    assert -(-len(FILINGS) // 100) > 50                                                        # 한 번에 받으면 50쪽 상한을 넘는 규모


def test_pool_days_recorded_and_reused(env):
    IX = CorpIndex()
    IX.pool(_client(Fake(), max_calls=10_000), "20250301", "20250310")
    IX.save()
    tr = Fake()
    pool = CorpIndex().pool(_client(tr, max_calls=10_000), "20250301", "20250310")   # 새 객체 — 파일에서 읽음
    assert len(pool) == 10 * PER_DAY and tr.urls == []


def test_window_guard(env):
    with pytest.raises(ValueError):
        CorpIndex().pool(_client(Fake()), "20250301", "20250701")


def test_build_index_only_then_filter_by_index(env):
    r = C.run(industry_codes=["4651"], years=[2024], listed="비상장", client=_client(Fake(), max_calls=10_000), build_index_only=True)["결과"]
    ix = r["색인"]
    assert r["후보_수"] == 0 and ix["완료"] is True and ix["모집단_색인"] == "7130/7130" and ix["버전"] == 1 and ix["갱신"]
    assert ix["비상장_모집단_일수"] == 31
    # 다음 실행: 기업개황은 하나도 부르지 않고(색인 사용), 업종이 맞는 회사(7130/50=143)만 재무 조회로 넘어간다
    tr = Fake(company_ok=False)
    r2 = C.run(industry_codes=["4651"], years=[2024], listed="비상장", client=_client(tr, max_calls=10_000), limit=100)["결과"]
    eps = [urllib.parse.urlparse(u).path.rsplit("/", 1)[-1] for u in tr.urls]
    qs = [dict(urllib.parse.parse_qsl(urllib.parse.urlparse(u).query)) for u in tr.urls]
    assert "company.json" not in eps
    asked = {q["corp_code"] for q in qs if "corp_code" in q}
    assert asked and all(_industry(c) == "46510" for c in asked) and len(asked) == 143
    assert r2["색인"]["완료"] is True


def test_build_index_resume_after_cap(env):
    r = C.run(industry_codes=["4651"], years=[2024], listed="비상장", client=_client(Fake(), max_calls=500), build_index_only=True)["결과"]
    n, N = map(int, r["색인"]["모집단_색인"].split("/"))
    assert r["멈춤"] and n < N == 7130 and "이어서" in r["색인"]["안내"] and r["남은_회사_수"] == N - n
    r = C.run(industry_codes=["4651"], years=[2024], listed="비상장", client=_client(Fake(), max_calls=10_000), build_index_only=True)["결과"]
    assert r["멈춤"] == "" and r["색인"]["완료"] is True


def test_daily_cap_respected_during_index(env, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_DAILY_CAP", "120")
    r = C.run(industry_codes=["4651"], years=[2024], listed="비상장", client=_client(Fake(), max_calls=10_000), build_index_only=True)["결과"]
    assert "오늘 호출 상한" in r["멈춤"] and r["호출"]["OpenDART_실호출"] == 120


# ---------- 사업부문표 손실 검사: 매출·비중 표만 ----------
FX = os.path.join(os.path.dirname(__file__), "data", "kr_comparables_fixtures")


def _sec(rc):
    s = open(os.path.join(FX, f"overview_{rc}.xml"), encoding="utf-8").read()
    a, b, t = next(x for x in ST.title_sections(s) if re.match(r"^\s*1\s*\.\s*(\([^)]*\))?\s*사업의\s*개요", x[2]))
    return s, s[a:b]


def test_subsidiary_ownership_tables_not_checked():
    s, sec = _sec("20250320000926")                  # 온타이드 — 종속회사 지분율·요약재무 표뿐
    assert C._segment_rows(sec) == [] and C._overview(s)["problems"] == []


@pytest.mark.parametrize("rc,label,amount", [
    ("20250312000813", "IT제품 판매", "216,364"),    # 제이씨현시스템
    ("20250319000886", "제조", "103,702"),            # 한글과컴퓨터 제조 부문
])
def test_segment_table_loss_still_caught(rc, label, amount):
    s, sec = _sec(rc)
    seg = C._segment_rows(sec)
    assert (label, amount) in seg or any(lab.startswith(label) and num == amount for lab, num in seg)
    ov = C._overview(s)
    assert ov["problems"] == []
    lost = "\n".join(line for line in ov["ctx"].split("\n") if amount not in line)
    assert any("사업부문표 손실" in x for x in C.overview_problems(lost, ov["raw"], "", seg))
