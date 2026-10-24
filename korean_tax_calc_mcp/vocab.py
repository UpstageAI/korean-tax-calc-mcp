"""세법 사실관계 어휘(facts_vocab.json) 로딩·조회.

법령 분류가 아니라 사실관계를 부르는 이름 체계. 계산기(kind·source·evidence)와
주장 대조 도구가 같이 읽는다.
"""
from __future__ import annotations

import json
from pathlib import Path

_CACHE: dict | None = None


def load() -> dict:
    """facts_vocab.json을 읽어 캐시한다(한 번만 읽음)."""
    global _CACHE
    if _CACHE is None:
        path = Path(__file__).parent / "data" / "facts_vocab.json"
        with open(path, encoding="utf-8") as f:
            _CACHE = json.load(f)
    return _CACHE


def _year_0101(year: int) -> int:
    """연도 → YYYY0101 키(부터 비교용)."""
    return year * 10_000 + 101


def _year_1231(year: int) -> int:
    """연도 → YYYY1231 키(까지 비교용)."""
    return year * 10_000 + 1231


def items_for(tool_name: str, field: str) -> list[dict]:
    """도구·필드(kind/source/evidence)에 매핑된 항목 목록.

    각 항목은 이름·뜻·필요한사실·별칭·매핑값을 포함한다.
    매핑값은 도구 필드가 "evidence=값" 형태일 때 그 값, "kind" 또는 "kind+source"
    형태일 때 항목 이름을 쓴다.
    """
    result: list[dict] = []
    for item in load()["항목"]:
        tools = item.get("도구", {})
        if tool_name not in tools:
            continue
        tool_field = tools[tool_name]

        if "=" in tool_field:
            prefix, value = tool_field.split("=", 1)
            if prefix == field:
                entry = dict(item)
                entry["_매핑값"] = value
                result.append(entry)
        elif field in tool_field.split("+"):
            entry = dict(item)
            entry["_매핑값"] = item["이름"]
            result.append(entry)
        elif tool_field == field:
            entry = dict(item)
            entry["_매핑값"] = item["이름"]
            result.append(entry)

    return result


def resolve(name: str, tool_name: str | None = None, year: int | None = None) -> dict:
    """입력 이름을 정식 이름으로 해결한다. 별칭도 받아들인다.

    반환값:
      - {"이름": canonical_name}  (별칭이 없거나 year 제한으로 걸러진 경우)
      - {"이름": canonical_name, "별칭": [alias, ...]}  (별칭이 있는 경우)
      - {"이름": canonical_name, "안내": "..."}

   Year가 주어지면 그 해에 유효한 별칭만 반환값에 포함한다.
    Year가 별칭 기간 밖이면 안내 문구를 함께 돌려준다.
    """
    name = name.strip()
    data = load()

    # 1. 정식 이름 일치 우선
    for item in data["항목"]:
        if item["이름"] == name:
            aliases: list[str] = []
            for alias in item.get("별칭", []):
                alias_name, from_date, to_date = alias
                if year is None:
                    aliases.append(alias_name)
                else:
                    ykey = _year_key(year)
                    from_ok = from_date is None or ykey >= int(from_date)
                    to_ok = to_date is None or ykey <= int(to_date)
                    if from_ok and to_ok:
                        aliases.append(alias_name)
            if aliases:
                return {"이름": name, "별칭": aliases}
            return {"이름": name}

    # 2. 별칭으로 찾기 (tool_name 힌트 있으면 그 도구 항목만)
    for item in data["항목"]:
        tools = item.get("도구", {})
        if tool_name is not None and tool_name not in tools:
            continue

        for alias in item.get("별칭", []):
            alias_name, from_date, to_date = alias
            if alias_name == name:
                if year is not None:
                    ykey = _year_key(year)
                    from_ok = from_date is None or ykey >= int(from_date)
                    to_ok = to_date is None or ykey <= int(to_date)
                    if not (from_ok and to_ok):
                        return {
                            "이름": item["이름"],
                            "안내": (
                                f"'{name}'은(는) "
                                f"{from_date or '이전'}~{to_date or '현재'} 기간 별칭입니다"
                            ),
                        }
                return {"이름": item["이름"]}

    # 3. 찾지 못함 — 입력 그대로 반환(호출측이 처리)
    return {"이름": name}


def rule(name: str, year: int) -> dict:
    """해당 연도(사업연도·귀속연도)에 맞는 판단 규칙을 반환한다.

    항목의 기본 판단 에 그해 적용 블록의 판단 을 덮어쓴 dict.
    부터 ≤ year0101 이고 까지 ≥ year1231 또는 까지가 null 인 적용 블록을 쓴다.
    """
    data = load()
    resolved = resolve(name)
    name = resolved["이름"]

    for item in data["항목"]:
        if item["이름"] == name:
            ykey_0101 = _year_0101(year)
            ykey_1231 = _year_1231(year)
            result = dict(item.get("판단", {}))

            for 적용 in item.get("적용", []):
                from_date = 적용.get("부터")
                to_date = 적용.get("까지")

                if from_date is not None and ykey_0101 < int(from_date):
                    continue
                if to_date is not None and ykey_1231 > int(to_date):
                    continue

                # 이 기간 적용 — 판단을 덮어씀
                period_judge = 적용.get("판단", {})
                result.update(period_judge)

            return result

    return {}


def rule_on(name: str, yyyymmdd: int) -> dict:
    """특정 기준일(YYYYMMDD 정수)에 맞는 판단 규칙을 반환한다.

    항목의 기본 판단 에 그날 적용 블록(부터 <= yyyymmdd <= 까지)의 판단 을 덮어쓴 dict.
    까지가 null이면 그날까지 적용 중이면 포함.
    """
    data = load()
    resolved = resolve(name)
    name = resolved["이름"]

    for item in data["항목"]:
        if item["이름"] == name:
            result = dict(item.get("판단", {}))

            for 적용 in item.get("적용", []):
                from_date = 적용.get("부터")
                to_date = 적용.get("까지")

                if from_date is not None and yyyymmdd < int(from_date):
                    continue
                if to_date is not None and yyyymmdd > int(to_date):
                    continue

                period_judge = 적용.get("판단", {})
                result.update(period_judge)

            return result

    return {}


def basis(name: str, year: int) -> list:
    """해당 연도에 맞는 근거 목록. 적용 블록의 근거를 우선하고 없으면 기본 근거."""
    data = load()
    resolved = resolve(name)
    name = resolved["이름"]

    for item in data["항목"]:
        if item["이름"] == name:
            ykey_0101 = _year_0101(year)
            ykey_1231 = _year_1231(year)

            for 적용 in item.get("적용", []):
                from_date = 적용.get("부터")
                to_date = 적용.get("까지")

                if from_date is not None and ykey_0101 < int(from_date):
                    continue
                if to_date is not None and ykey_1231 > int(to_date):
                    continue

                period_basis = 적용.get("근거")
                if period_basis:
                    return period_basis

            return item.get("근거", [])

    return []


# 차가감소득금액 집계 도구 — 항목 종류별 방향·소득처분·근거 사전
# 키: 종류(도구 inputs items[].종류 값), 값: {방향, 소득처분, 근거}
INCOME_ADJUSTMENT_KINDS = {
    "법인세비용":               {"방향": "가산", "소득처분": "기타사외유출", "근거": "법 제21조1호"},
    "법인지방소득세":            {"방향": "가산", "소득처분": "기타사외유출", "근거": "법 제21조1호"},
    "벌금·과태료·가산세":       {"방향": "가산", "소득처분": "기타사외유출", "근거": "법 제21조3호"},
    "환급금이자":               {"방향": "차감", "소득처분": "기타",          "근거": "법 제18조4호"},
    "자기주식처분이익(자본잉여금)": {"방향": "가산", "소득처분": "기타",          "근거": "법 제15조①·영 제11조2호의2"},
    "미수이자(원천징수대상)":     {"방향": "차감", "소득처분": "△유보",        "근거": "영 제70조①1호"},
    "비지정기부금":             {"방향": "가산", "소득처분": "기타사외유출", "근거": "법 제24조"},
    "기업업무추진비 한도초과":    {"방향": "가산", "소득처분": "기타사외유출", "근거": "법 제25조"},
    "감가상각비 한도초과":       {"방향": "가산", "소득처분": "유보",          "근거": "법 제23조"},
    "업무무관 지급이자":        {"방향": "가산", "소득처분": "기타사외유출", "근거": "법 제28조"},
    "수입배당금 익금불산입":     {"방향": "차감", "소득처분": "기타",          "근거": "법 제18조의2"},
    "이월결손금 보전 자산수증이익": {"방향": "차감", "소득처분": "기타",          "근거": "법 제18조6호"},
    "사업용 재산세":            {"방향": "없음", "소득처분": "—",             "근거": "법 제19조(손금)"},
    "기부금 한도초과":          {"방향": "차가감 이후", "소득처분": "기타사외유출", "근거": "법 제24조"},
}
