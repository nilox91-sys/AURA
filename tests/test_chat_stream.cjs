const {test}=require('node:test');const assert=require('node:assert/strict');
const {readAnswer}=require('../static/js/chat-stream.js');
function response(events) {
    const bytes=new TextEncoder().encode(events.map(e=>JSON.stringify(e)+'\n').join(''));
    return {ok:true,body:new ReadableStream({start(c){for(let i=0;i<bytes.length;i+=3)c.enqueue(bytes.slice(i,i+3));c.close();}})};
}
test('chat reader delivers UTF-8 dialect deltas in order and requires explicit success',async()=>{
    const seen=[];const result=await readAnswer(response([{event:'start'},{event:'delta',text:'Jamme, è pronta! 🎮'},
        {event:'done',status:'success',response:'Jamme, è pronta! 🎮'}]),event=>seen.push(event));
    assert.equal(seen[1].text,result.response);assert.equal(seen.at(-1).event,'done');
    await assert.rejects(readAnswer(response([{event:'delta',text:'Parziale.'}]),()=>{}),/interrotta/);
    await assert.rejects(readAnswer(response([{event:'error',error:'Quota esaurita'}]),()=>{}),/Quota esaurita/);
});
test('stale AI deltas are rejected after cancellation',async()=>{
    const controller=new AbortController();controller.abort();let count=0;
    await assert.rejects(readAnswer(response([{event:'delta',text:'Vecchia risposta'}]),()=>count++,controller.signal),{name:'AbortError'});
    assert.equal(count,0);
});
