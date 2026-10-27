const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('static/app.js','utf8');
const oldRecord={id:'a',segments:[]};
let renders=0,parses=0,calls=0;
const nodes={};
const ctx=vm.createContext({polling:false,state:null,recording:oldRecord,selectedId:'a',recordingValidator:null,
 localStorage:{getItem:()=>true,setItem(){}},api:async()=>({version:'test',settings:{},disk:{free_bytes:1},recordings:[{id:'a'}]}),
 $:id=>nodes[id]??={classList:{contains:()=>true,remove(){},add(){}}},setText(){},bytes:()=>'',modalVisible:()=>false,
 renderRecording(){renders++;},renderJob(){},updateButtons(){},renderHistory(){},
 fetch:async(path,opts)=>{calls++;if(calls===1)return {ok:true,status:200,headers:{get:()=> 'revision-1'},json:async()=>{parses++;return oldRecord;}};
 assert.equal(opts.headers['If-None-Match'],'revision-1');return {ok:false,status:304,json(){throw Error('Parsed a 304');}};}
});
vm.runInContext(source.slice(source.indexOf('async function poll()'),source.indexOf('\nfunction renderRecording()')),ctx);
(async()=>{await ctx.poll();await ctx.poll();await ctx.poll();assert.equal(renders,1);assert.equal(parses,1);assert.equal(ctx.recording,oldRecord);assert.equal(ctx.polling,false);console.log('PASS: unchanged polling preserves recording identity and skips JSON/render work');})().catch(e=>{console.error(e);process.exitCode=1;});
const activityContext=vm.createContext({recording:{duration:100,speakers:[{id:'a',name:'A'},{id:'b',name:'B'},{id:'c',name:'C'}],turns:[{speaker_id:'a',start:0,end:5},{speaker_id:'b',start:2,end:4},{speaker_id:'c',start:10,end:12}]},spectrumStart:0,spectrumEnd:100,activePlaybackSpeaker:null,audio:{paused:true},activityRegions:()=>[{start:2,end:4,speaker_ids:['a','b']}],colorFor:()=>['white','teal'],icon:()=>'',esc:String,time:String,speakerMuteMarkup:()=>''});
vm.runInContext(source.slice(source.indexOf('function activityMarkup(){'),source.indexOf('\nlet activityHash=')),activityContext);
const lanes=activityContext.activityMarkup();
assert.equal((lanes.match(/class="lane-overlap"/g)||[]).length,2,'Only participating lanes receive overlap markers');
assert.equal((lanes.match(/class="activity-turn"/g)||[]).length,3,'Every original speaker turn remains available');
activityContext.spectrumStart=6;
assert.equal((activityContext.activityMarkup().match(/class="activity-turn"/g)||[]).length,1,'Zoom excludes off-screen turns');
assert.match(source,/class="sample-spectrum" loading="lazy" decoding="async"/,'Samples load as their cards approach view');
console.log('PASS: participant-only overlap markers, viewport turn filtering, and lazy sample loading');
