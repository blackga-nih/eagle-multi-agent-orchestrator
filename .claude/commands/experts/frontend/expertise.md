---
type: expert-file
parent: "[[frontend/_index]]"
file-type: expertise
human_reviewed: false
tags: [expert-file, mental-model, frontend, nextjs, tailwind, chat, dashboard, test-results]
last_updated: 2026-03-09T12:00:00
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
- **react-markdown** + **remark-gfm** for message rendering (GFM tables, strikethrough, task lists)
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
| `/api/sessions/generate-title` | AI session naming — POST `{ message, response_snippet }` → `{ title }` |
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
  |   |-- simple-chat-interface.tsx  # Simple chat main — horizontal flex: chat-left + ActivityPanel-right
  |   |-- simple-message-list.tsx    # Message list — mdComponents (module-scope), MemoizedMarkdown, remarkGfm, streaming split
  |   |-- simple-welcome.tsx         # Simple welcome
  |   |-- simple-header.tsx          # Simple header
  |   |-- simple-quick-actions.tsx   # Quick action buttons
  |   |-- document-card.tsx          # Document result card (links to /documents/[id])
  |   |-- activity-panel.tsx         # 3-tab right panel (Documents, Activity, Agent Logs)
  |   |-- agent-logs.tsx             # Multi-agent stream timeline with click-to-expand modal
  |   |-- command-palette.tsx        # Ctrl+K command palette
  |   |-- tool-use-display.tsx       # Inline tool call status display
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
- `simple-chat-interface.tsx`: Horizontal flex layout — left chat column + right ActivityPanel
- `simple-message-list.tsx`: Message rendering with GFM markdown (tables, lists, code), MemoizedMarkdown for completed messages, inline streaming cursor
- `simple-welcome.tsx`: Simple welcome card
- `simple-header.tsx`: Minimal header
- `simple-quick-actions.tsx`: Quick action buttons
- `document-card.tsx`: Renders document results from agent (links to `/documents/[id]`)
- `activity-panel.tsx`: 3-tab collapsible right panel (380px open / 32px closed strip)
- `agent-logs.tsx`: Multi-agent stream timeline component with LogDetailModal
- `command-palette.tsx`: Ctrl+K command palette overlay
- `tool-use-display.tsx`: Inline tool call status badges

**Layout**: `SimpleHeader` + `SidebarNav` + `SimpleChatInterface`

`SimpleChatInterface` internal layout (horizontal flex):
```
<div class="h-full flex bg-[#F5F7FA]">
  <div class="flex-1 flex flex-col min-w-0">   ← left: chat + input footer
    ...
  </div>
  <ActivityPanel ... />                         ← right: 380px or 32px strip
</div>
```

**Key state in `SimpleChatInterface`**:
- `isPanelOpen` (boolean, default `true`) — controls ActivityPanel open/closed
- `logs`, `clearLogs`, `addUserInputLog` — destructured from `useAgentStream`
- `addUserInputLog(input)` called in `handleSend()` before `sendQuery()` to echo user turns into the log stream

### Activity Panel (`components/chat-simple/activity-panel.tsx`)

**Props**:
```typescript
interface ActivityPanelProps {
  logs: AuditLogEntry[];
  clearLogs: () => void;
  documents: Record<string, DocumentInfo[]>;
  messages: ChatMessage[];
  sessionId: string | null;
  isStreaming: boolean;
  isOpen: boolean;
  onToggle: () => void;
}
```

**Tabs**: `'documents' | 'activity' | 'logs'` (default: `'logs'`)

**Closed state** (isOpen=false): 32px wide vertical strip with left-angle arrow and "Activity" spelled vertically. Click to open.

**Open state** (isOpen=true): 380px wide panel with tab bar + content scroll area.

**Documents tab** (`DocumentsTab`):
- Flattens `Record<string, DocumentInfo[]>` → array of all docs
- Renders cards with type icon from `DOC_TYPE_ICONS` map (10 doc types: sow, igce, market_research, acquisition_plan, justification, eval_criteria, security_checklist, section_508, cor_certification, contract_type_justification)
- Shows doc type, word count, status badge (saved=green, template=amber)

**Activity tab** (`ActivityTab`):
- Session ID badge (monospace, truncated)
- Stats row: user/assistant message counts + pulsing "Streaming" indicator
- Message timeline: user=blue-50 border-blue-100 / assistant=gray-50 border-gray-100

**Agent Logs tab**: renders `<AgentLogs logs={logs} />` — event count badge on tab + clear button in sub-header

**EAGLE design tokens used**:
- Background: `#F5F7FA`, `bg-white`
- Border: `#D8DEE6`
- Primary text: `#003366`
- Accent: `#2196F3` (copy button links)

### Agent Logs (`components/chat-simple/agent-logs.tsx`)

**Purpose**: Multi-agent stream timeline. Consumes `AuditLogEntry[]`, renders one card per non-reasoning event.

**Key functions**:
- `groupLogs(logs)` — filters out `type === 'reasoning'` events before render
- `getEventContent(log)` — extracts preview string: tool call signature for `tool_use`, result snippet for `tool_result`, handoff target for `handoff`, truncated content for text/error
- `formatEventType(type)` — human label: `text` → "Report", `tool_use` → "Tool Use", etc.
- `getEventTypeBadge(type)` — Tailwind class string for event type badge color

**Cards**: Agent-colored border+bg from `getAgentColors(log.agent_id)`. Shows agent icon circle, agent name, event type badge, timestamp, content preview (2-line clamp).

**Auto-scroll**: `useEffect` on `filtered.length` scrolls the container to bottom on each new entry.

**Empty state**: Gear icon + "No agent events yet." message.

**LogDetailModal**: Fixed overlay (z-50), click-outside to close, Escape key to close.
- Header: agent icon + name + event type badge
- Toggle: Formatted / Raw JSON (active = `bg-[#003366] text-white`)
- Raw JSON mode: copy-to-clipboard button
- Formatted mode: type-specific layout (tool name + input for tool_use, name + result for tool_result, content for text/error, target+reason for handoff, metadata for complete)
- Footer: log entry id + formatted timestamp

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

### Simple Message List (`simple-message-list.tsx`)

**Component**: `components/chat-simple/simple-message-list.tsx`

This component handles rendering for the `/chat` (minimalist) interface. Key patterns:

**`mdComponents` (module-scope constant)**:
- Defined once outside the component to prevent unnecessary object recreation on every render
- Covers: `p`, `ul`, `ol`, `li`, `strong`, `h1`–`h3`, `code`, `pre`, `blockquote`
- Includes full GFM table components: `table` (scrollable wrapper), `thead`, `tbody`, `tr`, `th`, `td`
- Table wrapper uses `overflow-x-auto` + `border border-gray-200 rounded-lg`

**`remarkPlugins` (module-scope constant)**:
- `const remarkPlugins = [remarkGfm]` — defined once at module scope, not inline

**`MemoizedMarkdown` component**:
- `React.memo` wrapper around `ReactMarkdown` with `remarkPlugins` + `mdComponents`
- Used for completed (non-streaming) messages only — prevents re-parsing when other messages update

**Streaming vs. completed split**:
```typescript
{isStreamingThis ? (
    // Streaming: inline ReactMarkdown — content changes every token, cursor appended
    <ReactMarkdown remarkPlugins={remarkPlugins} components={mdComponents}>
        {message.content + ' ...'}
    </ReactMarkdown>
) : (
    // Completed: MemoizedMarkdown — stable reference, no re-parse on sibling updates
    <MemoizedMarkdown content={message.content} />
)}
```

**`isStreamingThis` detection**:
```typescript
const isStreamingThis = isTyping && isLastMessage && message.role === 'assistant';
```

**`isWaitingForFirstToken` detection** (prevents double indicator):
```typescript
const isWaitingForFirstToken =
    isTyping && (messages.length === 0 || messages[lastIdx]?.role === 'user');
```
Shows bouncing typing dots only before any assistant text arrives. Once streaming message is in the list, the inline `' ...'` cursor is shown instead.

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

## Part 8: Agent Color System (`client/lib/agent-colors.ts`)

### Purpose

Centralized per-agent color scheme registry. Used by `agent-logs.tsx`, `activity-panel.tsx`, and any future components that need to render agent-specific colors.

### `AgentColorScheme` Interface

```typescript
export interface AgentColorScheme {
  bg: string;       // e.g. 'bg-blue-50'
  text: string;     // e.g. 'text-blue-700'
  border: string;   // e.g. 'border-blue-200'
  badge: string;    // e.g. 'bg-blue-100 text-blue-700'
  icon: string;     // e.g. 'bg-blue-600'  (background for icon circle)
  gradient: string; // e.g. 'from-blue-500 to-blue-600'
}
```

### `AGENT_COLORS` Map (all registered agents)

| Agent ID | Color | Role |
|----------|-------|------|
| `supervisor` | gray | Orchestration layer |
| `oa-intake` | blue | Primary interaction |
| `knowledge-retrieval` | green | RAG/search |
| `document-generator` | purple | Document creation |
| `eagle` | blue | Root agent (same as oa-intake) |
| `legal-counsel` | rose | Strands specialist |
| `market-intelligence` | teal | Strands specialist |
| `tech-translator` | cyan | Strands specialist |
| `policy-supervisor` | indigo | Strands specialist |
| `policy-librarian` | emerald | Strands specialist |
| `policy-analyst` | violet | Strands specialist |
| `public-interest` | orange | Strands specialist |
| `default` | amber | Fallback for unknown agents |

### `AGENT_NAMES` Map

Human-readable display names keyed by agent ID. Unknown IDs fall back to the raw ID string.

### `AGENT_ICONS` Map

Single-character icon letter for each agent (rendered in a colored circle):
- `supervisor` → `S`, `eagle`/`oa-intake` → `E`, `knowledge-retrieval` → `K`, `document-generator` → `D`
- `legal-counsel` → `L`, `market-intelligence` → `M`, `tech-translator` → `T`
- `policy-supervisor` → `P`, `policy-librarian` → `B`, `policy-analyst` → `A`, `public-interest` → `I`

### Helper Functions

```typescript
getAgentColors(agentId: string): AgentColorScheme  // falls back to 'default'
getAgentName(agentId: string): string              // falls back to agentId
getAgentIcon(agentId: string): string              // falls back to agentId.charAt(0).toUpperCase()
```

### Adding a New Agent

When a new agent is added to `eagle-plugin/`, add entries to all three maps in `client/lib/agent-colors.ts`:
1. `AGENT_COLORS['new-agent-id']` — choose an unused Tailwind color family
2. `AGENT_NAMES['new-agent-id']` — human-readable name
3. `AGENT_ICONS['new-agent-id']` — single uppercase letter (check for conflicts)

---

## Part 9: useAgentStream Hook (`client/hooks/use-agent-stream.ts`)

### Return Shape

```typescript
export interface UseAgentStreamReturn {
  sendQuery: (query: string, sessionId?: string) => Promise<void>;
  isStreaming: boolean;
  logs: AuditLogEntry[];        // all SSE events collected during session
  lastMessage: Message | null;
  lastDocument: DocumentInfo | null;
  clearLogs: () => void;        // clears logs + resets message/document state
  error: string | null;
  addUserInputLog: (content: string) => void;   // echo user turn to logs
  addFormSubmitLog: (formType: string, data: Record<string, unknown>, summary?: string) => void;
}
```

### Log Entry Sources

`logs` accumulates `AuditLogEntry` objects from three origins:
1. **SSE events** — every parsed `StreamEvent` from the backend gets an `id: 'log-N'` prefix and is appended
2. **`addUserInputLog(content)`** — called by `SimpleChatInterface.handleSend()` before `sendQuery()` to add a `type:'text'` entry with `agent_id:'user'`
3. **`addFormSubmitLog(formType, data, summary?)`** — adds a `type:'metadata'` entry with `agent_id:'user'` for form submission events

### AuditLogEntry Type

`AuditLogEntry` extends `StreamEvent` with a required `id: string`. `StreamEvent` fields:

```typescript
{
  type: StreamEventType;   // text|reasoning|tool_use|tool_result|elicitation|metadata|complete|error|handoff|user_input|form_submit
  agent_id: string;
  agent_name: string;
  timestamp: string;       // ISO string
  content?: string;
  reasoning?: string;
  tool_use?: { name, input, tool_use_id?, execution_target? };
  tool_result?: { name, result };
  elicitation?: { question, fields? };
  metadata?: Record<string, any>;
}
```

### Consuming logs in a component

```typescript
const { logs, clearLogs, addUserInputLog } = useAgentStream({ ... });

// To pass to ActivityPanel:
<ActivityPanel logs={logs} clearLogs={clearLogs} ... />

// To echo user input before sendQuery:
addUserInputLog(input);
await sendQuery(query, sessionId);
```

### groupLogs() filter pattern

Before rendering, filter out `reasoning` events to keep the log panel clean:

```typescript
function groupLogs(logs: AuditLogEntry[]): AuditLogEntry[] {
  return logs.filter(l => (l.type as string) !== 'reasoning');
}
```

---

## Part 10: Known Issues and Patterns

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
- Collapsible right panel pattern: open=380px, closed=32px strip (vertical label + arrow)
- Agent color system centralized in `client/lib/agent-colors.ts` — all 12 agents registered
- `groupLogs()` to filter reasoning events before rendering the Agent Logs tab
- `addUserInputLog(input)` called in `handleSend()` so user turns appear in the agent log timeline
- Activity panel default tab is `'logs'` — most useful tab on first open
- LogDetailModal: Formatted/Raw JSON toggle, Escape key to close, click-outside to close
- `useEffect` on `filtered.length` for auto-scroll-to-bottom in log timeline
- Module-scope `mdComponents` + `remarkPlugins` constants in `simple-message-list.tsx` prevent object recreation on every render (discovered: 2026-03-09)
- `MemoizedMarkdown` (`React.memo`) for completed messages — only streaming message re-renders on each token (discovered: 2026-03-09)
- Split streaming/completed rendering: streaming appends `' ...'` cursor inline; completed uses memoized component (discovered: 2026-03-09)
- GFM table rendering requires both `remarkGfm` plugin AND all 6 table HTML components (`table`, `thead`, `tbody`, `tr`, `th`, `td`) in the components map (discovered: 2026-03-09)
- `validate-sse-pipeline.spec.ts` covers SSE schema, tool pairing, and tool card rendering — superset of the deprecated `validate-tool-cards-chevron.spec.ts` (discovered: 2026-03-09)

### Patterns To Avoid

- Don't embed large TRACE_LOGS in HTML dashboard for more than ~20 tests (file becomes huge)
- Don't use server components for pages with useState/useEffect (must be 'use client')
- Don't forget to update both frontends when adding tests (HTML + Next.js)
- Don't hardcode test counts in descriptions/labels (derive from data)
- Don't use short diagram actor aliases (`intake`, `docgen`) as SKILL_TEST_MAP keys — use the full plugin slug
- Don't add a new agent to eagle-plugin/ without updating `AGENT_COLORS`, `AGENT_NAMES`, and `AGENT_ICONS` in `agent-colors.ts`
- Don't use the horizontal flex layout inside a `flex-col` parent without `min-w-0` on the flex-1 child — this causes overflow
- Don't define `components` or `remarkPlugins` inline inside JSX — each render creates a new object reference, thrashing ReactMarkdown's memoization (discovered: 2026-03-09)
- Don't apply `MemoizedMarkdown` to the actively-streaming message — content changes every token and memo would suppress updates (discovered: 2026-03-09)
- Don't use `taskkill /F /PID` in Git Bash without `MSYS_NO_PATHCONV=1` — MSYS converts `/F` to a Unix file path and the command silently fails (discovered: 2026-03-09)
- Don't rename a superseded Playwright spec in place — prefix with `_deprecated_` so it is excluded from test runs while preserving git history (discovered: 2026-03-09)

### Common Issues

- **Backend offline**: Chat falls back to mock responses; health indicator shows red; `/api/health` returns 502
- **trace_logs.json missing**: Tests page shows error with run instructions
- **Cognito not configured**: Auth runs in dev mode with mock user (premium tier)
- **API routes fail**: Eval page shows empty run selector, traces tab says "No test traces"
- **SKILL_TEST_MAP missing key**: Eval modal "Test Traces" tab shows no results for that skill
- **TEST_NAMES/TEST_DEFS out of sync**: New tests show raw IDs on Next.js page or are missing from HTML dashboard
- **Unknown agent_id in logs**: Agent Logs renders with amber "default" color scheme — add to `agent-colors.ts`
- **ActivityPanel not visible**: Verify parent has `flex` (horizontal) not `flex flex-col`; SimpleChatInterface wraps in `<div class="h-full flex">`
- **Markdown tables not rendering**: Check both (a) `remarkGfm` in `remarkPlugins` array and (b) all 6 table components (`table`/`thead`/`tbody`/`tr`/`th`/`td`) in the `components` prop — either missing alone will break tables (discovered: 2026-03-09)
- **Next.js dev server EPERM `.next/trace`**: Stale node process holding file lock — see `fix-next-cache.md` for kill + clear procedure (discovered: 2026-03-09)
- **`taskkill /F /PID` fails silently in Git Bash**: MSYS path conversion mangles `/F` flag — prefix command with `MSYS_NO_PATHCONV=1` (discovered: 2026-03-09)

### Tips

- Open `test_results_dashboard.html` directly in browser for quick test result viewing (tests 1-20)
- The eval page keyboard shortcuts: arrows (navigate), +/- (zoom), 0 (fit), Enter (view prompt)
- Filter buttons in HTML dashboard support category-based filtering (skills, workflow, aws)
- The eval page's run selector prefers CloudWatch runs first, then local files
- Dev mode auth (no Cognito) gives premium tier with admin role
- `/api/health` proxies to FastAPI and returns 502 if backend is unreachable — useful for health indicator polling
- Agent Logs tab shows event count badge — useful for confirming the stream is running
- Click any event card in Agent Logs to open the LogDetailModal with full event details
- Use "Raw JSON" toggle in LogDetailModal to inspect the full AuditLogEntry for debugging

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
- 3-tab right panel (Documents/Activity/Agent Logs) as sibling of chat column in horizontal flex (discovered: 2026-03-04)
- Collapsible panel: open=380px / closed=32px toggle strip with vertical label (discovered: 2026-03-04)
- `groupLogs()` filtering reasoning events keeps Agent Logs tab readable during long streams (discovered: 2026-03-04)
- `addUserInputLog()` called before `sendQuery()` ensures user turns appear as first entry in each log sequence (discovered: 2026-03-04)
- LogDetailModal Formatted/Raw JSON toggle covers both human review and developer debugging in one modal (discovered: 2026-03-04)
- Centralizing agent colors in `agent-colors.ts` with `getAgentColors()`/`getAgentName()`/`getAgentIcon()` helpers makes new agent onboarding a 3-line change (discovered: 2026-03-04)
- Module-scope `mdComponents` constant (defined outside the component) avoids React object churn on every render (discovered: 2026-03-09, component: simple-message-list)
- `MemoizedMarkdown = React.memo(...)` for completed messages eliminates redundant ReactMarkdown re-parses when new messages stream in (discovered: 2026-03-09, component: simple-message-list)
- Streaming cursor pattern: append `' ...'` to `message.content` in the streaming branch; remove it automatically when `isStreamingThis` becomes false (discovered: 2026-03-09, component: simple-message-list)
- `fix-next-cache.md` skill doc: encoding Windows-specific troubleshooting steps as a runnable script makes cache issues a 30-second fix instead of a debug session (discovered: 2026-03-09)
- `MSYS_NO_PATHCONV=1` prefix prevents Git Bash (MSYS2) from converting Windows-style flags (`/F`, `/PID`) in `taskkill` (discovered: 2026-03-09)
- Playwright test consolidation: `validate-sse-pipeline.spec.ts` subsumes `validate-tool-cards-chevron.spec.ts` — prefixing deprecated tests with `_deprecated_` keeps them out of runs while preserving history (discovered: 2026-03-09)

### patterns_to_avoid
- Don't rely on embedded data in HTML dashboard for production (use API)
- Don't mix dark and light themes within a single page component
- Don't use short diagram aliases (intake, docgen) as SKILL_TEST_MAP keys — they differ from plugin slugs
- Don't forget `errors` field in TestRun interface — DynamoDB returns it alongside `failed`/`skipped` (discovered: 2026-03-04)
- Don't add a new Strands agent without updating all three maps in `agent-colors.ts` — unknown agents render amber fallback color
- Don't put `useEffect` network calls (e.g. health checks) inside components that mount on every page — use a shared context provider instead (discovered: 2026-03-05)
- Don't define `components` or `remarkPlugins` as inline JSX expressions — each render creates a new reference, defeating ReactMarkdown memoization (discovered: 2026-03-09, component: simple-message-list)
- Don't apply `React.memo` to the actively-streaming message branch — it will suppress token-by-token updates (discovered: 2026-03-09, component: simple-message-list)
- Don't run `taskkill /F /PID` raw in Git Bash without `MSYS_NO_PATHCONV=1` — the command silently fails (discovered: 2026-03-09)

### common_issues
- trace_logs.json must exist for /admin/tests to show data (legacy — new tests page uses DynamoDB)
- CloudWatch runs require AWS credentials configured in the environment
- Eval modal tabs show empty state when no run is selected
- HTML dashboard TEST_DEFS lags behind TEST_NAMES when new UC tests are added — check both before reporting test count
- `kb-review/[id]/approve` and `kb-review/[id]/reject` routes have TS errors: `params` should be `Promise<{ id: string }>` in Next.js 15+ (pre-existing)
- `@excalidraw/excalidraw` module not found — optional dependency, not installed (pre-existing)
- ActivityPanel internal default tab is 'logs' — if you want a different default, change `useState<TabId>('logs')` in `activity-panel.tsx`
- Navigation between protected pages feels slow: TopNav was re-mounting on every page (not in shared layout), firing checkBackendHealth() on each nav — fixed by BackendStatusContext (2026-03-05)
- GFM tables render as plain text (no grid): missing either `remarkGfm` plugin or any of the 6 table HTML components in the `components` prop — both are required (discovered: 2026-03-09, component: simple-message-list)
- `.next/trace` EPERM lock after crash: kill all Next.js node processes, then `mv .next/trace .next/trace.old` before restart (see `fix-next-cache.md`) (discovered: 2026-03-09)

### tips
- Use /admin/eval to demonstrate EAGLE workflow to stakeholders (10 use cases as of 2026-02-25)
- The eval page's SVG diagram supports export (right-click save as SVG)
- Run `npm run build` in client/ to verify no TypeScript errors
- SKILL_TEST_MAP line numbers shift as USE_CASES array grows — always verify line numbers with grep before editing
- Tests page now uses DynamoDB persistence — no more trace_logs.json dependency for pytest results
- Run `pytest tests/ -v` to auto-persist results to DDB (controlled by `EAGLE_PERSIST_TEST_RESULTS` env var)
- Agent Logs "Clear" button only appears when `logs.length > 0` and `activeTab === 'logs'`
- The `addFormSubmitLog()` hook export is available but not yet wired to any form — use it to log intake form submissions to the Agent Logs tab
- To fix zombie Next.js processes locking `.next/trace`, run the automated cleanup in `fix-next-cache.md` (kills Next.js node processes, clears trace file, restarts)
- `validate-sse-pipeline.spec.ts` is the canonical tool-card E2E test — it validates SSE schema, 1:1 tool pairing, chevron expand/collapse, and green status dot in one run
- Tool card Playwright selector: `.my-1.rounded-lg.border` — matches `ToolUseDisplay` wrapper class in `tool-use-display.tsx`
- When adding GFM table support, add `remarkGfm` to both `remarkPlugins` constant AND ensure all 6 table HTML elements are in `mdComponents` (discovered: 2026-03-09)
- `_deprecated_` prefix on Playwright specs excludes them from `npx playwright test` glob while keeping them in git history for reference (discovered: 2026-03-09)
