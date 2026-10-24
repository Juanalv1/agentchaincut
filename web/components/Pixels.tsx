import type { Copy } from "@/lib/i18n";

const P = "#E53AA3";
const Y = "#FFDC00";

/** Paint a pixel grid from ASCII rows; unknown chars are transparent. */
function Paint({ rows, map, size, className }: { rows: string[]; map: Record<string, string>; size: number; className?: string }) {
  const cells = rows.join("").split("");
  return (
    <div className={`px-grid${className ? ` ${className}` : ""}`} style={{ gridTemplateColumns: `repeat(${rows[0].length}, ${size}px)` }} aria-hidden="true">
      {cells.map((ch, i) => (
        <span key={i} style={{ width: size, height: size, background: map[ch] ?? "transparent" }} />
      ))}
    </div>
  );
}

const MASCOT = ["...........", "..XXXXXXX..", "..X.XXX.X..", "XXXXXXXXXXX", "XXXXXXXXXXX", "..XXXXXXX..", "..X.X.X.X..", "..X.X.X.X.."];
const KEEPER = ["..WWWWW..", ".WWWWWWW.", ".WVVVVVW.", ".WWWWWWW.", "...WWW...", ".GWWWWWG.", ".GWWWWWG.", "..WW.WW..", "..GG.GG.."];
const KEY = [".PP......", "P..PPPPPP", "P..P..P.P", ".PP......"];

export function HeroScene({ t }: { t: Copy }) {
  return (
    <div className="scene">
      <div className="figure">
        <div className="cage" role="img" aria-label={t.cageAria}>
          <Paint rows={MASCOT} map={{ X: "#D97757" }} size={14} className="float" />
          {[36, 74, 112, 150, 188].map((left) => (
            <span key={left} className="bar-v" style={{ left }} aria-hidden="true" />
          ))}
          <span className="lock" aria-hidden="true" />
        </div>
        <span className="figure-label" style={{ color: "#D97757" }}>{t.cageLabel.toUpperCase()}</span>
      </div>
      <div className="figure">
        <div className="keeper" role="img" aria-label={t.keeperAria}>
          <Paint rows={KEEPER} map={{ W: "#E5E5E5", V: P, G: "#737373" }} size={14} />
          <Paint rows={KEY} map={{ P }} size={10} className="float fast" />
        </div>
        <span className="figure-label" style={{ color: "#E5E5E5" }}>{t.keeperLabel.toUpperCase()}</span>
      </div>
    </div>
  );
}

function Arc({ marks }: { marks: Record<number, string> }) {
  return (
    <div className="arc">
      {Array.from({ length: 36 }, (_, i) => (
        <span key={i} style={{ background: marks[i] ?? "#0D0D0D" }} />
      ))}
    </div>
  );
}

const PAIRS: { input: Record<number, string>; output: Record<number, string>; who?: string }[] = [
  { input: { 7: P, 8: P }, output: { 7: P, 8: P }, who: "A" },
  { input: { 21: P, 27: P }, output: { 21: P, 27: P }, who: "B" },
  { input: { 16: P, 17: P, 22: P }, output: { 16: P, 17: P, 22: P }, who: "C" },
  { input: { 7: P, 8: P }, output: { 28: Y, 29: Y, 34: Y } },
];

export function ArcPairs({ t }: { t: Copy }) {
  return (
    <div className="pairs" role="img" aria-label={t.pairsAria}>
      {PAIRS.map((p, i) => (
        <div className="pair" key={i} data-test={!p.who} aria-hidden="true">
          <span className="pair-label">{(p.who ? t.example(i + 1) : t.testAttack).toUpperCase()}</span>
          <div className="pair-io">
            <Arc marks={p.input} />
            <span className="arrow">→</span>
            <Arc marks={p.output} />
          </div>
          <span className="pair-caption">{p.who ? t.pairCaption(p.who) : t.pairAttackCaption}</span>
        </div>
      ))}
    </div>
  );
}

export function Blocks({ pct }: { pct: number }) {
  const on = Math.round(pct / 5);
  return (
    <div className="blocks" aria-hidden="true">
      {Array.from({ length: 20 }, (_, i) => (
        <span key={i} data-on={i < on} />
      ))}
    </div>
  );
}

export function LogoPixels() {
  return (
    <span className="logo-px" aria-hidden="true">
      <span style={{ background: P }} />
      <span style={{ background: Y }} />
      <span style={{ background: Y }} />
      <span style={{ background: P }} />
    </span>
  );
}
