#!/usr/bin/env bash
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="$BACKEND_DIR/.runtime"
PG_PREFIX="$RUNTIME_DIR/pg16"
PG_BIN="$PG_PREFIX/usr/lib/postgresql/16/bin"
PG_LIB="$PG_PREFIX/usr/lib/x86_64-linux-gnu"
PG_DATA="$RUNTIME_DIR/postgres-wsl-data"
PG_LOG="$RUNTIME_DIR/postgres-wsl.log"
BACKEND_LOG="$RUNTIME_DIR/backend.wsl.log"
PORT="${PORT:-8000}"
BACKEND_PIDFILE="$RUNTIME_DIR/pids/backend.wsl.pid"

mkdir -p "$RUNTIME_DIR/debs" "$PG_PREFIX" "$RUNTIME_DIR/pids"

port_listener_lines() {
  ss -H -ltnp 2>/dev/null | awk -v port="$PORT" '$1 == "LISTEN" && $4 ~ (":" port "$")'
}

port_in_use() {
  [ -n "$(port_listener_lines)" ]
}

port_listener_pids() {
  port_listener_lines | grep -o 'pid=[0-9]\+' | awk -F= '{print $2}' | sort -u || true
}

process_args() {
  ps -p "$1" -o args= 2>/dev/null || true
}

is_backend_listener() {
  local pid="$1"
  local args

  args="$(process_args "$pid")"
  case "$args" in
    *uvicorn*"app.main:app"*|*"app.main:app"*uvicorn*)
      return 0
      ;;
  esac

  return 1
}

terminate_pid() {
  local pid="$1"
  local label="$2"

  if ! kill -0 "$pid" 2>/dev/null; then
    return 0
  fi

  echo "Stopping $label (pid $pid)..."
  kill "$pid" 2>/dev/null || true

  for _ in $(seq 1 20); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  echo "$label (pid $pid) did not stop after SIGTERM; sending SIGKILL..."
  kill -KILL "$pid" 2>/dev/null || true

  for _ in $(seq 1 10); do
    if ! kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
    sleep 0.2
  done

  return 1
}

cleanup_pidfile_process() {
  local pid

  if [ ! -f "$BACKEND_PIDFILE" ]; then
    return 0
  fi

  pid="$(awk 'NR == 1 {print $1}' "$BACKEND_PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && [ "$pid" -eq "$pid" ] 2>/dev/null; then
    terminate_pid "$pid" "pidfile backend" || true
  fi

  rm -f "$BACKEND_PIDFILE"
}

fail_port_busy() {
  echo "ERROR: Port $PORT is still in use; backend was not started." >&2
  echo "Listeners detected by ss:" >&2
  port_listener_lines >&2 || true
  exit 1
}

prepare_backend_port() {
  local pids pid args

  if ! command -v ss >/dev/null 2>&1; then
    echo "ERROR: ss is required to check port $PORT before backend startup." >&2
    exit 1
  fi

  if port_in_use; then
    echo "Port $PORT is already in use; checking for stale backend processes..."
  fi

  cleanup_pidfile_process

  if port_in_use; then
    pids="$(port_listener_pids)"
    if [ -z "$pids" ]; then
      fail_port_busy
    fi

    for pid in $pids; do
      if is_backend_listener "$pid"; then
        terminate_pid "$pid" "uvicorn backend listener on port $PORT" || true
      else
        args="$(process_args "$pid")"
        echo "Refusing to stop non-backend listener on port $PORT (pid $pid): ${args:-unknown command}" >&2
      fi
    done
  fi

  if port_in_use; then
    fail_port_busy
  fi
}

if [ ! -x "$PG_BIN/postgres" ]; then
  (
    cd "$RUNTIME_DIR/debs"
    apt-get download postgresql-16 postgresql-client-16 libpq5
  )
  for deb in "$RUNTIME_DIR"/debs/*.deb; do
    dpkg-deb -x "$deb" "$PG_PREFIX"
  done
fi

export LD_LIBRARY_PATH="$PG_LIB${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

if [ ! -d "$PG_DATA/base" ]; then
  rm -rf "$PG_DATA"
  "$PG_BIN/initdb" -D "$PG_DATA" --username=postgres --auth-local=trust --auth-host=scram-sha-256 --encoding=UTF8 --locale=C.UTF-8
  {
    echo
    echo "listen_addresses = '127.0.0.1'"
    echo "port = 5433"
    echo "unix_socket_directories = '$RUNTIME_DIR'"
  } >> "$PG_DATA/postgresql.conf"
fi

if ! "$PG_BIN/pg_isready" -h 127.0.0.1 -p 5433 -U postgres >/dev/null 2>&1; then
  "$PG_BIN/pg_ctl" -D "$PG_DATA" -l "$PG_LOG" -o "-p 5433 -k '$RUNTIME_DIR'" start
fi

for _ in $(seq 1 30); do
  "$PG_BIN/pg_isready" -h 127.0.0.1 -p 5433 -U postgres >/dev/null 2>&1 && break
  sleep 1
done

"$PG_BIN/psql" -h "$RUNTIME_DIR" -p 5433 -U postgres -tc "SELECT 1 FROM pg_roles WHERE rolname='prism'" | grep -q 1 ||
  "$PG_BIN/psql" -h "$RUNTIME_DIR" -p 5433 -U postgres -c "CREATE ROLE prism LOGIN PASSWORD 'prism123';"
"$PG_BIN/psql" -h "$RUNTIME_DIR" -p 5433 -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='prism_metabolic'" | grep -q 1 ||
  "$PG_BIN/createdb" -h "$RUNTIME_DIR" -p 5433 -U postgres -O prism prism_metabolic
"$PG_BIN/psql" -h "$RUNTIME_DIR" -p 5433 -U postgres -d prism_metabolic -c "GRANT CREATE ON SCHEMA public TO prism;" >/dev/null

if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
  python3 -m venv "$BACKEND_DIR/.venv"
fi

(
  cd "$BACKEND_DIR"
  . .venv/bin/activate
  python -m pip install -r requirements.txt
  python -m alembic upgrade head
  python -m app.seed.knowledge_seed --dataset core_v1
  prepare_backend_port
  setsid nohup uvicorn app.main:app --host 0.0.0.0 --port "$PORT" </dev/null > "$BACKEND_LOG" 2>&1 &
  echo "$!" > "$BACKEND_PIDFILE"
)

echo "Prism backend started on http://127.0.0.1:$PORT"
