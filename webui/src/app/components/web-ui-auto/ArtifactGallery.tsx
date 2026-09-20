"use client";

/**
 * 产物浏览器（存证）——截图缩略图带 + 大图查看器 + 视频 + 其它文件下载。
 *
 * 为什么要有它：Playwright 每次失败都会留下失败截图、trace.zip（可逐帧回放）
 * 和 error-context.md，但此前页面上只显示「文件名 · 大小」的灰色徽章，等于
 * 存证存了个寂寞。这里把图片直接渲染出来（点击开大图、左右键切换），
 * trace/视频给可点的入口，其它文件给下载。
 *
 * 两个模块共用（Web-UI 的 Playwright 产物、Unity 的截图/录像）：所以取文件的
 * URL 由调用方通过 ``urlFor`` 注入，默认还是 Web-UI 那套签名路径。
 */

import React, { useEffect, useMemo, useState } from "react";
import {
  ChevronLeft, ChevronRight, Download, FileText, FileArchive, ImageIcon, Video, X,
} from "lucide-react";
import {
  Dialog, DialogContent,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { webUiArtifactUrl, type WebUiScriptRun } from "@/lib/api/useNewModules";
import { cn } from "@/lib/utils";

const IMAGE_EXT = /\.(png|jpe?g|webp|gif)$/i;
const VIDEO_EXT = /\.(webm|mp4|mov)$/i;
const TRACE_EXT = /\.zip$/i;
const TEXT_EXT = /\.(md|txt|json|jsonl|log)$/i;

/** 产物取文件的 URL 解析器（默认 Web-UI 的签名 URL）。 */
export type ArtifactUrlFor = (path: string) => string;

/**
 * 画廊只依赖这三个字段，所以两个模块的产物结构都能喂进来（Web-UI 的
 * ``{name,path,size}`` 与 Unity 的 ``UnityArtifact``）。``size`` 允许为空 ——
 * 产物文件被清理后后端就是给 null（那时名字旁边没有大小，别显示成 0B）。
 */
export interface GalleryArtifact {
  name?: string;
  path: string;
  size?: number | null;
}

function urlOf(run: Pick<WebUiScriptRun, "id" | "share_sig">,
               path: string, urlFor?: ArtifactUrlFor): string {
  return urlFor ? urlFor(path) : webUiArtifactUrl(run, path);
}

export function artifactKind(path: string): "image" | "video" | "trace" | "text" | "file" {
  if (IMAGE_EXT.test(path)) return "image";
  if (VIDEO_EXT.test(path)) return "video";
  if (TRACE_EXT.test(path)) return "trace";
  if (TEXT_EXT.test(path)) return "text";
  return "file";
}

function humanSize(bytes?: number | null): string {
  if (bytes == null) return "";
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)}MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${bytes}B`;
}

/** 「名字 · 大小」——大小缺失时不留孤零零的分隔符。 */
function label(name: string, size?: number | null): string {
  return [name, humanSize(size)].filter(Boolean).join(" · ");
}

/** 去掉 test-results 里的随机目录前缀，让名字能读。 */
function shortName(path: string): string {
  const parts = path.split("/");
  return parts[parts.length - 1];
}

export function ArtifactThumb({
  run, path, size, onOpen, urlFor,
}: {
  run: Pick<WebUiScriptRun, "id" | "share_sig">;
  path: string;
  size?: number | null;
  onOpen?: () => void;
  urlFor?: ArtifactUrlFor;
}) {
  const url = urlOf(run, path, urlFor);
  // 单个文件也可能被单独删掉（目录还在），所以除了「整目录已清理」之外，
  // 每张图还要自己兜住加载失败：显示占位而不是破图 + alt 文本。
  const [broken, setBroken] = useState(false);
  return (
    <button
      type="button"
      onClick={broken ? undefined : onOpen}
      className="group relative overflow-hidden rounded-md border bg-muted/40 text-left"
      title={path}
    >
      {broken ? (
        <span className="flex h-24 w-40 flex-col items-center justify-center gap-1 px-2 text-center text-[10px] text-muted-foreground">
          <ImageIcon className="h-4 w-4" />
          图片已无法加载
        </span>
      ) : (
        <>
          {/* 用 img 而不是 next/image：产物是签名 URL 的动态接口，没有优化意义 */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={shortName(path)}
            loading="lazy"
            onError={() => setBroken(true)}
            className="h-24 w-40 object-cover object-top transition group-hover:opacity-90"
          />
        </>
      )}
      <span className="block truncate px-1.5 py-1 text-[10px] text-muted-foreground">
        {label(shortName(path), size)}
      </span>
    </button>
  );
}

/** 产物整目录被清理时的说明块 —— 比一排破图诚实。 */
export function ArtifactsPrunedNotice({
  run, pruned,
}: {
  run?: Pick<WebUiScriptRun, "artifacts_pruned">;
  pruned?: boolean;
}) {
  if (!(pruned ?? run?.artifacts_pruned)) return null;
  return (
    <div className="rounded-md border border-warning/40 bg-warning/10 p-3 text-xs text-warning">
      这次执行的产物文件已不在服务器上（运行目录被清理或磁盘回收），截图 / 录像 / trace
      都无法回看。执行记录本身与用例明细仍然有效；需要存证就重新执行一次。
    </div>
  );
}

/** 大图查看器：左右键切换、Esc 关闭。抽出来给「用例失败截图」单独复用。 */
export function ImageViewer({
  run, paths, index, onIndex, onClose, urlFor,
}: {
  run: Pick<WebUiScriptRun, "id" | "share_sig">;
  paths: string[];
  index: number | null;
  onIndex: (next: number) => void;
  onClose: () => void;
  urlFor?: ArtifactUrlFor;
}) {
  useEffect(() => {
    if (index === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "ArrowLeft") onIndex(Math.max(0, index - 1));
      else if (event.key === "ArrowRight") onIndex(Math.min(paths.length - 1, index + 1));
      else if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, onIndex, onClose, paths.length]);

  return (
    <Dialog open={index !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[92vw] p-2 sm:max-w-[92vw]">
        {index !== null && paths[index] && (
          <div className="flex max-h-[88vh] flex-col gap-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="truncate font-mono">{paths[index]}</span>
              <span>{index + 1} / {paths.length}</span>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={urlOf(run, paths[index], urlFor)}
              alt={shortName(paths[index])}
              className="max-h-[76vh] w-full object-contain"
            />
            <div className="flex items-center justify-between">
              <Button size="sm" variant="outline" disabled={index === 0}
                      onClick={() => onIndex(index - 1)}>
                <ChevronLeft className="mr-1 h-3.5 w-3.5" />上一张
              </Button>
              <a
                href={urlOf(run, paths[index], urlFor)}
                target="_blank" rel="noreferrer"
                className="text-xs text-primary hover:underline"
              >
                新标签页打开原图
              </a>
              <Button size="sm" variant="outline" disabled={index === paths.length - 1}
                      onClick={() => onIndex(index + 1)}>
                下一张<ChevronRight className="ml-1 h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export function ArtifactGallery({
  run, artifacts, urlFor, videoHint,
}: {
  run: Pick<WebUiScriptRun, "id" | "share_sig" | "artifacts_pruned">;
  artifacts: GalleryArtifact[];
  urlFor?: ArtifactUrlFor;
  /** 没有录像时给一句解释（两个模块的录制策略不同，由调用方说清） */
  videoHint?: string;
}) {
  const groups = useMemo(() => {
    const images = artifacts.filter((a) => artifactKind(a.path) === "image");
    const videos = artifacts.filter((a) => artifactKind(a.path) === "video");
    const traces = artifacts.filter((a) => artifactKind(a.path) === "trace");
    const texts = artifacts.filter((a) => artifactKind(a.path) === "text");
    const others = artifacts.filter((a) => artifactKind(a.path) === "file");
    return { images, videos, traces, texts, others };
  }, [artifacts]);

  const [lightbox, setLightbox] = useState<number | null>(null);
  const [textPreview, setTextPreview] = useState<GalleryArtifact | null>(null);

  if (run.artifacts_pruned) {
    // 详细说明由详情页顶部统一给（那里还解释了为什么报告按钮不见了），
    // 这里只留一句，避免同一段话在一屏里说两遍。
    return (
      <p className="py-6 text-center text-xs text-muted-foreground">
        该次执行的产物已被清理，本地无可查看的存证。
      </p>
    );
  }

  if (artifacts.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        这次执行没有产物（用例全部通过且未开 trace/video？）
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {groups.images.length > 0 && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <ImageIcon className="h-3.5 w-3.5" />截图 {groups.images.length} 张（点击看大图，←/→ 切换）
          </h4>
          <div className="flex flex-wrap gap-2">
            {groups.images.map((a, index) => (
              <ArtifactThumb
                key={a.path}
                run={run}
                path={a.path}
                size={a.size}
                urlFor={urlFor}
                onOpen={() => setLightbox(index)}
              />
            ))}
          </div>
        </section>
      )}

      {groups.videos.length === 0 && groups.images.length > 0 && (
        <p className="text-[11px] text-muted-foreground">{videoHint}</p>
      )}

      {groups.videos.length > 0 && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Video className="h-3.5 w-3.5" />录像 {groups.videos.length} 段
          </h4>
          <div className="flex flex-wrap gap-3">
            {groups.videos.map((a) => (
              <div key={a.path} className="w-[320px]">
                {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
                <video
                  controls
                  preload="metadata"
                  src={urlOf(run, a.path, urlFor)}
                  className="w-full rounded-md border bg-black"
                />
                <p className="mt-1 truncate text-[10px] text-muted-foreground">
                  {label(shortName(a.path), a.size)}
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {groups.traces.length > 0 && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <FileArchive className="h-3.5 w-3.5" />trace（在「官方报告」里点开可逐帧回放）
          </h4>
          <div className="flex flex-wrap gap-2">
            {groups.traces.map((a) => (
              <a
                key={a.path}
                href={urlOf(run, a.path, urlFor)}
                className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] hover:bg-muted"
              >
                <Download className="h-3 w-3" />
                {label(shortName(a.path), a.size)}
              </a>
            ))}
          </div>
        </section>
      )}

      {(groups.texts.length > 0 || groups.others.length > 0) && (
        <section>
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <FileText className="h-3.5 w-3.5" />其它文件
          </h4>
          <div className="flex flex-wrap gap-2">
            {[...groups.texts, ...groups.others].map((a) => (
              <button
                key={a.path}
                type="button"
                onClick={() => setTextPreview(a)}
                className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] hover:bg-muted"
              >
                {label(shortName(a.path), a.size)}
              </button>
            ))}
          </div>
        </section>
      )}

      {/* 大图查看器 */}
      <ImageViewer
        run={run}
        paths={groups.images.map((a) => a.path)}
        index={lightbox}
        onIndex={setLightbox}
        onClose={() => setLightbox(null)}
        urlFor={urlFor}
      />

      {/* 文本文件预览（error-context.md 之类） */}
      <Dialog open={textPreview !== null} onOpenChange={(open) => !open && setTextPreview(null)}>
        <DialogContent className="sm:max-w-3xl">
          <div className="flex items-center justify-between">
            <span className="truncate font-mono text-xs">{textPreview?.path}</span>
            <button type="button" onClick={() => setTextPreview(null)}>
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </div>
          {textPreview && (
            <ArtifactText run={run} path={textPreview.path} urlFor={urlFor} />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** 文本产物按需拉取（签名 URL 是普通 GET，可以直接 fetch 成文本）。 */
function ArtifactText({
  run, path, className, urlFor,
}: {
  run: Pick<WebUiScriptRun, "id" | "share_sig">;
  path: string;
  className?: string;
  urlFor?: ArtifactUrlFor;
}) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    fetch(urlOf(run, path, urlFor))
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((t) => alive && setText(t))
      .catch((e) => alive && setError(String(e)));
    return () => { alive = false; };
  }, [run, path, urlFor]);
  return (
    <pre className={cn("max-h-[70vh] overflow-auto rounded bg-muted p-3 text-[11px]", className)}>
      {error ? `读取失败：${error}` : text ?? "加载中…"}
    </pre>
  );
}
