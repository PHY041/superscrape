"use client";

interface ReportViewerProps {
  reportUrl: string;
  pdfUrl: string | null;
}

export default function ReportViewer({ reportUrl, pdfUrl }: ReportViewerProps) {
  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-slate-900">
          Visual Intelligence Report
        </h2>
        {pdfUrl && (
          <a
            href={pdfUrl}
            download
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition-colors"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 14 14"
              fill="none"
              aria-hidden="true"
            >
              <path
                d="M7 1v8M4 6l3 3 3-3M2 11h10"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Download PDF
          </a>
        )}
      </div>

      {/* iframe */}
      <div className="border border-slate-200 rounded-xl overflow-hidden bg-white">
        <iframe
          src={reportUrl}
          title="Visual Intelligence Report"
          className="w-full"
          style={{ height: "80vh" }}
          sandbox="allow-same-origin"
        />
      </div>
    </div>
  );
}
