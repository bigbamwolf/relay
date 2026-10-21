# RELAY

**When a Claude usage cap hits, drop a model tier instead of stopping.**

A tiny standalone CLI that wraps the headless [Claude Code](https://claude.com/claude-code) CLI (`claude -p`). It sends your prompt to the strongest model first. If that model is capped or overloaded, it hands the same prompt to the next tier down. It never ladders on any other kind of failure.

```bash
relay "summarize the open TODOs in this repo"
```

```
[RELAY H2 claude-sonnet-5]
...the answer...
```

The tag on the first line tells you, and any script reading the output, exactly which tier answered. No silent downgrade.

## The problem

You run Claude headless from a cron job, a script, or a long agent pipeline. Partway through the day the top model hits its usage limit. Every job after that fails, even though a smaller model would have answered the prompt just fine.

The naive fix is a retry loop. That is worse: it hammers a capped model, and it also retries failures that will never recover, like an expired login, so it hides the real problem.

RELAY does one narrow thing. It reads **why** a call failed, and only steps down a tier when the reason is a cap.

## Routing law

```diff
+ cap or overload      -> drop one tier, stamp the head that answered
+ every head capped    -> stop, exit 4, do not spin
- auth failure         -> HALT, never ladder a dead login
- budget ceiling hit   -> HALT, that is your own ceiling, not a cap
- any other hard error -> HALT, a ladder is not a retry loop
```

## Install

Requires Python 3.8+ (standard library only) and the `claude` CLI on your PATH, already logged in.

```bash
git clone https://github.com/bigbamwolf/relay.git
cd relay
./install.sh
```

That symlinks `relay` into `~/.local/bin`. Verify with `relay --ladder`.

## Usage

```
relay "your prompt"                  run the prompt down the ladder
relay "your prompt" --budget 2       cap spend per attempt, in USD (default 5)
relay "your prompt" --floor H2       never answer from below H2, halt instead
echo "your prompt" | relay -         read the prompt from stdin
relay --ladder                       print the configured ladder
relay --version
```

Use `--floor` when quality matters more than completion. With `--floor H2`, a capped H1 and a capped H2 end the run with exit 4 instead of quietly answering from the smallest model.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | answered, first stdout line is `[RELAY <head> <model>]` |
| `1` | usage error, or unknown `--floor` |
| `2` | auth failure, re authenticate the `claude` CLI |
| `3` | hard error that is not a cap, not laddered |
| `4` | every head in range is capped |
| `5` | the per attempt budget ceiling was hit |

### In a script

```bash
out=$(relay --floor H2 "draft a reply to this ticket: $ticket") || {
  echo "relay stopped with $?, try again after the reset" >&2
  exit 1
}
head=$(printf '%s\n' "$out" | head -1)
body=$(printf '%s\n' "$out" | tail -n +2)
```

## How it works

```
relay "prompt"
   |
   v
H1  claude -p --model <top>      answered?  print [RELAY H1 ...] + result, exit 0
   |  failed
   v
read stdout, stderr and the JSON result
   +-- auth pattern?     HALT exit 2
   +-- budget pattern?   HALT exit 5
   +-- cap pattern?      drop to H2, same prompt
   +-- anything else     HALT exit 3
   |
   v
H2 ... H3 ... out of heads   exit 4
```

Every attempt and outcome is appended to a log, so you can audit after the fact which runs were downgraded and why.

## Configuration

All optional, all environment variables:

| Variable | Default | What it does |
|---|---|---|
| `RELAY_LADDER` | `claude-opus-5,claude-sonnet-5,claude-haiku-4-5-20251001` | comma list of models, strongest first |
| `RELAY_CLAUDE_BIN` | `which claude` | path to the Claude Code CLI |
| `RELAY_CWD` | current dir | working dir each attempt runs in |
| `RELAY_PERMISSION_MODE` | unset | passed as `--permission-mode` when set |
| `RELAY_ENV_FILE` | unset | a `KEY=value` file loaded into the child env, for headless auth |
| `RELAY_TIMEOUT` | `1800` | seconds before one attempt is killed |
| `RELAY_HOME` | `~/.relay` | where the log lives |
| `RELAY_LOG` | `$RELAY_HOME/relay.log` | log file path |

Set `RELAY_LADDER` to whatever models your account can reach. Two tiers is fine.

## Tests

```bash
bash tests/test_relay.sh
```

Runs the whole routing law against a fake `claude` binary, no API calls, no spend.

## Limitations

* Failure detection is pattern matching on the CLI's output text. If the Claude CLI changes its error wording, a cap could be read as a hard error (safe, it halts) or the reverse. Check `RELAY_LOG` after upgrades.
* A lower tier is a weaker model. RELAY keeps a job alive, it does not promise the same quality. Use `--floor` where that matters, and read the head tag.
* It is one prompt in, one answer out. It does not resume a half finished agent session on the next tier.
* It does not wait for a cap to reset. When every head is capped it stops and says so.

## License

MIT. See [LICENSE](LICENSE).
