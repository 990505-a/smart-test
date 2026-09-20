# 芋道管理系统 登录参数校验（P0）

## 0. 环境与源码

- 测试环境：http://yudao-admin
- 租户：芋道源码
- 账号：admin / Ruoyi@h3-2026xK
- 被测源码目录：/Users/yun/Documents/ruoyi-vue-pro
  （后端模块在 yudao-module-system/ 下，登录相关实现请自行检索确认）

## 1. 账号与密码校验规则

REQ-LOGIN-001 登录账号必须为 4-30 位。
（代码依据：AuthLoginReqVO.java L28 @Length(min=4, max=30)）

REQ-LOGIN-002 登录账号仅允许由数字和字母组成，不得包含下划线、中文、空格等其它字符。
（代码依据：AuthLoginReqVO.java L29 @Pattern(regexp="^[a-zA-Z0-9]{4,30}$")）

REQ-LOGIN-003 登录密码必须为 4-16 位。
（代码依据：AuthLoginReqVO.java L33 @Length(min=4, max=16)）

REQ-LOGIN-004 登录账号不得为空。
（代码依据：AuthLoginReqVO.java L27 @NotEmpty）

REQ-LOGIN-005 登录密码不得为空。
（代码依据：AuthLoginReqVO.java L32 @NotEmpty）

REQ-LOGIN-006 账号或密码不满足上述任一规则时，登录必须被拒绝，且不得签发访问令牌。
（代码依据：AuthLoginReqVO.java L27-33 Bean Validation 注解，校验失败抛 MethodArgumentNotValidException 返回 400，不进入登录流程；AdminAuthServiceImpl.java L88-98 authenticate() 认证失败抛 AUTH_LOGIN_BAD_CREDENTIALS，不执行 createTokenAfterLoginSuccess）

## 2. 校验失败的提示

REQ-LOGIN-007 账号长度不满足时，必须提示「账号长度为 4-30 位」。
（代码依据：AuthLoginReqVO.java L28 message="账号长度为 4-30 位"）

REQ-LOGIN-008 账号包含非法字符时，必须提示「账号格式为数字以及字母」。
（代码依据：AuthLoginReqVO.java L29 message="账号格式为数字以及字母"）

REQ-LOGIN-009 密码长度不满足时，必须提示「密码长度为 4-16 位」。
（代码依据：AuthLoginReqVO.java L33 message="密码长度为 4-16 位"）

REQ-LOGIN-010 账号为空时必须提示「登录账号不能为空」；密码为空时必须提示「密码不能为空」。
（代码依据：AuthLoginReqVO.java L27 与 L32 的 @NotEmpty 注解 message 与 REQ-LOGIN-010 提示文案一致）

## 3. 图形验证码

REQ-LOGIN-011 图形验证码由配置项 yudao.captcha.enable 控制，未显式配置时默认为开启。
（代码依据：AdminAuthServiceImpl.java L76 @Value("${yudao.captcha.enable:true}")）

REQ-LOGIN-012 当 yudao.captcha.enable 为 false 时，登录不得校验图形验证码。
（代码依据：AdminAuthServiceImpl.java L203-205 doValidateCaptcha 中 if (!captchaEnable) return ResponseModel.success()）

REQ-LOGIN-013 当 yudao.captcha.enable 为 true 时，登录必须校验图形验证码，验证码不正确时不得登录成功。
（代码依据：AdminAuthServiceImpl.java L188-196 validateCaptcha 校验失败抛 AUTH_LOGIN_CAPTCHA_CODE_ERROR）

本测试环境该配置为 false，因此 REQ-LOGIN-013 不在执行验证范围内。

## 4. 边界与异常

| 编号 | 场景 | 期望 |
|---|---|---|
| EDGE-001 | 账号 3 位 | 拒绝，提示账号长度为 4-30 位 |
| EDGE-002 | 账号 30 位 | 通过长度校验 |
| EDGE-003 | 账号 31 位 | 拒绝 |
| EDGE-004 | 账号含下划线（如 zz_test） | 拒绝，提示账号格式为数字以及字母 |
| EDGE-005 | 账号含中文 | 拒绝 |
| EDGE-006 | 密码 3 位 | 拒绝，提示密码长度为 4-16 位 |
| EDGE-007 | 密码 16 位 | 通过长度校验 |
| EDGE-008 | 密码 17 位 | 拒绝 |
| EDGE-009 | 账号为空或密码为空 | 拒绝，提示对应文案 |
| EDGE-010 | 账号密码格式合法但账号不存在 | 登录失败 |
| EDGE-011 | 账号密码格式合法但密码错误 | 登录失败 |

（EDGE-010/011 登录失败提示代码依据：ErrorCodeConstants.java L13 AUTH_LOGIN_BAD_CREDENTIALS = "登录失败，账号密码不正确"）

## 5. 范围外

- 注册、重置密码、短信登录、社交登录
- 登录成功后的菜单与权限
- 登录失败次数限制与账号锁定
