import useSWR from "swr";
import { apiClient } from "@/lib/api-client";

export interface SessionInfo {
  name: string;
  files: string[];
  file_count: number;
}

export interface ReportContent {
  name: string;
  session: string;
  content: string;
}

export function useReportSessions() {
  return useSWR<{ success: boolean; data: SessionInfo[] }>(
    "/reports/sessions",
    (url: string) => apiClient.get<SessionInfo[]>(url),
  );
}

export function useReportContent(sessionName: string, fileName: string) {
  const encodedSession = encodeURIComponent(sessionName);
  const encodedFile = encodeURIComponent(fileName);
  return useSWR<{ success: boolean; data: ReportContent }>(
    sessionName && fileName
      ? `/reports/sessions/${encodedSession}/files/${encodedFile}`
      : null,
    (url: string) => apiClient.get<ReportContent>(url),
  );
}
