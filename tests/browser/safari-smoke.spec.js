const {test, expect} = require('@playwright/test');

const sse = (answer, provider = 'local') => [
  `event: meta\ndata: ${JSON.stringify({mode: 'PERSONAL', provider})}\n\n`,
  `event: token\ndata: ${JSON.stringify({text: answer})}\n\n`,
  'event: done\ndata: {"elapsed_seconds":0.01}\n\n',
].join('');

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

test('primary controls remain interactive in WebKit', async ({page}) => {
  await expect(page.locator('#talk-scene')).toBeVisible();
  await page.locator('#settings-button').click();
  await expect(page.locator('#setting-provider')).toBeEnabled();
  await page.locator('#settings-dialog .close-button').click();
  await page.locator('[data-go="memories"]').click();
  await expect(page.locator('#memory-import')).toBeVisible();
  await page.locator('[data-go="talk"]').click();
  await expect(page.locator('#chat-question')).toBeFocused();
});

test('an old voice request cannot take over a newer answer', async ({page}) => {
  let questionNumber = 0;
  await page.route('**/api/chat/stream', async (route) => {
    questionNumber += 1;
    const answer = questionNumber === 1 ? 'First completed answer.' : 'Second completed answer.';
    await route.fulfill({status: 200, contentType: 'text/event-stream', body: sse(answer)});
  });
  await page.route('**/api/voice/speak', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({status: 200, contentType: 'audio/wav', body: Buffer.from('RIFF')});
  });

  await page.locator('#chat-question').fill('First question');
  await page.locator('#chat-send').click();
  await expect(page.locator('#answer-text')).toHaveText('First completed answer.');
  await page.locator('#speak-answer').click();
  await page.locator('#chat-question').fill('Second question');
  await page.locator('#chat-send').click();

  await expect(page.locator('#answer-text')).toHaveText('Second completed answer.');
  await page.waitForTimeout(900);
  await expect(page.locator('#answer-text')).toHaveText('Second completed answer.');
  await expect(page.locator('#stop-speaking')).toBeHidden();
});
