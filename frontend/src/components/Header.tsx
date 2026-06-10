import type { HealthStatus } from '../api';

interface Props {
  health: { qdrant: HealthStatus; postgres: HealthStatus };
  conversationId: number | null;
  onNewChat: () => void;
}

function Dot({ status, label }: { status: HealthStatus; label: string }) {
  const color =
    status === 'ok' ? '#22c55e' : status === 'unavailable' ? '#ef4444' : '#6b7280';
  return (
    <span className="health-dot-wrap" title={`${label}: ${status}`}>
      <span className="health-dot" style={{ background: color }} />
      <span className="health-label">{label}</span>
    </span>
  );
}

export function Header({ health, conversationId, onNewChat }: Props) {
  return (
    <header className="header">
      <div className="header-left">
        <span className="logo">🔧</span>
        <span className="logo-text">Repair Buddy</span>
        {conversationId != null && (
          <span className="conv-badge">#{conversationId}</span>
        )}
      </div>
      <div className="header-right">
        <Dot status={health.postgres} label="DB" />
        <Dot status={health.qdrant} label="Qdrant" />
        <button className="new-chat-btn" onClick={onNewChat}>
          + Nowy czat
        </button>
      </div>
    </header>
  );
}
