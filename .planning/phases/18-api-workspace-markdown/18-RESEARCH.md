# Phase 18: Test Report File Viewer (Workspace Markdown) - Research

**Researched:** 2026-06-01
**Domain:** FastAPI file-system API + Next.js markdown report viewer
**Confidence:** HIGH

## Summary

This phase adds a read-only file-system viewer that browses Agent-generated test reports from the workspace directory. The workspace already stores session directories (e.g., `workspace/default/testcase/workspace/七日_2026.06.01.13.56/`) containing `test_cases_*.md` and `phase*.md` markdown files. The backend needs two FastAPI endpoints: one to list session directories and their files, another to serve individual markdown file content. The frontend needs two pages: a report list page showing session folders with their files, and a detail page rendering the markdown content.

The existing codebase provides everything needed. The `MarkdownContent` component (`webui/src/app/components/MarkdownContent.tsx`) already handles full markdown rendering with GFM tables, code blocks, headings, and streaming support. The `apiClient` pattern, SWR hooks, `ManagementLayout` sidebar, and FastAPI route registration are all well-established patterns across 17 prior phases. No new npm or pip dependencies are required.

**Primary recommendation:** Build two backend endpoints in a new `reports.py` router that read the workspace filesystem directly, and two frontend pages (`/reports/list` for directory listing, `/reports/[session]/[filename]` for detail view) reusing the existing `MarkdownContent` component.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | existing | Backend API endpoints | Already used across 13+ routers in `src/app/api/v2/` |
| pathlib.Path | stdlib | Filesystem traversal | Workspace path resolution via `settings.workspace_dir` |
| Next.js | 15.4.4 | Frontend pages | App Router with `page.tsx` pattern established |
| react-markdown | ^10.1.0 | Markdown rendering | Already installed in `webui/package.json` |
| remark-gfm | ^4.0.1 | GFM table support | Already installed, used by `MarkdownContent` |
| SWR | ^2.4.1 | Data fetching hooks | Standard pattern via `useSWR` across all data hooks |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| react-syntax-highlighter | ^16.1.1 | Code block rendering | Already used in `MarkdownContent` CodeBlock component |
| lucide-react | ^1.14.0 | Icons | Nav items, file/folder icons |
| date-fns | ^4.1.0 | Date formatting | Session timestamp parsing from directory names |
| Shadcn/ui (Card, etc.) | existing | UI components | Report cards, layout |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| File-system reading | Database storage | Filesystem is simpler for read-only, already the source of truth |
| react-markdown | Custom parser | Custom StreamingMarkdownContent exists for streaming; react-markdown for static content (both in MarkdownContent) |
| New /reports route | Reuse existing /reports page | Existing /reports is test execution dashboard with charts; need separate route for workspace file viewer |

**Installation:**
No new packages needed. All dependencies already installed.

**Version verification:** Already confirmed from `webui/package.json`:
- react-markdown: ^10.1.0
- remark-gfm: ^4.0.1
- swr: ^2.4.1

## Architecture Patterns

### Workspace Directory Structure (Verified)
```
workspace/
└── default/
    └── testcase/
        └── workspace/
            ├── 七日_2026.06.01.13.56/       # Session directory (project_timestamp)
            │   ├── phase1_requirement_analysis.md
            │   ├── phase2_test_strategy.md
            │   ├── phase4_quality_review.md
            │   ├── test_cases_深渊重构V2.md
            │   ├── test_cases_悬赏重构V2.md
            │   ├── test_cases_紫薇养灵玉试用.md
            │   └── ...more test case files
            ├── 七日_2026.05.29.17.23/       # Another session
            │   └── ...
            └── (loose .md files and .py scripts also present)
```

Key observations from filesystem audit:
1. Session directories follow pattern `{project}_{YYYY.MM.DD.HH.MM}` or `{project}` (legacy, no timestamp)
2. Files inside: `test_cases_*.md` (test case reports), `phase*.md` (analysis/strategy reports)
3. Some loose files exist at the workspace root level (legacy, pre-session isolation)
4. File sizes range from ~5KB (phase analysis) to ~53KB (comprehensive test case files)
5. Chinese characters in both directory names and filenames -- must handle UTF-8 encoding correctly

### Recommended Backend Pattern: File-System API Router

Follow the pattern from `wikis.py` (lightweight router, no database, reads filesystem directly):

```python
# src/app/api/v2/reports.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
from src.app.core.config import settings

router = APIRouter(prefix="/reports")

def _get_reports_base() -> Path:
    return settings.workspace_dir / "default" / "testcase" / "workspace"

@router.get("/sessions")
async def list_sessions():
    """List all session directories with their .md files."""
    base = _get_reports_base()
    if not base.exists():
        return {"success": True, "data": []}
    # iterate directories, collect .md files per session
    ...

@router.get("/sessions/{session_name}/files/{file_name}")
async def get_report_content(session_name: str, file_name: str):
    """Read and return markdown file content."""
    # SECURITY: validate no path traversal
    ...
```

### Recommended Frontend Pattern: Report Pages

Follow existing page patterns (e.g., `/reports/page.tsx`, `/api-tests/`):

```
webui/src/app/reports/
├── page.tsx                     # Existing: test execution dashboard (KEEP AS-IS)
├── components/
│   └── ...existing charts...
├── test-reports/
│   ├── page.tsx                 # NEW: Session list page (all sessions)
│   └── [session]/
│       ├── page.tsx             # NEW: File list for a session
│       └── [filename]/
│           └── page.tsx         # NEW: Markdown detail view
```

Alternative flatter structure (recommended for simplicity):
```
webui/src/app/test-reports/
├── page.tsx                     # Session list + file list per session
└── [session]/
    └── [filename]/
        └── page.tsx             # Markdown detail view
```

### Pattern 1: File Listing API
**What:** List session directories and their markdown files
**When to use:** Report list page
**Example:**
```python
# Source: established pattern from wikis.py
@router.get("/sessions")
async def list_sessions():
    base = _get_reports_base()
    if not base.exists():
        return {"success": True, "data": []}
    sessions = []
    for item in sorted(base.iterdir(), reverse=True):
        if item.is_dir():
            md_files = sorted(
                [f.name for f in item.iterdir() if f.suffix == ".md"]
            )
            if md_files:
                sessions.append({
                    "name": item.name,
                    "files": md_files,
                    "file_count": len(md_files),
                })
    return {"success": True, "data": sessions}
```

### Pattern 2: Content Serving with Path Traversal Protection
**What:** Serve markdown file content safely
**When to use:** Report detail page
**Example:**
```python
@router.get("/sessions/{session_name}/files/{file_name:path}")
async def get_report_content(session_name: str, file_name: str):
    base = _get_reports_base()
    file_path = (base / session_name / file_name).resolve()
    # Path traversal protection
    if not file_path.is_relative_to(base.resolve()):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    content = file_path.read_text(encoding="utf-8")
    return {"success": True, "data": {"name": file_name, "content": content}}
```

### Anti-Patterns to Avoid
- **Database storage for read-only files:** These markdown files are generated by Agents and live on the filesystem. Do not copy them to the database.
- **Custom markdown parser:** `MarkdownContent` component already handles GFM tables, code blocks, headings, blockquotes, lists, and streaming. Reuse it directly.
- **Path traversal vulnerability:** Always resolve paths and verify with `is_relative_to()` before serving file content.
- **Ignoring non-directory items:** The workspace root contains loose `.md` files and `.py` scripts. Only list directories that contain `.md` files.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Markdown rendering | Custom HTML converter | `MarkdownContent` component | Already handles GFM tables, code blocks, streaming; 476 lines of battle-tested code |
| API response types | New envelope types | `SuccessResponse`/`MessageResponse` from `schemas.common` | Consistent API contract across all endpoints |
| SWR data hooks | Custom fetch logic | `useSWR` + `apiClient` pattern | Established in 11+ hook files |
| Path resolution | Hardcoded paths | `settings.workspace_dir` | Respects workspace configuration, portable |
| Sidebar navigation | New layout component | `ManagementLayout` | Existing layout with nav items array |

**Key insight:** This phase is primarily "wiring" -- connecting existing filesystem data to existing UI components through standard API patterns. The only new code is the filesystem traversal logic and page components.

## Common Pitfalls

### Pitfall 1: Path Traversal Security Vulnerability
**What goes wrong:** User passes `../../etc/passwd` as session_name or file_name
**Why it happens:** Naive string concatenation for file paths
**How to avoid:** Always use `Path.resolve()` + `is_relative_to()` to validate paths stay within the workspace base directory
**Warning signs:** Any code that builds file paths from user input without validation

### Pitfall 2: Chinese Filename Encoding Issues
**What goes wrong:** Garbled characters in directory/file names when listing or serving
**Why it happens:** Default encoding on Windows may not be UTF-8
**How to avoid:** Always specify `encoding="utf-8"` in `read_text()` calls. FastAPI URL path parameters handle UTF-8 automatically.
**Warning signs:** `???` or mojibake in API responses for Chinese filenames

### Pitfall 3: URL-Encoding in File/Directory Names
**What goes wrong:** Chinese filenames in URLs get double-encoded or fail to match
**Why it happens:** Next.js dynamic route segments and fetch API handle encoding differently
**How to avoid:** Use `encodeURIComponent` on frontend when building URLs, `decodeURIComponent` semantics on backend. Test with Chinese filenames early.
**Warning signs:** 404 errors for files that exist on disk

### Pitfall 4: Large File Content in API Response
**What goes wrong:** Some test case files are 50KB+ of markdown; returning them all in one JSON response could be slow
**Why it happens:** Not considering file sizes
**How to avoid:** This is acceptable for this use case (50KB is fine for a JSON response). No streaming needed for static file content. Flag if files exceed ~1MB.
**Warning signs:** API response times >2s for individual files

### Pitfall 5: Route Collision with Existing /reports
**What goes wrong:** New report viewer pages conflict with the existing `/reports` test execution dashboard
**Why it happens:** `/reports` already has `page.tsx` with chart visualizations
**How to avoid:** Use a distinct route prefix (e.g., `/test-reports` or `/workspace-reports`) or nest under `/reports/test-reports/`
**Warning signs:** Next.js build errors or wrong page rendering

## Code Examples

### Backend: Full Reports Router (Verified Pattern)
```python
# Source: Pattern from src/app/api/v2/wikis.py + src/app/api/v2/workspaces.py
"""Workspace report file viewer API.

Read-only endpoints to list and serve markdown test reports
from the workspace filesystem.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException

from src.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports")


def _get_reports_base() -> Path:
    """Get base path for testcase workspace reports."""
    return settings.workspace_dir / "default" / "testcase" / "workspace"


@router.get("/sessions")
async def list_sessions() -> dict:
    """List all session directories with their .md files."""
    base = _get_reports_base()
    if not base.exists():
        return {"success": True, "data": []}

    sessions = []
    for item in sorted(base.iterdir(), reverse=True):
        if not item.is_dir():
            continue
        md_files = sorted(
            [f.name for f in item.iterdir() if f.suffix == ".md" and f.is_file()],
            key=lambda n: (0 if n.startswith("phase") else 1, n),
        )
        if md_files:
            sessions.append({
                "name": item.name,
                "files": md_files,
                "file_count": len(md_files),
            })

    return {"success": True, "data": sessions}


@router.get("/sessions/{session_name}/files/{file_name:path}")
async def get_report_content(session_name: str, file_name: str) -> dict:
    """Read and return markdown file content."""
    base = _get_reports_base().resolve()
    file_path = (base / session_name / file_name).resolve()

    if not file_path.is_relative_to(base):
        raise HTTPException(status_code=403, detail="Access denied")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.suffix != ".md":
        raise HTTPException(status_code=400, detail="Only .md files are supported")

    content = file_path.read_text(encoding="utf-8")
    return {
        "success": True,
        "data": {
            "name": file_name,
            "session": session_name,
            "content": content,
        },
    }
```

### Frontend: SWR Hook (Verified Pattern)
```typescript
// Source: Pattern from webui/src/lib/api/useWikis.ts
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";

export interface SessionInfo {
  name: string;
  files: string[];
  file_count: number;
}

export interface ReportContent {
  name: string;
  session: string;
  content: string;
}

export function useReportSessions() {
  return useSWR<{ success: boolean; data: SessionInfo[] }>(
    "/reports/sessions",
    (url: string) => apiClient.get<SessionInfo[]>(url),
  );
}

export function useReportContent(sessionName: string, fileName: string) {
  const encodedSession = encodeURIComponent(sessionName);
  const encodedFile = encodeURIComponent(fileName);
  return useSWR<{ success: boolean; data: ReportContent }>(
    sessionName && fileName
      ? `/reports/sessions/${encodedSession}/files/${encodedFile}`
      : null,
    (url: string) => apiClient.get<ReportContent>(url),
  );
}
```

### Frontend: Detail Page (Verified Pattern)
```tsx
// Source: Pattern from webui/src/app/reports/page.tsx + MarkdownContent.tsx
"use client";

import { use } from "react";
import { ManagementLayout } from "@/app/components/ManagementLayout";
import { MarkdownContent } from "@/app/components/MarkdownContent";
import { useReportContent } from "@/lib/api/useReports";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function ReportDetailPage({
  params,
}: {
  params: Promise<{ session: string; filename: string }>;
}) {
  const { session, filename } = use(params);
  const decodedSession = decodeURIComponent(session);
  const decodedFilename = decodeURIComponent(filename);
  const { data, isLoading, error } = useReportContent(decodedSession, decodedFilename);

  return (
    <ManagementLayout>
      <div className="space-y-4">
        <div className="flex items-center gap-4">
          <Link href="/test-reports">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4 mr-1" />
              返回列表
            </Button>
          </Link>
          <h2 className="text-xl font-bold">{decodedFilename}</h2>
          <span className="text-sm text-muted-foreground">{decodedSession}</span>
        </div>
        {isLoading ? (
          <div className="py-8 text-center text-muted-foreground">加载中...</div>
        ) : error ? (
          <div className="py-8 text-center text-destructive">加载失败: {error.message}</div>
        ) : (
          <MarkdownContent content={data?.data?.content ?? ""} />
        )}
      </div>
    </ManagementLayout>
  );
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| react-markdown v9 | react-markdown v10 (^10.1.0) | 2025 | ESM-only, simplified API |
| remark-gfm v3 | remark-gfm v4 (^4.0.1) | 2025 | Better table handling |
| Custom markdown in chat | Unified `MarkdownContent` component | Phase 1 | Single component for both streaming and static markdown |

**Deprecated/outdated:**
- None relevant. All markdown dependencies are current.

## Open Questions

1. **Route path for report viewer pages**
   - What we know: `/reports` already exists as test execution dashboard
   - What's unclear: Whether to use `/test-reports`, `/workspace-reports`, or nest under `/reports/`
   - Recommendation: Use `/test-reports` as a new top-level route to avoid collision. Add nav item to ManagementLayout sidebar.

2. **Multi-workspace support**
   - What we know: Current workspace dir structure has `workspace/default/testcase/workspace/`
   - What's unclear: Whether to support reading from non-default workspaces
   - Recommendation: Phase 18 scope: default workspace only. Hardcode `default` in backend for now. Add X-Space-Id header support as a future enhancement.

3. **Legacy loose files at workspace root**
   - What we know: Some `.md` files exist directly in `workspace/default/testcase/workspace/` (not inside session directories)
   - What's unclear: Whether to display these in the report viewer
   - Recommendation: Include them as a "Loose Files" pseudo-session at the top of the list, or skip them. Skipping is simpler and less confusing.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.13 | FastAPI backend | ✓ | 3.13.2 | -- |
| Node.js | Next.js frontend | ✓ | 22.14.0 | -- |
| npm | Frontend deps | ✓ | 10.9.2 | -- |
| react-markdown | Markdown rendering | ✓ | ^10.1.0 | -- |
| remark-gfm | GFM support | ✓ | ^4.0.1 | -- |
| SWR | Data hooks | ✓ | ^2.4.1 | -- |
| FastAPI | Backend API | ✓ | existing | -- |

**Missing dependencies with no fallback:**
- None. All dependencies available.

**Missing dependencies with fallback:**
- None.

## Sources

### Primary (HIGH confidence)
- Workspace filesystem audit (directly verified directory structure and file contents)
- `src/app/fastapi_app.py` - API router registration pattern
- `src/app/api/v2/wikis.py` - File-based API router pattern
- `src/app/api/v2/workspaces.py` - CRUD endpoint pattern with workspace service
- `src/app/api/deps.py` - Dependency injection patterns
- `src/app/core/config.py` - `workspace_dir` path resolution
- `webui/src/app/components/MarkdownContent.tsx` - Markdown rendering component (476 lines)
- `webui/src/lib/api-client.ts` - API client pattern
- `webui/src/app/components/ManagementLayout.tsx` - Sidebar navigation pattern
- `webui/package.json` - Dependency versions

### Secondary (MEDIUM confidence)
- `webui/src/lib/api/useWikis.ts` - SWR hook pattern for file-based APIs
- `webui/src/app/types/api.ts` - TypeScript response type patterns
- `webui/src/app/reports/page.tsx` - Management page pattern

### Tertiary (LOW confidence)
- None. All findings verified from source code.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all dependencies already installed and in use
- Architecture: HIGH - patterns established across 17 prior phases
- Pitfalls: HIGH - common file-system security issues well-documented

**Research date:** 2026-06-01
**Valid until:** 2026-07-01 (stable stack, no fast-moving dependencies)
