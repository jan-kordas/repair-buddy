import { useState, useEffect, useRef, useCallback } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatMessage } from './components/ChatMessage';
import { sendMessage, loadMessages, checkHealth } from './api';
import type { Source, HealthStatus } from './api';

const CONV_LIST_KEY = 'rb_conversations';
const ACTIVE_KEY = 'rb_active_id';

interface StoredConv { id: number; title: string; ts: number }
interface LocalMsg { role: 'user' | 'assistant'; content: string; sources?: Source[] | null }

function loadStoredConvs(): StoredConv[] {
  try { return JSON.parse(localStorage.getItem(CONV_LIST_KEY) ?? '[]'); }
  catch { return []; }
}

function saveStoredConvs(list: StoredConv[]) {
  localStorage.setItem(CONV_LIST_KEY, JSON.stringify(list));
}

export default function App() {
  const [conversations, setConversations] = useState<StoredConv[]>(loadStoredConvs);
  const [activeId, setActiveId] = useState<number | null>(() => {
    const stored = localStorage.getItem(ACTIVE_KEY);
    return stored ? parseInt(stored, 10) : null;
  });
  const [messages, setMessages] = useState<LocalMsg[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ qdrant: HealthStatus; postgres: HealthStatus }>({
    qdrant: 'loading', postgres: 'loading',
  });

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Health polling
  useEffect(() => {
    const poll = async () => {
      const [qdrant, postgres] = await Promise.all([checkHealth('qdrant'), checkHealth('postgres')]);
      setHealth({ qdrant, postgres });
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, []);

  // Load conversation on mount / switch
  useEffect(() => {
    if (!activeId) { setMessages([]); return; }
    loadMessages(activeId)
      .then((msgs) => {
        setMessages(
          msgs
            .filter((msg) => msg.role !== 'system')
            .map((msg) => ({ role: msg.role as 'user' | 'assistant', content: msg.content, sources: msg.sources })),
        );
      })
      .catch(() => {
        // stale id, clean up
        setActiveId(null);
        localStorage.removeItem(ACTIVE_KEY);
        const updated = conversations.filter((conv) => conv.id !== activeId);
        setConversations(updated);
        saveStoredConvs(updated);
      });
  }, [activeId]);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleNewChat = useCallback(() => {
    setActiveId(null);
    localStorage.removeItem(ACTIVE_KEY);
    setMessages([]);
    setError(null);
    setTimeout(() => textareaRef.current?.focus(), 0);
  }, []);

  const handleSelectConv = useCallback((id: number) => {
    setActiveId(id);
    localStorage.setItem(ACTIVE_KEY, String(id));
    setError(null);
  }, []);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) return;

    setInput('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setLoading(true);

    // Reset textarea height
    if (textareaRef.current) textareaRef.current.style.height = 'auto';

    try {
      const data = await sendMessage(question, activeId ?? undefined);

      if (!activeId) {
        const newConv: StoredConv = { id: data.conversation_id, title: question.slice(0, 48), ts: Date.now() };
        setConversations((prev) => {
          const updated = [newConv, ...prev.filter((conv) => conv.id !== data.conversation_id)].slice(0, 20);
          saveStoredConvs(updated);
          return updated;
        });
        setActiveId(data.conversation_id);
        localStorage.setItem(ACTIVE_KEY, String(data.conversation_id));
      }

      setMessages((prev) => [...prev, { role: 'assistant', content: data.answer, sources: data.sources }]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nieznany błąd');
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [input, loading, activeId]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); handleSend(); }
  };

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    event.target.style.height = 'auto';
    event.target.style.height = Math.min(event.target.scrollHeight, 180) + 'px';
  };

  const suggestions = [
    'Jak wymienić pasek rozrządu w Golf 4 1.9 TDI?',
    'Skoda Octavia I nie odpala na mrozie — co sprawdzić?',
    'Golf 4 — szarpanie przy zmianie biegów',
    'Octavia I — ubytek płynu chłodniczego bez wycieku',
  ];

  return (
    <div className="layout">
      <Sidebar
        health={health}
        conversations={conversations}
        activeId={activeId}
        onSelect={handleSelectConv}
        onNewChat={handleNewChat}
      />

      <div className="chat-area">
        <div className="chat-messages">
          {messages.length === 0 && !loading && (
            <div className="empty-state">
              <div className="empty-icon">🔧</div>
              <h1>Asystent mechanika</h1>
              <p>Specjalizuję się w VW Golf IV i Skoda Octavia I.<br />Opisz usterkę lub zadaj pytanie techniczne.</p>
              <div className="suggestions-grid">
                {suggestions.map((suggestion) => (
                  <button key={suggestion} className="suggestion-chip" onClick={() => { setInput(suggestion); textareaRef.current?.focus(); }}>
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, index) => (
            <ChatMessage key={index} role={msg.role} content={msg.content} sources={msg.sources} />
          ))}

          {loading && (
            <div className="msg-row msg-row--assistant">
              <div className="msg-avatar">🔧</div>
              <div className="msg-bubble msg-bubble--assistant">
                <div className="typing-dots"><span /><span /><span /></div>
              </div>
            </div>
          )}

          {error && (
            <div className="error-bar">
              ⚠ {error}
              <button onClick={() => setError(null)}>✕</button>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <div className="input-wrap">
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder="Opisz problem lub zadaj pytanie… (Enter wysyła, Shift+Enter = nowa linia)"
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={loading}
            />
            <button className="send-btn" onClick={handleSend} disabled={!input.trim() || loading} aria-label="Wyślij">
              ↑
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
