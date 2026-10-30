#!/usr/bin/env bash
# Checks that Claude Code runs with the Pro subscription inside a fresh container.
# The credential comes only from CLAUDE_CODE_OAUTH_TOKEN (created once with `claude setup-token`,
# passed with `docker run --env-file .env`). Nothing is kept between containers.
#
# Usage (from the repository root):
#   docker run --rm --env-file .env -v "$PWD:/work" refactoring-env check-claude
# Writes the JSON answer of the test call to docker/claude-sample.json (used to build the cost log).
set -u
MODEL=${MODEL:-claude-sonnet-5-5}
fails=0
ok()   { printf 'OK    %s\n' "$*"; }
bad()  { printf 'FAIL  %s\n' "$*"; fails=$((fails + 1)); }
info() { printf 'INFO  %s\n' "$*"; }

echo "== Clean start"
if [ -e "$HOME/.claude" ] || [ -e "$HOME/.claude.json" ]; then
    bad "~/.claude already exists: the container is not clean"
else
    ok "no ~/.claude: no earlier login, settings, memory or history"
fi
if [ -n "${ANTHROPIC_API_KEY:-}" ] || [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
    bad "ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN is set: it would be used instead of the Pro subscription"
fi
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
    ok "CLAUDE_CODE_OAUTH_TOKEN is set (value not shown)"
    # Format checks only; the token itself is never printed
    tok=$CLAUDE_CODE_OAUTH_TOKEN
    info "token length: ${#tok} characters"
    case "$tok" in
        sk-ant-oat01-*) ok "token starts with sk-ant-oat01- (format of claude setup-token)" ;;
        BURAYA*|*'<'*)  bad "the placeholder is still in .env: paste the real token" ;;
        *)              printf 'WARN  token does not start with sk-ant-oat01-: probably not copied completely\n' ;;
    esac
    if [[ "$tok" =~ [[:space:]] ]]; then bad "token contains a space or line break: put it on one line in .env"; fi
    if [[ "$tok" == *\"* || "$tok" == *\'* ]]; then bad "token contains quotes: remove them in .env"; fi
else
    bad "CLAUDE_CODE_OAUTH_TOKEN is not set: run with --env-file .env (docs/environment.md)"
fi
info "claude-code $(claude --version 2>&1)"
info "auto-update disabled: DISABLE_AUTOUPDATER=${DISABLE_AUTOUPDATER:-unset}"

echo
echo "== Test call with the Pro subscription (model: $MODEL)"
work=$(mktemp -d)          # empty project folder: no CLAUDE.md, no .claude/settings
out=$work/answer.json
start=$(date +%s)
( cd "$work" && claude -p "Reply with exactly the word OK." --model "$MODEL" --output-format json ) >"$out" 2>"$work/stderr.txt"
code=$?
info "exit code $code, $(( $(date +%s) - start )) s"
if [ "$code" -ne 0 ]; then
    bad "claude -p failed"
    grep -q '401' "$out" "$work/stderr.txt" 2>/dev/null \
        && info "401 = the token was rejected: copied incompletely, has extra characters, or was revoked. Create a new one with: claude setup-token"
    sed 's/^/      /' "$work/stderr.txt" | tail -n 20
    head -c 2000 "$out" | sed 's/^/      /'
fi

if [ -s "$out" ]; then
    python - "$out" "$MODEL" <<'PY' || fails=$((fails + 1))
import json, sys
path, model = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
print("INFO  top-level fields:", ", ".join(sorted(data)))
print("INFO  result:", repr(str(data.get("result", ""))[:80]), "| is_error:", data.get("is_error"))
for key in ("total_cost_usd", "duration_ms", "duration_api_ms", "num_turns", "session_id"):
    if key in data:
        print(f"INFO  {key}: {data[key]}")
if "usage" in data:
    print("INFO  usage:", json.dumps(data["usage"])[:400])

# Which models were used? Look for a per-model breakdown (field name taken from the output)
breakdown = {k: v for k, v in data.items() if "model" in k.lower() and isinstance(v, dict)}
models = sorted({m for v in breakdown.values() for m in v})
print("INFO  per-model fields:", ", ".join(breakdown) or "none found")
print("INFO  models used:", ", ".join(models) or "unknown")

failed = False
if data.get("is_error"):
    print("FAIL  the call returned an error"); failed = True
if models and any(not m.startswith(model) for m in models):
    print(f"FAIL  a model other than {model} was used"); failed = True
elif models:
    print(f"OK    only {model} was used")
else:
    print("FAIL  no per-model breakdown found; model cannot be checked"); failed = True
sys.exit(1 if failed else 0)
PY
    if [ -d /work/docker ] && [ -w /work/docker ]; then
        cp "$out" /work/docker/claude-sample.json && info "saved docker/claude-sample.json"
    fi
else
    bad "no JSON answer"
fi

echo
echo "== After the call"
[ -e "$HOME/.claude" ] && info "~/.claude was created inside this container only; it disappears with the container (--rm)"

rm -rf "$work"
echo
if [ "$fails" -eq 0 ]; then echo "Claude Code + Pro login OK"; else echo "$fails check(s) FAILED"; fi
exit "$fails"
