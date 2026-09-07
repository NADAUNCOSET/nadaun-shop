import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const {mountArtMotion}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/shop/motion.js','utf8')).toString('base64'));

// A small DOM/GSAP harness checks lifecycle and accessibility, not visual timing.
function setup(conditions={motion:true,desktop:false,fine:false,mobile:false}){
 class Element{
  constructor(tag='div',selectors=[]){this.tag=tag;this.selectors=new Set(selectors);this.children=[];this.listeners=new Map();this.attrs={};this.props=new Map();this.style={setProperty:(k,v)=>this.props.set(k,v),removeProperty:k=>this.props.delete(k)};const values=new Set();this.classList={add:k=>values.add(k),remove:k=>values.delete(k),contains:k=>values.has(k)};}
  get parentNode(){return this.parent}get firstElementChild(){return this.children[0]}
  get isConnected(){return this.root===true||!!this.parent?.isConnected}
  setAttribute(k,v){this.attrs[k]=v}
  addEventListener(k,fn){if(!this.listeners.has(k))this.listeners.set(k,new Set());this.listeners.get(k).add(fn)}
  removeEventListener(k,fn){this.listeners.get(k)?.delete(fn)}
  emit(k,e={}){for(const fn of this.listeners.get(k)||[])fn(e)}
  append(child){child.remove();child.parent=this;child.ownerDocument=this.ownerDocument;this.children.push(child)}
  before(child){child.remove();const index=this.parent.children.indexOf(this);child.parent=this.parent;child.ownerDocument=this.ownerDocument;this.parent.children.splice(index,0,child)}
  remove(){if(this.parent){this.parent.children.splice(this.parent.children.indexOf(this),1);this.parent=null}}
  replaceWith(child){this.before(child);this.remove()}
  closest(selector){return selector==='[hidden]'?(this.hidden?this:this.parent?.closest(selector)):null}
  matches(selector){return selector.split(',').some(s=>s===this.tag||this.selectors.has(s))}
  querySelectorAll(selector){return this.children.flatMap(c=>[...(c.matches(selector)?[c]:[]),...c.querySelectorAll(selector)])}
  querySelector(selector){return this.querySelectorAll(selector)[0]}
 }
 const doc=new Element('document');doc.root=true;doc.ownerDocument=doc;doc.createElement=tag=>Object.assign(new Element(tag),{ownerDocument:doc});doc.body=doc.createElement('body');doc.append(doc.body);const main=doc.createElement('main');doc.body.append(main);
 const photo=(parent=main,type='.brand-object')=>{const frame=new Element('span',[type]);parent.append(frame);const image=doc.createElement('img');frame.append(image);return {frame,image}};
 let activeScope=null,mediaCallback,mediaContext,cleanup;const effects=[],observers=[],timers=new Map();let id=0;
 const scope=fn=>{const previous=activeScope;const own=[];const result={revert(){for(const e of own)e.killed=true}};activeScope=own;fn();activeScope=previous;return result};
 const effect=(target,vars)=>{const e={target,vars,killed:false};effects.push(e);activeScope?.push(e);return e};
 const gsap={registerPlugin(){},context:scope,fromTo(target,from,to){return effect(target,to)},to:effect,timeline(vars){const e=effect(null,vars);e.fromTo=()=>e;e.to=()=>e;return e},matchMedia(){return {add(_queries,cb){mediaCallback=cb;mediaContext=scope(()=>{cleanup=cb({conditions})})},revert(){cleanup?.();mediaContext?.revert()}}}};
 const ST={refresh(){}};const env=new Element('window');env.setTimeout=fn=>{timers.set(++id,fn);return id};env.clearTimeout=id=>timers.delete(id);env.MutationObserver=class{constructor(fn){this.fn=fn;observers.push(this)}observe(target,options){this.target=target;this.options=options}disconnect(){this.disconnected=true}};
 const mount=()=>mountArtMotion(main,{gsap,ScrollTrigger:ST},env);
 return {doc,main,photo,effects,observers,timers,env,mount,Element,flush(){for(const [id,fn] of [...timers]){timers.delete(id);fn()}},change(next){cleanup?.();mediaContext.revert();conditions=next;mediaContext=scope(()=>{cleanup=mediaCallback({conditions})})}};
}

test('reduced motion leaves product images and link content untouched',()=>{
 const s=setup({motion:false});const {frame,image}=s.photo();const dispose=s.mount();
 assert.equal(frame.firstElementChild,image);assert.equal(s.effects.length,0);assert.equal(s.observers.length,0);assert.equal(s.doc.body.children.length,1);dispose();
});

test('scroll progress remains reversible and refreshes do not duplicate image animations',()=>{
 const s=setup();const {frame,image}=s.photo();const dispose=s.mount();
 const plane=frame.firstElementChild;assert.equal(plane.firstElementChild,image);assert.equal(plane.className,'motion-plane');
 const animation=s.effects.find(e=>e.vars.scrollTrigger?.trigger===frame);assert.ok(animation.vars.scrollTrigger.scrub);assert.equal(animation.vars.scrollTrigger.once,undefined);
 const count=s.effects.length;s.observers[0].fn();s.flush();s.main.emit('load');s.flush();assert.equal(s.effects.length,count);
 assert.deepEqual(s.observers[0].options,{childList:true,subtree:true});dispose();assert.equal(frame.firstElementChild,image);assert.ok(s.effects.every(e=>e.killed));
});

test('replacing search results releases old animations and registers the new photos',()=>{
 const s=setup();const old=s.photo();const dispose=s.mount();const previous=s.effects.find(e=>e.vars.scrollTrigger?.trigger===old.frame);
 old.frame.remove();const next=s.photo();s.observers[0].fn();s.flush();
 assert.equal(previous.killed,true);assert.equal(old.frame.firstElementChild,old.image);assert.equal(next.frame.firstElementChild.className,'motion-plane');
 assert.equal(s.effects.filter(e=>!e.killed&&e.vars.scrollTrigger?.trigger===next.frame).length,1);dispose();
});

test('changing motion preference restores the DOM and removes pointer, observer and timer work',()=>{
 const s=setup({motion:true,desktop:true,fine:true,mobile:false});const {frame,image}=s.photo();
 const pair=new s.Element('section',['.editorial-pair']);s.main.append(pair);pair.append(s.doc.createElement('a'));pair.append(s.doc.createElement('a'));
 const dispose=s.mount();assert.equal(pair.classList.contains('has-stacked-motion'),false);assert.equal(s.doc.body.children.length,3);
 s.observers[0].fn();assert.equal(s.timers.size,1);s.change({motion:false,desktop:true,fine:true,mobile:false});
 assert.equal(frame.firstElementChild,image);assert.equal(pair.classList.contains('has-stacked-motion'),false);assert.equal(s.doc.body.children.length,1);assert.equal(s.timers.size,0);assert.equal(s.observers[0].disconnected,true);
 assert.ok([...s.main.listeners.values(),...s.env.listeners.values(),...s.doc.listeners.values()].every(set=>!set.size));assert.ok(s.effects.every(e=>e.killed));
 s.change({motion:true,desktop:false,fine:false,mobile:true});assert.equal(frame.firstElementChild.className,'motion-plane');assert.equal(pair.classList.contains('has-stacked-motion'),false);dispose();
});

test('home keeps useful image links without JavaScript and uses the lightweight purchase image',()=>{
 const home=fs.readFileSync('index.html','utf8');
 for(const label of ['제품 구매','제품 렌탈','기프트 구매'])assert.ok(home.includes('<strong>'+label+'</strong>'));
 for(const href of ['/catalog.html','/catalog.html?kind=rental','/gifts.html'])assert.ok(home.includes('href="'+href+'"'));
 assert.ok(home.includes('/assets/shop/thumbnails/imweb-13283.webp'));assert.ok(!home.includes('/assets/shop/departments/purchase.jpg'));
 assert.ok(!home.includes('motion-ribbon'));assert.ok(!home.includes('class="editorial-pair"'));assert.ok(!home.includes('{{'));
 const css=fs.readFileSync('assets/shop/shop.css','utf8');assert.ok(css.includes('.editorial-pair.has-stacked-motion:focus-within>a'));assert.ok(css.includes('a:focus-visible .motion-plane'));
});

test('hidden brand search results release scroll work and restore it when shown',()=>{
 const s=setup();const {frame,image}=s.photo();const dispose=s.mount();const old=s.effects.find(e=>e.vars.scrollTrigger?.trigger===frame);
 frame.hidden=true;s.observers[0].fn();s.flush();assert.equal(old.killed,true);assert.equal(frame.firstElementChild,image);
 frame.hidden=false;s.observers[0].fn();s.flush();assert.equal(frame.firstElementChild.className,'motion-plane');dispose();
});
