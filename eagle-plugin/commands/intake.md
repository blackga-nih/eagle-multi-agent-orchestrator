---
name: intake
command: /intake
description: Start a new acquisition request or continue an existing intake
usage: /intake [requirement description]
examples:
  - /intake
  - /intake I need to purchase a CT scanner
  - /intake new software license for our research team
---

# /intake Command

Start a new acquisition request or continue an existing intake workflow.

## Usage

```
/intake [optional: brief description of requirement]
```

## Behavior

### Without Arguments
Starts the guided intake process:
1. Greet user and explain the process
2. Ask for basic information (what, how much, when)
3. Continue through intake workflow

### With Description
Jumpstarts intake with the provided description:
1. Parse the requirement description
2. Extract any embedded information (cost, timeline)
3. Ask targeted follow-up questions

## Examples

### Example 1: Start Fresh
```
User: /intake

EAGLE: Hi! I'm here to help you with your acquisition request. Let's start with the basics:

1. **What do you need?** (Describe the product, service, or equipment)
2. **What's the estimated cost?** (Under $10K, $10K-$250K, Over $250K, or unsure)
3. **When do you need it?**
```

### Example 2: With Description
```
User: /intake CT scanner for our imaging lab, approximately $500K, needed by Q2

EAGLE: Got it! Let me analyze your request:

**Requirement:** CT scanner for imaging lab
**Estimated Value:** ~$500,000
**Timeline:** Q2

This puts you in the **Negotiated Acquisition** category (FAR Part 15).

A few follow-up questions:
1. Do you have a specific vendor or model in mind?
2. Is this related to an existing contract?
3. Do you have approved funding?
```

## Context Management

The intake command creates or resumes a session context:

```json
{
  "session_id": "intake-{timestamp}",
  "stage": "initial|clarifying|determination|documents|complete",
  "acquisition_context": {
    "requirement": "...",
    "estimated_value": null,
    "acquisition_type": null,
    "timeline": null
  }
}
```

## Routing

This command routes to the `oa-intake` skill with any provided context.
