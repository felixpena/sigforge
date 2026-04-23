/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      colors: {
        forge: {
          bg: '#0a0a0f',
          panel: '#0f1117',
          border: '#1a1f2e',
          accent: '#00ff88',
          red: '#ff3366',
          yellow: '#ffcc00',
          blue: '#00aaff',
          purple: '#9945ff',
          dim: '#3a4055',
          text: '#c0cce0',
          muted: '#5a6580',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'scan-line': 'scanLine 2s linear infinite',
        'rain-drop': 'rainDrop 1.5s ease-in infinite',
      },
      keyframes: {
        scanLine: {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        rainDrop: {
          '0%': { opacity: 1, transform: 'translateY(0)' },
          '100%': { opacity: 0, transform: 'translateY(200px)' },
        },
      },
    },
  },
  plugins: [],
}
