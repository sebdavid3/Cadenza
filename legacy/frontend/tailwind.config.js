/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // Sistema estrictamente monocromo: negro, blanco y la escala entre ambos.
      // Al no haber color, la jerarquia la marcan el contraste y la tipografia:
      // blanco = enfasis e interaccion, grises = texto secundario y estados
      // inactivos, cursiva serif = advertencia.
      colors: {
        // Tinta: fondos, del negro puro hacia arriba
        ink: {
          DEFAULT: '#000000',
          900: '#0A0A0A',
          800: '#141414',
          700: '#1F1F1F',
        },
        // Hueso: texto, del blanco puro hacia abajo
        bone: {
          DEFAULT: '#FFFFFF',
          dim: '#A1A1A1',
          // 4.8:1 sobre negro puro. Un gris mas oscuro caeria por debajo del
          // minimo accesible para texto pequeño, que es donde se usa (.label)
          faint: '#787878',
        },
        // Papel: exclusivo del lienzo de partitura
        paper: '#FFFFFF',
      },
      // Tailwind declara un azul por defecto para el anillo de foco. Aqui el
      // foco se dibuja con outline, asi que la variable no llega a usarse, pero
      // se neutraliza para que la hoja compilada no contenga ningun color.
      ringColor: {
        DEFAULT: '#FFFFFF',
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
