"""
Anthropic API playground — a scratch space for experimenting with Claude,
separate from the RFP analysis agent in src/.

Usage:
    python playground.py
"""

from __future__ import annotations

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-opus-4-8"


def main() -> None:
    client = anthropic.Anthropic()
    messages: list[dict] = []

    print(f"Claude playground ({MODEL}). Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in ("exit", "quit"):
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        with client.messages.stream(
            model=MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            messages=messages,
        ) as stream:
            print("Claude: ", end="", flush=True)
            for text in stream.text_stream:
                print(text, end="", flush=True)
            print("\n")

            final_message = stream.get_final_message()

        assistant_text = next(
            (b.text for b in final_message.content if b.type == "text"), ""
        )
        messages.append({"role": "assistant", "content": assistant_text})


if __name__ == "__main__":
    main()
