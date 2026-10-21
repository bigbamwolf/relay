#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${HOME}/.local/bin"

command -v python3 >/dev/null || { echo "python3 not found"; exit 1; }
command -v claude  >/dev/null || echo "warning: 'claude' CLI not on PATH, set RELAY_CLAUDE_BIN"

mkdir -p "$BIN"
chmod +x "${ROOT}/relay.py" "${ROOT}/relay.sh"
ln -sf "${ROOT}/relay.sh" "${BIN}/relay"

echo "installed: ${BIN}/relay -> ${ROOT}/relay.sh"
case ":${PATH}:" in
  *":${BIN}:"*) ;;
  *) echo "note: add ${BIN} to your PATH" ;;
esac
echo "try: relay --ladder"
