# PW-Dogfood QA Report Template

**Target:** {target_url}
**Date:** {date}
**Scope:** {scope_description}
**Tester:** Hermes Agent (pw-dogfood — playwright-cli automated exploratory QA)
**Browser:** Chromium (playwright-cli)
**Output Directory:** {output_dir}

---

## Executive Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical | {critical_count} |
| 🟠 High | {high_count} |
| 🟡 Medium | {medium_count} |
| 🔵 Low | {low_count} |
| **Total** | **{total_count}** |

**Overall Assessment:** {one_sentence_assessment}

### Category Breakdown

| Category | Count |
|----------|-------|
| Functional | {functional_count} |
| Visual | {visual_count} |
| Accessibility | {accessibility_count} |
| Console | {console_count} |
| UX | {ux_count} |
| Security | {security_count} |
| Performance | {performance_count} |
| Content | {content_count} |

---

## Issues

<!-- Repeat this section for each issue found, sorted by severity (Critical first) -->

### Issue #{issue_number}: {issue_title}

| Field | Value |
|-------|-------|
| **Severity** | {severity_badge} |
| **Category** | {category} |
| **URL** | {url_where_found} |
| **Element Ref** | {eN_refs_involved} |

**Description:**
{detailed_description_of_the_issue}

**Steps to Reproduce:**
```bash
# Exact playwright-cli commands to reproduce
playwright-cli open --browser=chromium {url}
playwright-cli snapshot
playwright-cli click e5
playwright-cli console
```

**Expected Behavior:**
{what_should_happen}

**Actual Behavior:**
{what_actually_happens}

**Evidence:**

| Evidence Type | Path |
|---------------|------|
| Screenshot | `{output_dir}/screenshots/issue-{N}-*.png` |
| Trace | `{output_dir}/traces/issue-{N}-*.trace` |
| Video | `{output_dir}/videos/issue-{N}-*.webm` |

**Console Errors:**
```
{console_error_output}
```

**Network Failures:**
```
{failed_request_details_from_playwright_cli_network}
```

**Element Attributes:**
```
{eval_output_for_relevant_elements}
```

---

<!-- End of per-issue section -->

## Issues Summary Table

| # | Title | Severity | Category | URL | Key Evidence |
|---|-------|----------|----------|-----|-------------|
| {n} | {title} | {severity} | {category} | {url} | {evidence_type} |

---

## Performance Findings

### Page Load Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Total Load Time | {total_load_ms}ms | < 5000ms | {pass_or_fail} |
| TTFB | {ttfb_ms}ms | < 1000ms | {pass_or_fail} |
| FCP | {fcp_ms}ms | < 1800ms | {pass_or_fail} |
| DOM Node Count | {dom_nodes} | < 1500 | {pass_or_fail} |
| JS Heap Size | {heap_mb}MB | < 50MB | {pass_or_fail} |

### Resource Summary

| Metric | Count / Size |
|--------|-------------|
| Total Resources | {resource_count} |
| Large Resources (>200KB) | {large_count} |
| Slow Resources (>2s) | {slow_count} |
| Failed Requests (4xx/5xx) | {failed_count} |
| Duplicate Requests | {duplicate_count} |
| Uncached Static Resources | {uncached_count} |

### Performance Issues

<!-- List performance-related findings with details -->

---

## Security Findings

### Cookie Security

| Cookie Name | httpOnly | secure | sameSite | Domain | Finding |
|-------------|----------|--------|----------|--------|---------|
| {name} | {yes/no} | {yes/no} | {value} | {domain} | {issue_or_ok} |

### Storage Security

| Storage Type | Key | Sensitive? | Finding |
|-------------|-----|-----------|---------|
| localStorage | {key} | {yes/no} | {issue_or_ok} |
| sessionStorage | {key} | {yes/no} | {issue_or_ok} |

### XSS Probes

| Input Field | Payload | Renders? | Finding |
|-------------|---------|---------|---------|
| {field} | `<script>alert(1)</script>` | {yes/no} | {critical_or_ok} |
| {field} | `<img src=x onerror=alert(1)>` | {yes/no} | {critical_or_ok} |

### Mixed Content

| Type | URL | Finding |
|------|-----|---------|
| {active/passive} | {http_url} | {issue} |

### Security Issues

<!-- List security-related findings with details -->

---

## Accessibility Findings

### WCAG Compliance Summary

| WCAG Criterion | Check | Result | Issues Found |
|----------------|-------|--------|-------------|
| 1.1.1 Non-text Content | Image alt text | {pass/fail} | {count} |
| 1.3.1 Info and Relationships | Form labels | {pass/fail} | {count} |
| 1.3.1 Info and Relationships | Heading hierarchy | {pass/fail} | {count} |
| 1.3.1 Info and Relationships | Landmark regions | {pass/fail} | {count} |
| 1.4.3 Contrast (Minimum) | Color contrast AA | {pass/fail} | {count} |
| 2.1.1 Keyboard | Tab sequence completeness | {pass/fail} | {count} |
| 2.4.3 Focus Order | Focus trap in dialogs | {pass/fail} | {count} |
| 2.4.7 Focus Visible | Focus indicators | {pass/fail} | {count} |
| 2.4.4 Link Purpose | Ambiguous link text | {pass/fail} | {count} |
| 4.1.2 Name, Role, Value | ARIA validity | {pass/fail} | {count} |
| 4.1.3 Status Messages | aria-live regions | {pass/fail} | {count} |

### Accessibility Issues

<!-- List accessibility-related findings with details -->

---

## Testing Coverage

### Pages Tested
- {list_of_pages_visited_with_urls}

### Features Tested
- {list_of_features_exercised}

### Advanced Checks Performed
- Performance: {page_load_timing, resource_analysis, etc.}
- Security: {cookie_audit, xss_probes, mixed_content, etc.}
- Accessibility: {alt_text, form_labels, keyboard_nav, contrast, etc.}
- Responsive: {viewport_sizes_tested}
- Network resilience: {offline_simulation, api_failure, etc.}
- Role-based: {roles_tested_with_named_sessions}

### Not Tested / Out of Scope
- {areas_not_covered_and_why}

### Blockers
- {any_issues_that_prevented_testing_certain_areas}

---

## Evidence Artifacts

| Type | File | Issue # | Description |
|------|------|---------|-------------|
| Screenshot | `{output_dir}/screenshots/*.png` | {N} | {description} |
| Trace | `{output_dir}/traces/*.trace` | {N} | {description} |
| Trace Network | `{output_dir}/traces/*.network` | {N} | {description} |
| Video | `{output_dir}/videos/*.webm` | {N} | {description} |
| Auth State | `{output_dir}/storage/*.json` | — | Saved auth state |

---

## Recommendations

<!-- Top 3-5 most impactful recommendations based on findings -->

1. **{recommendation_1}** — addresses {severity} finding(s)
2. **{recommendation_2}** — addresses {severity} finding(s)
3. **{recommendation_3}** — addresses {severity} finding(s)

---

## Notes

{any_additional_observations_or_methodology_notes}