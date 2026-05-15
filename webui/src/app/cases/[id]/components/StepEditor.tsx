"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Trash2, Plus, GripVertical } from "lucide-react";

interface Step {
  step_number: number;
  action: string;
  expected_result: string;
}

interface StepEditorProps {
  steps: Step[];
  onChange: (steps: Step[]) => void;
}

export function StepEditor({ steps, onChange }: StepEditorProps) {
  const handleAddStep = useCallback(() => {
    const newStep: Step = {
      step_number: steps.length + 1,
      action: "",
      expected_result: "",
    };
    onChange([...steps, newStep]);
  }, [steps, onChange]);

  const handleRemoveStep = useCallback(
    (index: number) => {
      const newSteps = steps.filter((_, i) => i !== index);
      // Re-number steps
      newSteps.forEach((s, i) => {
        s.step_number = i + 1;
      });
      onChange(newSteps);
    },
    [steps, onChange]
  );

  const handleUpdateStep = useCallback(
    (index: number, field: "action" | "expected_result", value: string) => {
      const newSteps = [...steps];
      newSteps[index] = { ...newSteps[index], [field]: value };
      onChange(newSteps);
    },
    [steps, onChange]
  );

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[auto_1fr_1fr_auto] gap-2 text-sm font-medium text-muted-foreground">
        <span className="w-8" />
        <span>操作步骤</span>
        <span>预期结果</span>
        <span className="w-8" />
      </div>

      {steps.map((step, index) => (
        <div key={index} className="grid grid-cols-[auto_1fr_1fr_auto] gap-2 items-center">
          <div className="flex items-center gap-1 w-8">
            <GripVertical className="h-4 w-4 text-muted-foreground cursor-grab" />
            <span className="text-sm text-muted-foreground">{step.step_number}</span>
          </div>
          <Input
            placeholder="操作步骤"
            value={step.action}
            onChange={(e) => handleUpdateStep(index, "action", e.target.value)}
          />
          <Input
            placeholder="预期结果"
            value={step.expected_result}
            onChange={(e) => handleUpdateStep(index, "expected_result", e.target.value)}
          />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={() => handleRemoveStep(index)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      ))}

      <Button variant="outline" size="sm" onClick={handleAddStep} className="w-full">
        <Plus className="mr-2 h-4 w-4" />
        添加步骤
      </Button>
    </div>
  );
}
