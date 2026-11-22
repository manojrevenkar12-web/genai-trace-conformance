import { motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { type Report, type Status, worst } from "../../shared/data/report";
import styles from "./matrix.module.css";

const SHORT: Record<string, string> = {
  runs: "Runs",
  one_generation_per_call: "1 generation / call",
  model_name: "Model name",
  usage_exact: "Token usage",
  cost_exact: "Cost",
  readable_io: "Readable I/O",
  one_trace_per_run: "1 trace / run",
  nested_under_run: "Nested",
  tools_traced: "Tools",
  run_isolation: "Isolation",
  standard_attribute_names: "Standard names",
};
const GLYPH: Record<string, string> = { pass: "✓", fail: "✕", warn: "!", crash: "✕", "n/a": "", none: "" };
const WORD: Record<string, string> = { pass: "passes", fail: "fails", warn: "warns", crash: "crashes", "n/a": "does not apply", none: "not run" };

interface Picked { env: string; column: string }

export function Matrix({ report }: { report: Report }) {
  const reduce = useReducedMotion();
  const columns = ["runs", ...report.checks.map((c) => c.id)];
  const byEnv = useMemo(() => {
    const m = new Map<string, typeof report.cells>();
    for (const c of report.cells) m.set(c.env, [...(m.get(c.env) ?? []), c]);
    return m;
  }, [report]);
  const [picked, setPicked] = useState<Picked | null>(() => {
    const first = report.cells.find((c) => c.results.some((r) => r.status === "fail"));
    const chk = first?.results.find((r) => r.status === "fail")?.check;
    return first && chk ? { env: first.env, column: chk } : null;
  });

  function cellStatus(env: string, column: string): { status: Status | "crash" | "none"; count: number } {
    const cells = byEnv.get(env) ?? [];
    if (column === "runs") {
      const crashed = cells.filter((c) => !c.ran).length;
      return { status: crashed ? "crash" : "pass", count: crashed };
    }
    const st = cells.filter((c) => c.ran).map((c) => c.results.find((r) => r.check === column)?.status ?? "n/a");
    return { status: worst(st), count: st.filter((s) => s === "fail" || s === "warn").length };
  }

  const families = [...new Set(report.environments.map((e) => e.family))];
  const detail = picked
    ? (byEnv.get(picked.env) ?? []).map((c) =>
        picked.column === "runs"
          ? { scenario: c.scenario, status: c.ran ? "pass" : "crash", text: c.ran ? "ran to the end" : (c.error ?? "crashed") }
          : { scenario: c.scenario, status: c.ran ? (c.results.find((r) => r.check === picked.column)?.status ?? "n/a") : "crash", text: c.ran ? (c.results.find((r) => r.check === picked.column)?.detail ?? "") : "did not run" },
      )
    : [];
  const env = report.environments.find((e) => e.name === picked?.env);

  return (
    <section className={styles.wrap} aria-labelledby="matrix-title">
      <div className={styles.head}>
        <h2 id="matrix-title">Every SDK combination, every check</h2>
        <p>
          Each row is one environment of pinned SDK versions running its framework's scenarios against the local model server. A cell shows the worst outcome across those
          scenarios. Select a cell to read what happened.
        </p>
      </div>
      <div className={styles.scroll}>
        <table className={styles.grid}>
          <thead>
            <tr>
              <th scope="col" className={styles.envHead}>Environment</th>
              {columns.map((c) => (
                <th key={c} scope="col" className={styles.colHead}>
                  <span>{SHORT[c] ?? c}</span>
                </th>
              ))}
            </tr>
          </thead>
          {families.map((fam) => (
            <tbody key={fam}>
              {report.environments
                .filter((e) => e.family === fam)
                .map((e, ri) => (
                  <tr key={e.name}>
                    <th scope="row" className={styles.envName}>
                      {e.name}
                    </th>
                    {columns.map((col, ci) => {
                      const { status, count } = cellStatus(e.name, col);
                      const active = picked?.env === e.name && picked.column === col;
                      return (
                        <td key={col}>
                          <motion.button
                            type="button"
                            className={`${styles.cell} ${styles[status.replace("/", "")] ?? ""} ${active ? styles.active : ""}`}
                            aria-label={`${e.name}: ${SHORT[col]} ${WORD[status]}${count > 1 ? ` in ${count} scenarios` : ""}`}
                            aria-pressed={active}
                            onClick={() => setPicked({ env: e.name, column: col })}
                            initial={reduce ? false : { opacity: 0, scale: 0.6 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ duration: 0.25, delay: reduce ? 0 : 0.1 + ci * 0.035 + ri * 0.01 }}
                          >
                            <span aria-hidden>{GLYPH[status]}</span>
                            {count > 1 && <sub aria-hidden>{count}</sub>}
                          </motion.button>
                        </td>
                      );
                    })}
                  </tr>
                ))}
            </tbody>
          ))}
        </table>
      </div>
      <ul className={styles.legend} aria-label="Legend">
        <li><span className={`${styles.key} ${styles.pass}`}>✓</span> passes</li>
        <li><span className={`${styles.key} ${styles.fail}`}>✕</span> fails</li>
        <li><span className={`${styles.key} ${styles.warn}`}>!</span> warns</li>
        <li><span className={`${styles.key} ${styles.crash}`}>✕</span> scenario crashed</li>
        <li><span className={`${styles.key} ${styles.na}`} /> does not apply</li>
      </ul>
      {picked && env && (
        <div className={styles.detail} aria-live="polite">
          <div className={styles.detailHead}>
            <h3>
              {env.name}: {SHORT[picked.column]}
            </h3>
            <p className={styles.pins}>
              {Object.entries(env.pins).map(([k, v]) => (
                <code key={k}>
                  {k}=={v}
                </code>
              ))}
            </p>
          </div>
          <ul className={styles.rows}>
            {detail.map((d) => (
              <li key={d.scenario}>
                <span className={`${styles.dot} ${styles[d.status.replace("/", "")] ?? ""}`} aria-hidden>{GLYPH[d.status]}</span>
                <code>{d.scenario}</code>
                <span className={styles.text}>{d.text || "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
