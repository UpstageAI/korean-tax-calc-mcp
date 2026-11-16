"""국내 비교기업 후보 프로필과 프로필 비교(순수 함수, 네트워크 없음). Claude 작성(2026-11-16).

- schema: 후보 프로필 표준 열, 값 상태(확보 / 불명-없음 / 불명-못찾음), 근거 형식
- compare: 분석대상 프로필 × 후보 프로필 → 항목별 가까움/다름/불명 + 종합(포함 후보 / 사람 확인 / 제외 후보)

공시 수집(OpenDART)과 매출 행 분류는 다음 단계(kr_comparable_candidates)에서 붙인다.
"""
from .schema import (PROFILE_FIELDS, MIX_CATEGORIES, STATUS_OK, STATUS_NONE, STATUS_UNKNOWN, STATUSES,
                     value, empty_profile, validate_profile)
from .compare import DEFAULT_RULES, ITEMS, compare_profile, compare_many, run_tool as profile_compare

__all__ = ["PROFILE_FIELDS", "MIX_CATEGORIES", "STATUS_OK", "STATUS_NONE", "STATUS_UNKNOWN", "STATUSES",
           "value", "empty_profile", "validate_profile", "DEFAULT_RULES", "ITEMS", "compare_profile", "compare_many", "profile_compare"]
