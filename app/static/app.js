const {byId, state, api} = window.HereIAmCore;

function showFetchCompanion() {
  const companion = byId('fetch-companion');
  window.clearTimeout(state.fetchHideTimer);
  if (typeof companion.showPopover === 'function') {
    if (companion.matches(':popover-open')) companion.hidePopover();
    companion.showPopover();
  } else {
    companion.hidden = false;
  }
  companion.classList.remove('is-finishing');
  window.requestAnimationFrame(() => companion.classList.add('is-active'));
  if (!state.fetchStartedAt) state.fetchStartedAt = performance.now();
  startFetchMotion();
}

function clamp(value, minimum, maximum) { return Math.min(maximum, Math.max(minimum, value)); }

function initialFetchPoint() {
  return {x: Math.round(window.innerWidth * .12), y: Math.round(window.innerHeight * .76)};
}

function randomFetchPoint(origin) {
  const marginX = clamp(window.innerWidth * .09, 42, 120);
  const top = clamp(window.innerHeight * .16, 90, 170);
  const bottom = clamp(window.innerHeight * .16, 90, 150);
  const maximumX = Math.max(marginX + 1, window.innerWidth - marginX);
  const maximumY = Math.max(top + 1, window.innerHeight - bottom);
  const minimumDistance = Math.min(330, Math.max(150, Math.hypot(window.innerWidth, window.innerHeight) * .24));
  let candidate = origin;
  for (let attempt = 0; attempt < 18; attempt += 1) {
    candidate = {
      x: marginX + Math.random() * (maximumX - marginX),
      y: top + Math.random() * (maximumY - top),
    };
    if (Math.hypot(candidate.x - origin.x, candidate.y - origin.y) >= minimumDistance) break;
  }
  return candidate;
}

function dogPlacement(point) {
  const dog = document.querySelector('.fetch-dog');
  const width = dog.offsetWidth || clamp(window.innerWidth * .25, 180, 350);
  const height = dog.offsetHeight || width * .56;
  return {
    x: clamp(point.x - width * .57, 8, window.innerWidth - width - 8),
    y: clamp(point.y - height * .68, 55, window.innerHeight - height - 18),
    scale: .66 + clamp(point.y / window.innerHeight, .15, .85) * .34,
  };
}

function placeFetchActors(point) {
  const ball = document.querySelector('.fetch-ball');
  const dog = document.querySelector('.fetch-dog');
  const dogPoint = dogPlacement(point);
  ball.style.left = `${point.x}px`; ball.style.top = `${point.y}px`; ball.style.transform = '';
  dog.style.left = `${dogPoint.x}px`; dog.style.top = `${dogPoint.y}px`; dog.style.transform = `scale(${dogPoint.scale})`;
}

function setFetchDogPose(pose) {
  document.querySelector('.fetch-dog').dataset.pose = pose;
}

function waitForFetchSit(duration = 1150) {
  return new Promise((resolve) => {
    state.fetchSitResolve = resolve;
    state.fetchSitTimer = window.setTimeout(() => {
      state.fetchSitTimer = null;
      state.fetchSitResolve = null;
      resolve();
    }, duration);
  });
}

async function animateFetchCycle(origin, target) {
  const ball = document.querySelector('.fetch-ball');
  const dog = document.querySelector('.fetch-dog');
  const startDog = dogPlacement(origin); const endDog = dogPlacement(target);
  const dx = target.x - origin.x; const dy = target.y - origin.y;
  const dogDx = endDog.x - startDog.x; const dogDy = endDog.y - startDog.y;
  const direction = dogDx < 0 ? -1 : 1;
  const arc = Math.min(240, 85 + Math.hypot(dx, dy) * .28);
  const arcY = Math.min(dy * .48 - arc, 24 - origin.y);
  const cycleDuration = 4200;
  setFetchDogPose('running');
  placeFetchActors(origin);
  const ballAnimation = ball.animate([
    {transform:'translate3d(0,0,0) rotate(0deg)', offset:0},
    {transform:`translate3d(${dx * .48}px,${arcY}px,0) rotate(${direction * 430}deg)`, offset:.42},
    {transform:`translate3d(${dx}px,${dy}px,0) rotate(${direction * 840}deg)`, offset:.72},
    {transform:`translate3d(${dx}px,${dy - 13}px,0) rotate(${direction * 900}deg)`, offset:.79},
    {transform:`translate3d(${dx}px,${dy}px,0) rotate(${direction * 950}deg)`, offset:1},
  ], {duration:cycleDuration * .58, easing:'cubic-bezier(.24,.08,.58,1)', fill:'forwards'});
  const dogAnimation = dog.animate([
    {transform:`translate3d(0,0,0) scaleX(${direction}) scale(${startDog.scale})`, offset:0},
    {transform:`translate3d(0,0,0) scaleX(${direction}) scale(${startDog.scale})`, offset:.25},
    {transform:`translate3d(${dogDx * .22}px,${dogDy * .22 - 9}px,0) scaleX(${direction}) scale(${startDog.scale + (endDog.scale-startDog.scale)*.22}) rotate(-1deg)`, offset:.42},
    {transform:`translate3d(${dogDx * .48}px,${dogDy * .48 + 4}px,0) scaleX(${direction}) scale(${startDog.scale + (endDog.scale-startDog.scale)*.48}) rotate(1deg)`, offset:.58},
    {transform:`translate3d(${dogDx * .75}px,${dogDy * .75 - 8}px,0) scaleX(${direction}) scale(${startDog.scale + (endDog.scale-startDog.scale)*.75}) rotate(-1deg)`, offset:.74},
    {transform:`translate3d(${dogDx}px,${dogDy}px,0) scaleX(${direction}) scale(${endDog.scale})`, offset:.9},
    {transform:`translate3d(${dogDx}px,${dogDy}px,0) scaleX(${direction}) scale(${endDog.scale})`, offset:1},
  ], {duration:cycleDuration, easing:'linear', fill:'forwards'});
  state.fetchAnimations = [ballAnimation, dogAnimation];
  try { await dogAnimation.finished; } catch (_) { return; }
  if (!state.fetchMotionActive) return;
  state.fetchPoint = target;
  placeFetchActors(target);
  state.fetchAnimations.forEach((animation)=>animation.cancel());
  state.fetchAnimations = [];
  setFetchDogPose('sitting');
  await waitForFetchSit();
}

function startFetchMotion() {
  state.fetchMotionActive = true;
  if (state.fetchLoopRunning) return;
  state.fetchLoopRunning = true;
  if (!state.fetchPoint) state.fetchPoint = initialFetchPoint();
  if (document.body.classList.contains('reduce-motion')) { placeFetchActors(state.fetchPoint); state.fetchLoopRunning = false; return; }
  (async()=>{
    while (state.fetchMotionActive) {
      const origin = state.fetchPoint || initialFetchPoint();
      const target = randomFetchPoint(origin);
      await animateFetchCycle(origin, target);
    }
    state.fetchLoopRunning = false;
  })();
}

function stopFetchMotion() {
  state.fetchMotionActive = false;
  state.fetchAnimations.forEach((animation)=>animation.cancel());
  state.fetchAnimations = [];
  window.clearTimeout(state.fetchSitTimer);
  state.fetchSitTimer = null;
  if (state.fetchSitResolve) state.fetchSitResolve();
  state.fetchSitResolve = null;
}

function hideFetchCompanion() {
  if (state.fetchTaskCount > 0) return;
  const companion = byId('fetch-companion');
  const delay = Math.max(0, 420 - (performance.now() - state.fetchStartedAt));
  window.clearTimeout(state.fetchHideTimer);
  state.fetchHideTimer = window.setTimeout(() => {
    if (state.fetchTaskCount > 0) return;
    companion.classList.remove('is-active');
    companion.classList.add('is-finishing');
    state.fetchHideTimer = window.setTimeout(() => {
      if (state.fetchTaskCount > 0) return;
      if (typeof companion.hidePopover === 'function') {
        if (companion.matches(':popover-open')) companion.hidePopover();
      } else {
        companion.hidden = true;
      }
      companion.classList.remove('is-finishing');
      state.fetchStartedAt = 0;
      stopFetchMotion();
    }, 300);
  }, delay);
}

function beginFetchTask() {
  state.fetchTaskCount += 1;
  window.clearTimeout(state.fetchGraceTimer);
  showFetchCompanion();
}

function endFetchTask() {
  state.fetchTaskCount = Math.max(0, state.fetchTaskCount - 1);
  if (!state.fetchTaskCount) hideFetchCompanion();
}

function pulseFetchCompanion() {
  state.fetchButtonUntil = performance.now() + 900;
  showFetchCompanion();
  window.clearTimeout(state.fetchGraceTimer);
  state.fetchGraceTimer = window.setTimeout(() => {
    if (!state.fetchTaskCount) hideFetchCompanion();
  }, 850);
}

function setPresence(label, avatarState = 'resting') {
  byId('presence-status').textContent = label;
  document.body.dataset.avatarState = avatarState;
}

function showScene(name) {
  document.body.dataset.scene = name;
  document.querySelectorAll('[data-scene-panel]').forEach((panel) => {
    const active = panel.dataset.scenePanel === name;
    panel.hidden = !active;
    panel.classList.toggle('active', active);
  });
  document.querySelectorAll('[data-go]').forEach((button) => button.classList.toggle('active', button.dataset.go === name));
  if (name === 'memories') Promise.all([refreshLibrary(), refreshMemoryQueue()]);
  if (name === 'talk') byId('chat-question').focus();
  else window.requestAnimationFrame(() => byId(`${name}-title`)?.focus());
}

function setActivity(visible, title = '', detail = '') {
  const veil = byId('activity-veil');
  veil.hidden = !visible;
  if (title) byId('activity-title').textContent = title;
  if (detail) byId('activity-detail').textContent = detail;
  if (visible && !state.activityFetchHeld) {
    state.activityFetchHeld = true;
    beginFetchTask();
  } else if (!visible && state.activityFetchHeld) {
    state.activityFetchHeld = false;
    endFetchTask();
  }
}

function applyPreferences() {
  const p = state.preferences;
  if (!p) return;
  document.body.dataset.textSize = p.text_scale;
  document.body.classList.toggle('reduce-motion', p.reduce_motion);
  document.body.classList.toggle('high-contrast', p.high_contrast);
  const avatar = p.avatar;
  document.body.dataset.skin = avatar.skin;
  document.body.dataset.hair = avatar.hair;
  document.body.dataset.clothing = avatar.clothing;
  document.body.dataset.backdrop = avatar.backdrop;
  document.body.classList.toggle('avatar-glasses', avatar.glasses);
  byId('portrait-name').textContent = avatar.name || 'Here I Am';
  byId('setting-text-size').value = p.text_scale;
  byId('setting-motion').checked = p.reduce_motion;
  byId('setting-contrast').checked = p.high_contrast;
  byId('setting-auto-speak').checked = p.auto_speak;
  byId('setting-pre-render-voice').checked = Boolean(p.pre_render_voice);
  byId('setting-provider').value = p.provider;
  byId('setting-cloud-model').value = p.cloud_model;
  byId('setting-fidelity').value = p.fidelity;
  byId('avatar-name').value = avatar.name;
  byId('avatar-backdrop').value = avatar.backdrop;
  renderTalkProviderBadge(p.provider);
  toggleCloudFields();
}

function renderTalkProviderBadge(provider) {
  const badge = byId('talk-provider-badge');
  const selected = provider || state.preferences?.provider || 'local';
  badge.dataset.provider = selected;
  badge.textContent = selected === 'memory'
    ? 'No recorded answer'
    : selected === 'openai' ? 'Best answer · OpenAI' : 'Private answer · Local Gemma';
}

async function loadExperience() {
  const [result, providerStatus] = await Promise.all([api('/api/experience'), api('/api/providers/status')]);
  state.cloudConfigured = result.cloud_configured;
  state.cloudKeySource = result.cloud_key_source;
  state.runtimeCloudKeyAllowed = Boolean(result.runtime_cloud_key_allowed);
  state.providerStatus = providerStatus;
  state.preferences = result.preferences;
  const modelSelect = byId('setting-cloud-model');
  modelSelect.replaceChildren(...result.allowed_cloud_models.map((model) => {
    const option = document.createElement('option');
    option.value = model;
    option.textContent = model === 'gpt-5.4-mini'
      ? 'GPT-5.4 mini — efficient answer'
      : model === 'gpt-5.4' ? 'GPT-5.4 — highest quality' : model;
    return option;
  }));
  applyPreferences();
  renderProviderStatus();
  if (!state.preferences.onboarding_complete) byId('onboarding-dialog').showModal();
}

function renderProviderStatus() {
  const selected = byId('setting-provider').value;
  const status = state.providerStatus;
  const note = byId('provider-note');
  const readiness = byId('provider-readiness');
  if (selected === 'openai') {
    note.textContent = state.cloudConfigured
      ? 'Best-answer mode sends the current question, selected memory excerpts, and a short derived speaking-style profile to OpenAI.'
      : 'Best-answer mode is unavailable until an API key is configured by the operator.';
    readiness.textContent = state.cloudConfigured ? '● OpenAI is configured' : '○ OpenAI needs configuration';
    readiness.dataset.ready = state.cloudConfigured ? 'true' : 'false';
  } else {
    const ready = Boolean(status?.local_ready);
    note.textContent = 'Private mode keeps answer generation on this Mac. It may take longer.';
    readiness.textContent = ready ? `● ${status.local_model} is ready` : `○ ${status?.local_model || 'Local Gemma'} is not ready`;
    readiness.dataset.ready = ready ? 'true' : 'false';
  }
}

function collectPreferences() {
  const p = structuredClone(state.preferences);
  p.text_scale = byId('setting-text-size').value;
  p.reduce_motion = byId('setting-motion').checked;
  p.high_contrast = byId('setting-contrast').checked;
  p.auto_speak = byId('setting-auto-speak').checked;
  p.pre_render_voice = byId('setting-pre-render-voice').checked;
  p.provider = byId('setting-provider').value;
  p.cloud_model = byId('setting-cloud-model').value || 'gpt-5.4-mini';
  p.fidelity = byId('setting-fidelity').value;
  return p;
}

async function saveSettings(close = true) {
  const status = byId('settings-status');
  status.textContent = 'Saving…';
  try {
    state.preferences = collectPreferences();
    const result = await api('/api/experience', {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({preferences: state.preferences, cloud_api_key: byId('setting-cloud-key').value || null}),
    });
    state.preferences = result.preferences;
    state.cloudConfigured = result.cloud_configured;
    state.cloudKeySource = result.cloud_key_source;
    byId('setting-cloud-key').value = '';
    state.providerStatus = await api('/api/providers/status');
    applyPreferences();
    renderProviderStatus();
    status.textContent = `Saved. ${state.preferences.provider === 'openai' ? 'Best answer' : 'Private answer'} is selected.`;
    if (close) window.setTimeout(() => byId('settings-dialog').close(), 350);
  } catch (error) { status.textContent = error.message; }
}

async function saveProviderSelection() {
  const status = byId('settings-status');
  const selected = byId('setting-provider').value;
  const previous = state.preferences.provider;
  toggleCloudFields();
  status.textContent = `Switching to ${selected === 'openai' ? 'Best answer' : 'Private answer'}…`;
  try {
    const preferences = structuredClone(state.preferences);
    preferences.provider = selected;
    preferences.cloud_model = byId('setting-cloud-model').value || 'gpt-5.4-mini';
    const result = await api('/api/experience', {
      method: 'PUT', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({preferences}),
    });
    state.preferences = result.preferences;
    state.cloudConfigured = result.cloud_configured;
    state.cloudKeySource = result.cloud_key_source;
    state.providerStatus = await api('/api/providers/status');
    renderProviderStatus();
    renderTalkProviderBadge(state.preferences.provider);
    status.textContent = `${state.preferences.provider === 'openai' ? 'Best answer' : 'Private answer'} is now selected.`;
  } catch (error) {
    byId('setting-provider').value = previous;
    toggleCloudFields();
    status.textContent = error.message;
  }
}

function toggleCloudFields() {
  const cloud = byId('setting-provider').value === 'openai';
  byId('cloud-model-label').hidden = !cloud;
  byId('cloud-key-label').hidden = !cloud || state.cloudKeySource === 'environment' || !state.runtimeCloudKeyAllowed;
  renderProviderStatus();
}

async function saveAvatar() {
  state.preferences.avatar = {
    ...state.preferences.avatar,
    name: byId('avatar-name').value.trim() || 'Here I Am',
    backdrop: byId('avatar-backdrop').value,
  };
  applyPreferences();
  await api('/api/experience', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({preferences:state.preferences})});
  byId('avatar-dialog').close();
}

function growQuestionBox() {
  const input = byId('chat-question');
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 150)}px`;
}

function parseSSEBlock(block) {
  let event = 'message';
  const data = [];
  block.split('\n').forEach((line) => {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    if (line.startsWith('data:')) data.push(line.slice(5).trim());
  });
  if (!data.length) return null;
  try { return {event, data: JSON.parse(data.join('\n'))}; } catch { return null; }
}

async function askQuestion(question) {
  const value = question.trim();
  if (!value) return;
  cancelVoicePrerender();
  beginFetchTask();
  state.chatAbort?.abort();
  const generation = ++state.chatGeneration;
  const controller = new AbortController();
  state.chatAbort = controller;
  state.lastQuestion = value;
  state.lastAnswer = '';
  byId('chat-question').value = '';
  growQuestionBox();
  byId('answer-card').hidden = false;
  byId('answer-card').classList.remove('complete');
  byId('answer-text').textContent = '';
  byId('answer-announcement').textContent = '';
  byId('feedback-up').classList.remove('selected');
  byId('speak-answer').disabled = true;
  byId('compare-answer').disabled = true;
  setPresence('Finding the right memories…', 'thinking');
  byId('chat-send').disabled = true;
  let buffer = '';
  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({question:value}), signal: controller.signal,
    });
    if (generation !== state.chatGeneration) return;
    if (!response.ok) throw new Error((await response.json()).detail || 'The answer could not be started');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const {value: chunk, done} = await reader.read();
      if (generation !== state.chatGeneration) { await reader.cancel(); return; }
      if (done) break;
      buffer += decoder.decode(chunk, {stream:true}).replace(/\r\n/g, '\n');
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const parsed = parseSSEBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        if (!parsed) continue;
        if (parsed.event === 'meta') {
          state.lastMode = parsed.data.mode;
          state.lastProvider = parsed.data.provider;
          renderTalkProviderBadge(parsed.data.provider);
          setPresence(
            parsed.data.provider === 'memory'
              ? 'No matching memory was found'
              : parsed.data.provider === 'openai' ? 'Thinking in the cloud…' : 'Thinking here on this Mac…',
            'thinking',
          );
        } else if (parsed.event === 'token') {
          state.lastAnswer += parsed.data.text;
          byId('answer-text').textContent = state.lastAnswer;
          setPresence('Answering…', 'speaking');
        } else if (parsed.event === 'error') throw new Error(parsed.data.detail);
      }
    }
    byId('answer-card').classList.add('complete');
    byId('answer-announcement').textContent = 'Answer ready. The written answer appears above the answer controls.';
    byId('compare-answer').disabled = !state.lastAnswer || !state.cloudConfigured || state.lastProvider === 'memory';
    setPresence('Ready for another question', 'resting');
    if (state.lastProvider === 'memory') updateSpeakButton();
    else if (state.preferences.auto_speak && state.voice?.enabled && state.lastAnswer) await speakAnswer();
    else if (state.preferences.pre_render_voice && state.voice?.enabled && state.lastAnswer) startVoicePrerender();
    else updateSpeakButton();
  } catch (error) {
    if (error.name !== 'AbortError' && generation === state.chatGeneration) {
      byId('answer-text').textContent = `I couldn't answer that just now. ${error.message}`;
      byId('answer-card').classList.add('complete');
      setPresence('Something needs attention', 'resting');
      byId('answer-announcement').textContent = 'The answer could not be completed.';
    }
  } finally {
    if (generation === state.chatGeneration) {
      state.chatAbort = null;
      byId('chat-send').disabled = false;
    }
    endFetchTask();
  }
}

function clearAnswer() {
  state.chatGeneration += 1;
  state.chatAbort?.abort();
  state.chatAbort = null;
  cancelVoicePrerender();
  if (state.voicePreparing || state.voicePlaying) stopSpeaking();
  state.lastQuestion = '';
  state.lastAnswer = '';
  state.lastMode = '';
  state.lastProvider = '';
  byId('answer-text').textContent = '';
  byId('answer-announcement').textContent = '';
  byId('answer-card').classList.remove('complete');
  byId('answer-card').hidden = true;
  byId('answer-card').scrollTop = 0;
  byId('chat-send').disabled = false;
  byId('compare-answer').disabled = true;
  byId('feedback-up').classList.remove('selected');
  renderTalkProviderBadge(state.preferences?.provider);
  updateSpeakButton();
  setPresence('Ready to talk', 'resting');
  byId('chat-question').focus({preventScroll: true});
}

async function compareAnswers() {
  if (!state.lastQuestion || !state.cloudConfigured) return;
  const dialog = byId('benchmark-dialog');
  byId('benchmark-status').textContent = 'Using the same question and retrieved memories for both answers…';
  byId('benchmark-local-answer').textContent = '';
  byId('benchmark-openai-answer').textContent = '';
  byId('compare-answer').disabled = true;
  dialog.showModal();
  try {
    const result = await api('/api/chat/benchmark', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:state.lastQuestion}),
    });
    result.results.forEach((entry) => {
      byId(`benchmark-${entry.provider}-title`).textContent = `${entry.model} · ${entry.elapsed_seconds.toFixed(1)}s`;
      byId(`benchmark-${entry.provider}-answer`).textContent = entry.answer;
    });
    byId('benchmark-status').textContent = `${result.sources.length} memory passages · retrieval ${result.retrieval_seconds.toFixed(1)}s · ${result.mode.toLowerCase()} question`;
  } catch (error) {
    byId('benchmark-status').textContent = error.message;
  } finally {
    byId('compare-answer').disabled = !state.lastAnswer || !state.cloudConfigured;
  }
}

async function sendFeedback(rating) {
  if (!state.lastAnswer) return;
  const reason = rating === 'up' ? 'sounds_like_me' : 'not_my_voice';
  await api('/api/fidelity/feedback', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question:state.lastQuestion, answer:state.lastAnswer, rating, reason, mode:state.lastMode, provider:state.lastProvider})});
  byId(`feedback-${rating}`).classList.add('selected');
}

async function loadVoiceStatus() {
  try {
    state.voice = await api('/api/voice/status');
    const text = state.voice.enabled
      ? `AI voice is on (${state.voice.provider}).${state.voice.bridge_ready || state.voice.provider === 'elevenlabs' ? '' : ' The local voice helper is not running.'}`
      : 'AI voice is off. Answers remain available as text.';
    byId('voice-setting-status').textContent = text;
    byId('voice-revoke-button').hidden = !state.voice.enabled;
    updateSpeakButton();
  } catch (error) { byId('voice-setting-status').textContent = error.message; }
}

function animateAudio() {
  window.cancelAnimationFrame(state.audioAnimation);
  const data = new Uint8Array(state.audioAnalyser.frequencyBinCount);
  const mouth = document.querySelector('.mouth-open');
  const tick = () => {
    if (!state.voicePlaying) return;
    state.audioAnalyser.getByteFrequencyData(data);
    const energy = data.reduce((sum, value) => sum + value, 0) / data.length / 255;
    if (mouth) mouth.style.transform = `scaleY(${1 + energy * 4}) scaleX(${1 - energy * .18})`;
    document.querySelector('.portrait-glow').style.opacity = String(.45 + energy);
    state.audioAnimation = requestAnimationFrame(tick);
  };
  tick();
}

function ensureStreamingAudio() {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) throw new Error('Audio playback is not supported by this browser');
  if (!state.audioContext) {
    state.audioContext = new AudioContext();
    state.audioAnalyser = state.audioContext.createAnalyser();
    state.audioAnalyser.fftSize = 128;
    state.audioAnalyser.connect(state.audioContext.destination);
  }
  return state.audioContext;
}

function ensureBatchAudio() {
  return ensureStreamingAudio();
}

function updateSpeakButton() {
  const button = byId('speak-answer');
  const label = button.querySelector('span:last-child');
  const prerenderPending = Boolean(
    state.voicePrerenderRequestId
    && state.voicePrerenderText
    && state.voicePrerenderText === state.lastAnswer
    && !state.voicePrerenderBlob
  );
  const preparing = prerenderPending || state.voicePreparing;
  const ready = Boolean(state.voicePrerenderText === state.lastAnswer && state.voicePrerenderBlob?.size);
  button.hidden = state.voicePlaying;
  button.disabled = !state.voice?.enabled || !state.lastAnswer || preparing;
  button.setAttribute('aria-label', preparing ? 'Preparing voice' : ready ? 'Ready—play this answer' : 'Prepare and play this answer');
  label.textContent = preparing ? 'Preparing' : ready ? 'Ready—Play' : 'Play';
  const stopButton = byId('stop-speaking');
  if (state.voicePlaying) {
    stopButton.hidden = false;
    stopButton.setAttribute('aria-label', 'Playing — stop speaking');
    stopButton.querySelector('span:last-child').textContent = 'Playing';
  }
}

function cancelVoicePrerender() {
  const requestId = state.voicePrerenderRequestId;
  state.voicePrerenderAbort?.abort();
  if (requestId) fetch(`/api/voice/cancel/${encodeURIComponent(requestId)}`, {method:'POST', keepalive:true}).catch(()=>{});
  state.voicePrerenderAbort = null;
  state.voicePrerenderRequestId = null;
  state.voicePrerenderText = '';
  state.voicePrerenderBlob = null;
  if (state.voicePrerenderFetchHeld) { state.voicePrerenderFetchHeld = false; endFetchTask(); }
  updateSpeakButton();
}

function cancelVoiceOnPageExit() {
  const requestIds = [state.voiceRequestId, state.voicePrerenderRequestId].filter(Boolean);
  requestIds.forEach((requestId) => {
    fetch(`/api/voice/cancel/${encodeURIComponent(requestId)}`, {method:'POST', keepalive:true}).catch(()=>{});
  });
}

async function startVoicePrerender() {
  cancelVoicePrerender();
  const text = state.lastAnswer;
  const requestId = globalThis.crypto?.randomUUID?.() || `voice-preview-${Date.now()}`;
  const controller = new AbortController();
  state.voicePrerenderText = text; state.voicePrerenderRequestId = requestId; state.voicePrerenderAbort = controller;
  state.voicePrerenderFetchHeld = true;
  updateSpeakButton();
  setPresence('Preparing your voice while you read', 'thinking');
  beginFetchTask();
  try {
    const response = await fetch('/api/voice/speak', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text,speed:1,request_id:requestId}),signal:controller.signal});
    if (!response.ok) throw new Error('Background voice preparation did not complete');
    const blob = await response.blob();
    if (state.voicePrerenderText === text && blob.size) {
      state.voicePrerenderBlob = blob;
      setPresence('Voice is ready to play', 'resting');
    }
  } catch (_) {
    // Pre-rendering is optional; Play is re-enabled for a manual retry.
  } finally {
    if (state.voicePrerenderRequestId === requestId) {
      if (!state.voicePrerenderBlob) setPresence('Voice preparation paused — press Play to try again', 'resting');
      state.voicePrerenderAbort=null;
      state.voicePrerenderRequestId=null;
      if (state.voicePrerenderFetchHeld) { state.voicePrerenderFetchHeld=false; endFetchTask(); }
      updateSpeakButton();
    }
  }
}

async function playVoiceBlob(blob) {
  if (!blob?.size) throw new Error('The voice engine returned an empty audio file');
  const context = ensureBatchAudio();
  const audioBuffer = await context.decodeAudioData((await blob.arrayBuffer()).slice(0));
  if (context.state !== 'running') await context.resume();
  if (state.audioBufferSource) {
    state.audioBufferSource.onended = null;
    try { state.audioBufferSource.stop(); } catch (_) {}
  }
  const source = context.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(state.audioAnalyser);
  state.audioBufferSource = source;
  if (state.voiceFetchHeld) { state.voiceFetchHeld = false; endFetchTask(); }
  window.clearTimeout(state.voiceTimeout);
  state.voiceTimeout = null;
  state.voicePreparing = false;
  state.voicePlaying = true;
  source.onended = finishVoicePlayback;
  source.start(0);
  updateSpeakButton();
  setPresence('Playing your completed AI voice recording', 'speaking');
  animateAudio();
}

async function playVoiceFile(response) {
  const blob = await response.blob();
  await playVoiceBlob(blob);
}

function finishVoicePlayback() {
  state.voicePlaying = false;
  state.audioBufferSource = null;
  state.voiceSources = [];
  window.cancelAnimationFrame(state.audioAnimation);
  byId('speak-answer').hidden = false;
  updateSpeakButton();
  byId('stop-speaking').hidden = true;
  const mouth = document.querySelector('.mouth-open');
  if (mouth) mouth.style.transform = '';
  document.querySelector('.portrait-glow').style.opacity = '';
  setPresence('Ready to talk', 'resting');
}

async function speakAnswer() {
  if (!state.lastAnswer || !state.voice?.enabled) return;
  if (
    state.voicePrerenderRequestId
    && state.voicePrerenderText === state.lastAnswer
    && !state.voicePrerenderBlob
  ) {
    updateSpeakButton();
    setPresence('Your voice file is already being prepared', 'thinking');
    return;
  }
  stopSpeaking();
  const context = ensureBatchAudio();
  await context.resume();
  if (state.voicePrerenderText === state.lastAnswer && state.voicePrerenderBlob?.size) {
    await playVoiceBlob(state.voicePrerenderBlob);
    return;
  }
  const requestId = globalThis.crypto?.randomUUID?.() || `voice-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  state.voiceRequestId = requestId;
  state.voiceAbort = new AbortController();
  state.voicePreparing = true;
  state.voiceTimedOut = false;
  state.voiceStoppedByUser = false;
  state.voiceFetchHeld = true;
  beginFetchTask();
  updateSpeakButton();
  byId('stop-speaking').hidden = false;
  byId('stop-speaking').setAttribute('aria-label', 'Cancel voice preparation');
  byId('stop-speaking').querySelector('span:last-child').textContent = 'Cancel';
  setPresence('Preparing voice — you can keep reading or ask another question', 'thinking');
  state.voiceTimeout = window.setTimeout(() => {
    if (state.voicePreparing) setPresence('Your voice is still preparing — the written answer remains available', 'thinking');
  }, 20000);
  try {
    const response = await fetch('/api/voice/speak', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text:state.lastAnswer, speed:1, request_id:requestId}), signal:state.voiceAbort.signal});
    if (response.status === 409) throw new Error('A voice file is already being prepared. Please wait for it to finish.');
    if (!response.ok) throw new Error((await response.json()).detail || 'Voice generation failed');
    await playVoiceFile(response);
  } catch (error) {
    const message = error.name === 'AbortError'
      ? (state.voiceStoppedByUser
          ? 'Voice stopped. The written answer is still ready.'
          : 'Voice preparation canceled. The written answer is still ready.')
      : error.message;
    setPresence(message, 'resting');
    byId('stop-speaking').hidden = true;
    updateSpeakButton();
  } finally {
    if (state.voiceFetchHeld) { state.voiceFetchHeld = false; endFetchTask(); }
    window.clearTimeout(state.voiceTimeout);
    state.voiceTimeout = null;
    state.voicePreparing = false;
    state.voiceAbort = null;
    state.voiceRequestId = null;
    updateSpeakButton();
  }
}

function stopSpeaking() {
  const wasActive = state.voicePreparing || state.voicePlaying;
  const requestId = state.voiceRequestId;
  if (state.voiceFetchHeld) { state.voiceFetchHeld = false; endFetchTask(); }
  if (state.voicePreparing || state.voicePlaying) state.voiceStoppedByUser = true;
  if (state.voicePreparing) state.voiceAbort?.abort();
  state.voiceAbort?.abort();
  if (requestId) fetch(`/api/voice/cancel/${encodeURIComponent(requestId)}`, {method:'POST', keepalive:true}).catch(()=>{});
  state.voiceSources.forEach((source) => { try { source.stop(); } catch (_) {} });
  state.voiceSources = [];
  if (state.audioBufferSource) {
    state.audioBufferSource.onended = null;
    try { state.audioBufferSource.stop(); } catch (_) {}
    state.audioBufferSource.disconnect();
    state.audioBufferSource = null;
  }
  state.voicePlaying = false;
  window.clearTimeout(state.voicePlaybackTimer);
  state.voicePlaybackTimer = null;
  window.cancelAnimationFrame(state.audioAnimation);
  byId('speak-answer').hidden = false;
  updateSpeakButton();
  byId('stop-speaking').hidden = true;
  byId('stop-speaking').setAttribute('aria-label', 'Stop speaking');
  byId('stop-speaking').querySelector('span:last-child').textContent = 'Stop';
  const mouth = document.querySelector('.mouth-open');
  if (mouth) mouth.style.transform = '';
  document.querySelector('.portrait-glow').style.opacity = '';
  setPresence(wasActive ? 'Voice stopped. The written answer is still ready.' : 'Ready to talk', 'resting');
}

function drawIdleWave() {
  const canvas = byId('record-wave');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.strokeStyle = 'rgba(169,139,255,.6)'; ctx.lineWidth = 4; ctx.beginPath();
  for (let x=0;x<canvas.width;x+=8) { const y=canvas.height/2 + Math.sin(x/38)*8; x ? ctx.lineTo(x,y) : ctx.moveTo(x,y); }
  ctx.stroke();
}

function startRecordVisualizer(stream) {
  const AudioContext = window.AudioContext || window.webkitAudioContext;
  if (!AudioContext) return;
  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser(); analyser.fftSize = 256; source.connect(analyser);
  const data = new Uint8Array(analyser.frequencyBinCount);
  const canvas = byId('record-wave'); const ctx = canvas.getContext('2d');
  const draw = () => {
    if (!state.mediaRecorder || state.mediaRecorder.state === 'inactive') { context.close(); return; }
    state.recordAnimation = requestAnimationFrame(draw); analyser.getByteTimeDomainData(data);
    ctx.clearRect(0,0,canvas.width,canvas.height); ctx.strokeStyle='#6ee7df'; ctx.lineWidth=4; ctx.beginPath();
    data.forEach((value,index) => { const x=index/(data.length-1)*canvas.width; const y=value/255*canvas.height; index?ctx.lineTo(x,y):ctx.moveTo(x,y); }); ctx.stroke();
  }; draw();
}

function updateRecordTime() {
  const seconds = Math.floor((Date.now() - state.recordStartedAt) / 1000);
  byId('record-time').textContent = `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;
}

async function startRecording() {
  try {
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) throw new Error('This browser cannot record audio');
    state.mediaStream = await navigator.mediaDevices.getUserMedia({audio:true});
    const isSafari = /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
    const candidates=isSafari?['audio/mp4','audio/webm;codecs=opus','audio/webm']:['audio/webm;codecs=opus','audio/webm','audio/mp4'];
    const mimeType=candidates.find((item)=>MediaRecorder.isTypeSupported(item))||'';
    state.mediaRecorder=new MediaRecorder(state.mediaStream,mimeType?{mimeType}:undefined); state.recordedChunks=[];
    state.recordStopRequested=false; state.recordFinalizing=false; state.recordError='';
    state.mediaRecorder.ondataavailable=(event)=>{
      if(event.data.size){state.recordedChunks.push(event.data);console.info('[recording] audio chunk ready',{bytes:event.data.size,type:event.data.type});}
    };
    state.mediaRecorder.onerror=(event)=>{
      state.recordError=event.error?.message||'The browser stopped the recording unexpectedly';
      console.error('[recording] recorder error',event.error||event);
      if(state.mediaRecorder?.state!=='inactive')state.mediaRecorder.stop();
    };
    state.mediaRecorder.onstop=finalizeRecording;
    state.mediaStream.getAudioTracks().forEach((track)=>{
      track.onended=()=>{
        if(!state.recordStopRequested)byId('recording-status').textContent='The microphone stopped. Saving everything captured so far…';
      };
    });
    if(isSafari&&mimeType.includes('mp4'))state.mediaRecorder.start();else state.mediaRecorder.start(1000);
    console.info('[recording] started',{mimeType:state.mediaRecorder.mimeType||mimeType||'browser-default'});
    state.recordStartedAt=Date.now();
    state.recordTimer=setInterval(updateRecordTime,500); updateRecordTime(); startRecordVisualizer(state.mediaStream);
    byId('record-start').classList.add('active'); byId('record-start').querySelector('span:last-child').textContent='Recording';
    byId('record-start').disabled=true; byId('record-pause').disabled=false; byId('record-stop').disabled=false;
    byId('recording-status').textContent='I am listening. Take your time.'; setPresence('Listening to your memory…','listening');
  } catch(error){byId('recording-status').textContent=error.message;}
}

function pauseRecording(){
  if(!state.mediaRecorder)return;
  if(state.mediaRecorder.state==='recording'){state.mediaRecorder.pause();byId('record-pause').textContent='Continue';byId('recording-status').textContent='Paused.';}
  else if(state.mediaRecorder.state==='paused'){state.mediaRecorder.resume();byId('record-pause').textContent='Pause';byId('recording-status').textContent='Listening again.';}
}

function stopRecording(){
  if(!state.mediaRecorder||state.mediaRecorder.state==='inactive')return;
  state.recordStopRequested=true; clearInterval(state.recordTimer);
  byId('recording-status').textContent='Finishing and saving your memory…'; byId('record-pause').disabled=true; byId('record-stop').disabled=true;
  // Safari delivers its complete MP4 blob asynchronously after stop().
  // Keep the microphone track alive until the recorder's stop event fires.
  state.mediaRecorder.stop();
}

function releaseRecordingStream(){
  state.mediaStream?.getTracks().forEach((track)=>{track.onended=null;track.stop();});
}

async function finalizeRecording(){
  if(state.recordFinalizing)return;
  state.recordFinalizing=true; clearInterval(state.recordTimer); releaseRecordingStream();
  const unexpected=!state.recordStopRequested;
  console.info('[recording] stopped',{unexpected,chunks:state.recordedChunks.length,bytes:state.recordedChunks.reduce((total,chunk)=>total+chunk.size,0)});
  if(unexpected)byId('recording-status').textContent='The microphone stopped. Saving everything captured so far…';
  await uploadRecording({unexpected});
}

async function uploadRecording({unexpected=false}={}){
  try{
    if(!state.recordedChunks.length)throw new Error(state.recordError||'No sound was captured');
    const type=state.recordedChunks[0].type||state.mediaRecorder?.mimeType||'audio/webm'; const form=new FormData();
    form.append('file',new Blob(state.recordedChunks,{type}),type.includes('mp4')?'memory.m4a':'memory.webm');
    const title=byId('record-title').value.trim(); if(title)form.append('title',title);
    await api('/api/recordings/upload',{method:'POST',body:form});
    resetRecorder(); byId('recording-status').textContent=unexpected?'The microphone stopped, but your recording was saved safely.':'Your recording is safe and waiting for the next local batch.'; byId('record-title').value=''; showScene('memories'); await Promise.all([refreshLibrary(),refreshMemoryQueue()]);
  }catch(error){console.error('[recording] save failed',error);byId('recording-status').textContent=`That memory was not saved. ${error.message}`;resetRecorder();}
}

function resetRecorder(){
  clearInterval(state.recordTimer); cancelAnimationFrame(state.recordAnimation); releaseRecordingStream(); state.mediaRecorder=null;state.mediaStream=null;state.recordedChunks=[];
  state.recordStopRequested=false;state.recordFinalizing=false;state.recordError='';
  byId('record-start').disabled=false;byId('record-start').classList.remove('active');byId('record-start').querySelector('span:last-child').textContent='Record';
  byId('record-pause').disabled=true;byId('record-stop').disabled=true;byId('record-pause').textContent='Pause';byId('record-time').textContent='00:00';drawIdleWave();setPresence('Ready to talk','resting');
}

async function waitForJob(job, phase){
  while(true){
    const current=await api(`/api/jobs/${job.id}`); const percent=current.total?Math.round(current.processed/current.total*100):0;
    byId('activity-detail').textContent=`${phase} — ${current.message}${current.total?` (${percent}%)`:''}`;
    if(current.completed){if(current.status==='error')throw new Error(current.message);return current;} await new Promise((resolve)=>setTimeout(resolve,1500));
  }
}

function renderMemoryQueue(){
  const queue=state.memoryBatch; if(!queue)return;
  const panel=byId('memory-queue'); const count=queue.queued_recordings;
  const failed=Boolean(!queue.running&&count&&queue.last_job?.status==='error');
  const error=byId('memory-queue-error');
  panel.hidden=!count&&!queue.running; byId('memory-queue-count').textContent=count;
  panel.classList.toggle('has-error',failed);
  byId('memory-queue-title').textContent=queue.running
    ?'The local memory workshop is running'
    :failed
      ?`${count===1?'This recording still needs':'These recordings still need'} preparation`
      :`${count} ${count===1?'recording is':'recordings are'} safely waiting`;
  byId('memory-queue-detail').textContent=queue.running
    ?'The dog will keep fetching while local Gemma prepares every queued memory.'
    :`${queue.awaiting_transcription} waiting to become words · ${queue.ready_for_embedding} ready to connect`;
  error.hidden=!failed;
  error.textContent=failed?'Local Gemma stopped before it could finish organizing the memory. Nothing was lost, and it is safe to try again.':'';
  byId('memory-batch-open').disabled=queue.running||!count;
  byId('memory-batch-open').textContent=queue.running?'Preparing locally…':failed?'Try again':'Prepare all memories';
}

async function refreshMemoryQueue(){
  try{
    state.memoryBatch=await api('/api/memory-batch/status'); renderMemoryQueue();
    if(state.memoryBatch.running&&state.memoryBatch.active_job&&!state.batchWatching) monitorMemoryBatch(state.memoryBatch.active_job);
  }catch(error){byId('library-status').textContent=error.message;}
}

function memoryUploadTitle(file) {
  return file.name.replace(/\.[^.]+$/, '').replace(/[_-]+/g, ' ').trim().slice(0, 160) || 'Imported recording';
}

function isAudioUpload(file) {
  return Boolean(file?.size) && (
    file.type.startsWith('audio/')
    || /\.(wav|mp3|m4a|flac|aac|ogg|opus|webm|mp4)$/i.test(file.name)
  );
}

async function uploadMemoryFiles(fileList) {
  const files = Array.from(fileList || []);
  const status = byId('memory-upload-status');
  const zone = byId('memory-import');
  const choose = byId('memory-upload-choose');
  const valid = files.filter(isAudioUpload);
  status.classList.remove('is-error');
  if (!files.length) return;
  if (!valid.length) {
    status.textContent = 'Please choose a voice recording, such as WAV, M4A, MP3, or FLAC.';
    status.classList.add('is-error');
    return;
  }
  zone.setAttribute('aria-busy', 'true');
  choose.disabled = true;
  beginFetchTask();
  let completed = 0;
  try {
    for (const file of valid) {
      status.textContent = valid.length === 1
        ? `Adding ${file.name}…`
        : `Adding recording ${completed + 1} of ${valid.length}…`;
      const form = new FormData();
      form.append('file', file, file.name);
      form.append('title', memoryUploadTitle(file));
      await api('/api/recordings/upload', {method:'POST', body:form});
      completed += 1;
    }
    const skipped = files.length - valid.length;
    status.textContent = `${completed} ${completed === 1 ? 'recording is' : 'recordings are'} safely queued${skipped ? `; ${skipped} non-audio ${skipped === 1 ? 'file was' : 'files were'} skipped` : ''}.`;
    await Promise.all([refreshLibrary(), refreshMemoryQueue()]);
  } catch (error) {
    status.textContent = completed
      ? `${completed} ${completed === 1 ? 'recording was' : 'recordings were'} saved. The next file could not be added: ${error.message}`
      : `That recording could not be added. ${error.message}`;
    status.classList.add('is-error');
    await Promise.all([refreshLibrary(), refreshMemoryQueue()]);
  } finally {
    zone.setAttribute('aria-busy', 'false');
    zone.classList.remove('is-dragging');
    choose.disabled = false;
    byId('memory-upload-input').value = '';
    endFetchTask();
  }
}

function setupMemoryImport() {
  const zone = byId('memory-import');
  const input = byId('memory-upload-input');
  const openPicker = () => { if (zone.getAttribute('aria-busy') !== 'true') input.click(); };
  byId('memory-upload-choose').addEventListener('click', (event) => { event.stopPropagation(); openPicker(); });
  zone.addEventListener('click', (event) => { if (!event.target.closest('button')) openPicker(); });
  zone.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openPicker(); }
  });
  input.addEventListener('change', () => uploadMemoryFiles(input.files));
  ['dragenter','dragover'].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    if (zone.getAttribute('aria-busy') !== 'true') zone.classList.add('is-dragging');
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  }));
  zone.addEventListener('dragleave', (event) => {
    if (!zone.contains(event.relatedTarget)) zone.classList.remove('is-dragging');
  });
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    zone.classList.remove('is-dragging');
    if (zone.getAttribute('aria-busy') !== 'true') uploadMemoryFiles(event.dataTransfer?.files);
  });
  window.addEventListener('dragover', (event) => {
    if (Array.from(event.dataTransfer?.types || []).includes('Files')) event.preventDefault();
  });
  window.addEventListener('drop', (event) => {
    if (Array.from(event.dataTransfer?.types || []).includes('Files') && !zone.contains(event.target)) event.preventDefault();
  });
}

function openMemoryBatch(){
  if(!state.memoryBatch?.queued_recordings)return;
  const count=state.memoryBatch.queued_recordings;
  byId('memory-batch-explanation').textContent=`${count} ${count===1?'recording':'recordings'} will be transcribed, understood, and embedded only on this Mac. OpenAI will not receive or embed them.`;
  byId('memory-batch-confirm').checked=false;byId('memory-batch-start').disabled=true;byId('memory-batch-dialog-status').textContent='';byId('memory-batch-dialog').showModal();
}

async function startMemoryBatch(){
  if(!byId('memory-batch-confirm').checked)return;
  byId('memory-batch-start').disabled=true;byId('memory-batch-dialog-status').textContent='Starting the local workshop…';
  try{const job=await api('/api/memory-batch/start?confirm=true',{method:'POST'});byId('memory-batch-dialog').close();await monitorMemoryBatch(job);}
  catch(error){byId('memory-batch-dialog-status').textContent=error.message;byId('memory-batch-start').disabled=false;}
}

async function monitorMemoryBatch(job){
  if(state.batchWatching)return;state.batchWatching=true;document.body.classList.add('batch-processing');
  setActivity(true,'Preparing every queued memory','Here I Am is unavailable until local Gemma finishes.');setPresence('Local memory workshop running…','thinking');
  let outcome='';
  try{const finished=await waitForJob(job,'Working locally');if(finished.status==='error')throw new Error(finished.message);outcome='Every queued memory is ready. The local Gemma models have been unloaded.';}
  catch(error){outcome='The recording is safe, but Local Gemma could not finish. Review the highlighted memory workshop and try again.';}
  finally{state.batchWatching=false;document.body.classList.remove('batch-processing');setActivity(false);setPresence('Ready to talk','resting');await Promise.all([refreshLibrary(),refreshMemoryQueue()]);byId('library-status').textContent=outcome;}
}

function formatMemoryDate(sessionId){const match=sessionId.match(/^(\d{4})-(\d{2})-(\d{2})/);if(!match)return'';return new Date(`${match[1]}-${match[2]}-${match[3]}T12:00:00`).toLocaleDateString(undefined,{month:'long',day:'numeric',year:'numeric'});}

function renderMemories(){
  const query=byId('memory-search').value.trim().toLowerCase(); const sessions=state.sessions.filter((item)=>!query||item.title.toLowerCase().includes(query)||item.session_id.toLowerCase().includes(query));
  const cards=sessions.map((session)=>{const button=document.createElement('button');button.type='button';button.className='memory-card';button.setAttribute('aria-label',`${session.title}. ${session.embedded?'Ready to answer questions':'Waiting for local preparation'}.`);
    const date=document.createElement('small');date.textContent=formatMemoryDate(session.session_id);const title=document.createElement('h3');title.textContent=session.title;const status=document.createElement('div');status.className='memory-state';status.title=session.embedded?'Ready to answer questions':'Waiting for the local batch';
    ['recorded','transcribed','embedded'].forEach((key)=>{const dot=document.createElement('span');dot.classList.toggle('ready',session[key]);status.append(dot)});button.append(date,title,status);button.addEventListener('click',()=>openMemory(session.session_id));return button;});
  byId('memory-gallery').replaceChildren(...cards);byId('memory-summary').textContent=`${sessions.length} ${sessions.length===1?'memory':'memories'} in your story`;
}

async function refreshLibrary(){
  try{state.sessions=await api('/api/sessions');renderMemories();byId('library-status').textContent=state.sessions.length?'Choose any memory to read or change its words.':'Your first memory will appear here.';}
  catch(error){byId('library-status').textContent=error.message;}
}

async function openMemory(sessionId){
  try{const session=await api(`/api/sessions/${encodeURIComponent(sessionId)}`);state.activeSessionId=sessionId;byId('memory-dialog-title').textContent=session.title;byId('memory-meta').textContent=`${formatMemoryDate(sessionId)} · ${session.embedded?'Ready for questions':'Waiting for the local batch'}`;byId('memory-transcript').value=session.transcript||'';byId('memory-transcript').disabled=!session.transcript;byId('memory-save').disabled=!session.transcript;byId('memory-export').href=`/api/sessions/${encodeURIComponent(sessionId)}/export`;byId('memory-dialog-status').textContent=session.transcript?'Every save keeps the earlier version safe.':'The words will appear after the local batch.';byId('memory-dialog').showModal();}
  catch(error){byId('library-status').textContent=error.message;}
}

async function saveMemory(){
  if(!state.activeSessionId)return;const transcript=byId('memory-transcript').value.trim();if(!transcript)return;byId('memory-dialog-status').textContent='Saving…';
  try{await api(`/api/sessions/${encodeURIComponent(state.activeSessionId)}/transcript`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({transcript,reason:'reviewed in Living Portrait'})});byId('memory-dialog-status').textContent='Saved. This memory is queued for the next local batch.';await Promise.all([refreshLibrary(),refreshMemoryQueue()]);}
  catch(error){byId('memory-dialog-status').textContent=error.message;}
}

async function openVoiceSetup(){
  byId('voice-dialog-status').textContent='Finding clear recordings…';byId('voice-dialog').showModal();
  try{const candidates=await api('/api/voice/candidates');const options=candidates.map((item)=>{const option=document.createElement('option');option.value=item.session_id;option.textContent=`${formatMemoryDate(item.session_id)} · ${Math.round(item.duration_seconds/60)} minutes · quality ${Math.round(item.score)}%`;return option});byId('voice-candidate').replaceChildren(...options);byId('voice-dialog-status').textContent=candidates.length?'A 15-second reference will be prepared from the recording you choose.':'No suitable recordings were found.';byId('voice-create').disabled=!candidates.length;}
  catch(error){byId('voice-dialog-status').textContent=error.message;}
}

async function createVoice(){
  if(!byId('voice-consent').checked){byId('voice-dialog-status').textContent='Please confirm your right to use this voice.';return;}
  byId('voice-create').disabled=true;byId('voice-dialog-status').textContent='Preparing a private voice reference…';
  try{state.voice=await api('/api/voice/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session_id:byId('voice-candidate').value,confirm_voice_rights:true,provider:byId('voice-provider').value,reference_start_seconds:5,reference_duration_seconds:15})});byId('voice-dialog-status').textContent=state.voice.bridge_ready||state.voice.provider==='elevenlabs'?'Your AI voice is ready.':'The reference is ready. Start the local voice helper to speak.';await loadVoiceStatus();window.setTimeout(()=>byId('voice-dialog').close(),900);}
  catch(error){byId('voice-dialog-status').textContent=error.message;}finally{byId('voice-create').disabled=false;}
}

async function revokeVoice(){if(!window.confirm('Turn off the AI voice and remove its derived reference? Original recordings will stay safe.'))return;state.voice=await api('/api/voice/revoke?delete_reference=true',{method:'POST'});await loadVoiceStatus();}
async function clearVoiceCache(){byId('voice-setting-status').textContent='Clearing prepared voice files…';try{const result=await api('/api/voice/cache/clear',{method:'POST'});state.voicePrerenderBlob=null;byId('voice-setting-status').textContent=result.detail;}catch(error){byId('voice-setting-status').textContent=error.message;}}

function setupSpeechQuestion(){
  const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;if(!Recognition){byId('voice-question').hidden=true;return;}
  const recognition=new Recognition();recognition.lang='en-US';recognition.interimResults=true;
  recognition.onstart=()=>setPresence('Listening to your question…','listening');recognition.onresult=(event)=>{byId('chat-question').value=Array.from(event.results).map((item)=>item[0].transcript).join('');growQuestionBox();};recognition.onend=()=>setPresence('Ready to talk','resting');state.speechRecognition=recognition;
}

async function runReconciliation(){byId('technical-status').textContent='Checking without changing anything…';try{const report=await api('/api/reconciliation');byId('technical-status').textContent=report.issue_count?`${report.issue_count} items need attention. No automatic repairs were made.`:`All ${report.checked_sessions} memories are internally consistent.`;}catch(error){byId('technical-status').textContent=error.message;}}
async function createBackup(){byId('technical-status').textContent='Making a full safety copy…';try{const result=await api('/api/backups/structured',{method:'POST'});byId('technical-status').textContent=`Full safety copy ${result.backup_id} contains ${result.files} files.${result.warning?` ${result.warning}`:''}`;}catch(error){byId('technical-status').textContent=error.message;}}

function bindEvents(){
  window.addEventListener('pagehide',cancelVoiceOnPageExit);
  document.addEventListener('click',(event)=>{const button=event.target.closest('button');if(button&&!button.disabled&&!button.closest('#fetch-companion'))pulseFetchCompanion();},true);
  document.querySelectorAll('[data-go]').forEach((button)=>button.addEventListener('click',()=>showScene(button.dataset.go)));
  byId('home-button').addEventListener('click',()=>showScene('talk'));byId('settings-button').addEventListener('click',()=>byId('settings-dialog').showModal());byId('avatar-button').addEventListener('click',()=>byId('avatar-dialog').showModal());
  byId('text-size-button').addEventListener('click',async()=>{const order=['standard','large','largest'];state.preferences.text_scale=order[(order.indexOf(state.preferences.text_scale)+1)%order.length];applyPreferences();await api('/api/experience',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({preferences:state.preferences})});});
  byId('settings-save').addEventListener('click',()=>saveSettings());byId('setting-provider').addEventListener('change',saveProviderSelection);byId('avatar-save').addEventListener('click',saveAvatar);
  byId('chat-form').addEventListener('submit',(event)=>{event.preventDefault();askQuestion(byId('chat-question').value)});byId('chat-question').addEventListener('input',growQuestionBox);byId('chat-question').addEventListener('keydown',(event)=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();askQuestion(event.currentTarget.value)}});
  document.querySelectorAll('#suggestions button').forEach((button)=>button.addEventListener('click',()=>askQuestion(button.textContent)));
  byId('voice-question').addEventListener('click',()=>state.speechRecognition?.start());byId('speak-answer').addEventListener('click',speakAnswer);byId('stop-speaking').addEventListener('click',stopSpeaking);byId('compare-answer').addEventListener('click',compareAnswers);byId('feedback-up').addEventListener('click',()=>sendFeedback('up'));byId('clear-answer').addEventListener('click',clearAnswer);
  byId('record-start').addEventListener('click',startRecording);byId('record-pause').addEventListener('click',pauseRecording);byId('record-stop').addEventListener('click',stopRecording);
  byId('memory-search').addEventListener('input',renderMemories);byId('memory-save').addEventListener('click',saveMemory);
  setupMemoryImport();
  byId('memory-batch-open').addEventListener('click',openMemoryBatch);byId('memory-batch-close').addEventListener('click',()=>byId('memory-batch-dialog').close());byId('memory-batch-confirm').addEventListener('change',(event)=>{byId('memory-batch-start').disabled=!event.currentTarget.checked;});byId('memory-batch-start').addEventListener('click',startMemoryBatch);
  byId('voice-setup-button').addEventListener('click',openVoiceSetup);byId('voice-create').addEventListener('click',createVoice);byId('voice-cache-clear').addEventListener('click',clearVoiceCache);byId('voice-revoke-button').addEventListener('click',revokeVoice);
  byId('reconcile-run').addEventListener('click',runReconciliation);byId('backup-create').addEventListener('click',createBackup);byId('warm-model').addEventListener('click',async()=>{byId('technical-status').textContent='Warming local AI…';try{await api('/api/providers/local/warm',{method:'POST'});byId('technical-status').textContent='Local AI is warm and ready.';}catch(error){byId('technical-status').textContent=error.message;}});
  byId('onboarding-start').addEventListener('click',async()=>{state.preferences.onboarding_complete=true;await api('/api/experience',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({preferences:state.preferences})});byId('onboarding-dialog').close();});
}

async function initialize(){
  bindEvents();drawIdleWave();setupSpeechQuestion();
  try{await loadExperience();await Promise.all([refreshLibrary(),loadVoiceStatus(),refreshMemoryQueue()]);state.batchPollTimer=window.setInterval(refreshMemoryQueue,10000);if(!state.batchWatching)setPresence('Ready to talk','resting');}
  catch(error){setPresence(`Needs attention: ${error.message}`,'resting');}
}

initialize();
