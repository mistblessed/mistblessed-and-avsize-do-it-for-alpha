"""Generate secrets locally, without printing them or overwriting existing files."""
import argparse
import secrets
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(".env"))
    args = parser.parse_args()
    template = Path(__file__).resolve().parents[1] / ".env.example"
    text = template.read_text(encoding="utf-8")
    for name in ["ENCRYPTION_KEY", "REDIS_PASSWORD", "DEMO_API_KEY", "NO_RESTORE_API_KEY", "CONDITIONAL_API_KEY"]:
        text = text.replace(name + "=\n", name + "=" + secrets.token_hex(32) + "\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(text)
    print("Environment file created; secret values were not printed.")


if __name__ == "__main__":
    main()

