"""엔진 공통 예외 — 연도표 없는 해는 추정 계산하지 않는다(서버 _guard가 {"error", "주의"}로 돌려줌)."""


class NoYearTable(ValueError):
    """연도표 범위 밖 연도·과세기간 — 계산하지 않음(추정 금지). calc_cit·calc_income·calc_vat가 같은 클래스를 쓴다."""
