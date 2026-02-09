'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const initialIntakeSchema = z.object({
    requirement: z.string().min(1, 'Please describe what you need'),
    estimatedCost: z.string().min(1, 'Please select an estimated cost range'),
    timeline: z.string().min(1, 'Please provide a timeline'),
});

type InitialIntakeFormData = z.infer<typeof initialIntakeSchema>;

interface InitialIntakeFormProps {
    onSubmit: (data: InitialIntakeFormData) => void;
}

export default function InitialIntakeForm({ onSubmit }: InitialIntakeFormProps) {
    const {
        register,
        handleSubmit,
        formState: { errors },
    } = useForm<InitialIntakeFormData>({
        resolver: zodResolver(initialIntakeSchema),
    });

    return (
        <div className="bg-white border border-blue-200 rounded-lg p-6 shadow-sm">
            <div className="mb-4">
                <h3 className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <span className="w-6 h-6 bg-blue-600 text-white rounded-full flex items-center justify-center text-sm">
                        1
                    </span>
                    Initial Intake Form
                </h3>
                <p className="text-sm text-gray-600 mt-1 ml-8">
                    Let&apos;s gather some basic information about your acquisition request.
                </p>
            </div>

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        What do you need? <span className="text-red-500">*</span>
                    </label>
                    <textarea
                        {...register('requirement')}
                        rows={3}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="Describe the product, service, or equipment you need (e.g., CT Scanner for cardiac imaging)"
                    />
                    {errors.requirement && (
                        <p className="mt-1 text-sm text-red-600">{errors.requirement.message}</p>
                    )}
                </div>

                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        Estimated Cost Range <span className="text-red-500">*</span>
                    </label>
                    <select
                        {...register('estimatedCost')}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                        <option value="">Select cost range...</option>
                        <option value="under-15k">Under $15,000 (Micro-Purchase)</option>
                        <option value="15k-250k">$15,000 - $250,000 (Simplified)</option>
                        <option value="over-250k">Over $250,000 (Negotiated)</option>
                        <option value="unsure">Unsure</option>
                    </select>
                    {errors.estimatedCost && (
                        <p className="mt-1 text-sm text-red-600">{errors.estimatedCost.message}</p>
                    )}
                </div>

                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                        When do you need it by? <span className="text-red-500">*</span>
                    </label>
                    <select
                        {...register('timeline')}
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                        <option value="">Select timeline...</option>
                        <option value="asap">As Soon As Possible</option>
                        <option value="30-days">Within 30 days</option>
                        <option value="60-days">Within 60 days</option>
                        <option value="90-days">Within 90 days</option>
                        <option value="6-months">Within 6 months</option>
                        <option value="1-year">Within 1 year</option>
                        <option value="no-deadline">No specific deadline</option>
                        <option value="unknown">I&apos;m not sure</option>
                    </select>
                    {errors.timeline && (
                        <p className="mt-1 text-sm text-red-600">{errors.timeline.message}</p>
                    )}
                </div>

                <button
                    type="submit"
                    className="w-full px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
                >
                    Continue
                </button>
            </form>
        </div>
    );
}
