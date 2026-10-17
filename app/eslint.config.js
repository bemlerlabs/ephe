import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist/', 'src-tauri/target/', 'src-tauri/gen/'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': [
        'warn',
        { allowConstantExport: true },
      ],
      // `_arg` convention: named-but-deliberately-unused parameters (mocks,
      // interface fulfilment) are not an error
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // R48 S5: primitive guard — in dashboard components only the semantic
      // aliases count (text-status-*, text-ui-*, shadow-elevation-*,
      // z-*). The primitives stay as @theme sources; new call sites in
      // components should use the aliases (tolerance ±0, warn level).
      'no-restricted-syntax': [
        'warn',
        {
          selector: 'Literal[value=/\\btext-mist(?!-)/]',
          message: 'Semantischen Token-Alias statt Primitiv-Klasse verwenden (text-status-* / globals.css @theme).',
        },
        {
          selector: 'Literal[value=/\\bbg-black-forest\\b/]',
          message: 'Semantischen Token-Alias statt Primitiv-Klasse verwenden (surface-* / globals.css @theme).',
        },
      ],
    },
  },
)
