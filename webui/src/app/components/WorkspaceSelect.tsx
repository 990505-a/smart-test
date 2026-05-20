"use client";

import { useState } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Building2, Plus, Trash2 } from "lucide-react";
import { WorkspaceId } from "@/app/types/types";
import { useWorkspaces, useCreateWorkspace, useDeleteWorkspace } from "@/lib/api/useWorkspaces";

export function WorkspaceSelect({
  workspaceId,
  onWorkspaceChange,
}: {
  workspaceId: WorkspaceId;
  onWorkspaceChange: (id: WorkspaceId) => void;
}) {
  const { data } = useWorkspaces();
  const { trigger: createWorkspace, isMutating: isCreating } = useCreateWorkspace();
  const { trigger: deleteWorkspace, isMutating: isDeleting } = useDeleteWorkspace();
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");

  const workspaces = data?.data ?? [];
  const currentWorkspace = workspaces.find((ws) => ws.slug === workspaceId);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    const result = await createWorkspace({ name: newName.trim() });
    setShowCreate(false);
    setNewName("");
    if (result?.data?.slug) {
      onWorkspaceChange(result.data.slug);
    }
  };

  const handleDelete = async () => {
    if (!workspaceId || workspaceId === "default") return;
    await deleteWorkspace(workspaceId);
    onWorkspaceChange("default");
  };

  return (
    <div className="flex items-center gap-1">
      <Select
        value={workspaceId}
        onValueChange={(v) => {
          if (v !== null) onWorkspaceChange(v);
        }}
      >
        <SelectTrigger className="w-[160px] h-9">
          <Building2 className="mr-2 h-4 w-4" />
          <SelectValue placeholder="Workspace" />
        </SelectTrigger>
        <SelectContent>
          {workspaces.map((ws) => (
            <SelectItem key={ws.slug} value={ws.slug}>
              {ws.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={() => setShowCreate(true)}
        title="Create workspace"
      >
        <Plus className="h-4 w-4" />
      </Button>

      {currentWorkspace && !currentWorkspace.is_default && (
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-destructive hover:text-destructive"
          onClick={handleDelete}
          disabled={isDeleting}
          title="Delete workspace"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      )}

      {showCreate && (
        <div className="flex items-center gap-1">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Workspace name"
            className="h-8 w-[140px] rounded-md border bg-background px-2 text-sm"
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
              if (e.key === "Escape") { setShowCreate(false); setNewName(""); }
            }}
            autoFocus
          />
          <Button
            variant="outline"
            size="sm"
            className="h-8"
            onClick={handleCreate}
            disabled={isCreating || !newName.trim()}
          >
            Add
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8"
            onClick={() => { setShowCreate(false); setNewName(""); }}
          >
            Cancel
          </Button>
        </div>
      )}
    </div>
  );
}
