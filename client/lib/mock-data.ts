/**
 * Mock Data for EAGLE Intake MVP
 *
 * Sample data matching the backend schema for UI development and testing.
 */

import {
  User,
  Workflow,
  Document,
  RequirementSubmission,
  WorkflowStatus,
  AcquisitionType,
  DocumentStatus,
  SubmissionSource,
  ReviewStatus,
} from '@/types/schema';
import {
  WorkflowChecklist,
  ConversationTurn,
  AuditLog,
} from '@/types/schema-archive';

// =============================================================================
// USERS
// =============================================================================

export const CURRENT_USER: User = {
  id: 'user-001',
  email: 'jane.smith@nih.gov',
  display_name: 'Jane Smith',
  role: 'developer', // Developer has full access to all agents
  division: 'Center for Cancer Research',
  phone: '301-555-0123',
  preferences: { theme: 'light', notifications: true },
  created_at: '2024-01-15T09:00:00Z',
  updated_at: '2026-01-28T10:00:00Z',
  archived: false,
};

export const MOCK_USERS: User[] = [
  CURRENT_USER,
  {
    id: 'user-002',
    email: 'john.doe@nih.gov',
    display_name: 'John Doe',
    role: 'co',
    division: 'Office of Acquisitions',
    phone: '301-555-0124',
    preferences: {},
    created_at: '2023-06-01T09:00:00Z',
    updated_at: '2026-01-20T14:00:00Z',
    archived: false,
  },
  {
    id: 'user-003',
    email: 'sarah.johnson@nih.gov',
    display_name: 'Sarah Johnson',
    role: 'cor',
    division: 'Division of Cancer Treatment',
    phone: '301-555-0125',
    preferences: {},
    created_at: '2024-03-10T09:00:00Z',
    updated_at: '2026-01-25T11:00:00Z',
    archived: false,
  },
  {
    id: 'user-004',
    email: 'mike.wilson@nih.gov',
    display_name: 'Mike Wilson',
    role: 'admin',
    division: 'IT Services',
    phone: '301-555-0126',
    preferences: {},
    created_at: '2023-01-15T09:00:00Z',
    updated_at: '2026-01-28T09:00:00Z',
    archived: false,
  },
  {
    id: 'user-005',
    email: 'lisa.chen@nih.gov',
    display_name: 'Lisa Chen',
    role: 'analyst',
    division: 'Data Analytics',
    phone: '301-555-0127',
    preferences: {},
    created_at: '2024-06-01T09:00:00Z',
    updated_at: '2026-01-27T16:00:00Z',
    archived: false,
  },
];

// =============================================================================
// WORKFLOWS
// =============================================================================

export const CURRENT_WORKFLOW: Workflow = {
  id: 'wf-001',
  user_id: 'user-001',
  title: '128-Slice CT Scanner Acquisition',
  description: 'New CT scanner for imaging research facility',
  status: 'in_progress',
  acquisition_type: 'negotiated',
  estimated_value: 750000,
  timeline_deadline: '2026-06-30',
  urgency_level: 'urgent',
  current_step: 'funding_verification',
  metadata: {
    equipment_type: '128-slice CT Scanner',
    condition: 'new',
    vendor_preference: 'Siemens or GE',
  },
  created_at: '2026-01-28T12:00:00Z',
  updated_at: '2026-01-28T12:15:00Z',
  archived: false,
};

export const PAST_WORKFLOWS: Workflow[] = [
  {
    id: 'wf-002',
    user_id: 'user-001',
    title: 'Flow Cytometer Upgrade',
    description: 'Upgrade existing flow cytometer with new laser modules',
    status: 'completed',
    acquisition_type: 'simplified',
    estimated_value: 125000,
    timeline_deadline: '2026-01-15',
    urgency_level: 'standard',
    current_step: 'completed',
    metadata: {},
    created_at: '2025-11-01T09:00:00Z',
    updated_at: '2026-01-12T16:00:00Z',
    completed_at: '2026-01-12T16:00:00Z',
    archived: false,
  },
  {
    id: 'wf-003',
    user_id: 'user-001',
    title: 'Server Rack Maintenance Contract',
    description: 'Annual maintenance contract for data center equipment',
    status: 'completed',
    acquisition_type: 'micro_purchase',
    estimated_value: 45000,
    timeline_deadline: '2025-12-15',
    urgency_level: 'standard',
    current_step: 'completed',
    metadata: {},
    created_at: '2025-10-15T09:00:00Z',
    updated_at: '2025-12-05T14:00:00Z',
    completed_at: '2025-12-05T14:00:00Z',
    archived: false,
  },
  {
    id: 'wf-004',
    user_id: 'user-001',
    title: 'Laboratory Centrifuge',
    description: 'High-speed centrifuge for sample processing',
    status: 'approved',
    acquisition_type: 'simplified',
    estimated_value: 85000,
    timeline_deadline: '2026-02-28',
    urgency_level: 'standard',
    current_step: 'awaiting_po',
    metadata: {},
    created_at: '2026-01-10T09:00:00Z',
    updated_at: '2026-01-25T11:00:00Z',
    archived: false,
  },
];

// =============================================================================
// WORKFLOW CHECKLISTS
// =============================================================================

export const CURRENT_CHECKLIST: WorkflowChecklist[] = [
  {
    id: 'cl-001',
    workflow_id: 'wf-001',
    step_order: 1,
    step_id: 'initial_intake',
    step_name: 'Initial Intake Form',
    description: 'Capture basic acquisition requirements',
    status: 'completed',
    completed_by: 'user-001',
    completed_at: '2026-01-28T12:05:00Z',
  },
  {
    id: 'cl-002',
    workflow_id: 'wf-001',
    step_order: 2,
    step_id: 'equipment_specs',
    step_name: 'Equipment Specifications',
    description: 'Define technical requirements',
    status: 'completed',
    completed_by: 'user-001',
    completed_at: '2026-01-28T12:10:00Z',
  },
  {
    id: 'cl-003',
    workflow_id: 'wf-001',
    step_order: 3,
    step_id: 'funding_verification',
    step_name: 'Funding Verification',
    description: 'Confirm budget availability and funding source',
    status: 'in_progress',
  },
  {
    id: 'cl-004',
    workflow_id: 'wf-001',
    step_order: 4,
    step_id: 'market_research',
    step_name: 'Market Research',
    description: 'Research vendors and pricing',
    status: 'pending',
  },
  {
    id: 'cl-005',
    workflow_id: 'wf-001',
    step_order: 5,
    step_id: 'sow_draft',
    step_name: 'Statement of Work',
    description: 'Draft SOW document',
    status: 'pending',
  },
  {
    id: 'cl-006',
    workflow_id: 'wf-001',
    step_order: 6,
    step_id: 'igce',
    step_name: 'Cost Estimate (IGCE)',
    description: 'Independent Government Cost Estimate',
    status: 'pending',
  },
  {
    id: 'cl-007',
    workflow_id: 'wf-001',
    step_order: 7,
    step_id: 'co_review',
    step_name: 'CO Review',
    description: 'Contracting Officer review and approval',
    status: 'pending',
  },
];

// =============================================================================
// DOCUMENTS
// =============================================================================

export const MOCK_DOCUMENTS: Document[] = [
  {
    id: 'doc-001',
    workflow_id: 'wf-001',
    document_type: 'sow',
    title: 'Statement of Work - CT Scanner',
    status: 'in_progress',
    version: 2,
    content: `# Statement of Work
## 128-Slice CT Scanner Acquisition

### 1. Introduction

This Statement of Work (SOW) defines the requirements for procuring a **128-slice computed tomography (CT) scanner** with advanced cardiac imaging capabilities for the National Cancer Institute's Clinical Center.

### 2. Scope of Work

The contractor shall provide:

- One (1) 128-slice CT scanner with cardiac imaging package
- Installation and site preparation services
- Comprehensive training program for medical staff
- 12-month warranty with preventive maintenance
- Remote diagnostic capabilities

### 3. Technical Requirements

| Specification | Requirement |
|---------------|-------------|
| Slice Count | Minimum 128 slices |
| Rotation Speed | ≤ 0.28 seconds |
| Detector Coverage | ≥ 80mm |
| Spatial Resolution | ≤ 0.23mm |
| Temporal Resolution | ≤ 75ms |

### 4. Deliverables

1. **Equipment Delivery** - Within 90 days of contract award
2. **Installation** - Complete within 30 days of delivery
3. **Training** - 40 hours of on-site training for up to 20 staff members
4. **Documentation** - User manuals, maintenance guides, and training materials

### 5. Period of Performance

The period of performance shall be **12 months** from date of contract award.

> **Note:** All work must comply with FDA regulations and NIH safety standards.
`,
    created_at: '2026-01-28T12:00:00Z',
    updated_at: '2026-01-29T09:30:00Z',
  },
  {
    id: 'doc-002',
    workflow_id: 'wf-001',
    document_type: 'igce',
    title: 'IGCE - CT Scanner Acquisition',
    status: 'draft',
    version: 1,
    content: `# Independent Government Cost Estimate (IGCE)

## CT Scanner Acquisition - Cost Analysis

### Summary

| Category | Estimated Cost |
|----------|----------------|
| Equipment | $750,000 |
| Installation | $45,000 |
| Training | $15,000 |
| Maintenance (Year 1) | $60,000 |
| **Total** | **$870,000** |

### Methodology

Cost estimates were developed using:

1. **Market Research** - Analysis of GSA Schedule pricing
2. **Historical Data** - Previous CT scanner acquisitions (2023-2025)
3. **Vendor Quotes** - Preliminary quotes from 3 qualified vendors

### Equipment Cost Breakdown

- Base CT Scanner Unit: $680,000
- Cardiac Imaging Package: $45,000
- Workstation & Software: $25,000

### Assumptions

- Pricing based on FY2026 market conditions
- Does not include site renovation costs (handled separately)
- Assumes competitive procurement with ≥3 bids
`,
    created_at: '2026-01-28T12:00:00Z',
    updated_at: '2026-01-28T14:00:00Z',
  },
  {
    id: 'doc-003',
    workflow_id: 'wf-001',
    document_type: 'market_research',
    title: 'Market Research Report',
    status: 'approved',
    version: 3,
    content: `# Market Research Report

## 128-Slice CT Scanner Market Analysis

### Executive Summary

This report analyzes the current market for high-end CT scanners suitable for cardiac imaging applications at NIH facilities.

### Qualified Vendors

Three vendors meet the technical requirements:

1. **Siemens Healthineers** - SOMATOM Force
2. **GE Healthcare** - Revolution CT
3. **Philips** - Spectral CT 7500

### Market Conditions

The medical imaging equipment market is characterized by:

- **Limited competition** in the high-end segment (3-4 major vendors)
- **Long lead times** (90-180 days typical)
- **Stable pricing** with 2-3% annual increases

### Pricing Analysis

\`\`\`
Siemens SOMATOM Force:  $780,000 - $920,000
GE Revolution CT:       $750,000 - $880,000
Philips Spectral CT:    $720,000 - $850,000
\`\`\`

### Recommendation

Based on this analysis, we recommend:

> Proceed with full and open competition using a best-value tradeoff approach. All three vendors are technically capable and pricing is competitive.

### References

- GSA Advantage! Contract GS-07F-0000X
- MD Buyline Equipment Pricing Database
- Previous NIH CT Scanner acquisitions (2023-2025)
`,
    created_at: '2026-01-25T10:00:00Z',
    updated_at: '2026-01-28T16:00:00Z',
  },
];

// =============================================================================
// REQUIREMENTS
// =============================================================================

export const MOCK_REQUIREMENTS: import('@/types/schema-archive').Requirement[] = [
  {
    id: 'req-001',
    document_id: 'doc-001',
    requirement_key: 'equipment_description',
    label: 'Equipment Description',
    field_type: 'textarea',
    required: true,
    display_order: 1,
  },
  {
    id: 'req-002',
    document_id: 'doc-001',
    requirement_key: 'estimated_cost',
    label: 'Estimated Cost Range',
    field_type: 'text',
    required: true,
    display_order: 2,
  },
  {
    id: 'req-003',
    document_id: 'doc-001',
    requirement_key: 'funding_source',
    label: 'Funding Source',
    field_type: 'text',
    required: true,
    display_order: 3,
  },
  {
    id: 'req-004',
    document_id: 'doc-001',
    requirement_key: 'acquisition_method',
    label: 'Acquisition Method',
    field_type: 'select',
    required: true,
    options: ['Micro-Purchase', 'Simplified Acquisition', 'Negotiated Acquisition', 'Sole Source'],
    display_order: 4,
  },
  {
    id: 'req-005',
    document_id: 'doc-001',
    requirement_key: 'delivery_timeline',
    label: 'Delivery Timeline',
    field_type: 'text',
    required: true,
    display_order: 5,
  },
  {
    id: 'req-006',
    document_id: 'doc-001',
    requirement_key: 'technical_specs',
    label: 'Technical Specifications',
    field_type: 'textarea',
    required: false,
    display_order: 6,
  },
];

// =============================================================================
// REQUIREMENT SUBMISSIONS
// =============================================================================

export const MOCK_SUBMISSIONS: RequirementSubmission[] = [
  {
    id: 'sub-001',
    requirement_id: 'req-001',
    workflow_id: 'wf-001',
    value: '128-slice CT Scanner with cardiac imaging capabilities',
    source: 'user',
    submitted_by: 'user-001',
    review_status: 'approved',
    created_at: '2026-01-28T12:05:00Z',
    updated_at: '2026-01-28T12:05:00Z',
    citations: [],
  },
  {
    id: 'sub-002',
    requirement_id: 'req-002',
    workflow_id: 'wf-001',
    value: '$750,000 - $950,000',
    source: 'ai_generated',
    confidence_score: 0.92,
    reasoning: 'Based on market analysis of similar 128-slice CT scanners from Siemens, GE, and Philips. Price range accounts for installation, training, and first-year maintenance.',
    submitted_by: 'user-001',
    reviewed_by: 'user-001',
    review_status: 'approved',
    created_at: '2026-01-28T12:08:00Z',
    updated_at: '2026-01-28T12:10:00Z',
    citations: [
      {
        id: 'cit-001',
        submission_id: 'sub-002',
        source_type: 'market_data',
        source_title: 'MD Buyline CT Scanner Pricing Report 2025',
        source_url: 'https://mdbuyline.com/reports/ct-2025',
        excerpt: 'High-end 128-slice CT scanners range from $700K-$1.2M depending on configuration',
        relevance_score: 0.95,
        created_at: '2026-01-28T12:08:00Z',
      },
    ],
  },
  {
    id: 'sub-003',
    requirement_id: 'req-003',
    workflow_id: 'wf-001',
    value: 'Grant funds - NCI Cancer Imaging Program (expires Sept 2026)',
    source: 'user',
    submitted_by: 'user-001',
    review_status: 'pending',
    created_at: '2026-01-28T12:12:00Z',
    updated_at: '2026-01-28T12:12:00Z',
    citations: [],
  },
  {
    id: 'sub-004',
    requirement_id: 'req-004',
    workflow_id: 'wf-001',
    value: 'Negotiated Acquisition (FAR Part 15)',
    source: 'ai_generated',
    confidence_score: 0.98,
    reasoning: 'Acquisition value exceeds $250,000 SAT threshold. Competitive negotiation recommended for best value determination.',
    review_status: 'approved',
    created_at: '2026-01-28T12:08:00Z',
    updated_at: '2026-01-28T12:10:00Z',
    citations: [
      {
        id: 'cit-002',
        submission_id: 'sub-004',
        source_type: 'far_clause',
        source_title: 'FAR 13.003 - Simplified Acquisition Threshold',
        excerpt: 'The simplified acquisition threshold is $250,000',
        relevance_score: 1.0,
        created_at: '2026-01-28T12:08:00Z',
      },
    ],
  },
];

// =============================================================================
// CONVERSATION TURNS
// =============================================================================

export const MOCK_CONVERSATION_TURNS: ConversationTurn[] = [
  {
    id: 'turn-001',
    conversation_id: 'conv-001',
    turn_index: 0,
    role: 'user',
    content: 'I need to acquire a new CT scanner for the imaging facility',
    timestamp: '2026-01-28T12:05:00Z',
    tool_calls: [],
  },
  {
    id: 'turn-002',
    conversation_id: 'conv-001',
    turn_index: 1,
    role: 'assistant',
    agent_id: 'oa-intake',
    agent_name: 'OA Intake Agent',
    content: 'I can help you with that acquisition. A CT scanner is a significant piece of medical equipment. Let me gather some details to determine the best acquisition pathway.',
    reasoning: 'Detected medical equipment requirement. CT scanners typically exceed SAT threshold. Need to gather specifications to determine acquisition type.',
    timestamp: '2026-01-28T12:05:05Z',
    tool_calls: [],
    input_tokens: 45,
    output_tokens: 52,
    latency_ms: 850,
  },
  {
    id: 'turn-003',
    conversation_id: 'conv-001',
    turn_index: 2,
    role: 'assistant',
    agent_id: 'knowledge-retrieval',
    agent_name: 'Knowledge Retrieval',
    content: 'Based on recent acquisitions, 128-slice CT scanners range from $700K-$1.2M. I found 3 similar acquisitions in the past 18 months.',
    reasoning: 'Querying acquisition history and market data for CT scanner pricing benchmarks.',
    timestamp: '2026-01-28T12:05:10Z',
    tool_calls: [
      { name: 'search_acquisitions', input: { query: 'CT scanner', years: 2 } },
      { name: 'market_lookup', input: { equipment: 'CT scanner 128-slice' } },
    ],
    input_tokens: 120,
    output_tokens: 85,
    latency_ms: 1200,
  },
];

// =============================================================================
// AUDIT LOGS
// =============================================================================

export const MOCK_AUDIT_LOGS: AuditLog[] = [
  {
    id: 'audit-001',
    workflow_id: 'wf-001',
    user_id: 'user-001',
    action: 'workflow.created',
    resource_type: 'workflow',
    resource_id: 'wf-001',
    new_value: { title: '128-Slice CT Scanner Acquisition', status: 'draft' },
    timestamp: '2026-01-28T12:00:00Z',
  },
  {
    id: 'audit-002',
    workflow_id: 'wf-001',
    user_id: 'user-001',
    action: 'workflow.status_changed',
    resource_type: 'workflow',
    resource_id: 'wf-001',
    old_value: { status: 'draft' },
    new_value: { status: 'in_progress' },
    timestamp: '2026-01-28T12:05:00Z',
  },
  {
    id: 'audit-003',
    workflow_id: 'wf-001',
    user_id: 'user-001',
    action: 'checklist.step_completed',
    resource_type: 'checklist',
    resource_id: 'cl-001',
    new_value: { step_id: 'initial_intake', status: 'completed' },
    timestamp: '2026-01-28T12:05:00Z',
  },
  {
    id: 'audit-004',
    workflow_id: 'wf-001',
    action: 'submission.ai_generated',
    resource_type: 'submission',
    resource_id: 'sub-002',
    new_value: { source: 'ai_generated', confidence: 0.92 },
    metadata: { agent_id: 'knowledge-retrieval', model: 'claude-3-opus' },
    timestamp: '2026-01-28T12:08:00Z',
  },
  {
    id: 'audit-005',
    workflow_id: 'wf-001',
    user_id: 'user-001',
    action: 'submission.approved',
    resource_type: 'submission',
    resource_id: 'sub-002',
    old_value: { review_status: 'pending' },
    new_value: { review_status: 'approved' },
    timestamp: '2026-01-28T12:10:00Z',
  },
  {
    id: 'audit-006',
    workflow_id: 'wf-001',
    user_id: 'user-001',
    action: 'checklist.step_completed',
    resource_type: 'checklist',
    resource_id: 'cl-002',
    new_value: { step_id: 'equipment_specs', status: 'completed' },
    timestamp: '2026-01-28T12:10:00Z',
  },
  {
    id: 'audit-007',
    workflow_id: 'wf-001',
    action: 'acquisition_type.determined',
    resource_type: 'workflow',
    resource_id: 'wf-001',
    new_value: { acquisition_type: 'negotiated', reason: 'Value exceeds $250K SAT' },
    metadata: { agent_id: 'oa-intake', auto_determined: true },
    timestamp: '2026-01-28T12:08:00Z',
  },
];

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

export function getWorkflowStatusColor(status: WorkflowStatus): string {
  const colors: Record<WorkflowStatus, string> = {
    draft: 'bg-gray-100 text-gray-700',
    in_progress: 'bg-blue-100 text-blue-700',
    pending_review: 'bg-amber-100 text-amber-700',
    approved: 'bg-emerald-100 text-emerald-700',
    rejected: 'bg-red-100 text-red-700',
    completed: 'bg-green-100 text-green-700',
    cancelled: 'bg-gray-200 text-gray-500',
  };
  return colors[status] || colors.draft;
}

export function getAcquisitionTypeLabel(type: AcquisitionType): string {
  const labels: Record<AcquisitionType, string> = {
    micro_purchase: 'Micro-Purchase (<$10K)',
    simplified: 'Simplified ($10K-$250K)',
    negotiated: 'Negotiated (>$250K)',
  };
  return labels[type] || type;
}

export function getDocumentStatusColor(status: DocumentStatus): string {
  const colors: Record<DocumentStatus, string> = {
    not_started: 'bg-gray-100 text-gray-600',
    in_progress: 'bg-blue-100 text-blue-700',
    draft: 'bg-amber-100 text-amber-700',
    final: 'bg-purple-100 text-purple-700',
    approved: 'bg-green-100 text-green-700',
  };
  return colors[status] || colors.not_started;
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export function formatTime(dateString: string): string {
  return new Date(dateString).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function getRelativeTime(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateString);
}

// =============================================================================
// DOCUMENT TEMPLATES
// =============================================================================

export const MOCK_DOCUMENT_TEMPLATES: import('@/types/schema').DocumentTemplate[] = [
  {
    id: 'tpl-001',
    document_type: 'sow',
    name: 'Standard Statement of Work',
    description: 'General purpose SOW template for equipment acquisitions',
    content_template: '# Statement of Work\n\n## 1. Purpose\n{{purpose}}\n\n## 2. Scope\n{{scope}}\n\n## 3. Requirements\n{{requirements}}\n\n## 4. Deliverables\n{{deliverables}}\n\n## 5. Period of Performance\n{{period}}',
    schema_definition: {
      purpose: { type: 'text', required: true },
      scope: { type: 'textarea', required: true },
      requirements: { type: 'textarea', required: true },
      deliverables: { type: 'textarea', required: true },
      period: { type: 'text', required: true },
    },
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-06-01T09:00:00Z',
    updated_at: '2025-12-15T14:00:00Z',
  },
  {
    id: 'tpl-002',
    document_type: 'igce',
    name: 'IGCE - Equipment Purchase',
    description: 'Independent Government Cost Estimate for equipment acquisitions',
    content_template: '# Independent Government Cost Estimate\n\n## Item Description\n{{description}}\n\n## Cost Breakdown\n{{cost_breakdown}}\n\n## Market Research Summary\n{{market_research}}\n\n## Total Estimated Cost: {{total_cost}}',
    schema_definition: {
      description: { type: 'textarea', required: true },
      cost_breakdown: { type: 'textarea', required: true },
      market_research: { type: 'textarea', required: true },
      total_cost: { type: 'text', required: true },
    },
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-07-15T09:00:00Z',
    updated_at: '2025-11-20T10:00:00Z',
  },
  {
    id: 'tpl-003',
    document_type: 'market_research',
    name: 'Market Research Report',
    description: 'Standard market research template for vendor analysis',
    content_template: '# Market Research Report\n\n## Introduction\n{{introduction}}\n\n## Methodology\n{{methodology}}\n\n## Vendor Analysis\n{{vendors}}\n\n## Pricing Comparison\n{{pricing}}\n\n## Recommendation\n{{recommendation}}',
    schema_definition: {
      introduction: { type: 'textarea', required: true },
      methodology: { type: 'textarea', required: true },
      vendors: { type: 'textarea', required: true },
      pricing: { type: 'textarea', required: true },
      recommendation: { type: 'textarea', required: true },
    },
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-08-01T09:00:00Z',
    updated_at: '2025-10-05T11:00:00Z',
  },
  {
    id: 'tpl-004',
    document_type: 'justification',
    name: 'Sole Source Justification',
    description: 'J&A template for sole source acquisitions',
    content_template: '# Justification & Approval\n\n## Nature of Action\n{{nature}}\n\n## Statutory Authority\n{{authority}}\n\n## Rationale\n{{rationale}}\n\n## Market Research\n{{market_research}}\n\n## Determination\n{{determination}}',
    schema_definition: {},
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-09-01T09:00:00Z',
    updated_at: '2025-09-15T14:00:00Z',
  },
];

// =============================================================================
// AGENT SKILLS
// =============================================================================

export const MOCK_AGENT_SKILLS: import('@/types/schema-archive').AgentSkill[] = [
  {
    id: 'skill-001',
    skill_name: 'Document Generation',
    description: 'Generates acquisition documents from templates using contextual data',
    skill_type: 'document_gen',
    config: {
      model: 'claude-3-opus',
      temperature: 0.3,
      tools_enabled: ['template_fill', 'citation_lookup'],
    },
    prompt_template: 'Generate a {{document_type}} document for the following acquisition...',
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-05-01T09:00:00Z',
    updated_at: '2026-01-15T10:00:00Z',
  },
  {
    id: 'skill-002',
    skill_name: 'Market Research',
    description: 'Searches market data and vendor databases for pricing information',
    skill_type: 'search',
    config: {
      model: 'claude-3-sonnet',
      temperature: 0.2,
      tools_enabled: ['web_search', 'vendor_lookup', 'price_database'],
    },
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-06-15T09:00:00Z',
    updated_at: '2026-01-20T14:00:00Z',
  },
  {
    id: 'skill-003',
    skill_name: 'FAR Compliance Check',
    description: 'Validates documents against Federal Acquisition Regulation requirements',
    skill_type: 'validation',
    config: {
      model: 'claude-3-opus',
      temperature: 0.1,
      tools_enabled: ['far_lookup', 'policy_search'],
    },
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-07-01T09:00:00Z',
    updated_at: '2026-01-10T11:00:00Z',
  },
  {
    id: 'skill-004',
    skill_name: 'Data Extraction',
    description: 'Extracts structured data from uploaded documents and forms',
    skill_type: 'data_extraction',
    config: {
      model: 'claude-3-haiku',
      temperature: 0.0,
      tools_enabled: ['ocr', 'pdf_parser', 'form_reader'],
    },
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-08-15T09:00:00Z',
    updated_at: '2025-12-01T09:00:00Z',
  },
  {
    id: 'skill-005',
    skill_name: 'Intake Interview',
    description: 'Conducts conversational intake to gather acquisition requirements',
    skill_type: 'data_extraction',
    config: {
      model: 'claude-3-opus',
      temperature: 0.5,
      tools_enabled: ['form_builder', 'context_memory'],
    },
    is_active: false,
    created_by: 'user-002',
    created_at: '2024-10-01T09:00:00Z',
    updated_at: '2025-11-15T16:00:00Z',
  },
];

// =============================================================================
// SYSTEM PROMPTS
// =============================================================================

export const MOCK_SYSTEM_PROMPTS: import('@/types/schema-archive').SystemPrompt[] = [
  {
    id: 'prompt-001',
    prompt_name: 'OA Intake Agent',
    agent_role: 'intake_agent',
    content: 'You are an expert acquisition specialist for the NCI Office of Acquisitions. Your role is to help users initiate and complete acquisition requests...',
    version: 3,
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-04-01T09:00:00Z',
    updated_at: '2026-01-25T10:00:00Z',
  },
  {
    id: 'prompt-002',
    prompt_name: 'Document Generator',
    agent_role: 'document_agent',
    content: 'You are a document generation specialist. Generate acquisition documents that comply with FAR requirements...',
    version: 5,
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-05-15T09:00:00Z',
    updated_at: '2026-01-20T14:00:00Z',
  },
  {
    id: 'prompt-003',
    prompt_name: 'Review Agent',
    agent_role: 'review_agent',
    content: 'You are a compliance review specialist. Review acquisition documents for accuracy, completeness, and regulatory compliance...',
    version: 2,
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-06-01T09:00:00Z',
    updated_at: '2025-12-10T11:00:00Z',
  },
  {
    id: 'prompt-004',
    prompt_name: 'Orchestrator',
    agent_role: 'orchestrator',
    content: 'You are the supervisor agent coordinating between specialized agents. Route requests to appropriate agents and synthesize responses...',
    version: 4,
    is_active: true,
    created_by: 'user-002',
    created_at: '2024-07-01T09:00:00Z',
    updated_at: '2026-01-22T09:00:00Z',
  },
];

// =============================================================================
// USER GROUPS
// =============================================================================

export const MOCK_USER_GROUPS: import('@/types/schema-archive').UserGroup[] = [
  {
    id: 'group-001',
    name: 'Contracting Officers',
    description: 'Staff authorized to sign contracts and obligate funds',
    permissions: ['approve_workflow', 'sign_documents', 'manage_vendors'],
    created_at: '2024-01-01T09:00:00Z',
  },
  {
    id: 'group-002',
    name: 'COR Team',
    description: 'Contracting Officer Representatives providing technical oversight',
    permissions: ['review_documents', 'approve_technical', 'submit_modifications'],
    created_at: '2024-01-01T09:00:00Z',
  },
  {
    id: 'group-003',
    name: 'Budget Analysts',
    description: 'Financial specialists managing acquisition budgets',
    permissions: ['verify_funding', 'approve_budget', 'generate_reports'],
    created_at: '2024-01-01T09:00:00Z',
  },
  {
    id: 'group-004',
    name: 'Administrators',
    description: 'System administrators with full access',
    permissions: ['manage_users', 'manage_templates', 'manage_skills', 'view_audit_logs', 'system_config'],
    created_at: '2024-01-01T09:00:00Z',
  },
];

// =============================================================================
// ADDITIONAL HELPER FUNCTIONS
// =============================================================================

export function getSkillTypeColor(type: import('@/types/schema').SkillType): string {
  const colors: Record<import('@/types/schema').SkillType, string> = {
    document_gen: 'bg-purple-100 text-purple-700',
    data_extraction: 'bg-blue-100 text-blue-700',
    validation: 'bg-green-100 text-green-700',
    search: 'bg-amber-100 text-amber-700',
  };
  return colors[type] || 'bg-gray-100 text-gray-700';
}

export function getUserRoleColor(role: import('@/types/schema').UserRole): string {
  const colors: Record<import('@/types/schema').UserRole, string> = {
    co: 'bg-purple-100 text-purple-700',
    cor: 'bg-green-100 text-green-700',
    developer: 'bg-indigo-100 text-indigo-700',
    admin: 'bg-red-100 text-red-700',
    analyst: 'bg-amber-100 text-amber-700',
  };
  return colors[role] || 'bg-gray-100 text-gray-700';
}

export function getUserRoleLabel(role: import('@/types/schema').UserRole): string {
  const labels: Record<import('@/types/schema').UserRole, string> = {
    co: 'Contract Officer',
    cor: 'COR',
    developer: 'Developer',
    admin: 'Administrator',
    analyst: 'Analyst',
  };
  return labels[role] || role;
}
