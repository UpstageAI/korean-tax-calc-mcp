"""서식 틀 토큰 해석 함수 정답 테스트. 작성 Claude 2026-10-25 (docs/SPEC_form_templates.md 3절, docs/SPEC_form_resolver.md)."""
import pytest
from korean_tax_calc_mcp.forms_workbook import resolve_formula, tool_value, fill_text

RES = {"결과": {"한도초과": 2280000, "시부인_대상": 87000000, "직부인_대표자상여": 0},
       "계산": {"기본한도": 70600000, "전통시장_지출": 0, "지역사랑상품권_지출": 4000000},
       "계산식_입력": [{"이름": "월수", "값": 12}, {"이름": "중소기업여부", "값": True}, {"이름": "수입구간3_한도", "값": float("inf")}]}
LOCAL = {"③": "D8", "⑮": "D26", "⑤-1": "D10"}
CROSS = {("별지23을", "⑦합계"): ("별지23(을) 기업업무추진비", "F13")}


def rf(f, call=0):
    return resolve_formula(f, res=RES, call_idx=call, local=LOCAL, cross=CROSS)


@pytest.mark.parametrize("f, want", [
    ("=[입력.월수]", "=호출1_월수"),
    ("=IF([입력.중소기업여부],1,2)", "=IF(호출1_중소기업여부,1,2)"),
    ("=[입력.전통시장등비율|0]", "=0"),
    ("=[계산.기본한도]", "=70600000"),
    ("=[계산.지역사랑상품권_지출|0]", "=4000000"),
    ("=[계산.온누리상품권_지출|0]", "=0"),
    ("=[결과.시부인_대상]+[결과.직부인_대표자상여|0]", "=87000000+0"),
    ("=MAX(0,{③}-{⑮})", "=MAX(0,D8-D26)"),
    ("=SUM({⑤-1},D11)", "=SUM(D10,D11)"),
    ("={별지23을!⑦합계}", "='별지23(을) 기업업무추진비'!F13"),
    ("=MIN({③},{⑮})*[입력.월수]/12", "=MIN(D8,D26)*호출1_월수/12"),
])
def test_resolve_formula(f, want):
    assert rf(f) == want


def test_call_index_prefix():
    assert rf("=[입력.월수]", call=2) == "=호출3_월수"


@pytest.mark.parametrize("f", ["=[입력.없는이름]", "=[계산.없는키]", "=[결과.없는키]", "={없는slot}", "={별지99!①}"])
def test_missing_without_default_raises(f):
    with pytest.raises((KeyError, ValueError)):
        rf(f)


def test_inf_input_is_not_a_name():
    with pytest.raises((KeyError, ValueError)):
        rf("=[입력.수입구간3_한도]")          # 무한대 입력은 이름으로 쓰지 않음(입력·가정에 숫자 없음)


@pytest.mark.parametrize("path, want", [("결과.한도초과", 2280000), ("계산.기본한도", 70600000), ("계산.없음", None), ("결과.없음", None)])
def test_tool_value(path, want):
    assert tool_value(RES, path) == want


def test_fill_text():
    meta = {"법인명": "㈜가람정밀(가상)", "사업자등록번호": "", "기간_시작": "2025.01.01", "기간_끝": "2025.12.31", "계정과목": "기업업무추진비", "label": "기계장치"}
    t = "법 인 명\n{{법인명}} · {{기간_시작}} ~ {{기간_끝}} · 월수( {{입력.월수}} ) · {{label}}"
    assert fill_text(t, res=RES, meta=meta) == "법 인 명\n㈜가람정밀(가상) · 2025.01.01 ~ 2025.12.31 · 월수( 12 ) · 기계장치"
