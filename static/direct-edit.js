// Edit the displayed utterance in its own row. No blur-save and no global rename.
function directEditPayload(draft, name, text) {
  const payload={fingerprint:draft.answer.fingerprint,text};
  if(draft.segment.simultaneous){
    payload.source_speaker_id=draft.segment.speaker_id;
    payload.speaker_id=draft.segment.speaker_id;
  }
  if(name.trim()!==draft.name)payload.speaker_name=name.trim();
  return payload;
}
function openDirectEdit(index, row, focusName=false) {
  if(directEdit||inlineEditorHost)return toast('Save or cancel the current edit first.');
  if(busy())return toast('Wait for processing to finish before editing.');
  const sourceId=row.dataset.sourceSpeaker;
  const displayed=transcriptDisplayRows().find(r=>r.index===index&&(!sourceId||r.seg.speaker_id===sourceId));
  const answer=recording.answer_groups?.find(g=>g.indices[0]===index);
  if(!displayed||!answer)return toast('Refresh the recording before editing.');
  audio.pause();
  const seg=displayed.seg,name=segmentName(seg);
  directEdit={index,row,answer,segment:seg,name,rid:selectedId,saving:false};
  row.classList.add('direct-editing');
  row.querySelector('.transcript-speaker-edit').outerHTML=`<input class="speaker-label direct-name" aria-label="Speaker for this utterance only" maxlength="60" value="${esc(name)}" autocomplete="off">`;
  row.querySelector('.segment-text').innerHTML=`<textarea class="direct-text" aria-label="Transcript at ${time(seg.start)}" maxlength="4000" rows="1">${esc(seg.text)}</textarea><span class="direct-actions"><small>This utterance only · Ctrl+Enter to save</small><button class="text-button" data-direct-save>Save</button><button class="text-button" data-direct-cancel>Cancel</button><button class="text-button" data-direct-tools title="Gemma suggestions and overlap annotations">More tools</button><span class="direct-status" role="status"></span></span>`;
  const text=row.querySelector('.direct-text');
  const resize=()=>{text.style.height='auto';text.style.height=`${text.scrollHeight+2}px`;};
  text.addEventListener('input',resize);resize();
  row.querySelector(focusName?'.direct-name':'.direct-text').focus();
}
function closeDirectEdit(){
  if(!directEdit||directEdit.saving)return;
  directEdit=null;transcriptHash='';renderRecording();indexTranscriptRows();
}
async function saveDirectEdit(){
  const draft=directEdit;if(!draft||draft.saving)return;
  const name=draft.row.querySelector('.direct-name').value,text=draft.row.querySelector('.direct-text').value;
  const status=draft.row.querySelector('.direct-status');
  if(!text.trim()||!name.trim()){status.textContent='Enter a speaker label and transcript text.';return;}
  if(name===draft.name&&text===draft.segment.text){closeDirectEdit();return;}
  draft.saving=true;status.textContent='Saving…';
  draft.row.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=true);
  try{
    const next=await api(`/api/recordings/${draft.rid}/answers/${draft.index}`,{method:'PATCH',body:JSON.stringify(directEditPayload(draft,name,text))});
    if(selectedId===draft.rid)recording=next;
    draft.saving=false;closeDirectEdit();toast('Saved this utterance. Other speaker assignments are unchanged.');
  }catch(error){
    draft.saving=false;status.textContent=error.message;
    draft.row.querySelectorAll('input,textarea,button').forEach(el=>el.disabled=false);
  }
}
document.addEventListener('click',event=>{
  if(event.target.closest('[data-direct-save]'))saveDirectEdit();
  if(event.target.closest('[data-direct-cancel]'))closeDirectEdit();
  if(event.target.closest('[data-direct-tools]')&&directEdit&&!directEdit.saving){
    const draft=directEdit;
    const text=draft.row.querySelector('.direct-text').value,name=draft.row.querySelector('.direct-name').value;
    if(text!==draft.segment.text||name!==draft.name)return toast('Save or cancel these edits before opening more tools.');
    closeDirectEdit();openEditor(draft.index);
  }
});
document.addEventListener('keydown',event=>{
  if(!directEdit)return;
  if(event.key==='Escape'){event.preventDefault();event.stopImmediatePropagation();closeDirectEdit();}
  if(event.key==='Enter'&&(event.ctrlKey||event.metaKey)){event.preventDefault();saveDirectEdit();}
},true);
