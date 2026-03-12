import os
import uvicorn

port_env = os.environ.get("PORT", "NOT_SET")
print(f"[STARTUP] PORT env var = {port_env!r}", flush=True)
port = int(port_env) if port_env != "NOT_SET" else 8080
print(f"[STARTUP] Binding to port {port}", flush=True)
uvicorn.run("main:app", host="0.0.0.0", port=port)
