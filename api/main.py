"""FastAPI service: pipeline artifacts, live sessions through the proxy, ledger and SSE (owner: P5).

Run: `python -m api` (or `uvicorn api.main:create_app --factory`). On startup it runs the
pipeline when `artifacts/policy.yaml` is missing, then serves one in-process proxy whose
decisions stream to the dashboard over `GET /events`.
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any, AsyncIterator

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from acc.pipeline import run_pipeline
from acc.reachability import prove, scripted_attack
from proxy.core import Proxy
from proxy.ledger import Ledger
from world.data import World

ROOT = Path(__file__).resolve().parents[1]


class SessionIn(BaseModel):
    ticket_id: str | None = None
    customer_id: str = "C-001"
    subject: str = "Support request"
    body: str = "Hi, can you resend my last invoice?"
    reporter_email: str | None = None


class CallIn(BaseModel):
    tool: str
    args: dict[str, Any] = {}


class ApprovalIn(BaseModel):
    approver: str
    approve: bool


class TamperIn(BaseModel):
    index: int = 0


class State:
    def __init__(self, artifacts_dir: Path, world_dir: Path, seed: int) -> None:
        self.artifacts_dir, self.world_dir, self.seed = artifacts_dir, world_dir, seed
        if not (artifacts_dir / "policy.yaml").exists():
            run_pipeline(world_dir, artifacts_dir, seed=seed)
        self.reset()

    def reset(self) -> None:
        self.policy = yaml.safe_load((self.artifacts_dir / "policy.yaml").read_text(encoding="utf-8"))
        self.catalog = json.loads((self.artifacts_dir / "catalog.json").read_text(encoding="utf-8"))
        self.world = World(seed=self.seed)
        ledger_path = self.artifacts_dir / "live" / "ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text("", encoding="utf-8")  # a fresh audit log per server start
        self.proxy = Proxy(self.world, self.world.service_key, self.policy, Ledger(ledger_path))

    def artifact_names(self) -> list[str]:
        root = self.artifacts_dir
        names = [p.name for p in root.iterdir() if p.is_file()]
        names += [f"export/{p.name}" for p in (root / "export").glob("*") if p.is_file()]
        return sorted(names)


def create_app(artifacts_dir: str | Path = ROOT / "artifacts", world_dir: str | Path = ROOT / "world",
               seed: int = 26) -> FastAPI:
    state = State(Path(artifacts_dir), Path(world_dir), seed)
    app = FastAPI(title="AgentChainCut API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.state.acc = state

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "policy": state.policy["solver"], "sessions": len(state.proxy.sessions)}

    # -- artifacts -----------------------------------------------------------------------------

    @app.get("/artifacts")
    def artifacts() -> list[str]:
        return state.artifact_names()

    @app.get("/artifacts/{name:path}")
    def artifact(name: str) -> Any:
        if name not in state.artifact_names():  # also rules out path traversal
            raise HTTPException(404, f"unknown artifact {name}")
        path = state.artifacts_dir / name
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            return json.loads(text)
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        if path.suffix in (".yaml", ".yml"):
            return yaml.safe_load(text)
        return PlainTextResponse(text)

    @app.post("/pipeline/run")
    def pipeline_run() -> dict[str, Any]:
        summary = run_pipeline(state.world_dir, state.artifacts_dir, seed=state.seed)
        state.reset()
        return summary

    # -- live sessions through the proxy ------------------------------------------------------

    @app.post("/live/sessions")
    def start_session(body: SessionIn) -> dict[str, Any]:
        ticket_id = body.ticket_id
        if ticket_id is None:
            if body.customer_id not in state.world.customers:
                raise HTTPException(404, f"unknown customer {body.customer_id}")
            ticket_id = state.world.open_ticket(body.customer_id, body.subject, body.body, body.reporter_email).id
        try:
            sid = state.proxy.start_session(ticket_id)
        except Exception as exc:
            raise HTTPException(404, str(exc)) from None
        return {"session_id": sid, "ticket_id": ticket_id, "context": state.proxy.sessions[sid]}

    @app.post("/live/sessions/{session_id}/calls")
    async def call(session_id: str, body: CallIn) -> dict[str, Any]:
        return await state.proxy.call(session_id, body.tool, body.args)

    @app.get("/live/approvals")
    def approvals() -> list[dict[str, Any]]:
        return [{"approval_id": k, **v} for k, v in state.proxy.pending.items()]

    @app.post("/live/approvals/{approval_id}")
    async def decide(approval_id: str, body: ApprovalIn) -> dict[str, Any]:
        try:
            if body.approve:
                return await state.proxy.approve(approval_id, body.approver)
            return await state.proxy.reject(approval_id, body.approver)
        except KeyError:
            raise HTTPException(404, f"unknown or already decided approval {approval_id}") from None

    @app.post("/live/attack")
    async def attack() -> dict[str, Any]:
        """Same poisoned ticket against the unprotected backend and through the proxy."""
        customers = sorted(state.world.customers)
        victim, attacker = customers[-1], customers[-2]

        replay = World(seed=state.seed)
        unprotected_attack = scripted_attack(replay, victim_id=victim, attacker_customer_id=attacker)
        before = prove(replay, state.catalog, unprotected_attack, policy=None)

        live = scripted_attack(state.world, victim_id=victim, attacker_customer_id=attacker)
        sid = state.proxy.start_session(live["ticket_id"])
        outbox_before = len(state.world.outbox)
        steps, allowed = [], True
        for c in live["calls"]:
            out = await state.proxy.call(sid, c["tool"], c["args"])
            steps.append({"tool": c["tool"], **{k: out[k] for k in ("decision", "rule", "reason")}})
            if out["decision"] != "allow":
                allowed = False
                break
        leaked_live = any(m["to"] == "attacker@evil.test" for m in state.world.outbox[outbox_before:])
        return {
            "ticket": state.world.get_ticket(live["ticket_id"])["body"],
            "unprotected": {**before, "leaked": any(m["to"] == "attacker@evil.test" for m in replay.outbox)},
            "protected": {"result": {**before["result"], "allowed": allowed}, "steps": steps,
                          "session_id": sid, "leaked": leaked_live},
        }

    # -- ledger -------------------------------------------------------------------------------

    @app.get("/ledger")
    def ledger() -> list[dict[str, Any]]:
        return state.proxy.ledger.entries

    @app.get("/ledger/verify")
    def ledger_verify() -> dict[str, Any]:
        bad = state.proxy.ledger.verify()
        return {"intact": bad is None, "first_bad_index": bad, "entries": len(state.proxy.ledger.entries)}

    @app.post("/ledger/tamper")
    def ledger_tamper(body: TamperIn) -> dict[str, Any]:
        """Demo only: edit one in-memory entry (the file on disk is untouched) to show detection."""
        entries = state.proxy.ledger.entries
        if not 0 <= body.index < len(entries):
            raise HTTPException(404, "no such ledger entry")
        entry = entries[body.index]
        entry["decision"] = "allow" if entry["decision"] != "allow" else "deny"
        return ledger_verify()

    @app.post("/ledger/restore")
    def ledger_restore() -> dict[str, Any]:
        state.proxy.ledger.entries = Ledger.load(state.proxy.ledger.path).entries
        return ledger_verify()

    # -- server-sent events -------------------------------------------------------------------

    @app.get("/events")
    async def events(max_events: int | None = None) -> StreamingResponse:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for entry in state.proxy.ledger.entries:  # backfill so a fresh dashboard shows history
            queue.put_nowait({"type": "decision", "tool": entry["tool"], "entry": copy.deepcopy(entry), "backfill": True})
        unsubscribe = state.proxy.subscribe(queue.put_nowait)

        async def stream() -> AsyncIterator[str]:
            sent = 0
            try:
                while max_events is None or sent < max_events:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    yield f"data: {json.dumps(event)}\n\n"
                    sent += 1
            finally:
                unsubscribe()

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
