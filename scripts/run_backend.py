"""
Launcher script for SentraX FastAPI Backend & Web Dashboard
"""

import sys
import os
import subprocess
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from software.backend.core.config import settings


def free_port_if_needed(port: int = 8000):
    """Ensures port is not held by a previous zombie instance before binding."""
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(
                f"netstat -ano | findstr :{port}",
                shell=True,
                text=True,
                stderr=subprocess.DEVNULL
            )
            current_pid = os.getpid()
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5 and "LISTENING" in line:
                    try:
                        pid = int(parts[-1])
                        if pid != current_pid and pid != 0:
                            subprocess.run(
                                f"taskkill /F /PID {pid}",
                                shell=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                    except ValueError:
                        pass
        except Exception:
            pass


if __name__ == "__main__":
    free_port_if_needed(settings.PORT)
    print("=" * 65)
    print("SENTRAX INTELLIGENT ROAD SAFETY & SMART INFRASTRUCTURE PLATFORM")
    print(f"Starting server at http://{settings.HOST}:{settings.PORT}")
    print("Command Center Dashboard: http://localhost:8000")
    print("Interactive Swagger Docs: http://localhost:8000/docs")
    print("=" * 65)
    try:
        uvicorn.run("software.backend.main:app", host=settings.HOST, port=settings.PORT, reload=False, log_level="info")
    except Exception as e:
        print(f"[FATAL] Server exception: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
