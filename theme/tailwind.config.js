/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    // All HTML/JS files in your project's root-level templates directory
    '../templates/**/*.{html,js}',

    // Templates within your 'cases' app
    '../cases/templates/**/*.{html,js}',

    // Templates within your main project app (if you have templates here)
    '../case_management/templates/**/*.{html,js}',

    // If you ever add other apps with their own templates, add them here:
    // '../other_app/templates/**/*.{html,js}',
  ],
  theme: {
    extend: {
      // Add any custom colors, spacing, etc. here
      // Example:
      // colors: {
      //   brand: {
      //     light: '#3fbaeb',
      //     DEFAULT: '#0fa9e6',
      //     dark: '#0c87b8',
      //   }
      // }
    },
  },
  plugins: [
    // e.g. require('@tailwindcss/forms'),
    //      require('@tailwindcss/typography'),
  ],
}
