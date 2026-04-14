const ollamaStatus = document.getElementById('ollama-status');
const recordingStatus = document.getElementById('recording-status');
const transcribeStatus = document.getElementById('transcribe-status');
const analyzeStatus = document.getElementById('analyze-status');
const chatAnswer = document.getElementById('chat-answer');

let mediaRecorder = null;
let mediaStream = null;
let recordedChunks = [];
let activeTranscribeJob = null;
let activeAnalyzeJob = null;

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const isJson = response.headers.get('content-type')?.includes('application/json');
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof data === 'object' ? data.detail || JSON.stringify(data) : data;
    throw new Error(message);
  }
  return data;
}

function setProgress(progressEl, processed, total) {
  if (!total || total <= 0) {
    progressEl.value = 0;
    return;
  }
  progressEl.value = Math.round((processed / total) * 100);
}

async function refreshOllamaStatus() {
  try {
    const data = await api('/api/ollama/status');
    ollamaStatus.textContent = `Control: ${data.control.status || 'unknown'} | API reachable: ${data.api_reachable} | Chat model: ${data.chat_model} | Embeddings: ${data.embedding_model}`;
  } catch (err) {
    ollamaStatus.textContent = `Unable to read Ollama status: ${err.message}`;
  }
}

async function startOllama() {
  ollamaStatus.textContent = 'Starting Ollama…';
  try {
    const data = await api('/api/ollama/start', { method: 'POST' });
    ollamaStatus.textContent = data.detail || 'Ollama start requested';
    setTimeout(refreshOllamaStatus, 2000);
  } catch (err) {
    ollamaStatus.textContent = `Start failed: ${err.message}`;
  }
}

async function stopOllama() {
  ollamaStatus.textContent = 'Stopping Ollama…';
  try {
    const data = await api('/api/ollama/stop', { method: 'POST' });
    ollamaStatus.textContent = data.detail || 'Ollama stop requested';
    setTimeout(refreshOllamaStatus, 1500);
  } catch (err) {
    ollamaStatus.textContent = `Stop failed: ${err.message}`;
  }
}

async function startRecording() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : '';
    mediaRecorder = new MediaRecorder(mediaStream, mimeType ? { mimeType } : undefined);
    recordedChunks = [];
    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    };
    mediaRecorder.onstop = uploadRecording;
    mediaRecorder.start();
    recordingStatus.textContent = 'Recording in progress…';
    document.getElementById('record-start').disabled = true;
    document.getElementById('record-pause').disabled = false;
    document.getElementById('record-stop').disabled = false;
  } catch (err) {
    recordingStatus.textContent = `Unable to access microphone: ${err.message}`;
  }
}

function togglePause() {
  const pauseButton = document.getElementById('record-pause');
  if (!mediaRecorder) return;
  if (mediaRecorder.state === 'recording') {
    mediaRecorder.pause();
    pauseButton.textContent = 'Resume Recording';
    recordingStatus.textContent = 'Recording paused';
  } else if (mediaRecorder.state === 'paused') {
    mediaRecorder.resume();
    pauseButton.textContent = 'Pause Recording';
    recordingStatus.textContent = 'Recording resumed';
  }
}

function stopRecording() {
  if (!mediaRecorder) return;
  recordingStatus.textContent = 'Stopping and saving recording…';
  mediaRecorder.stop();
  mediaStream?.getTracks().forEach((track) => track.stop());
  document.getElementById('record-pause').disabled = true;
  document.getElementById('record-stop').disabled = true;
}

async function uploadRecording() {
  try {
    const blob = new Blob(recordedChunks, { type: recordedChunks[0]?.type || 'audio/webm' });
    const form = new FormData();
    form.append('file', blob, 'browser-recording.webm');
    const title = document.getElementById('record-title').value.trim();
    if (title) form.append('title', title);
    const data = await api('/api/recordings/upload', { method: 'POST', body: form });
    recordingStatus.textContent = `${data.message}. Session: ${data.session_id}`;
  } catch (err) {
    recordingStatus.textContent = `Upload failed: ${err.message}`;
  } finally {
    mediaRecorder = null;
    mediaStream = null;
    recordedChunks = [];
    document.getElementById('record-start').disabled = false;
    document.getElementById('record-pause').disabled = true;
    document.getElementById('record-stop').disabled = true;
    document.getElementById('record-pause').textContent = 'Pause Recording';
  }
}

async function pollJob(jobId, statusEl, progressEl) {
  try {
    const job = await api(`/api/jobs/${jobId}`);
    const total = job.total || 0;
    const processed = job.processed || 0;
    statusEl.textContent = `${job.message}${job.current_file ? ` | File: ${job.current_file}` : ''}${total ? ` | ${processed} of ${total}` : ''}`;
    setProgress(progressEl, processed, total);
    if (!job.completed) {
      setTimeout(() => pollJob(jobId, statusEl, progressEl), 1500);
    } else {
      statusEl.textContent = `${job.message}${job.result ? ` | Result: ${JSON.stringify(job.result)}` : ''}`;
      setProgress(progressEl, total || 1, total || 1);
    }
  } catch (err) {
    statusEl.textContent = `Job status failed: ${err.message}`;
  }
}

async function startTranscription() {
  transcribeStatus.textContent = 'Queueing transcription job…';
  document.getElementById('transcribe-progress').value = 0;
  try {
    const job = await api('/api/transcribe/start', { method: 'POST' });
    activeTranscribeJob = job.id;
    pollJob(activeTranscribeJob, transcribeStatus, document.getElementById('transcribe-progress'));
  } catch (err) {
    transcribeStatus.textContent = `Could not start transcription: ${err.message}`;
  }
}

async function startAnalysis() {
  analyzeStatus.textContent = 'Queueing analysis job…';
  document.getElementById('analyze-progress').value = 0;
  try {
    const job = await api('/api/analyze/start', { method: 'POST' });
    activeAnalyzeJob = job.id;
    pollJob(activeAnalyzeJob, analyzeStatus, document.getElementById('analyze-progress'));
  } catch (err) {
    analyzeStatus.textContent = `Could not start analysis: ${err.message}`;
  }
}

async function sendChat() {
  const question = document.getElementById('chat-question').value.trim();
  if (!question) {
    chatAnswer.textContent = 'Enter a question first';
    return;
  }
  chatAnswer.textContent = 'Thinking…';
  try {
    const data = await api('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    chatAnswer.textContent = data.answer;
  } catch (err) {
    chatAnswer.textContent = `Chat failed: ${err.message}`;
  }
}

document.getElementById('ollama-start').addEventListener('click', startOllama);
document.getElementById('ollama-stop').addEventListener('click', stopOllama);
document.getElementById('ollama-refresh').addEventListener('click', refreshOllamaStatus);
document.getElementById('record-start').addEventListener('click', startRecording);
document.getElementById('record-pause').addEventListener('click', togglePause);
document.getElementById('record-stop').addEventListener('click', stopRecording);
document.getElementById('transcribe-start').addEventListener('click', startTranscription);
document.getElementById('analyze-start').addEventListener('click', startAnalysis);
document.getElementById('chat-send').addEventListener('click', sendChat);

refreshOllamaStatus();
