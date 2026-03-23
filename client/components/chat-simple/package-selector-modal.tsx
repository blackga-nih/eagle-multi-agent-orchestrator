'use client';

import { useState, useEffect } from 'react';
import { Package, FileText, Folder, Loader2 } from 'lucide-react';
import Modal from '@/components/ui/modal';
import { UploadResult, listPackages, PackageInfo } from '@/lib/document-api';

interface PackageSelectorModalProps {
    isOpen: boolean;
    onClose: () => void;
    uploadResult: UploadResult | null;
    onAssign: (packageId: string | null, docType: string, title: string) => Promise<void>;
    getToken?: () => Promise<string | null>;
}

const DOC_TYPE_LABELS: Record<string, string> = {
    sow: 'Statement of Work',
    igce: 'Cost Estimate (IGCE)',
    market_research: 'Market Research',
    justification: 'Justification (J&A)',
    acquisition_plan: 'Acquisition Plan',
    unknown: 'Other Document',
};

export default function PackageSelectorModal({
    isOpen,
    onClose,
    uploadResult,
    onAssign,
    getToken,
}: PackageSelectorModalProps) {
    const [packages, setPackages] = useState<PackageInfo[]>([]);
    const [selectedPackageId, setSelectedPackageId] = useState<string | null>(null);
    const [selectedDocType, setSelectedDocType] = useState<string>('sow');
    const [title, setTitle] = useState<string>('');
    const [isLoading, setIsLoading] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch packages when modal opens
    useEffect(() => {
        if (isOpen && uploadResult) {
            setIsLoading(true);
            setError(null);

            // Initialize from classification
            const classification = uploadResult.classification;
            setSelectedDocType(classification?.doc_type || 'sow');
            setTitle(classification?.suggested_title || uploadResult.filename);

            // Pre-select package if in package context
            if (uploadResult.package_context?.package_id) {
                setSelectedPackageId(uploadResult.package_context.package_id);
            } else {
                setSelectedPackageId(null);
            }

            // Fetch available packages
            (async () => {
                try {
                    const token = getToken ? await getToken() : null;
                    const pkgs = await listPackages(token);
                    setPackages(pkgs);
                } catch (err) {
                    setError('Failed to load packages');
                } finally {
                    setIsLoading(false);
                }
            })();
        }
    }, [isOpen, uploadResult, getToken]);

    const handleSubmit = async () => {
        if (!uploadResult) return;

        setIsSubmitting(true);
        setError(null);

        try {
            await onAssign(selectedPackageId, selectedDocType, title);
            onClose();
        } catch (err) {
            setError(err instanceof Error ? err.message : 'Failed to assign document');
        } finally {
            setIsSubmitting(false);
        }
    };

    if (!uploadResult) return null;

    const classification = uploadResult.classification;

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title="Assign Document to Package"
            size="md"
            footer={
                <div className="flex justify-end gap-3">
                    <button
                        onClick={onClose}
                        disabled={isSubmitting}
                        className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
                    >
                        Cancel
                    </button>
                    <button
                        onClick={handleSubmit}
                        disabled={isSubmitting || isLoading}
                        className="px-4 py-2 text-sm bg-[#003366] text-white rounded-lg hover:bg-[#004488] disabled:opacity-50 transition-colors flex items-center gap-2"
                    >
                        {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                        {selectedPackageId ? 'Assign to Package' : 'Save Without Package'}
                    </button>
                </div>
            }
        >
            <div className="space-y-5">
                {/* File info */}
                <div className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                    <FileText className="w-5 h-5 text-blue-500 mt-0.5" />
                    <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-900 truncate">{uploadResult.filename}</p>
                        <p className="text-sm text-gray-500">
                            Classified as: <span className="font-medium text-gray-700">
                                {DOC_TYPE_LABELS[classification?.doc_type || 'unknown']}
                            </span>
                            {classification?.confidence && (
                                <span className="text-gray-400 ml-1">
                                    ({Math.round(classification.confidence * 100)}% confidence)
                                </span>
                            )}
                        </p>
                    </div>
                </div>

                {/* Document type override */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Document Type
                    </label>
                    <select
                        value={selectedDocType}
                        onChange={(e) => setSelectedDocType(e.target.value)}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
                    >
                        {Object.entries(DOC_TYPE_LABELS).map(([value, label]) => (
                            <option key={value} value={value}>{label}</option>
                        ))}
                    </select>
                </div>

                {/* Title */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Document Title
                    </label>
                    <input
                        type="text"
                        value={title}
                        onChange={(e) => setTitle(e.target.value)}
                        maxLength={255}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-500"
                        placeholder="Enter document title"
                    />
                </div>

                {/* Package selection */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Assign to Package
                    </label>

                    {isLoading ? (
                        <div className="flex items-center justify-center py-6">
                            <Loader2 className="w-6 h-6 animate-spin text-gray-400" />
                        </div>
                    ) : (
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                            {/* Workspace option */}
                            <label
                                className={`
                                    flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors
                                    ${selectedPackageId === null
                                        ? 'bg-blue-50 border-2 border-blue-500'
                                        : 'bg-gray-50 border-2 border-transparent hover:bg-gray-100'
                                    }
                                `}
                            >
                                <input
                                    type="radio"
                                    name="package"
                                    checked={selectedPackageId === null}
                                    onChange={() => setSelectedPackageId(null)}
                                    className="sr-only"
                                />
                                <Folder className={`w-5 h-5 ${selectedPackageId === null ? 'text-blue-500' : 'text-gray-400'}`} />
                                <div className="flex-1">
                                    <p className={`font-medium ${selectedPackageId === null ? 'text-blue-700' : 'text-gray-700'}`}>
                                        Save Without Package Assignment
                                    </p>
                                    <p className="text-xs text-gray-500">Keep this document in your personal uploads</p>
                                </div>
                            </label>

                            {/* Package options */}
                            {packages.filter((pkg) => !pkg.status || !['closed', 'archived'].includes(pkg.status)).map((pkg) => (
                                <label
                                    key={pkg.package_id}
                                    className={`
                                        flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors
                                        ${selectedPackageId === pkg.package_id
                                            ? 'bg-blue-50 border-2 border-blue-500'
                                            : 'bg-gray-50 border-2 border-transparent hover:bg-gray-100'
                                        }
                                    `}
                                >
                                    <input
                                        type="radio"
                                        name="package"
                                        checked={selectedPackageId === pkg.package_id}
                                        onChange={() => setSelectedPackageId(pkg.package_id)}
                                        className="sr-only"
                                    />
                                    <Package className={`w-5 h-5 ${selectedPackageId === pkg.package_id ? 'text-blue-500' : 'text-gray-400'}`} />
                                    <div className="flex-1 min-w-0">
                                        <p className={`font-medium truncate ${selectedPackageId === pkg.package_id ? 'text-blue-700' : 'text-gray-700'}`}>
                                            {pkg.package_id}
                                        </p>
                                        <p className="text-xs text-gray-500 truncate">{pkg.title}</p>
                                    </div>
                                    {pkg.status && (
                                        <span className={`text-xs px-2 py-0.5 rounded-full ${
                                            pkg.status === 'drafting' ? 'bg-yellow-100 text-yellow-700' :
                                            pkg.status === 'review' ? 'bg-blue-100 text-blue-700' :
                                            pkg.status === 'approved' ? 'bg-green-100 text-green-700' :
                                            'bg-gray-100 text-gray-600'
                                        }`}>
                                            {pkg.status}
                                        </span>
                                    )}
                                </label>
                            ))}

                            {packages.length === 0 && !isLoading && (
                                <p className="text-sm text-gray-500 text-center py-4">
                                    No packages found. The document will be saved to your workspace.
                                </p>
                            )}
                        </div>
                    )}
                </div>

                {error && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                        {error}
                    </div>
                )}
            </div>
        </Modal>
    );
}
