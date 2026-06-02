"""Hermes API bridge for LiveKit voice agents.

This module intentionally uses only Python stdlib so it can be tested without
LiveKit installed. The LiveKit worker imports this to turn finalized speech
transcripts into persisted Hermes session turns.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HermesBridgeConfig:
    api_url: str
    api_key: str
    session_id: str
    session_key: str | None = None
    timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> "HermesBridgeConfig":
        api_url = os.environ.get("HERMES_API_URL", "http://127.0.0.1:8642").rstrip("/")
        api_key = os.environ.get("HERMES_API_KEY") or os.environ.get("API_SERVER_KEY")
        session_id = os.environ.get("HERMES_SESSION_ID")
        session_key = os.environ.get("HERMES_SESSION_KEY")
        timeout_seconds = int(os.environ.get("HERMES_API_TIMEOUT_SECONDS", "300"))

        missing = []
        if not api_key:
            missing.append("HERMES_API_KEY or API_SERVER_KEY")
        if not session_id:
            missing.append("HERMES_SESSION_ID")
        if missing:
            raise RuntimeError("Missing Hermes bridge env vars: " + ", ".join(missing))

        assert api_key is not None
        assert session_id is not None
        return cls(
            api_url=api_url,
            api_key=api_key,
            session_id=session_id,
            session_key=session_key,
            timeout_seconds=timeout_seconds,
        )


class HermesBridgeError(RuntimeError):
    pass


class HermesBridge:
    def __init__(self, config: HermesBridgeConfig | None = None) -> None:
        self.config = config or HermesBridgeConfig.from_env()

    def ask(self, user_text: str, *, room_name: str | None = None) -> str:
        """Send one finalized user utterance to Hermes and return assistant text."""
        text = user_text.strip()
        if not text:
            return ""

        instructions = (
            "This message came from Daniel speaking through the LiveKit voice app. "
            "Treat it as part of the same Telegram conversation/session. Reply naturally for voice: "
            "be concise when possible, but use Hermes tools when needed."
        )
        if room_name:
            instructions += f" LiveKit room: {room_name}."

        payload = {
            "message": text,
            "instructions": instructions,
        }
        url = f"{self.config.api_url}/api/sessions/{self.config.session_id}/chat"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.config.session_key:
            headers["X-Hermes-Session-Key"] = self.config.session_key

        request = urllib.request.Request(
            url,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                data: dict[str, Any] = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:1000]
            raise HermesBridgeError(f"Hermes API returned HTTP {exc.code}: {detail}") from exc
        except Exception as exc:  # pragma: no cover - defensive network boundary
            raise HermesBridgeError(f"Hermes API call failed: {exc}") from exc

        message = data.get("message") or {}
        content = message.get("content") or data.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        return content.strip()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Send a text turn through the Hermes voice bridge")
    parser.add_argument("message", help="User message to send to Hermes")
    parser.add_argument("--room", default=None, help="Optional LiveKit room name")
    args = parser.parse_args()

    response = HermesBridge().ask(args.message, room_name=args.room)
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
