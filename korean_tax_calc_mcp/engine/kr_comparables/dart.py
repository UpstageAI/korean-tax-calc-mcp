"""OpenDART 호출기 — 순차 호출·간격·하루 상한·캐시·키 가림. Claude 작성(2026-11-16).

- 키: 환경변수 DART_API_KEY(사용자 본인 키, OpenDART 이용약관 제19조② — 제3자 이용 금지). 키는 결과·오류·로그 어디에도 남기지 않는다.
- 캐시: KR_COMPARABLES_CACHE_DIR(기본 ~/.cache/korean-tax-calc-mcp/opendart). 같은 요청은 다시 부르지 않는다.
  캐시 파일 이름 = sha1(엔드포인트 + 정렬한 요청 값) 앞 16자(키 제외) — 키가 바뀌어도 캐시를 그대로 쓴다.
- 안전장치: 호출 간격 0.35초 이상, 하루 호출 상한(KR_COMPARABLES_DAILY_CAP, 기본 2,000 — OpenDART 하루 한도 약 20,000의 1/10),
  실행 1회 상한(max_calls), status 020(한도 초과)·연속 오류 5회면 멈춤.
- transport를 바꿔 끼울 수 있어(테스트 모킹) 네트워크 없이 테스트할 수 있다.
"""
import datetime as _dt
import hashlib
import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://opendart.fss.or.kr/api/"
KEY_ENV = "DART_API_KEY"
KEY_GUIDE = ("OpenDART 인증키가 없습니다 — 환경변수 DART_API_KEY에 본인 키를 넣으세요. 발급: https://opendart.fss.or.kr (무료, 회원가입 후 인증키 신청). "
             "OpenDART 이용약관상 인증키는 발급받은 본인만 쓸 수 있습니다(제3자 이용 금지).")
DEFAULT_DAILY_CAP = 2000
MIN_INTERVAL = 0.35
RETRIES = 3                  # 일시 오류(연결 끊김·시간 초과·HTTP 5xx·429)만 최대 3회 재시도
BACKOFF = (1.0, 2.0, 4.0)    # 재시도 간격(초) — 점점 늘림


def transient(e):
    """다시 부르면 나아질 수 있는 오류인지 — HTTP 5xx·429, 연결 끊김·시간 초과. 그 밖의 HTTP 4xx는 아님."""
    code = getattr(e, "code", None)
    if isinstance(code, int):
        return code == 429 or code >= 500
    if isinstance(e, (urllib.error.URLError, TimeoutError, ConnectionError, OSError)):
        return True
    return False


class DartStop(Exception):
    """더 부르면 안 되는 상황(한도·상한·연속 오류). 메시지에 키 없음."""


def cache_dir():
    d = os.environ.get("KR_COMPARABLES_CACHE_DIR") or os.path.join(os.path.expanduser("~"), ".cache", "korean-tax-calc-mcp", "opendart")
    os.makedirs(d, exist_ok=True)
    return d


def mask(text, key=None):
    """문자열에서 인증키(그리고 crtfc_key 값)를 가린다."""
    s = str(text)
    key = key if key is not None else os.environ.get(KEY_ENV, "")
    if key:
        s = s.replace(key, "***")
    return re.sub(r"(crtfc_key=)[^&\s'\"]+", r"\1***", s)


def _ssl_ctx():
    c = ssl.create_default_context()
    # 인증서·호스트 검증은 그대로 둔다. Python 3.13+가 기본으로 켠 X509 엄격 검사(VERIFY_X509_STRICT)만 끈다 —
    # 실제로 opendart.fss.or.kr 연결이 엄격 검사에서만 'Missing Authority Key Identifier'로 실패한 적이 있음(망·인증서 체인에 따라 다름). 3.12 이하와 같은 검증 수준
    if hasattr(ssl, "VERIFY_X509_STRICT"):
        c.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return c


def urllib_transport(url, timeout=60):
    with urllib.request.urlopen(url, timeout=timeout, context=_ssl_ctx()) as r:
        return r.read()


class DartClient:
    def __init__(self, key=None, transport=None, max_calls=300, daily_cap=None, interval=MIN_INTERVAL, sleep=time.sleep):
        self.key = key if key is not None else os.environ.get(KEY_ENV, "")
        self.transport = transport or urllib_transport
        self.max_calls = max_calls
        self.daily_cap = int(daily_cap if daily_cap is not None else os.environ.get("KR_COMPARABLES_DAILY_CAP", DEFAULT_DAILY_CAP))
        self.interval = interval
        self.sleep = sleep
        self.calls = 0          # 이번 실행에서 실제로 부른 수(재시도 포함)
        self.retries = 0
        self.cache_hits = 0
        self.errors = []        # 키 가린 오류 문구
        self._consec = 0
        self._last = 0.0
        self.dir = cache_dir()

    # 하루 호출 수(캐시 폴더에 날짜별로 기록)
    def _day_file(self):
        return os.path.join(self.dir, "_calls_" + _dt.date.today().isoformat() + ".json")

    def _day_count(self):
        try:
            return json.load(open(self._day_file()))["n"]
        except (OSError, ValueError, KeyError):
            return 0

    def _day_add(self):
        n = self._day_count() + 1
        with open(self._day_file(), "w") as f:
            json.dump({"n": n}, f)

    def _check_caps(self):
        if self.calls >= self.max_calls:
            raise DartStop(f"이번 실행 호출 상한({self.max_calls}건)에 닿아 멈췄습니다 — 다시 실행하면 캐시로 이어서 진행합니다.")
        if self._day_count() >= self.daily_cap:
            raise DartStop(f"오늘 호출 상한({self.daily_cap}건, KR_COMPARABLES_DAILY_CAP)에 닿아 멈췄습니다 — 내일 다시 실행하면 캐시로 이어집니다.")

    def _path(self, endpoint, params, binary):
        p = dict(sorted(params.items()))
        h = hashlib.sha1((endpoint + json.dumps(p, ensure_ascii=False)).encode()).hexdigest()[:16]
        sub = os.path.join(self.dir, endpoint.split(".")[0])
        os.makedirs(sub, exist_ok=True)
        return os.path.join(sub, h + (".bin" if binary else ".json"))

    def get(self, endpoint, params, binary=False):
        """캐시 우선. 반환: JSON(dict) 또는 bytes(zip). 오류면 {'status': ..., 'message': ...}."""
        path = self._path(endpoint, params, binary)
        if os.path.exists(path):
            self.cache_hits += 1
            with open(path, "rb") as f:
                raw = f.read()
            return raw if binary else json.loads(raw.decode("utf-8"))
        if not self.key:
            raise DartStop(KEY_GUIDE)
        url = BASE + endpoint + "?" + urllib.parse.urlencode({"crtfc_key": self.key, **params})
        raw, err = None, None
        for attempt in range(1 + RETRIES):
            self._check_caps()          # 재시도도 호출 수·하루 상한에 셈
            wait = self.interval - (time.time() - self._last)
            if wait > 0:
                self.sleep(wait)
            self.calls += 1
            self._day_add()
            try:
                raw = self.transport(url)
                err = None
            except Exception as e:      # 메시지에서 키를 가린다
                err = mask(f"{type(e).__name__}: {e}", self.key)
                self._last = time.time()
                if not transient(e):
                    break               # 4xx(429 제외)·키 오류 등은 재시도해도 같음
                if attempt < RETRIES:
                    self.retries += 1
                    self.sleep(BACKOFF[attempt])
                continue
            self._last = time.time()
            break
        if err:
            tries = f" (일시 오류로 {RETRIES}회 재시도 후 실패)" if self.retries and attempt == RETRIES else ""
            return self._fail({"status": "NET", "message": err + tries})
        if binary:
            if raw[:2] != b"PK":
                txt = raw[:400].decode("utf-8", "replace")
                st = (re.search(r"<status>(\d+)</status>", txt) or re.search(r'"status"\s*:\s*"(\d+)"', txt))
                st = st.group(1) if st else "ERR"
                if st == "020":
                    raise DartStop("OpenDART 하루 한도 초과(status 020) — 내일 다시 실행하세요.")
                return self._fail({"status": st, "message": mask(txt[:200], self.key)})
            with open(path, "wb") as f:
                f.write(raw)
            self._consec = 0
            return raw
        try:
            d = json.loads(raw.decode("utf-8"))
        except ValueError:
            return self._fail({"status": "ERR", "message": "JSON 아님"})
        st = d.get("status")
        if st == "020":
            raise DartStop("OpenDART 하루 한도 초과(status 020) — 내일 다시 실행하세요.")
        if st in ("000", "013"):   # 013 = 조회 데이터 없음(정상 결과로 캐시)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
            self._consec = 0
            return d
        return self._fail({"status": st, "message": mask(d.get("message", ""), self.key)})

    def _fail(self, d):
        self._consec += 1
        self.errors.append(f"{d['status']}: {d['message']}")
        if self._consec >= 5:
            raise DartStop("OpenDART 연속 오류 5회로 멈췄습니다: " + d["message"][:120])
        return d
