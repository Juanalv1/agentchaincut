"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { OfficeFloor } from "@/components/OfficeFloor";
import { ToolGraph } from "@/components/ToolGraph";
import { ArcPairs, Blocks, HeroScene, LogoPixels } from "@/components/Pixels";
import { API_URL, api, loadSnapshot } from "@/lib/data";
import { verifyChain } from "@/lib/ledger";
import { COPY, type Copy, type Lang } from "@/lib/i18n";
import type { Attack, BenchRow, LedgerEntry, Snapshot, Step } from "@/lib/types";

const LIVE = API_URL !== "";
/** Held-out customers in the verify split (not exported in the snapshot). */
const HELDOUT_CUSTOMERS = 80;

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

function AttackSplit({ attack, t }: { attack: Attack; t: Copy }) {
  return (
    <div className="split">
      <div className="panel" data-tone={attack.unprotected.leaked ? "bad" : "good"}>
        <span className="label">{t.unprotected}</span>
        <span className="verdict" data-tone={attack.unprotected.leaked ? "bad" : "good"}>
          {attack.unprotected.leaked ? t.leakedVerdict : t.nothingLeft}
        </span>
        <StepList steps={attack.unprotected.steps} />
      </div>
      <div className="panel" data-tone={attack.protected.leaked ? "bad" : "good"}>
        <span className="label">{t.throughProxy}</span>
        <span className="verdict" data-tone={attack.protected.leaked ? "bad" : "good"}>
          {attack.protected.leaked ? t.leaked : t.refusedFirst}
        </span>
        <StepList steps={attack.protected.steps} />
      </div>
    </div>
  );
}

function ResultsTable({ rows, t }: { rows: BenchRow[]; t: Copy }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>{t.thDefense}</th>
            <th>{t.thAttackSuccess}</th>
            <th>{t.thUtility}</th>
            <th>{t.thFalseDenies}</th>
            <th>{t.thLabel}</th>
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
                <td colSpan={3} className="note">{t.notMeasured}</td>
              )}
              <td className="num">{r.label}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Dashboard({ lang }: { lang: Lang }) {
  const t = COPY[lang];
  const [data, setData] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [after, setAfter] = useState(false);
  const [attack, setAttack] = useState<Attack | null>(null);
  const [running, setRunning] = useState(false);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [broken, setBroken] = useState<number | null>(null);
  const [tab, setTab] = useState<"hook" | "progent" | "assay">("hook");

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

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
        <h1 style={{ fontSize: 48 }}>{t.snapshotMissing}</h1>
        <p className="lede">{t.runSync} <code>npm run sync</code> {t.after} <code>acc run world/</code>. ({error})</p>
      </main>
    );
  }
  if (!data || !attack) {
    return <main className="wrap hero"><p className="note">{t.loading}</p></main>;
  }

  const { catalog, invariants, policy, verify, details, bench } = data;
  const tools = policy.agents[0].tools;
  const accepted = invariants.filter((i) => i.status !== "rejected");
  const rejected = invariants.filter((i) => i.status === "rejected");
  const progentJson = JSON.stringify(data.progent, null, 2);
  const legitSessions = Math.max(0, ...accepted.map((i) => i.support));
  const mailRule = accepted.find((i) => i.tool === "mail.send") ?? accepted[0];
  const leakPct = verify.abuse.n ? Math.round((100 * (verify.abuse.n - verify.abuse.blocked)) / verify.abuse.n) : 0;
  const cut = attack.ticket.indexOf("SYSTEM:");
  const ticketSafe = cut >= 0 ? attack.ticket.slice(0, cut) : attack.ticket;
  const ticketInjected = cut >= 0 ? attack.ticket.slice(cut) : "";
  const oursRow = (name: string) => name === "AgentChainCut";

  return (
    <>
      <nav className="nav">
        <div className="wrap nav-inner">
          <a className="wordmark" href="#top"><LogoPixels />AGENTCHAINCUT</a>
          <div className="nav-links">
            <a href="#attack">{t.nav.attack}</a>
            <a href="#pattern">{t.nav.pattern}</a>
            <a href="#proof">{t.nav.proof}</a>
            <a href="#map">{t.nav.map}</a>
            <a href="#solver">{t.nav.solver}</a>
            <a href="#verify">{t.nav.verify}</a>
            <a href="#ledger">{t.nav.ledger}</a>
            <a href="#results">{t.nav.results}</a>
            <a href="#exports">{t.nav.exports}</a>
            <a href={t.otherLangHref} hrefLang={lang === "en" ? "es" : "en"}>{t.otherLang}</a>
          </div>
          <span className="mode" data-live={LIVE} title={LIVE ? t.modeLiveTitle : t.modeReplayTitle}>{LIVE ? t.modeLive : t.modeReplay}</span>
        </div>
      </nav>

      <main id="top">
        <section className="hero">
          <div className="wrap">
            <p className="label">{t.heroLabel}</p>
            <h1>{t.heroTitleA}<br /><span className="dim">{t.heroTitleB}</span></h1>
            <p className="lede">{t.heroLede}</p>
            <HeroScene t={t} />
          </div>
        </section>

        <section id="attack">
          <div className="wrap">
            <div className="narrow">
              <p className="label">{t.attackLabel}</p>
              <h2 className="big">{t.attackTitle}</h2>
              <p className="lede">{t.attackBody}</p>
              <div className="ticket" aria-label={t.poisonedTicket}>
                <p className="note" style={{ marginBottom: 14, letterSpacing: "0.08em", textTransform: "uppercase" }}>{t.incomingTicket}</p>
                <p>
                  {ticketSafe}
                  {ticketInjected && <span className="inj">{ticketInjected}</span>}
                </p>
              </div>
            </div>
            <AttackSplit attack={attack} t={t} />
            {LIVE && (
              <p style={{ marginTop: 24 }}>
                <button className="btn primary" onClick={runAttack} disabled={running} data-state={running ? "loading" : undefined}>
                  {running ? t.running : t.runAgain}
                </button>
              </p>
            )}
          </div>
        </section>

        <section id="office">
          <div className="wrap">
            <div className="narrow">
              <p className="label">{t.officeLabel}</p>
              <h2 className="big">{t.officeTitle}</h2>
              <p className="lede">{t.officeBody}</p>
            </div>
            <OfficeFloor attack={attack} t={t} running={running} onRun={LIVE ? runAttack : undefined} />
          </div>
        </section>

        <section id="pattern">
          <div className="wrap">
            <div className="narrow">
              <p className="label">{t.patternLabel}</p>
              <h2 className="big">{t.patternTitleA}<br />{t.patternTitleB}</h2>
              <p className="lede">{t.patternBody(legitSessions)}</p>
            </div>
            <ArcPairs t={t} />
            {mailRule && (
              <p className="mono-line narrow mined">
                {t.minedRule} <span className="hl-y">{mailRule.tool}.{mailRule.arg} == {mailRule.ctx_path}</span>
              </p>
            )}
            <div id="rules" className="head" style={{ marginBottom: 24 }}>
              <p className="label plain">{t.rulesLabel(invariants[0]?.support ?? 0)}</p>
              <h3>{t.rulesTitle}</h3>
              <p>{t.rulesBody}</p>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>{t.thId}</th><th>{t.thRule}</th><th>{t.thSupport}</th><th>{t.thDistinct}</th><th>{t.thViolations}</th><th>{t.thStatus}</th></tr>
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

        <section id="proof" className="proof">
          <div className="wrap">
            <p className="label plain">{t.proofLabel}</p>
            <p className="zero">{leakPct}<span>%</span></p>
            <p className="lede">{t.proofBody(HELDOUT_CUSTOMERS, verify.abuse.n, verify.heldout.n)}</p>
            <div className="facts">
              <div className="fact"><strong>{verify.heldout.pass}<small>/{verify.heldout.n}</small></strong><span>{t.legitPass}</span></div>
              <div className="fact"><strong>{verify.abuse.blocked}<small>/{verify.abuse.n}</small></strong><span>{t.attacksBlocked}</span></div>
              <div className="fact"><strong>{verify.false_deny.count}</strong><span>{t.falseDenies}</span></div>
              <div className="fact"><strong>{policy.solver.status}</strong><span>{t.factSolver(policy.solver.broken_tasks.length)}</span></div>
            </div>
          </div>
        </section>

        <section id="map">
          <div className="wrap">
            <div className="map-bar">
              <div className="head" style={{ marginBottom: 0 }}>
                <p className="label">{t.mapLabel}</p>
                <h2>{t.mapTitle}</h2>
              </div>
              <div className="seg" role="group" aria-label={t.policyView}>
                <button type="button" aria-pressed={!after} onClick={() => setAfter(false)}>{t.before}</button>
                <button type="button" aria-pressed={after} onClick={() => setAfter(true)}>{t.afterPolicy}</button>
              </div>
            </div>
            <ToolGraph catalog={catalog} policy={policy} verify={verify} after={after} cutAt={cutAt} />
            <div className="legend">
              <span><span className="leg" data-on="true">U</span> {t.legU}</span>
              <span><span className="leg" data-on="true">S</span> {t.legS}</span>
              <span><span className="leg" data-on="true">X</span> {t.legX}</span>
              <span>{t.pathExecuted} {String(verify.reachability_before.allowed)}, {t.afterEq} {String(verify.reachability_after?.allowed)}</span>
            </div>
          </div>
        </section>

        <section id="solver">
          <div className="wrap">
            <div className="head">
              <p className="label">OR-Tools CP-SAT · Rule of Two</p>
              <h2>{t.solverTitle(policy.solver.broken_tasks.length, policy.conflicts.length)}</h2>
            </div>
            <div className="facts">
              <div className="fact"><strong>{policy.solver.status}</strong><span>{t.solverStatus} ({policy.solver.method})</span></div>
              <div className="fact"><strong>{policy.solver.objective}</strong><span>{t.objective}</span></div>
              <div className="fact"><strong>{Object.values(tools).filter((t) => t.mode === "scoped").length}</strong><span>{t.toolsScoped}</span></div>
              <div className="fact"><strong>{Object.values(tools).filter((t) => t.mode === "deny").length}</strong><span>{t.toolsDenied}</span></div>
            </div>
            <div className="two">
              <div className="table-wrap">
                <table>
                  <thead><tr><th>{t.thTool}</th><th>{t.thMode}</th><th>{t.thBoundBy}</th></tr></thead>
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
                  <span className="label">{t.conflictLabel}</span>
                  <h3><code>{c.task}</code> {t.needs} {c.legs.join(" + ")}</h3>
                  <p>
                    {t.core} <code>{c.core.join(", ")}</code>. {t.conflictBody}
                  </p>
                  <ul className="steps">
                    {c.fixes.map((f) => (
                      <li key={f.type}>
                        <span className="chip" data-d={c.resolved_by === f.type ? "allow" : "skipped"}>
                          {c.resolved_by === f.type ? t.applied : t.option}
                        </span>
                        <span>
                          {f.type === "approval_edge"
                            ? <>{t.humanApprovalOn} <code>{f.tool}</code></>
                            : <>{t.splitAgent} {f.partition?.map((p) => `[${p.join(", ")}]`).join(" + ")}</>}
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
              <p className="label">{t.verifyLabel} · {verify.labels.heldout}</p>
              <h2>{t.verifyTitle}</h2>
            </div>
            <div className="facts">
              <div className="fact"><strong>{verify.heldout.pass}/{verify.heldout.n}</strong><span>{t.legitPass}</span></div>
              <div className="fact"><strong>{verify.abuse.blocked}/{verify.abuse.n}</strong><span>{t.attacksBlocked}</span></div>
              <div className="fact"><strong>{verify.false_deny.count}/{verify.false_deny.n}</strong><span>{t.falseDenies}</span></div>
            </div>
            <div className="two">
              <div className="bars" aria-label={t.blockedByFamily}>
                {Object.entries(details.abuse_by_family).map(([family, c]) => (
                  <div className="bar" key={family}>
                    <code>{family}</code>
                    <span className="bar-track" aria-hidden="true">
                      <span className="bar-fill" style={{ width: `${(100 * c.denied) / c.n}%` }} />
                      <span className="bar-fill held" style={{ width: `${(100 * c.held_for_approval) / c.n}%` }} />
                    </span>
                    <span className="num">{c.blocked}/{c.n}{c.held_for_approval ? ` (${t.human})` : ""}</span>
                  </div>
                ))}
              </div>
              <div>
                <h3 style={{ marginBottom: "12px" }}>{t.residual}</h3>
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
              <p className="label">{LIVE ? t.ledgerLive : t.ledgerReplay} · sha256(prev + canonical_json(entry))</p>
              <h2>{t.ledgerTitle}</h2>
            </div>
            <div className="chain-state">
              <span className="chain" data-intact={broken === null}>
                {broken === null ? t.chainIntact(ledger.length) : t.chainBroken(broken + 1)}
              </span>
              <button className="btn danger" onClick={tamper} disabled={!ledger.length}>{t.tamper}</button>
              <button className="btn" onClick={restore}>{t.restore}</button>
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
              <p className="label">{t.benchLabel}</p>
              <h2>{t.benchTitle}</h2>
              <p>{t.benchBody}</p>
            </div>
            <div className="bench">
              {bench.heldout_full.filter((r) => r.attack_success).sort((x, y) => Number(oursRow(x.name)) - Number(oursRow(y.name))).map((r) => {
                const p = (100 * r.attack_success!.count) / r.attack_success!.n;
                const name = t.benchName(r.name);
                const value = `${p.toFixed(1)}%`;
                return (
                  <div className="bench-row" key={r.name} data-ours={oursRow(r.name)} role="img" aria-label={t.benchAria(name, value)}>
                    <span className="bench-name" aria-hidden="true">{name}</span>
                    <Blocks pct={p} />
                    <span className="bench-value" aria-hidden="true">{value}</span>
                  </div>
                );
              })}
            </div>
            <p className="note" style={{ margin: "40px 0 0" }}>
              {t.benchFoot(bench.heldout_full[0]?.attack_success?.n ?? verify.abuse.n, bench.heldout_full[0]?.utility?.n ?? verify.heldout.n)}
            </p>
            <p className="label plain" style={{ marginTop: 72 }}>{t.resultsLabel}</p>
            <h3 style={{ marginBottom: 12 }}>{t.resultsTitle}</h3>
            <p className="lede" style={{ margin: "0 0 24px" }}>{t.resultsBody}</p>
            <ResultsTable rows={bench.heldout_full} t={t} />
            <h3 className="sub-title">{t.llmSample}</h3>
            <ResultsTable rows={bench.llm_sample} t={t} />
            {data.liveSummary && (
              <>
                <h3 className="sub-title">{t.liveTitle}</h3>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr><th>{t.thModelAttack}</th><th>{t.thLiveUnprotected}</th><th>{t.thLiveProtected}</th><th>{t.thLiveReplied}</th></tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.liveSummary.models).sort().map(([key, s]) => (
                        <tr key={key} data-ours={(s.unprotected.read_foreign_invoice ?? 0) > 0}>
                          <td><code>{key.includes(":") ? key.replace(":", " · ") : `${key} · obvious`}</code></td>
                          <td className="num">{s.unprotected.read_foreign_invoice ?? "—"} · {s.unprotected.leaked} /{s.unprotected.n}</td>
                          <td className="num">{s.protected.read_foreign_invoice ?? "—"} · {s.protected.leaked} /{s.protected.n}</td>
                          <td className="num">{s.protected.answered_customer ?? s.protected.replied_to_customer ?? "—"}/{s.protected.n}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="note" style={{ marginTop: "12px" }}>{t.liveNote}</p>
              </>
            )}
            <h3 className="sub-title">{t.agentdojoTitle}</h3>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr><th>{t.thSuite}</th><th>{t.thAttacksAllowed}</th><th>{t.thHeld}</th><th>{t.thUtilityLenient}</th><th>{t.thUtilityStrict}</th></tr>
                </thead>
                <tbody>
                  {[...data.agentdojo.suites, { suite: "all", ...data.agentdojo.total }].map((s) => (
                    <tr key={s.suite} data-ours={s.suite === "all"}>
                      <td>{s.suite}</td>
                      <td className="num">{pct(s.attacks_succeeded, s.attacks_n)} ({s.attacks_succeeded}/{s.attacks_n})</td>
                      <td className="num">{pct(s.attacks_held, s.attacks_n)}</td>
                      <td className="num">{pct(s.utility_lenient, s.utility_n)} ({s.utility_lenient}/{s.utility_n})</td>
                      <td className="num">{pct(s.utility_strict, s.utility_n)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note" style={{ marginTop: "12px" }}>
              {t.agentdojoNote}
            </p>
            <p className="note" style={{ marginTop: "16px" }}>
              {t.limits}
            </p>
          </div>
        </section>

        <section id="exports">
          <div className="wrap">
            <div className="head">
              <p className="label">{t.exportsLabel}</p>
              <h2>{t.exportsTitle}</h2>
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
        <div className="wrap">{t.footer}</div>
      </footer>
    </>
  );
}
