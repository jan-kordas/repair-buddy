const BASE = '/api';

export interface Source {
  source: string;
  page: number | null;
  snippet: string;
  relevance_score: number | null;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
  conversation_id: number;
}

export interface Message {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  sources: Source[] | null;
  created_at: string;
}

export type HealthStatus = 'ok' | 'unavailable' | 'loading';

export async function sendMessage(
  question: string,
  conversation_id?: number,
): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, conversation_id }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return res.json();
}

export async function loadMessages(conversation_id: number): Promise<Message[]> {
  const res = await fetch(`${BASE}/conversations/${conversation_id}/messages`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function checkHealth(
  service: 'qdrant' | 'postgres' | 'ollama',
): Promise<HealthStatus> {
  try {
    const res = await fetch(`${BASE}/health/${service}`, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return 'unavailable';
    const data = await res.json();
    return data.status === 'ok' ? 'ok' : 'unavailable';
  } catch {
    return 'unavailable';
  }
}
