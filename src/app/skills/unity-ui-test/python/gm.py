"""
GM 命令封装层
通过 LuaRemoteServer 远程执行 GmD.lua 中的 GM 指令，覆盖角色、道具、战斗、时间等常用测试场景。

所有方法本质上是构造 Lua 代码并通过 client.lua.exec/exec_sync 发送给 Unity 执行。
GM 指令最终由客户端的 GameServer:gm(...) 发送到服务端处理。

Usage:
    from unity_api import UnityClient
    from gm import GM

    client = UnityClient()
    gm = GM(client)
    gm.set_level(23)
    gm.clone_item(200001, 100000)
"""
import time
from unity_api import UnityClient


class GM:
    """GM 命令高级封装，映射 GmD.lua 中的常用指令。"""

    def __init__(self, client: UnityClient):
        self.client = client

    # ------------------------------------------------------------------ #
    #  底层调用
    # ------------------------------------------------------------------ #

    def raw(self, lua_code: str) -> str:
        """异步执行任意 Lua GM 代码（协程模式，支持 yield/网络请求）。"""
        return self.client.lua.exec(lua_code)

    def raw_sync(self, lua_code: str) -> str:
        """同步执行任意 Lua GM 代码。"""
        return self.client.lua.exec_sync(lua_code)

    def gm(self, *args: str) -> str:
        """发送任意 GM 指令。等价于 GmD.gm(...)。

        Args:
            *args: 传给 GameServer:gm() 的参数，以 Lua 字面量表示。
        Examples:
            gm.gm("'look_at'")
            gm.gm("'set_level'", "{23, 1}")
        """
        lua_args = ", ".join(str(a) for a in args)
        return self.client.lua.exec(f"GmD.gm({lua_args})")

    def eval(self, gs_expression: str) -> str:
        """在服务端执行任意 GS 表达式。等价于 GmD.eval(cmd)。

        Args:
            gs_expression: GS 语言表达式字符串。
        """
        escaped = gs_expression.replace("\\", "\\\\").replace("'", "\\'")
        return self.client.lua.exec(f"GmD.eval('{escaped}')")

    # ------------------------------------------------------------------ #
    #  等级与解锁
    # ------------------------------------------------------------------ #

    def set_level(self, level: int, sub_level: int = 1, default_type: str = None) -> str:
        """设置角色等级。

        Args:
            level: 主等级。
            sub_level: 子等级，默认 1。
            default_type: 可选，默认类型。
        """
        if default_type:
            return self.client.lua.exec(
                f"set_level({level}, {sub_level}, '{default_type}')"
            )
        return self.client.lua.exec(f"set_level({level}, {sub_level})")

    def set_sub_level(self, type_name: str, level: int) -> str:
        """设置小境界等级。

        Args:
            type_name: "hp" 或 "mp"。
            level: 目标等级。
        """
        return self.client.lua.exec(f"set_sub_level('{type_name}', {level})")

    def set_all_unlock(self) -> str:
        """一键解锁所有系统（最高等级+基础道具+秘境等）。"""
        return self.client.lua.exec("set_all_unlock()")

    def manual_unlock_systems(self) -> str:
        """手动解锁已到达等级的所有系统。"""
        return self.client.lua.exec("GmD.manual_unlock_systems()")

    def set_ashram_house_level(self, level: int) -> str:
        """设置洞府等级。"""
        return self.client.lua.exec(f"GmD.set_ashram_house_level({level})")

    def set_standard_char(self, standard_id: int) -> str:
        """设置标准人模板。"""
        return self.client.lua.exec(f"set_standard_char({standard_id})")

    # ------------------------------------------------------------------ #
    #  道具与背包
    # ------------------------------------------------------------------ #

    def clone_item(self, class_id: int, amount: int = 1,
                   quality: str = None, **params) -> str:
        """复制道具到背包。

        Args:
            class_id: 道具 class_id。
            amount: 数量，默认 1。
            quality: 品质，如 "orange"/"purple" 等，None 为默认品质。
            **params: 额外参数，如 level=50, refine_level=1。
        """
        args = f"{class_id}, {amount}"
        if quality:
            args += f", '{quality}'"
        else:
            args += ", nil"
        if params:
            param_str = ", ".join(f"{k}={_lua_value(v)}" for k, v in params.items())
            args += f", {{{param_str}}}"
        return self.client.lua.exec(f"clone({args})")

    def clone_range(self, from_id: int, to_id: int,
                    amount: int = 1, quality: str = None) -> str:
        """批量复制一个 class_id 区间内的所有道具。"""
        q = f"'{quality}'" if quality else "nil"
        return self.client.lua.exec(
            f"clone_range({from_id}, {to_id}, {amount}, {q})"
        )

    def add_base_items(self) -> str:
        """添加一套基础道具（灵石、机缘、仙元等）。"""
        return self.client.lua.exec("add_base_items()")

    def drop_all(self) -> str:
        """清空背包中所有可清除的道具。"""
        return self.client.lua.exec("drop_all()")

    def drop_all_coin(self) -> str:
        """清空所有货币类道具。"""
        return self.client.lua.exec("drop_all_coin()")

    def drop_item(self, rid: str, baggage_name: str = None) -> str:
        """按 RID 删除单个道具。"""
        if baggage_name:
            return self.client.lua.exec(
                f"GmD.drop_item('{rid}', '{baggage_name}')"
            )
        return self.client.lua.exec(f"GmD.drop_item('{rid}')")

    def set_bag_capacity(self, capacity: int) -> str:
        """设置背包容量。"""
        return self.client.lua.exec(f"set_bag_capacity({capacity})")

    # ------------------------------------------------------------------ #
    #  属性与战斗
    # ------------------------------------------------------------------ #

    def set_hp_mp(self, hp: int = -1, mp: int = -1,
                  hp_es: int = -1, mp_es: int = -1) -> str:
        """设置角色属性值（-1 表示不修改）。"""
        return self.client.lua.exec(
            f"set_my_query({hp}, {mp}, {hp_es}, {mp_es})"
        )

    def full_hp_mp(self) -> str:
        """补满 HP 和 MP。"""
        return self.client.lua.exec("full_hp_mp()")

    def kill_all_entity(self, prevent_born: bool = False) -> str:
        """击杀当前房间所有实体。"""
        lua_bool = "true" if prevent_born else "false"
        return self.client.lua.exec(f"kill_all_entity({lua_bool})")

    def kill_self(self) -> str:
        """击杀自己。"""
        return self.client.lua.exec("kill_self_entity()")

    def reborn_self(self) -> str:
        """复活自己。"""
        return self.client.lua.exec("GmD.reborn_self_entity()")

    def add_buff(self, buff_id: int, caster_rid: str, skill_id: int = 0) -> str:
        """给当前选中的实体添加 buff。"""
        return self.client.lua.exec(
            f"add_buff({buff_id}, '{caster_rid}', {skill_id})"
        )

    def remove_all_buff(self) -> str:
        """移除当前选中实体的所有 buff。"""
        return self.client.lua.exec("remove_all_buff()")

    def set_ent_kill_in_one(self, enable: bool = True) -> str:
        """设置一击必杀模式。"""
        lua_bool = "true" if enable else "false"
        return self.client.lua.exec(f"set_ent_kill_in_one({lua_bool})")

    def clear_strength(self) -> str:
        """清空体力。"""
        return self.client.lua.exec("clear_strength()")

    def full_strength(self) -> str:
        """补满体力。"""
        return self.client.lua.exec("full_strength()")

    # ------------------------------------------------------------------ #
    #  时间操控
    # ------------------------------------------------------------------ #

    def shift_add_time(self, seconds: int = 0, mins: int = 0,
                       hours: int = 0, days: int = 0) -> str:
        """偏移服务器时间（累加）。"""
        return self.client.lua.exec(
            f"debug_shift_add_time({seconds}, {mins}, {hours}, {days})"
        )

    def shift_add_one_day(self) -> str:
        """服务器时间前进一天。"""
        return self.client.lua.exec("debug_shift_add_one_day()")

    def shift_add_one_week(self) -> str:
        """服务器时间前进一周。"""
        return self.client.lua.exec("debug_shift_add_one_week()")

    def refresh_daily(self) -> str:
        """刷新每日数据。"""
        return self.client.lua.exec("debug_refresh_user_daily_data()")

    def refresh_weekly(self) -> str:
        """刷新每周数据。"""
        return self.client.lua.exec("debug_refresh_user_weekly_data()")

    def show_server_time(self) -> str:
        """打印当前服务器时间。"""
        return self.client.lua.exec("debug_cur_time()")

    # ------------------------------------------------------------------ #
    #  任务
    # ------------------------------------------------------------------ #

    def clear_task(self) -> str:
        """清除所有任务。"""
        return self.client.lua.exec("GmD.clear_task()")

    def assign_task(self, task_id: int) -> str:
        """分配指定任务。"""
        return self.client.lua.exec(f"GmD.assign_task({task_id})")

    def accept_task(self, task_id: int) -> str:
        """接受指定任务。"""
        return self.client.lua.exec(f"GmD.accept_task({task_id})")

    def finish_task(self, task_id: int) -> str:
        """完成指定任务。"""
        return self.client.lua.exec(f"GmD.finish_task({task_id})")

    def reset_task(self, skip_tasks: str = "") -> str:
        """重置任务。"""
        return self.client.lua.exec(f"GmD.reset_task('{skip_tasks}')")

    # ------------------------------------------------------------------ #
    #  配方
    # ------------------------------------------------------------------ #

    def unlock_drug_recipe(self, recipe_id: int) -> str:
        """解锁丹方。"""
        return self.client.lua.exec(f"unlock_drug_recipes({recipe_id})")

    def unlock_forge_recipe(self, recipe_id: int) -> str:
        """解锁图纸。"""
        return self.client.lua.exec(f"unlock_forge_recipes({recipe_id})")

    def forget_drug_recipe(self, recipe_id: int) -> str:
        """遗忘丹方。"""
        return self.client.lua.exec(f"forget_drug_recipes({recipe_id})")

    def forget_forge_recipe(self, recipe_id: int) -> str:
        """遗忘图纸。"""
        return self.client.lua.exec(f"forget_forge_recipes({recipe_id})")

    # ------------------------------------------------------------------ #
    #  道院 / 宗门
    # ------------------------------------------------------------------ #

    def create_test_gangs(self, num: int, room_id: int = 0,
                          full_member: bool = False) -> str:
        """创建测试道院。"""
        lua_bool = "true" if full_member else "false"
        return self.client.lua.exec(
            f"debug_create_test_gangs({num}, {room_id}, {lua_bool})"
        )

    def set_self_gang_owner(self, robot_num: int = 0) -> str:
        """将自己设为道院掌门。"""
        return self.client.lua.exec(f"debug_set_self_gang_owner({robot_num})")

    def add_gang_contribute(self, num: int) -> str:
        """增加道院贡献。"""
        return self.client.lua.exec(f"debug_add_gang_contribute({num})")

    def set_gang_level(self, level: int, exp: int = 0) -> str:
        """设置道院等级和经验。"""
        return self.client.lua.exec(f"debug_set_gang_lv_and_exp({level}, {exp})")

    # ------------------------------------------------------------------ #
    #  机器人 / 怪物
    # ------------------------------------------------------------------ #

    def add_robot(self, count: int = 1, room_class_id: int = 0,
                  room_line: int = -1, ashram_type: str = "default",
                  level: int = 6, auto_atk: bool = True,
                  standard_id: int = 6) -> str:
        """添加服务器机器人。"""
        lua_atk = "true" if auto_atk else "false"
        return self.client.lua.exec(
            f"server_robot_add({count}, {room_class_id}, {room_line}, "
            f"'{ashram_type}', {level}, {lua_atk}, {standard_id}, 0, 0, '80,80')"
        )

    def clear_robots(self) -> str:
        """清除所有服务器机器人。"""
        return self.client.lua.exec("server_robot_clear()")

    def del_robot(self, count: int = 1, room_class_id: int = 0,
                  room_line: int = -1) -> str:
        """删除服务器机器人。"""
        return self.client.lua.exec(
            f"server_robot_del({count}, {room_class_id}, {room_line})"
        )

    def add_monster(self, class_id: int, level: int = 1,
                    auto_atk: bool = False, distance: int = 30) -> str:
        """在英雄附近生成怪物。"""
        lua_atk = "true" if auto_atk else "false"
        return self.client.lua.exec(
            f"server_monster_add3({class_id}, {level}, {lua_atk}, {distance})"
        )

    def del_monster(self, monster_rid: str) -> str:
        """删除指定怪物。"""
        return self.client.lua.exec(f"server_monster_del('{monster_rid}')")

    # ------------------------------------------------------------------ #
    #  灵兽
    # ------------------------------------------------------------------ #

    def add_pet(self, class_id: int, sid: int = 0, level: int = 1,
                sub_level: int = 0) -> str:
        """添加灵兽。"""
        return self.client.lua.exec(
            f"server_pet_add({class_id}, {sid}, {level}, {sub_level}, 0, 0, 0, 0)"
        )

    def remove_pet(self, sid: int) -> str:
        """移除灵兽。"""
        return self.client.lua.exec(f"server_pet_remove({sid})")

    def pet_full_energy(self) -> str:
        """灵兽能量补满。"""
        return self.client.lua.exec("server_pet_full_energy()")

    def pet_reset_cd(self) -> str:
        """灵兽技能冷却重置。"""
        return self.client.lua.exec("server_pet_reset_cd()")

    # ------------------------------------------------------------------ #
    #  功法 / 神通
    # ------------------------------------------------------------------ #

    def set_gongfa_learn(self, times: int = 999) -> str:
        """设置一键感悟次数。"""
        return self.client.lua.exec(f"GmD.set_gongfa_learn({times})")

    def add_gongfa(self, gongfa_id: int, xiuxing_level: int = 0,
                   major_level: int = 0, num: int = 1) -> str:
        """添加功法。"""
        return self.client.lua.exec(
            f"add_gongfa({gongfa_id}, {xiuxing_level}, {major_level}, {num})"
        )

    def clear_gongfa(self) -> str:
        """清除所有功法。"""
        return self.client.lua.exec("clear_gongfa()")

    def add_shentong(self, shentong_id: int, level: int = 1,
                     num: int = 1, xiuxing: int = 0) -> str:
        """添加神通。"""
        return self.client.lua.exec(
            f"add_gongfa_shentong({shentong_id}, {level}, {num}, {xiuxing})"
        )

    def skill_unlock_all(self) -> str:
        """解锁所有技能。"""
        return self.client.lua.exec("skill_unlock_all()")

    # ------------------------------------------------------------------ #
    #  秘境 / 地图
    # ------------------------------------------------------------------ #

    def unlock_temple(self, temple_id: int = 0) -> str:
        """解锁秘境。0 = 所有。"""
        return self.client.lua.exec(f"unlock_temple({temple_id})")

    def unlock_grid_map(self) -> str:
        """解锁大地图。"""
        return self.client.lua.exec("unlock_grid_map()")

    def unlock_grid_temple(self) -> str:
        """解锁秘境地图。"""
        return self.client.lua.exec("unlock_grid_temple()")

    # ------------------------------------------------------------------ #
    #  引导与新手
    # ------------------------------------------------------------------ #

    def clear_guides(self) -> str:
        """清除所有引导。"""
        return self.client.lua.exec("clear_guides()")

    def remove_guide(self, guide_id: int) -> str:
        """移除指定引导。"""
        return self.client.lua.exec(f"remove_guide({guide_id})")

    # ------------------------------------------------------------------ #
    #  邮件
    # ------------------------------------------------------------------ #

    def send_reward_mail(self) -> str:
        """发送奖励邮件。"""
        return self.client.lua.exec("send_reward_mail()")

    def send_no_reward_mail(self) -> str:
        """发送无奖励邮件。"""
        return self.client.lua.exec("send_no_reward_mail()")

    # ------------------------------------------------------------------ #
    #  账号
    # ------------------------------------------------------------------ #

    def clear_self(self) -> str:
        """清档当前账号（危险操作）。"""
        return self.client.lua.exec("clear_self()")

    def logout(self) -> str:
        """退出登录。"""
        return self.client.lua.exec("logout_user()")

    # ------------------------------------------------------------------ #
    #  调试
    # ------------------------------------------------------------------ #

    def simulate_disconnect(self) -> str:
        """模拟掉线。"""
        return self.client.lua.exec("simulate_lost_connect()")

    def enable_network_debug(self, enable: bool = True) -> str:
        """开启/关闭网络调试日志。"""
        lua_bool = "true" if enable else "false"
        return self.client.lua.exec(f"enable_network_debug({lua_bool})")

    def add_reward(self, reward_id: int, num: int = 1) -> str:
        """添加奖励。"""
        return self.client.lua.exec(f"add_reward({reward_id}, {num})")

    # ------------------------------------------------------------------ #
    #  查询（返回值）
    # ------------------------------------------------------------------ #

    def query_item_amount(self, class_id: int) -> str:
        """查询道具数量。"""
        return self.client.lua.eval(
            f"BaggageD.get_class_id_amount({class_id})"
        )

    def query_user_field(self, field: str) -> str:
        """查询角色字段值。"""
        return self.client.lua.eval(f"USER:query('{field}')")

    def query_user_level(self) -> str:
        """查询角色当前等级。"""
        return self.client.lua.eval("USER:get_level()")

    def query_user_attrib(self, attrib: str) -> str:
        """查询角色属性值。"""
        return self.client.lua.eval(f"MeD.query_user_attrib('{attrib}')")


def _lua_value(v) -> str:
    """将 Python 值转为 Lua 字面量。"""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)
