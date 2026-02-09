'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { X } from 'lucide-react';

const equipmentSchema = z.object({
    equipmentType: z.string().min(1, 'Equipment type is required'),
    sliceCount: z.string().min(1, 'Please select specifications'),
    condition: z.enum(['new', 'refurbished', 'either', 'unknown']),
    manufacturer: z.string().optional(),
    clinicalUse: z.string().optional(),
});

type EquipmentFormData = z.infer<typeof equipmentSchema>;

interface InlineEquipmentFormProps {
    onSubmit: (data: EquipmentFormData) => void;
    onDismiss: () => void;
}

export default function InlineEquipmentForm({ onSubmit, onDismiss }: InlineEquipmentFormProps) {
    const {
        register,
        handleSubmit,
        formState: { errors },
    } = useForm<EquipmentFormData>({
        resolver: zodResolver(equipmentSchema),
        defaultValues: {
            equipmentType: 'CT Scanner',
            condition: 'new',
        },
    });

    return (
        <div className="bg-white border-2 border-blue-200 rounded-lg p-4 shadow-sm">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-blue-900">📄 Equipment Details Form</h3>
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
                        Equipment Type
                    </label>
                    <input
                        {...register('equipmentType')}
                        type="text"
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="e.g., CT Scanner, MRI, X-Ray"
                    />
                    {errors.equipmentType && (
                        <p className="mt-1 text-xs text-red-600">{errors.equipmentType.message}</p>
                    )}
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                        Specifications
                    </label>
                    <select
                        {...register('sliceCount')}
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                    >
                        <option value="">Select...</option>
                        <option value="64-slice">64-slice</option>
                        <option value="128-slice">128-slice</option>
                        <option value="256-slice">256-slice</option>
                        <option value="320-slice">320-slice</option>
                        <option value="unknown">I&apos;m not sure</option>
                    </select>
                    {errors.sliceCount && (
                        <p className="mt-1 text-xs text-red-600">{errors.sliceCount.message}</p>
                    )}
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">Condition</label>
                    <div className="space-y-1">
                        <label className="flex items-center text-sm">
                            <input {...register('condition')} type="radio" value="new" className="mr-2" />
                            New
                        </label>
                        <label className="flex items-center text-sm">
                            <input {...register('condition')} type="radio" value="refurbished" className="mr-2" />
                            Refurbished / Certified Pre-Owned
                        </label>
                        <label className="flex items-center text-sm">
                            <input {...register('condition')} type="radio" value="either" className="mr-2" />
                            Either
                        </label>
                        <label className="flex items-center text-sm text-gray-500">
                            <input {...register('condition')} type="radio" value="unknown" className="mr-2" />
                            I&apos;m not sure
                        </label>
                    </div>
                </div>

                <div>
                    <label className="block text-xs font-medium text-gray-700 mb-1">
                        Manufacturer (Optional)
                    </label>
                    <input
                        {...register('manufacturer')}
                        type="text"
                        className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        placeholder="e.g., GE, Siemens, Philips"
                    />
                </div>

                <button
                    type="submit"
                    className="w-full px-4 py-2 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                >
                    Submit Equipment Details
                </button>
            </form>
        </div>
    );
}
