import { useState } from 'react';
import type { Source } from '../api';

interface Props {
  sources: Source[];
}

function formatLabel(source: Source): string {
  if (source.source.startsWith('http')) {
    try {
      const url = new URL(source.source);
      return url.hostname.replace('www.', '');
    } catch {
      return source.source;
    }
  }
  const parts = source.source.split('/');
  const file = parts[parts.length - 1];
  if (source.page) return `${file} · s. ${source.page}`;
  return file;
}

export function SourcesPanel({ sources }: Props) {
  const [open, setOpen] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="sources-panel">
      <button className="sources-toggle" onClick={() => setOpen(!open)}>
        <span className="sources-icon">{open ? '▾' : '▸'}</span>
        <span>Źródła ({sources.length})</span>
      </button>

      {open && (
        <div className="sources-list">
          {sources.map((src, i) => (
            <div key={i} className="source-item">
              <div className="source-header">
                {src.source.startsWith('http') ? (
                  <a
                    href={src.source}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="source-link"
                  >
                    {formatLabel(src)}
                  </a>
                ) : (
                  <span className="source-file">{formatLabel(src)}</span>
                )}
                {src.relevance_score != null && (
                  <span className="source-score">
                    {(src.relevance_score * 100).toFixed(0)}%
                  </span>
                )}
              </div>
              <p className="source-snippet">{src.snippet}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
