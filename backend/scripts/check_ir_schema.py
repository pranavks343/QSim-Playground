"""Export or verify the static ProblemIR JSON Schema file."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.ir import ProblemIR  # noqa: E402

SCHEMA_PATH = BACKEND_ROOT / "core" / "ir_schema.json"


def render_schema() -> str:
    """Render the current ProblemIR JSON Schema deterministically."""

    return json.dumps(ProblemIR.model_json_schema(), indent=2, sort_keys=True) + "\n"


def write_schema() -> None:
    """Write the current ProblemIR JSON Schema to disk."""

    SCHEMA_PATH.write_text(render_schema(), encoding="utf-8")


def schema_is_current() -> bool:
    """Return whether the committed schema file matches the model."""

    if not SCHEMA_PATH.exists():
        return False
    return SCHEMA_PATH.read_text(encoding="utf-8") == render_schema()


def main() -> int:
    """Run the schema export/check command."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write the schema file.")
    args = parser.parse_args()

    if args.write:
        write_schema()
        return 0

    if not schema_is_current():
        sys.stderr.write(
            "backend/core/ir_schema.json is out of sync. "
            "Run `python scripts/check_ir_schema.py --write` from backend/.\n"
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
