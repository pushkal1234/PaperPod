const BARS = [0.45, 1, 0.6, 0.9, 0.5];

export default function Equalizer({ className = 'h-3.5', tone = 'brand' }) {
  const barColor =
    tone === 'light' ? 'bg-white/90' : 'bg-gradient-to-t from-brand-500 to-accent-400';
  return (
    <span className={`inline-flex items-end gap-[2px] ${className}`} aria-hidden="true">
      {BARS.map((h, i) => (
        <span
          key={i}
          className={`w-[2px] rounded-full ${barColor} animate-eq`}
          style={{ height: `${h * 100}%`, transformOrigin: 'bottom', animationDelay: `${i * 0.12}s` }}
        />
      ))}
    </span>
  );
}
