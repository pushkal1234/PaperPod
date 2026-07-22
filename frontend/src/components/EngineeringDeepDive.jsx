import { Cpu, Linkedin, BookOpen, ExternalLink, ArrowUpRight } from 'lucide-react';

const LINKS = [
  {
    id: 'linkedin',
    icon: Linkedin,
    label: 'Architecture deep dive',
    url: 'https://www.linkedin.com/pulse/building-production-grade-document-to-podcast-pipeline-pushkal-shukla-ebgjf',
    desc: 'LLM routing, retries, and production trade-offs.',
  },
  {
    id: 'medium',
    icon: BookOpen,
    label: 'Engineering blog',
    url: 'https://medium.com/@pushkalshuk/building-a-production-grade-document-to-podcast-pipeline-lessons-from-llm-routing-concurrency-88a7b064c279',
    desc: 'Density heuristics, adaptive TTS, and Q&A fallback.',
  },
  {
    id: 'producthunt',
    icon: ExternalLink,
    label: 'Product Hunt',
    url: 'https://www.producthunt.com/products/paperpod-2',
    desc: 'Follow updates and the public changelog.',
  },
];

export default function EngineeringDeepDive() {
  return (
    <section className="mx-auto max-w-3xl px-4 pt-8 text-center">
      <div className="rounded-3xl border border-paper-300 bg-white p-5 shadow-soft md:p-6">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-paper-300 bg-white/70 px-3 py-1 text-[11px] font-semibold text-stone-500">
          <Cpu className="h-3 w-3 text-brand-500" />
          For engineers
        </span>
        <h2 className="mt-3 font-display text-xl font-semibold text-stone-900">
          How it’s built
        </h2>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-stone-500">
          Idempotent processing, model-aware routing, adaptive concurrency, and retrieval-augmented Q&A.
        </p>

        <div className="mt-5 grid gap-3 sm:grid-cols-3 text-left">
          {LINKS.map(({ id, icon: Icon, label, url, desc }) => (
            <a
              key={id}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex flex-col rounded-2xl border border-paper-200 bg-paper-50/50 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:bg-white hover:shadow-glow"
            >
              <div className="flex items-start justify-between">
                <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-500 shadow-sm">
                  <Icon className="h-3 w-3" />
                  {label}
                </span>
                <ArrowUpRight className="h-3.5 w-3.5 text-stone-300 transition-colors group-hover:text-brand-500" />
              </div>
              <p className="mt-2 text-xs leading-relaxed text-stone-500">{desc}</p>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
