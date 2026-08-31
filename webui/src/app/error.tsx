"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[app error boundary]", error);
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6 text-foreground">
      <div className="w-full max-w-md rounded-xl border bg-card p-6 text-center shadow-sm">
        <h1 className="text-lg font-semibold">页面出现错误</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          操作未能完成，请重试。若问题持续，请刷新页面。
        </p>
        <Button className="mt-5" onClick={reset}>
          重试
        </Button>
      </div>
    </main>
  );
}
