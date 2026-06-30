/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Primary brand — calm jade / teal (matches PaperPod brand art)
        brand: {
          50: '#effaf7',
          100: '#d6f2ea',
          200: '#aee5d7',
          300: '#79d2be',
          400: '#43b89f',
          500: '#1f9d85',
          600: '#147e6c',
          700: '#136458',
          800: '#13504a',
          900: '#11423c',
        },
        // Warm coral accent (matches the promo art highlights).
        accent: {
          50: '#fff5f0',
          100: '#ffe6da',
          200: '#ffc9b4',
          300: '#ffa888',
          400: '#fb835a',
          500: '#f06434',
          600: '#dd4d20',
          700: '#b83b19',
          800: '#933218',
          900: '#772c18',
        },
        // Override legacy `purple-*` utilities to the warm accent so any
        // remaining gradient/text usages recolor on-brand instead of clashing.
        purple: {
          50: '#fff5f0',
          100: '#ffe6da',
          200: '#ffc9b4',
          300: '#ffa888',
          400: '#fb835a',
          500: '#f06434',
          600: '#dd4d20',
          700: '#b83b19',
          800: '#933218',
          900: '#772c18',
        },
        // Warm "paper" neutrals for surfaces and borders.
        paper: {
          50: '#fdfcf9',
          100: '#f9f6f0',
          200: '#f1ece2',
          300: '#e6ddcd',
          400: '#d6cab2',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        display: ['Fraunces', 'Georgia', 'serif'],
      },
      boxShadow: {
        soft: '0 1px 2px rgba(19,80,71,0.04), 0 10px 30px -12px rgba(19,80,71,0.12)',
        glow: '0 18px 48px -18px rgba(31,157,132,0.40)',
      },
      keyframes: {
        eq: {
          '0%, 100%': { transform: 'scaleY(0.3)' },
          '50%': { transform: 'scaleY(1)' },
        },
      },
      animation: {
        eq: 'eq 1.1s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
