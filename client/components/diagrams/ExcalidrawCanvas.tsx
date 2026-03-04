'use client';

/**
 * ExcalidrawCanvas — browser-only Excalidraw wrapper.
 *
 * Must be imported with next/dynamic + ssr:false because Excalidraw
 * uses browser-only APIs that don't exist in the Node SSR environment.
 *
 * We use `any` casts for Excalidraw's internal types to stay compatible
 * with the currently installed @excalidraw/excalidraw version without
 * coupling our public interface to its internal type changes.
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
import React, { useCallback, useImperativeHandle, forwardRef, useState } from 'react';
import { Excalidraw, exportToBlob } from '@excalidraw/excalidraw';

export interface DiagramElement {
  id: string;
  type: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  strokeColor?: string;
  backgroundColor?: string;
  text?: string;
  fontSize?: number;
  [key: string]: unknown;
}

export interface ExcalidrawCanvasRef {
  loadElements: (elements: DiagramElement[]) => void;
  clearCanvas: () => void;
  exportPng: () => Promise<Blob | null>;
  getElementCount: () => number;
  getElementTypes: () => string[];
}

interface ExcalidrawCanvasProps {
  title?: string;
  onElementsChanged?: (count: number) => void;
}

const ExcalidrawCanvas = forwardRef<ExcalidrawCanvasRef, ExcalidrawCanvasProps>(
  ({ title, onElementsChanged }, ref) => {
    const [api, setApi] = useState<any>(null);

    const loadElements = useCallback(
      (elements: DiagramElement[]) => {
        if (!api) return;
        api.updateScene({
          elements,
          appState: { viewBackgroundColor: '#ffffff', name: '' },
        });
        setTimeout(() => api.scrollToContent(), 100);
        onElementsChanged?.(elements.length);
      },
      [api, onElementsChanged],
    );

    const clearCanvas = useCallback(() => {
      if (!api) return;
      api.updateScene({ elements: [], appState: { viewBackgroundColor: '#ffffff', name: '' } });
      onElementsChanged?.(0);
    }, [api, onElementsChanged]);

    const exportPng = useCallback(async (): Promise<Blob | null> => {
      if (!api) return null;
      return exportToBlob({
        elements: api.getSceneElements(),
        appState: api.getAppState(),
        files: api.getFiles(),
        mimeType: 'image/png',
      } as any);
    }, [api]);

    const getElementCount = useCallback(() => {
      return api?.getSceneElements()?.length ?? 0;
    }, [api]);

    const getElementTypes = useCallback(() => {
      return api?.getSceneElements()?.map((e: any) => e.type) ?? [];
    }, [api]);

    useImperativeHandle(ref, () => ({
      loadElements,
      clearCanvas,
      exportPng,
      getElementCount,
      getElementTypes,
    }));

    return (
      <div style={{ width: '100%', height: '100%', position: 'relative' }}>
        {title && (
          <div
            style={{
              position: 'absolute',
              top: 8,
              left: '50%',
              transform: 'translateX(-50%)',
              background: 'rgba(255,255,255,0.9)',
              border: '1px solid #e1e4e8',
              borderRadius: 6,
              padding: '2px 12px',
              fontSize: 12,
              fontWeight: 600,
              color: '#003366',
              zIndex: 10,
              pointerEvents: 'none',
            }}
          >
            {title}
          </div>
        )}
        <Excalidraw
          excalidrawAPI={(a: any) => setApi(a)}
          UIOptions={{ canvasActions: { export: { saveFileToDisk: true } } }}
          initialData={{ appState: { viewBackgroundColor: '#ffffff' } as any }}
        />
      </div>
    );
  },
);

ExcalidrawCanvas.displayName = 'ExcalidrawCanvas';

export default ExcalidrawCanvas;
