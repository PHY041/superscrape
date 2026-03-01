"use client";

import { useParams } from "next/navigation";
import { useJobProgress } from "@/hooks/useJobProgress";
import ProgressTracker from "@/components/ProgressTracker";
import ReportViewer from "@/components/ReportViewer";
import DataDashboard from "@/components/DataDashboard";

export default function JobPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId ?? "";

  const { step, message, progress, isDone, isFailed, reportUrl, pdfUrl, errorMessage, platform } =
    useJobProgress(jobId);

  return (
    <div className="max-w-4xl space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-xl font-semibold text-slate-900 mb-1">
          {isDone ? "Analysis Complete" : isFailed ? "Analysis Failed" : "Analysis in Progress"}
        </h1>
        <p className="text-xs text-slate-400 font-mono">Job ID: {jobId}</p>
      </div>

      {/* Error state */}
      {isFailed && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-4 py-3">
          <p className="text-sm font-medium text-red-700 mb-1">
            Something went wrong
          </p>
          <p className="text-sm text-red-600">
            {errorMessage ?? "An unknown error occurred."}
          </p>
        </div>
      )}

      {/* Success alert */}
      {isDone && (
        <div className="bg-green-50 border border-green-200 rounded-xl px-4 py-3">
          <p className="text-sm font-medium text-green-700">
            Report ready — explore the intelligence dashboard below.
          </p>
        </div>
      )}

      {/* Progress tracker (always show while not done/failed) */}
      {!isDone && !isFailed && (
        <div className="bg-white border border-slate-200 rounded-xl p-6">
          <ProgressTracker step={step} message={message} progress={progress} platform={platform} />
        </div>
      )}

      {/* Done state: show progress summary + report */}
      {isDone && (
        <div className="bg-white border border-slate-200 rounded-xl p-6">
          <ProgressTracker step={step} message={message} progress={100} platform={platform} />
        </div>
      )}

      {/* Data Dashboard — review insights, story arc, action plan, A/B tests */}
      {isDone && <DataDashboard jobId={jobId} />}

      {/* HTML Report viewer */}
      {isDone && reportUrl && (
        <ReportViewer reportUrl={reportUrl} pdfUrl={pdfUrl} />
      )}
    </div>
  );
}
