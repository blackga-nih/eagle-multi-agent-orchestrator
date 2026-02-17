# EAGLE Home Page Redesign Plan

## Overview

Redesign the EAGLE application home page to match the Research Optimizer landing page style. The new design features a two-column layout with branding/description on the left and feature cards on the right that route to different sections of the application.

## Current State

**Current Home Page (`/`):**
- Directly loads the chat interface
- Centered layout with eagle logo and "Welcome to EAGLE"
- Four horizontal tool cards (Acquisition Intake, Document Generation, FAR/DFARS Search, Cost Estimation)
- Quick action buttons at top
- Chat input at bottom

**Screenshot Reference:** `current home page.png`

## Target State

**New Landing Page (`/`):**
- Two-column split layout (40% left / 60% right)
- Left column: Large branded "EAGLE" title with gradient, subtitle, description paragraph
- Right column: Vertical feature cards with icons, titles, and descriptions
- Routes to different application sections instead of being the chat interface

**Design Reference:** Research Optimizer at `researchoptimizer-dev.cancer.gov`

## Feature Cards

| Card | Icon | Title | Description | Route |
|------|------|-------|-------------|-------|
| 1 | 💬 | Chat | AI assistant for acquisition tasks | `/chat` |
| 2 | 📄 | Document Templates | Browse and use available templates | `/admin/templates` |
| 3 | 📦 | Acquisition Packages | View and manage acquisition packages | `/workflows` |
| 4 | ⚙️ | Admin | Dashboard, analytics, and settings | `/admin` |

## Route Changes

### Before
```
/ (home) → Chat interface directly
```

### After
```
/ (home)     → New landing page with feature cards
/chat        → Chat interface (moved from /)
/workflows   → Acquisition Packages (existing)
/admin       → Admin Dashboard (existing)
/admin/templates → Document Templates (existing)
```

## Implementation Steps

### Step 1: Create Chat Route

**File:** `client/app/chat/page.tsx`

**Action:** Create new file that renders the current chat interface

```tsx
// Copy the current home page implementation
// This becomes the dedicated chat page
'use client';

import { SimpleChatInterface } from '@/components/chat-simple';
import SimpleHeader from '@/components/chat-simple/simple-header';
import SidebarNav from '@/components/layout/sidebar-nav';
import AuthGuard from '@/components/auth/auth-guard';

export default function ChatPage() {
  return (
    <AuthGuard>
      <div className="flex flex-col h-screen overflow-hidden">
        <SimpleHeader />
        <div className="flex flex-1 overflow-hidden">
          <SidebarNav />
          <main className="flex-1 flex flex-col overflow-hidden bg-gradient-to-b from-slate-50 to-white">
            <SimpleChatInterface />
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
```

### Step 2: Redesign Home Page

**File:** `client/app/page.tsx`

**Action:** Replace with new landing page layout

```tsx
'use client';

import Link from 'next/link';
import { MessageSquare, FileText, Package, Settings } from 'lucide-react';
import SimpleHeader from '@/components/chat-simple/simple-header';
import AuthGuard from '@/components/auth/auth-guard';

const features = [
  {
    icon: MessageSquare,
    title: 'Chat',
    description: 'AI-powered assistant for acquisition tasks, FAR/DFARS search, and document guidance',
    href: '/chat',
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
  },
  {
    icon: FileText,
    title: 'Document Templates',
    description: 'Browse and use templates for SOWs, IGCEs, acquisition plans, and more',
    href: '/admin/templates',
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
  },
  {
    icon: Package,
    title: 'Acquisition Packages',
    description: 'View, manage, and track your acquisition packages and workflows',
    href: '/workflows',
    color: 'text-purple-600',
    bgColor: 'bg-purple-50',
  },
  {
    icon: Settings,
    title: 'Admin',
    description: 'Dashboard, analytics, user management, and system settings',
    href: '/admin',
    color: 'text-orange-600',
    bgColor: 'bg-orange-50',
  },
];

export default function HomePage() {
  return (
    <AuthGuard>
      <div className="flex flex-col min-h-screen">
        <SimpleHeader />
        <main className="flex-1 flex items-center justify-center p-8 bg-gradient-to-b from-slate-50 to-white">
          <div className="max-w-6xl w-full flex flex-col lg:flex-row gap-12 lg:gap-16">
            {/* Left Column - Branding */}
            <div className="lg:w-2/5 flex flex-col justify-center">
              <h1 className="text-5xl lg:text-6xl font-bold mb-2">
                <span className="bg-gradient-to-r from-[#003366] to-[#0066cc] bg-clip-text text-transparent">
                  EAGLE
                </span>
              </h1>
              <h2 className="text-xl lg:text-2xl font-semibold text-gray-700 mb-6">
                AI-Powered Acquisition Assistant
              </h2>
              <p className="text-gray-600 leading-relaxed mb-4">
                Empowering the NCI Office of Acquisitions with intelligent tools
                that streamline procurement workflows, automate document generation,
                and provide instant access to federal acquisition regulations.
              </p>
              <p className="text-gray-500 text-sm">
                Developed by NCI for acquisition professionals.
              </p>
            </div>

            {/* Right Column - Feature Cards */}
            <div className="lg:w-3/5 flex flex-col gap-4">
              {features.map((feature) => (
                <Link
                  key={feature.title}
                  href={feature.href}
                  className="flex items-start gap-4 p-5 bg-white rounded-xl border border-gray-200
                           hover:border-gray-300 hover:shadow-md transition-all group"
                >
                  <div className={`p-3 rounded-lg ${feature.bgColor}`}>
                    <feature.icon className={`w-6 h-6 ${feature.color}`} />
                  </div>
                  <div className="flex-1">
                    <h3 className={`font-semibold text-lg ${feature.color} group-hover:underline`}>
                      {feature.title}
                    </h3>
                    <p className="text-gray-600 text-sm mt-1">
                      {feature.description}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        </main>

        {/* Footer */}
        <footer className="text-center py-4 text-xs text-gray-400 border-t border-gray-100">
          EAGLE · National Cancer Institute · Powered by Claude (Anthropic SDK)
        </footer>
      </div>
    </AuthGuard>
  );
}
```

### Step 3: Update Sidebar Navigation

**File:** `client/components/layout/sidebar-nav.tsx`

**Action:** Update "New Chat" button to route to `/chat` instead of `/`

```tsx
// Change this line:
onClick={() => { createNewSession(); router.push('/'); }}

// To:
onClick={() => { createNewSession(); router.push('/chat'); }}
```

Also update session click handlers:
```tsx
// Change:
onClick={() => { setCurrentSession(session.id); router.push('/'); }}

// To:
onClick={() => { setCurrentSession(session.id); router.push('/chat'); }}
```

### Step 4: Update Top Navigation Chat Route

**File:** `client/components/layout/top-nav.tsx`

**Action:** Update the "Chat" link to route to `/chat` so TopNav behavior matches the new route architecture.

```tsx
// Change nav link:
{ href: '/', label: 'Chat', icon: <MessageSquare className="w-4 h-4" /> },

// To:
{ href: '/chat', label: 'Chat', icon: <MessageSquare className="w-4 h-4" /> },
```

Also update active-state logic to account for the new route:

```tsx
const isActive = (href: string) => {
  if (href === '/chat') return pathname === '/chat';
  return pathname.startsWith(href);
};
```

### Step 5: Add Home Link to Sidebar (Optional)

**File:** `client/components/layout/sidebar-nav.tsx`

**Action:** Add a "Home" link at the top of the sidebar

```tsx
import { Home } from 'lucide-react';

const homeNavItem: NavItem = {
  href: '/',
  label: 'Home',
  icon: <Home className="w-5 h-5" />,
};

// Render above the "New Chat" button:
<NavLink item={homeNavItem} />
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `client/app/chat/page.tsx` | CREATE | New chat page (copy of current home) |
| `client/app/page.tsx` | MODIFY | New landing page with two-column layout |
| `client/components/layout/sidebar-nav.tsx` | MODIFY | Update routes to `/chat` |
| `client/components/layout/top-nav.tsx` | MODIFY | Update Chat nav route to `/chat` |
| `client/app/globals.css` | MODIFY | Add gradient text styles (if needed) |

## Design Specifications

### Colors
- Primary Blue: `#003366` (NCI official)
- Gradient: `from-[#003366] to-[#0066cc]`
- Feature card colors:
  - Chat: Blue (`blue-600`)
  - Templates: Emerald (`emerald-600`)
  - Packages: Purple (`purple-600`)
  - Admin: Orange (`orange-600`)

### Typography
- Title: 5xl-6xl, bold, gradient
- Subtitle: xl-2xl, semibold, gray-700
- Description: base, gray-600
- Card titles: lg, semibold, colored
- Card descriptions: sm, gray-600

### Layout
- Max width: 6xl (1152px)
- Left column: 40% on large screens
- Right column: 60% on large screens
- Responsive: Stack vertically on mobile
- Card spacing: gap-4

## Testing Checklist

- [ ] Landing page renders correctly at `/`
- [ ] Chat interface works at `/chat`
- [ ] All feature card links work correctly
- [ ] "New Chat" button routes to `/chat`
- [ ] Session selection routes to `/chat`
- [ ] TopNav "Chat" link routes to `/chat` on all pages using `TopNav`
- [ ] TopNav active state highlights Chat only on `/chat`
- [ ] Responsive layout works on mobile
- [ ] Gradient text renders correctly
- [ ] Authentication still works

## Rollback Plan

If issues arise, revert changes by:
1. Delete `client/app/chat/page.tsx`
2. Restore `client/app/page.tsx` from git
3. Restore `client/components/layout/sidebar-nav.tsx` from git
4. Restore `client/components/layout/top-nav.tsx` from git

```bash
git checkout HEAD -- client/app/page.tsx client/components/layout/sidebar-nav.tsx client/components/layout/top-nav.tsx
rm -rf client/app/chat
```

## Timeline

Estimated implementation time: 1-2 hours

1. Create chat route: 15 minutes
2. Redesign home page: 45 minutes
3. Update sidebar navigation: 15 minutes
4. Update top navigation: 10 minutes
5. Testing and refinements: 30 minutes
