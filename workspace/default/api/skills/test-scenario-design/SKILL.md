---
name: test-scenario-design
description: Use when designing test scenarios from an OpenAPI specification. Covers unit-level (single-operation) and system-level (cross-operation sequence) scenario generation with positive, negative, and edge-case patterns.
version: 1.0.0
---

# Test Scenario Design for RESTful APIs

## Overview

Given a parsed OpenAPI specification, produce comprehensive test scenarios in
natural language. Each scenario must describe **what** is tested, **which
parameters** are sent, and **what response** is expected. Output format:

```
N. Scenario Name: <concise descriptive name>
   Scenario Description: <detailed description including parameters and expected outcomes>
```

## Unit Test Scenarios (per operation)

For each API operation independently:

| Category   | What to test |
|------------|-------------|
| **Positive** | Valid inputs → successful response (2xx). One baseline scenario per operation. |
| **Negative** | Invalid/missing required parameters → error response (4xx). Missing auth headers, malformed bodies, wrong Content-Type. |
| **Edge**     | Boundary values (empty strings, max-length strings, 0, negative numbers, null for optional fields). Enum parameters: try every value. Query params: no params, too many params. |

**Rules:**
- Each scenario tests exactly **one** operation.
- Parameter values come from the spec's schema (type, enum, format, min/max).
- If the spec defines multiple response status codes, generate a scenario targeting each.
- Include the expected response body structure for each scenario.

## System Test Scenarios (cross-operation)

Analyze all operations together to find dependencies:

1. **Producer-consumer chains:** POST creates a resource → GET reads it by the returned ID → PUT updates it → DELETE removes it.
2. **Lookup flows:** GET a list → pick an ID → GET details.
3. **Authentication flows:** POST login → extract token → use token in subsequent calls.

| Category   | What to test |
|------------|-------------|
| **Valid sequences** | 2–4 calls forming a logical workflow. Pass extracted IDs/tokens between calls. |
| **Invalid sequences** | Wrong ordering (GET before POST), missing prerequisites (DELETE without creating first), parameter conflicts (PUT with ID from wrong resource). |
| **Mixed outcome** | First call succeeds, second fails → verify the overall behavior. |

**Rules:**
- Every scenario must have **at least 2 API calls**, at most 4.
- The description must specify the full sequence: "Call A → extract field X → call B with X as parameter → expect ..."
- Cover as many operation combinations as possible.
- Invalid scenarios must be *logically flawed*, not just syntactically invalid.

## Principles

- **One scenario at a time.** Don't combine unrelated operations.
- **Be thorough.** Happy paths and error paths both matter.
- **Use the spec as the source of truth.** Every parameter name, type, and response code comes from the parsed OpenAPI document.
- **Small is scalable.** Work operation by operation to stay within token limits.
