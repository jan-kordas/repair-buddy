import type { HealthStatus } from '../api';

interface StoredConv {
  id: number;
  title: string;
  ts: number;
}

interface Props {
  health: { qdrant: HealthStatus; postgres: HealthStatus };
  conversations: StoredConv[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onNewChat: () => void;
}

function HealthRow({ status, label }: { status: HealthStatus; label: string }) {
  const color =
    status === 'ok' ? '#3fb950' : status === 'unavailable' ? '#f85149' : '#6b7280';
  return (
    <span className="sb-health-item" title={`${label}: ${status}`}>
      <span className="sb-health-dot" style={{ background: color }} />
      {label}
    </span>
  );
}

export function Sidebar({ health, conversations, activeId, onSelect, onNewChat }: Props) {
  return (
    <aside className="sidebar">
      <div className="sb-top">
        <div className="sb-logo">
          <span className="sb-logo-icon">🔧</span>
          <span className="sb-logo-text">Repair Buddy</span>
        </div>
        <button className="sb-new-btn" onClick={onNewChat}>
          <span>+</span> Nowy czat
        </button>
      </div>

      <nav className="sb-nav">
        {conversations.length > 0 && (
          <>
            <p className="sb-section-label">Historia</p>
            <ul className="sb-conv-list">
              {conversations.map((conv) => (
                <li key={conv.id}>
                  <button
                    className={`sb-conv-item ${conv.id === activeId ? 'sb-conv-item--active' : ''}`}
                    onClick={() => onSelect(conv.id)}
                  >
                    <span className="sb-conv-icon">💬</span>
                    <span className="sb-conv-title">{conv.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </nav>

      <div className="sb-bottom">
        <div className="sb-health-row">
          <HealthRow status={health.postgres} label="DB" />
          <HealthRow status={health.qdrant} label="Qdrant" />
        </div>
        <p className="sb-footer-text">VW Golf IV · Skoda Octavia I</p>
      </div>
    </aside>
  );
}
