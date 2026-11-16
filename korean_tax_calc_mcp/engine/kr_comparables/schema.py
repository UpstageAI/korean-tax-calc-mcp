"""후보 프로필 표준 열과 값 상태. Claude 작성(2026-11-16).

값 하나 = {"value": 숫자·참거짓·None, "status": 상태, "evidence": {"rcept_no", "account", "sentence"}, "note": 문자열}
상태
- 확보: 원문에서 값을 읽음
- 불명-없음: 계정·행이 원문에 없음을 확인(비교에서는 0 또는 '없음'으로 다룸 — 예: 재무상태표에 재고 계정 없음, 판관비 내역에 광고선전비 없음)
- 불명-못찾음: 원문에서 찾지 못함(0인지 모름 — 비교에서 '불명')
"""
STATUS_OK = "확보"
STATUS_NONE = "불명-없음"
STATUS_UNKNOWN = "불명-못찾음"
STATUSES = (STATUS_OK, STATUS_NONE, STATUS_UNKNOWN)

# 매출 구성 6갈래(매출 행 분류 칸)
MIX_CATEGORIES = {
    "product": "제품(직접·위탁 제조한 재화)",
    "merchandise": "상품(사서 되파는 재화)",
    "service": "용역(SI·컨설팅·유지보수·공사·운영 대행·임대 등)",
    "sw_license": "SW·라이선스(소프트웨어·게임·솔루션 판매·사용료, SaaS, 로열티)",
    "platform_fee": "플랫폼·중개수수료(플랫폼·결제·중개 수수료, 광고 매출)",
    "other": "기타",
}

# 후보 프로필 표준 열(회사·연도별 한 행) — 키: 설명
PROFILE_FIELDS = {
    "company_id": "회사 고유번호(OpenDART corp_code)",
    "company_name": "회사명",
    "listed": "상장 여부",
    "industry_code": "업종 코드(KSIC, 2~5자리 섞임)",
    "year": "사업연도",
    "fs_basis": "재무제표 기준(별도 우선 / 연결)",
    "rcept_no": "근거 공시 접수번호",
    **{f"mix_{k}": f"매출 구성 비중 — {v}" for k, v in MIX_CATEGORIES.items()},
    "mix_coverage": "매출 구성 커버리지(분류된 행 합계 ÷ 손익계산서 매출, 0.8~1.2만 비교에 씀)",
    "inv_to_sales": "재고자산 ÷ 매출",
    "raw_material_inv": "원재료·재공품 재고 유무(제조 신호)",
    "ppe_ratio": "유형자산 ÷ 자산총계",
    "intang_ratio": "무형자산 ÷ 자산총계",
    "rnd_ratio": "연구개발비 ÷ 매출",
    "advert_ratio": "광고선전비·판매촉진비 ÷ 매출",
    "ar_to_sales": "매출채권 ÷ 매출",
    "wc_ratio": "운전자본(매출채권 + 재고 − 매입채무) ÷ 매출",
    "related_sales_ratio": "특수관계자 매출 ÷ 매출(감사보고서 주석)",
    "related_purchase_ratio": "특수관계자 매입 ÷ 매출원가(없으면 매출)(감사보고서 주석)",
    "sga_ratio": "판매비와관리비 ÷ 매출",
    "business_desc": "사업 설명 원문(상장: 사업의 개요, 비상장: 감사보고서 주석 회사 개요) — 품목 키워드 대조용",
    "max_shareholder_pct": "최대주주 지분율 %(상장, 최대주주 현황)",
    "owner_pct": "최대주주·지배기업 지분율 %(비상장, 감사보고서 주석 주주 현황·지배기업 문장 — 근거 문장 포함, 지분만으로 제외하지 않음)",
    "loss_years": "분석 연도 중 영업손실 연도 수(note에 'n년 중 k년')",
    "control_signals": "실질 지배 신호 문장 [{kind: 임원 겸직|지배기업|유의적 영향력|자금 대여·보증, sentence}] — 참고, 법정 특수관계 판정 아님",
    "major_label": "대분류 꼬리표(제조·유통·서비스·무형자산 — 설명용, 판정에 쓰지 않음)",
}
VALUE_FIELDS = [k for k in PROFILE_FIELDS if k not in ("company_id", "company_name", "listed", "industry_code", "year", "fs_basis", "rcept_no", "major_label")]


def value(v=None, status=None, rcept_no=None, account=None, sentence=None, note=""):
    """값 하나를 표준 형식으로. status를 주지 않으면 v가 None이면 불명-못찾음, 아니면 확보."""
    if status is None:
        status = STATUS_UNKNOWN if v is None else STATUS_OK
    if status not in STATUSES:
        raise ValueError(f"status는 {STATUSES} 중 하나")
    if status == STATUS_OK and v is None:
        raise ValueError("확보 상태에는 값이 있어야 함")
    ev = {k: x for k, x in (("rcept_no", rcept_no), ("account", account), ("sentence", sentence)) if x}
    return {"value": v, "status": status, "evidence": ev, "note": note}


def empty_profile(**ident):
    """식별 열만 채운 빈 프로필(값 칸은 모두 불명-못찾음)."""
    p = {k: ident.get(k) for k in ("company_id", "company_name", "listed", "industry_code", "year", "fs_basis", "rcept_no", "major_label")}
    for k in VALUE_FIELDS:
        p[k] = value()
    return p


def validate_profile(p):
    """표준 열 확인 — 모르는 열·잘못된 상태를 오류 목록으로."""
    errs = []
    for k in p:
        if k not in PROFILE_FIELDS:
            errs.append(f"모르는 열: {k}")
    for k in VALUE_FIELDS:
        x = p.get(k)
        if x is None:
            continue
        if not isinstance(x, dict) or "status" not in x:
            errs.append(f"{k}: 값 형식은 value()로")
        elif x["status"] not in STATUSES:
            errs.append(f"{k}: 상태 '{x['status']}'")
    return errs
