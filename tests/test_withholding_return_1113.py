"""0.44.0 원천징수이행상황신고서 집계 도구와 서식 틀(2026-11-13, Claude).
원문: 소득세법 시행규칙 별지 제21호서식 <개정 2025. 3. 21.> 제1쪽·작성방법(제2쪽·제3쪽), 소득세법 제128조, 시행령 제185조(2025.12.31. 기준).
손계산: 작성방법 3.나(환급할 세액은 총합계에 넣지 않고 ⑮일반환급), 3.다(근로소득 세액 가감계 = A01+A02+A03+A06), 3.라3)(조정대상 환급세액을 코드 순서대로 충당)."""
import pathlib, shutil, subprocess
import openpyxl, pytest
from korean_tax_calc_mcp import server as S

SHEET = "원천 별지21 이행상황신고서"
MAY = dict(year=2025, month=5, lines=[
    {"코드": "A01", "인원": 45, "총지급액": 150_000_000, "소득세": 6_200_000},
    {"코드": "A25", "인원": 3, "총지급액": 13_000_000, "소득세": 390_000},
    {"코드": "A25", "인원": 1, "총지급액": 20_000_000, "소득세": 4_000_000, "가산세": 400_000, "비거주자": True, "메모": "미국 거주 개인, 서울 촬영"}])
FEB = dict(year=2025, month=2, prior_unrefunded=200_000, lines=[
    {"코드": "A01", "인원": 10, "총지급액": 30_000_000, "소득세": 1_000_000}, {"코드": "A04", "인원": 10, "총지급액": 400_000_000, "소득세": -1_500_000},
    {"코드": "A06", "인원": 10, "총지급액": 0, "소득세": -1_500_000}, {"코드": "A25", "인원": 2, "총지급액": 5_000_000, "소득세": 150_000},
    {"코드": "A60", "인원": 1, "총지급액": 9_000_000, "소득세": 1_260_000, "농어촌특별세": 20_000}])


def _fn(t):
    return getattr(t, "fn", t)


def test_payable_only_month():
    r = _fn(S.withholding_return)(**MAY)
    rows = r["계산"]["행"]
    assert rows["A30"]["인원"] == 4 and rows["A30"]["총지급액"] == 33_000_000 and rows["A30"]["소득세"] == 4_390_000 and rows["A30"]["가산세"] == 400_000
    assert rows["A30"]["납부_소득세등"] == 4_790_000                       # ⑩은 가산세 포함
    assert rows["A99"]["인원"] == 49 and rows["A99"]["총지급액"] == 183_000_000
    assert r["결과"]["납부세액_소득세등"] == 6_200_000 + 4_790_000 and r["결과"]["차월이월_환급세액"] == 0
    assert any("A25" in p["항목"] and "부표" in p["결론"] and "사업소득[A25]란" in p["결론"] for p in r["판단"])   # 비거주자 개인 인적용역은 사업소득 칸
    assert any("2025. 6. 10." in x for x in r["주의"])


def test_refund_offsets_in_code_order():
    r = _fn(S.withholding_return)(**FEB)
    rows, adj = r["계산"]["행"], r["계산"]["환급세액_조정"]
    assert rows["A10"]["인원"] == 20 and rows["A10"]["총지급액"] == 430_000_000      # 인원·총지급액은 A01+A02+A03+A04
    assert rows["A10"]["소득세"] == 1_000_000 - 1_500_000                          # 세액은 A01+A02+A03+A06
    assert adj["⑮ 일반환급"] == 500_000 and adj["⑱ 조정대상 환급세액"] == 700_000
    assert rows["A30"]["당월조정환급세액"] == 150_000 and rows["A30"]["납부_소득세등"] == 0   # 코드 순서: 사업(A30) 먼저
    assert rows["A60"]["당월조정환급세액"] == 550_000 and rows["A60"]["납부_소득세등"] == 710_000 and rows["A60"]["납부_농어촌특별세"] == 20_000
    assert rows["A99"]["소득세"] == 150_000 + 1_260_000                            # 환급할 세액은 총합계에 넣지 않음
    assert adj["⑲ 당월조정 환급세액계"] == 700_000 and adj["⑳ 차월이월 환급세액"] == 0
    big = _fn(S.withholding_return)(**{**FEB, "prior_unrefunded": 5_000_000})
    assert big["결과"]["납부세액_소득세등"] == 0 and big["결과"]["납부세액_농어촌특별세"] == 0
    assert big["계산"]["환급세액_조정"]["⑳ 차월이월 환급세액"] == 5_000_000 + 500_000 - 1_430_000


def test_rejections():
    f = _fn(S.withholding_return)
    assert "filed_on" in f(**{**MAY, "year": 2026})["문제"][0]   # 신고일 없으면 2025 귀속만(2026-11-14 신고일 기준으로 바꿈)
    assert "error" in f(**{**MAY, "year": 2024})
    assert "A27" in f(year=2025, month=5, lines=[{"코드": "A27", "인원": 1, "총지급액": 1, "소득세": 1}])["문제"][0]
    assert "가감계" in f(year=2025, month=5, lines=[{"코드": "A30", "인원": 1, "총지급액": 1, "소득세": 1}])["문제"][0]
    assert "error" in f(year=2025, month=5, lines=[{"코드": "A01", "인원": -1, "총지급액": 1, "소득세": 1}])
    assert "error" in f(**{**FEB, "refund_claim": 1})                              # 차월이월 환급세액 0인데 환급신청
    assert "error" in f(**{**FEB, "prior_refund_claimed": 300_000})


@pytest.mark.skipif(not shutil.which("soffice"), reason="수식 재계산에 LibreOffice 필요")
def test_form_sheet_recalculated(tmp_path):
    r = _fn(S.export_workbook)(title="w", calls=[{"label": "이행상황신고서", "tool": "withholding_return", "args": FEB}], output_dir=str(tmp_path))
    assert r["결과"]["오류_call"] == [] and SHEET in r["결과"]["시트"]
    raw = openpyxl.load_workbook(r["결과"]["파일"])[SHEET]
    assert "별지 제21호서식" in raw["A1"].value and raw["D9"].value == "A01" and raw["D39"].value == "A99" and raw["D15"].value == "A10"
    assert raw["F9"].value == "=호출1_A01_총지급액" and raw["G15"].value == "=G9+G10+G11+G14"      # A10 세액 = A01+A02+A03+A06
    out = pathlib.Path(tmp_path) / "re"
    subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), r["결과"]["파일"]], check=True, capture_output=True, timeout=180)
    ws = openpyxl.load_workbook(next(out.glob("*.xlsx")), data_only=True)[SHEET]
    assert (ws["E39"].value, ws["F39"].value, ws["G39"].value, ws["H39"].value) == (23, 444_000_000, 1_410_000, 20_000)
    assert (ws["J39"].value, ws["K39"].value, ws["L39"].value) == (700_000, 710_000, 20_000)
    assert ws["I43"].value == 700_000 and ws["K43"].value == 0                      # ⑱, ⑳
    checks = [c for row in ws.iter_rows(min_row=44, max_row=62, values_only=True) for c in row if c in ("일치", "확인 필요")]
    assert len(checks) == 13 and set(checks) == {"일치"}
