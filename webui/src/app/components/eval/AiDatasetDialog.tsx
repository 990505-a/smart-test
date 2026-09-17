"use client";

/**
 * AI 生成测评集：数据来源选「沉淀下来的完整对话记录」。
 *
 * 智能体跑完一次真实任务后，会话里留下了完整记录（用户任务 + 每次工具调用与
 * 结果 + 最终答复）。这类记录是评测集最好的素材——任务是被真实执行验证过的。
 * 这里把选中的会话交给主 LLM 提炼成用例草稿，**不直接落盘**：草稿回到编辑器里
 * 由人微调，改完再保存成 datasets/*.yaml。
 */

import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Loader2, Sparkles } from "lucide-react";
import {
  generateEvalDataset, useEvalSources,
  type EvalDatasetDetail, type EvalGenerateResult,
} from "@/lib/api/useNewModules";

const AGENT_OPTIONS = [
  { value: "testcase_agent", label: "用例生成" },
  { value: "unity_agent", label: "Unity 自动化" },
  { value: "webui_agent", label: "Web-UI 自动化" },
  { value: "code_analyst_agent", label: "代码分析" },
];

export function AiDatasetDialog({
  onClose,
  onGenerated,
}: {
  onClose: () => void;
  /** 生成完成 → 打开编辑器（file=null，seed=草稿） */
  onGenerated: (result: EvalGenerateResult) => void;
}) {
  const [agentFilter, setAgentFilter] = useState<string>("all");
  const sources = useEvalSources(agentFilter === "all" ? undefined : agentFilter);
  const [selected, setSelected] = useState<string[]>([]);
  const [targetAgent, setTargetAgent] = useState("testcase_agent");
  const [count, setCount] = useState("5");
  const [focus, setFocus] = useState("");
  const [name, setName] = useState("");
  const [running, setRunning] = useState(false);

  const rows = useMemo(() => sources.data ?? [], [sources.data]);

  const toggle = (threadId: string) => {
    setSelected((prev) =>
      prev.includes(threadId) ? prev.filter((id) => id !== threadId)
                              : [...prev, threadId]);
  };

  const run = async () => {
    if (selected.length === 0) {
      toast.error("先选至少一段对话作为数据来源");
      return;
    }
    setRunning(true);
    try {
      const result = await generateEvalDataset({
        thread_ids: selected,
        agent: targetAgent,
        count: Number(count) || 5,
        focus,
        name,
      });
      toast.success(`已生成 ${result.dataset.items.length} 条用例草稿，请在编辑器里微调后保存`);
      onGenerated(result);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "生成失败");
    } finally {
      setRunning(false);
    }
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />AI 生成测评集
            <Badge variant="outline" className="font-normal">来源：历史对话</Badge>
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          <p className="rounded bg-muted p-3 text-xs leading-5 text-muted-foreground">
            选一段**真实跑完的对话**（含工具调用记录），主 LLM 会把它提炼成
            <span className="font-mono"> input / expected / judge </span>
            三段式用例草稿。生成结果不会直接写进 datasets/——先在编辑器里按你的预期
            微调，保存后才成为正式评测集。
          </p>

          <div className="grid gap-3 md:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">按模式筛选来源</Label>
              <Select value={agentFilter} onValueChange={(v) => setAgentFilter(v ?? "all")}>
                <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部会话</SelectItem>
                  {AGENT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">被测 agent（评测集用）</Label>
              <Select value={targetAgent} onValueChange={(v) => setTargetAgent(v ?? "testcase_agent")}>
                <SelectTrigger className="h-8"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {AGENT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">生成条数</Label>
              <Input className="h-8" type="number" min={1} max={20} value={count}
                     onChange={(e) => setCount(e.target.value)} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-xs">数据集名（可留空）</Label>
              <Input className="h-8 font-mono text-xs" value={name}
                     placeholder="my-webui-regression"
                     onChange={(e) => setName(e.target.value)} />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-xs">额外要求（可选）</Label>
            <Input className="h-8 text-sm" value={focus}
                   placeholder="例如：只保留失败自修复相关的用例；每条都要带工具序列"
                   onChange={(e) => setFocus(e.target.value)} />
          </div>

          <div className="rounded border">
            <div className="flex items-center justify-between border-b px-3 py-2 text-xs text-muted-foreground">
              <span>选择数据来源（可多选，最多 5 段）</span>
              <span>已选 {selected.length}</span>
            </div>
            {sources.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />加载会话…
              </div>
            ) : rows.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                还没有可用的历史对话。先去对话页让智能体真跑一次。
              </p>
            ) : (
              <ScrollArea className="max-h-64">
                <ul className="divide-y">
                  {rows.map((row) => {
                    const checked = selected.includes(row.thread_id);
                    return (
                      <li key={row.thread_id}>
                        <label className="flex cursor-pointer items-start gap-2 px-3 py-2 hover:bg-muted/40">
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={checked}
                            onChange={() => toggle(row.thread_id)}
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm">{row.title}</span>
                            <span className="font-mono text-[11px] text-muted-foreground">
                              {row.agent || "未知模式"} · {row.messages} 条消息 · {row.thread_id.slice(0, 8)}
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </ScrollArea>
            )}
          </div>

          <div className="flex items-center justify-between">
            <p className="text-[11px] text-muted-foreground">
              生成走设置页的主 LLM（当前配置），记录过长会自动保留头尾。
            </p>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={onClose} disabled={running}>取消</Button>
              <Button onClick={run} disabled={running || selected.length === 0}>
                {running && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {running ? "生成中…" : "生成草稿"}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export type { EvalDatasetDetail };
