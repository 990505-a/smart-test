"use client";

import React, { useState, useCallback } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { FolderTreeNodeItem } from "./FolderTreeNodeItem";
import type { FolderTreeNode } from "@/app/types/api";

interface FolderTreeProps {
  nodes: FolderTreeNode[];
  onEdit: (node: FolderTreeNode) => void;
  onDelete: (node: FolderTreeNode) => void;
  onReorder: (id: string, newParentId: string | null, newIndex: number) => void;
}

function FolderTreeLevel({
  nodes,
  parentId,
  depth,
  expandedIds,
  toggleExpand,
  onEdit,
  onDelete,
  onReorder,
}: {
  nodes: FolderTreeNode[];
  parentId: string | null;
  depth: number;
  expandedIds: Set<string>;
  toggleExpand: (id: string) => void;
  onEdit: (node: FolderTreeNode) => void;
  onDelete: (node: FolderTreeNode) => void;
  onReorder: (id: string, newParentId: string | null, newIndex: number) => void;
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor)
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;
      if (!over || active.id === over.id) return;

      const oldIndex = nodes.findIndex((n) => n.id === active.id);
      const newIndex = nodes.findIndex((n) => n.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;

      // Call reorder with the moved item's new position
      onReorder(String(active.id), parentId, newIndex);
    },
    [nodes, parentId, onReorder]
  );

  const itemIds = nodes.map((n) => n.id);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={itemIds} strategy={verticalListSortingStrategy}>
        <div className="space-y-0.5">
          {nodes.map((node) => (
            <React.Fragment key={node.id}>
              <FolderTreeNodeItem
                node={node}
                depth={depth}
                isExpanded={expandedIds.has(node.id)}
                onToggle={() => toggleExpand(node.id)}
                onEdit={onEdit}
                onDelete={onDelete}
              />
              {/* Render children if expanded */}
              {expandedIds.has(node.id) &&
                node.children &&
                node.children.length > 0 && (
                  <FolderTreeLevel
                    nodes={node.children}
                    parentId={node.id}
                    depth={depth + 1}
                    expandedIds={expandedIds}
                    toggleExpand={toggleExpand}
                    onEdit={onEdit}
                    onDelete={onDelete}
                    onReorder={onReorder}
                  />
                )}
            </React.Fragment>
          ))}
        </div>
      </SortableContext>
    </DndContext>
  );
}

export function FolderTree({
  nodes,
  onEdit,
  onDelete,
  onReorder,
}: FolderTreeProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  if (!nodes || nodes.length === 0) {
    return (
      <div className="py-8 text-center text-muted-foreground">
        暂无文件夹，点击新建文件夹按钮创建
      </div>
    );
  }

  return (
    <FolderTreeLevel
      nodes={nodes}
      parentId={null}
      depth={0}
      expandedIds={expandedIds}
      toggleExpand={toggleExpand}
      onEdit={onEdit}
      onDelete={onDelete}
      onReorder={onReorder}
    />
  );
}
