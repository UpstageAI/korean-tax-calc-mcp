"""Solar 호출 한 곳(solar_client) — 상한·캐시·재시도·키 가림이 옮긴 뒤에도 같은지, 그리고 AI 생성 표시. 가짜 Solar로(네트워크 없음). Claude 작성(2026-11-23)."""
import functools
import hashlib
import json
import os

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.engine.kr_comparables import candidates as C
from korean_tax_calc_mcp.engine.kr_comparables import solar_client as SOL
from korean_tax_calc_mcp.engine.kr_comparables import subclass as SUB
from korean_tax_calc_mcp.engine.kr_comparables.dart import DartClient
from test_kr_comparable_candidates import Transport, _gold_solar, env, run  # noqa: F401
from test_kr_comparables_subclass import _desc, _prof, _solar, _sub_solar

KEY = "k" * 10
BODY = SOL.user_body("안녕")
OK = {"choices": [{"message": {"content": '{"a": 1}'}}]}


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setattr(SOL, "_sleep", lambda s: None)
    return tmp_path / "c"


def _counting(reply=OK, fail=0, exc=TimeoutError):
    calls = []

    def http(body, key):
        calls.append(body)
        if len(calls) <= fail:
            raise exc("t")
        return reply
    return http, calls


# ---------- 상한 ----------
def test_set_cap_default_and_clamp():
    for n, want in ((None, 60), (0, 0), (7, 7), (-3, 0), (9999, 500)):
        st = {}
        assert SOL.set_cap(st, n) == want and st["solar_cap"] == want


def test_cap_zero_skips_without_calling(cache):
    http, calls = _counting()
    st = {"solar_cap": 0}
    assert SOL.call(BODY, KEY, http, st) == (None, SOL.CAPPED)
    assert not calls and st["solar_capped"] == 1 and "solar_errors" not in st and st.get("solar_calls", 0) == 0


def test_cap_counts_real_calls_not_cache(cache):
    http, calls = _counting()
    st = {"solar_cap": 1}
    assert SOL.call(BODY, KEY, http, st) == (OK, SOL.API)
    assert SOL.call(BODY, KEY, http, st) == (OK, SOL.CACHE)               # 같은 요청은 캐시 — 상한에 안 걸림
    assert SOL.call(SOL.user_body("다른 요청"), KEY, http, st) == (None, SOL.CAPPED)
    assert len(calls) == 1 and st == {"solar_cap": 1, "solar_calls": 1, "solar_cached": 1, "solar_capped": 1}


def test_retries_count_toward_cap(cache):
    http, calls = _counting(fail=2)
    st = {"solar_cap": 5}
    assert SOL.call(BODY, KEY, http, st) == (OK, SOL.API)
    assert len(calls) == 3 and st["solar_calls"] == 3 and st["solar_retries"] == 2
    http2, calls2 = _counting(fail=10)
    st2 = {"solar_cap": 2}
    d, src = SOL.call(SOL.user_body("x"), KEY, http2, st2)
    assert (d, src) == (None, SOL.ERROR) and len(calls2) == 4 and st2["solar_errors"]   # 재시도 중에는 상한을 보지 않음(종전과 같음)


def test_non_transient_error_not_retried_and_key_masked(cache):
    def bad(body, key):
        raise ValueError("boom " + key)
    st = {}
    assert SOL.call(BODY, KEY, bad, st) == (None, SOL.ERROR)
    assert st["solar_calls"] == 1 and KEY not in json.dumps(st) and "***" in st["solar_errors"][0]
    assert not os.listdir(os.path.join(cache, SOL.CACHE_SUBDIR))           # 실패는 캐시에 남기지 않음


def test_cache_file_name_unchanged(cache):
    """옮긴 뒤에도 캐시 파일 이름이 같아야 쌓아 둔 답을 그대로 씀 — 본문 키 순서까지 종전과 같게."""
    assert list(SOL.user_body("x")) == ["model", "messages", "temperature"]                      # 매출 분류
    assert list(SOL.user_body("x", temperature_first=True)) == ["model", "temperature", "messages"]  # 세분류 판정
    http, _ = _counting()
    SOL.call(BODY, KEY, http, {})
    want = "v2_" + hashlib.sha1(json.dumps({"model": "solar-pro4", "messages": [{"role": "user", "content": "안녕"}], "temperature": 0},
                                           ensure_ascii=False).encode()).hexdigest()[:16] + ".json"
    assert os.listdir(os.path.join(cache, "solar")) == [want]


def test_run_cap_still_applies_after_move(env):
    out = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_gold_solar, max_solar_calls=0)
    h = out["결과"]["호출"]
    assert h["Solar_실호출"] == 0 and h["Solar_상한"] == 0 and h["Solar_상한으로_건너뜀"] >= 1
    assert out["결과"]["업종_짧은코드_확인필요"][0]["사유"] == SUB.CAPPED
    assert SOL.AI_MARK_KEY not in out["결과"]["업종_짧은코드_확인필요"][0]                 # 부르지 않았으니 AI 표시 없음
    assert SOL.AI_MARK_KEY not in out                                                     # 이 실행엔 Solar가 낸 값이 없음


# ---------- AI 생성 표시 ----------
def test_judge_marks_only_solar_answers(cache):
    r = SUB.judge(_prof(), "292", ["2922"], KEY, _solar("2922", "주력 제품은 가상 절삭기이며 매출의 대부분을 차지합니다."), {})
    assert r["판정"] == SUB.IN and r[SOL.AI_MARK_KEY] == SOL.AI_MARK_SUBCLASS
    r = SUB.judge(_prof(desc="인용 확인용 설명입니다 길게"), "292", ["2922"], KEY, _solar("2929", "원문에 없는 문장입니다 정말로"), {})   # 인용 불일치도 모델 답에서 나옴
    assert r["판정"] == SUB.UNSURE and r[SOL.AI_MARK_KEY] == SOL.AI_MARK_SUBCLASS
    assert SOL.AI_MARK_KEY not in SUB.judge(_prof(), "292", ["2922"], "", None, {})                       # 키 없음
    assert SOL.AI_MARK_KEY not in SUB.judge(_prof(desc="상한 확인용 설명입니다 길게"), "292", ["2922"], KEY, _solar("2922", "x"), {"solar_cap": 0})   # 상한
    def boom(body, key):
        raise ValueError("x")
    assert SOL.AI_MARK_KEY not in SUB.judge(_prof(desc="실패 확인용 설명입니다 길게"), "292", ["2922"], KEY, boom, {})                     # 호출 실패
    def junk(body, key):
        return {"choices": [{"message": {"content": "답 없음"}}]}
    assert SOL.AI_MARK_KEY not in SUB.judge(_prof(desc="다른 설명입니다 아주 길게"), "292", ["2922"], KEY, junk, {})   # 답을 못 읽음


def test_run_labels_solar_values(env):
    q = _desc(Transport())[:40]
    out = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_sub_solar("4652", q))
    assert out[SOL.AI_MARK_KEY] == SOL.AI_GENERATED and out[SOL.AI_MARK_KEY_EN] == SOL.AI_GENERATED_EN
    r = out["결과"]
    assert r["업종_짧은코드_포함"][0][SOL.AI_MARK_KEY] == SOL.AI_MARK_SUBCLASS
    evs = [p["mix_coverage"]["evidence"] for p in r["후보_프로필"]]
    solar_ev = [e for e in evs if SOL.AI_MARK_KEY in e]
    assert solar_ev and all(e[SOL.AI_MARK_KEY] == SOL.AI_MARK_MIX for e in solar_ev)
    assert any(m.startswith("Solar") for m in r["매출_분류_방법"])


def test_run_without_key_has_no_label(env):
    out = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="")
    assert SOL.AI_MARK_KEY not in json.dumps(out, ensure_ascii=False)


def test_label_shape_matches_pdf_tools():
    """PDF 도구(_add_ai_mark)와 같은 칸 이름·같은 자리(도구 결과 맨 위)."""
    pdf = S._add_ai_mark({})
    assert set(pdf) == {SOL.AI_MARK_KEY, SOL.AI_MARK_KEY_EN} == set(SOL.add_ai_mark({}))


def test_tool_passes_label_through(env, monkeypatch):
    monkeypatch.setenv("UPSTAGE_API_KEY", "u" * 20)
    monkeypatch.setattr(C, "DartClient", functools.partial(DartClient, transport=Transport(), interval=0, sleep=lambda s: None))
    monkeypatch.setattr(SOL, "http", _gold_solar)
    out = S.kr_comparable_candidates(industry_codes=["46"], years=[2024], listed="둘 다", limit=10)
    assert out[SOL.AI_MARK_KEY] == SOL.AI_GENERATED and out[SOL.AI_MARK_KEY_EN] == SOL.AI_GENERATED_EN
