"""Solar(Upstage) 호출 한 곳 — 매출 행 분류(revenue_mix)와 짧은 코드 세분류 판정(subclass)이 함께 쓴다. Claude 작성(2026-11-23).

여기서만 하는 일: HTTP 호출(시간 제한 120초), 일시 오류 재시도(1·2·4초), 실행당 실제 호출 상한(stat['solar_cap']),
응답 캐시(캐시 폴더/solar/v2_<요청 sha1 앞 16자>.json — 같은 요청은 다시 부르지 않고 같은 답), 오류 기록(키 가림),
모델 답의 JSON 읽기, 그리고 Solar가 낸 값에 붙이는 'AI 생성 표시' 문구.
stat 칸(candidates 결과의 '호출'로 나감): solar_calls(실제 호출, 재시도 포함)·solar_cached·solar_capped·solar_retries·solar_errors.
"""
import hashlib
import json
import os
import re
import time
import urllib.request

from .dart import BACKOFF, RETRIES, cache_dir, mask, transient, _ssl_ctx

MODEL = "solar-pro4"
URL = "https://api.upstage.ai/v1/chat/completions"
TIMEOUT = 120
CACHE_SUBDIR, CACHE_PREFIX = "solar", "v2_"

CALLS_DEFAULT = 60      # 실행당 Solar 실제 호출 상한 기본값(매출 분류 + 세분류 판정) — 닿으면 멈추지 않고 그 뒤 호출만 건너뜀
CALLS_MAX = 500

_sleep = time.sleep   # 테스트에서 바꿔 끼움

# 호출 결과 출처 — call()이 돌려줌
API, CACHE, CAPPED, ERROR = "api", "cache", "capped", "error"

# AI 생성 표시 — PDF 도구(_add_ai_mark)와 같은 칸 이름
AI_MARK_KEY = "AI 생성 표시"
AI_MARK_KEY_EN = "AI generation notice"
AI_GENERATED = ("이 결과 가운데 'AI 생성 표시'가 붙은 항목(매출 행 분류, 짧은 업종 코드의 세분류 판정)은 생성형 AI(Upstage Solar Pro 4)가 수행했습니다. "
                "금액·비중은 코드가 원문 표에서 읽은 값으로 계산했습니다. 사람이 원문과 대조해 확인하세요.")
AI_GENERATED_EN = ("Items in this result carrying 'AI 생성 표시' (sales-row classification, sub-class judgment for short industry codes) were produced by "
                   "generative AI (Upstage Solar Pro 4). Amounts and shares are computed by code from the filing tables. Please verify against the original filings.")
AI_MARK_MIX = "매출 행 분류(rows의 category·reason) 가운데 reason이 '원문 매출유형'·'원문 계정명'·'차감 행'이 아닌 행은 생성형 AI(Upstage Solar Pro 4)가 분류 — 금액·비중은 코드 계산, 사람 확인"
AI_MARK_SUBCLASS = "세분류 판정(판정·판정_세분류·사유)은 생성형 AI(Upstage Solar Pro 4)가 수행 — 근거_문장은 원문에 글자 그대로 있는지 코드로 확인, 사람 확인"


def set_cap(stat, max_calls=None):
    """실행당 실제 호출 상한을 stat['solar_cap']에 둠(None이면 기본 60, 0~500으로 자름) → 상한. 캐시에서 읽는 것은 세지 않음."""
    cap = max(0, min(int(CALLS_DEFAULT if max_calls is None else max_calls), CALLS_MAX))
    stat["solar_cap"] = cap
    return cap


def user_body(content, temperature_first=False):
    """요청 본문. 키 순서도 캐시 파일 이름(sha1)에 들어가므로 호출하는 쪽마다 종전 순서를 지킨다."""
    msgs = [{"role": "user", "content": content}]
    if temperature_first:
        return {"model": MODEL, "temperature": 0, "messages": msgs}
    return {"model": MODEL, "messages": msgs, "temperature": 0}


def http(body, key):
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=_ssl_ctx()) as r:
        return json.load(r)


def _cache_file(body):
    d_dir = os.path.join(cache_dir(), CACHE_SUBDIR)
    os.makedirs(d_dir, exist_ok=True)
    return os.path.join(d_dir, CACHE_PREFIX + hashlib.sha1(json.dumps(body, ensure_ascii=False).encode()).hexdigest()[:16] + ".json")


def call(body, key, http_fn=None, stat=None):
    """Solar 한 번 부르기(캐시·일시 오류 재시도·호출 상한) → (응답 dict|None, 출처 API|CACHE|CAPPED|ERROR).
    상한은 stat['solar_cap'](실행당 실제 호출 수, 재시도 포함) — 닿으면 부르지 않고 (None, CAPPED), stat['solar_capped']에 건너뛴 수.
    실패하면 (None, ERROR)이고 오류는 stat['solar_errors']에 키를 가려 적음."""
    f = _cache_file(body)
    stat = stat if stat is not None else {}
    try:
        if os.path.exists(f):
            d = json.load(open(f, encoding="utf-8"))
            stat["solar_cached"] = stat.get("solar_cached", 0) + 1
            return d, CACHE
        if stat.get("solar_cap") is not None and stat.get("solar_calls", 0) >= stat["solar_cap"]:
            stat["solar_capped"] = stat.get("solar_capped", 0) + 1       # 상한에 닿음 — 부르지 않음(오류로 적지 않음, 다음 실행은 캐시로 이어감)
            return None, CAPPED
        d = None
        for attempt in range(1 + RETRIES):       # 일시 오류만 재시도(1·2·4초), 다 실패하면 아래 except
            stat["solar_calls"] = stat.get("solar_calls", 0) + 1
            try:
                d = (http_fn or http)(body, key)
                break
            except Exception as e:
                if not transient(e) or attempt == RETRIES:
                    raise
                stat["solar_retries"] = stat.get("solar_retries", 0) + 1
                _sleep(BACKOFF[attempt])
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False)
        return d, API
    except Exception as e:
        stat.setdefault("solar_errors", []).append(mask(f"{type(e).__name__}: {e}", key))
        return None, ERROR


def cached(body, key, http_fn=None, stat=None):
    """call()의 응답만 — 실패·상한이면 None."""
    return call(body, key, http_fn, stat)[0]


def reply_json(d):
    """모델 답(choices[0].message.content)에서 첫 '{'부터 마지막 '}'까지를 JSON으로 읽음. 못 읽으면 예외."""
    return json.loads(re.search(r"\{.*\}", d["choices"][0]["message"]["content"], re.S).group(0))


def add_ai_mark(result):
    """결과 맨 위에 AI 생성 표시(한·영) — PDF 도구의 _add_ai_mark와 같은 칸."""
    result[AI_MARK_KEY] = AI_GENERATED
    result[AI_MARK_KEY_EN] = AI_GENERATED_EN
    return result
