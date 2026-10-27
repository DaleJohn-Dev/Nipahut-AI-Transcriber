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
