export default [
  {
    files: ["**/*.mjs"],
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
    },
    rules: {
      "no-undef": "error",
      "no-unused-vars": "error",
    },
  },
  {
    ignores: [".next/**", "out/**", "node_modules/**", "next-env.d.ts"],
  },
];
