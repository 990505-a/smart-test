"""Permission gate（两档权限选择器 + 只读命令白名单）.

会话级档位通过 configurable.permission_mode 传入（前端 ?permission= 查询参数）：

- **workspace_write**（默认）：**工作区是自由区，越界才拦**。
  文件工具分两面：写/改/删（write_file / edit_file / delete）只在目标路径
  落在「允许写入的根」内时自动放行，越界一律弹审批；读取不拦——探查代码、
  读参考文档是正常工作，拦了只会天天弹卡片。execute 按"命令是否有副作用"
  细分——纯只读探查命令（wc/head/grep/git log 等）白名单自动放行，其余弹
  审批。lark-cli 只放行搜索/读取类子命令（_lark_segment_safe）：飞书写入类
  操作（建/改/删/上传）一律弹审批，这是输入框「飞书检索」开关只读
  语义的命令层兜底；开关本身只控制智能体是否主动去飞书找需求
  （configurable.feishu_cli == "readonly" 时注入检索指引）。
- **full_access**：全部自动放行（前端切换到该档需要二次确认，后端不做
  二次校验——与 dsh 的 RiskConfirmation 一样属于 UI 层确认）。

⚠️ **文件面的边界不来自 backend，只来自本模块**。后端是 ``virtual_mode=False``
的真实路径语义（见 ``agents/workspace_backend.py``），它**有意**不做路径限制
——"完全访问档能操作工作区之外"正是靠这一点成立。官方文档对
``virtual_mode=False`` 的原话是 "provides no security against an agent choosing
paths outside root_dir… agents have unrestricted filesystem access"。

所以别再写"backend 已经把文件操作限制在工作区内"这类假设：那是假的，两层
互相以为对方在管、中间就是空的。越界要审批这件事**只有下面的 when 谓词负责**。

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
解析；文件面的边界是**审批**而非沙箱——用户在卡片上点「允许一次」之后
该次调用就真的越界执行了。这是有意的：决定权在人手里，不是禁止。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# 不再 import HumanInTheLoopMiddleware：审批走 create_deep_agent(interrupt_on=...)，
# 中间件由框架自己装（见文件末尾 build_interrupt_on 的说明）。
from langgraph.config import get_config

from src.app.core.config import settings

VALID_PERMISSION_MODES = ("workspace_write", "full_access")

# 前缀白名单：workspace_write 档下智能体可不经审批执行的命令。
# 三类：
# 1. 只读探查——wc/head/grep 等，只看现状不改变世界（git 单独按子命令判断，
#    见 _git_segment_safe，因为真实用法带 -C <path> 全局参数）；
# 2. lark-cli——飞书 skill 的操作走它，但只放行只读子命令（搜索/读取/识别，
#    见 _lark_segment_safe）：写操作（建/改/删/上传/移动/权限）一律弹审批，
#    这是「飞书检索开关」只读语义的命令层兜底；
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

# lark-cli 只读 shortcut（按 lark-drive / lark-doc 技能中的实际命令形态）。
_LARK_READONLY_SHORTCUTS = frozenset({
    # docs：读正文 / 解析统计 / 历史查询（+history-revert 是写，不在列）
    "+fetch", "+script", "+history-list", "+history-revert-status",
    "+media-preview",
    # drive：搜文档 / 识别 URL / 权限设置查询 / 版本历史 / 封面规格
    "+search", "+inspect", "+permission-get-setting", "+version-history",
    "+cover",
})
# lark-cli typed 资源调用的只读方法名（drive file.statistics get 等）。
_LARK_READONLY_METHODS = frozenset({"get", "list", "search"})
# 取值型全局 flag：跳过 flag 本身 + 它的值。
_LARK_VALUE_FLAGS = frozenset({"--as", "--identity", "--config", "--profile"})


def _lark_segment_safe(segment: str) -> bool:
    """lark-cli 命令按子命令判断：只放行搜索/读取类，写操作交审批。

    形态参照 `lark-cli --help` 与 /skills/lark-* 技能：
    ``lark-cli [全局flag] <domain> [+shortcut|resource method] [flags]``
    以及裸 API：``lark-cli api GET/POST/... <path>``。
    解析是前缀启发式：认不出的一律不放行（保守方向，最坏多弹一次审批）。
    """
    tokens = segment.split()
    index = 1  # tokens[0] = lark-cli / lark-cli.exe
    # 跳过全局 flag；--as user 之类取值型 flag 连值一起跳过
    while index < len(tokens) and tokens[index].startswith("-"):
        if tokens[index].lower() in _LARK_VALUE_FLAGS:
            index += 2
        else:
            index += 1
    if index >= len(tokens):
        return False  # 裸 lark-cli 无子命令：不放行（正常用法都会带子命令）
    head = tokens[index].lower()
    if head in ("help", "schema", "--help", "--version", "-v"):
        return True
    if head == "auth":
        nxt = tokens[index + 1].lower() if index + 1 < len(tokens) else ""
        return nxt == "status"
    if head == "api":
        method = tokens[index + 1].upper() if index + 1 < len(tokens) else ""
        return method == "GET"
    if head == "docs":
        nxt = tokens[index + 1].lower() if index + 1 < len(tokens) else ""
        return nxt in _LARK_READONLY_SHORTCUTS
    if head == "drive":
        nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
        if nxt.startswith("+"):
            return nxt.lower() in _LARK_READONLY_SHORTCUTS
        # typed 调用：drive <resource> <method>，看方法名是否只读
        method = tokens[index + 2].lower() if index + 2 < len(tokens) else ""
        return method in _LARK_READONLY_METHODS
    if head == "mindnotes":
        sub = [t.lower() for t in tokens[index + 1:index + 3]]
        return sub == ["nodes", "list"]
    # minutes / note 是 CLI 自述的纯读取域（会议纪要/转写检索）
    if head in ("minutes", "note"):
        return True
    return False

# 无害的 stderr 丢弃（只读命令常用）：先剥离再查副作用，避免 rg ... 2>/dev/null
# 这类纯读取命令被 ">" 检测误拦到人工审批。
_BENIGN_STDERR_DISCARD = re.compile(r"\s*\d?>\s*(?:/dev/null|nul)\b", re.IGNORECASE)


def _scan_command(command: str) -> tuple[list[str], bool]:
    """按**引号外**的控制符切分命令，并报告引号外是否存在副作用字符。

    返回 ``(段列表, 有副作用)``。

    不能用 ``re.split(r"&&|\\|\\||[;|\\n]")``：它不认引号，而 ``rg -n "a|b" path``
    里正则的交替符 ``|`` 是引号内的普通字符，被当成管道切开后，后半段自然不命中
    白名单——纯只读检索于是被判成"需要审批"。实测就是这条：agent 查源码时连发两条
    ``rg -n "x|y|z" ...``，都被拦下弹审批，而并行两条又正好引爆了前端"只回一条
    decision"的 bug（ValueError: Number of human decisions (1) does not match ...）。

    ``>`` / ``$(`` / 反引号同理，只在引号外才算副作用信号。
    """
    segments: list[str] = []
    buf: list[str] = []
    quote = ""  # "" | "'" | '"'
    side_effect = False
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            buf.append(ch)
            # 双引号内反斜杠仍是转义；单引号内一切原样
            if ch == "\\" and quote == '"' and i + 1 < n:
                buf.append(command[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        if ch == ">" or ch == "`" or (ch == "$" and command[i + 1:i + 2] == "("):
            side_effect = True
        if command[i:i + 2] in ("&&", "||"):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if ch in (";", "|", "\n"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segments.append("".join(buf))
    return [seg.strip() for seg in segments if seg.strip()], side_effect


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


_LARK_BINS = ("lark-cli", "lark-cli.exe")


def _segment_safe(segment: str) -> bool:
    first = segment.split()[0] if segment.split() else ""
    if first == "git" or first == "git.exe":
        return _git_segment_safe(segment)
    if first in _LARK_BINS:
        return _lark_segment_safe(segment)
    return segment.startswith(SAFE_COMMAND_PREFIXES)


def _command_segments(command: str) -> list[str]:
    return _scan_command(command)[0]


def _all_segments_safe(command: str) -> bool:
    # 先剥离无害的 stderr 丢弃（rg ... 2>/dev/null 这类），再交给引号感知的扫描器：
    # cat x > y 的每一段前缀都是安全的，引号外的输出重定向才是危险源。
    probe = _BENIGN_STDERR_DISCARD.sub(" ", command)
    segments, side_effect = _scan_command(probe)
    if side_effect:
        return False
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


# ============================================================================
# 文件写入边界（write_file / edit_file / delete）
# ============================================================================
#: 会改动磁盘的官方文件工具。参数名统一是 ``file_path``
#: （见 deepagents 的 _FS_TOOL_PATH_ARGS）。delete 是**递归**语义
#: （官方描述："removes it and everything inside it, recursively…
#: this cannot be undone"），所以与写文件同一套判断：
#: 目标在工作区内 ⇒ 其后代也在，精确比较即可；目标在工作区外 ⇒ 拦。
_WRITE_TOOLS = ("write_file", "edit_file", "delete")


def _allowed_write_roots() -> list[Path]:
    """本次 run「允许写入的根」清单。命中任一即视为工作区内（免审批）。

    只有一个来源：**平台自己的工作区目录** ``settings.workspace_dir``
    （``workspace/{space}/`` —— 上传、用例文档、记忆、产物都在这儿）。

    挂载进来的仓库**不再**算自由区（2026-09）：这条规则过去是"工作区 = 我随手改的
    地方"时代的语义，而现在能挂进来的只剩**代码仓库**（工作区选择器已删除，挂载只
    来自对话页输入框旁的「代码图谱仓库」选择器）。平台的铁律是"不改被测仓库"，
    所以改写仓库内文件一律弹审批 —— 用户点「允许一次」照样能改，但那必须是人的
    决定，不该是"选个仓库顺手带来的权限"。完全访问档仍然全放行。
    """
    try:
        return [settings.workspace_dir.expanduser().resolve()]
    except Exception:  # noqa: BLE001 — 取不到就当没有自由区（fail-closed）
        return []


def _resolution_root() -> Path | None:
    """相对路径的解析基准 —— 与 backend 一致：挂了仓库就用仓库，否则平台工作区。

    注意这**不是**写权限：解析出绝对路径之后仍然要按 ``_allowed_write_roots``
    判断放不放行。两者分开正是因为"在哪解析"和"能不能写"现在不是一回事。
    """
    try:
        from src.app.agents.workspace_backend import mounted_workspace_path

        mounted = mounted_workspace_path()
    except Exception:  # noqa: BLE001 — 非图执行上下文（如单测）
        mounted = ""
    if mounted:
        candidate = Path(mounted).expanduser()
        if candidate.is_dir():
            return candidate.resolve()
    roots = _allowed_write_roots()
    return roots[0] if roots else None


def _resolve_write_target(raw: Any) -> Path | None:
    """把工具参数里的路径解析成绝对路径；解析不出来返回 None（调用方 fail-closed）。

    相对路径按工作区解析（真实路径语义下 backend 也是这么做的）；``..`` 与
    符号链接靠 ``resolve()`` 归一化——它会展开链接，所以指到工作区外的软链
    也会被正确判为越界。判不出来的一律交给人工，不猜。
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            base = _resolution_root()
            if base is None:
                return None
            candidate = base / candidate
        return candidate.resolve()
    except Exception:  # noqa: BLE001 — 非法路径（含 NUL、超长等）也交人工
        return None


def _needs_write_approval(request) -> bool:
    """when 谓词：True=该文件写入/删除调用需要人工审批。

    **fail-closed**：路径缺失、类型不对、解析失败、根清单为空、判断不出在不在
    工作区内，一律返回 True。与 ``_needs_execute_approval`` 同取向——多问一次
    只是烦，漏问一次不可逆。

    反面参考：deepagents 自己的 ``middleware/_fs_interrupt.py`` 在
    ``validate_path`` 抛 ValueError 时 return False（放行）。那是**虚拟路径**
    世界的自洽写法（畸形路径稍后会被文件工具本身拒绝）；我们是真实路径语义，
    而 ``validate_path`` 会拒绝 Windows 绝对路径（``D:\\...``）和任何含 ``..``
    的路径——照抄会在这些**合法**输入上静默跳过审批，正好在最该拦的地方开口。
    """
    if _permission_mode() == "full_access":
        return False
    args = request.tool_call.get("args") or {}
    target = _resolve_write_target(args.get("file_path"))
    if target is None:
        return True
    roots = _allowed_write_roots()
    if not roots:
        return True
    for root in roots:
        try:
            # 严格位于根**之内**才算自由区。根自身不算——删掉用户挂进来的整个
            # 工作区（或整个平台 workspace/，那里是全部用例与记忆）是要问一次的：
            # 用户给的是一条"在这干活"的路径，不是"把这个删掉"的授权。
            # 注：delete 是递归语义，目标在根内则其后代也在根内，精确比较足够。
            if root in target.parents:
                return False
        except Exception:  # noqa: BLE001 — 不同盘符等无法比较的情形按越界处理
            continue
    return True


def build_interrupt_on(human_gated_tools: dict[str, str] | None = None) -> dict[str, Any]:
    """构造 ``create_deep_agent(interrupt_on=...)`` 的配置。

    过去这里返回一个自己搭的 ``HumanInTheLoopMiddleware`` 塞进 middleware 列表——
    那是重造官方已有的轮子：``create_deep_agent`` 的 ``interrupt_on`` 参数就是干这个的，
    而且白拿三件事：

    1. 声明式子 agent 默认继承主 agent 的审批配置；
    2. 与 ``permissions`` 里 ``mode="interrupt"`` 的规则自动合并；
    3. 中间件插在官方栈该在的位置（memory / prompt-caching 之后），不会被我们手写的
       middleware 顺序打乱。

    白名单逻辑本身（``_needs_execute_approval``）官方没有对应物——它判断的是**命令内容**，
    官方文档把这类"内容检查"指向自定义中间件/后端策略钩子。所以它留在这里，只是改成
    通过 ``InterruptOnConfig.when`` 谓词交给官方中间件执行。

    Args:
        human_gated_tools: 需要人工确认的**业务动作**，形如
            ``{"approve_case_document": "批准用例文档需要你确认"}``。不可逆的业务操作
            （批准/发布）不必再跳去另一个页面点按钮，决定权仍在用户手里：智能体调用
            该工具时 run 会停在 interrupt 上，用户点「允许一次」才继续。

    Returns:
        可直接传给 ``create_deep_agent(interrupt_on=...)`` 的字典。
    """
    interrupt_on: dict[str, Any] = {
        "execute": {
            # edit 是官方支持的第三种决策（改完再批准）；前端目前只发 approve/reject，
            # 这里先放开，等审批卡片支持"改命令"时不用再动后端。
            "allowed_decisions": ["approve", "edit", "reject"],
            "when": _needs_execute_approval,
            "description": "命令执行需要审批",
        },
    }
    # 文件写入面：工作区内自由（"给个路径就能访问"），越界弹审批。
    # 官方 permissions= 做不到这件事——它构造期静态、且对实现了
    # SandboxBackendProtocol 的 backend 直接 NotImplementedError
    # （我们的 WorkspaceShellBackend 继承 LocalShellBackend，正是这种），
    # 所以边界只能由这里的 when 谓词承担。
    for _tool in _WRITE_TOOLS:
        interrupt_on[_tool] = {
            # 写文件时 edit（改完再批准）是有实际意义的：用户可以把内容改对了再放行。
            "allowed_decisions": ["approve", "edit", "reject"],
            "when": _needs_write_approval,
            "description": "在工作区之外写入或删除需要审批",
        }
    for tool_name, description in (human_gated_tools or {}).items():
        interrupt_on[tool_name] = {
            "allowed_decisions": ["approve", "reject"],
            "description": description,
        }
    return interrupt_on


def dynamic_gate_entries(tool_names: Iterable[str]) -> dict[str, Any]:
    """给"哪些工具要人工审批"生成 interrupt_on 条目 —— **每轮现查装配目录**。

    工具是否要审批现在是用户数据（能力编辑器里勾），而 ``interrupt_on`` 是构建期参数，
    所以每个候选工具都先登记一条，审批与否交给 ``when`` 谓词在每次工具调用时现查：
    用户在页面上勾一下，下一轮就生效，不用重启。

    读不出来时 ``is_tool_gated`` 返回 False（放行）—— 装配配置坏了不该把 run 卡死。
    """
    from src.app.services.assembly_service import is_tool_gated

    entries: dict[str, Any] = {}
    for name in tool_names:
        entries[name] = {
            "allowed_decisions": ["approve", "reject"],
            "when": lambda _request, _name=name: is_tool_gated(_name),
            "description": f"{name} 已被设置为需要人工审批",
        }
    return entries
