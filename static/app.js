'use strict';
const $ = (id) => document.getElementById(id);
const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const time = (seconds = 0) => {seconds = Math.max(0, Math.floor(seconds)); const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60; return (h ? `${h}:` : '') + `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;};
const bytes = n => n >= 1024**3 ? `${(n / 1024**3).toFixed(1)} GB` : `${(n / 1024**2).toFixed(n < 1024**2 ? 1 : 0)} MB`;
const colors = [['#c5eeea','#176b70'],['#d6e7ff','#3063a3'],['#fbe5ae','#99661d'],['#e9dcfa','#8354a8'],['#f6d7de','#a44c67'],['#cee8d3','#426c45'],['#fbd6b9','#9b4b14'],['#d1ddff','#5344a5'],['#d5eceb','#356c68'],['#eadccf','#79543c']];
let state, recording, selectedId = localStorage.getItem('audio-recording'), variant = 'original', view = 'transcript', activeSpeaker = null, spectrumStart = 0, spectrumEnd = 0, lastSpectrumKey = '', transcriptHash = '', speakersHash = '', editIndex = -1, modalReturnFocus = null, polling = false, lastJobState = '', sampleEnd = null;
const audio = $('audio');
let activeSampleSpeaker=null,activePlaybackSpeaker=null,clipSelection=null,clipDragging=false,clipDragTrack=null,ignoreTrackClickUntil=0,audioGraph=null;
let draftTheme = localStorage.getItem('audio-theme') || 'light';
document.documentElement.dataset.theme = draftTheme;

async function api(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options, headers: {...(options.body && !(options.body instanceof FormData) ? {'Content-Type': 'application/json'} : {}), ...options.headers}});
  if (!response.ok) {
    let message = await response.text();
    try { const parsed = JSON.parse(message); message = typeof parsed.detail === 'string' ? parsed.detail : 'Check the selected settings.'; } catch {}
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json();
}
function toast(message) { $('toast').textContent = message; $('toast').classList.remove('hidden'); clearTimeout(toast.timer); toast.timer = setTimeout(() => $('toast').classList.add('hidden'), 5500); }
function handleError(error) { toast(error.message || String(error)); }
function busy() { return state?.job.state === 'running'; }
function modalVisible(){return !!document.querySelector('.modal-backdrop:not(.hidden)');}
function setText(element,value){if(element&&element.textContent!==String(value))element.textContent=value;}
function segmentName(segment){return segment.overlap||segment.speaker_id==='overlap'?'Overlap':speakerById(segment.speaker_id)?.name||'Unknown';}
function speakerById(sid) { return recording?.speakers.find(s => s.id === sid); }
function participantCount(){return recording?.speakers.filter(s=>s.identity_status!=='unresolved').length||0;}
function colorFor(sid) { if(sid?.startsWith('unresolved_'))return ['#e7ebee','#75818a'];const idx = recording?.speakers.findIndex(s => s.id === sid) ?? -1; return idx < 0 ? ['#e7ebee','#75818a'] : colors[idx % colors.length]; }
function avatarStyle(sid) { const [bg, color] = colorFor(sid); return `--avatar-bg:${bg};--avatar-color:${color}`; }
function initial(name) { return Array.from(name || '?')[0].toUpperCase(); }
function setTheme(theme) { draftTheme = theme; document.documentElement.dataset.theme = theme; localStorage.setItem('audio-theme', theme); document.querySelectorAll('[data-theme]').forEach(b => { if (b.tagName === 'BUTTON') b.classList.toggle('active', b.dataset.theme === theme); }); }

async function poll() {
  if (polling) return;
  polling = true;
  try {
    state = await api('/api/state');
    if (!localStorage.getItem('audio-theme')) setTheme(state.settings.theme || 'light');
    setText($('storage-footer'),`${bytes(state.disk.free_bytes)} free`);
    if (selectedId && !state.recordings.some(r => r.id === selectedId)) selectedId = null;
    if (!selectedId && state.recordings.length) selectedId = state.recordings[0].id;
    if (selectedId) {
      const polledId = selectedId;
      const next = await api(`/api/recordings/${polledId}`);
      if (polledId !== selectedId) return;
      const changed = JSON.stringify(next) !== JSON.stringify(recording);
      recording = next;
      localStorage.setItem('audio-recording', selectedId);
      if (changed&&!modalVisible()) renderRecording();
    }
    if(!modalVisible()){renderJob();updateButtons();}
    if (!$('settings-backdrop').classList.contains('hidden')) {
      if(!document.querySelector('[data-page="models"]').classList.contains('hidden'))renderModels();
      if(!document.querySelector('[data-page="storage"]').classList.contains('hidden'))renderStorage();
    }
    if (!$('history-backdrop').classList.contains('hidden')) renderHistory();
    $('local-status').classList.remove('connected-error');
  } catch (error) {
    $('local-status').textContent = 'Local server disconnected';
    $('local-status').classList.add('connected-error');
    $('local-substatus').textContent = 'Run Start Nipahut AI Transcriber.cmd to reconnect.';
  } finally { polling = false; }
}

function renderRecording() {
  if (!recording) return;
  $('recording-title').textContent = recording.title;
  const lang = recording.detected_language ? ` · detected: ${recording.detected_language}` : '';
  $('recording-meta').textContent = `${recording.filename}  ·  ${time(recording.duration)}  ·  ${participantCount()} speakers${lang}`;
  $('transcript-summary').textContent = `${recording.segments.length} segments · ${participantCount()} speakers`;
  $('speaker-count').textContent = participantCount();
  $('transcript-badge').classList.toggle('hidden', recording.status !== 'processing');
  document.querySelector('[data-variant="cleaned"]').disabled = !recording.cleaned;
  if (variant === 'cleaned' && !recording.cleaned) variant = 'original';
  if (recording.status !== 'importing' && recording.duration > 0) {
    const src = `/api/recordings/${selectedId}/audio/${variant}`;
    if (audio.getAttribute('src') !== src) { audio.src = src; lastSpectrumKey = ''; sampleEnd = null; }
    $('play-button').disabled = false; $('seek').disabled = false;
    renderSpectrum();
  }
  renderTranscript(); renderSpeakers(); renderActivity(); renderWarnings(); updatePlayback();
}
function renderWarnings() {
  const activeError = state?.job.state === 'error' && (!state.job.recording_id || state.job.recording_id === selectedId);
  const messages = activeError ? [state.job.message] : [...(recording?.warnings || []),...(recording?.audio_edits_pending?['Audio edits affect playback. Reprocess to update the transcript and speaker analysis.']:[])];
  $('alert').classList.toggle('hidden', !messages.length);
  $('alert').classList.toggle('error', !!activeError);
  $('alert').textContent = messages.join(' ');
}
function updateButtons() {
  const running = busy();
  $('import-button').disabled = running;
  $('empty-import')?.toggleAttribute('disabled', running);
  $('process-button').disabled = running || !recording || recording.duration <= 0 || recording.status === 'importing';
  $('process-button').querySelector('span').textContent = recording?.status === 'complete' ? 'Reprocess' : 'Transcribe';
  $('export-button').disabled = running || recording?.status !== 'complete';
  document.querySelectorAll('[data-confirm-speaker],[data-rename-speaker]').forEach(button => { button.disabled = running; });
}
function renderJob() {
  if (!state) return;
  const job = state.job;
  const running = job.state === 'running';
  const relevant = !job.recording_id || job.recording_id === selectedId;
  const labels = {prepare: 'Prepare', clean: 'Clean', transcribe: 'Transcribe', diarize: 'Diarize', names: 'Names', finalize: 'Finalize'};
  const opts = recording?.processing_settings || state.settings;
  const clean = opts.cleanup && (opts.cleanup.denoise || opts.cleanup.dehiss || opts.cleanup.normalize || opts.cleanup.hum !== 'off');
  const stages = ['prepare', ...(clean ? ['clean'] : []), 'transcribe', 'diarize', ...(opts.detect_names ? ['names'] : []), 'finalize'];
  const current = stages.indexOf(job.stage);
  const stepsMarkup = stages.map((stage, i) => `<span class="step ${relevant && running && i === current ? 'active' : relevant && ((running && i < current) || (job.state === 'complete' && job.kind === 'process')) ? 'done' : ''}" data-number="${i+1}">${labels[stage]}</span>${i < stages.length - 1 ? '<span class="step-arrow">›</span>' : ''}`).join('');
  if($('steps').innerHTML!==stepsMarkup)$('steps').innerHTML=stepsMarkup;
  const stageLabel = {prepare:'Preparing audio',clean:'Cleaning audio',transcribe:'Transcribing',diarize:'Diarizing',names:'Reading names',finalize:'Finalizing',download:'Downloading',load:'Loading model',unload:'Unloading model'};
  $('job-label').textContent = running ? (stageLabel[job.stage] || 'Processing') : relevant && job.state === 'error' ? 'Needs attention' : relevant && job.state === 'cancelled' ? 'Cancelled' : recording?.status === 'complete' ? 'Complete' : 'Ready';
  $('job-label').parentElement.title = job.message;
  $('job-label').previousElementSibling.className = running ? 'spinner' : 'status-dot';
  $('progress-track').classList.toggle('indeterminate', running && job.progress === null);
  $('progress-fill').style.width = `${running && job.progress !== null ? Math.round(job.progress * 100) : recording?.status === 'complete' ? 100 : 0}%`;
  $('job-percent').textContent = running && job.progress !== null ? `${Math.round(job.progress * 100)}%` : running ? '…' : recording?.status === 'complete' ? '✓' : '—';
  $('job-percent').title = 'Progress within the current step';
  $('cancel-button').classList.toggle('hidden', !running);
  $('local-status').textContent = running ? 'Processing locally' : recording?.status === 'complete' ? 'Transcript ready' : 'Ready to process locally';
  $('local-substatus').textContent = running ? job.message : 'No cloud connection required';
  if (lastJobState === 'running' && job.state !== 'running') { toast(job.state === 'error' ? job.message : job.state === 'cancelled' ? 'Processing cancelled' : 'Operation complete'); renderWarnings(); }
  lastJobState = job.state;
}

function renderSpectrum(force = false) {
  if (!recording?.duration) return;
  const zoom = Number($('zoom-select').value);
  const duration = recording.duration;
  spectrumStart = zoom ? Math.min(Math.max(0, Math.floor(audio.currentTime / zoom) * zoom), Math.max(0, duration - zoom)) : 0;
  spectrumEnd = zoom ? Math.min(duration, spectrumStart + zoom) : duration;
  const key = `${selectedId}:${variant}:${spectrumStart}:${spectrumEnd}:${recording.completed_at || ''}`;
  if (!force && key === lastSpectrumKey) return;
  lastSpectrumKey = key;
  const img = $('spectrum-image');
  img.src = `/api/recordings/${selectedId}/spectrogram?variant=${variant}&start=${spectrumStart}&end=${spectrumEnd}&v=${encodeURIComponent(recording.completed_at || '')}`;
  renderActivity();if(view==='timeline')renderTranscript(true);img.classList.remove('hidden'); $('spectrum-placeholder').classList.add('hidden'); $('playhead').classList.remove('hidden');
  $('time-axis').innerHTML = Array.from({length: 7}, (_, i) => `<span>${time(spectrumStart + (spectrumEnd - spectrumStart) * i / 6)}</span>`).join('');
}
function highlight(text, query) {
  if (!query) return esc(text);
  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
  return parts.map(p => p.toLocaleLowerCase() === query.toLocaleLowerCase() ? `<mark>${esc(p)}</mark>` : esc(p)).join('');
}
function activityRegions(){
  if(recording?.overlap_regions)return recording.overlap_regions;
  const events=[];for(const t of recording?.turns||[]){events.push([t.start,t.speaker_id,1],[t.end,t.speaker_id,-1]);}events.sort((a,b)=>a[0]-b[0]);
  const active=new Map(),regions=[];let previous=0;
  for(const [point,id,delta] of events){const ids=[...active].filter(([,n])=>n>0).map(([id])=>id);if(point>previous&&ids.length>1)regions.push({start:previous,end:point,speaker_ids:ids});active.set(id,(active.get(id)||0)+delta);previous=point;}return regions;
}
function activityMarkup(){
  if(!recording?.turns.length)return '<p class="setting-hint">Speaker activity appears after processing.</p>';
  const start=spectrumStart,end=spectrumEnd||recording.duration,width=Math.max(.01,end-start),regions=activityRegions();
  const speakers=recording.turns.some(t=>t.speaker_id==='unknown')?[...recording.speakers,{id:'unknown',name:'Unassigned · review'}]:recording.speakers;return speakers.map(s=>`<div class="activity-row"><button class="lane-play text-button" data-play-lane="${s.id}" title="Review ${esc(s.name)}: solo sections plus confirmed separated clips" aria-label="Play ${esc(s.name)} solo sections">${icon(activePlaybackSpeaker===s.id&&!audio.paused?'pause':'play')}</button><span class="lane-name" style="color:${colorFor(s.id)[1]}">${esc(s.name)}</span><div class="activity-track" data-lane-speaker="${s.id}">${regions.filter(r=>r.end>start&&r.start<end).map(r=>`<span class="lane-overlap" style="left:${Math.max(0,r.start-start)/width*100}%;width:${(Math.min(end,r.end)-Math.max(start,r.start))/width*100}%"></span>`).join('')}${recording.turns.filter(t=>t.speaker_id===s.id&&t.end>start&&t.start<end).map(t=>`<button class="activity-turn" data-seek="${t.start}" data-clip-end="${t.end}" title="${esc(s.name)} · ${time(t.start)}–${time(t.end)} · original audio mix" style="left:${Math.max(0,t.start-start)/width*100}%;width:${(Math.min(end,t.end)-Math.max(start,t.start))/width*100}%;background:${colorFor(s.id)[1]}"></button>`).join('')}${speakerMuteMarkup(s.id,start,end,width)}<i class="lane-playhead"></i></div></div>`).join('');
}
let activityHash='';
function renderActivity(){
  const hash=JSON.stringify([selectedId,recording?.turns,recording?.speakers,recording?.speaker_silences,spectrumStart,spectrumEnd]);if(hash===activityHash)return;activityHash=hash;
  const scroll=$('speaker-activity').scrollTop;$('speaker-activity').innerHTML=activityMarkup();$('speaker-activity').scrollTop=scroll;drawClipSelection();$('jump-overlap').disabled=!activityRegions().length;
}
function renderTranscript(force = false) {
  if (!recording) return;
  const query = $('search-input').value.trim();
  const key = JSON.stringify([recording.segments, recording.speakers, query, view, activeSpeaker]);
  if (!force && key === transcriptHash) return;
  transcriptHash = key;
  const content = $('transcript-content'); const scroll = content.scrollTop;
  if (!recording.segments.length) {
    content.innerHTML = `<div class="empty-state"><div class="empty-icon">${icon(recording.status === 'processing' ? 'settings' : 'play')}</div><h2>${recording.status === 'processing' ? 'Listening for every word…' : 'Your recording is ready.'}</h2><p>${recording.status === 'processing' ? 'Transcript segments appear as they are processed.' : 'Choose your language and models in Settings,<br>then select Transcribe to begin.'}</p>${recording.status !== 'processing' ? '<button class="button primary" id="start-from-empty">Transcribe recording</button>' : ''}</div>`;
    $('search-count').textContent = '';
    return;
  }
  if (view === 'timeline') {
    content.innerHTML = activityMarkup();
    return;
  }
  const filtered = recording.segments.map((seg, index) => ({seg, index})).filter(({seg}) => (!activeSpeaker || (seg.speaker_id === activeSpeaker || seg.speaker_ids?.includes(activeSpeaker))) && (!query || seg.text.toLocaleLowerCase().includes(query.toLocaleLowerCase()) || (speakerById(seg.speaker_id)?.name || '').toLocaleLowerCase().includes(query.toLocaleLowerCase())));
  $('search-count').textContent = query ? `${filtered.length} found` : activeSpeaker ? 'Filtered' : '';
  content.innerHTML = filtered.map(({seg,index}) => {
    const speaker = speakerById(seg.speaker_id), name = segmentName(seg);
    return `<div class="transcript-row" data-start="${seg.start}" data-end="${seg.end}" style="${avatarStyle(seg.speaker_id)}"><button class="timestamp" data-seek="${seg.start}" title="Play from ${time(seg.start)}">${time(seg.start)}</button><span class="avatar small-avatar">${esc(initial(name))}</span><span class="speaker-label" title="${esc(name)}${speaker?.suggested && !speaker.confirmed ? ' · suggested' : ''}">${esc(name)}</span><span class="segment-text" role="button" tabindex="0" aria-label="Edit transcript segment at ${time(seg.start)}" data-edit-index="${index}" title="${esc(seg.overlap?'Mixed voices: '+(seg.speaker_ids||[]).map(id=>speakerById(id)?.name||id).join(' + ')+'. Review the words and speaker assignment.':'Double-click or press Enter to edit')}">${highlight(seg.text,query)}${seg.overlap ? '<span class="overlap-badge">overlap · review</span>' : seg.identity_review?'<span class="overlap-badge">voice · review</span>':''}</span></div>`;
  }).join('') || '<div class="no-results">No matching transcript segments.</div>';
  content.scrollTop = scroll;
  markCurrentRow();
}
function renderSpeakers(force = false) {
  if (!recording) return;
  const hash = JSON.stringify([recording.speakers, selectedId, activeSpeaker, recording.completed_at]);
  if (!force && speakersHash === hash) return;
  speakersHash = hash;
  if (!recording.speakers.length) {
    $('speaker-list').innerHTML = `<div class="speaker-empty"><div class="avatar empty-avatar">?</div><h3>${recording.status === 'processing' ? 'Finding speaker turns…' : 'Meet the speakers'}</h3><p>Speaker voice samples and suggested names appear after diarization.</p></div>`;
    return;
  }
  $('speaker-list').innerHTML = recording.speakers.filter(s=>s.identity_status!=='unresolved').map((s,i) => `<article class="speaker-card" data-speaker="${s.id}" style="${avatarStyle(s.id)}"><div class="speaker-card-header"><button class="avatar text-button" data-filter-speaker="${s.id}" title="Filter transcript by this speaker" style="background:var(--avatar-bg);color:var(--avatar-color)">${esc(initial(s.name))}</button><div class="speaker-card-name"><strong>${esc(s.name)}</strong><small>Speaker ${String(i+1).padStart(2,'0')} · ${time(s.seconds)}</small></div><button class="text-button" data-play-speaker="${s.id}" aria-label="Play ${esc(s.name)} voice sample">${icon('play')}</button><button class="text-button" data-rename-speaker="${s.id}" aria-label="Rename ${esc(s.name)}">${icon('edit')}</button></div><div class="sample-label"><span>VOICE SAMPLE</span><span>${time(s.sample_start)}–${time(s.sample_end)}</span></div><img class="sample-spectrum" src="/api/recordings/${selectedId}/spectrogram?compact=true&start=${s.sample_start}&end=${s.sample_end}" alt="Spectrogram of ${esc(s.name)} voice sample">${s.evidence ? `<p class="speaker-evidence">“${esc(s.evidence)}”</p>` : ''}<div class="speaker-card-footer"><span class="suggested-tag">${activeSpeaker === s.id ? 'Transcript filtered' : s.suggested && !s.confirmed ? 'Suggested name' : !s.confirmed ? 'Name not identified' : ''}</span>${s.confirmed ? `<span class="confirmed">${icon('check')}Confirmed</span>` : `<button class="button" data-confirm-speaker="${s.id}" ${busy() ? 'disabled' : ''}>${icon('check')}Confirm</button>`}</div></article>`).join('');
}

function markCurrentRow() { document.querySelectorAll('.transcript-row').forEach(row => row.classList.toggle('current', audio.currentTime >= Number(row.dataset.start) && audio.currentTime <= Number(row.dataset.end))); }
function updatePlayback() {
  const duration = recording?.duration || 0;
  $('player-time').innerHTML = `${time(audio.currentTime)} <span>/ ${time(duration)}</span>`;
  $('seek').value = duration ? audio.currentTime / duration * 1000 : 0;
  const percent = (audio.currentTime - spectrumStart) / Math.max(.01, spectrumEnd - spectrumStart);
  $('playhead').style.left = `calc(35px + (100% - 35px) * ${Math.max(0, Math.min(1, percent))})`;
  $('spectrogram').setAttribute('aria-valuenow', String(Math.round(duration ? audio.currentTime / duration * 100 : 0)));
  $('play-button').innerHTML = icon(audio.paused ? 'play' : 'pause');
  $('play-button').setAttribute('aria-label', audio.paused ? 'Play audio' : 'Pause audio');
  document.querySelectorAll('.lane-playhead').forEach(el=>el.style.left=`${Math.max(0,Math.min(1,percent))*100}%`);
  updateLanePlayIcons();updateSamplePlayIcons();
  markCurrentRow();
}
function seekTo(seconds, play = false, end = null) { activeSampleSpeaker=null;activePlaybackSpeaker=null; if (!recording?.duration) return; sampleEnd = end; audio.currentTime = Math.max(0,Math.min(seconds,recording.duration)); if (play) {ensureAudioGraph();audio.play().catch(handleError);} renderSpectrum(); updatePlayback(); }
async function importFile(file) {
  if (!file || busy()) return;
  const data = new FormData(); data.append('file',file);
  $('import-button').disabled = true; toast('Importing recording…');
  try { const result = await api('/api/recordings', {method:'POST',body:data}); selectedId=result.id; resetRecording(); await poll(); } catch(error){handleError(error);} finally { $('file-input').value=''; updateButtons(); }
}
function resetRecording() { stopSeparatedNodes();separatedBuffers.clear(); activeSampleSpeaker=null;activePlaybackSpeaker=null;clipSelection=null;closeClipMenu();audio.pause(); audio.removeAttribute('src'); recording=null; transcriptHash='';speakersHash='';lastSpectrumKey='';activeSpeaker=null;sampleEnd=null;variant='original';$('search-input').value='';document.querySelectorAll('[data-variant]').forEach(b=>b.classList.toggle('active',b.dataset.variant==='original')); }
async function startProcessing() {
  if (!recording || busy()) return;
  if (recording.status==='complete' && !confirm('Reprocess this recording? This replaces transcript edits and speaker confirmations. Previous results are saved in revisions. Original audio is kept.')) return;
  try { await api(`/api/recordings/${selectedId}/process`,{method:'POST'}); await poll(); } catch(error){handleError(error);}
}

function openModal(id) { modalReturnFocus=document.activeElement; $(id).classList.remove('hidden'); document.body.style.overflow='hidden'; $(id).querySelector('button,input,select')?.focus(); }
function closeModal(id) { if(id==='separation-backdrop')document.querySelectorAll('#separation-preview audio').forEach(el=>el.pause()); $(id).classList.add('hidden'); if(!modalVisible()){document.body.style.overflow='';if(recording)renderRecording();renderJob();updateButtons();} modalReturnFocus?.focus(); }
function openSettings(tab='general') {
  if (!state) return;
  const s=state.settings;
  renderReferences();
  $('setting-language').value=s.language; $('setting-speakers').innerHTML='<option value="0">Detect automatically</option>'+Array.from({length:20},(_,i)=>`<option value="${i+1}">${i+1} speaker${i?'s':''}</option>`).join('');$('setting-speakers').value=String(recording?.expected_speakers??s.speaker_count);$('setting-speakers').disabled=busy();$('update-speakers').disabled=busy()||!recording?.segments.length; $('setting-detect-names').checked=s.detect_names;
  $('setting-window').value=String(s.introduction_seconds);$('setting-auto-unload').checked=s.auto_unload;
  $('setting-verify-speakers').checked=s.verify_uncertain_speakers??true;
  $('setting-denoise').checked=s.cleanup.denoise;$('setting-dehiss').checked=s.cleanup.dehiss;$('setting-normalize').checked=s.cleanup.normalize;
  $('setting-hum').value=s.cleanup.hum;$('setting-strength').value=Math.round(s.cleanup.strength*100);$('strength-label').value=`${Math.round(s.cleanup.strength*100)}%`;
  $('setting-diarization-audio').value=s.diarization_audio;setTheme(draftTheme);renderModels(true,true);renderStorage(); settingsTab(tab);openModal('settings-backdrop');
}
function settingsTab(tab) { document.querySelectorAll('[data-settings-tab]').forEach(b=>b.classList.toggle('active',b.dataset.settingsTab===tab));document.querySelectorAll('[data-page]').forEach(p=>p.classList.toggle('hidden',p.dataset.page!==tab)); }
let modelHash='';
function selectedModel(role){const select=document.querySelector(`[data-model-role="${role}"]`);return select?.value || (role==='transcription'?state.settings.asr_model:role==='diarization'?state.settings.speaker_model:state.settings.name_model);}
function renderModels(force=false,reset=false) {
  if(!state) return;
  const picks={separation:'sepformer-whamr',transcription:reset?state.settings.asr_model:selectedModel('transcription'),diarization:reset?state.settings.speaker_model:selectedModel('diarization'),names:reset?state.settings.name_model:selectedModel('names')};
  const hash=JSON.stringify([state.models.map(m=>[m.id,m.label]),picks]);
  if(!force&&hash===modelHash){updateModelStatus();return;}
  modelHash=hash;
  $('model-cards').innerHTML=[['transcription','Transcription'],['diarization','Speaker diarization'],['names','Introduction analysis'],['separation','Overlap separation · experimental']].map(([role,label])=>{
    const models=state.models.filter(m=>m.role===role),m=models.find(m=>m.id===picks[role])||models[0];
    return `<div class="model-card"><div class="model-heading"><strong>${label}</strong><span class="model-status ${m.loaded?'loaded':''}"><i></i>${m.loaded?'Loaded':m.installed?'Not loaded':'Not downloaded'}</span></div><div class="model-controls"><select data-model-role="${role}" aria-label="${label} model">${models.map(item=>`<option value="${item.id}" ${item.id===m.id?'selected':''}>${esc(item.label)}</option>`).join('')}</select>${m.id==='rules'?'<span class="badge">Always available</span>':`<button class="button ${!m.installed?'primary':''}" data-model-action="${!m.installed?'download':m.loaded?'unload':'load'}" data-model-id="${m.id}" ${busy()?'disabled':''}>${!m.installed?'Download':m.loaded?'Unload':'Load'}</button>`}</div><div class="model-meta"><span>${m.installed?bytes(m.disk_bytes)+' on disk':'About '+bytes(m.size)+' download'} · ${esc(m.license)}</span>${m.disk_bytes>0&&m.id!=='rules'?`<button class="text-button" data-model-action="delete" data-model-id="${m.id}" ${busy()?'disabled':''}>Remove</button>`:''}</div></div>`;
  }).join('');
  $('model-operation').textContent=busy()?state.job.message:'Models stay local. Unload frees RAM; Remove frees disk space.';
}
function updateModelStatus(){
  document.querySelectorAll('.model-card').forEach(card=>{
    const select=card.querySelector('[data-model-role]'),m=state.models.find(item=>item.id===select?.value);if(!m)return;
    const status=card.querySelector('.model-status'),label=m.loaded?'Loaded':m.installed?'Not loaded':'Not downloaded';
    status.classList.toggle('loaded',m.loaded);if(status.lastChild?.nodeType===3&&status.lastChild.nodeValue!==label)status.lastChild.nodeValue=label;
    const action=card.querySelector('[data-model-action]:not([data-model-action="delete"])');
    if(action){action.dataset.modelAction=!m.installed?'download':m.loaded?'unload':'load';setText(action,!m.installed?'Download':m.loaded?'Unload':'Load');action.disabled=busy();}
    const remove=card.querySelector('[data-model-action="delete"]');if(remove)remove.disabled=busy();
  });
  setText($('model-operation'),busy()?state.job.message:'Models stay local. Unload frees RAM; Remove frees disk space.');
}
async function saveSettings(close=true) {
  const previous=state.settings;
  const prefs={...previous,theme:draftTheme,language:$('setting-language').value,speaker_count:Number($('setting-speakers').value),
    detect_names:$('setting-detect-names').checked,introduction_seconds:Number($('setting-window').value),auto_unload:$('setting-auto-unload').checked,
    verify_uncertain_speakers:$('setting-verify-speakers').checked,
    asr_model:selectedModel('transcription'),name_model:selectedModel('names'),speaker_model:selectedModel('diarization'),diarization_audio:$('setting-diarization-audio').value,
    cleanup:{denoise:$('setting-denoise').checked,dehiss:$('setting-dehiss').checked,normalize:$('setting-normalize').checked,hum:$('setting-hum').value,strength:Number($('setting-strength').value)/100}};
  try{state.settings=await api('/api/settings',{method:'PUT',body:JSON.stringify(prefs)});if(recording&&!busy()){
    recording=await api(`/api/recordings/${selectedId}/participants`,{method:'PUT',body:JSON.stringify({count:prefs.speaker_count})});
    const references=[...document.querySelectorAll('.reference-row')].map(row=>({id:row.dataset.referenceId,name:row.querySelector('[data-ref-name]').value.trim(),start:Number(row.querySelector('[data-ref-start]').value),end:Number(row.querySelector('[data-ref-end]').value),confirmed:row.querySelector('[data-ref-confirm]').checked,name_confirmed:row.dataset.nameConfirmed==='true'||row.querySelector('[data-ref-name]').value.trim()!==row.dataset.originalName}));
    recording=await api(`/api/recordings/${selectedId}/references`,{method:'PUT',body:JSON.stringify({references})});
  }if(close)closeModal('settings-backdrop');toast(busy()?'Settings saved for the next processing run.':'Settings saved');renderJob();return true;}catch(error){handleError(error);return false;}
}
function referenceMarkup(r){return `<div class="reference-row" data-reference-id="${r.id}" data-name-confirmed="${!!r.name_confirmed}" data-original-name="${esc(r.name)}"><input data-ref-name aria-label="Reference speaker name" value="${esc(r.name)}" ${busy()?'disabled':''}><input type="number" data-ref-start aria-label="Reference start seconds" min="0" step="0.1" value="${r.start}" ${busy()?'disabled':''}><input type="number" data-ref-end aria-label="Reference end seconds" min="0" step="0.1" value="${r.end}" ${busy()?'disabled':''}><button class="text-button" data-seek="${r.start}" title="Listen from reference start">${icon('play')}</button><label title="I reviewed this clean voice sample"><input type="checkbox" data-ref-confirm ${r.confirmed?'checked':''} ${busy()?'disabled':''}>Reviewed</label><button class="text-button" data-remove-reference ${busy()?'disabled':''}>×</button></div>`;}
function renderReferences(){ $('voice-references').innerHTML=(recording?.voice_references||[]).map(referenceMarkup).join('');$('add-reference').disabled=busy()||!recording; }
$('add-reference').onclick=()=>{const ids=[...document.querySelectorAll('.reference-row')].map(r=>r.dataset.referenceId);const n=Array.from({length:20},(_,i)=>i).find(i=>!ids.includes(`speaker_${String(i).padStart(2,'0')}`));if(n===undefined)return toast('Up to 20 references are supported.');const start=Math.min(audio.currentTime,Math.max(0,recording.duration-3));$('voice-references').insertAdjacentHTML('beforeend',referenceMarkup({id:`speaker_${String(n).padStart(2,'0')}`,name:`Speaker ${n+1}`,start:Math.round(start*10)/10,end:Math.round(Math.min(recording.duration,start+3)*10)/10,confirmed:false}));};
let storageHash='';
function renderStorage(){if(!state)return;const hash=JSON.stringify([Object.values(state.disk).map(n=>Math.floor(n/1048576)),state.recordings,busy()]);if(hash===storageHash)return;storageHash=hash;$('storage-stats').innerHTML=[['Free disk space',state.disk.free_bytes],['Downloaded models',state.disk.models_bytes],['Saved recordings',state.disk.recordings_bytes]].map(([label,size])=>`<div class="storage-stat"><strong>${bytes(size)}</strong><span>${label}</span></div>`).join('');$('storage-recordings').innerHTML=state.recordings.map(r=>`<div class="saved-recording"><div><strong>${esc(r.title)}</strong><small>${time(r.duration)} · ${esc(r.status)}</small></div><button class="text-button" data-delete-recording="${r.id}" ${busy()?'disabled':''} aria-label="Delete ${esc(r.title)}">${icon('trash')}</button></div>`).join('')||'<p class="setting-hint">No recordings saved yet.</p>';}
function renderHistory() {$('history-list').innerHTML=state?.recordings.map(r=>`<button class="history-item" data-open-recording="${r.id}"><div><strong>${esc(r.title)}</strong><small>${time(r.duration)} · ${new Date(r.created_at).toLocaleDateString()}</small></div><span class="badge">${esc(r.status)}</span></button>`).join('')||'<div class="no-results">Import your first recording to get started.</div>';}
function openEditor(index){if(busy())return toast('Wait for processing to finish before editing.');editIndex=index;const s=recording.segments[index];$('edit-text').value=s.text;$('edit-speaker').innerHTML='<option value="unknown">Unknown</option><option value="overlap">Overlap · mixed voices</option>'+recording.speakers.filter(p=>p.identity_status!=='unresolved').map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('');$('edit-speaker').value=s.speaker_id;openModal('edit-backdrop');}

document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  try{
    if(button.matches('[data-play-lane]'))playSpeakerTurns(button.dataset.playLane);
    if(button.matches('[data-seek]'))seekTo(Number(button.dataset.seek),true);
    if(button.matches('[data-remove-reference]'))button.closest('.reference-row').remove();
    if(button.matches('[data-settings-tab]'))settingsTab(button.dataset.settingsTab);
    if(button.matches('[data-theme]'))setTheme(button.dataset.theme);
    if(button.matches('.close-modal'))closeModal('settings-backdrop');
    if(button.matches('.close-history'))closeModal('history-backdrop');
    if(button.matches('.close-edit'))closeModal('edit-backdrop');
    if(button.matches('[data-export]')){window.location.href=`/api/recordings/${selectedId}/export/${button.dataset.export}`;$('export-menu').classList.add('hidden');}
    if(button.matches('[data-variant]')){if(variant===button.dataset.variant)return;const pos=audio.currentTime,playing=!audio.paused;variant=button.dataset.variant;audio.src=`/api/recordings/${selectedId}/audio/${variant}`;audio.addEventListener('loadedmetadata',()=>{audio.currentTime=pos;if(playing)audio.play().catch(handleError);},{once:true});document.querySelectorAll('[data-variant]').forEach(b=>b.classList.toggle('active',b.dataset.variant===variant));renderSpectrum(true);}
    if(button.matches('[data-model-action]')){const {modelAction:action,modelId:id}=button.dataset;if(action==='delete'&&!confirm('Remove these downloaded model files? You can download them again later.'))return;await api(`/api/models/${id}/${action}`,{method:'POST'});await poll();}
    if(button.matches('[data-open-recording]')){selectedId=button.dataset.openRecording;resetRecording();closeModal('history-backdrop');const requestedId=selectedId;const result=await api(`/api/recordings/${requestedId}`);if(selectedId===requestedId){recording=result;localStorage.setItem('audio-recording',selectedId);renderRecording();updateButtons();}}
    if(button.matches('[data-delete-recording]')){const id=button.dataset.deleteRecording;if(!confirm('Delete this recording, its original audio, and all transcript results from disk?'))return;await api(`/api/recordings/${id}`,{method:'DELETE'});if(selectedId===id){selectedId=null;resetRecording();}await poll();if(!selectedId)location.reload();}
    if(button.matches('[data-play-speaker]')){const s=speakerById(button.dataset.playSpeaker);if(activeSampleSpeaker===s.id&&!audio.paused){audio.pause();seekTo(s.sample_start);activeSampleSpeaker=null;}else{seekTo(s.sample_start,true,s.sample_end);activeSampleSpeaker=s.id;}updatePlayback();}
    if(button.matches('[data-filter-speaker]')){activeSpeaker=activeSpeaker===button.dataset.filterSpeaker?null:button.dataset.filterSpeaker;view='transcript';setView();renderTranscript();renderSpeakers();}
    if(button.matches('[data-confirm-speaker]')){const s=speakerById(button.dataset.confirmSpeaker);recording=await api(`/api/recordings/${selectedId}/speakers/${s.id}`,{method:'PATCH',body:JSON.stringify({name:s.name,confirmed:true})});renderRecording();toast('Speaker name confirmed');}
    if(button.matches('[data-rename-speaker]')){if(busy())return toast('Wait for processing to finish before editing.');const s=speakerById(button.dataset.renameSpeaker);const name=prompt('Speaker name',s.name);if(name?.trim()){recording=await api(`/api/recordings/${selectedId}/speakers/${s.id}`,{method:'PATCH',body:JSON.stringify({name:name.trim(),confirmed:true})});renderRecording();}}
    if(button.id==='start-from-empty')await startProcessing();
  }catch(error){handleError(error);}
});
function setView(){ $('transcript-tab').classList.toggle('active',view==='transcript');$('timeline-tab').classList.toggle('active',view==='timeline');$('transcript-tab').setAttribute('aria-selected',String(view==='transcript'));$('timeline-tab').setAttribute('aria-selected',String(view==='timeline')); }
$('speaker-activity').onclick=event=>{const button=event.target.closest('[data-seek]');if(button)seekTo(Number(button.dataset.seek),true);};
$('jump-overlap').onclick=()=>{const regions=activityRegions();const next=regions.find(r=>r.start>audio.currentTime+.1)||regions[0];if(next)seekTo(next.start,true);};
$('transcript-tab').onclick=()=>{view='transcript';setView();renderTranscript();};$('timeline-tab').onclick=()=>{view='timeline';setView();renderTranscript();};
$('import-button').onclick=$('empty-import').onclick=()=>$('file-input').click();
$('file-input').onchange=()=>importFile($('file-input').files[0]);
$('process-button').onclick=startProcessing;
$('settings-button').onclick=()=>openSettings();
$('save-settings').onclick=()=>saveSettings();
$('update-speakers').onclick=async()=>{if(!await saveSettings(false))return;try{await api(`/api/recordings/${selectedId}/process`,{method:'POST',body:JSON.stringify({mode:'speakers'})});closeModal('settings-backdrop');await poll();}catch(error){handleError(error);}};
$('history-button').onclick=()=>{renderHistory();openModal('history-backdrop');};
$('cancel-button').onclick=async()=>{try{await api('/api/jobs/cancel',{method:'POST'});toast('Cancellation requested');}catch(error){handleError(error);}};
$('export-button').onclick=()=>{const open=$('export-menu').classList.toggle('hidden');$('export-button').setAttribute('aria-expanded',String(!open));};
$('play-button').onclick=()=>{activeSampleSpeaker=null;activePlaybackSpeaker=null;ensureAudioGraph();sampleEnd=null;if(audio.paused)audio.play().catch(handleError);else audio.pause();};
$('stop-button').onclick=()=>{audio.pause();seekTo(0);sampleEnd=null;updatePlayback();};
$('rewind-button').onclick=()=>skipPlayback(-10);$('forward-button').onclick=()=>skipPlayback(10);
$('seek').oninput=()=>seekTo(Number($('seek').value)/1000*(recording?.duration||0));
$('playback-speed').onchange=()=>{audio.playbackRate=Number($('playback-speed').value);};
$('mute-button').onclick=()=>{audio.muted=!audio.muted;$('mute-button').style.opacity=audio.muted?.4:1;$('mute-button').title=audio.muted?'Unmute':'Mute';scheduleMutes();};
$('zoom-select').onchange=()=>{renderSpectrum(true);updatePlayback();};
$('spectrogram').onclick=event=>{const r=$('spectrogram').getBoundingClientRect();seekTo(spectrumStart+Math.max(0,Math.min(1,(event.clientX-r.left-35)/(r.width-35)))*(spectrumEnd-spectrumStart));};
$('spectrogram').onkeydown=event=>{if(event.key==='ArrowRight'||event.key==='ArrowLeft'){event.preventDefault();seekTo(audio.currentTime+(event.key==='ArrowRight'?5:-5));}};
audio.ontimeupdate=()=>{advanceSpeakerPlayback();if(sampleEnd!==null&&audio.currentTime>=sampleEnd){audio.pause();sampleEnd=null;}renderSpectrum();updatePlayback();};audio.onplay=audio.onpause=audio.onended=updatePlayback;
audio.onerror=()=>{if(audio.getAttribute('src'))toast('Audio preview is unavailable. Wait for import to finish.');};
$('search-input').oninput=()=>renderTranscript();
$('transcript-content').ondblclick=event=>{const el=event.target.closest('[data-edit-index]');if(el)openEditor(Number(el.dataset.editIndex));};
$('transcript-content').onkeydown=event=>{const el=event.target.closest('[data-edit-index]');if(el&&(event.key==='Enter'||event.key===' ')){event.preventDefault();event.stopPropagation();openEditor(Number(el.dataset.editIndex));}};
$('save-edit').onclick=async()=>{try{recording=await api(`/api/recordings/${selectedId}/segments/${editIndex}`,{method:'PATCH',body:JSON.stringify({text:$('edit-text').value,speaker_id:$('edit-speaker').value})});closeModal('edit-backdrop');renderRecording();toast('Transcript updated');}catch(error){handleError(error);}};
$('setting-strength').oninput=()=>{$('strength-label').value=`${$('setting-strength').value}%`;};
$('model-cards').onchange=()=>renderModels(true);
document.querySelectorAll('.modal-backdrop').forEach(el=>el.addEventListener('click',event=>{if(event.target===el)closeModal(el.id);}));
document.addEventListener('click',event=>{if(!event.target.closest('.menu-anchor')){$('export-menu').classList.add('hidden');$('export-button').setAttribute('aria-expanded','false');}});
document.addEventListener('keydown',event=>{const modal=document.querySelector('.modal-backdrop:not(.hidden)');if(event.key==='Escape'){if(modal)closeModal(modal.id);$('export-menu').classList.add('hidden');}if(event.key==='Tab'&&modal){const list=[...modal.querySelectorAll('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea')].filter(el=>el.offsetParent!==null);const first=list[0],last=list.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}if(event.code==='Space'&&!modal&&!/INPUT|SELECT|TEXTAREA|BUTTON/.test(document.activeElement.tagName)){event.preventDefault();$('play-button').click();}});
let dragDepth=0;document.addEventListener('dragenter',event=>{if(event.dataTransfer.types.includes('Files')){event.preventDefault();dragDepth++;$('drop-overlay').classList.remove('hidden');}});document.addEventListener('dragover',event=>{if(event.dataTransfer.types.includes('Files'))event.preventDefault();});document.addEventListener('dragleave',()=>{if(--dragDepth<=0){dragDepth=0;$('drop-overlay').classList.add('hidden');}});document.addEventListener('drop',event=>{event.preventDefault();dragDepth=0;$('drop-overlay').classList.add('hidden');importFile(event.dataTransfer.files[0]);});
initClipControls();initSeparationControls();poll();setInterval(poll,1400);
