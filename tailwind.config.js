/** Tailwind build config — only used to compile static/css/tailwind.css. */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './static/index.html',
    './static/js/**/*.js'
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace']
      }
    }
  },
  plugins: []
};
