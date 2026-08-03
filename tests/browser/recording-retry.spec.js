const {test, expect} = require('@playwright/test');

test.beforeEach(async ({page}) => {
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
    await page.locator('#onboarding-start').click();
    await expect(onboarding).toBeHidden();
  }
  await page.locator('[data-go="remember"]').click();
});

// Seed a fake captured recording directly on shared state, bypassing the
// real microphone/MediaRecorder pipeline this test environment can't drive.
async function seedFakeRecording(page) {
  await page.evaluate(() => {
    const blob = new Blob(['synthetic-audio-bytes'], {type: 'audio/webm'});
    window.HereIAmCore.state.recordedChunks = [blob];
  });
}

test('a failed upload keeps the recording and offers a retry that succeeds', async ({page}) => {
  let attempt = 0;
  await page.route('**/api/recordings/upload', async (route) => {
    attempt += 1;
    if (attempt === 1) {
      await route.abort('failed');
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({session_id: 'retry-test-session', message: 'saved', recording_mode: 'solo'}),
    });
  });
  await page.route('**/api/sessions', (route) => route.fulfill({contentType: 'application/json', body: '[]'}));
  await page.route('**/api/memory-batch/status', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({queued_recordings: 0, running: false, last_job: null}),
  }));

  await seedFakeRecording(page);
  await page.evaluate(() => window.uploadRecording({unexpected: false}));

  await expect(page.locator('#recording-status')).toContainText('still here on this device');
  await expect(page.locator('#record-retry')).toBeVisible();
  const stillHasAudio = await page.evaluate(() => window.HereIAmCore.state.recordedChunks.length);
  expect(stillHasAudio).toBe(1);

  await page.locator('#record-retry').click();

  await expect(page.locator('#record-retry')).toBeHidden();
  await expect(page.locator('#recording-status')).toContainText('safe and waiting');
  expect(attempt).toBe(2);
});

test('retry refuses to proceed once the captured audio is gone (e.g. a fresh recording started)', async ({page}) => {
  await page.route('**/api/recordings/upload', (route) => route.abort('failed'));
  await seedFakeRecording(page);
  await page.evaluate(() => window.uploadRecording({unexpected: false}));
  await expect(page.locator('#record-retry')).toBeVisible();

  // Mirrors what startRecording() does when a new recording begins.
  await page.evaluate(() => { window.HereIAmCore.state.recordedChunks = []; });
  await page.locator('#record-retry').click();
  await expect(page.locator('#recording-status')).toContainText('nothing captured to retry');
});
