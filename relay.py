#!/usr/bin/env python3
"""RELAY. When a Claude usage cap hits, drop a model tier instead of stopping."""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys

__version__ = "1.0.0"

HOME = os.path.expanduser("~")
RELAY_HOME = os.environ.get("RELAY_HOME", os.path.join(HOME, ".relay"))
LOG = os.environ.get("RELAY_LOG", os.path.join(RELAY_HOME, "relay.log"))
CLAUDE_BIN = os.environ.get("RELAY_CLAUDE_BIN") or shutil.which("claude") or os.path.join(HOME, ".local", "bin", "claude")
PROJECT_DIR = os.environ.get("RELAY_CWD", os.getcwd())
ENV_FILE = os.environ.get("RELAY_ENV_FILE", "")
PERMISSION_MODE = os.environ.get("RELAY_PERMISSION_MODE", "")
TIMEOUT = int(os.environ.get("RELAY_TIMEOUT", "1800"))

DEFAULT_LADDER = "claude-opus-5-5,claude-sonnet-5-5,claude-haiku-4-5-20251001"

LIMIT_PAT = ["usage limit", "rate limit", "limit reached", "resets at", "overloaded",
             "too many requests", "quota", "529", "rate_limit", "try again later",
             "capacity", "exceeded"]

AUTH_PAT = ["failed to authenticate", "oauth access token has expired", "401",
            "re-authenticate", "invalid api key", "unauthorized"]

BUDGET_PAT = ["max-budget", "max budget", "budget exceeded", "exceeded budget", "error_max_budget"]


def ladder():
    raw = os.environ.get("RELAY_LADDER", DEFAULT_LADDER)
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return [(f"H{i + 1}", m) for i, m in enumerate(models)]


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def hits(text, pats):
    t = (text or "").lower()
    return any(k in t for k in pats)


def logline(msg):
    try:
        os.makedirs(os.path.dirname(LOG) or ".", exist_ok=True)
        with open(LOG, "a") as f:
            f.write(f"[{now()}] {msg}\n")
    except OSError:
        pass


def child_env():
    env = dict(os.environ)
    if ENV_FILE:
        try:
            with open(os.path.expanduser(ENV_FILE)) as f:
                for line in f:
                    m = re.match(r"\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)=(.*)", line.strip())
                    if m:
                        env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
        except OSError:
            logline(f"env file not readable: {ENV_FILE}")
    local_bin = os.path.join(HOME, ".local", "bin")
    if local_bin not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = local_bin + os.pathsep + env.get("PATH", "")
    for k in list(env):
        if k.startswith("RELAY_"):
            env.pop(k)
    return env


def run_head(model, prompt, budget):
    cmd = [CLAUDE_BIN, "-p", prompt, "--model", model,
           "--output-format", "json", "--max-budget-usd", str(budget)]
    if PERMISSION_MODE:
        cmd += ["--permission-mode", PERMISSION_MODE]
    try:
        r = subprocess.run(cmd, cwd=PROJECT_DIR, env=child_env(), capture_output=True,
                           text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return 124, "", "relay timeout"
    except FileNotFoundError:
        return 127, "", f"claude CLI not found at {CLAUDE_BIN}"
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def parse(raw):
    line = ""
    for ln in reversed((raw or "").strip().splitlines()):
        if ln.startswith("{"):
            line = ln
            break
    try:
        return json.loads(line) if line else {}
    except ValueError:
        return {}


def relay(prompt, budget, floor):
    heads = ladder()
    if floor:
        keep = [i for i, (tag, _) in enumerate(heads) if tag == floor.upper()]
        if not keep:
            print(f"[RELAY] unknown floor {floor}, ladder is {', '.join(t for t, _ in heads)}", file=sys.stderr)
            return 1
        heads = heads[:keep[0] + 1]
    for tag, model in heads:
        logline(f"{tag} {model} attempt")
        rc, raw, err = run_head(model, prompt, budget)
        j = parse(raw)
        blob = raw + "\n" + err + "\n" + json.dumps(j)
        result = j.get("result") or err or raw
        ok = rc == 0 and not j.get("is_error")
        if ok:
            logline(f"{tag} {model} ANSWERED")
            print(f"[RELAY {tag} {model}]")
            print(result)
            return 0
        if hits(blob, AUTH_PAT):
            logline(f"{tag} {model} AUTH DEAD, halting ladder")
            print(f"[RELAY HALT] auth failure at {tag}, this is not a rate limit.")
            print("Re-authenticate the claude CLI, the ladder will not paper over a dead login.")
            print(f"detail: {' '.join((result or '').split())[:200]}")
            return 2
        if hits(blob, BUDGET_PAT):
            logline(f"{tag} {model} BUDGET CEILING, halting ladder")
            print(f"[RELAY HALT] budget ceiling hit at {tag}. That is your own limit, not a cap.")
            print(f"detail: {' '.join((result or '').split())[:200]}")
            return 5
        if hits(blob, LIMIT_PAT):
            logline(f"{tag} {model} CAPPED, dropping a tier")
            print(f"[RELAY] {tag} {model} capped, dropping a tier", file=sys.stderr)
            continue
        logline(f"{tag} {model} hard error rc={rc}, halting ladder")
        print(f"[RELAY HALT] {tag} failed with a non limit error, not laddering.")
        print(f"detail: {' '.join((result or '').split())[:300]}")
        return 3
    logline("every head capped")
    print("[RELAY] every head is capped. Nothing left to drop to.")
    print("Save the task and retry after the limit resets.")
    return 4


USAGE = """usage: relay "your prompt" [--budget 5] [--floor H2]
       echo "your prompt" | relay -

  --budget USD   max spend per attempt, passed to claude --max-budget-usd (default 5)
  --floor  H2    never drop below this head, halt instead of answering from a lower tier
  --ladder       print the configured ladder and exit
  --version      print the version and exit"""


def main():
    args = sys.argv[1:]
    budget, floor = 5.0, ""
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("-h", "--help"):
            print(USAGE)
            sys.exit(0)
        if a == "--version":
            print(f"relay {__version__}")
            sys.exit(0)
        if a == "--ladder":
            for tag, model in ladder():
                print(f"{tag}  {model}")
            sys.exit(0)
        if a == "--budget" and i + 1 < len(args):
            try:
                budget = float(args[i + 1])
            except ValueError:
                print("--budget needs a number", file=sys.stderr)
                sys.exit(1)
            i += 2
        elif a == "--floor" and i + 1 < len(args):
            floor = args[i + 1]
            i += 2
        else:
            rest.append(a)
            i += 1
    if rest == ["-"]:
        prompt = sys.stdin.read().strip()
    else:
        prompt = " ".join(rest).strip()
    if not prompt:
        print(USAGE)
        sys.exit(1)
    sys.exit(relay(prompt, budget, floor))


if __name__ == "__main__":
    main()
