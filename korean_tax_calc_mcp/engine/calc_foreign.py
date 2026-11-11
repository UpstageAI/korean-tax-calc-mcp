"""해외직접투자 외국환 신고·사후관리·세무 연결 판정 (외국환거래법 제18조, 시행령 제8조, 외국환거래규정 제9-5조·제9-6조·제9-9조, 국조법 제58조).

0.29.0 신규 도구. 뷰티 브랜드의 해외법인 설립·대여·증자·청산 시나리오에서 외국환 신고 의무와 세무(국조법 해외직접투자명세, 법인세 손금) 연결을 함께 본다.
"""
from datetime import date

from .calc_deadline import add_months, month_end_plus

_EVENT_TYPES = frozenset({
    "신설출자", "증액출자", "지분양수", "유보금증자", "금전대여", "임원파견",
    "지점설치", "지분매각", "청산", "내용변경",
})


def _fmt(d: date) -> str:
    return d.isoformat()


def _is_fdi(event: str, ownership_ratio_after: float | None,
            loan_term_months: int | None, financial_business: bool) -> tuple[bool, str]:
    """해외직접투자 해당 여부(시행령 제8조)."""
    if financial_business:
        return False, "금융·보험업은 제9-10조에 따라 별도(한국은행 등) — 이 도구 범위 밖"
    if event == "임원파견":
        return True, "임원파견을 수반하므로 시행령 제8조 해외직접투자 해당"
    if event == "지점설치":
        return True, "지점 설치비·영업기금 송금 — 시행령 제8조②1호 해당"
    if event == "금전대여":
        if loan_term_months is None:
            return False, "금전대여 이벤트인데 loan_term_months 없음"
        if loan_term_months >= 12:
            return True, "기투자 법인에 1년 이상 대여 — 시행령 제8조 해외직접투자 해당"
        return False, "1년 미만 대여는 해외직접투자 아님 — 다른 자본거래 신고 검토"
    if ownership_ratio_after is not None and ownership_ratio_after >= 0.10:
        return True, f"출자 지분 {ownership_ratio_after:.0%} 이상 — 시행령 제8조 해외직접투자 해당"
    if ownership_ratio_after is not None and ownership_ratio_after < 0.10:
        return False, f"지분 {ownership_ratio_after:.0%} 미만으로 해외직접투자 요건 미충족(임원파견·기술제공·매매계약 등 관계 수립 없으면 해당 아님)"
    if event in {"신설출자", "증액출자"}:
        return False, "출자 이벤트인데 ownership_ratio_after 없이 지분 요건 판정 불가"
    return False, "해외직접투자 요건 미충족"


def fx_rule(d: date) -> dict:
    """외국환거래규정 제9-5조·제9-9조의 날짜별 규정(기획재정부 고시, 법제처 등록 연혁 2015~2026 전 판을 대조 — 2026-11-11).
    - 유보금(자체이익유보금·자본잉여금) 증액투자: 2019.5.2.까지 '거주자가 최대주주가 아닌 경우'만 사후보고(기한 규정 없음),
      2019.5.3.(제2019-12호)부터 조건 없이 사후보고(기한 규정 없음), 2023.7.4.(제2023-26호)부터 거래일부터 3개월 이내.
    - 거주자로부터 지분 양수: 2023.7.3.까지 신고(사전), 2023.7.4.부터 3개월 이내 사후보고.
    - 누적 투자금액 미화 50만불 이내: 2023.7.3.까지 지급일부터 1개월 이내 사후보고, 2023.7.4.~2025.2.9. 3개월 이내, 2025.2.10.(제2025-4호) 삭제.
    - 신고 내용 변경: 2017.12.31.까지 변경신고(사전, 일부 사유만 3개월 사후보고), 2018.1.1.(제2017-40호)부터 변경사유 발생 후 3개월 이내 보고(제9-5조②),
      2023.7.4.부터 변경사유가 발생한 회계기간 종료 후 5월 이내(제9-9조①8호).
    - 다른 거주자에게 지분 매각: 2018.1.1.부터 즉시 보고, 2021.6.18.(제2021-11호)부터 7영업일 이내, 2022.1.3.(제2021-37호)부터 3개월 이내
      (2023.7.4.부터 제9-9조①9호). 2017.12.31.까지는 따로 정한 문구 없음(변경신고 대상).
    - 연간사업실적보고서(제9-9조①5호, 부동산관련업 외): 면제 가능·현지법인 투자현황표 갈음 기준이
      2018.12.31.까지 50만·100만불, 2019.1.1.(제2018-28호)부터 100만·200만불, 2022.1.3.부터 200만·300만불, 2025.2.10.부터 '300만불 초과만 대상'."""
    return {
        "retained": "최대주주 아닌 경우만" if d < date(2019, 5, 3) else "사후보고" if d < date(2023, 7, 4) else "3개월",
        "transfer_post": d >= date(2023, 7, 4),
        "small": "1개월" if d < date(2023, 7, 4) else "3개월" if d < date(2025, 2, 10) else None,
        "change": "변경신고" if d < date(2018, 1, 1) else "3개월" if d < date(2023, 7, 4) else "회계기간 후 5월",
        "sale": None if d < date(2018, 1, 1) else "즉시" if d < date(2021, 6, 18) else "7영업일" if d < date(2022, 1, 3) else "3개월",
        "sale_basis": "제9-5조②" if d < date(2023, 7, 4) else "제9-9조① 제9호",
        "annual": ((500_000, 1_000_000) if d < date(2019, 1, 1) else (1_000_000, 2_000_000) if d < date(2022, 1, 3)
                   else (2_000_000, 3_000_000) if d < date(2025, 2, 10) else (3_000_000, None)),
    }


_DOCS = ["사업계획서(자금조달·운용계획)", "신용정보 채무불이행 미등록 증빙", "조세체납 없음 증빙", "기타 필요 서류"]
_SMALL_EVENTS = {"신설출자", "증액출자", "지분양수", "금전대여", "지점설치"}


def _reporting_deadline(event: str, event_date: date, paid_in: bool,
                        ownership_ratio_after: float, loan_term_months: int | None,
                        counterparty_resident: bool, cumulative_usd: float,
                        fiscal_year_end: date, main_bank_type: str, largest_shareholder: bool | None = None) -> dict:
    """신고 구분·기한·서류(규정 제9-5조·제9-6조·제9-9조) — 이벤트 날짜의 규정(fx_rule)으로."""
    fdi, _ = _is_fdi(event, ownership_ratio_after, loan_term_months, False)
    if not fdi:
        return {"구분": "해당없음", "기관": "", "기한": "", "서류": []}
    R = fx_rule(event_date)

    def post(due, 비고):
        return {"구분": "사후보고", "기관": main_bank_type, "기한": due, "서류": list(_DOCS), "비고": 비고}

    if event == "유보금증자":
        if R["retained"] == "3개월":
            return post(_fmt(add_months(event_date, 3)), "거래가 있은 날부터 3개월 이내(제9-5조② 제2호)")
        if R["retained"] == "사후보고":
            return post("사후(기한 규정 없음)", "유보금·자본잉여금 증액투자는 사후에 보고할 수 있음 — 2023.7.3.까지는 기한을 정한 문구 없음(제9-5조① 단서)")
        if largest_shareholder is False:
            return post("사후(기한 규정 없음)", "2019.5.2.까지는 거주자가 최대주주가 아닌 경우에만 사후보고(제9-5조① 단서)")
        return {"구분": "사전신고", "기관": main_bank_type, "기한": "거래 전(사전)", "서류": list(_DOCS),
                "비고": ("2019.5.2.까지 유보금 증액투자의 사후보고는 거주자가 최대주주가 아닌 경우만(제9-5조① 단서)"
                        + (" — largest_shareholder 미입력이라 사전신고로 봄" if largest_shareholder is None else " — 최대주주라 사전신고"))}
    if event == "지분양수" and counterparty_resident and R["transfer_post"]:
        return post(_fmt(add_months(event_date, 3)), "거주자로부터 지분 양수 — 거래가 있은 날부터 3개월 이내(제9-5조② 제1호, 2023.7.4. 이후)")
    # 금융·보험업은 사전신고라도 별도 안내
    out = {"구분": "사전신고", "기관": main_bank_type, "기한": "거래 전(사전)", "서류": list(_DOCS)}
    # 누적 투자금액 미화 50만불 이내: 사후보고를 '할 수 있다'(선택) — 기본 답은 사전신고로 두고 선택지를 따로 표시
    if event in _SMALL_EVENTS and cumulative_usd <= 500_000 and R["small"]:
        n = 1 if R["small"] == "1개월" else 3
        out["사후보고_가능"] = {"기한": _fmt(add_months(event_date, n)),
                           "기준": f"{'투자금 지급일' if n == 1 else '거래가 있은 날'}부터 {n}개월 이내",
                           "근거": f"누적 투자금액 미화 50만불 이내 — {'제9-5조① 단서(2023.7.3.까지 1개월)' if n == 1 else '제9-5조② 제3호(2023.7.4.~2025.2.9. 3개월)'}"}
    if event == "지분양수" and counterparty_resident:
        out["비고"] = "거주자로부터 지분 양수의 3개월 사후보고는 2023.7.4. 이후 — 그 전은 신고(사전) 대상(제9-5조①)"
    return out


def _aftercare_schedule(event: str, event_date: date, paid_in: bool,
                        cumulative_usd: float, ownership_ratio_after: float,
                        loan_term_months: int | None,
                        counterparty_resident: bool, recovered_usd: float | None,
                        fiscal_year_end: date) -> list[dict]:
    """사후관리 보고서 일정(규정 제9-9조①)."""
    sched = []
    fdi, _ = _is_fdi(event, ownership_ratio_after, loan_term_months, False)

    # 1호 외화증권취득보고서: 납입·대여 후 6월 이내 (paid_in 일 때)
    if paid_in and fdi and event in {"신설출자", "증액출자", "지분양수", "유보금증자", "금전대여"}:
        sched.append({
            "보고서": "외화증권취득보고서",
            "기한": _fmt(add_months(event_date, 6)),
            "근거": "제9-9조① 제1호",
        })

    # 4호 송금(투자)보고서: 즉시
    if fdi and event in {"신설출자", "증액출자", "지분양수", "유보금증자", "지점설치"}:
        sched.append({
            "보고서": "송금보고서",
            "기한": "즉시",
            "근거": "제9-9조① 제4호",
        })

    # 5호 연간사업실적보고서: 회계기간 종료 후 5월 이내. 면제 가능·투자현황표 갈음 기준은 제출기한 당시 규정(fx_rule)
    if fdi:
        due = month_end_plus(fiscal_year_end, 5)
        exempt_cap, table_cap = fx_rule(due)["annual"]
        row = {"보고서": "연간사업실적보고서", "근거": "제9-9조① 제5호"}
        if table_cap is None:                                   # 2025.2.10. 이후: 투자금액 합계 300만불 초과만 대상
            row["기한"] = _fmt(due) if cumulative_usd > exempt_cap else "대상 아님"
        elif cumulative_usd > table_cap:
            row["기한"] = _fmt(due)
        elif cumulative_usd > exempt_cap:
            row["기한"] = _fmt(due)
            row["비고"] = f"투자금액 합계 미화 {table_cap // 10_000:,}만불 이하 — 현지법인 투자현황표로 갈음할 수 있음(부동산관련업 제외)"
        else:
            row["기한"] = "면제 가능"
            row["비고"] = (f"투자금액 합계 미화 {exempt_cap // 10_000:,}만불 이하 — 신고기관의 장이 제출을 면제할 수 있음(부동산관련업 제외). "
                         f"면제받지 못하면 {_fmt(due)}까지")
        if fx_rule(fiscal_year_end)["annual"] != (exempt_cap, table_cap):
            row["주의"] = "회계기간 종료일과 제출기한 사이에 기준 금액이 개정됨 — 제출기한 당시 규정으로 판단(부칙에 적용례 없음, 신고기관 확인)"
        sched.append(row)

    # 6호 청산보고서: 청산 이벤트 → 회수 즉시
    if event == "청산":
        sched.append({
            "보고서": "청산보고서",
            "기한": "즉시",
            "근거": "제9-9조① 제6호, 제9-6조",
        })

    R = fx_rule(event_date)
    # 신고 내용 변경: 2023.7.4.부터 회계기간 종료 후 5월(제9-9조①8호) / 2018.1.1.~2023.7.3. 변경사유 발생 후 3개월(제9-5조②) / 그 전 변경신고(사전)
    if event == "내용변경" and fdi:
        if R["change"] == "회계기간 후 5월":
            sched.append({"보고서": "신고 내용 변경 보고서", "기한": _fmt(month_end_plus(fiscal_year_end, 5)), "근거": "제9-9조① 제8호"})
        elif R["change"] == "3개월":
            sched.append({"보고서": "신고 내용 변경 보고", "기한": _fmt(add_months(event_date, 3)), "근거": "제9-5조②(2018.1.1.~2023.7.3.)"})
        else:
            sched.append({"보고서": "변경신고", "기한": "변경 전(사전)", "근거": "제9-5조②(2017.12.31.까지)",
                          "비고": "상호·대표자·소재지 변경, 자회사·손자회사 지분율 변경 등 일부 사유는 변경사유 발생 후 3개월 이내 사후보고"})

    # 다른 거주자에게 지분 매각: 2018.1.1. 즉시 → 2021.6.18. 7영업일 → 2022.1.3. 3개월(2023.7.4.부터 제9-9조①9호)
    if event == "지분매각" and counterparty_resident:
        if R["sale"] == "3개월":
            sched.append({"보고서": "지분매각보고", "기한": _fmt(add_months(event_date, 3)), "근거": R["sale_basis"]})
        elif R["sale"] in ("즉시", "7영업일"):
            sched.append({"보고서": "지분매각보고", "기한": "즉시" if R["sale"] == "즉시" else "7영업일 이내", "근거": "제9-5조② 단서"})
        else:
            sched.append({"보고서": "변경신고", "기한": "변경 전(사전)", "근거": "제9-5조②(2017.12.31.까지)",
                          "비고": "지분 매각 보고를 따로 정한 문구 없음 — 신고 내용 변경으로 변경신고 대상"})

    return sched


def _tax_connection(event: str, fdi: bool, ownership_ratio_after: float,
                    event_date: date, fiscal_year_end: date,
                    loan_term_months: int | None) -> dict:
    """세무 연결(국조법 제58조, 법인46012-3838, 법인46012-1986)."""
    안내 = []
    if fdi:
        # 국조법 제58조: 사업연도 종료일 속하는 달 말일부터 6개월
        기한 = month_end_plus(fiscal_year_end, 6)
        안내.append(f"국조법 제58조 해외직접투자명세등 — 기한: {기한.isoformat()}(사업연도 종료일 속하는 달 말일 + 6개월)")
    if event == "청산":
        안내.append("회수 잔여재산 없음이 확인되면 주식가액 청산일 사업연도 손금(법인46012-3838) — 회수 가능 재산을 남기고 청산 보고하면 손금 부인·가지급금 위험")
    if event == "금전대여" and loan_term_months is not None and loan_term_months >= 12:
        안내.append("신고수리된 대여는 업무무관가지급금 아님(법인46012-1986), 인정이자는 별도(deemed_interest)")
    return {"해외직접투자명세_기한": _fmt(month_end_plus(fiscal_year_end, 6)) if fdi else "",
            "안내": 안내}


def foreign_exchange_reporting(
    event: str,
    ownership_ratio_after: float | None = None,
    loan_term_months: int | None = None,
    amount_usd: float = 0,
    cumulative_usd: float | None = None,
    main_bank_type: str = "지정은행",
    financial_business: bool = False,
    event_date: str = "",
    fiscal_year_end: str = "",
    counterparty_resident: bool = False,
    paid_in: bool = True,
    recovered_usd: float | None = None,
    largest_shareholder: bool | None = None,
) -> dict:
    """해외직접투자 외국환 신고·사후보고·청산 판정. 외국환거래법 제18조·시행령 제8조·외국환거래규정 제9-5조·제9-6조·제9-9조, 국조법 제58조.
    규정은 이벤트 날짜의 판으로(fx_rule) — 2016.1.1.~2026.12.31.만 지원.

    이벤트 종류(event)가 허용값 밖이면 ValueError(호출부에서 {"error":"입력 확인 필요 — 계산하지 않음","문제":[…],"허용값":…}로 변환).
    """
    # 입력 검증
    if event not in _EVENT_TYPES:
        raise ValueError(f"허용되지 않은 event: {event!r}. 허용값: {sorted(_EVENT_TYPES)}")
    if amount_usd < 0:
        raise ValueError("amount_usd는 0 이상")
    if cumulative_usd is not None and cumulative_usd < 0:
        raise ValueError("cumulative_usd는 0 이상")
    if recovered_usd is not None and recovered_usd < 0:
        raise ValueError("recovered_usd는 0 이상")
    if event == "금전대여" and loan_term_months is None:
        raise ValueError("금전대여 이벤트에는 loan_term_months 필요")
    try:
        ed = date.fromisoformat(event_date)
    except (ValueError, TypeError):
        raise ValueError(f"event_date 날짜 형식 오류: {event_date!r} (YYYY-MM-DD)")
    if not (date(2016, 1, 1) <= ed <= date(2026, 12, 31)):
        raise ValueError(f"event_date={event_date} — 2016.1.1.~2026.12.31.만 지원(외국환거래규정 연혁을 그 범위만 대조)")
    if not fiscal_year_end:
        fy = date(ed.year, 12, 31)
    else:
        try:
            fy = date.fromisoformat(fiscal_year_end)
        except (ValueError, TypeError):
            raise ValueError(f"fiscal_year_end 날짜 형식 오류: {fiscal_year_end!r} (YYYY-MM-DD)")

    cumulative_usd = cumulative_usd if cumulative_usd is not None else amount_usd
    ownership_ratio_after = ownership_ratio_after if ownership_ratio_after is not None else 0.0

    fdi, 사유 = _is_fdi(event, ownership_ratio_after, loan_term_months, financial_business)

    # 신고
    신고 = _reporting_deadline(event, ed, paid_in, ownership_ratio_after,
                                loan_term_months, counterparty_resident, cumulative_usd, fy,
                                main_bank_type, largest_shareholder)

    # 사후관리 일정
    사후관리 = _aftercare_schedule(event, ed, paid_in, cumulative_usd,
                                    ownership_ratio_after, loan_term_months,
                                    counterparty_resident,
                                    recovered_usd, fy)

    # 세무 연결
    세무 = _tax_connection(event, fdi, ownership_ratio_after, ed, fy, loan_term_months)

    # 판단
    판단 = [사유] if 사유 else []
    if financial_business:
        판단.append("금융·보험업 해외직접투자는 제9-10조에 따라 별도(한국은행 등) — 이 도구 범위 밖")
    if event == "청산" and recovered_usd == 0:
        판단.append("청산 시 분배 잔여재산은 즉시 국내로 회수함이 원칙(제9-6조) — 불가능 시 분할 회수, 청산 후 인정된 자본거래면 미회수 가능")

    주의 = [
        "금융·보험업·해외부동산·개인 투자자는 범위 밖",
        f"외국환거래규정은 이벤트 날짜({ed.isoformat()}) 당시 판 기준 — 2015~2026.11.2. 시행본을 판별로 대조(개정 잦음, 이후 개정은 korean-tax-mcp law_article로 확인)",
    ]
    if financial_business:
        주의.append("금융·보험업은 제9-10조 별도(한국은행 등) — 범위 밖")

    return {
        "결과": {
            "해외직접투자_해당": fdi,
            "사유": 사유,
            "신고": 신고,
            "사후관리": 사후관리,
            "세무": 세무,
        },
        "근거": "외국환거래법 제18조(자본거래 신고), 시행령 제8조(해외직접투자 정의), "
                "외국환거래규정 제9-5조(신고기관·사후보고·첨부서류), 제9-6조(청산), "
                "제9-9조(사후관리), 국조법 제58조(해외직접투자명세등)",
        "판단": 판단,
        "주의": 주의,
    }
