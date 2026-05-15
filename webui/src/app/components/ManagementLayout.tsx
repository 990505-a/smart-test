"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FolderKanban,
  FolderTree,
  FileText,
  PlayCircle,
  MessageSquare,
} from "lucide-react";

const SIDEBAR_ITEMS = [
  { href: "/projects", label: "项目列表", icon: FolderKanban },
  { href: "/folders", label: "文件夹", icon: FolderTree },
  { href: "/cases", label: "测试用例", icon: FileText },
  { href: "/runs", label: "测试执行", icon: PlayCircle },
] as const;

export function ManagementLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      {/* Left sidebar */}
      <aside className="w-[200px] flex-shrink-0 border-r bg-muted/40 p-4">
        <nav className="flex flex-col gap-1">
          {SIDEBAR_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive =
              pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors hover:bg-accent ${
                  isActive
                    ? "bg-accent font-medium"
                    : "text-muted-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="my-4 border-t" />

        <Link
          href="/chat"
          className="flex items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent"
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
