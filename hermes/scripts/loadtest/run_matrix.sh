#!/usr/bin/env bash
# Hermes load test (10.11): simulated students against Hermes in a Linux container of 2 vCPU, the model replaced by a
# stub (no OpenRouter call, nothing paid). Every variant × every N, each run on a fresh container (cold caches), the
# variants interleaved per N so a drift of the host hits them alike.
#
# Set up once (macOS, Colima; a profile of its own, the default one untouched):
#   colima start loadtest --cpu 2 --memory 4 --disk 20 --vm-type vz
#   colima ssh -p loadtest -- top -b -n1 | head -12   # systemd-logind spinning at ~80 % CPU (seen 10.11) → restart it:
#   colima ssh -p loadtest -- sudo systemctl restart systemd-logind
#   cd hermes && docker --context colima-loadtest build -t hermes-loadtest -f scripts/loadtest/Dockerfile .
#   WORK=<dir under $HOME (the VM sees only $HOME)>; per variant WORK/code/<variant>/ = a copy of hermes/ without .env
#   python loadgen.py --n 20 --write-games $WORK/games.json        # the students' games (needs a local stockfish)
#   python stub_llm.py --port 9999 &                                 # on the host
# Run, then read:
#   WORK=… PY=<python with httpx, chess> run_matrix.sh "1 5 10 20" "main branch branch-noplan" 240
#   python report.py $WORK/results
# Variants: a directory name under code/; <name>-noplan adds COACH_PRECOMPUTE_PLAN=0, off = branch with
# COACH_PRECOMPUTE=0. Afterwards: colima stop loadtest && colima delete loadtest; docker context use default.
set -u
NS=${1:-"1 5 10 20"}
VARIANTS=${2:-"main branch noplan"}
DURATION=${3:-240}
WORK=${WORK:?set WORK}
CTX=${DOCKER_CONTEXT_NAME:-colima-loadtest}
PY=${PY:-python3}
HERE=$(cd "$(dirname "$0")" && pwd)
STUB=${STUB_URL:-http://host.lima.internal:9999/v1}
mkdir -p "$WORK/results"
for n in $NS; do
  for v in $VARIANTS; do
    code=$v; extra=()
    case $v in
      noplan) code=branch; extra=(-e COACH_PRECOMPUTE_PLAN=0) ;;
      *-noplan) code=${v%-noplan}; extra=(-e COACH_PRECOMPUTE_PLAN=0) ;;
      off) code=branch; extra=(-e COACH_PRECOMPUTE=0) ;;
    esac
    name=hermes-lt
    docker --context "$CTX" rm -f $name >/dev/null 2>&1
    docker --context "$CTX" run -d --name $name -p 8642:8642 \
      -v "$WORK/code/$code:/app" -v "$WORK:/w" -w /app \
      -e PYTHONDONTWRITEBYTECODE=1 -e HERMES_HOME=/app/profiles/chess-coach \
      -e OPENROUTER_API_KEY=sk-stub-not-a-key -e BENCH_STUB_URL="$STUB" -e BENCH_GAMES_JSON=/w/games.json \
      -e COACH_EMIT_USAGE=1 -e COACH_TABLEBASE_URL=http://127.0.0.1:9/x ${extra[@]+"${extra[@]}"} \
      hermes-loadtest python scripts/loadtest/launcher.py >/dev/null
    for _ in $(seq 1 90); do
      curl -sf localhost:8642/health >/dev/null 2>&1 && break
      sleep 1
    done
    sleep 3
    echo "$(date +%T) run $v n=$n"
    "$PY" "$HERE/loadgen.py" --url http://127.0.0.1:8642 --games "$WORK/games.json" --n "$n" \
      --duration "$DURATION" --out "$WORK/results/$v-n$n.json"
    docker --context "$CTX" logs $name > "$WORK/results/$v-n$n.log" 2>&1
    docker --context "$CTX" rm -f $name >/dev/null 2>&1
  done
done
echo "$(date +%T) matrix done"
