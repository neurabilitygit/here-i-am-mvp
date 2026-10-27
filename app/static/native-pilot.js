/* Loaded only by the explicitly opted-in isolated iPhone pilot wrapper. */
(() => {
  const text = 'This is a local voice test for Here I Am. My recorded voice is being used on this Mac, and the complete answer is ready before playback begins.';
  const panel = document.createElement('section');
  panel.id = 'native-pilot-panel';
  panel.setAttribute('aria-label', 'Private iPhone test');
  panel.style.cssText = 'margin:100px 20px 12px;padding:18px;border:2px solid #f5ce78;border-radius:18px;background:#211d37;color:white;position:relative;z-index:2';
  const label = document.createElement('p');
  label.textContent = 'Private test copy — recordings here do not change your main library. Questions and memory processing are off for this test.';
  const button = document.createElement('button');
  button.id = 'pilot-load-voice';
  button.type = 'button';
  button.textContent = 'Load voice test';
  button.style.cssText = 'padding:14px 20px;border-radius:14px;font-size:20px;background:#f5ce78;color:#171328';
  const status = document.createElement('p');
  status.setAttribute('role', 'status');
  panel.append(label, button, status);
  document.body.prepend(panel);
  button.addEventListener('click', async () => {
    button.disabled = true;
    status.textContent = 'Loading the complete voice file…';
    try {
      const response = await fetch('/api/pilot/voice-sample');
      if (response.status === 401) document.dispatchEvent(new CustomEvent('here-i-am:auth-required'));
      if (!response.ok) throw new Error('Sign in to the private test, then try again.');
      const blob = await response.blob();
      if (!blob.size) throw new Error('The test voice file is empty.');
      window.stopSpeaking();
      window.cancelVoicePrerender();
      const state = window.HereIAmCore.state;
      state.chatGeneration += 1;
      state.lastAnswer = text;
      state.lastQuestion = 'Local voice playback test';
      state.lastProvider = 'memory';
      state.voicePrerenderText = text;
      state.voicePrerenderGeneration = state.chatGeneration;
      state.voicePrerenderBlob = blob;
      document.querySelector('#answer-text').textContent = text;
      document.querySelector('#answer-card').hidden = false;
      document.querySelector('#talk-provider-badge').textContent = 'Local cloned-voice test';
      document.querySelector('#answer-card').classList.add('complete');
      document.querySelector('#answer-provenance').hidden = true;
      window.showScene('talk', 'pilot_voice_test');
      document.querySelector('#chat-question').blur();
      window.updateSpeakButton();
      status.textContent = 'Ready. Press Ready — Play below to hear the complete test.';
      document.querySelector('#speak-answer').scrollIntoView({block:'center',behavior:'smooth'});
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
})();
