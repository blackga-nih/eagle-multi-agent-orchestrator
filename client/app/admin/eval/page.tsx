'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import AuthGuard from '@/components/auth/auth-guard';
import TopNav from '@/components/layout/top-nav';

// ============================================================
// DATA: Use Cases
// ============================================================
interface Actor {
  id: string;
  name: string;
  color: string;
}

interface Phase {
  name: string;
  color: string;
  border: string;
  startStep: number;
  endStep: number;
}

interface Step {
  type: 'message' | 'self' | 'note';
  from?: string;
  to?: string;
  actor?: string;
  label?: string;
  text?: string;
  desc?: string;
  prompt?: string;
  section?: string;
  dashed?: boolean;
}

interface UseCase {
  id: string;
  title: string;
  subtitle: string;
  actors: Actor[];
  phases: Phase[];
  steps: Step[];
}

const USE_CASES: UseCase[] = [
  {
    id: "uc01-happy",
    title: "UC-01: New Acquisition (Happy Path)",
    subtitle: "Simple $85K lab equipment with complete user knowledge",
    actors: [
      { id: "user", name: "COR / Program Staff", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Phase 1: Minimal Intake", color: "#1a2636", border: "#2a4a6a", startStep: 4, endStep: 7 },
      { name: "Phase 2: Clarifying Questions", color: "#1a2a1a", border: "#2a5a2a", startStep: 8, endStep: 13 },
      { name: "Phase 3: Determination", color: "#2a2218", border: "#5a4a2a", startStep: 14, endStep: 17 },
      { name: "Phase 4: Document Generation", color: "#261a26", border: "#5a2a5a", startStep: 21, endStep: 26 }
    ],
    steps: [
      { type: "message", from: "user", to: "ui", label: '"I need to buy lab equipment"', desc: "COR initiates an acquisition request through natural language" },
      { type: "message", from: "ui", to: "sup", label: "New session created", desc: "UI creates a new session and routes to the Supervisor Agent" },
      { type: "self", actor: "sup", label: "Detect intent: acquisition request", desc: "Supervisor analyzes the message and identifies it as an acquisition request" },
      { type: "message", from: "sup", to: "intake", label: "Delegate to OA Intake", desc: "Routes to the OA Intake Skill for guided intake workflow", prompt: "intake" },
      { type: "message", from: "intake", to: "ui", label: "Ask basics (what, cost, timeline)", desc: "Intake asks only 3 fields: requirement, estimated cost, timeline", prompt: "intake", section: "Phase 1: Minimal Intake Form" },
      { type: "message", from: "ui", to: "user", label: "Display intake form", desc: "UI renders the intake questions conversationally" },
      { type: "message", from: "user", to: "ui", label: '"$85K Illumina sequencer, need by March"', desc: "User provides all three basic data points in one response" },
      { type: "message", from: "ui", to: "intake", label: "Form submission", desc: "Answers sent to Intake Skill for processing" },
      { type: "message", from: "intake", to: "ui", label: '"Product or Service? Sole source?"', desc: "Smart follow-ups based on initial answers, not a rigid form", prompt: "intake", section: "Phase 2: Clarifying Questions" },
      { type: "message", from: "user", to: "ui", label: '"Product, only Illumina makes it"', desc: "User indicates sole source - triggers J&A requirement" },
      { type: "message", from: "ui", to: "intake", label: "Answers", desc: "Forward answers to Intake Skill" },
      { type: "message", from: "intake", to: "ui", label: '"Funding available? Existing contract?"', desc: "Follow-up on funding and contract vehicle", prompt: "intake", section: "Phase 2: Clarifying Questions" },
      { type: "message", from: "user", to: "ui", label: '"Grant funding, new purchase"', desc: "Confirms funding source and that this is a new acquisition" },
      { type: "message", from: "ui", to: "intake", label: "Answers", desc: "Forward to Intake Skill" },
      { type: "self", actor: "intake", label: "Apply decision tree", desc: "Intake applies determination logic based on all collected data", prompt: "intake", section: "Phase 3: Acquisition Pathway Determination" },
      { type: "note", actor: "intake", text: "$85K \u2192 Simplified (Part 13)\nSole vendor \u2192 J&A needed\nProduct \u2192 Fixed Price", desc: "Key determination: Simplified Acquisition, needs sole source justification" },
      { type: "message", from: "intake", to: "ui", label: "Display Acquisition Summary", desc: "Shows the determined pathway and key facts" },
      { type: "message", from: "intake", to: "ui", label: "Display Document Checklist", desc: "Lists required documents: SOW, IGCE, J&A, Market Research" },
      { type: "message", from: "user", to: "ui", label: '"Help me draft the SOW"', desc: "User requests document generation" },
      { type: "message", from: "ui", to: "sup", label: "Document generation request", desc: "Routes back through Supervisor for skill routing" },
      { type: "message", from: "sup", to: "docgen", label: "Generate SOW with intake data", desc: "Supervisor delegates to Document Generator with full context", prompt: "docgen" },
      { type: "self", actor: "docgen", label: "Apply SOW template", desc: "Loads SOW template from data/templates/sow-template.md", prompt: "docgen", section: "Document 1: Statement of Work (SOW)" },
      { type: "self", actor: "docgen", label: "Fill from intake context", desc: "Populates template with data collected during intake" },
      { type: "message", from: "docgen", to: "s3", label: "Store SOW v1 (.docx)", desc: "Saves generated document to S3 document store" },
      { type: "message", from: "s3", to: "docgen", label: "Pre-signed download URL", desc: "S3 returns a secure, time-limited download link", dashed: true },
      { type: "message", from: "docgen", to: "ui", label: "SOW ready for download", desc: "Document Generator notifies UI that document is ready" },
      { type: "message", from: "ui", to: "user", label: "Display SOW + download link", desc: "User can preview and download the generated SOW" },
      { type: "note", actor: "ui", text: "Checklist: SOW \u2713", desc: "Document checklist updates to show SOW complete" },
      { type: "message", from: "user", to: "ui", label: '"Now the IGCE"', desc: "User requests next document" },
      { type: "message", from: "ui", to: "sup", label: "Next document request", desc: "Routes IGCE request through Supervisor" },
      { type: "message", from: "sup", to: "docgen", label: "Generate IGCE", desc: "Delegates to Document Generator", prompt: "docgen", section: "Document 2: Independent Government Cost Estimate (IGCE)" },
      { type: "self", actor: "docgen", label: "Apply IGCE template + cost data", desc: "Uses IGCE template and populates with cost estimates" },
      { type: "message", from: "docgen", to: "s3", label: "Store IGCE v1", desc: "Saves IGCE to S3" },
      { type: "message", from: "docgen", to: "ui", label: "IGCE ready", desc: "Notifies UI" },
      { type: "message", from: "ui", to: "user", label: "Display IGCE + download link", desc: "User can download IGCE" },
      { type: "note", actor: "ui", text: "Checklist: SOW \u2713 IGCE \u2713", desc: "Two documents complete, J&A and Market Research remain" }
    ]
  },
  {
    id: "uc01-complex",
    title: "UC-01 Complex: Skill Invocation on \"I Don't Know\"",
    subtitle: ">$250K CT scanner where user lacks information",
    actors: [
      { id: "user", name: "COR / Program Staff", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "tech", name: "Tech Review Skill", color: "#20b2aa" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" }
    ],
    phases: [
      { name: "Skill Invocation: User Needs Help", color: "#2a1a1a", border: "#5a2a2a", startStep: 8, endStep: 14 },
      { name: "Skill Invocation: Quality Check", color: "#2a2218", border: "#5a4a2a", startStep: 20, endStep: 25 }
    ],
    steps: [
      { type: "message", from: "user", to: "ui", label: '"CT scanner, not sure on price, 6 weeks"', desc: "User has incomplete information" },
      { type: "message", from: "ui", to: "agent", label: "New session", desc: "Session created" },
      { type: "message", from: "agent", to: "intake", label: "Invoke OA Intake skill", desc: "Supervisor routes to intake", prompt: "intake" },
      { type: "message", from: "intake", to: "ui", label: "Equipment clarification questions", desc: "Intake asks targeted questions about the CT scanner" },
      { type: "message", from: "user", to: "ui", label: '"New, 128-slice, grant expiring"', desc: "User provides technical details" },
      { type: "message", from: "ui", to: "intake", label: "Answers", desc: "Forward to Intake" },
      { type: "message", from: "intake", to: "agent", label: "Estimate: $400K-$1M+ \u2192 Negotiated (Part 15)", desc: "Intake estimates cost range", dashed: true },
      { type: "message", from: "intake", to: "ui", label: '"Existing contract vehicle? Grant details?"', desc: "Asks about contract vehicle" },
      { type: "message", from: "user", to: "ui", label: '"I don\'t know"', desc: "KEY MOMENT: User doesn't have the information" },
      { type: "message", from: "intake", to: "agent", label: "User lacks info (contract vehicle)", desc: "Intake signals to Supervisor that user needs help", dashed: true },
      { type: "message", from: "agent", to: "comp", label: "Invoke Compliance skill (vehicle search)", desc: "Supervisor proactively invokes Compliance to find vehicles", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Search: NIH IDIQs, GSA MAS, HHS BPAs", desc: "Compliance searches knowledge base for applicable vehicles", prompt: "compliance", section: "Contract Vehicles" },
      { type: "message", from: "comp", to: "agent", label: "Found: NITAAC CIO-SP3, GSA 66 III, NIH BPA", desc: "Returns matching contract vehicles", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Present vehicle options to user", desc: "Supervisor presents findings to user" },
      { type: "message", from: "ui", to: "user", label: '"Here are available contract vehicles..."', desc: "User sees options they didn\'t know about" },
      { type: "message", from: "user", to: "ui", label: '"Show me my checklist"', desc: "User wants to see full requirements" },
      { type: "message", from: "agent", to: "ui", label: "Full document checklist (10 items)", desc: "Shows all required documents with status" },
      { type: "note", actor: "ui", text: "SOW \u2718 | IGCE \u2718 | AP \u2718\nMarket Research \u2718 | J&A TBD", desc: "10 items needed for Negotiated acquisition" },
      { type: "message", from: "user", to: "ui", label: '"Generate the Acquisition Plan"', desc: "User requests the most complex document" },
      { type: "message", from: "ui", to: "agent", label: "Document request", desc: "Routes to Supervisor" },
      { type: "message", from: "agent", to: "docgen", label: "Invoke Doc Generator (Full AP)", desc: "Delegates AP generation", prompt: "docgen", section: "Document 3: Acquisition Plan (AP)" },
      { type: "self", actor: "docgen", label: "Apply Full AP template (FAR 7.105)", desc: "Uses the comprehensive AP template", prompt: "docgen" },
      { type: "message", from: "docgen", to: "agent", label: "AP draft ready", desc: "Draft complete, needs quality check", dashed: true },
      { type: "message", from: "agent", to: "tech", label: "Invoke Tech Review skill", desc: "Supervisor sends for technical review", prompt: "tech-review" },
      { type: "self", actor: "tech", label: "Check specs, installation, training", desc: "Reviews technical requirements completeness", prompt: "tech-review", section: "Specification Validation" },
      { type: "message", from: "tech", to: "agent", label: "Missing: site prep, HVAC, electrical", desc: "Tech Review finds gaps", dashed: true },
      { type: "message", from: "agent", to: "ui", label: '"Before finalizing, we need: site details..."', desc: "Supervisor relays findings to user" },
      { type: "message", from: "user", to: "ui", label: "Provides additional details", desc: "User fills in the technical gaps" },
      { type: "message", from: "agent", to: "docgen", label: "Update AP with new details", desc: "Sends updated info for AP revision" },
      { type: "message", from: "docgen", to: "ui", label: "AP v2 ready for download", desc: "Revised AP with complete technical details" }
    ]
  },
  {
    id: "uc01-full-chain",
    title: "UC-01 Full Chain: All 6 Skills End-to-End",
    subtitle: "$500K IT modernization — Intake → Market → Compliance → Legal → Tech → DocGen (7 documents)",
    actors: [
      { id: "user", name: "COR / Program Staff", color: "#4a90d9" },
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" },
      { id: "market", name: "Market Intelligence Skill", color: "#20b2aa" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "legal", name: "Legal Counsel Skill", color: "#e06090" },
      { id: "tech", name: "Tech Review Skill", color: "#7b68ee" },
      { id: "docgen", name: "Doc Generator Skill", color: "#ffa500" }
    ],
    phases: [
      { name: "Phase 1: Intake & Determination", color: "#1a2636", border: "#2a4a6a", startStep: 2, endStep: 5 },
      { name: "Phase 2: Market Research", color: "#1a2a1a", border: "#2a5a2a", startStep: 6, endStep: 9 },
      { name: "Phase 3: Compliance Validation", color: "#2a2218", border: "#5a4a2a", startStep: 10, endStep: 13 },
      { name: "Phase 4: Legal Risk Assessment", color: "#2a1a1a", border: "#5a2a2a", startStep: 14, endStep: 17 },
      { name: "Phase 5: Technical Review", color: "#261a26", border: "#5a2a5a", startStep: 18, endStep: 21 },
      { name: "Phase 6: Document Generation", color: "#1a2620", border: "#2a5a3a", startStep: 22, endStep: 32 }
    ],
    steps: [
      // Initial request
      { type: "message", from: "user", to: "sup", label: '"IT modernization services, ~$500K, 3-year PoP"', desc: "COR requests a complex IT acquisition: agile development and cloud migration" },
      { type: "message", from: "sup", to: "intake", label: "Invoke OA Intake skill", desc: "Supervisor delegates to Intake for guided data collection", prompt: "intake" },

      // Phase 1: Intake
      { type: "message", from: "intake", to: "sup", label: "Clarifying Q&A with user", desc: "Intake asks targeted questions about scope, timeline, and requirements", prompt: "intake", section: "Phase 1: Minimal Intake Form" },
      { type: "message", from: "user", to: "sup", label: "Answers: agile dev, cloud migration, 3yr", desc: "User provides details on methodology and scope" },
      { type: "self", actor: "intake", label: "Determine: $500K → Negotiated (Part 15)", desc: "Intake applies decision tree: value above SAT, IT services, T&M likely", prompt: "intake", section: "Phase 3: Acquisition Pathway Determination" },
      { type: "note", actor: "intake", text: "$500K IT services, 3yr\nNegotiated (Part 15)\nAgile development\nCloud migration", desc: "Key determination: Negotiated acquisition, agile approach" },

      // Phase 2: Market Research
      { type: "message", from: "sup", to: "market", label: "Invoke Market Intelligence skill", desc: "Supervisor routes to Market Intelligence for vendor analysis", prompt: "compliance" },
      { type: "self", actor: "market", label: "Search GWAC vehicles (CIO-SP3, Alliant 2)", desc: "Searches government-wide contract vehicles for IT services" },
      { type: "self", actor: "market", label: "Small business analysis + labor rate benchmarking", desc: "Analyzes 22 vendors, 14 small business, GSA rate ranges $85-$210/hr" },
      { type: "message", from: "market", to: "sup", label: "22 vendors, recommend SB set-aside, GSA rates", desc: "Market research complete: recommends small business set-aside with GSA Schedule rates", dashed: true },

      // Phase 3: Compliance
      { type: "message", from: "sup", to: "comp", label: "Invoke Compliance skill", desc: "Supervisor sends to Compliance for regulatory validation", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Contract type: T&M (agile/iterative scope)", desc: "Determines Time & Materials appropriate for agile methodology", prompt: "compliance", section: "Contract Vehicles" },
      { type: "self", actor: "comp", label: "D&F required, FITARA review, Section 508", desc: "Identifies: D&F for T&M, CIO approval for IT, 508 compliance needed" },
      { type: "message", from: "comp", to: "sup", label: "T&M with D&F, FITARA, 508 checklist needed", desc: "Compliance findings: three additional requirements identified", dashed: true },

      // Phase 4: Legal
      { type: "message", from: "sup", to: "legal", label: "Invoke Legal Counsel skill", desc: "Supervisor sends to Legal for risk assessment", prompt: "compliance" },
      { type: "self", actor: "legal", label: "SB set-aside: no protest risk", desc: "Assesses bid protest risk — low for small business set-aside" },
      { type: "self", actor: "legal", label: "T&M rationale: cite FAR 39.103, appropriations OK", desc: "Documents T&M justification and confirms 3-year funding is bona fide need" },
      { type: "message", from: "legal", to: "sup", label: "Risk: LOW overall. Document T&M rationale.", desc: "Legal assessment complete: low risk, recommend thorough T&M documentation", dashed: true },

      // Phase 5: Tech Review
      { type: "message", from: "sup", to: "tech", label: "Invoke Tech Review skill", desc: "Supervisor sends to Tech Review for SOW quality check", prompt: "tech-review" },
      { type: "self", actor: "tech", label: "SOW sections: sprints, DoD, cloud milestones", desc: "Recommends agile-specific SOW structure: sprint deliverables, definition of done, migration milestones", prompt: "tech-review", section: "Specification Validation" },
      { type: "self", actor: "tech", label: "Eval criteria: technical 40%, past perf 30%, price 30%", desc: "Recommends evaluation factor weighting for best-value tradeoff" },
      { type: "message", from: "tech", to: "sup", label: "SOW structure + eval criteria recommendation", desc: "Tech review complete: SOW outline and scoring methodology ready", dashed: true },

      // Phase 6: Document Generation
      { type: "message", from: "sup", to: "docgen", label: "Invoke Document Generator (full package)", desc: "Supervisor delegates full 7-document package generation", prompt: "docgen" },
      { type: "self", actor: "docgen", label: "Generate Acquisition Plan", desc: "Full AP per FAR 7.105 with agile methodology justification", prompt: "docgen", section: "Document 1: Statement of Work (SOW)" },
      { type: "self", actor: "docgen", label: "Generate Statement of Work", desc: "Agile SOW with sprint structure, DoD criteria, cloud migration phases" },
      { type: "self", actor: "docgen", label: "Generate IGCE (GSA rates)", desc: "Independent Government Cost Estimate using GSA Schedule labor rates" },
      { type: "self", actor: "docgen", label: "Generate Market Research Report", desc: "Documents 22 vendors analyzed, SB set-aside justification" },
      { type: "self", actor: "docgen", label: "Generate D&F (T&M justification)", desc: "Determination & Findings for Time & Materials contract type" },
      { type: "self", actor: "docgen", label: "Generate Section 508 Certification", desc: "Accessibility compliance certification for IT deliverables" },
      { type: "self", actor: "docgen", label: "Generate Evaluation Criteria", desc: "Best-value tradeoff: technical approach 40%, past performance 30%, price 30%" },
      { type: "message", from: "docgen", to: "sup", label: "Complete package (7 documents)", desc: "All 7 documents generated and stored in S3", dashed: true },

      // Final delivery
      { type: "message", from: "sup", to: "user", label: "Acquisition package complete — ready for CO review", desc: "Full package delivered: AP, SOW, IGCE, Market Research, D&F, 508 Cert, Eval Criteria" },
      { type: "note", actor: "user", text: "\u2713 Acquisition Plan\n\u2713 SOW\n\u2713 IGCE\n\u2713 Market Research\n\u2713 D&F (T&M)\n\u2713 508 Certification\n\u2713 Eval Criteria\n\u2192 Ready for CO review", desc: "7 documents complete — package ready for Contracting Officer review" }
    ]
  },
  {
    id: "uc02",
    title: "UC-02: Micro-Purchase (<$15K)",
    subtitle: "Fast path for small purchases - ~2 minutes total",
    actors: [
      { id: "user", name: "COR / Program Staff", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Streamlined Intake", color: "#1a2636", border: "#2a4a6a", startStep: 3, endStep: 5 },
      { name: "Minimal Questions", color: "#1a2a1a", border: "#2a5a2a", startStep: 8, endStep: 10 }
    ],
    steps: [
      { type: "message", from: "user", to: "ui", label: '"I have a $14K quote for lab supplies"', desc: "User already has a quote" },
      { type: "message", from: "ui", to: "agent", label: "New session", desc: "Session created" },
      { type: "message", from: "agent", to: "intake", label: "Invoke OA Intake skill", desc: "Routes to intake", prompt: "intake" },
      { type: "message", from: "intake", to: "ui", label: '"Can you share the quote details?"', desc: "Intake recognizes likely micro-purchase" },
      { type: "message", from: "user", to: "ui", label: "Uploads quote / provides details", desc: "User provides the Fisher Scientific quote" },
      { type: "message", from: "ui", to: "intake", label: "Quote: $13,800 from Fisher Scientific", desc: "Quote parsed and sent to Intake" },
      { type: "self", actor: "intake", label: "$13,800 < $15K \u2192 Micro-purchase", desc: "Automatic determination: micro-purchase threshold", prompt: "intake", section: "Phase 3: Acquisition Pathway Determination" },
      { type: "message", from: "intake", to: "agent", label: "Determination: micro-purchase", desc: "Notifies Supervisor of pathway", dashed: true },
      { type: "message", from: "agent", to: "ui", label: '"Just a few quick items:"', desc: "Only 3 questions needed" },
      { type: "note", actor: "agent", text: "1. Funding source?\n2. Delivery location?\n3. Purchase card or PO?", desc: "Minimal questions for micro-purchase" },
      { type: "message", from: "user", to: "ui", label: '"Grant funds, Building 37, purchase card"', desc: "User provides all answers" },
      { type: "message", from: "ui", to: "agent", label: "Answers", desc: "Forward to Supervisor" },
      { type: "message", from: "agent", to: "docgen", label: "Generate purchase request", desc: "Only one document needed", prompt: "docgen" },
      { type: "self", actor: "docgen", label: "Generate purchase request form", desc: "Simple form with quote details" },
      { type: "message", from: "docgen", to: "s3", label: "Store purchase request", desc: "Save to S3" },
      { type: "message", from: "s3", to: "docgen", label: "Download URL", desc: "Return download link", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Purchase request ready", desc: "Notify UI" },
      { type: "message", from: "ui", to: "user", label: '"All set! Here\'s your purchase request."', desc: "User gets document immediately" },
      { type: "note", actor: "ui", text: "\u2713 Purchase Request\n\u2713 Quote attached\n\u2192 Ready for card holder", desc: "Total interaction: ~2 minutes" }
    ]
  },
  {
    id: "uc03",
    title: "UC-03: Option Exercise Package",
    subtitle: "Prepare option year package from previous year documents",
    actors: [
      { id: "user", name: "COR / CO", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Previous Package Ingestion", color: "#1a2636", border: "#2a4a6a", startStep: 3, endStep: 7 },
      { name: "Tuning Questions", color: "#1a2a1a", border: "#2a5a2a", startStep: 8, endStep: 10 },
      { name: "Option Validation", color: "#261a26", border: "#5a2a5a", startStep: 11, endStep: 13 }
    ],
    steps: [
      { type: "message", from: "user", to: "ui", label: '"Exercise Option Year 3 on contract HHSN261..."', desc: "COR needs to exercise a contract option" },
      { type: "message", from: "ui", to: "agent", label: "New session", desc: "Session created" },
      { type: "message", from: "agent", to: "intake", label: "Invoke (option exercise mode)", desc: "Intake activated in option exercise mode", prompt: "intake" },
      { type: "message", from: "intake", to: "ui", label: '"Upload your previous option package"', desc: "Needs prior year docs as baseline" },
      { type: "message", from: "user", to: "ui", label: "Uploads previous AP, SOW, IGCE (Year 2)", desc: "User provides last year's documents" },
      { type: "message", from: "ui", to: "intake", label: "Parse uploaded documents", desc: "Documents sent for analysis" },
      { type: "self", actor: "intake", label: "Extract: scope, costs, personnel, PoP", desc: "Parse and extract key data from prior year" },
      { type: "message", from: "intake", to: "agent", label: "Previous package context loaded", desc: "Baseline data extracted", dashed: true },
      { type: "message", from: "agent", to: "ui", label: '"I\'ve reviewed Year 2. Questions:"', desc: "Agent asks targeted tuning questions" },
      { type: "note", actor: "agent", text: "1. Scope changes?\n2. Personnel changes?\n3. Cost escalation?\n4. Performance issues?", desc: "Only asks what might have changed" },
      { type: "message", from: "user", to: "ui", label: '"Same scope, new COR, 3% escalation, no issues"', desc: "User provides updates" },
      { type: "message", from: "agent", to: "comp", label: "Invoke Compliance (option validation)", desc: "Verify option is exercisable", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Verify option clause, ceiling, dates", desc: "Checks contract terms allow option exercise", prompt: "compliance" },
      { type: "message", from: "comp", to: "agent", label: "Valid: Option 3 exercisable", desc: "Compliance confirms option is valid", dashed: true },
      { type: "message", from: "agent", to: "docgen", label: "Generate option package", desc: "Generate all 5 documents", prompt: "docgen" },
      { type: "note", actor: "docgen", text: "Parallel:\n- Updated AP\n- Updated SOW\n- Updated IGCE (3%)\n- Option Exercise Letter\n- COR Nomination", desc: "Five documents generated simultaneously" },
      { type: "message", from: "docgen", to: "s3", label: "Store option package", desc: "Save all documents" },
      { type: "message", from: "s3", to: "docgen", label: "Download URLs", desc: "Return links", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Option package complete", desc: "All documents ready" },
      { type: "message", from: "ui", to: "user", label: "5 documents ready for download", desc: "Complete option exercise package" }
    ]
  },
  {
    id: "uc04",
    title: "UC-04: Contract Modification",
    subtitle: "Add funding and extend period of performance",
    actors: [
      { id: "user", name: "COR / CO", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Modification Type Collection", color: "#1a2636", border: "#2a4a6a", startStep: 4, endStep: 7 },
      { name: "Modification Details", color: "#1a2a1a", border: "#2a5a2a", startStep: 8, endStep: 13 },
      { name: "Compliance Validation", color: "#261a26", border: "#5a2a5a", startStep: 15, endStep: 17 }
    ],
    steps: [
      { type: "message", from: "user", to: "ui", label: '"Modify contract HHSN261201500003I"', desc: "User needs to modify an existing contract" },
      { type: "message", from: "ui", to: "sup", label: "New session - modification intent", desc: "Session created" },
      { type: "self", actor: "sup", label: "Detect intent: contract modification", desc: "Supervisor identifies modification request" },
      { type: "message", from: "sup", to: "intake", label: "Delegate (modification mode)", desc: "Routes to Intake in modification mode", prompt: "intake" },
      { type: "message", from: "intake", to: "ui", label: '"What type of modification?"', desc: "Asks for modification category" },
      { type: "note", actor: "intake", text: "\u25cb Add funding\n\u25cb Extend PoP\n\u25cb Change scope\n\u25cb Admin change\n\u25cb Multiple changes", desc: "Modification type options" },
      { type: "message", from: "user", to: "ui", label: '"Add funding and extend PoP by 6 months"', desc: "User selects multiple changes" },
      { type: "message", from: "ui", to: "intake", label: "Modification details", desc: "Forward to Intake" },
      { type: "message", from: "intake", to: "ui", label: '"How much additional funding?"', desc: "Collect modification specifics" },
      { type: "message", from: "user", to: "ui", label: '"$150K for FY2026"', desc: "Funding amount specified" },
      { type: "message", from: "intake", to: "ui", label: '"New end date?"', desc: "Collect PoP extension" },
      { type: "message", from: "user", to: "ui", label: '"September 30, 2027"', desc: "New end date provided" },
      { type: "message", from: "intake", to: "ui", label: '"Within existing scope?"', desc: "Critical question - determines if J&A needed" },
      { type: "message", from: "user", to: "ui", label: '"Yes, same work continuing"', desc: "Within scope = no J&A needed" },
      { type: "self", actor: "intake", label: "Determine: bilateral mod, within scope", desc: "Intake determines modification approach" },
      { type: "message", from: "sup", to: "comp", label: "Validate modification approach", desc: "Send to Compliance for validation", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Check FAR: scope, funding, bilateral", desc: "Validates all compliance requirements met", prompt: "compliance" },
      { type: "message", from: "comp", to: "sup", label: "Validated: Standard bilateral mod", desc: "No additional justifications needed", dashed: true },
      { type: "message", from: "sup", to: "docgen", label: "Generate modification package", desc: "Generate all mod documents", prompt: "docgen" },
      { type: "note", actor: "docgen", text: "Parallel:\n- SF-30 Cover Page\n- Updated IGCE\n- Funds Certification\n- Updated AP", desc: "Four documents generated in parallel" },
      { type: "message", from: "docgen", to: "s3", label: "Store modification package", desc: "Save to S3" },
      { type: "message", from: "s3", to: "docgen", label: "Download URLs", desc: "Return links", dashed: true },
      { type: "message", from: "docgen", to: "ui", label: "Package ready", desc: "All documents ready" },
      { type: "message", from: "ui", to: "user", label: "4 documents ready for download", desc: "Complete modification package" },
      { type: "note", actor: "ui", text: "Checklist: All items \u2713\nReady for CO signature", desc: "Package complete and ready for signature" }
    ]
  },
  {
    id: "uc05",
    title: "UC-05: CO Package Review",
    subtitle: "Contracting Officer reviews package and gets findings",
    actors: [
      { id: "co", name: "Contracting Officer", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "tech", name: "Tech Review Skill", color: "#20b2aa" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" }
    ],
    phases: [
      { name: "Compliance Review", color: "#1a2636", border: "#2a4a6a", startStep: 4, endStep: 7 },
      { name: "Technical Review", color: "#1a2a1a", border: "#2a5a2a", startStep: 8, endStep: 11 }
    ],
    steps: [
      { type: "message", from: "co", to: "ui", label: '"Review this acquisition package"', desc: "CO wants package reviewed before signature" },
      { type: "message", from: "ui", to: "agent", label: "New session (CO role)", desc: "Session created with CO role" },
      { type: "message", from: "co", to: "ui", label: "Uploads: AP, SOW, IGCE, Market Research", desc: "Full package uploaded for review" },
      { type: "self", actor: "agent", label: "Parse all documents, identify types", desc: "Agent identifies document types" },
      { type: "message", from: "agent", to: "comp", label: "Invoke Compliance (package review)", desc: "Send to Compliance for FAR review", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Check FAR, clauses, cross-reference", desc: "Comprehensive compliance check", prompt: "compliance", section: "Compliance Checklist" },
      { type: "message", from: "comp", to: "agent", label: "5 Findings", desc: "Missing clause, cost mismatch, set-aside, PoP mismatch, outdated research", dashed: true },
      { type: "note", actor: "comp", text: "1. Missing FAR 52.219 clause\n2. AP cost \u2260 IGCE total\n3. Set-aside not justified\n4. PoP mismatch\n5. Market research >12mo", desc: "Five compliance issues found" },
      { type: "message", from: "agent", to: "tech", label: "Invoke Tech Review (SOW)", desc: "Send SOW for technical review", prompt: "tech-review" },
      { type: "self", actor: "tech", label: "Check specificity, deliverables, criteria", desc: "Reviews technical completeness", prompt: "tech-review", section: "Specification Validation" },
      { type: "message", from: "tech", to: "agent", label: "3 Findings", desc: "Undefined deliverable, no acceptance criteria, security incomplete", dashed: true },
      { type: "note", actor: "tech", text: "1. Task 3 deliverable undefined\n2. No acceptance criteria\n3. Security requirements incomplete", desc: "Three technical issues found" },
      { type: "message", from: "agent", to: "docgen", label: "Generate findings report", desc: "Create organized report", prompt: "docgen" },
      { type: "note", actor: "docgen", text: "\ud83d\udd34 Critical (2)\n\ud83d\udfe1 Moderate (4)\n\ud83d\udfe2 Minor (2)", desc: "Findings organized by severity" },
      { type: "message", from: "agent", to: "ui", label: "Package review complete", desc: "Results ready" },
      { type: "message", from: "ui", to: "co", label: "8 findings by severity", desc: "CO sees organized findings report" },
      { type: "message", from: "co", to: "ui", label: '"Fix the cost mismatch for me"', desc: "CO requests automated remediation" },
      { type: "message", from: "agent", to: "docgen", label: "Update IGCE", desc: "Auto-fix the IGCE to match AP" },
      { type: "self", actor: "docgen", label: "Reconcile IGCE total with AP", desc: "Adjusts IGCE numbers to match AP" },
      { type: "message", from: "agent", to: "ui", label: '"IGCE updated. Now shows $487,500."', desc: "Fix applied and confirmed" },
      { type: "message", from: "ui", to: "co", label: "Updated IGCE + download link", desc: "CO gets corrected document" }
    ]
  },
  {
    id: "uc07",
    title: "UC-07: Contract Close-Out",
    subtitle: "Generate close-out checklist and documents",
    actors: [
      { id: "co", name: "Contracting Officer", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Contract Analysis", color: "#1a2636", border: "#2a4a6a", startStep: 3, endStep: 5 },
      { name: "Close-Out Requirements", color: "#261a26", border: "#5a2a5a", startStep: 6, endStep: 8 }
    ],
    steps: [
      { type: "message", from: "co", to: "ui", label: '"Close out contract HHSN261200900045C"', desc: "CO needs to close out a completed contract" },
      { type: "message", from: "ui", to: "agent", label: "New session (close-out mode)", desc: "Session created" },
      { type: "message", from: "agent", to: "ui", label: '"Upload contract and final deliverables"', desc: "Requests supporting documents" },
      { type: "message", from: "co", to: "ui", label: "Uploads: contract, final invoice, deliverable log", desc: "CO provides documentation" },
      { type: "self", actor: "agent", label: "Parse contract: FFP, all options exercised", desc: "Identifies contract type and status" },
      { type: "note", actor: "agent", text: "Close-out type: FFP\nAll options exercised\nFinal payment: check", desc: "Contract analysis summary" },
      { type: "message", from: "agent", to: "comp", label: "Invoke Compliance (close-out checklist)", desc: "Get FAR 4.804 requirements", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Generate FAR 4.804 checklist (12 items)", desc: "Identifies all required close-out actions", prompt: "compliance" },
      { type: "message", from: "comp", to: "agent", label: "Close-out action list (12 items)", desc: "Complete checklist", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Close-out checklist", desc: "Display to CO" },
      { type: "note", actor: "ui", text: "\u2713 Final invoice paid\n\u2713 Deliverables accepted\n\u26a0 Release of claims\n\u26a0 Patent report\n\u2718 Property disposition\n\u2718 COR assessment", desc: "Status of each close-out item" },
      { type: "message", from: "co", to: "ui", label: '"Draft COR assessment and claims letter"', desc: "CO requests document generation" },
      { type: "message", from: "agent", to: "docgen", label: "Generate close-out docs", desc: "Generate 3 documents in parallel", prompt: "docgen" },
      { type: "note", actor: "docgen", text: "Parallel:\n- COR Final Assessment\n- Release of Claims Letter\n- Contract Completion Statement", desc: "Three close-out documents" },
      { type: "message", from: "docgen", to: "s3", label: "Store close-out package", desc: "Save to S3" },
      { type: "message", from: "s3", to: "docgen", label: "Download URLs", desc: "Return links", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Close-out documents ready", desc: "All documents complete" },
      { type: "message", from: "ui", to: "co", label: "3 documents + send claims to contractor", desc: "CO gets documents with next step guidance" }
    ]
  },
  {
    id: "uc08",
    title: "UC-08: Government Shutdown Notification",
    subtitle: "Time-critical: classify 200+ contracts and generate emails",
    actors: [
      { id: "co", name: "Contracting Officer", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "comp", name: "Compliance Skill", color: "#daa520" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" }
    ],
    phases: [
      { name: "Classify Each Contract (URGENT)", color: "#2a1a1a", border: "#5a2a2a", startStep: 3, endStep: 7 },
      { name: "Batch Email Generation", color: "#1a2a1a", border: "#2a5a2a", startStep: 9, endStep: 14 }
    ],
    steps: [
      { type: "message", from: "co", to: "ui", label: '"Shutdown in 4 hours. Need notifications."', desc: "URGENT: Government shutdown imminent" },
      { type: "message", from: "co", to: "ui", label: "Uploads active contract spreadsheet (200+)", desc: "CO provides full contract portfolio" },
      { type: "message", from: "ui", to: "agent", label: "Contract list received", desc: "200+ contracts to process" },
      { type: "message", from: "agent", to: "comp", label: "Invoke Compliance (shutdown classification)", desc: "Classify each contract", prompt: "compliance" },
      { type: "self", actor: "comp", label: "Classify 200+ contracts by category", desc: "Applies shutdown rules to each contract" },
      { type: "note", actor: "comp", text: "Cat A: 78 Continue (FFP)\nCat B: 45 Stop at limit\nCat C: 62 Stop work\nCat D: 15 Excepted", desc: "Four categories based on contract type and funding" },
      { type: "message", from: "comp", to: "agent", label: "Classification complete", desc: "All 200 classified", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Summary: 78 | 45 | 62 | 15", desc: "Present classification summary" },
      { type: "message", from: "ui", to: "co", label: "Classification summary by category", desc: "CO reviews the breakdown" },
      { type: "message", from: "co", to: "ui", label: '"Generate all notification emails"', desc: "CO approves batch generation" },
      { type: "message", from: "agent", to: "docgen", label: "Invoke Doc Generator (batch)", desc: "Generate 200 personalized emails", prompt: "docgen" },
      { type: "self", actor: "docgen", label: "Generate 4 templates + 200 emails", desc: "Template per category, personalized per contract" },
      { type: "note", actor: "docgen", text: "Template A: Continue\nTemplate B: Stop at limit\nTemplate C: Stop work\nTemplate D: Excepted", desc: "Four email templates, 200 personalized emails" },
      { type: "message", from: "docgen", to: "agent", label: "200 emails generated", desc: "All emails ready", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "All notifications ready", desc: "Ready for CO review" },
      { type: "message", from: "ui", to: "co", label: "200 draft emails by category", desc: "CO reviews and sends" },
      { type: "note", actor: "ui", text: "Hours of manual work\n\u2192 Minutes of review", desc: "Dramatic time savings in crisis scenario" }
    ]
  },
  {
    id: "uc09",
    title: "UC-09: Score Sheet Consolidation",
    subtitle: "180 score sheets from 9 reviewers on 20 proposals",
    actors: [
      { id: "co", name: "Contracting Officer", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "agent", name: "Supervisor Agent", color: "#50c878" },
      { id: "tech", name: "Tech Review Skill", color: "#20b2aa" },
      { id: "docgen", name: "Doc Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Score Sheet Analysis", color: "#1a2636", border: "#2a4a6a", startStep: 3, endStep: 7 },
      { name: "Question Deduplication", color: "#1a2a1a", border: "#2a5a2a", startStep: 9, endStep: 13 }
    ],
    steps: [
      { type: "message", from: "co", to: "ui", label: '"180 score sheets, 9 reviewers, 20 proposals"', desc: "Massive evaluation consolidation task" },
      { type: "message", from: "co", to: "ui", label: "Uploads 180 score sheet documents", desc: "All score sheets uploaded" },
      { type: "message", from: "ui", to: "agent", label: "Documents received", desc: "Agent receives all documents" },
      { type: "message", from: "agent", to: "tech", label: "Invoke Tech Review (score analysis)", desc: "Send for score analysis", prompt: "tech-review" },
      { type: "self", actor: "tech", label: "Parse 180 sheets, extract scores", desc: "Extract scores per evaluation factor", prompt: "tech-review" },
      { type: "self", actor: "tech", label: "Cross-reviewer analysis, outlier detection", desc: "Identify score variance and consensus" },
      { type: "message", from: "tech", to: "agent", label: "20 proposals, 5 factors, 3 divergent", desc: "Analysis complete", dashed: true },
      { type: "note", actor: "tech", text: "Score variance per factor\nOutlier detection\n3 proposals flagged", desc: "Statistical analysis of reviewer agreement" },
      { type: "message", from: "agent", to: "ui", label: '"3 proposals have significant disagreements"', desc: "Flags potential issues" },
      { type: "message", from: "agent", to: "tech", label: "Invoke Tech Review (question consolidation)", desc: "Consolidate reviewer questions", prompt: "tech-review" },
      { type: "self", actor: "tech", label: "847 questions \u2192 312 unique", desc: "Deduplicate and categorize questions" },
      { type: "note", actor: "tech", text: "89 answerable from RFP\n156 need Core input\n42 need amendment\n25 administrative", desc: "Questions categorized by action needed" },
      { type: "message", from: "tech", to: "agent", label: "Consolidated question list", desc: "312 unique questions categorized", dashed: true },
      { type: "message", from: "agent", to: "docgen", label: "Generate evaluation report", desc: "Create comprehensive report package", prompt: "docgen" },
      { type: "note", actor: "docgen", text: "Parallel:\n- Consensus Score Matrix\n- Consolidated Questions\n- 20 Per-Contractor Sheets\n- Evaluation Summary", desc: "Four evaluation documents" },
      { type: "message", from: "docgen", to: "s3", label: "Store evaluation package", desc: "Save all documents" },
      { type: "message", from: "s3", to: "docgen", label: "Download URLs", desc: "Return links", dashed: true },
      { type: "message", from: "agent", to: "ui", label: "Evaluation consolidation complete", desc: "All documents ready" },
      { type: "message", from: "ui", to: "co", label: "4 documents ready", desc: "Complete evaluation package" },
      { type: "note", actor: "ui", text: "\u2713 Consensus Score Matrix\n\u2713 312 Consolidated Questions\n\u2713 20 Per-Contractor Sheets\n\u2713 Evaluation Summary Report", desc: "From 180 score sheets to 4 organized documents" }
    ]
  },
  {
    id: "skill-09-intake",
    title: "Skill-09: OA Intake — CT Scanner Acquisition",
    subtitle: "Multi-turn intake workflow with cost-threshold detection",
    actors: [
      { id: "user", name: "COR / Program Staff", color: "#4a90d9" },
      { id: "ui", name: "Eagle UI", color: "#7b68ee" },
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "intake", name: "OA Intake Skill", color: "#ff6b6b" }
    ],
    phases: [
      { name: "Phase 1: Equipment Intake", color: "#1a2636", border: "#2a4a6a", startStep: 3, endStep: 5 },
      { name: "Phase 2: Clarification & Cost Estimation", color: "#1a2a1a", border: "#2a5a2a", startStep: 6, endStep: 9 },
      { name: "Phase 3: Funding & Vehicle Determination", color: "#2a2218", border: "#5a4a2a", startStep: 10, endStep: 12 }
    ],
    steps: [
      { type: "message", from: "user", to: "ui", label: '"I need to buy a cat scan machine, not sure the price"', desc: "User provides vague requirement — no cost estimate" },
      { type: "message", from: "ui", to: "sup", label: "New session created", desc: "UI creates session and routes to Supervisor" },
      { type: "message", from: "sup", to: "intake", label: "Delegate to OA Intake", desc: "Supervisor routes to OA Intake for guided intake", prompt: "oa-intake" },
      { type: "message", from: "intake", to: "ui", label: '"What type of CT scanner? Clinical or research?"', desc: "Intake asks clarifying questions about equipment type", prompt: "oa-intake", section: "Phase 1: Equipment Intake" },
      { type: "message", from: "user", to: "ui", label: '"Research CT for small animal imaging"', desc: "User clarifies it's a preclinical micro-CT" },
      { type: "message", from: "ui", to: "intake", label: "Equipment details", desc: "Forward clarification to Intake" },
      { type: "self", actor: "intake", label: "Estimate cost: micro-CT ~$250K–$500K", desc: "Intake estimates cost based on equipment type — above SAT", prompt: "oa-intake", section: "Phase 2: Clarification & Cost Estimation" },
      { type: "note", actor: "intake", text: "$250K+ → Above SAT\nNegotiated / FAR Part 15\nFull & Open Competition likely", desc: "Cost threshold triggers formal acquisition pathway" },
      { type: "message", from: "intake", to: "ui", label: '"Estimated $250K+. Sole source or competitive?"', desc: "Intake asks about competition strategy" },
      { type: "message", from: "user", to: "ui", label: '"There are a few vendors, competitive is fine"', desc: "User confirms competitive approach" },
      { type: "message", from: "ui", to: "intake", label: "Competition preference", desc: "Forward to Intake" },
      { type: "self", actor: "intake", label: "Determine: Negotiated, Full & Open, FAR 15", desc: "Apply decision tree with cost + competition data", prompt: "oa-intake", section: "Phase 3: Funding & Vehicle Determination" },
      { type: "message", from: "intake", to: "ui", label: "Acquisition Summary + Document Checklist", desc: "Presents pathway determination and required documents" },
      { type: "note", actor: "intake", text: "Pathway: Negotiated (Part 15)\nVehicle: Full & Open\nDocs: SOW, IGCE, Eval Criteria,\nAcquisition Plan, Market Research", desc: "Complete intake determination for CT scanner" }
    ]
  },
  {
    id: "skill-10-legal",
    title: "Skill-10: Legal Counsel — Sole Source J&A Review",
    subtitle: "$985K sole-source Illumina sequencer — FAR 6.302 authority check",
    actors: [
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "legal", name: "Legal Counsel", color: "#e06090" }
    ],
    phases: [
      { name: "Phase 1: Sole Source Submission", color: "#1a2636", border: "#2a4a6a", startStep: 0, endStep: 1 },
      { name: "Phase 2: FAR / Case Law Analysis", color: "#1a2a1a", border: "#2a5a2a", startStep: 2, endStep: 4 },
      { name: "Phase 3: Recommendation", color: "#2a2218", border: "#5a4a2a", startStep: 5, endStep: 6 }
    ],
    steps: [
      { type: "message", from: "sup", to: "legal", label: "Review J&A: $985K Illumina sequencer, sole source", desc: "Supervisor delegates sole source justification review to Legal Counsel", prompt: "legal-counsel" },
      { type: "self", actor: "legal", label: "Parse J&A: vendor, amount, authority cited", desc: "Legal Counsel extracts key facts from the J&A submission", prompt: "legal-counsel" },
      { type: "self", actor: "legal", label: "Check FAR 6.302-1: Only one responsible source", desc: "Validates the cited authority against FAR requirements", prompt: "legal-counsel", section: "FAR Authority Analysis" },
      { type: "self", actor: "legal", label: "Search GAO case law for Illumina precedents", desc: "Checks protest history for similar sole-source scientific equipment", prompt: "legal-counsel" },
      { type: "note", actor: "legal", text: "FAR 6.302-1 applicable ✓\nIllumina proprietary tech ✓\nGAO: B-417xxx sustained (weak market research)\nProtest risk: MODERATE", desc: "Legal analysis summary with risk assessment" },
      { type: "message", from: "legal", to: "sup", label: "J&A supportable with conditions", desc: "Legal Counsel returns recommendation", dashed: true },
      { type: "note", actor: "legal", text: "Recommendation:\n1. Strengthen market research section\n2. Document proprietary features\n3. Add brand-name justification\nProtest risk: Moderate → Low with fixes", desc: "Actionable legal recommendations to strengthen J&A" }
    ]
  },
  {
    id: "skill-11-market",
    title: "Skill-11: Market Intelligence — IT Modernization Research",
    subtitle: "$500K IT modernization — GSA vehicles, small business, pricing",
    actors: [
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "market", name: "Market Intelligence", color: "#20b2aa" }
    ],
    phases: [
      { name: "Phase 1: Research Request", color: "#1a2636", border: "#2a4a6a", startStep: 0, endStep: 1 },
      { name: "Phase 2: Vendor & Vehicle Analysis", color: "#1a2a1a", border: "#2a5a2a", startStep: 2, endStep: 4 },
      { name: "Phase 3: Market Findings", color: "#2a2218", border: "#5a4a2a", startStep: 5, endStep: 6 }
    ],
    steps: [
      { type: "message", from: "sup", to: "market", label: "Market research: $500K IT modernization", desc: "Supervisor delegates market research for IT infrastructure upgrade", prompt: "market-intelligence" },
      { type: "self", actor: "market", label: "Search GSA IT Schedule 70 / MAS vehicles", desc: "Identifies applicable GSA contract vehicles and BPAs", prompt: "market-intelligence", section: "GSA Vehicle Search" },
      { type: "self", actor: "market", label: "Small business set-aside analysis", desc: "Checks SBA size standards, HUBZone, 8(a), SDVOSB availability", prompt: "market-intelligence" },
      { type: "self", actor: "market", label: "Labor rate benchmarking (GSA rates vs market)", desc: "Compares GSA schedule rates against commercial market data", prompt: "market-intelligence" },
      { type: "note", actor: "market", text: "GSA MAS IT Category available ✓\n12 vendors on schedule\n4 small business eligible\nLabor rates: $95-$145/hr (GS-comparable)\nSet-aside recommended: SB or SDVOSB", desc: "Market research findings summary" },
      { type: "message", from: "market", to: "sup", label: "Market research complete — SB set-aside recommended", desc: "Returns comprehensive market research report", dashed: true },
      { type: "note", actor: "market", text: "Deliverables:\n- Vendor capability matrix\n- GSA pricing comparison\n- Small business analysis\n- Recommended acquisition strategy", desc: "Market Intelligence report package" }
    ]
  },
  {
    id: "skill-12-tech",
    title: "Skill-12: Tech Translator — Agile SOW Translation",
    subtitle: "Translate agile cloud migration requirements into contract language",
    actors: [
      { id: "user", name: "Program Staff", color: "#4a90d9" },
      { id: "tech", name: "Tech Translator", color: "#7b68ee" }
    ],
    phases: [
      { name: "Phase 1: Technical Requirements", color: "#1a2636", border: "#2a4a6a", startStep: 0, endStep: 1 },
      { name: "Phase 2: Contract Translation", color: "#1a2a1a", border: "#2a5a2a", startStep: 2, endStep: 4 },
      { name: "Phase 3: Evaluation Criteria", color: "#2a2218", border: "#5a4a2a", startStep: 5, endStep: 6 }
    ],
    steps: [
      { type: "message", from: "user", to: "tech", label: '"Translate agile cloud migration SOW requirements"', desc: "Program staff provides technical requirements in agile/DevOps language", prompt: "tech-translator" },
      { type: "self", actor: "tech", label: "Parse agile terminology: sprints, stories, velocity", desc: "Identifies agile-specific terms that need contract-language equivalents", prompt: "tech-translator", section: "Term Mapping" },
      { type: "self", actor: "tech", label: "Map sprints → milestones, stories → deliverables", desc: "Translates agile concepts into FAR-compatible contract terms", prompt: "tech-translator" },
      { type: "self", actor: "tech", label: "Add FedRAMP compliance requirements", desc: "Inserts mandatory cloud security and compliance language", prompt: "tech-translator", section: "Compliance Drivers" },
      { type: "note", actor: "tech", text: "Sprint → Performance Period Milestone\nUser Story → Functional Requirement\nVelocity → Performance Metric\nCI/CD → Continuous Delivery Capability\nFedRAMP High required", desc: "Technical-to-contract term mapping" },
      { type: "message", from: "tech", to: "user", label: "Translated SOW sections + eval criteria", desc: "Returns contract-ready language with evaluation criteria", dashed: true },
      { type: "note", actor: "tech", text: "Deliverables:\n- Translated SOW sections\n- Performance metrics table\n- Evaluation criteria (Technical/Management/Past Performance)\n- FedRAMP compliance matrix", desc: "Tech Translator output package" }
    ]
  },
  {
    id: "skill-13-public",
    title: "Skill-13: Public Interest — Fairness Review",
    subtitle: "$2.1M sole-source to incumbent — fairness & transparency check",
    actors: [
      { id: "sup", name: "Supervisor Agent", color: "#50c878" },
      { id: "public", name: "Public Interest", color: "#daa520" }
    ],
    phases: [
      { name: "Phase 1: Risky Acquisition Flagged", color: "#1a2636", border: "#2a4a6a", startStep: 0, endStep: 1 },
      { name: "Phase 2: Fairness Analysis", color: "#1a2a1a", border: "#2a5a2a", startStep: 2, endStep: 4 },
      { name: "Phase 3: Risk Mitigation", color: "#2a2218", border: "#5a4a2a", startStep: 5, endStep: 6 }
    ],
    steps: [
      { type: "message", from: "sup", to: "public", label: "Review: $2.1M sole-source IT to incumbent", desc: "Supervisor flags high-risk acquisition for fairness review", prompt: "public-interest" },
      { type: "self", actor: "public", label: "Check SAM.gov posting history", desc: "Verifies whether opportunity was posted for public notice", prompt: "public-interest", section: "Transparency Check" },
      { type: "self", actor: "public", label: "Assess vendor lock-in indicators", desc: "Analyzes incumbent dependency and switching costs", prompt: "public-interest" },
      { type: "self", actor: "public", label: "Evaluate congressional interest / IG risk", desc: "Checks for political sensitivity and oversight exposure", prompt: "public-interest" },
      { type: "note", actor: "public", text: "⚠ No SAM posting found\n⚠ Incumbent 5+ years, no recompete\n⚠ Limited market research on file\n⚠ Congressional interest: district-level", desc: "Multiple fairness red flags identified" },
      { type: "message", from: "public", to: "sup", label: "HIGH RISK — 4 fairness flags identified", desc: "Public Interest returns risk assessment with mitigation plan", dashed: true },
      { type: "note", actor: "public", text: "Mitigation Plan:\n1. Post RFI on SAM.gov (30 days)\n2. Conduct market research with 3+ sources\n3. Document incumbent justification\n4. Brief congressional liaison\nRisk: HIGH → MODERATE with actions", desc: "Actionable steps to reduce fairness risk" }
    ]
  },
  {
    id: "skill-14-docgen",
    title: "Skill-14: Document Generator — Acquisition Plan",
    subtitle: "FAR Part 13 Acquisition Plan for $300K lab centrifuge",
    actors: [
      { id: "user", name: "Program Staff", color: "#4a90d9" },
      { id: "docgen", name: "Document Generator", color: "#ffa500" },
      { id: "s3", name: "S3 Store", color: "#808080" }
    ],
    phases: [
      { name: "Phase 1: AP Request", color: "#1a2636", border: "#2a4a6a", startStep: 0, endStep: 1 },
      { name: "Phase 2: Document Assembly", color: "#1a2a1a", border: "#2a5a2a", startStep: 2, endStep: 5 },
      { name: "Phase 3: Storage & Delivery", color: "#2a2218", border: "#5a4a2a", startStep: 6, endStep: 8 }
    ],
    steps: [
      { type: "message", from: "user", to: "docgen", label: '"Generate Acquisition Plan for $300K centrifuge"', desc: "Request to generate AP for lab equipment procurement", prompt: "document-generator" },
      { type: "self", actor: "docgen", label: "Load AP template (FAR Part 13 simplified)", desc: "Selects appropriate template based on dollar threshold", prompt: "document-generator", section: "Template Selection" },
      { type: "self", actor: "docgen", label: "Populate Section 1: Purpose & Authority", desc: "Fills acquisition authority, funding, and background sections", prompt: "document-generator" },
      { type: "self", actor: "docgen", label: "Populate Sections 2-5: Scope, Strategy, Schedule", desc: "Fills technical scope, acquisition strategy, milestones", prompt: "document-generator" },
      { type: "self", actor: "docgen", label: "Generate cost table + signature blocks", desc: "Adds IGCE reference table and approval signature lines", prompt: "document-generator" },
      { type: "note", actor: "docgen", text: "AP Sections:\n1. Purpose & Authority\n2. Requirements Description\n3. Acquisition Strategy\n4. Cost/Schedule\n5. Approval & Signatures\nFAR 7.105 compliant", desc: "Complete AP structure per FAR requirements" },
      { type: "message", from: "docgen", to: "s3", label: "Store AP v1 (.docx)", desc: "Save generated Acquisition Plan to S3" },
      { type: "message", from: "s3", to: "docgen", label: "Pre-signed download URL", desc: "S3 returns secure download link", dashed: true },
      { type: "message", from: "docgen", to: "user", label: "Acquisition Plan ready for download", desc: "Document Generator delivers the completed AP with download link" }
    ]
  }
];

// ============================================================
// PROMPTS (condensed)
// ============================================================
// Prompt titles used as fallback while API loads
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

// Map prompt keys to test numbers for cross-referencing
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

interface RunMeta {
  filename?: string;
  name?: string;        // CloudWatch stream name
  timestamp: string;
  source: 'local' | 'cloudwatch';
  passed?: number;
  failed?: number;
  total_tests?: number;
}

interface TraceBlock {
  type: string;
  text?: string;
  tool?: string;
  id?: string;
  input?: Record<string, unknown>;
  tool_use_id?: string;
  content?: string;
}

interface TraceMessage {
  type: string;
  session_id?: string;
  result?: string;
  cost_usd?: number;
  usage?: Record<string, number>;
  content?: TraceBlock[];
}

interface TraceResult {
  status: string;
  logs: string[];
  trace?: TraceMessage[];
}

interface CWEvent {
  timestamp: string;
  message: Record<string, unknown> | string;
}

// ============================================================
// Simple Markdown to HTML renderer
// ============================================================
function renderMarkdown(md: string): string {
  let html = md
    // Escape HTML
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Code blocks (``` ... ```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, _lang, code) =>
    `<pre><code>${code.trim()}</code></pre>`
  );

  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Tables
  html = html.replace(/^(\|.+\|)\n(\|[-| :]+\|)\n((?:\|.+\|\n?)*)/gm, (_m, header, _sep, body) => {
    const ths = (header as string).split('|').filter((c: string) => c.trim()).map((c: string) => `<th>${c.trim()}</th>`).join('');
    const rows = (body as string).trim().split('\n').map((row: string) => {
      const tds = row.split('|').filter((c: string) => c.trim()).map((c: string) => `<td>${c.trim()}</td>`).join('');
      return `<tr>${tds}</tr>`;
    }).join('');
    return `<table><thead><tr>${ths}</tr></thead><tbody>${rows}</tbody></table>`;
  });

  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold / Italic
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr>');

  // Paragraphs (lines not already wrapped)
  html = html.replace(/^(?!<[a-z])((?!<\/)[^\n]+)$/gm, '<p>$1</p>');

  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, '');

  return html;
}

// ============================================================
// SVG Constants
// ============================================================
const ACTOR_W = 130;
const ACTOR_H = 50;
const ACTOR_GAP = 30;
const STEP_H = 42;
const TOP_MARGIN = 90;
const LEFT_MARGIN = 30;
const NOTE_W = 160;

// ============================================================
// Component
// ============================================================
export default function EvalViewer() {
  const [selectedUC, setSelectedUC] = useState(USE_CASES[0]);
  const [currentStep, setCurrentStep] = useState(0);
  const [zoom, setZoom] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalPrompt, setModalPrompt] = useState<{ key: string; title: string; section: string; content: string; file: string } | null>(null);
  const [prompts, setPrompts] = useState<Record<string, { title: string; file: string; content: string }>>({});
  const [promptsLoading, setPromptsLoading] = useState(true);
  const [availableRuns, setAvailableRuns] = useState<RunMeta[]>([]);
  const [selectedRun, setSelectedRun] = useState<RunMeta | null>(null);
  const [traceResults, setTraceResults] = useState<Record<string, TraceResult>>({});
  const [cwEvents, setCwEvents] = useState<CWEvent[]>([]);
  const [modalTab, setModalTab] = useState<'prompt' | 'traces' | 'logs'>('prompt');
  const [expandedTraces, setExpandedTraces] = useState<Set<string>>(new Set());

  // Fetch real prompts from eagle-plugin/ skill files via API
  useEffect(() => {
    fetch('/api/prompts')
      .then(res => res.json())
      .then(data => { setPrompts(data); setPromptsLoading(false); })
      .catch(() => setPromptsLoading(false));
  }, []);

  // Fetch available runs (CloudWatch first, local fallback)
  useEffect(() => {
    async function loadRuns() {
      const runs: RunMeta[] = [];

      // Try CloudWatch first
      try {
        const cwRes = await fetch('/api/cloudwatch?runs=1');
        if (cwRes.ok) {
          const cwData = await cwRes.json();
          for (const s of cwData.streams || []) {
            runs.push({
              name: s.name,
              timestamp: s.lastEvent || s.created || '',
              source: 'cloudwatch',
            });
          }
        }
      } catch { /* CloudWatch unavailable */ }

      // Also load local runs
      try {
        const localRes = await fetch('/api/trace-logs?list=1');
        if (localRes.ok) {
          const localData = await localRes.json();
          for (const r of localData.runs || []) {
            runs.push({
              filename: r.filename,
              timestamp: r.timestamp,
              source: 'local',
              passed: r.passed,
              failed: r.failed,
              total_tests: r.total_tests,
            });
          }
        }
      } catch { /* no local files */ }

      setAvailableRuns(runs);
      if (runs.length > 0) setSelectedRun(runs[0]);
    }
    loadRuns();
  }, []);

  // When a run is selected, load its trace data
  useEffect(() => {
    if (!selectedRun) return;
    let cancelled = false;

    async function loadRunData() {
      if (selectedRun!.source === 'local' && selectedRun!.filename) {
        try {
          const res = await fetch(`/api/trace-logs?run=${selectedRun!.filename}`);
          if (cancelled) return;
          if (res.ok) {
            const data = await res.json();
            setTraceResults(data.results || {});
          }
        } catch { /* ignore */ }
      } else if (selectedRun!.source === 'cloudwatch' && selectedRun!.name) {
        try {
          const res = await fetch(`/api/cloudwatch?stream=${encodeURIComponent(selectedRun!.name)}&group=test-runs`);
          if (cancelled) return;
          if (res.ok) {
            const data = await res.json();
            setCwEvents(data.events || []);
            // Convert CW events to trace results format
            const results: Record<string, TraceResult> = {};
            for (const ev of data.events || []) {
              const msg = typeof ev.message === 'object' ? ev.message : {};
              if ((msg as Record<string, unknown>).type === 'test_result') {
                const m = msg as Record<string, unknown>;
                results[String(m.test_id)] = {
                  status: String(m.status || 'unknown'),
                  logs: [`[CloudWatch] ${m.test_name}: ${m.status}`],
                };
              }
            }
            setTraceResults(results);
          }
        } catch { /* ignore */ }
      }
    }
    loadRunData();
    return () => { cancelled = true; };
  }, [selectedRun]);

  const svgRef = useRef<SVGSVGElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const diagramRef = useRef<HTMLDivElement>(null);
  const isPanning = useRef(false);
  const lastPan = useRef({ x: 0, y: 0 });

  const uc = selectedUC;
  const actors = uc.actors;
  const steps = uc.steps;
  const phases = uc.phases;

  const totalW = LEFT_MARGIN * 2 + actors.length * (ACTOR_W + ACTOR_GAP) - ACTOR_GAP;
  const totalH = TOP_MARGIN + steps.length * STEP_H + 80;

  const baseViewBox = { x: -20, y: -10, w: totalW + 40, h: totalH + 20 };
  const [viewBox, setViewBox] = useState(baseViewBox);

  // Reset viewBox when use case changes
  useEffect(() => {
    const newVB = { x: -20, y: -10, w: totalW + 40, h: totalH + 20 };
    setViewBox(newVB);
    setZoom(1);
    setCurrentStep(0);
  }, [selectedUC, totalW, totalH]);

  // Scroll sidebar active item into view
  useEffect(() => {
    const activeItem = sidebarRef.current?.querySelector(`[data-step="${currentStep}"]`);
    activeItem?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [currentStep]);

  // Compute actor X positions
  const actorX: Record<string, number> = {};
  actors.forEach((a, i) => {
    actorX[a.id] = LEFT_MARGIN + i * (ACTOR_W + ACTOR_GAP) + ACTOR_W / 2;
  });

  const goToStep = useCallback((idx: number) => {
    if (idx >= 0 && idx < steps.length) setCurrentStep(idx);
  }, [steps.length]);

  const nextStep = () => goToStep(currentStep + 1);
  const prevStep = () => goToStep(currentStep - 1);

  const zoomIn = () => {
    setViewBox(vb => {
      const cx = vb.x + vb.w / 2;
      const cy = vb.y + vb.h / 2;
      const nw = vb.w * 0.8;
      const nh = vb.h * 0.8;
      return { x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh };
    });
    setZoom(z => z / 0.8);
  };

  const zoomOut = () => {
    setViewBox(vb => {
      const cx = vb.x + vb.w / 2;
      const cy = vb.y + vb.h / 2;
      const nw = vb.w * 1.25;
      const nh = vb.h * 1.25;
      return { x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh };
    });
    setZoom(z => z / 1.25);
  };

  const fitToView = () => {
    setViewBox({ x: -20, y: -10, w: totalW + 40, h: totalH + 20 });
    setZoom(1);
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (modalOpen) {
        if (e.key === 'Escape') setModalOpen(false);
        return;
      }
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); nextStep(); }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); prevStep(); }
      if (e.key === 'Home') { e.preventDefault(); goToStep(0); }
      if (e.key === 'End') { e.preventDefault(); goToStep(steps.length - 1); }
      if (e.key === '+' || e.key === '=') zoomIn();
      if (e.key === '-') zoomOut();
      if (e.key === '0') fitToView();
      if (e.key === 'Enter') viewCurrentPrompt();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  });

  // Mouse pan/zoom
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.actor-box') || (e.target as HTMLElement).closest('.step-group')) return;
    isPanning.current = true;
    lastPan.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isPanning.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = viewBox.w / rect.width;
    const scaleY = viewBox.h / rect.height;
    const dx = (e.clientX - lastPan.current.x) * scaleX;
    const dy = (e.clientY - lastPan.current.y) * scaleY;
    setViewBox(vb => ({ ...vb, x: vb.x - dx, y: vb.y - dy }));
    lastPan.current = { x: e.clientX, y: e.clientY };
  };

  const handleMouseUp = () => { isPanning.current = false; };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    if (e.deltaY < 0) zoomIn();
    else zoomOut();
  };

  const viewCurrentPrompt = () => {
    const step = steps[currentStep];
    if (!step?.prompt) return;
    showPrompt(step.prompt, step.section);
  };

  const showPrompt = (key: string, section?: string) => {
    const prompt = prompts[key];
    if (!prompt) return;
    let content = prompt.content;
    if (section) {
      const escaped = section.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const match = content.match(new RegExp(`(## ${escaped}[\\s\\S]*?)(?=\\n## |$)`, 'i'));
      if (match) content = match[1];
    }
    setModalPrompt({ key, title: prompt.title, section: section || 'Full Prompt', content, file: prompt.file });
    setModalTab('prompt');
    setModalOpen(true);
  };

  // Get test traces for the current prompt key
  const getTestTracesForPrompt = (promptKey: string): { testId: string; result: TraceResult }[] => {
    const testIds = SKILL_TEST_MAP[promptKey] || [];
    return testIds
      .map(id => ({ testId: String(id), result: traceResults[String(id)] }))
      .filter(t => t.result);
  };

  // Get live logs from CloudWatch for current prompt
  const getLiveLogsForPrompt = (promptKey: string): CWEvent[] => {
    const testIds = SKILL_TEST_MAP[promptKey] || [];
    return cwEvents.filter(ev => {
      const msg = typeof ev.message === 'object' ? ev.message as Record<string, unknown> : {};
      return testIds.includes(Number(msg.test_id));
    });
  };

  // Get step label for sidebar
  const getStepLabel = (step: Step, idx: number) => {
    if (step.type === 'message') {
      const fromName = actors.find(a => a.id === step.from)?.name?.split(/[\s/]+/)[0] || step.from;
      const toName = actors.find(a => a.id === step.to)?.name?.split(/[\s/]+/)[0] || step.to;
      const text = `${fromName} \u2192 ${toName}: ${step.label}`;
      return text.length > 55 ? text.substring(0, 52) + '...' : text;
    } else if (step.type === 'self') {
      const name = actors.find(a => a.id === step.actor)?.name?.split(/[\s/]+/)[0] || step.actor;
      const text = `${name}: ${step.label}`;
      return text.length > 55 ? text.substring(0, 52) + '...' : text;
    } else {
      const text = `[Note] ${step.text?.split('\n')[0]}`;
      return text.length > 55 ? text.substring(0, 52) + '...' : text;
    }
  };

  // Render SVG step
  const renderStep = (step: Step, idx: number) => {
    const y = TOP_MARGIN + idx * STEP_H + 25;
    const opacity = idx === currentStep ? 1 : 0.5;

    if (step.type === 'message' && step.from && step.to) {
      const x1 = actorX[step.from];
      const x2 = actorX[step.to];
      const midX = (x1 + x2) / 2;
      const isHighlighted = idx === currentStep;
      const label = (step.label || '').length > 45 ? (step.label || '').substring(0, 42) + '...' : step.label;

      return (
        <g key={idx} className="step-group" style={{ opacity, cursor: 'pointer' }} onClick={() => goToStep(idx)}>
          <line
            x1={x1} y1={y} x2={x2 - (x2 > x1 ? 8 : -8)} y2={y}
            stroke={isHighlighted ? '#818cf8' : '#6b7280'}
            strokeWidth={isHighlighted ? 2.5 : 1.5}
            strokeDasharray={step.dashed ? '5 3' : 'none'}
            markerEnd={isHighlighted ? 'url(#arrowhead-hl)' : 'url(#arrowhead)'}
          />
          <text x={midX} y={y - 8} fill="#d1d5db" textAnchor="middle" fontSize="10" fontFamily="system-ui, sans-serif">
            {label}
          </text>
        </g>
      );
    }

    if (step.type === 'self' && step.actor) {
      const x = actorX[step.actor];
      const isHighlighted = idx === currentStep;
      const label = (step.label || '').length > 40 ? (step.label || '').substring(0, 37) + '...' : step.label;

      return (
        <g key={idx} className="step-group" style={{ opacity, cursor: 'pointer' }} onClick={() => goToStep(idx)}>
          <path
            d={`M ${x} ${y} C ${x + 40} ${y}, ${x + 40} ${y + 20}, ${x + 8} ${y + 20}`}
            stroke={isHighlighted ? '#818cf8' : '#6b7280'}
            strokeWidth={isHighlighted ? 2.5 : 1.5}
            fill="none"
            markerEnd={isHighlighted ? 'url(#arrowhead-hl)' : 'url(#arrowhead)'}
          />
          <text x={x + 48} y={y + 6} fill="#d1d5db" fontSize="10" fontFamily="system-ui, sans-serif">
            {label}
          </text>
        </g>
      );
    }

    if (step.type === 'note' && step.actor) {
      const x = actorX[step.actor] + ACTOR_W / 2 + 10;
      const lines = (step.text || '').split('\n');
      const h = lines.length * 14 + 10;
      const w = Math.min(NOTE_W, Math.max(...lines.map(l => l.length * 6)) + 20);

      return (
        <g key={idx} className="step-group" style={{ opacity, cursor: 'pointer' }} onClick={() => goToStep(idx)}>
          <rect x={x} y={y - 10} width={w} height={h} fill="#1e2030" stroke="#3a3d4a" strokeWidth={1} rx={4} ry={4} />
          {lines.map((line, li) => (
            <text key={li} x={x + 8} y={y + 4 + li * 14} fill="#9ca3af" fontSize="9" fontFamily="system-ui, sans-serif">
              {line}
            </text>
          ))}
        </g>
      );
    }

    return null;
  };

  // Detail bar info
  const stepInfo = () => {
    const step = steps[currentStep];
    if (!step) return { actors: 'Select a step', label: '', desc: '' };

    if (step.type === 'message') {
      const fromActor = actors.find(a => a.id === step.from);
      const toActor = actors.find(a => a.id === step.to);
      return {
        actors: `${fromActor?.name || step.from} \u2192 ${toActor?.name || step.to}`,
        actorColors: [fromActor?.color || '#999', toActor?.color || '#999'],
        label: step.label || '',
        desc: step.desc || ''
      };
    } else if (step.type === 'self') {
      const actor = actors.find(a => a.id === step.actor);
      return {
        actors: `${actor?.name || step.actor} (self)`,
        actorColors: [actor?.color || '#999'],
        label: step.label || '',
        desc: step.desc || ''
      };
    } else {
      const actor = actors.find(a => a.id === step.actor);
      return {
        actors: `Note on ${actor?.name || step.actor}`,
        actorColors: ['#eab308'],
        label: step.text?.split('\n')[0] || '',
        desc: step.desc || ''
      };
    }
  };

  const info = stepInfo();
  const currentStepData = steps[currentStep];

  // Find which phase each step belongs to
  const getPhaseForStep = (idx: number) => {
    return phases.find(p => idx >= p.startStep && idx <= p.endStep);
  };

  return (
    <AuthGuard>
      <div className="flex flex-col h-screen overflow-hidden bg-[#0f1117] text-gray-200">
        <TopNav />
            {/* Header bar */}
            <div className="flex items-center gap-4 px-4 py-2 bg-[#161822] border-b border-[#2a2d3a] shrink-0">
              <div className="text-sm font-semibold text-white">EAGLE <span className="text-gray-400 font-normal">Eval Viewer</span></div>
              <select
                value={uc.id}
                onChange={(e) => {
                  const found = USE_CASES.find(u => u.id === e.target.value);
                  if (found) setSelectedUC(found);
                }}
                className="bg-[#1e2030] border border-[#2a2d3a] text-gray-200 text-xs rounded px-2 py-1.5 min-w-[280px] focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {USE_CASES.map(u => (
                  <option key={u.id} value={u.id}>{u.title}</option>
                ))}
              </select>
              {availableRuns.length > 0 && (
                <>
                  <span className="text-gray-600">|</span>
                  <select
                    value={selectedRun ? (selectedRun.filename || selectedRun.name || '') : ''}
                    onChange={(e) => {
                      const run = availableRuns.find(r => (r.filename || r.name) === e.target.value);
                      if (run) setSelectedRun(run);
                    }}
                    className="bg-[#1e2030] border border-[#2a2d3a] text-gray-200 text-xs rounded px-2 py-1.5 min-w-[200px] focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    {availableRuns.map((r, i) => {
                      const label = r.source === 'cloudwatch'
                        ? `CW: ${r.name}`
                        : `${r.filename}${r.passed != null ? ` (${r.passed}/${r.total_tests})` : ''}`;
                      return <option key={i} value={r.filename || r.name || ''}>{label}</option>;
                    })}
                  </select>
                </>
              )}
              <div className="flex items-center gap-2 ml-auto">
                <button onClick={prevStep} disabled={currentStep <= 0} className="px-2 py-1 text-xs bg-[#1e2030] border border-[#2a2d3a] rounded hover:bg-[#252840] disabled:opacity-30 transition-colors">&laquo; Prev</button>
                <span className="text-xs text-gray-400 font-mono min-w-[60px] text-center">{currentStep + 1} / {steps.length}</span>
                <button onClick={nextStep} disabled={currentStep >= steps.length - 1} className="px-2 py-1 text-xs bg-[#1e2030] border border-[#2a2d3a] rounded hover:bg-[#252840] disabled:opacity-30 transition-colors">Next &raquo;</button>
              </div>
            </div>

            {/* Main layout */}
            <div className="flex flex-1 min-h-0">
              {/* Sidebar */}
              <aside ref={sidebarRef} className="w-72 bg-[#13151f] border-r border-[#2a2d3a] overflow-y-auto shrink-0">
                <div className="px-4 py-3 border-b border-[#2a2d3a]">
                  <div className="text-xs font-semibold text-gray-300">{uc.title}</div>
                  <div className="text-[10px] text-gray-500 mt-0.5">{uc.subtitle}</div>
                </div>
                {steps.map((step, i) => {
                  const phase = phases.find(p => p.startStep === i);
                  return (
                    <div key={i}>
                      {phase && (
                        <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 mt-2" style={{ borderLeft: `3px solid ${phase.border}`, marginLeft: '12px', paddingLeft: '8px' }}>
                          {phase.name}
                        </div>
                      )}
                      <button
                        data-step={i}
                        onClick={() => goToStep(i)}
                        className={`w-full flex items-center gap-2 px-4 py-1.5 text-left text-[11px] transition-colors ${
                          i === currentStep
                            ? 'bg-indigo-500/20 text-indigo-300 border-l-2 border-indigo-400'
                            : i < currentStep
                              ? 'text-gray-500 hover:bg-[#1a1c2e] border-l-2 border-transparent'
                              : 'text-gray-400 hover:bg-[#1a1c2e] border-l-2 border-transparent'
                        }`}
                      >
                        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${i === currentStep ? 'bg-indigo-400' : i < currentStep ? 'bg-gray-600' : 'bg-gray-700'}`} />
                        <span className="truncate flex-1">{getStepLabel(step, i)}</span>
                        {step.prompt && (
                          <span className="text-[8px] bg-indigo-500 text-white px-1.5 py-0.5 rounded-full shrink-0">prompt</span>
                        )}
                      </button>
                    </div>
                  );
                })}
              </aside>

              {/* Diagram area */}
              <div
                ref={diagramRef}
                className="flex-1 relative overflow-hidden bg-[#0f1117]"
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                onWheel={handleWheel}
                style={{ cursor: isPanning.current ? 'grabbing' : 'grab' }}
              >
                <svg
                  ref={svgRef}
                  viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
                  className="w-full h-full"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  {/* Defs */}
                  <defs>
                    <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                      <polygon points="0 0, 10 3.5, 0 7" fill="#9ca3af" />
                    </marker>
                    <marker id="arrowhead-hl" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
                      <polygon points="0 0, 10 3.5, 0 7" fill="#818cf8" />
                    </marker>
                  </defs>

                  {/* Phase backgrounds */}
                  {phases.map((p, i) => {
                    const y1 = TOP_MARGIN + p.startStep * STEP_H - 15;
                    const y2 = TOP_MARGIN + (p.endStep + 1) * STEP_H + 5;
                    return (
                      <g key={`phase-${i}`}>
                        <rect
                          x={LEFT_MARGIN - 15} y={y1}
                          width={totalW - LEFT_MARGIN * 2 + 30} height={y2 - y1}
                          fill={p.color} stroke={p.border} strokeWidth={1} rx={8} ry={8}
                        />
                        <text x={LEFT_MARGIN - 5} y={y1 + 14} fill={p.border} fontSize="11" fontFamily="system-ui, sans-serif">
                          {p.name}
                        </text>
                      </g>
                    );
                  })}

                  {/* Lifelines */}
                  {actors.map(a => (
                    <line
                      key={`lifeline-${a.id}`}
                      x1={actorX[a.id]} y1={TOP_MARGIN + 5}
                      x2={actorX[a.id]} y2={totalH - 20}
                      stroke="#2a2d3a" strokeWidth={1} strokeDasharray="6 4"
                    />
                  ))}

                  {/* Steps */}
                  {steps.map((step, i) => renderStep(step, i))}

                  {/* Actor headers (on top) */}
                  {actors.map((a) => {
                    const x = actorX[a.id];
                    const needsWrap = a.name.length > 18;
                    const parts = a.name.split(/[\s/]+/);
                    const mid = Math.ceil(parts.length / 2);

                    return (
                      <g
                        key={`actor-${a.id}`}
                        className="actor-box"
                        style={{ cursor: prompts[a.id] || prompts[a.id === 'sup' || a.id === 'agent' ? 'supervisor' : a.id] ? 'pointer' : 'default' }}
                        onClick={() => {
                          const key = a.id === 'sup' || a.id === 'agent' ? 'supervisor' : a.id;
                          if (prompts[key]) showPrompt(key);
                        }}
                      >
                        <rect
                          x={x - ACTOR_W / 2} y={10}
                          width={ACTOR_W} height={ACTOR_H}
                          fill={a.color} rx={8} ry={8}
                          stroke="rgba(255,255,255,0.2)" strokeWidth={1}
                        />
                        {needsWrap ? (
                          <text x={x} y={31} fill="white" textAnchor="middle" fontSize="10" fontWeight="600" fontFamily="system-ui, sans-serif">
                            <tspan x={x} dy="0">{parts.slice(0, mid).join(' ')}</tspan>
                            <tspan x={x} dy="13">{parts.slice(mid).join(' ')}</tspan>
                          </text>
                        ) : (
                          <text x={x} y={40} fill="white" textAnchor="middle" fontSize="11" fontWeight="600" fontFamily="system-ui, sans-serif">
                            {a.name}
                          </text>
                        )}
                      </g>
                    );
                  })}

                  {/* Title */}
                  <text x={totalW / 2} y={-2} fill="#6b7280" textAnchor="middle" fontSize="10" fontFamily="system-ui, sans-serif">
                    {uc.title}
                  </text>
                </svg>

                {/* Zoom controls */}
                <div className="absolute bottom-4 right-4 flex flex-col gap-1 bg-[#1e2030] border border-[#2a2d3a] rounded-lg p-1">
                  <button onClick={zoomIn} className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#252840] rounded transition-colors text-lg">+</button>
                  <div className="text-[10px] text-gray-500 text-center py-0.5">{Math.round(zoom * 100)}%</div>
                  <button onClick={zoomOut} className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#252840] rounded transition-colors text-lg">-</button>
                  <button onClick={fitToView} className="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-white hover:bg-[#252840] rounded transition-colors text-xs">Fit</button>
                </div>
              </div>
            </div>

            {/* Detail bar */}
            <div className="flex items-center gap-4 px-4 py-2.5 bg-[#161822] border-t border-[#2a2d3a] shrink-0">
              <div className="flex-1 min-w-0">
                <div className="text-xs font-medium" style={{ color: info.actorColors?.[0] || '#999' }}>{info.actors}</div>
                <div className="text-xs text-gray-300 truncate">{info.label}</div>
                {info.desc && <div className="text-[10px] text-gray-500 truncate">{info.desc}</div>}
              </div>
              {promptsLoading && currentStepData?.prompt && (
                <span className="text-[10px] text-gray-500 animate-pulse">Loading prompts...</span>
              )}
              <button
                onClick={viewCurrentPrompt}
                disabled={!currentStepData?.prompt || promptsLoading}
                className="px-3 py-1.5 text-xs bg-indigo-600 text-white rounded hover:bg-indigo-500 disabled:opacity-30 disabled:cursor-not-allowed transition-colors shrink-0"
              >
                {currentStepData?.prompt ? `View ${prompts[currentStepData.prompt]?.title || PROMPT_TITLES[currentStepData.prompt] || 'Prompt'}` : 'View Prompt'}
              </button>
            </div>

        {/* Tabbed Modal: Prompt | Test Traces | Live Logs */}
        {modalOpen && modalPrompt && (() => {
          const promptKey = modalPrompt.key || currentStepData?.prompt || '';
          const testTraces = getTestTracesForPrompt(promptKey);
          const liveLogs = getLiveLogsForPrompt(promptKey);
          const tabs = [
            { id: 'prompt' as const, label: 'Prompt' },
            { id: 'traces' as const, label: `Test Traces${testTraces.length ? ` (${testTraces.length})` : ''}` },
            { id: 'logs' as const, label: `Live Logs${liveLogs.length ? ` (${liveLogs.length})` : ''}` },
          ];

          return (
            <div
              className="fixed inset-0 bg-black/60 flex items-center justify-center z-50"
              onClick={(e) => { if (e.target === e.currentTarget) setModalOpen(false); }}
            >
              <div className="bg-[#1e2030] border border-[#2a2d3a] rounded-xl w-[750px] max-h-[80vh] flex flex-col mx-4">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2d3a]">
                  <div>
                    <h2 className="text-lg font-semibold text-white">{modalPrompt.title}</h2>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs bg-indigo-500/30 text-indigo-300 px-2 py-0.5 rounded-full">{modalPrompt.section}</span>
                      <span className="text-[10px] bg-green-500/20 text-green-300 px-2 py-0.5 rounded-full">Live from SDK</span>
                    </div>
                  </div>
                  <button onClick={() => setModalOpen(false)} className="text-gray-400 hover:text-white text-xl px-2">&times;</button>
                </div>

                {/* Tab bar */}
                <div className="flex border-b border-[#2a2d3a] px-6">
                  {tabs.map(tab => (
                    <button
                      key={tab.id}
                      onClick={() => setModalTab(tab.id)}
                      className={`px-4 py-2.5 text-xs font-medium transition-colors relative ${
                        modalTab === tab.id
                          ? 'text-indigo-300'
                          : 'text-gray-500 hover:text-gray-300'
                      }`}
                    >
                      {tab.label}
                      {modalTab === tab.id && (
                        <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-indigo-500 rounded-t" />
                      )}
                    </button>
                  ))}
                </div>

                {/* Tab content */}
                <div className="flex-1 overflow-y-auto">
                  {/* Prompt tab */}
                  {modalTab === 'prompt' && (
                    <div className="px-6 py-4 prose prose-invert prose-sm max-w-none
                      [&_h1]:text-lg [&_h1]:font-bold [&_h1]:text-white [&_h1]:mb-3
                      [&_h2]:text-base [&_h2]:font-semibold [&_h2]:text-indigo-300 [&_h2]:mt-5 [&_h2]:mb-2 [&_h2]:border-b [&_h2]:border-[#2a2d3a] [&_h2]:pb-1
                      [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-gray-200 [&_h3]:mt-4 [&_h3]:mb-1
                      [&_p]:text-sm [&_p]:text-gray-300 [&_p]:leading-relaxed [&_p]:mb-2
                      [&_ul]:text-sm [&_ul]:text-gray-300 [&_li]:mb-0.5
                      [&_ol]:text-sm [&_ol]:text-gray-300
                      [&_table]:text-xs [&_table]:border-collapse [&_table]:w-full [&_table]:my-2
                      [&_th]:bg-[#252840] [&_th]:text-gray-200 [&_th]:px-3 [&_th]:py-1.5 [&_th]:text-left [&_th]:border [&_th]:border-[#2a2d3a]
                      [&_td]:px-3 [&_td]:py-1.5 [&_td]:border [&_td]:border-[#2a2d3a] [&_td]:text-gray-400
                      [&_code]:bg-[#252840] [&_code]:text-indigo-300 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs
                      [&_pre]:bg-[#0f1117] [&_pre]:border [&_pre]:border-[#2a2d3a] [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:my-2 [&_pre]:overflow-x-auto
                      [&_pre_code]:bg-transparent [&_pre_code]:p-0
                      [&_strong]:text-gray-100
                      [&_hr]:border-[#2a2d3a] [&_hr]:my-4
                      [&_blockquote]:border-l-2 [&_blockquote]:border-indigo-500 [&_blockquote]:pl-3 [&_blockquote]:text-gray-400
                    ">
                      <div dangerouslySetInnerHTML={{ __html: renderMarkdown(modalPrompt.content) }} />
                    </div>
                  )}

                  {/* Test Traces tab */}
                  {modalTab === 'traces' && (
                    <div className="px-6 py-4">
                      {testTraces.length === 0 ? (
                        <div className="text-center py-8 text-gray-500 text-sm">
                          No test traces available for this skill.
                          {!selectedRun && ' Select a test run above to load traces.'}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {testTraces.map(({ testId, result }) => {
                            const traceExpanded = expandedTraces.has(testId);
                            const hasTrace = result.trace && result.trace.length > 0;
                            return (
                            <div key={testId} className="bg-[#0f1117] border border-[#2a2d3a] rounded-lg overflow-hidden">
                              <div className="flex items-center gap-2 px-4 py-2 bg-[#161822]">
                                <span className={`w-2 h-2 rounded-full ${result.status === 'pass' ? 'bg-green-500' : result.status === 'skip' ? 'bg-yellow-500' : 'bg-red-500'}`} />
                                <span className="text-xs font-medium text-gray-200">Test {testId}</span>
                                <span className={`text-[10px] px-2 py-0.5 rounded-full ${
                                  result.status === 'pass' ? 'bg-green-500/20 text-green-300' :
                                  result.status === 'skip' ? 'bg-yellow-500/20 text-yellow-300' :
                                  'bg-red-500/20 text-red-300'
                                }`}>
                                  {result.status.toUpperCase()}
                                </span>
                                {hasTrace && (
                                  <button
                                    onClick={() => setExpandedTraces(prev => {
                                      const next = new Set(prev);
                                      if (next.has(testId)) next.delete(testId); else next.add(testId);
                                      return next;
                                    })}
                                    className="ml-auto text-[10px] px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 hover:bg-indigo-500/30 transition-colors"
                                  >
                                    {traceExpanded ? 'Hide' : 'Show'} Full Trace ({result.trace!.length} msgs)
                                  </button>
                                )}
                              </div>
                              {/* Summary logs (always shown) */}
                              <pre className="text-[10px] text-gray-400 font-mono whitespace-pre-wrap p-4 max-h-48 overflow-y-auto leading-relaxed">
                                {result.logs.join('\n')}
                              </pre>
                              {/* Full conversation trace (expandable) */}
                              {traceExpanded && hasTrace && (
                                <div className="border-t border-[#2a2d3a] p-4 space-y-2">
                                  <div className="text-[10px] font-medium text-indigo-300 uppercase tracking-wider mb-2">Full Conversation Trace</div>
                                  {result.trace!.map((msg, i) => (
                                    <div key={i} className={`rounded p-2 text-[10px] font-mono ${
                                      msg.type === 'SystemMessage' ? 'bg-gray-800/50 border-l-2 border-gray-500' :
                                      msg.type === 'AssistantMessage' ? 'bg-emerald-900/20 border-l-2 border-emerald-500' :
                                      msg.type === 'UserMessage' ? 'bg-blue-900/20 border-l-2 border-blue-500' :
                                      msg.type === 'ResultMessage' ? 'bg-amber-900/20 border-l-2 border-amber-500' :
                                      'bg-gray-800/30 border-l-2 border-gray-600'
                                    }`}>
                                      <div className="flex items-center gap-2 mb-1">
                                        <span className={`font-bold ${
                                          msg.type === 'SystemMessage' ? 'text-gray-400' :
                                          msg.type === 'AssistantMessage' ? 'text-emerald-400' :
                                          msg.type === 'UserMessage' ? 'text-blue-400' :
                                          msg.type === 'ResultMessage' ? 'text-amber-400' :
                                          'text-gray-400'
                                        }`}>{msg.type}</span>
                                        {msg.session_id && <span className="text-gray-600">sid={msg.session_id.slice(0, 8)}...</span>}
                                        {msg.cost_usd != null && <span className="text-amber-300">${msg.cost_usd.toFixed(4)}</span>}
                                        {msg.usage && <span className="text-gray-500">{msg.usage.input_tokens || 0}in/{msg.usage.output_tokens || 0}out</span>}
                                      </div>
                                      {/* Content blocks */}
                                      {msg.content && msg.content.map((block, j) => (
                                        <div key={j} className="ml-3 mt-1">
                                          {block.type === 'text' && (
                                            <div className="text-gray-300 whitespace-pre-wrap max-h-60 overflow-y-auto">{block.text}</div>
                                          )}
                                          {block.type === 'thinking' && (
                                            <div className="text-purple-300 italic max-h-40 overflow-y-auto">
                                              <span className="text-purple-500 not-italic">[thinking] </span>{block.text}
                                            </div>
                                          )}
                                          {block.type === 'tool_use' && (
                                            <div className="text-cyan-300">
                                              <span className="text-cyan-500">[tool] </span>{block.tool}
                                              <pre className="text-gray-500 ml-4 mt-0.5 max-h-20 overflow-y-auto">{JSON.stringify(block.input, null, 2)}</pre>
                                            </div>
                                          )}
                                          {block.type === 'tool_result' && (
                                            <div className="text-gray-400 max-h-20 overflow-y-auto">
                                              <span className="text-gray-500">[result] </span>{block.content}
                                            </div>
                                          )}
                                        </div>
                                      ))}
                                      {/* ResultMessage result text */}
                                      {msg.result && (
                                        <div className="ml-3 mt-1 text-gray-300 whitespace-pre-wrap max-h-60 overflow-y-auto">{msg.result}</div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Live Logs tab */}
                  {modalTab === 'logs' && (
                    <div className="px-6 py-4">
                      {liveLogs.length === 0 ? (
                        <div className="text-center py-8 text-gray-500 text-sm">
                          No CloudWatch logs available.
                          {selectedRun?.source !== 'cloudwatch' && ' Select a CloudWatch run to view live logs.'}
                        </div>
                      ) : (
                        <div className="space-y-1">
                          {liveLogs.map((ev, i) => (
                            <div key={i} className="flex gap-3 text-xs font-mono py-1.5 border-b border-[#2a2d3a]/50">
                              <span className="text-gray-600 shrink-0 w-20">
                                {ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : '--'}
                              </span>
                              <pre className="text-gray-400 whitespace-pre-wrap flex-1">
                                {typeof ev.message === 'object' ? JSON.stringify(ev.message, null, 2) : String(ev.message)}
                              </pre>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between px-6 py-3 border-t border-[#2a2d3a]">
                  <span className="text-xs text-gray-500 font-mono">{modalPrompt.file}</span>
                  <button onClick={() => setModalOpen(false)} className="px-4 py-1.5 text-xs bg-[#252840] text-gray-300 rounded hover:bg-[#2a2d55] transition-colors">Close</button>
                </div>
              </div>
            </div>
          );
        })()}
      </div>
    </AuthGuard>
  );
}
