'use client';

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

interface InlineFundingFormProps {
    onSubmit: (data: FundingFormData) => void;
    onDismiss: () => void;
}

export default function InlineFundingForm({ onSubmit, onDismiss }: InlineFundingFormProps) {
    const {
        register,
        handleSubmit,
        control,
        formState: { errors },
    } = useForm<FundingFormData>({
        resolver: zodResolver(fundingSchema),
    });

    return (
        <div className="bg-white border-2 border-blue-200 rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-blue-900">📅 Funding & Timeline Form</h3>
                <button
                    onClick={onDismiss}
                    className="text-gray-400 hover:text-gray-600 transition-colors"
                    title="Skip form (continue typing)"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
            <p className="text-xs text-gray-600 mb-4">Fill out this form, or ignore it and continue typing your response.</p>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                        Funding Source *
                    </label>
                    <select
                        {...register('fundingSource')}
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                        <option value="">Select...</option>
                        <option value="Grant">Grant</option>
                        <option value="Appropriated Funds">Appropriated Funds</option>
                        <option value="No-Year Funds">No-Year Funds</option>
                        <option value="Other">Other</option>
                        <option value="Unknown">I&apos;m not sure</option>
                    </select>
                    {errors.fundingSource && (
                        <p className="mt-1 text-xs text-red-600">{errors.fundingSource.message}</p>
                    )}
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                        Grant Number (Optional)
                    </label>
                    <input
                        {...register('grantNumber')}
                        type="text"
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="e.g., 1R01CA123456-01"
                    />
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
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
                                    className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    placeholderText="Select expiration date"
                                />
                                <Calendar className="absolute right-3 top-2 w-4 h-4 text-gray-400 pointer-events-none" />
                            </div>
                        )}
                    />
                    {errors.grantExpiration && (
                        <p className="mt-1 text-xs text-red-600">{errors.grantExpiration.message}</p>
                    )}
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                        Urgency Justification *
                    </label>
                    <textarea
                        {...register('urgencyReason')}
                        rows={3}
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="Explain why this timeline is critical..."
                    />
                    {errors.urgencyReason && (
                        <p className="mt-1 text-xs text-red-600">{errors.urgencyReason.message}</p>
                    )}
                </div>

                <button
                    type="submit"
                    className="w-full px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                >
                    Submit Funding Details
                </button>
            </form>
        </div>
    );
}
