"""Lifecycle hygiene unit tests using a test double provider."""

import pytest

from reprobox.sandbox.lifecycle import ComputerRegistry, managed_computer
from reprobox.sandbox.provider import RunResult


class FakeComputer:
    def __init__(self, name: str, cid: str) -> None:
        self.name = name
        self.id = cid
        self.deleted = False
        self.stopped = False


class FakeProvider:
    def __init__(self, fail_delete_times: int = 0) -> None:
        self.computers: dict[str, FakeComputer] = {}
        self.delete_attempts = 0
        self.fail_delete_times = fail_delete_times

    def create(self, name: str) -> FakeComputer:
        comp = FakeComputer(name, f"cmp-{name}")
        self.computers[name] = comp
        return comp

    def delete(self, computer: FakeComputer) -> None:
        self.delete_attempts += 1
        if self.delete_attempts <= self.fail_delete_times:
            raise RuntimeError("Temporary delete failure")
        computer.deleted = True
        self.computers.pop(computer.name, None)

    def exists(self, computer: FakeComputer) -> bool:
        return computer.name in self.computers

    def run(self, computer: FakeComputer, command: str, timeout: int = 60) -> RunResult:
        return RunResult(stdout="fake", stderr="", exit_code=0, computer_id=computer.id)

    def write_file(self, computer: FakeComputer, path: str, data: bytes) -> None:
        pass

    def read_file(self, computer: FakeComputer, path: str) -> bytes:
        return b""

    def stop(self, computer: FakeComputer) -> None:
        computer.stopped = True

    def start(self, computer: FakeComputer) -> None:
        computer.stopped = False

    def list_prefixed(self, prefix: str = "") -> list[str]:
        return [c.id for c in self.computers.values()]


def test_deletion_on_success():
    prov = FakeProvider()
    name = "sbx-lifesuccess1"
    with managed_computer(prov, name) as comp:
        assert prov.exists(comp)
    assert not prov.exists(comp)
    assert comp.deleted


def test_deletion_on_failure_and_exception():
    prov = FakeProvider()
    name = "sbx-lifefail1"
    with pytest.raises(ValueError), managed_computer(prov, name) as comp:
        raise ValueError("Deliberate failure inside block")
    assert not prov.exists(comp)
    assert comp.deleted


def test_deletion_on_keyboard_interrupt():
    prov = FakeProvider()
    name = "sbx-lifeintr1"
    with pytest.raises(KeyboardInterrupt), managed_computer(prov, name) as comp:
        raise KeyboardInterrupt("Simulated Ctrl-C")
    assert not prov.exists(comp)
    assert comp.deleted


def test_delete_retry_succeeds():
    prov = FakeProvider(fail_delete_times=2)
    name = "sbx-liferetry1"
    with managed_computer(prov, name, max_delete_retries=3) as comp:
        pass
    assert not prov.exists(comp)
    assert comp.deleted
    assert prov.delete_attempts == 3


def test_registry_tracking_and_empties():
    reg = ComputerRegistry()
    prov = FakeProvider()
    c1 = prov.create("sbx-regtest1")
    reg.register("sbx-regtest1", c1, prov)
    assert "sbx-regtest1" in reg.active_names()

    reg.unregister("sbx-regtest1")
    assert "sbx-regtest1" not in reg.active_names()
