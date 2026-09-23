"""Create a source-only ZIP using an explicit allowlist; never include .env or weights."""
import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT_FILES = {"README.md", "AGENTS.md", "pyproject.toml", "uv.lock", "Dockerfile", "compose.yaml", ".env.example", ".gitignore", ".dockerignore"}
ROOT_DIRS = {"src", "tests", "tools", "config", "docs", "reports"}
EXTRA_FILES = {"config/ca/russian-trusted-root.pem"}
EXCLUDED_FILES = {"reports/holdout-quality.json"}
ALLOWED_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".txt"}
EXCLUDED = {"__pycache__", ".pytest_cache", ".hypothesis", ".ruff_cache", ".mypy_cache"}


def package(root: Path, output: Path) -> int:
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        if rel.as_posix() in EXCLUDED_FILES:
            continue
        if any(part in EXCLUDED or part.startswith(".env") for part in rel.parts) and rel.name != ".env.example":
            continue
        if (str(rel) in ROOT_FILES or rel.as_posix() in EXTRA_FILES
                or (rel.parts[0] in ROOT_DIRS and path.suffix in ALLOWED_SUFFIXES)):
            if path.stat().st_size > 2_000_000:
                raise ValueError("Unexpected large source artifact: " + str(rel))
            files.append(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.write(path, path.relative_to(root).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert "README.md" in archive.namelist()
        assert ".env" not in archive.namelist()
    print(f"Packaged {len(files)} files; SHA256 {hashlib.sha256(output.read_bytes()).hexdigest()}")
    return len(files)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    package(Path(__file__).resolve().parents[1], args.output.resolve())
