import { useCallback, useEffect, useState } from "react";

export type SetName = "heldout" | "dev";
export type Interval = [number, number, number];
export type Status = "pass" | "fail" | "warn" | "n/a";

export interface CheckResult { check: string; status: Status; detail: string }
export interface Cell { env: string; scenario: string; ran: boolean; error: string | null; results: CheckResult[] }
export interface Env { name: string; family: string; pins: Record<string, string> }
export interface Bisection { name: string; package: string; scenario: string; check: string | null; last_good: string; first_bad: string; tested: { version: string; good: boolean | null; detail: string }[] }
export interface FaultKind { planted: number; caught: number; attributed: number; recall: number | null; example: string | null }
export interface Prf { precision: number; recall: number; f1: number }
export interface Design {
  label: string;
  reached_users_share: Interval;
  caught_by_lab_share: Interval;
  exposure_cut_vs_status_quo: Interval;
  wrong_cost_cut_vs_status_quo: Interval;
  median_days_release_to_fix: number;
  maintainer_hours_per_week: Interval;
}
export interface Report {
  set: SetName;
  config_sha: string;
  collected_on: string;
  facts: { environments: number; cells: number; cells_ran: number; cells_crashed: number; model_calls: number; spans: number; pinned_versions: number; issues: number };
  checks: { id: string; title: string }[];
  environments: Env[];
  cells: Cell[];
  bisections: Bisection[];
  fault_study: { kinds: Record<string, FaultKind>; benign_changes: number; false_alarms: number; covered_recall: number };
  triage: { split_date: string; agent: { issues: number; micro: Prf; per_label: Record<string, Prf & { support: number }> }; naive: { issues: number; micro: Prf } };
  simulation: Record<string, Design>;
  gates: { gate: string; measured: number; pass: boolean }[];
}

export type LoadState = { status: "loading" } | { status: "error"; message: string } | { status: "missing" } | { status: "ready"; report: Report };

/** Loads reports/<set>.json as written by `python -m gtc.eval.cli dev` or `heldout`. */
export function useReport(set: SetName): { state: LoadState; retry: () => void } {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    setState({ status: "loading" });
    fetch(`./reports/${set}.json`)
      .then(async (res) => {
        if (!live) return;
        if (res.status === 404) return setState({ status: "missing" });
        if (!res.ok) throw new Error(`The report did not load (HTTP ${res.status}).`);
        const report = (await res.json()) as Report;
        if (live) setState({ status: "ready", report });
      })
      .catch((err: unknown) => live && setState({ status: "error", message: err instanceof Error ? err.message : String(err) }));
    return () => {
      live = false;
    };
  }, [set, attempt]);
  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  return { state, retry };
}

export const DESIGNS = ["status_quo", "agent_only", "nightly", "nightly_main", "lab"] as const;
export const SHORT: Record<string, string> = {
  status_quo: "Today",
  agent_only: "Triage agent only",
  nightly: "Nightly on releases",
  nightly_main: "Nightly on releases and main",
  lab: "The lab",
};
export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const label = (s: string) => s.replace(/_/g, " ");

/** Worst status first: a crashed run, then fail, warn, pass, n/a. */
export function worst(statuses: (Status | "crash")[]): Status | "crash" | "none" {
  for (const s of ["crash", "fail", "warn", "pass", "n/a"] as const) if (statuses.includes(s)) return s;
  return "none";
}
