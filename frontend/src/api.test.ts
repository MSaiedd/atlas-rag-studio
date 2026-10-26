import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, streamChat } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('streaming transport', () => {
  it('preserves Arabic and terminal events across arbitrary byte boundaries', async () => {
    const bytes = new TextEncoder().encode(
      'event: delta\r\ndata: {"text":"مرحباً"}\r\n\r\nevent: complete\r\ndata: {"id":"saved"}\r\n\r\n',
    );
    const stream = new ReadableStream({
      start(controller) {
        for (let i = 0; i < bytes.length; i++) controller.enqueue(bytes.slice(i, i + 1));
        controller.close();
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));
    const events: [string, unknown][] = [];
    await streamChat('/chat', {}, new AbortController().signal, (event, data) =>
      events.push([event, data]),
    );
    expect(events).toEqual([
      ['delta', { text: 'مرحباً' }],
      ['complete', { id: 'saved' }],
    ]);
  });

  it('reports an interrupted answer instead of treating a partial draft as complete', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response('event: delta\ndata: {"text":"partial"}\n\n', { status: 200 }),
        ),
    );
    await expect(streamChat('/chat', {}, new AbortController().signal, () => {})).rejects.toThrow(
      'before the answer completed',
    );
  });

  it('surfaces the server error before opening a stream', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'Models are warming up' }), { status: 503 }),
        ),
    );
    await expect(streamChat('/chat', {}, new AbortController().signal, () => {})).rejects.toThrow(
      'Models are warming up',
    );
  });

  it('keeps API permission errors visible', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ detail: 'Editor role required' }), { status: 403 }),
        ),
    );
    await expect(api('/collections', 'POST', { name: 'Policies' })).rejects.toThrow(
      'Editor role required',
    );
  });
});
