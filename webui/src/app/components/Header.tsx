"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import {
  FolderKanban,
  FolderTree,
  FileText,
  PlayCircle,
  Sun,
  Moon,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/projects", label: "项目列表", icon: FolderKanban },
  { href: "/folders", label: "文件夹", icon: FolderTree },
  { href: "/cases", label: "测试用例", icon: FileText },
  { href: "/runs", label: "测试执行", icon: PlayCircle },
] as const;

function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
    >
      <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
      <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
    </Button>
  );
}

interface HeaderProps {
  children?: React.ReactNode; // Right-side actions slot (chat-specific: agent tabs, workspace, settings, etc.)
}

export function Header({ children }: HeaderProps) {
  const pathname = usePathname();

  return (
    <header className="flex h-14 items-center justify-between border-b px-4">
      {/* Left: Title + Navigation */}
      <div className="flex items-center gap-4">
        <h1 className="text-lg font-semibold">智能测试平台</h1>
        <nav className="hidden items-center gap-1 md:flex">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const isActive =
              pathname === href || pathname.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition-colors hover:bg-accent ${
                  isActive ? "bg-accent font-medium" : "text-muted-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Center: Chat-specific controls */}
      {children && <div className="flex items-center gap-3">{children}</div>}

      {/* Right: Theme toggle */}
      <div className="flex items-center gap-2">
        <ThemeToggle />
      </div>
    </header>
  );
}
