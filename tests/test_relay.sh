#!/usr/bin/env bash
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELAY="$HERE/../relay.py"
export RELAY_CLAUDE_BIN="$HERE/fake_claude.sh"
export RELAY_LOG="$(mktemp -d)/relay.log"
export RELAY_LADDER="model-a,model-b,model-c"
pass=0; fail=0

check() {
  local name="$1" want_rc="$2" want_out="$3"; shift 3
  out=$(env "$@" python3 "$RELAY" "hello" 2>&1); rc=$?
  if [ "$rc" = "$want_rc" ] && printf '%s' "$out" | grep -q -- "$want_out"; then
    echo "[ OK ] $name"; pass=$((pass+1))
  else
    echo "[FAIL] $name (rc=$rc) $out"; fail=$((fail+1))
  fi
}

check "H1 answers"                0 "answer from model-a"  FAKE_CAPPED=
check "H1 capped drops to H2"     0 "answer from model-b"  FAKE_CAPPED=model-a
check "H1 H2 capped drops to H3"  0 "answer from model-c"  FAKE_CAPPED=model-a,model-b
check "every head capped"         4 "every head is capped" FAKE_CAPPED=model-a,model-b,model-c
check "auth failure halts"        2 "RELAY HALT"           FAKE_MODE=auth
check "budget ceiling halts"      5 "budget ceiling"       FAKE_MODE=budget
check "hard error halts"          3 "non limit error"      FAKE_MODE=crash

out=$(FAKE_CAPPED=model-a,model-b python3 "$RELAY" --floor H2 "hello" 2>&1); rc=$?
if [ "$rc" = 4 ]; then echo "[ OK ] floor H2 refuses H3"; pass=$((pass+1)); else echo "[FAIL] floor H2 (rc=$rc)"; fail=$((fail+1)); fi

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
