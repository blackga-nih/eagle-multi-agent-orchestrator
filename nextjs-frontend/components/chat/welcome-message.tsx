'use client';

import { Sparkles, Shield, FileText, Search } from 'lucide-react';

export default function WelcomeMessage() {
    return (
        <div className="flex justify-start animate-in fade-in slide-in-from-bottom-2 duration-500">
            <div className="max-w-[85%] bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
                {/* Header */}
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center text-white text-xl font-bold shadow-md shadow-blue-200">
                        E
                    </div>
                    <div>
                        <h2 className="text-lg font-bold text-gray-900">Welcome to EAGLE</h2>
                        <p className="text-xs text-blue-600 font-semibold uppercase tracking-wider">
                            Office of Acquisitions AI Assistant
                        </p>
                    </div>
                </div>

                {/* Greeting */}
                <p className="text-gray-700 mb-6 leading-relaxed">
                    Hello! I&apos;m EAGLE, your acquisition assistant. I can help you navigate the
                    procurement process, from initial intake to document generation.
                    What would you like to work on today?
                </p>

                {/* Capabilities */}
                <div className="grid grid-cols-2 gap-3 mb-4">
                    <div className="flex items-start gap-2 p-3 bg-blue-50 rounded-xl">
                        <FileText className="w-5 h-5 text-blue-600 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-gray-900">Acquisition Packages</p>
                            <p className="text-xs text-gray-600">Create and manage procurement requests</p>
                        </div>
                    </div>
                    <div className="flex items-start gap-2 p-3 bg-green-50 rounded-xl">
                        <Search className="w-5 h-5 text-green-600 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-gray-900">Research</p>
                            <p className="text-xs text-gray-600">Search regulations and policies</p>
                        </div>
                    </div>
                    <div className="flex items-start gap-2 p-3 bg-purple-50 rounded-xl">
                        <Sparkles className="w-5 h-5 text-purple-600 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-gray-900">Document Generation</p>
                            <p className="text-xs text-gray-600">Generate SOWs, IGCEs, and more</p>
                        </div>
                    </div>
                    <div className="flex items-start gap-2 p-3 bg-amber-50 rounded-xl">
                        <Shield className="w-5 h-5 text-amber-600 mt-0.5" />
                        <div>
                            <p className="text-sm font-semibold text-gray-900">Compliance</p>
                            <p className="text-xs text-gray-600">Ensure FAR/DFAR compliance</p>
                        </div>
                    </div>
                </div>

                {/* Hint */}
                <p className="text-xs text-gray-400 text-center">
                    Click a suggestion below or type your request
                </p>
            </div>
        </div>
    );
}
