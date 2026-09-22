"""Record meaningful RED and require unchanged test sources before GREEN."""
import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["red", "green"])
    parser.add_argument("--name", required=True)
    parser.add_argument("--tests", nargs="+", required=True)
    args = parser.parse_args()
    if not args.name.replace("-", "").replace("_", "").isalnum():
        parser.error("Use an alphanumeric task name")
    root = Path(__file__).resolve().parents[1]
    evidence = root / ".tdd" / args.name
    evidence.mkdir(parents=True, exist_ok=True)
    files = {item.split("::")[0] for item in args.tests}
    hashes = {}
    for name in files:
        path = (root / name).resolve()
        if not path.is_relative_to(root / "tests") or not path.is_file():
            parser.error("Tests must be existing files inside this project's tests directory")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    red_file = evidence / "red.json"
    if args.phase == "green":
        if not red_file.exists():
            raise SystemExit("Record an accepted RED phase for this task first")
        previous = json.loads(red_file.read_text())
        if previous["test_hashes"] != hashes or previous["tests"] != args.tests:
            raise SystemExit("Test selection or source changed since RED; obtain peer review and record RED again")
    junit = evidence / (args.phase + ".xml")
    command = [sys.executable, "-m", "pytest", *args.tests, "-q", "--junitxml", str(junit)]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace")
    (evidence / (args.phase + ".txt")).write_text(result.stdout + result.stderr, encoding="utf-8")
    if not junit.exists():
        raise SystemExit("No structured test results; fix the environment")
    tree = ET.parse(junit)
    cases = tree.findall(".//testcase")
    failures = len(tree.findall(".//failure"))
    errors = len(tree.findall(".//error"))
    skipped = len(tree.findall(".//skipped"))
    meaningful = bool(cases) and errors == 0 and skipped == 0
    accepted = meaningful and ((args.phase == "red" and result.returncode == 1 and failures > 0)
                              or (args.phase == "green" and result.returncode == 0 and failures == 0))
    print(f"phase={args.phase} tests={len(cases)} failures={failures} errors={errors} skips={skipped} accepted={accepted}")
    if not accepted:
        raise SystemExit(1)
    (evidence / (args.phase + ".json")).write_text(json.dumps({"tests": args.tests, "test_hashes": hashes,
        "phase": args.phase, "passed_gate": accepted, "command": command}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
