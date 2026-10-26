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

test('a failed recording survives reload and is removed only after server acknowledgement', async ({page}) => {
  const storageError = await page.evaluate(async () => {
    try {
      await window.RecordingDrafts.append('storage-probe', 0, new Blob(['probe']), {title:'probe'});
      await window.RecordingDrafts.remove('storage-probe');
      return null;
    } catch (error) { return `${error.name}: ${error.message}`; }
  });
  expect(storageError).toBeNull();
  await page.route('**/api/recordings/upload', (route) => route.abort('failed'));
  await page.locator('#record-title').fill('Recovery fixture');
  await seedFakeRecording(page);
  await page.evaluate(() => window.uploadRecording());
  await page.reload();
  await page.locator('[data-go="remember"]').click();
  await expect(page.locator('#recording-status')).toContainText('recovered on this device');
  await expect(page.locator('#record-title')).toHaveValue('Recovery fixture');
  await expect(page.locator('#record-start')).toBeDisabled();
  expect(await page.evaluate(async () => new Blob(window.HereIAmCore.state.recordedChunks).text())).toBe('synthetic-audio-bytes');
  await page.route('**/api/recordings/upload', (route) => route.fulfill({contentType:'application/json', body:JSON.stringify({session_id:'recovered-test', status:'ready'})}));
  await page.locator('#record-retry').click();
  await expect.poll(() => page.evaluate(() => window.RecordingDrafts.oldest())).toBeNull();
});

test('unavailable draft storage does not prevent upload or silently promise recovery', async ({page}) => {
  await page.route('**/api/recordings/upload', (route) => route.abort('failed'));
  await page.evaluate(() => { window.RecordingDrafts = {append: () => Promise.reject(new Error('quota exceeded'))}; });
  await seedFakeRecording(page);
  await page.evaluate(() => window.uploadRecording());
  await expect(page.locator('#recording-status')).toContainText('Keep this page open');
  expect(await page.evaluate(() => window.HereIAmCore.state.recordedChunks.length)).toBe(1);
});

test('a draft with a missing chunk cannot be marked complete or silently uploaded', async ({page}) => {
  const incomplete = await page.evaluate(async () => {
    await window.RecordingDrafts.append('incomplete-draft', 1, new Blob(['second chunk']), {});
    let rejected = false;
    try { await window.RecordingDrafts.finalize('incomplete-draft', 2, {}); }
    catch (_) { rejected = true; }
    return {rejected, draft: await window.RecordingDrafts.oldest()};
  });
  expect(incomplete.rejected).toBe(true);
  expect(incomplete.draft.complete).toBe(false);
  let uploads = 0;
  await page.route('**/api/recordings/upload', (route) => { uploads++; return route.abort('failed'); });
  await page.reload();
  await page.locator('[data-go="remember"]').click();
  await expect(page.locator('#recording-status')).toContainText('completeness could not be verified');
  await expect(page.locator('#record-retry')).toBeHidden();
  expect(uploads).toBe(0);
});

test('a delayed recovery lookup cannot overwrite a newer recording generation', async ({page}) => {
  const result = await page.evaluate(async () => {
    const state = window.HereIAmCore.state;
    let deliver;
    const original = window.RecordingDrafts;
    window.RecordingDrafts = {...original, oldest: () => new Promise((resolve) => { deliver = resolve; })};
    const recovery = window.restoreRecordingDraft();
    state.recordSession += 1;
    state.recordDraftId = 'new-recording';
    deliver({id:'old-recording', complete:true, chunks:[new Blob(['old audio'])]});
    await recovery;
    window.RecordingDrafts = original;
    return {id:state.recordDraftId, chunks:state.recordedChunks.length};
  });
  expect(result).toEqual({id:'new-recording', chunks:0});
});
