(() => {
const byId = (id) => document.getElementById(id);
const pageId = globalThis.crypto?.randomUUID?.() || `page-${Date.now()}-${Math.random().toString(16).slice(2)}`;

const state = {
  preferences: null, sessions: [], activeSessionId: null,
  lastQuestion: '', lastAnswer: '', lastMode: '', lastProvider: '',
  cloudConfigured: false, cloudKeySource: 'none', runtimeCloudKeyAllowed: false,
  providerStatus: null, voice: null,
  mediaRecorder: null, mediaStream: null, recordedChunks: [], recordStartedAt: 0,
  recordTimer: null, recordAnimation: null, recordStopRequested: false,
  recordFinalizing: false, recordError: '',
  chatAbort: null, chatGeneration: 0,
  voiceAbort: null, voiceRequestId: null, voiceTimeout: null,
  voicePreparing: false, voiceTimedOut: false, voiceSources: [], voiceNextTime: 0,
  voicePlaying: false, voiceStoppedByUser: false, voicePlaybackTimer: null,
  voicePlaybackStartedAt: 0,
  voicePrerenderAbort: null, voicePrerenderRequestId: null, voicePrerenderText: '',
  voicePrerenderBlob: null, voicePrerenderFetchHeld: false,
  audioContext: null, audioAnalyser: null, audioBufferSource: null, audioAnimation: null,
  speechRecognition: null,
  fetchTaskCount: 0, fetchButtonUntil: 0, fetchGraceTimer: null, fetchHideTimer: null,
  fetchStartedAt: 0, fetchPoint: null, fetchMotionActive: false, fetchLoopRunning: false,
  fetchAnimations: [], fetchSitTimer: null, fetchSitResolve: null,
  activityFetchHeld: false, voiceFetchHeld: false,
  memoryBatch: null, batchWatching: false, batchPollTimer: null,
  speakers: [], activeSpeakerId: null, activeSpeakerReviewId: null,
  pageId, activitySequence: 0, chatRequestId: null,
};

function activity(event, details = {}) {
  state.activitySequence += 1;
  const payload = {
    event,
    page_id: state.pageId,
    sequence: state.activitySequence,
    scene: document.body.dataset.scene || '',
    occurred_at: new Date().toISOString(),
    details,
  };
  fetch('/api/activity-events', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
    keepalive: true,
  }).catch(() => {});
}

async function api(url, options = {}) {
  const animate = performance.now() < state.fetchButtonUntil || state.fetchTaskCount > 0;
  if (animate) window.beginFetchTask();
  try {
    const response = await fetch(url, options);
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json() : await response.text();
    if (!response.ok) throw new Error(typeof data === 'object' ? data.detail || JSON.stringify(data) : data);
    return data;
  } finally {
    if (animate) window.endFetchTask();
  }
}

window.HereIAmCore = Object.freeze({byId, state, api, activity});
})();
