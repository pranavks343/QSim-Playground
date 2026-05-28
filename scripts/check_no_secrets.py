"""Pre-commit guard for env files and common secret patterns."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ENV_FILE_PATTERN = re.compile(r"(^|/)\.env($|[.].+)")
ALLOWLISTED_ENV_FILES = {".env.example", ".env.local.example"}
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9_./+=-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]{20,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)
TEXT_SUFFIXES = {
    ".cfg",
    ".env",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def staged_files() -> list[Path]:
    """Return paths staged for commit."""

    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines() if line.strip()]


def candidate_files(paths: list[Path]) -> list[Path]:
    """Filter to existing text-like files that should be scanned."""

    return [
        path
        for path in paths
        if path.exists()
        and path.is_file()
        and (path.suffix in TEXT_SUFFIXES or path.name in ALLOWLISTED_ENV_FILES)
    ]


def is_blocked_env_file(path: Path) -> bool:
    """Return whether a path is an env file that should never be committed."""

    return bool(ENV_FILE_PATTERN.search(path.as_posix())) and path.name not in ALLOWLISTED_ENV_FILES


def contains_secret_pattern(path: Path) -> bool:
    """Scan a file for common high-risk secret patterns."""

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return False

    return any(pattern.search(content) for pattern in SECRET_PATTERNS)


def main() -> int:
    """Run the secret guard."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true", help="Scan files staged in git.")
    args = parser.parse_args()

    paths = staged_files() if args.staged else [path for path in Path.cwd().rglob("*") if path.is_file()]
    blocked_env_files = [path for path in paths if is_blocked_env_file(path)]
    blocked_secret_files = [path for path in candidate_files(paths) if contains_secret_pattern(path)]

    if blocked_env_files or blocked_secret_files:
        for path in blocked_env_files:
            print(f"Refusing to commit environment file: {path}", file=sys.stderr)
        for path in blocked_secret_files:
            print(f"Potential secret pattern found in: {path}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
