# Web Testing Agent — Artifact Contract

This document defines the directory structures, file formats, and data contracts that bind the dual-mode agent workflows together.

---

## Mode A: Exploratory QA Artifacts

### Directory Layout

```
web-output/qa/{label}_{timestamp}/
├── screenshots/          # PNG screenshots per issue
├── traces/               # Playwright trace + network files
├── videos/               # WebM screen recordings
├── storage/              # Auth state JSON files
└── report.md             # Final structured report
```

### File Naming Conventions

| Artifact | Pattern | Example |
|---|---|---|
| Screenshot | `screenshots/issue-{N}-{short_desc}.png` | `issue-3-login-error.png` |
| Trace | `traces/issue-{N}-{short_desc}.trace` | `issue-3-login-error.trace` |
| Network | `traces/issue-{N}-{short_desc}.network` | `issue-3-login-error.network` |
| Video | `videos/issue-{N}-{short_desc}.webm` | `issue-3-login-error.webm` |
| Auth state | `storage/{role}-auth.json` | `storage/admin-auth.json` |

### Report Schema (`report.md`)

Must follow `pw-dogfood/templates/report-template.md` and include:
1. Executive summary (severity + category counts)
2. Per-issue sections (severity, category, URL, reproduction steps, evidence links)
3. Performance findings table
4. Security findings table
5. Accessibility findings table
6. Testing coverage section

---

## Mode B: Component-Aware Test Generation Artifacts

### Directory Layout

```
web-output/tests/{project_name}_{timestamp}/
├── component-registry.json      # (Agent 1) Extracted component metadata
├── testid-injections.json       # (Agent 2) Injected data-testid catalog
├── locator-catalog.json         # (Agent 3) Prioritized locator chains
├── poms/                        # (Agent 4) Generated Page Object Models
│   ├── LoginPage.ts
│   ├── DashboardPage.ts
│   └── ...
├── journeys.json                # (Agent 5) Planned user journeys + permutations
├── tests/                       # (Agent 6) Generated Playwright test files
│   ├── login/
│   │   ├── Login-standard.spec.ts
│   │   └── Login-lockedOut.spec.ts
│   └── ...
└── execution-report.json        # (Agent 7) Test run + failure classification
```

### Data Contracts

#### `component-registry.json`

Top-level schema:
```json
{
  "$schema": "https://component-aware.schema/v1/registry",
  "metadata": {
    "repo": "string",
    "branch": "string",
    "framework": "react|vue|angular|svelte",
    "scanTimestamp": "ISO8601",
    "totalComponents": 0
  },
  "components": [
    {
      "id": "ComponentName",
      "filePath": "src/components/ComponentName.tsx",
      "framework": "react",
      "type": "function-component",
      "props": [{"name": "", "type": "", "required": true, "defaultValue": null}],
      "state": [{"name": "", "type": "", "initialValue": "", "setter": ""}],
      "interactiveElements": [{"elementType": "", "role": "", "binding": "", "handler": ""}],
      "conditionalRendering": [{"condition": "", "renders": "", "type": ""}],
      "featureFlags": [],
      "childComponents": [],
      "accessibilityInfo": {"ariaLabels": [], "roles": []}
    }
  ]
}
```

#### `locator-catalog.json`

Top-level schema:
```json
{
  "version": "1.0",
  "generatedAt": "ISO8601",
  "entries": [
    {
      "componentId": "LoginForm",
      "elementRole": "submit-button",
      "priorityChain": [
        {"priority": 1, "strategy": "data-testid", "value": "LoginForm-button-submit"},
        {"priority": 2, "strategy": "role+name", "value": "getByRole('button', {name: 'Submit'})"},
        {"priority": 3, "strategy": "component-prop", "value": "..."},
        {"priority": 4, "strategy": "structural", "value": "..."}
      ]
    }
  ]
}
```

#### `journeys.json`

Top-level schema:
```json
{
  "version": "1.0",
  "journeys": [
    {
      "id": "j-login-standard",
      "name": "Login - standard user",
      "permutation": {
        "role": "standard_user",
        "featureFlags": {"showDelete": true}
      },
      "steps": [
        {"action": "navigateToLoginPage", "target": "LoginPage"},
        {"action": "submitLogin", "target": "LoginPage", "args": ["standard_user", "secret_sauce"]},
        {"action": "assertProductsVisible", "target": "InventoryPage"}
      ]
    }
  ]
}
```

#### POM Class Contract (TypeScript)

Every generated POM MUST:
1. Import from `@playwright/test`
2. Use **only** semantic locators (`getByTestId`, `getByRole`) — no raw CSS/XPath in public methods
3. Expose `waitForReady(): Promise<void>`
4. Expose `navigateTo(): Promise<void>`
5. Keep locators as `private readonly` fields

#### Playwright Test Contract (`*.spec.ts`)

Every generated test MUST:
1. Import `{ test, expect } from '@playwright/test'`
2. Import only POM classes (no raw locators)
3. Use `test.beforeEach` for state setup (Feature Flags, roles, mock data)
4. Name format: `{Component}-{Role}-{FlagState}-{Action}.spec.ts`
5. One `test.describe` per file, one `test()` per permutation
6. No hard-coded `page.waitForTimeout()` calls

---

## Cross-Mode Constraints

1. **Timestamp format**: `YYYYMMDD_HHMMSS` (24-hour, local time)
2. **Label sanitization**: Replace any non-alphanumeric/non-hyphen character with `_`, max 40 chars
3. **File paths**: Always use forward slashes in JSON metadata; OS paths in filesystem
4. **JSON indentation**: 2 spaces, UTF-8 encoding, no BOM
5. **No manual edits**: Generated artifacts should be treated as read-only downstream inputs; any intentional override must be documented in a `notes.md` file next to the artifact
