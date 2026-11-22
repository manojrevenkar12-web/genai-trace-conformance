import { label, pct, type Report } from "../../shared/data/report";
import styles from "./faults.module.css";

export function Faults({ report }: { report: Report }) {
  const fs = report.fault_study;
  const kinds = Object.entries(fs.kinds).sort((a, b) => (b[1].recall ?? 0) - (a[1].recall ?? 0) || b[1].planted - a[1].planted);
  return (
    <section className={styles.section} aria-labelledby="faults-title">
      <div className={styles.text}>
        <h2 id="faults-title">Do the checks catch the bugs integrations really ship?</h2>
        <p>
          Each kind is a class of real Langfuse integration issue, planted into clean traces captured from the real SDKs. Two kinds have no check yet; they are listed to show
          where the lab stops.
        </p>
        <p className={styles.fa}>
          <strong>{fs.false_alarms}</strong> false alarms on {fs.benign_changes} harmless changes: reordered exports, extra HTTP spans, extra attributes, renamed spans, 3 ms of clock skew.
        </p>
      </div>
      <ul className={styles.list}>
        {kinds.map(([k, v]) => (
          <li key={k}>
            <span className={styles.name}>{label(k)}</span>
            <span className={styles.bar} aria-hidden>
              <span style={{ width: `${(v.recall ?? 0) * 100}%` }} className={(v.recall ?? 0) < 0.5 ? styles.low : undefined} />
            </span>
            <span className={styles.n}>
              {pct(v.recall ?? 0)} <span>of {v.planted}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
