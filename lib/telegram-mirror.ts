export type MirrorRole = 'user' | 'assistant' | 'system';

export interface MirrorPayload {
  id?: string;
  roomName?: string;
  role: MirrorRole;
  text: string;
  timestamp?: number;
}

const roleLabel: Record<MirrorRole, string> = {
  user: '🎙️ Daniel',
  assistant: '🤖 Hermes',
  system: 'ℹ️ Voice app',
};

function env(name: string): string | undefined {
  const value = process.env[name];
  return value && value.trim().length > 0 ? value.trim() : undefined;
}

export function mirrorEnabled(): boolean {
  return Boolean(env('TELEGRAM_BOT_TOKEN') && env('TELEGRAM_CHAT_ID'));
}

export async function sendTelegramMirror(payload: MirrorPayload): Promise<void> {
  const botToken = env('TELEGRAM_BOT_TOKEN');
  const chatId = env('TELEGRAM_CHAT_ID');

  if (!botToken || !chatId) {
    throw new Error('Telegram mirroring is not configured');
  }

  const trimmed = payload.text.trim();
  if (!trimmed) return;

  const roomSuffix = payload.roomName ? `\n_room: ${payload.roomName}_` : '';
  const text = `${roleLabel[payload.role]}: ${trimmed}${roomSuffix}`;

  const body: Record<string, string> = {
    chat_id: chatId,
    text,
    parse_mode: 'Markdown',
    disable_web_page_preview: 'true',
  };

  const threadId = env('TELEGRAM_MESSAGE_THREAD_ID');
  if (threadId) {
    body.message_thread_id = threadId;
  }

  const response = await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Telegram sendMessage failed: ${response.status} ${errorText}`);
  }
}
