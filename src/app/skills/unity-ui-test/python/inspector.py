"""
UI 状态检查与调试工具
提供窗口列表快照、UI 树打印、按钮清单等用于调试和测试验证的功能。

优化特性：
  - get_all_windows 使用 UI.get_all_windows() 框架 API，正确处理 allow_multiple
  - dump_tree 通过单次 Lua 调用序列化子树（替代逐节点 HTTP 请求）
  - get_shown_windows_detail 返回含 instanceID 的完整信息
  - Lua 字符串拼接使用 table.concat 消除 O(n²) 问题

Usage:
    from unity_api import UnityClient
    from inspector import Inspector

    client = UnityClient()
    ins = Inspector(client)
    ins.print_shown_windows()
    ins.print_buttons(parent=some_id)
"""
from unity_api import UnityClient


def _lua(lines: list[str]) -> str:
    return "\n".join(lines)


def _escape_lua(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


class Inspector:
    """UI 检查器，用于观察游戏运行时 UI 状态。"""

    def __init__(self, client: UnityClient):
        self.client = client

    # ------------------------------------------------------------------ #
    #  窗口状态
    # ------------------------------------------------------------------ #

    def get_all_windows(self) -> dict[str, str]:
        """获取所有已加载窗口及其显示状态（正确处理 allow_multiple）。

        Returns:
            {"WindowName": "shown"|"hidden", ...}
            对于 allow_multiple 窗口，只要有一个实例 shown 就报 shown。
        """
        code = _lua([
            "local out = {}",
            "local seen = {}",
            "for _, w in ipairs(UI.get_all_windows()) do",
            "    local name = w:get_name()",
            "    local is_show = w.is_show and w:is_show()",
            "    if is_show then",
            "        seen[name] = 'shown'",
            "    elseif not seen[name] then",
            "        seen[name] = 'hidden'",
            "    end",
            "end",
            "for k, v in pairs(seen) do",
            "    out[#out+1] = k .. '\\x01' .. v",
            "end",
            "print(table.concat(out, '\\x02'))",
        ])
        output = self.client.lua.exec_sync(code).strip()
        if not output:
            return {}
        result = {}
        for item in output.split("\x02"):
            if "\x01" in item:
                name, status = item.split("\x01", 1)
                result[name] = status
        return result

    def get_shown_windows(self) -> list[str]:
        """获取当前正在显示的窗口名称列表。"""
        all_wins = self.get_all_windows()
        return [name for name, status in all_wins.items() if status == "shown"]

    def get_hidden_windows(self) -> list[str]:
        """获取当前已隐藏的窗口名称列表。"""
        all_wins = self.get_all_windows()
        return [name for name, status in all_wins.items() if status == "hidden"]

    def get_shown_windows_detail(self) -> list[dict]:
        """获取所有正在显示的窗口详细信息（含 instanceID）。

        用于精确追踪窗口实例，特别是 allow_multiple 场景。

        Returns:
            [{"name": str, "instanceID": int}, ...]
        """
        code = _lua([
            "local out = {}",
            "for _, w in ipairs(UI.get_all_windows(function(w) return w:is_show() end)) do",
            "    if w.gameobject then",
            "        out[#out+1] = w:get_name() .. '\\x01' .. w.gameobject:GetInstanceID()",
            "    end",
            "end",
            "print(table.concat(out, '\\x02'))",
        ])
        output = self.client.lua.exec_sync(code).strip()
        if not output:
            return []
        result = []
        for item in output.split("\x02"):
            if "\x01" in item:
                name, iid = item.split("\x01", 1)
                result.append({"name": name, "instanceID": int(iid)})
        return result

    def print_shown_windows(self):
        """打印当前显示中的窗口。"""
        windows = self.get_all_windows()
        shown = {k: v for k, v in windows.items() if v == "shown"}
        hidden = {k: v for k, v in windows.items() if v == "hidden"}
        print(f"=== Windows ({len(shown)} shown / {len(hidden)} hidden) ===")
        for name in sorted(shown):
            print(f"  [shown]  {name}")
        for name in sorted(hidden):
            print(f"  [hidden] {name}")

    # ------------------------------------------------------------------ #
    #  UI 树（单次 Lua 序列化）
    # ------------------------------------------------------------------ #

    def dump_tree(self, instance_id: int, *, depth: int = 3,
                  active_only: bool = False) -> str:
        """通过单次 Lua 调用序列化子树并返回格式化字符串。

        相比 print_tree 的逐节点 HTTP 请求，这里只需一次 exec_sync。

        Args:
            instance_id: 根节点 instanceID。
            depth: 递归深度。
            active_only: 只包含 active 节点。
        Returns:
            格式化的树形字符串。
        """
        active_filter = "true" if active_only else "false"
        code = _lua([
            "local out = {}",
            "local function dump(go, d, indent, is_last)",
            "    local t = go.transform",
            "    for i=0,t.childCount-1 do",
            "        local child = t:GetChild(i).gameObject",
            "        local active = child.activeInHierarchy",
            f"        if not {active_filter} or active then",
            "            local last = true",
            "            for j=i+1,t.childCount-1 do",
            "                local nxt = t:GetChild(j).gameObject",
            f"                if not {active_filter} or nxt.activeInHierarchy then",
            "                    last = false break",
            "                end",
            "            end",
            "            local prefix = last and '`-- ' or '|-- '",
            "            local status = active and '' or ' [inactive]'",
            "            local iid = child:GetInstanceID()",
            "            out[#out+1] = indent .. prefix .. child.name .. ' (' .. iid .. ')' .. status",
            "            if d > 1 then",
            "                local next_indent = indent .. (last and '    ' or '|   ')",
            "                dump(child, d-1, next_indent)",
            "            end",
            "        end",
            "    end",
            "end",
            "local root",
            "for _, w in ipairs(UI.get_all_windows()) do",
            f"    if w.gameobject and w.gameobject:GetInstanceID() == {instance_id} then",
            "        root = w.gameobject break",
            "    end",
            "end",
            "if not root then",
            "    local results = CS.UnityEngine.GameObject.FindObjectsOfType(typeof(CS.UnityEngine.Transform))",
            "    if results then",
            "        for i=0,results.Length-1 do",
            f"            if results[i].gameObject:GetInstanceID() == {instance_id} then",
            "                root = results[i].gameObject break",
            "            end",
            "        end",
            "    end",
            "end",
            "if not root then print('__NOT_FOUND__') return end",
            f"dump(root, {depth}, '')",
            "print(table.concat(out, '\\n'))",
        ])
        result = self.client.lua.exec_sync(code).strip()
        if result == "__NOT_FOUND__":
            return f"(node {instance_id} not found)"
        return result

    def get_tree(self, instance_id: int, *, depth: int = 2) -> dict:
        """递归获取 UI 节点树（通过 hierarchy API，多次 HTTP 请求）。

        对于大型子树推荐使用 dump_tree（单次 Lua 调用）。

        Args:
            instance_id: 根节点 instanceID。
            depth: 递归深度（0 = 只返回自身，不展开子节点）。
        Returns:
            嵌套 dict: {"name", "instanceID", "active", "children": [...]}
        """
        children_data = self.client.hierarchy.children(instance_id)
        tree_children = []
        if depth > 0:
            for child in children_data:
                subtree = self.get_tree(child["instanceID"], depth=depth - 1)
                tree_children.append(subtree)
        else:
            tree_children = [
                {"name": c["name"], "instanceID": c["instanceID"],
                 "active": c["active"], "children": []}
                for c in children_data
            ]
        return {
            "instanceID": instance_id,
            "children": tree_children,
        }

    def print_tree(self, instance_id: int, *, depth: int = 3,
                   indent: str = "", active_only: bool = False):
        """打印 UI 节点树（推荐使用 dump_tree 获得更好性能）。

        Args:
            instance_id: 根节点 instanceID。
            depth: 递归深度。
            active_only: 只打印 active 节点。
        """
        tree_str = self.dump_tree(instance_id, depth=depth,
                                  active_only=active_only)
        if indent:
            for line in tree_str.split("\n"):
                print(indent + line)
        else:
            print(tree_str)

    # ------------------------------------------------------------------ #
    #  按钮清单
    # ------------------------------------------------------------------ #

    def get_buttons(self, *, parent: int = None,
                    active_only: bool = False) -> list[dict]:
        """获取按钮列表。"""
        results = self.client.hierarchy.search(type="Button", parent=parent)
        if active_only:
            results = [r for r in results if r.get("active")]
        return results

    def print_buttons(self, *, parent: int = None, active_only: bool = False):
        """打印按钮清单表格。"""
        buttons = self.get_buttons(parent=parent, active_only=active_only)
        active = [b for b in buttons if b.get("active")]
        inactive = [b for b in buttons if not b.get("active")]
        print(f"=== Buttons ({len(active)} active / {len(inactive)} inactive) ===")
        print(f"{'name':<35} {'instanceID':>12}  {'active':>6}  {'scene'}")
        print("-" * 75)
        for btn in buttons:
            status = "Y" if btn.get("active") else "N"
            scene = btn.get("scene", "")
            print(f"{btn['name']:<35} {btn['instanceID']:>12}  {status:>6}  {scene}")

    # ------------------------------------------------------------------ #
    #  组件检查
    # ------------------------------------------------------------------ #

    def print_components(self, instance_id: int):
        """打印指定 GameObject 上的所有组件。"""
        comps = self.client.hierarchy.components(instance_id)
        print(f"=== Components (id={instance_id}) ===")
        for comp in comps:
            enabled = comp.get("enabled", "null")
            marker = {"true": "Y", "false": "N"}.get(enabled, "-")
            print(f"  [{marker}] {comp['typeName']} ({comp['fullName']})")

    # ------------------------------------------------------------------ #
    #  运行时数据
    # ------------------------------------------------------------------ #

    def eval_game_var(self, expression: str) -> str:
        """求值游戏运行时变量。"""
        return self.client.lua.eval(expression)

    def print_hero_info(self):
        """打印当前角色基础信息（单次 Lua 调用）。"""
        code = _lua([
            "local out = {}",
            "local fields = {'name', 'level', 'hp', 'mp'}",
            "for _, f in ipairs(fields) do",
            "    local ok, val = pcall(function() return HeroD.data[f] end)",
            "    out[#out+1] = f .. '\\x01' .. (ok and tostring(val) or '(unavailable)')",
            "end",
            "print(table.concat(out, '\\x02'))",
        ])
        raw = self.client.lua.exec_sync(code).strip()
        print("=== Hero Info ===")
        if raw:
            for item in raw.split("\x02"):
                if "\x01" in item:
                    field, val = item.split("\x01", 1)
                    print(f"  {field}: {val}")

    # ------------------------------------------------------------------ #
    #  窗口节点快速定位
    # ------------------------------------------------------------------ #

    def find_window_node(self, window_name: str) -> dict | None:
        """搜索窗口对应的 GameObject 节点。"""
        results = self.client.hierarchy.search(name=window_name)
        if not results:
            return None
        active = [r for r in results if r.get("active")]
        return active[0] if active else results[0]

    def inspect_window(self, window_name: str, *, button_only: bool = False):
        """检查一个窗口：打印节点树和按钮列表。

        Args:
            window_name: 窗口名称（如 "CharacterWindow"）。
            button_only: 只打印按钮，不打印树。
        """
        node = self.find_window_node(window_name)
        if not node:
            print(f"窗口 '{window_name}' 未找到")
            return

        wnd_id = node["instanceID"]
        print(f"\n{'='*60}")
        print(f"Window: {window_name} (id={wnd_id}, active={node.get('active')})")
        print(f"{'='*60}")

        if not button_only:
            print("\n--- Tree ---")
            self.print_tree(wnd_id, depth=2, active_only=True)

        print("\n--- Buttons ---")
        self.print_buttons(parent=wnd_id, active_only=True)
