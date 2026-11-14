"""법제처 국가법령정보 공동활용(DRF) — 시점별 조문 원문 조회.

인증키(OC)는 사용자 본인 것: https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC.
제3자 서버로 키를 전송하지 않으며, 오류 메시지의 OC 값은 OC=***로 가린다.
"""
import json
import os
import re
import ssl
import urllib.parse
import urllib.request
from functools import lru_cache

DRF = "https://www.law.go.kr/DRF"
CTX = ssl.create_default_context()  # 기본 TLS 검증 유지


# 법제처 DRF는 인증키를 주소의 OC 매개변수로 붙이고 응답 JSON의 링크에도 그 주소를 되돌려 준다.
# OC=, oc=, LAW_OC=, 그리고 '='의 URL 인코딩(%3D)·JSON 이스케이프(\u003d) 뒤에 오는 값을 잡는다. 이미 가린 OC=***는 건드리지 않는다.
_OC_RE = re.compile(r"(?i)(?<![A-Za-z0-9])(OC(?:=|%3D|\\u003d))(?!\*{3})[^&\s\"'<>\\#;,)\]}|`]+")


def _mask_oc(msg, literal=True):
    """문자열(오류 메시지·응답 본문·주소)에서 OC 값을 OC=***로 가린다.
    literal=True(오류 메시지용)면 환경변수 LAW_OC 값(4자 이상)이 OC= 없이 홀로 적힌 곳도 가린다.
    응답 본문에는 literal=False — 짧은 키가 조문 글자와 우연히 겹쳐 본문이 바뀌는 일을 막는다."""
    msg = _OC_RE.sub(r"\1***", msg)
    if literal:
        oc = os.environ.get("LAW_OC", "").strip()
        if len(oc) >= 4 and oc in msg:
            msg = msg.replace(oc, "***")
    return msg


def scrub_oc(obj):
    """중첩 JSON 값(dict·list·문자열) 전체에서 OC=<값>을 OC=***로 가린 사본을 돌려준다. 법제처 응답을 받는 즉시, 그리고 원자료를 저장하기 전에 쓴다."""
    if isinstance(obj, str):
        return _mask_oc(obj, literal=False)
    if isinstance(obj, dict):
        return {(_mask_oc(k, literal=False) if isinstance(k, str) else k): scrub_oc(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(scrub_oc(v) for v in obj)
    return obj


class NoKey(RuntimeError):
    pass


def _oc():
    oc = os.environ.get("LAW_OC", "").strip()
    if not oc:
        raise NoKey("법제처 OC 키가 없습니다 — https://open.law.go.kr 에서 무료 신청 후 환경변수 LAW_OC로 설정")
    return oc


def _get(path, query):
    """법제처 DRF API 호출. 타임아웃 20초.

    인증키는 여기서 만드는 요청 주소에만 쓴다. 법제처는 응답의 링크에 키가 든 주소를 되돌려 주므로,
    받은 즉시 본문 전체(원문 문자열과 파싱한 중첩 값)를 OC=***로 가려 돌려준다 — 캐시·결과·출처 링크·오류에 키가 남지 않게."""
    u = f"{DRF}/{path}?OC={_oc()}&type=JSON&{query}"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "korean-tax-audit-mcp"}),
                                    context=CTX, timeout=20) as r:
            raw = r.read()
    except Exception as e:
        raise RuntimeError(_mask_oc(str(e))) from None      # 원래 예외(주소를 든 HTTPError 등)를 이어 붙이지 않는다
    if isinstance(raw, (bytes, bytearray)):
        raw = bytes(raw).decode(json.detect_encoding(raw), "surrogatepass")
    try:
        return scrub_oc(json.loads(_mask_oc(raw, literal=False)))
    except ValueError as e:
        raise RuntimeError(_mask_oc(str(e))) from None       # JSONDecodeError.doc(응답 원문)을 들고 다니지 않게


def _list(x):
    return x if isinstance(x, list) else ([x] if x else [])


def jo6(article):
    """'제52조' → '005200', '제28조의2' → '002802'."""
    m = re.fullmatch(r"제?(\d+)조(?:의(\d+))?", (article or "").strip())
    if not m:
        raise ValueError("조문은 '제52조' 형식")
    return f"{int(m.group(1)):04d}{int(m.group(2) or 0):02d}"


@lru_cache(maxsize=128)
def _versions(law):
    d = _get("lawSearch.do", "target=eflaw&display=100&query=" + urllib.parse.quote(law))
    return [v for v in _list(d.get("LawSearch", {}).get("law")) if v.get("법령명한글") == law]


def version(law, as_of=""):
    """기준일(YYYYMMDD, 없으면 오늘)에 시행 중이던 연혁본 → (MST, 시행일자)."""
    import time
    day = as_of or time.strftime("%Y%m%d")
    vs = [v for v in _versions(law) if v.get("시행일자", "99999999") <= day]
    if not vs:
        return None, None
    v = max(vs, key=lambda x: x["시행일자"])
    return v["법령일련번호"], v["시행일자"]


def _texts(o):
    if isinstance(o, dict):
        for k, v in o.items():
            if k.endswith("내용") and k != "개정문내용" and isinstance(v, str):
                yield v
            elif isinstance(v, list) and v and all(isinstance(x, str) for x in v):
                yield "\n".join(v)
            elif isinstance(v, list) and v and all(isinstance(x, list) for x in v):
                for row in v:
                    yield "\n".join(x for x in row if isinstance(x, str))
            else:
                yield from _texts(v)
    elif isinstance(o, list):
        for v in o:
            yield from _texts(v)


def article(law, article_no, as_of=""):
    """조문 본문(문자열). as_of(YYYYMMDD)를 주면 그날 시행 중이던 버전.
    기준일 시행본 조문 원문을 반환한다."""
    mst, ef = version(law, as_of)
    if not mst:
        return ""
    d = _get("lawService.do", f"target=eflaw&MST={mst}&efYd={ef}&JO={jo6(article_no)}")
    body = "\n".join(t.strip() for t in _texts(d.get("법령", d)) if t.strip())
    return body or "조문 없음 — 조번호 확인"
