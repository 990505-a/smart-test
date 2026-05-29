"use client";

import { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import type { StandaloneConfig } from "@/lib/config";

interface ConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (config: StandaloneConfig) => void;
  initialConfig?: StandaloneConfig | null;
}

export function ConfigDialog({
  open,
  onOpenChange,
  onSave,
  initialConfig,
}: ConfigDialogProps) {
  const [deploymentUrl, setDeploymentUrl] = useState(
    initialConfig?.deploymentUrl || "",
  );
  const [assistantId, setAssistantId] = useState(
    initialConfig?.assistantId || "",
  );
  const [langsmithApiKey, setLangsmithApiKey] = useState(
    initialConfig?.langsmithApiKey || "",
  );
  const [enablePdfMultimodal, setEnablePdfMultimodal] = useState(
    initialConfig?.enablePdfMultimodal ?? true,
  );
  const [fastapiUrl, setFastapiUrl] = useState(
    initialConfig?.fastapiUrl || "",
  );

  useEffect(() => {
    if (open && initialConfig) {
      setDeploymentUrl(initialConfig.deploymentUrl || "");
      setAssistantId(initialConfig.assistantId || "");
      setLangsmithApiKey(initialConfig.langsmithApiKey || "");
      setEnablePdfMultimodal(initialConfig.enablePdfMultimodal ?? true);
      setFastapiUrl(initialConfig.fastapiUrl || "");
    }
  }, [open, initialConfig]);

  const handleSave = () => {
    if (!deploymentUrl || !assistantId) {
      alert("请填写所有必填字段");
      return;
    }

    onSave({
      deploymentUrl,
      assistantId,
      langsmithApiKey: langsmithApiKey || undefined,
      enablePdfMultimodal,
      fastapiUrl: fastapiUrl || "http://localhost:8000",
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[525px]">
        <DialogHeader>
          <DialogTitle>配置</DialogTitle>
          <DialogDescription>
            配置您的智能体部署设置。这些设置将保存在浏览器的本地存储中。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="deploymentUrl">部署 URL</Label>
            <Input
              id="deploymentUrl"
              placeholder="http://localhost:2026"
              value={deploymentUrl}
              onChange={(e) => setDeploymentUrl(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="assistantId">助手 ID</Label>
            <Input
              id="assistantId"
              placeholder="testcase_agent"
              value={assistantId}
              onChange={(e) => setAssistantId(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="langsmithApiKey">
              API Key <span className="text-muted-foreground">(可选)</span>
            </Label>
            <Input
              id="langsmithApiKey"
              type="password"
              placeholder="可选"
              value={langsmithApiKey}
              onChange={(e) => setLangsmithApiKey(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="fastapiUrl">
              FastAPI URL
            </Label>
            <Input
              id="fastapiUrl"
              placeholder="http://localhost:8000"
              value={fastapiUrl}
              onChange={(e) => setFastapiUrl(e.target.value)}
            />
          </div>
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-0.5">
              <Label htmlFor="multimodal">多模态模式</Label>
              <p className="text-sm text-muted-foreground">
                启用后支持解析图片和PDF中的图片内容（使用 GPT-4o）
              </p>
            </div>
            <Switch
              id="multimodal"
              checked={enablePdfMultimodal}
              onCheckedChange={setEnablePdfMultimodal}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleSave}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
