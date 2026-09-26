from __future__ import annotations

import asyncio
import logging
import os

from fastapi import FastAPI, Request, Header, HTTPException

from .commands import parse_command
from .config import load_config
from .github_client import GitHubClient
from .openclaw import OpenClawClient
from .orchestrator import Orchestrator
from .webhook import verify_signature

cfg = load_config()
gh = GitHubClient(os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPO", cfg.get("repo", "")))
oc = OpenClawClient(os.environ.get("OPSWARM_OPENCLAW_BIN", "openclaw"), int(os.environ.get("OPSWARM_OPENCLAW_TIMEOUT",
                                                                                           cfg.get("openclaw", {}).get(
                                                                                               "timeout_seconds",
                                                                                               600))))
engine = Orchestrator(cfg, gh, oc, os.environ.get("OPSWARM_DATA_DIR", "runtime-data"))
app = FastAPI(title="OpsSwarm Enterprise OpenClaw+GitHub", version="2.1.0")
logger = logging.getLogger("opsswarm.api")
_pending_issue_starts: set[int] = set()


POLL_SECONDS = max(2, int(os.environ.get("OPSWARM_GITHUB_POLL_SECONDS", "2")))


async def _github_issue_poll_loop() -> None:
    logger.info('GitHub issue poller started interval=%ss labels=%s', POLL_SECONDS, cfg.get('labels', {}).get('base', ['opsswarm']))
    while True:
        try:
            labels = [cfg.get("required_issue_label", "opsswarm")]
            issues = await gh.list_open_issues(labels=labels, per_page=50)
            logger.info('GitHub poll found %s open labeled issues', len(issues or []))
            for issue in issues or []:
                if issue.get("pull_request"):
                    continue
                number = int(issue["number"])
                if number not in engine.runs:
                    await _start_issue_background(number, f"poll-{number}")

                # Local/demo fallback for GitHub issue_comment webhooks. Only
                # structured /opsswarm commands are polled; ordinary comments
                # and OpsSwarm's own status messages are ignored.
                run = engine.runs.get(number)
                if not run:
                    continue
                comments = await gh.list_comments(number, per_page=100)
                for item in comments or []:
                    text = item.get("body") or ""
                    command = parse_command(text)
                    if not command:
                        continue
                    comment_id = str(item.get("id") or "")
                    if comment_id and comment_id in run.command_outcomes:
                        continue
                    actor = ((item.get("user") or {}).get("login") or "")
                    if not actor:
                        continue
                    permission = await gh.permission(actor)
                    try:
                        await engine.handle_comment(
                            number, actor, text, permission, command,
                            comment_id, f"poll-comment-{comment_id}")
                    except PermissionError as exc:
                        await gh.comment(number, f"OpsSwarm command rejected: {exc}")
                    except Exception as exc:
                        logger.exception("Polled GitHub command failed for issue #%s", number)
                        await gh.comment(
                            number,
                            f"OpsSwarm could not process the command: {type(exc).__name__}: {exc}",
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("GitHub issue polling failed")
        await asyncio.sleep(POLL_SECONDS)


@app.on_event("startup")
async def _start_github_issue_poller() -> None:
    enabled = os.environ.get("OPSWARM_GITHUB_POLL_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
    logger.info('GitHub issue poller enabled=%s interval=%ss', enabled, POLL_SECONDS)
    app.state.github_issue_poller = asyncio.create_task(_github_issue_poll_loop()) if enabled else None
    if not enabled:
        logger.info("GitHub issue polling fallback disabled; monitoring ingress/webhook remains active")


@app.on_event("shutdown")
async def _stop_github_issue_poller() -> None:
    task = getattr(app.state, "github_issue_poller", None)
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)





def _queue_issue_start(number: int, delivery_id: str | None) -> bool:
    """Queue issue processing without blocking webhook/poller discovery."""
    if number in engine.runs or number in _pending_issue_starts:
        return False
    _pending_issue_starts.add(number)

    async def runner() -> None:
        try:
            await _start_issue_background(number, delivery_id)
        finally:
            _pending_issue_starts.discard(number)

    asyncio.create_task(runner())
    return True

async def _start_issue_background(number: int, delivery_id: str | None) -> None:
    try:
        await engine.start_issue(number, delivery_id)
        logger.info("GitHub issue #%s accepted and processed by OpsSwarm", number)
    except Exception:
        logger.exception("GitHub issue #%s was received but processing failed", number)
        try:
            await gh.comment(
                number,
                "## OpsSwarm — processing failed\\n\\n"
                "The GitHub webhook was received, but the incident run failed during processing. "
                "Check the OpsSwarm service log for the exception.",
            )
        except Exception:
            logger.exception("Could not report processing failure on GitHub issue #%s", number)


@app.post("/internal/issues/{issue_number}/start")
async def start_issue_internal(issue_number: int):
    issue = await gh.get_issue(issue_number)
    labels = {x.get("name") for x in issue.get("labels", [])}
    required = cfg.get("required_issue_label", "opsswarm")
    if issue.get("pull_request"):
        return {"accepted": False, "reason": "pull_request"}
    if issue.get("state") != "open":
        return {"accepted": False, "reason": "issue_not_open"}
    if required not in labels:
        return {"accepted": False, "reason": "missing_required_label", "required_label": required}
    if issue_number in engine.runs:
        return {"accepted": True, "duplicate": True, "issue": issue_number}
    asyncio.create_task(_start_issue_background(issue_number, f"internal-{issue_number}"))
    return {"accepted": True, "issue": issue_number}

@app.get("/health")
async def health(): return {"ok": True, "version": "2.1.0", "architecture": "openclaw+github"}


@app.get("/runs")
async def runs(): return [r.model_dump(mode="json") for r in engine.runs.values()]


@app.get("/runs/{issue_number}")
async def run(issue_number: int):
    r = engine.runs.get(issue_number)
    if not r: raise HTTPException(404, "No run for issue")
    return r.model_dump(mode="json")


@app.get("/runs/{issue_number}/evidence")
async def evidence(issue_number: int):
    r = engine.runs.get(issue_number)
    if not r: raise HTTPException(404, "No run for issue")
    return engine.ev.list(r.run_id)


@app.get("/runs/{issue_number}/checkpoint")
async def get_checkpoint(issue_number: int):
    """Get the last checkpoint for a run."""
    r = engine.runs.get(issue_number)
    if not r: raise HTTPException(404, "No run for issue")
    checkpoint = engine.ev.get_last_checkpoint(r.run_id)
    if not checkpoint:
        return {"has_checkpoint": False, "checkpoint": None}
    return {"has_checkpoint": True, "checkpoint": checkpoint}


@app.post("/runs/{issue_number}/resume")
async def resume_run(issue_number: int):
    """Resume a run from its last checkpoint."""
    r = engine.runs.get(issue_number)
    if not r: raise HTTPException(404, "No run for issue")

    # Check for valid checkpoint
    checkpoint = engine.ev.get_last_checkpoint(r.run_id)
    if not checkpoint:
        raise HTTPException(400, "No checkpoint available for this run")

    checkpoint_type = checkpoint.get("payload", {}).get("checkpoint_type", "unknown")
    checkpoint_state = checkpoint.get("payload", {}).get("state", "unknown")

    return {
        "resumed": True,
        "checkpoint_type": checkpoint_type,
        "checkpoint_state": checkpoint_state,
        "current_state": r.state.value,
    }


@app.post("/webhooks/github")
async def github_webhook(request: Request, x_github_event: str | None = Header(None),
                         x_hub_signature_256: str | None = Header(None), x_github_delivery: str | None = Header(None)):
    body = await request.body();
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not verify_signature(secret, body, x_hub_signature_256): raise HTTPException(401, "Invalid webhook signature")
    data = await request.json()
    if x_github_event == "issues" and data.get("action") == "opened":
        number = int(data["issue"]["number"]);
        asyncio.create_task(_start_issue_background(number, x_github_delivery))
        return {"accepted": True, "issue": number}
    if x_github_event == "issue_comment" and data.get("action") == "created":
        number = int(data["issue"]["number"]);
        actor = data["comment"]["user"]["login"];
        text = data["comment"].get("body") or ""
        # Extract comment ID for idempotency
        comment_id = str(data["comment"].get("id", ""))
        permission = await gh.permission(actor)
        try:
            await engine.handle_comment(number, actor, text, permission, parse_command(text), comment_id,
                                        x_github_delivery)
        except PermissionError as e:
            await gh.comment(number, f"OpsSwarm command rejected: {e}")
        except Exception as e:
            await gh.comment(number, f"OpsSwarm could not process the command: `{type(e).__name__}: {e}`")
        return {"accepted": True}
    return {"ignored": True}


@app.post("/hooks/monitoring")
async def monitoring_event(payload: dict):
    title = payload.get("title") or f"[Incident] {payload.get('service', 'unknown service')}"
    details = payload.get("details_markdown") or ""
    body = f"""## Incident\n\n### Service\n{payload.get('service', 'unknown')}\n\n### Symptoms\n{payload.get('symptom', 'Monitoring alert')}\n\n### Customer impact\n{payload.get('customer_impact', 'unknown')}\n\n### Environment\n{payload.get('environment', 'production')}\n\n### Observed since\n{payload.get('observed_since', 'unknown')}\n\n### Additional information\nCreated automatically by OpsSwarm monitoring ingress.\n\n{details}\n"""
    labels = list(dict.fromkeys(
        cfg.get("labels", {}).get("base", ["opsswarm", "incident"]) + [payload.get("severity_label", "sev:2")]))
    issue = await gh.create_issue(title, body, labels);
    number = int(issue["number"]);
    asyncio.create_task(_start_issue_background(number, None))
    return {"accepted": True, "issue_number": number}
