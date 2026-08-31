# GM Commands Guide

通过 Python 封装远程执行游戏 GM 指令，用于快速搭建测试环境、操控角色状态和验证功能。

## 原理

GM 指令的调用链路：

```
Python (gm.py) → HTTP API → Unity LuaRemoteServer → GmD.lua → GameServer:gm(...) → 服务端处理
```

`python/gm.py` 将 GmD.lua 中的 GM 函数封装为 Python 方法，内部构造 Lua 代码通过 `client.lua.exec()` 发送到 Unity 运行时执行。

## 前提条件

1. Unity 编辑器已打开且处于 **Play Mode**
2. LuaRemoteServer 已启动（端口 16666）
3. 角色已登录游戏

## 初始化

参照 SKILL.md 的「路径约定与初始化」完成 sys.path 设置后：

```python
from unity_api import UnityClient
from gm import GM

client = UnityClient()
gm = GM(client)
```

## 常用操作速查

### 等级与解锁

```python
gm.set_level(23)                    # 设置等级为 23
gm.set_level(23, 1)                 # 设置等级 23，子等级 1
gm.set_sub_level("hp", 5)           # 设置体力小境界等级

gm.set_all_unlock()                 # 一键解锁所有系统（含基础道具发放）
gm.manual_unlock_systems()          # 解锁当前等级应有的系统
gm.set_ashram_house_level(16)       # 设置洞府等级
gm.set_standard_char(6)             # 设置标准人
```

### 道具与背包

```python
gm.clone_item(200001, 100000000)          # 添加灵石 1 亿
gm.clone_item(200002, 100000)             # 添加机缘 10 万
gm.clone_item(60440, 1, "orange", level=50, refine_level=1)  # 添加橙色法宝

gm.add_base_items()                       # 添加一套基础道具
gm.clone_range(200001, 200010, 1000)      # 批量复制区间道具

gm.drop_all()                             # 清空背包
gm.drop_all_coin()                        # 清空货币
gm.set_bag_capacity(200)                  # 设置背包容量

amount = gm.query_item_amount(200001)     # 查询道具数量
```

### 属性与战斗

```python
gm.full_hp_mp()                      # 补满 HP/MP
gm.set_hp_mp(hp=1000, mp=500)        # 设置 HP=1000, MP=500（-1 不修改）
gm.full_strength()                    # 补满体力
gm.clear_strength()                   # 清空体力

gm.set_ent_kill_in_one(True)          # 开启一击必杀
gm.kill_all_entity()                  # 击杀房间所有实体
gm.kill_all_entity(prevent_born=True) # 击杀并阻止刷新
gm.kill_self()                        # 击杀自己
gm.reborn_self()                      # 复活

gm.add_buff(1001, caster_rid, 0)      # 添加 buff
gm.remove_all_buff()                  # 移除所有 buff
```

### 时间操控

```python
gm.show_server_time()                # 查看当前服务器时间
gm.shift_add_one_day()               # 时间前进 1 天
gm.shift_add_one_week()              # 时间前进 1 周
gm.shift_add_time(hours=3)           # 时间前进 3 小时
gm.shift_add_time(days=2, hours=5)   # 时间前进 2 天 5 小时

gm.refresh_daily()                   # 刷新每日数据
gm.refresh_weekly()                  # 刷新每周数据
```

### 任务

```python
gm.assign_task(10001)                # 分配任务
gm.accept_task(10001)                # 接受任务
gm.finish_task(10001)                # 完成任务
gm.clear_task()                      # 清除所有任务
gm.reset_task()                      # 重置任务
```

### 机器人与怪物

```python
gm.add_robot(count=5, level=10)                    # 添加 5 个 10 级机器人
gm.add_robot(count=3, room_class_id=10001, level=6)  # 在指定房间添加
gm.del_robot(count=2)                              # 删除 2 个机器人
gm.clear_robots()                                  # 清除所有机器人

gm.add_monster(class_id=55000, level=5, distance=30)  # 在附近生成怪物
gm.del_monster("monster_rid_here")                    # 删除指定怪物
```

### 灵兽

```python
gm.add_pet(class_id=330004, level=10)   # 添加灵兽
gm.remove_pet(sid=1)                    # 移除灵兽
gm.pet_full_energy()                    # 补满灵兽能量
gm.pet_reset_cd()                       # 重置灵兽技能冷却
```

### 功法与神通

```python
gm.set_gongfa_learn(999)                         # 设置感悟次数
gm.add_gongfa(gongfa_id=1001, xiuxing_level=10)  # 添加功法
gm.clear_gongfa()                                # 清除所有功法
gm.add_shentong(251101, level=5)                  # 添加神通
gm.skill_unlock_all()                             # 解锁所有技能
```

### 秘境与地图

```python
gm.unlock_temple()          # 解锁所有秘境
gm.unlock_temple(10001)     # 解锁指定秘境
gm.unlock_grid_map()        # 解锁大地图
gm.unlock_grid_temple()     # 解锁秘境地图
```

### 道院

```python
gm.create_test_gangs(5)                        # 创建 5 个测试道院
gm.set_self_gang_owner()                       # 设自己为掌门
gm.add_gang_contribute(10000)                  # 增加道院贡献
gm.set_gang_level(10)                          # 设置道院等级
```

### 引导与邮件

```python
gm.clear_guides()           # 清除所有引导
gm.remove_guide(1001)       # 移除指定引导
gm.send_reward_mail()       # 发送奖励邮件
gm.send_no_reward_mail()    # 发送无奖励邮件
```

### 账号与调试

```python
gm.logout()                      # 退出登录
gm.clear_self()                  # 清档（危险）
gm.simulate_disconnect()         # 模拟掉线
gm.enable_network_debug(True)    # 开启网络调试
```

### 查询接口

```python
gm.query_item_amount(200001)         # 查询道具数量
gm.query_user_level()                # 查询角色等级
gm.query_user_field("name")          # 查询角色字段
gm.query_user_attrib("hp_max")       # 查询角色属性
```

## 底层调用

当封装方法不满足需求时，可直接执行 Lua 代码：

```python
# 执行任意 Lua（协程模式）
gm.raw("GameServer:gm('some_custom_gm', param1, param2)")

# 执行任意 Lua（同步模式）
gm.raw_sync("print(USER:query('name'))")

# 执行服务端 GS 表达式
gm.eval('RID("player_rid")=>some_method()')

# 发送原始 GM 指令
gm.gm("'set_level'", "{23, 1}")
```

## 典型测试场景

### 快速搭建测试环境

```python
from unity_api import UnityClient
from gm import GM

client = UnityClient()
gm = GM(client)

gm.set_all_unlock()           # 全解锁
gm.clone_item(200001, 1e8)    # 大量灵石
gm.clone_item(200002, 1e5)    # 大量机缘
gm.full_hp_mp()               # 满血满蓝
gm.clear_guides()             # 跳过引导
```

### 战斗测试环境

```python
gm.set_level(23)
gm.set_all_unlock()
gm.skill_unlock_all()
gm.full_hp_mp()
gm.full_strength()
gm.add_monster(class_id=55000, level=5, distance=30)
```

### 跨日测试

```python
gm.shift_add_one_day()
gm.refresh_daily()
# ... 执行测试 ...
gm.shift_add_one_day()
gm.refresh_daily()
# ... 验证第二天状态 ...
```

## 注意事项

- GM 指令通过网络发送到服务端，执行结果有延迟，必要时使用 `time.sleep()` 等待
- `set_all_unlock()` 会修改大量角色数据，仅在测试环境使用
- `clear_self()` 会永久清档，操作不可逆
- 时间操控类指令会影响服务器上所有玩家，谨慎使用
- 部分 GM 指令在非编辑器环境下需二次确认弹窗，自动化时使用编辑器模式可跳过
