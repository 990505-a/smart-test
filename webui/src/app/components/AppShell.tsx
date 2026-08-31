"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  ListChecks,
  MessageSquare,
  Brain,
  Wand2,
  Gamepad2,
  Settings,
  LogOut,
  Braces,
  Plug,
  BookOpen,
  Network,
  FlaskConical,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  UserRound,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { RequireAuth } from "@/app/components/RequireAuth";
import { useAuth } from "@/providers/AuthProvider";
import { toast } from "sonner";

const COLLAPSE_KEY = "stp-nav-collapsed";

const NAV_GROUPS = [
  {
    title: "工作台",
    items: [
      // 项目管理已合并进「测试用例」页的项目管理器（2026-08）
      { href: "/cases", label: "测试用例", icon: ListChecks },
    ],
  },
  {
    title: "自动化",
    items: [
      { href: "/api-auto", label: "接口自动化", icon: Braces },
      { href: "/ui-auto", label: "UI 自动化", icon: Gamepad2 },
    ],
  },
  {
    title: "智能与知识",
    items: [
      // 自进化已移除（2026-08 记忆系统 EverOS 化）：经验沉淀由 EverOS OME 离线进化接管
      { href: "/skills", label: "技能库", icon: Wand2 },
      { href: "/rag", label: "知识库", icon: BookOpen },
      { href: "/codebase", label: "代码图谱", icon: Network },
    ],
  },
  {
    title: "系统",
    items: [
      { href: "/mcp", label: "MCP 服务", icon: Plug },
      { href: "/memories", label: "Agent 记忆", icon: Brain },
      { href: "/settings", label: "设置", icon: Settings },
    ],
  },
] as const;

function NavRow({
  href,
  label,
  icon: Icon,
  collapsed,
  external,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  collapsed: boolean;
  external?: boolean;
}) {
  const pathname = usePathname();
  const isActive = !external && (pathname === href || pathname.startsWith(href + "/"));

  return (
    <Link
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      title={collapsed ? label : undefined}
      className={cn(
        "group relative flex h-8 items-center rounded-lg text-[13px] text-muted-foreground transition-colors duration-150",
        "hover:bg-accent hover:text-accent-foreground hover:no-underline",
        isActive && "bg-sidebar-accent font-medium text-sidebar-accent-foreground",
        collapsed ? "w-9 justify-center" : "w-full gap-2.5 px-2.5",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{label}</span>}
    </Link>
  );
}

function NavSidebar() {
  const router = useRouter();
  const { user, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const [collapsed, setCollapsed] = useState(true);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(COLLAPSE_KEY);
    // Default to the wide rail on large screens unless the user opted out.
    const wide = window.innerWidth >= 1024;
    setCollapsed(stored !== null ? stored === "1" : !wide);
    setHydrated(true);

    const onResize = () => {
      if (window.innerWidth < 1024) setCollapsed(true);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      localStorage.setItem(COLLAPSE_KEY, prev ? "0" : "1");
      return !prev;
    });
  };

  const onLogout = async () => {
    await logout();
    toast.success("已退出登录");
    router.replace("/login");
  };

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-[cubic-bezier(0.4,0,0.2,1)]",
        collapsed ? "w-14" : "w-[218px]",
      )}
    >
      {/* Brand row */}
      <div className={cn("flex h-[52px] items-center", collapsed ? "justify-center px-2" : "gap-2.5 px-3")}>
        <Link
          href="/chat"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground"
          title="智能测试平台"
        >
          <FlaskConical className="h-4 w-4" />
        </Link>
        {!collapsed && (
          <Link
            href="/chat"
            className="text-[15px] font-semibold tracking-wide no-underline hover:no-underline"
            style={{ color: "inherit" }}
          >
            智能测试平台
          </Link>
        )}
      </div>

      {/* Chat entry — the primary surface, kept above the groups */}
      <div className={cn("pb-2", collapsed ? "px-2" : "px-2.5")}>
        <NavRow href="/chat" label="AI 对话" icon={MessageSquare} collapsed={collapsed} />
      </div>

      {/* Grouped navigation */}
      <nav className={cn("flex-1 space-y-4 overflow-y-auto pb-3", collapsed ? "px-2" : "px-2.5")}>
        {NAV_GROUPS.map((group) => (
          <div key={group.title} className="space-y-0.5">
            {!collapsed && (
              <div className="px-2.5 pb-1 text-[11px] leading-4 text-muted-foreground/80">
                {group.title}
              </div>
            )}
            {collapsed && <div className="mx-auto mb-1 h-px w-6 bg-sidebar-border" />}
            {group.items.map((item) => (
              <NavRow key={item.href} {...item} collapsed={collapsed} />
            ))}
          </div>
        ))}
      </nav>

      {/* Footer: collapse + theme + user */}
      <div className={cn("space-y-1 border-t border-sidebar-border pt-2", collapsed ? "px-2 pb-3" : "px-2.5 pb-3")}>
        <div className={cn("flex", collapsed ? "flex-col items-center gap-1" : "items-center gap-1")}>
          <button
            onClick={toggleCollapsed}
            title={collapsed ? "展开导航" : "收起导航"}
            className="flex h-8 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title="切换主题"
            className="relative flex h-8 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
          >
            <Sun className="h-4 w-4 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
          </button>
        </div>

        {hydrated && (
          <div
            className={cn(
              "flex items-center rounded-lg text-[13px] text-muted-foreground",
              collapsed ? "h-9 justify-center" : "h-9 gap-2 px-2",
            )}
            title={user?.display_name || user?.username || ""}
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-secondary">
              <UserRound className="h-3.5 w-3.5" />
            </span>
            {!collapsed && (
              <span className="flex-1 truncate">{user?.display_name || user?.username || "未登录"}</span>
            )}
            {!collapsed && (
              <button
                onClick={onLogout}
                title="退出登录"
                className="text-muted-foreground transition-colors hover:text-destructive"
              >
                <LogOut className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
        {collapsed && hydrated && (
          <button
            onClick={onLogout}
            title="退出登录"
            className="flex h-8 w-9 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
          >
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </div>
    </aside>
  );
}

/**
 * Unified application shell: one collapsible navigation rail for every page
 * (chat and management alike), replacing the old split Header/ManagementLayout
 * navigation. The login page renders bare.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  if (pathname === "/login") {
    return <>{children}</>;
  }

  return (
    <RequireAuth>
      <div className="flex h-dvh overflow-hidden">
        <NavSidebar />
        <main className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</main>
      </div>
    </RequireAuth>
  );
}
