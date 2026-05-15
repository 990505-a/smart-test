"use client";

import React from "react";
import { useSortable } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Button } from "@/components/ui/button";
import { GripVertical, ChevronRight, ChevronDown, Folder, Pencil, Trash2 } from "lucide-react";
import type { FolderTreeNode } from "@/app/types/api";

interface FolderTreeNodeItemProps {
  node: FolderTreeNode;
  depth: number;
  isExpanded: boolean;
  onToggle: () => void;
  onEdit: (node: FolderTreeNode) => void;
  onDelete: (node: FolderTreeNode) => void;
}

export function FolderTreeNodeItem({
  node,
  depth,
  isExpanded,
  onToggle,
  onEdit,
  onDelete,
}: FolderTreeNodeItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: node.id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    paddingLeft: `${depth * 20}px`,
  };

  const hasChildren = node.children && node.children.length > 0;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-1 rounded-md px-2 py-1.5 hover:bg-accent/50 group ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      {/* Drag handle */}
      <button
        className="cursor-grab text-muted-foreground hover:text-foreground"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>

      {/* Expand/collapse button */}
      <button
        className="flex h-5 w-5 items-center justify-center"
        onClick={onToggle}
        disabled={!hasChildren}
      >
        {hasChildren ? (
          isExpanded ? (
            <ChevronDown className="h-4 w-4" />
          ) : (
            <ChevronRight className="h-4 w-4" />
          )
        ) : (
          <span className="w-4" />
        )}
      </button>

      {/* Folder icon */}
      <Folder className="h-4 w-4 text-muted-foreground" />

      {/* Folder name */}
      <span className="text-sm">{node.name}</span>

      {/* Action buttons (visible on hover) */}
      <div className="ml-auto flex gap-0.5 opacity-0 group-hover:opacity-100">
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={(e) => {
            e.stopPropagation();
            onEdit(node);
          }}
        >
          <Pencil className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(node);
          }}
        >
          <Trash2 className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
}
