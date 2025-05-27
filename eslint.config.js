export default [
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        window: 'readonly',
        document: 'readonly',
        // Add other browser or Node globals here if needed
      },
    },
    plugins: {},
    rules: {
      // Add custom rules here, for example:
      // 'semi': ['error', 'always'],
      // 'quotes': ['error', 'single'],
    },
    // Optionally, extends are not supported in the same way as before,
    // but you can use eslint:recommended like this:
    // https://eslint.org/docs/latest/use/configure/configuration-files-new#extending-other-configurations
    extends: ['eslint:recommended'],
  }
];