// Credentials arrive through stdin, never command-line arguments or logs.
const {webkit, expect} = require('../node_modules/@playwright/test');
let input='';
process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',async()=>{
  const {url,passphrase,audio}=JSON.parse(input);
  const browser=await webkit.launch();
  try {
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    await expect(page.locator('#login-dialog')).toBeVisible();
    await page.locator('#login-passphrase').fill(passphrase);
    await page.locator('#login-submit').click();
    await expect(page.locator('#login-dialog')).toBeHidden();
    await expect(page.locator('#talk-scene')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.locator('[data-go="remember"]').click();
    await page.locator('#record-title').fill('Synthetic native recovery acceptance');
    await page.route('**/api/recordings/upload',route=>route.abort('failed'));
    await page.evaluate(base64=>{
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
      window.HereIAmCore.state.recordedChunks=[new Blob([bytes],{type:'audio/wav'})];
    },audio);
    await page.evaluate(()=>window.uploadRecording());
    await expect(page.locator('#record-retry')).toBeVisible();
    await page.waitForLoadState('networkidle');
    await page.reload();
    await page.locator('[data-go="remember"]').click();
    await expect(page.locator('#recording-status')).toContainText('recovered on this device');
    await page.unroute('**/api/recordings/upload');
    const uploaded=page.waitForResponse(r=>r.url().endsWith('/api/recordings/upload')&&r.request().method()==='POST');
    await page.locator('#record-retry').click();
    const response=await uploaded;
    if(response.status()!==200)throw Error(`Upload failed: ${response.status()}`);
    const payload=await response.json();
    await expect(page.locator('#recording-status')).toContainText('safe and waiting');
    await expect.poll(()=>page.evaluate(()=>window.RecordingDrafts.oldest())).toBeNull();
    if(errors.length)throw Error('Unexpected browser JavaScript error: '+JSON.stringify(errors));
    console.log(JSON.stringify({login_ui:true,draft_recovered_after_reload:true,real_retry_upload:true,
      draft_removed_after_ack:true,session_id:payload.session_id,page_error_count:errors.length}));
  } catch(error) {
    console.error(error.message);
    process.exitCode=1;
  } finally {await browser.close();}
});
