"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";

type TopN = 10 | 20 | 30;
type Language = "en" | "zh";
type Platform = "amazon" | "walmart" | "ebay" | "etsy" | "shopee" | "tiktok_shop";

interface PlatformConfig {
  label: string;
  placeholder: string;
  inputLabel: string;
}

const PLATFORMS: Record<Platform, PlatformConfig> = {
  amazon: {
    label: "Amazon",
    placeholder: "boys dress shirt, B0ABC12345, or amazon.com URL",
    inputLabel: "Keyword, ASIN, or Amazon URL",
  },
  walmart: {
    label: "Walmart",
    placeholder: "portable blender, air fryer, baby stroller",
    inputLabel: "Search keyword",
  },
  ebay: {
    label: "eBay",
    placeholder: "vintage watch, laptop stand, bluetooth speaker",
    inputLabel: "Search keyword",
  },
  etsy: {
    label: "Etsy",
    placeholder: "handmade candle, custom jewelry, art print",
    inputLabel: "Search keyword",
  },
  shopee: {
    label: "Shopee",
    placeholder: "portable blender, phone case, wireless earbuds",
    inputLabel: "Search keyword",
  },
  tiktok_shop: {
    label: "TikTok Shop",
    placeholder: "skincare, led lights, phone accessories",
    inputLabel: "Search keyword",
  },
};

interface FormState {
  platform: Platform;
  query: string;
  top_n: TopN;
  language: Language;
  generate_lifestyle: boolean;
}

function isValidInput(value: string): boolean {
  return value.trim().length >= 2;
}

export default function SubmitForm() {
  const router = useRouter();
  const [form, setForm] = useState<FormState>({
    platform: "amazon",
    query: "",
    top_n: 10,
    language: "en",
    generate_lifestyle: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const platformConfig = PLATFORMS[form.platform];

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    const trimmed = form.query.trim();
    if (!trimmed) {
      setError("Please enter a search query.");
      return;
    }
    if (!isValidInput(trimmed)) {
      setError("Enter at least 2 characters.");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch("/api/proxy/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          platform: form.platform,
          query: trimmed,
          top_n: form.top_n,
          language: form.language,
          generate_lifestyle: form.generate_lifestyle,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? `Server error ${res.status}`);
      }

      const job = await res.json();
      router.push(`/jobs/${job.job_id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Unexpected error";
      setError(msg);
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Platform Selector */}
      <div>
        <span className="block text-sm font-medium text-slate-700 mb-1.5">
          Platform
        </span>
        <div className="flex rounded-lg border border-slate-200 overflow-hidden w-fit bg-white">
          {(Object.keys(PLATFORMS) as Platform[]).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setForm({ ...form, platform: p, query: "" })}
              disabled={submitting}
              className={`px-5 py-2 text-sm font-medium transition-colors ${
                form.platform === p
                  ? "bg-blue-600 text-white"
                  : "text-slate-600 hover:bg-slate-50"
              }`}
            >
              {PLATFORMS[p].label}
            </button>
          ))}
        </div>
      </div>

      {/* Query Input */}
      <div>
        <label
          htmlFor="query"
          className="block text-sm font-medium text-slate-700 mb-1.5"
        >
          {platformConfig.inputLabel}
        </label>
        <input
          id="query"
          type="text"
          value={form.query}
          onChange={(e) => setForm({ ...form, query: e.target.value })}
          placeholder={platformConfig.placeholder}
          className="w-full px-3 py-2.5 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent bg-white"
          disabled={submitting}
          autoComplete="off"
        />
      </div>

      {/* Products to analyze */}
      <div>
        <label
          htmlFor="top_n"
          className="block text-sm font-medium text-slate-700 mb-1.5"
        >
          Products to analyze
        </label>
        <select
          id="top_n"
          value={form.top_n}
          onChange={(e) =>
            setForm({ ...form, top_n: Number(e.target.value) as TopN })
          }
          className="w-full px-3 py-2.5 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:border-transparent bg-white"
          disabled={submitting}
        >
          <option value={10}>10 products (~70 images)</option>
          <option value={20}>20 products (~140 images)</option>
          <option value={30}>30 products (~210 images)</option>
        </select>
      </div>

      {/* Language and Lifestyle row */}
      <div className="flex flex-col sm:flex-row gap-5">
        {/* Language toggle */}
        <div className="flex-1">
          <span className="block text-sm font-medium text-slate-700 mb-1.5">
            Report language
          </span>
          <div className="flex rounded-lg border border-slate-200 overflow-hidden w-fit bg-white">
            {(["en", "zh"] as Language[]).map((lang) => (
              <button
                key={lang}
                type="button"
                onClick={() => setForm({ ...form, language: lang })}
                disabled={submitting}
                className={`px-5 py-2 text-sm font-medium transition-colors ${
                  form.language === lang
                    ? "bg-blue-600 text-white"
                    : "text-slate-600 hover:bg-slate-50"
                }`}
              >
                {lang === "en" ? "EN" : "\u4e2d\u6587"}
              </button>
            ))}
          </div>
        </div>

        {/* Lifestyle images toggle */}
        <div className="flex-1">
          <span className="block text-sm font-medium text-slate-700 mb-1.5">
            Lifestyle images
            <span className="ml-1.5 text-xs font-normal text-slate-400">
              +$0.09 per image
            </span>
          </span>
          <button
            type="button"
            role="switch"
            aria-checked={form.generate_lifestyle}
            onClick={() =>
              setForm({ ...form, generate_lifestyle: !form.generate_lifestyle })
            }
            disabled={submitting}
            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 ${
              form.generate_lifestyle ? "bg-blue-600" : "bg-slate-200"
            }`}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow-sm ${
                form.generate_lifestyle ? "translate-x-6" : "translate-x-1"
              }`}
            />
          </button>
          <span className="ml-2.5 text-sm text-slate-500 align-middle">
            {form.generate_lifestyle ? "On" : "Off"}
          </span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {/* Submit */}
      <button
        type="submit"
        disabled={submitting}
        className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors"
      >
        {submitting ? "Starting..." : "Start Analysis"}
      </button>
    </form>
  );
}
