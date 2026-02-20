"use client";

import type { PipelineStep } from "@/hooks/useJobProgress";

interface ProgressTrackerProps {
  step: PipelineStep;
  message: string;
  progress: number;
  platform?: string;
}

interface StepDefinition {
  key: PipelineStep;
  label: string;
}

const PLATFORM_LABELS: Record<string, string> = {
  amazon: "Amazon",
  walmart: "Walmart",
  ebay: "eBay",
  etsy: "Etsy",
  shopee: "Shopee",
  tiktok_shop: "TikTok Shop",
};

function getSteps(platform: string): StepDefinition[] {
  const platformLabel = PLATFORM_LABELS[platform] || platform;
  return [
    { key: "scraping", label: `Scraping ${platformLabel}` },
    { key: "analyzing", label: "AI Vision Analysis" },
    { key: "generating", label: "Lifestyle Images" },
    { key: "building_report", label: "Building Report" },
    { key: "done", label: "Complete" },
  ];
}

type StepStatus = "done" | "active" | "pending";

function getStepStatus(
  stepKey: PipelineStep,
  currentStep: PipelineStep
): StepStatus {
  const stepOrder: PipelineStep[] = [
    "queued",
    "scraping",
    "analyzing",
    "generating",
    "building_report",
    "done",
  ];
  // If failed, show steps up to the last completed as "done"
  if (currentStep === "failed") {
    return "pending";
  }
  const current = stepOrder.indexOf(currentStep);
  const target = stepOrder.indexOf(stepKey);

  if (current > target) return "done";
  if (current === target) return "active";
  return "pending";
}

function StepIcon({ status }: { status: StepStatus }) {
  if (status === "done") {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-blue-600 flex-shrink-0">
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          aria-hidden="true"
        >
          <path
            d="M2 6l3 3 5-5"
            stroke="white"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }

  if (status === "active") {
    return (
      <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-blue-600 flex-shrink-0">
        <span className="h-2.5 w-2.5 rounded-full bg-blue-600 animate-pulse" />
      </span>
    );
  }

  return (
    <span className="flex h-6 w-6 items-center justify-center rounded-full border-2 border-slate-200 flex-shrink-0">
      <span className="h-2 w-2 rounded-full bg-slate-200" />
    </span>
  );
}

export default function ProgressTracker({
  step,
  message,
  progress,
  platform = "amazon",
}: ProgressTrackerProps) {
  const steps = getSteps(platform);

  return (
    <div className="space-y-6">
      {/* Progress bar */}
      <div>
        <div className="flex justify-between items-center mb-1.5">
          <span className="text-sm font-medium text-slate-700">
            {progress}% complete
          </span>
          <span className="text-xs text-slate-400">Est. 8-12 min</span>
        </div>
        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-600 rounded-full transition-all duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Current message */}
      {message && (
        <p className="text-sm text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5">
          {message}
        </p>
      )}

      {/* Step list */}
      <ol className="space-y-3">
        {steps.map(({ key, label }) => {
          const status = getStepStatus(key, step);
          return (
            <li key={key} className="flex items-center gap-3">
              <StepIcon status={status} />
              <span
                className={`text-sm ${
                  status === "done"
                    ? "text-slate-900 font-medium"
                    : status === "active"
                    ? "text-blue-600 font-medium"
                    : "text-slate-400"
                }`}
              >
                {label}
                {status === "active" && (
                  <span className="ml-1.5 text-xs text-slate-400 font-normal">
                    Running...
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
