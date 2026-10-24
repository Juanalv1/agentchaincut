"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ToolGraph } from "@/components/ToolGraph";
import { API_URL, api, loadSnapshot } from "@/lib/data";
import { verifyChain } from "@/lib/ledger";
import type { Attack, BenchRow, LedgerEntry, Snapshot, Step } from "@/lib/types";

const LIVE = API_URL !== "";

function pct(count: number, n: number): string {
  return n ? `${((100 * count) / n).toFixed(1)}%` : "n/a";
}

function StepList({ steps }: { steps: Step[] }) {
  return (
    <ol className="steps">
      {steps.map((s, i) => (
        <li key={`${s.tool}-${i}`}>
          <span className="chip" data-d={s.decision}>{s.decision}</span>
          <span>
            <code>{s.tool}</code>
            {s.reason && <span className="note"> — {s.rule ? `${s.rule}: ` : ""}{s.reason}</span>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function AttackSplit({ attack }: { attack: Attack }) {
  return (
    <div className="split">
      <div className="panel" data-tone={attack.unprotected.leaked ? "bad" : "good"}>
        <span className="label">Unprotected · broad backend credential</span>
        <span className="verdict" data-tone={attack.unprotected.leaked ? "bad" : "good"}>
          {attack.unprotected.leaked ? "Another customer's invoice reached attacker@evil.test" : "Nothing left"}
        </span>
        <StepList steps={attack.unprotected.steps} />
      </div>
      <div className="panel" data-tone={attack.protected.leaked ? "bad" : "good"}>
        <span className="label">Through the AgentChainCut proxy</span>
        <span className="verdict" data-tone={attack.protected.leaked ? "bad" : "good"}>
          {attack.protected.leaked ? "Leaked" : "Refused at the first cross-tenant call"}
        </span>
        <StepList steps={attack.protected.steps} />
      </div>
    </div>
  );
}

function ResultsTable({ rows }: { rows: BenchRow[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Defense</th>
            <th>Attack success ↓</th>
            <th>Utility ↑</th>
            <th>False denies ↓</th>
            <th>Label</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.name} data-ours={r.name === "AgentChainCut"}>
              <td>{r.name}</td>
              {r.attack_success && r.utility && r.false_deny ? (
                <>
                  <td className="num">{pct(r.attack_success.count, r.attack_success.n)} ({r.attack_success.count}/{r.attack_success.n})</td>
                  <td className="num">{pct(r.utility.pass, r.utility.n)} ({r.utility.pass}/{r.utility.n})</td>
                  <td className="num">{pct(r.false_deny.count, r.false_deny.n)} ({r.false_deny.count}/{r.false_deny.n})</td>
                </>
              ) : (
                <td colSpan={3} className="note">not measured yet</td>
              )}
              <td className="num">{r.label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [after, setAfter] = useState(false);
  const [attack, setAttack] = useState<Attack | null>(null);
  const [running, setRunning] = useState(false);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [broken, setBroken] = useState<number | null>(null);
  const [tab, setTab] = useState<"hook" | "progent" | "assay">("hook");

  useEffect(() => {
    loadSnapshot()
      .then((snap) => {
        setData(snap);
        setAttack(snap.live.attack);
        if (!LIVE) setLedger(snap.live.ledger);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  // Live mode: stream decisions from the proxy over SSE.
  useEffect(() => {
    if (!LIVE) return;
    const source = new EventSource(`${API_URL}/events`);
    source.onmessage = (event) => {
      const payload = JSON.parse(event.data) as { type: string; entry?: LedgerEntry };
      if (payload.type === "decision" && payload.entry) {
        const entry = payload.entry;
        setLedger((prev) => (prev.some((e) => e.seq === entry.seq) ? prev : [...prev, entry]));
      }
    };
    return () => source.close();
  }, []);

  useEffect(() => {
    verifyChain(ledger).then(setBroken);
  }, [ledger]);

  const runAttack = useCallback(async () => {
    if (!LIVE) return;
    setRunning(true);
    try {
      setAttack(await api<Attack>("/live/attack", { method: "POST" }));
    } finally {
      setRunning(false);
    }
  }, []);

  const tamper = useCallback(async () => {
    if (LIVE) {
      await api("/ledger/tamper", { method: "POST", body: JSON.stringify({ index: 0 }) });
      setLedger(await api<LedgerEntry[]>("/ledger"));
      return;
    }
    setLedger((prev) =>
      prev.map((e, i) => (i === 0 ? { ...e, decision: e.decision === "allow" ? "deny" : "allow" } : e)),
    );
  }, []);

  const restore = useCallback(async () => {
    if (LIVE) {
      await api("/ledger/restore", { method: "POST" });
      setLedger(await api<LedgerEntry[]>("/ledger"));
    } else if (data) {
      setLedger(data.live.ledger);
    }
  }, [data]);

  const cutAt = useMemo(
    () => attack?.protected.steps.find((s) => s.decision !== "allow")?.tool,
    [attack],
  );

  if (error) {
    return (
      <main className="wrap hero">
        <h1>Snapshot missing</h1>
        <p className="lede">Run <code>npm run sync</code> after <code>acc run world/</code>. ({error})</p>
      </main>
    );
  }
  if (!data || !attack) {
    return <main className="wrap hero"><p className="note">Loading artifacts…</p></main>;
  }

  const { catalog, invariants, policy, verify, details, bench } = data;
  const tools = policy.agents[0].tools;
  const accepted = invariants.filter((i) => i.status !== "rejected");
  const rejected = invariants.filter((i) => i.status === "rejected");
  const progentJson = JSON.stringify(data.progent, null, 2);

  return (
    <>
      <nav className="nav">
        <div className="wrap nav-inner">
          <a className="wordmark" href="#top">AgentChainCut</a>
          <div className="nav-links">
            <a href="#map">Map</a>
            <a href="#rules">Rules</a>
            <a href="#solver">Solver</a>
            <a href="#verify">Verify</a>
            <a href="#ledger">Ledger</a>
            <a href="#results">Results</a>
            <a href="#exports">Exports</a>
          </div>
          <span className="mode" data-live={LIVE} title={LIVE ? "Streaming from the proxy API" : "Recorded run from the artifact snapshot"}>{LIVE ? "live" : "replay"}</span>
        </div>
      </nav>

      <main id="top">
        <section className="hero">
          <div className="wrap">
            <div className="hero-grid">
              <div className="head">
                <span className="label">Ticket → invoice → email</span>
                <h1>Least privilege, computed and proven.</h1>
              </div>
              <p className="lede">
                One poisoned support ticket, two agents with the same model and the same job. The only difference is
                the permission layer: a policy mined from legitimate traces, optimized with CP-SAT and enforced by a
                proxy that holds the credentials.
              </p>
            </div>
            <pre className="ticket" aria-label="Poisoned ticket">{attack.ticket}</pre>
            <AttackSplit attack={attack} />
            {LIVE && (
              <p style={{ marginTop: "var(--space-md)" }}>
                <button className="btn primary" onClick={runAttack} disabled={running} data-state={running ? "loading" : undefined}>
                  {running ? "Running…" : "Run the attack again"}
                </button>
              </p>
            )}
          </div>
        </section>

        <section id="map">
          <div className="wrap">
            <div className="map-bar">
              <div className="head" style={{ marginBottom: 0 }}>
                <span className="label">Reachability proof</span>
                <h2>Untrusted → sensitive → sink.</h2>
              </div>
              <div className="seg" role="group" aria-label="Policy view">
                <button aria-pressed={!after} onClick={() => setAfter(false)}>Before</button>
                <button aria-pressed={after} onClick={() => setAfter(true)}>After policy</button>
              </div>
            </div>
            <ToolGraph catalog={catalog} policy={policy} verify={verify} after={after} cutAt={cutAt} />
            <div className="legend">
              <span><span className="leg" data-on="true">U</span> untrusted input</span>
              <span><span className="leg" data-on="true">S</span> sensitive data</span>
              <span><span className="leg" data-on="true">X</span> external effect</span>
              <span>Path executed with scripted calls, no LLM: before = {String(verify.reachability_before.allowed)}, after = {String(verify.reachability_after?.allowed)}</span>
            </div>
          </div>
        </section>

        <section id="rules">
          <div className="wrap">
            <div className="head">
              <span className="label">Mined from {invariants[0]?.support ?? 0}+ legit calls</span>
              <h2>Rules that bind arguments to the session.</h2>
              <p>
                A candidate survives only with zero violations, at least five distinct values, a non-constant value and
                context fetched from the backend. Everything else stays visible with the reason it was rejected.
              </p>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>Id</th><th>Rule</th><th>Support</th><th>Distinct</th><th>Violations</th><th>Status</th></tr>
                </thead>
                <tbody>
                  {[...accepted, ...rejected].map((inv) => (
                    <tr key={inv.id}>
                      <td className="num">{inv.id}</td>
                      <td>
                        <code className={inv.status === "rejected" ? "struck" : undefined}>
                          {inv.tool}.{inv.arg} {inv.op === "eq" ? "==" : "∈"} {inv.ctx_path}
                        </code>
                        {inv.note && <div className="note">{inv.note}</div>}
                      </td>
                      <td className="num">{inv.support}</td>
                      <td className="num">{inv.distinct}</td>
                      <td className="num">{inv.violations}</td>
                      <td>
                        <span className="chip" data-d={inv.status === "rejected" ? "deny" : "allow"}>
                          {inv.status === "rejected" ? inv.reject_reason : inv.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>

        <section id="solver">
          <div className="wrap">
            <div className="head">
              <span className="label">OR-Tools CP-SAT · Rule of Two</span>
              <h2>{policy.solver.broken_tasks.length} legitimate tasks broken. {policy.conflicts.length} conflict explained.</h2>
            </div>
            <div className="facts">
              <div className="fact"><strong>{policy.solver.status}</strong><span>solver status ({policy.solver.method})</span></div>
              <div className="fact"><strong>{policy.solver.objective}</strong><span>objective (least-privilege cost)</span></div>
              <div className="fact"><strong>{Object.values(tools).filter((t) => t.mode === "scoped").length}</strong><span>tools scoped by a rule</span></div>
              <div className="fact"><strong>{Object.values(tools).filter((t) => t.mode === "deny").length}</strong><span>tools denied outright</span></div>
            </div>
            <div className="two">
              <div className="table-wrap">
                <table>
                  <thead><tr><th>Tool</th><th>Mode</th><th>Bound by</th></tr></thead>
                  <tbody>
                    {Object.entries(tools).map(([name, rule]) => (
                      <tr key={name}>
                        <td><code>{name}</code></td>
                        <td><span className="chip" data-d={rule.mode === "deny" ? "deny" : rule.mode === "approval" ? "approval" : "allow"}>{rule.mode}</span></td>
                        <td className="note">{rule.constraints?.map((c) => `${c.arg} ${c.op === "eq" ? "==" : "∈"} ${c.ctx}`).join(" · ") ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {policy.conflicts.map((c) => (
                <div className="panel" key={c.task}>
                  <span className="label">Conflict · minimal unsat core</span>
                  <h3><code>{c.task}</code> needs {c.legs.join(" + ")}</h3>
                  <p>
                    Core: <code>{c.core.join(", ")}</code>. The refund amount cannot be bound to the session, so the
                    external-effect leg stays open unless a human approves.
                  </p>
                  <ul className="steps">
                    {c.fixes.map((f) => (
                      <li key={f.type}>
                        <span className="chip" data-d={c.resolved_by === f.type ? "allow" : "skipped"}>
                          {c.resolved_by === f.type ? "applied" : "option"}
                        </span>
                        <span>
                          {f.type === "approval_edge"
                            ? <>Human approval on <code>{f.tool}</code></>
                            : <>Split the agent: {f.partition?.map((p) => `[${p.join(", ")}]`).join(" + ")}</>}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="verify">
          <div className="wrap">
            <div className="head">
              <span className="label">Held-out customers the miner never saw · {verify.labels.heldout}</span>
              <h2>New work passes. Attacks do not.</h2>
            </div>
            <div className="facts">
              <div className="fact"><strong>{verify.heldout.pass}/{verify.heldout.n}</strong><span>legit sessions pass</span></div>
              <div className="fact"><strong>{verify.abuse.blocked}/{verify.abuse.n}</strong><span>attacks blocked</span></div>
              <div className="fact"><strong>{verify.false_deny.count}/{verify.false_deny.n}</strong><span>false denies</span></div>
            </div>
            <div className="two">
              <div className="bars" aria-label="Blocked attacks by family">
                {Object.entries(details.abuse_by_family).map(([family, c]) => (
                  <div className="bar" key={family}>
                    <code>{family}</code>
                    <span className="bar-track" aria-hidden="true">
                      <span className="bar-fill" style={{ width: `${(100 * c.denied) / c.n}%` }} />
                      <span className="bar-fill held" style={{ width: `${(100 * c.held_for_approval) / c.n}%` }} />
                    </span>
                    <span className="num">{c.blocked}/{c.n}{c.held_for_approval ? " (human)" : ""}</span>
                  </div>
                ))}
              </div>
              <div>
                <h3 style={{ marginBottom: "var(--space-sm)" }}>Residual risk · lower bound</h3>
                <ul className="steps">
                  {verify.residual.map((r) => (
                    <li key={`${r.sink}.${r.arg}`}>
                      <span className="chip" data-d={r.status === "approval" ? "approval" : "skipped"}>{r.status}</span>
                      <code>{r.sink}.{r.arg}</code>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </section>

        <section id="ledger" className="band">
          <div className="wrap">
            <div className="head">
              <span className="label">{LIVE ? "Streaming from the proxy" : "Recorded proxy run"} · sha256(prev + canonical_json(entry))</span>
              <h2>Every decision, chained.</h2>
            </div>
            <div className="chain-state">
              <span className="chain" data-intact={broken === null}>
                {broken === null ? `chain intact · ${ledger.length} entries` : `chain broken at entry ${broken + 1}`}
              </span>
              <button className="btn danger" onClick={tamper} disabled={!ledger.length}>Tamper with entry 1</button>
              <button className="btn" onClick={restore}>Restore</button>
            </div>
            <ol className="ledger">
              {ledger.map((e, i) => (
                <li key={`${e.seq}-${i}`} data-broken={broken !== null && i >= broken}>
                  <span>#{e.seq}</span>
                  <span>{e.tool}</span>
                  <span><span className="chip" data-d={e.decision}>{e.decision}</span></span>
                  <span className="reason">{e.rule ?? "—"}: {e.reason}</span>
                  <span className="hash" title={e.hash}>{e.hash}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="results">
          <div className="wrap">
            <div className="head">
              <span className="label">Cross-tenant benchmark · same harness for every defense</span>
              <h2>Where static rules cannot follow the session.</h2>
              <p>Attack success counts a malicious call allowed automatically; utility counts legit sessions with no denied call. Every cell carries its n.</p>
            </div>
            <ResultsTable rows={bench.heldout_full} />
            <h3 style={{ margin: "var(--space-xl) 0 var(--space-sm)" }}>Stratified sample with the LLM-written policy</h3>
            <ResultsTable rows={bench.llm_sample} />
            <p className="note" style={{ marginTop: "var(--space-md)" }}>
              Declared limits: free-form SQL arguments, server-side bugs, residual channels above, and a synthetic world
              modeled on real API schemas.
            </p>
          </div>
        </section>

        <section id="exports">
          <div className="wrap">
            <div className="head">
              <span className="label">Same policy, existing enforcers</span>
              <h2>Exports.</h2>
            </div>
            <div className="tabs" role="tablist">
              {(["hook", "progent", "assay"] as const).map((t) => (
                <button key={t} role="tab" aria-selected={tab === t} className={`btn${tab === t ? " primary" : ""}`} onClick={() => setTab(t)}>
                  {t === "hook" ? "Claude Code hook" : t === "progent" ? "Progent-style JSON" : "Assay-style YAML"}
                </button>
              ))}
            </div>
            <figure style={{ margin: 0 }}>
              <pre className="code">{tab === "hook" ? data.hook : tab === "progent" ? progentJson : data.assay}</pre>
            </figure>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap">AgentChainCut · Platanus Hack 26 Caracas · team 21 · other teams build smarter guards; we build better locks and prove they fit.</div>
      </footer>
    </>
  );
}
