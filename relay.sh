#!/usr/bin/env bash
SELF="${BASH_SOURCE[0]}"
while [ -L "$SELF" ]; do
  DIR="$(cd -P "$(dirname "$SELF")" && pwd)"
  SELF="$(readlink "$SELF")"
  [[ "$SELF" != /* ]] && SELF="$DIR/$SELF"
done
exec python3 "$(cd -P "$(dirname "$SELF")" && pwd)/relay.py" "$@"
