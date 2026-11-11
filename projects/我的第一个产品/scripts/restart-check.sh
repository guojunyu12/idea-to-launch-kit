#!/usr/bin/env bash
set -u
PRODUCT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHECK_DIR="${RESTART_CHECK_DIR:-}"
[ -n "$CHECK_DIR" ] || { echo "RESTART_CHECK_DIR 未设置" >&2; exit 1; }
BACKEND="$PRODUCT_ROOT/backend"
PORT_FILE="$CHECK_DIR/port"
PID_FILE="$CHECK_DIR/pid"
DB_FILE="$CHECK_DIR/check.db"

start() {
  mkdir -p "$CHECK_DIR/storage"
  if [ -f "$PORT_FILE" ]; then
    PORT="$(cat "$PORT_FILE")"
  else
    PORT="$((18000 + RANDOM % 1000))"
    printf '%s' "$PORT" > "$PORT_FILE"
  fi
  if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
    echo "端口 $PORT 已被占用" >&2
    return 1
  fi
  PID="$(PYTHONPATH="$BACKEND" "$BACKEND/.venv/bin/python" "$PRODUCT_ROOT/scripts/start_service.py" "$BACKEND" "$CHECK_DIR" "$DB_FILE" "$PORT")"
  printf '%s' "$PID" > "$PID_FILE"
  for _ in $(seq 1 50); do
    if curl -fsS "http://127.0.0.1:$PORT/healthz" >/dev/null 2>&1; then
      printf '%s\n' "$PID"
      return 0
    fi
    sleep 0.1
  done
  echo "服务启动失败，见 $CHECK_DIR/server.log" >&2
  return 1
}

write_mark() {
  MARK="${1:-}"
  [ -n "$MARK" ] || { echo "缺少标记" >&2; exit 1; }
  PYTHONPATH="$BACKEND" "$BACKEND/.venv/bin/python" - "$DB_FILE" "$MARK" <<'PY'
import json
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.db import AuditEvent, Base

path, mark = sys.argv[1:]
engine = create_engine(f"sqlite:///{path}")
Base.metadata.create_all(engine)
with Session(engine) as session:
    row = AuditEvent(owner_id="restart-check", action="restart_check", result="written", metadata_json=json.dumps({"mark": mark}))
    session.add(row)
    session.commit()
    print(row.id)
PY
}

read_mark() {
  ID="${1:-}"
  [ -n "$ID" ] || { echo "缺少记录 ID" >&2; exit 1; }
  PYTHONPATH="$BACKEND" "$BACKEND/.venv/bin/python" - "$DB_FILE" "$ID" <<'PY'
import json
import sys
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.db import AuditEvent

path, row_id = sys.argv[1:]
engine = create_engine(f"sqlite:///{path}")
with Session(engine) as session:
    row = session.scalar(select(AuditEvent).where(AuditEvent.id == row_id))
    if row is None:
        raise SystemExit(1)
    print(json.loads(row.metadata_json)["mark"])
PY
}

stop() {
  if [ -f "$PID_FILE" ]; then kill "$(cat "$PID_FILE")" 2>/dev/null || true; fi
}

case "${1:-}" in
  start) start;;
  write) write_mark "${2:-}";;
  read) read_mark "${2:-}";;
  stop) stop;;
  *) echo "用法：$0 start|write <标记>|read <记录ID>|stop" >&2; exit 1;;
esac
