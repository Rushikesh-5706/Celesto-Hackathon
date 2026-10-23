"""AST scan verifying Law L2: the host never executes untrusted or external processes."""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
SCRIPTS_DIR = REPO_ROOT / "scripts"

FORBIDDEN_CALLS = {"eval", "exec", "compile"}
FORBIDDEN_MODULES = {"subprocess", "pty"}
FORBIDDEN_OS_CALLS = {"system", "popen", "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe"}


class HostExecVisitor(ast.NodeVisitor):
    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name in FORBIDDEN_MODULES:
                self.violations.append(f"{self.filename}:{node.lineno}: import {alias.name} is forbidden (Law L2)")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and (node.module in FORBIDDEN_MODULES or node.module.startswith("subprocess")):
            self.violations.append(f"{self.filename}:{node.lineno}: from {node.module} is forbidden (Law L2)")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Bare name calls: eval(...), exec(...)
        if isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_CALLS:
                self.violations.append(f"{self.filename}:{node.lineno}: bare call to {node.func.id}() is forbidden (Law L2)")

        # Attribute calls: os.system(...), os.popen(...)
        elif isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                if node.func.attr in FORBIDDEN_OS_CALLS:
                    self.violations.append(f"{self.filename}:{node.lineno}: call to os.{node.func.attr}() is forbidden (Law L2)")
            elif isinstance(node.func.value, ast.Attribute) and node.func.attr.startswith("create_subprocess"):
                self.violations.append(f"{self.filename}:{node.lineno}: asyncio subprocess execution is forbidden (Law L2)")

        self.generic_visit(node)


def test_no_host_execution_in_src_and_scripts():
    violations = []
    py_files = list(SRC_DIR.glob("**/*.py")) + list(SCRIPTS_DIR.glob("**/*.py"))

    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        visitor = HostExecVisitor(str(py_file))
        visitor.visit(tree)
        violations.extend(visitor.violations)

    assert not violations, "Found forbidden host execution calls:\n" + "\n".join(violations)
