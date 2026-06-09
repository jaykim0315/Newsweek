/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,ts}'],
  theme: {
    extend: {
      colors: {
        paper: '#faf8f3',
        ink:   '#1a1a1a',
        wine:  '#6b1f1f',
      },
      fontFamily: {
        masthead:  ['"Playfair Display"', 'Georgia', '"Times New Roman"', 'serif'],
        'serif-kr': ['"Noto Serif KR"', 'Georgia', 'serif'],
        'sans-kr':  ['"Noto Sans KR"', 'Helvetica Neue', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
