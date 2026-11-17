#!/usr/bin/env bash
# Baseline measurement of the generated LMS: analyzer, feedback and held-out tests, the failing tests run twice
# more, the flaky list and a separate coverage run (ADR 003, D17-D19, D26).
#
#   scripts/measure_baseline.sh --label NAME (--code DIR | --code-ref GIT_REF) [options]
#
#   --label NAME        name of the measurement; results go to results/baseline/trial/NAME/ (--out changes it)
#   --code DIR          folder that contains lms/ (default for the final baseline: dataset/lms/generated)
#   --code-ref REF      measure the code of a git ref instead (dataset/lms/generated at REF, exported with git
#                       archive), e.g. ce03f54 for the pilot code or v0-ai-baseline
#   --modules 1-14      only the test files of these modules (pilot code has modules 1-14 only)
#   --second-full-run   a second full test run (final baseline; D18)
#   --skip-analysis     tests only          --skip-coverage    no coverage run
#   --timeout SECONDS   per test set, default 7200
#   --background        start detached, print the process ID; log: <out>/raw/measure.log
#   --wait SECONDS      wait this long for .run.lock (default 21600); exit code 3 if it stays
#   --poll SECONDS      pause between lock checks (default 60)
#   --lock-file PATH    default <repo>/.run.lock
#   --image NAME        Docker image (default refactoring-env)   --cpuset CPUS   --memory SIZE (recorded)
#   --local             run the steps here, without docker (inside the image; used by the tests)
#   --dry-run           print what would run and stop
#
# The run lock (.run.lock in the repository root) is taken before the run and removed after it; if it exists the
# script waits (docs/environment.md). Everything runs in the Docker image with the network off.
# Windows / Git Bash: MSYS_NO_PATHCONV=1 and `pwd -W` are used for the mounts.
# Exit code: 0 done · 2 usage error · 3 lock not free in time · 4 the measurement is invalid (baseline.json says why).

set -u
export MSYS_NO_PATHCONV=1
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="refactoring-env"
LABEL=""; CODE=""; CODE_REF=""; OUT=""; MODULES=""; BG=0; LOCAL=0; DRY=0
WAIT=21600; POLL=60; LOCK="$REPO/.run.lock"; CPUSET=""; MEMORY=""; TESTS=""
PASS=(); ORIG_ARGS=("$@")

die() { echo "measure_baseline: $*" >&2; exit "${2:-2}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --label) LABEL="${2:?}"; shift 2 ;;
    --code) CODE="${2:?}"; shift 2 ;;
    --code-ref) CODE_REF="${2:?}"; shift 2 ;;
    --out) OUT="${2:?}"; shift 2 ;;
    --tests) TESTS="${2:?}"; shift 2 ;;
    --modules) MODULES="${2:?}"; PASS+=(--modules "$2"); shift 2 ;;
    --second-full-run|--skip-analysis|--skip-coverage) PASS+=("$1"); shift ;;
    --timeout) PASS+=(--timeout "${2:?}"); shift 2 ;;
    --background) BG=1; shift ;;
    --wait) WAIT="${2:?}"; shift 2 ;;
    --poll) POLL="${2:?}"; shift 2 ;;
    --lock-file) LOCK="${2:?}"; shift 2 ;;
    --image) IMAGE="${2:?}"; shift 2 ;;
    --cpuset) CPUSET="${2:?}"; shift 2 ;;
    --memory) MEMORY="${2:?}"; shift 2 ;;
    --local) LOCAL=1; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,29p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[ -n "$LABEL" ] || die "--label is required"
{ [ -n "$CODE" ] && [ -n "$CODE_REF" ]; } && die "give --code or --code-ref, not both"
{ [ -z "$CODE" ] && [ -z "$CODE_REF" ]; } && die "give --code or --code-ref"
[ -n "$OUT" ] || OUT="results/baseline/trial/$LABEL"
case "$OUT" in /*) ;; *) OUT="$REPO/$OUT" ;; esac
[ "$LOCAL" = 1 ] || case "$OUT" in "$REPO"/*) ;; *) die "without --local the output folder must be inside the repository" ;; esac

hostpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -w "$1"; else printf '%s' "$1"; fi; }

# --- background: start the same command detached and return ------------------------------------------------
if [ "$BG" = 1 ] && [ -z "${MEASURE_CHILD:-}" ] && [ "$DRY" = 0 ]; then
  mkdir -p "$OUT/raw"
  args=(); for a in "${ORIG_ARGS[@]}"; do [ "$a" = "--background" ] || args+=("$a"); done
  MEASURE_CHILD=1 nohup bash "${BASH_SOURCE[0]}" "${args[@]}" > "$OUT/raw/measure.log" 2>&1 &
  echo "started, process ID $!; log: $OUT/raw/measure.log"
  exit 0
fi

# --- code: a folder, or the code of a git ref exported to a temporary folder -------------------------------
TMP=""; CODE_SHA=""; MOUNT_CODE=""; CODE_ARG=""
git_repo() { (cd "$REPO" && git -c safe.directory='*' "$@"); }
if [ -n "$CODE_REF" ]; then
  CODE_SHA="$(git_repo rev-parse --verify "$CODE_REF^{commit}" 2>/dev/null)" || die "unknown git ref: $CODE_REF"
  if [ "$DRY" = 1 ]; then TMP="<temporary folder>"; else
    TMP="$(mktemp -d)"
    git_repo archive "$CODE_SHA" dataset/lms/generated | tar -x -C "$TMP" || die "git archive failed"
  fi
  CODE_DIR="$TMP/dataset/lms/generated"; MOUNT_CODE="$CODE_DIR"; CODE_ARG="/code"
else
  case "$CODE" in /*) CODE_DIR="$CODE" ;; *) CODE_DIR="$REPO/$CODE" ;; esac
  [ -d "$CODE_DIR/lms" ] || die "no lms/ package in $CODE_DIR"
  CODE_DIR="$(cd "$CODE_DIR" && pwd)"
  case "$CODE_DIR" in "$REPO"/*) CODE_ARG="/work/${CODE_DIR#"$REPO"/}" ;; *) MOUNT_CODE="$CODE_DIR"; CODE_ARG="/code" ;; esac
fi
OUT_ARG="/work/${OUT#"$REPO"/}"
MOUNT_TESTS=""
if [ -n "$TESTS" ]; then
  case "$TESTS" in /*) ;; *) TESTS="$REPO/$TESTS" ;; esac
  [ -d "$TESTS" ] || die "tests folder not found: $TESTS"
  case "$TESTS" in "$REPO"/*) TESTS_ARG="/work/${TESTS#"$REPO"/}" ;; *) MOUNT_TESTS="$TESTS"; TESTS_ARG="/tests" ;; esac
fi

if [ "$LOCAL" = 1 ]; then
  CODE_ARG="$CODE_DIR"; OUT_ARG="$OUT"
  [ -z "$TESTS" ] || TESTS_ARG="$TESTS"
fi
[ -z "$TESTS" ] || PASS+=(--tests "$TESTS_ARG")
STEP_ARGS=(--code "$CODE_ARG" --out "$OUT_ARG" --label "$LABEL" "${PASS[@]}")
[ -z "$CODE_SHA" ] || STEP_ARGS+=(--code-sha "$CODE_SHA")

# --- the command ---------------------------------------------------------------------------------------------
if [ "$LOCAL" = 1 ]; then
  CMD=(python "$REPO/scripts/analyzer/baseline.py" "${STEP_ARGS[@]}")
else
  IMAGE_ID="$(docker image inspect "$IMAGE" --format '{{.Id}}' 2>/dev/null || echo unknown)"
  DOCKER=(docker run --rm --network none -e "ANALYZER_IMAGE_ID=$IMAGE_ID" -e "MEASURE_CPUSET=$CPUSET" -e "MEASURE_MEMORY=$MEMORY")
  [ -z "$CPUSET" ] || DOCKER+=(--cpuset-cpus "$CPUSET")
  [ -z "$MEMORY" ] || DOCKER+=(--memory "$MEMORY")
  DOCKER+=(-v "$(hostpath "$REPO"):/work")
  [ -z "$MOUNT_CODE" ] || DOCKER+=(-v "$(hostpath "$MOUNT_CODE"):/code:ro")
  [ -z "$MOUNT_TESTS" ] || DOCKER+=(-v "$(hostpath "$MOUNT_TESTS"):/tests:ro")
  CMD=("${DOCKER[@]}" -w /work "$IMAGE" python scripts/analyzer/baseline.py "${STEP_ARGS[@]}")
fi

if [ "$DRY" = 1 ]; then
  echo "lock file:  $LOCK"
  echo "code:       ${CODE_REF:+$CODE_REF ($CODE_SHA), }$CODE_DIR"
  echo "output:     $OUT"
  printf 'command:   '; printf ' %q' "${CMD[@]}"; echo
  exit 0
fi

# --- run lock ------------------------------------------------------------------------------------------------
HELD=0
release() {
  if [ "$HELD" = 1 ] && grep -q "^pid=$$\$" "$LOCK" 2>/dev/null; then rm -f "$LOCK"; fi
  [ -z "$TMP" ] || rm -rf "$TMP"
}
trap release EXIT
trap 'exit 130' INT TERM
acquire() {
  ( set -C; printf 'who=%s@%s\nwhat=measure_baseline.sh %s\nstart=%s\npid=%s\n' "${USER:-${USERNAME:-unknown}}" "$(uname -n)" "$LABEL" \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$" > "$LOCK" ) 2>/dev/null
}
waited=0
while ! acquire; do
  if [ "$waited" -ge "$WAIT" ]; then
    echo "measure_baseline: $LOCK is still held after $waited s:" >&2; sed 's/^/    /' "$LOCK" >&2
    exit 3
  fi
  echo "[$(date -u +%H:%M:%S)] waiting for $LOCK ($(tr '\n' ' ' < "$LOCK" 2>/dev/null))"
  sleep "$POLL"; waited=$((waited + POLL))
done
HELD=1
echo "[$(date -u +%H:%M:%S)] lock taken: $LOCK"
mkdir -p "$OUT/raw"
export MEASURE_LOCK_FILE="$LOCK"

"${CMD[@]}"
status=$?
echo "[$(date -u +%H:%M:%S)] finished with exit code $status; lock released"
exit "$status"
