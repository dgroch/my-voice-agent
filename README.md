# Fig & Bloom Voice Agent

LiveKit React voice UI for Daniel/Fig & Bloom, based on LiveKit's official `agent-starter-react`.

## What is included

- Next.js web voice UI.
- `/api/token` endpoint for LiveKit room tokens.
- `/api/mirror` endpoint that mirrors finalized transcript messages to Telegram.
- Render blueprint (`render.yaml`).

## Required runtime environment

Set these on Render before expecting the voice room to connect:

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`

For Telegram transcript mirroring:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TELEGRAM_MESSAGE_THREAD_ID` — optional, only for Telegram topics/threads.

## Important limitation

This repo is the browser frontend and token/mirror server. A real assistant voice still needs a LiveKit Agent worker/cloud agent to join the room. The UI requests the agent named in `app-config.ts` if configured.

## Local development

```bash
corepack enable
pnpm install
pnpm dev
```
