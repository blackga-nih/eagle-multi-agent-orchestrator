# EAGLE — Frontend Design Handoff

**Prepared for:** Design Agent
**Date:** March 2026
**Branch:** report/acquisition-package-eval-2026-03-16
**Purpose:** Redesign all frontend pages except the Chat page. Optimize for clarity, trust, and federal UX standards.

---

## 1. Application Overview

**EAGLE** (Enhanced Acquisition Guidance Learning Engine) is an AI-powered acquisition assistant built for NCI (National Cancer Institute) Contracting Officer Representatives (CORs). It automates and streamlines the federal procurement process — from intake through full document package generation.

### What it does

- Guides CORs through structured acquisition planning via conversational AI
- Enforces FAR/DFARS/HHSAR compliance automatically
- Generates compliant acquisition documents (SOW, IGCE, Acquisition Plan, Market Research, D&F, RFP/RFQ, Source Selection Plan)
- Supports two core workflows: **Simple** (< $250K, simplified acquisition) and **Complex** ($250K+, full competition)
- Uses a supervisor + specialist subagent architecture (Compliance, Financial, Technical, Legal, Market, Public Interest agents)

### Target users

- **CORs** (Contracting Officer Representatives) — primary users, federal employees
- **COs** (Contracting Officers) — reviewers and approvers
- **Policy Group** — admin-level access for template and knowledge base management

### Scale targets (production)

- 600+ CORs, 200+ COs
- Concurrent sessions, multi-document generation
- FedRAMP MODERATE compliant, FIPS 199, CUI handling

---

## 2. Brand Identity

### Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `nci-blue` | `#003366` | Primary brand — headings, nav, EAGLE wordmark |
| `nci-blue-light` | `#004488` | Hover states, accents |
| `nci-primary` | `#003149` | Alternate dark |
| `nci-primary-dark` | `#0D2648` | Deep backgrounds |
| `nci-info` | `#004971` | Info banners |
| `nci-link` | `#0B6ED7` | Links and CTAs |
| `nci-success` | `#037F0C` | Success states |
| `nci-danger` | `#BB0E3D` | Errors, alerts |
| `nci-accent` | `#7740A4` | AI actions, agent badges |
| `nci-user-bubble` | `#E3F2FD` | User chat messages |

### Name & Logo

- **Name:** EAGLE
- **Tagline concept:** AI-powered acquisition guidance for federal procurement
- **Visual identity:** The eagle symbol represents authority, precision, and federal trust. The `#003366` NCI dark blue is the primary brand color — it should anchor all page headers and navigation.
- **Typography:** Currently uses system fonts + Tailwind defaults. Open for redesign — suggest clean sans-serif (Inter, DM Sans, or similar) for body + slightly heavier weight for headings.

### Existing UI conventions to be aware of

- `rounded-2xl` card style throughout
- `border border-gray-200` for card outlines
- `bg-gray-50` page backgrounds
- `lucide-react` for all icons
- `ReactMarkdown` + `remarkGfm` for AI response rendering

---

## 3. Pages — Current State

### 3A. Pages to KEEP (do not redesign)

#### `/chat` — AI Chat Interface ✅ KEEP AS-IS

The core product experience. SSE-streamed conversation with the EAGLE AI supervisor and specialist subagents.

**Key features:**
- `SimpleChatInterface` — main chat component
- Message list with tool-use cards (knowledge search, document creation, FAR lookups)
- Activity panel (right sidebar) with 5 tabs: Package, Activity, Bedrock, Traces, Notifications
- Source chips on AI responses (KB documents, FAR citations with authority-level color coding)
- Trace story modal (Langfuse observability)
- Sidebar navigation

**Do not modify the chat page.** All other pages are candidates for redesign.

---

### 3B. Pages to REDESIGN

#### `/` — Home Page

**Current state:** Feature grid with 4 cards (Chat, Document Templates, Acquisition Packages, Admin). NCI blue gradient on "EAGLE" heading. AuthGuard wrapper.

**What it must do:**
- Entry point for authenticated CORs
- Quick navigation to core workflows: start a chat, view packages, browse documents
- Display system health or recent activity summary
- Reinforce the EAGLE brand

**Current feel:** Generic dashboard grid. Needs more personality and clearer user journey entry points.

---

#### `/workflows` — Acquisition Packages (aka `/packages` redirects here)

**Current state:** List view of acquisition packages with search/filter/sort. Phase badge chips (intake → planning → documents → review → complete). Checklist progress bar. Modal detail view. Backed by mock + localStorage data.

**Key data model:**
```
Package {
  id: "PKG-2026-0001"
  title: string
  status: "in_progress" | "completed" | "draft"
  phase: "intake" | "planning" | "documents" | "review" | "complete"
  estimated_value: number
  created_at: timestamp
  checklist: { item: string, completed: boolean }[]
  documents: DocumentInfo[]
}
```

**What it must do:**
- Let CORs see all their active and past acquisition packages at a glance
- Show progress clearly (phase, checklist items done / total)
- Quick-create a new package
- Open a package for detail view or to continue in chat

**Current feel:** Table/list-heavy. Could benefit from a kanban or card-based layout with phase progression.

---

#### `/documents` — Document Library

**Current state:** Tabbed view (All / SOW / IGCE / Acquisition Plan / Market Research / etc.). Shows both mock static templates and AI-generated documents. Markdown preview. Export options (download .docx).

**Key data model:**
```
Document {
  id: string
  title: string
  doc_type: "sow" | "igce" | "ap" | "market_research" | "rfq" | "rfp" | "d_and_f" | ...
  status: "draft" | "final"
  version: number
  created_at: timestamp
  package_id?: string
  s3_key: string
  word_count: number
}
```

**What it must do:**
- Browse all generated documents across packages
- Filter by type, status, date
- Preview document content
- Download as Word (.docx)
- See which package a document belongs to

**Current feel:** Basic tabbed list. Could benefit from richer document cards with preview thumbnails or content summaries.

---

#### `/documents/[id]` — Individual Document View

**Current state:** Single document display — renders markdown content, shows metadata, download button.

**What it must do:**
- Full document preview in a clean reading layout
- Side panel with metadata (type, version, package, created date, word count)
- Download (.docx) and share actions
- Edit/request revision option (opens chat with document context)

---

#### `/login` — Authentication

**Current state:** Email + password form (Cognito). Redirects to `/` on success. No social/SSO options shown.

**Note:** Production auth will be PIV card only (federal employees). The email/password form is for development. Design should accommodate either flow gracefully.

**What it must do:**
- NCI-branded login experience
- Clear "EAGLE" identity
- Minimal friction for PIV-authenticated users
- Error states for failed auth

---

#### `/chat-advanced` — Alternative Chat Interface

**Current state:** Alternative/experimental chat view. Less used than `/chat`.

**What it must do:**
- Could be merged or removed during redesign
- If kept: same purpose as `/chat` but with different layout (e.g., wider document panel, smaller chat column)

---

### 3C. Admin Suite — `/admin/**`

The admin area is a secondary product surface used by Policy Group / system admins. It has 14 sub-pages.

**Admin pages:**

| Route | Purpose |
|-------|---------|
| `/admin` | Dashboard — stats grid (active workflows, total value, docs generated, avg completion time), quick actions, recent activity, system health |
| `/admin/users` | User management — list, create, deactivate users |
| `/admin/workspaces` | Workspace management — tenant/workspace configs |
| `/admin/templates` | Document template management — view, update, version templates |
| `/admin/skills` | Agent skill management — active/inactive skills, metadata |
| `/admin/agents` | Agent configuration view |
| `/admin/analytics` | Usage analytics — token counts, session stats, cost trends |
| `/admin/costs` | Cost attribution — per-tenant, per-tier cost breakdown |
| `/admin/subscription` | Subscription tier management (basic / advanced / premium) |
| `/admin/traces` | Langfuse trace viewer — session-level trace stories |
| `/admin/eval` | Eval suite viewer — test results, pass/fail history |
| `/admin/tests` | Test run history — 15+ test result records |
| `/admin/expertise` | Expert system viewer — agent expertise docs |
| `/admin/kb-reviews` | Knowledge base review queue |
| `/admin/diagrams` | AI Diagram Studio — Excalidraw-based architecture diagrams |
| `/admin/api-explorer` | Live API explorer for backend endpoints |

**Admin dashboard stats (4 cards):**
- Active Workflows count
- Total Value ($ across all packages)
- Documents Generated (count)
- Avg. Completion Time (days)

**System health indicators:**
- AI Services (green: all agents operational)
- Database (green: connected, latency)
- API Rate Limit (amber: % used)

**Admin feel:** Currently uses the same white card + gray-50 background as the rest of the app. Could be more information-dense. Needs clear separation from the COR user experience.

---

## 4. MVP1 Requirements & Thesis

### Thesis

EAGLE reduces the time and expertise burden on NCI CORs to complete compliant federal acquisition packages. Instead of manually consulting FAR/HHSAR handbooks, filling forms, and coordinating with specialists, a COR describes what they need in plain language, and EAGLE guides them through the entire process — asking only necessary questions, automatically applying regulatory requirements, and generating a complete document package ready for OA Intake submission.

### Two Core Workflows (POC scope)

#### Workflow 1: Simple Acquisition (< $250K, Simplified Acquisition Threshold)

**Scenario:** COR needs to buy lab equipment for $50,000
**Flow:**
1. COR: "I need to buy a microscope for my lab"
2. EAGLE asks: cost → timeline → specifications
3. EAGLE identifies: under SAT, simplified procedures apply
4. EAGLE generates: SOW + IGCE + basic Acquisition Plan
5. COR downloads all three as Word (.docx)

**Target completion:** Single session, minimal questions

**Documents generated:**
- Statement of Work (SOW)
- Independent Government Cost Estimate (IGCE)
- Acquisition Plan (simplified)

#### Workflow 2: Complex Acquisition ($250K+, Full Competition)

**Scenario:** COR needs IT support services for $500,000 over 3 years
**Flow:**
1. COR: "I need IT support services for my division"
2. EAGLE asks: cost → contract type → period of performance → labor categories → security requirements → small business → evaluation criteria
3. EAGLE identifies: over SAT, full competition required, T&M contract → D&F required
4. Multi-agent processing: Compliance (FAR thresholds), Financial (cost structure), Technical (SOW review)
5. EAGLE generates full document package
6. COR downloads all as Word (.docx)

**Documents generated:**
- Statement of Work (SOW)
- Acquisition Plan (full)
- Independent Government Cost Estimate (IGCE)
- Market Research Report
- Source Selection Plan
- Determination & Findings (if T&M / options)
- RFQ/RFP (nice to have)
- Evaluation Criteria (nice to have)

### MVP1 Feature Set (6 of 25)

| # | Feature | Scope |
|---|---------|-------|
| 1 | Multi-Agent Framework | Supervisor + Compliance + Financial + Technical agents |
| 2 | Knowledge Base | FAR/HHSAR basics via S3 vector KB |
| 3 | Authentication | PIV card (federal employees only) |
| 4 | Adaptive Questioning | Simple → Complex branching, progressive discovery |
| 5 | Document Generation | SOW, AP, IGCE, Market Research, D&F in Word format |
| 11 | Regulatory Intelligence | Threshold detection, FAR compliance, D&F triggers |

### Phase Roadmap

| Phase | Timeline | Focus |
|-------|----------|-------|
| **MVP** | 6 months | Features 1–6, 11, 17 — core architecture, document gen, basic compliance |
| **Advanced** | 12 months | Features 7–10, 14–16 — consistency engine, NVision, system integrations |
| **Full** | 18 months | Features 18–25 — AI learning, performance optimization, full collaboration |

---

## 5. Agent Architecture (for design reference)

EAGLE uses a **supervisor → specialist subagent** pattern.

```
Supervisor Agent
├── Compliance Agent     — FAR/HHSAR/NIH policy compliance
├── Financial Agent      — Cost estimation, IGCE validation
├── Technical Agent      — SOW review, technical requirements
├── Legal Agent          — Legal review, risk assessment (Phase 2)
├── Market Agent         — Market research, commercial analysis (Phase 2)
└── Public Interest Agent — Small business considerations (Phase 2)
```

Agents communicate via the chat interface. Users see:
- Tool-use cards (what each agent is doing)
- Source chips (knowledge base citations with authority level)
- Activity panel with real-time status

---

## 6. Document Types Supported

The system currently supports 10 document types with more planned:

| Type | Code | Common in |
|------|------|-----------|
| Statement of Work | `sow` | Both workflows |
| Acquisition Plan | `ap` | Both workflows |
| Independent Gov. Cost Estimate | `igce` | Both workflows |
| Market Research Report | `market_research` | Complex |
| Request for Quotation | `rfq` | Complex |
| Request for Proposal | `rfp` | Complex |
| Determination & Findings | `d_and_f` | Complex (T&M) |
| Justification for Other than Full Competition | `jofoc` | Complex (sole source) |
| Source Selection Plan | `source_selection` | Complex |
| Evaluation Criteria | `eval_criteria` | Complex |

---

## 7. Design Guidance for Redesign Agent

### Preserve

- The EAGLE wordmark and NCI dark blue (`#003366`) as primary brand anchor
- The chat page exactly as-is
- Federal / government trust signals — clean, structured, professional
- Accessibility (WCAG 2.1 AA minimum — federal requirement)

### Redesign goals

- **Clearer user journey:** Home page should immediately orient a COR to their most likely next action (start a new acquisition, continue a package, view documents)
- **Package-centric mental model:** The "Acquisition Package" is the core unit of work. Pages should make this prominent — not documents or chats in isolation
- **Progress visibility:** Phase progression (intake → planning → documents → review → complete) should be visually clear across the packages view
- **Admin separation:** Admin pages need a distinct visual treatment from the COR experience — different nav, possibly different sidebar color
- **Mobile-aware:** Though primarily desktop, tablet support matters for CORs in the field
- **Performance:** Next.js App Router — all redesigned pages should use Server Components where possible; only interactive elements need `'use client'`

### What NOT to redesign

- Authentication logic (Cognito integration)
- API calls and data fetching hooks
- SSE streaming infrastructure
- The `eagle-plugin/` agent and skill definitions
- Backend services

---

## 8. Tech Stack Reference (for design agent)

| Layer | Tech |
|-------|------|
| Framework | Next.js 14 App Router |
| Styling | Tailwind CSS |
| Icons | lucide-react |
| UI components | Custom (no shadcn, no MUI) |
| Markdown | react-markdown + remark-gfm |
| Auth | AWS Cognito (email/password dev, PIV prod) |
| State | React hooks (useState, useEffect, useMemo) |
| Data fetching | fetch() + custom hooks |
| Streaming | SSE via use-agent-stream.ts hook |

---

*Extracted from branch: `report/acquisition-package-eval-2026-03-16`*
*Source files: `client/app/**`, `docs/architecture/EAGLE-POC-scope-validation.md`, `docs/development/meeting-transcripts/.../SUMMARY-eagle-features-requirements.md`*
