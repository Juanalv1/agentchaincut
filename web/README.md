# AgentChainCut dashboard

Next.js 16 + React Flow, exported as a static site.

```bash
npm install
npm run sync      # copy artifacts + eval results + a recorded proxy run into public/demo
npm run build     # static export in out/
npx serve out     # replay mode (works offline from the snapshot)
```

Live mode: run the API (`python -m api` from the repo root) and build with
`NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build`. The ledger then streams over SSE and
"Run the attack again" / "Tamper" call the proxy. In replay mode the hash chain is re-verified
in the browser (WebCrypto SHA-256 over the same canonical JSON as the Python ledger).
