# Test Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a same-origin browser test workbench at `/test` for selecting a template, uploading an image, running the existing generation API, and previewing the result.

**Architecture:** FastAPI serves one static HTML page from the existing backend. Vanilla JavaScript calls the existing template, upload, task, and asset endpoints; no new business API or frontend dependency is introduced.

**Tech Stack:** FastAPI, HTML, CSS, vanilla JavaScript, existing pytest/TestClient.

**Spec:** `projects/我的第一个产品/docs/superpowers/specs/2026-11-08-test-workbench-design.md`

## Global Constraints

- The page is an acceptance tool, not the formal Next.js product frontend.
- Use only existing API endpoints; do not add login, moderation, history, or new dependencies.
- Keep the API key out of HTML, JavaScript, docs, and Git.
- Preserve responsive behavior, visible focus, and reduced-motion support.

## Review Focus

- Empty file or missing selection: the page should block the request and explain the next action.
- API error envelope: `error.code` and `error.message` should appear without raw stack traces.
- Asset download requires `X-Owner-ID`: fetch it with the header, then preview a blob URL.
- Mobile width: controls stack without horizontal scrolling.
- Repeated runs: revoke old blob URLs and reset state before a new generation.

### Task 1: Serve the test page

**Files:**
- Create: `projects/我的第一个产品/backend/app/web/test_console.html`
- Modify: `projects/我的第一个产品/backend/app/main.py`
- Test: `projects/我的第一个产品/backend/tests/test_app.py`

**Interfaces:**
- Consumes: existing `/api/v1/templates`, `/api/v1/uploads`, `/api/v1/tasks`, `/api/v1/assets/{version_id}` endpoints.
- Produces: `GET /test` returning `text/html`.

- [x] Write failing route test asserting `/test` contains the page title and upload endpoint reference.
- [x] Run the focused test to confirm it fails before the route and file exist.
- [ ] Implement `/test` with `FileResponse` or `HTMLResponse` and build the page with the specified palette, responsive layout, controls, status panel, and result preview.
- [ ] Run focused and full pytest suites.

### Task 2: Exercise the page in a browser and record evidence

**Files:**
- Create: `projects/我的第一个产品/docs/evidence/阶段2-2/测试工作台.png`
- Modify: `projects/我的第一个产品/docs/evidence/阶段2-2/照着做清单.md`

- [ ] Start the existing service with the local `.env` and open `/test`.
- [ ] Run one real generation through the page and verify the result preview, provider label, and dimensions.
- [ ] Save a screenshot or result capture in the stage evidence directory.
- [ ] Run `bash kit.sh 自检 我的第一个产品` and copy its six outcomes into the stage checklist/table if needed.
