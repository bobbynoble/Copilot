"""Interactive .env setup — asks for each API key and writes a clean .env file."""
from __future__ import annotations

from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"

PROMPTS = [
    ("ANTHROPIC_API_KEY", "Anthropic API key (starts with sk-ant-)", "https://console.anthropic.com"),
    ("CAMB_API_KEY", "camb.ai API key", "https://studio.camb.ai"),
    ("ELEVENLABS_API_KEY", "ElevenLabs API key", "https://elevenlabs.io (Profile > API Keys)"),
]


def main() -> None:
    print("This will create/overwrite your .env file with the keys you enter.")
    print("Paste each key when prompted, then press Enter. Leave blank to skip.\n")

    values = {}
    for key, label, url in PROMPTS:
        print(f"{label} — get yours at {url}")
        value = input(f"{key}: ").strip()
        values[key] = value
        print()

    lines = [
        "# Anthropic API Key",
        f"ANTHROPIC_API_KEY={values['ANTHROPIC_API_KEY']}",
        "",
        "# camb.ai API Key",
        f"CAMB_API_KEY={values['CAMB_API_KEY']}",
        "",
        "# ElevenLabs API Key",
        f"ELEVENLABS_API_KEY={values['ELEVENLABS_API_KEY']}",
        "",
        "# Optional: API key to protect the RFP agent endpoints",
        "RFP_API_KEY=",
        "",
        "# Optional: allowed CORS origins (comma-separated)",
        "CORS_ORIGINS=*",
        "",
    ]

    ENV_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {ENV_PATH}\n")

    # Verify
    import os
    from dotenv import load_dotenv
    load_dotenv(ENV_PATH, override=True)

    for key, _, _ in PROMPTS:
        value = os.getenv(key)
        if not value:
            print(f"{key}: NOT SET (you left it blank)")
        else:
            masked = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            print(f"{key}: {masked} (OK)")

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if anthropic_key and not anthropic_key.startswith("sk-ant-"):
        print(
            "\nWARNING: ANTHROPIC_API_KEY does not start with 'sk-ant-' — "
            "double check you copied the right key from https://console.anthropic.com"
        )


if __name__ == "__main__":
    main()
