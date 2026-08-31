"use client";

// 用例文档页（2026-08 重构）：一个项目 = 一份 Markdown 用例文档。
// 智能体生成落盘 → 用户在源文件上直接标注（✅/❌/⚠️ + `>` 批注）→
// 自进化按标注反思；飞书导出读同一份文档（标注自动剥离）。

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { parseAsString, useQueryState } from "nuqs";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHeader, EmptyState } from "@/app/components/ui-patterns";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Plus,
  Trash2,
  Loader2,
  Save,
  Eye,
  Pencil,
  FileText,
  ExternalLink,
  MessageSquareQuote,
  ListTree,
} from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "@/lib/api-client";
import { CaseStructureView } from "@/app/components/CaseStructureView";
import {
  useCaseDocs,
  useCaseDoc,
  useSaveCaseDoc,
  useDeleteCaseDoc,
  useLintCaseDoc,
  useReviewCaseDoc,
  useApproveCaseDoc,
  useReleaseCaseDoc,
  useRequestCaseDocChanges,
  type CaseDocInfo,
} from "@/lib/api/useCaseDocs";

const NEW_DOC_TEMPLATE = (name: string) =>
  `# ${name}_用例集\n\n## 分组\n\n#### 用例标题 [P0]\n\n前置：\n\n- 操作 ⇒ 预期结果\n`;

function formatDate(unix: number): string {
  return new Date(unix * 1000).toLocaleString("zh-CN", { hour12: false });
}

export default function CaseDocsPage() {
  const { data: docs, isLoading, mutate: reloadDocs } = useCaseDocs();
  const [documentQuery] = useQueryState("name", parseAsString);
  const [selected, setSelected] = useState<string | null>(documentQuery);
  const { data: doc, mutate: reloadDoc } = useCaseDoc(selected);

  const [draft, setDraft] = useState<string>("");
  const [mode, setMode] = useState<"structure" | "preview" | "edit">("structure");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<CaseDocInfo | null>(null);
  const [exporting, setExporting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const loadedName = useRef<string | null>(null);

  const { trigger: saveDoc, isMutating: saving } = useSaveCaseDoc();
  const { trigger: deleteDoc } = useDeleteCaseDoc();
  const { trigger: lintDoc, isMutating: linting } = useLintCaseDoc();
  const { trigger: reviewDoc, isMutating: reviewing } = useReviewCaseDoc();
  const { trigger: approveDoc, isMutating: approving } = useApproveCaseDoc();
  const { trigger: releaseDoc, isMutating: releasing } = useReleaseCaseDoc();
  const { trigger: requestChanges, isMutating: requestingChanges } = useRequestCaseDocChanges();

  // Load document content into the editor whenever selection changes
  useEffect(() => {
    if (doc && selected !== null && loadedName.current !== selected) {
      setDraft(doc.content);
      loadedName.current = selected;
      setMode("structure");
    }
  }, [doc, selected]);

  useEffect(() => {
    if (documentQuery && docs?.some((item) => item.name === documentQuery)) {
      if (selected !== documentQuery) setSelected(documentQuery);
      return;
    }
    if (!selected && docs && docs.length > 0) setSelected(docs[0].name);
  }, [documentQuery, docs, selected]);

  const dirty = useMemo(
    () => doc !== undefined && selected !== null && draft !== doc.content,
    [draft, doc, selected],
  );

  const handleSave = useCallback(async () => {
    if (!selected) return;
    try {
      await saveDoc({
        name: selected,
        content: draft,
        expected_revision: doc?.revision,
        expected_hash: doc?.content_hash,
      });
      loadedName.current = null; // force reload next effect pass
      await reloadDoc();
      await reloadDocs();
      toast.success("已保存草稿");
    } catch (e) {
      toast.error(`保存失败：${e instanceof Error ? e.message : e}`);
    }
  }, [selected, draft, doc?.revision, doc?.content_hash, saveDoc, reloadDoc, reloadDocs]);

  const actionArgs = useCallback(() => ({
    name: selected ?? "",
    expected_revision: doc?.revision,
    expected_hash: doc?.content_hash,
  }), [selected, doc?.revision, doc?.content_hash]);

  const handleWorkflowAction = useCallback(async (
    action: (args: ReturnType<typeof actionArgs>) => Promise<unknown>,
    successMessage: string,
  ) => {
    if (!selected) return;
    try {
      await action(actionArgs());
      await reloadDoc();
      await reloadDocs();
      toast.success(successMessage);
    } catch (e) {
      toast.error(`操作失败：${e instanceof Error ? e.message : e}`);
    }
  }, [selected, actionArgs, reloadDoc, reloadDocs]);

  const handleLint = useCallback(() =>
    handleWorkflowAction((args) => lintDoc(args), "Lint 检查完成"),
  [handleWorkflowAction, lintDoc]);

  const handleReview = useCallback(() =>
    handleWorkflowAction((args) => reviewDoc(args), "已完成二次复核"),
  [handleWorkflowAction, reviewDoc]);

  const handleApprove = useCallback(() =>
    handleWorkflowAction((args) => approveDoc(args), "已批准当前版本"),
  [handleWorkflowAction, approveDoc]);

  const handleRelease = useCallback(() =>
    handleWorkflowAction((args) => {
      if (!window.confirm("确定发布当前已批准版本吗？发布后将作为正式用例版本。")) {
        return Promise.resolve(null);
      }
      return releaseDoc(args);
    }, "已发布当前版本"),
  [handleWorkflowAction, releaseDoc]);

  const handleRequestChanges = useCallback(() =>
    handleWorkflowAction((args) => requestChanges(args), "已退回修改"),
  [handleWorkflowAction, requestChanges]);

  const handleCreate = useCallback(async () => {
    const name = newName.trim();
    if (!name) return;
    if (docs?.some((d) => d.name === name)) {
      toast.error("已存在同名文档");
      return;
    }
    try {
      await saveDoc({ name, content: NEW_DOC_TEMPLATE(name) });
      setCreating(false);
      setNewName("");
      loadedName.current = null;
      await reloadDocs();
      setSelected(name);
      toast.success("已创建文档");
    } catch (e) {
      toast.error(`创建失败: ${e instanceof Error ? e.message : e}`);
    }
  }, [newName, docs, saveDoc, reloadDocs]);

  const handleDelete = useCallback(async () => {
    if (!deleting) return;
    try {
      await deleteDoc(deleting.name);
      if (selected === deleting.name) {
        setSelected(null);
        loadedName.current = null;
      }
      toast.success(`已删除 ${deleting.name}`);
    } catch (e) {
      toast.error(`删除失败: ${e instanceof Error ? e.message : e}`);
    } finally {
      setDeleting(null);
    }
  }, [deleting, deleteDoc, selected]);

  const handleExportFeishu = useCallback(async () => {
    if (!selected) return;
    setExporting(true);
    try {
      const res = await apiClient.post<{ url?: string; mode?: string }>(
        "/feishu/mindnote/export",
        { project_name: selected },
      );
      const url = res.data?.url;
      if (url) {
        toast.success("已导出飞书思维导图", {
          action: { label: "打开", onClick: () => window.open(url, "_blank") },
        });
      } else {
        toast.info(res.data?.mode === "created" ? "已导出" : `导出结果: ${JSON.stringify(res.data).slice(0, 120)}`);
      }
    } catch (e) {
      toast.error(`飞书导出失败: ${e instanceof Error ? e.message : e}`);
    } finally {
      setExporting(false);
    }
  }, [selected]);

  // Insert an annotation at the end of the current line (✅/❌/⚠️ append to
  // heading; 批注 opens a `>` quote line below).
  const insertAtLine = useCallback((insertion: string, newLine: boolean) => {
    const el = textareaRef.current;
    if (!el) return;
    const pos = el.selectionStart ?? draft.length;
    let lineEnd = draft.indexOf("\n", pos);
    if (lineEnd === -1) lineEnd = draft.length;
    const insertAt = newLine ? lineEnd + 1 : lineEnd;
    const text = newLine ? `${insertion}` : insertion;
    const next = draft.slice(0, insertAt) + text + draft.slice(insertAt);
    setDraft(next);
    requestAnimationFrame(() => {
      el.focus();
      const cursor = insertAt + text.length;
      el.setSelectionRange(cursor, cursor);
    });
  }, [draft]);

  const annotatedCount = useMemo(
    () => docs?.filter((d) => d.annotated).length ?? 0,
    [docs],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 overflow-hidden">
        <div className="flex h-full flex-col">
          <div className="shrink-0 px-6 pt-6 lg:px-8">
            <PageHeader
              title="用例文档"
              description={`一个项目一份 Markdown：智能体生成落盘，在这里直接标注（✅ 好 / ❌ 不好 / ⚠️ 漏测 + > 批注），自进化按标注反思${docs?.length ? ` · 已标注 ${annotatedCount}/${docs.length} 份` : ""}`}
              actions={
                <Button onClick={() => setCreating(true)}>
                  <Plus className="mr-2 h-4 w-4" />
                  新建文档
                </Button>
              }
            />
          </div>

          <div className="flex min-h-0 flex-1 gap-4 px-6 pb-6 lg:px-8">
            {/* Document list */}
            <div className="flex w-72 shrink-0 flex-col overflow-hidden rounded-xl border">
              <div className="min-h-0 flex-1 overflow-y-auto p-2">
                {isLoading ? (
                  <div className="space-y-2 p-2">
                    {[1, 2, 3].map((i) => (
                      <Skeleton key={i} className="h-16 w-full" />
                    ))}
                  </div>
                ) : !docs || docs.length === 0 ? (
                  <EmptyState
                    title="还没有用例文档"
                    description="在聊天页让智能体生成用例（自动保存），或点右上角新建"
                    icon={FileText}
                    className="border-0 py-12"
                  />
                ) : (
                  <>
                    {([
                      { label: "正式版本（已批准/已发布）", items: docs.filter((d) => d.lifecycle_status === "released" || d.lifecycle_status === "approved") },
                      { label: "草稿与评审中", items: docs.filter((d) => d.lifecycle_status !== "released" && d.lifecycle_status !== "approved") },
                    ] as const)
                      .filter((section) => section.items.length > 0)
                      .map((section) => (
                        <div key={section.label} className="mb-2">
                          <p className="m-0 px-3 py-1 text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                            {section.label} · {section.items.length}
                          </p>
                          <ul className="m-0 list-none space-y-1 p-0">
                            {section.items.map((d) => (
                              <li key={d.name}>
                                <button
                                  type="button"
                                  onClick={() => setSelected(d.name)}
                                  className={`group w-full rounded-lg px-3 py-2.5 text-left transition-colors ${
                                    selected === d.name
                                      ? "bg-accent"
                                      : "hover:bg-accent/50"
                                  }`}
                                >
                                  <div className="flex items-start justify-between gap-2">
                                    <span className="line-clamp-1 text-sm font-medium">
                                      {d.title || d.name}
                                    </span>
                                    <div className="flex shrink-0 items-center gap-1">
                                      <Badge variant="secondary" className="h-5 px-1.5 text-[10px]">
                                        {d.lifecycle_status === "released" ? "已发布" : d.lifecycle_status === "approved" ? "已批准" : d.lifecycle_status === "in_review" ? "评审中" : d.lint_status === "failed" ? "Lint失败" : "草稿"}
                                      </Badge>
                                      <span
                                        role="button"
                                        tabIndex={0}
                                        className="mt-0.5 hidden shrink-0 rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive group-hover:block"
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setDeleting(d);
                                        }}
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter" || e.key === " ") {
                                            e.stopPropagation();
                                            setDeleting(d);
                                          }
                                        }}
                                      >
                                        <Trash2 className="h-3.5 w-3.5" />
                                      </span>
                                    </div>
                                  </div>
                                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                                    <span>{d.case_count} 条用例</span>
                                    {d.annotated && (
                                      <span className="flex items-center gap-1">
                                        {d.good > 0 && <Badge className="h-4 px-1 text-[10px]">✅{d.good}</Badge>}
                                        {d.bad > 0 && <Badge className="h-4 px-1 text-[10px]">❌{d.bad}</Badge>}
                                        {d.warn > 0 && <Badge className="h-4 px-1 text-[10px]">⚠️{d.warn}</Badge>}
                                      </span>
                                    )}
                                    <span className="ml-auto">{formatDate(d.updated_at)}</span>
                                  </div>
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      ))}
                  </>
                )}
              </div>
            </div>

            {/* Editor / preview */}
            <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border">
              {!selected ? (
                <EmptyState
                  title="选择左侧文档查看"
                  description="用例文档按 Markdown 组织：标题层级 = 思维导图节点层级"
                  icon={FileText}
                  className="m-auto border-0"
                />
              ) : (
                <>
                  <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {selected}.md
                    </span>
                    {dirty && (
                      <span className="text-xs text-warning">未保存</span>
                    )}
                    <div className="flex shrink-0 items-center rounded-md border p-0.5">
                      {(
                        [
                          { key: "structure", label: "结构", icon: ListTree },
                          { key: "preview", label: "Markdown", icon: Eye },
                          { key: "edit", label: "编辑", icon: Pencil },
                        ] as const
                      ).map(({ key, label, icon: Icon }) => (
                        <button
                          key={key}
                          type="button"
                          onClick={() => setMode(key)}
                          className={`flex h-6 items-center gap-1 rounded px-2 text-xs transition-colors ${
                            mode === key
                              ? "bg-accent font-medium"
                              : "text-muted-foreground hover:bg-accent/50"
                          }`}
                        >
                          <Icon className="h-3 w-3" />
                          {label}
                        </button>
                      ))}
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleLint}
                      disabled={linting || dirty}
                      title={dirty ? "请先保存草稿" : "运行确定性质量检查"}
                    >
                      {linting && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      Lint
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleReview}
                      disabled={reviewing || dirty || doc?.lint_status !== "passed"}
                      title={doc?.lint_status !== "passed" ? "请先通过 Lint" : "运行隔离上下文二次复核"}
                    >
                      {reviewing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      二次复核
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleApprove}
                      disabled={approving || dirty || doc?.lint_status !== "passed" || doc?.review_status !== "passed"}
                    >
                      {approving && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      批准
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRequestChanges}
                      disabled={requestingChanges || dirty || doc?.lifecycle_status !== "in_review"}
                    >
                      {requestingChanges && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      退回修改
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleRelease}
                      disabled={releasing || dirty || doc?.lifecycle_status !== "approved"}
                      title="只有已批准版本可以发布"
                    >
                      {releasing && <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />}
                      发布
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleExportFeishu}
                      disabled={exporting}
                    >
                      {exporting ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      飞书导图
                    </Button>
                    <Button size="sm" onClick={handleSave} disabled={!dirty || saving}>
                      {saving ? (
                        <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Save className="mr-1.5 h-3.5 w-3.5" />
                      )}
                      保存
                    </Button>
                  </div>

                  {doc && (
                    <div className="flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-xs text-muted-foreground">
                      <span>版本 v{doc.revision}</span>
                      <span>·</span>
                      <span>Lint：{doc.lint_status}</span>
                      <span>·</span>
                      <span>复核：{doc.review_status}</span>
                      {doc.unresolved_questions && doc.unresolved_questions.length > 0 && (
                        <span className="text-warning">
                          · 有 {doc.unresolved_questions.length} 个待确认问题（在聊天中回复智能体解答）
                        </span>
                      )}
                    </div>
                  )}

                  {doc?.lint_report && (!doc.lint_report.ok || doc.lint_report.warnings.length > 0) && (
                    <div className="max-h-32 shrink-0 overflow-y-auto border-b bg-muted/30 px-3 py-2 text-xs">
                      {doc.lint_report.errors.map((item, index) => (
                        <p key={`lint-error-${index}`} className="m-0 text-destructive">
                          {item.line ? `第${item.line}行：` : ""}{item.message}
                        </p>
                      ))}
                      {doc.lint_report.warnings.map((item, index) => (
                        <p key={`lint-warning-${index}`} className="m-0 text-warning">
                          {item.line ? `第${item.line}行：` : ""}{item.message}
                        </p>
                      ))}
                    </div>
                  )}

                  {doc?.review_report?.issues && doc.review_report.issues.length > 0 && (
                    <div className="max-h-40 shrink-0 overflow-y-auto border-b bg-amber-50/50 px-3 py-2 text-xs dark:bg-amber-950/20">
                      <p className="m-0 mb-1 font-medium">二次复核问题</p>
                      {doc.review_report.issues.map((issue, index) => (
                        <p key={`review-issue-${index}`} className="m-0 text-muted-foreground">
                          <span className="font-medium">[{issue.severity}]</span> {issue.evidence || issue.recommendation || issue.code}
                        </p>
                      ))}
                    </div>
                  )}

                  {mode === "structure" ? (
                    doc ? (
                      <CaseStructureView doc={doc} />
                    ) : (
                      <div className="flex flex-1 items-center justify-center">
                        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                      </div>
                    )
                  ) : mode === "edit" ? (
                    <>
                      <div className="flex shrink-0 items-center gap-1.5 border-b px-3 py-1.5 text-xs">
                        <span className="text-muted-foreground">标注：</span>
                        <Button variant="outline" size="sm" className="h-6 px-2" onClick={() => insertAtLine(" ✅", false)}>
                          ✅ 好
                        </Button>
                        <Button variant="outline" size="sm" className="h-6 px-2" onClick={() => insertAtLine(" ❌", false)}>
                          ❌ 不好
                        </Button>
                        <Button variant="outline" size="sm" className="h-6 px-2" onClick={() => insertAtLine(" ⚠️", false)}>
                          ⚠️ 漏测
                        </Button>
                        <Button variant="outline" size="sm" className="h-6 px-2" onClick={() => insertAtLine("> ", true)}>
                          <MessageSquareQuote className="mr-1 h-3 w-3" /> 批注
                        </Button>
                      </div>
                      <Textarea
                        ref={textareaRef}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        className="min-h-0 flex-1 resize-none rounded-none border-0 font-mono text-[13px] leading-6"
                        spellCheck={false}
                      />
                    </>
                  ) : (
                    <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
                      <div className="prose prose-sm max-w-none dark:prose-invert">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {draft || "（空文档）"}
                        </ReactMarkdown>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Create dialog */}
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle>新建用例文档</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="项目名，如 飞升之路_2026.08.28"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreating(false)}>
              取消
            </Button>
            <Button onClick={handleCreate} disabled={!newName.trim()}>
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除用例文档？</AlertDialogTitle>
            <AlertDialogDescription>
              将删除 {deleting?.name}.md（{deleting?.case_count ?? 0} 条用例及其标注），此操作不可恢复。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete}>删除</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
