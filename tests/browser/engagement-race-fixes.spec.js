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
});

test('a stale upload failure from a superseded recording does not clobber the new one', async ({page}) => {
  await page.route('**/api/recordings/upload', (route) => route.abort('failed'));
  await page.locator('[data-go="remember"]').click();
  await page.evaluate(() => {
    window.HereIAmCore.state.recordedChunks = [new Blob(['synthetic-audio-bytes'], {type: 'audio/webm'})];
  });

  const uploadPromise = page.evaluate(() => window.uploadRecording({unexpected: false}));
  // A new recording starts (as startRecording() does) before the failed
  // upload above has finished reporting failure.
  await page.evaluate(() => {
    window.HereIAmCore.state.recordSession += 1;
    document.getElementById('recording-status').textContent = 'I am listening. Take your time.';
  });
  await uploadPromise;

  await expect(page.locator('#recording-status')).toHaveText('I am listening. Take your time.');
  await expect(page.locator('#record-retry')).toBeHidden();
});

test('showLoginDialog closes any other open dialog instead of stacking on top of it', async ({page}) => {
  await page.evaluate(() => document.getElementById('quiz-dialog').showModal());
  await expect(page.locator('#quiz-dialog')).toBeVisible();

  await page.evaluate(() => window.showLoginDialog());

  await expect(page.locator('#login-dialog')).toBeVisible();
  await expect(page.locator('#quiz-dialog')).toBeHidden();
});

test('renderRelatedMemories ignores a response for a memory that is no longer open', async ({page}) => {
  await page.evaluate(() => { window.HereIAmCore.state.activeSessionId = 'memory-b'; });
  await page.locator('#related-memories').evaluate((el) => { el.hidden = true; });

  await page.evaluate(() => window.renderRelatedMemories('memory-a', [
    {session_id: 'stale-source', title: 'Should never appear', topics: '', distance: 0.1},
  ]));

  await expect(page.locator('#related-memories')).toBeHidden();
});

test('openQuiz keeps the reveal button disabled until the prompt actually arrives', async ({page}) => {
  let resolveQuiz;
  const quizArrived = new Promise((resolve) => { resolveQuiz = resolve; });
  await page.route('**/api/quiz/prompt', async (route) => {
    await quizArrived;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({session_id: 'quiz-session', topic_hint: 'the trumpet', quote: 'I loved playing trumpet at Tanglewood.'}),
    });
  });

  const opening = page.evaluate(() => window.openQuiz());

  await expect(page.locator('#quiz-dialog')).toBeVisible();
  await expect(page.locator('#quiz-reveal')).toBeDisabled();

  resolveQuiz();
  await opening;

  await expect(page.locator('#quiz-reveal')).toBeEnabled();
});
