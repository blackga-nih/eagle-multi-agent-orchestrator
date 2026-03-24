'use client';

export interface TemplateProvenance {
  template_id: string;
  template_source: string;
  template_version: number;
  template_name: string;
  doc_type: string;
}

export interface TemplateProvenanceBadgeProps {
  provenance?: TemplateProvenance;
}

type SourceKey = 's3_template' | 'plugin' | 'user' | 'tenant' | 'global' | 'markdown_fallback';

const SOURCE_CONFIG: Record<SourceKey, { label: string; classes: string }> = {
  s3_template: { label: 'S3', classes: 'bg-blue-100 text-blue-700' },
  plugin: { label: 'Plugin', classes: 'bg-green-100 text-green-700' },
  user: { label: 'User', classes: 'bg-purple-100 text-purple-700' },
  tenant: { label: 'Tenant', classes: 'bg-indigo-100 text-indigo-700' },
  global: { label: 'Global', classes: 'bg-gray-100 text-gray-700' },
  markdown_fallback: { label: 'Fallback', classes: 'bg-orange-100 text-orange-700' },
};

const DEFAULT_SOURCE_CONFIG = { label: 'Unknown', classes: 'bg-gray-100 text-gray-500' };

export default function TemplateProvenanceBadge({ provenance }: TemplateProvenanceBadgeProps) {
  if (!provenance) {
    return (
      <span className="inline-flex items-center text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-400 font-medium">
        No template
      </span>
    );
  }

  const { template_name, template_version, template_source } = provenance;
  const sourceKey = template_source as SourceKey;
  const config = SOURCE_CONFIG[sourceKey] ?? DEFAULT_SOURCE_CONFIG;

  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium text-gray-700">
      <span className="truncate max-w-[200px]" title={template_name}>
        {template_name}
      </span>
      <span className="text-gray-400 font-normal">v{template_version}</span>
      <span
        className={`inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide ${config.classes}`}
      >
        {config.label}
      </span>
    </span>
  );
}
