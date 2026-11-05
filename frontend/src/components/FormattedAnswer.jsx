/** Render Q&A answer text: paragraphs + **bold**, with no "*" ever shown. */
import { removeAsterisks } from '../textClean';

function cleanLatex(text) {
  return text
    .replace(/\\\(([^)]*)\\\)/g, '$1')
    .replace(/\\\[([^\]]*)\\\]/g, '$1');
}

function renderInline(text) {
  const cleaned = cleanLatex(text);
  // New answers arrive without markdown asterisks; older saved ones may still
  // have **bold** (rendered bold) and stray "*" (removed). A bold run can't
  // start/end with a space or contain a backtick, so code like `**kwargs` and
  // `**args` is never mistaken for one bold phrase.
  const parts = cleaned.split(/(\*\*[^*`\s](?:[^*`]*[^*`\s])?\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return (
        <strong key={i} className="font-semibold text-stone-900">
          {removeAsterisks(part.slice(2, -2), { keepCode: true })}
        </strong>
      );
    }
    return removeAsterisks(part, { keepCode: true });
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
