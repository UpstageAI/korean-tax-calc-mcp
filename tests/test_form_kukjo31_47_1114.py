"""국조 별지 제31호서식(갑·을·병)·제32호서식(갑·을)·제47호서식·제48호서식 틀과 overseas_subsidiary_statement (Claude 2026-11-14).

대조한 원문(국세법령정보시스템 HWP·조문, 법제처 보관 응답):
- 서식: 국조칙 2026.3.20. 시행본 별지 제31호서식(갑) <개정 2022. 3. 18.>·(을)·(병), 제32호서식(갑)·(을), 제47호서식 <개정 2026. 1. 2.>, 제48호서식 <개정 2022. 3. 18.>
- 국조법 제58조제1항: 2021.1.1.(법률 제17651호)·2022.1.1.·2023.1.1.·2024.1.1.·2025.1.1.·2026.1.2. 시행본 — 종료일이 속하는 달의 말일부터 6개월
- 국조령 제98조제1항: 2021.2.17.·2022.2.15.·2023.2.28.·2024.1.1.·2024.2.29.·2025.2.28.·2025.11.28.·2026.2.27. 시행본 — 제2호 가목·나목, 제3호 가목(10억·20억)·나목(50억·100억) 같음
- 저세율 기준: 2021 사업연도 15%(법 제27조제1항 2021년 시행본), 2022~ 법인세법 제55조 최고세율의 70%(2022년 25%, 2023~2025년 24%)
"""
import openpyxl
import pytest
from test_form_templates import build
from test_form_26 import Evaluator
from test_tools import c

G31, E31, B31 = "국조 별지31갑 합산과세판정", "국조 별지31을 조세부담", "국조 별지31병 보유비율"
G32, E32 = "국조 별지32갑 해외지주회사", "국조 별지32을 적용범위"
S47, S48 = "국조 별지47 해외현지법인명세", "국조 별지48 재무상황표"
M = 1_000_000
CFC = dict(year=2025, pretax_incomes=[1_000 * M, -100 * M, 500 * M], taxes_paid=[50 * M, 0, 30 * M], ownership_chains=[[0.6], [0.5, 0.4]],
           related_party=True, fy_end="2025-12-31", distributable={"unappropriated_retained_earnings": 900 * M, "mandatory_reserves": 30 * M})
FIN = {"01": 10_000, "14": 4_000, "21": 6_000, "22": 1_000, "23": 5_000, "27": 9_000, "28": 4_000, "29": 5_000, "30": 6_000, "56": 3_000,
       "31": 1_000, "57": 2_000, "38": 300, "42": 100, "58": 2_200, "47": 200, "48": 1_900, "71": 5_000, "76": 0, "77": 1_000, "82": 4_000}
OS = dict(year=2025, subsidiary={"name": "Garam Vietnam Co., Ltd.", "country": "베트남", "industry": "제조업", "industry_code": "292203",
                                 "local_id": "123456789", "shares": 600_000},
          ownership_direct=0.6, equity_investment=3_000 * M, loan_investment=500 * M, related_party=True, financials=FIN)


def wb_of(tmp_path, calls):
    return openpyxl.load_workbook(build(tmp_path, calls))


def listed(wb):
    return {wb["목록"].cell(r, 1).value: wb["목록"].cell(r, 2).value for r in range(1, wb["목록"].max_row + 1)}


# ── 국조31(갑·을·병) ──
def test_cfc31_cells_match_tool(tmp_path):
    wb = wb_of(tmp_path, [{"label": "CFC", "tool": "cfc_deemed_dividend", "args": CFC}])
    assert {G31, E31, B31} <= set(wb.sheetnames) and G32 not in wb.sheetnames and E32 not in wb.sheetnames
    ev = Evaluator(wb)
    # 을: ⑥ 결손 사업연도는 0, ⑩ 합계 = 1,000 + 0 + 500 = 1,500백만, ⑪ 합계 = 80백만
    assert [ev.v(E31, a) for a in ("C8", "D8", "E8", "F12", "F14")] == [1_000 * M, 0, 500 * M, 1_500 * M, 80 * M]
    # 갑: ⑪ 0.6 + 0.5×0.4 = 0.8, ⑭·⑮는 을에서, ⑬ = 80/1,500, 연평균 = 1,500/3 = 500백만 > 2억 → ⑫ 예
    assert abs(ev.v(G31, "F13") - 0.8) < 1e-12 and ev.v(G31, "F16") == 1_500 * M and ev.v(G31, "F17") == 80 * M
    assert abs(ev.v(G31, "F15") - 80 / 1_500) < 1e-12 and ev.v(G31, "F30") == 500 * M and ev.v(G31, "F14").startswith("[√] 예")
    assert abs(ev.v(G31, "F28") - 0.168) < 1e-12 and ev.v(G31, "D20") == 30 * M          # 2025: 24% × 70%, ⑱ 의무적립금
    for a in ("I13", "I15", "I16", "I17", "I30"):
        assert ev.v(G31, a) == "일치", a
    assert ",6)" in wb[G31]["I13"].value                                                # 비율 칸은 소수 6자리까지 대조
    # 병: ⑧ 직접 0.6·간접 0.2, ⑩ 소계 0.8 — 특수관계인 비율 입력이 없으면 내국인과 같음
    assert abs(ev.v(B31, "C20") - 0.6) < 1e-12 and abs(ev.v(B31, "C21") - 0.2) < 1e-12 and abs(ev.v(B31, "F22") - 0.8) < 1e-12
    assert ev.v(B31, "I22") == "일치" and ev.v(B31, "K22") == "일치"


def test_cfc31_basis_by_year_and_tool_values():
    for y, basis in ((2021, 0.15), (2022, 0.175), (2023, 0.168)):
        r = c("cfc_deemed_dividend", dict(CFC, year=y, fy_end=f"{y}-12-31"))
        inp = {i["이름"]: i["값"] for i in r["계산식_입력"]}
        assert abs(inp["저세율기준"] - basis) < 1e-12
        assert r["결과"]["조정후세전이익_합계"] == 1_500 * M and r["결과"]["납부세액_합계"] == 80 * M
        assert abs(r["결과"]["실제부담세율"] - 80 / 1_500) < 1e-12 and r["결과"]["판정보유비율"] == 0.8
    # 기존 계산식_입력 12개는 이름·순서 그대로(국조30갑 틀)
    names = [i["이름"] for i in r["계산식_입력"]][:12]
    assert names == ["사업연도", "처분전이익잉여금", "적용제외유보소득", "배당금", "상여금등", "의무적립금", "기과세간주배당잔여액",
                     "미실현평가이익", "월할2억원", "수동소득방식", "수동소득비율", "주식보유비율"]


def test_cfc31_2021_text_and_passive_32eul(tmp_path):
    args = dict(year=2021, pretax_incomes=[1_000 * M], taxes_paid=[100 * M], ownership_chains=[[0.3]], ownership_with_related_ratio=0.4,
                fy_end="2021-12-31", distributable={"unappropriated_retained_earnings": 1_000 * M}, fixed_facility_active_business=True,
                listed_industry="도매업", listed_industry_share=0.8, listed_industry_related_share=0.3,
                passive_income=300 * M, passive_excluded_dividends=50 * M, total_revenue=2_000 * M)
    wb = wb_of(tmp_path, [{"label": "수동", "tool": "cfc_deemed_dividend", "args": args}])
    assert E32 in wb.sheetnames and G32 not in wb.sheetnames
    ev = Evaluator(wb)
    assert "15%" in ev.v(G31, "D28") and ev.v(G31, "F28") == 0.15                        # 2021 사업연도 기준
    assert ev.v(G31, "F22").startswith("[ ] 예  [√]") and ev.v(G31, "F24").startswith("[√] 예")   # 업종기준 아님(특수관계 30%), 수동소득기준 해당
    # 32을 비율 = (300 − 50) / 2,000 = 12.5%, ⑥ 소계 0.8
    assert ev.v(E32, "D35") == 0.125 and ev.v(E32, "I35") == "일치" and ev.v(E32, "F16") == 0.8
    # 31병: 특수관계인 포함 비율 0.4를 주면 ⑩ 소계만
    assert ev.v(B31, "F22") == 0.4 and ev.v(B31, "F20") == "" and ev.v(B31, "K22") == "일치"
    # 30갑 ㉕ = (1,000 − 200) × 12.5% × 30% = 30백만
    assert ev.v("국조 별지30갑 유보소득계산", "F30") == 30 * M


def test_holding_32gap_and_pre2021_no_sheet(tmp_path):
    hold = dict(CFC, year=2023, fy_end="2023-12-31", holding_company_exemption=True)
    old = dict(CFC, year=2020, fy_end="2020-12-31")
    wb = wb_of(tmp_path, [{"label": "지주", "tool": "cfc_deemed_dividend", "args": hold}])
    assert G32 in wb.sheetnames and G31 in wb.sheetnames
    assert Evaluator(wb).v(G31, "F25").startswith("[√] 예")
    wb = wb_of(tmp_path, [{"label": "구", "tool": "cfc_deemed_dividend", "args": old}])
    assert not any(s.startswith("국조") for s in wb.sheetnames)
    assert "구 시행규칙의 서식 번호" in listed(wb)["국조 별지 제30호~제32호서식"]


# ── overseas_subsidiary_statement ──
def run(**kw):
    return c("overseas_subsidiary_statement", {"year": 2025, **kw})


def test_os_targets_boundaries():
    g = lambda **kw: run(**kw)["결과"]["재무상황표_제출대상"]
    assert g(ownership_direct=0.10, equity_investment=100 * M) is True                 # 가목: 10% 이상·1억원 이상
    assert g(ownership_direct=0.0999, equity_investment=100 * M) is False
    assert g(ownership_direct=0.10, equity_investment=60 * M, loan_investment=40 * M) is True   # 증권+대부 합계
    assert g(ownership_direct=0.10, equity_investment=100 * M - 1) is False
    assert g(ownership_direct=0.05, ownership_indirect=0.05, related_party=True) is True   # 나목: 직접·간접 10%·특수관계
    assert g(ownership_direct=0.05, ownership_indirect=0.05, related_party=False, equity_investment=500 * M) is False
    loss = lambda **kw: run(ownership_direct=0.5, related_party=True, **kw)["결과"]["손실거래명세서_제출대상"]
    assert loss(loss_single_year=5_000 * M) is True and loss(loss_single_year=5_000 * M - 1, loss_cumulative_5y=9_999 * M) is False
    assert loss(loss_cumulative_5y=10_000 * M) is True and loss() is None
    assert loss(filer="개인", loss_single_year=1_000 * M) is True and loss(filer="개인", loss_cumulative_5y=2_000 * M - 1) is False
    # 나목이 아니면(특수관계 없음) 금액과 무관하게 손실거래명세서 대상 아님
    assert run(ownership_direct=0.5, equity_investment=500 * M, loss_single_year=9_000 * M)["결과"]["손실거래명세서_제출대상"] is False


def test_os_deadline_and_errors():
    assert run()["결과"]["제출기한"] == "2026-06-30"
    assert run(fy_end="2025-03-31", year=2024)["결과"]["제출기한"] == "2025-09-30"
    assert run(fy_end="2024-08-31", year=2023)["결과"]["제출기한"] == "2025-02-28"
    assert run(year=2021, fy_end="2021-12-31")["결과"]["제출기한"] == "2022-06-30"
    assert "error" in run(year=2020) and "error" in run(financials={"45": 1}) and "error" in run(ownership_direct=0.7, ownership_indirect=0.4)


def test_os_identities():
    r = run(**{k: v for k, v in OS.items() if k != "year"})["결과"]
    by = {x["식"][:2]: x for x in r["항등식_확인"]}
    assert set(by) == {"01", "56", "57", "58", "48", "82", "21", "27"}                 # 식의 코드가 모두 있을 때만
    assert by["48"]["판정"] == "확인 필요" and by["48"]["오른쪽"] == 2_000 and by["48"]["차이"] == -100   # 2,200 − 200 ≠ 1,900
    assert all(x["판정"] == "일치" for k, x in by.items() if k != "48") and r["항등식_불일치"] == 1
    assert r["항등식_오른쪽"]["82"] == 4_000 and r["투자금액"] == 3_500 * M


def test_export_47_48(tmp_path):
    wb = wb_of(tmp_path, [{"label": "현지", "tool": "overseas_subsidiary_statement", "args": OS}])
    assert S47 in wb.sheetnames and S48 in wb.sheetnames
    ev = Evaluator(wb)
    assert ev.v(S47, "D17") == 60.0 and ev.v(S47, "B17") == 3_000 * M and ev.v(S47, "F17") == 500 * M
    assert wb[S47]["B10"].value == "Garam Vietnam Co., Ltd." and wb[S47]["B13"].value == "제조업 (292203)"
    assert wb[S47]["F39"].value == "2026-06-30"
    assert ev.v(S48, "C10") == 10_000 and ev.v(S48, "F35") == 1_900 and ev.v(S48, "C11") == ""   # 01, 48, 빈 코드 50
    ws = wb[S48]
    rows = {str(ws.cell(r, 1).value)[:2]: r for r in range(59, ws.max_row + 1) if ws.cell(r, 1).value}
    assert ev.v(S48, f"D{rows['01']}") == "일치" and ev.v(S48, f"D{rows['48']}") == "확인 필요"
    assert ev.v(S48, f"C{rows['48']}") == 2_000
    # 재무상황표 대상이 아니면 48 시트 없이 목록에 사유
    small = dict(OS, ownership_direct=0.05, related_party=False)
    wb = wb_of(tmp_path, [{"label": "소액", "tool": "overseas_subsidiary_statement", "args": small}])
    assert S47 in wb.sheetnames and S48 not in wb.sheetnames
    assert "제출 대상 아님" in listed(wb)["국조 별지 제48호서식"]
