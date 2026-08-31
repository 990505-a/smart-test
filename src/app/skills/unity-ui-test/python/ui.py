"""
UI 操控高级封装
基于 unity_api.UnityClient，提供搜索点击、窗口管理、等待机制等高频操作。
也集成了基于 TMP 文本内容的按钮查找与点击（需配合 TextReader）。

优化特性：
  - 关键操作合并为单次 Lua exec_sync 调用，减少 HTTP 往返
  - click_close 支持 window_name 直接通过 UI.close() 关闭（1 次调用）
  - find_and_click_by_text 在 Lua 侧完成查找+点击（1 次调用）
  - lua_click 通过 Lua onClick:Invoke() 触发按钮，绕过 hierarchy.click 限制
  - allow_multiple 窗口支持（get_shown_instances / instance_id）
  - 全量 ItemInfo 弹窗关闭（close_all_item_info）

Usage:
    from unity_api import UnityClient
    from ui import UI

    client = UnityClient()
    ui = UI(client)
    ui.find_and_click("character", parent=layout_id)
    ui.open_window("CharacterWindow")
    ui.find_and_click_by_text("宗门公告", window_name="GangRoomWindow")
"""
import time
from unity_api import UnityClient, UnityAPIError


def _lua(lines: list[str]) -> str:
    return "\n".join(lines)


def _escape_lua(s: str) -> str:
    return s.replace("\\", "\\\\").replace("'", "\\'")


class UI:
    """高级 UI 操控工具，组合 UnityClient 的基础 API。"""

    def __init__(self, client: UnityClient):
        self.client = client

    # ------------------------------------------------------------------ #
    #  搜索
    # ------------------------------------------------------------------ #

    def find_button(self, name: str, *, parent: int = None,
                    active_only: bool = True) -> dict | None:
        """搜索按钮，返回第一个匹配项。

        Args:
            name: 按钮名称关键字（模糊匹配）。
            parent: 限定在某个 GameObject 子树下搜索。
            active_only: 为 True 时优先返回 active 的按钮；全部 inactive 时返回第一个。
        Returns:
            匹配的 GameObject dict，或 None。
        """
        results = self.client.hierarchy.search(name=name, type="Button", parent=parent)
        if not results:
            return None
        if active_only:
            active = [r for r in results if r.get("active")]
            if active:
                return active[0]
        return results[0]

    def find_all_buttons(self, *, parent: int = None,
                         active_only: bool = False) -> list[dict]:
        """获取（指定子树下）所有按钮。"""
        results = self.client.hierarchy.search(type="Button", parent=parent)
        if active_only:
            return [r for r in results if r.get("active")]
        return results

    def find_node(self, name: str, *, parent: int = None) -> dict | None:
        """按名称搜索任意 GameObject，返回第一个 active 的匹配项。"""
        results = self.client.hierarchy.search(name=name, parent=parent)
        if not results:
            return None
        active = [r for r in results if r.get("active")]
        return active[0] if active else results[0]

    # ------------------------------------------------------------------ #
    #  点击
    # ------------------------------------------------------------------ #

    def click(self, instance_id: int, *, wait: float = 0.5) -> str:
        """点击按钮并等待（通过 C# hierarchy API）。"""
        result = self.client.hierarchy.click(instance_id)
        if wait > 0:
            time.sleep(wait)
        return result

    def lua_click(self, instance_id: int, *, wait: float = 0.5) -> str:
        """通过 Lua onClick:Invoke() 触发按钮点击。

        适用于 listen_button_clicked 注册的按钮，绕过 hierarchy.click()
        基于 ExecuteEvents.Execute 的限制。

        Args:
            instance_id: 按钮 GameObject 的 instanceID。
            wait: 点击后等待秒数。
        Returns:
            操作结果描述。
        Raises:
            UnityAPIError: 按钮未找到或没有 Button 组件。
        """
        lines = [
            "local root",
            f"for _, w in ipairs(UI.get_all_windows()) do",
            "    if w.gameobject then",
            f"        local btns = w.gameobject:GetComponentsInChildren(UT_BTN, true)",
            "        for i=0,btns.Length-1 do",
            f"            if btns[i].gameObject:GetInstanceID() == {instance_id} then",
            "                btns[i].onClick:Invoke()",
            f"                print('lua_clicked: ' .. btns[i].gameObject.name)",
            "                return",
            "            end",
            "        end",
            "    end",
            "end",
            "print('__NOT_FOUND__')",
        ]
        result = self.client.lua.exec_sync(_lua(lines)).strip()
        if result == "__NOT_FOUND__":
            raise UnityAPIError(f"lua_click: Button with instanceID={instance_id} not found")
        if wait > 0:
            time.sleep(wait)
        return result

    def find_and_click(self, name: str, *, parent: int = None,
                       wait: float = 1.0) -> str:
        """搜索按钮并点击。

        Args:
            name: 按钮名称关键字。
            parent: 限定搜索范围的父节点 instanceID。
            wait: 点击后等待秒数。
        Returns:
            click 接口的返回值。
        Raises:
            UnityAPIError: 按钮未找到或不可点击。
        """
        btn = self.find_button(name, parent=parent)
        if not btn:
            raise UnityAPIError(f"Button not found: '{name}'")
        if not btn.get("active"):
            raise UnityAPIError(
                f"Button '{name}' (id={btn['instanceID']}) is inactive"
            )
        return self.click(btn["instanceID"], wait=wait)

    def click_close(self, *, parent: int = None, wait: float = 1.0,
                    window_name: str = None) -> str:
        """点击关闭按钮。

        当指定 window_name 时，通过 Lua 直接调用 UI.close()（单次调用，最高效）。
        否则通过 hierarchy API 搜索关闭按钮（按优先级尝试）。

        按优先级依次尝试: btn_close → img_btn_close → BtnClose → btn_close_bg
        """
        if window_name:
            escaped = _escape_lua(window_name)
            code = _lua([
                f"local wnd = UI.query_shown_window('{escaped}')",
                "if wnd then",
                "    UI.close(wnd)",
                f"    print('closed: {escaped}')",
                "else",
                "    print('__WINDOW_NOT_FOUND__')",
                "end",
            ])
            result = self.client.lua.exec_sync(code).strip()
            if result == "__WINDOW_NOT_FOUND__":
                raise UnityAPIError(f"Window '{window_name}' not shown")
            if wait > 0:
                time.sleep(wait)
            return result

        close_names = ["btn_close", "img_btn_close", "BtnClose", "btn_close_bg"]
        for name in close_names:
            btn = self.find_button(name, parent=parent)
            if btn and btn.get("active"):
                return self.click(btn["instanceID"], wait=wait)
        raise UnityAPIError(
            f"No close button found (tried: {close_names})"
        )

    # ------------------------------------------------------------------ #
    #  窗口管理
    # ------------------------------------------------------------------ #

    def open_window(self, window_name: str, *args, wait: float = 2.0) -> str:
        """通过 Lua 打开窗口。

        Args:
            window_name: 窗口名称（如 "CharacterWindow"）。
            *args: 传给 UI.open 的额外参数（Lua 字面量字符串）。
            wait: 打开后等待秒数。
        """
        if args:
            lua_args = ", ".join(str(a) for a in args)
            code = f"UI.open('{window_name}', {lua_args})"
        else:
            code = f"UI.open('{window_name}')"
        result = self.client.lua.exec(code)
        if wait > 0:
            time.sleep(wait)
        return result

    def close_window(self, window_name: str, *, wait: float = 1.0) -> str:
        """通过 Lua 关闭窗口（单次调用，支持 allow_multiple）。"""
        escaped = _escape_lua(window_name)
        code = _lua([
            f"local wnd = UI.query_shown_window('{escaped}')",
            "if wnd then UI.close(wnd) end",
        ])
        result = self.client.lua.exec_sync(code)
        if wait > 0:
            time.sleep(wait)
        return result

    def hide_window(self, window_name: str) -> str:
        """通过 Lua 隐藏窗口（不销毁）。"""
        return self.client.lua.exec(f"UI.hide('{window_name}')")

    def show_window(self, window_name: str) -> str:
        """通过 Lua 显示已隐藏的窗口。"""
        return self.client.lua.exec(f"UI.show('{window_name}')")

    def is_window_shown(self, window_name: str) -> bool:
        """检查窗口是否正在显示（支持 allow_multiple）。"""
        escaped = _escape_lua(window_name)
        code = _lua([
            f"local wnd = UI.query_shown_window('{escaped}')",
            "print(wnd and 'true' or 'false')",
        ])
        result = self.client.lua.exec_sync(code).strip()
        return result == "true"

    # ------------------------------------------------------------------ #
    #  allow_multiple 窗口管理
    # ------------------------------------------------------------------ #

    def get_shown_instances(self, window_name: str) -> list[dict]:
        """获取指定窗口名所有正在显示的实例信息。

        适用于 allow_multiple 窗口（如 ItemInfoSimpleWindow），
        返回每个实例的 instanceID 以便精确操作。

        Returns:
            [{"name": str, "instanceID": int}, ...]
        """
        escaped = _escape_lua(window_name)
        code = _lua([
            "local out = {}",
            f"local all = UI.get_all_windows(function(w) return w:get_name() == '{escaped}' and w:is_show() end)",
            "for _, w in ipairs(all) do",
            "    if w.gameobject then",
            "        out[#out+1] = w:get_name() .. '\\x01' .. w.gameobject:GetInstanceID()",
            "    end",
            "end",
            "print(table.concat(out, '\\x02'))",
        ])
        raw = self.client.lua.exec_sync(code).strip()
        if not raw:
            return []
        result = []
        for item in raw.split("\x02"):
            if "\x01" in item:
                name, iid = item.split("\x01", 1)
                result.append({"name": name, "instanceID": int(iid)})
        return result

    def close_all_item_info(self, *, wait: float = 0.5) -> str:
        """关闭所有物品信息弹窗（覆盖全部 ItemInfoBase 子类）。

        覆盖窗口：EquipmentInfoWindow, ItemInfoSimpleWindow,
        ItemInfoDetailWindow, ItemInfoChooseWindow, ItemInfoEquipSoulWindow,
        ItemSourceWindow, DaoHuoDetailsRewardWindow, CommonItemSellWindow,
        ShopBatchBuyItemsWindow
        """
        code = _lua([
            "local names = {",
            "    'EquipmentInfoWindow', 'ItemInfoSimpleWindow',",
            "    'ItemInfoDetailWindow', 'ItemInfoChooseWindow',",
            "    'ItemInfoEquipSoulWindow', 'ItemSourceWindow',",
            "    'DaoHuoDetailsRewardWindow', 'CommonItemSellWindow',",
            "    'ShopBatchBuyItemsWindow',",
            "}",
            "local closed = {}",
            "for _, name in ipairs(names) do",
            "    local all = UI.get_all_windows(function(w)",
            "        return w:get_name() == name and w:is_show()",
            "    end)",
            "    for _, w in ipairs(all) do",
            "        UI.close(w)",
            "        closed[#closed+1] = name",
            "    end",
            "end",
            "print('closed: ' .. #closed)",
        ])
        result = self.client.lua.exec_sync(code).strip()
        if wait > 0:
            time.sleep(wait)
        return result

    # ------------------------------------------------------------------ #
    #  等待
    # ------------------------------------------------------------------ #

    def wait_for_window(self, window_name: str, *,
                        timeout: float = 10.0, interval: float = 0.5) -> bool:
        """轮询等待窗口出现。

        Returns:
            True 如果窗口在超时前出现，False 如果超时。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.is_window_shown(window_name):
                return True
            time.sleep(interval)
        return False

    def wait_for_window_close(self, window_name: str, *,
                              timeout: float = 10.0, interval: float = 0.5) -> bool:
        """轮询等待窗口关闭。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_window_shown(window_name):
                return True
            time.sleep(interval)
        return False

    def wait_for_node(self, name: str, *, parent: int = None,
                      timeout: float = 10.0, interval: float = 0.5) -> dict | None:
        """轮询等待某个 GameObject 出现并处于 active 状态。

        Returns:
            找到的 GameObject dict，或超时返回 None。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            node = self.find_node(name, parent=parent)
            if node and node.get("active"):
                return node
            time.sleep(interval)
        return None

    def wait_for_hierarchy_window(self, name: str, *,
                                  timeout: float = 10.0,
                                  interval: float = 0.5) -> dict | None:
        """轮询等待 Hierarchy 中指定名称的 active 窗口出现。

        适用于不在 UI._windows 中管理的弹窗（通过 hierarchy.search 检测）。

        Returns:
            找到的 GameObject dict，或超时返回 None。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            results = self.client.hierarchy.search(name=name)
            active = [r for r in results if r.get("active")]
            if active:
                return active[0]
            time.sleep(interval)
        return None

    # ------------------------------------------------------------------ #
    #  截图
    # ------------------------------------------------------------------ #

    def screenshot(self, save_path: str = "screenshot.png") -> str:
        """截图的快捷方式。"""
        return self.client.screenshot.capture(save_path)

    # ------------------------------------------------------------------ #
    #  组合操作
    # ------------------------------------------------------------------ #

    def open_and_verify(self, window_name: str, *,
                        wait: float = 2.0, timeout: float = 10.0) -> bool:
        """打开窗口并验证是否成功打开。"""
        self.open_window(window_name, wait=wait)
        return self.is_window_shown(window_name) or self.wait_for_window(
            window_name, timeout=timeout - wait
        )

    def close_and_verify(self, window_name: str, *,
                         wait: float = 1.0, timeout: float = 5.0) -> bool:
        """关闭窗口并验证是否成功关闭。"""
        self.close_window(window_name, wait=wait)
        return not self.is_window_shown(window_name) or self.wait_for_window_close(
            window_name, timeout=timeout - wait
        )

    def click_and_wait_window(self, button_name: str, window_name: str, *,
                              parent: int = None, timeout: float = 5.0) -> bool:
        """点击按钮后等待目标窗口出现。"""
        self.find_and_click(button_name, parent=parent, wait=0.3)
        return self.wait_for_window(window_name, timeout=timeout)

    def switch_hud_tab(self, tab_name: str, *,
                       hud_layout_id: int = None) -> bool:
        """切换 HudWindow 底部导航栏 Tab。

        Args:
            tab_name: Tab 名称，可选 character/gongfa/wild/house/gang/mmo/clan。
            hud_layout_id: HudWindow/layout 节点的 instanceID。
                           不传则自动搜索。
        Returns:
            True 如果切换成功（按钮被点击）。
        """
        tab_window_map = {
            "character": "CharacterWindow",
            "gongfa":    "GongfaRoomWindow",
            "house":     "HouseRoomWindow",
            "gang":      "GangRoomWindow",
            "mmo":       "MMORoomWindow",
            "clan":      "ClanRoomWindow",
        }

        if hud_layout_id is None:
            layout = self.find_node("layout", parent=self._find_hud_id())
            if not layout:
                raise UnityAPIError("HudWindow/layout not found")
            hud_layout_id = layout["instanceID"]

        self.find_and_click(tab_name, parent=hud_layout_id, wait=2.0)

        expected = tab_window_map.get(tab_name)
        if expected:
            return self.wait_for_window(expected, timeout=5.0)
        return True

    def _find_hud_id(self) -> int:
        """查找 HudWindow 的 instanceID。"""
        node = self.find_node("HudWindow")
        if not node:
            raise UnityAPIError("HudWindow not found in hierarchy")
        return node["instanceID"]

    # ------------------------------------------------------------------ #
    #  基于 TMP 文本的按钮查找与点击（单次 Lua 调用优化）
    # ------------------------------------------------------------------ #

    def find_and_click_by_text(self, text: str, *,
                               window_name: str,
                               instance_id: int = None,
                               exact: bool = True,
                               strip_tags: bool = False,
                               wait: float = 1.0) -> str:
        """通过按钮上的 TMP 文本内容查找并点击按钮（单次 Lua 调用）。

        在 Lua 侧完成查找和点击，合并为单次 exec_sync 调用。
        找到匹配按钮后直接调用 onClick:Invoke()。

        Args:
            text: 按钮显示文本（如 "宗门公告"）。
            window_name: 限定搜索的窗口名称（必填）。
            instance_id: 窗口 instanceID（allow_multiple 场景）。
            exact: True = 精确匹配；False = 包含匹配。
            strip_tags: True 时先剥离富文本标签再匹配。
            wait: 点击后等待秒数。
        Returns:
            点击结果描述。
        Raises:
            UnityAPIError: 按钮未找到或窗口不存在。
        """
        escaped_text = _escape_lua(text)

        if instance_id is not None:
            root_lines = [
                "local root",
                f"for _, w in ipairs(UI.get_all_windows()) do",
                f"    if w.gameobject and w.gameobject:GetInstanceID() == {instance_id} then",
                "        root = w.gameobject",
                "        break",
                "    end",
                "end",
                "if not root then print('__NOT_FOUND__') return end",
            ]
        else:
            escaped_wnd = _escape_lua(window_name)
            root_lines = [
                f"local wnd = UI.query_shown_window('{escaped_wnd}')",
                "if not wnd then print('__WINDOW_NOT_FOUND__') return end",
                "local root = wnd.gameobject",
                "if not root then print('__NO_GAMEOBJECT__') return end",
            ]

        if strip_tags:
            txt_prep = "            local cmp = txt:gsub('<[^>]+>', '')"
        else:
            txt_prep = "            local cmp = txt"

        if exact:
            match_cond = f"cmp == '{escaped_text}'"
        else:
            match_cond = f"cmp:find('{escaped_text}', 1, true)"

        lines = root_lines + [
            "local btns = root:GetComponentsInChildren(UT_BTN, true)",
            "for i=0,btns.Length-1 do",
            "    local btn = btns[i]",
            "    local bgo = btn.gameObject",
            "    if bgo.activeInHierarchy then",
            "        local tmp = bgo:GetComponent(UT_TMP)",
            "        if not tmp then tmp = bgo:GetComponentInChildren(UT_TMP, false) end",
            "        if tmp then",
            "            local txt = tostring(tmp.text)",
            txt_prep,
            f"            if {match_cond} then",
            "                btn.onClick:Invoke()",
            "                print('clicked: ' .. bgo.name .. ' (' .. txt .. ')')",
            "                return",
            "            end",
            "        end",
            "    end",
            "end",
            "print('__NOT_FOUND__')",
        ]

        result = self.client.lua.exec_sync(_lua(lines)).strip()
        if result in ("__NOT_FOUND__", "__WINDOW_NOT_FOUND__", "__NO_GAMEOBJECT__"):
            mode = "精确" if exact else "包含"
            raise UnityAPIError(
                f"未找到 TMP 文本{mode}匹配 {text!r} 的 active 按钮（窗口: {window_name}）"
            )
        if wait > 0:
            time.sleep(wait)
        return result

    def switch_tab_by_text(self, tab_text: str, *,
                           window_name: str,
                           instance_id: int = None,
                           strip_tags: bool = False,
                           wait: float = 1.0) -> bool:
        """通用 Tab 切换：在指定窗口内通过显示文本点击 Tab 按钮。

        适用于 HudWindow 以外的任何含 Tab 结构的窗口。
        内部使用单次 Lua 调用完成查找+点击。

        Args:
            tab_text: Tab 上显示的文字（如 "心法道途"）。
            window_name: 窗口名称（必填）。
            instance_id: 窗口 instanceID（allow_multiple 场景）。
            strip_tags: True 时先剥离富文本再匹配。
            wait: 点击后等待秒数。
        Returns:
            True 如果按钮被成功点击。
        Raises:
            UnityAPIError: 找不到目标 Tab 按钮。
        """
        self.find_and_click_by_text(
            tab_text,
            window_name=window_name,
            instance_id=instance_id,
            strip_tags=strip_tags,
            wait=wait,
        )
        return True

    def switch_tab_and_verify(self, tab_text: str, *,
                              window_name: str,
                              verify_node: str,
                              verify_text: str,
                              instance_id: int = None,
                              strip_tags: bool = False,
                              tab_wait: float = 1.0,
                              verify_timeout: float = 5.0) -> bool:
        """切换 Tab 后等待指定节点出现期望文本，验证内容已正确加载。

        Args:
            tab_text: Tab 显示文字。
            window_name: 窗口名称。
            verify_node: 切换后用于验证的节点名。
            verify_text: 该节点应包含的文本（包含匹配）。
            instance_id: 窗口 instanceID（allow_multiple 场景）。
            strip_tags: 查找 Tab 按钮时是否剥离富文本。
            tab_wait: 点击 Tab 后等待动画的时间（秒）。
            verify_timeout: 等待 verify_text 出现的超时时间（秒）。
        Returns:
            True 如果 Tab 切换并验证成功。
        Raises:
            UnityAPIError: Tab 按钮未找到，或超时后验证文本仍未出现。
        """
        from text_reader import TextReader
        self.switch_tab_by_text(tab_text, window_name=window_name,
                                instance_id=instance_id,
                                strip_tags=strip_tags, wait=tab_wait)
        tr = TextReader(self.client)
        ok = tr.wait_for_text(
            verify_node, verify_text,
            window_name=window_name,
            instance_id=instance_id,
            exact=False,
            strip_tags=True,
            timeout=verify_timeout,
        )
        if not ok:
            current = tr.get_text(verify_node, window_name=window_name,
                                  instance_id=instance_id, strip_tags=True)
            raise UnityAPIError(
                f"切换到 Tab '{tab_text}' 后超时，节点 '{verify_node}' 未出现期望文本\n"
                f"  期望包含: {verify_text!r}\n"
                f"  实际值:   {current!r}"
            )
        return True

    # ------------------------------------------------------------------ #
    #  Hierarchy 窗口操作（非托管弹窗）
    # ------------------------------------------------------------------ #

    def close_hierarchy_window(self, instance_id: int, *,
                               wait: float = 1.0) -> str:
        """通过 children 导航找到 btn_close 并关闭非托管窗口。

        适用于不在 UI._windows 中的弹窗，通过 Hierarchy API 逐层导航。

        Args:
            instance_id: 窗口 GameObject 的 instanceID。
            wait: 关闭后等待秒数。
        Returns:
            点击结果。
        Raises:
            UnityAPIError: 未找到关闭按钮。
        """
        close_names = {"btn_close", "img_btn_close", "BtnClose", "btn_close_bg"}
        children = self.client.hierarchy.children(instance_id)

        for child in children:
            if child["name"] in close_names and child.get("active"):
                return self.click(child["instanceID"], wait=wait)
            sub_children = self.client.hierarchy.children(child["instanceID"])
            for sub in sub_children:
                if sub["name"] in close_names and sub.get("active"):
                    return self.click(sub["instanceID"], wait=wait)

        raise UnityAPIError(
            f"btn_close not found in hierarchy window {instance_id}"
        )

    def find_in_children(self, parent_id: int, name: str, *,
                         max_depth: int = 5) -> dict | None:
        """在指定父节点子树中通过 Lua 递归搜索节点（单次调用）。

        比 hierarchy.search(parent=X) 更可靠，避免跨窗口返回的问题。

        Args:
            parent_id: 父节点 instanceID。
            name: 目标节点名称。
            max_depth: 最大搜索深度。
        Returns:
            {"name": str, "instanceID": int, "active": bool}，或 None。
        """
        escaped = _escape_lua(name)
        code = _lua([
            "local function find(go, name, depth)",
            "    if depth <= 0 then return nil end",
            "    local t = go.transform",
            "    for i=0,t.childCount-1 do",
            "        local child = t:GetChild(i).gameObject",
            "        if child.name == name then",
            "            return child:GetInstanceID() .. '\\x01' .. (child.activeInHierarchy and '1' or '0') .. '\\x01' .. child.name",
            "        end",
            "        local r = find(child, name, depth-1)",
            "        if r then return r end",
            "    end",
            "    return nil",
            "end",
            "local root",
            "for _, w in ipairs(UI.get_all_windows()) do",
            f"    if w.gameobject and w.gameobject:GetInstanceID() == {parent_id} then",
            "        root = w.gameobject break",
            "    end",
            "end",
            "if not root then",
            f"    root = CS.UnityEngine.GameObject.Find('') -- fallback",
            "    print('__NOT_FOUND__') return",
            "end",
            f"local r = find(root, '{escaped}', {max_depth})",
            "if r then print(r) else print('__NOT_FOUND__') end",
        ])
        raw = self.client.lua.exec_sync(code).strip()
        if not raw or raw == "__NOT_FOUND__":
            return None
        parts = raw.split("\x01", 2)
        if len(parts) != 3:
            return None
        return {
            "instanceID": int(parts[0]),
            "active": parts[1] == "1",
            "name": parts[2],
        }
