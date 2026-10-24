import type { Snapshot } from "./types";

/** Live mode when NEXT_PUBLIC_API_URL points at `python -m api`; otherwise offline replay. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "";

async function json<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}

async function text(path: string): Promise<string> {
  const res = await fetch(path);
  return res.ok ? res.text() : "";
}

export async function loadSnapshot(): Promise<Snapshot> {
  const base = "/demo";
  const [catalog, invariants, policy, verify, details, bench, live, hook, assay, progent, agentdojo] = await Promise.all([
    json<Snapshot["catalog"]>(`${base}/catalog.json`),
    json<Snapshot["invariants"]>(`${base}/invariants.json`),
    json<Snapshot["policy"]>(`${base}/policy.json`),
    json<Snapshot["verify"]>(`${base}/verify.json`),
    json<Snapshot["details"]>(`${base}/verify_details.json`),
    json<Snapshot["bench"]>(`${base}/crosstenant.json`),
    json<Snapshot["live"]>(`${base}/live.json`),
    text(`${base}/acc_hook.py.txt`),
    text(`${base}/assay.yaml`),
    json<Snapshot["progent"]>(`${base}/progent.json`),
    json<Snapshot["agentdojo"]>(`${base}/agentdojo.json`),
  ]);
  return { catalog, invariants, policy, verify, details, bench, live, hook, assay, progent, agentdojo };
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json() as Promise<T>;
}
