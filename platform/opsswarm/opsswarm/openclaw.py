from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import httpx
import yaml


class OpenClawError(RuntimeError):
    pass


class OpenClawClient:
    def __init__(self, binary="openclaw", timeout=600):
        # On Windows, asyncio.create_subprocess_exec does not reliably resolve
        # the npm .cmd shim from the bare command name. Resolve it explicitly.
        requested = binary or "openclaw"
        if os.name == "nt" and requested.lower() in {"openclaw", "openclaw.exe", "openclaw.cmd"}:
            self.binary = shutil.which("openclaw.cmd") or shutil.which("openclaw") or requested
        else:
            self.binary = shutil.which(requested) or requested
        self.timeout = timeout
        self.gateway_url = os.environ.get("OPSWARM_OPENCLAW_HTTP_URL", "").strip().rstrip("/")
        self.gateway_token = os.environ.get("OPSWARM_OPENCLAW_GATEWAY_TOKEN", "").strip()
        if self.gateway_url and not self.gateway_token:
            self.gateway_token = self._load_local_gateway_token()

    @staticmethod
    def _load_local_gateway_token() -> str:
        """Read the local OpenClaw gateway token without copying it into OpsSwarm config."""
        try:
            state_dir = Path(os.environ.get("OPENCLAW_STATE_DIR", "")).expanduser()
            if not str(state_dir) or str(state_dir) == ".":
                state_dir = Path.home() / ".openclaw"
            cfg_path = state_dir / "openclaw.json"
            data = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            auth = (data.get("gateway") or {}).get("auth") or {}
            if isinstance(auth, dict) and auth.get("mode") == "token":
                return str(auth.get("token") or "").strip()
        except (OSError, ValueError, TypeError):
            return ""
        return ""

    @staticmethod
    def _response_text(envelope: dict[str, Any]) -> str:
        """Extract assistant text from an OpenResponses non-streaming response."""
        direct = envelope.get("output_text")
        if isinstance(direct, str) and direct:
            return direct

        texts: list[str] = []
        for item in envelope.get("output") or []:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("text"), str):
                texts.append(item["text"])
            for part in item.get("content") or []:
                if not isinstance(part, dict):
                    continue
                value = part.get("text")
                if isinstance(value, str):
                    texts.append(value)
                elif isinstance(value, dict) and isinstance(value.get("value"), str):
                    texts.append(value["value"])
        if texts:
            return "".join(texts)

        raise OpenClawError("No assistant text in OpenClaw HTTP response")

    async def _run_text_http(self, agent: str, session_key: str, prompt: str) -> str:
        headers = {
            "Content-Type": "application/json",
            "x-openclaw-agent-id": agent,
        }
        if self.gateway_token:
            headers["Authorization"] = f"Bearer {self.gateway_token}"

        payload = {
            "model": "openclaw",
            "input": prompt,
            "user": session_key,
            "stream": False,
        }
        timeout = httpx.Timeout(float(self.timeout + 30), connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{self.gateway_url}/v1/responses", headers=headers, json=payload)

        if response.status_code >= 400:
            detail = response.text[-1200:]
            try:
                body = response.json()
                error = body.get("error") if isinstance(body, dict) else None
                if isinstance(error, dict) and error.get("message"):
                    detail = str(error["message"])
            except ValueError:
                pass
            raise OpenClawError(f"OpenClaw gateway HTTP {response.status_code}: {detail}")

        try:
            envelope = response.json()
        except ValueError as exc:
            raise OpenClawError("OpenClaw gateway returned invalid JSON") from exc
        if not isinstance(envelope, dict):
            raise OpenClawError("OpenClaw gateway returned an invalid response envelope")
        return self._response_text(envelope)

    async def _run_text_cli(self, agent: str, session_key: str, prompt: str) -> str:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write(prompt)
            path = f.name
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary, "agent", "--agent", agent, "--session-key", session_key,
                "--message-file", path, "--json", "--timeout", str(self.timeout),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            out, err = await asyncio.wait_for(proc.communicate(), timeout=self.timeout + 30)
            if proc.returncode != 0:
                raise OpenClawError(f"OpenClaw failed rc={proc.returncode}: {err.decode(errors='replace')[-1200:]}")
            envelope = json.loads(out.decode())
            if not envelope.get("ok", True):
                raise OpenClawError(str(envelope.get("error")))
            if isinstance(envelope.get("final"), str):
                return envelope["final"]
            for p in envelope.get("payloads", []):
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    return p["text"]
            # Gateway-backed response may nest payloads under result.
            result = envelope.get("result") or {}
            for p in result.get("payloads", []) if isinstance(result, dict) else []:
                if isinstance(p, dict) and isinstance(p.get("text"), str):
                    return p["text"]
            raise OpenClawError("No assistant text in OpenClaw JSON envelope")
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    async def run_text(self, agent: str, session_key: str, prompt: str) -> str:
        if self.gateway_url:
            try:
                return await self._run_text_http(agent, session_key, prompt)
            except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
                # Container deployments are HTTP-only: falling back to a second CLI
                # execution can duplicate a recovery after a transient gateway error.
                http_required = os.environ.get("OPSWARM_OPENCLAW_HTTP_REQUIRED", "").strip().lower() in {
                    "1", "true", "yes", "on"
                }
                if http_required:
                    raise OpenClawError(
                        f"OpenClaw gateway is unreachable at {self.gateway_url}"
                    ) from exc
                # Preserve the legacy local CLI fallback for workstation deployments.
                pass
        return await self._run_text_cli(agent, session_key, prompt)

    @staticmethod
    def _repair_json_candidate(candidate: str) -> str:
        """Repair a small, deterministic set of common LLM JSON defects.

        This never invokes the model again. That matters because run_json is also
        used by recovery agents, where replaying an agent could duplicate a write.
        """
        out: list[str] = []
        in_string = False
        escaped = False

        for i, ch in enumerate(candidate):
            if not in_string:
                out.append(ch)
                if ch == '"':
                    in_string = True
                continue

            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                out.append(ch)
                escaped = True
                continue
            if ch == '"':
                j = i + 1
                while j < len(candidate) and candidate[j].isspace():
                    j += 1
                nxt = candidate[j] if j < len(candidate) else ""
                if nxt in {":", ",", "}", "]", "", '"'}:
                    out.append(ch)
                    in_string = False
                else:
                    out.append('\\"')
                continue
            if ch == "\n":
                out.append("\\n")
            elif ch == "\r":
                out.append("\\r")
            elif ch == "\t":
                out.append("\\t")
            elif ord(ch) < 0x20:
                out.append(f"\\u{ord(ch):04x}")
            else:
                out.append(ch)

        repaired = "".join(out)
        repaired = re.sub(r",\\s*([}\\]])", r"\\1", repaired)

        # If the model omitted a comma between two otherwise valid JSON values,
        # the stdlib decoder points at the exact unexpected token. Insert only
        # at that reported location, with a strict repair budget.
        for _ in range(8):
            try:
                json.loads(repaired)
                break
            except json.JSONDecodeError as exc:
                if exc.msg != "Expecting ',' delimiter" or exc.pos >= len(repaired):
                    break
                repaired = repaired[:exc.pos] + "," + repaired[exc.pos:]
        return repaired

    @staticmethod
    def _extract_json(text: str) -> Any:
        s = text.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            # bounded salvage: first object or array only
            starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
            if not starts:
                raise
            start = min(starts)
            opening = s[start]
            closing = "}" if opening == "{" else "]"
            end = s.rfind(closing)
            if end <= start:
                raise
            candidate = s[start:end + 1]

        try:
            return json.loads(candidate)
        except json.JSONDecodeError as candidate_error:
            repaired = OpenClawClient._repair_json_candidate(candidate)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as repaired_error:
                for value in (candidate, repaired):
                    try:
                        parsed = yaml.safe_load(value)
                    except yaml.YAMLError:
                        continue
                    if isinstance(parsed, (dict, list)):
                        return json.loads(json.dumps(parsed, ensure_ascii=False, default=str))
                raise repaired_error from candidate_error

    async def run_json(self, agent: str, session_key: str, prompt: str) -> Any:
        text = await self.run_text(agent, session_key, prompt)
        try:
            return self._extract_json(text)
        except json.JSONDecodeError as exc:
            # Never auto-replay the agent here: recovery-responder may already
            # have completed a side effect before emitting malformed JSON.
            raise OpenClawError(
                f"OpenClaw returned malformed JSON at line {exc.lineno}, "
                f"column {exc.colno}: {exc.msg}"
            ) from exc
