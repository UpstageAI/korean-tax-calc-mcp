"""외국납부세액공제(foreign_tax_credit) 테스트 — 법인세 법 제57조·시행령 제94조.

손계산 사례: 법인세법 제55조(세율)·제57조(외국납부세액공제)·시행령 제94조(공제한도 계산).
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a): return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


def test_tool_registered():
    """foreign_tax_credit이 mcp.list_tools()에 등록되었는지 확인."""
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "foreign_tax_credit" in names


def test_basic_direct_tax_credit():
    """테스트01: 직접외국납부세액만 있는 기본 세액공제.
    과세표준 1억 원, 산출세액 1천만 원(2025년 10%), 국외원천소득 3천만 원, 직접외국납부세액 2백만 원.
    국가별 한도 = 10,000,000 × 30,000,000 ÷ 100,000,000 = 3,000,000.
    공제액 = min(2,000,000, 3,000,000) = 2,000,000. 한도초과 없음.
    근거: 법 §57①, 영 §94②⑦."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "미국",
            "foreign_income": 30_000_000,
            "direct_tax": 2_000_000,
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["산출세액"] == 9_000_000        # 1억 × 9% (2025년 제55조①)
    assert 결과["과세표준"] == 100_000_000
    assert 결과["간접외국납부세액"] == 0
    assert 결과["Gross-up_익금산입액"] == 0
    assert 결과["외국납부세액공제액"] == 2_000_000
    assert 결과["공제한도_합계"] == 2_700_000   # 9,000,000 × 30,000,000 ÷ 100,000,000
    assert 결과["한도초과_이월액"] == 0
    assert 결과["이월배제액"] == 0
    assert 결과["이월공제기간"] == "2026~2035"   # 발생 사업연도 다음해부터 10년: 2025+1 ~ 2025+10
    assert 결과["손금산입_대상(직접)"] == 0       # 세액공제 방법
    국가 = 결과["국가별"][0]
    assert 국가["국가"] == "미국"
    assert 국가["직접외국납부세액"] == 2_000_000
    assert 국가["공제한도"] == 2_700_000
    assert 국가["공제액"] == 2_000_000
    assert 국가["한도초과액"] == 0
    assert 국가["외국납부세액_계"] == 2_000_000
    assert "근거" in r


def test_limit_exceeded():
    """테스트02: 한도 초과 — 직접외국납부세액 7백만, 한도 6백만.
    과세표준 1억, 산출세액 1천만(2025년 10%), 국외원천소득 6천만.
    한도 = 10,000,000 × 60,000,000 ÷ 100,000,000 = 6,000,000.
    공제액 = min(7,000,000, 6,000,000) = 6,000,000.
    한도초과 이월액 = 1,000,000. 이월공제기간 10년(2025~2034).
    근거: 법 §57①②, 영 §94⑦."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "중국",
            "foreign_income": 60_000_000,
            "direct_tax": 7_000_000,
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["외국납부세액공제액"] == 5_400_000   # min(7,000,000, 5,400,000)
    assert 결과["공제한도_합계"] == 5_400_000        # 9,000,000 × 60,000,000 ÷ 100,000,000
    assert 결과["한도초과_이월액"] == 1_600_000     # 7,000,000 − 5,400,000
    국가 = 결과["국가별"][0]
    assert 국가["공제액"] == 5_400_000
    assert 국가["한도초과액"] == 1_600_000
    assert 국가["한도초과_이월액"] == 1_600_000


def test_indirect_foreign_tax():
    """테스트03: 간접외국납부세액(Gross-up).
    외국자회사 A: 수입배당금 1억(원천징수 전), 자회사 소득금액 2억, 자회사 법인세액 4천만, 지분율 15%.
    2025년 기준 지분율 10% 이상 → 요건 충족.
    간접외국납부세액 = 40,000,000 × 100,000,000 ÷ (200,000,000 − 40,000,000)
                      = 40,000,000 × 100,000,000 ÷ 160,000,000
                      = 25,000,000.
    Gross-up 익금산입액 = 25,000,000 (base_includes_grossup=False → 과세표준에 더함 → 125,000,000).
    국가별 한도 분자 = 국외원천소득 1억3천만 + Gross-up 2천5백만 = 1억5천5백만원.
    한도 = 11,250,000 × 155,000,000 ÷ 125,000,000 = 11,250,000 (비율 1.0 상한).
    외국납부세액 계 = 직접 2백만 + 원천징수세 150만 + 간접 2천5백만 = 2천850만원.
      (withholding_tax는 간접요건 무관 직접세액에 합산)
    공제액 = min(28,500,000, 11,250,000) = 11,250,000.
    근거: 법 §57④·⑤, §15②2호, §57①, 영 §94②⑦⑧."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 130_000_000,   # 30M + 100M dividend (수입배당금 포함)
            "direct_tax": 2_000_000,
            "subsidiaries": [{
                "name": "NL Subsidiary A",
                "dividend": 100_000_000,
                "withholding_tax": 1_500_000,
                "received_on": "2025-03-31",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 200_000_000,
                "sub_tax": 40_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["산출세액"] == 11_250_000         # 125,000,000 × 9%
    assert 결과["과세표준"] == 125_000_000        # base + Gross-up
    assert 결과["간접외국납부세액"] == 25_000_000
    assert 결과["Gross-up_익금산입액"] == 25_000_000
    assert 결과["외국납부세액공제액"] == 11_250_000  # min(28,500,000, 11,250,000)
    assert 결과["공제한도_합계"] == 11_250_000
    국가 = 결과["국가별"][0]
    assert 국가["간접외국납부세액"] == 25_000_000
    assert 국가["Gross-up_익금산입액"] == 25_000_000
    assert 국가["외국납부세액_계"] == 28_500_000     # 직접 200만 + 원천징수 150만 + 간접 2,500만
    assert 국가["직접외국납부세액"] == 3_500_000     # 2,000,000 + 1,500,000
    assert 국가["공제한도"] == 11_250_000
    assert 국가["공제액"] == 11_250_000
    assert 국가["한도초과액"] == 17_250_000
    assert 국가["한도초과_이월액"] == 17_250_000    # 한도초과액 − 이월배제액(0)
    # 자회사 결과
    sub = 국가["외국자회사"][0]
    assert sub["외국자회사"] == "NL Subsidiary A"
    assert sub["수입배당금"] == 100_000_000
    assert sub["간접외국납부세액"] == 25_000_000
    assert sub["요건충족"] is True
    assert sub["익금불산입"] is False
    assert sub["공제대상_원천징수세"] == 1_500_000
    assert "40,000,000 × 100,000,000 ÷ (200,000,000 − 40,000,000)" in sub["산식"]


def test_method_sinkan_2021_error():
    """테스트04: 2021년 이후 손금산입 방법 → error.
    2021.1.1. 이후 개시 사업연도부터 손금산입방법 삭제(법 §57②, 법률 17652).
    근거: 법 §57②(법률 17652, 2020.12.22.), 부칙 제19조."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "손금산입",
        "countries": [{
            "country": "미국",
            "foreign_income": 10_000_000,
            "direct_tax": 1_000_000,
        }],
        "months": 12,
    })
    assert "error" in r
    assert "method" in str(r.get("필요 입력", []))


def test_method_sinkan_2020_ok():
    """테스트05: 2020 사업연도 손금산입 방법 허용.
    공제액 0, Gross-up 0, 간접세액 0. 손금산입_대상(직접) = 직접 + 간주 + 원천징수세.
    근거: 법 §57①②(2020-01-01 시행본), 허용 방법: 세액공제·손금산입."""
    r = c("foreign_tax_credit", {
        "year": 2020,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "손금산입",
        "countries": [{
            "country": "미국",
            "foreign_income": 20_000_000,
            "direct_tax": 2_000_000,
            "deemed_tax": 500_000,
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["손금산입_대상(직접)"] == 2_500_000   # 직접 2백만 + 간주 50만 (원천징수세 없음)
    assert 결과["산출세액"] == 10_000_000            # 100,000,000 × 10%
    assert 결과["과세표준"] == 100_000_000           # base 그대로
    assert 결과["간접외국납부세액"] == 0
    assert 결과["Gross-up_익금산입액"] == 0
    assert 결과["외국납부세액공제액"] == 0
    assert 결과["공제한도_합계"] == 0                 # 손금산입 method: 공제 없음
    assert 결과["한도초과_이월액"] == 0
    assert 결과["이월배제액"] == 0
    assert 결과["확인 필요"] == "손금산입액은 과세표준 계산 전에 각 사업연도 소득에서 빼야 함 (법 §57②)"
    assert 결과["이월공제기간"] == "2021~2030"       # 발생 사업연도 다음해부터 10년(부칙 연장): 2020+1 ~ 2020+10
    국가 = 결과["국가별"][0]
    assert 국가["직접외국납부세액"] == 2_000_000     # 원천징수세 없음
    assert 국가["손금산입_대상(직접)"] == 2_500_000  # 2,000,000 + 500,000
    assert 국가["공제한도"] == 0
    assert 국가["공제액"] == 0
    assert 국가["간접외국납부세액"] == 0


def test_participation_exempt_2023():
    """테스트06: 2023년부터 제18조의4 익금불산입 적용 배당은 간접외국납부세액 제외.
    외국자회사 배당금에 대해 participation_exempt=True → 간접외국납부세액 공제 제외,
    그 배당의 withholding_tax도 공제 대상 아님(익금불산입 배당에 대한 세액).
    foreign_income=130,000,000(수입배당금 포함), 원천징수세 제외 → 직접외국납부세액=2,000,000.
    근거: 법 §57⑤·⑦(법률 19193, 2022.12.31.), §18조의4."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 130_000_000,   # 30M + 100M dividend
            "direct_tax": 2_000_000,
            "subsidiaries": [{
                "name": "NL Sub PE",
                "dividend": 100_000_000,
                "withholding_tax": 1_500_000,
                "received_on": "2025-03-31",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 200_000_000,
                "sub_tax": 40_000_000,
                "participation_exempt": True,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["간접외국납부세액"] == 0          # participation_exempt → 제외
    assert 결과["Gross-up_익금산입액"] == 0
    국가 = 결과["국가별"][0]
    assert 국가["간접외국납부세액"] == 0
    assert 국가["외국납부세액_계"] == 2_000_000  # 직접세만 (원천징수세 공제 대상 아님)
    assert 국가["직접외국납부세액"] == 2_000_000
    assert 국가["공제한도"] == 9_000_000        # 9,000,000 × 130,000,000 ÷ 100,000,000 → 1.0 상한
    assert 국가["공제액"] == 2_000_000          # min(2,000,000, 9,000,000)
    sub = 국가["외국자회사"][0]
    assert sub["익금불산입"] is True
    assert sub["요건충족"] is False              # participation_exempt로 인해 미충족 처리
    assert "제18조의4" in sub["처리"]
    assert sub["공제대상_원천징수세"] == 0       # 익금불산입 배당의 원천징수세는 공제 대상 아님


def test_reduction_excluded_이월배제():
    """테스트07: 감면분(감면·면제 대상 국외원천소득×감면비율)이 있는 경우 이월배제액 발생.
    2025년 법인세율 9%(2억 이하). 국외원천소득 5천만, 감면분 1천만, 대응비용 0, 직접외국납부세액 6백만.
    분자 = 50,000,000 − 0 − 10,000,000 + 0 = 40,000,000.
    한도 = 9,000,000 × 40,000,000 ÷ 100,000,000 = 3,600,000.
    대응비용 차감 전 한도 = 9,000,000 × 50,000,000 ÷ 100,000,000 = 4,500,000.
    공제액 = min(6,000,000, 3,600,000) = 3,600,000.
    한도초과액 = 6,000,000 − 3,600,000 = 2,400,000.
    이월배제액 = min(6,000,000, 4,500,000) − 3,600,000 = 900,000.
    한도초과_이월액 = 2,400,000 − 900,000 = 1,500,000.
      (한도초과액 중 대응비용 차감 전 한도와 차감 후 한도의 차이만큼은 이월배제,
       나머지만 이월공제 대상으로 이월)
    근거: 영 §94⑮."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "싱가포르",
            "foreign_income": 50_000_000,
            "direct_tax": 6_000_000,
            "related_costs": 0,
            "reduction_excluded": 10_000_000,
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["외국납부세액공제액"] == 3_600_000   # min(6,000,000, 3,600,000)
    assert 결과["공제한도_합계"] == 3_600_000
    assert 결과["한도초과_이월액"] == 1_500_000     # 2,400,000 − 900,000 (이월배제액 차감)
    assert 결과["이월배제액"] == 900_000
    국가 = 결과["국가별"][0]
    assert 국가["공제액"] == 3_600_000
    assert 국가["한도초과액"] == 2_400_000
    assert 국가["이월배제액(대응비용 관련)"] == 900_000
    assert 국가["한도초과_이월액"] == 1_500_000


def test_base_includes_grossup_true():
    """테스트08: base_includes_grossup=True → Gross-up이 이미 base에 포함됨.
    간접외국납부세액은 계산되지만 과세표준은 base 그대로(125,000,000).
    한도는 base 기준 분자(foreign_income + Gross-up)로 계산.
    foreign_income=130,000,000(수입배당금 포함), 직접세액=2,000,000+1,500,000=3,500,000.
    근거: 법 §15②2호(익금산입), §57④."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 125_000_000,   # Gross-up 2천5백만 이미 포함된 과세표준
        "base_includes_grossup": True,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 130_000_000,   # 30M + 100M dividend
            "direct_tax": 2_000_000,
            "subsidiaries": [{
                "name": "NL Sub",
                "dividend": 100_000_000,
                "withholding_tax": 1_500_000,
                "received_on": "2025-03-31",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 200_000_000,
                "sub_tax": 40_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["간접외국납부세액"] == 25_000_000
    assert 결과["Gross-up_익금산입액"] == 25_000_000  # 계산상 값은 존재
    assert 결과["산출세액"] == 11_250_000             # 125,000,000 × 9%
    assert 결과["과세표준"] == 125_000_000            # base 그대로 (Gross-up 이미 포함)
    # 한도 = 11,250,000 × (130,000,000 + 25,000,000) ÷ 125,000,000 = 11,250,000 (비율 1.0)
    assert 결과["공제한도_합계"] == 11_250_000
    assert 결과["세무조정"] == []                      # Gross-up 이미 포함 → 추가 세무조정 없음
    국가 = 결과["국가별"][0]
    assert 국가["직접외국납부세액"] == 3_500_000      # 2,000,000 + 1,500,000
    assert 국가["외국납부세액_계"] == 28_500_000      # 3,500,000 + 0 + 25,000,000
    assert 국가["공제한도"] == 11_250_000
    assert 국가["공제액"] == 11_250_000


def test_short_year_months():
    """테스트09: 사업연도 월수 6개월 → 산출세액 월할 환산.
    과세표준 1억, 6개월 → (1억 × 12/6) × 10% × 6/12 = 2억 × 10% × 0.5 = 1천만.
    실제로는: base × 12/6 = 2억(환산 과세표준), tier 계산 후 × 6/12.
    2억 × 10% = 2천만 → × 6/12 = 1천만.
    근거: 법 §55②(1년 미만 사업연도 월할)."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "미국",
            "foreign_income": 30_000_000,
            "direct_tax": 2_000_000,
        }],
        "months": 6,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["산출세액"] == 9_000_000    # 월할 환산: 1억×12/6×9%×6/12 = 9,000,000
    # 한도 = 9,000,000 × 30,000,000 ÷ 100,000,000 = 2,700,000
    assert 결과["공제한도_합계"] == 2_700_000


def test_no_countries_error():
    """테스트10: countries 목록이 비어 있으면 계산하지 않음."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [],
        "months": 12,
    })
    assert "error" in r


def test_resource_dev_5pct():
    """테스트11: 해외자원개발 법인은 지분율 5%로 간접외국납부세액 요건 충족.
    2025년 기준 해외자원개발 지분율 5%(vocab 규칙), 보유 6개월 이상.
    foreign_income=70,000,000(수입배당금 50M 포함), 직접세액=1,000,000+500,000=1,500,000.
    간접외국납부세액 = 20,000,000 × 50,000,000 ÷ (100,000,000 − 20,000,000) = 12,500,000.
    과세표준 = 100,000,000 + 12,500,000 = 112,500,000.
    산출세액 = 112,500,000 × 9% = 10,125,000.
    한도 = 10,125,000 × (70,000,000 + 12,500,000) ÷ 112,500,000 = 7,425,000.
    외국납부세액_계 = 1,500,000 + 0 + 12,500,000 = 14,000,000.
    공제액 = min(14,000,000, 7,425,000) = 7,425,000.
    근거: 법 §57⑤(해외자원개발 100분의 5), 영 §94⑨."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "인도네시아",
            "foreign_income": 70_000_000,   # 20M + 50M dividend
            "direct_tax": 1_000_000,
            "subsidiaries": [{
                "name": "자원자회사",
                "dividend": 50_000_000,
                "withholding_tax": 500_000,
                "received_on": "2025-06-30",
                "ownership": 0.08,
                "holding_months": 12,
                "resource_dev": True,
                "sub_income": 100_000_000,
                "sub_tax": 20_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["간접외국납부세액"] == 12_500_000
    assert 결과["Gross-up_익금산입액"] == 12_500_000
    assert 결과["산출세액"] == 10_125_000         # 112,500,000 × 9%
    assert 결과["과세표준"] == 112_500_000        # base + Gross-up
    assert 결과["외국납부세액공제액"] == 7_425_000
    assert 결과["공제한도_합계"] == 7_425_000
    국가 = 결과["국가별"][0]
    sub = 국가["외국자회사"][0]
    assert sub["요건충족"] is True
    assert sub["간접외국납부세액"] == 12_500_000
    assert 국가["직접외국납부세액"] == 1_500_000  # 1,000,000 + 500,000
    assert 국가["외국납부세액_계"] == 14_000_000  # 1,500,000 + 0 + 12,500,000
    assert 국가["공제한도"] == 7_425_000
    assert 국가["공제액"] == 7_425_000


def test_2022_25pct_ownership():
    """테스트12: 2022년 사업연도 — 지분율 25% 기준.
    소유 지분율 20% → 요건 미충족(2022년까지 25%).
    foreign_income=70,000,000(수입배당금 50M 포함), 직접세액=1,000,000+500,000=1,500,000.
    간접요건 미충족으로 간접세액=0, withholding_tax는 직접세액에 합산.
    근거: 법 §57⑤(100분의 25), 영 §94⑨, vocab '간접외국납부세액' 적용 2015~2022."""
    r = c("foreign_tax_credit", {
        "year": 2022,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "베트남",
            "foreign_income": 70_000_000,   # 20M + 50M dividend
            "direct_tax": 1_000_000,
            "subsidiaries": [{
                "name": "VN Sub",
                "dividend": 50_000_000,
                "withholding_tax": 500_000,
                "received_on": "2022-06-30",
                "ownership": 0.20,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 100_000_000,
                "sub_tax": 20_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    국가 = r["결과"]["국가별"][0]
    sub = 국가["외국자회사"][0]
    assert sub["요건충족"] is False
    assert sub["간접외국납부세액"] == 0
    assert "25%" in sub["요건"]
    assert 국가["직접외국납부세액"] == 1_500_000   # 1,000,000 + 500,000 (withholding_tax 합산)
    assert 국가["외국납부세액_계"] == 1_500_000   # 직접세액만 (간접 0)


def test_basis_포함():
    """테스트13: 결과에 근거(근거, 연도별_근거)가 포함되는지 확인."""
    r = c("foreign_tax_credit", {
        "year": 2025,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "미국",
            "foreign_income": 30_000_000,
            "direct_tax": 2_000_000,
        }],
        "months": 12,
    })
    assert "근거" in r
    assert len(r["근거"]) > 0
    assert "연도별_근거" in r
    assert "외국납부세액공제" in r["연도별_근거"]


def test_2022_short_holding_no_indirect():
    """2022년, 보유 4개월 → 간접외국납부세액 0·요건충족 false.
    자회사 배당 5,000만(지분 40%, 보유 4개월, 원천징수 500만, 자회사 소득 2억·법인세 4,000만).
    2022년 기준 지분율 25% 이상이나 보유기간 6개월 미달 → 간접세액 0.
    직접외국납부세액 = 원천징수세 500만(직접세액은 미지정 → 0 + 원천징수세).
    근거: 법 §57⑤(25%), 영 §94⑨(6개월), vocab '간접외국납부세액' 2015~2022 적용."""
    r = c("foreign_tax_credit", {
        "year": 2022,
        "base": 500_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "베트남",
            "foreign_income": 500_000_000,
            "subsidiaries": [{
                "name": "VN Sub",
                "dividend": 50_000_000,
                "withholding_tax": 5_000_000,
                "received_on": "2022-06-30",
                "ownership": 0.40,
                "holding_months": 4,
                "resource_dev": False,
                "sub_income": 200_000_000,
                "sub_tax": 40_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["간접외국납부세액"] == 0
    assert 결과["Gross-up_익금산입액"] == 0
    국가 = 결과["국가별"][0]
    sub = 국가["외국자회사"][0]
    assert sub["요건충족"] is False
    assert sub["간접외국납부세액"] == 0
    assert 국가["직접외국납부세액"] == 5_000_000   # withholding_tax만 (direct_tax 미지정)
    assert 국가["외국납부세액_계"] == 5_000_000


def test_2024_participation_exempt_no_error():
    """2024년, 국외원천소득 300만, 익금불산입 배당 6,000만(participation_exempt=True).
    익금불산입 배당은 국외원천소득 검사에서 제외하므로 error 아님.
    간접·직접 모두 0 (직접세 미지정, 익금불산입으로 간접 제외).
    근거: 법 §57⑤⑦(법률 19193), §18조의4, vocab '간접외국납부세액' 2023~ 적용."""
    r = c("foreign_tax_credit", {
        "year": 2024,
        "base": 3_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 3_000_000,
            "subsidiaries": [{
                "name": "NL Sub PE",
                "dividend": 60_000_000,
                "received_on": "2024-03-31",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 200_000_000,
                "sub_tax": 40_000_000,
                "participation_exempt": True,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r
    결과 = r["결과"]
    assert 결과["간접외국납부세액"] == 0
    assert 결과["외국납부세액공제액"] == 0
    국가 = 결과["국가별"][0]
    assert 국가["간접외국납부세액"] == 0
    assert 국가["직접외국납부세액"] == 0
    sub = 국가["외국자회사"][0]
    assert sub["익금불산입"] is True
    assert sub["요건충족"] is False


def test_2018_carryover_period_10yr():
    """2018년 한도초과 발생 → 이월공제기간 == "2019~2028".
    2016~2020년 개시 사업연도 발생분은 부칙(법률 17652 제19조)으로 10년 적용.
    start = 2018+1 = 2019, end = 2018+10 = 2028.
    근거: 법률 17652 부칙 제19조, vocab '외국납부세액공제' 2016~2020 적용(부칙연장_이월공제기간 10)."""
    r = c("foreign_tax_credit", {
        "year": 2018,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "중국",
            "foreign_income": 60_000_000,
            "direct_tax": 7_000_000,
        }],
        "months": 12,
    })
    assert "error" not in r
    assert r["결과"]["이월공제기간"] == "2019~2028"


def test_2023_pe_missing_error():
    """2023년 이후 받은 배당에 participation_exempt 누락 → error dict 반환(예외 아님).
    사업연도 2023, received_on="2023-06-30", 지분율 15%, participation_exempt 키 없음.
    필요 입력 키에 "countries[0].subsidiaries[0].participation_exempt"가 포함되어야 함.
    근거: 법 §57⑤(법률 19193, 2022.12.31. 개정), §18조의4, vocab '간접외국납부세액' 2023~ 적용."""
    r = c("foreign_tax_credit", {
        "year": 2023,
        "base": 200_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 200_000_000,
            "subsidiaries": [{
                "name": "NL Sub",
                "dividend": 50_000_000,
                "received_on": "2023-06-30",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 100_000_000,
                "sub_tax": 20_000_000,
                # participation_exempt 누락
            }],
        }],
        "months": 12,
    })
    assert "error" in r
    assert "예외" not in r.get("error", "")
    필요입력 = r.get("필요 입력", {})
    assert "countries[0].subsidiaries[0].participation_exempt" in 필요입력


def test_2023_date_based_ownership():
    """지분율 요건은 배당 받은 날(received_on) 기준.
    (a) year=2023, received_on="2022-12-20" → 2022년까지 25% 기준 → 지분 15% → 미충족(간접 0).
    (b) year=2023, received_on="2023-01-05" → 2023년부터 10% 기준 → 지분 15% → 충족(간접 계산).
    근거: 법 §57⑤(법률 19193, 부칙 제4조), vocab '간접외국납부세액' 적용 블록(부터~까지)."""
    # (a) 2022-12-20 수령 → 25% 기준 → 지분 15% → 미충족
    r_a = c("foreign_tax_credit", {
        "year": 2023,
        "base": 200_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 200_000_000,
            "subsidiaries": [{
                "name": "NL Sub",
                "dividend": 50_000_000,
                "received_on": "2022-12-20",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 100_000_000,
                "sub_tax": 20_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r_a
    sub_a = r_a["결과"]["국가별"][0]["외국자회사"][0]
    assert sub_a["요건충족"] is False
    assert sub_a["간접외국납부세액"] == 0

    # (b) 2023-01-05 수령 → 10% 기준 → 지분 15% → 충족
    r_b = c("foreign_tax_credit", {
        "year": 2023,
        "base": 200_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "네덜란드",
            "foreign_income": 200_000_000,
            "subsidiaries": [{
                "name": "NL Sub",
                "dividend": 50_000_000,
                "received_on": "2023-01-05",
                "ownership": 0.15,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 100_000_000,
                "sub_tax": 20_000_000,
                "participation_exempt": False,
            }],
        }],
        "months": 12,
    })
    assert "error" not in r_b
    sub_b = r_b["결과"]["국가별"][0]["외국자회사"][0]
    assert sub_b["요건충족"] is True
    assert sub_b["간접외국납부세액"] > 0


def test_2023_pe_missing_error_variant():
    """2023년 배당·participation_exempt 없음 → error(예외 아님) 재확인.
    지분율 요건은 충족하나 participation_exempt 누락으로 계산 자체가 거부됨.
    근거: 법 §57⑤(법률 19193), vocab '간접외국납부세액' 2023~ 적용."""
    r = c("foreign_tax_credit", {
        "year": 2023,
        "base": 100_000_000,
        "base_includes_grossup": False,
        "method": "세액공제",
        "countries": [{
            "country": "미국",
            "foreign_income": 100_000_000,
            "subsidiaries": [{
                "name": "US Sub",
                "dividend": 30_000_000,
                "received_on": "2023-03-15",
                "ownership": 0.20,
                "holding_months": 12,
                "resource_dev": False,
                "sub_income": 80_000_000,
                "sub_tax": 16_000_000,
                # participation_exempt 누락
            }],
        }],
        "months": 12,
    })
    assert "error" in r
    assert "참여" not in r.get("error", "") or "참여" in str(r.get("필요 입력", {}))
    필요입력 = r.get("필요 입력", {})
    assert "countries[0].subsidiaries[0].participation_exempt" in 필요입력


def test_all_tools_listed():
    """테스트14: foreign_tax_credit이 전체 도구 목록에 포함된다."""
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "foreign_tax_credit" in names
    # 기존 도구들도 여전히 등록되어 있는지 확인
    기존 = {"corporate_tax", "entertainment_limit", "deemed_interest", "other_income_aggregate"}
    assert 기존 <= names  # 기존 도구들이 사라지지 않았는지 확인
