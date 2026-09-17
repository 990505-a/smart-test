"use client";

/**
 * 用例编辑器：新建 / 修改 spec、设备与浏览器矩阵、AI 生成、修复历史 diff。
 *
 * 之前这个页面只能「新建」——保存过的用例写错了没有任何入口能改，而智能体的
 * 自修复又会在后台静默改写 content。所以这里除了编辑器，还额外交代两件事：
 * 这份用例跑在什么设备/浏览器上、AI 到底改了哪几行。
 */

import React, { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { javascript } from "@codemirror/lang-javascript";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Save, Play, Sparkles, History } from "lucide-react";
import {
  createWebUiScript, updateWebUiScript, runWebUiScript, generateWebUiSpec,
  useWebUiScriptDetail, type WebUiRepairEntry, type WebUiScript,
} from "@/lib/api/useNewModules";
import { diffLines, diffSummary } from "@/lib/text-diff";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

// CodeMirror 依赖 DOM，Next 的 SSR 阶段不能渲染它
const CodeMirror = dynamic(() => import("@uiw/react-codemirror"), { ssr: false });

const DEVICE_PRESETS = ["iPhone 13", "iPhone SE", "Pixel 5", "Galaxy S9+", "iPad Mini"];
const BROWSERS = ["chromium", "webkit"] as const;

const EXAMPLE_SPEC = `import { test, expect } from '@playwright/test'

test.describe('豆瓣电影 · 首页', () => {
  test('首页应展示影片列表', async ({ page }) => {
    test.setTimeout(60000)
    await page.goto('/movie/')

    const cards = page.locator('a[href*="/movie/subject/"]')
    await expect(cards.first()).toBeVisible({ timeout: 20000 })
    expect(await cards.count()).toBeGreaterThan(2)

    await page.screenshot({ path: 'artifacts/首页-影片列表.png', fullPage: true })
  })
})
`;

interface EditorState {
  name: string;
  module: string;
  description: string;
  target_url: string;
  spec_file: string;
  device: string;
  desktop: boolean;
  browsers: string[];
  video: string;   // "" = 默认(仅失败保留) | "on" = 始终 | "off" = 不录
  status: string;
  content: string;
}

function stateFrom(script: WebUiScript | null): EditorState {
  const options = (script as { options?: Record<string, unknown> } | null)?.options ?? {};
  const device = typeof options.device === "string" ? options.device : "iPhone 13";
  const browsers = Array.isArray(options.browsers) ? options.browsers.map(String) : [];
  const video = typeof options.video === "string" ? options.video : "";
  return {
    name: script?.name ?? "",
    module: script?.module ?? "",
    description: script?.description ?? "",
    target_url: script?.target_url ?? "https://m.douban.com/movie/",
    spec_file: script?.spec_file ?? "tests/spec.spec.ts",
    device,
    // options 里没有 device 键 = 之前存的就是桌面
    desktop: !("device" in options),
    browsers,
    video,
    status: script?.status ?? "draft",
    content: script?.content ?? EXAMPLE_SPEC,
  };
}

function RepairHistoryPanel({ entries }: { entries: WebUiRepairEntry[] }) {
  const [diffIndex, setDiffIndex] = useState<number | null>(null);
  if (entries.length === 0) {
    return <p className="text-xs text-muted-foreground">没有自修复记录（失败后未触发 AI 修复）。</p>;
  }
  const entry = diffIndex === null ? null : entries[diffIndex];
  return (
    <div className="flex flex-col gap-2">
      {entries.map((item, index) => {
        const summary = item.before && item.after ? diffSummary(item.before, item.after) : null;
        return (
          <div key={`${item.version}-${index}`} className="rounded-md border p-2">
            <div className="flex items-center gap-2 text-xs">
              <Badge variant="secondary" className="font-normal">v{item.version}</Badge>
              <span className="text-muted-foreground">{item.at}</span>
              {summary && (
                <span className="text-muted-foreground">
                  <span className="text-emerald-600">+{summary.added}</span>{" "}
                  <span className="text-red-600">-{summary.removed}</span>
                </span>
              )}
              {item.before && item.after && (
                <button type="button" className="ml-auto text-primary hover:underline"
                        onClick={() => setDiffIndex(index)}>
                  看改了哪几行
                </button>
              )}
            </div>
            <pre className="mt-1 max-h-24 overflow-auto whitespace-pre-wrap rounded bg-muted p-2 text-[11px] text-muted-foreground">
              {item.error}
            </pre>
          </div>
        );
      })}

      <Dialog open={diffIndex !== null} onOpenChange={(open) => !open && setDiffIndex(null)}>
        <DialogContent className="sm:max-w-4xl">
          <DialogHeader>
            <DialogTitle>
              AI 自修复改动（v{entry?.version}）
            </DialogTitle>
          </DialogHeader>
          {entry?.before && entry?.after && (
            <pre className="max-h-[70vh] overflow-auto rounded bg-muted p-3 text-[11px] leading-5">
              {diffLines(entry.before, entry.after).map((op, index) => (
                <div
                  key={index}
                  className={cn(
                    "px-1",
                    op.type === "add" && "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
                    op.type === "del" && "bg-red-500/15 text-red-800 line-through dark:text-red-300",
                  )}
                >
                  <span className="mr-2 inline-block w-8 select-none text-right text-muted-foreground/60">
                    {op.leftNo ?? ""}
                  </span>
                  <span className="mr-2 inline-block w-8 select-none text-right text-muted-foreground/60">
                    {op.rightNo ?? ""}
                  </span>
                  {op.type === "add" ? "+" : op.type === "del" ? "-" : " "} {op.text}
                </div>
              ))}
            </pre>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function ScriptEditorDialog({
  open, onOpenChange, scriptId, onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 传 id = 编辑已有用例；不传 = 新建 */
  scriptId?: string | null;
  onSaved: () => void;
}) {
  const detail = useWebUiScriptDetail(open && scriptId ? scriptId : null);
  const [state, setState] = useState<EditorState>(() => stateFrom(null));
  const [saving, setSaving] = useState<"save" | "run" | null>(null);
  const [genOpen, setGenOpen] = useState(false);
  const [intent, setIntent] = useState("");
  const [generating, setGenerating] = useState(false);
  const [tab, setTab] = useState<"edit" | "repair">("edit");

  // 打开时用详情接口回填（列表接口不返回 content，避免列表响应过大）
  useEffect(() => {
    if (!open) return;
    if (!scriptId) {
      setState(stateFrom(null));
      setTab("edit");
      return;
    }
    if (detail.data) setState(stateFrom(detail.data));
  }, [open, scriptId, detail.data]);

  const repairs = useMemo(
    () => ((detail.data as { repair_history?: WebUiRepairEntry[] } | undefined)?.repair_history ?? []),
    [detail.data],
  );

  const patch = (partial: Partial<EditorState>) => setState((s) => ({ ...s, ...partial }));

  const payload = () => {
    const options: Record<string, unknown> = {};
    if (!state.desktop && state.device.trim()) options.device = state.device.trim();
    if (state.browsers.length > 0) options.browsers = state.browsers;
    if (state.video) options.video = state.video;
    return {
      name: state.name.trim(),
      module: state.module.trim() || null,
      description: state.description.trim() || null,
      target_url: state.target_url.trim() || null,
      spec_file: state.spec_file.trim() || "tests/spec.spec.ts",
      content: state.content,
      status: state.status,
      options,
    };
  };

  const save = async (alsoRun: boolean) => {
    if (!state.name.trim()) { toast.error("请填写用例名"); return; }
    if (!state.content.trim()) { toast.error("spec 内容不能为空"); return; }
    setSaving(alsoRun ? "run" : "save");
    try {
      let id = scriptId ?? null;
      if (id) {
        await updateWebUiScript(id, payload());
      } else {
        const created = await createWebUiScript(payload());
        id = created.id;
      }
      if (alsoRun && id) {
        await runWebUiScript(id);
        toast.success("已保存并开始执行（失败会自动自修复），可在执行历史里查看");
      } else {
        toast.success("已保存");
      }
      onSaved();
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(null);
    }
  };

  const generate = async () => {
    if (!intent.trim()) { toast.error("请描述测试意图"); return; }
    setGenerating(true);
    try {
      const result = await generateWebUiSpec({
        intent: intent.trim(),
        name: state.name.trim() || intent.trim().slice(0, 40),
        target_url: state.target_url.trim() || undefined,
        module: state.module.trim() || undefined,
        save: false,
      });
      patch({ content: result.content });
      if (!state.name.trim()) patch({ name: intent.trim().slice(0, 40) });
      setGenOpen(false);
      toast.success("已生成 spec 初稿，请检查断言后再保存");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "生成失败");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl p-0 sm:max-w-5xl">
        <div className="flex max-h-[90vh] flex-col">
          <DialogHeader className="border-b px-4 py-3">
            <DialogTitle className="flex items-center gap-2 text-base">
              {scriptId ? "编辑用例" : "新建 Web-UI 用例"}
              {scriptId && detail.data && (
                <Badge variant="outline" className="font-normal">v{detail.data.version}</Badge>
              )}
              <div className="ml-auto flex items-center gap-1">
                <button type="button" onClick={() => setTab("edit")}
                        className={cn("rounded px-2 py-1 text-xs",
                          tab === "edit" ? "bg-muted font-medium" : "text-muted-foreground")}>
                  编辑
                </button>
                <button type="button" onClick={() => setTab("repair")}
                        className={cn("rounded px-2 py-1 text-xs",
                          tab === "repair" ? "bg-muted font-medium" : "text-muted-foreground")}>
                  <History className="mr-1 inline h-3 w-3" />
                  修复历史{repairs.length > 0 ? `（${repairs.length}）` : ""}
                </button>
              </div>
            </DialogTitle>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto px-4 py-3">
            {tab === "repair" ? (
              <RepairHistoryPanel entries={repairs} />
            ) : (
              <div className="flex flex-col gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>用例名 *</Label>
                    <Input value={state.name} onChange={(e) => patch({ name: e.target.value })}
                           placeholder="豆瓣电影首页冒烟" />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>业务模块</Label>
                    <Input value={state.module} onChange={(e) => patch({ module: e.target.value })}
                           placeholder="电影" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>目标站点（baseURL）</Label>
                    <Input value={state.target_url}
                           onChange={(e) => patch({ target_url: e.target.value })}
                           placeholder="https://m.douban.com/movie/" />
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>spec 文件路径</Label>
                    <Input value={state.spec_file}
                           onChange={(e) => patch({ spec_file: e.target.value })}
                           placeholder="tests/spec.spec.ts" />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>设备模拟</Label>
                    <div className="flex items-center gap-2">
                      <Input value={state.desktop ? "" : state.device} disabled={state.desktop}
                             onChange={(e) => patch({ device: e.target.value })}
                             placeholder="iPhone 13" list="device-presets" />
                      <datalist id="device-presets">
                        {DEVICE_PRESETS.map((d) => <option key={d} value={d} />)}
                      </datalist>
                      <label className="flex shrink-0 items-center gap-1.5 text-xs">
                        <input type="checkbox" checked={state.desktop}
                               onChange={(e) => patch({ desktop: e.target.checked })} />
                        桌面浏览器
                      </label>
                    </div>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <Label>浏览器矩阵</Label>
                    <div className="flex h-9 items-center gap-3">
                      {BROWSERS.map((browser) => (
                        <label key={browser} className="flex items-center gap-1.5 text-xs">
                          <input
                            type="checkbox"
                            checked={state.browsers.includes(browser)}
                            onChange={(e) => patch({
                              browsers: e.target.checked
                                ? [...state.browsers, browser]
                                : state.browsers.filter((b) => b !== browser),
                            })}
                          />
                          {browser}
                        </label>
                      ))}
                      <span className="text-[11px] text-muted-foreground">
                        全不勾 = 只跑 chromium
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="flex flex-col gap-1.5">
                    <Label>录像</Label>
                    <select
                      value={state.video}
                      onChange={(e) => patch({ video: e.target.value })}
                      className="h-9 rounded-md border bg-transparent px-2 text-xs"
                    >
                      <option value="">仅失败时保留（默认，省磁盘）</option>
                      <option value="on">始终录制（通过的用例也留）</option>
                      <option value="off">不录制</option>
                    </select>
                  </div>
                  <div className="flex items-end pb-2 text-[11px] text-muted-foreground">
                    录像在「产物存证」里可直接播放、可拖进度条；单次执行约 1–3MB。
                  </div>
                </div>

                <div className="flex flex-col gap-1.5">
                  <Label>说明</Label>
                  <Input value={state.description}
                         onChange={(e) => patch({ description: e.target.value })}
                         placeholder="这条用例覆盖什么、为什么这么断言" />
                </div>

                <div className="flex flex-col gap-1.5">
                  <div className="flex items-center justify-between">
                    <Label>spec 内容（Playwright Test / TypeScript）</Label>
                    <Button size="sm" variant="outline" onClick={() => setGenOpen(true)}>
                      <Sparkles className="mr-1.5 h-3.5 w-3.5" />AI 生成
                    </Button>
                  </div>
                  <div className="overflow-hidden rounded-md border">
                    <CodeMirror
                      value={state.content}
                      height="340px"
                      extensions={[javascript({ typescript: true })]}
                      onChange={(value) => patch({ content: value })}
                    />
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    相对路径 goto（<code>page.goto(&apos;/movie/&apos;)</code>），baseURL 由执行器注入；
                    断言要给出具体期望值，每条用例至少留一张截图。
                  </p>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 border-t px-4 py-3">
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground">状态</Label>
              <select
                value={state.status}
                onChange={(e) => patch({ status: e.target.value })}
                className="h-8 rounded-md border bg-transparent px-2 text-xs"
              >
                <option value="draft">草稿</option>
                <option value="active">启用</option>
                <option value="broken">异常</option>
                <option value="archived">归档</option>
              </select>
            </div>
            <div className="ml-auto flex items-center gap-2">
              <Button variant="ghost" onClick={() => onOpenChange(false)}>取消</Button>
              <Button variant="outline" onClick={() => save(false)} disabled={saving !== null}>
                {saving === "save" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  : <Save className="mr-1.5 h-4 w-4" />}
                保存
              </Button>
              <Button onClick={() => save(true)} disabled={saving !== null}>
                {saving === "run" ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                  : <Play className="mr-1.5 h-4 w-4" />}
                保存并执行
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>

      {/* AI 生成 spec */}
      <Dialog open={genOpen} onOpenChange={setGenOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader><DialogTitle>用一句话生成 Playwright 用例</DialogTitle></DialogHeader>
          <div className="flex flex-col gap-3">
            <Textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              className="min-h-[120px]"
              placeholder="例如：验证豆瓣电影首页「影院热映」区块至少有 5 部影片，每张卡片有详情链接与评分，并留截图"
            />
            <p className="text-[11px] text-muted-foreground">
              生成的是初稿：断言是否成立、选择器是否命中，都要跑一遍才知道。
              生成的用例不会自动入库。
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setGenOpen(false)}>取消</Button>
              <Button onClick={generate} disabled={generating}>
                {generating && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                生成
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </Dialog>
  );
}
