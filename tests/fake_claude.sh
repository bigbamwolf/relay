#!/usr/bin/env bash
# Stand in for the claude CLI. FAKE_CAPPED is a comma list of models that report a usage cap.
# FAKE_MODE=auth or FAKE_MODE=budget or FAKE_MODE=crash forces that failure on every model.
model=""
while [ $# -gt 0 ]; do
  case "$1" in --model) model="$2"; shift 2 ;; *) shift ;; esac
done
case "${FAKE_MODE:-}" in
  auth)   echo '{"is_error":true,"result":"Failed to authenticate. API Error: 401"}'; exit 1 ;;
  budget) echo '{"is_error":true,"subtype":"error_max_budget_usd","result":""}'; exit 1 ;;
  crash)  echo 'segfault in something' >&2; exit 139 ;;
esac
case ",${FAKE_CAPPED:-}," in
  *",$model,"*) echo '{"is_error":true,"result":"Claude usage limit reached. Your limit resets at 5pm"}'; exit 1 ;;
esac
echo "{\"is_error\":false,\"result\":\"answer from $model\"}"
