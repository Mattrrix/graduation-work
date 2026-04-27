#!/usr/bin/env bash
# Управление AI-серверами для Phase 3 + Phase 6.
#
# Два сервера запускаются нативно на хосте macOS (Docker GPU passthrough
# на macOS не работает — MLX/Metal в контейнере = CPU only = в 3-5×
# медленнее). Контейнеры extract / transform дёргают через
# host.docker.internal:8111 (PaddleOCR) и :8112 (Qwen).
#
#   :8112  mlx_lm.server   — mlx-community/Qwen3.5-9B-MLX-4bit (NER + summary)
#   :8111  mlx_vlm.server  — PaddlePaddle/PaddleOCR-VL-1.5 (OCR)
#
# Использование:
#   bash infra/ai/serve.sh up      — поднять оба, ждать готовности.
#   bash infra/ai/serve.sh down    — остановить оба.
#   bash infra/ai/serve.sh status  — PID / RAM / uptime / health-ping.
#
# PID-файлы и логи лежат в .runtime/ (gitignored).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

VENV="$PROJECT_ROOT/.venv_ai"
RUNTIME_DIR="$PROJECT_ROOT/.runtime"
QWEN_MODEL="mlx-community/Qwen3.5-9B-MLX-4bit"
QWEN_PORT=8112
OCR_PORT=8111

mkdir -p "$RUNTIME_DIR"

# --- helpers ---------------------------------------------------------------

require_venv() {
    if [[ ! -x "$VENV/bin/mlx_lm.server" ]] || [[ ! -x "$VENV/bin/mlx_vlm.server" ]]; then
        echo "[!] .venv_ai не найден или повреждён."
        echo "    Создать: python3.12 -m venv .venv_ai && \\"
        echo "             .venv_ai/bin/pip install -r infra/ai/requirements.txt"
        exit 1
    fi
}

is_alive() {
    local pidfile="$1"
    [[ -f "$pidfile" ]] && kill -0 "$(cat "$pidfile")" 2>/dev/null
}

start_server() {
    local name="$1" port="$2" log="$3" pid="$4"
    shift 4
    if is_alive "$pid"; then
        echo "[=] $name уже запущен (PID $(cat "$pid"), порт $port)."
        return 0
    fi
    echo "[+] Запускаю $name на :$port..."
    "$@" > "$log" 2>&1 &
    echo $! > "$pid"
    # Ждём пока uvicorn / httpd скажет что слушает.
    local deadline=$(( $(date +%s) + 60 ))
    while (( $(date +%s) < deadline )); do
        if grep -qE "Uvicorn running|Starting httpd at" "$log" 2>/dev/null; then
            echo "    готов (PID $(cat "$pid"))."
            return 0
        fi
        if ! kill -0 "$(cat "$pid")" 2>/dev/null; then
            echo "[!] $name упал. Последние строки лога:"
            tail -20 "$log" | sed 's/^/    /'
            return 1
        fi
        sleep 1
    done
    echo "[!] $name не стартовал за 60с. Лог: $log"
    return 1
}

stop_server() {
    local name="$1" pid="$2"
    if ! is_alive "$pid"; then
        echo "[=] $name не запущен."
        rm -f "$pid"
        return 0
    fi
    local p
    p=$(cat "$pid")
    echo "[-] Останавливаю $name (PID $p)..."
    kill "$p" 2>/dev/null || true
    # Graceful wait, потом SIGKILL.
    for _ in 1 2 3 4 5; do
        kill -0 "$p" 2>/dev/null || break
        sleep 1
    done
    if kill -0 "$p" 2>/dev/null; then
        echo "    SIGTERM не помог, SIGKILL."
        kill -9 "$p" 2>/dev/null || true
    fi
    rm -f "$pid"
}

ping_server() {
    local url="$1"
    if curl -sf -m 2 "$url" >/dev/null 2>&1; then
        echo "OK"
    else
        echo "FAIL"
    fi
}

show_one() {
    local name="$1" pid="$2" port="$3" healthurl="$4"
    if is_alive "$pid"; then
        local p rss etime
        p=$(cat "$pid")
        rss=$(ps -p "$p" -o rss= 2>/dev/null | awk '{printf "%.1f GB", $1/1024/1024}')
        etime=$(ps -p "$p" -o etime= 2>/dev/null | xargs)
        printf "  %-20s PID %-7s RSS %-9s up %-10s health %s\n" \
            "$name" "$p" "$rss" "$etime" "$(ping_server "$healthurl")"
    else
        printf "  %-20s — не запущен\n" "$name"
    fi
}

# --- commands --------------------------------------------------------------

cmd_up() {
    require_venv
    start_server "Qwen NER (:$QWEN_PORT)" "$QWEN_PORT" \
        "$RUNTIME_DIR/mlx_lm.log" "$RUNTIME_DIR/mlx_lm.pid" \
        "$VENV/bin/mlx_lm.server" \
            --host 0.0.0.0 --port "$QWEN_PORT" \
            --model "$QWEN_MODEL" \
            --log-level INFO

    start_server "PaddleOCR (:$OCR_PORT)" "$OCR_PORT" \
        "$RUNTIME_DIR/mlx_vlm.log" "$RUNTIME_DIR/mlx_vlm.pid" \
        "$VENV/bin/mlx_vlm.server" \
            --host 0.0.0.0 --port "$OCR_PORT" \
            --kv-bits 8

    echo
    cmd_status
}

cmd_down() {
    stop_server "Qwen NER"   "$RUNTIME_DIR/mlx_lm.pid"
    stop_server "PaddleOCR"  "$RUNTIME_DIR/mlx_vlm.pid"
}

cmd_status() {
    echo "AI-сервера:"
    show_one "Qwen NER (:$QWEN_PORT)"  "$RUNTIME_DIR/mlx_lm.pid"  "$QWEN_PORT"  "http://127.0.0.1:$QWEN_PORT/v1/models"
    show_one "PaddleOCR (:$OCR_PORT)"  "$RUNTIME_DIR/mlx_vlm.pid" "$OCR_PORT"   "http://127.0.0.1:$OCR_PORT/health"
    echo
    echo "Логи: tail -f $RUNTIME_DIR/{mlx_lm,mlx_vlm}.log"
}

case "${1:-status}" in
    up|start)    cmd_up ;;
    down|stop)   cmd_down ;;
    status|ps)   cmd_status ;;
    restart)     cmd_down; cmd_up ;;
    *)
        echo "usage: $0 {up|down|status|restart}" >&2
        exit 2
        ;;
esac
