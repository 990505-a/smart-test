"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema, type Options as SanitizeSchema } from "rehype-sanitize";
import { cn } from "@/lib/utils";
import { rewriteLocalImages } from "@/lib/rewriteLocalImages";

interface MarkdownContentProps {
  content: string;
  className?: string;
  streaming?: boolean;
}

function CodeBlock({
  language,
  code,
  plain = false,
}: {
  language?: string;
  code: string;
  /** Render as a plain <pre> (no Prism). Used for code still streaming in. */
  plain?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [SyntaxHighlighterComponent, setSyntaxHighlighterComponent] = useState<React.ElementType | null>(null);
  const [syntaxStyle, setSyntaxStyle] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || isVisible) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" },
    );

    observer.observe(element);
    return () => observer.disconnect();
  }, [isVisible]);

  useEffect(() => {
    if (plain || !isVisible || !language || SyntaxHighlighterComponent) return;

    let disposed = false;
    Promise.all([
      import("react-syntax-highlighter"),
      import("react-syntax-highlighter/dist/esm/styles/prism"),
    ]).then(([highlighterModule, styleModule]) => {
      if (disposed) return;
      setSyntaxHighlighterComponent(() => highlighterModule.Prism);
      setSyntaxStyle(styleModule.oneDark);
    });

    return () => { disposed = true; };
  }, [SyntaxHighlighterComponent, isVisible, language, plain]);

  const fallback = (
    <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-[#282c34] p-4 font-mono text-sm leading-6 text-white">
      {code}
    </pre>
  );

  return (
    <div ref={containerRef} className="my-4 max-w-full overflow-hidden last:mb-0">
      {!plain && language && SyntaxHighlighterComponent && syntaxStyle ? (
        <SyntaxHighlighterComponent
          style={syntaxStyle}
          language={language}
          PreTag="div"
          className="max-w-full rounded-md text-sm"
          wrapLines={true}
          wrapLongLines={true}
          lineProps={{
            style: {
              wordBreak: "break-all",
              whiteSpace: "pre-wrap",
              overflowWrap: "break-word",
            },
          }}
          customStyle={{
            margin: 0,
            maxWidth: "100%",
            overflowX: "auto",
            fontSize: "0.875rem",
          }}
        >
          {code}
        </SyntaxHighlighterComponent>
      ) : (
        fallback
      )}
    </div>
  );
}

function renderInlineMarkdown(text: string) {
  const codeParts = text.split(/(`[^`]+`)/g);

  const renderStyledText = (segment: string, prefix: string) => {
    const tokens = segment.split(
      /(https?:\/\/[^\s]+|\*\*[^*]+\*\*|__[^_]+__|~~[^~]+~~|\*[^*]+\*|_[^_]+_|<br\s*\/?>)/gi,
    );

    return tokens.map((token, index) => {
      if (!token) return null;

      if (/^https?:\/\//.test(token)) {
        return (
          <a
            key={`${prefix}-link-${index}`}
            href={token}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary no-underline hover:underline"
          >
            {token}
          </a>
        );
      }

      if ((token.startsWith("**") && token.endsWith("**")) || (token.startsWith("__") && token.endsWith("__"))) {
        return <strong key={`${prefix}-strong-${index}`}>{token.slice(2, -2)}</strong>;
      }

      if (token.startsWith("~~") && token.endsWith("~~")) {
        return <del key={`${prefix}-del-${index}`}>{token.slice(2, -2)}</del>;
      }

      if ((token.startsWith("*") && token.endsWith("*")) || (token.startsWith("_") && token.endsWith("_"))) {
        return <em key={`${prefix}-em-${index}`}>{token.slice(1, -1)}</em>;
      }

      if (/^<br\s*\/?>$/i.test(token)) {
        return <br key={`${prefix}-br-${index}`} />;
      }

      return <React.Fragment key={`${prefix}-text-${index}`}>{token}</React.Fragment>;
    });
  };

  return codeParts.flatMap((part, index) => {
    if (!part) return [];

    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return (
        <code
          key={`inline-code-${index}`}
          className="rounded-sm bg-muted px-1 py-0.5 font-mono text-[0.9em]"
        >
          {part.slice(1, -1)}
        </code>
      );
    }

    return renderStyledText(part, `segment-${index}`);
  });
}

/**
 * Parse line-oriented markdown into React rows. Pure function.
 *
 * @param openFencePlain when true, a code fence left open at the END of the
 *   content (still streaming in) renders as a plain <pre> instead of running
 *   Prism over the whole block on every token.
 */
function parseMarkdownRows(content: string, openFencePlain: boolean): React.ReactNode[] {
  const lines = content.split(/\r?\n/);
  const rows: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLanguage = "";
  let codeLines: string[] = [];
  let tableBuffer: string[] = [];

  const flushTable = (keyPrefix: string) => {
    if (tableBuffer.length < 2) {
      tableBuffer.forEach((tableLine, tableIndex) => {
        rows.push(
          <p key={`${keyPrefix}-fallback-${tableIndex}`} className="m-0 whitespace-pre-wrap break-words text-sm leading-relaxed">
            {renderInlineMarkdown(tableLine)}
          </p>,
        );
      });
      tableBuffer = [];
      return;
    }

    const normalizedRows = tableBuffer
      .map((row) => row.trim())
      .filter(Boolean)
      .map((row) =>
        row
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((cell) => cell.trim()),
      );

    const separatorPattern = /^:?-{3,}:?$/;
    const hasHeaderSeparator = normalizedRows[1]?.every((cell) => separatorPattern.test(cell));

    if (!hasHeaderSeparator) {
      tableBuffer.forEach((tableLine, tableIndex) => {
        rows.push(
          <p key={`${keyPrefix}-plain-${tableIndex}`} className="m-0 whitespace-pre-wrap break-words text-sm leading-relaxed">
            {renderInlineMarkdown(tableLine)}
          </p>,
        );
      });
      tableBuffer = [];
      return;
    }

    const headers = normalizedRows[0] ?? [];
    const bodyRows = normalizedRows.slice(2);

    rows.push(
      <div key={`${keyPrefix}-table`} className="my-2 overflow-x-auto">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr>
              {headers.map((header, headerIndex) => (
                <th key={`${keyPrefix}-th-${headerIndex}`} className="border border-border bg-muted px-2 py-1 text-left font-semibold">
                  {renderInlineMarkdown(header)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {bodyRows.map((row, rowIndex) => (
              <tr key={`${keyPrefix}-tr-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`${keyPrefix}-td-${rowIndex}-${cellIndex}`} className="border border-border px-2 py-1 align-top">
                    {renderInlineMarkdown(cell)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>,
    );

    tableBuffer = [];
  };

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    const codeFenceMatch = /^```([a-zA-Z0-9_-]*)\s*$/.exec(trimmed);

    if (codeFenceMatch) {
      flushTable(`table-before-fence-${index}`);

      if (!inCodeBlock) {
        inCodeBlock = true;
        codeLanguage = codeFenceMatch[1] || "";
        codeLines = [];
      } else {
        rows.push(
          <div key={`code-${index}`} className="my-2">
            <CodeBlock language={codeLanguage || undefined} code={codeLines.join("\n")} />
          </div>,
        );
        inCodeBlock = false;
        codeLanguage = "";
        codeLines = [];
      }
      return;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      return;
    }

    if (trimmed.includes("|")) {
      tableBuffer.push(line);
      return;
    }

    if (tableBuffer.length > 0) {
      flushTable(`table-${index}`);
    }

    if (!trimmed) {
      rows.push(<div key={`empty-${index}`} className="h-2" />);
      return;
    }

    const headingMatch = /^(#{1,6})\s+(.*)$/.exec(line);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const headingClassName =
        {
          1: "text-2xl font-semibold",
          2: "text-xl font-semibold",
          3: "text-lg font-semibold",
          4: "text-base font-semibold",
          5: "text-sm font-semibold",
          6: "text-sm font-medium",
        }[level] ?? "text-base font-semibold";

      rows.push(
        <div key={`heading-${index}`} className={cn("mt-2", headingClassName)}>
          {renderInlineMarkdown(headingMatch[2])}
        </div>,
      );
      return;
    }

    const quoteMatch = /^>\s?(.*)$/.exec(line);
    if (quoteMatch) {
      rows.push(
        <blockquote key={`quote-${index}`} className="border-l-4 border-border pl-4 italic text-primary/70">
          {renderInlineMarkdown(quoteMatch[1])}
        </blockquote>,
      );
      return;
    }

    const taskListMatch = /^\s*[-*+]\s+\[([ xX])\]\s+(.*)$/.exec(line);
    if (taskListMatch) {
      const checked = taskListMatch[1].toLowerCase() === "x";
      rows.push(
        <div key={`task-${index}`} className="flex items-start gap-2 pl-2">
          <span className="mt-[0.1rem] text-sm">{checked ? "☑" : "☐"}</span>
          <span className={cn(checked && "text-muted-foreground line-through")}>
            {renderInlineMarkdown(taskListMatch[2])}
          </span>
        </div>,
      );
      return;
    }

    const unorderedListMatch = /^\s*[-*+]\s+(.*)$/.exec(line);
    if (unorderedListMatch) {
      rows.push(
        <div key={`ul-${index}`} className="flex items-start gap-2 pl-2">
          <span className="mt-[0.4rem] text-xs">•</span>
          <span>{renderInlineMarkdown(unorderedListMatch[1])}</span>
        </div>,
      );
      return;
    }

    const orderedListMatch = /^\s*([0-9]+)\.\s+(.*)$/.exec(line);
    if (orderedListMatch) {
      rows.push(
        <div key={`ol-${index}`} className="flex items-start gap-2 pl-2">
          <span className="min-w-5 text-sm text-muted-foreground">{orderedListMatch[1]}.</span>
          <span>{renderInlineMarkdown(orderedListMatch[2])}</span>
        </div>,
      );
      return;
    }

    rows.push(
      <p key={`p-${index}`} className="m-0 whitespace-pre-wrap break-words text-sm leading-relaxed">
        {renderInlineMarkdown(line)}
      </p>,
    );
  });

  if (tableBuffer.length > 0) {
    flushTable("table-final");
  }

  if (inCodeBlock) {
    rows.push(
      <div key="code-open-final" className="my-2">
        <CodeBlock
          language={codeLanguage || undefined}
          code={codeLines.join("\n")}
          plain={openFencePlain}
        />
      </div>,
    );
  }

  return rows;
}

/** Minimum lines kept in the re-parsed tail so short paragraphs don't thrash. */
const STREAMING_TAIL_MIN_LINES = 3;

/**
 * Incremental streaming renderer: content is split at the last blank line
 * outside a code fence into a stable prefix and an active tail. The stable
 * subtree is memoized as an element (same reference → React skips its
 * reconciliation entirely), so each token only re-parses the tail — the old
 * implementation re-parsed every line of the whole message per token (O(n²)).
 */
function StreamingMarkdownContent({ content }: { content: string }) {
  const { stableContent, tailContent, stableKey } = useMemo(() => {
    const lines = content.split(/\r?\n/);
    let inCode = false;
    let boundaryIdx = -1;
    for (let i = 0; i < lines.length - 1; i++) {
      const trimmed = lines[i].trim();
      if (/^```/.test(trimmed)) {
        inCode = !inCode;
        continue;
      }
      if (!inCode && trimmed === "") boundaryIdx = i;
    }
    if (boundaryIdx >= 0 && lines.length - 1 - boundaryIdx >= STREAMING_TAIL_MIN_LINES) {
      return {
        stableContent: lines.slice(0, boundaryIdx + 1).join("\n"),
        tailContent: lines.slice(boundaryIdx + 1).join("\n"),
        stableKey: `${boundaryIdx}-${lines.length}`,
      };
    }
    return { stableContent: "", tailContent: content, stableKey: "none" };
  }, [content]);

  const stableRows = useMemo(
    () => (stableContent ? <>{parseMarkdownRows(stableContent, false)}</> : null),
    // Recompute only when the boundary moves; content before it is immutable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stableKey],
  );

  const tailRows = useMemo(
    () => parseMarkdownRows(tailContent, true),
    [tailContent],
  );

  return (
    <div className="space-y-3">
      {stableRows}
      {tailRows}
    </div>
  );
}

/**
 * 消息里的内嵌 HTML 白名单（在默认 schema 上扩展）。
 *
 * rehype-raw 是必要的（LLM/技能文档会直出 <br>、截图 <img> 等），但它不做
 * 任何过滤：不加这一层，<iframe>/<style>/<form> 会原样进 DOM。
 *
 * 为什么不能直接用默认 schema：它按 GitHub 标签集来，不认 mark/abbr，还会
 * 剥掉 className（code 上的 language-xxx 没了 → 代码块语言识别失效）。
 *
 * 为什么必须显式写 strip：hast-util-sanitize 对不在 tagNames 的标签是「拆
 * 外壳、留子节点」——<style> 的 CSS 文本、<form>/<button> 里的文字会当正文
 * 显示出来；只有列进 strip 的标签才整棵子树丢弃。
 * 注意 strip 只对**不在 tagNames** 的标签生效，所以要从默认 schema 里额外
 * 摘掉 input（默认为了 GFM 任务清单放行 <input type=checkbox>）。
 * 未列入 attributes 的属性（含全部 on* 事件处理器与 style）由白名单机制
 * 自动丢弃；src/href 仍走默认 protocols 限制（javascript: 等协议被拦）。
 */
const MARKDOWN_SANITIZE_SCHEMA: SanitizeSchema = {
  ...defaultSchema,
  strip: [
    ...(defaultSchema.strip ?? ["script"]),
    "style",
    "iframe",
    "object",
    "embed",
    "form",
    "input",
    "button",
    "link",
    "meta",
    "base",
  ],
  tagNames: [
    ...(defaultSchema.tagNames ?? []).filter((name) => name !== "input"),
    // 默认 schema 没有的两个行内标签（LLM 输出里常见）
    "mark",
    "abbr",
  ],
  attributes: {
    ...defaultSchema.attributes,
    // 语言类名（language-xxx）与高亮类名：markdownComponents.code 靠它取语言
    code: ["className"],
    pre: ["className"],
    div: ["className"],
    span: ["className"],
    // 截图/插图：src 只放行相对路径与 http(s)（默认 protocols），javascript: 拦掉
    img: ["src", "alt", "title", "width", "height"],
  },
};

const markdownComponents = {
  code({
    className,
    children,
    ...props
  }: {
    className?: string;
    children?: React.ReactNode;
  }) {
    const match = /language-(\w+)/.exec(className || "");
    const code = String(children).replace(/\n$/, "");
    const isBlockCode = Boolean(match) || code.includes("\n");

    return isBlockCode ? (
      <CodeBlock language={match?.[1]} code={code} />
    ) : (
      <code className="rounded-sm bg-muted px-1 py-0.5 font-mono text-[0.9em]" {...props}>
        {children}
      </code>
    );
  },
  pre({ children }: { children?: React.ReactNode }) {
    return <>{children}</>;
  },
  a({ href, children }: { href?: string; children?: React.ReactNode }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary no-underline hover:underline">
        {children}
      </a>
    );
  },
  blockquote({ children }: { children?: React.ReactNode }) {
    return (
      <blockquote className="my-4 border-l-4 border-border pl-4 italic text-primary/50">
        {children}
      </blockquote>
    );
  },
  ul({ children }: { children?: React.ReactNode }) {
    return <ul className="my-4 pl-6 list-disc [&>li:last-child]:mb-0 [&>li]:mb-1">{children}</ul>;
  },
  ol({ children }: { children?: React.ReactNode }) {
    return <ol className="my-4 pl-6 list-decimal [&>li:last-child]:mb-0 [&>li]:mb-1">{children}</ol>;
  },
  table({ children }: { children?: React.ReactNode }) {
    return (
      <div className="my-4 overflow-x-auto">
        <table className="w-full border-collapse [&_td]:border [&_td]:border-border [&_td]:p-2 [&_th]:border [&_th]:border-border [&_th]:bg-muted [&_th]:p-2 [&_th]:text-left [&_th]:font-semibold">
          {children}
        </table>
      </div>
    );
  },
  img({ src, alt }: { src?: string | Blob; alt?: string }) {
    const srcUrl = typeof src === "string" ? src : src ? URL.createObjectURL(src) : "";
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={srcUrl} alt={alt || ""} className="my-4 max-w-full rounded-md" loading="lazy" />
    );
  },
};

/*
 * prose 的默认色板是给浅色背景用的（--tw-prose-bold/code/headings 都是 #101828），
 * 只有 prose-invert 把它们换成白。正文靠 text-inherit 夺回颜色不受影响，但
 * strong / code / h1-h6 没有工具类覆盖，漏掉 dark:prose-invert 就会在暗色下
 * 变成近黑字——所以这一条不能删。
 * 行内代码自带背景色块，插件默认的 `` 伪元素反引号是多余的，一并关掉。
 */
const PROSE_CLASS =
  "prose dark:prose-invert prose-code:before:content-none prose-code:after:content-none " +
  "min-w-0 max-w-full overflow-hidden break-words text-sm leading-relaxed text-inherit " +
  "[&_h1:first-child]:mt-0 [&_h1]:mb-4 [&_h1]:mt-6 [&_h1]:font-semibold " +
  "[&_h2:first-child]:mt-0 [&_h2]:mb-4 [&_h2]:mt-6 [&_h2]:font-semibold " +
  "[&_h3:first-child]:mt-0 [&_h3]:mb-4 [&_h3]:mt-6 [&_h3]:font-semibold " +
  "[&_h4:first-child]:mt-0 [&_h4]:mb-4 [&_h4]:mt-6 [&_h4]:font-semibold " +
  "[&_h5:first-child]:mt-0 [&_h5]:mb-4 [&_h5]:mt-6 [&_h5]:font-semibold " +
  "[&_h6:first-child]:mt-0 [&_h6]:mb-4 [&_h6]:mt-6 [&_h6]:font-semibold " +
  "[&_p:last-child]:mb-0 [&_p]:mb-4";

export const MarkdownContent = React.memo<MarkdownContentProps>(
  ({ content, className = "", streaming = false }) => {
    const containerClassName = useMemo(
      () => cn(PROSE_CLASS, className),
      [className],
    );
    // 本地路径图片（E:\…、workspace/…）先改写成 /files 端点 URL：必须在
    // ReactMarkdown/sanitize 之前做——rehype-sanitize 的协议白名单会把
    // "E:" 当非法 scheme 剥掉 src，事后改写就晚了。
    const processed = useMemo(() => rewriteLocalImages(content), [content]);

    if (streaming) {
      return (
        <div className={containerClassName}>
          <StreamingMarkdownContent content={processed} />
        </div>
      );
    }

    return (
      <div className={containerClassName}>
        {/* 顺序不能反：raw 先解析内嵌 HTML，sanitize 必须在其后清洗整棵树 */}
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          rehypePlugins={[rehypeRaw, [rehypeSanitize, MARKDOWN_SANITIZE_SCHEMA]]}
          components={markdownComponents}
        >
          {processed}
        </ReactMarkdown>
      </div>
    );
  },
);

MarkdownContent.displayName = "MarkdownContent";
