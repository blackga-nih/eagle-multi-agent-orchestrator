'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, FileText, AlertCircle } from 'lucide-react';

export interface ComplianceReadinessGaugeProps {
  score: number;
  missingDocuments?: string[];
  draftDocuments?: string[];
  totalRequired?: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function scoreToColor(score: number): { stroke: string; text: string; bg: string; label: string } {
  if (score >= 80) {
    return { stroke: '#16a34a', text: 'text-green-700', bg: 'bg-green-50', label: 'Ready' };
  }
  if (score >= 50) {
    return { stroke: '#d97706', text: 'text-amber-700', bg: 'bg-amber-50', label: 'Partial' };
  }
  return { stroke: '#dc2626', text: 'text-red-700', bg: 'bg-red-50', label: 'Not Ready' };
}

// SVG circular gauge parameters
const RADIUS = 44;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function CircularGauge({
  score,
  colors,
}: {
  score: number;
  colors: ReturnType<typeof scoreToColor>;
}) {
  const pct = clamp(score, 0, 100) / 100;
  const dashOffset = CIRCUMFERENCE * (1 - pct);

  return (
    <svg
      width="120"
      height="120"
      viewBox="0 0 120 120"
      className="block"
      role="img"
      aria-label={`Compliance readiness score: ${score}%`}
    >
      {/* Track */}
      <circle cx="60" cy="60" r={RADIUS} fill="none" stroke="#e5e7eb" strokeWidth="10" />
      {/* Progress arc — starts at top (−90°) */}
      <circle
        cx="60"
        cy="60"
        r={RADIUS}
        fill="none"
        stroke={colors.stroke}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={CIRCUMFERENCE}
        strokeDashoffset={dashOffset}
        transform="rotate(-90 60 60)"
        style={{ transition: 'stroke-dashoffset 0.6s ease' }}
      />
      {/* Score text */}
      <text
        x="60"
        y="55"
        textAnchor="middle"
        dominantBaseline="middle"
        className="font-bold"
        fill={colors.stroke}
        fontSize="20"
        fontWeight="700"
      >
        {score}%
      </text>
      {/* Label text */}
      <text
        x="60"
        y="74"
        textAnchor="middle"
        dominantBaseline="middle"
        fill="#6b7280"
        fontSize="10"
        fontWeight="500"
      >
        {colors.label}
      </text>
    </svg>
  );
}

export default function ComplianceReadinessGauge({
  score,
  missingDocuments = [],
  draftDocuments = [],
  totalRequired,
}: ComplianceReadinessGaugeProps) {
  const [expanded, setExpanded] = useState(false);
  const safeScore = clamp(Math.round(score), 0, 100);
  const colors = scoreToColor(safeScore);
  const hasDetails = missingDocuments.length > 0 || draftDocuments.length > 0;

  return (
    <div className={`rounded-xl border p-4 ${colors.bg} border-gray-200`}>
      <div className="flex items-center gap-5">
        {/* Circular gauge */}
        <div className="flex-shrink-0">
          <CircularGauge score={safeScore} colors={colors} />
        </div>

        {/* Summary text */}
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Compliance Readiness</h3>

          {totalRequired !== undefined && (
            <p className="text-xs text-gray-500 mb-2">
              {totalRequired - missingDocuments.length} of {totalRequired} documents complete
            </p>
          )}

          <div className="space-y-1">
            {missingDocuments.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-red-700">
                <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{missingDocuments.length} missing</span>
              </div>
            )}
            {draftDocuments.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-amber-700">
                <FileText className="w-3.5 h-3.5 flex-shrink-0" />
                <span>{draftDocuments.length} in draft</span>
              </div>
            )}
          </div>

          {hasDetails && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-xs text-gray-600 hover:text-gray-900 transition-colors"
            >
              {expanded ? (
                <>
                  <ChevronUp className="w-3.5 h-3.5" />
                  Hide details
                </>
              ) : (
                <>
                  <ChevronDown className="w-3.5 h-3.5" />
                  Show details
                </>
              )}
            </button>
          )}
        </div>
      </div>

      {/* Expandable details */}
      {expanded && hasDetails && (
        <div className="mt-3 pt-3 border-t border-gray-200 space-y-3">
          {missingDocuments.length > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-red-600 mb-1.5">
                Missing Documents
              </div>
              <ul className="space-y-1">
                {missingDocuments.map((doc) => (
                  <li key={doc} className="flex items-center gap-1.5 text-xs text-gray-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-400 flex-shrink-0" />
                    {doc}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {draftDocuments.length > 0 && (
            <div>
              <div className="text-[10px] font-bold uppercase tracking-wide text-amber-600 mb-1.5">
                Draft Documents
              </div>
              <ul className="space-y-1">
                {draftDocuments.map((doc) => (
                  <li key={doc} className="flex items-center gap-1.5 text-xs text-gray-700">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 flex-shrink-0" />
                    {doc}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
