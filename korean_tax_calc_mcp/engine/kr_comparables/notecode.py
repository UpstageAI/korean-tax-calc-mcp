"""주석 제목 → 표준 코드(금감원 XBRL 주석 코드). 사전은 data/note_title_codes.json(주석에 코드가 붙은 사업보고서의 제목 → 코드). Claude 작성(2026-11-18).
lookup(제목) → {'코드': [코드…], '방법': 같음|포함|비슷함|안 붙음, '확정': bool}
- 같음: 사전에 그 제목이 있음. 그 제목을 쓴 회사의 20% 이상이 고른 코드를 모두 돌려줌(한 제목에 두 주석을 합쳐 쓰는 회사가 있음 — '매출원가 및 판매비와관리비').
- 포함·비슷함: 사전 제목이 일부 들어 있거나 글자 2개 묶음이 60% 이상 겹침(어순만 다른 제목 — '성격별 비용'). 추정으로만 씀.
- 확정: '같음'이고 코드가 하나이며 그 코드의 몫이 80% 이상."""
import collections
import functools
import json
import os
import re

def norm(t):
    t = re.sub(r"<[^>]+>", "", t); t = re.sub(r"\[[A-Z]?\d+\]", "", t); t = re.sub(r"^\s*[\d\-\.]+\s*", "", t)
    t = re.sub(r"&cr;|&nbsp;|\(?\s*단위\s*[:：]?\s*(천원|백만원|원)\s*\)?", "", t)
    t = re.sub(r"\((연결|별도)\)|,\s*계속|\(계속\)|\s\d+$", "", t)
    t = re.sub(r"[\s·ㆍ,\.\(\)/\-:：]|및|과|와|의|등", "", t)
    return re.sub(r"\d+$", "", t)
def base(code): return code[:-1] + "0" if code[-1] == "5" else code
def grams(t): return {t[i:i + 2] for i in range(len(t) - 1)}
MULTI_MIN, SURE_MIN, SIM_MIN = 0.2, 0.8, 0.6

# 보조 코드 — 금감원 주석 코드(K-IFRS 기준)에 없는 주석. 일반기업회계기준 감사보고서에 주로 나온다. 코드는 우리 것(K로 시작).
AUX = {"K110": "부가가치 계산", "K120": "포괄손익계산서(주석)", "K130": "외화자산·부채", "K140": "재무제표 확정일·승인", "K150": "보유토지 공시지가",
       "K160": "보험가입", "K170": "종업원 복지·사회 기여금", "K180": "유가증권(매도가능·만기보유·단기매매·투자자산)", "K190": "전기오류수정·재작성·재분류",
       "K200": "계속기업", "K210": "온실가스·환경", "K230": "연구개발비", "K240": "환불부채·반환제품회수권", "K250": "파생상품", "K260": "대여금",
       "K270": "경제 환경·사업 불확실성", "K280": "한국채택국제회계기준 전환", "K290": "회생·채무조정·상장 관련 절차"}
# 사전에 없는 제목에 쓰는 규칙(위에서부터, 정규화한 제목에 적용). 뒤쪽 D 코드는 금감원 코드의 다른 제목 꼴.
RULES = [(r"부가가치", "K110"), (r"^포괄손익계산서", "K120"), (r"기타포괄손익", "D861000"), (r"외화(자산|부채|환산)|화폐성외화", "K130"), (r"재무제표.{0,6}(확정|승인)", "K140"), (r"공시지가", "K150"),
         (r"보험가입", "K160"), (r"종업원.{0,4}복지|기여금", "K170"), (r"매도가능|만기보유|단기매매|유가증권|[단장]기투자자산", "K180"),
         (r"오류수정|재무제표재작성|재분류", "K190"), (r"계속기업", "K200"), (r"온실가스|환경(기준|정책)", "K210"), (r"연구개발비|경상개발비", "K230"),
         (r"환불(부채|자산)|반환(재고|제품)", "K240"), (r"통화선도|파생", "K250"), (r"연구비|개발비", "K230"), (r"고객.{0,4}계약.{0,6}수익|분양(매출|수익)|공사수익", "D831150"), (r"이익준비금", "D861300"), (r"경영진.{0,6}보상", "D818000"), (r"배출권", "K210"), (r"대여금", "K260"),
         (r"회계(처리)?(정책|추정).{0,6}변경|회계변경", "D811000"), (r"회계(처리)?방침|회계정책", "D800600"), (r"유동성위험|위험관리", "D822380"), (r"리스부채", "D832620"), (r"리스", "D832610"), (r"소송|지급보증|보증내역|약정", "D827580"),
         (r"담보", "D822320"), (r"차입금", "D822400"), (r"전환(상환)?우선주|회사채|사채", "D822450"), (r"확정급여|확정기여|퇴직", "D834480"), (r"적립금", "D861300"),
         (r"주식(매수)?선택권|주식보상", "D834120"), (r"공사계약|계약부채", "D831150"), (r"중단사업", "D825900"), (r"현금유입유출이없는", "D851100"),
         (r"분할|합병|사업결합|(영업|사업)(양수|양도|매각)|동일지배|자산집단취득", "D817000"), (r"성격별", "D834300"),
         (r"(보고기간|재무제표일|결산일).{0,6}(후|이후).{0,8}(사건|사항)|후속사건", "D815000"), (r"[주좌]당(손익|손실|이익|순이익|순손실)", "D838000"), (r"^회사(개황|개요)|이하\"", "D810000"),
         (r"불확실성|경제환경|코로나|COVID|인플레이션|영업환경", "K270"), (r"한국채택국제회계기준.{0,4}(전환|적용)|별도재무제표로전환", "K280"), (r"회생|채무조정|공동관리|상장폐지|매매거래정지", "K290"),
         (r"보증(?!금)", "D827580"), (r"회계추정|추정.{0,3}(판단|가정|사용)|중요한가정", "D811000"), (r"영업(집중|부분)|지역별|고객별", "D871100"),
         (r"수주|건설형공사|분양|진행기준|미청구공사|초과청구공사|투입법|고객계약", "D831150"), (r"사용.{0,2}제한.{0,4}(예|적금|금융)|예치금", "D822470"), (r"잉여금|결손", "D861300"), (r"배당", "D861310"),
         (r"보조금|공사부담금", "D831400"), (r"매각예정", "D825900"), (r"지분법|관계기업|종속(기업|법인|회사)", "D825700"), (r"보험.{0,6}(가입|종류)|부보", "K160"), (r"보유토지", "K150"),
         (r"(주식|자본).{0,3}(발행|내용|할인)", "D861200"), (r"중소기업.{0,6}특례", "D800600"), (r"대손", "D822420"), (r"급여|종업원부채", "D834480"), (r"특수관계|관계(관련)?회사.{0,3}거래", "D818000"), (r"우발", "D827580"), (r"신용위험", "D822380")]

# 제목에 이 낱말이 있으면 그 코드를 후보에 꼭 넣는다(정규화한 제목 앞 30자에 적용, (낱말, 코드, 빼는 낱말)). '있는데 없다고 답하는' 일을 막는 장치 — 2026-11-18 전수 대조에서 나온 것.
ENSURE = [(r"재고자산", "D826380", None), (r"특수관계", "D818000", None), (r"유형자산", "D822100", r"투자부동산"), (r"무형자산", "D823180", None), (r"매출채권|수취채권", "D822420", None),
          (r"충당부채", "D827570", r"퇴직급여충당|대손충당"), (r"우발|약정|소송|보증", "D827580", r"보증금|품질보증|판매보증|하자보증"), (r"차입금|차입부채", "D822400", None), (r"법인세", "D835110", None),
          (r"리스|사용권자산", "D832610", None), (r"판매비|관리비|영업비용", "D834310", None), (r"매출액|영업수익|수익인식|고객계약", "D831150", None), (r"영업부문|부문별|부문정보|보고부문", "D871100", None),
          (r"부가가치", "K110", None), (r"외화(자산|부채|환산)|화폐성외화", "K130", None), (r"연구개발|경상개발", "K230", None), (r"성격별", "D834300", None)]
SPLIT = re.compile(r"\s*(?:및|과|와|,|ㆍ|·|/)\s*")

_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "note_title_codes.json")


class Dict:
    """제목 사전. table = {정규화한 제목: {코드: 회사 수}}. coded = {회사: [(코드, 제목)…]}에서 만들 수도 있음(한 회사 빼고 재기용, exclude)."""
    def __init__(self, coded=None, exclude=None, table=None):
        self.T = collections.defaultdict(collections.Counter)
        for t, cs in (table or {}).items():
            self.T[t].update(cs)
        for k, rows in (coded or {}).items():
            if k != exclude:
                for c, t in rows: self.T[t][c] += 1
        self.G = {t: grams(t) for t in self.T}
        self._memo = {}
    def _codes(self, t):
        cs = self.T[t]; tot = sum(cs.values())
        return [c for c, n in cs.most_common() if n / tot >= MULTI_MIN], cs.most_common(1)[0][1] / tot
    def lookup(self, title):
        """제목 → 코드 후보. 한 제목에 여러 주석을 합친 경우('유형자산 및 무형자산')는 나눈 조각의 코드도 더하고, ENSURE 낱말이 있으면 그 코드도 더한다(더해진 코드는 추정)."""
        if title in self._memo:
            return self._memo[title]
        self._memo[title] = r = self._lookup(title)
        return r
    def _lookup(self, title):
        r = self._lookup1(title)
        codes = list(r["코드"]); added = False
        parts = [x for x in SPLIT.split(re.sub(r"^\s*[\d\-\.]+\s*", "", title)) if x.strip()]
        if len(parts) > 1:
            for part in parts:
                t = norm(part)
                if len(t) >= 3 and t in self.T:
                    for c in self._codes(t)[0][:1]:
                        if c not in codes: codes.append(c); added = True
        t = norm(title)[:30]
        for pat, code, no in ENSURE:
            if code not in codes and re.search(pat, t) and not (no and re.search(no, t)):
                codes.append(code); added = True
        if added:
            return {"코드": codes, "방법": (r["방법"] + "+낱말") if r["코드"] else "낱말", "확정": False}
        return r
    def _lookup1(self, title):
        t = norm(title)
        if not t:
            return {"코드": [], "방법": "안 붙음", "확정": False}
        if t in self.T:
            codes, share = self._codes(t)
            return {"코드": codes, "방법": "같음", "확정": len(codes) == 1 and share >= SURE_MIN}
        best = None
        for k in self.T:
            if len(k) >= 3 and (k in t or (len(t) >= 4 and t in k)):
                if best is None or len(k) > len(best): best = k
        if best:
            return {"코드": self._codes(best)[0], "방법": "포함", "확정": False}
        g = grams(t); sim = None
        ct = collections.Counter(t)
        for k, gk in self.G.items():
            j = len(g & gk) / len(g | gk) if g and gk else 0
            same_chars = len(t) >= 4 and len(t) / len(k) >= 0.6 and not (ct - collections.Counter(k))     # 글자는 다 들어 있고 순서만 다름('성격별비용' ↔ '비용성격별분류')
            score = max(j, 0.99 if same_chars else 0)
            if score >= SIM_MIN and (sim is None or score > sim[0]): sim = (score, k)
        if sim:
            return {"코드": self._codes(sim[1])[0], "방법": "비슷함", "확정": False}
        for pat, code in RULES:
            if re.search(pat, t):
                return {"코드": [code], "방법": "규칙", "확정": False}
        return {"코드": [], "방법": "안 붙음", "확정": False}

BODY_START = re.compile(r"\(\s*1\s*\)|①|\b1\)|가\.|당기|당사|회사[는의가]|연결(실체|회사|기업)[는의이]|지배기업[은의]|다음|보고기간|기업회계기준|주석\s*\d|한국채택|일반기업회계")
def _ok_cut(rest, n):
    """rest[:n]에서 끊어도 되는가 — 뒤가 비었거나, 본문이 시작되거나, 글자가 아닌 기호. 뒤에 낱말이 이어지면 더 긴 제목의 앞부분이다('금융부채의 유동성위험 …')."""
    rem = rest[n:].lstrip()
    if re.search(r"(의|및|과|와)$", rest[:n].rstrip()) and rem: return False
    if re.match(r"[,ㆍ·/]", rem): return False                      # '매출, 매출원가 및 판매비와관리비' — 나열이 이어짐
    return not rem or bool(BODY_START.match(rem)) or not re.match(r"[가-힣A-Za-z]", rem)
def cut_title(rest, D, loose=False):
    """번호 뒤 글에서 제목만. → (제목, 사전에 있는가). loose: 줄 맨 앞 제목이면 사전에 있는 가장 긴 앞머리를 뒤에 한글이 바로 붙어도 받는다('2. 중요한 회계정책재무제표의 …')."""
    for n in range(min(len(rest), 40), 1, -1):
        if norm(rest[:n]) in D.T and _ok_cut(rest, n):
            return re.sub(r"\s*[\(（]\s*\d{1,2}\s*[\)）]?\s*$", "", rest[:n]).strip(), True      # 뒤에 붙은 '(1)'은 본문의 첫 항목 번호
    m = BODY_START.search(rest)
    t = (rest[:m.start()] if m and m.start() >= 2 else rest).strip(" :")
    r = re.match(r"(.{3,}?)\s*\1", t)                              # 제목 뒤에 같은 말로 본문이 시작됨('비용의 성격별 분류비용의 성격별 분류는')
    if r: t = r.group(1).strip()
    if len(t) <= 40:
        return t, norm(t) in D.T
    if loose:
        for n in range(40, 2, -1):
            if len(norm(rest[:n])) >= 3 and norm(rest[:n]) in D.T and norm(rest[:n]) != norm(rest[:n - 1]):
                return rest[:n].strip(), True
    return (t[:40], False) if m else ("", False)


@functools.lru_cache(maxsize=1)
def default():
    """패키지에 든 사전."""
    with open(_PATH, encoding="utf-8") as f:
        return Dict(table=json.load(f)["제목"])
