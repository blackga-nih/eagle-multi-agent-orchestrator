'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { FileImage, FileText, Loader2, RefreshCw } from 'lucide-react';
import Modal from '@/components/ui/modal';
import { docLabel } from './checklist-panel';
import {
  listPackageAttachments,
  PackageAttachment,
  promotePackageAttachment,
  updatePackageAttachment,
} from '@/lib/document-api';

interface PackageAttachmentsPanelProps {
  packageId: string;
  getToken: () => Promise<string | null>;
  isStreaming?: boolean;
  checklistDocTypes?: string[];
  onChanged?: () => void;
}

const FALLBACK_DOC_TYPES = [
  'sow',
  'igce',
  'market_research',
  'acquisition_plan',
  'justification',
  'son_products',
  'son_services',
];

type AttachmentIntent = 'supporting' | 'checklist' | 'official';

function prettyLabel(value?: string | null): string {
  if (!value) return 'Uncategorized';
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function AttachmentRow({
  attachment,
  onManage,
  disabled,
}: {
  attachment: PackageAttachment;
  onManage: (attachment: PackageAttachment) => void;
  disabled?: boolean;
}) {
  const Icon = attachment.attachment_type === 'document' ? FileText : FileImage;

  return (
    <div className="rounded-lg border border-[#D8DEE6] bg-white px-3 py-2.5">
      <div className="flex items-start gap-2">
        <div className="mt-0.5 rounded-lg bg-gray-100 p-2">
          <Icon className="h-4 w-4 text-gray-600" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-[#003366]">
            {attachment.title || attachment.filename}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[10px] text-gray-500">
            <span className="rounded-full bg-gray-100 px-1.5 py-0.5">
              {prettyLabel(attachment.category)}
            </span>
            <span className="rounded-full bg-gray-100 px-1.5 py-0.5">
              {prettyLabel(attachment.usage)}
            </span>
            {attachment.linked_doc_type && (
              <span className="rounded-full bg-amber-50 px-1.5 py-0.5 text-amber-700">
                Checklist: {docLabel(attachment.linked_doc_type)}
              </span>
            )}
            {attachment.doc_type && (
              <span className="rounded-full bg-blue-50 px-1.5 py-0.5 text-blue-700">
                {prettyLabel(attachment.doc_type)}
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onManage(attachment)}
          className={`shrink-0 rounded-md px-2.5 py-1.5 text-[11px] font-medium transition ${
            disabled
              ? 'cursor-not-allowed bg-gray-100 text-gray-400'
              : attachment.usage === 'official_document'
                ? 'bg-green-100 text-green-700 hover:bg-green-200'
                : 'bg-[#003366] text-white hover:bg-[#004488]'
          }`}
        >
          {attachment.usage === 'official_document' ? 'Official' : 'Manage'}
        </button>
      </div>
    </div>
  );
}

export default function PackageAttachmentsPanel({
  packageId,
  getToken,
  isStreaming = false,
  checklistDocTypes = [],
  onChanged,
}: PackageAttachmentsPanelProps) {
  const [attachments, setAttachments] = useState<PackageAttachment[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAttachment, setSelectedAttachment] = useState<PackageAttachment | null>(null);
  const [intent, setIntent] = useState<AttachmentIntent>('supporting');
  const [targetDocType, setTargetDocType] = useState('sow');
  const [draftTitle, setDraftTitle] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const loadAttachments = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const next = await listPackageAttachments(packageId, token);
      setAttachments(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load attachments');
    } finally {
      setIsLoading(false);
    }
  }, [getToken, packageId]);

  useEffect(() => {
    void loadAttachments();
  }, [loadAttachments]);

  const availableDocTypes = useMemo<string[]>(() => {
    const values = new Set<string>(FALLBACK_DOC_TYPES);
    for (const docType of checklistDocTypes) {
      if (docType) values.add(docType);
    }
    for (const attachment of attachments) {
      if (attachment.linked_doc_type) values.add(attachment.linked_doc_type);
      if (attachment.doc_type) values.add(attachment.doc_type);
    }
    return Array.from(values);
  }, [attachments, checklistDocTypes]);

  const checklistCount = useMemo(
    () => attachments.filter((attachment) => attachment.usage === 'checklist_support').length,
    [attachments],
  );

  const handleManageClick = (attachment: PackageAttachment) => {
    setSelectedAttachment(attachment);
    setTargetDocType(
      attachment.linked_doc_type ||
        attachment.doc_type ||
        availableDocTypes[0] ||
        FALLBACK_DOC_TYPES[0],
    );
    setDraftTitle(attachment.title || attachment.filename);
    if (attachment.usage === 'official_document') {
      setIntent('official');
    } else if (attachment.usage === 'checklist_support' || attachment.linked_doc_type) {
      setIntent('checklist');
    } else {
      setIntent('supporting');
    }
  };

  const closeModal = () => {
    if (isSaving) return;
    setSelectedAttachment(null);
  };

  const handleSave = async () => {
    if (!selectedAttachment) return;
    setIsSaving(true);
    setError(null);
    try {
      const token = await getToken();
      if (intent === 'official') {
        await promotePackageAttachment(
          packageId,
          selectedAttachment.attachment_id,
          {
            doc_type: targetDocType,
            title: draftTitle,
            set_as_official: true,
          },
          token,
        );
      } else {
        await updatePackageAttachment(
          packageId,
          selectedAttachment.attachment_id,
          {
            title: draftTitle,
            usage: intent === 'checklist' ? 'checklist_support' : 'reference',
            linked_doc_type: intent === 'checklist' ? targetDocType : null,
          },
          token,
        );
      }
      setSelectedAttachment(null);
      await loadAttachments();
      onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update attachment');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="mt-4">
      <div className="mb-2 flex items-center justify-between">
        <div>
          <h4 className="text-[10px] font-medium uppercase tracking-wider text-gray-400">
            Package Attachments
            {attachments.length > 0 && (
              <span className="ml-1.5 rounded-full bg-gray-200 px-1.5 py-0.5 text-[9px] font-bold text-gray-600">
                {attachments.length}
              </span>
            )}
          </h4>
          {attachments.length > 0 && (
            <p className="mt-0.5 text-[10px] text-gray-400">
              {checklistCount} linked to checklist items
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => void loadAttachments()}
          className="rounded p-1 text-gray-400 transition hover:text-gray-600"
          title="Refresh attachments"
        >
          <RefreshCw className={`h-3 w-3 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-md border border-red-200 bg-red-50 px-2.5 py-2 text-[11px] text-red-700">
          {error}
        </div>
      )}

      {isLoading && attachments.length === 0 && (
        <div className="py-4 text-center text-[11px] text-gray-400">Loading attachments...</div>
      )}

      {!isLoading && attachments.length === 0 && (
        <div className="rounded-lg border border-dashed border-[#D8DEE6] bg-gray-50 px-3 py-4 text-center">
          <p className="text-xs text-gray-500">No package attachments yet.</p>
          <p className="mt-1 text-[10px] text-gray-400">
            Upload requirements docs, prior SOWs, IGCEs, or screenshots into the active package.
          </p>
        </div>
      )}

      {attachments.length > 0 && (
        <div className="space-y-2">
          {attachments.map((attachment) => (
            <AttachmentRow
              key={attachment.attachment_id}
              attachment={attachment}
              onManage={handleManageClick}
              disabled={isStreaming}
            />
          ))}
        </div>
      )}

      <Modal
        isOpen={!!selectedAttachment}
        onClose={closeModal}
        title="Manage Attachment"
        size="md"
        footer={
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={closeModal}
              disabled={isSaving}
              className="rounded-lg px-4 py-2 text-sm text-gray-600 transition-colors hover:bg-gray-100 hover:text-gray-900"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={isSaving}
              className="flex items-center gap-2 rounded-lg bg-[#003366] px-4 py-2 text-sm text-white transition-colors hover:bg-[#004488] disabled:opacity-50"
            >
              {isSaving && <Loader2 className="h-4 w-4 animate-spin" />}
              Save Attachment Intent
            </button>
          </div>
        }
      >
        {selectedAttachment && (
          <div className="space-y-4">
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="truncate text-sm font-semibold text-gray-900">
                {selectedAttachment.title || selectedAttachment.filename}
              </p>
              <p className="mt-1 text-xs text-gray-500">
                Choose how this uploaded file should behave in the package workflow.
              </p>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">Attachment Title</label>
              <input
                type="text"
                value={draftTitle}
                onChange={(e) => setDraftTitle(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
                maxLength={255}
              />
            </div>

            <div>
              <p className="mb-2 block text-sm font-medium text-gray-700">Intent</p>
              <div className="space-y-2">
                <label className="flex items-start gap-3 rounded-lg border border-gray-200 px-3 py-3">
                  <input
                    type="radio"
                    name="attachment-intent"
                    checked={intent === 'supporting'}
                    onChange={() => setIntent('supporting')}
                    className="mt-0.5"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Supporting document</p>
                    <p className="mt-1 text-xs text-gray-500">
                      Keep this as package context and include it in exports, without tying it to a specific checklist item.
                    </p>
                  </div>
                </label>
                <label className="flex items-start gap-3 rounded-lg border border-gray-200 px-3 py-3">
                  <input
                    type="radio"
                    name="attachment-intent"
                    checked={intent === 'checklist'}
                    onChange={() => setIntent('checklist')}
                    className="mt-0.5"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Supports checklist item</p>
                    <p className="mt-1 text-xs text-gray-500">
                      Link this upload to a package checklist artifact without replacing the official document.
                    </p>
                  </div>
                </label>
                <label className="flex items-start gap-3 rounded-lg border border-gray-200 px-3 py-3">
                  <input
                    type="radio"
                    name="attachment-intent"
                    checked={intent === 'official'}
                    onChange={() => setIntent('official')}
                    className="mt-0.5"
                  />
                  <div>
                    <p className="text-sm font-medium text-gray-800">Use as official checklist document</p>
                    <p className="mt-1 text-xs text-gray-500">
                      Promote this upload into the canonical package document flow for the selected checklist item.
                    </p>
                  </div>
                </label>
              </div>
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-700">Checklist Item</label>
              <select
                value={targetDocType}
                onChange={(e) => setTargetDocType(e.target.value)}
                disabled={intent === 'supporting'}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              >
                {availableDocTypes.map((value) => (
                  <option key={value} value={value}>
                    {docLabel(value)}
                  </option>
                ))}
              </select>
            </div>

            <div className="rounded-lg border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
              {intent === 'official'
                ? 'Promoting does not delete the uploaded attachment. It creates a canonical package document and keeps the original upload for reference.'
                : intent === 'checklist'
                  ? 'Checklist support keeps this file attached to the package and links it to a checklist item for context and export.'
                  : 'Supporting documents remain general package context and can still be used during generation and ZIP export.'}
            </div>

            {selectedAttachment.usage === 'official_document' && intent !== 'official' && (
              <div className="rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                This upload has already been promoted once. Changing its attachment intent here will not delete the canonical package document that was created from it.
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
