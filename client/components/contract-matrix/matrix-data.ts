/**
 * Contract Requirements Matrix — pure data & logic.
 * Ported from docs/contract-requirements-matrix.html (lines 960-1706).
 * All functions are pure (no DOM, no React).
 */

import type {
  AcquisitionMethod,
  ContractType,
  DollarThreshold,
  MatrixState,
  Requirements,
  CellData,
  CellColor,
  Preset,
  ApprovalChainNode,
  ContractTypeFactor,
  FactorAnswer,
  RankedRecommendation,
} from './matrix-types';

// ============================================================
// STATIC DATA
// ============================================================

export const METHODS: AcquisitionMethod[] = [
  { id: 'micro', label: 'Micro-Purchase', sub: 'FAR 13.2 — up to $15K', far: '13.2' },
  { id: 'sap', label: 'Simplified (SAP)', sub: 'FAR 13 — $15K to $350K', far: '13' },
  { id: 'negotiated', label: 'Negotiated', sub: 'FAR 15 — above $350K', far: '15' },
  { id: 'fss', label: 'FSS Direct Order', sub: 'FAR 8.4 — Schedule pricing', far: '8.4' },
  { id: 'bpa-est', label: 'BPA Establishment', sub: 'FAR 8.4 — Blanket agreement', far: '8.4' },
  { id: 'bpa-call', label: 'BPA Call Order', sub: 'FAR 8.4 — Order under BPA', far: '8.4' },
  { id: 'idiq', label: 'IDIQ Parent Award', sub: 'FAR 16.5 — Indefinite delivery', far: '16.5' },
  {
    id: 'idiq-order',
    label: 'IDIQ Task/Delivery Order',
    sub: 'FAR 16.5 — Order under IDIQ',
    far: '16.5',
  },
  { id: 'sole', label: 'Sole Source / J&A', sub: 'FAR 6.3 — Limited competition', far: '6.3' },
];

export const TYPES: ContractType[] = [
  { id: 'ffp', label: 'Firm-Fixed-Price (FFP)', risk: 95, category: 'fp' },
  { id: 'fp-epa', label: 'FP w/ Economic Price Adj', risk: 80, category: 'fp' },
  { id: 'fpi', label: 'Fixed-Price Incentive (FPI)', risk: 65, category: 'fp' },
  { id: 'cpff', label: 'Cost-Plus-Fixed-Fee (CPFF)', risk: 25, category: 'cr' },
  { id: 'cpif', label: 'Cost-Plus-Incentive-Fee (CPIF)', risk: 35, category: 'cr' },
  { id: 'cpaf', label: 'Cost-Plus-Award-Fee (CPAF)', risk: 20, category: 'cr' },
  { id: 'tm', label: 'Time & Materials (T&M)', risk: 15, category: 'loe' },
  { id: 'lh', label: 'Labor-Hour (LH)', risk: 15, category: 'loe' },
];

export const THRESHOLDS: DollarThreshold[] = [
  { value: 15000, label: '$15K MPT', short: '$15K' },
  { value: 25000, label: '$25K Synopsis', short: '$25K' },
  { value: 350000, label: '$350K SAT', short: '$350K' },
  { value: 750000, label: '$750K SubK', short: '$750K' },
  { value: 900000, label: '$900K J&A', short: '$900K' },
  { value: 2500000, label: '$2.5M TINA', short: '$2.5M' },
  { value: 4500000, label: '$4.5M Congress', short: '$4.5M' },
  { value: 6000000, label: '$6M IDIQ Enh', short: '$6M' },
  { value: 20000000, label: '$20M AP', short: '$20M' },
  { value: 50000000, label: '$50M HCA', short: '$50M' },
  { value: 90000000, label: '$90M SPE J&A', short: '$90M' },
  { value: 100000000, label: '$100M SPE', short: '$100M' },
  { value: 150000000, label: '$150M OAP', short: '$150M' },
];

export const PRESETS: Record<string, Preset> = {
  micro: {
    method: 'micro',
    type: 'ffp',
    dollarValue: 8000,
    isIT: false,
    isSB: false,
    isRD: false,
    isHS: false,
    isServices: false,
  },
  'simple-product': {
    method: 'sap',
    type: 'ffp',
    dollarValue: 150000,
    isIT: false,
    isSB: true,
    isRD: false,
    isHS: false,
    isServices: false,
  },
  'it-services': {
    method: 'idiq-order',
    type: 'tm',
    dollarValue: 2000000,
    isIT: true,
    isSB: false,
    isRD: false,
    isHS: false,
    isServices: true,
  },
  'rd-contract': {
    method: 'negotiated',
    type: 'cpff',
    dollarValue: 8000000,
    isIT: false,
    isSB: false,
    isRD: true,
    isHS: true,
    isServices: true,
  },
  'large-sole': {
    method: 'sole',
    type: 'ffp',
    dollarValue: 25000000,
    isIT: true,
    isSB: false,
    isRD: false,
    isHS: false,
    isServices: true,
  },
};

export const APPROVAL_CHAINS: Record<string, ApprovalChainNode[]> = {
  ap: [
    { label: 'CO', min: 0, max: 350000 },
    { label: 'One above CO', min: 350000, max: 20000000 },
    { label: 'OA Director / HCA', min: 20000000, max: 50000000 },
    { label: 'HCA-NIH', min: 50000000, max: 150000000 },
    { label: 'HHS/OAP', min: 150000000, max: Infinity },
  ],
  ja: [
    { label: 'CO', min: 0, max: 900000 },
    { label: 'HCA + Competition Advocate', min: 900000, max: 20000000 },
    { label: 'HCA + Reviews', min: 20000000, max: 90000000 },
    { label: 'SPE / HHS/OAP', min: 90000000, max: Infinity },
  ],
  as: [
    { label: 'OA Director / HCA', min: 0, max: 50000000 },
    { label: 'HCA-NIH', min: 50000000, max: 100000000 },
    { label: 'DDM-NIH', min: 100000000, max: 150000000 },
    { label: 'HHS/OAP', min: 150000000, max: Infinity },
  ],
};

export const DEFAULT_STATE: MatrixState = {
  method: 'sap',
  type: 'ffp',
  dollarValue: 100000,
  isIT: false,
  isSB: false,
  isRD: false,
  isHS: false,
  isServices: true,
};

// ============================================================
// PURE FUNCTIONS
// ============================================================

export function isTypeDisabled(method: string, typeId: string): boolean {
  if (method === 'micro' && typeId !== 'ffp') return true;
  if (
    (method === 'fss' || method === 'bpa-call' || method === 'bpa-est') &&
    ['cpff', 'cpif', 'cpaf'].includes(typeId)
  )
    return true;
  return false;
}

export function apApproval(v: number): string {
  if (v > 150000000) return 'HHS/OAP approval required (> $150M)';
  if (v > 50000000) return 'HCA-NIH approval required ($50M\u2013$150M)';
  if (v > 20000000) return 'OA Director approval by HCA ($20M\u2013$50M)';
  return 'One level above CO (SAT\u2013$20M)';
}

export function jaApproval(v: number): string {
  if (v > 90000000) return 'SPE through HHS/OAP (> $90M) \u2014 FAR 6.304(a)(4)';
  if (v > 20000000) return 'HCA + additional reviews ($20M\u2013$90M) \u2014 FAR 6.304(a)(3)';
  if (v > 900000) return 'HCA + NIH Competition Advocate ($900K\u2013$20M) \u2014 FAR 6.304(a)(2)';
  return 'CO approval (\u2264 $900K) \u2014 FAR 6.304(a)(1)';
}

export function fmtDollar(v: number): string {
  if (v >= 1000000000) return '$' + (v / 1000000000).toFixed(1) + 'B';
  if (v >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
  if (v >= 1000) return '$' + (v / 1000).toFixed(0) + 'K';
  return '$' + v.toLocaleString();
}

export function sliderToDollar(v: number): number {
  if (v <= 0) return 0;
  return Math.round(Math.pow(10, (v / 22) * Math.log10(200000000)));
}

export function dollarToSlider(d: number): number {
  if (d <= 0) return 0;
  return (Math.log10(d) / Math.log10(200000000)) * 22;
}

export function getActiveApprovalIndex(chain: ApprovalChainNode[], dollarValue: number): number {
  let activeIdx = 0;
  for (let i = 0; i < chain.length; i++) {
    if (dollarValue >= chain[i].min) activeIdx = i;
  }
  return activeIdx;
}

// ============================================================
// CORE: getRequirements
// ============================================================

export function getRequirements(s: MatrixState): Requirements {
  const v = s.dollarValue;
  const m = s.method;
  const t = s.type;
  const tObj = TYPES.find((x) => x.id === t)!;
  const isCR = tObj.category === 'cr';
  const isLOE = tObj.category === 'loe';
  const isFP = tObj.category === 'fp';

  // --- Warnings ---
  const warnings: string[] = [];
  const errors: string[] = [];

  if (isCR) {
    warnings.push(
      'Cost-reimbursement requires written AP approval, adequate contractor accounting system, and designated COR (FAR 16.301).',
    );
    if (s.isRD) {
      warnings.push('CPFF fee cap for R&D: 15% of estimated cost (FAR 16.304).');
    }
  }
  if (isLOE) {
    warnings.push(
      'T&M/LH is LEAST PREFERRED. CO must prepare D&F that no other contract type is suitable (FAR 16.601).',
    );
    if (m === 'bpa-est' && v > 350000) {
      warnings.push('T&M/LH BPAs > 3 years require HCA approval (not just standard D&F).');
    }
  }
  if (t === 'cpaf') {
    warnings.push(
      'CPAF requires approved award-fee plan before award. Rollover of unearned fee is PROHIBITED (FAR 16.402-2).',
    );
  }

  if (m === 'micro' && v > 15000) {
    errors.push('Micro-purchase threshold is $15,000 (HHS). Value exceeds MPT.');
  }
  if (m === 'sap' && v > 350000) {
    errors.push(
      'SAP threshold is $350,000 (SAT). Value exceeds SAT \u2014 use Negotiated (FAR 15).',
    );
  }

  // --- Documents ---
  const docs: Requirements['docs'] = [];
  docs.push({ name: 'Purchase Request', required: true, note: 'FAR 4.803(a)(1)' });

  if (m !== 'micro') {
    docs.push({
      name: s.isServices ? 'SOW / PWS' : 'Statement of Need (SON)',
      required: true,
      note: s.isServices ? 'Performance-based with QASP (FAR 37.6)' : 'Product specifications',
    });
  } else {
    docs.push({ name: 'SOW / PWS', required: false, note: 'Not required for micro-purchase' });
  }

  docs.push({
    name: 'IGCE',
    required: m !== 'micro',
    note:
      v > 350000 ? 'Detailed breakdown required (HHSAM 307.105-71)' : 'Sufficient detail/breakdown',
  });

  if (v > 350000) {
    docs.push({
      name: 'Market Research Report',
      required: true,
      note: 'HHS template required (HHSAM 310.000)',
    });
  } else if (v > 15000) {
    docs.push({
      name: 'Market Research',
      required: true,
      note: 'Documented justification (less formal)',
    });
  } else {
    docs.push({
      name: 'Market Research',
      required: false,
      note: 'Not required for micro-purchase',
    });
  }

  if (v > 350000) {
    docs.push({ name: 'Acquisition Plan', required: true, note: apApproval(v) });
  } else {
    docs.push({
      name: 'Acquisition Plan',
      required: false,
      note: 'Not required below SAT ($350K)',
    });
  }

  const needsJA = m === 'sole' || (m === 'fss' && v > 350000) || (m === 'bpa-call' && v > 350000);
  docs.push({
    name: 'J&A / Justification',
    required: needsJA,
    note: needsJA ? jaApproval(v) : 'Only if sole source / limited competition',
  });

  const needsDF = isLOE || (isCR && v > 350000) || t === 'fpi' || t === 'cpaf';
  docs.push({
    name: 'D&F (Determination & Findings)',
    required: needsDF,
    note: isLOE
      ? 'Required: no other type suitable (FAR 16.601)'
      : isCR
        ? 'Required for cost-reimbursement'
        : 'Required for incentive/award-fee',
  });

  const needsSSP = m === 'negotiated' && v > 350000;
  docs.push({
    name: 'Source Selection Plan',
    required: needsSSP,
    note: needsSSP ? 'Evaluation factors with relative importance' : 'N/A for this method',
  });

  const needsSubK = v > 750000 && !s.isSB;
  docs.push({
    name: 'Subcontracting Plan',
    required: needsSubK,
    note: needsSubK
      ? 'Required for non-SB > $750K (FAR 19.705)'
      : s.isSB
        ? 'Exempt \u2014 small business awardee'
        : 'Below $750K threshold',
  });

  const needsQASP = s.isServices && m !== 'micro';
  docs.push({
    name: 'QASP',
    required: needsQASP,
    note: needsQASP
      ? 'Required for performance-based services (FAR 46)'
      : 'Products / micro-purchase',
  });

  docs.push({
    name: 'HHS-653 Small Business Review',
    required: v > 15000,
    note: v > 15000 ? 'Required > MPT (AA 2023-02 Amendment 3)' : 'Below MPT',
  });

  if (s.isIT) {
    docs.push({
      name: 'IT Security & Privacy Certification',
      required: true,
      note: 'HHSAM 339.101(c)(1)',
    });
    docs.push({
      name: 'Section 508 ICT Evaluation',
      required: v > 15000,
      note: 'Required for IT > MPT',
    });
  }
  if (s.isHS) {
    docs.push({
      name: 'Human Subjects Provisions',
      required: true,
      note: 'HHSAR 370.3, 45 CFR 46',
    });
  }

  // --- Thresholds ---
  const triggered = THRESHOLDS.filter((th) => v >= th.value);
  const notTriggered = THRESHOLDS.filter((th) => v < th.value);

  // --- Compliance ---
  const compliance: Requirements['compliance'] = [];
  compliance.push({
    name: 'Section 889 Compliance',
    status: 'req',
    note: 'FAR 52.204-25 \u2014 all solicitations/contracts',
  });
  compliance.push({
    name: 'BAA/TAA Checklist',
    status: m !== 'micro' ? 'req' : 'cond',
    note: 'HHSAM 325.102-70',
  });
  compliance.push({
    name: 'SAM.gov Synopsis',
    status: v > 25000 ? 'req' : 'na',
    note: v > 25000 ? 'Required > $25K (FAR 5.101)' : 'Below $25K',
  });
  compliance.push({
    name: 'CPARS Evaluation',
    status: v > 350000 ? 'req' : 'na',
    note: v > 350000 ? 'Required > SAT' : 'Below SAT',
  });
  compliance.push({
    name: 'Congressional Notification',
    status: v > 4500000 ? 'req' : 'na',
    note: v > 4500000 ? 'Required > $4.5M \u2014 email grantfax@hhs.gov' : 'Below $4.5M',
  });
  compliance.push({
    name: 'Certified Cost/Pricing Data (TINA)',
    status: v > 2500000 ? 'req' : 'na',
    note: v > 2500000 ? 'Required > $2.5M (with exceptions)' : 'Below $2.5M',
  });
  if (s.isIT) {
    compliance.push({
      name: 'Section 508 ICT Accessibility',
      status: 'req',
      note: 'Required for IT acquisitions',
    });
    compliance.push({
      name: 'IT Security & Privacy Language',
      status: 'req',
      note: 'HHSAM Part 339.105',
    });
  }
  if (s.isHS) {
    compliance.push({
      name: 'Human Subjects Protection (45 CFR 46)',
      status: 'req',
      note: 'HHSAR 370.3',
    });
  }
  compliance.push({
    name: 'Severable Services \u22641yr/period',
    status: s.isServices ? 'req' : 'na',
    note: 'FAR 37.106(b), 32.703-3(b)',
  });

  // --- Competition ---
  let competition = '';
  if (m === 'micro') competition = 'Single quote acceptable. Government purchase card preferred.';
  else if (m === 'sap')
    competition =
      v > 25000
        ? 'Maximum practicable competition. Minimum 3 sources if practicable. Synopsis on SAM.gov.'
        : 'Reasonable competition. Minimum 3 sources if practicable.';
  else if (m === 'negotiated')
    competition =
      'Full and open competition required (FAR Part 6). Synopsis, evaluation factors, source selection.';
  else if (m === 'fss')
    competition =
      v > 350000
        ? 'eBuy posting OR RFQ to enough contractors for 3 quotes. Price reduction attempt required.'
        : 'Consider quotes from at least 3 schedule contractors.';
  else if (m === 'bpa-est')
    competition =
      v > 350000
        ? 'eBuy posting to ALL schedule holders OR 3-quote effort. Document award decision.'
        : 'Seek quotes from at least 3 schedule holders.';
  else if (m === 'bpa-call')
    competition =
      v > 350000
        ? 'RFQ to all BPA holders OR limited sources justification. Fair opportunity required.'
        : 'Fair opportunity to all BPA holders > MPT, or justification.';
  else if (m === 'idiq')
    competition =
      'Full and open competition for parent contract. Multiple award preference unless exception (FAR 16.504).';
  else if (m === 'idiq-order') {
    if (v > 7500000)
      competition =
        'Fair opportunity to all IDIQ holders. Clear requirements, evaluation factors with relative importance, post-award notifications/debriefings.';
    else if (v > 350000)
      competition =
        'Fair opportunity. Provide fair notice, issue solicitation/RFQ, document award basis.';
    else
      competition =
        'Fair opportunity. May place without further solicitation if fair consideration documented.';
  } else if (m === 'sole')
    competition =
      'Exception to competition \u2014 FAR 6.302 authority required. Full J&A with CO certification.';

  if (m === 'idiq-order' && v > 6000000) {
    competition +=
      ' ENHANCED: Detailed evaluation factors + relative importance + post-award notification + debriefing (> $6M).';
  }

  // --- PMR Checklist ---
  let pmr = 'HHS PMR Common Requirements';
  if (m === 'sap' || (m === 'negotiated' && v <= 350000)) pmr = 'HHS PMR SAP Checklist';
  else if (m === 'negotiated') pmr = 'HHS PMR Negotiated + Common Requirements';
  else if (m === 'fss') pmr = 'HHS PMR FSS Order Checklist';
  else if (m === 'bpa-est' || m === 'bpa-call') pmr = 'HHS PMR BPA Checklist';
  else if (m === 'idiq' || m === 'idiq-order') pmr = 'HHS PMR IDIQ Checklist';
  else if (m === 'sole') pmr = 'HHS PMR SAP or Negotiated + J&A Requirements';
  else if (m === 'micro') pmr = 'Micro-Purchase \u2014 Minimal file documentation';

  // --- Timeline ---
  let timeMin = 1,
    timeMax = 5;
  if (m === 'micro') {
    timeMin = 0;
    timeMax = 1;
  } else if (m === 'sap') {
    timeMin = 2;
    timeMax = 6;
  } else if (m === 'negotiated') {
    timeMin = 12;
    timeMax = 36;
  } else if (m === 'fss') {
    timeMin = 2;
    timeMax = 8;
  } else if (m === 'bpa-est') {
    timeMin = 4;
    timeMax = 12;
  } else if (m === 'bpa-call') {
    timeMin = 1;
    timeMax = 4;
  } else if (m === 'idiq') {
    timeMin = 16;
    timeMax = 52;
  } else if (m === 'idiq-order') {
    timeMin = 2;
    timeMax = 12;
  } else if (m === 'sole') {
    timeMin = 4;
    timeMax = 16;
  }

  if (v > 90000000) {
    timeMin += 6;
    timeMax += 8;
  } else if (v > 50000000) {
    timeMin += 4;
    timeMax += 6;
  } else if (v > 20000000) {
    timeMin += 2;
    timeMax += 4;
  }

  // --- Risk & Fee Caps ---
  const riskPct = tObj.risk;
  const feeCaps: string[] = [];
  if (isCR) {
    if (s.isRD) feeCaps.push('R&D: \u226415% of est. cost');
    feeCaps.push('Other CPFF: \u226410% of est. cost');
    feeCaps.push('A-E public works: \u22646% of est. construction');
    feeCaps.push('Cost-plus-%-of-cost: PROHIBITED');
  }

  return {
    docs,
    triggered,
    notTriggered,
    compliance,
    competition,
    pmr,
    timeMin,
    timeMax,
    riskPct,
    warnings,
    errors,
    feeCaps,
    isCR,
    isLOE,
    isFP,
  };
}

// ============================================================
// GRID: getCellData
// ============================================================

export function getCellData(methodId: string, typeId: string, gridState: MatrixState): CellData {
  const invalid = isTypeDisabled(methodId, typeId);
  if (invalid) return { invalid: true };

  const cellState: MatrixState = {
    method: methodId,
    type: typeId,
    dollarValue: gridState.dollarValue,
    isIT: gridState.isIT,
    isSB: gridState.isSB,
    isRD: gridState.isRD,
    isHS: gridState.isHS,
    isServices: gridState.isServices,
  };

  const result = getRequirements(cellState);
  const tObj = TYPES.find((x) => x.id === typeId)!;
  const reqDocs = result.docs.filter((d) => d.required).length;

  return {
    invalid: false,
    reqDocs,
    totalDocs: result.docs.length,
    riskPct: tObj.risk,
    warnings: result.warnings.length,
    errors: result.errors.length,
    hasJA: result.docs.some((d) => d.name.includes('J&A') && d.required),
    hasDF: result.docs.some((d) => d.name.includes('D&F') && d.required),
    timeMin: result.timeMin,
    timeMax: result.timeMax,
    isCR: result.isCR,
    isLOE: result.isLOE,
    competition: result.competition,
    pmr: result.pmr,
    docs: result.docs,
    compliance: result.compliance,
    allWarnings: result.warnings,
  };
}

export function cellColor(reqDocs: number): CellColor {
  if (reqDocs <= 3)
    return { bg: 'rgba(34,197,94,0.12)', border: 'rgba(34,197,94,0.3)', text: '#22c55e' };
  if (reqDocs <= 6)
    return { bg: 'rgba(234,179,8,0.12)', border: 'rgba(234,179,8,0.3)', text: '#eab308' };
  if (reqDocs <= 9)
    return { bg: 'rgba(249,115,22,0.12)', border: 'rgba(249,115,22,0.3)', text: '#f97316' };
  return { bg: 'rgba(239,68,68,0.12)', border: 'rgba(239,68,68,0.3)', text: '#ef4444' };
}

// ============================================================
// SUMMARY GENERATION (for "Apply to Chat")
// ============================================================

export function generateSummary(s: MatrixState): string {
  const r = getRequirements(s);
  const v = s.dollarValue;
  const mObj = METHODS.find((x) => x.id === s.method)!;
  const tObj = TYPES.find((x) => x.id === s.type)!;
  const reqDocs = r.docs.filter((d) => d.required).map((d) => d.name);
  const reqCompliance = r.compliance.filter((c) => c.status === 'req').map((c) => c.name);

  const parts: string[] = [];
  parts.push(
    `Acquisition: ${mObj.label} (FAR ${mObj.far}), ${tObj.label}, estimated ${fmtDollar(v)}.`,
  );

  const flags: string[] = [];
  if (s.isIT) flags.push('IT requirement');
  if (s.isSB) flags.push('small business awardee');
  if (s.isRD) flags.push('R&D effort');
  if (s.isHS) flags.push('human subjects');
  if (s.isServices) flags.push('services');
  if (flags.length) parts.push('Factors: ' + flags.join(', ') + '.');

  parts.push(`\nRequired documents (${reqDocs.length}): ${reqDocs.join(', ')}.`);
  parts.push(
    `\nApproval: AP \u2014 ${v > 350000 ? apApproval(v) : 'Not required below SAT'}. J&A \u2014 ${jaApproval(v)}.`,
  );
  parts.push(`\nCompetition: ${r.competition}`);
  parts.push(`\nCompliance: ${reqCompliance.join(', ')}.`);
  parts.push(`\nPMR Checklist: ${r.pmr}.`);
  parts.push(`\nTimeline estimate: ${r.timeMin}\u2013${r.timeMax} weeks.`);

  if (r.warnings.length) {
    parts.push(`\nWarnings: ${r.warnings.join(' ')}`);
  }

  return parts.join('\n');
}

// ============================================================
// TAB 3: CONTRACT TYPE FACTORS (13 FAR 16.104 factors)
// ============================================================

export const CONTRACT_TYPE_FACTORS: ContractTypeFactor[] = [
  {
    id: 'commerciality',
    name: 'Commerciality',
    farRef: 'FAR 12.207',
    options: [
      { id: 'commercial', label: 'Commercial item', weights: { fp: 10, cr: -8, loe: -2 } },
      { id: 'semi-commercial', label: 'Modified commercial', weights: { fp: 5, cr: -2, loe: 2 } },
      {
        id: 'non-commercial',
        label: 'Non-commercial / custom',
        weights: { fp: -2, cr: 5, loe: 3 },
      },
    ],
  },
  {
    id: 'price-competition',
    name: 'Price Competition',
    farRef: 'FAR 15.403-1',
    options: [
      { id: 'adequate', label: 'Adequate competition', weights: { fp: 8, cr: -3, loe: 0 } },
      { id: 'limited', label: 'Limited competition', weights: { fp: 2, cr: 3, loe: 2 } },
      {
        id: 'sole-source',
        label: 'Sole source / no competition',
        weights: { fp: -3, cr: 5, loe: 4 },
      },
    ],
  },
  {
    id: 'price-analysis',
    name: 'Price Analysis Capability',
    farRef: 'FAR 15.404-1',
    options: [
      {
        id: 'strong',
        label: 'Catalog / market prices available',
        weights: { fp: 8, cr: -5, loe: -2 },
      },
      {
        id: 'moderate',
        label: 'Some comparable pricing exists',
        weights: { fp: 3, cr: 1, loe: 1 },
      },
      { id: 'weak', label: 'No comparable pricing available', weights: { fp: -3, cr: 5, loe: 3 } },
    ],
  },
  {
    id: 'cost-analysis',
    name: 'Cost Analysis Available',
    farRef: 'FAR 15.404-1(c)',
    options: [
      {
        id: 'yes',
        label: 'Certified cost/pricing data available',
        weights: { fp: 2, cr: 6, loe: 0 },
      },
      { id: 'partial', label: 'Some cost data, not certified', weights: { fp: 3, cr: 2, loe: 2 } },
      { id: 'no', label: 'No cost data available', weights: { fp: 5, cr: -8, loe: 3 } },
    ],
  },
  {
    id: 'type-complexity',
    name: 'Type & Complexity',
    farRef: 'FAR 16.104(a)',
    options: [
      { id: 'well-defined', label: 'Well-defined / routine', weights: { fp: 8, cr: -3, loe: 0 } },
      { id: 'moderate', label: 'Moderately complex', weights: { fp: 2, cr: 3, loe: 3 } },
      { id: 'high', label: 'High complexity / R&D', weights: { fp: -5, cr: 8, loe: 4 } },
    ],
  },
  {
    id: 'combining',
    name: 'Combining Contract Types',
    farRef: 'FAR 16.104(b)',
    options: [
      { id: 'single', label: 'Single type appropriate', weights: { fp: 2, cr: 2, loe: 2 } },
      { id: 'hybrid', label: 'Hybrid type needed', weights: { fp: 0, cr: 0, loe: 5 } },
    ],
  },
  {
    id: 'urgency',
    name: 'Urgency',
    farRef: 'FAR 16.104(c)',
    options: [
      { id: 'normal', label: 'Normal timeline', weights: { fp: 3, cr: 2, loe: 0 } },
      { id: 'urgent', label: 'Urgent requirement', weights: { fp: 5, cr: -2, loe: 6 } },
      { id: 'crisis', label: 'Emergency / crisis', weights: { fp: 8, cr: -5, loe: 8 } },
    ],
  },
  {
    id: 'period',
    name: 'Period of Performance',
    farRef: 'FAR 16.104(d)',
    options: [
      { id: 'short', label: 'Short (\u22641 year)', weights: { fp: 6, cr: -2, loe: 3 } },
      { id: 'medium', label: 'Medium (1\u20133 years)', weights: { fp: 2, cr: 3, loe: 2 } },
      { id: 'long', label: 'Long (3+ years)', weights: { fp: -3, cr: 6, loe: 0 } },
    ],
  },
  {
    id: 'contractor-capability',
    name: 'Contractor Capability',
    farRef: 'FAR 16.104(e)',
    options: [
      { id: 'proven', label: 'Proven / established', weights: { fp: 5, cr: 2, loe: 0 } },
      { id: 'moderate', label: 'Moderate experience', weights: { fp: 2, cr: 3, loe: 2 } },
      { id: 'new', label: 'New / unproven', weights: { fp: -3, cr: 5, loe: 4 } },
    ],
  },
  {
    id: 'accounting-system',
    name: 'Accounting System Adequacy',
    farRef: 'FAR 16.104(f)',
    options: [
      { id: 'adequate', label: 'Adequate system', weights: { fp: 2, cr: 6, loe: 2 } },
      { id: 'partial', label: 'Partially adequate', weights: { fp: 3, cr: -2, loe: 3 } },
      {
        id: 'inadequate',
        label: 'Inadequate / not evaluated',
        weights: { fp: 6, cr: -10, loe: 5 },
      },
    ],
  },
  {
    id: 'concurrent-contracts',
    name: 'Concurrent Contracts',
    farRef: 'FAR 16.104(g)',
    options: [
      { id: 'none', label: 'No concurrent contracts', weights: { fp: 2, cr: 2, loe: 2 } },
      { id: 'some', label: 'Some concurrent contracts', weights: { fp: 0, cr: 3, loe: 3 } },
      { id: 'many', label: 'Extensive concurrent work', weights: { fp: -2, cr: 4, loe: 4 } },
    ],
  },
  {
    id: 'subcontracting',
    name: 'Subcontracting Extent',
    farRef: 'FAR 16.104(h)',
    options: [
      { id: 'minimal', label: 'Minimal subcontracting', weights: { fp: 4, cr: 0, loe: 2 } },
      { id: 'moderate', label: 'Moderate subcontracting', weights: { fp: 1, cr: 3, loe: 2 } },
      { id: 'extensive', label: 'Extensive subcontracting', weights: { fp: -2, cr: 5, loe: 3 } },
    ],
  },
  {
    id: 'acquisition-history',
    name: 'Acquisition History',
    farRef: 'FAR 16.104(i)',
    options: [
      { id: 'first-time', label: 'First-time buy', weights: { fp: -3, cr: 5, loe: 4 } },
      { id: 'prior-fp', label: 'Prior buy was fixed-price', weights: { fp: 8, cr: -3, loe: 0 } },
      { id: 'prior-cr', label: 'Prior buy was cost-reimb', weights: { fp: -2, cr: 6, loe: 2 } },
      { id: 'prior-tm', label: 'Prior buy was T&M/LH', weights: { fp: 0, cr: 2, loe: 7 } },
    ],
  },
];

// ============================================================
// TAB 3: SCORING ENGINE
// ============================================================

/** Map each TYPES entry to a category for scoring */
const TYPE_CATEGORY_MAP: Record<string, 'fp' | 'cr' | 'loe'> = {};
for (const t of TYPES) {
  TYPE_CATEGORY_MAP[t.id] = t.category;
}

export function recommendContractType(answers: FactorAnswer[]): RankedRecommendation[] {
  // Accumulate raw scores per category
  const catScores = { fp: 0, cr: 0, loe: 0 };
  const catMax = { fp: 0, cr: 0, loe: 0 };
  const reasoning: Record<string, string[]> = {};
  let crBlocked = false;

  for (const t of TYPES) {
    reasoning[t.id] = [];
  }

  for (const answer of answers) {
    const factor = CONTRACT_TYPE_FACTORS.find((f) => f.id === answer.factorId);
    if (!factor) continue;
    const option = factor.options.find((o) => o.id === answer.optionId);
    if (!option) continue;

    catScores.fp += option.weights.fp;
    catScores.cr += option.weights.cr;
    catScores.loe += option.weights.loe;

    // Track max possible positive score per category
    const maxFP = Math.max(...factor.options.map((o) => o.weights.fp));
    const maxCR = Math.max(...factor.options.map((o) => o.weights.cr));
    const maxLOE = Math.max(...factor.options.map((o) => o.weights.loe));
    catMax.fp += maxFP;
    catMax.cr += maxCR;
    catMax.loe += maxLOE;

    // Detect if CR is blocked (inadequate accounting system)
    if (factor.id === 'accounting-system' && option.id === 'inadequate') {
      crBlocked = true;
    }

    // Generate reasoning snippets
    for (const t of TYPES) {
      const cat = TYPE_CATEGORY_MAP[t.id];
      const w = option.weights[cat];
      if (Math.abs(w) >= 5) {
        reasoning[t.id].push(`${factor.name}: ${w > 0 ? '+' : ''}${w} (${option.label})`);
      }
    }
  }

  // Score each type based on its category score + type-specific adjustments
  return TYPES.map((t) => {
    const cat = TYPE_CATEGORY_MAP[t.id];
    const rawScore = catScores[cat];
    const maxScore = catMax[cat] || 1;
    const blocked = cat === 'cr' && crBlocked;

    // Normalize to 0-100
    const normalizedScore = Math.max(0, Math.round(((rawScore + maxScore) / (2 * maxScore)) * 100));

    return {
      typeId: t.id,
      label: t.label,
      score: blocked ? 0 : normalizedScore,
      maxScore: 100,
      reasoning: reasoning[t.id],
      blocked,
    };
  }).sort((a, b) => b.score - a.score);
}
