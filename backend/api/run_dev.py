"""Development server entry point."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog
import uvicorn


def main() -> None:
    """Run the local FastAPI development server."""

    backend_dir = Path(__file__).resolve().parents[1]
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    existing_pythonpath = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = (
        str(backend_dir)
        if not existing_pythonpath
        else f"{backend_dir}{os.pathsep}{existing_pythonpath}"
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
    uvicorn.run(
        "api.main:create_app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        factory=True,
        log_config=None,
    )


if __name__ == "__main__":
    main()
