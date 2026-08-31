---
name: api-test-quality
description: Use when analyzing REST API test quality. Covers syntax validation, data type correctness (LLM-based), status code coverage (two variants: static script analysis + dynamic post-execution), method coverage analysis, and deterministic metrics aggregation.
version: 1.1.0
---

# API Test Quality Analysis

## Overview

After generating and executing test scripts, measure quality.
This skill covers both **deterministic tool calls** and **LLM-based
analysis** that the orchestrator performs inline.

---

## 1. Syntax Correctness

Run `check_script_syntax` on every generated script.
Track results across all scripts to compute the **overall ratio**
(MASTEST formula 1):

```
SyntaxCorrectness = count(valid scripts) / count(total scripts) × 100%
```

If errors are reported, fix the script and re-check.
For deeper validation: `execute` → `npx tsc --noEmit <file>`.

---

## 2. Data Type Correctness  (LLM-based)

For each test script, analyze parameter types against the API spec.
Only consider parameters **explicitly required by the scenario**.

**Special cases:**
- Scenario requires no parameters AND script has none → `"total": 0, "coverage_percent": 100`.
- Script sends extra parameters not required by the scenario → count as mismatches.
- Parameter present but wrong type → mismatch (value correctness is secondary).
- Parameter required but missing → mismatch.

**Output this exact JSON per endpoint:**

```json
{
  "coverage": 87.5,
  "detail": {
    "POST /pet": {
      "matched": 3,
      "total": 4,
      "coverage_percent": 75.0,
      "mismatches": [
        {"parameter": "status", "expected_type": "string", "actual_type": "number"}
      ]
    }
  }
}
```

Aggregate overall coverage as: `sum(matched) / sum(total) × 100`.
Do NOT average per-endpoint percentages.

---

## 3. Status Code Coverage  (LLM-based, two approaches)

### 3a. Static — by script analysis

After generating a script but **before execution**, analyze which
status codes are asserted. Use this JSON format:

```json
{
  "coverage": 66.67,
  "detail": {
    "GET /pet/findByStatus": {
      "expected": ["200", "400"],
      "used_in_script": ["200"],
      "coverage_percent": 50.0
    }
  }
}
```

- Only include status codes defined in the spec AND required by the scenario.
- Ignore codes asserted in the script that aren't in the spec.
- Overall coverage: `sum(used) / sum(expected) × 100` — NOT an average.

### 3b. Dynamic — by execution results

After execution, compare actual response codes against expected:

```json
{
  "coverage": 75.0,
  "detail": {
    "GET /pet/findByStatus": {
      "expected": ["200", "400"],
      "covered_after_execution": ["200", "400"],
      "coverage_percent": 100.0
    }
  }
}
```

- Only count codes that both appear in the spec AND were returned.
- Report both approaches in the final summary to show pre- and post-execution coverage.

---

## 4. Method / Operation Coverage

Use `compute_coverage` (deterministic) rather than manual LLM analysis.
Pass `tested_operation_ids_json` with the operationIds that appear in test scripts.
The tool applies formula (7): `|Ops(T)| / |Ops(api)| × 100%`.

---

## 5. Deterministic Metrics Aggregation

Call `compute_coverage` as a single call collecting all deterministic formulas:

| Parameter | Value |
|-----------|-------|
| `parsed_api_json` | Output from `parse_openapi_spec` |
| `generated_scenarios_json` | `[...]` LLM-generated scenario names |
| `accepted_scenarios_json` | `[...]` scenarios after review (exclude rejected) |
| `tested_operation_ids_json` | `[...]` operationIds covered by scripts |
| `original_script` | Raw LLM output (optional, for usability) |
| `final_script` | Edited version (optional, for usability) |

Returns `scenario_coverage` (formulas 4-5), `operation_coverage` (formula 7),
and `usability` (formula 3, Levenshtein).

---

## 6. Bug Detection

Flag any of these as bugs:

1. **Functional errors** — API returns 5xx on valid input.
2. **Spec inconsistencies** — Response body missing required fields, wrong types.
3. **Undefined status codes** — Code returned but not listed in spec.
4. **Assertion failures** — Any `expect()` that fails during execution.

Report format per bug:
```
[{endpoint}] {scenario_name}: expected {expected}, got {actual} — {detail}
```

---

## 7. Final Report Template

```
## Test Results: {api_title} v{api_version}

| Metric | Value |
|--------|-------|
| Total operations | {n} |
| Unit test scenarios generated | {n} |
| System test scenarios generated | {n} |
| Scripts produced | {n} |
| **Syntax correctness** | {pct}%  ({valid}/{total}) |
| **Data type correctness** | {pct}%  ({matched}/{total} params) |
| **Status code coverage (script)** | {pct}% |
| **Status code coverage (execution)** | {pct}% |
| **Operation coverage** | {pct}%  ({tested}/{total}) |
| **Scenario coverage** | {pct}%  ({accepted}/{total}) |
| **Usability** (avg edit distance) | {dist} chars, {pct}% similarity |

### Bugs Found (if any)
[List each bug with endpoint, scenario, expected vs actual]
```
