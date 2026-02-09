import type { Config } from 'tailwindcss';

const config: Config = {
    content: [
        './pages/**/*.{js,ts,jsx,tsx,mdx}',
        './components/**/*.{js,ts,jsx,tsx,mdx}',
        './app/**/*.{js,ts,jsx,tsx,mdx}',
    ],
    theme: {
        extend: {
            colors: {
                nci: {
                    primary: '#003149',
                    'primary-dark': '#0D2648',
                    danger: '#BB0E3D',
                    accent: '#7740A4',
                    info: '#004971',
                    link: '#0B6ED7',
                    success: '#037F0C',
                },
            },
        },
    },
    plugins: [],
};

export default config;
