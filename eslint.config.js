import globals from 'globals';

export default [
  {
    ignores: [
      "node_modules/",
      "dist/",
      "vps_instances/",
      "data/",
      "*.log",
      "*.pid",
      ".env*"
    ]
  },
  {
    files: ["**/*.js", "**/*.mjs", "**/*.cjs"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.node,
        ...globals.es2022
      }
    },
    rules: {
      "no-unused-vars": ["warn", { "argsIgnorePattern": "^_" }],
      "no-console": "off",
      "prefer-const": "error",
      "no-var": "error",
      "eqeqeq": ["error", "always"],
      "curly": ["error", "all"],
      "block-scoped-var": "error",
      "no-fallthrough": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-script-url": "error",
      "no-self-compare": "error",
      "no-throw-literal": "error",
      "radix": "error",
      "yoda": "error",
      "prefer-arrow-callback": "warn",
      "prefer-template": "warn",
      "object-shorthand": "warn",
      "prefer-destructuring": ["warn", { "array": false, "object": true }]
    }
  }
];