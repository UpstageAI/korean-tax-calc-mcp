"""사업보고서 'II. 사업의 내용 > 3. 원재료 및 생산설비'에서 직접 생산 여부의 단서를 원문 그대로 뽑는다.

기능 분석에서 '후보가 직접 만드는가(공장·설비) / 외주로 만들게 하는가'를 볼 때 쓰는 자리.
'1. 사업의 개요'의 '제조 및 판매업 영위' 같은 사업 목적 문구로는 알 수 없고 이 절에 적혀 있다
(2026-11-18 화장품 업종 상장 13곳: 13곳 모두 절이 있고 11곳은 단서가 한쪽으로만 나옴).
- 판정하지 않는다 — 단서(문장·표 유무)와 원문 일부만 낸다. '직접 제조/안 함' 판정은 조문 MCP 몫.
- 비상장사 감사보고서에는 이 절이 없다 — 부르지 않는다.
Claude 작성(2026-11-18)."""
import re

from .statements import title_sections, txt

TEXT_MAX = 1500
SNIP = 60
# 자체 생산설비가 없다는 문장 — '자체 생산공장을 보유하고 있지 않습니다', '자체 생산설비 없이 OEM방식으로', '전 제품을 외주생산방식'
NO_OWN = re.compile(
    r"(?:자체|별도의?)\s*(?:생산|제조)?\s*(?:공장|시설|설비)[을를은는이가]?\s*(?:을\s*)?(?:보유하고\s*있지\s*(?:않|아니)|보유하지\s*(?:않|아니)|없이|없으|없습|없고|없음)"
    r"|(?:전|모든)\s*제품을?\s*(?:외주|위탁)\s*(?:생산|제조|가공)"
    r"|(?:외주|위탁)\s*생산\s*(?:방식|을\s*하고|하고)"
    r"|OEM(?:\s*/\s*ODM)?\s*(?:의\s*)?(?:방식|형태)으?로\s*(?:제품을\s*)?(?:생산|제조)"
    r"|(?:제품|제조)의?\s*생산을\s*(?:외주|위탁)|생산을\s*위탁")
# 직접 생산의 흔적 — 생산능력·생산실적·가동률 표, 공장별 설비 현황
OWN = re.compile(r"생산\s*능력|생산\s*실적|가\s*동\s*률|가\s*동\s*율|(?:공장|사업장)별\s*(?:자산|설비)|생산\s*설비\s*(?:의\s*)?현황|생산\s*시설\s*현황")
# '해당사항 없음'으로 지운 줄 — '생산실적 및 가동률 … 해당사항이 없습니다'는 흔적이 아님
VOID = re.compile(r"해당\s*사항\s*(?:이\s*)?없|표기하지\s*않|기재하지\s*않|생략|어렵|산정하지\s*않|하지\s*않습니다")
DATA = re.compile(r"단\s*위\s*[:：]|\(\s*단\s*위|\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*%")   # 흔적 뒤에 실제 숫자 표가 있어야 함 — '생산능력' 소제목만 있고 '기획·마케팅에 주력'이면 흔적 아님


def section(s):
    """'원재료 및 생산설비'(또는 '생산 및 설비') 절의 원문(HTML). 없으면 ''."""
    secs = title_sections(s)
    start = next((i for i, (_a, _b, t) in enumerate(secs) if re.match(r"\s*I{1,2}\.\s*사업의\s*내용", t)), None)
    if start is None:
        return ""
    for a, b, t in secs[start + 1:]:
        if re.match(r"\s*(I{1,3}|IV|V)\.\s", t):
            break
        if re.search(r"생산\s*(?:및|과)?\s*설비|원재료\s*및\s*생산", t):
            return s[a:b]
    return ""


def _plain(sec):
    return re.sub(r"\s+", " ", txt(re.sub(r"<TITLE[^>]*>.*?</TITLE>", " ", sec, flags=re.S))).strip()


def _snips(text, pat, void_check=False):
    out = []
    for m in pat.finditer(text):
        around = text[max(0, m.start() - SNIP):m.end() + SNIP]
        if void_check:
            after = text[m.end():m.end() + 150]
            if VOID.search(text[m.start():m.end() + 100]) or not DATA.search(after):
                continue
        if around not in out:
            out.append(around)
    return out


def extract(s):
    """사업보고서 원문 → {'found', 'text', 'truncated', 'no_own_facility': [문장], 'own_production': [문장], 'problems': [..]}.

    no_own_facility: 자체 생산설비가 없다·외주로 생산한다는 원문 문장. own_production: 생산능력·생산실적·가동률·공장별 설비 현황 원문(‘해당사항 없음’으로 지운 줄은 뺌).
    둘 다 있으면 사업부문마다 다를 수 있다(예: 화장품은 외주, 다른 사업은 공장) — problems에 적는다."""
    sec = section(s)
    if not sec:
        return {"found": False, "text": "", "truncated": False, "no_own_facility": [], "own_production": [], "problems": ["원재료 및 생산설비 절 없음"]}
    text = _plain(sec)
    no_own = _snips(text, NO_OWN)
    own = _snips(text, OWN, void_check=True)
    problems = []
    if no_own and own:
        problems.append("자체 생산설비가 없다는 문장과 생산능력·설비 현황이 함께 있음 — 사업부문·자회사마다 다를 수 있어 원문 확인")
    return {"found": True, "text": text[:TEXT_MAX], "truncated": len(text) > TEXT_MAX,
            "no_own_facility": no_own[:3], "own_production": own[:3], "problems": problems}
