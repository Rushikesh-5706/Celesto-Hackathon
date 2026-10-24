from __future__ import annotations

import json
import logging
import posixpath
import shlex
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from reprobox.agent.llm import LLMClient
from reprobox.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from reprobox.agent.tools import AGENT_TOOLS
from reprobox.constants import TEST_FILE_PATH
from reprobox.exceptions import CommandBlocked, LLMRateLimitExceeded, LLMTransportError
from reprobox.sandbox.audited_provider import AuditedProvider
from reprobox.sandbox.guard import Guard
from reprobox.sandbox.handle import GuestHandle

logger = logging.getLogger(__name__)


@dataclass
class AgentLoopResult:
    success: bool
    turns: int
    summary: str
    test_authored: bool
    prompt_tokens: int
    completion_tokens: int
    blocked_count: int = 0
    tool_call_counts: dict[str, int] = field(default_factory=dict)
    rate_limit_count: int = 0
    failure_reason: str = ""


class AgentToolExecutor:
    def __init__(self, provider: AuditedProvider, guest: GuestHandle, run_id: str = "") -> None:
        self.provider = provider
        self.guest = guest
        self.run_id = run_id
        self.blocked_count = 0
        self.tool_call_counts: dict[str, int] = defaultdict(int)
        self.test_authored = False
        self.pytest_executed = False

    def list_dir(self, path: str = "/workspace/case") -> str:
        self.tool_call_counts["list_dir"] += 1
        norm = posixpath.normpath(path)
        if not norm.startswith("/workspace/case") and norm != "/workspace/case":
            self.blocked_count += 1
            return "Error: Path must be under /workspace/case"
        if any(c in path for c in (";", "&", "|", "`", "$", "\n")):
            self.blocked_count += 1
            return "Error: Invalid shell characters in path"

        quoted = shlex.quote(norm)
        cmd = f"ls -la -- {quoted}"
        try:
            res = self.provider.run(
                self.guest, cmd, origin="agent", run_id=self.run_id, step="agent_loop"
            )
            return res.stdout or res.stderr or "[empty directory]"
        except CommandBlocked as exc:
            self.blocked_count += 1
            return f"Command blocked [{exc.rule_id}]: {exc.reason}"
        except Exception as exc:
            return f"Error executing ls: {exc}"

    def read_file(self, path: str) -> str:
        self.tool_call_counts["read_file"] += 1
        norm = posixpath.normpath(path)
        if not norm.startswith("/workspace/case"):
            self.blocked_count += 1
            return "Error: Path must be under /workspace/case"
        if any(c in path for c in (";", "&", "|", "`", "$", "\n")):
            self.blocked_count += 1
            return "Error: Invalid shell characters in path"

        try:
            data = self.provider.read_file(
                self.guest, norm, origin="agent", run_id=self.run_id, step="agent_loop"
            )
            return data.decode("utf-8", errors="replace")
        except CommandBlocked as exc:
            self.blocked_count += 1
            return f"File read blocked [{exc.rule_id}]: {exc.reason}"
        except Exception as exc:
            return f"Error reading file: {exc}"

    def run_shell(self, command: str) -> str:
        self.tool_call_counts["run_shell"] += 1
        try:
            res = self.provider.run(
                self.guest, command, origin="agent", run_id=self.run_id, step="agent_loop"
            )
            out = res.stdout
            if res.stderr:
                out = f"{out}\n{res.stderr}" if out else res.stderr
            return out or "[command executed with no output]"
        except CommandBlocked as exc:
            self.blocked_count += 1
            return f"Command blocked [{exc.rule_id}]: {exc.reason}"
        except Exception as exc:
            return f"Error executing command: {exc}"

    def write_test_file(self, content: str) -> str:
        self.tool_call_counts["write_test_file"] += 1
        decision = Guard.evaluate_test_file_write(content)
        if not decision.allowed:
            self.blocked_count += 1
            return f"Test write blocked [{decision.rule_id}]: {decision.reason}"

        try:
            self.provider.write_file(
                self.guest,
                TEST_FILE_PATH,
                content.encode("utf-8"),
                origin="pipeline",
                run_id=self.run_id,
                step="agent_loop",
            )
            self.test_authored = True
            return f"Successfully wrote test to {TEST_FILE_PATH}"
        except Exception as exc:
            return f"Error writing test file: {exc}"

    def run_pytest(self, path: str = TEST_FILE_PATH) -> str:
        self.tool_call_counts["run_pytest"] += 1
        norm = posixpath.normpath(path)
        if not norm.startswith("/workspace/case"):
            self.blocked_count += 1
            return "Error: Pytest target must be under /workspace/case"

        quoted = shlex.quote(norm)
        cmd = f"python3 -m pytest {quoted} -p no:cacheprovider --tb=short"
        try:
            res = self.provider.run(
                self.guest, cmd, origin="agent", run_id=self.run_id, step="agent_loop"
            )
            self.pytest_executed = True
            out = res.stdout
            if res.stderr:
                out = f"{out}\n{res.stderr}" if out else res.stderr
            return out or "[pytest completed with no output]"
        except CommandBlocked as exc:
            self.blocked_count += 1
            return f"Pytest execution blocked [{exc.rule_id}]: {exc.reason}"
        except Exception as exc:
            return f"Error running pytest: {exc}"

    def execute(self, name: str, args: dict[str, Any]) -> str:
        if name == "finish":
            self.tool_call_counts["finish"] += 1
            return f"Completed: {args.get('summary', 'Done')}"
        if name == "list_dir":
            return self.list_dir(args.get("path", "/workspace/case"))
        if name == "read_file":
            return self.read_file(args.get("path", ""))
        if name == "run_shell":
            return self.run_shell(args.get("command", ""))
        if name == "write_test_file":
            return self.write_test_file(args.get("content", ""))
        if name == "run_pytest":
            return self.run_pytest(args.get("path", TEST_FILE_PATH))
        return f"Unknown tool: {name}"


class AgentLoop:
    def __init__(
        self,
        provider: AuditedProvider,
        guest: GuestHandle,
        llm: LLMClient | None = None,
        run_id: str = "",
        sandbox_name: str = "",
    ) -> None:
        self.provider = provider
        self.guest = guest
        self.llm = llm or LLMClient()
        self.run_id = run_id
        self.sandbox_name = sandbox_name or guest.sandbox_name
        self.executor = AgentToolExecutor(provider, guest, run_id=run_id)

    def _truncate(self, text: str, max_chars: int = 4000) -> str:
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n...[output truncated]...\n" + text[-half:]

    def run(
        self,
        issue_title: str,
        issue_body: str,
        turns_limit: int = 15,
    ) -> AgentLoopResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(issue_title, issue_body)},
        ]

        turn = 0
        finished = False
        summary = ""
        failure_reason = ""

        while turn < turns_limit and not finished:
            turn += 1
            logger.info("Agent turn %d/%d for sandbox %s", turn, turns_limit, self.sandbox_name)

            try:
                resp = self.llm.chat(messages, tools=AGENT_TOOLS)
            except LLMRateLimitExceeded as exc:
                logger.error("LLM rate limit retries exhausted on turn %d: %s", turn, exc)
                return AgentLoopResult(
                    success=False,
                    turns=turn,
                    summary="LLM rate limit retries exhausted",
                    test_authored=self.executor.test_authored,
                    prompt_tokens=self.llm.total_prompt_tokens,
                    completion_tokens=self.llm.total_completion_tokens,
                    blocked_count=self.executor.blocked_count,
                    tool_call_counts=dict(self.executor.tool_call_counts),
                    rate_limit_count=self.llm.rate_limit_count,
                    failure_reason="llm_rate_limited",
                )
            except (LLMTransportError, Exception) as exc:
                logger.error("LLM call failed on turn %d: %s", turn, exc)
                return AgentLoopResult(
                    success=False,
                    turns=turn,
                    summary=f"LLM transport error: {exc}",
                    test_authored=self.executor.test_authored,
                    prompt_tokens=self.llm.total_prompt_tokens,
                    completion_tokens=self.llm.total_completion_tokens,
                    blocked_count=self.executor.blocked_count,
                    tool_call_counts=dict(self.executor.tool_call_counts),
                    rate_limit_count=self.llm.rate_limit_count,
                    failure_reason="llm_error",
                )

            assistant_msg: dict[str, Any] = {"role": "assistant"}
            if resp.content:
                assistant_msg["content"] = resp.content
            if resp.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments)
                            if isinstance(tc.arguments, dict)
                            else str(tc.arguments),
                        },
                    }
                    for tc in resp.tool_calls
                ]
            messages.append(assistant_msg)

            if not resp.tool_calls:
                # Model did not issue tools
                if "finish" in (resp.content or "").lower():
                    finished = True
                    summary = resp.content or ""
                continue

            for tc in resp.tool_calls:
                tool_output = self.executor.execute(tc.name, tc.arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": self._truncate(tool_output),
                    }
                )
                if tc.name == "finish":
                    finished = True
                    summary = str(tc.arguments.get("summary", ""))

            if finished:
                break

        if not self.executor.test_authored:
            failure_reason = "agent_no_test" if turn < turns_limit else "agent_turn_limit"
        elif not finished:
            failure_reason = "agent_turn_limit"

        return AgentLoopResult(
            success=finished and self.executor.test_authored,
            turns=turn,
            summary=summary,
            test_authored=self.executor.test_authored,
            prompt_tokens=self.llm.total_prompt_tokens,
            completion_tokens=self.llm.total_completion_tokens,
            blocked_count=self.executor.blocked_count,
            tool_call_counts=dict(self.executor.tool_call_counts),
            rate_limit_count=self.llm.rate_limit_count,
            failure_reason=failure_reason,
        )
