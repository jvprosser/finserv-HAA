"""Start the demo as a Cloudera AI application.

Cloudera AI proxies browsers to 127.0.0.1 on the port in CDSW_APP_PORT.
The Application run command is: python3 cml_app.py
"""

from __future__ import annotations

import asyncio
import os
import threading

import uvicorn


def listen_address() -> tuple[str, int]:
    port = int(os.environ.get("CDSW_APP_PORT", "8000"))
    return "127.0.0.1", port


def serve() -> None:
    host, port = listen_address()
    kwargs = {"app": "app.main:app", "host": host, "port": port}
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        uvicorn.run(**kwargs)
        return
    # Cloudera AI runs this file inside Jupyter, which already has an event loop.
    # uvicorn.run() calls asyncio.run() and fails there, so run it on a thread.
    thread = threading.Thread(target=uvicorn.run, kwargs=kwargs, daemon=False)
    thread.start()
    thread.join()


if __name__ == "__main__":
    serve()
