# Performance Testing Procedures

Detailed procedures for measuring and diagnosing web application performance using playwright-cli's JavaScript execution and network inspection capabilities.

## 1. Page Load Timing

### 1.1 Navigation Timing API

Capture full page load lifecycle metrics:

```bash
playwright-cli run-code "async page => {
  const timing = await page.evaluate(() => {
    const t = performance.timing;
    return {
      dns: t.domainLookupEnd - t.domainLookupStart,
      tcp: t.connectEnd - t.connectStart,
      tls: t.secureConnectionStart > 0 ? t.connectEnd - t.secureConnectionStart : 0,
      ttfb: t.responseStart - t.requestStart,
      download: t.responseEnd - t.responseStart,
      domParsing: t.domInteractive - t.domLoading,
      domComplete: t.domComplete - t.domLoading,
      loadEvent: t.loadEventEnd - t.loadEventStart,
      total: t.loadEventEnd - t.navigationStart,
      navigationType: t.type
    };
  });
  return timing;
}"
```

**Thresholds:**
- DNS: < 50ms (local cache), < 200ms (remote)
- TCP: < 100ms
- TLS: < 200ms
- TTFB: < 500ms (good), < 1000ms (acceptable), > 1000ms (issue)
- Download: depends on content size, but < 2000ms for typical pages
- DOM parsing: < 1000ms
- Total load: < 3000ms (good), < 5000ms (acceptable), > 5000ms (issue — report as Medium)

### 1.2 Core Web Vitals (Approximate)

Playwright doesn't directly measure Core Web Vitals, but we can approximate:

```bash
playwright-cli run-code "async page => {
  // FCP approximation — first paint time
  const paints = await page.evaluate(() => {
    const entries = performance.getEntriesByType('paint');
    return entries.map(e => ({ name: e.name, startTime: e.startTime }));
  });

  // LCP approximation — largest contentful paint
  const lcp = await page.evaluate(() => {
    const entries = performance.getEntriesByType('largest-contentful-paint');
    return entries.length > 0 ? { startTime: entries[entries.length - 1].startTime, size: entries[entries.length - 1].size, element: entries[entries.length - 1].element?.tagName } : null;
  });

  return { paints, lcp };
}"
```

**FCP Thresholds:**
- < 1.8s: Good
- 1.8s - 3.0s: Needs Improvement (report as Medium)
- > 3.0s: Poor (report as High)

## 2. Resource Analysis

### 2.1 Resource Inventory

List all loaded resources with size and timing:

```bash
playwright-cli run-code "async page => {
  const resources = await page.evaluate(() => {
    return performance.getEntriesByType('resource').map(r => ({
      name: r.name.split('/').pop() || r.name,
      type: r.initiatorType,
      size: r.transferSize,
      encodedSize: r.encodedBodySize,
      decodedSize: r.decodedBodySize,
      duration: Math.round(r.duration),
      ttfb: Math.round(r.responseStart - r.requestStart),
      cached: r.transferSize === 0
    }));
  });
  return resources;
}"
```

### 2.2 Large Resources

Identify resources exceeding size thresholds:

```bash
playwright-cli run-code "async page => {
  const large = await page.evaluate(() => {
    const THRESHOLD = 100000; // 100KB
    return performance.getEntriesByType('resource')
      .filter(r => r.transferSize > THRESHOLD)
      .sort((a, b) => b.transferSize - a.transferSize)
      .map(r => ({
        name: r.name.split('/').pop(),
        sizeKB: Math.round(r.transferSize / 1024),
        type: r.initiatorType,
        duration: Math.round(r.duration)
      }));
  });
  return large;
}"
```

**Report any resource > 200KB as Medium (Performance).** Report > 500KB as High.

### 2.3 Slow Resources

Identify resources with excessive load times:

```bash
playwright-cli run-code "async page => {
  const slow = await page.evaluate(() => {
    const THRESHOLD = 2000; // 2 seconds
    return performance.getEntriesByType('resource')
      .filter(r => r.duration > THRESHOLD)
      .sort((a, b) => b.duration - a.duration)
      .map(r => ({
        name: r.name.split('/').pop(),
        duration: Math.round(r.duration),
        type: r.initiatorType,
        size: Math.round(r.transferSize / 1024)
      }));
  });
  return slow;
}"
```

## 3. DOM Complexity

### 3.1 Node Count

```bash
playwright-cli eval "() => document.querySelectorAll('*').length"
```

**Thresholds:**
- < 800 nodes: Good
- 800 - 1500: Acceptable
- > 1500: Report as Medium (Performance) — "Excessive DOM complexity"
- > 3000: Report as High

### 3.2 Deeply Nested Elements

```bash
playwright-cli run-code "async page => {
  const deep = await page.evaluate(() => {
    let maxDepth = 0;
    const deepElements = [];
    function walk(el, depth) {
      if (depth > maxDepth) maxDepth = depth;
      if (depth > 15) deepElements.push({ tag: el.tagName, id: el.id, depth });
      for (const child of el.children) walk(child, depth + 1);
    }
    walk(document.body, 0);
    return { maxDepth, deepElements };
  });
  return deep;
}"
```

**Report nesting depth > 15 as Low (Performance).**

### 3.3 Shadow DOM Usage

```bash
playwright-cli eval "() => [...document.querySelectorAll('*')].filter(e => e.shadowRoot).length"
```

Useful context — shadow DOM can complicate accessibility testing.

## 4. Memory & Runtime

### 4.1 JS Heap Size

```bash
playwright-cli run-code "async page => {
  const mem = await page.evaluate(() => {
    if (performance.memory) {
      return {
        usedJSHeapSizeMB: Math.round(performance.memory.usedJSHeapSize / 1048576),
        totalJSHeapSizeMB: Math.round(performance.memory.totalJSHeapSize / 1048576),
        jsHeapSizeLimitMB: Math.round(performance.memory.jsHeapSizeLimit / 1048576)
      };
    }
    return 'performance.memory not available (non-Chrome)';
  });
  return mem;
}"
```

**Report usedJSHeapSize > 50MB as Medium (Performance).** Report > 100MB as High.

### 4.2 Long Tasks

Check for tasks blocking the main thread > 50ms:

```bash
playwright-cli run-code "async page => {
  const longTasks = await page.evaluate(() => {
    const observer = new PerformanceObserver(list => {
      window.__longTasks = list.getEntries();
    });
    observer.observe({ type: 'longtask', buffered: true });
    // Return buffered entries if available
    return window.__longTasks || performance.getEntriesByType('longtask') || [];
  });
  return longTasks;
}"
```

## 5. Network Waterfall

### 5.1 Capture Network Log

```bash
playwright-cli tracing-start

playwright-cli goto {target_url}
playwright-cli run-code "async page => {
  await page.waitForLoadState('networkidle');
}"

playwright-cli tracing-stop
```

The `.network` trace file contains the full waterfall with timing for each request. Copy to output:
```bash
cp .playwright-cli/traces/trace-*.network {output_dir}/traces/performance-waterfall.network
```

### 5.2 Failed/Slow Requests

```bash
playwright-cli network
```

Look for:
- 4xx responses — missing resources or auth failures
- 5xx responses — server errors
- Requests taking > 3s — backend performance issues
- Duplicate requests — same URL loaded multiple times

## 6. Caching Headers

Check if static resources have proper caching:

```bash
playwright-cli run-code "async page => {
  const resources = await page.evaluate(() => {
    return performance.getEntriesByType('resource')
      .filter(r => r.initiatorType === 'link' || r.initiatorType === 'script' || r.initiatorType === 'img')
      .map(r => ({
        name: r.name.split('/').pop(),
        type: r.initiatorType,
        cached: r.transferSize === 0,
        size: r.transferSize
      }));
  });
  return resources;
}"
```

Resources that are never cached (transferSize > 0 on reload) may lack Cache-Control headers — report as Low (Performance).

## 7. Performance Testing Checklist

When performing performance testing, check each item:

| # | Check | Command | Threshold | Report If |
|---|-------|---------|-----------|-----------|
| 1 | Total page load time | Navigation timing API | < 5s | > 5s |
| 2 | TTFB | Navigation timing API | < 1s | > 1s |
| 3 | FCP | Paint entries | < 1.8s | > 3s |
| 4 | DOM node count | `eval "document.querySelectorAll('*').length"` | < 1500 | > 1500 |
| 5 | Large resources (>200KB) | Resource inventory | 0 | > 0 found |
| 6 | Slow resources (>2s) | Slow resource check | 0 | > 0 found |
| 7 | JS heap size | `performance.memory` | < 50MB | > 50MB |
| 8 | Failed network requests | `playwright-cli network` | 0 | > 0 4xx/5xx |
| 9 | Duplicate requests | Network trace | 0 | Same URL loaded > 2x |
| 10 | Cacheable resources cached | Reload resource check | All static cached | Static not cached |