"""짧은 업종 코드 후보의 세분류 가르기(subclass) — 가짜 Solar로. Claude 작성(2026-11-20)."""
import json

import pytest

from korean_tax_calc_mcp.engine.kr_comparables import subclass as SC
from korean_tax_calc_mcp.engine.kr_comparables.schema import empty_profile, value
from test_kr_comparable_candidates import Transport, _gold_solar, env, run  # noqa: F401

DESC = "당사는 가상의 물건을 만들어 파는 회사입니다. 주력 제품은 가상 절삭기이며 매출의 대부분을 차지합니다."


def _prof(desc=DESC, rows=(("가상 절삭기 / 제품", 80), ("부품 / 상품", 20))):
    p = empty_profile(company_id="1", company_name="가상", listed=True, industry_code="292", year=2024, fs_basis="별도", rcept_no="r1")
    p["business_desc"] = value(desc, rcept_no="r1", account="사업의 개요") if desc else value(note="못 찾음")
    p["mix_coverage"] = value(1.0, rcept_no="r1")
    p["mix_coverage"]["evidence"]["rows"] = [{"label": l, "amount": a, "category": "goods"} for l, a in rows]
    return p


def _solar(code, quote, seen=None):
    def http(body, key):
        if seen is not None:
            seen.append(body)
        return {"choices": [{"message": {"content": json.dumps({"code": code, "quote": quote, "reason": "시험"}, ensure_ascii=False)}}]}
    return http


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "c"))


def test_options_are_siblings_at_input_depth():
    opts, rel = SC.options("292", ["2922", "4653"])
    assert rel == ["2922"] and {o["code"] for o in opts} >= {"2921", "2922", "2929"} and all(len(o["code"]) == 4 for o in opts)
    assert next(o for o in opts if o["code"] == "2922")["하위"]            # 하위 분류 이름을 붙여 보냄
    assert all(len(o["code"]) == 4 for o in SC.options("29", ["2922"])[0])   # 2자리 등록도 입력 자릿수로


def test_in_scope_keeps_with_verified_quote():
    seen = []
    r = SC.judge(_prof(), "292", ["2922"], "k" * 10, _solar("2922", "주력 제품은 가상 절삭기이며 매출의 대부분을 차지합니다.", seen), {})
    assert r["판정"] == SC.IN and r["세분류"]["code"] == "2922" and "절삭기" in r["근거_문장"]
    text = seen[0]["messages"][0]["content"]
    assert seen[0]["temperature"] == 0 and "가상 절삭기 / 제품 (80%)" in text and "80\n" not in text   # 비중만, 금액은 안 보냄


def test_other_subclass_reported_with_class_and_quote():
    r = SC.judge(_prof(), "292", ["2922"], "k" * 10, _solar("2929", "가상 절삭기 / 제품 (80%)"), {})   # 비중 꼬리표는 떼고 대조
    assert r["판정"] == SC.OTHER and r["세분류"]["code"] == "2929" and r["근거_문장"] == "가상 절삭기 / 제품"


@pytest.mark.parametrize("code,quote,why", [
    ("2922", "당사는 공작기계를 만드는 회사입니다.", "그대로 없음"),      # 지어낸 인용
    ("2922", "절삭기", "그대로 없음"),                                    # 너무 짧은 인용
    ("불명", "", "가를 수 없음"),
    ("해당없음", "", "어디에도 들지 않는다"),
    ("9999", "주력 제품은 가상 절삭기이며", "가를 수 없음"),              # 선택지에 없는 코드
])
def test_unverifiable_answers_are_unsure_not_dropped(code, quote, why):
    r = SC.judge(_prof(), "292", ["2922"], "k" * 10, _solar(code, quote), {})
    assert r["판정"] == SC.UNSURE and why in r["사유"] and r["근거_문장"] is None


def test_partial_quote_keeps_only_verified_pieces():
    q = "주력 제품은 가상 절삭기이며 매출의 대부분을 차지합니다. 세계 1위 회사입니다."
    r = SC.judge(_prof(), "292", ["2922"], "k" * 10, _solar("2922", q), {})
    assert r["판정"] == SC.IN and "세계 1위" not in r["근거_문장"] and "절삭기" in r["근거_문장"]


def test_no_key_no_text_and_failure_are_unsure():
    assert SC.judge(_prof(), "292", ["2922"], "", None, {})["판정"] == SC.UNSURE
    assert "못 찾음" in SC.judge(_prof(desc="", rows=()), "292", ["2922"], "k" * 10, _solar("2922", "x"), {})["사유"]
    def boom(body, key):
        raise ValueError("고장")
    st = {}
    r = SC.judge(_prof(), "292", ["2922"], "k" * 10, boom, st)
    assert r["판정"] == SC.UNSURE and "실패" in r["사유"] and st["solar_errors"]


def test_longer_input_than_option_is_unsure():
    r = SC.judge(_prof(), "292", ["2922", "29271"], "k" * 10, _solar("2927", "주력 제품은 가상 절삭기이며"), {})
    assert r["판정"] == SC.UNSURE and "더 세분" in r["사유"]


def test_same_request_is_cached(tmp_path):
    seen, st = [], {}
    for _ in range(2):
        SC.judge(_prof(), "292", ["2922"], "k" * 10, _solar("2922", "주력 제품은 가상 절삭기이며", seen), st)
    assert len(seen) == 1 and st["solar_cached"] == 1


def test_prompt_has_no_industry_or_company_names():
    assert not any(w in SC.PROMPT for w in ("화장품", "기계", "의약", "철강", "도매"))


# ---------- run()에 연결 ----------
def _sub_solar(code, quote):
    def http(body, key):
        if "한국표준산업분류" in body["messages"][0]["content"]:
            return {"choices": [{"message": {"content": json.dumps({"code": code, "quote": quote}, ensure_ascii=False)}}]}
        return _gold_solar(body, key)
    return http


def _desc(tr):
    r = run(tr, industry_codes=["4652"], listed="상장", short_code_subclass="끔", upstage_key="u" * 20, solar_http=_gold_solar)["결과"]
    return next(p for p in r["후보_프로필"] if p["industry_code"] == "465")["business_desc"]["value"]


def test_run_drops_other_subclass_and_lists_it(env):
    q = _desc(Transport())[:40]
    out = run(Transport(), industry_codes=["4652"], listed="상장", short_code_subclass="거름", upstage_key="u" * 20, solar_http=_sub_solar("4659", q))
    r = out["결과"]
    assert r["후보_수"] == 1 and r["업종_짧은코드_포함"] == []
    d = r["업종_짧은코드_다른세분류"]
    assert len(d) == 1 and d[0]["판정_세분류"]["code"] == "4659" and d[0]["근거_문장"] and d[0]["rcept_no"]
    assert r["입력"]["short_code_subclass"] == "거름" and any("다른 세분류 1개" in n for n in out["주의"])


def test_run_keeps_in_scope_and_unsure(env, monkeypatch, tmp_path):
    q = _desc(Transport())[:40]
    r = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_sub_solar("4652", q))["결과"]
    assert r["후보_수"] == 2 and r["업종_짧은코드_포함"][0]["판정"] == SC.IN and r["업종_짧은코드_다른세분류"] == []
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "other"))     # 같은 요청은 캐시 답을 쓰므로 캐시를 바꿔 다른 답을 받음
    r = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_sub_solar("4659", "원문에 없는 문장입니다 정말로"))["결과"]
    assert r["후보_수"] == 2 and len(r["업종_짧은코드_확인필요"]) == 1 and r["업종_짧은코드_다른세분류"] == []


def _same_candidates(a, b):
    return a["후보_수"] == b["후보_수"] and a["후보_행"] == b["후보_행"] and a["후보_프로필"] == b["후보_프로필"]


def _baseline():
    """세분류 판정을 끈 결과 — 0.69.0의 후보 수·후보 행·프로필과 같음."""
    return run(Transport(), industry_codes=["4652"], listed="상장", short_code_subclass="끔", upstage_key="u" * 20, solar_http=_gold_solar)["결과"]


def test_default_is_mark_only_and_candidates_unchanged(env):
    """기본값은 '표시만' — 다른 세분류로 판정돼도 후보 수·후보 행·프로필은 판정을 끈 것과 같고 판정 칸만 붙음."""
    q = _desc(Transport())[:40]
    base = _baseline()
    out = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_sub_solar("4659", q))
    r = out["결과"]
    assert r["입력"]["short_code_subclass"] == "표시만" and _same_candidates(r, base) and r["후보_수"] == 2
    assert len(r["업종_짧은코드_다른세분류"]) == 1 and r["업종_짧은코드_포함"][0]["판정"] == SC.OTHER
    ent = {k: v for k, v in r["업종_짧은코드_포함"][0].items() if k in base["업종_짧은코드_포함"][0]}
    assert ent == base["업종_짧은코드_포함"][0]                      # 종전 칸은 그대로, 판정 칸만 추가
    assert any("참고용" in n and "정확도가 크게 다르고" in n for n in out["주의"]) and any("빼지 않고" in n for n in out["주의"])
    r2 = run(Transport(), industry_codes=["4652"], listed="상장", short_code_subclass="표시만", upstage_key="u" * 20, solar_http=_sub_solar("4659", q))["결과"]
    assert _same_candidates(r2, r)


def test_default_keeps_candidates_without_key_or_on_solar_failure(env, monkeypatch, tmp_path):
    base = _baseline()
    no_key = run(Transport(), industry_codes=["4652"], listed="상장")["결과"]            # 키 없음(매출 분류도 규칙으로 바뀌므로 수와 회사만 비교)
    assert no_key["후보_수"] == base["후보_수"] and [p["company_id"] for p in no_key["후보_프로필"]] == [p["company_id"] for p in base["후보_프로필"]]
    assert len(no_key["업종_짧은코드_확인필요"]) == 1 and no_key["업종_짧은코드_다른세분류"] == []

    def failing(body, key):                                                              # 세분류 판정 호출만 실패
        if "한국표준산업분류" in body["messages"][0]["content"]:
            raise ValueError("고장")
        return _gold_solar(body, key)
    for mode in ("표시만", "거름"):
        monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / ("f_" + mode)))
        r = run(Transport(), industry_codes=["4652"], listed="상장", short_code_subclass=mode, upstage_key="u" * 20, solar_http=failing)["결과"]
        assert r["후보_수"] == base["후보_수"] and r["후보_행"] == base["후보_행"]
        assert r["업종_짧은코드_확인필요"][0]["사유"] == "Solar 호출 실패" and r["업종_짧은코드_다른세분류"] == []


def test_run_without_key_keeps_all_as_unsure(env):
    out = run(Transport(), industry_codes=["4652"], listed="상장")
    r = out["결과"]
    assert r["후보_수"] == 2 and len(r["업종_짧은코드_확인필요"]) == 1 and any("UPSTAGE_API_KEY가 없어" in n for n in out["주의"])


def test_run_keywords_keep_old_behaviour(env):
    calls = []
    def http(body, key):
        calls.append(body["messages"][0]["content"][:30])
        return _gold_solar(body, key)
    out = run(Transport(), industry_codes=["4652"], listed="상장", short_code_keywords=["셋톱박스"], upstage_key="u" * 20, solar_http=http)
    r = out["결과"]
    assert r["후보_수"] == 2 and r["업종_짧은코드_다른세분류"] == [] and "판정" not in r["업종_짧은코드_포함"][0]
    assert not any("한국표준산업분류" in c for c in calls) and "적용 안 함" in r["입력"]["short_code_subclass"]


def test_run_rejects_unknown_option(env):
    with pytest.raises(ValueError):
        run(Transport(), industry_codes=["4652"], short_code_subclass="아무거나")


def test_solar_cap_skips_call_and_marks_unsure(monkeypatch, tmp_path):
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path))
    calls = []
    def http(body, key):
        calls.append(1)
        return _solar("2922", "주력 제품은 가상 절삭기이며 매출의 대부분을 차지합니다.")(body, key)
    st = {"solar_cap": 0}
    r = SC.judge(_prof(), "292", ["2922"], "k" * 10, http, st)
    assert r["판정"] == SC.UNSURE and r["사유"] == SC.CAPPED and not calls                 # 상한 0 — 부르지 않고 확인 필요
    assert st["solar_capped"] == 1 and "solar_errors" not in st                            # 오류가 아니라 건너뜀으로 셈
    st2 = {"solar_cap": 1}
    assert SC.judge(_prof(), "292", ["2922"], "k" * 10, http, st2)["판정"] == SC.IN and len(calls) == 1
    assert SC.judge(_prof(), "292", ["2922"], "k" * 10, http, st2)["판정"] == SC.IN and len(calls) == 1   # 같은 요청은 캐시 — 상한에 안 걸림


def test_run_solar_cap_keeps_candidates_and_reports(env, monkeypatch, tmp_path):
    base = _baseline()
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "cap0"))
    out = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_gold_solar, max_solar_calls=0)
    r = out["결과"]
    assert r["후보_수"] == base["후보_수"] and [p["company_id"] for p in r["후보_프로필"]] == [p["company_id"] for p in base["후보_프로필"]]
    assert r["호출"]["Solar_실호출"] == 0 and r["호출"]["Solar_상한"] == 0 and r["호출"]["Solar_상한으로_건너뜀"] >= 1
    assert r["업종_짧은코드_확인필요"][0]["사유"] == SC.CAPPED and r["업종_짧은코드_다른세분류"] == []
    assert any("Solar 호출 상한(0회)" in n for n in out["주의"])
    monkeypatch.setenv("KR_COMPARABLES_CACHE_DIR", str(tmp_path / "dflt"))
    d = run(Transport(), industry_codes=["4652"], listed="상장", upstage_key="u" * 20, solar_http=_gold_solar)
    assert d["결과"]["호출"]["Solar_상한"] == 60 and d["결과"]["호출"]["Solar_상한으로_건너뜀"] == 0
    assert not any("Solar 호출 상한" in n for n in d["주의"])
