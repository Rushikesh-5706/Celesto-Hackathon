"""Agent deliberation loop interacting with the sandbox through guarded tools."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from reprobox.agent.llm import LLMClient
from reprobox.agent.prompts import SYSTEM_PROMPT, build_user_prompt
from reprobox.agent.tools import AGENT_TOOLS
from reprobox.constants import (
    AGENT_TOOL_TRUNCATE,
    ORIGIN_AGENT,
    TEST_FILE_PATH,
)
from reprobox.sandbox.audit import audit_logger
from reprobox.sandbox.guard import Guard
from reprobox.sandbox.provider import ComputerProvider
from reprobox.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class AgentLoopResult:
    success: bool
    turns: int
    summary: str
    test_authored: bool
    prompt_tokens: int
    completion_tokens: int
    error: str | None = None


class AgentLoop:
    """Orchestrates LLM turns and tool executions inside the sandbox."""

    def __init__(
        self,
        computer: Any,
        provider: ComputerProvider,
        sandbox_name: str,
        run_id: str,
        llm_client: LLMClient | None = None,
    ) -> None:
        self.computer = computer
        self.provider = provider
        self.sandbox_name = sandbox_name
        self.run_id = run_id
        self.llm = llm_client or LLMClient()
        self.test_authored = False

    def _truncate(self, text: str) -> str:
        if len(text) > AGENT_TOOL_TRUNCATE:
            return text[:AGENT_TOOL_TRUNCATE] + "\n...[truncated]"
        return text

    def run(
        self, issue_title: str, issue_body: str, max_turns: int | None = None
    ) -> AgentLoopResult:
        turns_limit = max_turns or settings.agent_max_turns
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(issue_title, issue_body)},
        ]

        summary = ""
        finished = False

        for turn in range(1, turns_limit + 1):
            logger.info("Agent turn %d/%d (run_id=%s)", turn, turns_limit, self.run_id)

            try:
                resp = self.llm.chat(messages=messages, tools=AGENT_TOOLS)
            except Exception as e:
                logger.error("LLM error on turn %d: %s", turn, e)
                return AgentLoopResult(
                    success=False,
                    turns=turn,
                    summary="Aborted due to LLM failure",
                    test_authored=self.test_authored,
                    prompt_tokens=self.llm.total_prompt_tokens,
                    completion_tokens=self.llm.total_completion_tokens,
                    error=str(e),
                )

            # Build assistant message object
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
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in resp.tool_calls
                ]

            messages.append(assistant_msg)

            if not resp.tool_calls:
                if resp.content and "finish" in resp.content.lower():
                    finished = True
                    summary = resp.content
                    break
                # If no tool called, prompt continuation
                messages.append(
                    {
                        "role": "user",
                        "content": "Please continue your investigation and author the test in `/workspace/case/tests/test_issue_repro.py`.",
                    }
                )
                continue

            for tc in resp.tool_calls:
                tool_output = self._execute_tool(tc.name, tc.arguments)
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

        return AgentLoopResult(
            success=finished and self.test_authored,
            turns=min(turn, turns_limit),
            summary=summary,
            test_authored=self.test_authored,
            prompt_tokens=self.llm.total_prompt_tokens,
            completion_tokens=self.llm.total_completion_tokens,
        )

    def _execute_tool(self, name: str, args: dict[str, Any]) -> str:
        """Dispatch and execute an individual tool call under security guard."""
        if name == "finish":
            return f"Completed: {args.get('summary', 'Done')}"

        if name == "list_dir":
            path = args.get("path", "/workspace/case")
            if ".." in path or not path.startswith("/workspace/case"):
                return "Error: Path must be under /workspace/case"
            cmd = f"ls -la {path}"
            res = self.provider.run(self.computer, cmd)
            return res.stdout or res.stderr or "[empty directory]"

        if name == "read_file":
            path = args.get("path", "")
            if not path or ".." in path or not path.startswith("/workspace/case"):
                return "Error: Path must be under /workspace/case"
            try:
                data = self.provider.read_file(self.computer, path)
                # Audit file read
                audit_logger.log_command(
                    sandbox_name=self.sandbox_name,
                    command=f"read_file {path}",
                    decision="allow",
                    run_id=self.run_id,
                    origin=ORIGIN_AGENT,
                    step="agent_loop",
                )
                return data.decode("utf-8", errors="replace")
            except Exception as e:
                return f"Error reading file: {e}"

        if name == "write_test_file":
            content = args.get("content", "")
            decision = Guard.evaluate_test_file_write(TEST_FILE_PATH, content)
            if not decision.allowed:
                return f"Error: Write blocked by guard ({decision.rule_id}): {decision.reason}"

            try:
                data = content.encode("utf-8")
                self.provider.write_file(self.computer, TEST_FILE_PATH, data)
                self.test_authored = True
                sha = hashlib.sha256(data).hexdigest()[:12]
                audit_logger.log_command(
                    sandbox_name=self.sandbox_name,
                    command=f"write_file {TEST_FILE_PATH} sha256={sha} bytes={len(data)}",
                    decision="allow",
                    run_id=self.run_id,
                    origin=ORIGIN_AGENT,
                    step="agent_loop",
                )
                return f"Successfully wrote {len(data)} bytes to {TEST_FILE_PATH}"
            except Exception as e:
                return f"Failed to write file: {e}"

        if name == "run_pytest":
            path = args.get("path", "/workspace/case/tests/test_issue_repro.py")
            if not path.startswith("/workspace/case"):
                return "Error: Pytest path must be under /workspace/case"
            cmd = f"python3 -m pytest {path} -p no:cacheprovider"
            decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
            audit_logger.log_command(
                sandbox_name=self.sandbox_name,
                command=cmd,
                decision=decision.decision,
                run_id=self.run_id,
                origin=ORIGIN_AGENT,
                step="agent_loop",
                rule_id=decision.rule_id,
                reason=decision.reason,
            )
            if not decision.allowed:
                return f"Error: Command blocked by guard: {decision.reason}"
            res = self.provider.run(self.computer, cmd)
            return (res.stdout + "\n" + res.stderr).strip()

        if name == "run_shell":
            cmd = args.get("command", "")
            decision = Guard.evaluate(cmd, origin=ORIGIN_AGENT)
            audit_logger.log_command(
                sandbox_name=self.sandbox_name,
                command=cmd,
                decision=decision.decision,
                run_id=self.run_id,
                origin=ORIGIN_AGENT,
                step="agent_loop",
                rule_id=decision.rule_id,
                reason=decision.reason,
            )
            if not decision.allowed:
                return f"Command blocked by security guard (rule: {decision.rule_id}): {decision.reason}"

            res = self.provider.run(self.computer, cmd)
            output = (
                res.stdout
                if res.exit_code == 0
                else f"{res.stdout}\n{res.stderr} (exit code: {res.exit_code})"
            )
            return output.strip() or "[no output]"

        return f"Unknown tool: {name}"
