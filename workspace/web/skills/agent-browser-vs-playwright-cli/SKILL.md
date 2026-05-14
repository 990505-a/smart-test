---
name: agent-browser-vs-playwright-cli
description: Choose between agent-browser (default) and playwright-cli for web automation. Covers selection criteria, token efficiency, command parity, and framework-specific pitfalls. No built-in Browser — only two production-grade frameworks.
tags: [browser, testing, comparison, workaround, framework-selection, agent-browser, playwright-cli]
related_skills: [agent-browser, playwright-cli, pw-dogfood]
---

# Browser Automation Framework Selection: agent-browser vs playwright-cli

Two production-grade frameworks for web automation. Pick the right one, know its limits, switch when needed.

## Quick Decision

| Criteria | Choose |
|----------|--------|
| **Most tasks (default)** | agent-browser |
| Cross-browser testing (firefox/webkit) | playwright-cli |
| CI/CD trace evidence | playwright-cli |
| Token efficiency priority | agent-browser |
| Network mocking | either — see parity table |
| Video recording | agent-browser (`record`) — simpler |
| Dialog control (dismiss/prompt input) | either — both support `dialog` commands |
| Slow async content (needs smart wait) | agent-browser — 5 built-in wait commands |
| Bulk data extraction | agent-browser (`eval --stdin` with JS) |

**Rule of thumb**: Start with agent-browser. Switch to playwright-cli only when you need firefox/webkit or CI traces.

## Framework Comparison

| Dimension | agent-browser | playwright-cli |
|-----------|--------------|----------------|
| **Architecture** | Rust daemon, persists across commands | Node.js process per command |
| **Response time** | 0.1-0.3s per command | 0.5-1.5s per command |
| **Snapshot tokens** | ~200-400 (`snapshot -i`) | ~500-800 (full page) |
| **Snapshot mode** | Interactive-only by default (`-i`) | Always full page |
| **Element targeting** | Semantic locators (`find role/text/label`) + `@eN` refs | `@eN` refs + CSS + getByRole/getByTestId (mixed reliability) |
| **Wait commands** | 5 types: `wait @ref`, `wait --text`, `wait --url`, `wait --load networkidle`, `wait --fn "JS"` | None — must `sleep N` via terminal |
| **Sessions** | `--session a/b` isolated browsers | `-s=name` isolated browsers |
| **Auth state** | Vault + `auth save/load` | `state-save/state-load` JSON |
| **Video** | `record start/stop` → .webm | `video-start/stop` → .webm |
| **Tracing** | Not available | `tracing-start/stop` → trace ZIP |
| **Cross-browser** | Chromium only | chromium, firefox, webkit |
| **Network mock** | `network route/unroute` | `route/unroute` |
| **Console/Network logs** | `console` / `network` | `console` / `network` |
| **Dialog control** | `dialog accept/dismiss` | `dialog-accept/dismiss` |

## Command Parity Map

Commands that exist in both frameworks (different syntax):

| Operation | agent-browser | playwright-cli |
|-----------|--------------|----------------|
| Open browser | `open URL` | `open --browser=chromium URL` |
| Navigate | `goto URL` | `goto URL` |
| Click | `click @e5` or `click "selector"` | `click e5` or `click "#sel"` |
| Type/Fill | `type @e5 "text"` or `fill @e5 "text"` | `fill e5 "text"` or `type "text"` |
| Press key | `press Enter` | `press Enter` |
| Screenshot | `screenshot` or `screenshot @e5` | `screenshot` or `screenshot e5` |
| Select dropdown | `select @e5 "value"` | `select e9 "value"` |
| Hover | `hover @e5` | `hover e4` |
| Drag | `drag @e2 @e8` | `drag e2 e8` |
| Upload | `upload @e5 ./file.pdf` | `upload ./document.pdf` |
| Check/Uncheck | `check @e12` / `uncheck @e12` | `check e12` / `uncheck e12` |
| Dblclick | `dblclick @e5` | `dblclick e7` |
| Eval JS | `eval "document.title"` or `eval --stdin` | `eval "document.title"` |
| Get snapshot | `snapshot` or `snapshot -i` | `snapshot` |
| Close | `close` | `close` |
| Console logs | `console` | `console` |
| Network logs | `network` | `network` |
| Go back/forward | `go-back` / `go-forward` | `go-back` / `go-forward` |
| Reload | `reload` | `reload` |
| Tab management | `tab-new/select/close/list` | `tab-new/select/close/list` |
| Resize viewport | `resize 1920 1080` | `resize 1920 1080` |

Commands unique to each:

| agent-browser only | playwright-cli only |
|--------------------|--------------------|
| `find role "button"` | `tracing-start/stop` |
| `find text "Submit"` | `run-code "async page => ..."` |
| `find label "Email"` | `pdf --filename=out.pdf` |
| `wait @ref / --text / --url / --load / --fn` | `cookie-*` (full CRUD) |
| `auth save/load/list` | `localstorage-*` (full CRUD) |
| `record start/stop` (video) | `sessionstorage-*` (full CRUD) |
| `network route/unroute/log` | `video-start/stop/chapter` |
| `dialog accept "text" / dismiss` | `dialog-accept/dismiss` |

## agent-browser Pitfalls

1. **Ref staleness** — `@eN` refs expire when the DOM changes. Re-snapshot before acting on a ref from an earlier step. Record ref AND stable selector on discovery.
2. **No tracing** — if you need Playwright trace ZIP for CI evidence, you must use playwright-cli.
3. **Chromium only** — cannot test firefox/webkit rendering bugs.
4. **`onclick` attribute events** — `click @ref` may not fire `onclick="handler()"` bound events. Fallback: `eval "handlerFn()"` to call the function directly.
5. **Dynamic content** — accessibility tree may not show content revealed from `display:none → visible`. Verify with `eval`:
   ```bash
   agent-browser eval "document.querySelector('#finish')?.textContent || 'not found'"
   ```
6. **Cookie/storage CRUD** — agent-browser lacks `cookie-set/delete` and `localstorage/sessionstorage-set/delete`. Use `eval` workaround:
   ```bash
   agent-browser eval "document.cookie = 'key=value; path=/'"
   agent-browser eval "localStorage.setItem('theme', 'dark')"
   ```
7. **Daemon must be running** — `agent-browser` auto-starts the daemon on first command, but if it crashes, commands fail silently. Check with `agent-browser list` or restart via `agent-browser kill && agent-browser open`.

## playwright-cli Pitfalls

1. **No wait commands** — the biggest weakness. Must `sleep N` via terminal for async content. Agent heuristic: check `console` output instead of blind sleeps.
2. **Full snapshot on every command** — every click/fill/goto outputs a full page snapshot (~500-800 tokens). Use `--raw` to suppress when chaining commands; re-snapshot explicitly only when you need to see changes.
3. **`--browser=chromium` required** — environment has no Chrome binary. Always `open --browser=chromium`.
4. **Node.js process per command** — slower than agent-browser daemon. Each command spawns a process, parses config, connects to browser.
5. **getByTestId fails as string locator** — `click "getByTestId('checkout')"` does NOT work. Use CSS: `click "[data-test='checkout']"`.
6. **getByRole mixed reliability** — test before relying on it. Prefer CSS selectors or refs.
7. **`unroute` after every mock** — leftover routes corrupt subsequent page loads. Always `unroute` after network mocking tests.
8. **Refs (eN) are transient** — change after every snapshot. Record ref AND stable locator (`eval "el => el.getAttribute('data-testid')" e5`) immediately.

## Framework Fallback Chain

When your primary framework hits a wall:

```
agent-browser → (need tracing?) → playwright-cli
agent-browser → (need firefox/webkit?) → playwright-cli
playwright-cli → (need smart wait?) → agent-browser
playwright-cli → (token budget tight?) → agent-browser snapshot -i
```

**Never fall back to built-in Browser** for production tasks — its 35% interaction coverage and auto-accept dialogs make it unreliable for evidence-grade testing.

## Token Efficiency Strategies

### agent-browser (already efficient)
- `snapshot -i` — only interactive elements, ~200-400 tokens
- `find role/text/label` — locate elements without snapshot
- `eval --stdin` — pipe JS from file, avoid inline escaping issues

### playwright-cli (needs discipline)
- `--raw` flag on intermediate commands — suppress snapshot output
- `snapshot --depth=4` — limit depth for complex pages
- `snapshot eN` — single element instead of full page
- `eval` over `run-code` for simple queries (shorter output)
- Skip re-snapshotting unchanged pages; check `console` instead

## Quick Reference: Scenario → Framework → Command

| Scenario | Framework | Key Commands |
|----------|-----------|-------------|
| Standard page interaction | agent-browser | `open` → `snapshot -i` → `click @e5` |
| Smart wait for async content | agent-browser | `wait --text "Success"` or `wait --load networkidle` |
| Cross-browser test | playwright-cli | `open --browser=firefox URL` |
| CI trace evidence | playwright-cli | `tracing-start` → actions → `tracing-stop` |
| Network mock | either | ab: `network route "**/api/**" --body='...'` / pw: `route "**/api/**" --body='...'` |
| Dialog control | either | ab: `dialog accept "text"` / pw: `dialog-accept "text"` |
| Cookie/storage manipulation | playwright-cli | `cookie-set/get/delete`, `localstorage-*`, `sessionstorage-*` |
| Bulk data extraction | agent-browser | `eval --stdin` with JS querySelectorAll |
| Video recording | agent-browser | `record start demo.webm` → `record stop` |
| Auth session reuse | either | ab: `auth save/load` / pw: `state-save/state-load` |
| Form submission | either | ab: `fill @e5 "val"` → `click @submit` / pw: `fill e5 "val" --submit` |
| Performance audit | playwright-cli | `run-code "async page => ..."` with Performance API |
| Accessibility audit | playwright-cli | `run-code` with Playwright accessibility assertions |