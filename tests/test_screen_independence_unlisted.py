"""tp_comparable_screen·kr_comparable_candidates — 독립성 자료가 없는 후보(비상장)를 '통과'로 내지 않음. 가상 회사. Claude 작성(2026-11-20).
배경: 비상장은 최대주주 지분율이 후보 행에 없어 S1a·S1b가 0%로 계산돼 전부 통과했음."""
from korean_tax_calc_mcp.engine import calc_tp_screen as T
from korean_tax_calc_mcp.engine.kr_comparables import candidates as C

YEARS = [2022, 2023, 2024]


def _rows(cid, name, om=0.05, **extra):
    return [{"company_id": cid, "company_name": name, "country": "KR", "industry_code": "46539", "currency": "KRW", "year": y,
             "revenue": 1000, "operating_profit": 1000 * om, "total_assets": 800, **extra} for y in YEARS]


def _tp():
    return {"name": "분석대상", "is_resident": True, "years": {y: {"revenue": 100, "operating_profit": 3} for y in YEARS}}


def run(rows, screens=None):
    return T.comparable_screen(rows=rows, tested_party=_tp(), analysis_years=YEARS, tested_year=2024, screens=screens,
                               multi_year_reason={"code": 1, "text": "경기 변동"}, search_log={"db": "가상"})


def _mx(r):
    return {m["company_id"]: m for m in r["탈락_매트릭스"]}


BASE = (_rows("A", "가나", 0.04, max_shareholder_pct=10) + _rows("B", "다라", 0.05, max_shareholder_pct=20)
        + _rows("C", "마바", 0.06, max_shareholder_pct=30))


def test_no_shareholder_data_is_skipped_not_passed():
    r = run(BASE + _rows("U", "사아", 0.07), {"independence_pct": 25})
    m = _mx(r)
    assert m["U"]["S1a"].startswith("건너뜀") and "자료 없음" in m["U"]["S1a"]
    assert m["U"]["S1b"].startswith("건너뜀") and "자료 없음" in m["U"]["S1b"]
    assert m["U"]["최종"] == "선정"                                   # 자료가 없다는 이유로 떨어뜨리지 않음
    assert any("독립성 자료 없는 후보 1곳" in w for w in r["경고"])


def test_parent_statement_without_shareholder_data_needs_review():
    note = "지배기업: 지배기업 가상홀딩스 AG"
    r = run(BASE + _rows("P", "자차", 0.07, control_note=note), {"independence_pct": 25})
    m = _mx(r)
    assert m["P"]["S1a"].startswith("검토 필요") and "가상홀딩스" in m["P"]["S1a"]
    assert m["P"]["최종"] == "선정"                                   # 탈락이 아니라 사람 확인
    who = [x for x in r["결과"]["사람_확인"] if x["company_id"] == "P"]
    assert who and "가상홀딩스" in who[0]["사유"]


def test_rows_with_shareholder_data_are_unchanged():
    """지분율이 있는 후보는 종전 그대로 — control_note가 있어도 지분율로 판정."""
    a = run(BASE + _rows("L", "카타", 0.07, max_shareholder_pct=30), {"independence_pct": 25})
    b = run(BASE + _rows("L", "카타", 0.07, max_shareholder_pct=30, control_note="지배기업: 지배기업 가상홀딩스"), {"independence_pct": 25})
    assert _mx(a) == _mx(b) and a["결과"]["범위"] == b["결과"]["범위"]
    assert _mx(a)["A"]["S1a"] == "통과" and _mx(a)["L"]["S1b"].startswith("탈락")
    assert not any("독립성 자료 없는" in w for w in a["경고"])


def test_database_independence_indicator_counts_as_data():
    """유료 DB 독립성 지표가 있으면 지분율이 없어도 종전처럼 지표로 판정."""
    sc = {"independence_bvd_reject": ["C", "D"]}
    r = run(BASE + _rows("X", "파하", 0.07, bvd_independence="A") + _rows("Y", "거너", 0.08, bvd_independence="D"), sc)
    m = _mx(r)
    assert m["X"]["S1a"] == "통과" and m["X"]["S1b"] == "통과" and m["Y"]["S1b"].startswith("탈락")
    assert not any("독립성 자료 없는" in w for w in r["경고"])


def test_control_note_from_profile_signals():
    sig = [{"kind": "자금 대여·보증", "sentence": "단기대여금 100"}, {"kind": "지배기업", "sentence": "지배기업 가상홀딩스 AG"},
           {"kind": "기업집단 계열", "sentence": "가상그룹 계열회사"}, {"kind": "유의적 영향력", "sentence": "유의적 영향력 (주)가상"}]
    note = C.control_note(sig)
    assert note.startswith("지배기업: 지배기업 가상홀딩스 AG") and "기업집단 계열: 가상그룹 계열회사" in note
    assert "대여" not in note and "유의적" not in note
    assert C.control_note([{"kind": "자금 대여·보증", "sentence": "x"}]) is None and C.control_note(None) is None and C.control_note([]) is None
    assert "control_note" in C.CANDIDATE_COLS
