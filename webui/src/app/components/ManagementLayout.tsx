"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FolderKanban, FolderTree, FileText, PlayCircle, Webhook, GitBranch, MessageSquare, Code2, Globe, FileSearch, Brain } from "lucide-react";
import { cn } from "@/lib/utils";
import { Separator } from "@/components/ui/separator";

const NAV_ITEMS = [
  { href: "/projects", label: "项目列表", icon: FolderKanban },
  { href: "/folders", label: "文件夹", icon: FolderTree },
  { href: "/cases", label: "测试用例", icon: FileText },
  { href: "/runs", label: "测试执行", icon: PlayCircle },
  { href: "/api-tests", label: "API测试", icon: Webhook },
  { href: "/web-tests", label: "Web测试", icon: Globe },
  { href: "/scenarios", label: "测试场景", icon: GitBranch },
  { href: "/code-analysis", label: "代码分析", icon: Code2 },
  { href: "/test-reports", label: "测试报告", icon: FileSearch },
  { href: "/memories", label: "智能体记忆", icon: Brain },
] as const;

export function ManagementLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* Left sidebar */}
      <aside className="w-[200px] flex-shrink-0 border-r bg-muted/40 p-4">
        <nav className="flex flex-col gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
                  isActive && "bg-accent font-medium"
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
        <Separator className="my-4" />
        <Link
          href="/chat"
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        >
          <MessageSquare className="h-4 w-4" />
          返回聊天
        </Link>
      </aside>

      {/* Right content area */}
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  );
}
