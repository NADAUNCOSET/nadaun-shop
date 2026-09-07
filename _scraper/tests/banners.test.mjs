import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const {mountBanners}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/shop/banners.js','utf8')).toString('base64'));
function setup(reduce=false){
 const node=()=>({attrs:{},events:{},textContent:'',hidden:false,classList:{values:new Set(),add(k){this.values.add(k)},remove(k){this.values.delete(k)},toggle(k,on){on?this.add(k):this.remove(k)}},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){this.events[k]=f}});
 const doc=node();doc.hidden=false;const media=node();media.matches=reduce;
 const slides=Array.from({length:3},(_,i)=>Object.assign(node(),{dataset:{bannerTitle:'Brand '+i}}));
 const controls=Object.fromEntries(['[data-banner-play]','[data-banner-prev]','[data-banner-next]','[data-banner-status]','.banner-caption','.banner-counter','.banner-controls'].map(s=>[s,node()]));
 const root=Object.assign(node(),{ownerDocument:doc,querySelector:s=>controls[s],querySelectorAll:()=>slides});
 let nextId=0;const timers=new Map();const env={matchMedia:()=>media,setTimeout(f){timers.set(++nextId,f);return nextId},clearTimeout(id){timers.delete(id)}};
 mountBanners(root,env);return {root,doc,media,slides,controls,timers,click:s=>controls[s].events.click(),tick(){const [id,f]=timers.entries().next().value;timers.delete(id);f()}};
}
test('automatic banners cycle, with only the current link accessible',()=>{
 const s=setup();assert.equal(s.timers.size,1);s.tick();
 assert.equal(s.slides[1].inert,false);assert.equal(s.slides[0].inert,true);assert.equal(s.slides[2].attrs['aria-hidden'],'true');
 s.tick();s.tick();assert.equal(s.controls['.banner-counter'].textContent,'01 / 03');assert.equal(s.timers.size,1);
});
test('reduced motion keeps manual navigation, wrapping and announcements without autoplay',()=>{
 const s=setup(true);assert.equal(s.timers.size,0);s.click('[data-banner-prev]');
 assert.equal(s.controls['.banner-counter'].textContent,'03 / 03');assert.equal(s.slides[2].inert,false);
 assert.match(s.controls['[data-banner-status]'].textContent,/3 \/ 3, Brand 2/);assert.equal(s.timers.size,0);
});
test('focus and manual controls pause; hidden tabs never advance; replay requires an explicit action',()=>{
 const s=setup();s.doc.hidden=true;s.doc.events.visibilitychange();assert.equal(s.timers.size,0);
 s.doc.hidden=false;s.doc.events.visibilitychange();assert.equal(s.timers.size,1);
 s.root.events.focusin();assert.equal(s.timers.size,0);s.click('[data-banner-next]');assert.equal(s.timers.size,0);
 s.click('[data-banner-play]');assert.equal(s.timers.size,1);
 s.media.matches=true;s.media.events.change();assert.equal(s.timers.size,0);
});
test('published banners target existing pages and studio navigation has a standalone crawlable page',()=>{
 const home=fs.readFileSync('index.html','utf8');const config=JSON.parse(fs.readFileSync('data/catalog/banners.json','utf8'));
 assert.doesNotMatch(home,/나의 장비 찾기|\{\{/);
 assert.equal((home.match(/class="shop-banner-slide/g)||[]).length,config.banners.length);
 for(const b of config.banners){assert.ok(fs.existsSync(b.href.slice(1)),b.href);assert.ok(home.includes(b.desktop));assert.ok(home.includes(b.mobile))}
 const studio=fs.readFileSync('studio.html','utf8');assert.match(studio,/data-mode="studio"/);assert.match(studio,/2층 나다운 스튜디오/);
 assert.match(studio,/최소 2시간/);assert.doesNotMatch(studio,/class="product-card"|\{\{/);
 for(const file of ['index.html','catalog.html','checkout.html','services.html'])assert.match(fs.readFileSync(file,'utf8'),/class="nav-end" href="\/studio.html"/);
 assert.ok(fs.readFileSync('catalog-sitemap.xml','utf8').includes('https://shop.nadaun.co/studio.html'));
});
