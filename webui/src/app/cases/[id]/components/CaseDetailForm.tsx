"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StepEditor } from "./StepEditor";
import type { TestCaseInfo, TestCaseUpdate } from "@/app/types/api";

interface CaseDetailFormProps {
  testCase: TestCaseInfo;
  onSave: (data: TestCaseUpdate) => void;
  isSaving: boolean;
}

export function CaseDetailForm({ testCase, onSave, isSaving }: CaseDetailFormProps) {
  const [name, setName] = useState(testCase.name);
  const [description, setDescription] = useState(testCase.description || "");
  const [preconditions, setPreconditions] = useState(testCase.preconditions || "");
  const [priority, setPriority] = useState(testCase.priority);
  const [state, setState] = useState(testCase.state);
  const [template, setTemplate] = useState<"test_case" | "test_case_bdd">(testCase.template);
  const [feature, setFeature] = useState(testCase.feature || "");
  const [scenario, setScenario] = useState(testCase.scenario || "");
  const [background, setBackground] = useState(testCase.background || "");
  const [steps, setSteps] = useState(
    testCase.steps.map((s) => ({
      step_number: s.step_number,
      action: s.action,
      expected_result: s.expected_result || "",
    }))
  );

  const handleSave = useCallback(() => {
    const data: TestCaseUpdate = {
      name,
      description: description || undefined,
      preconditions: preconditions || undefined,
      priority,
      state,
      template,
      feature: template === "test_case_bdd" ? feature : undefined,
      scenario: template === "test_case_bdd" ? scenario : undefined,
      background: template === "test_case_bdd" ? background : undefined,
      steps: template === "test_case" ? steps : undefined,
    };
    onSave(data);
  }, [name, description, preconditions, priority, state, template, feature, scenario, background, steps, onSave]);

  return (
    <div className="space-y-6">
      {/* Basic info */}
      <div className="space-y-4">
        <div className="grid gap-2">
          <Label htmlFor="caseName">用例名称</Label>
          <Input
            id="caseName"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="caseDescription">描述</Label>
          <Textarea
            id="caseDescription"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="grid gap-2">
          <Label htmlFor="casePreconditions">前置条件</Label>
          <Textarea
            id="casePreconditions"
            value={preconditions}
            onChange={(e) => setPreconditions(e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="grid gap-2">
            <Label>优先级</Label>
            <Select value={priority} onValueChange={(val) => setPriority(val as typeof priority)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="low">低</SelectItem>
                <SelectItem value="medium">中</SelectItem>
                <SelectItem value="high">高</SelectItem>
                <SelectItem value="critical">严重</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-2">
            <Label>状态</Label>
            <Select value={state} onValueChange={(val) => setState(val as typeof state)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="new">新建</SelectItem>
                <SelectItem value="review_pending">待评审</SelectItem>
                <SelectItem value="reviewed">已评审</SelectItem>
                <SelectItem value="not_run">未执行</SelectItem>
                <SelectItem value="passed">通过</SelectItem>
                <SelectItem value="failed">失败</SelectItem>
                <SelectItem value="blocked">阻塞</SelectItem>
                <SelectItem value="skipped">跳过</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
      </div>

      {/* Template toggle */}
      <div className="flex items-center justify-between gap-4 rounded-md border p-4">
        <div className="space-y-0.5">
          <Label>BDD 模式</Label>
          <p className="text-sm text-muted-foreground">
            启用后切换到 BDD 模式，使用 Feature/Scenario/Background 格式
          </p>
        </div>
        <Switch
          checked={template === "test_case_bdd"}
          onCheckedChange={(checked) =>
            setTemplate(checked ? "test_case_bdd" : "test_case")
          }
        />
      </div>

      {/* Template-specific content */}
      {template === "test_case" ? (
        <div className="space-y-4">
          <h3 className="text-lg font-medium">测试步骤</h3>
          <StepEditor steps={steps} onChange={setSteps} />
        </div>
      ) : (
        <div className="space-y-4">
          <h3 className="text-lg font-medium">BDD 定义</h3>
          <div className="grid gap-2">
            <Label htmlFor="bddFeature">Feature</Label>
            <Textarea
              id="bddFeature"
              placeholder="Feature: ..."
              value={feature}
              onChange={(e) => setFeature(e.target.value)}
              rows={3}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="bddScenario">Scenario</Label>
            <Textarea
              id="bddScenario"
              placeholder="Scenario: ..."
              value={scenario}
              onChange={(e) => setScenario(e.target.value)}
              rows={4}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="bddBackground">Background</Label>
            <Textarea
              id="bddBackground"
              placeholder="Background: ..."
              value={background}
              onChange={(e) => setBackground(e.target.value)}
              rows={3}
            />
          </div>
        </div>
      )}

      {/* Save button */}
      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={isSaving}>
          {isSaving ? "保存中..." : "保存"}
        </Button>
      </div>
    </div>
  );
}
