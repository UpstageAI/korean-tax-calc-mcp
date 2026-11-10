"""실사용 점검에서 미뤄 둔 결함 — 연도별 조문·용어, 업종 표기, 표 칸, 설명·스키마 일치, 직접 호출, 대손 제외 채권."""
import asyncio
import json

import pytest

from korean_tax_calc_mcp import server as S
from korean_tax_calc_mcp.server import mcp
from tests._helpers import call as c


TC = {"equity": 1_000_000_000, "borrowings": 3_000_000_000, "total_interest": 150_000_000}


# ── 과소자본: 적용 연도의 조문 번호(국조법 2021.1.1. 전부개정) ─────────────────
def test_thin_cap_cites_article_in_force():
    old = c("thin_capitalization", dict(TC, year=2018))
    assert "제14조" in old["근거"] and "제22조" not in old["근거"], old["근거"]
    assert "제14조" in old["결과"]["근거"] and "제22조" not in old["결과"]["근거"]
    new = c("thin_capitalization", dict(TC, year=2025))
    assert "제22조" in new["근거"] and "제14조" not in new["근거"], new["근거"]
    assert "시행령 제34조" not in new["근거"]          # 시행령 제34조는 통합기업보고서 — 과소자본은 제46조~제50조
    assert "제46조" in new["근거"] and "제24조" in old["근거"]
    # 배당 처분 원천징수 재계산 근거도 그해 조문
    r = c("thin_capitalization", dict(TC, year=2019, recipient_residence_country="미국", dividend_treaty_rate=0.15))
    assert "국조법 제14조" in r["결과"]["원천징수 재계산"]["근거"]


# ── 간이과세자: 법령 표의 업종 이름·흔한 표기 ─────────────────────────────────
LEDGER = {"공급": [{"항목": "카드매출", "금액": 50_000_000}], "매입": []}


@pytest.mark.parametrize("bt,rate", [("그 밖의 서비스업", 0.3), ("운수 및 창고업", 0.3), ("운수업", 0.3),
                                     ("금융 및 보험 관련 서비스업", 0.4), ("전문·과학 및 기술서비스업", 0.4),
                                     ("농업ㆍ임업 및 어업", 0.2), ("재생용 재료수집 및 판매업", 0.15), ("소매업", 0.15)])
def test_simplified_vat_accepts_statutory_names(bt, rate):
    r = S.simplified_vat_return(year=2025, business_type=bt, ledger=LEDGER)
    assert "error" not in r, r
    assert r["계산"]["부가가치율"] == rate


def test_simplified_vat_unknown_type_lists_allowed():
    r = S.simplified_vat_return(year=2025, business_type="우주관광업", ledger=LEDGER)
    assert "error" in r and "그밖의서비스업" in r["허용값"]


# ── 의제매입세액: 비율은 '비율' 칸, '금액' 칸은 원 단위만 ──────────────────────
def test_deemed_input_steps_ratio_column():
    r = S.vat_deemed_input_credit(period="2026-1", industry="제조", purchase_total=100_000_000, freight_included=6_000_000,
                                  used_taxable=70_000_000, used_exempt=15_000_000, ending_inventory_common=10_000_000,
                                  taxable_supply=280_000_000, exempt_supply=120_000_000, individual=False, sme=False)
    steps = r["결과"]["단계별_계산"]
    for s in steps:
        if "금액" in s:
            assert isinstance(s["금액"], int) and not isinstance(s["금액"], bool), s
    by = {s["항목"]: s for s in steps}
    assert by["운반비 제외 비율"]["비율"] == pytest.approx(0.06)
    assert by["운송비 제외 계수 (1 − 운반비 비율)"]["비율"] == pytest.approx(0.94)
    assert any(k.startswith("공제율") and "비율" in v for k, v in by.items())


# ── 기업업무추진비: 2024.1.1. 이후 사업연도는 새 이름 ─────────────────────────
ENT_LEDGER = [{"항목": "거래처 식대", "금액": 30_000_000}, {"항목": "골프", "금액": 5_000_000, "증빙": "없음"},
              {"항목": "공연", "금액": 2_000_000, "성격": "문화"}]


def test_entertainment_term_by_year():
    new = S.entertainment_limit(year=2025, sme=True, general_revenue=1_000_000_000, expensed=50_000_000)
    assert "세무상 기업업무추진비" in new["결과"] and "접대비" not in json.dumps(new, ensure_ascii=False)
    old = S.entertainment_limit(year=2023, sme=True, general_revenue=1_000_000_000, expensed=50_000_000)
    assert "세무상 접대비" in old["결과"]
    a = S.entertainment_adjustment(year=2025, sme=True, ledger=ENT_LEDGER, revenue={"매출액": 5_000_000_000})
    t = json.dumps({k: a[k] for k in ("판단", "계산식_입력", "결과", "근거") if k in a}, ensure_ascii=False)
    assert "접대비" not in t, [x for x in t.split('"') if "접대비" in x]
    b = S.entertainment_adjustment(year=2023, sme=True, ledger=ENT_LEDGER, revenue={"매출액": 5_000_000_000})
    assert "문화접대비" in json.dumps(b["판단"], ensure_ascii=False)


# ── 도구 설명과 스키마 일치 ─────────────────────────────────────────────────
@pytest.mark.parametrize("name", ["entertainment_limit", "entertainment_adjustment", "simplified_vat_return", "special_tax_credit"])
def test_description_names_every_parameter(name):
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == name)
    missing = [p for p in tool.input_schema["properties"] if p not in tool.description]
    assert not missing, missing


def test_special_tax_credit_description_lists_earner_types():
    tool = next(t for t in asyncio.run(mcp.list_tools()) if t.name == "special_tax_credit")
    for v in ("'근로'", "'일용근로'", "'근로소득없음'"):
        assert v in tool.description


# ── 업무무관 지급이자: 파이썬에서 dict로 직접 호출 ────────────────────────────
def test_nonbusiness_interest_accepts_dicts():
    loans = [{"interest": 10_000_000, "jeoksu": 36_500_000_000, "kind": "일반"}]
    r = S.nonbusiness_interest_disallowance(loans=loans, nonbusiness_jeoksu=3_650_000_000, year=2025)
    assert "error" not in r, r
    simple = S.nonbusiness_interest_disallowance(loans=[{"interest": 10_000_000, "jeoksu": 36_500_000_000}], nonbusiness_jeoksu=3_650_000_000)
    assert "error" not in simple, simple
    assert simple["결과"]["손금불산입(기타사외유출)"] == 1_000_000


# ── 재계산: 기계장치에 건물 키 없음 ─────────────────────────────────────────
def test_input_tax_recalc_neutral_key():
    args = dict(acquired={"year": 2022, "period": "2기"}, input_tax=20_000_000,
                ratios=[{"year": 2022, "period": "2기", "exempt_ratio": 0.5}, {"year": 2023, "period": "1기", "exempt_ratio": 0.56}])
    m = S.input_tax_recalculation(asset_type="기타감가상각자산", **args)
    assert m["결과"]["매입세액"] == 20_000_000 and "건물_매입세액" not in m["결과"]
    b = S.input_tax_recalculation(asset_type="건물·구축물", **args)
    assert b["결과"]["매입세액"] == 20_000_000


# ── 업무용승용차: 운행기록 작성인데 비율이 없으면 입력 확인 안내 ─────────────
def test_business_car_missing_ratio_message():
    r = S.business_car_expense(year=2025, upkeep=3_000_000, depreciation=12_000_000, booked_depreciation=0, log_kept=True)
    assert r["error"].startswith("입력 확인 필요"), r
    assert "business_ratio" in json.dumps(r, ensure_ascii=False) and "NoneType" not in json.dumps(r, ensure_ascii=False)


# ── 공통매입세액: 직전 과세기간 값을 안 넣으면 0으로 쓰지 않음 ───────────────
CIT = {"year": 2025, "period": "2기", "filing": "확정",
       "supplies": {"예정": {"taxable": 280_000_000, "exempt": 220_000_000}, "확정": {"taxable": 320_000_000, "exempt": 180_000_000}},
       "ledger": [{"항목": "공통 비품·용역", "매입세액": 6_000_000, "사용처": "공통"}],
       "common_asset_sales": [{"sale_price": 300_000, "input_tax": 100_000}]}


def test_common_input_tax_prior_missing_not_zero(tmp_path):
    r = c("common_input_tax", CIT)
    assert not any(x["이름"].startswith("직전") for x in r["계산식_입력"]), r["계산식_입력"]
    out = c("export_workbook", {"title": "w", "calls": [{"label": "공통매입", "tool": "common_input_tax", "args": CIT}],
                                "output_dir": str(tmp_path)})
    assert "error" not in out, out
    import openpyxl
    wb = openpyxl.load_workbook(out["결과"]["파일"])
    ws = next(wb[s] for s in wb.sheetnames if "공통사용재화" in s)
    assert ws["A7"].value != 0 and ws["B7"].value != 0 and "입력 없음" in str(ws["A7"].value)


# ── 대손금: 법 제19조의2② 채권(채무보증 구상채권·특수관계인 업무무관 가지급금) ──
BOOK = {"opening": 20_000_000, "offset": 0, "provision": 10_000_000, "closing": 30_000_000}


def _bd(writeoffs, **kw):
    args = dict(year=2025, sme=True, book=BOOK, receivables_prev_end_book=1_000_000_000,
                receivables_end_book=1_200_000_000, writeoffs=writeoffs)
    args.update(kw)
    return S.bad_debt_adjustment(**args)


def test_bad_debt_excluded_receivable():
    base = {"kind": "회수불능", "amount": 500_000_000, "arose_in": "당기", "booked": "손비"}
    plain = _bd([base])
    assert plain["계산"]["세법상 당기 대손금"] == 500_000_000
    r = _bd([dict(base, excluded_reason="특수관계인업무무관가지급금", recipient="법인", lent_on="2023-03-01")])
    assert "error" not in r, r
    assert r["계산"]["세법상 당기 대손금"] == 0
    assert r["계산"]["세법상 당기말 채권"] == 1_200_000_000            # 설정대상 채권에 다시 더하지 않음(법 제34조②)
    adj = [s for s in r["세무조정"] if "19조의2" in s["구분"]]
    assert adj == [{"구분": adj[0]["구분"], "조정": "손금불산입", "금액": 500_000_000, "소득처분": "기타사외유출"}]
    j = json.dumps(r["판단"], ensure_ascii=False)
    assert "제19조의2②2호" in j and "제106조" in j
    # 귀속자가 임원이면 상여, 주주면 배당
    r2 = _bd([dict(base, excluded_reason="특수관계인업무무관가지급금", recipient="임원", lent_on="2023-03-01")])
    assert any(s["소득처분"] == "상여" and s["금액"] == 500_000_000 for s in r2["세무조정"])
    # 채무보증 구상채권
    r3 = _bd([dict(base, excluded_reason="채무보증구상채권", recipient="법인")])
    assert r3["계산"]["세법상 당기 대손금"] == 0 and "제19조의2②1호" in json.dumps(r3["판단"], ensure_ascii=False)


def test_bad_debt_related_party_timing():
    base = {"kind": "회수불능", "amount": 100_000_000, "arose_in": "당기", "booked": "손비",
            "excluded_reason": "특수관계인업무무관가지급금", "recipient": "법인"}
    # 2021.1.1. 이후 대여분: 대여시점에 특수관계였으면 대손사유 발생 때 관계가 끝났어도 제외(법 제19조의2②2호 후단)
    a = _bd([dict(base, lent_on="2022-05-01", related_at_lending=True, related_at_event=False)])
    assert a["계산"]["세법상 당기 대손금"] == 0
    # 2020.12.31. 이전 대여분: 대손사유 발생 당시 특수관계가 없으면 대손금 인정(개정 전 판례 기준)
    b = _bd([dict(base, lent_on="2020-05-01", related_at_lending=True, related_at_event=False)])
    assert b["계산"]["세법상 당기 대손금"] == 100_000_000
    assert "부칙" in json.dumps(b["판단"], ensure_ascii=False)


def test_bad_debt_excluded_balance_out_of_base():
    r = _bd([{"kind": "회수불능", "amount": 10_000_000, "arose_in": "당기", "booked": "손비"}],
            excluded_receivables_end_book=200_000_000, excluded_receivables_prev_end_book=100_000_000)
    assert r["계산"]["세법상 당기말 채권"] == 1_000_000_000
    assert r["계산"]["세법상 전기말 채권"] == 900_000_000
    assert r["서식_표"]["34_채권잔액"][0]["설정제외"] == 200_000_000


def test_bad_debt_excluded_reason_validated():
    r = _bd([{"kind": "회수불능", "amount": 1, "arose_in": "당기", "excluded_reason": "아무거나"}])
    assert "error" in r
