import type { LedgerEntry } from "./types";

export const GENESIS = "0".repeat(64);

/** Same bytes as Python json.dumps(obj, sort_keys=True, separators=(",", ":")) for ASCII data. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  const obj = value as Record<string, unknown>;
  return `{${Object.keys(obj)
    .sort()
    .map((k) => `${JSON.stringify(k)}:${canonicalJson(obj[k])}`)
    .join(",")}}`;
}

async function sha256Hex(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Index of the first entry that breaks the chain, or null when intact. */
export async function verifyChain(entries: LedgerEntry[]): Promise<number | null> {
  let prev = GENESIS;
  for (let i = 0; i < entries.length; i++) {
    const { hash, ...body } = entries[i];
    if (body.prev !== prev || hash !== (await sha256Hex(prev + canonicalJson(body)))) return i;
    prev = hash;
  }
  return null;
}
