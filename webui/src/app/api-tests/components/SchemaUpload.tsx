"use client";

import { useState, useCallback, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Upload, CheckCircle, AlertCircle } from "lucide-react";
import { uploadSchemaFile } from "@/lib/api/useApiTests";

interface SchemaUploadProps {
  projectId: string;
}

export function SchemaUpload({ projectId }: SchemaUploadProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;

      // Validate file type
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (!ext || !["json", "yaml", "yml"].includes(ext)) {
        setResult({
          success: false,
          message: "仅支持 .json, .yaml, .yml 格式的文件",
        });
        return;
      }

      setUploading(true);
      setResult(null);
      try {
        await uploadSchemaFile(projectId, file);
        setResult({
          success: true,
          message: `文件 "${file.name}" 上传成功`,
        });
      } catch (err) {
        setResult({
          success: false,
          message: `上传失败: ${err instanceof Error ? err.message : "未知错误"}`,
        });
      } finally {
        setUploading(false);
        // Reset file input
        if (fileInputRef.current) {
          fileInputRef.current.value = "";
        }
      }
    },
    [projectId],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>上传Schema文件</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            上传 OpenAPI/Swagger 规范文件（.json, .yaml, .yml），
            系统将解析并生成对应的API测试配置。
          </p>

          <div className="flex items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".json,.yaml,.yml"
              onChange={handleFileSelect}
              className="hidden"
              id="schema-file-input"
            />
            <Button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              variant="outline"
            >
              <Upload className="mr-2 h-4 w-4" />
              {uploading ? "上传中..." : "选择文件"}
            </Button>
            <span className="text-xs text-muted-foreground">
              支持 .json, .yaml, .yml
            </span>
          </div>

          {result && (
            <div
              className={`flex items-center gap-2 rounded-md p-3 text-sm ${
                result.success
                  ? "bg-green-50 text-green-800"
                  : "bg-red-50 text-red-800"
              }`}
            >
              {result.success ? (
                <CheckCircle className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4" />
              )}
              {result.message}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
