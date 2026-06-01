'use client';

import { useEffect, useRef } from 'react';
import type { ReceivedMessage } from '@livekit/components-react';

interface UseTelegramMirrorOptions {
  messages: ReceivedMessage[];
  roomName?: string;
}

export function useTelegramMirror({ messages, roomName }: UseTelegramMirrorOptions) {
  const mirroredIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const receivedMessage of messages) {
      const { id, from, message, timestamp } = receivedMessage;
      const text = typeof message === 'string' ? message.trim() : '';
      if (!id || !text || mirroredIds.current.has(id)) continue;

      mirroredIds.current.add(id);
      const role = from?.isLocal ? 'user' : 'assistant';

      fetch('/api/mirror', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, roomName, role, text, timestamp }),
      }).catch((error) => {
        console.warn('Telegram transcript mirror failed', error);
      });
    }
  }, [messages, roomName]);
}
