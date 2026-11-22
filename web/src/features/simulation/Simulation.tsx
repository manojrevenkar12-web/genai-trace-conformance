import { useState } from "react";

import { DESIGNS, pct, type Report, SHORT } from "../../shared/data/report";
import styles from "./simulation.module.css";

const W = 560;
const LABEL = 200;
const ROW = 36;

export function Simulation({ report }: { report: Report }) {
  const s = report.simulation;
  const [hover, setHover] = useState<string | null>(null);
  const shown = DESIGNS.filter((d) => d !== "status_quo");
  const max = Math.max(0.8, ...shown.map((d) => s[d]!.exposure_cut_vs_status_quo[2]));
  const x = (v: number) => LABEL + (v / max) * (W - LABEL - 50);
  const h = shown.length * ROW + 26;
  const ticks = [0, 0.2, 0.4, 0.6, 0.8].filter((t) => t <= max);
  return (
    <section className={styles.section} aria-labelledby="sim-title">
      <div className={styles.text}>
        <h2 id="sim-title">What it is worth across six months of framework releases</h2>
        <p>
          A simulated ecosystem of ten integrations releasing on their own schedules; some releases break tracing in the ways the fault study measured. Every design meets the
          same releases and the same luck. Five of the ten integrations have scenarios in the lab; the other five can only be caught by users.
        </p>
      </div>
      <figure className={styles.chart} aria-label="Cut in project-days on broken traces against today, with 95% intervals">
        <svg viewBox={`0 0 ${W} ${h}`} className={styles.svg} role="img" aria-hidden>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={x(t)} x2={x(t)} y1={0} y2={h - 20} stroke="var(--grid)" />
              <text x={x(t)} y={h - 4} textAnchor="middle" className={styles.axis}>{pct(t)}</text>
            </g>
          ))}
          {shown.map((d, i) => {
            const v = s[d]!.exposure_cut_vs_status_quo;
            const y = i * ROW + ROW / 2;
            const lab = d === "lab";
            const color = lab ? "var(--accent)" : "var(--ink-3)";
            return (
              <g key={d} onMouseEnter={() => setHover(d)} onMouseLeave={() => setHover(null)}>
                <rect x={0} y={y - ROW / 2} width={W} height={ROW} rx={4} fill={hover === d ? "var(--grid)" : "transparent"} />
                <text x={0} y={y + 4} className={lab ? styles.nameStrong : styles.name}>{SHORT[d]}</text>
                <line x1={x(v[1])} x2={x(v[2])} y1={y} y2={y} stroke={color} strokeWidth={2} strokeLinecap="round" />
                <circle cx={x(v[0])} cy={y} r={6} fill={color} stroke="var(--surface)" strokeWidth={2} />
                <text x={x(v[2]) + 10} y={y + 4} className={styles.value}>{pct(v[0])}</text>
              </g>
            );
          })}
        </svg>
        <figcaption className={styles.caption}>
          {hover
            ? `${SHORT[hover]}: ${s[hover]!.label}. ${pct(s[hover]!.caught_by_lab_share[0])} of bugs caught by the lab, ${pct(s[hover]!.reached_users_share[0])} reached users, median ${s[hover]!.median_days_release_to_fix.toFixed(1)} days from release to fix.`
            : "Cut in project-days spent on broken traces, against today. Dot: mean over 20 simulated half-years; line: 95% interval."}
        </figcaption>
      </figure>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">Design</th>
            <th scope="col">Bugs reaching users</th>
            <th scope="col">Caught by the lab</th>
            <th scope="col">Wrong-cost project-days cut</th>
            <th scope="col">Days, release to fix</th>
            <th scope="col">Maintainer hours / week</th>
          </tr>
        </thead>
        <tbody>
          {DESIGNS.map((d) => (
            <tr key={d} className={d === "lab" ? styles.mine : undefined}>
              <th scope="row">{SHORT[d]}</th>
              <td>{pct(s[d]!.reached_users_share[0])}</td>
              <td>{pct(s[d]!.caught_by_lab_share[0])}</td>
              <td>{d === "status_quo" ? "–" : pct(s[d]!.wrong_cost_cut_vs_status_quo[0])}</td>
              <td>{s[d]!.median_days_release_to_fix.toFixed(1)}</td>
              <td>{s[d]!.maintainer_hours_per_week[0].toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
