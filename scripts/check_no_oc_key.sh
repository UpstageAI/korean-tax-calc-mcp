#!/usr/bin/env bash
# 법제처 Open API 키(OC 값)가 저장소에 들어가지 못하게 막는 검사.
#
# 법제처 DRF는 키를 주소에 붙이고(…?OC=<키>&…), 응답 JSON의 링크에도 같은 주소를 되돌려 준다.
# 응답을 그대로 저장하거나 출처 링크를 데이터 파일로 옮기면 키가 따라 들어가므로, 값이 아니라 모양(패턴)으로 잡는다.
#
#   bash scripts/check_no_oc_key.sh             스테이징된 파일(커밋될 내용)을 검사 — pre-commit 훅이 부른다
#   bash scripts/check_no_oc_key.sh --all       추적 파일 전체(git ls-files)를 검사 — 테스트·CI가 부른다
#   bash scripts/check_no_oc_key.sh --files F…  지정한 파일을 검사
#   bash scripts/check_no_oc_key.sh --install   이 저장소의 pre-commit 훅으로 설치(모든 worktree에 적용)
#
# 찾으면 '파일:줄 번호'만 찍고 1로 끝난다. 찾은 값은 화면에 찍지 않는다(터미널·에이전트 출력으로 새지 않게).
set -u
export LC_ALL=C

# 값으로 보는 글자: 영문·숫자와 . _ @ + - . 따라서 OC=***, OC={oc}, OC=<키>, OC=$LAW_OC, OC=%s, OC=&…(빈 값), OC=본인키는 걸리지 않는다.
V='[A-Za-z0-9._@+-]+'
EQ='(=|%3[Dd]|\\u003[Dd])'          # = 과 그 URL 인코딩(%3D)·JSON 이스케이프(=)
PATTERNS=(
  "(^|[^A-Za-z0-9_])OC${EQ}${V}"                                  # 주소·본문 어디든 OC=<값>
  "law\\.go\\.kr[^[:space:]\"']*[?&]([Oo][Cc])${EQ}${V}"         # law.go.kr 주소 속 oc=<값>(소문자 포함)
  "LAW_OC${EQ}${V}"                                                # 환경변수 줄 LAW_OC=<값>(.env·설정 예시)
  "\"LAW_OC\"[[:space:]]*:[[:space:]]*\"${V}\""                   # MCP 설정 JSON "LAW_OC": "<값>"
)
# 허용하는 자리표시(값 전체가 일치할 때만). 최소로 유지한다.
#   test·TEST        — 법제처 안내 문서의 예시 키, 테스트의 가짜 값
#   YOUR_…·your_…    — 문서의 '여기에 본인 키' 자리표시
#   xxx…·XXX…        — 문서의 가림 표기
#   optional         — README-EN 설정 예시("LAW_OC": "optional" — 넣지 않아도 된다는 뜻)
ALLOW='^(test|TEST|YOUR[A-Z_]*|your[a-z_-]*|xxx+|XXX+|optional)$'

ANY="$(printf '%s|' "${PATTERNS[@]}")"; ANY="${ANY%|}"

scan_stream() {   # 표준입력을 검사. 걸린 줄 번호를 한 줄에 하나씩 출력
  grep -naoE -- "$ANY" | while IFS= read -r hit; do
    ln="${hit%%:*}"; m="${hit#*:}"
    val="$(printf '%s' "$m" | sed -E 's/"$//; s/.*(=|%3[Dd]|\\u003[Dd]|:[[:space:]]*")//')"
    printf '%s' "$val" | grep -qE -- "$ALLOW" || printf '%s\n' "$ln"
  done | sort -un
}

install_hook() {
  local src dir hook
  src="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
  dir="$(git rev-parse --git-path hooks)" || exit 2      # core.hooksPath가 있으면 그곳, 없으면 공용 .git/hooks(모든 worktree 공용)
  mkdir -p "$dir"
  cp "$src" "$dir/check_no_oc_key.sh" && chmod +x "$dir/check_no_oc_key.sh"
  hook="$dir/pre-commit"
  if [ -f "$hook" ] && ! grep -q 'check_no_oc_key.sh' "$hook"; then
    printf '\n# 법제처 OC 키 검사\n"$(dirname "$0")/check_no_oc_key.sh" || exit 1\n' >> "$hook"   # 기존 훅 뒤에 덧붙임
  elif [ ! -f "$hook" ]; then
    printf '#!/usr/bin/env bash\n# 법제처 OC 키 검사\n"$(dirname "$0")/check_no_oc_key.sh" || exit 1\n' > "$hook"
  fi
  chmod +x "$hook"
  echo "설치됨: $hook"
}

mode="staged"; files=()
case "${1:-}" in
  --all) mode="all" ;;
  --files) mode="files"; shift; files=("$@") ;;
  --install) install_hook; exit 0 ;;
  "" ) ;;
  *) echo "사용법: $0 [--all | --files 파일… | --install]" >&2; exit 2 ;;
esac

found=0
report() {   # $1 = 표시할 경로, 표준입력 = 내용
  local lines
  lines="$(scan_stream)"
  [ -z "$lines" ] && return 0
  found=1
  printf '%s\n' "$lines" | while IFS= read -r ln; do echo "$1:$ln"; done >&2
}

if [ "$mode" = "files" ]; then
  for f in ${files[@]+"${files[@]}"}; do [ -f "$f" ] && report "$f" < "$f"; done
elif [ "$mode" = "all" ]; then
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "git 저장소가 아님" >&2; exit 2; }
  cd "$(git rev-parse --show-toplevel)" || exit 2
  # 먼저 한 번에 걸러 후보 파일만 자세히 본다(파일 수가 많아도 빠르게)
  while IFS= read -r -d '' f; do
    [ -f "$f" ] && report "$f" < "$f"
  done < <(git ls-files -z | xargs -0 grep -laE --null -- "$ANY" 2>/dev/null)
else
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "git 저장소가 아님" >&2; exit 2; }
  while IFS= read -r -d '' f; do
    report "$f" < <(git show ":$f" 2>/dev/null)      # 작업 폴더가 아니라 커밋될 내용(인덱스)을 본다
  done < <(git diff --cached --name-only --diff-filter=ACMR -z)
fi

if [ "$found" -ne 0 ]; then
  cat >&2 <<'EOF'
법제처 OC 키로 보이는 값이 있습니다(위 '파일:줄'). 값을 OC=*** 로 가린 뒤 다시 시도하세요.
  원자료 저장: python scripts/redact_oc.py < 받은파일 > 저장할파일
  자리표시(예: OC=test, OC={oc})는 걸리지 않습니다. 이미 push했다면 키를 재발급하세요.
EOF
  exit 1
fi
exit 0
