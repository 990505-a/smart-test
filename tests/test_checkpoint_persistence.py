"""会话状态落盘保活的契约（src/app/agents/checkpoint_persistence.py）。

不需要真的 langgraph 运行时：这里验的是**保活逻辑本身**——

* 运行时不在（FastAPI 进程、pytest）或显式关掉落盘时，什么都不做；
* 注册表里还活着的 dict 会被写盘，**且被强引用攥住**（弱引用注册表的条目因此不会
  被 GC 掉后被静默丢弃 —— 这正是 2026-09-22 那次"checkpoint 从不落盘"的成因）；
* 单个 dict 写失败不影响其余，失败数如实返回；
* ``ensure_checkpoint_persistence`` 幂等，重复调用不会起第二个线程。
"""

from __future__ import annotations

import weakref

import pytest

from src.app.agents import checkpoint_persistence as cp


class _FakeStore:
    """够用的假状态 dict：有 filename、能 sync（或按需抛错）。"""

    def __init__(self, filename: str, *, fail: bool = False, entries: int = 0) -> None:
        self.filename = filename
        self.fail = fail
        self.entries = entries
        self.synced = 0

    def sync(self) -> None:
        self.synced += 1
        if self.fail:
            raise OSError("disk on fire")


class _FakePersistence:
    def __init__(self, stores: dict[str, _FakeStore], *, disabled: bool = False) -> None:
        self._stores = {name: weakref.ref(store) for name, store in stores.items()}
        self.DISABLE_FILE_PERSISTENCE = disabled
        self.registered: list[str] = []

    def register_persistent_dict(self, store) -> None:
        self.registered.append(store.filename)


@pytest.fixture(autouse=True)
def _isolate_keep_alive(monkeypatch):
    """每个用例一份干净的强引用表，避免互相污染。"""
    monkeypatch.setattr(cp, "_KEEP_ALIVE", {})
    yield


@pytest.fixture
def _in_server(monkeypatch):
    """假装自己跑在 langgraph 服务进程里（保活只在那里生效，见 _enabled）。"""
    monkeypatch.setattr(cp, "_enabled", lambda: True)


def test_no_runtime_is_a_noop(monkeypatch):
    monkeypatch.setattr(cp, "_persistence_module", lambda: None)

    assert cp.sync_state_files() == (0, 0)


def test_disabled_persistence_is_a_noop(monkeypatch, _in_server):
    fake = _FakePersistence({}, disabled=True)
    monkeypatch.setattr(cp, "_persistence_module", lambda: fake)
    monkeypatch.setattr(cp, "_state_dicts", lambda: pytest.fail("不该碰任何 store"))

    assert cp.sync_state_files() == (0, 0)


def test_syncs_registered_stores_and_holds_them_alive(monkeypatch, _in_server):
    store = _FakeStore(".langgraph_api/.langgraph_checkpoint.1.pckl", entries=3)
    fake = _FakePersistence({store.filename: store})
    monkeypatch.setattr(cp, "_persistence_module", lambda: fake)
    monkeypatch.setattr(cp, "_state_dicts", lambda: [(store.filename, store)])

    ok, failed = cp.sync_state_files()

    assert (ok, failed) == (1, 0)
    assert store.synced == 1
    # 强引用：弱引用注册表里那条不会因为没人持有就被丢掉
    assert cp._KEEP_ALIVE[store.filename] is store
    assert fake.registered == [store.filename]


def test_one_failure_does_not_stop_the_others(monkeypatch, _in_server):
    good = _FakeStore(".langgraph_api/.langgraph_ops.pckl")
    bad = _FakeStore(".langgraph_api/store.pckl", fail=True)
    fake = _FakePersistence({good.filename: good, bad.filename: bad})
    monkeypatch.setattr(cp, "_persistence_module", lambda: fake)
    monkeypatch.setattr(
        cp, "_state_dicts", lambda: [(good.filename, good), (bad.filename, bad)]
    )

    ok, failed = cp.sync_state_files()

    assert (ok, failed) == (1, 1)
    assert good.synced == 1 and bad.synced == 1


def test_dead_weakrefs_are_skipped(monkeypatch, _in_server):
    """注册表里已失效的条目不会把保活搞崩（运行时对它们就是静默丢弃）。"""
    live = _FakeStore(".langgraph_api/.langgraph_ops.pckl")
    dead = _FakeStore(".langgraph_api/.langgraph_checkpoint.2.pckl")
    fake = _FakePersistence({live.filename: live, dead.filename: dead})
    del dead  # 让弱引用失效
    monkeypatch.setattr(cp, "_persistence_module", lambda: fake)
    monkeypatch.setattr(cp, "_state_dicts", lambda: [(live.filename, live)])

    assert cp.sync_state_files() == (1, 0)


def test_ensure_is_idempotent(monkeypatch, _in_server):
    fake = _FakePersistence({})
    monkeypatch.setattr(cp, "_persistence_module", lambda: fake)
    monkeypatch.setattr(cp, "_state_dicts", lambda: [])
    monkeypatch.setattr(cp, "_keeper_loop", lambda: None)  # 不真的起循环
    monkeypatch.setattr(cp, "_started", False)

    assert cp.ensure_checkpoint_persistence() is True
    assert cp.ensure_checkpoint_persistence() is False


def test_ensure_skips_when_runtime_missing(monkeypatch, _in_server):
    monkeypatch.setattr(cp, "_persistence_module", lambda: None)
    monkeypatch.setattr(cp, "_started", False)

    assert cp.ensure_checkpoint_persistence() is False


def test_does_nothing_outside_the_langgraph_server(monkeypatch):
    """FastAPI / pytest / CLI 进程里一律不动手：多进程写同一批 pckl 只会互相抹掉。"""
    monkeypatch.setattr(cp, "_persistence_module", lambda: _FakePersistence({}))
    monkeypatch.setattr(cp, "_enabled", lambda: False)
    monkeypatch.setattr(cp, "_started", False)

    assert cp.sync_state_files() == (0, 0)
    assert cp.ensure_checkpoint_persistence() is False
