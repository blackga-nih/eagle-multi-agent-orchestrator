// Pure TypeScript interfaces for the Contract Requirements Matrix

export interface AcquisitionMethod {
  id: string;
  label: string;
  sub: string;
  far: string;
}

export interface ContractType {
  id: string;
  label: string;
  risk: number;
  category: 'fp' | 'cr' | 'loe';
}

export interface DollarThreshold {
  value: number;
  label: string;
  short: string;
}

export interface MatrixState {
  method: string;
  type: string;
  dollarValue: number;
  isIT: boolean;
  isSB: boolean;
  isRD: boolean;
  isHS: boolean;
  isServices: boolean;
}

export interface DocRequirement {
  name: string;
  required: boolean;
  note: string;
}

export interface ComplianceItem {
  name: string;
  status: 'req' | 'cond' | 'na';
  note: string;
}

export interface ApprovalChainNode {
  label: string;
  min: number;
  max: number;
}

export interface Requirements {
  docs: DocRequirement[];
  triggered: DollarThreshold[];
  notTriggered: DollarThreshold[];
  compliance: ComplianceItem[];
  competition: string;
  pmr: string;
  timeMin: number;
  timeMax: number;
  riskPct: number;
  warnings: string[];
  errors: string[];
  feeCaps: string[];
  isCR: boolean;
  isLOE: boolean;
  isFP: boolean;
}

export interface CellData {
  invalid: boolean;
  reqDocs?: number;
  totalDocs?: number;
  riskPct?: number;
  warnings?: number;
  errors?: number;
  hasJA?: boolean;
  hasDF?: boolean;
  timeMin?: number;
  timeMax?: number;
  isCR?: boolean;
  isLOE?: boolean;
  competition?: string;
  pmr?: string;
  docs?: DocRequirement[];
  compliance?: ComplianceItem[];
  allWarnings?: string[];
}

export interface CellColor {
  bg: string;
  border: string;
  text: string;
}

export interface Preset {
  method: string;
  type: string;
  dollarValue: number;
  isIT: boolean;
  isSB: boolean;
  isRD: boolean;
  isHS: boolean;
  isServices: boolean;
}

// ── Tab 3: Contract Type Selector ──

export interface FactorOption {
  id: string;
  label: string;
  description?: string;
  /** Scoring weights: positive favors, negative penalizes */
  weights: { fp: number; cr: number; loe: number };
}

export interface ContractTypeFactor {
  id: string;
  name: string;
  farRef: string;
  options: FactorOption[];
}

export interface FactorAnswer {
  factorId: string;
  optionId: string;
}

export interface RankedRecommendation {
  typeId: string;
  label: string;
  score: number;
  maxScore: number;
  reasoning: string[];
  blocked: boolean;
}

export type MatrixTab = 'explorer' | 'grid' | 'selector';
