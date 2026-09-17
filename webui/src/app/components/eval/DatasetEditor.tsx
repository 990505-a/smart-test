"use client";

/**
 * 评测集编辑器（表单式）。
 *
 * 为什么要有它：评测集原本只能手写 YAML 文件——缩进、块标量 `>-`、字段名全靠记，
 * 写错一个缩进要等到跑批次才发现。这里把同一份结构做成表单：填完保存，后端用
 * `yaml.safe_dump` 落成人类可读的 YAML（多行文本走 `|` 块）。文件仍是唯一事实源，
 * 手改也不会被页面覆盖——页面每次打开都从磁盘读回。
 */

import React, { useEffect, useMemo, useState } from "react";
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
import {
  EvalDatasetInfo, useEvalDatasetDetail, saveEvalDataset,
  type EvalDatasetDetail,
} from "@/lib/api/useNewModules";
import { toast } from "sonner";
import { Loader2, Plus, Trash2, ChevronDown, ChevronRight } from "lucide-react";

type DraftExpected = {
  contains: string;
  not_contains: string;
  toolsSequence: string;
  toolsMode: "subsequence" | "exact";
  maxToolErrors: string;
  evidence: string;
};

type DraftJudge = { criteria: string; pass: string };

type DraftItem = {
  id: string;
  input: string;
  useExpected: boolean;
  expected: DraftExpected;
  useJudge: boolean;
  judge: DraftJudge;
};

type Draft = {
  file: string;
  name: string;
  description: string;
  agent: string;
  maxRepair: string;
  items: DraftItem[];
};

const AGENT_OPTIONS = ["webui_agent", "testcase_agent", "unity_agent", "code_analyst_agent"];

const EMPTY_EXPECTED: DraftExpected = {
  contains: "", not_contains: "", toolsSequence: "", toolsMode: "subsequence",
  maxToolErrors: "", evidence: "",
};
const EMPTY_ITEM: DraftItem = {
  id: "", input: "", useExpected: true, expected: { ...EMPTY_EXPECTED },
  useJudge: false, judge: { criteria: "", pass: "0.7" },
};

const splitList = (text: string): string[] =>
  text.split(/[,，\n]/).map((part) => part.trim()).filter(Boolean);

/** 结构化 draft → 后端 payload（空壳字段不写出去）。 */
function toPayload(draft: Draft) {
  return {
    file: draft.file.trim() || undefined,
    name: draft.name.trim(),
    description: draft.description.trim() || null,
    agent: draft.agent.trim() || "webui_agent",
    max_repair: draft.maxRepair.trim() === "" ? null : Number(draft.maxRepair),
    items: draft.items.map((item, index) => ({
      id: item.id.trim() || `item-${index + 1}`,
      input: item.input,
      expected: item.useExpected ? {
        contains: splitList(item.expected.contains),
        not_contains: splitList(item.expected.not_contains),
        tools: splitList(item.expected.toolsSequence).length
          ? { sequence: splitList(item.expected.toolsSequence), mode: item.expected.toolsMode }
          : null,
        max_tool_errors: item.expected.maxToolErrors.trim() === ""
          ? null : Number(item.expected.maxToolErrors),
        evidence: item.expected.evidence.trim() || null,
      } : null,
      judge: item.useJudge && item.judge.criteria.trim() ? {
        criteria: item.judge.criteria,
        pass_threshold: Number(item.judge.pass) || 0.7,
      } : null,
    })),
  };
}

function fromDetail(detail: EvalDatasetDetail): Draft {
  return {
    file: detail.file,
    name: detail.name,
    description: detail.description ?? "",
    agent: detail.agent,
    maxRepair: detail.max_repair == null ? "" : String(detail.max_repair),
    items: detail.items.map((item) => ({
      id: item.id,
      input: item.input,
      useExpected: Boolean(item.expected),
      expected: {
        contains: (item.expected?.contains ?? []).join(", "),
        not_contains: (item.expected?.not_contains ?? []).join(", "),
        toolsSequence: (item.expected?.tools?.sequence ?? []).join(", "),
        toolsMode: item.expected?.tools?.mode ?? "subsequence",
        maxToolErrors: item.expected?.max_tool_errors == null
          ? "" : String(item.expected.max_tool_errors),
        evidence: item.expected?.evidence ?? "",
      },
      useJudge: Boolean(item.judge),
      judge: { criteria: item.judge?.criteria ?? "", pass: String(item.judge?.pass_threshold ?? 0.7) },
    })),
  };
}

function ItemCard({ item, index, onChange, onRemove, canRemove }: {
  item: DraftItem;
  index: number;
  onChange: (next: DraftItem) => void;
  onRemove: () => void;
  canRemove: boolean;
}) {
  const [open, setOpen] = useState(true);
  const patch = (partial: Partial<DraftItem>) => onChange({ ...item, ...partial });
  const patchExpected = (partial: Partial<DraftExpected>) =>
    patch({ expected: { ...item.expected, ...partial } });
  const patchJudge = (partial: Partial<DraftJudge>) =>
    patch({ judge: { ...item.judge, ...partial } });

  return (
    <div className="rounded-md border">
      <div className="flex items-center gap-2 border-b bg-muted/40 px-3 py-2">
        <button type="button" className="text-muted-foreground" onClick={() => setOpen(!open)}
                aria-label={open ? "收起这条用例" : "展开这条用例"}>
          {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
        <Input aria-label={`第 ${index + 1} 条用例的 id`}
               className="h-8 max-w-[220px] font-mono text-xs" value={item.id}
               placeholder={`item-${index + 1}`}
               onChange={(e) => patch({ id: e.target.value })} />
        <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
          {item.input.trim().slice(0, 60) || "（还没写任务，展开填写）"}
        </span>
        {canRemove && (
          <Button type="button" size="sm" variant="ghost" onClick={onRemove}
                  aria-label="删除这条用例">
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        )}
      </div>

      {open && (
        <div className="flex flex-col gap-3 p-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`item-${index}-input`}>任务（input）*</Label>
            <textarea
              id={`item-${index}-input`}
              className="min-h-[86px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring"
              value={item.input}
              placeholder="交给智能体的任务原话。写清产出要求：几条、什么格式、什么语言——判据必须在任务里交代过，judge 才判得动。"
              onChange={(e) => patch({ input: e.target.value })}
            />
          </div>

          <div className="rounded border border-dashed p-2.5">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={item.useExpected}
                     onChange={(e) => patch({ useExpected: e.target.checked })} />
              确定性期望（expected）— 免费、可复现，门禁主力
            </label>
            {item.useExpected && (
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-contains`}>答复须包含（逗号分隔）→ task_output_match</Label>
                  <Input id={`item-${index}-contains`} className="h-8 text-sm" value={item.expected.contains}
                         placeholder="登录, 验证码"
                         onChange={(e) => patchExpected({ contains: e.target.value })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-not-contains`}>不得出现（逗号分隔）→ no_forbidden_content</Label>
                  <Input id={`item-${index}-not-contains`} className="h-8 text-sm" value={item.expected.not_contains}
                         placeholder="我不确定"
                         onChange={(e) => patchExpected({ not_contains: e.target.value })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-tools`}>工具序列（逗号分隔）→ tool_sequence</Label>
                  <Input id={`item-${index}-tools`} className="h-8 font-mono text-xs" value={item.expected.toolsSequence}
                         placeholder="webui_run_spec"
                         onChange={(e) => patchExpected({ toolsSequence: e.target.value })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-mode`}>序列匹配方式</Label>
                  <Select value={item.expected.toolsMode}
                          onValueChange={(v) => patchExpected({ toolsMode: v as "subsequence" | "exact" })}>
                    <SelectTrigger id={`item-${index}-mode`} className="h-8"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="subsequence">subsequence（子序列，允许中间夹别的工具）</SelectItem>
                      <SelectItem value="exact">exact（严格一致）</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-max-errors`}>工具报错预算 → tool_errors（留空 = 不检查）</Label>
                  <Input id={`item-${index}-max-errors`} className="h-8 text-sm" type="number" min={0}
                         value={item.expected.maxToolErrors} placeholder="0"
                         onChange={(e) => patchExpected({ maxToolErrors: e.target.value })} />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-evidence`}>期望产物路径 → evidence_exists（支持一个 *）</Label>
                  <Input id={`item-${index}-evidence`} className="h-8 font-mono text-xs" value={item.expected.evidence}
                         placeholder="artifacts/*.png"
                         onChange={(e) => patchExpected({ evidence: e.target.value })} />
                </div>
              </div>
            )}
          </div>

          <div className="rounded border border-dashed p-2.5">
            <label className="flex items-center gap-2 text-sm font-medium">
              <input type="checkbox" checked={item.useJudge}
                     onChange={(e) => patch({ useJudge: e.target.checked })} />
              LLM 裁判（judge）— 判需要读懂语义的标准
            </label>
            {item.useJudge && (
              <div className="mt-2 flex flex-col gap-3">
                <div className="flex flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-criteria`}>评审标准（criteria）</Label>
                  <textarea
                    id={`item-${index}-criteria`}
                    className="min-h-[70px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:border-ring"
                    value={item.judge.criteria}
                    placeholder="写「判不通过的条件」比只写正面要求更有约束力，例如：多于或少于 3 条判不通过。"
                    onChange={(e) => patchJudge({ criteria: e.target.value })}
                  />
                </div>
                <div className="flex w-40 flex-col gap-1.5">
                  <Label className="text-xs" htmlFor={`item-${index}-pass`}>及格线 pass（0–1）</Label>
                  <Input id={`item-${index}-pass`} className="h-8 text-sm" type="number" step="0.05" min={0} max={1}
                         value={item.judge.pass}
                         onChange={(e) => patchJudge({ pass: e.target.value })} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function DatasetEditor({ file, seed, seedFileName, onClose, onSaved }: {
  /** null = 新建 */
  file: string | null;
  /** 初稿：从另一个评测集拷来的（复制），或 AI 从历史对话生成的草稿 */
  seed?: EvalDatasetDetail | null;
  /** 初稿建议的文件名（AI 生成时用；不给就按 -copy 命名） */
  seedFileName?: string;
  onClose: () => void;
  onSaved: (file: string) => void;
}) {
  const detail = useEvalDatasetDetail(file, Boolean(file));
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (file) {
      if (detail.data) setDraft(fromDetail(detail.data));
      return;
    }
    if (seed) {
      const suggested = seedFileName
        ?? `${(seed.file ?? "dataset").replace(/\.ya?ml$/, "")}-copy.yaml`;
      setDraft({ ...fromDetail(seed), file: suggested });
      return;
    }
    setDraft({
      file: "my-first.yaml", name: "my-first", description: "", agent: "testcase_agent",
      maxRepair: "", items: [{ ...EMPTY_ITEM, expected: { ...EMPTY_EXPECTED },
                               judge: { criteria: "", pass: "0.7" } }],
    });
  }, [file, seed, seedFileName, detail.data]);

  const problem = useMemo(() => {
    if (!draft) return null;
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*\.ya?ml$/.test(draft.file.trim())) {
      return "文件名要以 .yaml 结尾，只能用字母数字和 . _ -";
    }
    if (!draft.name.trim()) return "name 不能为空";
    if (draft.items.length === 0) return "至少要有一条用例";
    if (draft.items.some((item) => !item.input.trim())) return "每条用例都要写 input";
    const ids = draft.items.map((item, i) => item.id.trim() || `item-${i + 1}`);
    const duplicate = ids.find((id, i) => ids.indexOf(id) !== i);
    if (duplicate) return `用例 id 重复：${duplicate}`;
    return null;
  }, [draft]);

  const save = async () => {
    if (!draft || problem) return;
    setSaving(true);
    try {
      const response = await saveEvalDataset(file, toPayload(draft) as never);
      toast.success(file ? "已保存" : `已创建 ${draft.file.trim()}`);
      onSaved(response.data.file ?? draft.file.trim());
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const patchItem = (index: number, next: DraftItem) => {
    if (!draft) return;
    const items = [...draft.items];
    items[index] = next;
    setDraft({ ...draft, items });
  };

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="sm:max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {file ? `编辑评测集 · ${file}` : "新建评测集"}
            {file && <Badge variant="outline" className="font-normal">磁盘文件</Badge>}
          </DialogTitle>
        </DialogHeader>

        {!draft ? (
          <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />读取中…
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <div className="grid gap-3 md:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ds-file">文件名 *（保存在 datasets/ 下）</Label>
                <Input id="ds-file" value={draft.file} disabled={Boolean(file)} className="font-mono text-sm"
                       onChange={(e) => setDraft({ ...draft, file: e.target.value })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ds-name">评测集名 name *（批次名会用它）</Label>
                <Input id="ds-name" value={draft.name}
                       onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ds-agent">被测 agent</Label>
                <Input id="ds-agent" list="eval-agent-options" value={draft.agent}
                       onChange={(e) => setDraft({ ...draft, agent: e.target.value })} />
                <datalist id="eval-agent-options">
                  {AGENT_OPTIONS.map((agent) => <option key={agent} value={agent} />)}
                </datalist>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="ds-description">说明 description</Label>
                <Input id="ds-description" value={draft.description} placeholder="这个集子测什么"
                       onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
              </div>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">用例（{draft.items.length}）</span>
              <Button type="button" size="sm" variant="outline"
                      onClick={() => setDraft({
                        ...draft,
                        items: [...draft.items,
                                { ...EMPTY_ITEM, expected: { ...EMPTY_EXPECTED },
                                  judge: { criteria: "", pass: "0.7" } }],
                      })}>
                <Plus className="mr-1 h-3.5 w-3.5" />添加用例
              </Button>
            </div>

            <div className="flex flex-col gap-3">
              {draft.items.map((item, index) => (
                <ItemCard
                  key={index}
                  item={item}
                  index={index}
                  canRemove={draft.items.length > 1}
                  onChange={(next) => patchItem(index, next)}
                  onRemove={() => setDraft({
                    ...draft, items: draft.items.filter((_, i) => i !== index),
                  })}
                />
              ))}
            </div>

            {file && detail.data?.raw && (
              <details className="rounded border p-3">
                <summary className="cursor-pointer text-sm font-medium">
                  查看磁盘上的原始 YAML（也可以直接手改，页面会读回）
                </summary>
                <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted p-2 text-[11px] leading-4">
                  {detail.data.raw}
                </pre>
              </details>
            )}

            {problem && <p className="text-xs text-destructive">{problem}</p>}

            <div className="flex items-center justify-end gap-2">
              <Button type="button" variant="ghost" onClick={onClose}>取消</Button>
              <Button type="button" onClick={save} disabled={saving || Boolean(problem)}>
                {saving && <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />}
                {file ? "保存" : "创建"}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export type { EvalDatasetInfo };
