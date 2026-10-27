// Lane review includes overlap in the original mix unless a confirmed source is ready.
const soloReviewCache=new WeakMap();
function speakerSoloTurns(sid){
  if(!recording)return [];
  let cache=soloReviewCache.get(recording);if(!cache){cache=new Map();soloReviewCache.set(recording,cache);}if(cache.has(sid))return cache.get(sid);
  const turns=recording?.turns||[],blocked=[...turns.filter(t=>t.speaker_id!==sid),...(recording?.overlap_regions||[]),...(recording?.silenced_ranges||[])].sort((a,b)=>a.start-b.start),solo=[];
  for(const turn of turns.filter(t=>t.speaker_id===sid).sort((a,b)=>a.start-b.start)){
    let parts=[{start:turn.start+.04,end:turn.end-.04}];
    for(const other of blocked){const start=other.start-.06,end=other.end+.06;parts=parts.flatMap(p=>end<=p.start||start>=p.end?[p]:[{start:p.start,end:Math.min(p.end,start)},{start:Math.max(p.start,end),end:p.end}].filter(r=>r.end-r.start>=.08));}
    for(const part of parts){if(part.end-part.start<.08)continue;const last=solo.at(-1);if(last&&part.start<=last.end)last.end=Math.max(last.end,part.end);else solo.push(part);}
  }
  cache.set(sid,solo);return solo;
}
function ensureAudioGraph(){
  if(!audioGraph){const Context=window.AudioContext||window.webkitAudioContext;if(!Context)throw new Error('Audio editing playback is unavailable in this renderer.');const context=new Context(),source=context.createMediaElementSource(audio),gain=context.createGain();source.connect(gain);gain.connect(context.destination);audioGraph={context,gain};}
  audioGraph.context.resume().catch(handleError);scheduleMutes();
}
function scheduleMutes(){
  scheduleSeparatedPlayback();
  if(!audioGraph)return;
  const {context,gain}=audioGraph,now=context.currentTime,pos=audio.currentTime,rate=audio.playbackRate||1,ranges=recording?.silenced_ranges||[];
  if(activePlaybackSpeaker){
    const solo=speakerOriginalTurns(activePlaybackSpeaker);gain.gain.cancelScheduledValues(now);gain.gain.setValueAtTime(solo.some(r=>r.start<=pos&&r.end>pos)?1:0,now);
    if(!audio.paused)for(const r of solo){if(r.end<=pos)continue;if(r.start>pos)gain.gain.setValueAtTime(1,now+(r.start-pos)/rate);gain.gain.setValueAtTime(0,now+(r.end-pos)/rate);}
    return;
  }
  gain.gain.cancelScheduledValues(now);gain.gain.setValueAtTime(ranges.some(r=>r.start<=pos&&r.end>pos)?0:1,now);
  if(audio.paused)return;
  for(const r of ranges){if(r.end<=pos)continue;if(r.start>pos)gain.gain.setValueAtTime(0,now+(r.start-pos)/rate);gain.gain.setValueAtTime(1,now+(r.end-pos)/rate);}
}
function updateLanePlayIcons(){document.querySelectorAll('[data-play-lane]').forEach(button=>{const use=button.querySelector('use'),name=activePlaybackSpeaker===button.dataset.playLane&&!audio.paused?'pause':'play';if(use?.getAttribute('href')!==`#i-${name}`)use?.setAttribute('href',`#i-${name}`);});}
async function playSpeakerTurns(sid){
  activeSampleSpeaker=null;
  const turns=speakerReviewTurns(sid);if(!turns.length){toast('No audible sections found for this speaker. Check the lane silence edits.');return;}
  if(activePlaybackSpeaker===sid&&!audio.paused){audio.pause();return;}
  audio.pause();
  const playbackRecording=selectedId;
  try{await prepareSeparatedPlayback(sid);}catch(error){toast(`Separated preview unavailable; playing the original mix instead. ${error.message}`);}
  if(playbackRecording!==selectedId)return;
  const resume=activePlaybackSpeaker===sid&&turns.some(t=>t.start<=audio.currentTime&&t.end>audio.currentTime);
  activePlaybackSpeaker=sid;sampleEnd=null;ensureAudioGraph();if(!resume)audio.currentTime=turns[0].start;
  audio.play().then(scheduleMutes).catch(handleError);updateLanePlayIcons();toast(`Reviewing ${speakerById(sid)?.name||'speaker'}: all detected turns, including overlaps. Unseparated overlaps play the original mix.`);
}
function advanceSpeakerPlayback(){
  if(!activePlaybackSpeaker||audio.paused)return;
  const turns=speakerReviewTurns(activePlaybackSpeaker),pos=audio.currentTime;
  if(turns.some(t=>t.start<=pos&&t.end>pos))return;
  const next=turns.find(t=>t.start>pos);
  if(next){audio.currentTime=next.start;scheduleMutes();}else{audio.pause();activePlaybackSpeaker=null;updateLanePlayIcons();}
}
function speakerMuteMarkup(sid,start,end,width){return (recording?.speaker_silences?.[sid]||[]).filter(r=>r.end>start&&r.start<end).map(r=>`<span class="lane-silenced" title="Silenced solo activity; original kept" style="left:${Math.max(0,r.start-start)/width*100}%;width:${(Math.min(end,r.end)-Math.max(start,r.start))/width*100}%"></span>`).join('');}
function drawClipSelection(){
  document.querySelectorAll('.lane-selection').forEach(e=>e.remove());
  if(!clipSelection||clipSelection.recording!==selectedId)return;
  const track=document.querySelector(`#speaker-activity [data-lane-speaker="${clipSelection.speaker}"]`);if(!track)return;
  const width=Math.max(.01,spectrumEnd-spectrumStart),a=Math.max(spectrumStart,clipSelection.start),b=Math.min(spectrumEnd,clipSelection.end);
  if(b>a)track.insertAdjacentHTML('beforeend',`<span class="lane-selection" style="left:${(a-spectrumStart)/width*100}%;width:${(b-a)/width*100}%"></span>`);
}
function clipTime(event,track){const rect=track.getBoundingClientRect();return spectrumStart+Math.max(0,Math.min(1,(event.clientX-rect.left)/rect.width))*(spectrumEnd-spectrumStart);}
function clipHasOverlap(selection){
  const own=(recording?.turns||[]).filter(t=>t.speaker_id===selection.speaker&&t.end>selection.start&&t.start<selection.end);
  return own.some(a=>(recording?.turns||[]).some(b=>b.speaker_id!==selection.speaker&&Math.min(a.end,b.end,selection.end)>Math.max(a.start,b.start,selection.start)));
}
let clipMenu;
function clipStamp(value){return time(value)+'.'+String(Math.floor(value%1*1000)).padStart(3,'0');}
function closeClipMenu(){clipMenu?.classList.add('hidden');}
function showClipMenu(event,selection){
  if(!clipMenu){clipMenu=document.createElement('div');clipMenu.id='clip-context-menu';clipMenu.className='clip-context-menu hidden';clipMenu.setAttribute('role','menu');document.body.appendChild(clipMenu);}
  const overlap=clipHasOverlap(selection);
  clipMenu.innerHTML=`<strong>Assigned to ${esc(speakerById(selection.speaker)?.name||'Unknown')}</strong><small>${clipStamp(selection.start)} - ${clipStamp(selection.end)}</small><button role="menuitem" data-clip-action="silence" ${overlap||busy()?'disabled':''}>Silence clip</button><button role="menuitem" data-clip-action="restore" ${busy()?'disabled':''}>Restore audio</button><button role="menuitem" data-clip-action="clear">Clear selection</button><small>${overlap?'This overlaps another voice. Speaker-only muting needs separated tracks; other speakers will not be muted.':'Only this speaker’s detected solo turns are affected. Original audio is kept. Reprocess to update the transcript.'}</small>`;
  const canSeparate=overlap&&selection.end-selection.start>=.5&&selection.end-selection.start<=20&&!busy();
  clipMenu.querySelector('[data-clip-action="clear"]').insertAdjacentHTML('beforebegin',`<button role="menuitem" data-clip-action="separate" ${canSeparate?'':'disabled'}>Separate two voices · experimental</button>`);
  clipMenu.classList.remove('hidden');clipMenu.style.left=`${Math.max(8,Math.min(event.clientX,window.innerWidth-290))}px`;clipMenu.style.top=`${Math.max(8,Math.min(event.clientY,window.innerHeight-clipMenu.offsetHeight-8))}px`;
}
function initClipControls(){
  const activity=$('speaker-activity');
  activity.addEventListener('pointerdown',event=>{const track=event.target.closest('.activity-track');if(!track||event.button!==0||busy())return;const pos=clipTime(event,track);clipSelection={speaker:track.dataset.laneSpeaker,recording:selectedId,anchor:pos,start:pos,end:pos};clipDragging=true;clipDragTrack=track;activity.setPointerCapture(event.pointerId);closeClipMenu();drawClipSelection();});
  activity.addEventListener('pointermove',event=>{if(!clipDragging||!clipDragTrack)return;const pos=clipTime(event,clipDragTrack);clipSelection.start=Math.min(clipSelection.anchor,pos);clipSelection.end=Math.max(clipSelection.anchor,pos);drawClipSelection();});
  activity.addEventListener('pointerup',()=>{if(clipDragging&&clipSelection.end-clipSelection.start>.04)ignoreTrackClickUntil=performance.now()+400;clipDragging=false;clipDragTrack=null;});
  activity.addEventListener('pointercancel',()=>{clipDragging=false;clipDragTrack=null;});
  activity.addEventListener('contextmenu',event=>{const track=event.target.closest('.activity-track');if(!track)return;event.preventDefault();const sid=track.dataset.laneSpeaker;
    if(!clipSelection||clipSelection.recording!==selectedId||clipSelection.speaker!==sid||clipSelection.end-clipSelection.start<.04){const turn=event.target.closest('[data-clip-end]');if(!turn)return toast('Drag across a speaker lane to select a time range.');clipSelection={recording:selectedId,speaker:sid,start:Number(turn.dataset.seek),end:Number(turn.dataset.clipEnd)};}
    drawClipSelection();showClipMenu(event,clipSelection);
  });
  document.addEventListener('click',event=>{if(event.target.closest('.activity-track')&&performance.now()<ignoreTrackClickUntil){event.preventDefault();event.stopImmediatePropagation();}},true);
  document.addEventListener('click',async event=>{const action=event.target.closest('[data-clip-action]');if(!action){if(!event.target.closest('#clip-context-menu'))closeClipMenu();return;}if(action.disabled||!clipSelection)return;
    if(action.dataset.clipAction==='clear'){clipSelection=null;drawClipSelection();closeClipMenu();return;}
    if(action.dataset.clipAction==='separate'){requestSeparation({...clipSelection});return;}
    try{recording=await api(`/api/recordings/${selectedId}/audio-edits`,{method:'POST',body:JSON.stringify({start:clipSelection.start,end:clipSelection.end,speaker_id:clipSelection.speaker,action:action.dataset.clipAction})});renderRecording();scheduleMutes();toast('Audio edit saved. Original kept; reprocess to update the transcript.');closeClipMenu();}catch(error){handleError(error);}
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeClipMenu();});
  audio.addEventListener('play',scheduleMutes);audio.addEventListener('pause',scheduleMutes);audio.addEventListener('seeked',scheduleMutes);audio.addEventListener('ratechange',scheduleMutes);audio.addEventListener('loadedmetadata',scheduleMutes);
  setInterval(()=>{if(activePlaybackSpeaker&&!audio.paused)advanceSpeakerPlayback();},40);
}

function updateSamplePlayIcons(){document.querySelectorAll('[data-play-speaker]').forEach(button=>{const sid=button.dataset.playSpeaker,playing=activeSampleSpeaker===sid&&!audio.paused,name=speakerById(sid)?.name||'speaker',use=button.querySelector('use'),href=playing?'#i-stop':'#i-play';if(use?.getAttribute('href')!==href)use?.setAttribute('href',href);const label=`${playing?'Stop':'Play'} ${name} voice sample`;if(button.getAttribute?.('aria-label')!==label)button.setAttribute('aria-label',label);});}
function skipPlayback(delta){const sid=activePlaybackSpeaker,playing=!audio.paused;seekTo(audio.currentTime+delta,playing);activePlaybackSpeaker=sid;if(sid)advanceSpeakerPlayback();updatePlayback();}
