"""会话 checkpoint 落盘保活 —— 把"重启即失忆"这件事堵死。

## 现象与定位（2026-09-22）

平台用 ``langgraph_api.server:app`` 起服务，运行时是 ``langgraph_runtime_inmem``。
这套运行时自带一套"存盘"机制：把状态 dict 注册进 ``_persistence._stores``，由一个
10 秒一次的刷盘线程写成 ``.langgraph_api/*.pckl``，下次启动由各自的构造逻辑读回。

实测下来这套机制在本机**只覆盖了 ops 存储**：``.langgraph_ops.pckl``（线程记录、
运行队列）每 10 秒刷新，而 ``.langgraph_checkpoint.{1,2,3}.pckl``（会话状态本体）、
``store.pckl``、``.langgraph_retry_counter.pckl`` 从头到尾没被写过 —— 即使它们已经
注册在 ``_stores`` 里、对象活着、``flag='c'``、手动 ``sync()`` 立刻就能写出来。

后果不是"慢"或"丢几条"，而是**重启服务 = 所有会话的模型上下文清零**：界面看着一切
正常（消息在 SQLite 里有镜像，历史照旧显示），但回到旧会话发"继续"，agent 只收到这
一句，前面聊过的全看不见 —— 用户看到的就是"它不记得了"。

## 为什么不只是"多刷一次盘"

运行时用的是**弱引用**注册表（``_stores[key] = weakref.ref(d)``），刷盘循环对失效
条目是静默丢弃。也就是说，只要没有别人攥着这些 dict，它们随时可能被 GC 掉，注册表
里就没有了 —— 这正好解释"注册过却没写"。所以这里做的是两件事：

1. **攥住**：我们拿到对象就存进 ``_KEEP_ALIVE``，弱引用不会失效；
2. **写盘**：每个对象逐一 ``sync()``（逐条 try/except，单个失败不拖累其余）。

退出时再收一次尾（``atexit``），避免"刚写完 checkpoint 就重启"。

## 为什么不换成 SqliteSaver 之类的持久化 checkpointer

那需要新装 ``langgraph-checkpoint-sqlite`` 依赖并改 ``LANGGRAPH_CHECKPOINTER`` 配置。
代价不小，而这里缺的只是"把已经存在的对象写下去"这一步 —— 用同一个 dict 再写一次
文件不会和运行时自带逻辑冲突（它自己写的就是同一个快照）。
"""

from __future__ import annotations

import atexit
import logging
import sys
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

#: 与运行时自带的刷盘间隔一致（``_persistence._flush_interval``）
INTERVAL_SEC = 10
#: 心跳日志间隔（每多少次刷盘打一行日志）
HEARTBEAT_EVERY = 6

#: ``filename -> 状态 dict`` 的**强引用**。见模块 docstring：运行时的注册表是弱引用，
#: 没人攥着就会被 GC，然后被它的刷盘循环静默丢掉。
_KEEP_ALIVE: dict[str, Any] = {}

_lock = threading.Lock()
_started = False


def _persistence_module():
    """运行时的 ``_persistence`` 模块；不在 langgraph 服务进程里时返回 None。

    FastAPI、pytest 这些进程根本没加载运行时，导入即失败，直接跳过。
    """
    try:
        from langgraph_runtime_inmem import _persistence  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — 导入失败只意味着"这里不需要保活"
        return None
    return _persistence


def _state_dicts() -> list[tuple[str, Any]]:
    """要保活的状态 dict，``(filename, dict)`` 列表。

    只覆盖**运行时刷盘漏掉的那部分**：

    * ``checkpoint.MEMORY`` —— 会话状态本体（storage / writes / blobs 三个分片），
      也就是"重启即失忆"的直接原因。这份对象是第一次用到 checkpointer 时才构造的，
      而构造时就地把磁盘内容读了回来（``factory`` 里 ``d.load()``），所以我们拿到它
      时内容已经是"磁盘 + 内存"的并集，写回去不会丢任何东西。
    * ``store.STORE`` —— 长期记忆/向量存储，同理在构造时读盘。

    **ops 存储（``.langgraph_ops.pckl``，线程记录）与重试计数不在保活范围内**，理由
    不是"不重要"，而是**它们必须由运行时自己写**：``GlobalStore`` 在 import 时构造
    并清空（``clear()``），真正的磁盘内容要等 ``database.connect()`` 里的 ``load()``
    才回来 —— 中间这段时间谁写谁就把已有记录抹掉。2026-09-22 这个保活模块的第一版
    正是踩了这一步：启动时替运行时写了一次空的 ops，把已有的线程记录清了。运行时
    自己的刷盘循环对 ops 一直是正常的（实测每 10 秒稳定刷新），交给它就好。
    """
    found: dict[str, Any] = {}

    try:
        from langgraph_runtime_inmem import checkpoint as checkpoint_mod  # noqa: PLC0415

        saver = getattr(checkpoint_mod, "MEMORY", None)
        for attr in ("storage", "writes", "blobs"):
            candidate = getattr(saver, attr, None)
            filename = getattr(candidate, "filename", None)
            if filename:
                found[filename] = candidate
    except Exception:  # noqa: BLE001
        pass

    try:
        from langgraph_runtime_inmem.store import STORE  # noqa: PLC0415

        for candidate in (STORE._data, STORE._vectors):
            filename = getattr(candidate, "filename", None)
            if filename:
                found[filename] = candidate
    except Exception:  # noqa: BLE001
        pass

    return sorted(found.items())


def _enabled() -> bool:
    """保活是否该在**本进程**里跑。

    判据是"我在 langgraph 服务里" —— 只有它会 import ``langgraph_api.server``。
    FastAPI、pytest、命令行脚本用的是同一个 venv，也就 import 得到同一套运行时，
    但它们和正在跑的服务**抢同一批 ``*.pckl`` 文件**：实测会撞出
    ``PermissionError: .langgraph_api\\store.pckl.tmp``，而且它们内存里那份还不是
    服务里那份 —— 谁写谁就把对方的状态抹了。所以这里收紧到只看服务进程。
    """
    if "langgraph_api.server" not in sys.modules:
        return False
    persistence = _persistence_module()
    return persistence is not None and not getattr(
        persistence, "DISABLE_FILE_PERSISTENCE", False
    )


def sync_state_files() -> tuple[int, int]:
    """把当前所有状态 dict 写一遍盘，返回 ``(成功数, 失败数)``。"""
    if not _enabled():
        return (0, 0)

    persistence = _persistence_module()
    if persistence is None or getattr(persistence, "DISABLE_FILE_PERSISTENCE", False):
        return (0, 0)

    ok = failed = 0
    for filename, store in _state_dicts():
        # 攥住（弱引用注册表里的条目因此不会失效），并补登记一次（幂等），
        # 让运行时自带的刷盘循环也带上它。
        _KEEP_ALIVE[filename] = store
        try:
            persistence.register_persistent_dict(store)
        except Exception:  # noqa: BLE001
            pass
        try:
            store.sync()
            ok += 1
        except Exception as exc:  # noqa: BLE001 — 单个失败不拖累其余
            failed += 1
            logger.warning("会话状态落盘失败: %s (%s)", filename, exc)
    return (ok, failed)


def _keeper_loop() -> None:
    rounds = 0
    while True:
        time.sleep(INTERVAL_SEC)
        rounds += 1
        try:
            ok, failed = sync_state_files()
        except Exception as exc:  # noqa: BLE001 — 保活线程绝不能死
            logger.warning("会话状态落盘保活异常（已忽略，下轮继续）: %s", exc)
            continue
        if ok and rounds % HEARTBEAT_EVERY == 0:
            logger.info(
                "会话状态落盘保活：%s 个状态文件 / %s 项", ok, len(_KEEP_ALIVE)
            )


def ensure_checkpoint_persistence() -> bool:
    """幂等启动保活；返回本次是否真的启动（重复调用返回 False）。"""
    global _started
    with _lock:
        if _started:
            return False
        if not _enabled() or _persistence_module() is None:
            return False
        _started = True

    try:
        sync_state_files()
    except Exception as exc:  # noqa: BLE001 — 起不来也不能拦服务启动
        logger.warning("会话状态首次落盘失败: %s", exc)

    atexit.register(sync_state_files)
    threading.Thread(
        target=_keeper_loop, name="checkpoint-persistence-keeper", daemon=True
    ).start()
    logger.info(
        "会话状态落盘保活已启动（每 %s 秒一次；本机运行时自带的刷盘只覆盖 ops 存储）",
        INTERVAL_SEC,
    )
    return True
