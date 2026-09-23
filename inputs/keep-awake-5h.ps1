<#
  让显示器在指定时间内不熄屏、系统不进睡眠（默认 5 小时，到期自动释放）。

  为什么需要它
  ------------
  本机「平衡」电源方案里 VIDEOIDLE=600s：显示器 10 分钟无操作即关闭。
  屏幕一灭，Play Mode 里的移动端 Unity 工程会走
  「D3D11 设备丢失 → 编辑器自杀」那条路（2026-09-22 平台侧同类事故，
  见 services/unity_service.py:458-476 的 _AWAKE 段）。

  平台自带的防休眠只在**用例脚本运行期间**生效（随 case.py 子进程结束
  自动失效），不覆盖「在对话里用工具驱动 Unity」与「两次运行之间的空档」。
  本脚本补的正是这段。

  机制
  ----
  SetThreadExecutionState(ES_CONTINUOUS | ES_DISPLAY_REQUIRED | ES_SYSTEM_REQUIRED)
  与 caffeine 同类做法：向系统声明「电源请求」，**不改动电源方案**，
  进程退出即自动失效。平台侧同一个 API 已在本机验证过有效。

  用法
  ----
    powershell -NoProfile -ExecutionPolicy Bypass -File inputs\keep-awake-5h.ps1
    powershell -NoProfile -ExecutionPolicy Bypass -File inputs\keep-awake-5h.ps1 -Minutes 600

  停止：Stop-Process -Id <PID>（PID 见启动输出与状态文件）
  状态：inputs\keep-awake.status.txt（含到期时间与心跳）
#>
param(
    [int]$Minutes = 300,
    [string]$StatusFile = "$PSScriptRoot\keep-awake.status.txt"
)

$signature = @'
using System;
using System.Runtime.InteropServices;
public static class PowerHold {
    [DllImport("kernel32.dll", SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
'@
Add-Type -TypeDefinition $signature -Language CSharp | Out-Null

$ES_CONTINUOUS       = [uint32]0x80000000
$ES_SYSTEM_REQUIRED  = [uint32]0x00000001
$ES_DISPLAY_REQUIRED = [uint32]0x00000002
$holdFlags           = $ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_DISPLAY_REQUIRED
$releaseFlags        = $ES_CONTINUOUS

$started  = Get-Date
$deadline = $started.AddMinutes($Minutes)
$final    = "unknown"

function Write-Status([string]$state) {
    try {
        @(
            "state    = $state"
            "pid      = $PID"
            "started  = $($started.ToString('yyyy-MM-dd HH:mm:ss'))"
            "until    = $($deadline.ToString('yyyy-MM-dd HH:mm:ss'))"
            "minutes  = $Minutes"
            "heartbeat= $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))"
        ) -join "`r`n" | Set-Content -Path $StatusFile -Encoding UTF8
    } catch {
        # 状态文件写不进去不影响常亮本身
    }
}

Write-Status "holding"
try {
    while ((Get-Date) -lt $deadline) {
        # 每 30 秒重申一次：ES_CONTINUOUS 下单次调用本可长期有效，重申是为了在
        # 异常重置（驱动/会话事件）后自动恢复，代价可忽略。
        [void][PowerHold]::SetThreadExecutionState($holdFlags)
        Write-Status "holding"
        Start-Sleep -Seconds 30
    }
    $final = "expired"
} catch {
    $final = "error: $($_.Exception.Message)"
} finally {
    [void][PowerHold]::SetThreadExecutionState($releaseFlags)
    Write-Status $final
}
