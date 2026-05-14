# Security Checks Procedures

Detailed procedures for auditing web application security using playwright-cli's cookie inspection, storage state, JavaScript execution, and network interception capabilities.

## 1. Cookie Security Audit

### 1.1 List All Cookies and Check Flags

```bash
playwright-cli cookie-list
```

For each cookie, verify:

| Flag | What It Prevents | Required For |
|------|------------------|-------------|
| `httpOnly` | XSS stealing cookie via `document.cookie` | ALL session/auth cookies |
| `secure` | Cookie sent over HTTP (intercepted) | ALL cookies on HTTPS sites |
| `sameSite=Lax` or `Strict` | CSRF attacks via cross-origin requests | ALL session cookies |

**Report missing httpOnly on session/auth cookies as Critical (Security).**
**Report missing secure flag on HTTPS sites as High (Security).**
**Report sameSite not set or sameSite=None without secure as High (Security).**

### 1.2 Check for Sensitive Data in Cookies

```bash
playwright-cli run-code "async page => {
  const cookies = await page.context().cookies();
  return cookies.map(c => ({
    name: c.name,
    valueLength: c.value.length,
    containsEmail: c.value.includes('@'),
    containsTokenPattern: /^(eyJ|Bearer|token_|session)/.test(c.value),
    httpOnly: c.httpOnly,
    secure: c.secure,
    sameSite: c.sameSite,
    domain: c.domain,
    expires: c.expires > 0 ? new Date(c.expires * 1000).toISOString() : 'session'
  }));
}"
```

Look for:
- Email addresses in cookie values (PII leakage)
- JWT patterns (`eyJ` = base64-encoded JSON header) without httpOnly
- Session tokens with long expiry (> 30 days without refresh)
- Cookies set on overly broad domains (`.example.com` when should be `app.example.com`)

### 1.3 Check Cookie Scope

```bash
playwright-cli cookie-list --domain={target_domain}
```

Verify:
- Auth cookies scoped to the specific subdomain, not parent domain
- No cookies with path `/` that should be scoped tighter
- No third-party cookies from unfamiliar domains

## 2. localStorage / sessionStorage Security

### 2.1 Inspect localStorage for Sensitive Data

```bash
playwright-cli localstorage-list
```

**Critical finding:** Auth tokens, passwords, API keys, or PII stored in localStorage. localStorage is:
- Accessible to any JS on the page (XSS can read it)
- Never sent to server (can't be validated)
- Persisted indefinitely (survives browser restart)
- Per-origin (any subdomain on same origin can access)

```bash
# Check for specific sensitive patterns
playwright-cli run-code "async page => {
  const sensitivePatterns = ['token', 'auth', 'password', 'secret', 'key', 'credential', 'jwt', 'session', 'api_key'];
  const items = await page.evaluate(() => {
    return Object.entries(localStorage).map(([k, v]) => ({ key: k, valueLength: v.length, valuePreview: v.substring(0, 50) }));
  });
  return items.filter(i => sensitivePatterns.some(p => i.key.toLowerCase().includes(p)));
}"
```

**Report any auth token in localStorage without httpOnly equivalent as Critical (Security).**
**Report PII (email, phone, address) in localStorage as High (Security).**

### 2.2 Inspect sessionStorage

```bash
playwright-cli sessionstorage-list
```

sessionStorage is slightly safer (cleared on tab close), but same XSS risk while tab is open. Apply same checks.

### 2.3 Check IndexedDB

```bash
playwright-cli run-code "async page => {
  const dbs = await page.evaluate(async () => {
    const databases = await indexedDB.databases();
    return databases;
  });
  return dbs;
}"
```

IndexedDB can store large amounts of data — check if sensitive data is stored there.

## 3. XSS (Cross-Site Scripting) Probing

### 3.1 Input Field Injection

Test if input fields properly sanitize HTML/JS content:

```bash
# Inject script tag into text fields
playwright-cli fill eN "<script>alert('xss-test-1')</script>"
playwright-cli click {submit_ref}
playwright-cli snapshot

# Check if the script tag rendered as executable HTML
playwright-cli eval "() => document.body.innerHTML.includes('<script>alert')"
```

If `true`, this is a **Critical (Security)** finding — stored XSS.

```bash
# Inject event handler
playwright-cli fill eN "<img src=x onerror=alert('xss-test-2')>"
playwright-cli click {submit_ref}
playwright-cli eval "() => document.body.innerHTML.includes('onerror=alert')"
```

### 3.2 URL Parameter Injection

```bash
# Test reflected XSS via URL
playwright-cli goto "https://{target}/search?q=<script>alert('xss')</script>"
playwright-cli eval "() => document.body.innerHTML.includes('<script>alert')"
```

### 3.3 Template Injection

```bash
# Test template literal injection (Vue/Angular)
playwright-cli fill eN "{{constructor.constructor('return alert(1)')()}}"
playwright-cli click {submit_ref}
playwright-cli console error   # Check for template execution errors
```

**Report confirmed XSS as Critical (Security).** Report unsuccessful but unsanitized input as High (Defense in Depth).

## 4. Mixed Content Check

### 4.1 HTTP Resources on HTTPS Pages

```bash
playwright-cli console warning
```

Mixed content warnings indicate HTTP resources loaded on an HTTPS page. These are:
- Security risk (HTTP resources can be tampered)
- Blocked by browsers in most cases (active mixed content)
- May cause visual/functional breakage

```bash
# Specifically check for insecure resource URLs
playwright-cli run-code "async page => {
  const insecure = await page.evaluate(() => {
    const links = [...document.querySelectorAll('link[href^=\"http://\"]')].map(e => e.href);
    const scripts = [...document.querySelectorAll('script[src^=\"http://\"]')].map(e => e.src);
    const images = [...document.querySelectorAll('img[src^=\"http://\"]')].map(e => e.src);
    const iframes = [...document.querySelectorAll('iframe[src^=\"http://\"]')].map(e => e.src);
    return { links, scripts, images, iframes };
  });
  return insecure;
}"
```

**Report active mixed content (scripts, iframes) as Critical (Security).**
**Report passive mixed content (images, stylesheets) as High (Security).**

## 5. CORS & API Security

### 5.1 Check API Response Headers

```bash
playwright-cli network
```

Look for:
- `Access-Control-Allow-Origin: *` on authenticated APIs (High)
- `Access-Control-Allow-Credentials: true` with `Allow-Origin: *` (Critical — violates CORS spec)
- Missing `X-Content-Type-Options: nosniff` (Low)
- Missing `X-Frame-Options: DENY/SAMEORIGIN` (Medium — clickjacking risk)
- Missing `Content-Security-Policy` header (Medium)

### 5.2 API Auth Verification

```bash
# Test if APIs require auth
playwright-cli state-save {output_dir}/storage/authenticated.json

# Clear auth state and try API call
playwright-cli cookie-clear
playwright-cli localstorage-clear

# Navigate to a page that makes API calls
playwright-cli goto {page_with_api_call}
playwright-cli network    # Do APIs return 401 or 200?

# Restore auth state
playwright-cli state-load {output_dir}/storage/authenticated.json
```

**Report APIs returning user data without auth as Critical (Security).**

## 6. CSRF (Cross-Site Request Forgery) Checks

### 6.1 Check for CSRF Tokens

```bash
playwright-cli run-code "async page => {
  const forms = await page.evaluate(() => {
    return [...document.querySelectorAll('form[method=\"POST\"], form[method=\"post\"]')].map(form => {
      const csrfInput = form.querySelector('input[name*=\"csrf\"], input[name*=\"token\"], input[name*=\"_token\"]');
      return {
        id: form.id || form.action,
        hasCsrf: !!csrfInput,
        csrfName: csrfInput?.name,
        csrfValue: csrfInput?.value?.substring(0, 20)
      };
    });
  });
  return forms;
}"
```

**Report POST forms without CSRF tokens as High (Security).**

## 7. Open Redirect Check

### 7.1 Redirect Parameter Injection

```bash
# Test if redirect URLs accept external domains
playwright-cli goto "https://{target}/login?redirect=https://evil.com"
playwright-cli snapshot

# Check current URL
playwright-cli eval "() => window.location.href"
```

If the browser redirects to `evil.com`, this is a **High (Security)** finding.

## 8. Information Disclosure

### 8.1 Check for Debug/Dev Endpoints

```bash
# Common debug endpoints to probe
playwright-cli goto "https://{target}/_debug"
playwright-cli goto "https://{target}/.env"
playwright-cli goto "https://{target}/swagger"
playwright-cli goto "https://{target}/api/docs"
playwright-cli goto "https://{target}/graphql"
playwright-cli console error
```

**Report accessible debug/admin endpoints in production as Critical (Security).**

### 8.2 Server Version Disclosure

```bash
# Check response headers via network
playwright-cli network
```

Look for:
- `Server: Apache/2.4.51` — reveals exact server version
- `X-Powered-By: Express` — reveals framework
- `X-AspNet-Version: 4.0.30319` — reveals runtime version

**Report server version headers as Low (Security — Information Disclosure).**

### 8.3 Console Information Leakage

```bash
playwright-cli console
```

Look for:
- Stack traces with file paths
- API endpoint URLs logged
- User IDs, session IDs printed to console
- Environment variable values

**Report sensitive data in console.log as Medium (Security).**

### 8.4 Source Map Exposure

```bash
playwright-cli run-code "async page => {
  const sourceMaps = await page.evaluate(() => {
    const scripts = [...document.querySelectorAll('script[src]')];
    return scripts.map(s => s.src + '.map').filter(async url => {
      try { const r = await fetch(url); return r.ok; } catch { return false; }
    });
  });
  return sourceMaps;
}"
```

**Report accessible source maps in production as Medium (Security).**

## 9. Authentication & Session Security

### 9.1 Session Handling

```bash
# Login and capture session state
playwright-cli open --browser=chromium {login_url}
playwright-cli snapshot
playwright-cli fill {email_ref} "test@example.com"
playwright-cli fill {password_ref} "testpass"
playwright-cli click {login_ref}
playwright-cli cookie-list            # What session cookies were set?
playwright-cli localstorage-list      # What tokens were stored?

# Test session expiry
playwright-cli run-code "async page => {
  // Check cookie expiry
  const cookies = await page.context().cookies();
  const sessionCookies = cookies.filter(c => c.name.toLowerCase().includes('session') || c.name.toLowerCase().includes('auth'));
  return sessionCookies.map(c => ({
    name: c.name,
    expires: c.expires,
    isSessionCookie: c.expires === -1 || c.expires === 0,
    httpOnly: c.httpOnly,
    secure: c.secure,
    sameSite: c.sameSite
  }));
}"
```

**Report session cookies with expiry > 30 days as Medium (Security).**
**Report session cookies without httpOnly as Critical (Security).**

### 9.2 Password Field Security

```bash
playwright-cli run-code "async page => {
  const pwFields = await page.evaluate(() => {
    return [...document.querySelectorAll('input[type=\"password\"]')].map(f => ({
      autocomplete: f.autocomplete,
      name: f.name,
      id: f.id,
      maxLength: f.maxLength,
      hasMinLength: f.minLength > 0,
      formId: f.form?.id
    }));
  });
  return pwFields;
}"
```

**Report password fields with `autocomplete=on` or `autocomplete=current-password` on login forms as Low (Security).**
**Report password fields lacking maxLength as Low.**

## 10. Security Testing Checklist

| # | Check | Command | Severity If Found |
|---|-------|---------|-------------------|
| 1 | Auth cookies: httpOnly flag | `cookie-list` | Critical if missing |
| 2 | All cookies: secure flag on HTTPS | `cookie-list` | High if missing |
| 3 | Session cookies: sameSite flag | `cookie-list` | High if None without secure |
| 4 | localStorage: auth tokens present | `localstorage-list` | Critical if found |
| 5 | localStorage: PII present | `localstorage-list` | High if found |
| 6 | XSS: script injection renders | `fill + eval` | Critical if confirmed |
| 7 | XSS: event handler injection | `fill + eval` | Critical if confirmed |
| 8 | Mixed content: HTTP on HTTPS | `console warning` + `eval` | Critical (active) / High (passive) |
| 9 | CORS: Allow-Origin * on auth APIs | `network` | High |
| 10 | POST forms: CSRF tokens | `run-code form check` | High if missing |
| 11 | Open redirect: external domain accepted | `goto + eval URL` | High if confirmed |
| 12 | Debug endpoints accessible | `goto /_debug, /.env` | Critical if accessible |
| 13 | Source maps accessible | `run-code fetch .map` | Medium |
| 14 | Server version headers | `network` | Low |
| 15 | Console: sensitive data logged | `console` | Medium |
| 16 | Password fields: autocomplete off | `run-code pw field check` | Low |