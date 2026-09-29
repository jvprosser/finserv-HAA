"""Start the demo as a Cloudera AI application.

Cloudera AI proxies browsers to 127.0.0.1 on the port in CDSW_APP_PORT.
The Application run command is: python3 cml_app.py
"""

from __future__ import annotations

import os

import uvicorn


def listen_address() -> tuple[str, int]:
    port = int(os.environ.get("CDSW_APP_PORT", "8000"))
    return "127.0.0.1", port


if __name__ == "__main__":
    host, port = listen_address()
    uvicorn.run("app.main:app", host=host, port=port)
