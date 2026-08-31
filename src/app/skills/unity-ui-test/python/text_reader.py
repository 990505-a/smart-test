"""
TMP 文本读取工具
读取 Unity UI 中 TextMeshProUGUI 组件的文本内容，支持：
  - 富文本标签剥离（strip_tags）
  - 进度条解析（get_progress / assert_progress）
  - 正则模式断言（assert_text_pattern）
  - 按索引访问同名节点（get_text_at / assert_text_at）
  - 数值比较断言（get_number / assert_number）
  - 按文本查找/点击按钮、等待文本变化
  - allow_multiple 窗口支持（instance_id 定位）

Usage:
    from unity_api import UnityClient
    from text_reader import TextReader

    client = UnityClient()
    tr = TextReader(client)

    # 读取并断言（自动剥离富文本）
    tr.assert_text("text_name", "衣·灵纱绘羽", window_name="OperateActivityWindow",
                   strip_tags=True)

    # 断言进度 >= 100%
    tr.assert_progress("slider_txt", min_ratio=1.0, window_name="OperateActivityWindow")

    # 断言第 3 个积分门槛为 120
    tr.assert_text_at("text_score", index=2, expected="120",
                      window_name="OperateActivityWindow")

    # 对 allow_multiple 窗口，用 instance_id 精确定位某个实例
    tr.get_text("text_name", instance_id=12345)

重要说明：
  - UT_TMP  = typeof(TextMeshProUGUI)，游戏全局已注册
  - UT_BTN  = typeof(UnityEngine.UI.Button)
  - Lua 字符串必须使用单引号，避免 JSON 序列化时引入反斜杠转义
"""
import re
import time
from unity_api import UnityClient, UnityAPIError


_ERROR_MARKERS = frozenset({
    "__WINDOW_NOT_FOUND__", "__NO_GAMEOBJECT__", "__NOT_FOUND__",
})


def _lua(lines: list[str]) -> str:
    """拼接 Lua 代码行（Unix 换行符，避免 CRLF 导致 Lua 解析失败）。"""
    return "\n".join(lines)


def _strip_tags(text: str) -> str:
    """剥离 TMP 富文本标签（<color=...>、<size=...> 等），返回纯文本。"""
    return re.sub(r"<[^>]+>", "", text)


def _parse_number(text: str) -> float:
    """将字符串解析为浮点数（自动剥离富文本和空白）。

    Raises:
        ValueError: 无法解析为数字时。
    """
    cleaned = _strip_tags(text).strip()
    return float(cleaned)


def _escape_lua(s: str) -> str:
    """转义 Lua 单引号字符串中的特殊字符。"""
    return s.replace("\\", "\\\\").replace("'", "\\'")


class TextReader:
    """读取 Unity UI 中 TextMeshProUGUI 组件的文本内容。

    所有方法均通过 exec_sync 同步执行 Lua 代码，直接访问运行时 C# 对象。
    支持通过 window_name 或 instance_id 定位目标窗口。
    """

    def __init__(self, client: UnityClient):
        self.client = client

    # ------------------------------------------------------------------ #
    #  内部工具
    # ------------------------------------------------------------------ #

    def _lua_get_root_go(self, window_name: str = None,
                         instance_id: int = None) -> list[str]:
        """生成获取窗口根 gameobject 的 Lua 片段。

        支持两种定位方式：
        - window_name: 使用 UI.query_shown_window()，正确处理 allow_multiple
        - instance_id: 遍历 UI.get_all_windows() 按 gameobject instanceID 匹配
        """
        if instance_id is not None:
            return [
                "local root",
                f"for _, w in ipairs(UI.get_all_windows()) do",
                f"    if w.gameobject and w.gameobject:GetInstanceID() == {instance_id} then",
                "        root = w.gameobject",
                "        break",
                "    end",
                "end",
                "if not root then print('__NOT_FOUND__') return end",
            ]
        elif window_name:
            escaped = _escape_lua(window_name)
            return [
                f"local wnd = UI.query_shown_window('{escaped}')",
                "if not wnd then print('__WINDOW_NOT_FOUND__') return end",
                "local root = wnd.gameobject",
                "if not root then print('__NO_GAMEOBJECT__') return end",
            ]
        return []

    def _lua_get_window_go(self, window_name: str) -> list[str]:
        """向后兼容的窗口定位方法。"""
        return self._lua_get_root_go(window_name=window_name)

    def _lua_iter_shown_windows(self) -> list[str]:
        """生成遍历所有显示中窗口的 Lua 片段（正确处理 allow_multiple）。"""
        return [
            "local _shown = UI.get_all_windows(function(w) return w.is_show and w:is_show() end)",
        ]

    def _exec(self, code: str) -> str:
        """执行 Lua 并返回输出字符串。"""
        return self.client.lua.exec_sync(code)

    def _maybe_strip(self, text: str, strip: bool) -> str:
        """按需剥离富文本标签。"""
        return _strip_tags(text) if strip else text

    def _is_error(self, raw: str) -> bool:
        """检查 Lua 返回值是否为错误标记。"""
        return not raw or raw in _ERROR_MARKERS

    # ------------------------------------------------------------------ #
    #  单节点文本读取（定向快速路径）
    # ------------------------------------------------------------------ #

    def get_text(self, node_name: str, *,
                 window_name: str = None,
                 instance_id: int = None,
                 include_inactive: bool = True,
                 strip_tags: bool = False) -> str | None:
        """按节点名获取 TMP 文本（返回第一个匹配节点）。

        使用定向 Lua 查询，只搜索匹配节点名的 TMP，找到即返回（早停）。

        Args:
            node_name: GameObject 名称（精确匹配）。
            window_name: 限定搜索范围的窗口名。
            instance_id: 限定搜索的窗口 gameobject instanceID（用于 allow_multiple 窗口）。
            include_inactive: 是否包含 inactive 节点。
            strip_tags: True 时自动剥离富文本标签。
        Returns:
            文本字符串，节点不存在时返回 None。
        """
        inactive_flag = "true" if include_inactive else "false"
        escaped_name = _escape_lua(node_name)

        if window_name or instance_id:
            root_lines = self._lua_get_root_go(window_name=window_name,
                                               instance_id=instance_id)
            lines = root_lines + [
                f"local tmps = root:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "for i=0,tmps.Length-1 do",
                "    local tmp = tmps[i]",
                f"    if tmp.gameObject.name == '{escaped_name}' then",
                "        print(tostring(tmp.text))",
                "        return",
                "    end",
                "end",
                "print('__NOT_FOUND__')",
            ]
        else:
            lines = self._lua_iter_shown_windows() + [
                "for _, wnd in ipairs(_shown) do",
                "    if wnd.gameobject then",
                f"        local tmps = wnd.gameobject:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "        for i=0,tmps.Length-1 do",
                "            local tmp = tmps[i]",
                f"            if tmp.gameObject.name == '{escaped_name}' then",
                "                print(tostring(tmp.text))",
                "                return",
                "            end",
                "        end",
                "    end",
                "end",
                "print('__NOT_FOUND__')",
            ]

        raw = self._exec(_lua(lines)).strip()
        if self._is_error(raw):
            return None
        return _strip_tags(raw) if strip_tags else raw

    def get_texts(self, node_name: str, *,
                  window_name: str = None,
                  instance_id: int = None,
                  include_inactive: bool = True,
                  strip_tags: bool = False) -> list[str]:
        """获取所有同名节点的 TMP 文本列表。

        使用定向 Lua 查询，只收集匹配节点名的 TMP 文本。

        Args:
            strip_tags: True 时对每个文本值剥离富文本标签。
        Returns:
            文本列表，未找到时返回空列表。
        """
        inactive_flag = "true" if include_inactive else "false"
        escaped_name = _escape_lua(node_name)

        if window_name or instance_id:
            root_lines = self._lua_get_root_go(window_name=window_name,
                                               instance_id=instance_id)
            lines = root_lines + [
                f"local tmps = root:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "local out = {}",
                "for i=0,tmps.Length-1 do",
                "    local tmp = tmps[i]",
                f"    if tmp.gameObject.name == '{escaped_name}' then",
                "        out[#out+1] = tostring(tmp.text)",
                "    end",
                "end",
                "print(table.concat(out, '\\x02'))",
            ]
        else:
            lines = self._lua_iter_shown_windows() + [
                "local out = {}",
                "for _, wnd in ipairs(_shown) do",
                "    if wnd.gameobject then",
                f"        local tmps = wnd.gameobject:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "        for i=0,tmps.Length-1 do",
                "            local tmp = tmps[i]",
                f"            if tmp.gameObject.name == '{escaped_name}' then",
                "                out[#out+1] = tostring(tmp.text)",
                "            end",
                "        end",
                "    end",
                "end",
                "print(table.concat(out, '\\x02'))",
            ]

        raw = self._exec(_lua(lines)).strip()
        if self._is_error(raw):
            return []
        result = [t for t in raw.split("\x02") if t]
        if strip_tags:
            return [_strip_tags(v) for v in result]
        return result

    def get_text_at(self, node_name: str, index: int, *,
                    window_name: str = None,
                    instance_id: int = None,
                    include_inactive: bool = True,
                    strip_tags: bool = False) -> str | None:
        """获取第 N 个同名节点的文本（适用于列表/网格中大量同名节点场景）。

        Args:
            index: 0-based 索引，按 UI 树中从上到下的出现顺序排列。
            strip_tags: True 时剥离富文本标签。
        Returns:
            文本字符串，索引越界时返回 None。
        """
        texts = self.get_texts(node_name,
                               window_name=window_name,
                               instance_id=instance_id,
                               include_inactive=include_inactive,
                               strip_tags=strip_tags)
        if index < 0 or index >= len(texts):
            return None
        return texts[index]

    # ------------------------------------------------------------------ #
    #  批量文本读取
    # ------------------------------------------------------------------ #

    def get_all_texts(self, *,
                      window_name: str = None,
                      instance_id: int = None,
                      include_inactive: bool = True) -> dict[str, list[str]]:
        """获取指定范围内所有 TMP 节点的原始文本（含富文本标签）。

        Returns:
            {节点名: [文本, ...]} 字典（同名节点合并到同一 key，保留出现顺序）。
        """
        inactive_flag = "true" if include_inactive else "false"

        if window_name or instance_id:
            root_lines = self._lua_get_root_go(window_name=window_name,
                                               instance_id=instance_id)
            lines = root_lines + [
                f"local tmps = root:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "local out = {}",
                "for i=0,tmps.Length-1 do",
                "    local tmp = tmps[i]",
                "    out[#out+1] = tmp.gameObject.name .. '\\x01' .. tostring(tmp.text)",
                "end",
                "print(table.concat(out, '\\x02'))",
            ]
        else:
            lines = self._lua_iter_shown_windows() + [
                "local out = {}",
                "for _, wnd in ipairs(_shown) do",
                "    if wnd.gameobject then",
                f"        local tmps = wnd.gameobject:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "        for i=0,tmps.Length-1 do",
                "            local tmp = tmps[i]",
                "            out[#out+1] = tmp.gameObject.name .. '\\x01' .. tostring(tmp.text)",
                "        end",
                "    end",
                "end",
                "print(table.concat(out, '\\x02'))",
            ]

        raw = self._exec(_lua(lines)).strip()
        if self._is_error(raw):
            return {}

        result: dict[str, list[str]] = {}
        for pair in raw.split("\x02"):
            if "\x01" in pair:
                name, text = pair.split("\x01", 1)
                result.setdefault(name, []).append(text)
        return result

    # ------------------------------------------------------------------ #
    #  进度条解析
    # ------------------------------------------------------------------ #

    def get_progress(self, node_name: str, *,
                     window_name: str = None,
                     instance_id: int = None,
                     index: int = 0) -> tuple[float, float] | None:
        """解析进度条文本（格式 "当前值/总量"，支持带富文本标签）。

        Args:
            node_name: TMP 节点名（如 "slider_txt"）。
            window_name: 限定搜索范围。
            instance_id: 窗口 instanceID（allow_multiple 场景）。
            index: 同名多节点时指定第几个（0-based）。
        Returns:
            (current, total) 浮点数元组；解析失败或节点不存在时返回 None。

        Examples:
            '<color=#65dccc>999</color>/100' → (999.0, 100.0)
            '0/20'                           → (0.0, 20.0)
        """
        raw = self.get_text_at(node_name, index,
                               window_name=window_name,
                               instance_id=instance_id,
                               strip_tags=True)
        if raw is None:
            return None
        raw = raw.strip()
        m = re.match(r"^([\d.]+)\s*/\s*([\d.]+)$", raw)
        if not m:
            return None
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None

    def get_all_progress(self, node_name: str, *,
                         window_name: str = None,
                         instance_id: int = None) -> list[tuple[float, float]]:
        """获取所有同名进度条节点的 (current, total) 列表。"""
        texts = self.get_texts(node_name, window_name=window_name,
                               instance_id=instance_id, strip_tags=True)
        result = []
        for t in texts:
            m = re.match(r"^([\d.]+)\s*/\s*([\d.]+)$", t.strip())
            if m:
                try:
                    result.append((float(m.group(1)), float(m.group(2))))
                except ValueError:
                    pass
        return result

    # ------------------------------------------------------------------ #
    #  数值提取
    # ------------------------------------------------------------------ #

    def get_number(self, node_name: str, *,
                   window_name: str = None,
                   instance_id: int = None,
                   index: int = 0) -> float | None:
        """获取节点文本并解析为数字（自动剥离富文本）。

        Args:
            index: 同名多节点时指定第几个（0-based）。
        Returns:
            float 数值；节点不存在或无法解析时返回 None。
        """
        raw = self.get_text_at(node_name, index,
                               window_name=window_name,
                               instance_id=instance_id,
                               strip_tags=True)
        if raw is None:
            return None
        try:
            return _parse_number(raw)
        except ValueError:
            return None

    def get_numbers(self, node_name: str, *,
                    window_name: str = None,
                    instance_id: int = None) -> list[float]:
        """获取所有同名节点的数值列表（自动剥离富文本，跳过无法解析的节点）。"""
        texts = self.get_texts(node_name, window_name=window_name,
                               instance_id=instance_id, strip_tags=True)
        result = []
        for t in texts:
            try:
                result.append(_parse_number(t))
            except ValueError:
                pass
        return result

    # ------------------------------------------------------------------ #
    #  按钮文本读取与查找
    # ------------------------------------------------------------------ #

    def get_button_texts(self, *,
                         window_name: str,
                         instance_id: int = None,
                         include_inactive: bool = True) -> list[dict]:
        """获取指定窗口中所有按钮及其 TMP 文本标签。

        Returns:
            [{"name": str, "instanceID": int, "active": bool, "text": str}, ...]
        """
        inactive_flag = "true" if include_inactive else "false"
        root_lines = self._lua_get_root_go(window_name=window_name,
                                           instance_id=instance_id)
        lines = root_lines + [
            f"local btns = root:GetComponentsInChildren(UT_BTN, {inactive_flag})",
            "local out = {}",
            "for i=0,btns.Length-1 do",
            "    local btn = btns[i]",
            "    local bgo = btn.gameObject",
            "    local tmp = bgo:GetComponent(UT_TMP)",
            "    if not tmp then tmp = bgo:GetComponentInChildren(UT_TMP, false) end",
            "    local txt = tmp and tostring(tmp.text) or ''",
            "    local active = bgo.activeInHierarchy and '1' or '0'",
            "    local iid = bgo:GetInstanceID()",
            "    out[#out+1] = iid .. '\\x01' .. active .. '\\x01' .. bgo.name .. '\\x01' .. txt",
            "end",
            "print(table.concat(out, '\\x02'))",
        ]

        raw = self._exec(_lua(lines)).strip()
        if self._is_error(raw):
            return []

        result = []
        for item in raw.split("\x02"):
            parts = item.split("\x01", 3)
            if len(parts) == 4:
                iid, active, name, text = parts
                result.append({
                    "instanceID": int(iid),
                    "active": active == "1",
                    "name": name,
                    "text": text,
                })
        return result

    def find_button_by_text(self, text: str, *,
                            window_name: str,
                            instance_id: int = None,
                            exact: bool = True,
                            strip_tags: bool = False,
                            active_only: bool = True) -> dict | None:
        """通过 TMP 文本内容查找按钮（Lua 侧早停，找到即返回）。

        Args:
            text: 要匹配的文本。
            exact: True = 精确匹配；False = 包含匹配。
            strip_tags: True 时先剥离富文本再匹配。
            active_only: True = 只返回 active 的按钮。
        Returns:
            {"name": str, "instanceID": int, "active": bool, "text": str}，或 None。
        """
        escaped = _escape_lua(text)
        active_flag = "true" if active_only else "false"
        root_lines = self._lua_get_root_go(window_name=window_name,
                                           instance_id=instance_id)

        if strip_tags:
            txt_prep = "            local cmp = txt:gsub('<[^>]+>', '')"
        else:
            txt_prep = "            local cmp = txt"

        if exact:
            match_cond = f"cmp == '{escaped}'"
        else:
            match_cond = f"cmp:find('{escaped}', 1, true)"

        lines = root_lines + [
            "local btns = root:GetComponentsInChildren(UT_BTN, true)",
            "for i=0,btns.Length-1 do",
            "    local btn = btns[i]",
            "    local bgo = btn.gameObject",
            f"    if not {active_flag} or bgo.activeInHierarchy then",
            "        local tmp = bgo:GetComponent(UT_TMP)",
            "        if not tmp then tmp = bgo:GetComponentInChildren(UT_TMP, false) end",
            "        if tmp then",
            "            local txt = tostring(tmp.text)",
            txt_prep,
            f"            if {match_cond} then",
            "                local iid = bgo:GetInstanceID()",
            "                print(iid .. '\\x01' .. (bgo.activeInHierarchy and '1' or '0') .. '\\x01' .. bgo.name .. '\\x01' .. txt)",
            "                return",
            "            end",
            "        end",
            "    end",
            "end",
            "print('__NOT_FOUND__')",
        ]

        raw = self._exec(_lua(lines)).strip()
        if self._is_error(raw):
            return None

        parts = raw.split("\x01", 3)
        if len(parts) != 4:
            return None
        iid, active, name, btn_text = parts
        return {
            "instanceID": int(iid),
            "active": active == "1",
            "name": name,
            "text": btn_text,
        }

    def find_nodes_by_text(self, text: str, *,
                           window_name: str = None,
                           instance_id: int = None,
                           exact: bool = True,
                           include_inactive: bool = True) -> list[dict]:
        """通过 TMP 文本内容查找节点，返回含 instanceID 的列表。

        Returns:
            [{"name": str, "instanceID": int, "active": bool, "text": str}, ...]
        """
        inactive_flag = "true" if include_inactive else "false"
        escaped = _escape_lua(text)

        if exact:
            match_cond = f"tostring(tmp.text) == '{escaped}'"
        else:
            match_cond = f"tostring(tmp.text):find('{escaped}', 1, true)"

        collect_lines = [
            "local out = {}",
            f"    for i=0,tmps.Length-1 do",
            "        local tmp = tmps[i]",
            f"        if {match_cond} then",
            "            local bgo = tmp.gameObject",
            "            out[#out+1] = bgo:GetInstanceID() .. '\\x01'",
            "                .. (bgo.activeInHierarchy and '1' or '0') .. '\\x01'",
            "                .. bgo.name .. '\\x01' .. tostring(tmp.text)",
            "        end",
            "    end",
        ]

        if window_name or instance_id:
            root_lines = self._lua_get_root_go(window_name=window_name,
                                               instance_id=instance_id)
            lines = root_lines + [
                f"local tmps = root:GetComponentsInChildren(UT_TMP, {inactive_flag})",
            ] + collect_lines + [
                "print(table.concat(out, '\\x02'))",
            ]
        else:
            lines = self._lua_iter_shown_windows() + [
                "local out = {}",
                "for _, wnd in ipairs(_shown) do",
                "    if wnd.gameobject then",
                f"        local tmps = wnd.gameobject:GetComponentsInChildren(UT_TMP, {inactive_flag})",
                "        for i=0,tmps.Length-1 do",
                "            local tmp = tmps[i]",
                f"            if {match_cond} then",
                "                local bgo = tmp.gameObject",
                "                out[#out+1] = bgo:GetInstanceID() .. '\\x01'",
                "                    .. (bgo.activeInHierarchy and '1' or '0') .. '\\x01'",
                "                    .. bgo.name .. '\\x01' .. tostring(tmp.text)",
                "            end",
                "        end",
                "    end",
                "end",
                "print(table.concat(out, '\\x02'))",
            ]

        raw = self._exec(_lua(lines)).strip()
        if self._is_error(raw):
            return []

        result = []
        for item in raw.split("\x02"):
            parts = item.split("\x01", 3)
            if len(parts) == 4:
                iid, active, name, txt = parts
                result.append({
                    "instanceID": int(iid),
                    "active": active == "1",
                    "name": name,
                    "text": txt,
                })
        return result

    # ------------------------------------------------------------------ #
    #  等待
    # ------------------------------------------------------------------ #

    def wait_for_text(self, node_name: str, expected: str, *,
                      window_name: str = None,
                      instance_id: int = None,
                      exact: bool = True,
                      strip_tags: bool = False,
                      timeout: float = 10.0,
                      interval: float = 0.5) -> bool:
        """轮询等待节点文本变为指定值（使用定向快速路径）。

        Args:
            strip_tags: True 时剥离富文本后再比较。
            exact: True = 精确匹配；False = 包含匹配。
        Returns:
            True 如果在超时前满足条件，否则 False。
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            current = self.get_text(node_name,
                                    window_name=window_name,
                                    instance_id=instance_id,
                                    strip_tags=strip_tags)
            if current is not None:
                matched = (current == expected) if exact else (expected in current)
                if matched:
                    return True
            time.sleep(interval)
        return False

    def wait_for_text_change(self, node_name: str, *,
                             window_name: str = None,
                             instance_id: int = None,
                             strip_tags: bool = False,
                             timeout: float = 10.0,
                             interval: float = 0.5) -> str | None:
        """等待节点文本发生变化，返回变化后的新文本。

        Returns:
            新文本（按 strip_tags 设置处理），或超时返回 None。
        """
        initial = self.get_text(node_name,
                                window_name=window_name,
                                instance_id=instance_id,
                                strip_tags=strip_tags)
        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(interval)
            current = self.get_text(node_name,
                                    window_name=window_name,
                                    instance_id=instance_id,
                                    strip_tags=strip_tags)
            if current != initial:
                return current
        return None

    # ------------------------------------------------------------------ #
    #  断言
    # ------------------------------------------------------------------ #

    def assert_text(self, node_name: str, expected: str, *,
                    window_name: str = None,
                    instance_id: int = None,
                    contains: bool = False,
                    strip_tags: bool = False,
                    msg: str = None):
        """断言节点的 TMP 文本内容。

        Args:
            expected: 期望文本。
            contains: False = 精确匹配；True = 包含匹配。
            strip_tags: True 时先剥离富文本标签再断言。
        Raises:
            AssertionError: 文本不匹配。
            UnityAPIError: 节点未找到。
        """
        actual = self.get_text(node_name,
                               window_name=window_name,
                               instance_id=instance_id,
                               strip_tags=strip_tags)
        if actual is None:
            scope = f" in '{window_name}'" if window_name else ""
            raise UnityAPIError(f"节点 '{node_name}'{scope} 未找到或无 TMP 组件")

        if contains:
            ok = expected in actual
            fail_msg = msg or (
                f"节点 '{node_name}' 文本不包含期望值\n"
                f"  期望包含: {expected!r}\n"
                f"  实际值:   {actual!r}"
            )
        else:
            ok = actual == expected
            fail_msg = msg or (
                f"节点 '{node_name}' 文本不匹配\n"
                f"  期望: {expected!r}\n"
                f"  实际: {actual!r}"
            )
        assert ok, fail_msg

    def assert_text_at(self, node_name: str, index: int, expected: str, *,
                       window_name: str = None,
                       instance_id: int = None,
                       contains: bool = False,
                       strip_tags: bool = False,
                       msg: str = None):
        """断言第 N 个同名节点的 TMP 文本（列表/网格场景）。

        Args:
            index: 0-based 索引。
            expected: 期望文本。
            contains: False = 精确；True = 包含。
            strip_tags: True 时剥离富文本后断言。
        Raises:
            AssertionError: 文本不匹配。
            UnityAPIError: 节点未找到或索引越界。
        """
        texts = self.get_texts(node_name,
                               window_name=window_name,
                               instance_id=instance_id,
                               strip_tags=strip_tags)
        if index < 0 or index >= len(texts):
            scope = f" in '{window_name}'" if window_name else ""
            raise UnityAPIError(
                f"节点 '{node_name}'[{index}]{scope} 不存在（共 {len(texts)} 个）"
            )
        actual = texts[index]

        if contains:
            ok = expected in actual
            fail_msg = msg or (
                f"节点 '{node_name}'[{index}] 文本不包含期望值\n"
                f"  期望包含: {expected!r}\n"
                f"  实际值:   {actual!r}"
            )
        else:
            ok = actual == expected
            fail_msg = msg or (
                f"节点 '{node_name}'[{index}] 文本不匹配\n"
                f"  期望: {expected!r}\n"
                f"  实际: {actual!r}"
            )
        assert ok, fail_msg

    def assert_text_pattern(self, node_name: str, pattern: str, *,
                            window_name: str = None,
                            instance_id: int = None,
                            index: int = 0,
                            strip_tags: bool = True,
                            msg: str = None):
        """断言节点文本符合正则表达式模式（适用于含动态数字/时间的文本）。

        Args:
            pattern: Python 正则表达式（re 语法）。
            index: 同名多节点时指定第几个（0-based）。
            strip_tags: True 时先剥离富文本再匹配（默认开启）。
        Raises:
            AssertionError: 正则不匹配。
            UnityAPIError: 节点未找到。

        Examples:
            tr.assert_text_pattern("text_refresh", r"活动结束：\\d+天\\d+小时")
            tr.assert_text_pattern("text_tips",    r"\\d+天后解锁")
        """
        actual = self.get_text_at(node_name, index,
                                  window_name=window_name,
                                  instance_id=instance_id,
                                  strip_tags=strip_tags)
        if actual is None:
            scope = f" in '{window_name}'" if window_name else ""
            raise UnityAPIError(f"节点 '{node_name}'[{index}]{scope} 未找到")

        ok = bool(re.search(pattern, actual))
        fail_msg = msg or (
            f"节点 '{node_name}'[{index}] 文本不匹配正则 {pattern!r}\n"
            f"  实际值: {actual!r}"
        )
        assert ok, fail_msg

    def assert_progress(self, node_name: str, *,
                        window_name: str = None,
                        instance_id: int = None,
                        index: int = 0,
                        min_ratio: float = None,
                        max_ratio: float = None,
                        min_val: float = None,
                        max_val: float = None,
                        exact_val: float = None,
                        msg: str = None):
        """断言进度条文本（"当前值/总量" 格式）满足条件。

        参数优先级（可组合使用）：
            min_ratio / max_ratio — 当前值/总量的比值范围（如 min_ratio=1.0 表示 >= 100%）
            min_val / max_val     — 当前值的绝对范围
            exact_val             — 当前值精确等于

        Raises:
            AssertionError: 条件不满足。
            UnityAPIError: 节点未找到或文本不是进度格式。

        Examples:
            tr.assert_progress("slider_txt", min_ratio=1.0)
            tr.assert_progress("slider_txt", min_val=10, window_name="ShopWindow")
            tr.assert_progress("slider_txt", index=1, exact_val=0)
        """
        result = self.get_progress(node_name, window_name=window_name,
                                   instance_id=instance_id, index=index)
        if result is None:
            raw = self.get_text_at(node_name, index,
                                   window_name=window_name,
                                   instance_id=instance_id)
            scope = f" in '{window_name}'" if window_name else ""
            raise UnityAPIError(
                f"节点 '{node_name}'[{index}]{scope} 无法解析为进度格式（当前值={raw!r}）"
            )

        current, total = result
        ratio = (current / total) if total != 0 else 0.0

        checks = []
        if min_ratio is not None:
            checks.append((ratio >= min_ratio,
                           f"进度比值 {ratio:.2%} < 期望最小值 {min_ratio:.2%}"))
        if max_ratio is not None:
            checks.append((ratio <= max_ratio,
                           f"进度比值 {ratio:.2%} > 期望最大值 {max_ratio:.2%}"))
        if min_val is not None:
            checks.append((current >= min_val,
                           f"当前值 {current} < 期望最小值 {min_val}"))
        if max_val is not None:
            checks.append((current <= max_val,
                           f"当前值 {current} > 期望最大值 {max_val}"))
        if exact_val is not None:
            checks.append((current == exact_val,
                           f"当前值 {current} != 期望值 {exact_val}"))

        for ok, reason in checks:
            assert ok, msg or (
                f"节点 '{node_name}'[{index}] 进度断言失败：{reason}\n"
                f"  进度文本: {current}/{total} ({ratio:.2%})"
            )

    def assert_number(self, node_name: str, *,
                      window_name: str = None,
                      instance_id: int = None,
                      index: int = 0,
                      eq: float = None,
                      gt: float = None,
                      gte: float = None,
                      lt: float = None,
                      lte: float = None,
                      msg: str = None):
        """断言节点文本解析为数字后满足比较条件（自动剥离富文本）。

        Args:
            eq:  == 期望值
            gt:  >  期望值
            gte: >= 期望值
            lt:  <  期望值
            lte: <= 期望值
        Raises:
            AssertionError: 条件不满足。
            UnityAPIError: 节点未找到或文本不是数字。

        Examples:
            tr.assert_number("text_score", index=0, gte=40)
            tr.assert_number("text_num",   index=2, eq=5)
            tr.assert_number("text_level", gte=10, lt=100)
        """
        value = self.get_number(node_name, window_name=window_name,
                                instance_id=instance_id, index=index)
        if value is None:
            raw = self.get_text_at(node_name, index,
                                   window_name=window_name,
                                   instance_id=instance_id)
            scope = f" in '{window_name}'" if window_name else ""
            raise UnityAPIError(
                f"节点 '{node_name}'[{index}]{scope} 无法解析为数字（值={raw!r}）"
            )

        checks = []
        if eq  is not None: checks.append((value == eq,  f"{value} != {eq}"))
        if gt  is not None: checks.append((value >  gt,  f"{value} 不 > {gt}"))
        if gte is not None: checks.append((value >= gte, f"{value} 不 >= {gte}"))
        if lt  is not None: checks.append((value <  lt,  f"{value} 不 < {lt}"))
        if lte is not None: checks.append((value <= lte, f"{value} 不 <= {lte}"))

        for ok, reason in checks:
            assert ok, msg or (
                f"节点 '{node_name}'[{index}] 数值断言失败：{reason}"
            )

    # ------------------------------------------------------------------ #
    #  调试辅助
    # ------------------------------------------------------------------ #

    def print_all_texts(self, *, window_name: str = None,
                        instance_id: int = None,
                        include_inactive: bool = False,
                        strip_tags: bool = False):
        """打印指定范围内所有 TMP 节点及其文本（调试用）。"""
        scope = f"窗口 '{window_name}'" if window_name else "所有活跃窗口"
        texts = self.get_all_texts(window_name=window_name,
                                   instance_id=instance_id,
                                   include_inactive=include_inactive)
        print(f"=== TMP 文本 ({scope}, {len(texts)} 个节点名) ===")
        for name, vals in sorted(texts.items()):
            for v in vals:
                display = _strip_tags(v) if strip_tags else v
                display = display if len(display) <= 40 else display[:40] + "..."
                print(f"  {name:<35} {display!r}")

    def print_button_texts(self, *, window_name: str,
                           instance_id: int = None,
                           active_only: bool = True):
        """打印按钮及其 TMP 文本（调试用）。"""
        buttons = self.get_button_texts(window_name=window_name,
                                        instance_id=instance_id)
        filtered = [b for b in buttons if not active_only or b["active"]]
        print(f"=== 按钮文本 ('{window_name}', {len(filtered)} 个) ===")
        print(f"{'instanceID':>12}  {'active':>6}  {'name':<35}  text")
        print("-" * 80)
        for btn in filtered:
            status = "Y" if btn["active"] else "N"
            text = _strip_tags(btn["text"]) if len(btn["text"]) > 30 else btn["text"]
            text = text[:30] + "..." if len(text) > 30 else text
            print(f"{btn['instanceID']:>12}  {status:>6}  {btn['name']:<35}  {text!r}")
