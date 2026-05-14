# Accessibility Testing Procedures

Detailed procedures for auditing web application accessibility using playwright-cli's JavaScript execution, snapshot inspection, and keyboard simulation capabilities. Covers WCAG 2.1 AA compliance checks.

## 1. Image Alt Text Audit

### 1.1 Missing Alt Text on Meaningful Images

```bash
playwright-cli run-code "async page => {
  const images = await page.evaluate(() => {
    return [...document.querySelectorAll('img')].map(img => ({
      src: img.src.split('/').pop() || img.src,
      alt: img.alt,
      hasAlt: img.hasAttribute('alt'),
      altEmpty: img.alt === '',
      role: img.getAttribute('role'),
      ariaLabel: img.getAttribute('aria-label'),
      decorative: img.alt === '' || img.getAttribute('role') === 'presentation' || img.getAttribute('aria-hidden') === 'true',
      width: img.naturalWidth,
      height: img.naturalHeight
    }));
  });
  return images;
}"
```

**WCAG Rule:** All meaningful images must have non-empty alt text. Decorative images should have `alt=""` or `role="presentation"`.

**Report meaningful images without alt text as Medium (Accessibility).** (Images > 50x50px are likely meaningful.)

### 1.2 Images with Placeholder Alt Text

```bash
playwright-cli run-code "async page => {
  const placeholderAlts = await page.evaluate(() => {
    const placeholders = ['image', 'photo', 'picture', 'img', 'placeholder', 'alt', 'spacer', 'icon'];
    return [...document.querySelectorAll('img[alt]')].filter(img => {
      const alt = img.alt.toLowerCase().trim();
      return placeholders.some(p => alt === p) || alt.length < 3 && alt.length > 0;
    }).map(img => ({
      src: img.src.split('/').pop(),
      alt: img.alt,
      width: img.naturalWidth
    }));
  });
  return placeholderAlts;
}"
```

**Report placeholder/meaningless alt text as Low (Accessibility).**

## 2. Form Label Audit

### 2.1 Missing Labels on Inputs

```bash
playwright-cli run-code "async page => {
  const inputs = await page.evaluate(() => {
    return [...document.querySelectorAll('input, select, textarea')].filter(el => {
      // Skip hidden, submit, button, image, reset types
      const type = el.type || 'text';
      if (['hidden', 'submit', 'button', 'image', 'reset', 'file'].includes(type)) return false;
      // Check for label association
      const hasLabel = el.labels?.length > 0;
      const hasAriaLabel = el.hasAttribute('aria-label') && el.getAttribute('aria-label').trim();
      const hasAriaLabelledBy = el.hasAttribute('aria-labelledby');
      const hasTitle = el.hasAttribute('title') && el.getAttribute('title').trim();
      return !hasLabel && !hasAriaLabel && !hasAriaLabelledBy && !hasTitle;
    }).map(el => ({
      tag: el.tagName.toLowerCase(),
      type: el.type || 'text',
      name: el.name,
      id: el.id,
      placeholder: el.placeholder
    }));
  });
  return inputs;
}"
```

**WCAG Rule:** Every form input must have an associated label (via `<label>`, `aria-label`, `aria-labelledby`, or `title`).

**Report inputs without any label mechanism as High (Accessibility).**

### 2.2 Mismatched label-for and input-id

```bash
playwright-cli run-code "async page => {
  const mismatches = await page.evaluate(() => {
    return [...document.querySelectorAll('label[for]')].filter(label => {
      const target = document.getElementById(label.for);
      return !target;  // label's for= attribute doesn't match any id
    }).map(label => ({
      labelText: label.textContent?.trim(),
      forAttr: label.for
    }));
  });
  return mismatches;
}"
```

**Report labels with broken `for` attributes as Medium (Accessibility).**

### 2.3 Placeholder Used as Label

```bash
playwright-cli run-code "async page => {
  const placeholderOnly = await page.evaluate(() => {
    return [...document.querySelectorAll('input[placeholder], textarea[placeholder]')]
      .filter(el => {
        const hasLabel = el.labels?.length > 0;
        const hasAriaLabel = el.hasAttribute('aria-label');
        return !hasLabel && !hasAriaLabel && el.placeholder;
      })
      .map(el => ({
        tag: el.tagName.toLowerCase(),
        type: el.type,
        placeholder: el.placeholder,
        name: el.name
      }));
  });
  return placeholderOnly;
}"
```

**Report inputs relying only on placeholder as Medium (Accessibility).** Placeholder disappears on focus and is not a substitute for a label.

## 3. Keyboard Navigation Audit

### 3.1 Tab Sequence Completeness

Walk the entire Tab sequence and record focus targets:

```bash
playwright-cli run-code "async page => {
  const tabSequence = [];
  let prevFocused = document.activeElement;
  for (let i = 0; i < 50; i++) {
    prevFocused.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }));
    const focused = document.activeElement;
    if (focused === prevFocused || focused === document.body) break;
    tabSequence.push({
      tag: focused.tagName,
      text: focused.textContent?.substring(0, 40),
      ariaLabel: focused.getAttribute('aria-label'),
      role: focused.getAttribute('role'),
      id: focused.id,
      type: focused.type
    });
    prevFocused = focused;
  }
  return { count: tabSequence.length, elements: tabSequence };
}"
```

**Report interactive elements not reachable via Tab as High (Accessibility).** (Buttons, links, inputs that Tab never reaches.)

### 3.2 Focus Trap Detection

```bash
# Navigate into a modal/dialog
playwright-cli click {modal_trigger_ref}
playwright-cli snapshot

# Tab 20 times within modal — should NOT escape
playwright-cli press Tab
playwright-cli press Tab
playwright-cli press Tab
playwright-cli press Tab
playwright-cli press Tab
playwright-cli press Tab
playwright-cli eval "() => document.activeElement.closest('[role=\"dialog\"]') !== null"
```

If `false` after 6+ Tabs inside a dialog, focus escaped — **High (Accessibility)**.

### 3.3 Focus Indicator Visibility

```bash
playwright-cli press Tab
playwright-cli screenshot --filename={output_dir}/screenshots/focus-indicator.png

# Check computed focus styles
playwright-cli run-code "async page => {
  const focused = document.activeElement;
  const outline = getComputedStyle(focused).outline;
  const outlineWidth = getComputedStyle(focused).outlineWidth;
  const boxShadow = getComputedStyle(focused).boxShadow;
  return {
    element: focused.tagName + '#' + focused.id,
    outline: outline,
    outlineWidth: outlineWidth,
    boxShadow: boxShadow,
    hasVisibleFocus: outlineWidth !== '0px' || boxShadow !== 'none'
  };
}"
```

**Report invisible focus indicators (outline: none, outline-width: 0, no box-shadow) as Medium (Accessibility).**

### 3.4 Skip Navigation Link

```bash
playwright-cli run-code "async page => {
  const firstLink = document.querySelector('a');
  return {
    href: firstLink?.href,
    text: firstLink?.textContent?.trim(),
    isSkipLink: firstLink?.textContent?.toLowerCase().includes('skip') || firstLink?.href?.includes('#main') || firstLink?.href?.includes('#content')
  };
}"
```

**Report missing skip navigation link on pages with navigation menus as Medium (Accessibility).** Not a strict WCAG requirement but best practice.

## 4. ARIA Audit

### 4.1 Invalid ARIA Roles

```bash
playwright-cli run-code "async page => {
  const validRoles = ['alert', 'alertdialog', 'application', 'article', 'banner', 'button', 'cell', 'checkbox', 'columnheader', 'combobox', 'complementary', 'contentinfo', 'definition', 'dialog', 'directory', 'document', 'feed', 'figure', 'form', 'grid', 'gridcell', 'group', 'heading', 'img', 'link', 'list', 'listbox', 'listitem', 'log', 'main', 'marquee', 'math', 'menu', 'menuitem', 'menuitemcheckbox', 'menuitemradio', 'navigation', 'none', 'note', 'option', 'presentation', 'progressbar', 'radio', 'radiogroup', 'region', 'row', 'rowgroup', 'rowheader', 'search', 'searchbox', 'separator', 'slider', 'spinbutton', 'status', 'switch', 'table', 'tablist', 'tabpanel', 'term', 'textbox', 'timer', 'toolbar', 'tooltip', 'tree', 'treegrid', 'treeitem'];
  return [...document.querySelectorAll('[role]')].filter(el => !validRoles.includes(el.getAttribute('role'))).map(el => ({
    tag: el.tagName,
    role: el.getAttribute('role'),
    id: el.id,
    text: el.textContent?.substring(0, 30)
  }));
}"
```

**Report invalid ARIA roles as Medium (Accessibility).**

### 4.2 Missing ARIA on Dynamic Content

```bash
playwright-cli run-code "async page => {
  // Check for live regions on dynamic content areas
  const liveRegions = document.querySelectorAll('[aria-live]');
  const dynamicContainers = document.querySelectorAll('[id*=\"status\"], [id*=\"result\"], [id*=\"message\"], [id*=\"notification\"], [id*=\"alert\"], [class*=\"status\"], [class*=\"result\"], [class*=\"message\"]');
  return {
    liveRegionsCount: liveRegions.length,
    liveRegionDetails: [...liveRegions].map(el => ({ id: el.id, ariaLive: el.getAttribute('aria-live'), text: el.textContent?.substring(0, 30) }),
    dynamicContainersWithoutLive: [...dynamicContainers].filter(el => !el.hasAttribute('aria-live')).map(el => ({ id: el.id, class: el.className?.substring(0, 30) }))
  };
}"
```

**Report dynamic content containers without aria-live as Medium (Accessibility).**

### 4.3 ARIA State Checks

```bash
playwright-cli run-code "async page => {
  // Elements with aria-expanded should be interactive
  const expandedEls = [...document.querySelectorAll('[aria-expanded]')].map(el => ({
    tag: el.tagName,
    ariaExpanded: el.getAttribute('aria-expanded'),
    isInteractive: el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button' || el.tabIndex >= 0,
    id: el.id
  }));

  // Elements with aria-selected should be in a tablist/listbox
  const selectedEls = [...document.querySelectorAll('[aria-selected]')].map(el => ({
    tag: el.tagName,
    ariaSelected: el.getAttribute('aria-selected'),
    parentRole: el.parentElement?.getAttribute('role'),
    id: el.id
  }));

  return { expandedEls, selectedEls };
}"
```

**Report aria-expanded on non-interactive elements as High (Accessibility).**

## 5. Color Contrast Audit

### 5.1 Programmatically Check Contrast

```bash
playwright-cli run-code "async page => {
  function getLuminance(r, g, b) {
    const [rs, gs, bs] = [r, g, b].map(c => {
      c = c / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * rs + 0.7152 * gs + 0.0722 * bs;
  }

  function parseColor(color) {
    const match = color.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
    if (!match) return null;
    return { r: parseInt(match[1]), g: parseInt(match[2]), b: parseInt(match[3]) };
  }

  function contrastRatio(fg, bg) {
    const l1 = getLuminance(fg.r, fg.g, fg.b);
    const l2 = getLuminance(bg.r, bg.g, bg.b);
    const lighter = Math.max(l1, l2);
    const darker = Math.min(l1, l2);
    return (lighter + 0.05) / (darker + 0.05);
  }

  const issues = [];
  const textElements = document.querySelectorAll('p, span, a, h1, h2, h3, h4, h5, h6, label, button, td, th, li');
  for (const el of textElements) {
    const style = getComputedStyle(el);
    const fg = parseColor(style.color);
    const bg = parseColor(style.backgroundColor);
    if (!fg || !bg || style.backgroundColor === 'rgba(0, 0, 0, 0)' || style.backgroundColor === 'transparent') continue;
    const ratio = contrastRatio(fg, bg);
    const fontSize = parseFloat(style.fontSize);
    const fontWeight = parseFloat(style.fontWeight);
    const isLargeText = fontSize >= 18 || (fontSize >= 14 && fontWeight >= 700);
    const minRatio = isLargeText ? 3.0 : 4.5;  // WCAG AA
    if (ratio < minRatio) {
      issues.push({
        tag: el.tagName,
        text: el.textContent?.substring(0, 40),
        ratio: Math.round(ratio * 100) / 100,
        minRequired: minRatio,
        fontSize: fontSize,
        fontWeight: fontWeight,
        fgColor: style.color,
        bgColor: style.backgroundColor
      });
    }
  }
  return issues.slice(0, 30);  // Limit output
}"
```

**WCAG AA Thresholds:**
- Normal text (< 18px, or < 14px bold): contrast ratio >= 4.5
- Large text (>= 18px, or >= 14px bold): contrast ratio >= 3.0

**Report contrast ratio < 4.5 for normal text as Medium (Accessibility).**
**Report contrast ratio < 3.0 for large text as High (Accessibility).**
**Report contrast ratio < 3.0 for any text as Critical (Accessibility).**

## 6. Heading Structure Audit

### 6.1 Heading Hierarchy

```bash
playwright-cli run-code "async page => {
  const headings = [...document.querySelectorAll('h1, h2, h3, h4, h5, h6')].map(h => ({
    level: parseInt(h.tagName[1]),
    text: h.textContent?.trim().substring(0, 50),
    id: h.id
  }));

  const issues = [];
  // Check: only one h1 per page
  const h1Count = headings.filter(h => h.level === 1).length;
  if (h1Count > 1) issues.push('Multiple h1 headings found: ' + h1Count);
  if (h1Count === 0) issues.push('No h1 heading found');

  // Check: heading levels don't skip (e.g., h1 -> h3 without h2)
  for (let i = 1; i < headings.length; i++) {
    const skip = headings[i].level - headings[i-1].level;
    if (skip > 1) issues.push('Heading skip: h' + headings[i-1].level + ' -> h' + headings[i].level + ' ("' + headings[i].text + '")');
  }

  return { headings, issues };
}"
```

**Report heading level skips as Medium (Accessibility).**
**Report missing h1 as Low (Accessibility).**
**Report multiple h1 as Low (Accessibility).**

## 7. Link Audit

### 7.1 Ambiguous Link Text

```bash
playwright-cli run-code "async page => {
  const ambiguousTexts = ['click here', 'learn more', 'read more', 'more info', 'see more', 'details', 'here', 'link', 'go', 'download'];
  const links = [...document.querySelectorAll('a')].filter(a => {
    const text = a.textContent?.trim().toLowerCase();
    return ambiguousTexts.includes(text) && !a.hasAttribute('aria-label') && !a.hasAttribute('title');
  }).map(a => ({
    text: a.textContent?.trim(),
    href: a.href.split('/').pop(),
    hasAriaLabel: a.hasAttribute('aria-label')
  }));
  return links;
}"
```

**Report ambiguous link text without aria-label as Low (Accessibility).**

### 7.2 Links Without Visible Focus State

See Section 3.3 — Tab to each link and screenshot.

### 7.3 Broken Links (404)

```bash
playwright-cli run-code "async page => {
  const links = [...document.querySelectorAll('a[href]')].map(a => ({
    text: a.textContent?.trim().substring(0, 30),
    href: a.href,
    isExternal: !a.href.startsWith(window.location.origin)
  }));
  return links;
}"
```

Then visit each internal link and check for 404s (this is part of functional testing, but also accessibility — broken links prevent access).

## 8. Semantic Structure Audit

### 8.1 Landmark Regions

```bash
playwright-cli run-code "async page => {
  const landmarks = {
    header: document.querySelectorAll('header, [role=\"banner\"]').length,
    nav: document.querySelectorAll('nav, [role=\"navigation\"]').length,
    main: document.querySelectorAll('main, [role=\"main\"]').length,
    footer: document.querySelectorAll('footer, [role=\"contentinfo\"]').length,
    aside: document.querySelectorAll('aside, [role=\"complementary\"]').length,
    search: document.querySelectorAll('[role=\"search\"]').length,
    form: document.querySelectorAll('form, [role=\"form\"]').length
  };
  return landmarks;
}"
```

**Report pages without `<main>` landmark as Medium (Accessibility).** Screen reader users rely on landmarks for navigation.

### 8.2 Lists Without Proper Markup

```bash
playwright-cli run-code "async page => {
  // Find div/span elements used as list items without ul/ol parent
  const fakeLists = [...document.querySelectorAll('div, span')].filter(el => {
    const style = getComputedStyle(el);
    return style.display === 'list-item' || style.listStyleType !== 'none';
  }).filter(el => !el.closest('ul, ol, [role=\"list\"]')).length;

  // Find visual bullet patterns without semantic markup
  const bulletPatterns = [...document.querySelectorAll('div > div, div > span')].filter(el => {
    return el.textContent?.match(/^[•·▪▸►→]\s/) || el.previousElementSibling?.textContent?.match(/^[•·▪▸►→]\s/);
  }).length;

  return { fakeLists, approximateVisualLists: bulletPatterns };
}"
```

**Report visual lists without `<ul>/<ol>` markup as Low (Accessibility).**

## 9. Accessibility Testing Checklist

| # | Check | Command | WCAG Criterion | Severity If Found |
|---|-------|---------|----------------|-------------------|
| 1 | Meaningful images: alt text | `run-code img audit` | 1.1.1 | Medium |
| 2 | Form inputs: labels | `run-code label audit` | 1.3.1, 4.1.2 | High |
| 3 | Tab sequence: all interactive reachable | `run-code Tab sequence` | 2.1.1 | High |
| 4 | Focus trap: in dialogs | `press Tab + eval` | 2.4.3 | High |
| 5 | Focus indicators: visible | `press Tab + screenshot + eval` | 2.4.7 | Medium |
| 6 | ARIA roles: valid | `run-code role audit` | 4.1.2 | Medium |
| 7 | Color contrast: meets AA | `run-code contrast audit` | 1.4.3 | Medium/High |
| 8 | Heading hierarchy: no skips | `run-code heading audit` | 1.3.1 | Medium |
| 9 | Landmark regions: main present | `run-code landmark audit` | 1.3.1 | Medium |
| 10 | Link text: not ambiguous | `run-code link audit` | 2.4.4 | Low |
| 11 | aria-live: on dynamic content | `run-code live region audit` | 4.1.3 | Medium |
| 12 | Skip nav link: present | `eval first link` | 2.4.1 | Low (best practice) |
| 13 | Placeholder-only labels | `run-code placeholder audit` | 1.3.1 | Medium |
| 14 | Invalid ARIA expanded on non-interactive | `run-code aria state audit` | 4.1.2 | High |