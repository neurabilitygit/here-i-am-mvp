const {defineConfig, devices} = require('@playwright/test');

module.exports = defineConfig({
  testDir: './tests/browser',
  testIgnore: '**/._*',
  globalTeardown: require.resolve('./tests/browser/global-teardown'),
  timeout: 30000,
  fullyParallel: false,
  workers: 1,
  use: {
    baseURL: 'http://127.0.0.1:8791',
    trace: 'retain-on-failure',
  },
  projects: [
    {name: 'webkit', use: {...devices['Desktop Safari']}},
    {name: 'mobile-safari', use: {...devices['iPhone 13']}},
  ],
  webServer: {
    command: 'bash scripts/start_browser_test_server.sh',
    url: 'http://127.0.0.1:8791/api/health',
    reuseExistingServer: false,
    timeout: 120000,
  },
});
