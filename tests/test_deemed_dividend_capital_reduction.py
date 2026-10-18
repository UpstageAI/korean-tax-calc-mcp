"""의제배당(감자·주식소각·퇴사·탈퇴·해산) 끝에서 끝까지 계산기 정답 테스트 (Claude 작성 2026-10-13, 검토 2026).
근거 조문: 법인세법 제16조①1호·4호 / 소득세법 제17조②1호·3호, 시행령 제14조①1호가목·③ / 시행령 제27조①1호가목·③.
손계산 사례는 각 테스트 주석에 계산 근거를 함께 기재한다.
"""
import asyncio, json
from korean_tax_calc_mcp.server import mcp


def c(n, a):
    return json.loads(asyncio.run(mcp.call_tool(n, a)).content[0].text)


# ── 사례 1: 개인·감자·자본준비금 비과세 무상주(단기소각 대상)·의제배당 발생 ──
# 근거: 소득세법 제17조②1호, 소득세법 시행령 제27조③(단기소각)
# 계산 (수정 1: 단기소각 대상 비과세 주식은 총평균에서 제외):
#   보유: 유상취득 10,000주×1,000원 + 비과세무상주(자본준비금) 5,000주(단기 대상) = 15,000주
#   결의일 2025-10-01, 2년 cutoff = 2023-10-01
#   → 2024-06-01 비과세무상주 5,000주: cutoff 이후 → 단기소각 대상 (자본준비금 → 개인은 포함)
#   평균단가: 기타 주식(유상 10,000주)만 기준 = 10,000,000 ÷ 10,000 = 1,000원
#   D=5,000, G=3,000
#   일반소각 3,000주 × 1,000원 = 3,000,000원
#   소멸주식 취득가액 = 0 + 3,000,000 = 3,000,000원
#   의제배당 = 15,000,000 − 3,000,000 = 12,000,000원
#   소각후: 15,000 − 8,000 = 7,000주, 장부가액 10,000,000 − 3,000,000 = 7,000,000원, 1주 1,000원
def test_personal_capital_reduction_with_short_term_burn():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-10-01",
        "acquisitions": [
            {"date": "2023-01-01", "shares": 10_000, "kind": "유상취득", "unit_cost": 1_000},
            {"date": "2024-06-01", "shares": 5_000, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 15_000_000,
        "cancelled_shares": 8_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 12_000_000         # 15,000,000 − 3,000,000
    assert res["소멸주식_취득가액"] == 3_000_000    # 3,000 × 1,000
    assert res["단기소각주식수"] == 5_000
    assert res["일반소각주식수"] == 3_000
    assert res["평균단가"] == 1_000.0               # 10,000,000 ÷ 10,000 = 1,000원
    assert res["소각후_보유주식수"] == 7_000
    assert res["소각후_1주당_장부가액"] == 1_000.0  # 7,000,000 ÷ 7,000 = 1,000원
    assert "소득세법 제17조②1호" in r["근거"]
    assert "소득세법 시행령 제27조" in r["근거"]    # 단기소각 근거 포함


# ── 사례 2: 개인·감자·2년 초과 + 주식발행초과금 → 단기소각 대상 아님 ──
# 근거: 소득세법 제17조②1호, 시행령 제27조③(2년 이내 제한), 제27조①(자본준비금만 단기소각 대상)
# 계산:
#   보유: 유상취득 5,000주×1,200원 + 비과세무상주(주식발행초과금) 4,000주 = 9,000주, 총취득원가 6,000,000원
#   결의일 2025-09-01, cutoff 2023-09-01
#   → 2023-06-01 비과세무상주 4,000주: cutoff 이전 → 대상 아님, 게다가 개인·주식발행초과금 → 제외
#   D=0, G=6,000
#   평균단가 = 6,000,000 ÷ 9,000 = 666원
#   일반소각 6,000주 × 666원 = 3,996,000원
#   의제배당 = 12,000,000 − 3,996,000 = 8,004,000원
#   소각후: 9,000 − 6,000 = 3,000주, 장부가액 6,000,000 − 3,996,000 = 2,004,000원, 1주 668원
def test_personal_capital_reserve_outside_two_year():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-09-01",
        "acquisitions": [
            {"date": "2022-01-01", "shares": 5_000, "kind": "유상취득", "unit_cost": 1_200},
            {"date": "2023-06-01", "shares": 4_000, "kind": "무상주_비과세", "source": "주식발행초과금"},
        ],
        "cash_received": 12_000_000,
        "cancelled_shares": 6_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 8_004_000         # 12,000,000 − 3,996,000
    assert res["단기소각주식수"] == 0               # 2년 초과 + 개인·주식발행초과금 → 제외
    assert res["일반소각주식수"] == 6_000
    assert res["평균단가"] == 666.0                 # 6,000,000 ÷ 9,000 = 666원
    assert res["소각후_보유주식수"] == 3_000
    assert res["소각후_1주당_장부가액"] == 668.0    # 2,004,000 ÷ 3,000 = 668원
    assert "소득세법 제17조②1호" in r["근거"]


# ── 사례 3: 법인·해산(보유 전부 소멸, 취소 주식 수 생략) ──
# 근거: 법인세법 제16조①4호, 법인세법 시행령 제13조2호(잔여재산가액 확정일)
# 계산:
#   보유: 유상취득 10,000주×1,000원 + 유상취득 10,000주×1,500원 = 20,000주, 총취득원가 25,000,000원
#   D=0, G=20,000
#   평균단가 = 25,000,000 ÷ 20,000 = 1,250원
#   소멸주식 취득가액 = 20,000 × 1,250 = 25,000,000원
#   받은대가 = 50,000,000원
#   의제배당 = 50,000,000 − 25,000,000 = 25,000,000원
#   소각후: 0주, 장부가액 0원
def test_corp_dissolution():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "법인",
        "event": "해산",
        "resolution_date": "2025-12-01",
        "acquisitions": [
            {"date": "2020-01-01", "shares": 10_000, "kind": "유상취득", "unit_cost": 1_000},
            {"date": "2021-01-01", "shares": 10_000, "kind": "유상취득", "unit_cost": 1_500},
        ],
        "cash_received": 50_000_000,
        "cancelled_shares": None,   # 퇴사·탈퇴·해산은 생략 → 보유 전부
    })
    assert "error" not in r
    res = r["결과"]
    assert res["소멸주식수"] == 20_000
    assert res["단기소각주식수"] == 0
    assert res["일반소각주식수"] == 20_000
    assert res["소멸주식_취득가액"] == 25_000_000   # 20,000 × 1,250
    assert res["의제배당금액"] == 25_000_000         # 50,000,000 − 25,000,000
    assert res["소각후_보유주식수"] == 0
    assert res["소각후_1주당_장부가액"] == 0.0
    assert "법인세법 제16조①4호" in r["근거"]


# ── 사례 4: 법인·주식소각·과세 무상주(액면가) + 비과세 단기 소각 혼합 ──
# 근거: 법인세법 제16조①1호, 법인세법 시행령 제14조①1호가목·③
# 계산 (수정 1: 단기소각 대상 비과세 주식은 총평균에서 제외):
#   보유: 유상취득 10,000주×800원 + 과세무상주 5,000주(액면가 500원) + 비과세무상주 3,000주(단기 대상)
#        = 18,000주, 기타 총취득원가 8,000,000 + 2,500,000 = 10,500,000원
#   결의일 2025-04-15, cutoff 2023-04-15
#   → 2024-09-01 비과세무상주 3,000주: cutoff 이후 → 단기소각 대상 (법인, 재원 무관)
#   기타 주식: 유상 10,000주 + 과세 5,000주 = 15,000주, 총취득원가 10,500,000원
#   평균단가 = 10,500,000 ÷ 15,000 = 700원
#   D=3,000, G=4,000
#   일반소각 4,000주 × 700원 = 2,800,000원
#   의제배당 = 18,000,000 − 2,800,000 = 15,200,000원
#   소각후: 18,000 − 7,000 = 11,000주, 장부가액 10,500,000 − 2,800,000 = 7,700,000원, 1주 700원
def test_corp_taxable_bonus_and_short_term_mix():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "법인",
        "event": "주식소각",
        "resolution_date": "2025-04-15",
        "acquisitions": [
            {"date": "2022-01-10", "shares": 10_000, "kind": "유상취득", "unit_cost": 800},
            {"date": "2023-06-01", "shares": 5_000, "kind": "무상주_과세"},
            {"date": "2024-09-01", "shares": 3_000, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 18_000_000,
        "cancelled_shares": 7_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 15_200_000         # 18,000,000 − 2,800,000
    assert res["단기소각주식수"] == 3_000
    assert res["일반소각주식수"] == 4_000
    assert res["소멸주식_취득가액"] == 2_800_000     # 4,000 × 700
    assert res["평균단가"] == 700.0                  # 10,500,000 ÷ 15,000 = 700원
    assert res["소각후_보유주식수"] == 11_000
    assert res["소각후_1주당_장부가액"] == 700.0     # 7,700,000 ÷ 11,000 = 700원
    assert "법인세법 제16조①1호" in r["근거"]
    assert "법인세법 시행령 제14조" in r["근거"]     # 단기소각 근거 포함


# ── 사례 5: 손실(의제배당 0) ──
# 근거: 소득세법 제17조②1호(Received amount < 취득가액 → 의제배당 아님, 손실은 의제배당 아님)
# 계산:
#   보유: 유상취득 5,000주×2,000원 = 5,000주, 총취득원가 10,000,000원
#   D=0, G=3,000
#   평균단가 = 10,000,000 ÷ 5,000 = 2,000원
#   소멸주식 취득가액 = 3,000 × 2,000 = 6,000,000원
#   받은대가 = 1,000,000원
#   의제배당 = max(0, 1,000,000 − 6,000,000) = 0원
def test_loss_no_deemed_dividend():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-08-01",
        "acquisitions": [
            {"date": "2023-01-01", "shares": 5_000, "kind": "유상취득", "unit_cost": 2_000},
        ],
        "cash_received": 1_000_000,
        "cancelled_shares": 3_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 0                    # 손실 → 0
    assert res["소멸주식_취득가액"] == 6_000_000      # 3,000 × 2,000
    assert res["소각후_보유주식수"] == 2_000
    assert res["소각후_1주당_장부가액"] == 2_000.0
    assert "소득세법 제17조②1호" in r["근거"]


# ── 사례 6: 처분 이력 포함(처분은 cutoff 이전 → 비례 처분 규칙 미적용) ──
# 근거: 소득세법 제17조②1호, 시행령 제27조③(처분은 보유 주식 수에서 차감, 단기소각 기간 중이면 주식 수 비례)
# 계산 (수정 1: 단기소각 대상 비과세 주식은 총평균에서 제외):
#   취득: 유상 10,000×1,000 + 비과세 5,000(2022-06, cutoff 이전→대상 아님) + (처분 3,000) + 비과세 2,000(2024-06, cutoff 이후→단기 대상)
#        = 보유 14,000주, 기타 총취득원가 10,000,000원, 기타 총주식수 10,000 + 5,000 = 15,000주(비과세 2,000주 제외)
#   평균단가 = 10,000,000 ÷ 15,000 = 666원 (666.66… → 666)
#   결의일 2025-11-01, cutoff 2023-11-01
#   → 2024-06-01 비과세 2,000주: 단기 대상 → D=2,000, G=4,000
#   일반소각 4,000주 × 666원 = 2,664,000원
#   의제배당 = 8,000,000 − 2,664,000 = 5,336,000원
#   소각후: 14,000 − 6,000 = 8,000주, 장부가액 10,000,000 − 2,664,000 = 7,336,000원, 1주 917원
def test_with_disposal_history():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "주식소각",
        "resolution_date": "2025-11-01",
        "acquisitions": [
            {"date": "2021-01-10", "shares": 10_000, "kind": "유상취득", "unit_cost": 1_000},
            {"date": "2022-06-01", "shares": 5_000, "kind": "무상주_비과세", "source": "자본준비금"},
            {"date": "2023-01-01", "shares": 3_000, "kind": "처분"},
            {"date": "2024-06-01", "shares": 2_000, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 8_000_000,
        "cancelled_shares": 6_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 5_336_000         # 8,000,000 − 2,664,000
    assert res["단기소각주식수"] == 2_000
    assert res["일반소각주식수"] == 4_000
    assert res["소멸주식_취득가액"] == 2_664_000    # 4,000 × 666
    assert res["평균단가"] == 666.0                 # 10,000,000 ÷ 15,000 = 666원
    assert res["소각후_보유주식수"] == 8_000        # 14,000 − 6,000
    assert res["소각후_1주당_장부가액"] == 917.0    # 7,336,000 ÷ 8,000 = 917원
    assert "소득세법 제17조②1호" in r["근거"]


# ── 사례 7: 단기소각 대상 주식만 소멸(G=0) ──
# 근거: 법인세법 시행령 제14조③(비과세 무상주를 먼저 소각한 것으로 봄, 취득가액 0)
# 계산:
#   보유: 유상 10,000×500 + 비과세 5,000 = 15,000주, 총취득원가 5,000,000원
#   D=3,000, G=0
#   평균단가 = 5,000,000 ÷ 15,000 = 333원
#   소멸주식 취득가액 = 3,000×0 + 0 = 0원
#   의제배당 = 3,000,000 − 0 = 3,000,000원
#   소각후: 15,000 − 3,000 = 12,000주
def test_all_short_term_burn():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "법인",
        "event": "감자",
        "resolution_date": "2025-12-01",
        "acquisitions": [
            {"date": "2024-01-01", "shares": 10_000, "kind": "유상취득", "unit_cost": 500},
            {"date": "2024-06-01", "shares": 5_000, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 3_000_000,
        "cancelled_shares": 3_000,   # 단기 대상(5,000주) 중 3,000주만 소멸
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 3_000_000          # 받은 금전 전액(취득가액 0)
    assert res["소멸주식_취득가액"] == 0
    assert res["단기소각주식수"] == 3_000
    assert res["일반소각주식수"] == 0
    assert res["소각후_보유주식수"] == 12_000
    assert "법인세법 제16조①1호" in r["근거"]


# ── 사례 8: 재산가액 포함(현금 외 재산) ──
# 근거: 소득세법 제17조②1호(금전 외 재산의 가액도 포함, 주식은 결의일 시가 기준)
# 계산:
#   보유: 유상 5,000×1,000 = 5,000주, 총취득원가 5,000,000원
#   D=0, G=3,000, 평균단가 1,000원, 소멸취득가액 3,000,000원
#   받은대가 = 2,000,000 + 3,000,000 = 5,000,000원
#   의제배당 = 5,000,000 − 3,000,000 = 2,000,000원
def test_with_property_value():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-07-01",
        "acquisitions": [
            {"date": "2023-01-01", "shares": 5_000, "kind": "유상취득", "unit_cost": 1_000},
        ],
        "cash_received": 2_000_000,
        "property_value": 3_000_000,    # 주식 시가 3,000,000원(결의일 기준)
        "cancelled_shares": 3_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 2_000_000          # (2,000,000+3,000,000) − 3,000,000
    assert res["받은대가"] == 5_000_000
    # 주의 키는 최상위(결과 밖) — property_value 포함 시 주의 문자열에 반영
    assert "재산" in str(r.get("주의", [])) or "재산가액" in str(r["결과"].get("산식", ""))
    assert "소득세법 제17조②1호" in r["근거"]


# ── 사례 9: par_value 누락(무상주_과세 있음) → error ──
def test_error_missing_par_value():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "법인",
        "event": "감자",
        "resolution_date": "2025-01-01",
        "acquisitions": [
            {"date": "2024-01-01", "shares": 1_000, "kind": "무상주_과세"},
        ],
        "cash_received": 1_000_000,
        "cancelled_shares": 1_000,
        # par_value 없음
    })
    assert "error" in r
    assert "par_value" in str(r.get("필요 입력", r.get("문제", [])))


# ── 사례 10: 결의일 이후 취득 → error ──
def test_error_after_resolution_date():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-05-01",
        "acquisitions": [
            {"date": "2025-06-01", "shares": 1_000, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 1_000_000,
        "cancelled_shares": 1_000,
        "par_value": 500,
    })
    assert "error" in r
    assert any("이후" in p for p in r.get("문제", []))


# ── 사례 11: 소멸 주식 수 > 보유 주식 수 → error ──
def test_error_cancelled_exceeds_held():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "주식소각",
        "resolution_date": "2025-03-01",
        "acquisitions": [
            {"date": "2024-01-01", "shares": 1_000, "kind": "유상취득", "unit_cost": 1_000},
        ],
        "cash_received": 2_000_000,
        "cancelled_shares": 2_000,   # 보유 1,000주 초과
        "par_value": 500,
    })
    assert "error" in r
    assert any("cancelled_shares" in p or "보유" in p for p in r.get("문제", []))


# ── 사례 12: 개인·주식소각·자본준비금 비과세(2년 이내) ──
# 근거: 소득세법 제17조②1호, 시행령 제27조①1호가목·③
# 계산 (수정 1: 단기소각 대상 비과세 주식은 총평균에서 제외):
#   보유: 유상 8,000×2,000 + 비과세(자본준비금) 4,000(단기 대상) = 12,000주, 기타 총취득원가 16,000,000원
#   결의일 2025-06-01, cutoff 2023-06-01
#   → 2024-05-01 비과세 4,000주: cutoff 이후 → 단기 대상 (자본준비금 → 개인 포함)
#   기타 주식: 유상 8,000주, 총취득원가 16,000,000원
#   평균단가 = 16,000,000 ÷ 8,000 = 2,000원
#   D=4,000, G=1,000
#   일반소각 1,000주 × 2,000원 = 2,000,000원
#   의제배당 = 10,000,000 − 2,000,000 = 8,000,000원
#   소각후: 12,000 − 5,000 = 7,000주, 장부가액 16,000,000 − 2,000,000 = 14,000,000원, 1주 2,000원
def test_personal_stock_buyback_short_term_capital_reserve():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "주식소각",
        "resolution_date": "2025-06-01",
        "acquisitions": [
            {"date": "2023-07-01", "shares": 8_000, "kind": "유상취득", "unit_cost": 2_000},
            {"date": "2024-05-01", "shares": 4_000, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 10_000_000,
        "cancelled_shares": 5_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 8_000_000          # 10,000,000 − 2,000,000
    assert res["단기소각주식수"] == 4_000
    assert res["일반소각주식수"] == 1_000
    assert res["소멸주식_취득가액"] == 2_000_000     # 1,000 × 2,000
    assert res["평균단가"] == 2_000.0                # 16,000,000 ÷ 8,000 = 2,000원
    assert res["소각후_보유주식수"] == 7_000         # 12,000 − 5,000
    assert res["소각후_1주당_장부가액"] == 2_000.0   # 14,000,000 ÷ 7,000 = 2,000원
    assert "소득세법 제17조②1호" in r["근거"]


# ── 신규 테스트 1: 단기소각 대상 비과세 주식은 총평균에서 제외 (fix 요청 1번 예시) ──
# 근거: 소득세법 제17조②1호, 시행령 제27조①1호가목·③
# 계산:
#   유상취득 4,000주×10,000원 + 무상주_과세 1,000주×액면 5,000원 + 비과세 500주(단기 대상, 취득가액 0)
#    = 기타 총취득원가 40,000,000 + 5,000,000 = 45,000,000원, 기타 총주식수 4,000 + 1,000 = 5,000주
#   평균단가 = 45,000,000 ÷ 5,000 = 9,000원 (비과세 500주는 분모에서 제외)
#   D=500(소각 대상 1,500주 중 먼저 소각), G=1,000
#   일반소각 1,000주 × 9,000원 = 9,000,000원
#   소멸주식 취득가액 = 0 + 9,000,000 = 9,000,000원
#   의제배당 = 15,000,000 − 9,000,000 = 6,000,000원
#   소각후 Holdings = 5,500 − 1,500 = 4,000주, 장부가액 45,000,000 − 9,000,000 = 36,000,000원, 1주 9,000원
def test_short_term_excluded_from_average():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-10-01",
        "acquisitions": [
            {"date": "2023-01-01", "shares": 4_000, "kind": "유상취득", "unit_cost": 10_000},
            {"date": "2023-06-01", "shares": 1_000, "kind": "무상주_과세"},
            {"date": "2024-06-01", "shares": 500, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 15_000_000,
        "cancelled_shares": 1_500,
        "par_value": 5_000,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 6_000_000          # 15,000,000 − 9,000,000
    assert res["소멸주식_취득가액"] == 9_000_000     # 1,000 × 9,000
    assert res["단기소각주식수"] == 500
    assert res["일반소각주식수"] == 1_000
    assert res["평균단가"] == 9_000.0                # 45,000,000 ÷ 5,000 = 9,000원
    assert res["소각후_보유주식수"] == 4_000         # 5,500 − 1,500
    assert res["소각후_1주당_장부가액"] == 9_000.0   # 36,000,000 ÷ 4,000 = 9,000원
    assert "소득세법 제17조②1호" in r["근거"]


# ── 신규 테스트 2: 해산·퇴사·탈퇴는 단기소각 특례 없음 + 전체 취득가액 (fix 요청 2번) ──
# 근거: 법인세법 제16조①4호, 법인세법 시행령 제13조2호
# 계산:
#   보유: 유상 10,000주×1,000원 + 비과세 500주(자본준비금, 단기 대상) = 10,500주
#   해산 → 단기소각 특례 없음, D=0
#   소멸주식 취득가액 = 전체 취득가액 = 10,000,000원 (평균·반올림 없이, 비과세 0 포함)
#   의제배당 = 30,000,000 − 10,000,000 = 20,000,000원
#   소각후 Holdings = 0주
def test_dissolution_no_short_term_exception():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "법인",
        "event": "해산",
        "resolution_date": "2025-12-01",
        "acquisitions": [
            {"date": "2022-01-01", "shares": 10_000, "kind": "유상취득", "unit_cost": 1_000},
            {"date": "2024-06-01", "shares": 500, "kind": "무상주_비과세", "source": "자본준비금"},
        ],
        "cash_received": 30_000_000,
        "cancelled_shares": None,   # 해산 → 보유 전부 소멸
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["소멸주식수"] == 10_500             # 10,000 + 500
    assert res["단기소각주식수"] == 0             # 해산 → 단기소각 특례 없음
    assert res["일반소각주식수"] == 10_500
    assert res["소멸주식_취득가액"] == 10_000_000 # 전체 취득가액(평균 아님)
    assert res["의제배당금액"] == 20_000_000       # 30,000,000 − 10,000,000
    assert res["소각후_보유주식수"] == 0
    assert res["소각후_1주당_장부가액"] == 0.0
    assert "법인세법 제16조①4호" in r["근거"]
    # 해산은 단기소각 근거(법인세법 시행령 제14조) 미포함
    assert "법인세법 시행령 제14조" not in r["근거"]


# ── 신규 테스트 3: 단기소각 기간 중 처분은 비례 처분 (fix 요청 3번) ──
# 근거: 소득세법 제17조②1호, 소득세법 시행령 제27조③ 후단(비례 처분)
# 계산:
#   결의: 2025-10-01, cutoff = 2023-10-01
#   유상취득 2022-01-01 10,000주×1,000원 (cutoff 이전 → 대상 아님)
#   비과세 2024-05-01 5,000주 (cutoff 이후 → 단기 대상)
#   처분 2024-08-01 3,000주 (단기소각 기간 중: cutoff~결의일 사이)
#     → 처분 직전 보유 = 15,000주, 처분 비율 = 3,000/15,000 = 0.2
#     → 단기소각 대상 5,000주 × 0.2 = 1,000주 감소 → 남은 단기 대상 4,000주
#     → 기타 주식 10,000주 × (1−0.2) = 8,000주
#     → 기타 총취득원가 = 10,000,000 × 0.8 = 8,000,000원
#   감자 5,000주: D = min(4,000, 5,000) = 4,000, G = 1,000
#   평균단가 = 8,000,000 ÷ 8,000 = 1,000원
#   소멸주식 취득가액 = 4,000×0 + 1,000×1,000 = 1,000,000원
#   의제배당 = 5,000,000 − 1,000,000 = 4,000,000원
#   소각후 Holdings = 12,000 − 5,000 = 7,000주, 장부가액 8,000,000 − 1,000,000 = 7,000,000원, 1주 1,000원
def test_disposal_within_short_term_period_pro_rata():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-10-01",
        "acquisitions": [
            {"date": "2022-01-01", "shares": 10_000, "kind": "유상취득", "unit_cost": 1_000},
            {"date": "2024-05-01", "shares": 5_000, "kind": "무상주_비과세", "source": "자본준비금"},
            {"date": "2024-08-01", "shares": 3_000, "kind": "처분"},
        ],
        "cash_received": 5_000_000,
        "cancelled_shares": 5_000,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 4_000_000          # 5,000,000 − 1,000,000
    assert res["소멸주식_취득가액"] == 1_000_000     # 1,000 × 1,000
    assert res["단기소각주식수"] == 4_000
    assert res["일반소각주식수"] == 1_000
    assert res["평균단가"] == 1_000.0                # 8,000,000 ÷ 8,000 = 1,000원
    assert res["소각후_보유주식수"] == 7_000         # 12,000 − 5,000
    assert res["소각후_1주당_장부가액"] == 1_000.0   # 7,000,000 ÷ 7,000 = 1,000원
    assert "소득세법 제17조②1호" in r["근거"]
    assert "소득세법 시행령 제27조" in r["근거"]
    # 처분 항목은 소각이 아니므로 일반_감소·단기소각_감소 모두 0
    dispos = [h for h in res["취득이력"] if h["구분"] == "처분"]
    assert len(dispos) == 1
    assert dispos[0]["일반_감소"] == 0
    assert dispos[0]["단기소각_감소"] == 0
    assert dispos[0]["취득가액_감소"] == 0


# 개인·감자·의제배당 발생 → 근거에 소득세법 제17조②1호 + 소득세법 시행령 제27조 모두 포함
# 근거: 소득세법 제17조②1호, 소득세법 시행령 제27조(취득가액 계산)
# 계산:
#   유상 2,000주×5,000원 = 총취득원가 10,000,000원, 보유 2,000주
#   D=0(소각 500주, 단기 대상 무상주 없음), G=500
#   평균단가 = 10,000,000 ÷ 2,000 = 5,000원
#   소멸취득가액 = 500 × 5,000 = 2,500,000원
#   받은대가 = 300만, 의제배당 = 3,000,000 − 2,500,000 = 500,000원
#   소각후: 1,500주, 장부가액 7,500,000원, 1주 5,000원
def test_personal_basis_always_two_articles():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-10-01",
        "acquisitions": [
            {"date": "2023-01-01", "shares": 2_000, "kind": "유상취득", "unit_cost": 5_000},
        ],
        "cash_received": 3_000_000,
        "cancelled_shares": 500,
        "par_value": 500,
    })
    assert "error" not in r
    assert "소득세법 제17조②1호" in r["근거"]
    assert "소득세법 시행령 제27조" in r["근거"]   # 단기소각 없어도 취득가액 계산 근거 포함


# 법인·감자·의제배당 0 → 최상위 주의[0]이 "의제배당 없음"으로 시작
# 근거: 법인세법 제16조①1호, 법인세법 시행령 제14조
# 계산:
#   유상 1,000주×20,000원 = 총취득원가 20,000,000원, 보유 1,000주
#   D=0(소각 100주, 단기 대상 무상주 없음), G=100
#   평균단가 = 20,000,000 ÷ 1,000 = 20,000원
#   소멸취득가액 = 100 × 20,000 = 2,000,000원
#   받은대가 = 150만, 의제배당 = max(0, 1,500,000 − 2,000,000) = 0원 (손실)
def test_corp_no_deemed_dividend_warning_top_level():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "법인",
        "event": "감자",
        "resolution_date": "2025-10-01",
        "acquisitions": [
            {"date": "2023-01-01", "shares": 1_000, "kind": "유상취득", "unit_cost": 20_000},
        ],
        "cash_received": 1_500_000,
        "cancelled_shares": 100,
        "par_value": 500,
    })
    assert "error" not in r
    res = r["결과"]
    assert res["의제배당금액"] == 0
    assert "주의" in r               # 최상위 키 (결과 밖)
    assert isinstance(r["주의"], list)
    assert len(r["주의"]) >= 1
    assert r["주의"][0].startswith("의제배당 없음")


# 개인·감자·단기소각기간 내 비과세 무상주 + source 없음 → error, 필요 입력에 "source"
# 근거: 소득세법 제17조②1호, 소득세법 시행령 제27조③
# 계산: 개인 주주는 비과세 무상주 재원(주식발행초과금·자본준비금·재평가적립금)에 따라 단기소각 포함/제외가 결정되므로 source 필수
def test_personal_short_term_bonus_missing_source_error():
    r = c("deemed_dividend_capital_reduction", {
        "shareholder_type": "개인",
        "event": "감자",
        "resolution_date": "2025-06-30",
        "acquisitions": [
            {"date": "2024-01-01", "shares": 1_000, "kind": "유상취득", "unit_cost": 10_000},
            {"date": "2024-10-01", "shares": 100, "kind": "무상주_비과세"},   # source 없음 → 오류
        ],
        "cash_received": 10_000_000,
        "cancelled_shares": 50,
        "par_value": 500,
    })
    assert "error" in r
    필요 = r.get("필요 입력", [])
    assert any("source" in s for s in 필요)
