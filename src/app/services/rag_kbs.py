"""知识库注册表 —— 一个知识库 = 一个 LightRAG 实例 + 一个 workspace + 一个端口。

**为什么是"一库一实例"**：LightRAG 官方确实支持多库隔离，但隔离单位是
*服务实例*（`--workspace` / `WORKSPACE`，启动时定死），不是请求参数——
`/query`、`/documents/*`、`/graph/*` 的请求体里**没有** workspace 字段
（可用 `GET /openapi.json` 自查：0 个模型带这个字段），自带 WebUI 里也只是展示
而已。官方的多站点部署（docs/MultiSiteDeployment.md）走的就是"一个站点一个实例、
端口/挂载路径分开"。所以"两个项目别混在一起"在这里 = 两个实例。

**隔离靠 workspace，不靠目录**：LightRAG 的文件类存储统一按
``working_dir/[<workspace>/]<文件>`` 落盘（json_kv / json_doc_status / networkx
三个实现都是这个约定），上传文件的暂存目录同理（``inputs/<workspace>/``）。
所以所有实例共用一个 ``lightrag_working_dir``，各自的 workspace 天然分家：
``workspace/default/rag/ruoyi/kv_store_full_docs.json``。默认库的 workspace 是
空串——这是 LightRAG 的"全局命名空间"，也是升级前就有的行为，数据一个字节都不动。

**事实源是文件**（``workspace/<space>/rag_kbs.json``，与 ``assembly.json`` 同级）：
启动器要在**没有数据库**的前提下按它拉起进程，而平台（FastAPI）负责写它。
这条"文件 + 用的时候重读"的桥与装配目录、记忆清单、.env 是同一套，本机与容器
两种部署都成立。

``workspace`` 名会经过 LightRAG 自己的 sanitize（非字母数字下划线换成 ``_``），
所以连字符在库里是下划线：key ``ruoyi-web`` → workspace ``ruoyi_web``。
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from src.app.core.config import settings
from src.app.core.workspace import get_workspace_dir

logger = logging.getLogger(__name__)

#: 注册表文件名（放在 ``workspace/<space>/`` 下）
KBS_FILENAME = "rag_kbs.json"

#: 默认库的 key：启动器里的服务名就是 ``lightrag``（与 core/integrations.py 的
#: ``launch="lightrag"`` 对应），端口也是历史值 :5014。
DEFAULT_KB_KEY = "default"
DEFAULT_KB_PORT = 5014

#: 新库的端口从 5021 往上找空位。5010-5016 是平台自己的服务
#: （控制台/智能体/后端/前端/知识库默认实例/浏览器执行器/Unity 桥），一律不占。
KB_PORT_BASE = 5021
KB_PORT_MIN = 5014
KB_PORT_MAX = 5060
RESERVED_PORTS = frozenset({5010, 5011, 5012, 5013, 5015, 5016, 9749})

#: key 同时是 LightRAG 的 workspace 名与目录名，白名单比 safe_segment 更紧：
#: 只允许小写字母/数字/下划线/连字符（大写会让 "ruoyi" 与 "Ruoyi" 变成两个库）。
_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")


@dataclass(frozen=True)
class KB:
    """一个知识库 = 一个 lightrag-server 进程。"""

    key: str
    label: str
    port: int
    description: str = ""

    @property
    def workspace(self) -> str:
        """LightRAG 的 WORKSPACE（数据命名空间）。

        默认库留空串：LightRAG 里空 workspace 表示全局命名空间，升级前就是这个
        值，改掉它等于把老数据搬走——不是"重命名"，是"消失"。
        """
        if self.key == DEFAULT_KB_KEY:
            return ""
        return re.sub(r"[^a-zA-Z0-9_]", "_", self.key)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def service_name(self) -> str:
        """启动器里的服务名（日志文件名、控制台卡片都按它区分）。"""
        return "lightrag" if self.key == DEFAULT_KB_KEY else f"lightrag-{self.key}"

    @property
    def webui_url(self) -> str:
        return f"{self.base_url}/webui"

    @property
    def settings_url(self) -> str:
        """LightRAG 自带界面里的「RAG 设置」页（平台注入的 overlay，见 tools/lightrag-ui）。"""
        return f"{self.base_url}/webui/rag-settings.html"

    @property
    def data_dir(self) -> str:
        """数据目录（相对项目根，给人看/排障用）。"""
        base = settings.lightrag_working_dir.rstrip("/")
        return f"{base}/{self.workspace}" if self.workspace else base

    @property
    def inputs_dir(self) -> str:
        """上传文件暂存目录（LightRAG 自己在 workspace 下开子目录）。"""
        return f"inputs/{self.workspace}" if self.workspace else "inputs"

    def to_dict(self) -> dict:
        return {
            **self.to_row(),
            "workspace": self.workspace,
            "base_url": self.base_url,
            "webui_url": self.webui_url,
            "settings_url": self.settings_url,
            "service_name": self.service_name,
            "data_dir": self.data_dir,
            "inputs_dir": self.inputs_dir,
        }

    def to_row(self) -> dict:
        """落盘/保存用的可编辑字段（派生字段不写进文件）。"""
        return {"key": self.key, "label": self.label, "port": self.port,
                "description": self.description}


# ---------------------------------------------------------------------------
# 读写（文件 + mtime 缓存）
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[tuple[int, int] | None, tuple[KB, ...]]] = {}


def kbs_path(space_id: str | None = None) -> Path:
    return get_workspace_dir(space_id) / KBS_FILENAME


def _seed() -> tuple[KB, ...]:
    """没有注册表文件时的默认库：沿用 lightrag_* 三项设置的老行为。"""
    port = urlparse(settings.lightrag_base_url).port or DEFAULT_KB_PORT
    return (KB(key=DEFAULT_KB_KEY, label="默认知识库", port=port,
               description="沿用 LIGHTRAG_BASE_URL / LIGHTRAG_WORKING_DIR（升级前的单库行为）"),)


def load_kbs(space_id: str | None = None) -> tuple[KB, ...]:
    """读注册表。文件不存在 / 读不动 / 坏 JSON 都回落到默认库，绝不抛。

    启动器与平台两侧都走这里，所以"读不动"必须降级而不是崩：一个坏 JSON 不该
    让知识库在控制台上消失。
    """
    path = kbs_path(space_id)
    space = space_id or path.parent.name
    try:
        stat = path.stat()
        stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
    except OSError:
        stamp = None

    cached = _cache.get(space)
    if cached is not None and cached[0] == stamp:
        return cached[1]

    kbs = _seed()
    if stamp is not None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = raw.get("kbs") if isinstance(raw, dict) else raw
            kbs = _rows_to_kbs(rows or [])
        except Exception as exc:  # noqa: BLE001 —— 配置文件坏了不该拦服务
            logger.warning("[rag-kbs] %s 读取失败，按默认库继续: %s", path, exc)
            kbs = _seed()

    _cache[space] = (stamp, kbs)
    return kbs


def save_kbs(rows: list[dict], space_id: str | None = None) -> tuple[KB, ...]:
    """写注册表（临时文件 + 原子替换）。校验不过抛 ValueError。"""
    errors = validate(rows)
    if errors:
        raise ValueError("；".join(errors))
    kbs = _rows_to_kbs(rows)
    path = kbs_path(space_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps({"kbs": [k.to_row() for k in kbs]},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    _cache.pop(space_id or path.parent.name, None)
    logger.info("[rag-kbs] 已保存 %d 个知识库: %s",
                len(kbs), ", ".join(f"{k.key}:{k.port}" for k in kbs))
    return load_kbs(space_id)


def invalidate_cache() -> None:
    _cache.clear()


def _rows_to_kbs(rows) -> tuple[KB, ...]:
    kbs: list[KB] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        try:
            port = int(row.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        kbs.append(KB(key=key, label=str(row.get("label") or key).strip() or key,
                      port=port, description=str(row.get("description") or "").strip()))
    return tuple(kbs)


# ---------------------------------------------------------------------------
# 校验 / 查询 / 建议
# ---------------------------------------------------------------------------

def validate(rows: list[dict]) -> list[str]:
    """返回人话错误列表（空 = 通过）。设置页保存前调用。"""
    errors: list[str] = []
    if not rows:
        return ["至少保留一个知识库"]
    seen_keys: set[str] = set()
    seen_ports: set[int] = set()
    for row in rows:
        key = str(row.get("key") or "").strip()
        if not _KEY_RE.match(key):
            errors.append(f"知识库 key {key!r} 不合法：只允许小写字母/数字/下划线/连字符，"
                          f"以字母或数字开头，最长 32 字符")
            continue
        if key in seen_keys:
            errors.append(f"知识库 key 重复: {key}")
        seen_keys.add(key)

        try:
            port = int(row.get("port") or 0)
        except (TypeError, ValueError):
            port = 0
        if not (KB_PORT_MIN <= port <= KB_PORT_MAX):
            errors.append(f"{key} 的端口 {port} 超出范围（{KB_PORT_MIN}-{KB_PORT_MAX}）")
        elif port in RESERVED_PORTS:
            errors.append(f"{key} 的端口 {port} 被平台服务占用（5010-5016 / 9749）")
        if port in seen_ports:
            errors.append(f"{key} 的端口 {port} 与其他知识库重复")
        seen_ports.add(port)
    return errors


def get_kb(key: str | None, space_id: str | None = None) -> KB | None:
    """按 key 找库；空 key = 默认库。找不到返回 None（调用方给可读错误）。"""
    kbs = load_kbs(space_id)
    wanted = (key or "").strip()
    if not wanted:
        return kbs[0]
    for kb in kbs:
        if kb.key == wanted:
            return kb
    return None


def default_kb(space_id: str | None = None) -> KB:
    return load_kbs(space_id)[0]


def describe_keys(space_id: str | None = None) -> str:
    """给模型看的库清单（一行一个），工具报错时拼进提示。"""
    return "、".join(f"{k.key}（{k.label}）" for k in load_kbs(space_id))


def suggest_kb(rows: list[dict] | None = None) -> dict:
    """新增库的建议值：端口挑一个空位，key/label 留空由用户填。"""
    kbs = _rows_to_kbs(rows) if rows else load_kbs()
    used = {k.port for k in kbs} | set(RESERVED_PORTS)
    port = next((p for p in range(KB_PORT_BASE, KB_PORT_MAX + 1) if p not in used),
                KB_PORT_MAX)
    return {"key": "", "label": "", "port": port, "description": ""}


def to_rows(kbs: tuple[KB, ...] | list[KB]) -> list[dict]:
    return [k.to_row() for k in kbs]
