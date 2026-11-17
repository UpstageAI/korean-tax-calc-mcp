"""한국표준산업분류(KSIC 11차) 찾아보기 — data/ksic.json(통계청 고시 제2024-203호 해설서에서 tools/build_ksic.py로 만듦).

판단 없음: 코드 ↔ 이름, 상위·하위 단계, 10차 → 11차 연계(구·신 연계표)만. OpenDART 기업개황의 업종 코드는 11차를 씀
(2026-11-17 색인 5자리 3,597개 대조: 11차에만 있는 코드 99곳, 10차에만 있는 코드 0곳). Claude 작성(2026-11-17).
"""
import json
import os
import re
from functools import lru_cache

_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "ksic.json")
LEVELS = ("대분류", "중분류", "소분류", "세분류", "세세분류")


@lru_cache(maxsize=1)
def data():
    d = json.load(open(_PATH, encoding="utf-8"))
    d["_by"] = {it["code"]: it for it in d["items"]}
    return d


def source():
    return data()["source"]


def item(code):
    return data()["_by"].get(str(code).strip().upper())


def parents(code):
    """'20423' → [C 제조업, 20, 204, 2042] (숫자 코드만)."""
    code = str(code)
    if not code.isdigit():
        return []
    it = item(code)
    out = [item(it["section"])] if it else []
    out += [item(code[:n]) for n in range(2, len(code)) if item(code[:n])]
    return [{"code": p["code"], "name": p["name"], "level": p["level"]} for p in out if p]


def children(code, leaf_only=False):
    code = str(code)
    by = data()["_by"]
    if not code.isdigit():   # 대분류 문자
        kids = [it for it in by.values() if it["section"] == code and it["code"] != code]
    else:
        kids = [it for c, it in by.items() if c.isdigit() and c.startswith(code) and c != code]
    if leaf_only:
        kids = [it for it in kids if it["level"] == "세세분류"]
    return [{"code": it["code"], "name": it["name"], "level": it["level"]} for it in sorted(kids, key=lambda x: x["code"])]


def from_v10(code):
    """10차 세세분류 코드가 11차에서 바뀌었으면 11차 코드 목록, 아니면 None(같은 코드 그대로)."""
    return data()["links_10_to_11"]["changed"].get(str(code))


def search(query, level=None, limit=30):
    """이름에 낱말이 모두 들어 있는 항목(띄어쓰기로 여러 낱말). 세세분류부터."""
    words = [w for w in re.split(r"\s+", str(query).strip()) if w]
    if not words:
        return []
    hits = [it for it in data()["items"] if all(w in it["name"] for w in words) and (level is None or it["level"] == level)]
    hits.sort(key=lambda it: (-LEVELS.index(it["level"]), it["code"]))
    return [{"code": it["code"], "name": it["name"], "level": it["level"]} for it in hits[:limit]]


def describe(code):
    """입력 코드 하나를 풀어 씀 — 11차에 있으면 이름·단계·상위, 10차 코드면 11차 연계, 없으면 None."""
    c = str(code).strip().upper().lstrip("C") if str(code).strip().upper() != "C" else "C"
    it = item(c)
    if it:
        return {"code": c, "name": it["name"], "level": it["level"], "상위": parents(c), "세세분류_수": len(children(c, leaf_only=True)) if it["level"] != "세세분류" else 1}
    new = from_v10(c)
    if new:
        return {"code": c, "name": None, "level": "10차 코드", "11차": [{"code": n, "name": item(n)["name"]} for n in new if item(n)]}
    return None
