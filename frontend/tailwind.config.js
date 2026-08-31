/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Tinta: fondos, de más oscuro a menos
        ink: {
          DEFAULT: '#0E0E10',
          900: '#141416',
          800: '#1C1C1F',
          700: '#26262A',
        },
        // Hueso: texto, de más presente a más tenue
        bone: {
          DEFAULT: '#E8E6E1',
          dim: '#9B9892',
          faint: '#6B6862',
        },
        // Latón: único acento del sistema
        brass: {
          DEFAULT: '#C9A227',
          dim: '#8A701A',
        },
        // Ladrillo: único color de error, deliberadamente apagado
        brick: '#C1554A',
        // Papel: exclusivo del lienzo de partitura
        paper: '#F7F5F0',
      },
      fontFamily: {
        display: ['Spectral', 'Georgia', 'serif'],
        sans: ['ui-sans-serif', 'system-ui', 'Segoe UI', 'Helvetica', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      letterSpacing: {
        label: '0.14em',
      },
      keyframes: {
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'none' },
        },
        // Cabeza de nota que recorre el pentagrama mientras se transcribe
        'staff-travel': {
          '0%':   { left: '0%', opacity: '0' },
          '10%':  { opacity: '1' },
          '90%':  { opacity: '1' },
          '100%': { left: '100%', opacity: '0' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.45' },
        },
      },
      animation: {
        'fade-in': 'fade-in 260ms ease-out both',
        'staff-travel': 'staff-travel 2.6s cubic-bezier(.4,0,.6,1) infinite',
        'pulse-soft': 'pulse-soft 1.8s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
