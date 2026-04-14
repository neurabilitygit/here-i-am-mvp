const API = window.location.origin.replace(':8080', ':8000');
let mediaRecorder = null;
let recordedChunks = [];
let streamRef = null;
let recorderMimeType = '';

async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

function setText(id, text) {
  document.getElementById(id).textContent = text;
}

function setProgress(id, processed, total) {
  const element = document.getElementById(id);
  const pct = total > 0 ? Math.round((processed / total) * 100) : 0;
  element.value = pct;
}

async function refreshOllama() {
  try {
    const data = await api('/api/ollama/status');
    setText('ollama-status', JSON.stringify(data, null, 2));
  } catch (err) {
    setText('ollama-status', String(err));
  }
}

async function startOllama() {
  try {
    const data = await api('/api/ollama/start', { method: 'POST' });
    setText('ollama-status', JSON.stringify(data, null, 2));
  } catch (err) {
    setText('ollama-status', String(err));
  }
}

async function stopOllama() {
  try {
    const data = await api('/api/ollama/stop', { method: 'POST' });
    setText('ollama-status', JSON.stringify(data, null, 2));
  } catch (err) {
    setText('ollama-status', String(err));
  }
}

function chooseMimeType() {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/mp4',
    'audio/ogg;codecs=opus',
  ];
  for (const candidate of candidates) {
    if (window.MediaRecorder && MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }
  return '';
}

async function startRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    return;
  }
  recorderMimeType = chooseMimeType();
  streamRef = await navigator.mediaDevices.getUserMedia({ audio: true });
  recordedChunks = [];
  mediaRecorder = recorderMimeType ? new MediaRecorder(streamRef, { mimeType: recorderMimeType }) : new MediaRecorder(streamRef);
  mediaRecorder.ondataavailable = event => {
    if (event.data && event.data.size > 0) {
      recordedChunks.push(event.data);
    }
  };
  mediaRecorder.onstart = () => {
    setText('recording-state', 'Recording in progress.');
    setText('recording-meta', `Format: ${recorderMimeType || 'browser default'}`);
  };
  mediaRecorder.onpause = () => setText('recording-state', 'Recording paused.');
  mediaRecorder.onresume = () => setText('recording-state', 'Recording resumed.');
  mediaRecorder.onstop = async () => {
    setText('recording-state', 'Saving recording...');
    try {
      const blob = new Blob(recordedChunks, { type: recorderMimeType || 'application/octet-stream' });
      const extension = recorderMimeType.includes('mp4') ? 'm4a' : recorderMimeType.includes('ogg') ? 'ogg' : 'webm';
      const formData = new FormData();
      formData.append('file', blob, `recording.${extension}`);
      formData.append('mime_type', blob.type || recorderMimeType || 'application/octet-stream');
      const response = await fetch(`${API}/api/recordings/save`, { method: 'POST', body: formData });
      const data = await response.json();
      setText('recording-state', 'Recording saved.');
      setText('recording-meta', `Session: ${data.session_id}\nStored: ${data.recording_path}`);
    } catch (err) {
      setText('recording-state', `Save failed: ${err}`);
    } finally {
      if (streamRef) {
        streamRef.getTracks().forEach(t => t.stop());
      }
    }
  };
  mediaRecorder.start(1000);
}

function pauseRecording() {
  if (!mediaRecorder) return;
  if (mediaRecorder.state === 'recording') {
    mediaRecorder.pause();
  } else if (mediaRecorder.state === 'paused') {
    mediaRecorder.resume();
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
  }
}

async function runTranscriptions() {
  await api('/api/transcriptions/run', { method: 'POST' });
  await refreshTranscriptions();
}

async function refreshTranscriptions() {
  const data = await api('/api/transcriptions/status');
  setText('transcribe-status', `${data.status}: ${data.message || ''}`.trim());
  setText('transcribe-file', data.current_file ? `Working on: ${data.current_file} | ${data.processed}/${data.total}` : `${data.processed || 0}/${data.total || 0}`);
  setProgress('transcribe-progress', data.processed || 0, data.total || 0);
}

async function runAnalysis() {
  await api('/api/analysis/run', { method: 'POST' });
  await refreshAnalysis();
}

async function refreshAnalysis() {
  const data = await api('/api/analysis/status');
  setText('analysis-status', `${data.status}: ${data.message || ''}`.trim());
  setText('analysis-file', data.current_file ? `Working on: ${data.current_file} | ${data.processed}/${data.total}` : `${data.processed || 0}/${data.total || 0}`);
  setProgress('analysis-progress', data.processed || 0, data.total || 0);
}

async function sendChat() {
  const question = document.getElementById('chat-question').value.trim();
  if (!question) return;
  setText('chat-answer', 'Thinking...');
  try {
    const data = await api('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    setText('chat-answer', data.answer || 'No answer returned.');
  } catch (err) {
    setText('chat-answer', String(err));
  }
}

function attach() {
  document.getElementById('ollama-start').addEventListener('click', startOllama);
  document.getElementById('ollama-stop').addEventListener('click', stopOllama);
  document.getElementById('ollama-refresh').addEventListener('click', refreshOllama);
  document.getElementById('record-start').addEventListener('click', startRecording);
  document.getElementById('record-pause').addEventListener('click', pauseRecording);
  document.getElementById('record-stop').addEventListener('click', stopRecording);
  document.getElementById('transcribe-run').addEventListener('click', runTranscriptions);
  document.getElementById('transcribe-refresh').addEventListener('click', refreshTranscriptions);
  document.getElementById('analysis-run').addEventListener('click', runAnalysis);
  document.getElementById('analysis-refresh').addEventListener('click', refreshAnalysis);
  document.getElementById('chat-send').addEventListener('click', sendChat);
}

attach();
refreshOllama();
refreshTranscriptions();
refreshAnalysis();
setInterval(refreshTranscriptions, 3000);
setInterval(refreshAnalysis, 3000);
