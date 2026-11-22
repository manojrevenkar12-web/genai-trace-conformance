import { label, type Prf, type Report } from "../../shared/data/report";
import styles from "./triage.module.css";

function Row({ name, m }: { name: string; m: Prf }) {
  return (
    <tr>
      <th scope="row">{name}</th>
      {(["precision", "recall", "f1"] as const).map((k) => (
        <td key={k}>
          <span className={styles.bar} aria-hidden>
            <span style={{ width: `${m[k] * 100}%` }} />
          </span>
          {m[k].toFixed(2)}
        </td>
      ))}
    </tr>
  );
}

export function Triage({ report }: { report: Report }) {
  const t = report.triage;
  const labels = Object.entries(t.agent.per_label).filter(([, v]) => v.support > 0);
  return (
    <section className={styles.section} aria-labelledby="triage-title">
      <div className={styles.text}>
        <h2 id="triage-title">The triage agent, scored by Langfuse's maintainers</h2>
        <p>
          It reads a GitHub issue, names the integration and the symptom, and points to the scenario and check that reproduce it. Scored against the integration labels
          maintainers put on {t.agent.issues} real issues {report.set === "heldout" ? `from ${t.split_date} on, after its rules were frozen` : `created before ${t.split_date}`}.
        </p>
      </div>
      <div className={styles.tables}>
        <table className={styles.table}>
          <thead>
            <tr><th scope="col">Labeller</th><th scope="col">Precision</th><th scope="col">Recall</th><th scope="col">F1</th></tr>
          </thead>
          <tbody>
            <Row name="Triage agent" m={t.agent.micro} />
            <Row name="Any mention of the framework" m={t.naive.micro} />
          </tbody>
        </table>
        <table className={styles.table}>
          <thead>
            <tr><th scope="col">Label</th><th scope="col">Issues</th><th scope="col">Precision</th><th scope="col">Recall</th></tr>
          </thead>
          <tbody>
            {labels.map(([k, v]) => (
              <tr key={k}>
                <th scope="row">{label(k.replace("integration-", ""))}</th>
                <td>{v.support}</td>
                <td>{v.precision.toFixed(2)}</td>
                <td>{v.recall.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
