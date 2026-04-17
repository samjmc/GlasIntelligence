import js from '@eslint/js'
import globals from 'globals'
import pluginVue from 'eslint-plugin-vue'

export default [
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'warn',
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-console': 'off',
      // Soft cap (~750 LOC); warn only — refactor oversized files incrementally (see docs/code-conventions.md)
      'max-lines': ['warn', { max: 750, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    ignores: ['dist/', 'node_modules/'],
  },
]
