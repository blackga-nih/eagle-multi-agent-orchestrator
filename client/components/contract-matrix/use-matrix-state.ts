'use client';

import { useState, useMemo, useCallback } from 'react';
import type {
  MatrixState,
  Requirements,
  FactorAnswer,
  RankedRecommendation,
  MatrixTab,
} from './matrix-types';
import {
  DEFAULT_STATE,
  PRESETS,
  METHODS,
  TYPES,
  isTypeDisabled,
  getRequirements,
  generateSummary,
  recommendContractType,
} from './matrix-data';

export function useMatrixState(initialMethod?: string, initialType?: string) {
  const [state, setState] = useState<MatrixState>(() => {
    const s = { ...DEFAULT_STATE };
    if (initialMethod) {
      const m = METHODS.find(
        (x) =>
          x.id === initialMethod || x.label.toLowerCase().includes(initialMethod.toLowerCase()),
      );
      if (m) s.method = m.id;
    }
    if (initialType) {
      const t = TYPES.find(
        (x) => x.id === initialType || x.label.toLowerCase().includes(initialType.toLowerCase()),
      );
      if (t && !isTypeDisabled(s.method, t.id)) s.type = t.id;
    }
    return s;
  });

  const [activeTab, setActiveTab] = useState<MatrixTab>('explorer');
  const [factorAnswers, setFactorAnswers] = useState<FactorAnswer[]>([]);

  const setMethod = useCallback((id: string) => {
    setState((prev) => {
      const next = { ...prev, method: id };
      // If current type is disabled for new method, reset to ffp
      if (isTypeDisabled(id, prev.type)) {
        next.type = 'ffp';
      }
      return next;
    });
  }, []);

  const setType = useCallback((id: string) => {
    setState((prev) => {
      if (isTypeDisabled(prev.method, id)) return prev;
      return { ...prev, type: id };
    });
  }, []);

  const setDollarValue = useCallback((v: number) => {
    setState((prev) => ({ ...prev, dollarValue: v }));
  }, []);

  const toggleFlag = useCallback(
    (key: keyof Pick<MatrixState, 'isIT' | 'isSB' | 'isRD' | 'isHS' | 'isServices'>) => {
      setState((prev) => ({ ...prev, [key]: !prev[key] }));
    },
    [],
  );

  const applyPreset = useCallback((name: string) => {
    const p = PRESETS[name];
    if (p) setState({ ...p });
  }, []);

  const requirements: Requirements = useMemo(() => getRequirements(state), [state]);

  const recommendations: RankedRecommendation[] = useMemo(
    () => recommendContractType(factorAnswers),
    [factorAnswers],
  );

  const setFactorAnswer = useCallback((factorId: string, optionId: string) => {
    setFactorAnswers((prev) => {
      const filtered = prev.filter((a) => a.factorId !== factorId);
      return [...filtered, { factorId, optionId }];
    });
  }, []);

  const clearFactorAnswers = useCallback(() => {
    setFactorAnswers([]);
  }, []);

  const summary = useMemo(() => generateSummary(state), [state]);

  return {
    state,
    activeTab,
    setActiveTab,
    setMethod,
    setType,
    setDollarValue,
    toggleFlag,
    applyPreset,
    requirements,
    summary,
    // Tab 3
    factorAnswers,
    setFactorAnswer,
    clearFactorAnswers,
    recommendations,
  };
}
