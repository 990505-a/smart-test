"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { WORKSPACES, WorkspaceId } from "@/app/types/types";
import { Building2 } from "lucide-react";

export function WorkspaceSelect({
  workspaceId,
  onWorkspaceChange,
}: {
  workspaceId: WorkspaceId;
  onWorkspaceChange: (id: WorkspaceId) => void;
}) {
  return (
    <Select value={workspaceId} onValueChange={(v) => { if (v !== null) onWorkspaceChange(v as WorkspaceId); }}>
      <SelectTrigger className="w-[160px] h-9">
        <Building2 className="mr-2 h-4 w-4" />
        <SelectValue placeholder="Workspace" />
      </SelectTrigger>
      <SelectContent>
        {WORKSPACES.map((ws) => (
          <SelectItem key={ws.id} value={ws.id}>
            {ws.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
