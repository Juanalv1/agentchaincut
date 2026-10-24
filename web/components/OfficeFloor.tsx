"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Copy } from "@/lib/i18n";
import type { Attack, Step } from "@/lib/types";

type Mode = "unprotected" | "protected";

/** Department is the MCP server prefix of the tool (tickets.get → tickets). */
const DEPTS = ["tickets", "billing", "mail"] as const;
const STEP_MS = 1400;

function deptOf(tool: string): string {
  return tool.split(".")[0];
}

/**
 * Animated office floor: each MCP server is a department, the agent walks to the
 * department of every recorded tool call, and the proxy desk stamps the real decision.
 */
export function OfficeFloor({
  attack,
  t,
  onRun,
  running,
}: {
  attack: Attack;
  t: Copy;
  onRun?: () => Promise<void>;
  running: boolean;
}) {
  const [mode, setMode] = useState<Mode>("protected");
  const [shown, setShown] = useState(0);
  const timer = useRef<number | null>(null);
  const steps: Step[] = attack[mode].steps;

  const play = useCallback(() => {
    if (timer.current) window.clearInterval(timer.current);
    setShown(0);
    let i = 0;
    timer.current = window.setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= steps.length && timer.current) window.clearInterval(timer.current);
    }, STEP_MS);
  }, [steps]);

  useEffect(() => {
    play();
    return () => {
      if (timer.current) window.clearInterval(timer.current);
    };
  }, [play, attack]);

  const run = useCallback(async () => {
    if (onRun) await onRun();
    play();
  }, [onRun, play]);

  const current = shown > 0 ? steps[shown - 1] : null;
  const where = current ? deptOf(current.tool) : "lobby";
  const done = shown >= steps.length;
  const outcome = attack[mode].leaked ? "bad" : "good";

  return (
    <div className="office" data-mode={mode}>
      <div className="office-bar">
        <div className="office-tabs" role="tablist">
          {(["unprotected", "protected"] as Mode[]).map((m) => (
            <button key={m} role="tab" aria-selected={mode === m} className="tab" data-on={mode === m} onClick={() => setMode(m)}>
              {m === "unprotected" ? t.officeUnprotected : t.officeProtected}
            </button>
          ))}
        </div>
        <button className="btn primary" onClick={run} disabled={running} data-state={running ? "loading" : undefined}>
          {running ? t.running : t.officeRun}
        </button>
      </div>

      <div className="floor" aria-hidden="true">
        <div className="room lobby" data-active={where === "lobby"}>
          <span className="room-name">{t.officeLobby}</span>
        </div>
        {mode === "protected" && (
          <div className="desk" data-d={current?.decision}>
            <span className="room-name">{t.officeDesk}</span>
            {current && <span className="stamp" key={shown} data-d={current.decision}>{current.decision}</span>}
          </div>
        )}
        {DEPTS.map((d) => (
          <div key={d} className="room" data-dept={d} data-active={where === d}
            data-blocked={where === d && current?.decision === "deny"}>
            <span className="room-name">{t.officeDepts[d]}</span>
            <span className="room-server">{d}.*</span>
          </div>
        ))}
        <div className="agent" data-at={where} data-d={current?.decision}>
          <span className="agent-head" />
          <span className="agent-body" />
        </div>
      </div>

      <ol className="office-log">
        {steps.slice(0, shown).map((s, i) => (
          <li key={`${s.tool}-${i}`} className="log-line">
            <span className="chip" data-d={s.decision}>{s.decision}</span>
            <code>{t.officeDepts[deptOf(s.tool) as (typeof DEPTS)[number]] ?? deptOf(s.tool)} → {s.tool}</code>
            <span className="note"> — {s.rule ? `${s.rule}: ` : ""}{s.reason}</span>
          </li>
        ))}
        {!done && <li className="log-line cursor note">{t.officeWorking}</li>}
        {done && (
          <li className="log-line verdict" data-tone={outcome}>
            {attack[mode].leaked ? t.leakedVerdict : t.refusedFirst}
          </li>
        )}
      </ol>
    </div>
  );
}
