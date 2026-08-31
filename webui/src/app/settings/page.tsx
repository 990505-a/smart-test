"use client";

import React, { useEffect, useState } from "react";
import { PageHeader } from "@/app/components/ui-patterns";
import { useAuth } from "@/providers/AuthProvider";
import { apiClient } from "@/lib/api-client";
import {
  useModelSettings,
  useModelPresets,
  usePlatformSettings,
  useFeishuStatus,
  useUnityStatus,
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
    heading: "文本模型（对话主模型）",
    placeholder: "deepseek-chat / glm-5.3-flash（留空用 DeepSeek 官方）",
  },
  {
    key: "llm_base_url",
    label: "API 地址",
    placeholder: "https://api.siliconflow.cn/v1（留空用 DeepSeek 官方端点）",
  },
  { key: "llm_api_key", label: "API Key", secret: true, placeholder: "留空使用 .env 中的 DeepSeek Key" },
  {
    key: "vision_model",
    label: "模型名称",
    heading: "视觉模型（选填，处理图片消息）",
    placeholder: "gpt-4o / glm-4.5v（留空则复用文本模型）",
  },
  { key: "vision_base_url", label: "API 地址", placeholder: "留空使用文本模型的 API 地址" },
  { key: "vision_api_key", label: "API Key", secret: true, placeholder: "留空使用文本模型的 Key" },
];

const PLATFORM_FIELDS: { key: string; label: string; secret?: boolean; placeholder?: string }[] = [
  { key: "feishu_folder_token", label: "飞书目录（每次导出自动新建思维导图）", placeholder: "目录 URL 中 drive/folder/ 后面的 token" },
  { key: "feishu_mindnote_id", label: "飞书思维导图 ID（固定追加模式）", placeholder: "用例保存目标 mindnote id；配置目录后此项不生效" },
  { key: "lark_cli_bin", label: "lark-cli 命令", placeholder: "lark-cli" },
  { key: "lark_cli_identity", label: "飞书身份 (user/bot)", placeholder: "user" },
  { key: "lightrag_base_url", label: "LightRAG 服务地址", placeholder: "http://127.0.0.1:5014" },
  { key: "lightrag_embedding_base_url", label: "Embedding API 地址", placeholder: "https://api.siliconflow.cn/v1" },
  { key: "lightrag_embedding_model", label: "Embedding 模型", placeholder: "BAAI/bge-m3" },
  { key: "lightrag_embedding_api_key", label: "Embedding API Key", secret: true },
  { key: "codebase_memory_exe", label: "代码图谱 exe 路径（GS 定制版）", placeholder: "C:/codebase/cbm-gs.exe" },
  { key: "game_repo_path", label: "游戏仓库路径", placeholder: "E:/m72-publish/m72" },
  { key: "game_client_repo", label: "游戏客户端路径", placeholder: "E:/m72-publish/m72/client" },
  { key: "unity_host", label: "Unity 主机", placeholder: "127.0.0.1" },
  { key: "unity_port", label: "Unity LuaRemoteServer 端口", placeholder: "16666" },
  { key: "everos_enabled", label: "记忆模块开关 (true/false)" },
  { key: "everos_port", label: "EverOS 记忆服务端口", placeholder: "9631" },
  { key: "everos_embedding_api_key", label: "记忆 Embedding Key（解锁向量检索/反思/技能蒸馏）", secret: true, placeholder: "留空=关键词模式；任意 OpenAI 兼容 key" },
  { key: "everos_embedding_base_url", label: "记忆 Embedding API 地址", placeholder: "留空复用 LightRAG 的地址；OpenAI 官方填 https://api.openai.com/v1" },
  { key: "everos_embedding_model", label: "记忆 Embedding 模型", placeholder: "留空复用 LightRAG 的模型；OpenAI 官方填 text-embedding-3-small" },
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
  const { user, refresh } = useAuth();
  const modelSettings = useModelSettings();
  const modelPresets = useModelPresets();
  const platformSettings = usePlatformSettings();
  const feishuStatus = useFeishuStatus();
  const unityStatus = useUnityStatus();

  const [savingModel, setSavingModel] = useState(false);
  const [savingPlatform, setSavingPlatform] = useState(false);
  const [testingModel, setTestingModel] = useState(false);
  const [selectedPreset, setSelectedPreset] = useState("");
  const [presetBusy, setPresetBusy] = useState(false);
  const [newUsername, setNewUsername] = useState("");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);

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

  const runModelTest = async (form: Record<string, string>) => {
    setTestingModel(true);
    try {
      const result = await testModelConnection(form);
      const fmt = (r: { ok: boolean; latency_ms?: number; error?: string; model?: string; skipped?: boolean }) =>
        r.ok
          ? `${r.model ?? ""}${r.skipped ? "" : ` · ${r.latency_ms}ms`}`
          : `${r.model ?? ""} 失败：${r.error ?? "未知错误"}`;
      if (result.text.ok && result.vision.ok) {
        toast.success(`连通正常 — 文本 ${fmt(result.text)}；视觉 ${fmt(result.vision)}`);
      } else {
        toast.error(`文本模型 ${fmt(result.text)}；视觉模型 ${fmt(result.vision)}`);
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

  const changeUsername = async () => {
    if (!newUsername.trim()) return;
    setProfileSaving(true);
    try {
      await apiClient.post("/auth/change-username", { new_username: newUsername.trim() });
      toast.success("用户名已修改");
      setNewUsername("");
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "修改失败");
    } finally {
      setProfileSaving(false);
    }
  };

  const changePassword = async () => {
    if (!oldPassword || !newPassword) {
      toast.error("请输入原密码和新密码");
      return;
    }
    setProfileSaving(true);
    try {
      await apiClient.post("/auth/change-password", { old_password: oldPassword, new_password: newPassword });
      toast.success("密码已修改");
      setOldPassword("");
      setNewPassword("");
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "修改失败");
    } finally {
      setProfileSaving(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-8 lg:px-8">
        <div className="flex flex-col gap-6">
          <PageHeader
            title="设置"
            description={
              <span className="flex flex-wrap items-center gap-x-3">
                <span>账号、模型与平台集成配置。集成状态：</span>
                <span className="flex items-center gap-1">
                  飞书
                  {feishuStatus.data?.logged_in ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-destructive" />
                  )}
                </span>
                <span className="flex items-center gap-1">
                  Unity
                  {unityStatus.data?.available ? (
                    <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5 text-destructive" />
                  )}
                </span>
              </span>
            }
          />

        {/* 账号设置 */}
        <Card className="p-5">
          <h3 className="text-base font-semibold">账号</h3>
          <p className="mt-0.5 text-xs text-muted-foreground">
            当前用户：{user?.username}（{user?.role}）
            {user?.must_change_password && " · 请尽快修改默认密码"}
          </p>
          <Separator className="my-4" />
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div className="flex flex-col gap-3">
              <Label>修改用户名</Label>
              <Input
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                placeholder={user?.username}
              />
              <div>
                <Button size="sm" variant="outline" onClick={changeUsername} disabled={profileSaving || !newUsername.trim()}>
                  修改用户名
                </Button>
              </div>
            </div>
            <div className="flex flex-col gap-3">
              <Label>修改密码</Label>
              <Input
                type="password"
                value={oldPassword}
                onChange={(e) => setOldPassword(e.target.value)}
                placeholder="原密码"
              />
              <Input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="新密码（至少6位）"
              />
              <div>
                <Button size="sm" variant="outline" onClick={changePassword} disabled={profileSaving}>
                  修改密码
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* 模型设置 */}
        {modelSettings.data && (
          <SettingsForm
            title="模型"
            description="文本模型支持任意 OpenAI 兼容端点（OpenAI / 硅基流动 / OneAPI / vLLM 等）：填了 API 地址即走该端点，留空使用 DeepSeek 官方。视觉模型留空则由文本模型处理图片（需文本模型本身支持视觉）。思考强度在聊天页按会话设置。密钥显示为 ******** 时保持不变即可"
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

        {/* 平台集成设置 */}
        {platformSettings.data && (
          <SettingsForm
            title="平台集成"
            description="飞书 / LightRAG / codebase-memory / 游戏仓库 / Unity / 自进化调度"
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
