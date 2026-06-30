/** Render Q&A answer text: paragraphs + **bold** without showing raw markdown. */

function cleanLatex(text) {
  return text
    .replace(/\\\(([^)]*)\\\)/g, '$1')
    .replace(/\\\[([^\]]*)\\\]/g, '$1');
}

function renderInline(text) {
  const cleaned = cleanLatex(text);
  const parts = cleaned.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-stone-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part.replace(/\*\*/g, '');
  });
}

export default function FormattedAnswer({ text }) {
  if (!text) return null;

  const paragraphs = text.split(/\n\n+/);

  return (
    <div className="space-y-3">
      {paragraphs.map((para, i) => (
        <p key={i} className="whitespace-pre-wrap">
          {renderInline(para.trim())}
        </p>
      ))}
    </div>
  );
}
