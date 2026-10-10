"""income 사전검토 규칙(소득세·원천세·연말정산). 작성 Mia(윤승미)
원천: knowledge/14_소득세_원천세_연말정산_조사포인트.md §13 (PR-01~23, 보조 WH-01·02·03·07·09·13).
2025 귀속 기준. 날짜는 "YYYY-MM-DD", 월은 "YYYY-MM" 문자열. 금액은 원 단위 int.
근로자별 항목은 "근로자" 리스트의 dict 원소 키로 받는다(아래 SCHEMA의 "근로자[].xxx").
"""
from datetime import date
from . import rule, hit, ok, check, Missing  # noqa: F401
from .. import calc_income as C

SCHEMA = {
    "귀속연도": "귀속 과세연도(int, 예 2025)",
    # 원천징수이행상황신고서
    "원천세신고.근로소득총지급액": "원천징수이행상황신고서 근로소득 A01~A04 인원·총지급액 합계 중 연간 총지급액(연말정산분 A04 기준, 원)",
    "원천세신고.소득처분신고액": "원천징수이행상황신고서 소득처분(인정상여 등) 총지급액 합계(원)",
    # 지급명세서 제출
    "지급명세서.근로제출일": "근로소득 지급명세서 제출일(YYYY-MM-DD)",
    "지급명세서.근로지급액": "기한 후 제출된 근로소득 지급명세서 지급금액 합계(원)",
    "일용근로자": "일용근로소득 지급명세서 리스트 [{주민번호, 지급월[YYYY-MM], 건설(bool), 제출일{YYYY-MM:YYYY-MM-DD}, 지급액{YYYY-MM:원}, 일급, 일원천세}]",
    # 법인세 연계
    "법인세.소득자료명세서상여": "법인세 소득자료(인정상여·인정배당·기타소득)명세서 상여 처분액 합계(원)",
    "법인세.임원퇴직금한도초과": "법인세 세무조정 임원퇴직금 한도초과 손금불산입액(원)",
    "퇴직지급명세서.임원퇴직금": "임원 퇴직소득 지급명세서 퇴직급여 합계(원)",
    # 사업장·연구소
    "사업장.업종": "중기감면 적용 사업장 주된 업종명(문자열, 한국표준산업분류 명칭 권장)",
    "사업장.공공기관": "국가·지자체·공공기관·지방공기업 여부(bool, 조특령§27③ 단서)",
    # 소득처분 원천징수(법인세 연계)
    "소득처분.배당처분액": "법인세 소득자료명세서 배당 처분액 합계(원)",
    "소득처분.배당원천징수액": "배당 처분분 원천징수 소득세(원, 지방소득세 제외)",
    "소득처분.기타소득처분액": "법인세 소득자료명세서 기타소득 처분액 합계(원)",
    "소득처분.기타소득원천징수액": "기타소득 처분분 원천징수 소득세(원, 지방소득세 제외)",
    "연구소.인정여부": "기업부설연구소·연구개발전담부서 인정 여부(bool, 인정 DB)",
    "연구소.인정연구원수": "인정 연구소 연구원 수(명, 인정 DB)",
    # 근로자별 — 근로소득원천징수영수증(지급명세서)
    "근로자": "근로자 리스트. 원소 키는 아래 근로자[].* 참조",
    "근로자[].성명": "성명",
    "근로자[].주민번호": "주민등록번호",
    "근로자[].세대번호": "주민등록 세대 식별자(등본 전산)",
    "근로자[].세대주": "세대주 여부(bool)",
    "근로자[].총급여": "원천징수영수증 ⑯ 계(총급여, 비과세 제외, 원)",
    "근로자[].근로소득공제": "원천징수영수증 근로소득공제(원)",
    "근로자[].과세표준": "원천징수영수증 종합소득 과세표준(원)",
    "근로자[].산출세액": "원천징수영수증 산출세액(원)",
    "근로자[].감면세액": "원천징수영수증 세액감면(조특법§30 중소기업 취업자, 원)",
    "근로자[].근로소득세액공제": "원천징수영수증 근로소득세액공제(원)",
    "근로자[].근무월수": "해당 연도 근무월수(1~12)",
    "근로자[].비과세합계": "비과세소득 합계(⑳ 비과세 계, 원). 없으면 비과세.* 합산",
    "근로자[].비과세.식대": "비과세 식사대 P01 연간(원)",
    "근로자[].현물식사": "현물식사(구내식당 등) 제공 여부(bool, 급여대장)",
    "근로자[].비과세.연구보조비": "비과세 연구보조비 H10 등 연간(원)",
    "근로자[].비과세.보육수당": "비과세 보육수당 Q02 연간(원)",
    "근로자[].비과세.출산지원금": "비과세 출산지원금 Q03(원)",
    "근로자[].출산지원금지급일": "출산지원금 지급일(YYYY-MM-DD)",
    "근로자[].비과세.야간근로": "생산직 야간근로수당 비과세 O01(원)",
    "근로자[].직전연도총급여": "직전 과세기간 총급여(전년 지급명세서, 원)",
    "근로자[].대표자친족": "대표자·지배주주와 친족 여부(bool, 가족관계 전산)",
    "근로자[].인정상여": "원천징수영수증 ⑮ 인정상여(원)",
    "근로자[].임원퇴직한도초과근로소득": "원천징수영수증 ⑮-3 임원 퇴직소득금액 한도초과액(원)",
    "근로자[].임원퇴직": "임원 퇴직 dict {퇴직소득금액, 월수_2011이전, 월수_2012_2019, 월수_2020이후, 연평균총급여_2019, 연평균총급여_퇴직전, 2011퇴직가정액(선택)}",
    "근로자[].인정상여재정산": "인정상여 귀속연도 재정산 dict {당초총급여, 당초과세표준, 당초결정세액(선택), 기타세액공제(근로소득세액공제 외), 인정상여, 추가원천징수신고액}",
    "근로자[].종전근무지": "종(전) 근무지 지급명세서 존재(bool)",
    "근로자[].종전합산": "주(현) 근무지 연말정산에 종전 소득 합산(bool)",
    "근로자[].확정신고": "다음 해 5월 종합소득세 확정신고 여부(bool)",
    "근로자[].부양가족": "부양가족 명세 리스트 [{주민번호, 관계(직계존속|직계비속|형제자매|배우자|기타), 생년월일, 장애인(bool), 사망일, 근로소득만(bool), 총급여, 일용만(bool), 소득금액합계}]",
    "근로자[].중기감면": "중기감면 dict {계약일, 생년월일, 병역연수, 장애인, 경력단절, 청년(bool), 감면율(0.9|0.7), 감면대상총급여, 취업일, 최초감면취업일, 감면최종지급월(YYYY-MM), 임원, 최대주주}",
    "근로자[].월세": "월세 세액공제 dict {공제액, 지급액, 지원금, 공제율(0.17|0.15), 주택보유(bool, 12.31. 세대), 종합소득금액}",
    "근로자[].주택자금공제": "주택임차차입금·장기주택저당차입금 소득공제액 합계(원)",
    "근로자[].장기주택저당이자공제": "장기주택저당차입금 이자상환액 소득공제(원)",
    "근로자[].세대보유주택수": "12.31. 현재 세대 보유 주택 수(주택 보유 전산)",
}

S, F = "소득·원천", "근로소득 지급명세서"


def _W(d):
    return d["근로자"]


def _g(w, k, i):
    v = w.get(k)
    if v is None: raise Missing(f"근로자[{i}].{k}")
    return v


def _name(w, i): return w.get("성명") or w.get("주민번호") or f"#{i}"


def _d(s): return date.fromisoformat(s)


def _age(birth, at):
    b = _d(birth) if isinstance(birth, str) else birth
    return at.year - b.year - ((at.month, at.day) < (b.month, b.day))


def _out(bad, note):
    return hit(None, None, f"{note}: " + "; ".join(bad)) if bad else ok()


# ── 근로자별 재계산 (WH-01·02·03·07) ─────────────────────────────
@rule("I-WH01", S, F, "근로소득공제 재계산 불일치", "소득세법 제47조①", needs=["근로자"], source="14 WH-01")
def _(d):
    bad = []
    for i, w in enumerate(_W(d)):
        r, c = _g(w, "근로소득공제", i), C.earned_deduction(_g(w, "총급여", i))
        if abs(r - c) > 1: bad.append(f"{_name(w, i)} 신고 {r:,} / 재계산 {c:,}")
    return _out(bad, "근로소득공제 불일치")


@rule("I-WH02", S, F, "산출세액 재계산 불일치", "소득세법 제55조①", needs=["근로자"], source="14 WH-02")
def _(d):
    bad = []
    for i, w in enumerate(_W(d)):
        r, c = _g(w, "산출세액", i), C.income_tax(_g(w, "과세표준", i))
        if abs(r - c) > 1: bad.append(f"{_name(w, i)} 신고 {r:,} / 재계산 {c:,}")
    return _out(bad, "산출세액 불일치")


@rule("I-WH07", S, F, "중기감면액 한도·산식 초과", "조특법 제30조", needs=["근로자"], source="14 WH-07")
def _(d):
    """근로소득만 있는 근로자 전제(근로소득금액/종합소득금액 = 1). 감면세액이 산식·200만원 한도 재계산값을 초과하면 의심."""
    bad = []
    for i, w in enumerate(_W(d)):
        red = w.get("감면세액") or 0
        if not red: continue
        m = _g(w, "중기감면", i)
        c = C.sme_youth_reduction(_g(w, "산출세액", i), _g(w, "총급여", i),
                                  m.get("감면대상총급여", w["총급여"]), m.get("감면율", 0.9 if m.get("청년") else 0.7))
        if red > c + 1: bad.append(f"{_name(w, i)} 감면 {red:,} / 재계산 한도 {c:,}")
    return _out(bad, "중기감면 과다")


# ── PR-01~04 인적공제 ────────────────────────────────────────────
@rule("I-PR01", S, F, "부양가족 중복 기본공제", "소득세법 시행령 제106조②", needs=["근로자"], source="14 PR-01")
def _(d):
    seen = {}
    for i, w in enumerate(_W(d)):
        for p in w.get("부양가족") or []:
            seen.setdefault(p["주민번호"], []).append(_name(w, i))
    bad = [f"{k} → {', '.join(v)}" for k, v in seen.items() if len(v) > 1]
    return _out(bad, "동일 부양가족 2명 이상 공제")


@rule("I-PR02", S, F, "부양가족 소득요건 초과", "소득세법 제50조", needs=["근로자"], source="14 PR-02", kind="외부자료")
def _(d):
    """부양가족 본인 지급명세서 전산 대사 필요. 근로소득만: 총급여 500만원 이하, 일용만: 금액 무관, 그 외 소득금액 100만원 이하."""
    bad = []
    for i, w in enumerate(_W(d)):
        for p in w.get("부양가족") or []:
            if p.get("관계") == "본인" or p.get("일용만"): continue
            if p.get("근로소득만"):
                if p.get("총급여") is None: raise Missing(f"근로자[{i}].부양가족.총급여")
                if p["총급여"] > 5_000_000: bad.append(f"{_name(w, i)}-{p['주민번호']} 총급여 {p['총급여']:,}")
            elif p.get("소득금액합계") is not None and p["소득금액합계"] > 1_000_000:
                bad.append(f"{_name(w, i)}-{p['주민번호']} 소득금액 {p['소득금액합계']:,}")
    return _out(bad, "소득요건 초과 부양가족")


@rule("I-PR03", S, F, "과세기간 개시일 전 사망자 공제", "소득세법 제53조", needs=["귀속연도", "근로자"], source="14 PR-03", kind="외부자료")
def _(d):
    """사망일은 사망 전산으로 확인."""
    start = date(d["귀속연도"], 1, 1)
    bad = [f"{_name(w, i)}-{p['주민번호']} 사망 {p['사망일']}" for i, w in enumerate(_W(d))
           for p in w.get("부양가족") or [] if p.get("사망일") and _d(p["사망일"]) < start]
    return _out(bad, "개시일 전 사망자")


@rule("I-PR04", S, F, "부양가족 연령요건 미충족", "소득세법 제50조①", needs=["귀속연도", "근로자"], source="14 PR-04")
def _(d):
    """연령은 귀속연도 − 출생연도. 직계존속 60세 이상, 직계비속 20세 이하, 형제자매 20세 이하 또는 60세 이상. 장애인은 연령 무관."""
    y, bad = d["귀속연도"], []
    for i, w in enumerate(_W(d)):
        for p in w.get("부양가족") or []:
            if p.get("장애인") or not p.get("생년월일"): continue
            a, rel = y - _d(p["생년월일"]).year, p.get("관계")
            wrong = (rel == "직계비속" and a > 20) or (rel == "형제자매" and 20 < a < 60) or (rel == "직계존속" and a < 60)
            if wrong: bad.append(f"{_name(w, i)}-{p['주민번호']} {rel} {a}세")
    return _out(bad, "연령요건 미충족")


# ── PR-05~09 비과세 ─────────────────────────────────────────────
@rule("I-PR05", S, F, "식대 비과세 월 20만원 초과·현물식사 중복", "소득세법 시행령 제17조의2", needs=["근로자"], source="14 PR-05")
def _(d):
    bad = []
    for i, w in enumerate(_W(d)):
        v = w.get("비과세.식대") or 0
        if not v: continue
        cap = 200_000 * _g(w, "근무월수", i)
        if w.get("현물식사"): bad.append(f"{_name(w, i)} 현물식사+비과세식대 {v:,}")
        elif v > cap: bad.append(f"{_name(w, i)} 비과세식대 {v:,} > 한도 {cap:,} (과세전환 {v - cap:,})")
    return _out(bad, "식대 비과세 초과")


@rule("I-PR06", S, F, "연구보조비 비과세 대상 초과", "소득세법 시행령 제12조", needs=["근로자", "연구소.인정여부"], source="14 PR-06", kind="외부자료")
def _(d):
    """연구소 인정 DB 대사. 월 20만원 초과분도 함께 표시."""
    ppl = [(i, w) for i, w in enumerate(_W(d)) if (w.get("비과세.연구보조비") or 0) > 0]
    bad = []
    if ppl and not d["연구소.인정여부"]: bad.append(f"연구소 미인정인데 {len(ppl)}명 비과세")
    elif ppl and len(ppl) > d["연구소.인정연구원수"]: bad.append(f"적용 {len(ppl)}명 > 인정 연구원 {d['연구소.인정연구원수']}명")
    for i, w in ppl:
        cap = 200_000 * _g(w, "근무월수", i)
        if w["비과세.연구보조비"] > cap: bad.append(f"{_name(w, i)} {w['비과세.연구보조비']:,} > 한도 {cap:,}")
    return _out(bad, "연구보조비 비과세 의심")


@rule("I-PR07", S, F, "보육수당 비과세 대상 자녀 없음·한도 초과", "소득세법 제12조3호", needs=["귀속연도", "근로자"], source="14 PR-07")
def _(d):
    """과세기간 개시일 현재 6세 이하 자녀 기준(부양가족 명세 한정 — 명세 외 자녀는 가족관계 확인). 2025 귀속 월 20만원."""
    start, bad = date(d["귀속연도"], 1, 1), []
    for i, w in enumerate(_W(d)):
        v = w.get("비과세.보육수당") or 0
        if not v: continue
        kids = [p for p in w.get("부양가족") or [] if p.get("관계") == "직계비속" and p.get("생년월일") and _age(p["생년월일"], start) <= 6]
        if not kids: bad.append(f"{_name(w, i)} 6세 이하 자녀 없음")
        cap = 200_000 * _g(w, "근무월수", i)
        if v > cap: bad.append(f"{_name(w, i)} 보육 {v:,} > 한도 {cap:,}")
    return _out(bad, "보육수당 비과세 의심")


@rule("I-PR08", S, F, "출산지원금 비과세 요건 의심", "소득세법 제12조3호머목", needs=["근로자"], source="14 PR-08")
def _(d):
    """지급일 기준 출생 후 2년 이내 자녀 필요(지급일 없으면 12.31.). 대표자 친족 수령은 과세."""
    bad = []
    for i, w in enumerate(_W(d)):
        if not (w.get("비과세.출산지원금") or 0): continue
        pay = _d(w["출산지원금지급일"]) if w.get("출산지원금지급일") else date(d["귀속연도"], 12, 31)
        kids = [p for p in w.get("부양가족") or [] if p.get("관계") == "직계비속" and p.get("생년월일")
                and 0 <= (pay - _d(p["생년월일"])).days and _d(p["생년월일"]) >= pay.replace(year=pay.year - 2)]
        if not kids: bad.append(f"{_name(w, i)} 2년 이내 출생 자녀 없음")
        if w.get("대표자친족"): bad.append(f"{_name(w, i)} 대표자 친족")
    return _out(bad, "출산지원금 비과세 의심")


@rule("I-PR09", S, F, "야간근로수당 비과세 직전연도 총급여 3천만원 초과", "소득세법 시행령 제17조", needs=["근로자"], source="14 PR-09", kind="외부자료")
def _(d):
    """전년도 지급명세서 필요. 직종·월정액 요건은 별도 확인."""
    bad = []
    for i, w in enumerate(_W(d)):
        if (w.get("비과세.야간근로") or 0) and _g(w, "직전연도총급여", i) > 30_000_000:
            bad.append(f"{_name(w, i)} 직전 총급여 {w['직전연도총급여']:,}")
    return _out(bad, "야간근로 비과세 부적격")


# ── PR-10~14 중기감면 ───────────────────────────────────────────
def _sme(d):
    return [(i, w, w["중기감면"]) for i, w in enumerate(_W(d)) if (w.get("감면세액") or 0) and w.get("중기감면")]


@rule("I-PR10", S, F, "중기감면 연령요건 밖", "조특법 제30조, 조특령 제27조", needs=["근로자"], source="14 PR-10")
def _(d):
    """계약일 현재 만 나이 − 병역기간(최대 6년) 15~34세 또는 60세 이상. 장애인·경력단절 코드는 제외."""
    bad = []
    for i, w, m in _sme(d):
        if m.get("장애인") or m.get("경력단절"): continue
        if not m.get("계약일") or not m.get("생년월일"): raise Missing(f"근로자[{i}].중기감면.계약일/생년월일")
        a = _age(m["생년월일"], _d(m["계약일"]))
        adj = a - min(m.get("병역연수") or 0, 6)
        if not (15 <= adj <= 34 or a >= 60): bad.append(f"{_name(w, i)} 계약일 {a}세(병역차감 {adj}세)")
    return _out(bad, "연령요건 밖 감면")


# 조특령§27③(2025.2.28. 개정, 2025.11.28. 시행본 원문 확인) 감면 대상 업종 — 열거 업종을 주된 사업으로 하는 기업만 대상(positive list).
# 키: 조문 호 명칭, 값: 업종명 대사 키워드. 2025.2.28. 이후 취업자부터 통관업·가상자산 매매중개업·수의업·부동산 임대업 제외(개정 부칙,
# [원천] 2025 연말정산 안내 14~15쪽). 주점·비알코올 음료점·비디오물 감상실은 개정 전부터 제외. 공공기관 등은 단서로 제외.
SME_JOB_INDUSTRIES = {
    "농업, 임업 및 어업": ["농업", "임업", "어업"], "광업": ["광업"], "제조업": ["제조"],
    "전기, 가스, 증기 및 공기조절 공급업": ["전기", "가스", "증기", "공기조절"],
    "수도, 하수 및 폐기물처리, 원료재생업": ["수도", "하수", "폐기물", "원료재생"], "건설업": ["건설"],
    "도매 및 소매업": ["도매", "소매"], "운수 및 창고업": ["운수", "운송", "창고", "물류", "택배", "통관"],
    "숙박 및 음식점업": ["숙박", "음식점", "음식", "주점", "음료점", "커피"],
    "정보통신업": ["정보통신", "출판", "영상", "방송", "통신", "소프트웨어", "프로그래밍", "시스템 통합", "정보서비스",
               "포털", "데이터베이스", "비디오물", "가상자산"],
    "부동산업": ["부동산"], "연구개발업": ["연구개발"], "광고업": ["광고"], "시장조사 및 여론조사업": ["시장조사", "여론조사"],
    "건축기술, 엔지니어링 및 기타 과학기술 서비스업": ["건축기술", "엔지니어링", "과학기술"],
    "기타 전문, 과학 및 기술 서비스업": ["전문디자인", "디자인", "사진", "번역", "통역", "수의"],
    "사업시설 관리, 사업 지원 및 임대 서비스업": ["사업시설", "사업 지원", "사업지원", "임대 서비스", "청소", "경비", "경호",
                                  "인력공급", "고용알선", "콜센터", "텔레마케팅", "여행사", "보안시스템", "렌탈", "대여"],
    "기술 및 직업훈련학원": ["직업훈련", "기술 및 직업훈련"], "컴퓨터 학원": ["컴퓨터 학원", "컴퓨터학원"],
    "사회복지 서비스업": ["사회복지"], "개인 및 소비용품 수리업": ["수리"],
    "창작 및 예술 관련 서비스업": ["창작", "예술"], "도서관, 사적지 및 유사 여가 관련 서비스업": ["도서관", "사적지"],
    "스포츠 서비스업": ["스포츠"],
}
SME_JOB_EXCL = ["주점", "비알코올", "음료점", "커피", "비디오물 감상실"]            # §27③9호·10호 괄호(개정 전부터)
SME_JOB_EXCL_20250228 = ["통관", "가상자산", "수의", "부동산 임대", "부동산임대"]   # 2025.2.28. 이후 취업자
SME_JOB_EXCL_DATE = date(2025, 2, 28)
_EXCL, _EXCL_2025 = SME_JOB_EXCL, SME_JOB_EXCL_20250228


def sme_job_industry(ind, hire=None):
    """(대상 여부, 사유). ind=업종명, hire=취업일(date)."""
    if any(k in ind for k in SME_JOB_EXCL): return False, "주점·비알코올 음료점·비디오물 감상실 제외"
    if any(k in ind for k in SME_JOB_EXCL_20250228):
        if hire is None: return False, "2025.2.28. 이후 취업자 제외 업종(취업일 확인)"
        if hire >= SME_JOB_EXCL_DATE: return False, "2025.2.28. 이후 취업 — 제외 업종"
        return True, "2025.2.28. 전 취업 — 종전 대상"
    for name, keys in SME_JOB_INDUSTRIES.items():
        if any(k in ind for k in keys): return True, name
    return False, "조특령§27③ 열거 업종 아님"


@rule("I-PR11", S, F, "중기감면 대상 업종 아닌 사업장", "조특령 제27조③", needs=["근로자", "사업장.업종"], source="14 PR-11")
def _(d):
    """조특령§27③ 열거 업종(23개 호 + 18의2 컴퓨터 학원) 키워드 대사. 업종명이 열거 명칭과 다르면 KSIC 분류로 재확인.
    공공기관 등(단서)은 업종 무관 제외."""
    ind, bad = d["사업장.업종"], []
    for i, w, m in _sme(d):
        if d.get("사업장.공공기관"): bad.append(f"{_name(w, i)} 공공기관 등"); continue
        okk, why = sme_job_industry(ind, _d(m["취업일"]) if m.get("취업일") else None)
        if not okk: bad.append(f"{_name(w, i)} 업종 {ind}: {why}")
    return _out(bad, "대상 업종 아닌 사업장 감면")


@rule("I-PR12", S, F, "중기감면 임원·최대주주·친족 적용", "조특법 제30조", needs=["근로자"], source="14 PR-12", kind="외부자료")
def _(d):
    """등기부·주주명부·가족관계 전산 필요."""
    bad = [f"{_name(w, i)} " + ",".join(k for k in ("임원", "최대주주") if m.get(k)) + (" 대표자친족" if w.get("대표자친족") else "")
           for i, w, m in _sme(d) if m.get("임원") or m.get("최대주주") or w.get("대표자친족")]
    return _out(bad, "제외 근로자 감면")


@rule("I-PR13", S, F, "중기감면 기간 종료 후 감면", "조특법 제30조①", needs=["근로자"], source="14 PR-13", kind="외부자료")
def _(d):
    """최초 감면 취업일부터 3년(청년 5년)이 되는 날이 속하는 달까지. 홈택스 감면 이력 필요."""
    bad = []
    for i, w, m in _sme(d):
        if not m.get("최초감면취업일") or not m.get("감면최종지급월"): raise Missing(f"근로자[{i}].중기감면.최초감면취업일/감면최종지급월")
        s = _d(m["최초감면취업일"]); n = 5 if m.get("청년") else 3
        try: e = s.replace(year=s.year + n)
        except ValueError: e = date(s.year + n, 2, 28)
        end = f"{e.year:04d}-{e.month:02d}"
        if m["감면최종지급월"] > end: bad.append(f"{_name(w, i)} 종료월 {end} 이후 {m['감면최종지급월']}까지 감면")
    return _out(bad, "기간 경과 감면")


@rule("I-PR14", S, F, "근로소득세액공제 감면비율 미조정·재계산 불일치", "소득세법 제59조, 조특법 제30조", needs=["근로자"], source="14 PR-14 / WH-03")
def _(d):
    bad = []
    for i, w in enumerate(_W(d)):
        r = _g(w, "근로소득세액공제", i)
        c = C.earned_tax_credit(_g(w, "산출세액", i), _g(w, "총급여", i), w.get("감면세액") or 0)
        if abs(r - c) > 1: bad.append(f"{_name(w, i)} 신고 {r:,} / 재계산 {c:,}")
    return _out(bad, "근로소득세액공제 불일치")


# ── PR-15~17 주택 ───────────────────────────────────────────────
@rule("I-PR15", S, F, "월세 세액공제 대상·공제율·금액 의심", "조특법 제95조의2", needs=["근로자"], source="14 PR-15 / WH-09", kind="외부자료")
def _(d):
    """주택 보유는 12.31. 세대 전산. 총급여 8천만 초과 배제, 5,500만 초과·종합소득 4,500만 초과자 17% 불가, 공제액 = Min(지급−지원금, 1천만) × 율."""
    bad = []
    for i, w in enumerate(_W(d)):
        m = w.get("월세")
        if not m or not m.get("공제액"): continue
        g, rate, inc = _g(w, "총급여", i), m.get("공제율"), m.get("종합소득금액")
        if m.get("주택보유"): bad.append(f"{_name(w, i)} 세대 주택 보유")
        if g > 80_000_000 or (inc is not None and inc > 70_000_000): bad.append(f"{_name(w, i)} 총급여 {g:,} 대상 아님"); continue
        if rate == 0.17 and (g > 55_000_000 or (inc is not None and inc > 45_000_000)): bad.append(f"{_name(w, i)} 17% 적용 부적격")
        if m.get("지급액") is not None and rate:
            c = int(min(m["지급액"] - (m.get("지원금") or 0), 10_000_000) * rate)
            if m["공제액"] > c + 1: bad.append(f"{_name(w, i)} 공제 {m['공제액']:,} > 재계산 {c:,}")
    return _out(bad, "월세 세액공제 의심")


@rule("I-PR16", S, F, "동일 세대 세대주·세대원 모두 월세·주택자금 공제", "조특법 제95조의2, 소득세법 제52조④", needs=["근로자"], source="14 PR-16", kind="외부자료")
def _(d):
    """등본 세대 전산 필요(세대번호). 세대원 공제는 세대주 미공제 시에만."""
    hh = {}
    for i, w in enumerate(_W(d)):
        used = (w.get("월세") or {}).get("공제액") or w.get("주택자금공제")
        if used and w.get("세대번호"): hh.setdefault(w["세대번호"], []).append((w.get("세대주"), _name(w, i)))
    bad = [f"세대 {k}: {', '.join(n for _, n in v)}" for k, v in hh.items()
           if any(h for h, _ in v) and any(not h for h, _ in v)]
    return _out(bad, "세대 내 중복 공제")


@rule("I-PR17", S, F, "장기주택저당차입금 이자공제자 2주택 이상", "소득세법 제52조⑤", needs=["근로자"], source="14 PR-17", kind="외부자료")
def _(d):
    bad = []
    for i, w in enumerate(_W(d)):
        if (w.get("장기주택저당이자공제") or 0) and _g(w, "세대보유주택수", i) >= 2:
            bad.append(f"{_name(w, i)} 세대 {w['세대보유주택수']}주택")
    return _out(bad, "2주택 이상 이자공제")


# ── PR-18~23 신고서 대사·제출 ───────────────────────────────────
def _nontax(w):
    if w.get("비과세합계") is not None: return w["비과세합계"]
    return sum(v for k, v in w.items() if k.startswith("비과세.") and isinstance(v, (int, float)))


@rule("I-PR18", S, "원천징수이행상황신고서", "근로소득 총지급액 ≠ 지급명세서 총급여+비과세", "소득세법 제164조",
      needs=["원천세신고.근로소득총지급액", "근로자"], source="14 PR-18")
def _(d):
    tot = sum(_g(w, "총급여", i) + _nontax(w) for i, w in enumerate(_W(d)))
    return check(d["원천세신고.근로소득총지급액"], tot, "지급명세서 합계와 불일치 — 누락 인원 확인")


@rule("I-PR19", S, "원천징수이행상황신고서", "법인세 상여 처분 있는데 소득처분 원천신고·인정상여 기재 없음", "소득세법 제135조④",
      needs=["법인세.소득자료명세서상여", "원천세신고.소득처분신고액"], source="14 PR-19", kind="외부자료")
def _(d):
    """법인세 신고서 연계 — 존재 여부 대사. 재정산 금액 재계산은 I-WH11(소법§135④·소령§49①3호)."""
    b = d["법인세.소득자료명세서상여"]
    if not b: return ok()
    rep = d["원천세신고.소득처분신고액"] + sum(w.get("인정상여") or 0 for w in d.get("근로자") or [])
    return ok() if rep else hit(0, b, "상여 처분액 원천징수 미신고")


@rule("I-PR20", S, F, "임원 퇴직금 한도초과 있는데 근로소득 ⑮-3 미기재", "소득세법 제22조③",
      needs=["퇴직지급명세서.임원퇴직금", "법인세.임원퇴직금한도초과"], source="14 PR-20", kind="외부자료")
def _(d):
    """존재 여부 대사. 한도 산식 재계산은 I-WH18(소법§22③④, 소령§42의2⑥)."""
    if not (d["퇴직지급명세서.임원퇴직금"] and d["법인세.임원퇴직금한도초과"]): return ok()
    s = sum(w.get("임원퇴직한도초과근로소득") or 0 for w in d.get("근로자") or [])
    return ok() if s else hit(0, d["법인세.임원퇴직금한도초과"], "⑮-3 미기재(법인세 한도초과액 참고치)")


def _max_run(months):
    ms = sorted({int(m[:4]) * 12 + int(m[5:7]) for m in months})
    best = cur = 0; prev = None
    for m in ms:
        cur = cur + 1 if prev is not None and m == prev + 1 else 1
        best, prev = max(best, cur), m
    return best


@rule("I-PR21", S, "일용근로소득 지급명세서", "장기 일용근로자 일반 근로소득 미전환", "소득세법 시행령 제20조",
      needs=["일용근로자"], source="14 PR-21")
def _(d):
    """연속 3개월 이상(건설 12개월 이상) 일용 지급 + 일반 근로 지급명세서 없음. 월 단위 연속으로 근사(실제는 동일 고용주 계속 고용일수)."""
    reg = {w.get("주민번호") for w in d.get("근로자") or []}
    bad = []
    for p in d["일용근로자"]:
        n, need = _max_run(p.get("지급월") or []), 12 if p.get("건설") else 3
        if n >= need and p.get("주민번호") not in reg: bad.append(f"{p.get('주민번호')} 연속 {n}개월")
    return _out(bad, "장기 일용 의심")


@rule("I-PR22", S, F, "종전 근무지 소득 미합산·확정신고 없음", "소득세법 제73조", needs=["근로자"], source="14 PR-22", kind="외부자료")
def _(d):
    """복수 지급명세서·종소세 신고 전산 필요."""
    bad = [_name(w, i) for i, w in enumerate(_W(d)) if w.get("종전근무지") and not w.get("종전합산") and w.get("확정신고") is False]
    return _out(bad, "종전 소득 미합산")


@rule("I-PR23", S, "지급명세서", "지급명세서 제출기한 경과", "소득세법 제164조, 제81조의11",
      needs=["귀속연도"], source="14 PR-23")
def _(d):
    """근로: 다음 연도 3.10.(휴일 순연 미반영), 일용: 지급월 다음 달 말일. 가산세 1%(3개월 내 0.5%)는 참고치."""
    y, bad = d["귀속연도"], []
    if d.get("지급명세서.근로제출일") is None and d.get("일용근로자") is None: raise Missing("지급명세서.근로제출일")
    if d.get("지급명세서.근로제출일"):
        due, sub = date(y + 1, 3, 10), _d(d["지급명세서.근로제출일"])
        if sub > due:
            w3 = (sub - due).days <= 92
            pen = C.payment_statement_penalty(d["지급명세서.근로지급액"], w3) if d.get("지급명세서.근로지급액") else None
            bad.append(f"근로 제출 {sub} > 기한 {due}" + (f", 가산세 참고 {pen:,}" if pen is not None else ""))
    for p in d.get("일용근로자") or []:
        for m, s in (p.get("제출일") or {}).items():
            yy, mm = int(m[:4]), int(m[5:7])
            ny, nm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
            nxt = date(ny + (nm == 12), 1 if nm == 12 else nm + 1, 1)
            due = date.fromordinal(nxt.toordinal() - 1)
            if _d(s) > due: bad.append(f"일용 {p.get('주민번호')} {m}분 제출 {s} > 기한 {due}")
    return _out(bad, "제출기한 경과")


@rule("I-WH13", S, "일용근로소득 지급명세서", "일용근로 원천세 재계산 불일치", "소득세법 제134조③, 제86조",
      needs=["일용근로자"], source="14 WH-13")
def _(d):
    bad = []
    for p in d["일용근로자"]:
        if p.get("일급") is None or p.get("일원천세") is None: continue
        c = C.daily_worker_tax(p["일급"])
        if abs(p["일원천세"] - c) > 1: bad.append(f"{p.get('주민번호')} 일급 {p['일급']:,} 신고 {p['일원천세']:,} / 재계산 {c:,}")
    return _out(bad, "일용 원천세 불일치")


# ── 소득처분·임원퇴직 재계산(조문 원문 확인: knowledge/16) ──────────────────
@rule("I-WH11", S, F, "상여 처분 재정산 결정세액", "소득세법 제135조④·제131조②, 소득세법 시행령 제49조①3호·제196조", needs=["근로자"],
      source="14 WH-11")
def _(d):
    """인정상여는 근로 제공 사업연도 귀속(소령§49①3호) → 귀속연도 총급여에 가산해 연말정산 재계산(소령§196) − 당초 결정세액
    = 추가 원천징수(지급시기: 신고분 신고일·수정신고일, 결정·경정분 소득금액변동통지서 받은 날, 소법§135④→§131②).
    소령§192는 소득금액변동통지(결정·경정일부터 15일 내 법인 통지) 절차 조문. 대상자(근로자[].인정상여재정산)만 계산."""
    bad = []
    for i, w in enumerate(_W(d)):
        m = w.get("인정상여재정산")
        if not m: continue
        r = C.deemed_bonus_resettlement(m["당초총급여"], m["당초과세표준"], m.get("인정상여", w.get("인정상여") or 0),
                                        m.get("기타세액공제", 0), m.get("당초결정세액"))
        rep_ = m.get("추가원천징수신고액")
        if rep_ is None: raise Missing(f"근로자[{i}].인정상여재정산.추가원천징수신고액")
        if rep_ + 10 < r["추가원천징수세액"]:
            bad.append(f"{_name(w, i)} 신고 {rep_:,} / 재계산 {r['추가원천징수세액']:,} (결정세액 {r['당초결정세액']:,}→{r['재정산결정세액']:,})")
    return _out(bad, "인정상여 재정산 추가 원천징수 과소")


@rule("I-WH12", S, "원천징수이행상황신고서", "배당·기타소득 처분 원천징수세율", "소득세법 제129조①2호나목·6호라목",
      needs=["소득처분.배당처분액", "소득처분.기타소득처분액"], source="14 WH-12")
def _(d):
    """배당 처분 14%(§129①2호나목), 기타소득 처분 20%(§129①6호라목, 필요경비 없음). 지방소득세 별도, 10원 미만 절사."""
    bad = []
    for k, kind in (("배당", "배당"), ("기타소득", "기타")):
        amt = d[f"소득처분.{k}처분액"]
        if not amt: continue
        should = C.withholding_tax(kind, amt)
        got = d.get(f"소득처분.{k}원천징수액")
        if got is None: raise Missing(f"소득처분.{k}원천징수액")
        if got + 10 < should: bad.append(f"{k} 처분 {amt:,} 원천징수 {got:,} < {should:,}({C.WITHHOLDING_RATES[kind]:.0%})")
    return _out(bad, "소득처분 원천징수 과소")


@rule("I-WH18", S, F, "임원 퇴직금 소법§22③ 한도초과 재계산", "소득세법 제22조③④, 소득세법 시행령 제42조의2⑤⑥", needs=["근로자"],
      source="14 WH-18")
def _(d):
    """한도 = 2019.12.31. 소급 3년 연평균 총급여 × 1/10 × 2012~2019 근무월수/12 × 3 + 퇴직 전 3년 연평균 총급여 × 1/10 × 2020 이후
    근무월수/12 × 2. 대상 = 퇴직소득금액 − 2011.12.31. 퇴직 가정액(월수 안분 또는 규정 선택). 초과액은 근로소득(⑮-3)."""
    bad = []
    for i, w in enumerate(_W(d)):
        m = w.get("임원퇴직")
        if not m: continue
        c = C.exec_retirement_excess(m["퇴직소득금액"], m.get("월수_2011이전", 0), m.get("월수_2012_2019", 0), m.get("월수_2020이후", 0),
                                     m.get("연평균총급여_2019", 0), m.get("연평균총급여_퇴직전", 0), m.get("2011퇴직가정액"))
        r = w.get("임원퇴직한도초과근로소득") or 0
        if abs(r - c) > 1: bad.append(f"{_name(w, i)} ⑮-3 신고 {r:,} / 재계산 {c:,}")
    return _out(bad, "임원 퇴직소득 한도초과액 불일치")
