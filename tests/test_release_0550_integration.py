"""0.55.0 통합 확인(2026-11-15, Claude) — 따로 올라온 변경이 한 트리에서 만나는 곳.
  1. 서식 시트 순서: 2016~2024 부가가치세 신고서 판, 2016~2020 국제조세 구 서식 판이 현행 서식과 같은 자리에 온다.
  2. 끝수 키('납부할 금액(10원 미만 버림)')와 영문 표기·통합 문서 시트가 함께 나온다."""
import openpyxl
from test_form_old_intl_1115 import A, B, OS
from test_form_templates import build
from test_form_vat21_years import BASE


def _names(tmp_path, calls, **kw):
    return openpyxl.load_workbook(build(tmp_path, calls, **kw)).sheetnames


def test_old_edition_form_sheets_sit_where_current_forms_do(tmp_path):
    # 일부러 거꾸로 넣는다 — 해외현지법인 → 국제거래명세서 → 대손세액 → 부가 신고서(2019판)
    calls = [
        {"label": "해외현지법인", "tool": "overseas_subsidiary_statement", "args": dict(OS, year=2019)},
        {"label": "국제거래명세서", "tool": "international_transaction_statement", "args": dict(year=2018, parties=[A, B])},
        {"label": "대손세액", "tool": "vat_bad_debt_credit", "args": {"bad_debt_incl_vat": 3_300_000}},
        {"label": "신고서", "tool": "vat_return_general", "args": dict(BASE, year=2019)},
    ]
    names = _names(tmp_path, calls)
    forms = [n for n in names if n.startswith(("부가 ", "구국조 ", "국조 ", "법인 "))]
    assert forms[0] == "부가 별지21 신고서 2019판"                         # 신고서가 부속 서식 앞
    assert forms[1:3] == ["부가 신고서 대손세액가감(8)", "부가 별지19 대손세액공제신고서"]
    old = [n for n in forms if n.startswith("구국조 별지8갑")]
    assert old == ["구국조 별지8갑 2018판 (1)", "구국조 별지8갑 2018판 (2)"]
    i8, i13 = forms.index(old[-1]), forms.index("구국조 별지1의3 2015판")
    i81, i82 = forms.index("법인 별지81 해외현지법인명세"), forms.index("법인 별지82 재무상황표")
    assert 2 < forms.index(old[0]) < i8 < i13 < i81 < i82                  # 명세서 → 정상가격 신고서 → 해외현지법인 명세 → 재무상황표
    assert names.index(forms[-1]) < min(i for i, n in enumerate(names) if n.startswith("계산"))   # 서식 틀은 계산 시트 앞


def test_current_edition_order_unchanged_for_single_tool(tmp_path):
    names = _names(tmp_path, [{"label": "국제거래명세서", "tool": "international_transaction_statement", "args": dict(year=2023, parties=[A])}])
    forms = [n for n in names if n.startswith("국조 ")]
    assert forms == ["국조 별지16갑 국제거래명세서", "국조 별지20 정상가격산출방법"]


def test_english_blend_uses_new_glossary_terms_and_keeps_unlisted_keys(tmp_path):
    """영문 용어집에 새로 든 표기(국제거래명세서)는 통합 문서의 '계산 상세'에도 쓰이고, 용어집에 없는 키(끝수 규칙의 '납부할 금액(10원 미만 버림)',
    순액 약정의 '약정_순액')는 지어내지 않고 국문 그대로 — 시나리오 시트와 '계산 상세'에 같은 글자로 나오고 결과의 번역_없음에 모인다."""
    import json
    import pathlib

    from tests._helpers import call as c
    samples = json.loads((pathlib.Path(__file__).parent / "data" / "blend_sweep_calls.json").read_text(encoding="utf-8"))
    calls = [{"label": t, "tool": t, "args": samples[t]} for t in ("corporate_filing_obligations", "branch_profits_tax")]
    calls.append({"label": "net", "tool": "nonresident_withholding",
                  "args": dict(income_kind="사용료", recipient_type="법인", residence_country="미국", amount=100_000_000, treaty_rate=0.15,
                               net_of_tax=True, payer_bears_local_tax=True)})
    r = c("export_workbook", {"title": "glossary", "calls": calls, "output_dir": str(tmp_path), "lang": "en", "issues": [{"issue": "x"}]})
    assert r["결과"]["시트"] == ["Summary", "Inputs", "Workings", "Issues Log", "Calc detail"]
    wb = openpyxl.load_workbook(r["결과"]["파일"])
    text = lambda n: {x.value for row in wb[n].iter_rows() for x in row if isinstance(x.value, str) and x.data_type != "f"}
    detail, workings = text("Calc detail"), text("Workings")
    assert "Statement of international transactions (국제거래명세서)" in detail
    key = "납부할 금액(10원 미만 버림)"
    assert key in detail and key in workings and key in r["결과"]["번역_없음"]
    assert "약정_순액" in detail and "약정_순액" in r["결과"]["번역_없음"] and "역산.끝수" in detail
    assert not [t for t in detail | workings if "payable" in t.lower()]            # 공식 영문이 없는 키에 영문을 지어 붙이지 않음
