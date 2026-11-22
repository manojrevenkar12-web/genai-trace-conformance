import { useState } from "react";

import { Bisections } from "../features/bisect/Bisections";
import { Faults } from "../features/faults/Faults";
import { Matrix } from "../features/matrix/Matrix";
import { Simulation } from "../features/simulation/Simulation";
import { Triage } from "../features/triage/Triage";
import { pct, type Report, type SetName, useReport } from "../shared/data/report";
import { Failed, Loading, Missing } from "../shared/ui/states";
import styles from "./App.module.css";

function initialSet(): SetName {
  return new URLSearchParams(window.location.search).get("set") === "dev" ? "dev" : "heldout";
}

function Headline({ report }: { report: Report }) {
  const f = report.facts;
  const failing = report.cells.filter((c) => c.results.some((r) => r.status === "fail")).length;
  const lab = report.simulation.lab!;
  return (
    <div className={styles.headline}>
      <h1>
        {failing} of {f.cells} real SDK runs show a trace that does not match what the model provider charged{f.cells_crashed ? `, and ${f.cells_crashed} combinations the installer allows crash` : ""}.
      </h1>
      <p>
        {f.environments} {report.set === "heldout" ? "held-out" : "development"} environments, {f.pinned_versions} pinned versions of Langfuse, OpenAI, Anthropic, LangChain, Pydantic AI
        and the Agents SDK, {f.model_calls} model calls and {f.spans} spans captured over OTLP. The checks caught {pct(report.fault_study.covered_recall)} of planted bugs of the
        kinds they cover with {report.fault_study.false_alarms} false alarms, and in the simulated ecosystem the lab cut project-days on broken traces by{" "}
        {pct(lab.exposure_cut_vs_status_quo[0])}.
      </p>
    </div>
  );
}

export function App() {
  const [set, setSet] = useState<SetName>(initialSet);
  const { state, retry } = useReport(set);
  return (
    <div className={styles.page}>
      <header className={styles.top}>
        <div>
          <p className={styles.name}>genai-trace-conformance</p>
          <p className={styles.what}>Conformance lab for LLM tracing integrations</p>
        </div>
        <div className={styles.switch} role="group" aria-label="Which run to show">
          {(["heldout", "dev"] as const).map((s) => (
            <button key={s} aria-pressed={set === s} onClick={() => setSet(s)}>
              {s === "heldout" ? "Held-out run" : "Development run"}
            </button>
          ))}
        </div>
      </header>
      <main className={styles.main}>
        {state.status === "loading" && <Loading />}
        {state.status === "error" && <Failed message={state.message} onRetry={retry} />}
        {state.status === "missing" && <Missing set={set} onDev={() => setSet("dev")} />}
        {state.status === "ready" && (
          <>
            <Headline report={state.report} />
            <Matrix report={state.report} />
            <Bisections report={state.report} />
            <Faults report={state.report} />
            <Triage report={state.report} />
            <Simulation report={state.report} />
            <footer className={styles.foot}>
              Collected {state.report.collected_on}, config {state.report.config_sha}. The SDKs, the exporters and the wire format are real; the model provider is a local server,
              and the ecosystem in the last section is simulated. See the README for the limits.
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
