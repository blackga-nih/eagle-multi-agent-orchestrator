import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';
import js from '@eslint/js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
    baseDirectory: __dirname,
    recommendedConfig: js.configs.recommended,
});

const eslintConfig = [
    {
        ignores: [
            '.next/**',
            '.next.bak/**',
            'out/**',
            'node_modules/**',
            'test-results/**',
            'playwright-report/**',
            'public/**',
        ],
    },
    ...compat.extends('next/core-web-vitals'),
];

export default eslintConfig;
