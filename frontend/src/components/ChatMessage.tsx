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
    <div className={`msg-row ${isUser ? 'msg-row--user' : 'msg-row--assistant'}`}>
      <div className="msg-avatar">{isUser ? '👤' : '🔧'}</div>
      <div className={`msg-bubble ${isUser ? 'msg-bubble--user' : 'msg-bubble--assistant'}`}>
        {isUser ? (
          <p>{content}</p>
        ) : (
          <div className="prose" dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }} />
        )}
        {!isUser && sources && sources.length > 0 && <SourcesPanel sources={sources} />}
      </div>
    </div>
  );
}
