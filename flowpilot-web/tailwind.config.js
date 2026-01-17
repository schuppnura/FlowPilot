/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'nura-orange': '#F28C3D',
        'nura-dark': '#333340',
        'nura-bg': '#FAFAFA',
      },
    },
  },
  plugins: [],
}
