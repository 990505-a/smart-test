"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/providers/AuthProvider";
import { getConfig, saveConfig, DEFAULT_FASTAPI_URL } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { FlaskConical } from "lucide-react";

export default function LoginPage() {
  const { login, user } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showServer, setShowServer] = useState(false);
  const [fastapiUrl, setFastapiUrl] = useState(
    () => getConfig()?.fastapiUrl || DEFAULT_FASTAPI_URL
  );

  React.useEffect(() => {
    if (user) router.replace("/chat");
  }, [user, router]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      toast.error("请输入用户名和密码");
      return;
    }
    setSubmitting(true);
    try {
      await login(username, password);
      toast.success("登录成功");
      router.replace("/chat");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "登录失败";
      toast.error(
        msg === "Failed to fetch"
          ? `无法连接后端服务（${fastapiUrl}），请确认 FastAPI 已启动，或点击下方「服务器设置」修改地址`
          : msg
      );
    } finally {
      setSubmitting(false);
    }
  };

  const saveServerUrl = () => {
    // 只覆盖 fastapiUrl；deploymentUrl 等已有覆盖保持不变
    saveConfig({
      ...getConfig(),
      fastapiUrl: fastapiUrl.trim().replace(/\/$/, ""),
    });
    toast.success("服务器地址已保存，请重试登录");
    setShowServer(false);
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-muted/40">
      <div className="w-full max-w-sm rounded-xl border bg-background p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-7 w-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <FlaskConical className="h-4 w-4" />
          </div>
          <h1 className="text-2xl font-semibold">智能测试平台</h1>
          <p className="mt-1 text-sm text-muted-foreground">游戏测试全生命周期 AI 平台</p>
        </div>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="username">用户名</Label>
            <Input
              id="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              autoComplete="username"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">密码</Label>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>
          <Button type="submit" disabled={submitting} className="mt-2 w-full">
            {submitting ? "登录中…" : "登 录"}
          </Button>
        </form>

        <div className="mt-4 text-center">
          <button
            type="button"
            onClick={() => setShowServer(!showServer)}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            服务器设置（{fastapiUrl}）
          </button>
          {showServer && (
            <div className="mt-2 flex gap-2">
              <Input
                value={fastapiUrl}
                onChange={(e) => setFastapiUrl(e.target.value)}
                placeholder={DEFAULT_FASTAPI_URL}
                className="h-8 text-xs"
              />
              <Button size="sm" variant="outline" onClick={saveServerUrl} className="shrink-0">
                保存
              </Button>
            </div>
          )}
        </div>

        <p className="mt-4 text-center text-xs text-muted-foreground">
          首次启动默认账号 admin / admin123，登录后请在设置页修改密码
        </p>
      </div>
    </div>
  );
}
