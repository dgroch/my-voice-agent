# Hermes-backed LiveKit worker

This worker makes the LiveKit app feel like Daniel's Hermes bot instead of a generic voice assistant.

It should run on the Hermes host so it can call the local Hermes API server at `http://127.0.0.1:8642` while joining LiveKit Cloud rooms as the agent participant.

## Required environment

```bash
# LiveKit room/agent dispatch
export LIVEKIT_URL='wss://...livekit.cloud'
export LIVEKIT_API_KEY='...'
export LIVEKIT_API_SECRET='...'
export LIVEKIT_AGENT='my-hermes-agent'   # must match the frontend Render env var

# Hermes bridge
export HERMES_API_URL='http://127.0.0.1:8642'
export HERMES_API_KEY='***'          # use the Hermes API_SERVER_KEY value, or set API_SERVER_KEY directly
export HERMES_SESSION_ID='20260601_175300_d7d884'
export HERMES_SESSION_KEY='telegram:6340716310'
```

`HERMES_SESSION_ID` is the active Telegram session this conversation is currently using. If the Telegram thread resets/compresses into a new session, update this env var.

## Install and run locally

From repo root:

```bash
cd agent_worker
uv sync
uv run --module livekit.agents download-files
uv run worker.py start
```

For development logs:

```bash
uv run worker.py dev
```

## How it works

- LiveKit handles audio transport, STT, VAD, and TTS.
- `HermesAgent.llm_node()` bypasses a generic LLM.
- The latest finalized user transcript is posted to:

```text
POST /api/sessions/{HERMES_SESSION_ID}/chat
```

- Hermes Director does the reasoning/tool work and returns text.
- The worker yields that text back into the LiveKit TTS path.

## Why this is Level 3-ish

The bridge targets the existing Telegram Hermes session id and session key, so voice turns are persisted in the same session lineage rather than a separate generic API conversation.

## Caveats

- This requires the Hermes API server to remain running locally.
- A Render-hosted worker cannot call `127.0.0.1:8642`; if running on Render, expose Hermes API through a secure tunnel or VPN and set `HERMES_API_URL` accordingly.
- Tool-heavy Hermes responses will take longer than a pure realtime voice model. The value is tool/context fidelity, not minimum latency.
- The Hermes API server's model/tool configuration must be healthy. If the worker speaks an error like `API call failed after 3 retries: Connection error`, the LiveKit bridge reached Hermes successfully but Hermes' own model/provider path failed for that request.
