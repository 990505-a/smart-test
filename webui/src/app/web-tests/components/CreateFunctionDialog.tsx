"use client";

import { useState, useCallback } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Plus } from "lucide-react";
import { useCreateWebFunction } from "@/lib/api/useWebFunctions";
import type { WebFunctionCreate } from "@/app/types/api";

interface CreateFunctionDialogProps {
  projectId: string;
  onSuccess?: () => void;
}

export function CreateFunctionDialog({ projectId, onSuccess }: CreateFunctionDialogProps) {
  const [open, setOpen] = useState(false);
  const { trigger: createFunction, isMutating: isCreating } = useCreateWebFunction(projectId);

  // Form fields
  const [displayName, setDisplayName] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [businessModule, setBusinessModule] = useState("");

  const handleSubmit = useCallback(async () => {
    if (!displayName.trim() || !name.trim()) return;

    const payload: WebFunctionCreate = {
      project_id: projectId,
      display_name: displayName.trim(),
      name: name.trim(),
      description: description || undefined,
      base_url: baseUrl || undefined,
      business_module: businessModule || undefined,
    };

    await createFunction(payload);
    setOpen(false);
    // Reset form
    setDisplayName("");
    setName("");
    setDescription("");
    setBaseUrl("");
    setBusinessModule("");
    onSuccess?.();
  }, [projectId, displayName, name, description, baseUrl, businessModule, createFunction, onSuccess]);

  return (
    <>
      <Button size="sm" disabled={isCreating} onClick={() => setOpen(true)}>
        <Plus className="mr-2 h-4 w-4" />
        新建功能
      </Button>

      <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>新建Web功能</DialogTitle>
          <DialogDescription>
            创建一个新的Web测试功能模块。
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-4">
          <div className="grid gap-2">
            <Label htmlFor="displayName">显示名称 *</Label>
            <Input
              id="displayName"
              placeholder="如：用户登录模块"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="funcName">功能名称 *</Label>
            <Input
              id="funcName"
              placeholder="如：user-login"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="funcDesc">描述</Label>
            <Textarea
              id="funcDesc"
              placeholder="可选描述"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="baseUrl">基础URL</Label>
            <Input
              id="baseUrl"
              placeholder="https://example.com"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="businessModule">业务模块</Label>
            <Input
              id="businessModule"
              placeholder="如：认证模块"
              value={businessModule}
              onChange={(e) => setBusinessModule(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            取消
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!displayName.trim() || !name.trim() || isCreating}
          >
            {isCreating ? "创建中..." : "创建"}
          </Button>
        </DialogFooter>
      </DialogContent>
      </Dialog>
    </>
  );
}
