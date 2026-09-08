import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const {mountBanners}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('assets/shop/banners.js','utf8')).toString('base64'));
function setup(reduce=false){
 const node=()=>({attrs:{},events:{},textContent:'',hidden:false,classList:{values:new Set(),add(k){this.values.add(k)},remove(k){this.values.delete(k)},toggle(k,on){on?this.add(k):this.remove(k)}},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){this.events[k]=f}});
 const doc=node();doc.hidden=false;const media=node();media.matches=reduce;
 const slides=Array.from({length:3},(_,i)=>Object.assign(node(),{dataset:{bannerTitle:'Brand '+i}}));
 const controls=Object.fromEntries(['[data-banner-pause]','[data-banner-prev]','[data-banner-next]','[data-banner-status]','.banner-caption','.banner-counter','.banner-controls'].map(s=>[s,node()]));
 const root=Object.assign(node(),{dataset:{},ownerDocument:doc,querySelector:s=>controls[s],querySelectorAll:()=>slides,contains:target=>Object.values(controls).includes(target)});
 let nextId=0;const timers=new Map(),delays=[];const env={matchMedia:()=>media,setTimeout(f,delay){delays.push(delay);timers.set(++nextId,f);return nextId},clearTimeout(id){timers.delete(id)}};
 mountBanners(root,env);return {root,doc,media,slides,controls,timers,delays,click:(s,detail=1)=>controls[s].events.click({detail}),leave(){root.events.focusout({relatedTarget:null})},focus(){root.events.focusin({target:{matches:()=>true}})},tick(){const [id,f]=timers.entries().next().value;timers.delete(id);f()}};
}
test('banners start automatically at five seconds and only the current link is accessible',()=>{
 const s=setup();assert.equal(s.timers.size,1);assert.equal(s.delays[0],5000);
 assert.equal(s.slides[0].inert,false);assert.equal(s.slides[1].inert,true);s.tick();
 assert.equal(s.slides[1].inert,false);assert.equal(s.slides[0].inert,true);assert.equal(s.slides[2].attrs['aria-hidden'],'true');
 s.tick();s.tick();assert.equal(s.controls['.banner-counter'].textContent,'01 / 03');assert.equal(s.timers.size,1);
});
test('reduced-motion visitors also get automatic rotation without an animated transition',()=>{
 const s=setup(true);assert.equal(s.timers.size,1);s.tick();assert.equal(s.slides[1].inert,false);
 assert.match(fs.readFileSync('assets/shop/shop.css','utf8'),/@media\(prefers-reduced-motion:reduce\)\{\.shop-banner-slide\{transition:none\}/);
});
test('mouse or touch navigation restarts the interval without leaving autoplay paused',()=>{
 const s=setup();s.click('[data-banner-prev]');assert.equal(s.controls['.banner-counter'].textContent,'03 / 03');
 assert.equal(s.timers.size,1);s.tick();assert.equal(s.controls['.banner-counter'].textContent,'01 / 03');
 s.click('[data-banner-next]');assert.equal(s.timers.size,1);s.tick();assert.equal(s.slides[2].inert,false);
 assert.match(s.controls['[data-banner-status]'].textContent,/2 \/ 3, Brand 1/);
});
test('keyboard focus pauses while reading and resumes when leaving the banner',()=>{
 const s=setup();s.focus();assert.equal(s.timers.size,0);s.click('[data-banner-next]',0);assert.equal(s.timers.size,0);
 s.root.events.focusout({relatedTarget:s.controls['[data-banner-prev]']});assert.equal(s.timers.size,0);
 s.leave();assert.equal(s.timers.size,1);s.tick();assert.equal(s.slides[2].inert,false);
});
test('hidden tabs suspend timers and resume with a full interval',()=>{
 const s=setup();s.doc.hidden=true;s.doc.events.visibilitychange();assert.equal(s.timers.size,0);
 s.doc.hidden=false;s.doc.events.visibilitychange();assert.equal(s.timers.size,1);assert.equal(s.delays.at(-1),5000);
});
test('the keyboard-accessible pause choice survives navigation, focus changes and tab switches',()=>{
 const s=setup();s.focus();s.click('[data-banner-pause]',0);s.leave();assert.equal(s.timers.size,0);
 s.click('[data-banner-next]');assert.equal(s.timers.size,0);
 s.doc.hidden=true;s.doc.events.visibilitychange();s.doc.hidden=false;s.doc.events.visibilitychange();assert.equal(s.timers.size,0);
 s.click('[data-banner-pause]');assert.equal(s.timers.size,1);
});
test('published banners target existing pages and studio navigation has a standalone crawlable page',()=>{
 const home=fs.readFileSync('index.html','utf8');const config=JSON.parse(fs.readFileSync('data/catalog/banners.json','utf8'));
 assert.doesNotMatch(home,/나의 장비 찾기|data-banner-play|\{\{/);
 assert.ok(home.includes('banner-accessibility-pause'));
 assert.equal((home.match(/class="shop-banner-slide/g)||[]).length,config.banners.length);
 for(const b of config.banners){assert.ok(fs.existsSync(new URL(b.href,'https://shop.nadaun.co').pathname.slice(1)),b.href);assert.ok(home.includes(b.desktop));assert.ok(home.includes(b.mobile))}
 const studio=fs.readFileSync('studio.html','utf8');assert.match(studio,/data-mode="studio"/);assert.match(studio,/2층 나다운 스튜디오/);
 assert.match(studio,/최소 2시간/);assert.doesNotMatch(studio,/class="product-card"|\{\{/);
 for(const file of ['index.html','catalog.html','checkout.html','services.html'])assert.match(fs.readFileSync(file,'utf8'),/class="nav-end" href="\/studio.html"/);
 assert.ok(fs.readFileSync('catalog-sitemap.xml','utf8').includes('https://shop.nadaun.co/studio.html'));
});

test('all brands are visible in the initial directory response and both entry points open it separately',()=>{
 const data=JSON.parse(fs.readFileSync('data/catalog/brands.json','utf8'));const page=fs.readFileSync('brands.html','utf8');
 assert.equal((page.match(/class="brand-tile"/g)||[]).length,data.brands.length);
 for(const brand of data.brands){assert.ok(page.includes('href="/brands/'+brand.id+'.html"'));assert.ok(page.includes(brand.representative_image.replaceAll('&','&amp;')))}
 assert.ok(page.includes('data-mode="brands"'));assert.ok(page.includes('id="brand-search"'));assert.ok(!page.includes('aria-expanded="false"'));
 for(const file of ['index.html','catalog.html','brands.html','brands/dji.html']){
  const html=fs.readFileSync(file,'utf8');assert.match(html,/<a href="\/brands.html" class="nav-brands" target="_blank" rel="noopener"/);
 }
 assert.match(fs.readFileSync('index.html','utf8'),/id="all-brands" href="\/brands.html" target="_blank" rel="noopener"/);
 assert.ok(fs.readFileSync('catalog-sitemap.xml','utf8').includes('https://shop.nadaun.co/brands.html'));
});
