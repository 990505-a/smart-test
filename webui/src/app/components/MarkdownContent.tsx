"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

interface MarkdownContentProps {
  content: string;
  className?: string;
  streaming?: boolean;
}

function CodeBlock({
  language,
  code,
}: {
  language?: string;
  code: string;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [SyntaxHighlighterComponent, setSyntaxHighlighterComponent] = useState<any>(null);
  const [syntaxStyle, setSyntaxStyle] = useState<any>(null);

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
    if (!isVisible || !language || SyntaxHighlighterComponent) return;

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
  }, [SyntaxHighlighterComponent, isVisible, language]);

  const fallback = (
    <pre className="m-0 overflow-x-auto whitespace-pre-wrap break-all rounded-md bg-[#282c34] p-4 font-mono text-sm leading-6 text-white">
      {code}
    </pre>
  );

  return (
    <div ref={containerRef} className="my-4 max-w-full overflow-hidden last:mb-0">
      {language && SyntaxHighlighterComponent && syntaxStyle ? (
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

function StreamingMarkdownContent({ content }: { content: string }) {
  const lines = useMemo(() => content.split(/\r?\n/), [content]);

  const renderedRows = useMemo(() => {
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
          <CodeBlock language={codeLanguage || undefined} code={codeLines.join("\n")} />
        </div>,
      );
    }

    return rows;
  }, [lines]);

  return <div className="space-y-3">{renderedRows}</div>;
}

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
    return <ul className="my-4 pl-6 [&>li:last-child]:mb-0 [&>li]:mb-1">{children}</ul>;
  },
  ol({ children }: { children?: React.ReactNode }) {
    return <ol className="my-4 pl-6 [&>li:last-child]:mb-0 [&>li]:mb-1">{children}</ol>;
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

const PROSE_CLASS =
  "prose min-w-0 max-w-full overflow-hidden break-words text-sm leading-relaxed text-inherit " +
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

    if (streaming) {
      return (
        <div className={containerClassName}>
          <StreamingMarkdownContent content={content} />
        </div>
      );
    }

    return (
      <div className={containerClassName}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {content}
        </ReactMarkdown>
      </div>
    );
  },
);

MarkdownContent.displayName = "MarkdownContent";
