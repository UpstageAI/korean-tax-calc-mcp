"""법제처 OC 키가 응답·결과·오류·저장소에 남지 않는지 고정한다.

1. 받는 즉시 지우기: audit/agents/law.py의 _get(이 저장소에서 법제처를 직접 부르는 유일한 코드)이 응답 본문의 OC=<값>을 OC=***로 바꿔 돌려준다.
2. 저장소 전체 검사: scripts/check_no_oc_key.sh --all 이 추적 파일 전체에서 키 모양을 찾지 못해야 한다.
3. 감시는 울려 보고 믿는다: 가짜 키를 넣은 임시 파일·임시 저장소에서 검사와 커밋 훅이 실제로 막는지 확인한다.

이 파일의 가짜 키는 글자를 이어 붙여 만든다 — 검사 대상 모양('OC' + '=' + 값)이 소스에 그대로 적히지 않게.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from korean_tax_calc_mcp.audit.agents import law

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_no_oc_key.sh"
FAKE = "kg" + "fake" + "7391"          # 가짜 키(실제 키 아님)
OC = "OC" + "="                         # 검사에 걸리지 않게 나눠 적는다
MASKED = OC + "***"


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setenv("LAW_OC", FAKE)
    law._versions.cache_clear()
    yield
    law._versions.cache_clear()


def _fake_urlopen(monkeypatch, body):
    """법제처 요청이 지나는 가장 아래 함수(urlopen)를 가짜로 바꾼다. body가 예외면 그 예외를 낸다. 요청 주소를 기록해 돌려준다."""
    urls = []

    def fake(req, **k):
        urls.append(req.full_url)
        if isinstance(body, BaseException): raise body
        return _Resp(body)

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return urls


def _dump(x): return json.dumps(x, ensure_ascii=False, default=str)


# ── 1. 받는 즉시 지우기 ──

def test_get_masks_nested_links_and_keeps_key_only_in_request_url(monkeypatch):
    body = {"LawSearch": {"law": [
        {"법령명한글": "법인세법", "법령상세링크": f"/DRF/lawService.do?{OC}{FAKE}&target=eflaw&MST=1&type=HTML"},
        {"중첩": {"목록": [f"https://www.law.go.kr/DRF/lawService.do?target=law&oc={FAKE}", f"끝에 붙은 {OC}{FAKE}"]}},
    ]}}
    urls = _fake_urlopen(monkeypatch, json.dumps(body, ensure_ascii=False).encode())
    got = law._get("lawSearch.do", "target=eflaw&query=x")
    assert FAKE not in _dump(got)
    assert got["LawSearch"]["law"][0]["법령상세링크"] == f"/DRF/lawService.do?{MASKED}&target=eflaw&MST=1&type=HTML"
    assert got["LawSearch"]["law"][1]["중첩"]["목록"] == ["https://www.law.go.kr/DRF/lawService.do?target=law&oc=***", f"끝에 붙은 {MASKED}"]
    assert got["LawSearch"]["law"][0]["법령명한글"] == "법인세법"          # 다른 값은 그대로
    assert len(urls) == 1 and f"?{OC}{FAKE}&type=JSON&" in urls[0]          # 실제 요청 주소에만 키가 쓰인다


@pytest.mark.parametrize("raw", [
    '{"링크": "/DRF/x.do?OC\\u003d%s\\u0026type\\u003dHTML"}',      # JSON 이스케이프(\u003d)로 온 '='
    '{"링크": "/DRF/x.do?OC%%3D%s%%26type%%3DHTML"}',                # URL 인코딩(%3D)
    '{"링크": "/DRF/x.do?a=1&amp;OC=%s&amp;type=HTML"}',            # HTML 이스케이프된 &
    '{"설정": "LAW_OC=%s"}',
])
def test_get_masks_encoded_forms(monkeypatch, raw):
    _fake_urlopen(monkeypatch, (raw % FAKE).encode())
    assert FAKE not in _dump(law._get("lawService.do", "target=eflaw"))


def test_scrub_keeps_placeholders_and_body_text():
    """빈 값·이미 가린 값은 그대로, 본문 글자는 키와 우연히 같아도 바뀌지 않는다(OC= 뒤에 올 때만 가림)."""
    src = {"a": f"/DRF/x.do?{OC}&target=law", "b": f"x?{MASKED}&y=1", "본문": f"제1조 {FAKE} doc=abc", "n": 3, "l": [None, True]}
    assert law.scrub_oc(src) == src


def test_memory_cache_holds_masked_values(monkeypatch):
    """_get 위의 메모리 캐시(_versions)에 들어가는 값에도 키가 없다."""
    row = {"법령명한글": "법인세법", "시행일자": "20250101", "법령일련번호": "1", "법령상세링크": f"/DRF/lawService.do?{OC}{FAKE}&MST=1"}
    _fake_urlopen(monkeypatch, json.dumps({"LawSearch": {"totalCnt": "1", "law": [row]}}, ensure_ascii=False).encode())
    first = law._versions("법인세법")
    assert first and FAKE not in _dump(first)
    assert law._versions("법인세법") is first


def test_http_error_carries_no_key(monkeypatch):
    """법제처가 HTTP 오류로 답해도 올라오는 예외(메시지·이어 붙은 원인)에 키가 없다."""
    url = f"{law.DRF}/lawSearch.do?{OC}{FAKE}&type=JSON&target=eflaw"
    _fake_urlopen(monkeypatch, urllib.error.HTTPError(url, 500, f"Server Error at {url}", {}, io.BytesIO(b"")))
    with pytest.raises(RuntimeError) as ei:
        law._get("lawSearch.do", "target=eflaw")
    e = ei.value
    assert FAKE not in str(e) and MASKED in str(e)
    assert e.__cause__ is None and e.__suppress_context__      # 주소를 든 원래 예외가 traceback에 따라 나오지 않는다


def test_broken_response_error_carries_no_key(monkeypatch):
    """JSON이 아닌 응답(오류 안내 HTML)에 키가 섞여 와도 예외에 키가 없다."""
    _fake_urlopen(monkeypatch, f"<html><a href='/DRF/x.do?{OC}{FAKE}&type=HTML'>오류</a></html>".encode())
    with pytest.raises(RuntimeError) as ei:
        law._get("lawSearch.do", "target=eflaw")
    assert FAKE not in str(ei.value) and ei.value.__cause__ is None


def test_error_message_masks_bare_key():
    """오류 메시지는 OC= 없이 키만 적힌 경우도 가린다."""
    assert FAKE not in law._mask_oc(f"인증 실패: 사용자 {FAKE} 는 등록되지 않음, 요청 x?{OC}{FAKE}")


# ── 2·3. 저장소 전체 검사와 커밋 전 검사 ──

def _git_ok():
    return shutil.which("git") and shutil.which("bash") and subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True).returncode == 0


def _need_git():
    if _git_ok(): return
    if os.environ.get("CI"): pytest.fail("CI에서는 git 저장소 안에서 돌아야 한다 — 건너뛰면 검사가 조용히 꺼진다")
    pytest.skip("git 저장소가 아님(배포본에서 실행)")


# 임시 저장소에서 git을 돌릴 때는 개발자 PC의 전역 설정(core.hooksPath 등)을 읽지 않게 한다 — 훅이 엉뚱한 곳에 설치되지 않도록
ISOLATED = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _run(*args, cwd=ROOT, env=None):
    return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True, env=env)


def _git(cwd):
    return lambda *a, cwd=cwd: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                                              cwd=cwd, capture_output=True, text=True, env=ISOLATED)


def test_no_oc_key_in_tracked_files():
    _need_git()
    r = _run("--all")
    assert r.returncode == 0, "추적 파일에 법제처 OC 키로 보이는 값이 있음:\n" + r.stderr


BAD = [   # 걸려야 하는 모양
    '{"링크": "/DRF/lawService.do?%s%s&target=law"}' % (OC, FAKE),
    "https://www.law.go.kr/DRF/lawSearch.do?type=JSON&oc" + "=" + FAKE,
    "https://www.law.go.kr/DRF/lawSearch.do?OC%3D" + FAKE,
    '{"링크": "x?OC\\u003d' + FAKE + '"}',
    "LAW_" + OC + FAKE,
    '{"env": {"LAW_OC": "' + FAKE + '"}}',
    OC + "testing1",                                   # 허용 낱말로 시작해도 값 전체가 같지 않으면 걸린다
]
GOOD = [  # 걸리면 안 되는 자리표시
    OC + "***&a", OC + "{oc}", OC + "<키>", OC + "$LAW_OC", OC + "%s", OC + "&type=JSON", OC + "test&x", OC + "YOUR_KEY",
    "LAW_" + OC + "your_key", '"LAW_OC": "YOUR_OC"', "doc=abc123", "LAW_" + OC + "…", OC + "본인키",
]


@pytest.mark.parametrize("line", BAD)
def test_scanner_rings_on_fake_key(tmp_path, line):
    f = tmp_path / "raw.json"
    f.write_text("첫 줄\n" + line + "\n", encoding="utf-8")
    r = _run("--files", str(f))
    assert r.returncode == 1, line
    assert f"{f}:2" in r.stderr                         # 파일과 줄 번호만 알려 주고
    assert FAKE not in r.stdout + r.stderr              # 값은 찍지 않는다


def test_scanner_allows_placeholders(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("\n".join(GOOD) + "\n", encoding="utf-8")
    r = _run("--files", str(f))
    assert r.returncode == 0, r.stderr


def test_all_mode_rings_in_a_repo_with_a_leak(tmp_path):
    """--all 이 실제로 추적 파일을 읽는지 — 가짜 키를 커밋한 임시 저장소에서 울려 본다."""
    _need_git()
    g = _git(tmp_path)
    g("init", "-q")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "깨끗.json").write_text('{"링크": "x?%s&a=1"}' % MASKED, encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "clean")
    assert _run("--all", cwd=tmp_path, env=ISOLATED).returncode == 0
    (tmp_path / "data" / "출처 링크.json").write_text(BAD[0], encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "leak")
    r = _run("--all", cwd=tmp_path, env=ISOLATED)
    assert r.returncode == 1 and "data/출처 링크.json:1" in r.stderr and FAKE not in r.stderr, r.stderr


def test_pre_commit_hook_blocks_staged_fake_key(tmp_path):
    """설치한 훅이 가짜 키가 든 커밋을 막고, 가리면 통과시킨다. worktree에서도 같은 훅이 돈다."""
    _need_git()
    repo, wt = tmp_path / "repo", tmp_path / "wt"
    repo.mkdir()
    g = _git(repo)
    g("init", "-q"); (repo / "a.txt").write_text("a\n"); g("add", "-A"); g("commit", "-qm", "init")
    assert _run("--install", cwd=repo, env=ISOLATED).returncode == 0
    assert (repo / ".git" / "hooks" / "pre-commit").exists()
    g("worktree", "add", "-q", str(wt), "-b", "side")
    for where in (repo, wt):
        (where / "raw.json").write_text(BAD[0] + "\n", encoding="utf-8")
        g("add", "raw.json", cwd=where)
        r = g("commit", "-qm", "leak", cwd=where)
        assert r.returncode != 0 and "raw.json:1" in r.stderr and FAKE not in r.stdout + r.stderr, (where, r.stderr)
        (where / "raw.json").write_text(BAD[0].replace(FAKE, "***") + "\n", encoding="utf-8")
        g("add", "raw.json", cwd=where)
        r = g("commit", "-qm", "masked", cwd=where)
        assert r.returncode == 0, (where, r.stderr)


def test_redact_script_masks_before_saving(tmp_path):
    """원자료 저장 도우미(scripts/redact_oc.py)를 거친 파일은 검사를 통과한다."""
    raw = "\n".join(BAD) + "\n"
    env = {k: v for k, v in os.environ.items() if k != "LAW_OC"}
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "redact_oc.py")], input=raw, capture_output=True, text=True, env=env, encoding="utf-8")
    assert r.returncode == 0 and FAKE not in r.stdout and r.stdout.count("***") >= len(BAD) - 1, r.stdout
    f = tmp_path / "saved.json"
    f.write_text(r.stdout, encoding="utf-8")
    assert _run("--files", str(f)).returncode == 0
