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
  await expect(solo).toBeVisible();
  await expect(conversation).toBeVisible();
  // Read both rectangles in one browser frame. Separate round trips can
  // compare different positions during scene-in animation or smooth scrolling.
  await expect.poll(() => page.evaluate(() => {
    const first = document.querySelector('label:has(#record-mode-solo)').getBoundingClientRect();
    const second = document.querySelector('label:has(#record-mode-conversation)').getBoundingClientRect();
    return second.top - first.bottom;
  })).toBeGreaterThanOrEqual(-1);
});

test('a ready voice uses the native iPhone media route on the first tap', async ({page}) => {
  await page.evaluate(() => {
    window.__nativeAudioPlayCalls = 0;
    HTMLMediaElement.prototype.play = function playProbe() {
      window.__nativeAudioPlayCalls += 1;
      queueMicrotask(() => this.onplaying?.());
      return Promise.resolve();
    };
    HTMLMediaElement.prototype.pause = () => {};
    HTMLMediaElement.prototype.load = () => {};
    // Mock the media transport as well as play(): synthetic fixture bytes are
    // not decodable audio and must not trigger a real asynchronous media error.
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {configurable: true, set() {}, get() { return ''; }});
    const state = window.HereIAmCore.state;
    state.lastAnswer = 'A prepared answer for native iPhone playback.';
    state.chatGeneration = 1;
    state.voicePrerenderText = state.lastAnswer;
    state.voicePrerenderGeneration = 1;
    state.voicePrerenderBlob = new Blob(['prepared-voice'], {type: 'audio/wav'});
    document.getElementById('answer-text').textContent = state.lastAnswer;
    document.getElementById('answer-card').hidden = false;
    window.updateSpeakButton();
  });

  expect(await page.evaluate(() => isIOSPlaybackDevice())).toBe(true);
  await expect(page.locator('#speak-answer')).toContainText('Ready—Play');
  await expect(page.locator('#speak-answer')).toBeEnabled();
  await page.locator('#speak-answer').tap();

  await expect.poll(() => page.evaluate(() => window.__nativeAudioPlayCalls)).toBe(1);
  expect(await page.evaluate(() => window.HereIAmCore.state.voicePlaybackMethod)).toBe('html_audio');
  expect(await page.evaluate(() => window.HereIAmCore.state.audioContext)).toBeNull();
  await expect(page.locator('#stop-speaking')).toContainText('Playing');
});

test('completed preparation hides Cancel and offers Ready—Play', async ({page}) => {
  await page.evaluate(() => {
    const state = window.HereIAmCore.state;
    state.lastAnswer = 'A prepared answer.';
    state.voicePrerenderText = state.lastAnswer;
    state.voicePrerenderBlob = new Blob(['ready'], {type: 'audio/wav'});
    state.voicePreparing = false;
    state.voicePlaying = false;
    document.getElementById('answer-card').hidden = false;
    document.getElementById('stop-speaking').hidden = false;
    window.updateSpeakButton();
  });
  await expect(page.locator('#stop-speaking')).toBeHidden();
  await expect(page.locator('#speak-answer')).toContainText('Ready—Play');
});
