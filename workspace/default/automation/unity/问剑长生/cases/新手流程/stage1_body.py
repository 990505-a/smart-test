# ============================================================================
# STAGE 1　启动界面 → 登出 → 注册并登录 → 创角改名 → 踏入仙途 → 新手主界面
#   起跑线：GameRoot/Canvas2D/Normal/BootWindow(Clone)（启动界面）
#   本段 2026-09-23 在本工程实跑通过（exit 0，290s）；合并后仅把断言换成不依赖
#   被闸门拦住的工具的那一套，并给角色名加了"重名就换名重试"。
# ============================================================================
import random

BOOT = "GameRoot/Canvas2D/Normal/BootWindow(Clone)"
AVATAR = BOOT + "/panel/right_top_panel/btn_user_center"
USER_CENTER = "GameRoot/Canvas2D/Normal/UserCenterWindow(Clone)"
ACCOUNT = "GameRoot/Canvas2D/Normal/AccountWindow(Clone)"
CREATE = "GameRoot/Canvas2D/Normal/CreateCharacterWindow(Clone)"
GUIDE = "GameRoot/Canvas2D/Normal/GuideChooseSkipWindow(Clone)"
TASKWIN = "GameRoot/Canvas2D/Normal/TaskWindow(Clone)"
SIMPLE_TIP = "GameRoot/Canvas2D/Top/SimpleTipWindow(Clone)/simpleTip/text_simple"

# 角色名：3 个汉字（服务端要求 2~6 字），每次随机拼 —— 上一轮建的角色名会被服务端
# 记着，用固定名跑第二遍会撞「名字已存在，请重新输入。」，然后流程卡死在创角界面。
_GIVEN = ["无痕", "青锋", "长歌", "行舟", "扶摇", "照野", "临风", "听雪", "沧浪", "问剑"]
_TAIL = "云川舟山风月华星岳"


def new_name():
    return random.choice(_GIVEN) + random.choice(_TAIL)


def create_character(name, timeout=200):
    """写名字 → 踏入仙途；被服务端以「名字已存在/非法」拒绝就换个名字重来。

    返回真正被服务端接受的名字。三步一循环，最多换 3 个名字。
    """
    for attempt in range(3):
        wait_visible(CREATE + "/root/face_state/panel_create/bottom/input_name", 20)
        u.set_text(CREATE + "/root/face_state/panel_create/bottom/input_name", name)
        time.sleep(1.0)
        txt = text_of(CREATE + "/root/face_state/panel_create/bottom", 5)
        assert name in txt, "角色名未写入输入框：%r" % txt[:200]
        print("STEP: 角色名已写入 -> %s（第 %d 次尝试）" % (name, attempt + 1))
        u.screenshot("04_name_input.png")
        u.click(CREATE + "/root/face_state/panel_create/btn_ok")

        t0 = time.time()
        rejected = ""
        while time.time() - t0 < timeout:
            if is_visible(GUIDE):
                return name
            if is_visible(SIMPLE_TIP):
                rejected = text_of(SIMPLE_TIP, 1)
                if rejected:
                    break
            time.sleep(1.0)
        else:
            raise AssertionError(
                "点「踏入仙途」后既没出现身份弹窗、也没有拒绝提示（等了 %ss）" % timeout)
        print("WARN: 服务端拒绝了这个角色名：%s —— 换名重试" % rejected[:100])
        time.sleep(1.5)
    raise AssertionError("连续 3 个角色名都被服务端拒绝，创角没能完成")


stage("STAGE 1 注册创角启程")
require_play_mode()
check_console("baseline")

# --- 1. 起跑线：启动界面 ---
# 平台不复位：这一条要求游戏停在**启动界面**（新号流程由本用例自己走完登出→注册→创角）。
# 不在就当场停下并说清该恢复成什么样 —— 别跑到"点右上角头像"才发现点的是别的东西。
at_start_line(BOOT, "(启动界面 BootWindow)")
wait_visible(BOOT, 60, "(启动界面)")
u.screenshot("01_boot.png")

# --- 2. 点右上角人物头像 ---
tap(AVATAR, 20, "(右上角头像)")

# --- 3. 已登录则先登出，再点一次头像 ---
time.sleep(2)
if is_visible(USER_CENTER):
    print("STEP: 当前为已登录状态，先登出")
    expect_text(USER_CENTER + "/btn_logout/text", "登出")
    tap(USER_CENTER + "/btn_logout", 15, "(登出)")
    wait_hidden(USER_CENTER, 20, "(用户中心)")
    tap(AVATAR, 20, "(右上角头像)")
else:
    print("STEP: 当前为未登录状态，直接进入登录/注册窗")

wait_visible(ACCOUNT, 30, "(登录/注册窗)")
u.screenshot("02_account.png")

# --- 4. 注册 → 随机账号 → 注册并登录 ---
tap(ACCOUNT + "/adapter/btn_list/btn_register", 20, "(注册页签)")
wait_visible(ACCOUNT + "/adapter/btn_random", 15, "(随机账号)")
tap(ACCOUNT + "/adapter/btn_random", 15, "(随机账号)")
time.sleep(1)
print("STEP: 随机账号已生成 -> " + text_of(ACCOUNT + "/adapter", 5)[:160])
tap(ACCOUNT + "/adapter/btn_list/btn_register_and_login", 20, "(注册并登录)")

# --- 5. 等过场动画结束、创角界面出现（实测约 90s，机器卡时更久）---
wait_visible(CREATE, 200, "(注册并登录后的过场动画)")
u.screenshot("03_create_character.png")

# --- 6. 选择角色 → 下一步 → 进入预览 ---
tap(CREATE + "/root/panel_select_body/btn_select", 20, "(选择角色)")
wait_visible(CREATE + "/root/face_state/choose_life_panel", 20, "(出身面板)")
tap(CREATE + "/root/face_state/choose_life_panel/choose_shape/btn_face_next", 20, "(出身-下一步)")
wait_visible(CREATE + "/root/panel_select_face/bottom/tab_root/btn_face_apply", 20, "(形象预览)")
tap(CREATE + "/root/panel_select_face/bottom/tab_root/btn_face_apply", 20, "(进入预览)")

# --- 7. 命名 → 踏入仙途（重名自动换名）---
NAME = create_character(new_name())

# --- 8. 身份选择弹窗 → 启程 → 落地新手主界面 ---
wait_visible(GUIDE, 200, "(踏入仙途后的服务端创角)")
expect_text(GUIDE + "/CommonFrame/content", "启程")
u.screenshot("05_guide_choose.png")
tap(GUIDE + "/CommonFrame/content/btn_go", 20, "(启程)")
wait_visible(TASKWIN, 120, "(启程后进入新手主界面)")
u.screenshot("06_started.png")

# --- 9. 无新增报错 ---
check_console("STAGE1")
print("STAGE 1 DONE: 登出→注册并登录→创角(%s)→启程（新手主界面已出现）" % NAME)
