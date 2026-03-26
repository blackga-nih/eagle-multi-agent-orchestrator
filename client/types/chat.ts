/**
 * Shared Chat Types
 *
 * Common types used across chat interfaces (simple and advanced)
 * and the document viewer.
 */

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  reasoning?: string;
  agent_id?: string;
  agent_name?: string;
}

/** Backward-compatible alias so existing imports of `Message` keep working. */
export type Message = ChatMessage;

export interface DocxPreviewBlock {
  block_id: string;
  kind: 'heading' | 'paragraph' | 'checkbox';
  text: string;
  level?: number | null;
  checked?: boolean | null;
}

export interface XlsxPreviewCell {
  cell_ref: string;
  row: number;
  col: number;
  value: string;
  display_value: string;
  editable: boolean;
  is_formula?: boolean;
}

export interface XlsxPreviewRow {
  row_index: number;
  cells: XlsxPreviewCell[];
}

export interface XlsxPreviewSheet {
  sheet_id: string;
  title: string;
  max_row: number;
  max_col: number;
  truncated?: boolean;
  rows: XlsxPreviewRow[];
}

export interface TemplateProvenance {
  template_id: string;
  template_source: 'user' | 'tenant' | 'global' | 'plugin' | 's3_template' | 'markdown_fallback';
  template_version: number;
  template_name: string;
  doc_type: string;
}

export interface DocumentInfo {
  document_id?: string;
  package_id?: string;
  document_type: string;
  doc_type?: string;
  title: string;
  content?: string;
  file_type?: string;
  content_type?: string;
  is_binary?: boolean;
  download_url?: string | null;
  mode?: 'package' | 'workspace';
  status?: string;
  version?: number;
  word_count?: number;
  generated_at?: string;
  s3_key?: string;
  s3_location?: string;
  source?: string;
  template_path?: string;
  preview_mode?: 'docx_blocks' | 'xlsx_grid' | 'text_fallback' | 'none' | null;
  preview_blocks?: DocxPreviewBlock[];
  preview_sheets?: XlsxPreviewSheet[];
  template_provenance?: TemplateProvenance;
  system_tags?: string[];
  user_tags?: string[];
  far_tags?: string[];
  completeness_pct?: number;
}
