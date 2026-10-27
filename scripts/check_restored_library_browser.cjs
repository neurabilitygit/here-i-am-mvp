const {webkit,expect}=require('../node_modules/@playwright/test');
const {createHash}=require('node:crypto');
let input='';
process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',async()=>{
  const {url,passphrase,recordingId,count,seconds,audioSha256}=JSON.parse(input);
  const browser=await webkit.launch();
  try {
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    expect((await page.request.get(url+'/api/sessions')).status()).toBe(401);
    await page.locator('#login-passphrase').fill(passphrase);
    await page.locator('#login-submit').click();
    await expect(page.locator('#login-dialog')).toBeHidden();
    const savedAudio=await page.request.get(url+'/api/sessions/'+recordingId+'/audio');
    expect(savedAudio.status()).toBe(200);
    const audioDigest=createHash('sha256').update(await savedAudio.body()).digest('hex');
    if(audioSha256)expect(audioDigest).toBe(audioSha256);
    await page.locator('[data-go="memories"]').click();
    await expect(page.locator('#memory-gallery .memory-card')).toHaveCount(count);
    await page.locator('#memory-gallery .memory-card').filter({hasText:recordingId}).click();
    await expect(page.locator('#memory-dialog')).toBeVisible();
    await expect(page.locator('#memory-meta')).toContainText('Waiting for the local batch');
    await expect.poll(()=>page.locator('#memory-audio').evaluate(audio=>Number.isFinite(audio.duration)?audio.duration:0)).toBeGreaterThan(seconds-.1);
    const duration=await page.locator('#memory-audio').evaluate(audio=>audio.duration);
    expect(Math.abs(duration-seconds)).toBeLessThan(.1);
    if(errors.length)throw Error(errors.join('; '));
    console.log(JSON.stringify({login:true,unauthenticated_library_blocked:true,audio_sha256:audioDigest,
      memory_count:count,phone_recording_visible:true,
      pending_state_preserved:true,recording_audio_loaded:true,audio_seconds:duration,page_error_count:0}));
  } catch(error) {console.error(error.message);process.exitCode=1;}
  finally {await browser.close();}
});
