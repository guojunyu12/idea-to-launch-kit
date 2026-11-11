from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


backend, check_dir, db_file, port = sys.argv[1:]
env = os.environ.copy()
env.update(
    {
        "TASK_DB_URL": f"sqlite:///{db_file}",
        "STORAGE_ROOT": str(Path(check_dir) / "storage"),
        "TEMPLATE_LIBRARY_PATH": str(Path(backend).parent / "data" / "templates.json"),
        "GEN_PROVIDER_MODE": "mock",
        "PYTHONPATH": backend,
    }
)
log = open(Path(check_dir) / "server.log", "ab", buffering=0)
proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port],
    cwd=backend,
    env=env,
    stdin=subprocess.DEVNULL,
    stdout=log,
    stderr=log,
    start_new_session=True,
)
print(proc.pid)
