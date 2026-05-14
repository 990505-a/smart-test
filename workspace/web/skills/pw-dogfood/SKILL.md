---
name: pw-dogfood
description: Professional web application QA testing using playwright-cli — systematic exploration, evidence capture (traces/screenshots/video), performance & security checks, accessibility audit, and structured bug reports
version: 2.0.0
metadata:
  hermes:
    tags: [qa, testing, browser, web, playwright-cli, dogfood]
    related_skills: [playwright-cli]
---

# PW-Dogfood: Professional Web QA Testing with playwright-cli

## Overview

This skill guides systematic, professional-quality QA testing of web applications using the **playwright-cli** toolset. Unlike the built-in browser dogfood skill, playwright-cli provides:

- **Tracing** — full DOM+network+console+action replay for deep debugging
- **Network interception** — mock APIs, simulate offline, measure request timing
- **Storage state** — save/restore auth sessions, inspect cookies/localStorage/sessionStorage
- **Video recording** — annotated screencasts with chapter markers and overlays
- **JavaScript execution** — `eval` / `run-code` for performance metrics, DOM inspection, custom assertions
- **Multi-session** — named sessions (`-s=name`) for parallel role-based testing

These capabilities enable a deeper, more evidence-rich QA process than simple snapshot-and-screenshot workflows.

## Prerequisites

- playwright-cli installed and on PATH: `export PATH="/root/.hermes/node/bin:$PATH"`
- Target URL and testing scope from the user
- (Optional) Auth credentials for role-based testing

## Quick Reference — Key Commands

| Command | Purpose |
|---------|---------|
| `playwright-cli open --browser=chromium URL` | Start browser session (always use `--browser=chromium`) |
| `playwright-cli snapshot` | Get accessibility tree with element refs (eN) |
| `playwright-cli snapshot --depth=N` | Limit snapshot depth for efficiency |
| `playwright-cli click eN` / `fill eN "text"` | Interact with elements by ref |
| `playwright-cli console` / `console warning` / `console error` | Check JS console output |
| `playwright-cli network` | Inspect network requests |
| `playwright-cli screenshot` / `screenshot --filename=X.png` | Capture visual evidence |
| `playwright-cli tracing-start` / `tracing-stop` | Record full trace (DOM, network, actions, console) |
| `playwright-cli video-start X.webm` / `video-stop` | Record video screencast |
| `playwright-cli eval "JS expression"` / `eval "el => expr" eN` | Execute JS, inspect element attributes |
| `playwright-cli run-code "async page => {...}"` | Run complex Playwright code |
| `playwright-cli state-save` / `state-load` | Save/restore auth state (cookies + localStorage) |
| `playwright-cli route "**/API**" --status=404` | Mock/block network requests |
| `playwright-cli cookie-list` / `localstorage-list` | Inspect storage |
| `playwright-cli resize W H` | Change viewport for responsive testing |
| `playwright-cli -s=name open URL` | Named session for multi-role testing |
| `playwright-cli close` / `close-all` | Cleanup |

## Inputs

The user provides:
1. **Target URL** — entry point for testing
2. **Scope** — areas/features to focus on (or "full site" for comprehensive)
3. **Auth info** (optional) — credentials, roles to test
4. **Output directory** (optional) — where evidence and report go (default: `./pw-dogfood-output`)

## Workflow — 6 Phases

Follow this systematic 6-phase workflow. Each phase builds on the previous one.

---

### Phase 1: Plan & Setup

1. **Create output directory structure:**
   ```
   {output_dir}/
   ├── screenshots/       # PNG screenshots
   ├── traces/            # Playwright trace files (.trace, .network)
   ├── videos/            # WebM video recordings
   ├── storage/           # Auth state JSON files
   └── report.md          # Final report (Phase 6)
   ```
   Use terminal: `mkdir -p {output_dir}/{screenshots,traces,videos,storage}`

2. **Build a test plan:**
   - List all pages to visit (home, nav links, key flows)
   - Identify user roles (admin, guest, authenticated user)
   - List edge cases (empty states, invalid input, 404, offline)
   - Prioritize: core flows > edge cases > visual polish

3. **Start browser and navigate to target:**
   ```bash
   playwright-cli open --browser=chromium {target_url}
   ```

4. **Capture initial console state (clear buffer):**
   ```bash
   playwright-cli console
   ```
   Record any pre-existing errors — these are immediate findings.

5. **Save baseline snapshot for diff comparison later:**
   ```bash
   playwright-cli snapshot --filename={output_dir}/traces/baseline-snapshot.yaml
   ```

---

### Phase 2: Systematic Exploration

For each page/feature in your test plan:

#### 2.1 Navigate & Assess

```bash
playwright-cli goto {page_url}
playwright-cli console          # Check for JS errors on load
playwright-cli snapshot         # Get element refs for interaction
playwright-cli screenshot --filename={output_dir}/screenshots/{page_name}-loaded.png
```

#### 2.2 Test Interactive Elements

Use the snapshot refs (eN) to interact systematically:

```bash
# Read the snapshot, identify clickable/fillable elements
playwright-cli click e5
playwright-cli console          # Check for errors after interaction
playwright-cli snapshot         # See what changed
```

**Form testing pattern:**
```bash
# 1. Test empty submission (validation check)
playwright-cli click {submit_button_ref}

# 2. Test invalid input
playwright-cli fill e3 "invalid@@email"
playwright-cli click {submit_button_ref}

# 3. Test valid input
playwright-cli fill e3 "user@example.com"
playwright-cli fill e4 "Valid Name"
playwright-cli click {submit_button_ref}
playwright-cli console          # Errors after submission?
```

**Auth flow testing pattern:**
```bash
# Login
playwright-cli fill {email_ref} "{email}"
playwright-cli fill {password_ref} "{password}"
playwright-cli click {login_ref}
playwright-cli console          # Auth errors?
playwright-cli snapshot         # Did we reach the dashboard?
playwright-cli state-save {output_dir}/storage/auth.json  # Save for reuse

# Logout
playwright-cli click {logout_ref}
playwright-cli snapshot         # Redirected to login page?
playwright-cli cookie-list      # Session cookies cleared?
playwright-cli localstorage-list # Auth tokens removed?

# Re-authenticate via saved state (skip login form)
playwright-cli state-load {output_dir}/storage/auth.json
playwright-cli goto {protected_page}
```

**Navigation flow testing:**
```bash
# Click through multi-step processes end-to-end
playwright-cli click e2         # Step 1
playwright-cli snapshot         # Verify transition
playwright-cli click e7         # Step 2
playwright-cli console          # Check for errors mid-flow
```

#### 2.3 Edge Case Probing

- **Empty states**: Submit forms with all fields blank
- **Special characters**: Type `<script>alert(1)</script>`, `null`, `undefined` into inputs
- **Very long input**: Fill text fields with 500+ character strings
- **Keyboard navigation**: `playwright-cli press Tab` through all interactive elements
- **Rapid interaction**: Click the same button 5 times quickly
- **Back/forward**: `playwright-cli go-back` then `go-forward` — check state preservation

#### 2.4 After Each Interaction

Always run this mini-check sequence:
```bash
playwright-cli console          # 1. Silent JS errors = high-value finding
playwright-cli network          # 2. Failed requests (4xx/5xx)
playwright-cli snapshot         # 3. DOM state changed as expected?
```

If you find an issue, immediately enter **Phase 3: Evidence Collection** for that issue before continuing exploration.

---

### Phase 3: Evidence Collection

For EVERY issue found, capture rich evidence using playwright-cli's advanced capabilities. This is where playwright-cli far exceeds simple screenshot-based approaches.

#### 3.1 Screenshot Evidence

```bash
playwright-cli screenshot --filename={output_dir}/screenshots/issue-{N}-{description}.png
```

#### 3.2 Trace Evidence (Most Powerful)

Traces capture DOM snapshots before/after every action, network waterfall, console logs, and timing. Start tracing BEFORE the problematic action:

```bash
playwright-cli tracing-start

# Reproduce the issue step-by-step
playwright-cli goto {page_url}
playwright-cli click e3         # The problematic click
playwright-cli fill e5 "bad input"

playwright-cli tracing-stop
```

Trace files are saved to `.playwright-cli/traces/`. Copy them to your output:
```bash
cp .playwright-cli/traces/trace-*.trace {output_dir}/traces/
cp .playwright-cli/traces/trace-*.network {output_dir}/traces/
```

#### 3.3 Console & Network Evidence

```bash
# Console errors specific to the issue
playwright-cli console          # All levels
playwright-cli console error    # Only errors

# Network failures related to the issue
playwright-cli network          # Failed requests visible here
```

#### 3.4 Element Attribute Evidence

When an element behaves unexpectedly, inspect its attributes:
```bash
playwright-cli eval "el => el.getAttribute('data-testid')" e5
playwright-cli eval "el => el.className" e5
playwright-cli eval "el => el.disabled" e5
playwright-cli eval "el => getComputedStyle(el).display" e5
```

#### 3.5 Video Evidence (for Complex Flows)

For multi-step reproduction that needs visual narration:
```bash
playwright-cli video-start {output_dir}/videos/issue-{N}-{description}.webm

# Reproduce the full flow
playwright-cli goto {page_url}
playwright-cli video-chapter "Starting Point" --description="Navigating to the form page"
playwright-cli fill e3 "bad input"
playwright-cli video-chapter "Error Trigger" --description="Submitting invalid data"
playwright-cli click e5

playwright-cli video-stop
```

#### 3.6 Storage State Evidence

For auth/session-related issues:
```bash
playwright-cli cookie-list
playwright-cli localstorage-list
playwright-cli sessionstorage-list
```

#### 3.7 Record Issue Details

For each issue, record:
- **Issue number** (sequential: #1, #2, ...)
- **URL** where the issue occurs
- **Steps to reproduce** (exact playwright-cli commands)
- **Expected behavior**
- **Actual behavior**
- **Severity** (Critical / High / Medium / Low) — see `references/issue-taxonomy.md`
- **Category** (Functional / Visual / Accessibility / Console / UX / Security / Performance / Content)
- **Evidence artifacts** (screenshot, trace, video, console output paths)
- **Element identifier** — CRITICAL: refs (eN) are transient and change after every interaction. Record the ref AND a stable locator (CSS selector, data-testid, role+name) at the moment of discovery. Do not rely on refs for later reference.

---

### Phase 4: Advanced Testing

This phase uses playwright-cli capabilities that simple browser tools cannot replicate. Run these checks AFTER completing basic exploration.

#### 4.1 Performance Testing

Load `references/performance-testing.md` for the full checklist with thresholds and JS snippets. Key areas to cover:

- **Page load timing**: Navigation Timing API (TTFB, FCP, total load)
- **Resource analysis**: Inventory large (>200KB) and slow (>2s) resources
- **DOM complexity**: Node count, nesting depth, shadow DOM
- **Memory & runtime**: JS heap size, long tasks
- **Network waterfall**: Tracing + `network` for failed/duplicate requests
- **Caching headers**: Check static resources are properly cached

#### 4.2 Security Checks

Load `references/security-checks.md` for the full checklist with severity mappings. Key areas to cover:

- **Cookie security**: httpOnly, secure, sameSite flags on auth cookies
- **Storage leakage**: Auth tokens/PII in localStorage or sessionStorage
- **XSS probing**: Script injection into inputs, URL parameter injection, template injection
- **Mixed content**: HTTP resources on HTTPS pages
- **CORS & API security**: Misconfigured headers, unauthenticated endpoints
- **CSRF tokens**: POST forms without CSRF protection
- **Information disclosure**: Debug endpoints, server version headers, source maps

#### 4.3 Accessibility Audit

Load `references/accessibility-testing.md` for the full checklist with WCAG mappings and JS snippets. Key areas to cover:

- **Image alt text**: Meaningful images without non-empty alt
- **Form labels**: Inputs without label, aria-label, aria-labelledby, or title
- **Keyboard navigation**: Tab sequence completeness, focus traps in dialogs, focus indicator visibility
- **ARIA audit**: Invalid roles, missing aria-live on dynamic content, aria-expanded on non-interactive elements
- **Color contrast**: WCAG AA compliance (4.5:1 normal text, 3:1 large text)
- **Heading structure**: Level skips, missing/multiple h1
- **Semantic structure**: Landmark regions, ambiguous link text

#### 4.4 Responsive Testing

Test at multiple viewport sizes:
```bash
# Desktop
playwright-cli resize 1920 1080
playwright-cli screenshot --filename={output_dir}/screenshots/{page}-desktop.png

# Tablet
playwright-cli resize 768 1024
playwright-cli snapshot
playwright-cli screenshot --filename={output_dir}/screenshots/{page}-tablet.png

# Mobile
playwright-cli resize 375 667
playwright-cli snapshot
playwright-cli screenshot --filename={output_dir}/screenshots/{page}-mobile.png

# Check for layout breaks at each size
playwright-cli eval "() => [...document.querySelectorAll('*')].filter(e => e.offsetWidth > document.documentElement.clientWidth).map(e => e.tagName + ':' + e.id)"
```

#### 4.5 Role-Based Testing (Multi-Session)

If the app has multiple user roles, test each in a named session:

```bash
# Admin session
playwright-cli -s=admin open --browser=chromium {login_url}
playwright-cli -s=admin fill e1 "admin@example.com"
playwright-cli -s=admin fill e2 "adminpass"
playwright-cli -s=admin click e3
playwright-cli -s=admin state-save {output_dir}/storage/admin-auth.json

# Guest session (different browser instance!)
playwright-cli -s=guest open --browser=chromium {target_url}
playwright-cli -s=guest snapshot
# Test what guest can/cannot access

# Compare: admin sees feature X, guest should NOT
playwright-cli -s=admin eval "() => document.querySelectorAll('.admin-panel').length"
playwright-cli -s=guest eval "() => document.querySelectorAll('.admin-panel').length"
```

#### 4.6 Network Resilience Testing

Simulate adverse network conditions:

```bash
# Block all images — does the page still function?
playwright-cli route "**/*.{png,jpg,jpeg,gif,svg,webp}" --status=404
playwright-cli reload
playwright-cli snapshot
playwright-cli screenshot --filename={output_dir}/screenshots/{page}-no-images.png
playwright-cli unroute

# Block API calls — graceful degradation?
playwright-cli route "**/api/**" --status=500
playwright-cli reload
playwright-cli console error
playwright-cli unroute

# Simulate offline
playwright-cli run-code "async page => {
  await page.route('**/*', route => route.abort('internetdisconnected'));
}"
playwright-cli reload
playwright-cli console
playwright-cli unroute
```

#### 4.7 State Persistence Testing

```bash
# Test that logout clears sensitive data
playwright-cli state-save {output_dir}/storage/pre-logout.json
playwright-cli click {logout_button_ref}
playwright-cli cookie-list       # Session cookies cleared?
playwright-cli localstorage-list # Auth tokens removed?

# Test that cart/state survives page reload
playwright-cli fill e3 "item selection"
playwright-cli click {add_to_cart_ref}
playwright-cli localstorage-list
playwright-cli reload
playwright-cli localstorage-list # Cart data still there?
```

---

### Phase 5: Categorize & Prioritize

1. **Review all collected issues.**
2. **De-duplicate** — merge issues that are the same bug in different manifestations.
3. **Assign final severity and category** using `references/issue-taxonomy.md`.
4. **Cross-reference evidence** — ensure each issue has at least one screenshot, and preferably a trace or console log.
5. **Sort by severity** (Critical > High > Medium > Low).
6. **Count issues** by severity and category for the executive summary.

Severity priority criteria:
- **Critical**: Core feature broken, data loss, security vulnerability
- **High**: Key feature impaired, workaround may exist
- **Medium**: UX affected but functional
- **Low**: Cosmetic/minor polish

---

### Phase 6: Report

Generate the final report using the template at `templates/report-template.md`.

The report must include:
1. **Executive summary** — total issues, severity breakdown, overall assessment
2. **Per-issue sections** with:
   - Issue number and title
   - Severity and category badges
   - URL where observed
   - Description
   - Steps to reproduce (exact playwright-cli commands)
   - Expected vs actual behavior
   - Evidence artifacts (screenshot path, trace path, video path)
   - Console errors / network failures
   - Element refs involved
3. **Summary table** of all issues
4. **Performance findings** (load timing, resource metrics)
5. **Security findings** (cookie flags, XSS probes, data leakage)
6. **Accessibility findings** (missing alt text, labels, keyboard nav)
7. **Testing coverage** — pages tested, features tested, not tested, blockers

Save the report to `{output_dir}/report.md`.

#### Cleanup

Before writing the report, perform cleanup:

1. **Inventory evidence files** — list all files in `{output_dir}/screenshots/`, `{output_dir}/traces/`, `{output_dir}/videos/`, `{output_dir}/storage/`. Ensure every issue has corresponding artifacts.
2. **Close browser** — `playwright-cli close` or `playwright-cli close-all`. Leaked sessions waste resources and may interfere with future runs.
3. **Write report** — using `templates/report-template.md`.

---

## Key Differences from Built-in Browser Dogfood

| Aspect | Built-in Browser Dogfood | PW-Dogfood (playwright-cli) |
|--------|-------------------------|----------------------------|
| Element targeting | @eN refs from accessibility snapshot | eN refs + CSS selectors + Playwright locators + eval attribute inspection |
| Console checking | `browser_console()` per interaction | `playwright-cli console` with level filtering (error/warning/all) |
| Evidence depth | Screenshots only | Screenshots + traces (DOM+network+action replay) + video + element attributes |
| Performance | Not available | `performance.timing`, resource metrics, DOM node count via `eval/run-code` |
| Security | Not available | Cookie security flags, XSS probes, localStorage leakage, mixed content |
| Accessibility | Visual assessment only | Programmatic alt-text checks, label checks, keyboard focus tracking |
| Network | Not available | Request mocking, offline simulation, API failure testing |
| Multi-role | Single browser session | Named sessions (`-s=name`) for parallel role testing |
| State management | Not available | `state-save/state-load`, cookie/localStorage inspection |
| Responsive | Not available | `resize W H` for viewport testing at any size |

## Tips & Pitfalls

### Critical Rules

- **Always use `--browser=chromium`** when opening browser sessions — no Chrome binary exists in this environment.
- **Always check `playwright-cli console` after navigation and after significant interactions.** Silent JS errors are among the most valuable findings.
- **Refs (eN) are transient** — they change after every snapshot. When you discover an issue, record the ref AND extract a stable locator immediately (`eval "el => el.getAttribute('data-testid')" e5` or `eval "el => el.className" e5`). Never expect refs to survive a page transition or reload.
- **Start tracing BEFORE the problematic action**, not after. Traces capture the full sequence leading to the issue.
- **For form testing, always try empty submission first** — many apps fail to validate required fields.
- **Copy trace files from `.playwright-cli/traces/` to your output directory** — traces in the default location may be overwritten by subsequent runs.
- **Don't forget to unroute** after network mocking tests — `playwright-cli unroute` removes all routes. Leftover routes will affect subsequent page loads.

### Token Efficiency

- **Use `snapshot --depth=4`** for pages with deep DOM trees. Full snapshots on complex pages consume excessive tokens. Use deeper snapshots only when targeting specific nested elements.
- **Use `--raw` flag** not just for piping, but for evidence collection: `playwright-cli --raw console` / `--raw network` produce clean text without page status headers, ideal for embedding in reports.
- **Use `snapshot eN`** to snapshot a specific element instead of the entire page when you only need to inspect one component.
- **Prefer `eval` over `run-code`** for simple queries. `eval` produces shorter output. Use `run-code` only when you need async operations or page-level APIs.
- **Avoid re-snapshotting unchanged pages.** If a click produced no visible state change, skip the follow-up snapshot and check `console` instead.

### Failure Recovery

When interactions fail, use this fallback sequence:

1. **Ref expired** → Re-snapshot and get fresh refs. If element still exists, use the new ref.
2. **Ref not found in snapshot** → Element may be hidden/offscreen. Use CSS selector: `playwright-cli click "#submit-btn"` or Playwright locator: `playwright-cli click "getByRole('button', { name: 'Submit' })"`.
3. **Click does nothing** → Element may be covered by overlay or offscreen. Try `playwright-cli eval "el => el.getBoundingClientRect()" eN` to check position, then `playwright-cli mousemove X Y` + `playwright-cli click eN` for precision targeting.
4. **Fill doesn't work** → Some custom inputs (React/Vue) don't respond to `fill`. Use `playwright-cli click eN` first to focus, then `playwright-cli type "text"` character by character.
5. **Dialog blocks interaction** → Use `playwright-cli dialog-accept` or `dialog-dismiss` to handle unexpected alert/confirm/prompt dialogs.

### Session Management

- **Named sessions (`-s=name`)** are independent browser instances — use them for testing different user roles simultaneously.
- **Run `playwright-cli console` at the start** to clear the buffer and establish a baseline. Pre-existing errors on first load are immediate findings.
- **Clean up browser sessions** with `playwright-cli close` or `playwright-cli close-all` when done. Leaked sessions waste resources.

### JS Execution Caveats

- **NodeList is not Array** — `document.querySelectorAll()` returns a NodeList without `.filter()` / `.map()`. Always spread first: `[...document.querySelectorAll('x')]`. This is a common bug in JS snippets — double-check any `eval` / `run-code` that chains array methods on querySelectorAll results.
- **`getComputedStyle` with transparent backgrounds** — `rgba(0,0,0,0)` and `transparent` are not valid contrast backgrounds. Skip these elements in contrast checks (the actual background is inherited from a parent).
- **`performance.memory`** is Chrome-only — returns `undefined` in Firefox/WebKit. Guard with `if (performance.memory)` checks.

## Linked Files

- `references/issue-taxonomy.md` — Severity levels and category definitions
- `references/performance-testing.md` — Detailed performance testing procedures
- `references/security-checks.md` — Security audit checklist and procedures
- `references/accessibility-testing.md` — Accessibility testing procedures
- `templates/report-template.md` — Report generation template