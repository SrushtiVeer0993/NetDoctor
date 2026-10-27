import { useEffect, useState } from "react";
import { FileText, Download } from "lucide-react";
import DashboardLayout from "../layouts/DashboardLayout";
import { api } from "../services/api";
import type { DiagnosisSummary } from "../types";

interface ReportRow {
  id: number;
  created_at: string;
  format: "pdf" | "csv" | "json";
  diagnostic_run_id: number | null;
  download_url: string;
}

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : error?.message || "Something went wrong.";
}

async function saveDownload(url: string, filename: string) {
  // The API requires a bearer token, so downloads must use the authenticated
  // Axios client instead of a plain browser link/window.open.
  const response = await api.get<Blob>(url, { responseType: "blob" });
  const objectUrl = URL.createObjectURL(response.data);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}

export default function Reports() {
  const [runs, setRuns] = useState<DiagnosisSummary[]>([]);
  const [reports, setReports] = useState<ReportRow[]>([]);
  const [working, setWorking] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [runsRes, reportsRes] = await Promise.all([
        api.get<DiagnosisSummary[]>("/api/diagnostics/history"),
        api.get<ReportRow[]>("/api/reports"),
      ]);
      setRuns(runsRes.data);
      setReports(reportsRes.data);
    } catch (err) {
      setError(`Could not load reports: ${errorMessage(err)}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function generate(runId: number, format: ReportRow["format"]) {
    setWorking(`generate-${runId}-${format}`);
    setError(null);
    try {
      const response = await api.post<{ download_url: string }>(`/api/reports/${runId}/${format}`);
      await saveDownload(response.data.download_url, `netdoctor_run_${runId}.${format}`);
      await load();
    } catch (err) {
      setError(`Could not generate or download the report: ${errorMessage(err)}`);
    } finally {
      setWorking(null);
    }
  }

  async function download(report: ReportRow) {
    setWorking(`download-${report.id}`);
    setError(null);
    try {
      const runLabel = report.diagnostic_run_id == null ? "report" : `run_${report.diagnostic_run_id}`;
      await saveDownload(report.download_url, `netdoctor_${runLabel}.${report.format}`);
    } catch (err) {
      setError(`Could not download the report: ${errorMessage(err)}`);
    } finally {
      setWorking(null);
    }
  }

  return (
    <DashboardLayout>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-slate-100">Reports</h1>
        <p className="text-sm text-slate-500 mt-0.5">Export any past diagnostic run as PDF, CSV, or JSON</p>
      </div>

      {error && (
        <div role="alert" className="mb-4 rounded-lg border border-red-900 bg-red-950/30 p-4 text-sm text-red-300">
          {error} <button onClick={() => void load()} className="ml-2 underline">Retry</button>
        </div>
      )}
      {loading && <div role="status" className="mb-4 text-sm text-slate-500">Loading reports…</div>}

      <div className="rounded-lg border border-border bg-panel p-5 mb-6 overflow-x-auto">
        <div className="text-sm font-medium text-slate-200 mb-3">Diagnostic runs</div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-slate-600 uppercase">
              <th className="pb-2 font-normal">Time</th>
              <th className="pb-2 font-normal">Health</th>
              <th className="pb-2 font-normal">Export</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-border">
                <td className="py-2 text-slate-400">{new Date(run.created_at).toLocaleString()}</td>
                <td className="py-2 text-slate-200 font-mono-num">{run.health_score}</td>
                <td className="py-2">
                  <div className="flex gap-2">
                    {(["pdf", "csv", "json"] as const).map((format) => {
                      const key = `generate-${run.id}-${format}`;
                      return (
                        <button
                          key={format}
                          onClick={() => void generate(run.id, format)}
                          disabled={working !== null}
                          className="text-xs px-2.5 py-1 rounded border border-border text-slate-400 hover:border-healthy hover:text-healthy disabled:opacity-50"
                        >
                          {working === key ? "Preparing…" : format.toUpperCase()}
                        </button>
                      );
                    })}
                  </div>
                </td>
              </tr>
            ))}
            {!loading && !error && runs.length === 0 && (
              <tr><td colSpan={3} className="py-6 text-center text-slate-600">No diagnostic runs yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="rounded-lg border border-border bg-panel p-5">
        <div className="text-sm font-medium text-slate-200 mb-3">Generated reports</div>
        <div className="space-y-2">
          {reports.map((report) => (
            <div key={report.id} className="flex items-center justify-between gap-4 text-sm border-t border-border pt-2 first:border-t-0 first:pt-0">
              <div className="flex items-center gap-2 min-w-0 text-slate-300">
                <FileText size={14} className="text-slate-500 shrink-0" />
                <span className="truncate">
                  Run #{report.diagnostic_run_id ?? "—"} · {report.format.toUpperCase()} · {new Date(report.created_at).toLocaleString()}
                </span>
              </div>
              <button
                onClick={() => void download(report)}
                disabled={working !== null}
                className="flex shrink-0 items-center gap-1 text-xs text-healthy hover:underline disabled:opacity-50"
              >
                <Download size={13} /> {working === `download-${report.id}` ? "Downloading…" : "Download"}
              </button>
            </div>
          ))}
          {!loading && !error && reports.length === 0 && <div className="text-sm text-slate-600">No reports generated yet.</div>}
        </div>
      </div>
    </DashboardLayout>
  );
}
