import { renderMarkdown } from '../markdown';
import { SourcesPanel } from './SourcesPanel';
import type { Source } from '../api';

interface Props {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[] | null;
}

export function ChatMessage({ role, content, sources }: Props) {
  const isUser = role === 'user';

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
      <div className="message-avatar">
        {isUser ? '👤' : '🔧'}
      </div>
      <div className={`message-bubble ${isUser ? 'bubble--user' : 'bubble--assistant'}`}>
        {isUser ? (
          <p className="message-text">{content}</p>
        ) : (
          <div
            className="message-text prose"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
          />
        )}
        {!isUser && sources && sources.length > 0 && (
          <SourcesPanel sources={sources} />
        )}
      </div>
    </div>
  );
}
