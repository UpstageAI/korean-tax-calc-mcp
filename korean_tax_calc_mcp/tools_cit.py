"""퇴직급여충당금·퇴직연금충당금 세무조정(retirement_allowance_adjustment) 본문 — server.py에서 분리. 도구 등록(스키마·docstring·_guard)은 server.py의 얇은 래퍼가 맡는다."""
from . import vocab


def retirement_allowance_adjustment_impl(year, allowance, prior_disallowed, estimate, salary, succeeded_disallowed, conversion_fund, pension) -> dict:
    """server.retirement_allowance_adjustment의 본문(서명·설명은 그쪽 참조)."""
    from .server import _ok   # 순환 import 회피 — 호출 시점에 가져옴

    # ── 입력 정리 ──
    opening = int(allowance.get("opening", 0))
    closing = int(allowance.get("closing", 0))
    provision = int(allowance.get("provision", 0) or 0)
    paid_cash = int(allowance.get("paid_cash", 0) or 0)
    paid_pension = int(allowance.get("paid_pension", 0) or 0)
    other_increase = int(allowance.get("other_increase", 0) or 0)

    has_prov = provision > 0
    has_pension = pension is not None
    needs_estimate = has_prov or has_pension
    needs_salary = has_prov

    # ── 입력 누락 검사 ──
    missing = []
    if needs_estimate and (estimate is None or int(estimate.get("lump_sum", 0) or 0) == 0):
        missing.append("estimate.lump_sum — 기말 일시퇴직기준 추계액")
    if needs_salary and (salary is None or int(salary.get("total", 0) or 0) == 0):
        missing.append("salary.total — 당기 총급여액")
    if paid_pension > 0 and pension is None:
        missing.append("pension.prior_deducted — 세무상 퇴직연금충당금 기초잔액")
    if missing:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"input 누락: {', '.join(missing)}"],
                "필요 입력": missing}

    # ── 장부 증감 검증 ──
    calc_closing = opening + provision + other_increase - paid_cash - paid_pension
    if calc_closing != closing:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": [f"장부 증감 불일치: opening({opening:,}) + provision({provision:,}) + other_increase({other_increase:,}) − paid_cash({paid_cash:,}) − paid_pension({paid_pension:,}) = {calc_closing:,} ≠ closing({closing:,})"],
                "필요 입력": ["opening + provision + other_increase − paid_cash − paid_pension = closing 확인"]}

    # ── 어휘 규칙 ──
    rule_h = vocab.rule("퇴직급여충당금_한도", year)
    급여_비율 = rule_h.get("총급여_비율")
    적립비율 = rule_h.get("추계액_적립비율")
    if 급여_비율 is None:
        return {"error": "입력 확인 필요 — 계산하지 않음",
                "문제": ["vocab '퇴직급여충당금_한도'에 총급여_비율이 없음"],
                "필요 입력": ["vocab 확인"]}

    # ── 추정 추계액 ──
    lump_sum = int(estimate.get("lump_sum", 0) or 0) if estimate else 0
    actuarial = int(estimate.get("actuarial", 0) or 0) if estimate else 0
    추계액 = max(lump_sum, actuarial)

    # DC 전환자 설정 전 기계상 퇴직급여충당금 (pension 없으면 0)
    dc_transferred = int(pension.get("dc_transferred_allowance", 0) or 0) if has_pension else 0

    # ── 대상 총급여 ──
    총급여_전체 = int(salary.get("total", 0) or 0) if salary else 0
    dc_members = int(salary.get("dc_members", 0) or 0) if salary else 0
    not_eligible = int(salary.get("not_eligible", 0) or 0) if salary else 0
    대상_총급여 = 총급여_전체 - dc_members - not_eligible

    # ── 총급여 기준 한도 ──
    총급여기준_한도 = int(대상_총급여 * 급여_비율)

    # ── 추계액 기준 누적한도 ──
    # 누적한도 = max(일시퇴직, 보험수리) × 적립비율 + 퇴직금전환금 − 세무상 설정전 잔액(음수 0 처리 전)
    # 적립비율 적용 추계액 부분
    적립_추계액 = int(추계액 * 적립비율)
    # 세무상 설정전 잔액(아래에서 계산) 차감 전 임시값
    # 실제 계산시 세무상_설정전잔액을 먼저 구해야 함 — 순환 참조는 아님(세무상 설정전잔액은 당기 설정과 별개)
    # "세무상 설정전 잔액 = 기초 − 기초 부인누계 − (상계 중 세무상 잔액 사용분) + (other_increase − succeeded_disallowed)… 구체 산식은 어휘 처리"
    # 어휘 '처리'에 상세 산식이 없으므로 계산 규칙대로:
    # 세무상 설정전 잔액 = 기초 − 기초부인누계 − min(지급총액, max(0, 기초 − 기초부인누계)) + other_increase − succeeded_disallowed

    # 세무상 기초 잔액 = opening − prior_disallowed − dc(확정기여형 전환자 설정 전 충당금)
    세무_기초_잔액 = opening - prior_disallowed - dc_transferred

    # 지급액이 세무상 잔액 초과 여부
    # 운용자산 지급분 중 세무상 퇴직연금충당금과 상계되는 몫은 퇴직급여충당금을 쓰지 않는다(2026-10-30 수정: 종전엔 지급총액 전부를 세무상 잔액에서 뺐음)
    _pd_early = int(pension.get("prior_deducted", 0) or 0) if (pension is not None) else 0
    _book_paid_early = int(pension.get("book_paid", 0) or 0) if (pension is not None) else 0
    _연금감소총_early = min(_book_paid_early + paid_pension, _pd_early) if pension is not None else 0
    _연금상계_early = max(0, _연금감소총_early - min(_book_paid_early, _pd_early)) if pension is not None else 0
    지급총액 = paid_cash + paid_pension
    세무상_잔액_사용액 = min(paid_cash + (paid_pension - _연금상계_early), max(0, 세무_기초_잔액))

    # 세무상 설정전 잔액 (당기 설정 전)
    세무상_설정전잔액 = 세무_기초_잔액 - 세무상_잔액_사용액 + other_increase - succeeded_disallowed
    # 음수면 0 (한도 계산 시)
    세무_설정전잔액_하한 = max(0, 세무상_설정전잔액)

    # 누적한도 = 적립_추계액 + conversion_fund − 세무상 설정전잔액(음수 0 처리)
    누적한도 = 적립_추계액 + conversion_fund - 세무_설정전잔액_하한
    누적한도 = max(0, 누적한도)

    추계액기준_한도 = 누적한도
    누계액기준_한도 = 추계액기준_한도   # 판단·산식 문자열용 동의어

    # ── 퇴직급여충당금 한도 ──
    퇴직급여충당금_한도 = min(총급여기준_한도, 추계액기준_한도)

    # ── 한도초과액 ──
    한도초과액 = max(0, provision - 퇴직급여충당금_한도)

    # prior_deducted는 pension 블록 앞에서 미리 추출(pension 없으면 0) — 부인액_추인 계산에 필요
    _prior_deducted = int(pension.get("prior_deducted", 0) or 0) if has_pension else 0

    # ── 지급 상계 & 부인액 추인 ──
    # 1. 세무상 충당금(기초 − 기초 부인누계)과 지급 상계
    세무상_충당금_기초 = max(0, 세무_기초_잔액)
    # 2. 연금상계분을 뺀 과세 지급액만 세무상 충당금과 상계
    #    연금상계 = min(paid_pension, prior_deducted) (pension 있으면), 없으면 0
    # 2026-10-30: 위 _연금상계_early와 같은 식(장부 퇴직연금충당금 상계분 book_paid를 먼저 세무상 연금충당금에서 뺀 뒤 남는 몫) — CodeSolar 지적 반영
    연금상계 = _연금상계_early if has_pension else 0
    과세_지급액 = paid_cash + (paid_pension - 연금상계)
    # 3. 과세 지급액이 세무상 잔액을 초과하는 부분 = 부인액과 상계 → 손금산입△유보
    초과지급액 = max(0, 과세_지급액 - 세무상_충당금_기초)
    부인액_추인 = min(초과지급액, prior_disallowed)  # 부인누계(유보)와 상계 → 추인

    # ── 지급 후 세무상 잔액(설정 전) 재계산 ──
    # 실제 세무상 사용 후 잔액 = 세무상_설정전잔액(이미 computed) − 한도초과 반영 전
    # 한도초과는 provision에서 발생하므로 별도

    # ── 퇴직연금 조정일 때 ──
    # 연금충당금 상계액은 pension 유무와 무관하게 정의(pension 없으면 0)
    # 운용자산 지급분(paid_pension)은 먼저 세무상 연금충당금(prior_deducted)과 상계 →
    #     그 상계액만큼 퇴직연금충당금 손금불산입(유보) + 퇴직급여충당금 손금산입(△유보)
    #     초과분은 퇴직급여충당금 직접 지급으로 보아 부인누계(유보)와 상계 → 손금산입(△유보) 추인
    연금충당금_상계액 = 0
    연금초과 = max(0, paid_pension - 연금충당금_상계액)   # pension 없으면 paid_pension 전액
    퇴직연금_결과 = None
    if has_pension:
        asset_closing = int(pension.get("asset_closing", 0) or 0)
        prior_deducted = int(pension.get("prior_deducted", 0) or 0)
        book_provision = int(pension.get("book_provision", 0) or 0)

        # 운용자산 지급분 처리(2026-10-30 수정): 운용자산에서 지급된 금액은 장부에서 퇴직연금충당금과 상계한 몫(book_paid)과
        # 퇴직급여충당금과 상계한 몫(paid_pension)으로 나뉘지만, 세무상으로는 둘 다 먼저 세무상 퇴직연금충당금(prior_deducted)에서 빠진다.
        # book_paid 몫은 장부·세무가 같아 조정 없음, paid_pension 몫은 손금불산입(연금충당금)·손금산입(퇴직급여충당금)으로 바꾼다.
        book_paid = int(pension.get("book_paid", 0) or 0)
        세무_연금_감소총 = min(book_paid + paid_pension, prior_deducted)
        연금충당금_상계액 = max(0, 세무_연금_감소총 - min(book_paid, prior_deducted))
        연금초과 = max(0, paid_pension - 연금충당금_상계액)

        # 이미 손금산입한 부담금 = prior_deducted − 당기 세무상 감소 총액(장부 상계분 + 퇴직급여충당금 상계분)
        # (시행규칙 제24조②: 이미 손금산입한 부담금 = 누계 − 당기 수령·상계액)
        이미_손금산입한_부담금 = prior_deducted - 세무_연금_감소총

        # 기말 세무상 퇴직급여충당금(퇴직연금 반영 전)
        # DC 전환자 설정 전 충당금은 세무상 잔액에 그대로 남으므로 더해줌
        # 설정 후 세무상 잔액 = (dc 제외 설정전잔액) + min(provision, 한도) + dc
        세무상_퇴직급여충당금_기말 = 세무_설정전잔액_하한 + (provision - 한도초과액) + dc_transferred

        # DC 전환자 설정 전 기계상 퇴직급여충당금이 있으면 그만큼 차감(퇴직연금 한도 계산 시)
        # "추계액기준 연금한도 = 추계액 − 세무상 퇴직급여충당금 기말잔액(− dc_transferred_allowance 반영)"
        dc_조정_기말 = max(0, 세무상_퇴직급여충당금_기말 - dc_transferred)
        추계액기준_연금한도 = max(0, 추계액 - dc_조정_기말 - 이미_손금산입한_부담금)

        # 운용자산기준 연금한도 = max(0, asset_closing − 이미_손금산입한_부담금)
        운용자산기준_연금한도 = max(0, asset_closing - 이미_손금산입한_부담금)

        # 손금산입범위 = min(두 한도)
        손금산입범위 = min(추계액기준_연금한도, 운용자산기준_연금한도)
        손금산입범위 = max(0, 손금산입범위)

        # 결산 계상(book_provision)과 비교해 부족분 손금산입·△유보, 초과분 손금불산입·유보
        퇴직연금_납입_부족 = max(0, 손금산입범위 - book_provision)  # 손금산입·△유보
        퇴직연금_납입_초과 = max(0, book_provision - 손금산입범위)  # 손금불산입·유보

        # 세무상_퇴직연금충당금_기말 = 이미_손금산입한_부담금 + 당기 손금산입액
        # 당기 손금산입액 = max(0, 손금산입범위 − book_provision) = 퇴직연금_납입_부족
        세무상_퇴직연금충당금_기말 = 이미_손금산입한_부담금 + 퇴직연금_납입_부족

        퇴직연금_결과 = {
            "연금충당금_상계액": 연금충당금_상계액,
            "장부_연금충당금_상계(book_paid)": book_paid,
            "세무상_연금충당금_당기감소": 세무_연금_감소총,
            "이미_손금산입한_부담금": 이미_손금산입한_부담금,
            "추계액기준_연금한도": 추계액기준_연금한도,
            "운용자산기준_연금한도": 운용자산기준_연금한도,
            "퇴직연금_손금산입범위액": 손금산입범위,
            "퇴직연금_납입_부족": 퇴직연금_납입_부족,
            "퇴직연금_납입_초과": 퇴직연금_납입_초과,
            "세무상_퇴직연금충당금_기말": max(0, 세무상_퇴직연금충당금_기말),
        }

    # ── 세무조정 조립 ──
    settlements = []
    # 1. 한도초과(손금불산입·유보)
    if 한도초과액 > 0:
        settlements.append({"구분": "퇴직급여충당금 한도초과",
                            "조정": "손금불산입",
                            "금액": 한도초과액,
                            "소득처분": "유보",
                            "근거": "법인세법 제33조①·시행령 제60조①·②",
                            "이유": f"당기 설정액 {provision:,}원 > 한도 {퇴직급여충당금_한도:,}원 → 초과 {한도초과액:,}원 손금불산입(유보)"})
    # 2. 부인액 추인(손금산입·△유보)
    if 부인액_추인 > 0:
        settlements.append({"구분": "퇴직급여충당금(부인액 추인)",
                            "조정": "손금산입",
                            "금액": 부인액_추인,
                            "소득처분": "△유보",
                            "근거": "법인세법 제33조②·기본통칙 33-60…5",
                            "이유": f"지급 총액 {지급총액:,}원 중 퇴직연금충당금 상계 {연금상계:,}원을 뺀 {과세_지급액:,}원이 세무상 충당금 {세무상_충당금_기초:,}원을 넘는 {초과지급액:,}원 → 부인누계(유보)와 상계, {부인액_추인:,}원 추인(△유보)"})
    # 3. 퇴직연금 부족(손금산입·△유보) — 있으면
    if has_pension and 퇴직연금_결과:
        r = 퇴직연금_결과
        if r["퇴직연금_납입_부족"] > 0:
            settlements.append({"구분": "퇴직연금충당금",
                                "조정": "손금산입",
                                "금액": r["퇴직연금_납입_부족"],
                                "소득처분": "△유보",
                                "근거": "법인세법 제33조①·시행령 제44조의2④·시행규칙 제24조②",
                                "이유": f"손금산입범위 {r['퇴직연금_손금산입범위액']:,}원 − 결산 계상 {book_provision:,}원 = 부족 {r['퇴직연금_납입_부족']:,}원 → 신고조정 손금산입(△유보)"})
        if r["퇴직연금_납입_초과"] > 0:
            settlements.append({"구분": "퇴직연금충당금 한도초과",
                                "조정": "손금불산입",
                                "금액": r["퇴직연금_납입_초과"],
                                "소득처분": "유보",
                                "근거": "법인세법 제33조①·시행령 제44조의2④·시행규칙 제24조②",
                                "이유": f"결산 계상 {book_provision:,}원 > 손금산입범위 {r['퇴직연금_손금산입범위액']:,}원 → 초과 {r['퇴직연금_납입_초과']:,}원 손금불산입(유보)"})
        # 퇴직연금 지급 시 상계: 운용자산 지급분은 우선 연금충당금(prior_deducted)과 상계
        #   → 상계액만큼 퇴직연금충당금 손금불산입(유보) + 퇴직급여충당금 손금산입(△유보)
        #   → 남은 초과분은 퇴직급여충당금 직접 지급으로 보아 부인누계(유보)와 상계 → 추인
        if paid_pension > 0:
            if 연금충당금_상계액 > 0:
                settlements.append({"구분": "퇴직연금충당금(지급 상계)",
                                    "조정": "손금불산입",
                                    "금액": 연금충당금_상계액,
                                    "소득처분": "유보",
                                    "근거": "법인세법 제33조②·어휘 퇴직연금_지급(기본통칙 33-60…5)",
                                    "이유": f"퇴직연금운용자산에서 {paid_pension:,}원 지급, 그중 {연금충당금_상계액:,}원(min(지급액, prior_deducted {prior_deducted:,}))은 세무상 연금충당금과 상계 → 이미 손금산입(△유보)한 퇴직연금충당금 손금불산입(유보)"})
                settlements.append({"구분": "퇴직급여충당금(퇴직연금 지급 대체)",
                                    "조정": "손금산입",
                                    "금액": 연금충당금_상계액,
                                    "소득처분": "△유보",
                                    "근거": "법인세법 제33조②·어휘 퇴직연금_지급(기본통칙 33-60…5)",
                                    "이유": f"연금충당금 상계액 {연금충당금_상계액:,}원만큼 퇴직급여충당금과 상계 → 손금산입(△유보)"})


    # ── 소득처분별 합계 ──
    유보_합계 = sum(s["금액"] for s in settlements if s["소득처분"] == "유보")
    델타유보_합계 = sum(s["금액"] for s in settlements if s["소득처분"] == "△유보")
    손금불산입_합계 = sum(s["금액"] for s in settlements if s["조정"] == "손금불산입")
    손금산입_합계 = sum(s["금액"] for s in settlements if s["조정"] == "손금산입")
    익금산입_합계 = sum(s["금액"] for s in settlements if s["조정"] == "익금산입")
    소득금액_순영향 = 손금불산입_합계 + 익금산입_합계 - 손금산입_합계
    가산조정 = 손금불산입_합계 + 익금산입_합계
    차감조정 = 손금산입_합계

    처분별 = {}
    if 유보_합계 != 0:
        처분별["유보"] = 유보_합계
    if 델타유보_합계 != 0:
        처분별["△유보"] = 델타유보_합계

    result = {
        "소득처분별_합계": 처분별,
        "손금불산입_합계": 손금불산입_합계,
        "소득금액_순영향": 소득금액_순영향,
        "가산조정": 가산조정,
        "차감조정": 차감조정,
    }

    # ── 계산 키 재정의 ──
    # 퇴직급여충당금_상계 = (paid_cash + 연금초과) 중 세무상 충당금(기초 − 부인누계)과 실제 상계한 금액
    # 연금초과 = pension 없으면 paid_pension 전액, pension 있으면 paid_pension − 연금충당금_상계액
    과세_지급액 = paid_cash + 연금초과
    퇴직급여충당금_상계 = min(과세_지급액, max(0, 세무_기초_잔액))

    # 누적한도 = 추계액 × 적립비율 + 퇴직금전환금 (세무_설정전잔액 차감 전)
    누적한도_raw = 적립_추계액 + conversion_fund
    # 추계액을_기준으로_한도 = max(0, 누적한도 − 세무_설정전잔액)
    추계액을_기준으로_한도 = max(0, 누적한도_raw - 세무_설정전잔액_하한)
    # 퇴직급여충당금_한도 = min(총급여기준_한도, 추계액을_기준으로_한도)
    퇴직급여_한도 = min(총급여기준_한도, 추계액을_기준으로_한도)
    한도초과액 = max(0, provision - 퇴직급여_한도)

    calc = {
        "세무상_퇴직급여충당금_지급전잔액": 세무_설정전잔액_하한,
        "퇴직연금충당금_상계": 연금충당금_상계액,
        "퇴직급여충당금_상계": 퇴직급여충당금_상계,
        "부인액_추인": 부인액_추인,
        "세무상_설정전잔액": 세무_설정전잔액_하한,
        "대상_총급여": 대상_총급여,
        "총급여기준_한도": 총급여기준_한도,
        "추계액": 추계액,
        "추계액_적립비율": 적립비율,
        "누적한도": 누적한도_raw,
        "추계액기준_한도": 추계액을_기준으로_한도,
        "퇴직급여충당금_한도": 퇴직급여_한도,
        "세무상_퇴직급여충당금_기말": max(0, 세무_설정전잔액_하한 + min(provision, 퇴직급여_한도) + dc_transferred),
        "퇴직급여충당금_유보_기말": prior_disallowed + succeeded_disallowed + max(0, provision - 퇴직급여_한도) - 부인액_추인 - 연금충당금_상계액,
    }

    if 퇴직연금_결과:
        calc.update({
            "이미_손금산입한_부담금": 퇴직연금_결과["이미_손금산입한_부담금"],
            "추계액기준_연금한도": 퇴직연금_결과["추계액기준_연금한도"],
            "운용자산기준_연금한도": 퇴직연금_결과["운용자산기준_연금한도"],
            "퇴직연금_손금산입범위액": 퇴직연금_결과["퇴직연금_손금산입범위액"],
            "세무상_퇴직연금충당금_기말": 퇴직연금_결과["세무상_퇴직연금충당금_기말"],
            "퇴직연금_조정금액": 퇴직연금_결과["퇴직연금_납입_부족"] - 퇴직연금_결과["퇴직연금_납입_초과"],
        })

    근거_목록 = vocab.basis("퇴직급여충당금_한도", year)
    근거_문자열 = ", ".join(
        f"{b[0]} {b[1]} {b[2]}" + (f" {b[3]}" if b[3] else "")
        for b in 근거_목록
    )

    판단_목록 = [
        {"항목": "장부 증감 검증", "결론": "일치" if calc_closing == closing else "불일치",
         "근거": "기본통칙 33-60…5"},
        {"항목": "대상 총급여", "결론": f"{대상_총급여:,}원 (전체 {총급여_전체:,} − DC 설정자 {dc_members:,} − 지급대상 외 {not_eligible:,})",
         "근거": "법인세법 시행령 제60조①"},
        {"항목": "총급여 기준 한도", "결론": f"{총급여기준_한도:,}원 (= {대상_총급여:,} × {급여_비율*100:.0f}%)",
         "근거": "법인세법 시행령 제60조①"},
        {"항목": "추계액", "결론": f"{추계액:,}원 (일시퇴직 {lump_sum:,}원, 보험수리 {actuarial:,}원 중 큰 금액)",
         "근거": "법인세법 시행령 제60조②·제44조의2④"},
        {"항목": "추계액 적립비율", "결론": f"{적립비율*100:.0f}%",
         "근거": "법인세법 시행령 제60조②(연도별)"},
        {"항목": "추계액 기준 누적한도", "결론": f"{누계액기준_한도:,}원 (= {추계액:,} × {적립비율*100:.0f}% + 전환금 {conversion_fund:,} − 세무상 설정전 {세무_설정전잔액_하한:,})",
         "근거": "법인세법 시행령 제60조②·④"},
        {"항목": "퇴직급여충당금 한도", "결론": f"{퇴직급여충당금_한도:,}원 (= min(총급여기준 {총급여기준_한도:,}, 추계액기준 {누계액기준_한도:,}))",
         "근거": "법인세법 제33조①·시행령 제60조①·②"},
        {"항목": "한도초과", "결론": f"{한도초과액:,}원" if 한도초과액 > 0 else "없음",
         "근거": "법인세법 제33조①·시행령 제60조③"},
        {"항목": "퇴직금 지급 상계", "결론": (f"지급 {지급총액:,}원 = 퇴직연금충당금 상계 {연금충당금_상계액:,}원 + 퇴직급여충당금 상계 {calc['퇴직급여충당금_상계']:,}원"
                                            f"(세무상 기초잔액 {세무상_충당금_기초:,}원 범위) + 초과 {초과지급액:,}원 → 부인누계 추인 {부인액_추인:,}원"),
         "근거": "법인세법 제33조②·기본통칙 33-60…5"},
    ]

    if dc_members > 0 or dc_transferred > 0:
        판단_목록.append({"항목": "확정기여형 전환 회사",
            "결론": "확인 필요 — 전환 전 근무분 퇴직급여충당금(시행규칙 제31조②)이 장부에 남은 회사는 이 도구가 일부만 처리합니다. 처리: pension.dc_transferred_allowance로 받은 금액을 지급 상계·누적한도에서 떼어 둠. 처리하지 않음: ① 그 금액 계산(직전 사업연도말 퇴직급여충당금 누적액 × 확정기여형 설정자 추계액 비율) ② 확정기여형만 있고 확정급여형 퇴직연금이 없는 회사의 그 금액 입력 ③ 그 몫을 전환자에게 지급하거나 확정기여형으로 이전한 금액 ④ 그 몫과 관련된 부인누계 구분. 해당하면 결과를 세무 전문가가 확인해야 합니다.",
            "근거": "법인세법 시행규칙 제31조②·별지 제32호서식 작성방법 2~4"})

    if has_pension and 퇴직연금_결과:
        r = 퇴직연금_결과
        판단_목록.extend([
            {"항목": "이미 손금산입한 부담금", "결론": f"{r['이미_손금산입한_부담금']:,}원 (누계 {prior_deducted:,} − 연금충당금 상계액 {r['연금충당금_상계액']:,})",
             "근거": "법인세법 시행규칙 제24조②"},
            {"항목": "추계액 기준 연금한도", "결론": f"{r['추계액기준_연금한도']:,}원 (= 추계액 {추계액:,} − (기말 세무상 퇴직급여충당금 {calc['세무상_퇴직급여충당금_기말']:,} − DC전환 {dc_transferred:,}))",
             "근거": "법인세법 시행령 제44조의2④"},
            {"항목": "운용자산 기준 연금한도", "결론": f"{r['운용자산기준_연금한도']:,}원 (= 운용자산 기말잔액 {asset_closing:,} − 이미 손금산입한 부담금 {r['이미_손금산입한_부담금']:,})",
             "근거": "법인세법 시행규칙 별지 제33호서식 ⑨"},
            {"항목": "퇴직연금 손금산입범위", "결론": f"{r['퇴직연금_손금산입범위액']:,}원 (= min(추계액기준 {r['추계액기준_연금한도']:,}, 운용자산기준 {r['운용자산기준_연금한도']:,}))",
             "근거": "법인세법 시행규칙 별지 제33호서식 ⑩"},
            {"항목": "퇴직연금 결산 계상", "결론": f"{book_provision:,}원",
             "근거": "법인세법 시행령 제44조의2④"},
            {"항목": "퇴직연금 부족/초과", "결론": (f"부족 {r['퇴직연금_납입_부족']:,}원(손금산입·△유보)" if r['퇴직연금_납입_부족'] > 0 else
                                                      f"초과 {r['퇴직연금_납입_초과']:,}원(손금불산입·유보)" if r['퇴직연금_납입_초과'] > 0 else "일치"),
             "근거": "법인세법 시행령 제44조의2④·시행규칙 제24조②"},
        ])

    result_data = {"세무조정": settlements, **result}
    산식_str = (
        f"① 장부 증감: opening({opening:,}) + provision({provision:,}) + other_increase({other_increase:,}) "
        f"− paid_cash({paid_cash:,}) − paid_pension({paid_pension:,}) = closing({closing:,}) [일치]\n"
        f"② 세무상 기초 잔액 = opening − prior_disallowed" + (f" − dc(확정기여형 전환자 설정 전 충당금) = {opening:,} − {prior_disallowed:,} − {dc_transferred:,} = {세무_기초_잔액:,}" if dc_transferred > 0 else f" = {opening:,} − {prior_disallowed:,} = {세무_기초_잔액:,}") + "\n"
        f"③ 세무상 충당금 지급 상계: 지급액 {지급총액:,} − 퇴직연금충당금 상계 {연금충당금_상계액:,} = {paid_cash + 연금초과:,}원, min({paid_cash + 연금초과:,}, 세무상 잔액 {세무상_충당금_기초:,}) = {calc['퇴직급여충당금_상계']:,}원 사용\n"
        f"④ 부인액 추인: min(max(0, {paid_cash + 연금초과:,} − 세무상 잔액 {세무상_충당금_기초:,}), prior_disallowed {prior_disallowed:,}) = {부인액_추인:,}원\n"
        f"⑤ 대상 총급여 = {총급여_전체:,} − DC {dc_members:,} − 지급대상 외 {not_eligible:,} = {대상_총급여:,}원\n"
        f"⑥ 총급여 기준 한도 = {대상_총급여:,} × {급여_비율*100:.0f}% = {총급여기준_한도:,}원\n"
        f"⑦ 추계 추계액 = max(일시퇴직 {lump_sum:,}, 보험수리 {actuarial:,}) = {추계액:,}원\n"
        f"⑧ 추계액 기준 누적한도 = {추계액:,} × {적립비율*100:.0f}% + 전환금 {conversion_fund:,} = {calc['누적한도']:,}원 (세무상 설정전 잔액 차감 전)\n"
        f"⑨ 추계액을_기준으로_한도 = max(0, ⑧ {calc['누적한도']:,} − 세무상 설정전 {세무_설정전잔액_하한:,}) = {calc['추계액기준_한도']:,}원\n"
        f"⑩ 퇴직급여충당금 한도 = min(⑥ {총급여기준_한도:,}, ⑨ {calc['추계액기준_한도']:,}) = {calc['퇴직급여충당금_한도']:,}원\n"
        f"⑪ 한도초과 = max(0, provision {provision:,} − 한도 {calc['퇴직급여충당금_한도']:,}) = {한도초과액:,}원 → 손금불산입(유보)\n"
        + (f"⑫ 퇴직연금: 이미 손금산입 부담금 = {prior_deducted:,} − 연금충당금 상계액 {r['연금충당금_상계액']:,} = {r['이미_손금산입한_부담금']:,}원\n"
           f"    추계액을_기준으로 연금한도 = {추계액:,} − (기말 충당금 {calc['세무상_퇴직급여충당금_기말']:,} − DC전환 {dc_transferred:,}) = {r['추계액기준_연금한도']:,}원\n"
           f"    운용자산 기준 연금한도 = {asset_closing:,} − 이미 손금산입 {r['이미_손금산입한_부담금']:,} = {r['운용자산기준_연금한도']:,}원\n"
           f"    손금산입범위 = min({r['추계액기준_연금한도']:,}, {r['운용자산기준_연금한도']:,}) = {r['퇴직연금_손금산입범위액']:,}원\n"
           f"    부족 {r['퇴직연금_납입_부족']:,}원 → 손금산입(△유보), 초과 {r['퇴직연금_납입_초과']:,}원 → 손금불산입(유보)\n"
           f"    퇴직연금 지급 상계: {r['연금충당금_상계액']:,}원 → 퇴직연금충당금 손금불산입(유보) + 퇴직급여충당금 손금산입(△유보)\n"
           f"    퇴직연금 지급 초과분: {연금초과:,}원 → 퇴직급여충당금 직접 지급(손금산입·△유보)\n"
           if has_pension and r else "")
    )

    # ── 계산식_입력 (이름·값·설명 목록) ──
    기중지급_세무상 = paid_cash + paid_pension - 연금충당금_상계액
    계산식_입력_목록 = [
        {"이름": "장부기초", "값": opening, "설명": "장부상 퇴직급여충당금 기초잔액"},
        {"이름": "DC설정전", "값": dc_transferred, "설명": "확정기여형 전환자 설정 전 기계상 퇴직급여충당금 (pension 없으면 0)"},
        {"이름": "기초부인누계", "값": prior_disallowed, "설명": "기초 퇴직급여충당금 부인누계(유보)"},
        {"이름": "기중지급", "값": 기중지급_세무상, "설명": "기중 지급(세무상 퇴직급여충당금에서 지급한 몫: paid_cash + paid_pension − 연금충당금_상계액)"},
        {"이름": "퇴직금전환금", "값": conversion_fund, "설명": "국민연금 퇴직금전환금 기말잔액"},
        {"이름": "회사계상", "값": provision, "설명": "당기 퇴직급여충당금 회사 계상액"},
        {"이름": "장부기말", "값": closing, "설명": "장부상 퇴직급여충당금 기말잔액"},
        {"이름": "추계액_일시퇴직", "값": lump_sum, "설명": "기말 일시퇴직기준 추계액"},
        {"이름": "추계액_보험수리", "값": actuarial, "설명": "기말 보험수리기준 추계액"},
        {"이름": "추계액_적립비율", "값": 적립비율, "설명": "연도별 추계액 적립비율"},
        {"이름": "퇴직연금여부", "값": has_pension, "설명": "확정급여형 퇴직연금 유무"},
    ]
    if has_pension:
        연금_수령 = book_paid + paid_pension
        계산식_입력_목록.extend([
            {"이름": "연금충당금_기초", "값": prior_deducted, "설명": "세무상 퇴직연금충당금 기초잔액(이미 손금산입한 부담금 누계)"},
            {"이름": "연금_수령", "값": 연금_수령, "설명": "퇴직연금운용자산에서 지급 + 장부 퇴직연금충당금 상계분(book_paid + paid_pension)"},
            {"이름": "연금_회사계상", "값": book_provision, "설명": "결산에 계상한 퇴직연금충당금"},
            {"이름": "운용자산기말", "값": asset_closing, "설명": "퇴직연금운용자산 기말잔액"},
        ])
        asset_opening = int(pension.get("asset_opening", 0) or 0) if pension else 0
        deposited = int(pension.get("deposited", 0) or 0) if pension else 0
        has_asset_opening = pension.get("asset_opening") is not None if pension else False
        has_deposited = pension.get("deposited") is not None if pension else False
        if has_asset_opening:
            계산식_입력_목록.append({"이름": "운용자산기초", "값": asset_opening, "설명": "퇴직연금운용자산 기초잔액"})
            계산식_입력_목록.append({"이름": "운용자산납입", "값": asset_closing - asset_opening + 연금_수령, "설명": "운용자산 기말잔액 − 기초잔액 + 연금 수령"})
        elif has_deposited:
            계산식_입력_목록.append({"이름": "운용자산납입", "값": deposited, "설명": "당기 퇴직연금예치금 등 납입액"})
            계산식_입력_목록.append({"이름": "운용자산기초", "값": asset_closing - deposited + 연금_수령, "설명": "운용자산 기말잔액 − 납입액 + 연금 수령"})
        # 둘 다 없으면 운용자산기초·운용자산납입 미포함

    # ── 서식_표 ──
    서식_표 = {}
    if salary:
        서식_표["32_총급여"] = [{
            "계정명": "총급여",
            "총급여_인원": "",
            "총급여": 총급여_전체 - dc_members,
            "지급대상외_인원": "",
            "지급대상외": not_eligible,
            "지급대상_인원": "",
        }]

    return _ok(result_data, 근거_문자열, 계산=calc, 판단=판단_목록, 산식=산식_str,
               계산식_입력=계산식_입력_목록, 서식_표=서식_표)
