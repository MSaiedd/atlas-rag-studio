let token = '';
export function connectToken(value: string) {
  token = value;
}
function headers(json = false) {
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(json ? { 'Content-Type': 'application/json' } : {}),
  };
}
export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`/api${path}`, {
    method,
    headers: headers(body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
  }
  return response.json();
}
export async function uploadFile(file: File, collectionId: string) {
  const body = new FormData();
  body.append('file', file);
  body.append('collection_id', collectionId);
  const response = await fetch('/api/documents', { method: 'POST', headers: headers(), body });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Upload failed');
  return result;
}
export async function download(path: string, filename: string) {
  const response = await fetch(`/api${path}`, { headers: headers() });
  if (!response.ok) throw new Error('Download is unavailable for this workspace');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
export async function streamChat(
  path: string,
  body: unknown,
  signal: AbortSignal,
  receive: (event: string, data: unknown) => void,
) {
  const response = await fetch(`/api${path}`, {
    method: 'POST',
    headers: headers(true),
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Answer could not start');
  }
  if (!response.body) throw new Error('Streaming is unavailable');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let completed = false;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n');
    let end;
    while ((end = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const event =
        frame
          .split('\n')
          .find((line) => line.startsWith('event:'))
          ?.slice(6)
          .trim() || 'message';
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n');
      if (data) {
        receive(event, JSON.parse(data));
        if (event === 'complete' || event === 'error') completed = true;
      }
    }
  }
  if (!completed && !signal.aborted)
    throw new Error('The connection ended before the answer completed');
}
