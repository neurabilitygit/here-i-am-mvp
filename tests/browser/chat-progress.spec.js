const {test, expect} = require('@playwright/test');

test.beforeEach(async ({page}) => {
  await page.route('**/api/voice/status', route => route.fulfill({
    contentType: 'application/json', body: JSON.stringify({enabled: false, provider: 'local'}),
  }));
  const [experienceResponse] = await Promise.all([
    page.waitForResponse(r => r.url().endsWith('/api/experience') && r.request().method() === 'GET'),
    page.goto('/'),
  ]);
  const experience = await experienceResponse.json();
  if (!experience.preferences?.onboarding_complete) {
    await expect(page.locator('#onboarding-dialog')).toBeVisible();
    await page.locator('#onboarding-start').click();
  }
  await page.waitForLoadState('networkidle');
  // Control real streaming boundaries without invoking any local/cloud model.
  await page.evaluate(() => {
    const originalFetch = window.fetch;
    window.fetch = (url, options) => {
      if (url !== '/api/chat/stream') return originalFetch(url, options);
      if (window.chatTestHttpError) return Promise.resolve(new Response(
        JSON.stringify({detail: 'The answer engine is unavailable.'}), {status: 503},
      ));
      let streamController;
      let closed = false;
      const stream = new ReadableStream({start(controller) { streamController = controller; }});
      const abort = () => {
        if (!closed) { closed = true; streamController.error(new DOMException('Canceled', 'AbortError')); }
      };
      options.signal.addEventListener('abort', abort, {once: true});
      window.chatTestStream = {
        emit(event, data) {
          streamController.enqueue(new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
        },
        end() { closed = true; options.signal.removeEventListener('abort', abort); streamController.close(); },
      };
      return Promise.resolve(new Response(stream, {headers: {'Content-Type': 'text/event-stream'}}));
    };
  });
});

async function submit(page, question = 'A synthetic memoir question') {
  await page.locator('#chat-question').fill(question);
  await page.locator('#chat-send').click();
}

test('thinking is visible before headers or answer text and remains clear during a slow response', async ({page}, testInfo) => {
  await page.clock.install();
  await submit(page);
  await expect(page.locator('#chat-progress')).toBeVisible();
  await expect(page.locator('#chat-progress-title')).toHaveText('Thinking…');
  await expect(page.locator('#chat-progress-detail')).toContainText('Your question was received');
  await expect(page.locator('#answer-text')).toHaveText('');
  await expect(page.locator('#answer-text')).toHaveAttribute('aria-busy', 'true');
  expect(await page.locator('#answer-text').evaluate(el => getComputedStyle(el, '::after').display)).toBe('none');
  await page.evaluate(() => window.chatTestStream.emit('meta', {mode: 'PERSONAL', provider: 'local', sources: []}));
  await expect(page.locator('#chat-progress-detail')).toContainText('Reviewing your recorded memories');
  await page.screenshot({path: testInfo.outputPath('thinking.png')});
  await page.clock.fastForward(16000);
  await expect(page.locator('#chat-progress-title')).toHaveText('Still thinking…');
  await page.evaluate(() => window.chatTestStream.emit('token', {text: 'A supported memory.'}));
  await expect(page.locator('#chat-progress-title')).toHaveText('Writing your answer…');
  await expect(page.locator('#answer-text')).toHaveText('A supported memory.');
  await page.evaluate(() => { window.chatTestStream.emit('done', {}); window.chatTestStream.end(); });
  await expect(page.locator('#chat-progress')).toBeHidden();
  await expect(page.locator('#answer-text')).toHaveAttribute('aria-busy', 'false');
  await expect(page.locator('#answer-text')).toHaveText('A supported memory.');
  await expect(page.locator('#chat-send')).toBeEnabled();
});

test('clear cancels thinking and an old request cannot hide a new progress message', async ({page}) => {
  await submit(page);
  await expect(page.locator('#chat-progress')).toBeVisible();
  await page.locator('#clear-answer').click();
  await expect(page.locator('#answer-card')).toBeHidden();
  await expect(page.locator('#chat-progress')).toBeHidden();
  expect(await page.evaluate(() => window.HereIAmCore.state.chatThinkingTimer)).toBeNull();
  await submit(page, 'A second synthetic question');
  await expect(page.locator('#chat-progress-title')).toHaveText('Thinking…');
  await expect(page.locator('#chat-progress')).toBeVisible();
  await page.locator('#clear-answer').click();
});

test('HTTP and streamed errors remove thinking and show an actionable message', async ({page}) => {
  await page.evaluate(() => { window.chatTestHttpError = true; });
  await submit(page);
  await expect(page.locator('#answer-text')).toContainText('The answer engine is unavailable.');
  await expect(page.locator('#chat-progress')).toBeHidden();
  await expect(page.locator('#chat-send')).toBeEnabled();
  await page.evaluate(() => { window.chatTestHttpError = false; });
  await submit(page);
  await page.evaluate(() => { window.chatTestStream.emit('error', {detail: 'Please try again.'}); window.chatTestStream.end(); });
  await expect(page.locator('#answer-text')).toContainText('Please try again.');
  await expect(page.locator('#chat-progress')).toBeHidden();
  expect(await page.evaluate(() => window.HereIAmCore.state.chatThinkingTimer)).toBeNull();
});

test('thinking remains readable with reduced motion and is not restored as an answer', async ({page}) => {
  await page.emulateMedia({reducedMotion: 'reduce'});
  await submit(page);
  await expect(page.locator('#chat-progress-title')).toHaveText('Thinking…');
  expect(await page.locator('.chat-progress-dots i').first().evaluate(el => getComputedStyle(el).animationName)).toBe('none');
  await page.locator('#clear-answer').click();
  await page.reload();
  await expect(page.locator('#answer-card')).toBeHidden();
  await expect(page.locator('#chat-progress')).toBeHidden();
});
