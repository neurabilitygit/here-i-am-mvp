// Automated mobile WebKit coverage, not proof of a physical iPhone speaker/mic.
const {webkit,expect,devices}=require('../node_modules/@playwright/test');
let input='';
process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',async()=>{
  const {passphrase,url,screenshot}=JSON.parse(input);
  const browser=await webkit.launch();
  try {
    const context=await browser.newContext({...devices['iPhone 13']});
    await context.addCookies([{name:'here_i_am_session',value:'production-cookie-sentinel',url}]);
    const page=await context.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(url);
    expect((await context.request.get(url+'/api/pilot/voice-sample')).status()).toBe(401);
    await page.locator('#login-passphrase').fill(passphrase);
    await page.locator('#login-submit').click();
    await expect(page.locator('#login-dialog')).toBeHidden();
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.voice?.bridge_ready)).toBe(true);
    const cookies=await context.cookies();
    expect(cookies.find(c=>c.name==='here_i_am_session').value).toBe('production-cookie-sentinel');
    expect(cookies.some(c=>c.name==='here_i_am_pilot_session')).toBe(true);
    expect((await context.request.post(url+'/api/memory-batch/start')).status()).toBe(403);
    expect((await context.request.post(url+'/api/chat')).status()).toBe(403);
    await page.locator('#pilot-load-voice').click();
    await expect(page.locator('#speak-answer')).toHaveAccessibleName('Ready—play this answer');
    await expect(page.locator('#speak-answer')).toBeEnabled();
    if(screenshot)await page.screenshot({path:screenshot,fullPage:false});
    await page.locator('#speak-answer').click();
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.voicePlaying)).toBe(true);
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.nativeAudio?.currentTime||0)).toBeGreaterThan(.2);
    const playback=await page.evaluate(()=>{
      const audio=window.HereIAmCore.state.nativeAudio;
      return {method:window.HereIAmCore.state.voicePlaybackMethod,muted:audio.muted,volume:audio.volume};
    });
    expect(playback.muted).toBe(false);
    expect(playback.volume).toBeGreaterThan(0);
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.voicePlaying),{timeout:30000}).toBe(false);
    await expect(page.locator('#talk-scene')).toBeVisible();
    await expect(page.locator('#answer-text')).toContainText('This is a local voice test');
    const secureCapture=await page.evaluate(()=>isSecureContext&&typeof navigator.mediaDevices?.getUserMedia==='function');
    expect(secureCapture).toBe(true);
    await page.locator('[data-go="remember"]').click();
    await expect(page.locator('#remember-scene')).toBeVisible();
    if(errors.length)throw Error(errors.join('; '));
    console.log(JSON.stringify({https:true,separate_cookie:true,production_cookie_preserved:true,
      unauthenticated_audio_blocked:true,inference_and_embedding_blocked:true,
      ready_play_one_click:true,native_audio_time_advanced:true,playback,
      playback_completed:true,answer_preserved:true,secure_microphone_api:true,
      remember_visible:true,page_error_count:0,physical_iphone_verified:false}));
  } catch(error) {console.error(error.message);process.exitCode=1;}
  finally {await browser.close();}
});
