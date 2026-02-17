/**
 * Template Hydration Utilities
 *
 * When the backend doesn't return filled document content (connection issues,
 * SSE missed, S3 down), the frontend falls back to raw template files with
 * {{PLACEHOLDER}} variables. These utilities hydrate templates using session
 * context so documents are always context-aware.
 */

import { AcquisitionData } from '@/components/chat/chat-interface';

export interface HydrationContext {
    requirement?: string;
    estimatedValue?: string;
    timeline?: string;
    urgency?: string;
    funding?: string;
    equipmentType?: string;
    acquisitionType?: string;
    preparer?: string;
    backgroundContext?: string;
}

export interface HydrationResult {
    content: string;
    unfilledCount: number;
}

interface MessageLike {
    role: 'user' | 'assistant';
    content: string;
}

/** Check whether content contains any {{PLACEHOLDER}} patterns. */
export function hasPlaceholders(content: string): boolean {
    return /\{\{\s*\w+\s*\}\}/.test(content);
}

/** Convert SNAKE_CASE to Title Case (e.g. BACKGROUND_CONTEXT -> Background Context). */
export function snakeCaseToTitleCase(s: string): string {
    return s
        .split('_')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
}

/** Extract background context from the first few user messages. */
export function extractBackgroundFromMessages(messages: MessageLike[]): string {
    const userMessages = messages
        .filter((m) => m.role === 'user')
        .slice(0, 3)
        .map((m) => m.content);
    return userMessages.join(' ').slice(0, 1500);
}

/** Build a HydrationContext from AcquisitionData and chat messages. */
export function buildHydrationContext(
    acquisitionData: Partial<AcquisitionData>,
    messages: MessageLike[],
    userName?: string,
): HydrationContext {
    return {
        requirement: acquisitionData.requirement,
        estimatedValue: acquisitionData.estimatedValue || acquisitionData.estimatedCost,
        timeline: acquisitionData.timeline,
        urgency: acquisitionData.urgency,
        funding: acquisitionData.funding,
        equipmentType: acquisitionData.equipmentType,
        acquisitionType: acquisitionData.acquisitionType,
        preparer: userName,
        backgroundContext: extractBackgroundFromMessages(messages),
    };
}

// Common variable mappings (template var -> context field)
const COMMON_VARS: Record<string, keyof HydrationContext> = {
    TITLE: 'requirement',
    DATE: 'timeline', // overridden below with today's date
    PREPARER: 'preparer',
    PREPARED_BY: 'preparer',
    REQUIREMENT_DESCRIPTION: 'requirement',
    ESTIMATED_VALUE: 'estimatedValue',
    ESTIMATED_COST: 'estimatedValue',
    TOTAL_ESTIMATED_COST: 'estimatedValue',
    BASE_PERIOD: 'timeline',
    PERIOD_OF_PERFORMANCE: 'timeline',
    URGENCY_LEVEL: 'urgency',
    FUNDING_SOURCES: 'funding',
    FUNDING_SOURCE: 'funding',
    BACKGROUND_CONTEXT: 'backgroundContext',
    BACKGROUND: 'backgroundContext',
    EQUIPMENT_TYPE: 'equipmentType',
    ACQUISITION_TYPE: 'acquisitionType',
    ACQUISITION_METHOD: 'acquisitionType',
};

// Per-document-type overrides that map to specific context fields
const DOC_TYPE_OVERRIDES: Record<string, Record<string, keyof HydrationContext>> = {
    sow: {
        PURPOSE_STATEMENT: 'requirement',
        PURPOSE: 'requirement',
        SCOPE_DESCRIPTION: 'requirement',
        SCOPE: 'requirement',
    },
    market_research: {
        REQUIREMENT_OVERVIEW: 'requirement',
        MARKET_OVERVIEW: 'backgroundContext',
    },
    acquisition_plan: {
        STATEMENT_OF_NEED: 'requirement',
        PLAN_SUMMARY: 'requirement',
    },
    justification: {
        DESCRIPTION_OF_SUPPLIES_SERVICES: 'requirement',
        JUSTIFICATION_DESCRIPTION: 'requirement',
    },
    igce: {
        COST_SUMMARY: 'estimatedValue',
        LABOR_CATEGORY: 'equipmentType',
    },
};

/**
 * Hydrate a template by replacing {{PLACEHOLDER}} variables with values
 * from the hydration context. Remaining unmatched placeholders are converted
 * to human-readable "[Title Case - To Be Filled]" markers.
 */
export function hydrateTemplate(
    template: string,
    documentType: string,
    context: HydrationContext,
): HydrationResult {
    const typeOverrides = DOC_TYPE_OVERRIDES[documentType] || {};
    const today = new Date().toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });

    let unfilledCount = 0;

    const content = template.replace(/\{\{\s*(\w+)\s*\}\}/g, (_match, varName: string) => {
        // Special case: DATE always gets today's date
        if (varName === 'DATE' || varName === 'CURRENT_DATE') {
            return today;
        }

        // Check doc-type-specific overrides first, then common mappings
        const contextKey = typeOverrides[varName] || COMMON_VARS[varName];
        if (contextKey) {
            const value = context[contextKey];
            if (value && value.trim()) {
                return value;
            }
        }

        // No value found — convert to readable marker
        unfilledCount++;
        return `[${snakeCaseToTitleCase(varName)} - To Be Filled]`;
    });

    return { content, unfilledCount };
}
