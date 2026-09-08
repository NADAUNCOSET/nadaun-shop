import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const {mountScenes}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/shop/scenes.js')).toString('base64'));
function setup(motion=true){
 const listeners=new Map(),effects=[],observers=[],states=new Set();
 const doc={body:{dataset:{}},hidden:false,addEventListener:(k,fn)=>listeners.set(k,fn),removeEventListener:k=>listeners.delete(k)};
 const grid={},heading={},title={},secondary={};
 const scene={classList:{toggle:(k,on)=>on?states.add(k):states.delete(k),remove:k=>states.delete(k)},querySelector:s=>s==='.scene-grid'?grid:heading,querySelectorAll:s=>s==='.motion-line>span'?[title]:[secondary],getBoundingClientRect:()=>({top:100,bottom:900})};
 const main={ownerDocument:doc,querySelectorAll:()=>[scene],querySelector:()=>null};
 let cleanup,queries;
 const effect=(target,vars)=>{const e={target,vars};effects.push(e);return e};
 const gsap={fromTo:(target,from,to)=>effect(target,{from,...to}),timeline(vars){const e=effect(null,vars);e.fromTo=()=>e;return e},matchMedia(){return{add(q,fn){queries=q;cleanup=fn({conditions:{motion,mobile:false}})},revert(){cleanup?.();for(const e of effects)e.killed=true}}}};
 const env={innerHeight:800,IntersectionObserver:class{constructor(fn){this.emit=fn;observers.push(this)}observe(target){this.target=target}disconnect(){this.disconnected=true}}};
 return {doc,scene,grid,states,effects,listeners,observers,env,mount:preference=>mountScenes(main,{gsap,ScrollTrigger:{refresh(){}},motionPreference:preference},env),get queries(){return queries}};
}
test('section choreography follows scroll progress and tears down its observer and animations',()=>{
 const s=setup(),dispose=s.mount();assert.equal(s.doc.body.dataset.motionActive,'true');assert.equal(s.observers[0].target,s.scene);
 assert.ok(s.effects.some(e=>e.target===s.grid&&e.vars.scrollTrigger.scrub));assert.ok(s.effects.every(e=>!e.vars.scrollTrigger?.pin));
 s.observers[0].emit([{target:s.scene,isIntersecting:true}]);assert.ok(s.states.has('is-in-view'));
 dispose();assert.equal(s.states.size,0);assert.equal(s.listeners.size,0);assert.equal(s.observers[0].disconnected,true);assert.equal(s.doc.body.dataset.motionActive,'false');assert.ok(s.effects.every(e=>e.killed));
});
test('continuous product movement pauses outside the viewport and in a hidden tab',()=>{
 const s=setup(),dispose=s.mount();s.observers[0].emit([{target:s.scene,isIntersecting:true}]);assert.ok(s.states.size);
 s.observers[0].emit([{target:s.scene,isIntersecting:false}]);assert.equal(s.states.size,0);
 s.doc.hidden=true;s.listeners.get('visibilitychange')();assert.equal(s.states.size,0);
 s.doc.hidden=false;s.listeners.get('visibilitychange')();assert.ok(s.states.size);dispose();
});
test('reduced motion adds no observer or transforms; a manual choice uses a separate media query',()=>{
 const s=setup(false),dispose=s.mount();assert.equal(s.effects.length,0);assert.equal(s.observers.length,0);dispose();
 const enabled=setup(),stop=enabled.mount('on');assert.equal(enabled.queries.motion,'all');stop();
 const disabled=setup(false);disabled.mount('off');assert.equal(disabled.queries.motion,'not all');assert.equal(disabled.effects.length,0);
});
test('white gallery retains real brand links, separate rentals and an operable motion control',()=>{
 const home=fs.readFileSync('index.html','utf8');
 for(const section of ['purchase','brands','rental'])assert.ok(home.includes('data-scene="'+section+'"'));
 assert.ok(home.includes('data-motion-control'));assert.ok(home.includes('brand-mark'));assert.ok(home.includes('data-mode="home"'));assert.ok(home.includes('/assets/shop/storefront.css?v='));
 assert.ok(!home.includes('{{'));assert.ok(!home.includes('motion-ribbon'));assert.ok(!home.includes('class="editorial-pair"'));
});
