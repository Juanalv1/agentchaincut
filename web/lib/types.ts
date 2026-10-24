export type Legs = { U: boolean; S: boolean; X: boolean };
export type Tool = {
  tool: string;
  server: string;
  description: string;
  args: { name: string; type: string; role: string }[];
  legs: Legs;
  source: string;
  rationale: string;
};
export type Invariant = {
  id: string;
  tool: string;
  arg: string;
  op: "eq" | "in";
  ctx_path: string;
  support: number;
  distinct: number;
  violations: number;
  status: "accepted" | "rejected" | "suggested";
  reject_reason?: string;
  note?: string;
};
export type Constraint = { arg: string; op: "eq" | "in"; ctx: string; invariant?: string };
export type Rule = { mode: "allow" | "scoped" | "approval" | "deny"; constraints?: Constraint[] };
export type Conflict = {
  task: string;
  legs: string[];
  core: string[];
  fixes: { type: string; tool?: string; partition?: string[][] }[];
  resolved_by?: string;
};
export type Policy = {
  agents: { name: string; tools: Record<string, Rule> }[];
  legs_per_session: Record<"U" | "S" | "X", boolean | "bounded">;
  solver: { status: string; method?: string; objective: number; broken_tasks: string[] };
  conflicts: Conflict[];
};
export type Path = { path: string[]; legs: string[]; allowed?: boolean };
export type Verify = {
  reachability_before: Path;
  reachability_after?: Path;
  heldout: { n: number; pass: number };
  abuse: { n: number; blocked: number };
  false_deny: { n: number; count: number };
  residual: { sink: string; arg: string; status: string; claim: string }[];
  labels: Record<string, string>;
};
export type VerifyDetails = {
  abuse_by_family: Record<string, { n: number; blocked: number; denied: number; held_for_approval: number }>;
};
export type LedgerEntry = {
  seq: number;
  ts: string;
  session_id: string;
  tool: string;
  args_hash: string;
  decision: "allow" | "deny" | "approval";
  rule: string | null;
  reason: string;
  prev: string;
  hash: string;
};
export type Step = { tool: string; decision: string; rule: string | null; reason: string };
export type Attack = {
  ticket: string;
  unprotected: { result: Path; steps: Step[]; leaked: boolean };
  protected: { result: Path; steps: Step[]; leaked: boolean; session_id?: string };
};
export type BenchRow = {
  name: string;
  label: string;
  attack_success?: { n: number; count: number };
  utility?: { n: number; pass: number };
  false_deny?: { n: number; count: number };
  attack_success_by_family?: Record<string, number>;
  family_n?: Record<string, number>;
  policy_variance?: { runs: number; sessions: number; sessions_with_differing_policies: number };
};
export type Bench = { heldout_full: BenchRow[]; llm_sample: BenchRow[] };
export type AgentDojoSuite = {
  suite: string;
  utility_n: number;
  utility_lenient: number;
  utility_strict: number;
  attacks_n: number;
  attacks_succeeded: number;
  attacks_held: number;
};
export type AgentDojo = { benchmark: string; method: string; suites: AgentDojoSuite[]; total: Omit<AgentDojoSuite, "suite"> };
export type Snapshot = {
  catalog: Tool[];
  invariants: Invariant[];
  policy: Policy;
  verify: Verify;
  details: VerifyDetails;
  bench: Bench;
  agentdojo: AgentDojo;
  live: { attack: Attack; ledger: LedgerEntry[] };
  hook: string;
  assay: string;
  progent: { session_id: string; note: string; policy: unknown };
};
