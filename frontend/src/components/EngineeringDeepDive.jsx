import { Cpu, Linkedin, BookOpen, Rocket, ArrowUpRight } from 'lucide-react';

// Each link mirrors the VideoShowcase card anatomy: a branded visual header,
// then title + description, then a CTA pinned to the bottom. `gradient` and
// `accent` give each platform its own on-brand identity.
const LINKS = [
  {
    id: 'linkedin',
    icon: Linkedin,
    kind: 'Article',
    wordmark: 'LinkedIn',
    label: 'Architecture deep dive',
    desc: 'The full story on LLM routing, idempotent retries, and the production trade-offs behind the pipeline.',
    cta: 'Read the deep dive',
    url: 'https://www.linkedin.com/pulse/building-production-grade-document-to-podcast-pipeline-pushkal-shukla-ebgjf',
    gradient: 'from-[#0a66c2] to-[#004182]',
    accent: 'text-[#0a66c2]',
  },
  {
    id: 'medium',
    icon: BookOpen,
    kind: 'Blog',
    wordmark: 'Medium',
    label: 'Engineering blog',
    desc: 'Density heuristics, adaptive TTS concurrency, and the retrieval-augmented Q&A fallback, explained.',
    cta: 'Read the blog',
    url: 'https://medium.com/@pushkalshuk/building-a-production-grade-document-to-podcast-pipeline-lessons-from-llm-routing-concurrency-88a7b064c279',
    gradient: 'from-stone-800 to-stone-950',
    accent: 'text-stone-800',
  },
  {
    id: 'producthunt',
    icon: Rocket,
    kind: 'Launch',
    wordmark: 'Product Hunt',
    label: 'Follow the launch',
    desc: 'Track new features and the public changelog — and support PaperPod with an upvote.',
    cta: 'View on Product Hunt',
    url: 'https://www.producthunt.com/products/paperpod-2',
    gradient: 'from-[#ff6154] to-[#da552f]',
    accent: 'text-[#da552f]',
  },
];

export default function EngineeringDeepDive() {
  return (
    <section className="mx-auto max-w-3xl pt-8 text-center">
      <div className="flex flex-col rounded-3xl border border-paper-300 bg-white p-5 shadow-soft md:p-6 lg:min-h-[30rem]">
        <span className="mx-auto inline-flex items-center gap-1.5 rounded-full border border-paper-300 bg-white/70 px-3 py-1 text-[11px] font-semibold text-stone-500">
          <Cpu className="h-3 w-3 text-brand-500" />
          For engineers
        </span>
        <h2 className="mt-3 font-display text-xl font-semibold text-stone-900">
          How it’s built
        </h2>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-stone-500">
          Idempotent processing, model-aware routing, adaptive concurrency, and retrieval-augmented Q&A.
        </p>

        <div className="mt-6 grid flex-1 items-stretch gap-4 text-left sm:grid-cols-3">
          {LINKS.map(({ id, icon: Icon, kind, wordmark, label, desc, cta, url, gradient, accent }) => (
            <a
              key={id}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex h-full flex-col overflow-hidden rounded-2xl border border-paper-300 bg-white p-2 shadow-soft transition duration-200 hover:-translate-y-0.5 hover:shadow-glow"
            >
              {/* Branded header — echoes the video thumbnails above */}
              <div className={`relative flex aspect-[16/10] w-full items-center justify-center overflow-hidden rounded-xl bg-gradient-to-br ${gradient}`}>
                <span className="absolute left-2.5 top-2.5 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-stone-700 backdrop-blur">
                  {kind}
                </span>
                <div className="flex flex-col items-center gap-1.5 text-white">
                  <Icon className="h-8 w-8 transition-transform duration-300 group-hover:scale-110" />
                  <span className="text-xs font-semibold tracking-wide">{wordmark}</span>
                </div>
              </div>

              {/* Text + CTA */}
              <div className="flex flex-1 flex-col px-1.5 pb-1 pt-3">
                <h3 className="font-display text-sm font-semibold text-stone-900">{label}</h3>
                <p className="mt-1 flex-1 text-xs leading-relaxed text-stone-500">{desc}</p>
                <span className={`mt-3 inline-flex items-center gap-1 text-xs font-semibold ${accent}`}>
                  {cta}
                  <ArrowUpRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
                </span>
              </div>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
