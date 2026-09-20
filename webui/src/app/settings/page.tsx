"use client";

import React, { useEffect, useState } from "react";
import { PageHeader } from "@/app/components/ui-patterns";
import { ReadinessCenter } from "@/app/components/ReadinessCenter";
import { apiClient } from "@/lib/api-client";
import {
  useFeishuStatus,
  useModelSettings,
  useModelPresets,
  usePlatformSettings,
  useLangfuseSettings,
  testLangfuseConnection,
  useMonitorLangfuseSettings,
  testMonitorLangfuseConnection,
  useJudgeSettings,
  testJudgeConnection,
  testModelConnection,
  applyModelPreset,
  saveModelPreset,
  deleteModelPreset,
  startFeishuLogin,
  completeFeishuLogin,
  type FeishuDeviceLogin,
} from "@/lib/api/useNewModules";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Loader2, CheckCircle2, XCircle } from "lucide-react";

type SettingField = {
  key: string;
  label: string;
  secret?: boolean;
  placeholder?: string;
  /** when set, renders a Select instead of a text input */
  select?: { value: string; label: string }[];
  /** when set, renders a full-width group heading above this field */
  heading?: string;
};

const MODEL_FIELDS: SettingField[] = [
  {
    key: "llm_model",
    label: "模型名称",
    heading: "对话主模型",
    placeholder: "deepseek-chat / glm-5.3-flash（留空用 DeepSeek 官方）",
  },
  {
    key: "llm_base_url",
    label: "API 地址",
    placeholder: "https://api.siliconflow.cn/v1（留空用 DeepSeek 官方端点）",
  },
  { key: "llm_api_key", label: "API Key", secret: true, placeholder: "留空使用 .env 中的 DeepSeek Key" },
];

const LANGFUSE_FIELDS: { key: string; label: string; secret?: boolean; placeholder?: string;
  select?: { value: string; label: string }[] }[] = [
  {
    key: "langfuse_enabled",
    label: "是否上报",
    select: [
      { value: "true", label: "上报（测评 trace 与分数写入 Langfuse）" },
      { value: "false", label: "关闭（结果只在本地）" },
    ],
  },
  { key: "langfuse_base_url", label: "Langfuse 地址", placeholder: "http://127.0.0.1:3000" },
  { key: "langfuse_public_key", label: "Public Key", placeholder: "pk-lf-…（决定 trace 落在哪个项目）" },
  { key: "langfuse_secret_key", label: "Secret Key", secret: true, placeholder: "sk-lf-…（留空表示不修改）" },
  { key: "langfuse_environment", label: "环境标识", placeholder: "eval" },
];

// Langfuse 监控（日常智能体使用链路）：与测评那组 key 分开，日常排查看监控组织、
// 跑测评只看测评组织。默认关闭——没配就不上报，避免误写进测评的 Langfuse。
const MONITOR_FIELDS: { key: string; label: string; secret?: boolean; placeholder?: string;
  select?: { value: string; label: string }[] }[] = [
  {
    key: "langfuse_monitor_enabled",
    label: "是否上报日常对话",
    select: [
      { value: "true", label: "上报（日常对话 trace 写入监控 Langfuse）" },
      { value: "false", label: "关闭（默认，不上报）" },
    ],
  },
  { key: "langfuse_monitor_base_url", label: "Langfuse 地址", placeholder: "http://127.0.0.1:3000" },
  { key: "langfuse_monitor_public_key", label: "Public Key", placeholder: "pk-lf-…（监控组织的项目）" },
  { key: "langfuse_monitor_secret_key", label: "Secret Key", secret: true, placeholder: "sk-lf-…（留空表示不修改）" },
  { key: "langfuse_monitor_environment", label: "环境标识", placeholder: "monitor" },
];

// LLM 裁判（测评打分）：三个都留空 = 继承主 LLM。这里的文案必须把"留空继承"
// 说清楚——之前没有任何入口，用户看到测评页卡片上写着 judge：glm-4.7，
// 却翻遍设置也找不到在哪配。
const JUDGE_FIELDS: { key: string; label: string; secret?: boolean; placeholder?: string }[] = [
  { key: "judge_model", label: "裁判模型", placeholder: "留空 = 继承主 LLM（推荐另配一个，避免与被测 agent 同源）" },
  { key: "judge_base_url", label: "API 地址", placeholder: "留空 = 继承主 LLM 的地址" },
  { key: "judge_api_key", label: "API Key", secret: true, placeholder: "留空 = 继承主 LLM 的 Key（留空表示不修改）" },
];

const PLATFORM_FIELDS: { key: string; label: string; secret?: boolean; placeholder?: string }[] = [  { key: "feishu_folder_token", label: "飞书目录（每次导出自动新建思维导图）", placeholder: "目录 URL 中 drive/folder/ 后面的 token" },
  { key: "feishu_mindnote_id", label: "飞书思维导图 ID（固定追加模式）", placeholder: "用例保存目标 mindnote id；配置目录后此项不生效" },
  { key: "feishu_mindnote_parent_node", label: "固定导图的父节点（可选）", placeholder: "追加模式下整棵树挂到哪个节点下；留空挂根节点" },
  { key: "feishu_template_mindnote_id", label: "思维导图样式模板 ID（可选）", placeholder: "一张调好连线风格、只留根节点的干净导图；填了走「复制模板」写出，留空回退 OPML 导入（连线为默认曲线）" },
  { key: "lark_cli_bin", label: "lark-cli 命令", placeholder: "lark-cli" },
  { key: "lark_cli_identity", label: "飞书身份 (user/bot)", placeholder: "user" },
  // LightRAG（知识库）的配置**不在这里**：模型 / Embedding / 知识库清单都挪到了
  // LightRAG 自带界面的「RAG 设置」页（每页右上角有入口，或见 /rag 页的地址）。
  // 那些值是启动 LightRAG 进程的环境变量，放在本体那一侧改完重启才说得通。
  { key: "unity_mcp_url", label: "Unity MCP 桥地址", placeholder: "http://127.0.0.1:5016/mcp" },
  { key: "unity_mcp_transport", label: "桥传输方式 (http/stdio)", placeholder: "http" },
  { key: "unity_mcp_command", label: "stdio 启动命令（留空用默认）", placeholder: "uvx --from mcpforunityserver==10.2.0 mcp-for-unity --transport stdio" },
  { key: "unity_mcp_server", label: "工具名方言 (auto/coplay/ivan/generic)", placeholder: "auto" },
  { key: "api_auto_max_repair", label: "接口脚本自修复次数上限" },
];

function SettingsForm({
  title,
  description,
  fields,
  values,
  onSave,
  saving,
  headerRender,
  extraActions,
}: {
  title: string;
  description: string;
  fields: SettingField[];
  values: Record<string, string | null>;
  onSave: (values: Record<string, string>) => Promise<void>;
  saving: boolean;
  /** renders extra UI (e.g. preset row) between description and the grid, with access to the form state */
  headerRender?: (
    form: Record<string, string>,
    setForm: React.Dispatch<React.SetStateAction<Record<string, string>>>,
  ) => React.ReactNode;
  /** renders extra buttons (e.g. connectivity test) next to 保存 */
  extraActions?: (form: Record<string, string>) => React.ReactNode;
}) {
  const [form, setForm] = useState<Record<string, string>>({});

  useEffect(() => {
    setForm(Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v ?? ""])));
  }, [values]);

  return (
    <Card className="p-5">
      <h3 className="text-base font-semibold">{title}</h3>
      <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
      {headerRender?.(form, setForm)}
      <Separator className="my-4" />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {fields.map(({ key, label, secret, placeholder, select, heading }) => (
          <React.Fragment key={key}>
            {heading && (
              <h4 className="mt-2 text-sm font-medium first:mt-0 md:col-span-2">{heading}</h4>
            )}
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={key}>{label}</Label>
              {select ? (
                <Select
                  value={form[key] ?? null}
                  onValueChange={(v) => setForm((f) => ({ ...f, [key]: v ?? "" }))}
                >
                  <SelectTrigger id={key} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {select.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id={key}
                  type={secret ? "password" : "text"}
                  value={form[key] ?? ""}
                  placeholder={placeholder}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                />
              )}
            </div>
          </React.Fragment>
        ))}
      </div>
      <div className="mt-4 flex justify-end gap-2">
        {extraActions?.(form)}
        <Button onClick={() => onSave(form)} disabled={saving} size="sm">
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          保存
        </Button>
      </div>
    </Card>
  );
}

/** 飞书登录引导：设备码流三步（发起 → 浏览器授权 → 回来完成） */
function FeishuLoginGuide() {
  const { data: status, mutate, isLoading } = useFeishuStatus();
  const [login, setLogin] = useState<FeishuDeviceLogin | null>(null);
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setBusy(true);
    try {
      const result = await startFeishuLogin();
      setLogin(result);
      window.open(result.verification_url, "_blank");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "发起登录失败");
    } finally {
      setBusy(false);
    }
  };

  const complete = async () => {
    if (!login) return;
    setBusy(true);
    try {
      const result = await completeFeishuLogin(login.device_code);
      if (result.logged_in) {
        toast.success("飞书登录成功");
        setLogin(null);
        mutate();
      } else {
        toast.error("尚未完成授权——请先在打开的页面中确认授权，再点一次");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "完成登录失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-medium">
            飞书集成
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            ) : status?.logged_in ? (
              <CheckCircle2 className="h-4 w-4 text-success" />
            ) : (
              <XCircle className="h-4 w-4 text-destructive" />
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {status?.available === false
              ? "lark-cli 未安装。请先安装 Node.js，然后运行：npm install -g @larksuite/cli，安装后点「重新检测」"
              : status?.logged_in
                ? `已登录${status.user ? `：${status.user}` : ""}。智能体可按 /skills/lark-* 技能执行飞书操作（读文档、导图、云空间等）`
                : "已检测到 lark-cli，但尚未登录。点击「登录飞书」，在打开的浏览器页面完成授权后回到本页确认"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {status?.available === false ? (
            <Button size="sm" variant="outline" disabled={busy} onClick={() => mutate()}>
              重新检测
            </Button>
          ) : status?.logged_in ? null : login ? (
            <>
              <Button size="sm" variant="outline" disabled={busy} onClick={() => mutate()}>
                重新检测
              </Button>
              <Button size="sm" disabled={busy} onClick={complete}>
                {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                我已完成授权
              </Button>
            </>
          ) : (
            <Button size="sm" disabled={busy} onClick={start}>
              {busy && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              登录飞书
            </Button>
          )}
        </div>
      </div>
      {login && (
        <div className="mt-3 rounded-md border bg-muted/40 px-3 py-2 text-xs break-all">
          授权链接（{Math.floor((login.expires_in ?? 600) / 60)} 分钟内有效）：
          <a
            href={login.verification_url}
            target="_blank"
            rel="noreferrer"
            className="ml-1 text-brand underline"
          >
            {login.verification_url}
          </a>
        </div>
      )}
    </Card>
  );
}

export default function SettingsPage() {
  const modelSettings = useModelSettings();
  const modelPresets = useModelPresets();
  const platformSettings = usePlatformSettings();
  const langfuseSettings = useLangfuseSettings();
  const monitorSettings = useMonitorLangfuseSettings();
  const judgeSettings = useJudgeSettings();

  const [savingModel, setSavingModel] = useState(false);
  const [savingPlatform, setSavingPlatform] = useState(false);
  const [savingLangfuse, setSavingLangfuse] = useState(false);
  const [testingLangfuse, setTestingLangfuse] = useState(false);
  const [savingMonitor, setSavingMonitor] = useState(false);
  const [testingMonitor, setTestingMonitor] = useState(false);
  const [savingJudge, setSavingJudge] = useState(false);
  const [testingJudge, setTestingJudge] = useState(false);
  const [testingModel, setTestingModel] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presetBusy, setPresetBusy] = useState(false);

  const saveModel = async (values: Record<string, string>) => {
    setSavingModel(true);
    try {
      await apiClient.put("/settings/model", { values });
      toast.success("模型设置已保存，下一轮对话起即时生效");
      modelSettings.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSavingModel(false);
    }
  };

  const saveLangfuse = async (values: Record<string, string>) => {
    setSavingLangfuse(true);
    try {
      await apiClient.put("/settings/langfuse", { values });
      toast.success("Langfuse 配置已保存：网页触发的测评立刻生效，CLI 重启后生效");
      langfuseSettings.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSavingLangfuse(false);
    }
  };

  const saveJudge = async (values: Record<string, string>) => {
    setSavingJudge(true);
    try {
      await apiClient.put("/settings/judge", { values });
      toast.success("裁判配置已保存：网页触发的测评下一批次立刻生效");
      judgeSettings.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSavingJudge(false);
    }
  };

  const runJudgeTest = async (form: Record<string, string>) => {
    setTestingJudge(true);
    try {
      const result = await testJudgeConnection(form);
      if (result.ok) {
        const from = result.source === "judge" ? "独立配置" : "继承主 LLM";
        toast.success(
          `裁判可用 · ${result.latency_ms}ms · ${result.model}（${from}）`
          + (result.verdict ? ` · 自检判定 ${result.verdict.score}` : ""),
        );
      } else {
        toast.error(`不通：${result.error ?? "未知错误"}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTestingJudge(false);
    }
  };

  const saveMonitor = async (values: Record<string, string>) => {
    setSavingMonitor(true);
    try {
      await apiClient.put("/settings/langfuse-monitor", { values });
      toast.success("监控配置已保存：日常对话从下一轮开始上报（无需重启）");
      monitorSettings.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSavingMonitor(false);
    }
  };

  const runMonitorTest = async (form: Record<string, string>) => {
    setTestingMonitor(true);
    try {
      const result = await testMonitorLangfuseConnection(form);
      if (result.ok) {
        toast.success(
          `连通正常（${result.latency_ms}ms）· 项目 ${result.project_name ?? "?"}`
          + (result.organization ? ` · 组织 ${result.organization}` : ""),
        );
      } else {
        toast.error(result.error ?? "连通失败");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTestingMonitor(false);
    }
  };

  const runLangfuseTest = async (form: Record<string, string>) => {    setTestingLangfuse(true);
    try {
      const result = await testLangfuseConnection(form);
      if (result.ok) {
        toast.success(
          `连通正常 · ${result.latency_ms}ms · 项目 ${result.project_name ?? "?"}`
          + `（${result.project_id ?? "?"}）`
          + (result.organization ? ` · 组织 ${result.organization}` : ""),
        );
      } else {
        toast.error(`不通：${result.error ?? "未知错误"}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTestingLangfuse(false);
    }
  };

  const runModelTest = async (form: Record<string, string>) => {
    setTestingModel(true);
    try {
      const result = await testModelConnection(form);
      const fmt = (r: { ok: boolean; latency_ms?: number; error?: string; model?: string }) =>
        r.ok
          ? `${r.model ?? ""} · ${r.latency_ms}ms`
          : `${r.model ?? ""} 失败：${r.error ?? "未知错误"}`;
      if (result.ok) {
        toast.success(`连通正常 — ${fmt(result)}`);
      } else {
        toast.error(fmt(result));
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "测试失败");
    } finally {
      setTestingModel(false);
    }
  };

  const applyPreset = async (
    setForm: React.Dispatch<React.SetStateAction<Record<string, string>>>,
  ) => {
    if (!selectedPreset) return;
    setPresetBusy(true);
    try {
      const data = await applyModelPreset(selectedPreset);
      setForm(Object.fromEntries(Object.entries(data.values).map(([k, v]) => [k, v ?? ""])));
      toast.success(`已应用预设「${data.applied}」并即时生效`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "应用失败");
    } finally {
      setPresetBusy(false);
    }
  };

  const savePreset = async (form: Record<string, string>) => {
    const name = window.prompt("预设名称：", form.llm_model || selectedPreset || "");
    if (!name?.trim()) return;
    setPresetBusy(true);
    try {
      await saveModelPreset(name.trim(), form);
      setSelectedPreset(name.trim());
      modelPresets.mutate();
      toast.success(`预设「${name.trim()}」已保存`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setPresetBusy(false);
    }
  };

  const removePreset = async () => {
    if (!selectedPreset || !window.confirm(`删除预设「${selectedPreset}」？`)) return;
    setPresetBusy(true);
    try {
      await deleteModelPreset(selectedPreset);
      setSelectedPreset("");
      modelPresets.mutate();
      toast.success("预设已删除");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "删除失败");
    } finally {
      setPresetBusy(false);
    }
  };

  const savePlatform = async (values: Record<string, string>) => {
    setSavingPlatform(true);
    try {
      await apiClient.put("/settings/platform", { values });
      toast.success("平台集成设置已保存");
      platformSettings.mutate();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSavingPlatform(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-6">
          <PageHeader
            title="设置"
            description="模型与平台集成配置（本地单机模式，无需登录）。各依赖的就绪状态见下方「就绪中心」"
          />

        {/* 就绪中心：外部依赖唯一的一份状态视图（描述来自后端 integrations 注册表） */}
        <ReadinessCenter />

        {/* 本地单机模式说明（原「账号」卡片：登录已移除，见 api/v2/auth.py） */}
        <Card className="p-5">
          <h3 className="text-base font-semibold">运行模式</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            本地单机模式：平台不要求登录，所有操作以本机身份执行。工作区、用例、记忆都在本机
            <code className="mx-1">workspace/</code>目录下，请自行做好备份与访问控制
            （对外暴露时建议在反向代理层加 Basic Auth）。
          </p>
        </Card>

        {/* 模型设置 */}
        {modelSettings.data && (
          <SettingsForm
            title="模型"
            description="支持任意 OpenAI 兼容端点（OpenAI / 硅基流动 / OneAPI / vLLM 等）：填了 API 地址即走该端点，留空使用 DeepSeek 官方。需要处理图片消息时，模型本身要支持读图。思考强度、以及「本次会话用哪个模型」都在聊天页按会话设置。密钥显示为 ******** 时保持不变即可"
            fields={MODEL_FIELDS}
            values={modelSettings.data}
            onSave={saveModel}
            saving={savingModel}
            headerRender={(form, setForm) => (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <Select value={selectedPreset || null} onValueChange={(v) => setSelectedPreset(v ?? "")}>
                  <SelectTrigger size="sm" className="w-56">
                    <SelectValue placeholder="模型预设" />
                  </SelectTrigger>
                  <SelectContent>
                    {(modelPresets.data ?? []).map((p) => (
                      <SelectItem key={p.name} value={p.name}>
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!selectedPreset || presetBusy}
                  onClick={() => applyPreset(setForm)}
                >
                  应用
                </Button>
                <Button size="sm" variant="outline" disabled={presetBusy} onClick={() => savePreset(form)}>
                  存当前为预设
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={!selectedPreset || presetBusy}
                  onClick={removePreset}
                >
                  删除
                </Button>
              </div>
            )}
            extraActions={(form) => (
              <Button variant="outline" size="sm" disabled={testingModel} onClick={() => runModelTest(form)}>
                {testingModel && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                测试连通
              </Button>
            )}
          />
        )}

        {/* 飞书登录引导（设备码流：本页发起 → 浏览器授权 → 回本页完成） */}
        <FeishuLoginGuide />

        {/* Langfuse（测评追踪）：trace 与分数写到哪里 */}
        {langfuseSettings.data && (
          <SettingsForm
            title="Langfuse（测评追踪）"
            description="测评的 trace 与分数上报到哪个 Langfuse 实例。key 对属于某个项目——trace 链接的路由前缀就是那个项目 id，所以换 key 等于换项目（对应 .env 的 LANGFUSE_*）。"
            fields={LANGFUSE_FIELDS}
            values={langfuseSettings.data}
            onSave={saveLangfuse}
            saving={savingLangfuse}
            extraActions={(form) => (
              <Button variant="outline" size="sm" disabled={testingLangfuse}
                      onClick={() => runLangfuseTest(form)}>
                {testingLangfuse && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                测试连通
              </Button>
            )}
          />
        )}

        {/* Langfuse（监控）：日常对话的 trace 落到另一个组织，与测评互不干扰 */}
        {monitorSettings.data && (
          <SettingsForm
            title="Langfuse（监控 · 日常对话）"
            description="日常使用平台智能体时（用例生成 / Unity / Web-UI / 代码分析）的 trace 上报到这里，
            与上面「测评追踪」是两套 key：日常排查看监控，跑测评时只看测评，两边的 trace 不混在一起。
            留空/关闭即不上报（对应 .env 的 LANGFUSE_MONITOR_*）。"
            fields={MONITOR_FIELDS}
            values={monitorSettings.data}
            onSave={saveMonitor}
            saving={savingMonitor}
            extraActions={(form) => (
              <Button variant="outline" size="sm" disabled={testingMonitor}
                      onClick={() => runMonitorTest(form)}>
                {testingMonitor && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                测试连通
              </Button>
            )}
          />
        )}

        {/* LLM 裁判（测评打分）：留空即继承主 LLM，卡片上直接写清实际用谁 */}
        {judgeSettings.data && (
          <SettingsForm
            title="LLM 裁判（测评打分）"
            description={
              `测评里 llm_judge / llm_judge_pass 两个分数由它给出。三项都留空表示「继承主 LLM」——`
              + `当前实际使用：${judgeSettings.data.effective.model}`
              + `（${judgeSettings.data.effective.source === "judge" ? "独立配置" : "继承主 LLM"}）`
              + `，地址 ${judgeSettings.data.effective.base_url.replace("host.docker.internal", "localhost")}。`
              + `建议另配一个模型：judge 与被测 agent 同源时，同一套偏好会同时影响行为和评判（对应 .env 的 JUDGE_*）。`
            }
            fields={JUDGE_FIELDS}
            values={judgeSettings.data.values}
            onSave={saveJudge}
            saving={savingJudge}
            extraActions={(form) => (
              <Button variant="outline" size="sm" disabled={testingJudge}
                      onClick={() => runJudgeTest(form)}>
                {testingJudge && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                测试连通
              </Button>
            )}
          />
        )}

        {/* 平台集成设置 */}
        {platformSettings.data && (
          <SettingsForm
            title="平台集成"
            description="飞书 / LightRAG / Unity 的连接信息，以及记忆总开关。代码图谱引擎由平台自管安装（版本与安装按钮在「代码图谱」页），这里不需要填路径。"
            fields={PLATFORM_FIELDS}
            values={platformSettings.data}
            onSave={savePlatform}
            saving={savingPlatform}
          />
        )}
        </div>
      </div>
    </div>
  );
}
