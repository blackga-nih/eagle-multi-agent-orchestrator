'use client';

import React, { useState, useCallback, useMemo, useRef, useEffect, useImperativeHandle, forwardRef } from 'react';
import { Calculator, ChevronLeft, ChevronRight } from 'lucide-react';
import { XlsxPreviewSheet, XlsxPreviewCell } from '@/types/chat';

export interface PendingCellEdit {
  sheetId: string;
  cellRef: string;
  value: string;
}

export interface SpreadsheetPreviewHandle {
  /** Commits any currently editing cell. Returns the edit info for immediate use (avoids async state race). */
  commitPendingEdit: () => PendingCellEdit | null;
}

interface SpreadsheetPreviewProps {
  sheets: XlsxPreviewSheet[];
  activeSheetId: string | null;
  onActiveSheetChange: (sheetId: string) => void;
  isEditing: boolean;
  onCellChange?: (sheetId: string, cellRef: string, value: string) => void;
}

/**
 * Compact Excel-like spreadsheet viewer with inline editing.
 */
export const SpreadsheetPreview = forwardRef<SpreadsheetPreviewHandle, SpreadsheetPreviewProps>(
  function SpreadsheetPreview(
    { sheets, activeSheetId, onActiveSheetChange, isEditing, onCellChange },
    ref
  ) {
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const tabsContainerRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);
  const onCellChangeRef = useRef(onCellChange);
  onCellChangeRef.current = onCellChange;

  const activeSheet = useMemo(
    () => sheets.find((s) => s.sheet_id === activeSheetId) || sheets[0] || null,
    [sheets, activeSheetId]
  );

  useEffect(() => {
    const container = tabsContainerRef.current;
    if (!container) return;
    const checkOverflow = () => {
      setShowLeftArrow(container.scrollLeft > 0);
      setShowRightArrow(container.scrollLeft < container.scrollWidth - container.clientWidth - 1);
    };
    checkOverflow();
    container.addEventListener('scroll', checkOverflow);
    window.addEventListener('resize', checkOverflow);
    return () => {
      container.removeEventListener('scroll', checkOverflow);
      window.removeEventListener('resize', checkOverflow);
    };
  }, [sheets]);

  const scrollTabs = (direction: 'left' | 'right') => {
    tabsContainerRef.current?.scrollBy({ left: direction === 'left' ? -150 : 150, behavior: 'smooth' });
  };

  const getColumnLabel = useCallback((colIndex: number): string => {
    let label = '';
    let n = colIndex;
    while (n >= 0) {
      label = String.fromCharCode(65 + (n % 26)) + label;
      n = Math.floor(n / 26) - 1;
    }
    return label;
  }, []);

  const parseColumn = useCallback((cellRef: string): number => {
    const match = cellRef.match(/^([A-Z]+)/);
    if (!match) return 0;
    const letters = match[1];
    let col = 0;
    for (let i = 0; i < letters.length; i++) {
      col = col * 26 + (letters.charCodeAt(i) - 64);
    }
    return col - 1;
  }, []);

  const gridData = useMemo(() => {
    if (!activeSheet) return { grid: [], maxCol: 0, maxRow: 0, colWidths: [] };

    const cellMap = new Map<string, XlsxPreviewCell>();
    let maxRow = 0;
    let maxCol = 0;

    for (const row of activeSheet.rows) {
      for (const cell of row.cells) {
        cellMap.set(cell.cell_ref, cell);
        maxRow = Math.max(maxRow, cell.row);
        const colIdx = parseColumn(cell.cell_ref);
        maxCol = Math.max(maxCol, colIdx + 1);
      }
    }

    maxRow = Math.max(maxRow, activeSheet.max_row || 0);
    maxCol = Math.max(maxCol, activeSheet.max_col || 0);

    const grid: (XlsxPreviewCell | null)[][] = [];
    for (let r = 1; r <= maxRow; r++) {
      const rowCells: (XlsxPreviewCell | null)[] = [];
      for (let c = 0; c < maxCol; c++) {
        const ref = `${getColumnLabel(c)}${r}`;
        rowCells.push(cellMap.get(ref) || null);
      }
      grid.push(rowCells);
    }

    // Calculate column widths based on content (sample first 20 rows)
    const colWidths: number[] = [];
    const MIN_WIDTH = 50;
    const CHAR_WIDTH = 7; // approximate px per character

    for (let c = 0; c < maxCol; c++) {
      let maxLen = 0;
      let isNumeric = true;
      for (let r = 0; r < Math.min(grid.length, 20); r++) {
        const cell = grid[r]?.[c];
        const text = cell?.display_value || '';
        maxLen = Math.max(maxLen, text.length);
        // Check if column contains mostly numbers
        if (text && !/^[\d,.$%\-\s]*$/.test(text)) {
          isNumeric = false;
        }
      }
      // Column A (labels) gets more width; numeric columns stay narrow
      const maxWidth = c === 0 ? 180 : isNumeric ? 80 : 120;
      const calcWidth = Math.min(maxWidth, Math.max(MIN_WIDTH, maxLen * CHAR_WIDTH + 12));
      colWidths.push(calcWidth);
    }

    return { grid, maxCol, maxRow, colWidths };
  }, [activeSheet, getColumnLabel, parseColumn]);

  const handleCellClick = useCallback(
    (cell: XlsxPreviewCell | null, sheetId: string, cellRef: string) => {
      if (!isEditing || !cell || !cell.editable || cell.is_formula) return;
      // Use | as separator since sheet_id contains colons (e.g., "0:igce")
      setEditingCell(`${sheetId}|${cellRef}`);
      setEditValue(cell.value);
      setTimeout(() => inputRef.current?.focus(), 0);
    },
    [isEditing]
  );

  const handleCellBlur = useCallback(() => {
    if (!editingCell || !onCellChangeRef.current) return;
    // Split on | to correctly separate sheet_id (may contain :) from cell_ref
    const sepIndex = editingCell.lastIndexOf('|');
    if (sepIndex === -1) return;
    const sheetId = editingCell.slice(0, sepIndex);
    const cellRef = editingCell.slice(sepIndex + 1);
    onCellChangeRef.current(sheetId, cellRef, editValue);
    setEditingCell(null);
    setEditValue('');
  }, [editingCell, editValue]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleCellBlur();
      } else if (e.key === 'Escape') {
        setEditingCell(null);
        setEditValue('');
      }
    },
    [handleCellBlur]
  );

  // Expose commitPendingEdit so parent can commit before save
  useImperativeHandle(ref, () => ({
    commitPendingEdit: (): PendingCellEdit | null => {
      if (editingCell && onCellChangeRef.current) {
        // Split on | to correctly separate sheet_id from cell_ref
        const sepIndex = editingCell.lastIndexOf('|');
        if (sepIndex === -1) return null;
        const sheetId = editingCell.slice(0, sepIndex);
        const cellRef = editingCell.slice(sepIndex + 1);
        const value = editValue;
        onCellChangeRef.current(sheetId, cellRef, value);
        setEditingCell(null);
        setEditValue('');
        // Return the edit for immediate use (avoids async state race condition)
        return { sheetId, cellRef, value };
      }
      return null;
    },
  }), [editingCell, editValue]);

  if (!sheets.length) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        No spreadsheet data available
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full border border-gray-300 bg-white text-xs">
      {/* Sheet tabs */}
      <div className="flex items-center bg-gray-100 border-b border-gray-300 h-7 flex-shrink-0">
        {showLeftArrow && (
          <button onClick={() => scrollTabs('left')} className="px-1 text-gray-500 hover:text-gray-700">
            <ChevronLeft className="w-3 h-3" />
          </button>
        )}
        <div
          ref={tabsContainerRef}
          className="flex-1 flex overflow-x-auto"
          style={{ scrollbarWidth: 'none' }}
        >
          {sheets.map((sheet) => (
            <button
              key={sheet.sheet_id}
              onClick={() => onActiveSheetChange(sheet.sheet_id)}
              className={`px-3 py-1 text-xs border-r border-gray-300 whitespace-nowrap ${
                sheet.sheet_id === activeSheetId
                  ? 'bg-white font-medium text-gray-900 border-b-2 border-b-blue-500'
                  : 'text-gray-600 hover:bg-gray-50'
              }`}
            >
              {sheet.title}
            </button>
          ))}
        </div>
        {showRightArrow && (
          <button onClick={() => scrollTabs('right')} className="px-1 text-gray-500 hover:text-gray-700">
            <ChevronRight className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-auto">
        {activeSheet && gridData.grid.length > 0 && (
          <table className="border-collapse" style={{ tableLayout: 'fixed' }}>
            <colgroup>
              <col style={{ width: 32 }} />
              {gridData.colWidths.map((w, i) => (
                <col key={i} style={{ width: w }} />
              ))}
            </colgroup>
            <thead className="sticky top-0 z-10">
              <tr className="bg-gray-100">
                <th className="border-b border-r border-gray-300 text-[10px] text-gray-500 font-normal sticky left-0 bg-gray-100 z-20" />
                {Array.from({ length: gridData.maxCol }, (_, i) => (
                  <th
                    key={i}
                    className="border-b border-r border-gray-300 text-[10px] text-gray-600 font-medium py-0.5 px-1 text-center"
                  >
                    {getColumnLabel(i)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {gridData.grid.map((rowCells, rowIndex) => {
                const rowNum = rowIndex + 1;
                return (
                  <tr key={rowIndex} className="hover:bg-blue-50/30">
                    <td className="bg-gray-50 border-b border-r border-gray-200 text-[10px] text-gray-500 py-0.5 px-1 text-center sticky left-0 z-10 font-normal">
                      {rowNum}
                    </td>
                    {rowCells.map((cell, colIndex) => {
                      const cellRef = `${getColumnLabel(colIndex)}${rowNum}`;
                      const cellKey = activeSheet ? `${activeSheet.sheet_id}|${cellRef}` : '';
                      const isEditingThis = editingCell === cellKey;
                      const isFormula = cell?.is_formula;
                      const isEditable = isEditing && cell?.editable && !isFormula;

                      return (
                        <td
                          key={colIndex}
                          onClick={() => handleCellClick(cell, activeSheet.sheet_id, cellRef)}
                          className={`border-b border-r border-gray-200 p-0 overflow-hidden ${
                            isFormula ? 'bg-blue-50' : isEditable ? 'cursor-pointer hover:bg-yellow-50' : ''
                          }`}
                        >
                          {isEditingThis ? (
                            <input
                              ref={inputRef}
                              type="text"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={handleCellBlur}
                              onKeyDown={handleKeyDown}
                              className="w-full h-full px-1 py-0.5 text-xs border-2 border-blue-500 outline-none"
                            />
                          ) : (
                            <div className="px-1 py-0.5 min-h-[18px] flex items-center overflow-hidden">
                              {isFormula && cell?.display_value && (
                                <Calculator className="w-2.5 h-2.5 text-blue-400 mr-0.5 flex-shrink-0" />
                              )}
                              <span className={`truncate ${isFormula ? 'text-blue-700' : 'text-gray-900'}`} title={cell?.display_value || ''}>
                                {cell?.display_value || ''}
                              </span>
                            </div>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Compact footer */}
      <div className="flex items-center justify-between px-2 py-1 bg-gray-50 border-t border-gray-300 text-[10px] text-gray-500 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <Calculator className="w-2.5 h-2.5 text-blue-400" />
            Formula
          </span>
          {isEditing && (
            <span className="text-green-600 font-medium flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-green-500 rounded-full" />
              Edit mode - click cells to modify
            </span>
          )}
        </div>
        <span>{gridData.maxRow} rows &times; {gridData.maxCol} columns</span>
      </div>
    </div>
  );
});

export default SpreadsheetPreview;
