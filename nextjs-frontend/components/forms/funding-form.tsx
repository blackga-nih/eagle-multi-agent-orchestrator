'use client';

import { useState } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import DatePicker from 'react-datepicker';
import { X, Calendar } from 'lucide-react';
import 'react-datepicker/dist/react-datepicker.css';

const fundingSchema = z.object({
    fundingSource: z.string().min(1, 'Funding source is required'),
    grantNumber: z.string().optional(),
    grantExpiration: z.date({
        required_error: 'Grant expiration date is required',
    }),
    fundingAmount: z.string().optional(),
    urgencyReason: z.string().min(1, 'Urgency reason is required'),
});

type FundingFormData = z.infer<typeof fundingSchema>;

interface FundingFormModalProps {
    open: boolean;
    onClose: () => void;
    onSubmit: (data: FundingFormData) => void;
}

export default function FundingFormModal({ open, onClose, onSubmit }: FundingFormModalProps) {
    const {
        register,
        handleSubmit,
        control,
        formState: { errors },
    } = useForm<FundingFormData>({
        resolver: zodResolver(fundingSchema),
    });

    if (!open) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
                <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
                    <h2 className="text-xl font-semibold text-gray-900">Funding & Timeline Details</h2>
                    <button
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-600 transition-colors"
                    >
                        <X className="w-5 h-5" />
                    </button>
                </div>

                <form onSubmit={handleSubmit(onSubmit)} className="p-6 space-y-6">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Funding Source
                        </label>
                        <select
                            {...register('fundingSource')}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        >
                            <option value="">Select funding source...</option>
                            <option value="Grant">Grant</option>
                            <option value="Appropriated Funds">Appropriated Funds</option>
                            <option value="No-Year Funds">No-Year Funds</option>
                            <option value="Other">Other</option>
                        </select>
                        {errors.fundingSource && (
                            <p className="mt-1 text-sm text-red-600">{errors.fundingSource.message}</p>
                        )}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Grant Number (Optional)
                        </label>
                        <input
                            {...register('grantNumber')}
                            type="text"
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="e.g., 1R01CA123456-01"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Grant Expiration Date *
                        </label>
                        <Controller
                            control={control}
                            name="grantExpiration"
                            render={({ field }) => (
                                <div className="relative">
                                    <DatePicker
                                        selected={field.value}
                                        onChange={(date) => field.onChange(date)}
                                        dateFormat="MMMM d, yyyy"
                                        minDate={new Date()}
                                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                        placeholderText="Select expiration date"
                                    />
                                    <Calendar className="absolute right-3 top-2.5 w-5 h-5 text-gray-400 pointer-events-none" />
                                </div>
                            )}
                        />
                        {errors.grantExpiration && (
                            <p className="mt-1 text-sm text-red-600">{errors.grantExpiration.message}</p>
                        )}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Available Funding Amount (Optional)
                        </label>
                        <input
                            {...register('fundingAmount')}
                            type="text"
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="e.g., $500,000"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Urgency Justification *
                        </label>
                        <textarea
                            {...register('urgencyReason')}
                            rows={4}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="Explain why this timeline is critical (e.g., grant expiration, equipment failure, patient safety, research milestone...)"
                        />
                        {errors.urgencyReason && (
                            <p className="mt-1 text-sm text-red-600">{errors.urgencyReason.message}</p>
                        )}
                    </div>

                    <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                        <h4 className="text-sm font-semibold text-yellow-900 mb-1">Important</h4>
                        <p className="text-xs text-yellow-800">
                            A 6-week timeline for equipment over $250K is very aggressive. We&apos;ll work to
                            identify existing contract vehicles (IDIQ, GSA Schedule, BPA) to expedite the
                            process.
                        </p>
                    </div>

                    <div className="flex gap-3 pt-4">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                        >
                            Cancel
                        </button>
                        <button
                            type="submit"
                            className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                        >
                            Submit
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
