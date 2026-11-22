import type { Bisection, Report } from "../../shared/data/report";
import styles from "./bisect.module.css";

function key(v: string): number[] {
  return v.split(".").map((x) => Number(x));
}
function cmp(a: string, b: string): number {
  const x = key(a), y = key(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) - (y[i] ?? 0);
  return 0;
}

function Ladder({ b }: { b: Bisection }) {
  const points = [{ version: b.last_good, good: true as boolean | null, end: true }, ...b.tested.map((t) => ({ ...t, end: false })), { version: b.first_bad, good: false as boolean | null, end: true }];
  const uniq = [...new Map(points.map((p) => [p.version, p])).values()].sort((p, q) => cmp(p.version, q.version));
  return (
    <figure className={styles.card} aria-label={`${b.name}: last good ${b.package} ${b.last_good}, first bad ${b.first_bad}`}>
      <figcaption>
        <h3>{b.name}</h3>
        <p className={styles.sub}>
          <code>{b.scenario}</code>, {b.check ? <>check <code>{b.check}</code></> : "does it run at all"}, {b.tested.length} versions tested
        </p>
      </figcaption>
      <ol className={styles.ladder}>
        {uniq.map((p) => {
          const boundary = p.version === b.first_bad;
          return (
            <li key={p.version} className={`${styles.step} ${p.good ? styles.good : styles.bad} ${boundary ? styles.boundary : ""}`}>
              <span className={styles.mark} aria-hidden>{p.good ? "✓" : "✕"}</span>
              <code>{b.package} {p.version}</code>
              {boundary && <span className={styles.tag}>first bad</span>}
              {p.version === b.last_good && <span className={styles.tagGood}>last good</span>}
            </li>
          );
        })}
      </ol>
      <p className={styles.why}>{b.tested.find((t) => t.version === b.first_bad)?.detail ?? b.tested.find((t) => !t.good)?.detail}</p>
    </figure>
  );
}

export function Bisections({ report }: { report: Report }) {
  if (!report.bisections.length) return null;
  return (
    <section className={styles.section} aria-labelledby="bisect-title">
      <div className={styles.text}>
        <h2 id="bisect-title">The first release that broke it</h2>
        <p>Bisect holds every other pin fixed and searches the package's releases, so a finding arrives with the version to pin below and the change to read.</p>
      </div>
      <div className={styles.cards}>
        {report.bisections.map((b) => (
          <Ladder key={b.name} b={b} />
        ))}
      </div>
    </section>
  );
}
