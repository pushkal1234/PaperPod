// Remove markdown "*" from AI text before it's shown, copied or downloaded.
// The server already cleans new podcasts and answers; this cleans ones saved
// before that. Same rules as remove_asterisks() in
// backend/app/services/llm_service.py; keep the two in step.
//   **bold** / *italics* -> markers removed
//   "* " bullet at line start -> "• "
//   "2 * 3" -> "2 × 3"
// keepCode=false (podcast transcript): every other "*" goes too.
// keepCode=true (Q&A answers): "*" that is part of code stays, i.e. inside
// `backticks` or touching an identifier (**kwargs, *ptr, a*b).
// No lookbehind on purpose: older Safari (iOS < 16.4) can't parse it, and a
// regex it can't parse would stop the whole app from loading there.
const CODE = /```[\s\S]*?```|`[^`\n]+`/g;
const BULLET = /^([ \t]*)\*+[ \t]+/gm;
const BOLD = /(^|[^A-Za-z0-9_*])\*\*(\S(?:[^\n]*?\S)?)\*\*(?![A-Za-z0-9_*])/gm;
const ITALIC = /(^|[^A-Za-z0-9_*])\*(\S(?:[^*\n]*?\S)?)\*(?![A-Za-z0-9_*])/gm;
const MULTIPLY = /([\d)])[ \t]*\*[ \t]*(?=[\d(])/g;
const STRAY = /(^|[^A-Za-z0-9_*])\*+(?![A-Za-z0-9_*.])/gm;

export function removeAsterisks(text, { keepCode = false } = {}) {
  if (!text || !text.includes('*')) return text;
  const code = [];
  let out = text;
  if (keepCode) {
    out = out.replace(CODE, (m) => {
      code.push(m);
      return `\u0000${code.length - 1}\u0000`;
    });
  }
  out = out
    .replace(BULLET, '$1• ')
    .replace(BOLD, '$1$2')
    .replace(ITALIC, '$1$2')
    .replace(MULTIPLY, '$1 × ');
  if (keepCode) {
    out = out
      .replace(STRAY, '$1')
      .replace(/\u0000(\d+)\u0000/g, (_, i) => code[Number(i)]);
  } else {
    out = out.replace(/\*/g, '');
  }
  return out.replace(/[ \t]{2,}/g, ' ');
}
