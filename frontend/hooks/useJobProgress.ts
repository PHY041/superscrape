"use client";

import { useEffect, useRef, useState } from "react";

export type PipelineStep =
  | "queued"
  | "scraping"
  | "analyzing"
  | "generating"
  | "building_report"
  | "done"
  | "failed";

export interface ProgressState {
  step: PipelineStep;
  message: string;
  progress: number;
  detail: Record<string, unknown>;
  isDone: boolean;
  isFailed: boolean;
  reportUrl: string | null;
  pdfUrl: string | null;
  errorMessage: string | null;
  platform: string;
}

const INITIAL_STATE: ProgressState = {
  step: "queued",
  message: "Waiting to start...",
  progress: 0,
  detail: {},
  isDone: false,
  isFailed: false,
  reportUrl: null,
  pdfUrl: null,
  errorMessage: null,
  platform: "amazon",
};

export function useJobProgress(jobId: string): ProgressState {
  const [state, setState] = useState<ProgressState>(INITIAL_STATE);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!jobId) return;

    const es = new EventSource(`/api/proxy/jobs/${jobId}/stream`);
    esRef.current = es;

    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as {
          step: PipelineStep;
          message: string;
          progress: number;
          detail: Record<string, unknown>;
        };

        const isDone = data.step === "done";
        const isFailed = data.step === "failed";

        const reportUrl =
          isDone && typeof data.detail?.report_url === "string"
            ? `/api/proxy${data.detail.report_url}`
            : null;

        const pdfUrl =
          isDone && typeof data.detail?.pdf_url === "string" && data.detail.pdf_url !== ""
            ? `/api/proxy${data.detail.pdf_url}`
            : null;

        const errorMessage =
          isFailed && typeof data.detail?.error === "string"
            ? (data.detail.error as string)
            : isFailed
            ? data.message
            : null;

        setState((prev) => {
          // Extract platform from detail (sent on first scraping event)
          const platform =
            typeof data.detail?.platform === "string"
              ? data.detail.platform
              : prev.platform;

          return {
            step: data.step,
            message: data.message,
            progress: data.progress,
            detail: data.detail,
            isDone,
            isFailed,
            reportUrl,
            pdfUrl,
            errorMessage,
            platform,
          };
        });

        if (isDone || isFailed) {
          es.close();
        }
      } catch {
        // Ignore parse errors for malformed events
      }
    };

    es.onerror = () => {
      es.close();
      setState((prev) => {
        if (prev.isDone || prev.isFailed) return prev;
        return {
          ...prev,
          isFailed: true,
          errorMessage: "Lost connection to server. Please refresh.",
        };
      });
    };

    return () => {
      es.close();
    };
  }, [jobId]);

  return state;
}
