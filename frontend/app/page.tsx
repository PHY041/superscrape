import SubmitForm from "@/components/SubmitForm";

export default function HomePage() {
  return (
    <div className="max-w-xl">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900 mb-2">
          Visual Intelligence
        </h1>
        <p className="text-sm text-slate-500 leading-relaxed">
          Select a platform and enter a search query to run an AI-powered
          visual analysis of top products. The report includes image type
          distribution, camera angles, and actionable recommendations.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-6">
        <SubmitForm />
      </div>

      <div className="mt-4 flex items-start gap-2 text-sm text-slate-400 bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
        <svg
          width="14"
          height="14"
          viewBox="0 0 14 14"
          fill="none"
          className="mt-0.5 flex-shrink-0"
          aria-hidden="true"
        >
          <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
          <path
            d="M7 6.5v4M7 4h.01"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
        Analysis takes 8-12 minutes depending on the number of products and
        whether lifestyle images are enabled.
      </div>
    </div>
  );
}
