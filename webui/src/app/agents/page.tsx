"use client";

/**
 * 智能体装配页 —— 层级就是 **智能体 → 能力 → 工具 / 技能 / 权限**，全部可编辑。
 *
 * - 左栏是智能体（可新建/删除）；对话页可以在它们之间切换。
 * - 右栏是这个智能体装配了哪些能力（每项一个开关），以及「新增能力」。
 * - 能力点开是一个编辑器：说明、领域提示词、**工具**（从代码里已有的工具挑）、
 *   **技能**（从 skills/ 挑）、**依赖仓库**、哪些工具要**人工审批**。
 *   技能因此不再是独立的一个库，而是能力的一部分。
 *
 * 数据存在后端 `workspace/<space>/assembly.json`（`services/assembly_service.py`）；
 * 工具候选池来自代码清单（工具是 Python 函数，界面造不出来）。保存后**下一轮对话
 * 生效**，不用重启 —— 中间件按 `configurable.agent_id` 每轮现算工具面与提示词。
 */

import React, { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { PageHeader, EmptyState } from "@/app/components/ui-patterns";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { apiClient } from "@/lib/api-client";
import {
  AlertTriangle, BookOpen, RefreshCw, RotateCcw, ShieldAlert, Sparkles, Terminal, Trash2, Wrench,
} from "lucide-react";

/* ------------------------------------------------------------------ 类型 */

interface AgentDef {
  id: string;
  label: string;
  description: string;
  capabilities: string[];
}

interface CapabilityDef {
  key: string;
  label: string;
  description: string;
  domain_prompt: string;
  tools: string[];
  skills: string[];
  requires_repo: boolean;
  gated: string[];
  tool_names: string[];
  tool_count: number;
}

interface ToolEntry {
  symbol: string;
  module: string;
  export: string;
  names: string[];
  description: string;
  missing: boolean;
}

interface SkillEntry {
  dir: string;
  name: string;
  description: string;
  guides: string[];
}

interface CatalogView {
  agents: AgentDef[];
  capabilities: CapabilityDef[];
  tool_catalog: ToolEntry[];
  skill_catalog: SkillEntry[];
  default_agent_id: string;
  file: string;
  is_default: boolean;
  ignored?: string[];
  note?: string;
}

/* ------------------------------------------------------------------ 页面 */

export default function AgentsPage() {
  const { data, error, mutate } = useSWR<CatalogView>(
    "/agents", () => apiClient.get<CatalogView>("/agents").then((r) => r.data));

  const [agentId, setAgentId] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState("");
  const [note, setNote] = useState("");
  const [editAgent, setEditAgent] = useState<AgentDef | null>(null);
  const [editCap, setEditCap] = useState<CapabilityDef | null>(null);

  const agents = data?.agents ?? [];
  const capabilities = data?.capabilities ?? [];
  const agent = useMemo(
    () => agents.find((a) => a.id === agentId) ?? agents[0] ?? null,
    [agents, agentId],
  );

  useEffect(() => {
    if (!agentId && data?.agents?.length) {
      setAgentId(data.default_agent_id && data.agents.some((a) => a.id === data.default_agent_id)
        ? data.default_agent_id
        : data.agents[0].id);
    }
  }, [agentId, data]);

  if (error) {
    return (
      <div className="mx-auto w-full max-w-[1400px] px-6 py-6 lg:px-8">
        <PageHeader title="智能体装配" description="读取装配目录失败。" />
        <EmptyState title="拿不到装配目录" description="请确认后端在运行（:5012），然后刷新本页。" />
      </div>
    );
  }

  async function save(next: { agents: AgentDef[]; capabilities: CapabilityDef[] }) {
    setBusy(true);
    setFailed("");
    try {
      await apiClient.put("/agents/catalog", {
        agents: next.agents.map((a) => ({
          id: a.id, label: a.label, description: a.description, capabilities: a.capabilities,
        })),
        capabilities: next.capabilities.map((c) => ({
          key: c.key, label: c.label, description: c.description, domain_prompt: c.domain_prompt,
          tools: c.tools, skills: c.skills, requires_repo: c.requires_repo, gated: c.gated,
        })),
      });
      await mutate();
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  /** 重启 LangGraph：让代码清单里新增的工具进候选池（会中断正在跑的对话）。 */
  async function reloadService() {
    if (!confirm("重启 LangGraph 服务？\n\n用途：把代码里新增的工具加载进来。\n代价：正在跑的对话会被中断（它们是进程内 checkpoint）。")) return;
    setBusy(true);
    setFailed("");
    try {
      const res = await apiClient.post<{ restarted: boolean; error?: string; hint?: string; note?: string; tools_before?: number }>(
        "/agents/reload", {});
      const d = res.data;
      if (d.restarted) {
        setNote(`${d.note ?? "已重启"}（重启前候选池 ${d.tools_before ?? "?"} 个符号）`);
        // 新进程要几秒才起来，等一下再拉一次目录
        await new Promise((r) => setTimeout(r, 9000));
        await mutate();
      } else {
        setFailed(`${d.error ?? "重启失败"} ${d.hint ?? ""}`);
      }
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "重启失败");
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setBusy(true);
    setFailed("");
    try {
      await apiClient.delete("/agents/catalog");
      setAgentId("");
      await mutate();
    } catch (err) {
      setFailed(err instanceof Error ? err.message : "恢复默认失败");
    } finally {
      setBusy(false);
    }
  }

  const toggleCapability = (key: string, mounted: boolean) => {
    if (!agent) return;
    const caps = mounted
      ? [...agent.capabilities, key]
      : agent.capabilities.filter((k) => k !== key);
    save({ agents: agents.map((a) => (a.id === agent.id ? { ...a, capabilities: caps } : a)),
           capabilities });
  };

  const deleteCapability = (key: string) => {
    if (!confirm(`删除能力「${key}」？用到它的智能体会一起摘掉。`)) return;
    save({
      agents: agents.map((a) => ({ ...a, capabilities: a.capabilities.filter((k) => k !== key) })),
      capabilities: capabilities.filter((c) => c.key !== key),
    });
  };

  const deleteAgent = () => {
    if (!agent || agents.length <= 1) return;
    if (!confirm(`删除智能体「${agent.label}」？`)) return;
    save({ agents: agents.filter((a) => a.id !== agent.id), capabilities });
    setAgentId("");
  };

  return (
    <div className="flex-1 overflow-hidden">
      <div className="mx-auto flex h-full w-full max-w-[1600px] flex-col px-6 py-6 lg:px-8">
        <PageHeader
          title="智能体装配"
          description="智能体 → 能力 → 工具 / 技能 / 权限，全都可以自己改。保存后下一轮对话生效，不用重启。"
        />
        <div className="mt-4 flex min-h-0 flex-1 gap-4">
          {/* ============ 左栏：智能体 ============ */}
          <aside className="flex w-72 shrink-0 flex-col gap-3">
            <Card className="flex min-h-0 flex-1 flex-col p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold">智能体</span>
                <Button size="sm" variant="ghost" title="新建智能体"
                        onClick={() => setEditAgent({ id: "", label: "", description: "", capabilities: [] })}>
                  <Sparkles className="h-4 w-4" />
                </Button>
              </div>
              <Separator className="my-2" />
              <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pr-0.5">
                {agents.map((a) => (
                  <button key={a.id} type="button" onClick={() => setAgentId(a.id)}
                          className={`w-full rounded-lg border px-2.5 py-1.5 text-left transition
                            ${a.id === agent?.id
                              ? "border-primary/50 bg-muted/70"
                              : "border-transparent hover:bg-muted/40"}`}>
                    <div className="flex items-center gap-2">
                      <Sparkles className={`h-3.5 w-3.5 shrink-0 ${a.id === agent?.id ? "text-brand" : "text-muted-foreground"}`} />
                      <span className="min-w-0 flex-1 truncate text-sm">{a.label || a.id}</span>
                    </div>
                    <div className="truncate pl-5.5 text-[11px] text-muted-foreground">
                      {a.capabilities.length} 项能力
                      {a.id === data?.default_agent_id && " · 默认"}
                    </div>
                  </button>
                ))}
              </div>
              <Separator className="my-2" />
              <div className="flex items-center justify-between text-[11px] text-muted-foreground">
                <span title={data?.file}>装配目录</span>
                <Button size="sm" variant="ghost" disabled={busy || data?.is_default}
                        onClick={reset} title="删掉目录文件，回到代码清单播种出来的那套">
                  <RotateCcw className="mr-1 h-3 w-3" />恢复默认
                </Button>
              </div>
              {/* 工具是代码里的 @tool 函数，在 graph 编译期注册 —— 往代码清单里加了
                  新工具必须重启服务才挂得上（技能上传后不用，每轮现扫目录）。 */}
              <Button size="sm" variant="ghost" className="w-full text-[11px] text-muted-foreground"
                      disabled={busy} onClick={reloadService}
                      title="往代码清单里加了新工具之后点它：重启 LangGraph 服务，工具才会进候选池">
                <RefreshCw className="mr-1 h-3 w-3" />重新加载工具池（重启服务）
              </Button>
            </Card>
          </aside>

          {/* ============ 右栏：这个智能体的能力 ============ */}
          <main className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
              {agent && (
                <>
                  <Card className="p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <Sparkles className="h-4 w-4 text-brand" />
                      <span className="text-sm font-semibold">{agent.label || agent.id}</span>
                      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">{agent.id}</code>
                      <Badge variant="secondary" className="text-[11px]">
                        装配 {agent.capabilities.length}/{capabilities.length} 项能力
                      </Badge>
                      <div className="ml-auto flex items-center gap-2">
                        {failed && <span className="max-w-[420px] text-[11px] text-destructive">{failed}</span>}
                        {note && !failed && <span className="max-w-[420px] text-[11px] text-muted-foreground">{note}</span>}
                        <Button size="sm" variant="outline" onClick={() => setEditAgent(agent)}>
                          编辑
                        </Button>
                        <Button size="sm" variant="outline" disabled={busy || agents.length <= 1}
                                onClick={deleteAgent}>
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                    {agent.description && (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">{agent.description}</p>
                    )}
                    <p className="mt-2 text-xs leading-5 text-muted-foreground">
                      在对话页输入框旁选这个智能体。它的自我介绍与能力清单进提示词，
                      工具面按下面勾选的能力收敛。
                    </p>
                  </Card>

                  {capabilities.map((cap) => {
                    const mounted = agent.capabilities.includes(cap.key);
                    return (
                      <Card key={cap.key} className={`p-4 ${mounted ? "" : "opacity-70"}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <Wrench className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span className="text-sm font-semibold">{cap.label || cap.key}</span>
                          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">{cap.key}</code>
                          <Badge variant="secondary" className="text-[11px]">{cap.tool_count} 工具</Badge>
                          {cap.requires_repo && (
                            <Badge variant="outline" className="text-[11px]">
                              <Terminal className="mr-1 h-3 w-3" />需挂代码图谱仓库
                            </Badge>
                          )}
                          {cap.gated.length > 0 && (
                            <Badge variant="outline" className="text-[11px] text-amber-600">
                              <ShieldAlert className="mr-1 h-3 w-3" />{cap.gated.length} 个需审批
                            </Badge>
                          )}
                          <div className="ml-auto flex items-center gap-2">
                            <Button size="sm" variant="outline" onClick={() => setEditCap(cap)}>
                              编辑
                            </Button>
                            <Button size="sm" variant="outline" disabled={busy}
                                    onClick={() => deleteCapability(cap.key)}>
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                            <label className="flex items-center gap-2 pl-2 text-xs">
                              <span className={mounted ? "text-foreground" : "text-muted-foreground"}>装配</span>
                              <Switch checked={mounted} disabled={busy}
                                      onCheckedChange={(v: boolean) => toggleCapability(cap.key, v)} />
                            </label>
                          </div>
                        </div>
                        {cap.description && (
                          <p className="mt-2 text-xs leading-5 text-muted-foreground">{cap.description}</p>
                        )}
                        <div className="mt-2 flex flex-wrap items-center gap-1.5">
                          {cap.tool_names.length === 0 && (
                            <span className="text-[11px] text-amber-600">还没挑工具：这个能力现在是空的</span>
                          )}
                          {cap.tool_names.map((n) => (
                            <code key={n} className={`rounded px-1.5 py-0.5 font-mono text-[11px] ${
                              cap.gated.includes(n) ? "bg-amber-500/10 text-amber-700" : "bg-muted text-foreground/80"
                            }`} title={cap.gated.includes(n) ? "需要人工审批" : undefined}>
                              {n}
                            </code>
                          ))}
                        </div>
                        {cap.skills.length > 0 && (
                          <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
                            <BookOpen className="h-3 w-3" />技能：
                            {cap.skills.map((s) => (
                              <code key={s} className="font-mono">{s}</code>
                            ))}
                          </div>
                        )}
                      </Card>
                    );
                  })}

                  <Button variant="outline" className="w-full"
                          onClick={() => setEditCap({
                            key: "", label: "", description: "", domain_prompt: "",
                            tools: [], skills: [], requires_repo: false, gated: [],
                            tool_names: [], tool_count: 0,
                          })}>
                    + 新增能力
                  </Button>
                </>
              )}
            </div>
          </main>
        </div>
      </div>

      {editAgent && data && (
        <AgentDialog agent={editAgent} capabilities={capabilities} agents={agents}
                     onClose={() => setEditAgent(null)}
                     onSave={(next) => {
                       const exists = agents.some((a) => a.id === next.id);
                       save({
                         agents: exists
                           ? agents.map((a) => (a.id === next.id ? next : a))
                           : [...agents, next],
                         capabilities,
                       });
                       setAgentId(next.id);
                       setEditAgent(null);
                     }} />
      )}
      {editCap && data && (
        <CapabilityDialog cap={editCap} tools={data.tool_catalog} skills={data.skill_catalog}
                          existingKeys={capabilities.map((c) => c.key)}
                          onClose={() => setEditCap(null)}
                          onSave={(next) => {
                            const exists = capabilities.some((c) => c.key === next.key);
                            save({
                              agents,
                              capabilities: exists
                                ? capabilities.map((c) => (c.key === next.key ? next : c))
                                : [...capabilities, next],
                            });
                            setEditCap(null);
                          }} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------ 智能体对话框 */

function AgentDialog({ agent, capabilities, agents, onClose, onSave }: {
  agent: AgentDef;
  capabilities: CapabilityDef[];
  agents: AgentDef[];
  onClose: () => void;
  onSave: (agent: AgentDef) => void;
}) {
  const isNew = !agent.id;
  const [id, setId] = useState(agent.id);
  const [label, setLabel] = useState(agent.label);
  const [description, setDescription] = useState(agent.description);
  const [caps, setCaps] = useState<string[]>(agent.capabilities);

  const idTaken = isNew && (agents.some((a) => a.id === id.trim()) || !id.trim());

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{isNew ? "新建智能体" : `编辑「${agent.label || agent.id}」`}</DialogTitle></DialogHeader>
        <div className="space-y-3 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">标识（英文/数字，对话页参数用它）</Label>
              <Input value={id} disabled={!isNew} placeholder="api-explorer"
                     onChange={(e) => setId(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label className="text-xs">名字（给模型自我介绍用）</Label>
              <Input value={label} placeholder="接口探索助手"
                     onChange={(e) => setLabel(e.target.value)} className="mt-1" />
            </div>
          </div>
          <div>
            <Label className="text-xs">说明（进提示词，写清它是干什么的）</Label>
            <Textarea value={description} rows={2} className="mt-1"
                      placeholder="专做接口探索与回归：扫接口、生成用例、跑批量。"
                      onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <Label className="text-xs">装配哪些能力</Label>
            <div className="mt-1 space-y-1">
              {capabilities.map((c) => (
                <label key={c.key} className="flex items-center gap-2 rounded border px-2 py-1.5">
                  <input type="checkbox" checked={caps.includes(c.key)}
                         onChange={(e) => setCaps(e.target.checked
                           ? [...caps, c.key] : caps.filter((k) => k !== c.key))} />
                  <span className="text-sm">{c.label || c.key}</span>
                  <span className="ml-auto text-[11px] text-muted-foreground">{c.tool_count} 工具</span>
                </label>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button disabled={idTaken}
                  onClick={() => onSave({
                    id: id.trim(), label: label.trim() || id.trim(),
                    description: description.trim(), capabilities: caps,
                  })}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------ 能力对话框 */

function CapabilityDialog({ cap, tools, skills, existingKeys, onClose, onSave }: {
  cap: CapabilityDef;
  tools: ToolEntry[];
  skills: SkillEntry[];
  existingKeys: string[];
  onClose: () => void;
  onSave: (cap: CapabilityDef) => void;
}) {
  const isNew = !cap.key;
  const [key, setKey] = useState(cap.key);
  const [label, setLabel] = useState(cap.label);
  const [description, setDescription] = useState(cap.description);
  const [domainPrompt, setDomainPrompt] = useState(cap.domain_prompt);
  const [picked, setPicked] = useState<string[]>(cap.tools);
  const [pickedSkills, setPickedSkills] = useState<string[]>(cap.skills);
  const [requiresRepo, setRequiresRepo] = useState(cap.requires_repo);
  const [gated, setGated] = useState<string[]>(cap.gated);

  // 按来源模块分组展示工具（一个能力往往只来自两三个文件）
  const groups = useMemo(() => {
    const byModule = new Map<string, ToolEntry[]>();
    for (const t of tools) byModule.set(t.module, [...(byModule.get(t.module) ?? []), t]);
    return [...byModule];
  }, [tools]);

  const namesOf = (symbols: string[]) =>
    tools.filter((t) => symbols.includes(t.symbol)).flatMap((t) => t.names);

  const pickedNames = namesOf(picked);
  const keyTaken = isNew && (!key.trim() || existingKeys.includes(key.trim()));

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isNew ? "新增能力" : `编辑「${cap.label || cap.key}」`}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4 text-sm">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs">标识</Label>
              <Input value={key} disabled={!isNew} placeholder="api-explore"
                     onChange={(e) => setKey(e.target.value)} className="mt-1" />
            </div>
            <div>
              <Label className="text-xs">名字（进分诊表）</Label>
              <Input value={label} placeholder="接口探索执行"
                     onChange={(e) => setLabel(e.target.value)} className="mt-1" />
            </div>
          </div>
          <div>
            <Label className="text-xs">一句话说明（分诊依据：什么时候该走这个能力）</Label>
            <Input value={description} className="mt-1"
                   placeholder="扫接口文档、生成 pytest 用例、批量执行与自修复。"
                   onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div>
            <Label className="text-xs">领域提示词（进系统提示的「能力」段）</Label>
            <Textarea value={domainPrompt} rows={4} className="mt-1"
                      placeholder={"### 接口探索\n\n先读 OpenAPI 文档 → 生成 pytest → 执行 → 失败自修复。"}
                      onChange={(e) => setDomainPrompt(e.target.value)} />
          </div>

          <div>
            <div className="flex items-center justify-between">
              <Label className="text-xs">工具（只能从代码里已有的挑，共 {tools.length} 个符号）</Label>
              <span className="text-[11px] text-muted-foreground">已选 {pickedNames.length} 个</span>
            </div>
            <div className="mt-1 max-h-72 space-y-3 overflow-y-auto rounded border p-2">
              {groups.map(([mod, list]) => (
                <div key={mod}>
                  <div className="text-[11px] text-muted-foreground">
                    <code className="font-mono">
                      {mod.replace(/^src\.app\.agents\./, "agents/").replace(/\./g, "/")}.py
                    </code>
                  </div>
                  <div className="mt-1 space-y-0.5">
                    {list.map((t) => (
                      <label key={t.symbol} className="flex items-start gap-2 rounded px-1 py-0.5 hover:bg-muted/40">
                        <input type="checkbox" className="mt-0.5" checked={picked.includes(t.symbol)}
                               onChange={(e) => setPicked(e.target.checked
                                 ? [...picked, t.symbol] : picked.filter((s) => s !== t.symbol))} />
                        <span className="min-w-0 flex-1">
                          <code className="font-mono text-xs">{t.names.join(", ") || t.export}</code>
                          {t.missing && <span className="ml-2 text-[11px] text-destructive">解析失败</span>}
                          {t.description && (
                            <span className="block text-[11px] text-muted-foreground">{t.description}</span>
                          )}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs">技能（模型会看到这几个 SKILL.md 的清单）</Label>
            <div className="mt-1 grid grid-cols-2 gap-1">
              {skills.map((s) => (
                <label key={s.dir} className="flex items-start gap-2 rounded border px-2 py-1.5">
                  <input type="checkbox" className="mt-0.5" checked={pickedSkills.includes(s.dir)}
                         onChange={(e) => setPickedSkills(e.target.checked
                           ? [...pickedSkills, s.dir] : pickedSkills.filter((d) => d !== s.dir))} />
                  <span className="min-w-0 flex-1">
                    <code className="font-mono text-xs">{s.name}</code>
                    <span className="block truncate text-[11px] text-muted-foreground" title={s.description}>
                      {s.description}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 rounded border px-3 py-2">
            <Switch checked={requiresRepo} onCheckedChange={(v: boolean) => setRequiresRepo(v)} />
            <span className="text-xs">
              依赖仓库：只有本次会话挂了仓库，这个能力的工具才出现在工具面上
            </span>
          </div>

          <div>
            <Label className="text-xs">
              需要人工审批的工具（勾上的：模型每次调用都弹审批卡片等你确认）
            </Label>
            <div className="mt-1 flex flex-wrap gap-2 rounded border p-2">
              {pickedNames.length === 0 && (
                <span className="text-[11px] text-muted-foreground">先在上面的工具里挑几个</span>
              )}
              {pickedNames.map((n) => (
                <label key={n} className="flex items-center gap-1.5 rounded bg-muted px-2 py-0.5">
                  <input type="checkbox" checked={gated.includes(n)}
                         onChange={(e) => setGated(e.target.checked
                           ? [...gated, n] : gated.filter((g) => g !== n))} />
                  <code className="font-mono text-[11px]">{n}</code>
                </label>
              ))}
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button disabled={keyTaken}
                  onClick={() => onSave({
                    key: key.trim(),
                    label: label.trim() || key.trim(),
                    description: description.trim(),
                    domain_prompt: domainPrompt,
                    tools: picked,
                    skills: pickedSkills,
                    requires_repo: requiresRepo,
                    gated: gated.filter((g) => pickedNames.includes(g)),
                    tool_names: pickedNames,
                    tool_count: pickedNames.length,
                  })}>
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
