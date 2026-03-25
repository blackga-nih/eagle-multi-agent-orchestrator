# EAGLE Codebase Refactoring Guide

Status: Historical analysis and roadmap snapshot. Use [`20260325-refactor-completion-plan.md`](/Users/hoquemi/Desktop/sm_eagle/docs/20260325-refactor-completion-plan.md) for current execution status and [`refactor-status-index.md`](/Users/hoquemi/Desktop/sm_eagle/docs/refactor-status-index.md) for document routing.

**Date:** 2026-03-19
**Status:** Historical - Analysis Complete
**Estimated Total Duplicated/Dead Code:** ~2,500+ lines

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [High Severity Issues](#high-severity-issues)
   - [1. DynamoDB Client Initialization Duplication](#1-dynamodb-client-initialization-duplication)
   - [2. agentic_service.py Mixed Responsibilities](#2-agentic_servicepy-mixed-responsibilities)
   - [3. _exec_create_document() Function Overload](#3-_exec_create_document-function-overload)
   - [4. simple-chat-interface.tsx Component Bloat](#4-simple-chat-interfacetsx-component-bloat)
   - [5. Agent Logs Component Duplication](#5-agent-logs-component-duplication)
   - [6. Date Formatting Duplication](#6-date-formatting-duplication)
   - [7. Configuration Sprawl](#7-configuration-sprawl)
   - [8. Dead Code - mcp_agent_integration.py](#8-dead-code---mcp_agent_integrationpy)
3. [Structural Issues (From Architecture Audit)](#structural-issues-from-architecture-audit)
   - [9. Frontend Persistence Fragmentation](#9-frontend-persistence-fragmentation)
   - [10. Template Duplication Across Trees](#10-template-duplication-across-trees)
   - [11. Diagram Source Duplication](#11-diagram-source-duplication)
   - [12. Workspace Store Naming Confusion](#12-workspace-store-naming-confusion)
   - [13. Repository Hygiene Issues](#13-repository-hygiene-issues)
   - [14. Infrastructure Options Overlap](#14-infrastructure-options-overlap)
   - [15. Justfile Platform Mixing](#15-justfile-platform-mixing)
4. [Medium Severity Issues](#medium-severity-issues)
5. [Low Severity Issues](#low-severity-issues)
6. [Files That Are Large But OK](#files-that-are-large-but-ok)
7. [Target Architecture](#target-architecture)
8. [Redundancy Map](#redundancy-map)
9. [Implementation Roadmap](#implementation-roadmap)
10. [Related Documentation](#related-documentation)

---

## Executive Summary

This document identifies genuine refactoring opportunities in the EAGLE codebase, distinguishing between files that are problematic vs. files that are legitimately large due to complexity.

### Key Findings

| Category | Count | Estimated Lines Affected |
|----------|-------|--------------------------|
| High Severity (Code) | 8 issues | ~2,000 lines |
| Structural Issues | 7 issues | Architecture-level |
| Medium Severity | 7 issues | ~500 lines |
| Low Severity | 5 issues | ~200 lines |
| Dead Code | 2 files | ~300 lines |
| Asset Duplication | 2 areas | Templates + Diagrams |

### Primary Themes

1. **Code Duplication:** DynamoDB client initialization repeated in 16+ files; agent logs components nearly identical
2. **Responsibility Overload:** `agentic_service.py` (3,736 lines) and `simple-chat-interface.tsx` (777 lines) do too many things
3. **Scattered Configuration:** Environment variables spread across 25+ files with no central source of truth
4. **Dead Code:** Unused files and deprecated functions still in codebase
5. **Asset Duplication:** Templates and diagrams exist in multiple directories with drift
6. **Legacy Entanglement:** Deprecated orchestration still anchors active code paths
7. **Competing Abstractions:** Multiple frontend persistence models, overlapping infrastructure options

---

## High Severity Issues

### 1. DynamoDB Client Initialization Duplication

#### Problem Statement

Every store module implements identical lazy singleton patterns for AWS clients. This creates ~300 lines of pure duplication across 16+ files.

#### Affected Files

```
server/app/session_store.py          (lines 29-37)
server/app/document_store.py         (lines 34-42)
server/app/approval_store.py
server/app/audit_store.py
server/app/changelog_store.py
server/app/config_store.py
server/app/feedback_store.py
server/app/package_store.py
server/app/plugin_store.py
server/app/pref_store.py
server/app/prompt_store.py
server/app/skill_store.py
server/app/template_store.py
server/app/test_result_store.py
server/app/workspace_store.py
server/app/wspc_store.py
server/app/agentic_service.py        (lines 143-161)
```

#### Current Pattern (Duplicated)

```python
# This exact pattern appears in EVERY store file:

_dynamodb = None
_s3 = None

def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        _dynamodb = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-east-1"))
    return _dynamodb

def _get_s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
    return _s3

def _get_table():
    return _get_dynamodb().Table(os.getenv("EAGLE_SESSIONS_TABLE", "eagle"))
```

#### Why This Is a Problem

1. **Maintenance Burden:** If the singleton pattern needs to change (e.g., adding connection pooling), you must update 16+ files
2. **Consistency Risk:** Different files could diverge accidentally (e.g., one uses a different default region)
3. **Testing Nightmare:** Each file needs its own mocking setup for AWS clients
4. **No Connection Reuse:** Each store gets its own client instance instead of sharing

#### Recommended Solution

Create a new shared module: `server/app/db_client.py`

```python
"""
Centralized AWS client management for EAGLE.
All store modules should import from here instead of creating their own clients.
"""
import os
from functools import lru_cache
from typing import Any

import boto3
from mypy_boto3_dynamodb import DynamoDBServiceResource
from mypy_boto3_s3 import S3Client
from mypy_boto3_logs import CloudWatchLogsClient


# Configuration
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
EAGLE_TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
EAGLE_BUCKET_NAME = os.getenv("EAGLE_S3_BUCKET", "eagle-documents")


@lru_cache(maxsize=1)
def get_dynamodb() -> DynamoDBServiceResource:
    """Get shared DynamoDB resource. Cached for connection reuse."""
    return boto3.resource("dynamodb", region_name=AWS_REGION)


@lru_cache(maxsize=1)
def get_s3() -> S3Client:
    """Get shared S3 client. Cached for connection reuse."""
    return boto3.client("s3", region_name=AWS_REGION)


@lru_cache(maxsize=1)
def get_cloudwatch_logs() -> CloudWatchLogsClient:
    """Get shared CloudWatch Logs client. Cached for connection reuse."""
    return boto3.client("logs", region_name=AWS_REGION)


@lru_cache(maxsize=1)
def get_table():
    """Get the main EAGLE DynamoDB table."""
    return get_dynamodb().Table(EAGLE_TABLE_NAME)


def item_to_dict(item: dict) -> dict:
    """
    Convert DynamoDB item to plain dict, handling Decimal types.
    Shared utility for all stores.
    """
    from decimal import Decimal

    def convert(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        elif isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert(i) for i in obj]
        return obj

    return convert(item)


def now_iso() -> str:
    """Return current UTC timestamp in ISO format. Shared utility."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
```

#### Migration Steps

1. Create `server/app/db_client.py` with the above content
2. For each store file:
   ```python
   # Before:
   _dynamodb = None
   def _get_dynamodb(): ...
   def _get_table(): ...

   # After:
   from .db_client import get_table, get_s3, item_to_dict, now_iso
   ```
3. Remove local `_get_dynamodb()`, `_get_s3()`, `_get_table()`, `_item_to_dict()`, `_now_iso()` functions
4. Run tests to verify functionality

#### Estimated Impact

- **Lines Removed:** ~300 (20 lines x 16 files)
- **Lines Added:** ~60 (new db_client.py)
- **Net Reduction:** ~240 lines
- **Testing Improvement:** Single mock point for all AWS clients

---

### 2. agentic_service.py Mixed Responsibilities

#### Problem Statement

`server/app/agentic_service.py` is a 3,736-line monolith that mixes business logic, AWS integration, tool dispatch, and data extraction. This makes it nearly impossible to unit test individual concerns.

#### File Location

`server/app/agentic_service.py` (3,736 lines)

#### Current Responsibilities (All in One File)

| Responsibility | Lines | Examples |
|----------------|-------|----------|
| Document Generation | ~800 | `_generate_sow()`, `_generate_igce()`, `_generate_ap()` |
| Data Extraction | ~300 | `_extract_first_money_value()`, `_extract_section_bullets()` |
| Context Handling | ~400 | `_augment_document_data_from_context()`, `_normalize_context_text()` |
| Tool Dispatch | ~500 | `execute_tool()`, `TOOL_DISPATCH` dict |
| Tool Handlers | ~1000 | `_exec_create_document()`, `_exec_search_far()`, etc. |
| AWS Operations | ~200 | Direct S3, DynamoDB, CloudWatch calls |
| Utilities | ~200 | Type inference, path handling, validation |

#### Why This Is a Problem

1. **Cannot Test in Isolation:** To test `_generate_sow()`, you need to mock S3, DynamoDB, and CloudWatch
2. **Tight Coupling:** Changes to one area risk breaking others
3. **Poor Discoverability:** Finding relevant code requires scrolling through 3,700 lines
4. **No Reusability:** Cannot use document extractors without importing entire file

#### Recommended Solution

Split into focused modules:

```
server/app/
├── agentic_service.py           # Reduced to orchestration only (~500 lines)
├── document_generators/
│   ├── __init__.py
│   ├── base.py                  # Abstract base class
│   ├── sow_generator.py         # SOW-specific logic
│   ├── igce_generator.py        # IGCE-specific logic
│   ├── ap_generator.py          # Acquisition Plan logic
│   └── far_search.py            # FAR/DFARS search
├── tool_handlers/
│   ├── __init__.py
│   ├── registry.py              # TOOL_DISPATCH dict
│   ├── document_handler.py      # _exec_create_document
│   ├── search_handler.py        # _exec_search_far
│   └── context_handler.py       # Context-related tools
├── extractors/
│   ├── __init__.py
│   ├── money.py                 # _extract_first_money_value
│   ├── bullets.py               # _extract_section_bullets
│   └── sow_targets.py           # _extract_sow_clear_targets
└── context_utils.py             # _augment_document_data_from_context
```

#### Example: Extract Document Generator

**Before (in agentic_service.py):**
```python
def _generate_sow(context: dict, template: str) -> str:
    # 150 lines of SOW generation logic
    ...
```

**After (in document_generators/sow_generator.py):**
```python
"""Statement of Work generator."""
from typing import Optional
from .base import DocumentGenerator


class SOWGenerator(DocumentGenerator):
    """Generates Statement of Work documents from context data."""

    def __init__(self, template_service):
        self.template_service = template_service

    def generate(self, context: dict, template: Optional[str] = None) -> str:
        """
        Generate a SOW document.

        Args:
            context: Acquisition context containing requirements, CLINs, etc.
            template: Optional template override

        Returns:
            Generated SOW content as string
        """
        # Clean, testable logic here
        ...
```

#### Migration Steps

1. Create `document_generators/` directory with base class
2. Extract one generator at a time (start with `sow_generator.py`)
3. Update imports in `agentic_service.py` to use new modules
4. Add unit tests for each extracted module
5. Repeat for tool handlers and extractors
6. Final `agentic_service.py` should only handle orchestration

#### Estimated Impact

- **Original:** 3,736 lines in 1 file
- **After:** ~500 lines orchestration + ~3,000 lines in focused modules
- **Benefit:** Each module can be tested independently

---

### 3. _exec_create_document() Function Overload

#### Problem Statement

The `_exec_create_document()` function in `agentic_service.py` is 300+ lines handling 6+ distinct code paths with deeply nested conditionals.

#### File Location

`server/app/agentic_service.py` (lines 1829-2100+)

#### Current Code Paths in Single Function

1. **Inline Edit Path:** User provides inline edits to existing content
2. **AI Content Generation:** Generate content via AI model
3. **Template Generation:** Use document templates
4. **Package Document Path:** Route through package service
5. **Direct S3 Storage:** Store directly to S3
6. **Response Building:** Different response structures per path

#### Why This Is a Problem

```python
def _exec_create_document(tool_input: dict, context: dict) -> dict:
    # Path 1: Check if inline edit
    if tool_input.get("inline_edit"):
        # 50 lines of inline edit handling
        if tool_input.get("use_ai"):
            # 30 lines of AI-assisted edit
        else:
            # 20 lines of direct edit

    # Path 2: Template or AI generation
    elif tool_input.get("template_id"):
        # 80 lines of template handling
        if context.get("package_id"):
            # 40 lines of package routing
        else:
            # 40 lines of direct storage

    # Path 3: Pure AI generation
    else:
        # 100 lines of AI generation
        # More nested conditionals...

    # Response building varies by path
    return response  # Different structures!
```

**Problems:**
- Cannot test inline edit path without setting up template infrastructure
- Changes to AI generation risk breaking template path
- Response contract is unclear (different shapes per path)

#### Recommended Solution

Apply Strategy Pattern with clear handler interface:

```python
# tool_handlers/document_handler.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class DocumentResult:
    """Standardized result from all document operations."""
    document_id: str
    document_type: str
    content: str
    s3_key: Optional[str] = None
    package_id: Optional[str] = None
    version: int = 1


class DocumentHandler(ABC):
    """Base class for document creation strategies."""

    @abstractmethod
    def can_handle(self, tool_input: dict) -> bool:
        """Return True if this handler can process the input."""
        pass

    @abstractmethod
    def handle(self, tool_input: dict, context: dict) -> DocumentResult:
        """Process the document creation request."""
        pass


class InlineEditHandler(DocumentHandler):
    """Handles inline document edits."""

    def can_handle(self, tool_input: dict) -> bool:
        return bool(tool_input.get("inline_edit"))

    def handle(self, tool_input: dict, context: dict) -> DocumentResult:
        # Clean 50-line implementation
        ...


class TemplateGenerationHandler(DocumentHandler):
    """Handles template-based document generation."""

    def can_handle(self, tool_input: dict) -> bool:
        return bool(tool_input.get("template_id"))

    def handle(self, tool_input: dict, context: dict) -> DocumentResult:
        # Clean 80-line implementation
        ...


class AIGenerationHandler(DocumentHandler):
    """Handles AI-powered document generation."""

    def can_handle(self, tool_input: dict) -> bool:
        return True  # Default handler

    def handle(self, tool_input: dict, context: dict) -> DocumentResult:
        # Clean 100-line implementation
        ...


# Handler registry
DOCUMENT_HANDLERS = [
    InlineEditHandler(),
    TemplateGenerationHandler(),
    AIGenerationHandler(),  # Must be last (default)
]


def exec_create_document(tool_input: dict, context: dict) -> dict:
    """
    Create a document using the appropriate strategy.
    Clean 20-line orchestration function.
    """
    for handler in DOCUMENT_HANDLERS:
        if handler.can_handle(tool_input):
            result = handler.handle(tool_input, context)
            return {
                "document_id": result.document_id,
                "document_type": result.document_type,
                "content": result.content,
                "s3_key": result.s3_key,
                "package_id": result.package_id,
                "version": result.version,
            }

    raise ValueError("No handler found for document request")
```

#### Migration Steps

1. Create `tool_handlers/document_handler.py` with base class and `DocumentResult`
2. Extract `InlineEditHandler` first (smallest, easiest to test)
3. Add comprehensive tests for inline edit
4. Extract `TemplateGenerationHandler`
5. Extract `AIGenerationHandler`
6. Replace `_exec_create_document()` with new orchestrator
7. Remove old function

#### Estimated Impact

- **Before:** 300 lines, untestable paths
- **After:** 4 files, ~400 lines total, each independently testable
- **Benefit:** Clear contracts, easy to add new document types

---

### 4. simple-chat-interface.tsx Component Bloat

#### Problem Statement

`simple-chat-interface.tsx` has 777 lines with 13+ useState calls, mixing session management, streaming, tool tracking, uploads, and keyboard shortcuts in one component.

#### File Location

`client/components/chat-simple/simple-chat-interface.tsx` (777 lines)

#### Current State Variables (13+)

```typescript
// All in one component:
const [messages, setMessages] = useState<Message[]>([]);
const [streamingMsg, setStreamingMsg] = useState<Message | null>(null);
const [input, setInput] = useState("");
const [isLoadingSession, setIsLoadingSession] = useState(true);
const [documents, setDocuments] = useState<GeneratedDocument[]>([]);
const [toolCallsByMsg, setToolCallsByMsg] = useState<Record<string, ToolCall[]>>({});
const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
const [feedbackStatus, setFeedbackStatus] = useState<FeedbackStatus | null>(null);
const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
const [isPackageSelectorOpen, setIsPackageSelectorOpen] = useState(false);
const [isDragging, setIsDragging] = useState(false);
const [isPanelOpen, setIsPanelOpen] = useState(true);
```

#### Mixed Concerns in One Component

| Concern | Description | Lines |
|---------|-------------|-------|
| Session Management | Load, save, title generation | ~100 |
| Streaming State | Message lifecycle, tool calls | ~150 |
| Document Tracking | Deduplication, persistence | ~80 |
| File Upload | Drag-drop, validation | ~100 |
| Input Handling | Slash commands, keyboard shortcuts | ~80 |
| Command Palette | Ctrl+K state | ~50 |
| Panel State | Collapse/expand | ~30 |
| Effects | Multiple interdependent useEffects | ~100 |

#### Why This Is a Problem

1. **Impossible to Test:** Cannot test session loading without mocking streaming, documents, uploads
2. **Effect Spaghetti:** Multiple useEffects depend on each other, hard to trace execution order
3. **Prop Drilling:** Passes 7+ props to child components
4. **No Reuse:** Session management logic cannot be used in other chat interfaces

#### Recommended Solution

Extract into focused hooks and context:

```typescript
// hooks/use-session-management.ts
export function useSessionManagement(sessionId: string) {
  const [isLoading, setIsLoading] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessionTitle, setSessionTitle] = useState("");

  // Session loading logic
  useEffect(() => {
    loadSession(sessionId).then(data => {
      setMessages(data.messages);
      setSessionTitle(data.title);
      setIsLoading(false);
    });
  }, [sessionId]);

  // Auto-save logic
  const saveSession = useCallback(async () => {
    await persistSession(sessionId, messages, sessionTitle);
  }, [sessionId, messages, sessionTitle]);

  return {
    isLoading,
    messages,
    setMessages,
    sessionTitle,
    setSessionTitle,
    saveSession,
  };
}


// hooks/use-tool-tracking.ts
export function useToolTracking() {
  const [toolCallsByMsg, setToolCallsByMsg] = useState<Record<string, ToolCall[]>>({});
  const [pendingToolCalls, setPendingToolCalls] = useState<Set<string>>(new Set());

  const registerToolCall = useCallback((msgId: string, toolCall: ToolCall) => {
    setToolCallsByMsg(prev => ({
      ...prev,
      [msgId]: [...(prev[msgId] || []), toolCall],
    }));
  }, []);

  const markToolComplete = useCallback((toolCallId: string) => {
    setPendingToolCalls(prev => {
      const next = new Set(prev);
      next.delete(toolCallId);
      return next;
    });
  }, []);

  return {
    toolCallsByMsg,
    pendingToolCalls,
    registerToolCall,
    markToolComplete,
  };
}


// contexts/ChatContext.tsx
interface ChatContextValue {
  sessionId: string;
  documents: GeneratedDocument[];
  toolCallsByMsg: Record<string, ToolCall[]>;
  agentStatus: AgentStatus | null;
}

export const ChatContext = createContext<ChatContextValue | null>(null);

export function ChatProvider({ sessionId, children }: Props) {
  const session = useSessionManagement(sessionId);
  const tools = useToolTracking();
  const [documents, setDocuments] = useState<GeneratedDocument[]>([]);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);

  return (
    <ChatContext.Provider value={{
      sessionId,
      documents,
      toolCallsByMsg: tools.toolCallsByMsg,
      agentStatus,
    }}>
      {children}
    </ChatContext.Provider>
  );
}


// Refactored simple-chat-interface.tsx (~200 lines)
export function SimpleChatInterface({ sessionId }: Props) {
  const session = useSessionManagement(sessionId);
  const tools = useToolTracking();
  const upload = useFileUpload();
  const [input, setInput] = useState("");

  // Much cleaner component with delegated concerns
  return (
    <ChatProvider sessionId={sessionId}>
      <div className="flex h-full">
        <ChatArea
          messages={session.messages}
          isLoading={session.isLoading}
          onSend={handleSend}
        />
        <ActivityPanel />
      </div>
    </ChatProvider>
  );
}
```

#### New File Structure

```
client/
├── hooks/
│   ├── use-session-management.ts    # NEW: Session load/save
│   ├── use-tool-tracking.ts         # NEW: Tool call state
│   ├── use-file-upload.ts           # NEW: Upload handling
│   └── use-agent-stream.ts          # Existing, simplified
├── contexts/
│   └── ChatContext.tsx              # NEW: Shared chat state
└── components/chat-simple/
    └── simple-chat-interface.tsx    # Reduced to ~200 lines
```

#### Migration Steps

1. Create `use-session-management.ts` - extract session loading/saving
2. Create `use-tool-tracking.ts` - extract tool call state
3. Create `use-file-upload.ts` - extract drag-drop and upload logic
4. Create `ChatContext.tsx` - eliminate prop drilling
5. Refactor `simple-chat-interface.tsx` to use new hooks/context
6. Update child components to use context instead of props

#### Estimated Impact

- **Before:** 777 lines, untestable
- **After:** ~200 lines + 4 focused modules (~600 lines total)
- **Benefit:** Each hook can be tested independently; components use context

---

### 5. Agent Logs Component Duplication

#### Problem Statement

Two nearly identical agent logs components exist with the same logic for event filtering, badge coloring, and modal rendering.

#### Affected Files

| File | Lines | Location |
|------|-------|----------|
| `agent-logs.tsx` | 578 | `client/components/chat-simple/` |
| `multi-agent-logs.tsx` | 448 | `client/components/chat/` |

**Total duplicated code:** ~1,000 lines

#### Duplicated Logic

Both files contain:

```typescript
// Identical in both files:
function formatEventType(type: string): string { ... }
function getEventTypeBadge(type: string): string { ... }
function getEventIcon(type: string): React.ReactNode { ... }
function formatTime(timestamp: string): string { ... }

// Identical collapse logic:
const collapsedEvents = useMemo(() => {
  return events.reduce((acc, event) => {
    // Same text event collapsing logic
  }, []);
}, [events]);

// Identical badge color mapping:
const badgeColors = {
  tool_use: "bg-blue-100 text-blue-800",
  tool_result: "bg-green-100 text-green-800",
  reasoning: "bg-purple-100 text-purple-800",
  // ... same colors
};
```

#### Why This Is a Problem

1. **Bug Fixes Required Twice:** A fix in one file must be manually applied to the other
2. **Styling Drift:** Badge colors could diverge, confusing users
3. **Feature Disparity:** New event types need to be added in two places
4. **Maintenance Cost:** ~1,000 lines to maintain instead of ~500

#### Recommended Solution

Consolidate into a single, configurable component:

```typescript
// components/shared/agent-logs-viewer.tsx

import { useMemo } from 'react';
import { formatRelativeTime } from '@/lib/date-utils';

interface AgentLogsViewerProps {
  events: AgentEvent[];
  variant?: 'compact' | 'detailed';  // For different UI contexts
  showModal?: boolean;
  onEventClick?: (event: AgentEvent) => void;
}

// Shared utilities
const EVENT_CONFIG = {
  tool_use: {
    badge: "bg-blue-100 text-blue-800",
    icon: WrenchIcon,
    label: "Tool Use",
  },
  tool_result: {
    badge: "bg-green-100 text-green-800",
    icon: CheckCircleIcon,
    label: "Result",
  },
  reasoning: {
    badge: "bg-purple-100 text-purple-800",
    icon: BrainIcon,
    label: "Reasoning",
  },
  // ... all event types
} as const;

function formatEventType(type: string): string {
  return EVENT_CONFIG[type]?.label ?? type;
}

function getEventTypeBadge(type: string): string {
  return EVENT_CONFIG[type]?.badge ?? "bg-gray-100 text-gray-800";
}

export function AgentLogsViewer({
  events,
  variant = 'detailed',
  showModal = true,
  onEventClick,
}: AgentLogsViewerProps) {
  // Shared collapse logic
  const collapsedEvents = useMemo(() => {
    return collapseConsecutiveTextEvents(events);
  }, [events]);

  // Shared rendering with variant support
  return (
    <div className={variant === 'compact' ? 'space-y-1' : 'space-y-2'}>
      {collapsedEvents.map(event => (
        <AgentLogEntry
          key={event.id}
          event={event}
          variant={variant}
          onClick={onEventClick}
        />
      ))}
    </div>
  );
}
```

#### Migration Steps

1. Create `components/shared/agent-logs-viewer.tsx` with shared implementation
2. Extract event config to `lib/agent-event-config.ts`
3. Update `agent-logs.tsx` to use new shared component with `variant="detailed"`
4. Update `multi-agent-logs.tsx` to use new shared component with `variant="compact"`
5. Delete duplicated code from both files
6. Add tests for shared component

#### Estimated Impact

- **Before:** 1,026 lines across 2 files
- **After:** ~500 lines in 1 shared component + 2 thin wrappers (~50 lines each)
- **Net Reduction:** ~400 lines

---

### 6. Date Formatting Duplication

#### Problem Statement

Date/time formatting is implemented independently in 5 different files with slight variations.

#### Affected Files

| File | Function | Behavior |
|------|----------|----------|
| `agent-logs.tsx` | `formatTime()` | Returns "HH:MM:SS" |
| `activity-panel.tsx` | `formatRelativeTime()` | Returns "2 hours ago" |
| `documents/[id]/page.tsx` | `formatRelativeTime()` | Returns "2 hours ago" |
| `mock-data.ts` | `formatTime()` | Returns "HH:MM:SS" |
| `admin/tests/page.tsx` | `formatTimestamp()` | Returns "Mar 19, 2026 2:30 PM" |

#### Current Implementations

```typescript
// agent-logs.tsx
function formatTime(timestamp: string): string {
  const date = new Date(timestamp);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// activity-panel.tsx
function formatRelativeTime(timestamp: string): string {
  const now = new Date();
  const date = new Date(timestamp);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins} min ago`;
  // ... more logic
}
```

#### Why This Is a Problem

1. **Inconsistent Behavior:** "2 hours ago" vs "02:30:45" for the same timestamp in different views
2. **Bug Duplication:** Edge case bugs must be fixed in 5 places
3. **No i18n Ready:** Hard to internationalize when logic is scattered

#### Recommended Solution

Create unified date utilities:

```typescript
// lib/date-utils.ts

/**
 * Format timestamp as relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSecs = Math.floor(diffMs / 1000);
  const diffMins = Math.floor(diffSecs / 60);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSecs < 60) return "just now";
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays < 7) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;

  return formatDate(date);
}

/**
 * Format timestamp as time only (e.g., "02:30:45")
 */
export function formatTime(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Format timestamp as date only (e.g., "Mar 19, 2026")
 */
export function formatDate(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

/**
 * Format timestamp as full datetime (e.g., "Mar 19, 2026 2:30 PM")
 */
export function formatDateTime(timestamp: string | Date): string {
  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}
```

#### Migration Steps

1. Create `lib/date-utils.ts` with all formatting functions
2. Add unit tests for edge cases (DST, timezones, invalid input)
3. Update each file to import from `date-utils`
4. Remove inline implementations
5. Verify consistent behavior across app

#### Estimated Impact

- **Before:** ~150 lines across 5 files
- **After:** ~50 lines in 1 file + imports
- **Net Reduction:** ~100 lines
- **Benefit:** Consistent date display across entire app

---

### 7. Configuration Sprawl

#### Problem Statement

Environment variables are scattered across 25+ backend files with inconsistent patterns, no type safety, and no central documentation.

#### Affected Files (Partial List)

```
server/app/main.py                    - REQUIRE_AUTH, LOG_LEVEL
server/app/streaming_routes.py        - REQUIRE_AUTH
server/app/strands_agentic_service.py - LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY
server/app/error_webhook.py           - ERROR_WEBHOOK_URL, ERROR_WEBHOOK_ENABLED
server/app/admin_service.py           - COST_INPUT_PER_1K, COST_OUTPUT_PER_1K
server/app/session_store.py           - EAGLE_SESSIONS_TABLE, SESSION_TTL_DAYS
server/app/cognito_auth.py            - COGNITO_USER_POOL_ID, COGNITO_CLIENT_ID
server/app/bedrock_service.py         - AWS_REGION, BEDROCK_MODEL_ID
server/app/template_service.py        - TEMPLATES_S3_BUCKET
server/app/health_checks.py           - Various health check configs
server/app/teams_notifier.py          - TEAMS_WEBHOOK_URL
server/app/daily_scheduler.py         - DAILY_DIGEST_ENABLED
server/app/telemetry/cloudwatch_emitter.py - CW_LOG_GROUP, CW_NAMESPACE
server/app/telemetry/langfuse_client.py - LANGFUSE_* vars
```

#### Current Pattern (Scattered)

```python
# error_webhook.py
WEBHOOK_URL = os.getenv("ERROR_WEBHOOK_URL", "")
WEBHOOK_ENABLED = os.getenv("ERROR_WEBHOOK_ENABLED", "true").lower() == "true"

# admin_service.py
COST_INPUT_PER_1K = float(os.getenv("COST_INPUT_PER_1K", "0.003"))

# session_store.py
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
SESSION_TTL_DAYS = int(os.getenv("SESSION_TTL_DAYS", "30"))
```

#### Why This Is a Problem

1. **No Single Source of Truth:** Cannot see all config in one place
2. **Type Casting Everywhere:** Manual `int()`, `float()`, `.lower() == "true"` repeated
3. **Inconsistent Naming:** Some use `EAGLE_` prefix, others don't
4. **No Validation:** Invalid config values cause runtime errors
5. **Hard to Audit:** Security review must check 25+ files

#### Recommended Solution

Create centralized configuration with validation:

```python
# server/app/config.py
"""
Centralized configuration for EAGLE backend.
All environment variables should be accessed through this module.
"""
import os
from dataclasses import dataclass
from typing import Optional


def _bool(value: str) -> bool:
    """Parse boolean from environment variable."""
    return value.lower() in ("true", "1", "yes")


def _int(value: str, default: int) -> int:
    """Parse integer from environment variable."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _float(value: str, default: float) -> float:
    """Parse float from environment variable."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


@dataclass(frozen=True)
class AWSConfig:
    """AWS-related configuration."""
    region: str = os.getenv("AWS_REGION", "us-east-1")
    sessions_table: str = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
    s3_bucket: str = os.getenv("EAGLE_S3_BUCKET", "eagle-documents")
    templates_bucket: str = os.getenv("TEMPLATES_S3_BUCKET", "eagle-templates")


@dataclass(frozen=True)
class AuthConfig:
    """Authentication configuration."""
    require_auth: bool = _bool(os.getenv("REQUIRE_AUTH", "false"))
    cognito_user_pool_id: Optional[str] = os.getenv("COGNITO_USER_POOL_ID")
    cognito_client_id: Optional[str] = os.getenv("COGNITO_CLIENT_ID")
    cognito_region: str = os.getenv("COGNITO_REGION", "us-east-1")


@dataclass(frozen=True)
class CostConfig:
    """Cost calculation configuration."""
    input_per_1k: float = _float(os.getenv("COST_INPUT_PER_1K", "0.003"), 0.003)
    output_per_1k: float = _float(os.getenv("COST_OUTPUT_PER_1K", "0.015"), 0.015)


@dataclass(frozen=True)
class TelemetryConfig:
    """Observability configuration."""
    langfuse_public_key: Optional[str] = os.getenv("LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: Optional[str] = os.getenv("LANGFUSE_SECRET_KEY")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    cloudwatch_log_group: str = os.getenv("CW_LOG_GROUP", "/eagle/agentic")
    cloudwatch_namespace: str = os.getenv("CW_NAMESPACE", "EAGLE")


@dataclass(frozen=True)
class WebhookConfig:
    """Webhook notification configuration."""
    error_webhook_url: str = os.getenv("ERROR_WEBHOOK_URL", "")
    error_webhook_enabled: bool = _bool(os.getenv("ERROR_WEBHOOK_ENABLED", "true"))
    teams_webhook_url: str = os.getenv("TEAMS_WEBHOOK_URL", "")


@dataclass(frozen=True)
class SessionConfig:
    """Session management configuration."""
    ttl_days: int = _int(os.getenv("SESSION_TTL_DAYS", "30"), 30)
    max_messages: int = _int(os.getenv("MAX_SESSION_MESSAGES", "100"), 100)


# Singleton instances
aws = AWSConfig()
auth = AuthConfig()
cost = CostConfig()
telemetry = TelemetryConfig()
webhooks = WebhookConfig()
session = SessionConfig()


def validate() -> list[str]:
    """
    Validate configuration and return list of warnings.
    Call at startup to catch issues early.
    """
    warnings = []

    if auth.require_auth and not auth.cognito_user_pool_id:
        warnings.append("REQUIRE_AUTH=true but COGNITO_USER_POOL_ID not set")

    if telemetry.langfuse_public_key and not telemetry.langfuse_secret_key:
        warnings.append("LANGFUSE_PUBLIC_KEY set but LANGFUSE_SECRET_KEY missing")

    return warnings
```

#### Usage After Migration

```python
# Before:
TABLE_NAME = os.getenv("EAGLE_SESSIONS_TABLE", "eagle")
TTL = int(os.getenv("SESSION_TTL_DAYS", "30"))

# After:
from app.config import aws, session

table = aws.sessions_table
ttl = session.ttl_days
```

#### Migration Steps

1. Create `server/app/config.py` with all config dataclasses
2. Add validation function for startup checks
3. Update each file to import from config module
4. Remove inline `os.getenv()` calls
5. Add startup validation in `main.py`
6. Document all config in README

#### Estimated Impact

- **Before:** 25+ files with scattered config
- **After:** 1 central config module + imports
- **Benefit:** Type safety, validation, single source of truth

---

### 8. Dead Code - mcp_agent_integration.py

#### Problem Statement

`mcp_agent_integration.py` is a 282-line file that is never imported anywhere in the codebase. It references non-existent classes.

#### File Location

`server/app/mcp_agent_integration.py` (282 lines)

#### Evidence of Dead Code

```bash
# Search for imports of this module:
$ grep -r "mcp_agent_integration" server/
# No results

# Search for the class name:
$ grep -r "MCPAgentCoreIntegration" server/
server/app/mcp_agent_integration.py:class MCPAgentCoreIntegration:
# Only defined, never used

# References non-existent classes:
from .agentic_service import AgenticService  # AgenticService doesn't exist
from .runtime_context import RuntimeContextManager  # Partially implemented
```

#### Why This Is a Problem

1. **Maintenance Liability:** Changes to dependencies might break this file silently
2. **Confusion:** New developers might try to use or extend it
3. **Technical Debt:** 282 lines of code serving no purpose
4. **False Security:** If tests pass, this code is not being tested

#### Recommended Action

**Option A: Delete** (Recommended if feature is abandoned)
```bash
git rm server/app/mcp_agent_integration.py
```

**Option B: Resurrect** (If feature is still planned)
1. Fix broken imports
2. Add to actual code path
3. Add tests

#### Migration Steps

1. Verify no dynamic imports: `grep -r "importlib.*mcp_agent" server/`
2. Check git history for context on why it was created
3. If abandoned, delete with commit message explaining removal
4. If needed, create issue to track resurrection

#### Estimated Impact

- **Lines Removed:** 282
- **Risk:** Zero (verified not imported)

---

## Structural Issues (From Architecture Audit)

These issues are more architectural in nature and were identified in the companion audit (`20260319-codebase-refactor-audit.md`).

### 9. Frontend Persistence Fragmentation

#### Problem Statement

The frontend has multiple competing client persistence abstractions with no unified strategy.

#### Affected Files

| File | Purpose | Storage |
|------|---------|---------|
| `client/contexts/session-context.tsx` | Session state | Uses `use-local-cache.ts` |
| `client/hooks/use-local-cache.ts` | General caching | IndexedDB + localStorage |
| `client/lib/document-store.ts` | Document/package state | localStorage |
| `client/hooks/use-agent-session.ts` | MCP-style sessions | Separate persistence |
| `client/lib/conversation-store.ts` | Conversation state | Another localStorage layer |
| `client/lib/conversation-sync.ts` | Sync logic | Backend sync |

#### Why This Is a Problem

1. **Multiple Sources of Truth:** Session, document, and conversation state are not centered around one domain model
2. **Hard to Reason About:** Freshness, hydration, optimistic writes, and fallback behavior are unclear
3. **Maintenance Burden:** Changes to persistence strategy require updating multiple abstractions
4. **Testing Complexity:** Each storage model needs separate mocking strategies

#### Recommended Solution

1. Define a single client persistence strategy for the current product path
2. Consolidate chat session persistence and generated document persistence behind one storage facade
3. Move MCP/demo conversation persistence into an isolated feature area or archive it
4. Replace ad hoc fallback writes with explicit sync states and cache invalidation rules

```typescript
// Proposed: client/lib/unified-storage.ts

interface StorageConfig {
  primaryStore: 'indexeddb' | 'localstorage';
  syncStrategy: 'optimistic' | 'write-through';
  ttlSeconds: number;
}

class UnifiedStorage {
  // Single entry point for all client persistence
  async saveSession(sessionId: string, data: SessionData): Promise<void>;
  async loadSession(sessionId: string): Promise<SessionData | null>;
  async saveDocuments(sessionId: string, docs: Document[]): Promise<void>;
  async loadDocuments(sessionId: string): Promise<Document[]>;

  // Sync coordination
  async syncWithBackend(sessionId: string): Promise<SyncResult>;
  onConflict(handler: ConflictHandler): void;
}
```

---

### 10. Template Duplication Across Trees

#### Problem Statement

Template files are duplicated between the frontend and plugin directories with identical filenames.

#### Affected Directories

```
client/public/templates/           ← Frontend copy
eagle-plugin/data/templates/       ← Plugin copy
```

#### Evidence

The template filenames match one-for-one. Both directories contain the same document templates (SOW, IGCE, AP, etc.).

#### Why This Is a Problem

1. **Silent Divergence:** Content updates can silently diverge between copies
2. **No Single Source of Truth:** Unclear which is authoritative
3. **Copy-Based Reuse:** Repo encourages duplication instead of generation
4. **Backend Confusion:** Template semantics exist in `template_registry.py`, `template_service.py`, and `template_store.py`

#### Recommended Solution

1. Pick ONE canonical template source directory (recommend `eagle-plugin/data/templates/`)
2. Generate or sync frontend copies during build/release
3. Add a manifest describing template type, display label, version, and consumer targets

```yaml
# eagle-plugin/data/templates/manifest.yaml
templates:
  - id: sow-standard
    file: sow-standard.md
    display_name: Statement of Work (Standard)
    version: 1.2.0
    consumers:
      - frontend
      - backend
  - id: igce-simplified
    file: igce-simplified.xlsx
    display_name: IGCE (Simplified)
    version: 1.0.0
    consumers:
      - backend
```

```bash
# Build script
npm run sync-templates  # Copies from eagle-plugin to client/public
```

---

### 11. Diagram Source Duplication

#### Problem Statement

Mermaid diagram source files exist in multiple locations with different rendered outputs.

#### Affected Directories

```
docs/architecture/diagrams/mermaid/
docs/architecture/diagrams/mermaid-diagrams/mermaid/
eagle-plugin/diagrams/mermaid/
```

Several files exist in all locations with the same names. The PNG renderings already differ in some matching files, indicating drift.

#### Why This Is a Problem

1. **Untrustworthy Documentation:** Design documentation becomes unreliable
2. **Drift Already Happening:** Rendered outputs differ between copies
3. **No Canonical Source:** Unclear which to update

#### Recommended Solution

1. Keep ONE canonical source directory: `docs/architecture/diagrams/mermaid/`
2. Treat PNG files as generated artifacts (don't commit, or regenerate on CI)
3. Replace duplicates with symlinks or documented export steps
4. Add diagram generation to CI/CD

```bash
# .github/workflows/diagrams.yml
- name: Generate diagrams
  run: |
    npx @mermaid-js/mermaid-cli -i docs/architecture/diagrams/mermaid/*.mmd \
                                  -o docs/architecture/diagrams/png/
```

---

### 12. Workspace Store Naming Confusion

#### Problem Statement

Two workspace-related stores exist with unclear naming and relationship.

#### Affected Files

```
server/app/workspace_store.py   ← Workspace entity lifecycle
server/app/wspc_store.py        ← Workspace... something?
```

Both are actively imported in `main.py` and `strands_agentic_service.py`.

#### Why This Is a Problem

1. **Opaque Naming:** `wspc_store.py` is cryptic
2. **Unclear Responsibility:** Relationship between the two is not obvious
3. **High-Friction Debt:** Central admin/customization area should be clear

#### Recommended Solution

1. Rename `wspc_store.py` to `workspace_override_store.py` or `workspace_config_store.py`
2. Group related workspace modules into a subpackage
3. Add typed interfaces for "workspace", "override", and "resolved prompt source"

```
server/app/workspaces/
├── __init__.py
├── workspace_store.py          # Core workspace CRUD
├── workspace_override_store.py # Tenant customizations (renamed from wspc_store)
├── workspace_resolver.py       # Resolves effective workspace config
└── models.py                   # Workspace, Override, ResolvedConfig types
```

---

### 13. Repository Hygiene Issues

#### Problem Statement

Generated artifacts are tracked in git, and build outputs clutter the tree.

#### Evidence

- Tracked: `client/playwright-report/index.html`
- Tracked: `client/test-results/.last-run.json`
- Present in tree: `.next/`, `node_modules/`, `.venv/`, `.pytest_cache/`, `__pycache__/`

#### Why This Is a Problem

1. **Noise in Code Review:** Generated files create churn and merge conflicts
2. **Signal Reduction:** Hard to separate source from output
3. **Onboarding Friction:** New contributors confused about what matters

#### Recommended Solution

1. Remove tracked test artifacts:
   ```bash
   git rm -r --cached client/playwright-report/
   git rm -r --cached client/test-results/
   ```

2. Update `.gitignore`:
   ```gitignore
   # Test artifacts
   client/playwright-report/
   client/test-results/

   # Build outputs
   .next/
   node_modules/
   .venv/
   __pycache__/
   .pytest_cache/
   ```

3. Add cleanup check in CI or pre-commit hook

---

### 14. Infrastructure Options Overlap

#### Problem Statement

Multiple infrastructure-as-code approaches exist without clear status markers.

#### Affected Directories

| Directory | Status | Notes |
|-----------|--------|-------|
| `infrastructure/cdk-eagle/` | Active | Primary CDK path |
| `infrastructure/cdk/` | Deprecated | Still present |
| `infrastructure/cloud_formation/` | Reference | Documented for stack creation |
| `infrastructure/terraform/` | ? | Also exists |

#### Why This Is a Problem

1. **Looks Like Four Parallel Approaches:** Not clear which to use
2. **Maintenance Confusion:** Changes might be made to wrong stack
3. **Onboarding Friction:** New developers don't know where to look

#### Recommended Solution

1. Mark each path with explicit status: `active`, `reference-only`, `experimental`, `archived`
2. Move reference-only systems under `infrastructure/archive/` or `infrastructure/reference/`
3. Update README and docs to match actual support policy

```
infrastructure/
├── cdk-eagle/              # ACTIVE - Primary infrastructure
├── reference/
│   ├── cdk-deprecated/     # ARCHIVED - Old CDK approach
│   ├── cloudformation/     # REFERENCE - Manual stack creation
│   └── terraform/          # EXPERIMENTAL - Not production ready
└── README.md               # Documents status of each
```

---

### 15. Justfile Platform Mixing

#### Problem Statement

The `Justfile` mixes Linux/Docker commands with Windows-specific commands, making it unpredictable across environments.

#### Evidence

```just
# Some recipes use standard Docker/Linux flows
deploy:
    docker compose up -d

# Others use Windows-specific commands
kill-port:
    taskkill /F /PID $(netstat -ano | findstr :8000)
```

#### Why This Is a Problem

1. **Unpredictable Behavior:** Recipes fail silently on wrong OS
2. **No Portability Boundaries:** Unclear which commands work where
3. **Long Shell Programs:** Complex logic embedded in Justfile

#### Recommended Solution

1. Split recipes into portable core tasks and OS-specific wrappers
2. Move complex logic to `scripts/` directory
3. Group commands by concern: local dev, validation, deploy, infrastructure

```just
# Justfile - portable commands only
dev:
    @just _dev-{{os()}}

_dev-linux:
    docker compose up -d

_dev-windows:
    powershell scripts/dev-windows.ps1

# Or use scripts for complex logic
validate:
    ./scripts/validate.sh
```

---

## Medium Severity Issues

### Summary Table

| Issue | File | Lines | Problem | Effort |
|-------|------|-------|---------|--------|
| `main.py` monolith | `server/app/main.py` | 3,383 | 40+ endpoints mixed together | High |
| Tool dispatch coupling | strands → agentic_service | ~50 | Imports private `_exec_*` functions | Medium |
| Parallel chat interfaces | 2 files | 1,489 | Duplicate with unclear primary | Medium |
| `useAgentStream` hook | `use-agent-stream.ts` | 629 | Mixes SSE, tool exec, logging | Medium |
| `ActivityPanel` | `activity-panel.tsx` | 555 | 5 tabs in one component | Low |
| Cost calculation | 3 services | ~150 | Pricing logic duplicated | Low |
| Frontend API helpers | 2 files | ~330 | Different fetch patterns | Low |

### Recommended Approach

These issues should be addressed after high-severity items, as they impact maintainability but don't block development.

---

## Low Severity Issues

| Issue | Location | Problem |
|-------|----------|---------|
| Helper duplication | Store files | `_now_iso()`, `_item_to_dict()` in 10+ files |
| Deprecated function | `agentic_service.py:3599` | `stream_chat()` marked DEPRECATED |
| Markdown components | 3 files | Same `mdComponents` defined 3x |
| Stream type mismatch | client ↔ server | Frontend has extra event types |
| Archived tests | `tests/_archived_*` | 2 archived tests in directory |

---

## Files That Are Large But OK

These files are legitimately large due to complexity, not poor design:

| File | Lines | Why It's Acceptable |
|------|-------|---------------------|
| `strands_agentic_service.py` | ~2,000 | Complex orchestration; single responsibility |
| `use-local-cache.ts` | 598 | IndexedDB + fallback + TTL; self-contained |
| `document-browser.tsx` | 471 | Rich UI with many states; cohesive |
| `eagle_skill_constants.py` | ~100 | Plugin discovery; focused purpose |
| `admin-api.ts` | 204 | API client; well-organized |

**Do not refactor these** - they are complex because the domain is complex.

---

## Implementation Roadmap

### Phase 0: Stabilize Repository Shape (1 day)

| Task | Impact | Effort |
|------|--------|--------|
| Remove tracked test artifacts from git | Reduce noise | 30 min |
| Update `.gitignore` | Prevent future commits | 15 min |
| Rename `wspc_store.py` → `workspace_override_store.py` | Clarity | 30 min |
| Add deprecation comments to `agentic_service.py` | Prevent new work | 15 min |
| Document canonical chat UI and infrastructure path | Alignment | 1 hour |
| Mark infrastructure directories with status | Clarity | 30 min |

### Phase 1: Quick Wins (1-2 days)

| Task | Impact | Effort | Files |
|------|--------|--------|-------|
| Create `lib/date-utils.ts` | 5 files fixed | 2 hours | 1 new, 5 updated |
| Delete `mcp_agent_integration.py` | Cleanup | 15 min | 1 deleted |
| Delete archived test files | Cleanup | 15 min | 2 deleted |
| Choose canonical template source | Prevent drift | 1 hour | Update docs |
| Choose canonical diagram source | Prevent drift | 1 hour | Update docs |

### Phase 2: Foundation (3-5 days)

| Task | Impact | Effort | Files |
|------|--------|--------|-------|
| Create `db_client.py` | 16 files fixed | 1 day | 1 new, 16 updated |
| Create `config.py` | 25 files fixed | 1 day | 1 new, 25 updated |
| Consolidate agent logs | 1000 lines saved | 1 day | 1 new, 2 updated |
| Extract FastAPI routers from `main.py` | Maintainability | 1 day | 6 new routers |
| Template sync script | Single source | 2 hours | 1 script |

### Phase 3: Major Refactors (1-2 weeks)

| Task | Impact | Effort | Files |
|------|--------|--------|-------|
| Split `agentic_service.py` | Testability | 3-5 days | 5-8 new, 1 split |
| Extract tool dispatch to shared module | Decouple strands | 1 day | 1 new |
| Extract chat hooks | Testability | 2-3 days | 4 new, 1 reduced |
| Split `_exec_create_document` | Testability | 2 days | 4 new |
| Consolidate frontend persistence | Single model | 2 days | 1 new facade |

### Phase 4: Cleanup (1 week)

| Task | Impact | Effort |
|------|--------|--------|
| Remove `agentic_service.py` imports from active paths | Retire legacy | 2-3 days |
| Archive non-active infrastructure | Reduce confusion | 1 day |
| Split `Justfile` by platform/concern | Portability | 1 day |
| Update documentation to match reality | Accuracy | 1 day |

### Verification After Each Phase

```bash
# Backend
ruff check app/
python -m pytest tests/ -v

# Frontend
npx tsc --noEmit
npx playwright test

# Integration
docker compose up --build
# Run smoke tests
```

---

## Appendix: File Size Reference

### Backend Files by Size

| File | Lines | Status |
|------|-------|--------|
| `agentic_service.py` | 3,736 | REFACTOR |
| `main.py` | 3,383 | CONSIDER |
| `strands_agentic_service.py` | ~2,000 | OK |
| `session_store.py` | ~400 | DEDUPE |
| `document_store.py` | ~350 | DEDUPE |

### Frontend Files by Size

| File | Lines | Status |
|------|-------|--------|
| `simple-chat-interface.tsx` | 777 | REFACTOR |
| `chat-interface.tsx` | 712 | CONSIDER |
| `use-agent-stream.ts` | 629 | CONSIDER |
| `use-local-cache.ts` | 598 | OK |
| `agent-logs.tsx` | 578 | DEDUPE |
| `activity-panel.tsx` | 555 | CONSIDER |

---

## Target Architecture

This is the recommended direction for refactoring, aligned with the companion architecture audit:

### Backend Target Structure

```
server/app/
├── api/
│   └── routers/
│       ├── admin.py
│       ├── chat.py
│       ├── documents.py
│       ├── health.py
│       ├── templates.py
│       └── workspaces.py
├── core/
│   ├── config.py           # Centralized configuration
│   ├── db_client.py        # Shared AWS clients
│   ├── logging.py
│   └── lifecycle.py        # App startup/shutdown
├── domains/
│   ├── chat/
│   │   ├── service.py
│   │   └── models.py
│   ├── documents/
│   │   ├── generators/     # SOW, IGCE, AP generators
│   │   ├── service.py
│   │   └── store.py
│   ├── templates/
│   │   ├── registry.py
│   │   ├── service.py
│   │   └── store.py
│   ├── workspaces/
│   │   ├── store.py
│   │   ├── override_store.py
│   │   └── resolver.py
│   └── telemetry/
├── tools/
│   ├── registry.py         # TOOL_DISPATCH - single source
│   ├── handlers/
│   │   ├── document_handler.py
│   │   ├── search_handler.py
│   │   └── context_handler.py
│   └── extractors/
│       ├── money.py
│       ├── bullets.py
│       └── sow_targets.py
├── integrations/
│   ├── aws/
│   ├── mcp/
│   └── bedrock/
└── legacy/                  # Explicit deprecated code
    ├── agentic_service.py
    └── sdk_agentic_service.py
```

### Frontend Target Structure

```
client/
├── app/                     # Next.js routes
├── features/
│   ├── chat/
│   │   ├── components/
│   │   │   ├── chat-interface.tsx    # Single canonical chat
│   │   │   ├── message-list.tsx
│   │   │   └── activity-panel/
│   │   ├── hooks/
│   │   │   ├── use-session.ts
│   │   │   ├── use-streaming.ts
│   │   │   └── use-tool-tracking.ts
│   │   └── context/
│   │       └── chat-context.tsx
│   ├── documents/
│   ├── admin/
│   └── templates/
├── shared/
│   ├── ui/                  # Shadcn components
│   ├── hooks/
│   │   └── use-unified-storage.ts
│   ├── lib/
│   │   ├── date-utils.ts
│   │   ├── unified-storage.ts
│   │   └── api-client.ts
│   └── types/
└── legacy/
    └── mcp/                 # MCP conversation stack if still needed
```

### Key Principles

1. **No new feature work in deprecated modules**
2. **One source of truth for every shared asset:** templates, diagrams, config
3. **One active chat path and one active client persistence model**
4. **Router files stay thin:** business logic in domain services
5. **Compatibility layers may call into active services, not vice versa**
6. **Generated artifacts must not be committed** unless explicit product reason
7. **Docs must declare status:** current, reference, archived, or superseded

---

## Redundancy Map

| Area | Redundancy | Risk | Recommendation |
|------|-----------|------|----------------|
| Chat UI | `chat/` and `chat-simple/` | High | One canonical, extract shared, archive other |
| Agent runtime | `agentic_service.py`, `strands_agentic_service.py` | High | Extract shared tool layer, retire deprecated |
| Client persistence | `use-local-cache`, `document-store`, `conversation-store` | High | Consolidate to one active model |
| Templates | `client/public/templates` and `eagle-plugin/data/templates` | High | One source plus generated consumers |
| DynamoDB clients | 16+ store files | High | Extract to `db_client.py` |
| Diagrams | 3+ mermaid paths | Medium | One source plus generated outputs |
| Infrastructure | CDK, deprecated CDK, Terraform, CloudFormation | Medium | Explicit active/archive split |
| Workspace stores | `workspace_store` and `wspc_store` | Medium | Rename and regroup |
| Date formatting | 5 frontend files | Medium | Extract to `date-utils.ts` |
| Agent logs | 2 nearly identical components | Medium | Consolidate to shared component |

---

## Related Documentation

- **Architecture Audit:** `docs/20260319-codebase-refactor-audit.md` - Strategic analysis of structural issues
- **This Document:** Tactical refactoring guide with code examples
- **CLAUDE.md:** Project overview and development patterns
