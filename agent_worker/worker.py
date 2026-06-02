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
import logging
import os
import sys
from pathlib import Path
from typing import Any

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, RoomInputOptions, cli, inference, llm
from livekit.plugins import silero

logger = logging.getLogger("hermes_voice_bridge")

# Allow `python agent_worker/worker.py ...` from repo root.
sys.path.append(str(Path(__file__).resolve().parent))
from hermes_bridge import HermesBridge, HermesBridgeError  # noqa: E402


class HermesPlaceholderLLM(llm.LLM):
    """Non-answering LLM marker so LiveKit runs Agent.llm_node().

    LiveKit 1.5 requires an LLM object before it will generate a reply, even
    when the Agent overrides llm_node(). This class should never be asked to
    chat; HermesAgent.llm_node is the real generation path.
    """

    @property
    def model(self) -> str:
        return "hermes-director-api"

    @property
    def provider(self) -> str:
        return "hermes"

    def chat(self, **_: Any) -> Any:
        raise RuntimeError("HermesPlaceholderLLM.chat should not be called; HermesAgent.llm_node handles generation")


class HermesAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a thin voice transport for Daniel's Hermes Director profile. "
                "Do not answer from this LiveKit agent's own knowledge. The llm_node sends "
                "each user turn to Hermes and speaks the returned Hermes response."
            ),
            llm=HermesPlaceholderLLM(),
        )
        self.bridge = HermesBridge()
        self.room_name: str | None = None
        self._turn_tasks: set[asyncio.Task[None]] = set()

    async def on_enter(self) -> None:
        logger.info("agent entered room", extra={"room": self.room_name})
        try:
            await self.session.say("Hermes voice bridge is connected.", allow_interruptions=True)
        except Exception:
            # Greeting is non-critical; avoid failing room join because TTS hiccuped.
            logger.exception("failed to say greeting")

    async def on_user_turn_completed(self, turn_ctx: Any, new_message: Any) -> None:
        text = message_text(new_message)
        logger.info(
            "user turn completed",
            extra={
                "room": self.room_name,
                "text_len": len(text),
                "text_preview": text[:160],
                "message_type": type(new_message).__name__,
            },
        )
        if not text:
            return

        # Do not block LiveKit's turn lifecycle while Hermes thinks. A background
        # task keeps the room responsive, then explicitly schedules TTS playback.
        task = asyncio.create_task(self._answer_turn(text))
        self._turn_tasks.add(task)
        task.add_done_callback(self._turn_tasks.discard)

    async def _answer_turn(self, text: str) -> None:
        try:
            logger.info("calling Hermes API from background turn", extra={"room": self.room_name, "text_len": len(text)})
            response = await asyncio.to_thread(self.bridge.ask, text, room_name=self.room_name)
            logger.info("Hermes background turn returned", extra={"room": self.room_name, "response_len": len(response)})
        except HermesBridgeError as exc:
            logger.exception("Hermes API bridge error in background turn")
            response = f"I heard you, but Hermes returned an error: {exc}"
        except Exception as exc:  # pragma: no cover - defensive runtime boundary
            logger.exception("unexpected Hermes bridge failure in background turn")
            response = f"I heard you, but could not contact Hermes: {exc}"

        if not response:
            response = "Hermes returned an empty response."

        try:
            logger.info("scheduling Hermes speech", extra={"room": self.room_name, "response_len": len(response), "response_preview": response[:160]})
            handle = self.session.say(response, allow_interruptions=False, add_to_chat_ctx=True)
            await handle.wait_for_playout()
            logger.info("Hermes speech playout completed", extra={"room": self.room_name})
        except Exception:
            logger.exception("failed to play Hermes speech")

    async def llm_node(self, chat_ctx: Any, tools: list[Any], model_settings: Any) -> str:
        """No-op LLM hook.

        LiveKit requires an LLM object before it processes turns, but Hermes
        generation and speech playback are handled in on_user_turn_completed().
        Returning an empty string prevents a duplicate Hermes call from racing
        the direct speech task.
        """
        user_text = latest_user_text(chat_ctx)
        logger.info(
            "llm_node no-op; direct background turn owns response",
            extra={"room": self.room_name, "text_len": len(user_text), "text_preview": user_text[:160]},
        )
        return ""

def message_text(msg: Any) -> str:
    """Extract text from a LiveKit ChatMessage-ish object."""
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


def latest_user_text(chat_ctx: Any) -> str:
    """Extract the latest user message from LiveKit ChatContext without tight coupling."""
    try:
        messages = chat_ctx.messages()
    except Exception:
        messages = getattr(chat_ctx, "items", []) or []

    for msg in reversed(messages):
        if getattr(msg, "role", None) != "user":
            continue
        text = message_text(msg)
        if text:
            return text
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

    @session.on("user_input_transcribed")
    def _on_user_input_transcribed(ev: Any) -> None:
        transcript = getattr(ev, "transcript", "") or ""
        logger.info(
            "user input transcribed",
            extra={
                "room": agent.room_name,
                "is_final": getattr(ev, "is_final", None),
                "transcript_len": len(transcript),
                "transcript_preview": transcript[:160],
            },
        )

    @session.on("conversation_item_added")
    def _on_conversation_item_added(ev: Any) -> None:
        item = getattr(ev, "item", None)
        logger.info(
            "conversation item added",
            extra={
                "room": agent.room_name,
                "role": getattr(item, "role", None),
                "text_len": len(message_text(item)) if item is not None else 0,
                "text_preview": message_text(item)[:160] if item is not None else "",
            },
        )

    @session.on("error")
    def _on_error(ev: Any) -> None:
        logger.error("agent session error", extra={"room": agent.room_name, "event": repr(ev)})

    await session.start(room=ctx.room, agent=agent, room_input_options=RoomInputOptions(audio_enabled=True, text_enabled=True))


if __name__ == "__main__":
    cli.run_app(server)
