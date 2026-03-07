"use client";

import { useEffect, useState } from "react";

interface PainPoint {
  category: string;
  description: string;
  frequency: string;
  sentiment_score?: number;
  sample_quotes?: string[];
}

interface PositiveHighlight {
  aspect: string;
  frequency: string;
  sample_quotes?: string[];
}

interface ReviewInsights {
  pain_points: PainPoint[];
  positive_highlights: PositiveHighlight[];
  visual_recommendations: string[];
  sentiment_summary: {
    overall_score?: number;
    positive_pct?: number;
    negative_pct?: number;
    top_complaint?: string;
    top_praise?: string;
  };
  total_reviews_analyzed: number;
}

interface StorySlot {
  position: number;
  slot_type: string;
  purpose: string;
  visual_brief: string;
  text_overlay: string;
  background: string;
  key_selling_point: string;
  differentiation_from_competitors: string;
}

interface StoryArc {
  story_arc_name: string;
  narrative_theme: string;
  slots: StorySlot[];
  rationale: string;
  estimated_ctr_impact: string;
}

interface ActionPhase {
  phase: number;
  title: string;
  timeframe: string;
  priority: string;
  actions: { action: string; rationale: string; expected_impact: string }[];
}

interface ABTest {
  test_name: string;
  hypothesis: string;
  control: string;
  variant: string;
  metric: string;
  estimated_impact: string;
  priority: number;
}

interface SeasonalAlert {
  event: string;
  date_range: string;
  urgency: string;
  recommendation: string;
  days_until: number;
}

interface BenchmarkData {
  category: string;
  total_products: number;
  total_images: number;
  image_type_distribution: Record<string, number>;
  angle_distribution: Record<string, number>;
  background_distribution: Record<string, number>;
  has_person_ratio: number;
  has_text_ratio: number;
  top_style_tags: string[];
  quality_avg: number;
  missing_slots_ranking: Record<string, number>;
  aplus_adoption_rate: number;
  aplus_avg_score: number;
  price_tier_distribution: Record<string, number>;
}

interface JobData {
  products: Array<{ title: string; price: string; rating: number; reviews_count: number; reviews?: Array<{ text: string; stars: number }> }>;
  analyses: Array<{ image_type: string; selling_point_angle: string; info_hierarchy: string; text_coverage_pct: number }>;
  report: { keyword: string; total_products: number; total_images: number; image_type_distribution: Record<string, number>; recommendations: string[] };
  action_plan: ActionPhase[];
  ab_tests: ABTest[];
  seasonal_alerts: SeasonalAlert[];
  review_insights: ReviewInsights;
  story_arc: StoryArc;
  benchmark: BenchmarkData | null;
}

type Tab = "overview" | "benchmark" | "reviews" | "story_arc" | "action_plan" | "ab_tests";

const TAB_LABELS: Record<Tab, string> = {
  overview: "Overview",
  benchmark: "Benchmark",
  reviews: "Review Insights",
  story_arc: "7-Image Strategy",
  action_plan: "Action Plan",
  ab_tests: "A/B Tests",
};

const FREQ_COLORS: Record<string, string> = {
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
};

const URGENCY_COLORS: Record<string, string> = {
  critical: "bg-red-50 border-red-300 text-red-800",
  high: "bg-amber-50 border-amber-300 text-amber-800",
  medium: "bg-blue-50 border-blue-300 text-blue-800",
  low: "bg-slate-50 border-slate-200 text-slate-600",
};

export default function DataDashboard({ jobId }: { jobId: string }) {
  const [data, setData] = useState<JobData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("overview");

  useEffect(() => {
    async function fetchData() {
      try {
        const res = await fetch(`/api/proxy/jobs/${jobId}/data`);
        if (!res.ok) throw new Error(`Failed to load data: ${res.status}`);
        const json = await res.json();
        setData(json);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [jobId]);

  if (loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-8 text-center">
        <div className="h-5 w-5 border-2 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
        <p className="text-sm text-slate-500">Loading intelligence data...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
        <p className="text-sm text-red-700">{error ?? "No data available"}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Seasonal alerts banner */}
      {data.seasonal_alerts.length > 0 && (
        <div className="space-y-2">
          {data.seasonal_alerts.map((alert, i) => (
            <div key={i} className={`border rounded-lg px-4 py-2.5 text-sm ${URGENCY_COLORS[alert.urgency] ?? URGENCY_COLORS.low}`}>
              <span className="font-medium">{alert.event}</span>
              <span className="mx-2 opacity-50">|</span>
              <span>{alert.recommendation}</span>
              <span className="ml-2 text-xs opacity-60">({alert.days_until}d away)</span>
            </div>
          ))}
        </div>
      )}

      {/* Tab navigation */}
      <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
        {(Object.keys(TAB_LABELS) as Tab[]).filter((t) =>
          t !== "benchmark" || (data.benchmark && data.benchmark.total_products > 0)
        ).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 px-3 py-2 text-sm font-medium rounded-md transition-colors ${
              tab === t
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {TAB_LABELS[t]}
            {t === "benchmark" && data.benchmark && (
              <span className="ml-1.5 text-xs text-slate-400">
                ({data.benchmark.total_products.toLocaleString()})
              </span>
            )}
            {t === "reviews" && data.review_insights?.total_reviews_analyzed > 0 && (
              <span className="ml-1.5 text-xs text-slate-400">
                ({data.review_insights.total_reviews_analyzed})
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="bg-white border border-slate-200 rounded-xl p-6">
        {tab === "overview" && <OverviewTab data={data} />}
        {tab === "benchmark" && <BenchmarkTab benchmark={data.benchmark} report={data.report} />}
        {tab === "reviews" && <ReviewsTab insights={data.review_insights} />}
        {tab === "story_arc" && <StoryArcTab arc={data.story_arc} />}
        {tab === "action_plan" && <ActionPlanTab phases={data.action_plan} />}
        {tab === "ab_tests" && <ABTestsTab tests={data.ab_tests} />}
      </div>

      {/* Export button */}
      <div className="flex justify-end">
        <a
          href={`/api/proxy/exports/${jobId}`}
          download
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M7 1v8M4 6l3 3 3-3M2 11h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Download All Data (ZIP)
        </a>
      </div>
    </div>
  );
}

/* ── Tab Components ────────────────────────────────────────────── */

function OverviewTab({ data }: { data: JobData }) {
  const r = data.report;
  return (
    <div className="space-y-6">
      {/* Stats grid */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Products", value: r.total_products },
          { label: "Images", value: r.total_images },
          { label: "Reviews", value: data.review_insights?.total_reviews_analyzed ?? 0 },
          { label: "Pain Points", value: data.review_insights?.pain_points?.length ?? 0 },
        ].map((s) => (
          <div key={s.label} className="bg-slate-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-semibold text-slate-900">{s.value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Image type distribution */}
      <div>
        <h3 className="text-sm font-medium text-slate-700 mb-3">Image Type Distribution</h3>
        <div className="space-y-2">
          {Object.entries(r.image_type_distribution).sort(([,a],[,b]) => b - a).map(([type, pct]) => (
            <div key={type} className="flex items-center gap-3">
              <span className="text-xs text-slate-500 w-24 text-right">{type}</span>
              <div className="flex-1 h-5 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${Math.min(pct, 100)}%` }} />
              </div>
              <span className="text-xs text-slate-600 w-12">{pct.toFixed(1)}%</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recommendations */}
      {r.recommendations.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">Key Recommendations</h3>
          <ul className="space-y-1.5">
            {r.recommendations.map((rec, i) => (
              <li key={i} className="text-sm text-slate-600 flex gap-2">
                <span className="text-blue-500 flex-shrink-0">-</span>
                {rec}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Sentiment summary */}
      {data.review_insights?.sentiment_summary?.overall_score != null && (
        <div className="bg-slate-50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-slate-700 mb-2">Customer Sentiment</h3>
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-2xl font-semibold text-green-600">
                {Math.round((data.review_insights.sentiment_summary.overall_score ?? 0) * 100)}%
              </span>
              <span className="text-xs text-slate-500 ml-1">positive</span>
            </div>
            {data.review_insights.sentiment_summary.top_praise && (
              <div className="flex-1 text-slate-500 text-xs">
                Top praise: <span className="text-slate-700">{data.review_insights.sentiment_summary.top_praise.slice(0, 80)}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewsTab({ insights }: { insights: ReviewInsights }) {
  if (!insights || insights.total_reviews_analyzed === 0) {
    return <p className="text-sm text-slate-500">No review data available for this search.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Visual recommendations */}
      {insights.visual_recommendations.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">
            Visual Strategy Recommendations
            <span className="text-xs text-slate-400 font-normal ml-1.5">(from {insights.total_reviews_analyzed} reviews)</span>
          </h3>
          <div className="space-y-2">
            {insights.visual_recommendations.map((rec, i) => (
              <div key={i} className="flex gap-2.5 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2.5 text-sm text-blue-800">
                <span className="text-blue-500 font-medium flex-shrink-0">{i + 1}.</span>
                {rec}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pain points */}
      {insights.pain_points.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">Customer Pain Points</h3>
          <div className="space-y-2">
            {insights.pain_points.map((pp, i) => (
              <div key={i} className="border border-slate-200 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${FREQ_COLORS[pp.frequency] ?? FREQ_COLORS.low}`}>
                    {pp.frequency}
                  </span>
                  <span className="text-xs text-slate-400 uppercase tracking-wide">{pp.category}</span>
                </div>
                <p className="text-sm text-slate-700">{pp.description}</p>
                {pp.sample_quotes && pp.sample_quotes.length > 0 && (
                  <p className="text-xs text-slate-400 mt-1.5 italic">&ldquo;{pp.sample_quotes[0].slice(0, 120)}&rdquo;</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Positive highlights */}
      {insights.positive_highlights.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">What Customers Love</h3>
          <div className="space-y-2">
            {insights.positive_highlights.map((ph, i) => (
              <div key={i} className="flex items-start gap-2 text-sm">
                <span className="text-green-500 mt-0.5 flex-shrink-0">+</span>
                <div>
                  <span className="text-slate-700">{ph.aspect}</span>
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${FREQ_COLORS[ph.frequency] ?? FREQ_COLORS.low}`}>
                    {ph.frequency}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StoryArcTab({ arc }: { arc: StoryArc }) {
  if (!arc || !arc.slots || arc.slots.length === 0) {
    return <p className="text-sm text-slate-500">No story arc data available.</p>;
  }

  const SLOT_COLORS: Record<string, string> = {
    hero: "bg-blue-600",
    infographic: "bg-amber-500",
    lifestyle: "bg-green-500",
    size_chart: "bg-purple-500",
    comparison: "bg-red-500",
    detail: "bg-cyan-500",
    social_proof: "bg-pink-500",
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h3 className="text-base font-semibold text-slate-900">{arc.story_arc_name}</h3>
        <p className="text-sm text-slate-500 mt-1">{arc.narrative_theme}</p>
        {arc.estimated_ctr_impact && (
          <span className="inline-block mt-2 text-xs px-2 py-1 bg-green-100 text-green-700 rounded-full font-medium">
            Estimated CTR impact: {arc.estimated_ctr_impact}
          </span>
        )}
      </div>

      {/* 7 slots */}
      <div className="space-y-3">
        {arc.slots.map((slot) => (
          <div key={slot.position} className="border border-slate-200 rounded-lg p-4">
            <div className="flex items-center gap-3 mb-2">
              <span className="flex items-center justify-center h-7 w-7 rounded-full bg-slate-900 text-white text-xs font-bold">
                {slot.position}
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full text-white font-medium ${SLOT_COLORS[slot.slot_type] ?? "bg-slate-500"}`}>
                {slot.slot_type}
              </span>
              <span className="text-xs text-slate-400">{slot.background} background</span>
            </div>
            <p className="text-sm text-slate-700 mb-1">{slot.purpose}</p>
            {slot.visual_brief && (
              <p className="text-xs text-slate-500">{slot.visual_brief}</p>
            )}
            {slot.key_selling_point && (
              <p className="text-xs text-blue-600 mt-1.5">Selling point: {slot.key_selling_point}</p>
            )}
            {slot.differentiation_from_competitors && (
              <p className="text-xs text-green-600 mt-0.5">vs competitors: {slot.differentiation_from_competitors}</p>
            )}
          </div>
        ))}
      </div>

      {/* Rationale */}
      {arc.rationale && (
        <div className="bg-slate-50 rounded-lg p-4">
          <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">Strategic Rationale</h4>
          <p className="text-sm text-slate-700">{arc.rationale}</p>
        </div>
      )}
    </div>
  );
}

function ActionPlanTab({ phases }: { phases: ActionPhase[] }) {
  if (!phases || phases.length === 0) {
    return <p className="text-sm text-slate-500">No action plan available.</p>;
  }

  const PRIORITY_COLORS: Record<string, string> = {
    high: "border-l-red-500",
    medium: "border-l-amber-500",
    low: "border-l-slate-300",
  };

  return (
    <div className="space-y-6">
      {phases.map((phase) => (
        <div key={phase.phase}>
          <div className="flex items-center gap-3 mb-3">
            <span className="flex items-center justify-center h-6 w-6 rounded-full bg-blue-600 text-white text-xs font-bold">
              {phase.phase}
            </span>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">{phase.title}</h3>
              <span className="text-xs text-slate-400">{phase.timeframe}</span>
            </div>
          </div>
          <div className="space-y-2 ml-9">
            {phase.actions.map((action, i) => (
              <div key={i} className={`border-l-4 ${PRIORITY_COLORS[action.expected_impact] ?? PRIORITY_COLORS.medium} bg-white border border-slate-200 rounded-r-lg p-3`}>
                <p className="text-sm text-slate-800">{action.action}</p>
                {action.rationale && (
                  <p className="text-xs text-slate-500 mt-1">{action.rationale}</p>
                )}
                {action.expected_impact && (
                  <span className="inline-block mt-1 text-xs text-slate-400">Impact: {action.expected_impact}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ABTestsTab({ tests }: { tests: ABTest[] }) {
  if (!tests || tests.length === 0) {
    return <p className="text-sm text-slate-500">No A/B test suggestions available.</p>;
  }

  return (
    <div className="space-y-4">
      {tests.map((test, i) => (
        <div key={i} className="border border-slate-200 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-slate-900">
              <span className="text-xs text-slate-400 mr-1.5">#{test.priority}</span>
              {test.test_name}
            </h3>
            {test.estimated_impact && (
              <span className="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full font-medium">
                {test.estimated_impact}
              </span>
            )}
          </div>
          <p className="text-sm text-slate-600 mb-3">{test.hypothesis}</p>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-slate-50 rounded-lg p-2.5">
              <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Control</span>
              <p className="text-sm text-slate-700 mt-0.5">{test.control}</p>
            </div>
            <div className="bg-blue-50 rounded-lg p-2.5">
              <span className="text-xs font-medium text-blue-500 uppercase tracking-wide">Variant</span>
              <p className="text-sm text-blue-800 mt-0.5">{test.variant}</p>
            </div>
          </div>
          <div className="mt-2 text-xs text-slate-400">Primary metric: {test.metric}</div>
        </div>
      ))}
    </div>
  );
}

function BenchmarkTab({ benchmark, report }: { benchmark: BenchmarkData | null; report: JobData["report"] }) {
  if (!benchmark || !benchmark.total_products) {
    return <p className="text-sm text-slate-500">No benchmark data available for this category.</p>;
  }

  const TIER_COLORS: Record<string, string> = {
    budget: "text-emerald-600",
    mid_range: "text-blue-600",
    premium: "text-violet-600",
    luxury: "text-amber-600",
  };

  return (
    <div className="space-y-6">
      {/* Benchmark stats */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: "Benchmark Products", value: benchmark.total_products.toLocaleString() },
          { label: "Benchmark Images", value: benchmark.total_images.toLocaleString() },
          { label: "A+ Adoption", value: `${benchmark.aplus_adoption_rate.toFixed(0)}%` },
          { label: "Avg Quality", value: `${benchmark.quality_avg.toFixed(1)}/5` },
        ].map((s) => (
          <div key={s.label} className="bg-slate-50 rounded-lg p-3 text-center">
            <div className="text-2xl font-semibold text-slate-900">{s.value}</div>
            <div className="text-xs text-slate-500 mt-0.5">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Opportunities (missing slots) */}
      {Object.keys(benchmark.missing_slots_ranking).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-3">Your Opportunities</h3>
          <div className="space-y-2">
            {Object.entries(benchmark.missing_slots_ranking).slice(0, 5).map(([slot, pct]) => (
              <div key={slot} className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
                <span className="text-lg font-bold text-amber-600">{pct.toFixed(0)}%</span>
                <div className="flex-1">
                  <span className="text-sm text-amber-800">missing <strong>{slot.replace(/_/g, " ")}</strong></span>
                  <p className="text-xs text-amber-600 mt-0.5">Add this image to beat {pct.toFixed(0)}% of competitors</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Image type comparison */}
      <div>
        <h3 className="text-sm font-medium text-slate-700 mb-3">
          Image Type: Your Competitors vs Category Benchmark
        </h3>
        <div className="flex gap-4 text-xs text-slate-500 mb-2">
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-blue-500 rounded-sm inline-block" /> Your Competitors</span>
          <span className="flex items-center gap-1"><span className="w-3 h-3 bg-slate-300 rounded-sm inline-block" /> Benchmark</span>
        </div>
        <div className="space-y-3">
          {Object.keys({ ...benchmark.image_type_distribution, ...report.image_type_distribution })
            .sort()
            .map((type) => {
              const yours = report.image_type_distribution[type] ?? 0;
              const theirs = benchmark.image_type_distribution[type] ?? 0;
              const delta = yours - theirs;
              return (
                <div key={type}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-slate-500 w-24 text-right">{type}</span>
                    <div className="flex-1 flex items-center gap-2">
                      <div className="flex-1 h-4 bg-slate-100 rounded-full overflow-hidden relative">
                        <div className="h-full bg-blue-500 rounded-full absolute top-0 left-0" style={{ width: `${Math.min(yours, 100)}%` }} />
                      </div>
                      <span className="text-xs w-10 text-blue-600">{yours.toFixed(0)}%</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-24" />
                    <div className="flex-1 flex items-center gap-2">
                      <div className="flex-1 h-4 bg-slate-100 rounded-full overflow-hidden relative">
                        <div className="h-full bg-slate-300 rounded-full absolute top-0 left-0" style={{ width: `${Math.min(theirs, 100)}%` }} />
                      </div>
                      <span className="text-xs w-10 text-slate-500">{theirs.toFixed(0)}%</span>
                      <span className={`text-xs font-semibold ${delta > 0 ? "text-emerald-600" : delta < 0 ? "text-red-500" : "text-slate-400"}`}>
                        {delta > 0 ? "+" : ""}{delta.toFixed(0)}%
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
        </div>
      </div>

      {/* Price tier distribution */}
      {Object.keys(benchmark.price_tier_distribution).length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-3">Price Tier Distribution</h3>
          <div className="grid grid-cols-4 gap-3">
            {Object.entries(benchmark.price_tier_distribution).map(([tier, pct]) => (
              <div key={tier} className="bg-slate-50 rounded-lg p-3 text-center">
                <div className={`text-xl font-bold ${TIER_COLORS[tier] ?? "text-slate-600"}`}>{pct.toFixed(0)}%</div>
                <div className="text-xs text-slate-500 mt-0.5">{tier.replace(/_/g, " ")}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Style tags */}
      {benchmark.top_style_tags.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2">Dominant Category Styles</h3>
          <div className="flex flex-wrap gap-2">
            {benchmark.top_style_tags.map((tag) => (
              <span key={tag} className="text-xs px-2.5 py-1 bg-blue-50 text-blue-700 rounded-full font-medium">
                {tag.replace(/_/g, " ")}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* A+ score */}
      {benchmark.aplus_avg_score > 0 && (
        <div className="bg-slate-50 rounded-lg p-4">
          <h3 className="text-sm font-medium text-slate-700 mb-2">A+ Content Intelligence</h3>
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-2xl font-semibold text-blue-600">{benchmark.aplus_adoption_rate.toFixed(0)}%</span>
              <span className="text-xs text-slate-500 ml-1">have A+ content</span>
            </div>
            <div>
              <span className="text-2xl font-semibold text-amber-600">{benchmark.aplus_avg_score.toFixed(1)}</span>
              <span className="text-xs text-slate-500 ml-1">/ 9 avg score</span>
            </div>
            <div className="flex-1 text-xs text-slate-500">
              Most A+ content in this category scores below average — doing it well puts you ahead.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
