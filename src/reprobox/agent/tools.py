"""Structured tool declarations for the LLM function-calling interface."""

from __future__ import annotations

from typing import Any

AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List files and directories in the given path within /workspace/case.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path under /workspace/case (default: /workspace/case)",
                        "default": "/workspace/case",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file within /workspace/case.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path to read",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run an allowed read-only shell command (e.g. ls, grep, find, wc, cat) inside the sandbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to run",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_test_file",
            "description": "Write or update the single test reproduction file at /workspace/case/tests/test_issue_repro.py.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Python test source code using pytest assertions",
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_pytest",
            "description": "Run pytest on a test file under /workspace/case.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Test file path (e.g. /workspace/case/tests/test_issue_repro.py)",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Signal that test reproduction is complete and authoring is finished.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief explanation of how the test reproduces the issue",
                    }
                },
                "required": ["summary"],
            },
        },
    },
]
