import { NextResponse } from 'next/server';
import { type MirrorPayload, mirrorEnabled, sendTelegramMirror } from '@/lib/telegram-mirror';

export const runtime = 'nodejs';
export const revalidate = 0;

export async function GET() {
  return NextResponse.json({ enabled: mirrorEnabled() });
}

export async function POST(req: Request) {
  if (!mirrorEnabled()) {
    return NextResponse.json(
      { ok: false, error: 'Telegram mirroring is not configured' },
      { status: 503 }
    );
  }

  const secret = process.env.MIRROR_SHARED_SECRET;
  if (secret) {
    const provided = req.headers.get('x-mirror-secret');
    if (provided !== secret) {
      return NextResponse.json({ ok: false, error: 'Unauthorized' }, { status: 401 });
    }
  }

  let payload: MirrorPayload;
  try {
    payload = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: 'Invalid JSON' }, { status: 400 });
  }

  if (
    !payload ||
    typeof payload.text !== 'string' ||
    !['user', 'assistant', 'system'].includes(payload.role)
  ) {
    return NextResponse.json({ ok: false, error: 'Invalid mirror payload' }, { status: 400 });
  }

  try {
    await sendTelegramMirror(payload);
    return NextResponse.json({ ok: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unknown mirror error';
    console.error(message);
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
