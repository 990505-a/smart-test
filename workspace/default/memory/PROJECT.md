# PROJECT.md — 项目上下文

> 项目级的固定事实（路径、端口、环境）。会变的信息别写这里。

- **2026-09-17 21:40** · 项目上下文 · _agent_

  芋道(ruoyi-vue-pro)登录参数校验需求:平台核对了 /Users/yun/Documents/ruoyi-vue-pro 源码,AuthLoginReqVO.java L25-33 的注解与需求 REQ-LOGIN-001~010 的规则/文案逐条一致(@NotEmpty"登录账号不能为空"/@Length(4,30)"账号长度为 4-30 位"/@Pattern"^[a-zA-Z0-9]{4,30}$""账号格式为数字以及字母"/密码@Length(4,16)"密码长度为 4-16 位");AdminAuthServiceImpl.java L76 @Value("${yudao.captcha.enable:true}") 默认 true,L198-207 关闭时跳过校验;ErrorCodeConstants.java L13 账号密码错误文案「登录失败，账号密码不正确」。本地仓库 yudao-ui/ 前端源码不完整(仅 MES 片段),完整前端在部署环境 http://yudao-admin,登录页断言以页面实际提示为准,必要时用浏览器实测补证。

- **2026-09-19 18:33** · 项目上下文 · _agent_

  Unity 工程 jynew《群侠传，启动！》（/Users/yun/Documents/unity-games/jynew/jyx2，Unity 2022.3.61f1，MCP 桥 :5016，flavor=coplay）客户端 UI 与自动化要点（2026-09-19 实测）：
  
  - 根结构：MainCanvas/{MainUI, NormalUI, PopupUI, Top}。HUD 是 MainCanvas/MainUI/MainUIPanel(Clone)，右侧三入口路径 .../AnimRoot/Image-right/BtnRoot/{BagButton,XiakeButton,SystemButton}（中文文本为子节点 Text）。
  - NormalUI 下的面板（对象常驻，靠 activeSelf 开关，必须用 u.is_visible 判断，不能用 exists/expect_absent）：SystemUIPanel(Clone)（菜单项在 SelectionPanel/SelectMenu/SelectPanel/Container/{SaveButton,LoadButton,GraphicSettingsButton,MainMenuButton,ResumeGameBtn}）、BagUIPanel(Clone)（Btns/CloseBtn 关闭、FilterBtns/Filter{All,Item,Cost,Equipment,Book,Anqi}）、XiakeUIPanel(Clone)（BackButton 关闭；MainContent 下 NameText/InfoText/SkillText/ItemsText；队伍列表 RoleScroll/Viewport/RoleParent）、ChatUIPanel(Clone)（对话：Name/NameTxt、Content/MainContent/Panel/Text；MainBg=推进；选项在 SelectionPanel/SelectMenu/SelectPanel/Container 的 StorySelectionItem(Clone)）、InteractUIPanel(Clone)（BtnRoot/InteractiveButton1/MainBg 触发交互，2 号位为备用隐藏位）。
  - 移动：编辑器内键鼠/摇杆输入合成不可靠，用游戏自身接口 Jyx2.Jyx2_PlayerMovement.MoveToDestination(Vector3)（配合 NavMeshAgent.isStopped=false）。开局场景 01_moqiaoshanzhuang：玩家(26.6,0.12,1.8)，张云贤(26.56,0.10,0.42)、朱云天(15.34,0.06,9.12)、何云多(12.80,0.09,26.58)。
  - 对话推进：循环 click ChatUIPanel(Clone)/MainBg；出现选项时用 C# 取 Container 首个子项的 Button.onClick.Invoke()。选项无法用路径点击（同名克隆）。
  - 既有噪音（非用例失败）：开局 Console 有 XLua `no field __Hotfix0_Talk` 报错与 5 个 Jyx2Configs/*Helper 载入失败；本机录像合成 ffmpeg 退出码 187 一直失败，只写 WARN 不影响判定；截图偶发 `CaptureScreenshotAsTexture() failed ... end of frame`（动画中调用），重试即可。
  - 已入库用例：script_id=cfd3485f-8c20-4081-8f04-605fc0e1d608「群侠传 · 正常游戏流程冒烟」，覆盖 HUD/系统菜单/背包/侠客面板/走到 NPC 交互/剧情对话推进（含选项分支）/恢复自由探索，实测 3 次全过，单次约 13-21s。

- **2026-09-19 20:05** · 项目上下文 · _agent_

  jynew 新手流程冷启动链路与用例（2026-09-19 实测）：

  - 新手流程链路：0_MODLoaderScene（MOD 管理器，点 _ButtonsLayout/LaunchModButton）→ 0_MainMenu（GameMainMenu(Clone)，自动弹 ReleaseNotePanel 更新日志需点 MainBody/CloseButton）→ mainPanel/homeBtnAndTxtPanel/NewGameButton「重新开始」→ InputNamePanel/NameInput 输入姓名 + inputSure 确定 → StartNewRolePanel/YesBtn「满意」→ 进开局场景跑开场剧情 → 自由探索。
  - Build Settings 只有 4 个引导场景（0_Init/0_GameStart/0_MODLoaderScene/0_MainMenu），地图场景不在 Build Settings：RESET 起跑线只能用 Assets/0_MODLoaderScene.unity + wait_for=ModPanelLauncher（ModPanelNew(Clone) 是运行时克隆，按名查不到，不能当 wait_for）。
  - 实测开局场景是 70_xiaoxiamiju（小虾米居，JYX2 MOD 的 ka691 事件），不是 SAMPLE MapConfig 里标 START 的 00_mochuanlinju（渡城残魂传）：运行时实际加载的是 JYX2 MOD（LuaFilePatten=ka{0}）。注意 Assets/Mods/SAMPLE/ModSetting.asset 里 PlayerName=陶六一，但运行时 OnNewGame 实测走「输入姓名」分支——建角分支要以实测为准，用例已做双分支兼容。
  - 开场对话推进：循环 click ChatUIPanel(Clone)/MainBg，ka691 全程约 26-27 次点击（含 Timeline/PlayAnimation 段需轮询等待）；结束后 HUD（MainUIPanel(Clone)）左上显示「{主角名} 1 级 小虾米居」。
  - 克隆对象可见性：u.is_visible 对 MainUI 层克隆对象（ModPanelNew/GameMainMenu(Clone)）解析不可靠会恒 False；可靠写法是 u.find_objects(path=...) 取 objects[].activeInHierarchy。
  - 已入库用例：script_id=e22efa61-a393-4c2d-a114-3670c6f2ef49「群侠传 · 新手流程冒烟（启动模组→建角→开场剧情→自由探索）」，script 内置 self-reset（场景不是 0_MODLoaderScene 就 u.reset(hard)），实测 2 次全过，单次约 96s。

- **2026-09-20 02:06** · 项目上下文 · _agent_

  ruoyi-vue-pro（芋道）仓库结构事实（2026-09-04 HEAD 01a0eaf，master 分支，revision=2026.08-jdk8-SNAPSHOT，JDK8 + Spring Boot 2.7.18）：
  
  - **构建范围 ≪ 代码范围**：根 pom.xml 的 <modules> 只有 yudao-dependencies、yudao-framework（聚合）、yudao-server、yudao-module-system、yudao-module-infra 是激活的，其余 16 个业务模块（member/bpm/report/mp/pay/mall/crm/erp/iot/mes/wms/hrm/fms/pms/im/ai）全部被注释（pom.xml L17-35），注释理由写明"保证编译速度"。yudao-server/pom.xml 同样只依赖 system + infra，其余依赖注释（全文件 95 处 <!--）。结论：**磁盘上有 18 个模块的完整源码，但实际能编译运行/Maven 测试的只有 system + infra**；统计"测试覆盖率/用例分布"时必须区分这两个口径。
  - 磁盘源码量：main java 约 5.8 千文件 / 38.6 万行（不含 iot、mall 两个聚合模块的子模块）；最大的几个：mes 1122 文件/8.8 万行、hrm 577/5.5 万、system 419/2.7 万、crm 282、pms 281、im 279、fms 259。yudao-framework 下 15 个 starter 共约 350 文件 / 2.3 万行。
  - 聚合模块：yudao-module-iot → {iot-biz, iot-core, iot-gateway}；yudao-module-mall → {product, promotion, statistics, trade, trade-api}。它们自身 src 下没有 java，代码量统计要下钻一层。
  - **yudao-ui 前端几乎为空**：5 个子目录只有 README.md，加 yudao-ui-admin-vue3 下 6 个 MES 文件（src/api/mes/wm/{productreceipt,productreceipt/detail,productreceipt/line,sn}/index.ts + src/views/mes/wm/sn/index.vue），共 11 个文件。UI 自动化不能指望本地前端源码，只能对部署环境（http://yudao-admin）实测。
  - **URL 前缀由包名决定**（不是 context-path）：yudao-framework/yudao-spring-boot-starter-web 的 WebProperties.java:24 `adminApi = new Api("/admin-api", "**.controller.admin.**")`，即 controller.admin 包 → /admin-api，controller.app 包 → /app-api；Swagger 分组见 YudaoSwaggerAutoConfiguration.java:124。application-local.yaml 里的 context-path=/admin 是 Spring Boot Admin 的，不是业务接口前缀。
  - 横切依赖热度（图谱 fan-in）：yudao-common 10753、mybatis starter 5057、iot-biz 2739、test starter 2670、iot-gateway 2437、trade 2356 —— common/mybatis 是所有模块的地基。
  - 配置侧客观事实：端口 48080（application-local.yaml）；多租户 module 级 enable=true（application.yaml:326）；captcha 配置在 application.yaml:104；api-encrypt 默认关闭且 request/response-key 是文档示例值（application.yaml:290-296）；SpringDoc/Knife4j 默认开启；local/dev 配置明文数据库口令 root/123456（application-local.yaml:61,74；application-dev.yaml:52,57）；mybatis-plus.encryptor.password 硬编码（application.yaml:80）。
  - 测试资产：src/test 下 411 个 Java 测试文件，但**大部分属于未启用的模块**（hrm 51、system 39、ai 32、pms 30、infra 26、mes 26、fms 24、im 21、bpm 20、pay 15、wms 11、member 8…），当前构建口径下只跑 system/infra 的 65 个。
  - 启动类 YudaoServerApplication.java:18 scanBasePackages = server + module，所以启用模块只需在 pom 打开注释，无需改代码。
