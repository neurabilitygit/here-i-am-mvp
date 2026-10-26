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

test('successful login opens a fresh landing page after Safari commits the session cookie', async ({page}) => {
  await page.route('**/api/auth/login', (route) => route.fulfill({
    contentType: 'application/json',
    body: JSON.stringify({authenticated: true, required: true}),
  }));
  await page.evaluate(() => window.showLoginDialog());
  await page.locator('#login-passphrase').fill('synthetic passphrase');

  await Promise.all([
    page.waitForNavigation(),
    page.locator('#login-form button[type="submit"]').click(),
  ]);

  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator('#talk-scene')).toBeVisible();
  await expect(page.locator('#login-dialog')).toBeHidden();
});

test('suggested questions stay disabled until the current answer finishes', async ({page}) => {
  let finishAnswer;
  const answerCanFinish = new Promise((resolve) => { finishAnswer = resolve; });
  await page.route('**/api/chat/stream', async (route) => {
    await answerCanFinish;
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: [
        'event: meta\ndata: {"mode":"PERSONAL","provider":"local","sources":[]}\n\n',
        'event: token\ndata: {"text":"A grounded answer."}\n\n',
        'event: done\ndata: {"elapsed_seconds":0.1}\n\n',
      ].join(''),
    });
  });

  await page.locator('#suggestions button').first().click();
  await expect(page.locator('#suggestions button').first()).toBeDisabled();
  await expect(page.locator('#suggestions button').nth(1)).toBeDisabled();
  await expect(page.locator('#chat-send')).toBeDisabled();

  finishAnswer();
  await expect(page.locator('#answer-text')).toHaveText('A grounded answer.');
  await expect(page.locator('#suggestions button').first()).toBeEnabled();
  await expect(page.locator('#chat-send')).toBeEnabled();
});

test('voice creation waits for a valid recording choice', async ({page}) => {
  let releaseCandidates;
  const candidatesCanLoad = new Promise((resolve) => { releaseCandidates = resolve; });
  await page.route('**/api/voice/candidates', async (route) => {
    await candidatesCanLoad;
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify([{
        session_id: '2026-04-14_03-10-17_recording',
        duration_seconds: 373.4,
        transcript_words: 800,
        words_per_minute: 128.5,
        score: 91.2,
      }]),
    });
  });

  await page.locator('#settings-button').click();
  await page.locator('#voice-setup-button').click();
  await expect(page.locator('#voice-dialog')).toBeVisible();
  await expect(page.locator('#voice-create')).toBeDisabled();
  await expect(page.locator('#voice-candidate')).toBeDisabled();

  releaseCandidates();
  await expect(page.locator('#voice-candidate')).toHaveValue('2026-04-14_03-10-17_recording');
  await expect(page.locator('#voice-create')).toBeEnabled();
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
