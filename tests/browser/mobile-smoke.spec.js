const {test, expect} = require('@playwright/test');

test.beforeEach(async ({page}, testInfo) => {
  test.skip(testInfo.project.name !== 'mobile-safari', 'mobile-viewport-only checks');
  await page.route('**/api/voice/status', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({enabled: true, provider: 'local', reference_ready: true, bridge_ready: true}),
  }));
  const [experienceResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/experience') && response.request().method() === 'GET'),
    page.goto('/'),
  ]);
  const experience = await experienceResponse.json();
  const onboarding = page.locator('#onboarding-dialog');
  if (!experience.preferences?.onboarding_complete) {
    await expect(onboarding).toBeVisible();
    await page.locator('#onboarding-start').tap();
    await expect(onboarding).toBeHidden();
  }
});

test('touch-tap navigation moves between Talk, Remember, and Memories', async ({page}) => {
  await expect(page.locator('#talk-scene')).toBeVisible();

  await page.locator('[data-go="remember"]').tap();
  await expect(page.locator('#remember-scene')).toBeVisible();
  await expect(page.locator('#record-start')).toBeVisible();

  await page.locator('[data-go="memories"]').tap();
  await expect(page.locator('#memories-scene')).toBeVisible();
  await expect(page.locator('#memory-import')).toBeVisible();

  await page.locator('[data-go="talk"]').tap();
  await expect(page.locator('#talk-scene')).toBeVisible();
});

test('recording controls are tappable on a phone viewport', async ({page}) => {
  await page.locator('[data-go="remember"]').tap();
  const recordStart = page.locator('#record-start');
  await expect(recordStart).toBeVisible();
  const box = await recordStart.boundingBox();
  expect(box.width).toBeGreaterThanOrEqual(44);
  expect(box.height).toBeGreaterThanOrEqual(44);
});

test('recording mode choices stack in a single column on a phone-width viewport', async ({page}) => {
  await page.locator('[data-go="remember"]').tap();
  const solo = page.locator('label:has(#record-mode-solo)');
  const conversation = page.locator('label:has(#record-mode-conversation)');
  const soloBox = await solo.boundingBox();
  const conversationBox = await conversation.boundingBox();
  expect(conversationBox.y).toBeGreaterThanOrEqual(soloBox.y + soloBox.height - 1);
});
