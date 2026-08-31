"""Permission gate tests：两档模式 + 只读命令白名单 + 副作用防护。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.app.middleware import permission_gate as gate


def _request(command: str) -> SimpleNamespace:
    return SimpleNamespace(tool_call={"args": {"command": command}})


# ---------------------------------------------------------------------------
# 白名单：只读探查命令自动放行（needs_approval=False）
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "wc -l /repo/client/Assets/Lua/Game/Manager/GangSeason/GS_VeinCongressD.lua",
        'head -60 "/repo/client/Assets/Lua/x.lua"',
        "tail -n 50 /repo/log.txt",
        "cat /repo/config.lua",
        "ls -la /repo",
        "grep -rn \"gang_season_vein\" /repo/client",
        "rg --files /repo",
        "file /repo/bin/game.exe",
        "stat /repo/README.md",
        "du -sh /repo",
        "sort names.txt",
        "uniq -c lines.txt",
        "cut -d, -f1 data.csv",
        "sed -n '1,10p' /repo/x.lua",
        "awk '{print $1}' table.txt",
        "git -C /repo status",
        "git -C /repo log --oneline -5",
        "git -C /repo diff HEAD~1",
        "git -C /repo show abc123",
        "git --no-pager log",
        "git status",
        "git log",
        "whoami",
        "where python",
        "python --version",
        # 链式：每一段都是只读命令 → 整条放行（上次重跑被卡的真实命令形态）
        'wc -l /repo/a.lua; head -60 /repo/a.lua',
        "cat a.lua | grep pattern | sort | uniq",
        "git log && git diff",
        # 只读探查 + 无害 stderr 丢弃 + echo 分隔符（真实踩坑形态）
        'rg -n "week_gain" x.gs 2>/dev/null | head -30; echo "---"; rg -n "clear" x.gs 2> nul | head -20',
        "echo done",
        "echo ---",
    ],
)
def test_readonly_commands_pass_without_approval(command):
    assert gate._needs_execute_approval(_request(command)) is False


# ---------------------------------------------------------------------------
# 审批：有副作用或不在白名单的命令仍要人工批准
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "pip install requests",
        "rm -rf /tmp/x",
        "find . -delete",                          # find 的写原语，不入白名单
        "find . -name '*.log' -exec rm {} \\;",    # 链拆段后含非白名单段
        "sed -i 's/a/b/' /repo/x.lua",             # sed 只有 -n 打印模式在白名单
        "git branch feature-x",                     # 建/删分支是写操作
        "git push origin master",
        "git -C /repo push origin master",           # 全局参数后跟写子命令
        "git -C /repo branch feature-x",
        "git -C /repo commit -m x",
        "curl http://example.com",
        "chmod +x script.sh",
        "mkdir /repo/new",
        # 副作用信号：输出重定向（stderr 丢弃豁免不能放开真重定向）
        "cat /repo/a.lua > /workspace/out.txt",
        "wc -l /repo/a.lua >> stats.txt",
        "rg -n x a.gs 2>/dev/null > out.txt",
        # 副作用信号：命令替换 / 反引号
        "cat $(rm -rf /tmp/x)",
        "wc -l `rm /tmp/x`",
        # 链式：任一段非白名单 → 整条审批
        "wc -l /repo/a.lua; pip install x",
        "head -5 a.lua && rm b.lua",
    ],
)
def test_side_effect_commands_require_approval(command):
    assert gate._needs_execute_approval(_request(command)) is True


def test_empty_command_requires_approval():
    assert gate._needs_execute_approval(_request("")) is True


# ---------------------------------------------------------------------------
# 档位解析：read_only 已移除并回落 workspace_write
# ---------------------------------------------------------------------------

def _set_mode(monkeypatch, configurable: dict):
    monkeypatch.setattr(gate, "get_config", lambda: {"configurable": configurable})


def test_valid_modes(monkeypatch):
    _set_mode(monkeypatch, {"permission_mode": "full_access"})
    assert gate._permission_mode() == "full_access"
    _set_mode(monkeypatch, {"permission_mode": "workspace_write"})
    assert gate._permission_mode() == "workspace_write"


def test_read_only_falls_back_to_workspace_write(monkeypatch):
    _set_mode(monkeypatch, {"permission_mode": "read_only"})
    assert gate._permission_mode() == "workspace_write"
    # 回落后 wc 仍走白名单放行，而不是旧只读档的"任何命令都问"
    assert gate._needs_execute_approval(_request("wc -l a.lua")) is False


def test_unknown_and_missing_mode_default_workspace(monkeypatch):
    _set_mode(monkeypatch, {"permission_mode": "banana"})
    assert gate._permission_mode() == "workspace_write"
    _set_mode(monkeypatch, {})
    assert gate._permission_mode() == "workspace_write"


def test_legacy_execute_approval_off_maps_to_full_access(monkeypatch):
    _set_mode(monkeypatch, {"execute_approval": "off"})
    assert gate._permission_mode() == "full_access"
    # full_access 下连写命令也不打断（该档保持不变）
    assert gate._needs_execute_approval(_request("pip install x")) is False


def test_full_access_never_interrupts(monkeypatch):
    _set_mode(monkeypatch, {"permission_mode": "full_access"})
    assert gate._needs_execute_approval(_request("rm -rf /")) is False
