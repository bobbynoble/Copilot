"""Fix common .env file issues on Windows (BOM / wrong encoding) and verify keys load."""
from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"


def main() -> None:
    if not ENV_PATH.exists():
        print(f"ERROR: {ENV_PATH} does not exist. Copy .env.example to .env first.")
        return

    raw = ENV_PATH.read_bytes()

    # Strip UTF-8 BOM or UTF-16 BOM if present, then decode and re-save as plain UTF-8.
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8")
        print("Found UTF-8 BOM — removing it.")
    elif raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        text = raw.decode("utf-16")
        print("Found UTF-16 encoding — converting to UTF-8.")
    else:
        text = raw.decode("utf-8")
        print("No BOM found — file encoding looks fine.")

    # Normalize line endings and strip trailing whitespace on each line.
    lines = [line.rstrip() for line in text.splitlines()]
    ENV_PATH.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))
    print(f"Rewrote {ENV_PATH} as plain UTF-8 (no BOM).\n")

    # Now verify the keys load correctly.
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)

    for key in ("ANTHROPIC_API_KEY", "CAMB_API_KEY", "ELEVENLABS_API_KEY"):
        value = os.getenv(key)
        if not value:
            print(f"{key}: NOT SET")
        else:
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"{key}: {masked}")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key and not anthropic_key.startswith("sk-ant-"):
        print(
            "\nWARNING: ANTHROPIC_API_KEY does not start with 'sk-ant-' — "
            "this does not look like a valid Anthropic key. "
            "Get one from https://console.anthropic.com (Settings > API Keys)."
        )


if __name__ == "__main__":
    main()
