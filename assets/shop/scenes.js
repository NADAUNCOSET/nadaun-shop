/** Section-scale scroll choreography. Default HTML stays fully visible. */
export function mountScenes(main,{gsap,ScrollTrigger:ST,motionPreference='system'},env=window){
 if(!main||!gsap||!ST)return ()=>{};
 const doc=main.ownerDocument,media=gsap.matchMedia();
 const motion=motionPreference==='on'?'all':motionPreference==='off'?'not all':'(prefers-reduced-motion:no-preference)';
 media.add({motion,mobile:'(max-width:700px)'},context=>{
  if(!context.conditions.motion)return;
  doc.body.dataset.motionActive='true';
  const scenes=[...main.querySelectorAll('.home-scene')];
  const mobile=context.conditions.mobile;
  const observer=new env.IntersectionObserver(entries=>{
   for(const entry of entries)entry.target.classList.toggle('is-in-view',entry.isIntersecting&&!doc.hidden);
  },{threshold:0,rootMargin:'40px 0px'});
  for(const scene of scenes){
   observer.observe(scene);
   const grid=scene.querySelector('.scene-grid'),title=scene.querySelectorAll('.motion-line>span');
   const heading=scene.querySelector('.section-head'),secondary=scene.querySelectorAll('.section-index,.section-head p,.section-head .text-button');
   const intro=gsap.timeline({scrollTrigger:{trigger:heading,start:'top 94%',end:'top 48%',scrub:.55,invalidateOnRefresh:true}});
   intro.fromTo(title,{yPercent:125},{yPercent:0,ease:'power3.out',duration:1})
    .fromTo(secondary,{y:24,opacity:.12},{y:0,opacity:1,ease:'power2.out',duration:.65,stagger:.07},.16);
   if(grid)gsap.fromTo(grid,{y:mobile?42:85,scale:mobile?.985:.95,clipPath:'inset(0% 0% 16% 0%)'},{y:0,scale:1,clipPath:'inset(0% 0% 0% 0%)',ease:'power2.out',scrollTrigger:{trigger:grid,start:'top 100%',end:'top 35%',scrub:.65,invalidateOnRefresh:true}});
   gsap.fromTo(scene,{'--scene-line':0},{'--scene-line':1,ease:'none',scrollTrigger:{trigger:scene,start:'bottom 105%',end:'bottom 55%',scrub:.45}});
  }
  // The existing banner keeps its uploaded aspect ratio and native controls.
  const banner=main.querySelector('.shop-banner-stage');
  if(banner)gsap.fromTo(banner,{scale:1,opacity:1},{scale:.97,opacity:.4,ease:'none',scrollTrigger:{trigger:banner,start:'top top',end:'bottom top',scrub:.5}});
  const visibility=()=>{
   for(const scene of scenes){
    const rect=scene.getBoundingClientRect();
    scene.classList.toggle('is-in-view',!doc.hidden&&rect.bottom>0&&rect.top<env.innerHeight);
   }
  };
  doc.addEventListener('visibilitychange',visibility);
  ST.refresh();
  return ()=>{observer.disconnect();doc.removeEventListener('visibilitychange',visibility);for(const scene of scenes)scene.classList.remove('is-in-view');doc.body.dataset.motionActive='false'};
 });
 return ()=>media.revert();
}
