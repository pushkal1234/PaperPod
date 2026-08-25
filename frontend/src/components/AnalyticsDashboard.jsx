import { useEffect, useState } from 'react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';
import { Headphones, Clock, FileAudio, Type, Loader2, BarChart3 } from 'lucide-react';
import { getStats } from '../api';

// Brand-aligned palette for the source donut segments.
const SOURCE_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ec4899', '#3b82f6', '#8b5cf6', '#94a3b8'];
const STATUS_COLORS = { ready: '#10b981', failed: '#f43f5e', processing: '#f59e0b' };

const SOURCE_LABELS = {
  pdf: 'PDF',
  docx: 'Word',
  pptx: 'PowerPoint',
  txt: 'Text file',
  image: 'Image',
  pasted: 'Pasted text',
  other: 'Other',
};

function formatDuration(seconds) {
  const s = Math.max(0, Math.round(seconds || 0));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s % 60}s`;
  return `${s}s`;
}

function formatMonth(key) {
  // key is "YYYY-MM"
  const [y, m] = key.split('-');
  const d = new Date(Number(y), Number(m) - 1, 1);
  return d.toLocaleString('en-US', { month: 'short', year: '2-digit' });
}

function KpiCard({ icon: Icon, label, value, hint }) {
  return (
    <div className="bg-white border border-paper-300 rounded-2xl p-4 shadow-soft">
      <div className="flex items-center gap-2 text-stone-400">
        <Icon className="w-4 h-4" />
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-bold text-stone-900">{value}</p>
      {hint && <p className="text-xs text-stone-400 mt-0.5">{hint}</p>}
    </div>
  );
}

export default function AnalyticsDashboard() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getStats()
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-10 text-stone-400">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        Loading your stats…
      </div>
    );
  }

  // Silently hide on error or when there's nothing meaningful to show yet.
  if (error || !stats || (stats.totals?.podcasts ?? 0) === 0) return null;

  const { totals, by_source = [], status_breakdown = [], over_time = [] } = stats;

  const sourceData = by_source.map((d) => ({
    name: SOURCE_LABELS[d.source] || d.source,
    value: d.count,
  }));
  const statusData = status_breakdown.filter((d) => d.count > 0);
  const timeData = over_time.map((d) => ({ name: formatMonth(d.month), count: d.count }));

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-stone-700">
        <BarChart3 className="w-5 h-5 text-brand-600" />
        <h3 className="font-display text-lg font-semibold">Your listening stats</h3>
      </div>

      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard icon={Headphones} label="Podcasts" value={totals.podcasts} hint={`${totals.ready} ready`} />
        <KpiCard icon={Clock} label="Listening time" value={formatDuration(totals.listening_seconds)} hint="total generated" />
        <KpiCard icon={FileAudio} label="Avg length" value={formatDuration(totals.avg_seconds)} hint="per podcast" />
        <KpiCard icon={Type} label="Words" value={totals.words.toLocaleString()} hint="turned into audio" />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Podcasts over time */}
        {timeData.length > 0 && (
          <div className="bg-white border border-paper-300 rounded-2xl p-4 shadow-soft">
            <p className="text-sm font-semibold text-stone-700 mb-3">Podcasts over time</p>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={timeData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0ede6" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#a8a29e' }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: '#a8a29e' }} axisLine={false} tickLine={false} />
                <Tooltip cursor={{ fill: '#f5f3ee' }} contentStyle={{ borderRadius: 12, border: '1px solid #e7e2d8', fontSize: 13 }} />
                <Bar dataKey="count" name="Podcasts" fill="#6366f1" radius={[6, 6, 0, 0]} maxBarSize={48} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Source breakdown donut */}
        {sourceData.length > 0 && (
          <div className="bg-white border border-paper-300 rounded-2xl p-4 shadow-soft">
            <p className="text-sm font-semibold text-stone-700 mb-3">By source type</p>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={sourceData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={50} outerRadius={80} paddingAngle={2}>
                  {sourceData.map((entry, i) => (
                    <Cell key={entry.name} fill={SOURCE_COLORS[i % SOURCE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e7e2d8', fontSize: 13 }} />
                <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Success vs failed — only worth showing when there are failures */}
      {totals.failed > 0 && statusData.length > 1 && (
        <div className="bg-white border border-paper-300 rounded-2xl p-4 shadow-soft max-w-md">
          <p className="text-sm font-semibold text-stone-700 mb-3">Generation success</p>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={statusData} dataKey="count" nameKey="status" cx="50%" cy="50%" outerRadius={70}>
                {statusData.map((entry) => (
                  <Cell key={entry.status} fill={STATUS_COLORS[entry.status] || '#94a3b8'} />
                ))}
              </Pie>
              <Tooltip contentStyle={{ borderRadius: 12, border: '1px solid #e7e2d8', fontSize: 13 }} />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12, textTransform: 'capitalize' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
