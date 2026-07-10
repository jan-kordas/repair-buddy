// Simple markdown → HTML renderer (no external deps)
export function renderMarkdown(text: string): string {
  const lines = text.split('\n');
  const result: string[] = [];
  let inUl = false;
  let inOl = false;

  const closeList = () => {
    if (inUl) { result.push('</ul>'); inUl = false; }
    if (inOl) { result.push('</ol>'); inOl = false; }
  };

  const inlineFormat = (value: string) =>
    value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>');

  for (const raw of lines) {
    const line = raw.trimEnd();

    const olMatch = line.match(/^(\d+)\.\s+(.*)/);
    const ulMatch = line.match(/^[-*]\s+(.*)/);
    const h3Match = line.match(/^###\s+(.*)/);
    const h2Match = line.match(/^##\s+(.*)/);
    const h1Match = line.match(/^#\s+(.*)/);

    if (h1Match || h2Match || h3Match) {
      closeList();
      const tag = h1Match ? 'h1' : h2Match ? 'h2' : 'h3';
      const content = inlineFormat((h1Match ?? h2Match ?? h3Match)![1]);
      result.push(`<${tag}>${content}</${tag}>`);
    } else if (ulMatch) {
      if (inOl) { result.push('</ol>'); inOl = false; }
      if (!inUl) { result.push('<ul>'); inUl = true; }
      result.push(`<li>${inlineFormat(ulMatch[1])}</li>`);
    } else if (olMatch) {
      if (inUl) { result.push('</ul>'); inUl = false; }
      if (!inOl) { result.push('<ol>'); inOl = true; }
      result.push(`<li>${inlineFormat(olMatch[2])}</li>`);
    } else if (line === '' || line === '---') {
      closeList();
      result.push('<br/>');
    } else {
      closeList();
      result.push(`<p>${inlineFormat(line)}</p>`);
    }
  }

  closeList();
  return result.join('');
}
