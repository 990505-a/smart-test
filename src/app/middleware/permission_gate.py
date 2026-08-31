"""Permission gate（两档权限选择器 + 只读命令白名单）.

会话级档位通过 configurable.permission_mode 传入（前端 ?permission= 查询参数）：

- **workspace_write**（默认）：文件写工具自由放行——backend 已把文件操作
  限制在 workspace 目录内；execute 按"命令是否有副作用"细分——纯只读
  探查命令（wc/head/grep/git log 等）白名单自动放行，其余弹审批。
- **full_access**：全部自动放行（前端切换到该档需要二次确认，后端不做
  二次校验——与 dsh 的 RiskConfirmation 一样属于 UI 层确认）。

2026-08 收敛说明：原 read_only 档已移除。用例工作流（需求包/用例文档/
sidecar）必须落盘，只读档等于关闭整个流程，没有真实使用场景；防写代码
仓库靠的是 /repo 只读挂载（结构层），不靠权限档位。旧链接携带
?permission=read_only 会回落到默认 workspace_write。

其余对齐的 dsh 原则：

- **授权严格单次**（allowed-once，没有 allow-always）。
- **拒绝对模型可见**：拒绝作为 status=error 的 ToolMessage 返回，模型
  会换路径而不是无限重试（denial as model-facing contract）。
- **防链式绕过**：管道/&&/||/; 链的每一段都必须命中白名单；任何一段
  含输出重定向（> >>）或命令替换（$( ) 反引号）时整条命令都要审批。
- 兼容旧参数：configurable.execute_approval="off" 等价 full_access；
  read_only 同样按兼容输入回落 workspace_write。

已知边界（与 dsh 一致的取舍）：白名单是前缀启发式而非完整 shell 语法
解析；文件面的"workspace 限制"来自 backend 路由（软限制），非 OS 沙箱。
"""

from __future__ import annotations

import re

from langchain.agents.middleware import AgentMiddleware, HumanInTheLoopMiddleware
from langgraph.config import get_config

VALID_PERMISSION_MODES = ("workspace_write", "full_access")

# 前缀白名单：workspace_write 档下智能体可不经审批执行的命令。
# 三类：
# 1. 只读探查——wc/head/grep 等，只看现状不改变世界（git 单独按子命令判断，
#    见 _git_segment_safe，因为真实用法带 -C <path> 全局参数）；
# 2. lark-cli——飞书 skill 的全部操作走它，登录态（用户自己授权的账号
#    与 scope）就是权限边界；
# 3. 环境版本查询。
# 注意 "git branch" 不放行：裸 branch 可建/删分支，属于写操作；
# "find" 不放行：-delete/-exec 是写原语，前缀匹配拦不住，代码定位用 glob 工具。
SAFE_COMMAND_PREFIXES = (
    # 只读探查（文件与目录）
    "cat ",
    "head ",
    "tail ",
    "wc ",
    "ls",
    "dir ",
    "grep ",
    "rg ",
    "file ",
    "stat ",
    "du ",
    "df ",
    "sort",
    "uniq",
    "cut ",
    "sed -n ",           # 仅显式打印模式；其余 sed 子命令（如 -i 写文件）不放行
    "awk ",
    "type ",
    "echo",              # 无害：输出重定向已被副作用检测单独拦截
    # 平台集成
    "lark-cli",
    "lark-cli.exe",
    # 环境查询
    "node --version",
    "python --version",
    "where ",
    "whoami",
)

# git 只读子命令：status/log/diff/show 等。remote 不在列（remote add 是写）。
_READ_ONLY_GIT_SUBCOMMANDS = frozenset(
    {"status", "log", "diff", "show", "rev-parse", "ls-files", "blame"}
)

_CHAIN_SPLIT = re.compile(r"&&|\|\||[;|\n]")
# 无害的 stderr 丢弃（只读命令常用）：先剥离再查副作用，避免 rg ... 2>/dev/null
# 这类纯读取命令被 ">" 检测误拦到人工审批。
_BENIGN_STDERR_DISCARD = re.compile(r"\s*\d?>\s*(?:/dev/null|nul)\b", re.IGNORECASE)
# 副作用信号：输出重定向 / 命令替换 / 反引号。命中任一则整条命令审批。
_SIDE_EFFECT_RE = re.compile(r">|\$\(|`")


def _git_segment_safe(segment: str) -> bool:
    """git 命令按子命令判断：跳过 -C <path> 等全局参数后的首个子命令只读才放行。"""
    tokens = segment.split()
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token == "-C":
            index += 2  # -C 带一个路径参数
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token in _READ_ONLY_GIT_SUBCOMMANDS
    return False


def _segment_safe(segment: str) -> bool:
    if segment == "git" or segment.startswith("git "):
        return _git_segment_safe(segment)
    return segment.startswith(SAFE_COMMAND_PREFIXES)


def _command_segments(command: str) -> list[str]:
    return [seg.strip() for seg in _CHAIN_SPLIT.split(command) if seg.strip()]


def _all_segments_safe(command: str) -> bool:
    # 先剥离无害的 stderr 丢弃，再整条查副作用信号：
    # cat x > y 的每一段前缀都是安全的，输出重定向才是危险源。
    probe = _BENIGN_STDERR_DISCARD.sub(" ", command)
    if _SIDE_EFFECT_RE.search(probe):
        return False
    # 段落拆分仍用原始命令（保持路径/参数原样）。
    segments = _command_segments(command)
    return bool(segments) and all(_segment_safe(seg) for seg in segments)


def _permission_mode() -> str:
    """Read the per-conversation permission mode from the run config."""
    try:
        configurable = (get_config() or {}).get("configurable") or {}
        mode = str(configurable.get("permission_mode", "")).strip().lower()
        if mode in VALID_PERMISSION_MODES:
            return mode
        # 兼容旧开关：execute_approval=off → full_access；
        # 已废弃的 read_only → 回落默认 workspace_write
        if str(configurable.get("execute_approval", "")).strip().lower() == "off":
            return "full_access"
    except Exception:  # noqa: BLE001 — 非图执行上下文（如单测）用默认档
        pass
    return "workspace_write"


def _needs_execute_approval(request) -> bool:
    """when 谓词：True=该 execute 调用需要人工审批。"""
    mode = _permission_mode()
    if mode == "full_access":
        return False
    # workspace_write：只读白名单命中自动放行
    command = str((request.tool_call.get("args") or {}).get("command", ""))
    return not _all_segments_safe(command)


def build_permission_middleware() -> AgentMiddleware:
    """两档权限门：只门控 execute；文件写由 workspace 路由兜底。"""
    return HumanInTheLoopMiddleware(
        interrupt_on={
            "execute": {
                "allowed_decisions": ["approve", "reject"],
                "when": _needs_execute_approval,
                "description": "命令执行需要审批",
            },
        },
        description_prefix="操作需要审批",
    )
