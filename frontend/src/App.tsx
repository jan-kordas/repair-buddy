import { useState, useEffect, useRef, useCallback } from 'react';
import { Header } from './components/Header';
import { ChatMessage } from './components/ChatMessage';
import { sendMessage, loadMessages, checkHealth } from './api';
import type { Source, HealthStatus } from './api';

const STORAGE_KEY = 'repair_buddy_conv_id';

interface LocalMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[] | null;
}

export default function App() {
  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored ? parseInt(stored, 10) : null;
  });
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ qdrant: HealthStatus; postgres: HealthStatus }>({
    qdrant: 'loading',
    postgres: 'loading',
  });

  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load health status
  useEffect(() => {
    const poll = async () => {
      const [qdrant, postgres] = await Promise.all([
        checkHealth('qdrant'),
        checkHealth('postgres'),
      ]);
      setHealth({ qdrant, postgres });
    };
    poll();
    const id = setInterval(poll, 15000);
    return () => clearInterval(id);
  }, []);

  // Load history when conversation id is known
  useEffect(() => {
    if (!conversationId) return;
    loadMessages(conversationId)
      .then((msgs) => {
        const mapped: LocalMessage[] = msgs
          .filter((m) => m.role !== 'system')
          .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content, sources: m.sources }));
        setMessages(mapped);
      })
      .catch(() => {
        // Conversation not found — start fresh
        localStorage.removeItem(STORAGE_KEY);
        setConversationId(null);
      });
  }, []);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const handleNewChat = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setConversationId(null);
    setMessages([]);
    setError(null);
    textareaRef.current?.focus();
  }, []);

  const handleSend = useCallback(async () => {
    const question = input.trim();
    if (!question || loading) return;

    setInput('');
    setError(null);
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setLoading(true);

    try {
      const data = await sendMessage(question, conversationId ?? undefined);

      if (!conversationId) {
        setConversationId(data.conversation_id);
        localStorage.setItem(STORAGE_KEY, String(data.conversation_id));
      }

      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: data.answer, sources: data.sources },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Nieznany błąd');
      setMessages((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
      textareaRef.current?.focus();
    }
  }, [input, loading, conversationId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = 'auto';
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
  };

  return (
    <div className="app">
      <Header health={health} conversationId={conversationId} onNewChat={handleNewChat} />

      <main className="chat-main">
        {messages.length === 0 && !loading && (
          <div className="empty-state">
            <div className="empty-icon">🔧</div>
            <h2>Asystent mechanika</h2>
            <p>Specjalizuję się w VW Golf IV i Skoda Octavia I.</p>
            <p>Opisz problem lub zadaj pytanie techniczne.</p>
            <div className="suggestions">
              {[
                'Jak wymienić pasek rozrządu w Golf 4 1.9 TDI?',
                'Skoda Octavia nie odpala na mrozie',
                'Golf 4 — szarpanie przy zmianie biegów',
              ].map((s) => (
                <button
                  key={s}
                  className="suggestion-chip"
                  onClick={() => {
                    setInput(s);
                    textareaRef.current?.focus();
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <ChatMessage
            key={i}
            role={msg.role}
            content={msg.content}
            sources={msg.sources}
          />
        ))}

        {loading && (
          <div className="message-row message-row--assistant">
            <div className="message-avatar">🔧</div>
            <div className="message-bubble bubble--assistant">
              <div className="typing-indicator">
                <span /><span /><span />
              </div>
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
      </main>

      <footer className="chat-footer">
        <div className="input-row">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Opisz problem lub zadaj pytanie… (Enter = wyślij, Shift+Enter = nowa linia)"
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            rows={1}
            disabled={loading}
          />
          <button
            className="send-btn"
            onClick={handleSend}
            disabled={!input.trim() || loading}
            aria-label="Wyślij"
          >
            ↑
          </button>
        </div>
        <p className="footer-hint">
          Baza wiedzy: Skoda Octavia I · VW Golf IV
        </p>
      </footer>
    </div>
  );
}
