const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  { ignores: ['dist/*', 'ios/*', 'android/*'] },
  { rules: { 'import/no-unresolved': 'off' } },   // tsc checks imports
]);
