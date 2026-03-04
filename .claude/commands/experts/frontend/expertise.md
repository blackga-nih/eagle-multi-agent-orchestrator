---
type: expert-file
parent: "[[frontend/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, frontend, nextjs, tailwind, chat, dashboard, test-results]
last_updated: 2026-03-04T04:30:00
---

# Frontend Expertise (Complete Mental Model)

> **Sources**: client/, test_results_dashboard.html, tailwind.config.ts, globals.css

---

## Part 1: Architecture (Next.js App Structure, Page Routes, Component Tree)

### Framework

- **Next.js 14+** with App Router (`app/` directory)
- **TypeScript** throughout
- **Tailwind CSS** with custom NCI color palette
- **lucide-react** for icons
- **react-markdown** for message rendering
- **amazon-cognito-identity-js** for auth

### Page Routes

| Route | File | Description |
|-------|------|-------------|
| `/` | `app/page.tsx` | Feature hub — 4 cards: Chat, Templates, Acquisition Packages, Admin |
| `/chat` | `app/chat/page.tsx` | Minimalist chat with sidebar nav (SimpleChatInterface) |
| `/chat-advanced` | `app/chat-advanced/page.tsx` | Complex chat with sidebar, forms, agent logs |
| `/login` | `app/login/page.tsx` | Cognito sign-in page |
| `/admin` | `app/admin/page.tsx` | Admin dashboard home |
| `/admin/tests` | `app/admin/tests/page.tsx` | SDK test results viewer |
| `/admin/eval` | `app/admin/eval/page.tsx` | Eval viewer with use case diagrams |
| `/admin/agents` | `app/admin/agents/page.tsx` | Agent management |
| `/admin/costs` | `app/admin/costs/page.tsx` | Cost tracking |
| `/admin/analytics` | `app/admin/analytics/page.tsx` | Analytics |
| `/admin/skills` | `app/admin/skills/page.tsx` | Skill management |
| `/admin/expertise` | `app/admin/expertise/page.tsx` | Expertise panel |
| `/admin/users` | `app/admin/users/page.tsx` | User management |
| `/admin/templates` | `app/admin/templates/page.tsx` | Document templates |
| `/admin/subscription` | `app/admin/subscription/page.tsx` | Subscription tiers |
| `/documents` | `app/documents/page.tsx` | Document browser |
| `/documents/[id]` | `app/documents/[id]/page.tsx` | Single document view |
| `/workflows` | `app/workflows/page.tsx` | Workflow list |

### API Routes

| Route | Purpose |
|-------|---------|
| `/api/health` | Proxies to FastAPI `/api/health`; returns 502 if backend unreachable |
| `/api/trace-logs` | Serves trace_logs.json; `?list=1` lists all runs, `?run=<file>` loads specific run |
| `/api/cloudwatch` | `?runs=1` lists CW streams; `?stream=<name>&group=test-runs` loads events |
| `/api/prompts` | Loads skill prompt files from eagle-plugin/ |
| `/api/invoke` | Agent invocation endpoint |
| `/api/conversations` | Conversation CRUD |
| `/api/conversations/[agentId]` | Agent-specific conversation history |
| `/api/conversations/context` | Conversation context endpoint |
| `/api/sessions` | Session management |
| `/api/sessions/[sessionId]` | Single session CRUD |
| `/api/sessions/[sessionId]/messages` | Session messages |
| `/api/documents` | Document CRUD |
| `/api/documents/[id]` | Single document operations |
| `/api/user` | Current user info |
| `/api/user/usage` | Usage tracking |
| `/api/admin/dashboard` | Admin dashboard data |
| `/api/admin/users` | User management |
| `/api/admin/costs` | Cost data |
| `/api/admin/telemetry` | Telemetry data |

### Component Tree

```
components/
  |-- chat/                          # Complex chat (used at /chat-advanced)
  |   |-- chat-interface.tsx         # Main chat component with sidebar
  |   |-- message-list.tsx           # Message rendering with forms
  |   |-- welcome-message.tsx        # Welcome card with capabilities
  |   |-- suggested-prompts.tsx      # Prompt suggestion buttons
  |   |-- slash-command-picker.tsx   # Slash command autocomplete
  |   |-- multi-agent-logs.tsx       # Agent stream log viewer
  |   |-- inline-equipment-form.tsx  # Equipment detail form
  |   |-- inline-funding-form.tsx    # Funding detail form
  |   |-- agent-message.tsx          # Agent message bubble
  |
  |-- chat-simple/                   # Minimalist chat (used at /chat)
  |   |-- simple-chat-interface.tsx  # Simple chat main
  |   |-- simple-message-list.tsx    # Simple message list
  |   |-- simple-welcome.tsx         # Simple welcome
  |   |-- simple-header.tsx          # Simple header
  |   |-- simple-quick-actions.tsx   # Quick action buttons
  |   |-- document-card.tsx          # Document result card (links to /documents/[id])
  |
  |-- layout/
  |   |-- top-nav.tsx                # Top navigation bar
  |   |-- sidebar-nav.tsx            # Side navigation
  |   |-- page-header.tsx            # Page header component
  |   |-- chat-history-dropdown.tsx  # Chat history selector
  |
  |-- auth/
  |   |-- auth-guard.tsx             # Auth protection wrapper
  |
  |-- forms/
  |   |-- initial-intake-form.tsx    # Initial acquisition intake form
  |   |-- equipment-form.tsx         # Equipment details form
  |   |-- funding-form.tsx           # Funding details form
  |
  |-- checklist/
  |   |-- document-checklist.tsx     # Document readiness checklist
  |
  |-- documents/
  |   |-- document-browser.tsx       # Document list
  |   |-- document-upload.tsx        # File upload component
  |   |-- document-requirements.tsx  # Document requirements
  |
  |-- summary/
  |   |-- acquisition-card.tsx       # Acquisition summary card
  |
  |-- agents/
  |   |-- agent-sidebar.tsx          # Agent info sidebar
  |   |-- agent-chat.tsx             # Agent chat component
  |   |-- mcp-tool-result.tsx        # MCP tool result display
  |
  |-- expertise/
  |   |-- expertise-panel.tsx        # Expertise viewer
  |
  |-- settings/
  |   |-- expertise-manager.tsx      # Expertise management
  |
  |-- ui/
  |   |-- badge.tsx                  # Badge component
  |   |-- data-table.tsx             # Data table
  |   |-- modal.tsx                  # Modal dialog
  |   |-- tabs.tsx                   # Tab component
  |   |-- markdown-renderer.tsx      # Markdown renderer
  |
  |-- error-boundary.tsx             # Error boundary wrapper
```

---

## Part 2: Chat Interface (Chat Components, Message Types, Welcome Flow)

### Complex Chat (`/chat-advanced`)

**Main component**: `components/chat/chat-interface.tsx`

**Layout**: Two-column layout:
- Left: Chat area (messages + input)
- Right: Sidebar (450px) with 3 tabs: Active Intake, Order History, Agent Logs

**Message Types** (defined in `chat-interface.tsx`):

```typescript
interface Message {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    reasoning?: string;      // Expandable "Agent Intent Log"
    agent_id?: string;       // Source agent
    agent_name?: string;     // Human-readable agent name
}
```

**AcquisitionData** (tracks intake state):

```typescript
interface AcquisitionData {
    requirement?: string;
    estimatedValue?: string;
    estimatedCost?: string;
    timeline?: string;
    urgency?: string;
    funding?: string;
    equipmentType?: string;
    acquisitionType?: string;
}
```

**Input Features**:
- Text input with slash command autocomplete (`/` triggers picker)
- Voice input (Web Speech API)
- Backend health indicator (green/red pill)
- Streaming status indicator

**Sidebar Tabs**:
- `current`: AcquisitionCard + DocumentChecklist + DocumentUpload
- `history`: Past workflows from mock data
- `logs`: Multi-agent stream viewer (real-time events)

**Form Flow**:
1. User types `/acquisition-package` or clicks capability card
2. `activeForm` state set to `'initial'`
3. `InitialIntakeForm` rendered inline in message list
4. On submit: form marked as submitted (frozen), user message added, sent to backend
5. Agent response may trigger `'equipment'` or `'funding'` follow-up forms

**Backend Integration** (`use-agent-stream` hook):
- `sendQuery(query, sessionId)` sends to backend
- `onMessage` callback adds assistant messages
- `isStreaming` controls UI state
- Falls back to mock response when backend offline

### Minimalist Chat (`/chat`)

**Components**: `components/chat-simple/`
- `simple-chat-interface.tsx`: Minimal layout, no sidebar
- `simple-message-list.tsx`: Clean message rendering
- `simple-welcome.tsx`: Simple welcome card
- `simple-header.tsx`: Minimal header
- `simple-quick-actions.tsx`: Quick action buttons
- `document-card.tsx`: Renders document results from agent (links to `/documents/[id]`)

**Layout**: `SimpleHeader` + `SidebarNav` + `SimpleChatInterface` (no form-heavy sidebar)

### Home Page (`/`)

Not a chat page — it is a feature hub landing page with:
- Left column: EAGLE branding + description
- Right column: 4 `<Link>` feature cards:
  1. **Chat** → `/chat`
  2. **Document Templates** → `/admin/templates`
  3. **Acquisition Packages** → `/workflows`
  4. **Admin** → `/admin`
- Footer: "EAGLE · National Cancer Institute · Powered by Claude (Anthropic SDK)"

### Welcome Message

**Component**: `components/chat/welcome-message.tsx`

Shows 4 capability cards:
1. **Acquisition Packages** (FileText icon, blue)
2. **Research** (Search icon, green)
3. **Document Generation** (Sparkles icon, purple)
4. **Compliance** (Shield icon, amber)

Followed by `SuggestedPrompts` component.

### Message Rendering

**Component**: `components/chat/message-list.tsx`

- User messages: Right-aligned, blue bubble (`bg-nci-user-bubble`)
- Assistant messages: Left-aligned, white bubble with EAGLE badge
- ReactMarkdown for rich text rendering
- Expandable "Reasoning" panel (Brain icon, accordion)
- Copy button (hover-to-show)
- Typing indicator with bouncing dots

---

## Part 3: Admin Dashboard (Tests Page, Eval Page, Data Sources)

### Tests Page (`/admin/tests`)

**File**: `client/app/admin/tests/page.tsx`

**Purpose**: Display pytest run history with drill-down into individual test results. Data persisted to DynamoDB via `conftest.py` hooks.

**Data Loading**: Fetches from `/api/admin/test-runs` (list) and `/api/admin/test-runs/{run_id}` (detail)

**Interfaces**:

```typescript
interface TestRun {
    run_id: string;
    timestamp: string;
    total: number;
    passed: number;
    failed: number;
    skipped: number;
    errors: number;
    duration_s: number;
    pass_rate: number;
    model: string;
    trigger: string;
}

interface TestResultDetail {
    nodeid: string;
    test_file: string;
    test_name: string;
    status: string;
    duration_s: number;
    error: string;
}
```

**Views**:

1. **Run List View**: Cards for each pytest run showing pass/fail icon, timestamp, model, test counts, pass rate, duration. Click to drill down.

2. **Run Detail View**:
   - Stats cards: Total, Passed, Failed, Skipped, Duration
   - Metadata: timestamp, model, pass rate
   - Filter bar: All / Pass / Fail (pill buttons)
   - Results grouped by test file
   - Expandable error traces for failed tests (red background, monospace)

**Backend API**:
- `GET /api/admin/test-runs?limit=N` → `{ runs: TestRun[], count: number }`
- `GET /api/admin/test-runs/{run_id}` → `{ run_id, results: TestResultDetail[], count }`
- Data stored in DynamoDB `eagle` table with `TESTRUN#` PK/SK pattern

**Protected by**: `<AuthGuard>` wrapper + `<TopNav />` header

### Eval Page (`/admin/eval`)

**File**: `client/app/admin/eval/page.tsx`

**Purpose**: Interactive sequence diagram eval viewer for EAGLE use cases + test run cross-reference

**Key Data Structures**:

1. **USE_CASES** array: 10 use cases
   - `uc01-happy`, `uc01-complex`, `uc01-full-chain`, `uc02`, `uc03`, `uc04`, `uc05`, `uc07`, `uc08`, `uc09`
   - Each has: id, title, subtitle, actors[], phases[], steps[]
   - Step types: `message`, `self`, `note`
   - Steps can have `prompt` key linking to skill prompts

2. **PROMPT_TITLES** Record: Human names for all agent/skill prompt keys (~line 659)
   - 8 agents + 5 skills + 2 diagram aliases (see Part 4)

3. **SKILL_TEST_MAP** Record: Maps plugin-slug keys to test IDs (~line 681)

**Features**:
- SVG sequence diagram with actor headers, lifelines, message arrows, self-loops, notes
- Phase backgrounds (colored rectangles)
- Step-by-step navigation (keyboard arrows, click)
- Pan + zoom (mouse drag, wheel, +/- keys)
- Sidebar with step list, phase markers, prompt badges
- Run selector: CloudWatch streams + local trace_logs.json files
- Tabbed modal: Prompt content | Test Traces | Live CloudWatch Logs
- Markdown renderer for prompt content

**Data Sources**:
- Prompts from `/api/prompts` (skill files from eagle-plugin/)
- Runs from `/api/cloudwatch?runs=1` (CW streams) + `/api/trace-logs?list=1` (local)
- Run data from `/api/trace-logs?run=<file>` or `/api/cloudwatch?stream=<name>&group=test-runs`

---

## Part 4: Test Result Mappings (TEST_NAMES, TEST_DEFS, SKILL_TEST_MAP, Readiness Panel, Categories)

### TEST_NAMES (`client/app/admin/tests/page.tsx` ~line 28)

Maps test ID strings to human-readable names for the Next.js test results page. Currently 27 entries:

```typescript
const TEST_NAMES: Record<string, string> = {
    '1': 'Session Creation + Tenant Context Injection',
    '2': 'Session Resume (Stateless Multi-Turn)',
    '3': 'Trace Observation (Frontend Event Types)',
    '4': 'Subagent Orchestration',
    '5': 'Cost + Token Tracking',
    '6': 'Tier-Gated MCP Tool Access',
    '7': 'Skill Loading: OA Intake',
    '8': 'Subagent Tool Tracking',
    '9': 'OA Intake Workflow',
    '10': 'Legal Counsel Skill',
    '11': 'Market Intelligence Skill',
    '12': 'Tech Review Skill',
    '13': 'Public Interest Skill',
    '14': 'Document Generator Skill',
    '15': 'Supervisor Multi-Skill Chain',
    '16': 'S3 Document Operations',
    '17': 'DynamoDB Intake Operations',
    '18': 'CloudWatch Logs Operations',
    '19': 'Document Generation',
    '20': 'CloudWatch E2E Verification',
    '21': 'UC-02 Micro-Purchase (<$15K)',
    '22': 'UC-03 Option Exercise',
    '23': 'UC-04 Contract Modification',
    '24': 'UC-05 CO Package Review',
    '25': 'UC-07 Contract Close-Out',
    '26': 'UC-08 Shutdown Notification',
    '27': 'UC-09 Score Consolidation',
};
```

### SKILL_TEST_MAP (`client/app/admin/eval/page.tsx` ~line 681)

Maps plugin-slug keys (full agent/skill names) to test IDs for cross-referencing in the eval modal.
Keys use full plugin slugs — NOT the short diagram actor IDs:

```typescript
const SKILL_TEST_MAP: Record<string, number[]> = {
    'oa-intake': [7, 9, 21, 22, 23],
    'document-generator': [14],
    'tech-review': [12, 27],
    compliance: [10, 24, 25, 26],
    supervisor: [15, 28],
    'legal-counsel': [10, 24, 25, 26, 28],
    'market-intelligence': [11, 28],
    'tech-translator': [12, 27],
    'public-interest': [13],
    'policy-supervisor': [],
    'policy-librarian': [],
    'policy-analyst': [],
    'sdk-skill-subagent': [28],
    s3_document_ops: [16],
    dynamodb_intake: [17],
    cloudwatch_logs: [18],
    create_document: [14, 19],
    cloudwatch_e2e: [20],
};
```

Note: Test 28 is referenced in SKILL_TEST_MAP but not yet in TEST_NAMES — it will need a TEST_NAMES entry when the test is added.

### PROMPT_TITLES (`client/app/admin/eval/page.tsx` ~line 659)

Fallback display names for all agents, skills, and diagram actor aliases while API loads:

```typescript
const PROMPT_TITLES: Record<string, string> = {
    // Agents
    supervisor: 'EAGLE Supervisor Agent',
    'legal-counsel': 'Legal Counsel Agent',
    'market-intelligence': 'Market Intelligence Agent',
    'tech-translator': 'Tech Translator Agent',
    'public-interest': 'Public Interest Agent',
    'policy-supervisor': 'Policy Supervisor Agent',
    'policy-librarian': 'Policy Librarian Agent',
    'policy-analyst': 'Policy Analyst Agent',
    // Skills
    'oa-intake': 'OA Intake Skill',
    'document-generator': 'Document Generator Skill',
    compliance: 'Compliance Skill',
    'tech-review': 'Tech Review Skill',
    'knowledge-retrieval': 'Knowledge Retrieval Skill',
    // Aliases for USE_CASES diagram actor IDs
    intake: 'OA Intake Skill',
    docgen: 'Document Generator Skill',
};
```

### Cross-Reference Usage

The eval modal uses SKILL_TEST_MAP to:
1. `getTestTracesForPrompt(promptKey)` -- finds test results for the displayed skill
2. `getLiveLogsForPrompt(promptKey)` -- filters CloudWatch events by test_id
3. Renders traces in the "Test Traces" tab and CW events in the "Live Logs" tab

---

## Part 5: Legacy HTML Dashboard (TEST_DEFS, LATEST_RESULTS, Filter System, Readiness Indicators)

### File: `test_results_dashboard.html`

Standalone single-file HTML dashboard. No build step required. Open in browser directly.

### TEST_DEFS (~line 124)

Array of test definitions with category tags:

```javascript
const TEST_DEFS = [
    { id: 1,  name: "Session Creation",           desc: "...", category: "core" },
    { id: 2,  name: "Session Resume",             desc: "...", category: "core" },
    { id: 3,  name: "Trace Observation",           desc: "...", category: "traces" },
    { id: 4,  name: "Subagent Orchestration",      desc: "...", category: "agents" },
    { id: 5,  name: "Cost Tracking",               desc: "...", category: "core" },
    { id: 6,  name: "Tier-Gated MCP Tools",        desc: "...", category: "tools" },
    { id: 7,  name: "Skill Loading",               desc: "...", category: "skills" },
    { id: 8,  name: "Subagent Tool Tracking",       desc: "...", category: "agents" },
    { id: 9,  name: "OA Intake Workflow",           desc: "...", category: "workflow" },
    { id: 10, name: "Legal Counsel Skill",         desc: "...", category: "skills" },
    { id: 11, name: "Market Intelligence Skill",   desc: "...", category: "skills" },
    { id: 12, name: "Tech Review Skill",           desc: "...", category: "skills" },
    { id: 13, name: "Public Interest Skill",       desc: "...", category: "skills" },
    { id: 14, name: "Document Generator Skill",    desc: "...", category: "skills" },
    { id: 15, name: "Supervisor Multi-Skill Chain", desc: "...", category: "workflow" },
    { id: 16, name: "S3 Document Operations",      desc: "...", category: "aws" },
    { id: 17, name: "DynamoDB Intake Operations",  desc: "...", category: "aws" },
    { id: 18, name: "CloudWatch Logs Operations",  desc: "...", category: "aws" },
    { id: 19, name: "Document Generation",         desc: "...", category: "aws" },
    { id: 20, name: "CloudWatch E2E Verification", desc: "...", category: "aws" },
];
```

Note: The HTML dashboard TEST_DEFS still covers tests 1-20 only. Tests 21-27 (UC use-case tests) are in TEST_NAMES on the Next.js page but may not yet be added to the HTML dashboard.

### Category System

| Category | Test IDs | Description |
|----------|----------|-------------|
| `core` | 1, 2, 5 | Session management, cost tracking |
| `traces` | 3 | Frontend event type mapping |
| `agents` | 4, 8 | Subagent orchestration and tracking |
| `tools` | 6 | MCP tool access |
| `skills` | 7, 10-14 | Skill loading and validation |
| `workflow` | 9, 15 | Multi-turn and multi-skill workflows |
| `aws` | 16-20 | AWS tool integration with boto3 confirm |

### Filter Buttons

Toolbar has 6 filter buttons: All (20), Pass, Fail, Skills, Workflow, AWS.

`filterCards(filter, btn)` shows/hides cards based on:
- `pass`, `fail`, `skip` -- match CSS class on card
- `skills`, `workflow`, `aws` -- match `data-category` attribute

### LATEST_RESULTS (~line 147)

Embedded results object keyed by test ID (number). Each entry:

```javascript
{
    status: "pass" | "fail" | "skip",
    tokens_in: number,
    tokens_out: number,
    cost: number,
    session_id?: string,
    details: string
}
```

### TRACE_LOGS (~line 167)

Embedded trace log object keyed by test ID (string). Each entry is an array of log lines with syntax highlighting:
- `system-msg`, `assistant-text`, `assistant-tool`, `tool-result`, `result-msg`
- `subagent`, `pass`, `fail`, `cost`, `phase`, `context`, `info`

The `classifyLine()` function (~line 172) maps log line patterns to CSS classes.

### Readiness Panel (~line 306)

Array of readiness checks, each maps to specific test results:

```javascript
const readiness = [
    { label: "Session management (create/resume)", ready: results[1]?.status === 'pass' && results[2]?.status === 'pass' },
    { label: "Trace events (ToolUseBlock/TextBlock)", ready: results[3]?.status === 'pass' },
    { label: "Subagent orchestration", ready: results[4]?.status === 'pass' },
    // ... one entry per test (19 total)
    { label: "CloudWatch E2E verification", ready: results[20]?.status === 'pass' },
];
```

Each renders as a green/red dot + label in the summary section.

### Card Structure

Each test card shows:
- Test ID + name in header
- Status badge (PASS/FAIL/SKIP colored)
- Card body: description, cost, tokens, session, details
- Expandable trace log panel (click to expand, button to collapse)
- Cards span full width when expanded (`grid-column: 1 / -1`)

---

## Part 6: Auth and Context (Cognito, auth-context.tsx)

### Auth Context (`client/contexts/auth-context.tsx`)

**Provider**: `<AuthProvider>` wraps the app

**Hook**: `useAuth()` returns:

```typescript
interface AuthContextValue {
    user: AuthUser | null;
    isLoading: boolean;
    isAuthenticated: boolean;
    getToken: () => Promise<string>;
    signIn: (email: string, password: string) => Promise<void>;
    signOut: () => void;
    error: string | null;
}
```

**AuthUser** shape:

```typescript
interface AuthUser {
    userId: string;      // Cognito sub
    tenantId: string;    // custom:tenant_id
    email: string;
    tier: string;        // custom:tier (default: 'standard')
    roles: string[];     // cognito:groups
    displayName: string; // email prefix
}
```

### Dev Mode

When `NEXT_PUBLIC_COGNITO_USER_POOL_ID` is empty or not set, auth runs in dev mode:
- Immediately provides a mock `DEV_USER` (userId: 'dev-user', tenantId: 'dev-tenant', tier: 'premium', roles: ['admin'])
- `getToken()` returns empty string
- `signIn()` sets the mock user immediately

### Cognito Configuration

Environment variables:
- `NEXT_PUBLIC_COGNITO_USER_POOL_ID`
- `NEXT_PUBLIC_COGNITO_CLIENT_ID`
- `NEXT_PUBLIC_COGNITO_REGION` (default: 'us-east-1')

Auth flow: `USER_PASSWORD_AUTH` (Cognito Essentials tier)

### Token Refresh

- Automatic refresh scheduled 5 minutes before ID token expiry
- Uses `cognitoUser.getSession()` for silent refresh
- On refresh failure: force sign-out, set error message

### AuthGuard (`components/auth/auth-guard.tsx`)

Wrapper component that:
- Shows loading spinner while `isLoading`
- Redirects to `/login` when not authenticated
- Renders children when authenticated

### Session Context (`contexts/session-context.tsx`)

Provides session persistence:
- `currentSessionId`: active session
- `saveSession(messages, acquisitionData)`: save to local storage
- `loadSession(sessionId)`: load from local storage

---

## Part 7: Styling and Config (Tailwind, globals.css)

### Tailwind Config (`client/tailwind.config.ts`)

Custom NCI color palette:

```typescript
colors: {
    nci: {
        primary: '#003149',
        'primary-dark': '#0D2648',
        danger: '#BB0E3D',
        accent: '#7740A4',
        info: '#004971',
        link: '#0B6ED7',
        success: '#037F0C',
        blue: '#003366',
        'blue-light': '#004488',
        'user-bubble': '#E3F2FD',
        'user-border': '#BBDEFB',
    },
},
```

Usage in components: `bg-nci-blue`, `text-nci-info`, `bg-nci-user-bubble`, etc.

Content paths scanned: `./pages/**`, `./components/**`, `./app/**`

### Global CSS (`client/app/globals.css`)

**CSS Variables**:
- `--nci-blue: #003366`
- `--nci-blue-light: #004488`
- `--user-bubble: #E3F2FD`
- `--user-border: #BBDEFB`

**Animations**:
- `.animate-slide-in` -- sidebar slide-in (0.3s ease-out)
- `.msg-slide-in` -- message entrance (opacity + translateY)
- `.typing-dot` -- bouncing dots with staggered delay (0s, 0.2s, 0.4s)
- `.streaming-cursor` -- blinking cursor after streaming text

**Markdown Styles** (`.msg-bubble`):
- `strong` -- NCI blue color
- `code:not(pre code)` -- light blue background with NCI blue text
- `pre` -- dark theme code blocks (#1e1e2e bg, #cdd6f4 text)
- `table` -- clean table with alternating row colors
- `blockquote` -- left blue border with italic text

**User bubble overrides** (`.msg-bubble-user`):
- `strong` -- darker blue (#1e3a5f)
- `code` -- semi-transparent blue background

**Copy button**: `.copy-btn` is hidden (opacity: 0), shown on `.msg-wrapper:hover`

**Custom scrollbar**: 6px width, gray thumb, transparent track

### Eval Page Styling

The eval page (`/admin/eval`) uses a dark theme:
- Background: `#0f1117`
- Panel backgrounds: `#161822`, `#13151f`, `#1e2030`
- Borders: `#2a2d3a`
- Accent: indigo-500 (`#818cf8`)
- SVG diagram with dark backgrounds and colored phase rectangles

---

## Part 8: Known Issues and Patterns

### Registration Consistency

When adding a new test, the following 3 frontend locations must be updated:

| # | File | Variable | Format |
|---|------|----------|--------|
| 1 | `test_results_dashboard.html` | `TEST_DEFS` (~line 124) | `{ id: N, name: "...", desc: "...", category: "..." }` |
| 2 | `client/app/admin/tests/page.tsx` | `TEST_NAMES` (~line 28) | `'N': 'Human Name'` |
| 3 | `client/app/admin/eval/page.tsx` | `SKILL_TEST_MAP` (~line 681) | `key: [N]` (if skill/tool test) |

Plus the readiness panel in `test_results_dashboard.html` (~line 306).

**Important**: Tests 21-27 (UC use-case tests) exist in TEST_NAMES but the HTML dashboard TEST_DEFS has not been updated to include them. When adding new UC tests, update both. SKILL_TEST_MAP references test 28 but it does not yet have a TEST_NAMES entry.

### Data Flow

```
server/tests/test_eagle_sdk_eval.py
  |-- writes --> trace_logs.json
  |-- emits --> CloudWatch /eagle/test-runs

trace_logs.json
  |-- read by --> /api/trace-logs --> /admin/tests (Next.js)
  |-- read by --> /api/trace-logs --> /admin/eval (Next.js, run selector)
  |-- embedded as --> LATEST_RESULTS, TRACE_LOGS (HTML dashboard)

CloudWatch /eagle/test-runs
  |-- read by --> /api/cloudwatch --> /admin/eval (Next.js, run selector)
```

### Patterns That Work

- AuthGuard wrapper for all protected pages
- `'use client'` directive on all interactive pages
- Lucide icons consistently used throughout
- Dark theme for eval page (SVG-based), light theme for chat and tests
- Inline forms in message list (not separate pages)
- Debounced session saves (500ms timeout)
- Backend health check via `/api/health` proxy route (30-second polling interval)
- Full plugin slugs as SKILL_TEST_MAP keys (e.g., `'oa-intake'`, `'document-generator'`) matching eagle-plugin/ directory names

### Patterns To Avoid

- Don't embed large TRACE_LOGS in HTML dashboard for more than ~20 tests (file becomes huge)
- Don't use server components for pages with useState/useEffect (must be 'use client')
- Don't forget to update both frontends when adding tests (HTML + Next.js)
- Don't hardcode test counts in descriptions/labels (derive from data)
- Don't use short diagram actor aliases (`intake`, `docgen`) as SKILL_TEST_MAP keys — use the full plugin slug

### Common Issues

- **Backend offline**: Chat falls back to mock responses; health indicator shows red; `/api/health` returns 502
- **trace_logs.json missing**: Tests page shows error with run instructions
- **Cognito not configured**: Auth runs in dev mode with mock user (premium tier)
- **API routes fail**: Eval page shows empty run selector, traces tab says "No test traces"
- **SKILL_TEST_MAP missing key**: Eval modal "Test Traces" tab shows no results for that skill
- **TEST_NAMES/TEST_DEFS out of sync**: New tests show raw IDs on Next.js page or are missing from HTML dashboard

### Tips

- Open `test_results_dashboard.html` directly in browser for quick test result viewing (tests 1-20)
- The eval page keyboard shortcuts: arrows (navigate), +/- (zoom), 0 (fit), Enter (view prompt)
- Filter buttons in HTML dashboard support category-based filtering (skills, workflow, aws)
- The eval page's run selector prefers CloudWatch runs first, then local files
- Dev mode auth (no Cognito) gives premium tier with admin role
- `/api/health` proxies to FastAPI and returns 502 if backend is unreachable — useful for health indicator polling

---

## Learnings

### patterns_that_work
- Dual frontend strategy: standalone HTML for quick viewing, Next.js for full dashboard
- TEST_NAMES as simple Record<string, string> makes adding tests trivial
- SKILL_TEST_MAP enables automatic cross-referencing in eval modal
- Readiness panel provides at-a-glance status for all capabilities
- Full plugin slugs as SKILL_TEST_MAP keys keeps eval page in sync with eagle-plugin/ naming
- Home page as feature hub (not chat) provides cleaner first-use experience
- DynamoDB-backed test results page (`/admin/tests`) with run list → detail drill-down (discovered: 2026-03-04)
- `encodeURIComponent(runId)` for URL-safe run_id in API calls (discovered: 2026-03-04)
- Grouping test results by `test_file` in detail view improves readability (discovered: 2026-03-04)

### patterns_to_avoid
- Don't rely on embedded data in HTML dashboard for production (use API)
- Don't mix dark and light themes within a single page component
- Don't use short diagram aliases (intake, docgen) as SKILL_TEST_MAP keys — they differ from plugin slugs
- Don't forget `errors` field in TestRun interface — DynamoDB returns it alongside `failed`/`skipped` (discovered: 2026-03-04)

### common_issues
- trace_logs.json must exist for /admin/tests to show data (legacy — new tests page uses DynamoDB)
- CloudWatch runs require AWS credentials configured in the environment
- Eval modal tabs show empty state when no run is selected
- HTML dashboard TEST_DEFS lags behind TEST_NAMES when new UC tests are added — check both before reporting test count
- `kb-review/[id]/approve` and `kb-review/[id]/reject` routes have TS errors: `params` should be `Promise<{ id: string }>` in Next.js 15+ (pre-existing)
- `@excalidraw/excalidraw` module not found — optional dependency, not installed (pre-existing)

### tips
- Use /admin/eval to demonstrate EAGLE workflow to stakeholders (10 use cases as of 2026-02-25)
- The eval page's SVG diagram supports export (right-click save as SVG)
- Run `npm run build` in client/ to verify no TypeScript errors
- SKILL_TEST_MAP line numbers shift as USE_CASES array grows — always verify line numbers with grep before editing
- Tests page now uses DynamoDB persistence — no more trace_logs.json dependency for pytest results
- Run `pytest tests/ -v` to auto-persist results to DDB (controlled by `EAGLE_PERSIST_TEST_RESULTS` env var)
