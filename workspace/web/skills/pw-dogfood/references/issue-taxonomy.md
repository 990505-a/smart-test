# Issue Taxonomy (Enhanced for PW-Dogfood)

Use this taxonomy to classify issues found during QA testing. This version extends the basic dogfood taxonomy with **Security**, **Performance**, and **Accessibility** categories that playwright-cli enables.

## Severity Levels

### Critical
The issue makes a core feature completely unusable, causes data loss, or exposes a security vulnerability.

**Examples:**
- Application crashes or shows a blank white page
- Form submission silently loses user data
- Authentication is completely broken (can't log in at all)
- Payment flow fails and charges the user without completing the order
- Reflected or stored XSS vulnerability confirmed via eval
- Authentication tokens exposed in localStorage without encryption
- Session cookies lack httpOnly/secure flags enabling theft
- API returns user data without auth check (IDOR)

### High
The issue significantly impairs functionality but a workaround may exist.

**Examples:**
- A key button does nothing when clicked (but refreshing fixes it)
- Search returns no results for valid queries
- Form validation rejects valid input
- Page loads but critical content is missing or garbled
- Navigation link leads to a 404 or wrong page
- Uncaught JavaScript exceptions in the console on core pages
- Page takes >10s to become interactive (FCP > 5s)
- Mixed content warnings (HTTP resources on HTTPS page)
- Missing CSRF protection on state-changing forms

### Medium
The issue is noticeable and affects user experience but doesn't block core functionality.

**Examples:**
- Layout is misaligned or overlapping on certain screen sections
- Images fail to load (broken image icons)
- Slow performance (visible loading delays 3-10 seconds)
- Form field lacks proper validation feedback (no error message on bad input)
- Console warnings that suggest deprecated or misconfigured features
- Inconsistent styling between similar pages
- Cookies missing sameSite=Lax/Strict (medium risk)
- localStorage storing non-sensitive data without cleanup
- Suboptimal resource loading (no lazy loading, unoptimized images)

### Low
Minor polish issues that don't affect functionality.

**Examples:**
- Typos or grammatical errors in text content
- Minor spacing or alignment inconsistencies
- Placeholder text left in production ("Lorem ipsum")
- Favicon missing
- Console info/debug messages that shouldn't be in production
- Subtle color contrast issues that don't fail WCAG requirements
- Excessive console.log output from development
- Unminified CSS/JS served in production

## Categories

### Functional
Issues where features don't work as expected.

- Buttons/links that don't respond
- Forms that don't submit or submit incorrectly
- Broken user flows (can't complete a multi-step process)
- Incorrect data displayed
- Features that work partially
- State not preserved across navigation (back/forward)
- Cart/session data lost on reload
- Pagination or filtering broken

### Visual
Issues with the visual presentation of the page.

- Layout problems (overlapping elements, broken grids)
- Broken images or missing media
- Styling inconsistencies
- Responsive design failures at specific viewport widths
- Z-index issues (elements hidden behind others)
- Text overflow or truncation
- Elements rendering outside viewport (overflow issues)
- Dark mode / theme inconsistencies

### Accessibility
Issues that prevent or hinder access for users with disabilities.

- Missing alt text on meaningful images (detected via eval)
- Poor color contrast (fails WCAG AA)
- Elements not reachable via keyboard navigation (Tab sequence gaps)
- Missing form labels or ARIA attributes (detected via eval)
- Focus indicators missing or unclear
- Screen reader incompatible content
- Focus trap in modals/dialogs (user can't Tab out)
- aria-live regions missing for dynamic updates

### Console
Issues detected through JavaScript console output.

- Uncaught exceptions and unhandled promise rejections
- Failed network requests (4xx, 5xx errors visible in console)
- Deprecation warnings
- CORS errors
- Mixed content warnings (HTTP resources on HTTPS page)
- Excessive console.log output left from development
- React/Vue/Angular framework-specific warnings

### UX (User Experience)
Issues where functionality works but the experience is poor.

- Confusing navigation or information architecture
- Missing loading indicators (user doesn't know something is happening)
- No feedback after user actions (button click with no visible result)
- Inconsistent interaction patterns across pages
- Missing confirmation dialogs for destructive actions
- Poor error messages that don't help the user recover
- Auto-focus not set on first input in forms
- No way to undo or reverse actions

### Security
Issues that expose vulnerabilities or leak sensitive data. playwright-cli's cookie/localStorage/eval commands make these detectable.

- XSS: script injection via input fields renders as executable HTML
- Cookies missing httpOnly, secure, or sameSite flags
- Auth tokens or PII stored in localStorage (accessible to XSS)
- Mixed content: HTTP scripts/images loaded on HTTPS pages
- CORS misconfiguration allowing unauthorized origins
- Sensitive data in URL query parameters (visible in logs)
- Missing CSRF tokens on POST forms
- Open redirect vulnerabilities
- API endpoints returning data without proper auth
- Developer tools/debug endpoints accessible in production

### Performance
Issues affecting page speed or resource efficiency. playwright-cli's performance.timing and network commands make these measurable.

- FCP (First Contentful Paint) > 3 seconds
- TTI (Time to Interactive) > 5 seconds
- Unoptimized images (transferSize > 200KB without lazy loading)
- Excessive DOM nodes (>1500 elements)
- Render-blocking resources (CSS/JS in <head> without async/defer)
- No caching headers on static resources (Cache-Control missing)
- Duplicate resource loads (same JS/CSS loaded multiple times)
- Bundle size > 500KB without code splitting
- localStorage usage > 5MB (risk of quota exceeded errors)

### Content
Issues with the text, media, or information on the page.

- Typos and grammatical errors
- Placeholder/dummy content in production
- Outdated information
- Missing content (empty sections)
- Broken or dead links to external resources
- Incorrect or misleading labels
- Inconsistent terminology across pages
- Missing legal/compliance text where required