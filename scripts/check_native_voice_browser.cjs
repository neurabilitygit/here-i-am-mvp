const {webkit,expect}=require('../node_modules/@playwright/test');
let input='';
process.stdin.on('data',chunk=>input+=chunk);
process.stdin.on('end',async()=>{
  const {passphrase,text}=JSON.parse(input);
  const browser=await webkit.launch();
  try {
    const page=await browser.newPage();
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto('http://127.0.0.1:8792/');
    await page.locator('#login-passphrase').fill(passphrase);
    await page.locator('#login-submit').click();
    await expect(page.locator('#login-dialog')).toBeHidden();
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.voice?.bridge_ready)).toBe(true);
    // Seed only the written answer; voice fetch, decode, and playback are real.
    await page.evaluate(text=>{
      window.HereIAmCore.state.lastAnswer=text;
      document.querySelector('#answer-text').textContent=text;
      document.querySelector('#answer-card').hidden=false;
      window.updateSpeakButton();
    },text);
    await page.locator('#speak-answer').click();
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.voicePlaying),{timeout:10000}).toBe(true);
    const rms=()=>page.evaluate(()=>{
      const a=window.HereIAmCore.state.audioAnalyser;
      const samples=new Float32Array(a.fftSize);
      a.getFloatTimeDomainData(samples);
      return Math.sqrt(samples.reduce((sum,x)=>sum+x*x,0)/samples.length);
    });
    await expect.poll(rms,{timeout:10000}).toBeGreaterThan(.001);
    await expect.poll(()=>page.evaluate(()=>window.HereIAmCore.state.voicePlaying),{timeout:45000}).toBe(false);
    await expect(page.locator('#answer-text')).toHaveText(text);
    await expect(page.locator('#talk-scene')).toBeVisible();
    if(errors.length)throw Error('Unexpected browser JavaScript error');
    console.log(JSON.stringify({one_click_playback:true,nonzero_web_audio_signal:true,playback_completed:true,
      answer_preserved:true,talk_remained_visible:true,page_error_count:0,physical_speaker_verified:false}));
  } catch(error) {console.error(error.message);process.exitCode=1;}
  finally {await browser.close();}
});
