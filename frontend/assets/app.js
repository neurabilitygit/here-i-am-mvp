const API = 'http://localhost:8080/api';

let mediaRecorder = null;
let recordChunks = [];
let currentSessionId = null;
let isPaused = false;
let activeTranscribeJob = null;
let activeAnalysisJob = null;

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `Request failed: ${res.status}`);
  return data;
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function setMeter(id, percent) {
  document.getElementById(id).style.width = `${Math.max(0, Math.min(100, percent))}%`;
}

function logBox(id, message) {
  setText(id, typeof message === 'string' ? message : JSON.stringify(message, null, 2));
}

async function refreshOllama() {
  try {
    const data = await api('/ollama/status');
    logBox('ollama-status', JSON.stringify(data, null, 2));
  } catch (err) {
    logBox('ollama-status', String(err));
  }
}

async function ollamaAction(action) {
  try {
    const data = await api(`/ollama/${action}`, { method: 'POST' });
    logBox('ollama-status', JSON.stringify(data, null, 2));
  } catch (err) {
    logBox('ollama-status', String(err));
  }
}

async function startRecording() {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') return;
  const started = await api('/record/start', { method: 'POST' });
  currentSessionId = started.session_id;
  setText('record-session', currentSessionId);
  setText('record-state', 'Recording');
  setMeter('record-meter', 10);
  logBox('record-log', `Session created at ${started.session_dir}`);

  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
  recordChunks = [];
  mediaRecorder.ondataavailable = event => {
    if (event.data && event.data.size > 0) recordChunks.push(event.data);
  };
  mediaRecorder.onstop = async () => {
    const blob = new Blob(recordChunks, { type: 'audio/webm' });
    const formData = new FormData();
    formData.append('session_id', currentSessionId);
    formData.append('audio', blob, 'capture.webm');
    logBox('record-log', 'Uploading audio and converting to FLAC...');
    try {
      const saved = await api('/record/stop', { method: 'POST', body: formData });
      logBox('record-log', JSON.stringify(saved, null, 2));
      setText('record-state', 'Saved');
      setMeter('record-meter', 100);
      await refreshTranscribeSummary();
    } catch (err) {
      logBox('record-log', String(err));
      setText('record-state', 'Error');
    }
    stream.getTracks().forEach(track => track.stop());
  };
  mediaRecorder.start(1000);
}

async function togglePauseRecording() {
  if (!mediaRecorder) return;
  if (!isPaused) {
    mediaRecorder.pause();
    isPaused = true;
    setText('record-state', 'Paused');
    setMeter('record-meter', 45);
    const fd = new FormData();
    fd.append('session_id', currentSessionId);
    await api('/record/pause', { method: 'POST', body: fd });
    logBox('record-log', 'Recording paused');
  } else {
    mediaRecorder.resume();
    isPaused = false;
    setText('record-state', 'Recording');
    setMeter('record-meter', 60);
    const fd = new FormData();
    fd.append('session_id', currentSessionId);
    await api('/record/resume', { method: 'POST', body: fd });
    logBox('record-log', 'Recording resumed');
  }
}

function stopRecording() {
  if (!mediaRecorder || mediaRecorder.state === 'inactive') return;
  setText('record-state', 'Stopping');
  setMeter('record-meter', 80);
  mediaRecorder.stop();
  isPaused = false;
}

async function refreshTranscribeSummary() {
  try {
    const data = await api('/transcribe/summary');
    setText('transcribe-count', String(data.count));
    logBox('transcribe-log', JSON.stringify(data, null, 2));
  } catch (err) {
    logBox('transcribe-log', String(err));
  }
}

async function refreshAnalysisSummary() {
  try {
    const data = await api('/analysis/summary');
    setText('analysis-count', String(data.count));
    logBox('analysis-log', JSON.stringify(data, null, 2));
  } catch (err) {
    logBox('analysis-log', String(err));
  }
}

async function startTranscribeJob() {
  try {
    const data = await api('/transcribe/start', { method: 'POST' });
    activeTranscribeJob = data.job_id;
    logBox('transcribe-log', `${data.detail}\nJob: ${data.job_id}`);
    pollJob(activeTranscribeJob, 'transcribe');
  } catch (err) {
    logBox('transcribe-log', String(err));
  }
}

async function startAnalysisJob() {
  try {
    const data = await api('/analysis/start', { method: 'POST' });
    activeAnalysisJob = data.job_id;
    logBox('analysis-log', `${data.detail}\nJob: ${data.job_id}`);
    pollJob(activeAnalysisJob, 'analysis');
  } catch (err) {
    logBox('analysis-log', String(err));
  }
}

async function pollJob(jobId, type) {
  const logId = type === 'transcribe' ? 'transcribe-log' : 'analysis-log';
  const fileId = type === 'transcribe' ? 'transcribe-file' : 'analysis-file';
  const meterId = type === 'transcribe' ? 'transcribe-meter' : 'analysis-meter';
  const refreshSummary = type === 'transcribe' ? refreshTranscribeSummary : refreshAnalysisSummary;

  const timer = setInterval(async () => {
    try {
      const job = await api(`/jobs/${jobId}`);
      const progress = job.progress || {};
      setText(fileId, progress.filename || 'None');
      setMeter(meterId, progress.percent || 0);
      logBox(logId, JSON.stringify(job, null, 2));
      if (job.status === 'complete' || job.status === 'failed') {
        clearInterval(timer);
        await refreshSummary();
      }
    } catch (err) {
      clearInterval(timer);
      logBox(logId, String(err));
    }
  }, 2000);
}

async function askChat() {
  const question = document.getElementById('chat-question').value.trim();
  if (!question) return;
  logBox('chat-answer', 'Thinking...');
  try {
    const data = await api('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    logBox('chat-answer', data.answer || 'No answer returned');
  } catch (err) {
    logBox('chat-answer', String(err));
  }
}

document.getElementById('btn-check-ollama').addEventListener('click', refreshOllama);
document.getElementById('btn-start-ollama').addEventListener('click', () => ollamaAction('start'));
document.getElementById('btn-stop-ollama').addEventListener('click', () => ollamaAction('stop'));
document.getElementById('btn-record-start').addEventListener('click', startRecording);
document.getElementById('btn-record-pause').addEventListener('click', togglePauseRecording);
document.getElementById('btn-record-stop').addEventListener('click', stopRecording);
document.getElementById('btn-refresh-transcribe').addEventListener('click', refreshTranscribeSummary);
document.getElementById('btn-start-transcribe').addEventListener('click', startTranscribeJob);
document.getElementById('btn-refresh-analysis').addEventListener('click', refreshAnalysisSummary);
document.getElementById('btn-start-analysis').addEventListener('click', startAnalysisJob);
document.getElementById('btn-chat-ask').addEventListener('click', askChat);

refreshOllama();
refreshTranscribeSummary();
refreshAnalysisSummary();
