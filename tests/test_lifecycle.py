from __future__ import annotations

import threading

import pytest

from reprobox.sandbox.handle import GuestHandle
from reprobox.sandbox.lifecycle import (
    ComputerRegistry,
    managed_computer,
    sweep_orphans,
)


class FakeComputer:
    def __init__(self, name: str, cid: str) -> None:
        self.name = name
        self.id = cid
        self.deleted = False


class FakeLifecycleProvider:
    def __init__(self, fail_delete_times: int = 0, fail_create: bool = False) -> None:
        self.computers: dict[str, FakeComputer] = {}
        self.delete_attempts = 0
        self.fail_delete_times = fail_delete_times
        self.fail_create = fail_create

    def create(self, name: str) -> GuestHandle:
        if self.fail_create:
            raise RuntimeError("Simulation: create failed")
        comp = FakeComputer(name, f"cmp_{name}")
        self.computers[name] = comp
        return GuestHandle(sandbox_name=name, computer_id=comp.id, sdk_object=comp)

    def delete(self, handle: GuestHandle) -> None:
        self.delete_attempts += 1
        if self.delete_attempts <= self.fail_delete_times:
            raise RuntimeError("Temporary delete failure")
        comp = self.computers.pop(handle.sandbox_name, None)
        if comp:
            comp.deleted = True

    def exists(self, handle: GuestHandle) -> bool:
        return handle.sandbox_name in self.computers


def test_worker_thread_pipeline_import():
    # Defect R-C6 verification
    error = None

    def worker():
        nonlocal error
        try:
            __import__("reprobox.pipeline.orchestrator")
        except Exception as e:
            error = e

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=5.0)
    assert error is None, f"Worker thread import raised: {error}"


def test_deletion_on_success():
    prov = FakeLifecycleProvider()
    name = "sbx-lifesuccess1"
    with managed_computer(prov, name) as handle:
        assert prov.exists(handle)
    assert not prov.exists(handle)


def test_deletion_on_failure():
    prov = FakeLifecycleProvider()
    name = "sbx-lifefail1"
    with pytest.raises(ValueError), managed_computer(prov, name) as handle:
        raise ValueError("Deliberate failure inside block")
    assert not prov.exists(handle)


def test_deletion_on_keyboard_interrupt():
    prov = FakeLifecycleProvider()
    name = "sbx-lifeintr1"
    with pytest.raises(KeyboardInterrupt), managed_computer(prov, name) as handle:
        raise KeyboardInterrupt("Simulated Ctrl-C")
    assert not prov.exists(handle)


def test_deletion_on_timeout():
    prov = FakeLifecycleProvider()
    name = "sbx-lifetimeout1"
    with pytest.raises(TimeoutError), managed_computer(prov, name) as handle:
        raise TimeoutError("Simulated timeout")
    assert not prov.exists(handle)


def test_no_orphan_on_create_failure():
    prov = FakeLifecycleProvider(fail_create=True)
    name = "sbx-createfail1"
    with pytest.raises(RuntimeError), managed_computer(prov, name):
        pass
    assert len(prov.computers) == 0


def test_registry_tracking_and_emergency_cleanup():
    reg = ComputerRegistry()
    prov = FakeLifecycleProvider()
    h1 = prov.create("sbx-regtest1")
    reg.register(h1, prov)
    assert len(reg.active_handles()) == 1

    reg.cleanup_all()
    assert len(reg.active_handles()) == 0
    assert not prov.exists(h1)


def test_sweep_never_deletes_id_absent_from_ledger():
    class MockLedger:
        def list_runs(self, limit=100):
            return [{"computer_id": "cmp_known", "state": "created"}]

    # Even if cloud has unknown computers, sweep ignores them
    prov = FakeLifecycleProvider()
    deleted = sweep_orphans(prov, ledger_repo=MockLedger())
    assert len(deleted) == 0
