'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { X } from 'lucide-react';

const equipmentSchema = z.object({
    equipmentType: z.string().min(1, 'Equipment type is required'),
    sliceCount: z.string().min(1, 'Slice count is required'),
    condition: z.enum(['new', 'refurbished', 'either']),
    manufacturer: z.string().optional(),
    clinicalUse: z.string().optional(),
});

type EquipmentFormData = z.infer<typeof equipmentSchema>;

interface EquipmentFormModalProps {
    open: boolean;
    onClose: () => void;
    onSubmit: (data: EquipmentFormData) => void;
}

export default function EquipmentFormModal({
    open,
    onClose,
    onSubmit,
}: EquipmentFormModalProps) {
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

    if (!open) return null;

    return (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-white rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto">
                <div className="sticky top-0 bg-white border-b border-gray-200 p-4 flex items-center justify-between">
                    <h2 className="text-xl font-semibold text-gray-900">Equipment Details</h2>
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
                            Equipment Type
                        </label>
                        <input
                            {...register('equipmentType')}
                            type="text"
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="e.g., CT Scanner, MRI, X-Ray"
                        />
                        {errors.equipmentType && (
                            <p className="mt-1 text-sm text-red-600">{errors.equipmentType.message}</p>
                        )}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Slice Count / Specifications
                        </label>
                        <select
                            {...register('sliceCount')}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        >
                            <option value="">Select slice count...</option>
                            <option value="64-slice">64-slice</option>
                            <option value="128-slice">128-slice</option>
                            <option value="256-slice">256-slice</option>
                            <option value="320-slice">320-slice</option>
                        </select>
                        {errors.sliceCount && (
                            <p className="mt-1 text-sm text-red-600">{errors.sliceCount.message}</p>
                        )}
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">Condition</label>
                        <div className="space-y-2">
                            <label className="flex items-center">
                                <input
                                    {...register('condition')}
                                    type="radio"
                                    value="new"
                                    className="mr-2"
                                />
                                New
                            </label>
                            <label className="flex items-center">
                                <input
                                    {...register('condition')}
                                    type="radio"
                                    value="refurbished"
                                    className="mr-2"
                                />
                                Refurbished / Certified Pre-Owned
                            </label>
                            <label className="flex items-center">
                                <input
                                    {...register('condition')}
                                    type="radio"
                                    value="either"
                                    className="mr-2"
                                />
                                Either
                            </label>
                        </div>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Manufacturer Preference (Optional)
                        </label>
                        <input
                            {...register('manufacturer')}
                            type="text"
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="e.g., GE, Siemens, Philips, Canon"
                        />
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Clinical Use (Optional)
                        </label>
                        <textarea
                            {...register('clinicalUse')}
                            rows={3}
                            className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            placeholder="e.g., Cardiac imaging, oncology, neuro, research..."
                        />
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
