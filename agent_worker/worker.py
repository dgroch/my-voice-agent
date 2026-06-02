"""LiveKit agent worker that uses Hermes as the brain.

Run this on the Hermes host (not Render) so it can call the local Hermes API at
http://127.0.0.1:8642 while still joining LiveKit Cloud rooms.

Required env:
  LIVEKIT_URL
  LIVEKIT_API_KEY
  LIVEKIT_API_SECRET
  LIVEKIT_AGENT              # must match the frontend env var
  HERMES_SESSION_ID          # active Telegram Hermes session id
  API_SERVER_KEY or HERMES_API_KEY

Optional env:
  HERMES_API_URL             # default http://127.0.0.1:8642
  HERMES_SESSION_KEY         # e.g. telegram:6340716310
  HERMES_STT_MODEL           # default deepgram/nova-3 via LiveKit inference
  HERMES_TTS_MODEL           # default cartesia/sonic-3 via LiveKit inference
  HERMES_TTS_VOICE           # default Cartesia voice id
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, cli, inference
from livekit.plugins import silero

# Allow `python agent_worker/worker.py ...` from repo root.
sys.path.append(str(Path(__file__).resolve().parent))
from hermes_bridge import HermesBridge, HermesBridgeError  # noqa: E402


class HermesAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a thin voice transport for Daniel's Hermes Director profile. "
                "Do not answer from this LiveKit agent's own knowledge. The llm_node sends "
                "each user turn to Hermes and speaks the returned Hermes response."
            )
        )
        self.bridge = HermesBridge()
        self.room_name: str | None = None

    async def on_enter(self) -> None:
        try:
            await self.session.say("Hermes voice bridge is connected.", allow_interruptions=True)
        except Exception:
            # Greeting is non-critical; avoid failing room join because TTS hiccuped.
            pass

    def llm_node(self, chat_ctx: Any, tools: list[Any], model_settings: Any):
        """Replace the default LLM with a Hermes API call.

        LiveKit calls this after a finalized user turn. It must return an async
        iterable of strings/chunks. We extract the latest user text from the
        LiveKit chat context, send it to Hermes, then yield Hermes' response for
        TTS and transcript forwarding.
        """

        async def stream():
            user_text = latest_user_text(chat_ctx)
            if not user_text:
                yield "I didn't catch that. Could you repeat it?"
                return

            try:
                response = await asyncio.to_thread(self.bridge.ask, user_text, room_name=self.room_name)
            except HermesBridgeError as exc:
                yield f"I reached the voice room, but Hermes returned an error: {exc}"
                return
            except Exception as exc:  # pragma: no cover - defensive runtime boundary
                yield f"I reached the voice room, but could not contact Hermes: {exc}"
                return

            yield response or "Hermes returned an empty response."

        return stream()


def latest_user_text(chat_ctx: Any) -> str:
    """Extract the latest user message from LiveKit ChatContext without tight coupling."""
    try:
        messages = chat_ctx.messages()
    except Exception:
        messages = getattr(chat_ctx, "items", []) or []

    for msg in reversed(messages):
        if getattr(msg, "role", None) != "user":
            continue
        text = getattr(msg, "text_content", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = [part for part in content if isinstance(part, str) and part.strip()]
            if parts:
                return "\n".join(parts).strip()
    return ""


server = AgentServer()


@server.rtc_session(agent_name=os.environ.get("LIVEKIT_AGENT", "my-hermes-agent"))
async def hermes_voice_session(ctx: JobContext):
    agent = HermesAgent()
    agent.room_name = getattr(ctx.room, "name", None)

    session = AgentSession(
        stt=inference.STT(model=os.environ.get("HERMES_STT_MODEL", "deepgram/nova-3"), language="multi"),
        tts=inference.TTS(
            model=os.environ.get("HERMES_TTS_MODEL", "cartesia/sonic-3"),
            voice=os.environ.get("HERMES_TTS_VOICE", "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"),
        ),
        vad=silero.VAD.load(),
    )
    await session.start(room=ctx.room, agent=agent)


if __name__ == "__main__":
    cli.run_app(server)
