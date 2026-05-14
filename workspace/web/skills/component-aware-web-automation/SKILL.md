---
name: component-aware-web-automation
description: Component-aware E2E test generation via source-code static analysis — a two-phase, seven-agent pipeline that builds deterministic Playwright tests from upstream understanding.
allowed-tools: Bash(shell:*) Bash(npx:*) Bash(npm:*) Bash(node:*) Bash(git:*)
---

# Component-Aware Web Automation: The Director Architecture

## Compatibility

Requires access to application source code repository. Supports React (.tsx/.jsx), Vue (.vue SFC), Angular (.component.ts), and Svelte (.svelte) applications. Needs Playwright for test execution and Node.js for static analysis scripts.

## Architecture Overview

Two-phase, seven-agent pipeline:

- **Phase 1 (Setup)**: `script-analyst` → `stage-manager` → `blocking-coach` → `set-designer`
- **Phase 2 (Execution)**: `choreographer` → `assistant-director` → `continuity-lead`

***

## The Paradox We Solve

E2E testing is both essential and fragile. Current AI testing stays in the "DOM scraping" stage — an improvising actor guessing intent from rendered HTML. This has fundamental blind spots:

- **No business context**: The browser sees "what is rendered", not "why it exists"
- **Incomplete state coverage**: The browser shows one rendering state, missing Feature Flag and permission permutations
- **Selector-contract断裂**: Generated selectors have no link to source code — UI changes break tests

**Playwright needs a Director, not another actor.**

Our architecture **upstreams understanding** from runtime to source code itself, achieving deterministic automation through component-aware static analysis.

***

## Architecture: Two-Phase, Seven-Agent Pipeline

The system decouples "understanding the architecture" from "executing tests" into two phases, orchestrated by seven specialized AI agents.

### Phase 1: Setup the Stage — Static Analysis (Upstream)

This phase operates **on source code**, before any browser opens. It builds a structured Single Source of Truth.

#### Agent 1: Script Analyst (剧本分析师)

**Mission**: Deep-dive into source code, identify all interactive component "actors", filter noise, build component-aware Single Source of Truth.

**What it does**:
1. Scan all component files (`.tsx`, `.vue`, `.component.ts`, `.svelte`) in the repository
2. For each component, extract:
   - Component name / type
   - Props interface (names, types, defaults, required/optional)
   - State / data properties (names, types, initial values)
   - Rendered interactive elements (buttons, inputs, links, dropdowns)
   - Conditional rendering logic (v-if, conditional props, Feature Flag guards)
   - Event handlers and their business semantics
3. Build a **Component Registry** — the Single Source of Truth mapping component identity to its semantic contract

**Output**: `component-registry.json` — structured catalog of all components with their semantic properties

See [references/script-analyst-guide.md](references/script-analyst-guide.md) for detailed extraction patterns per framework.

#### Agent 2: Stage Manager (舞台经理)

**Mission**: Ensure every interactive element has a "blocking mark" (定位标识). If source code lacks them, auto-inject context-aware `data-testid`.

**What it does**:
1. Read the Component Registry from Agent 1
2. For each interactive element, check if it already has stable identifiers:
   - `data-testid` attribute
   - `aria-label` or accessible name
   - Unique semantic role + name combination
3. If missing, **generate and inject** a context-aware `data-testid` following the pattern:
   ```
   {componentName}-{elementRole}-{semanticDescriptor}
   Examples:
   LoginForm-input-email
   LoginForm-button-submit
   UserTable-button-deleteRow
   NavMenu-link-dashboard
   ```
4. Create a patch/diff for each file that needs injection
5. The injection is **upstream** — it improves the source code, making ALL future tests benefit

**Output**: `testid-injections.json` — list of injected identifiers + source code patches

See [references/stage-manager-guide.md](references/stage-manager-guide.md) for injection patterns and naming conventions.

#### Agent 3: Blocking Coach (调度教练)

**Mission**: Pre-determine the most effective locator path for every element, generate a prioritized locator catalog. Tests never need to "grope for paths" at runtime.

**What it does**:
1. Combine Component Registry + testid injections
2. For every interactive element, generate a **locator priority chain**:
   ```
   Priority 1: data-testid (if injected or pre-existing) — deterministic, survives refactoring
   Priority 2: Semantic role + accessible name — resilient to DOM structure changes
   Priority 3: Component type + key prop — framework-aware, survives CSS changes
   Priority 4: Stable structural selector — last resort before CSS/XPath
   ```
3. Validate each locator against the source code AST to ensure it actually resolves
4. Build the **Locator Catalog** — a complete lookup table from semantic intent to concrete Playwright locator

**Output**: `locator-catalog.json` — prioritized locators for every interactive element

See [references/blocking-coach-guide.md](references/blocking-coach-guide.md) for locator priority rules and validation methodology.

#### Agent 4: Set Designer (布景师)

**Mission**: Generate Page Object Models (POM) from the application architecture. Not throwaway scripts, but developer-readable, maintainable first-class infrastructure.

**What it does**:
1. Read Component Registry + Locator Catalog
2. Identify page-level compositions — which components appear on which routes
3. Generate POM classes that:
   - Encapsulate all locators for a page as private properties
   - Expose **semantic action methods** (not "click button", but "submitLoginForm", "addUserToTable")
   - Include **state assertion methods** (waitForPageReady, assertFormErrors, assertTableRowCount)
   - Support **multiple state variants** based on Feature Flags and permissions
4. Each POM is a TypeScript class with proper typing, following the convention:
   ```typescript
   class LoginPage {
     // Locators from catalog — never hand-written
     private emailInput = page.getByTestId('LoginForm-input-email')
     private submitButton = page.getByTestId('LoginForm-button-submit')
     
     // Semantic actions — business-level, not DOM-level
     async submitLogin(email: string, password: string) { ... }
     async assertLoginError(expectedMessage: string) { ... }
     
     // State variants
     async withFeatureFlag(flag: string): LoginPage { ... }
   }
   ```

**Output**: `poms/` directory — TypeScript POM classes for every page/route

See [references/set-designer-guide.md](references/set-designer-guide.md) for POM generation patterns and conventions.

***

### Phase 2: Run the Show — Generation & Execution

This phase uses the structured artifacts from Phase 1 to generate and execute deterministic tests.

#### Agent 5: Choreographer (编舞师)

**Mission**: Analyze business logic and state transitions, plan complete high-level user journeys, automatically covering Feature Flags and edge cases.

**What it does**:
1. Analyze route configurations, permission models, and Feature Flag definitions from source code
2. Enumerate all **state permutations** that produce different UI renderings:
   ```
   Example permutations for a UserTable page:
   - { role: admin, featureFlag_showDelete: true }    → full table with delete buttons
   - { role: admin, featureFlag_showDelete: false }   → table without delete buttons
   - { role: viewer, featureFlag_showDelete: true }   → table without delete buttons (permission override)
   - { role: viewer, featureFlag_showDelete: false }  → table without delete buttons
   ```
3. For each permutation, plan a **user journey** — a sequence of semantic actions:
   ```
   Journey: "Admin deletes a user from table"
   Steps:
     1. navigateToLoginPage
     2. submitLogin(adminCredentials)
     3. navigateToUserTable
     4. assertDeleteButtonsVisible (only in permutation with flag=true + role=admin)
     5. deleteUserByName("John Doe")
     6. assertUserNotInTable("John Doe")
   ```
4. Generate journey coverage matrix — ensuring every permutation is tested

**Output**: `journeys.json` — complete user journey definitions with state permutations

See [references/choreographer-guide.md](references/choreographer-guide.md) for journey planning methodology and permutation enumeration.

#### Agent 6: Assistant Director (副导演)

**Mission**: Map planned steps precisely to POM methods, generate deterministic Playwright test code.

**What it does**:
1. Read journeys from Agent 5 + POMs from Agent 4 + Locator Catalog from Agent 3
2. For each journey, generate a Playwright test that:
   - Uses **only POM methods** — never raw locators or page.selectors
   - Sets up required **state permutations** (Feature Flags, permissions, mock data)
   - Includes proper **beforeEach/afterEach** hooks for state setup/teardown
   - Is **deterministic** — the same source code always produces the same test
3. Generated test structure:
   ```typescript
   test.describe('Admin deletes user from table', () => {
     test.beforeEach(async ({ page }) => {
       // Setup: enable feature flag, set admin role
       await setFeatureFlag(page, 'showDelete', true)
       await setRole(page, 'admin')
     })
     
     test('admin can delete user when flag enabled', async ({ page }) => {
       const loginPage = new LoginPage(page)
       const userTable = new UserTablePage(page)
       
       await loginPage.submitLogin('admin', 'password')
       await userTable.navigateTo()
       await userTable.assertDeleteButtonsVisible()
       await userTable.deleteUserByName('John Doe')
       await userTable.assertUserNotInTable('John Doe')
     })
   })
   ```

**Output**: `tests/` directory — deterministic Playwright test files

See [references/assistant-director-guide.md](references/assistant-director-guide.md) for test generation patterns and POM mapping conventions.

#### Agent 7: Continuity Lead (场记)

**Mission**: Execute tests and monitor. When failures occur, distinguish code bugs from test-update needs, and auto-heal.

**What it does**:
1. Execute all generated Playwright tests
2. On failure, perform **root cause classification**:
   - **Code Bug**: The application genuinely broke — POM method cannot find element that SHOULD exist based on source code — Report as bug
   - **Test Update Need**: Source code changed intentionally (component renamed, prop changed, route moved) — Trigger Phase 1 re-analysis for affected components only
   - **Environment Issue**: Network error, timeout, flaky rendering — Retry with adjusted thresholds
3. For "Test Update Need" failures, auto-trigger **partial re-analysis**:
   - Re-run Agent 1 on affected component files only
   - Re-run Agent 2-4 to update injections, locators, POMs for affected components
   - Re-run Agent 6 to regenerate affected tests only
4. Generate a **failure report** with classification and recommended action

**Output**: Test execution report + classification + auto-healing actions when applicable

See [references/continuity-lead-guide.md](references/continuity-lead-guide.md) for failure classification logic and auto-healing workflow.

***

## How to Use This Skill

### Full Pipeline Execution (Recommended)

Run the complete two-phase pipeline when starting fresh or after major code changes:

```
Phase 1:
  1. Run script-analyst — analyze source code, generate component-registry.json
  2. Run stage-manager — check/inject data-testid, generate testid-injections.json
  3. Run blocking-coach — generate locator catalog, generate locator-catalog.json
  4. Run set-designer — generate POM classes, output to poms/ directory

Phase 2:
  5. Run choreographer — plan journeys with permutations, generate journeys.json
  6. Run assistant-director — generate Playwright tests, output to tests/ directory
  7. Run continuity-lead — execute tests, classify failures, auto-heal if needed
```

### Partial Re-Analysis (Incremental Updates)

When source code changes affect specific components, re-run only the affected agents:

```
1. Identify changed component files (from git diff)
2. Re-run Agent 1 on those files only → update component-registry.json
3. Re-run Agent 2-4 for affected components → update injections, locators, POMs
4. Re-run Agent 6 for affected journeys → regenerate affected tests
5. Re-run Agent 7 → execute updated tests
```

### One-Shot Quick Test (When Source Code Unavailable)

When you cannot access source code (testing a deployed site), use the **runtime fallback mode**:

```
1. Detect frontend framework at runtime
2. Access component tree via DevTools protocol (if available)
3. Use semantic role + accessible name as locators (priority 2 from blocking-coach rules)
4. Never generate permanent POMs from runtime data — these are throwaway explorations only
5. Log that runtime fallback was used — recommend upstream analysis when source code becomes available
```

⚠️ **Important**: Runtime fallback mode is NOT the Director architecture. It is the "improvising actor" approach — useful for exploration but fundamentally lacking the determinism and state-coverage that upstream analysis provides. Always prefer source-code analysis when possible.

***

## Why This Architecture Changes the Game

1. **Speed**: Initial setup takes 30-40 minutes. One-click integration with existing repos, no rewrite needed.

2. **Shift from patching to defining**: Developers no longer write selectors or reverse-engineer DOM. Energy goes to:
   - Defining meaningful business flows
   - Validating complex business logic
   - Reviewing generated tests as maintainable code

3. **Scales with code**: Setup is one-time investment. Maintenance is driven by source code changes, not by runtime failures. Determinism enables smooth scaling as codebase grows.

4. **Future: Git-level monitoring**: Next stage — agents scan PRs in real-time, proactively analyze whether changes break existing logic, and suggest test updates as PR comments. Testing becomes a living system that evolves with the application.

***

## Key Principles

| Principle | What It Means | Anti-Pattern |
|---|---|---|
| **Upstream over Runtime** | Understand at source-code level first | Reading DOM at runtime as primary strategy |
| **Deterministic over Heuristic** | Same source → same test, always | Runtime guesswork that varies per execution |
| **POM over Raw Locators** | All interactions through semantic POM methods | `page.click('.btn-primary')` in test code |
| **Proactive over Reactive** | Source changes drive test updates | Test failures trigger emergency patches |
| **Cover Permutations over Single State** | Test all Feature Flag + role combos | Only testing what's currently visible |
| **Inject over Compromise** | Add missing identifiers to source code | Falling back to fragile selectors when identifiers missing |
| **Classify over Retry** | Distinguish bug vs test-need vs env-issue | Blindly retrying failed tests |

***

## Artifact Flow Diagram

```
Source Code (.tsx/.vue/.component.ts/.svelte)
     │         │
     │ [Agent 1: Script Analyst] ──→ component-registry.json
     │ [Agent 2: Stage Manager] ──→ testid-injections.json + source patches
     │ [Agent 3: Blocking Coach] ──→ locator-catalog.json
     │ [Agent 4: Set Designer] ──→ poms/*.ts (Page Object Models)
     │ [Agent 5: Choreographer] ──→ journeys.json (with permutations)
     │ [Agent 6: Assistant Director] ──→ tests/*.spec.ts (Playwright tests)
     │ [Agent 7: Continuity Lead] ──→ execution-report.json
     │                             │                             │
     └────────────────────→ Partial re-analysis loop
```

***

## References

- [Script Analyst Guide](references/script-analyst-guide.md) — Source code extraction patterns per framework
- [Stage Manager Guide](references/stage-manager-guide.md) — data-testid injection naming conventions
- [Blocking Coach Guide](references/blocking-coach-guide.md) — Locator priority rules and validation
- [Set Designer Guide](references/set-designer-guide.md) — POM generation patterns and conventions
- [Choreographer Guide](references/choreographer-guide.md) — Journey planning and permutation enumeration
- [Assistant Director Guide](references/assistant-director-guide.md) — Test generation and POM mapping
- [Continuity Lead Guide](references/continuity-lead-guide.md) — Failure classification and auto-healing

## Scripts

- [extract-components.sh](scripts/extract-components.sh) — Extract component registry from source code repository
- [inject-testids.sh](scripts/inject-testids.sh) — Scan and inject missing data-testid attributes
- [generate-poms.sh](scripts/generate-poms.sh) — Generate POM classes from component registry + locator catalog
- [run-pipeline.sh](scripts/run-pipeline.sh) — Execute the full 7-agent pipeline end-to-end