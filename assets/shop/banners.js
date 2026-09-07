/** Native controls remain usable with motion disabled; no catalogue request needed. */
export function mountBanners(root, env = window) {
  if (!root) return;
  const slides = [...root.querySelectorAll('.shop-banner-slide')];
  if (slides.length < 2) return;
  const reduced = env.matchMedia('(prefers-reduced-motion:reduce)');
  const doc = root.ownerDocument;
  const play = root.querySelector('[data-banner-play]');
  let index = 0, timer, paused = reduced.matches, hovering = false;
  const stop = () => { env.clearTimeout(timer); root.classList.remove('is-playing'); };
  const schedule = () => {
    stop();
    const running = !paused && !hovering && !doc.hidden;
    play.textContent = paused ? '▶' : 'Ⅱ';
    play.setAttribute('aria-label', paused ? '배너 자동 넘김 재생' : '배너 자동 넘김 일시정지');
    if (running) {
      // Restart the visual timer after every manual or automatic transition.
      void root.offsetWidth;
      root.classList.add('is-playing');
      timer = env.setTimeout(() => show(index + 1), 7000);
    }
  };
  const show = (next, announce = false) => {
    index = (next + slides.length) % slides.length;
    slides.forEach((slide, i) => {
      slide.classList.toggle('is-active', i === index);
      slide.inert = i !== index;
      slide.setAttribute('aria-hidden', String(i !== index));
    });
    const title = slides[index].dataset.bannerTitle;
    root.querySelector('.banner-caption').textContent = title;
    root.querySelector('.banner-counter').textContent = `${String(index + 1).padStart(2, '0')} / ${String(slides.length).padStart(2, '0')}`;
    if (announce) root.querySelector('[data-banner-status]').textContent = `${index + 1} / ${slides.length}, ${title}`;
    schedule();
  };
  root.querySelector('.banner-controls').hidden = false;
  root.querySelector('[data-banner-prev]').addEventListener('click', () => { paused = true; show(index - 1, true); });
  root.querySelector('[data-banner-next]').addEventListener('click', () => { paused = true; show(index + 1, true); });
  play.addEventListener('click', () => { paused = !paused; schedule(); });
  root.addEventListener('focusin', () => { paused = true; schedule(); });
  root.addEventListener('pointerenter', e => { if (e.pointerType === 'mouse') { hovering = true; schedule(); } });
  root.addEventListener('pointerleave', () => { hovering = false; schedule(); });
  doc.addEventListener('visibilitychange', schedule);
  reduced.addEventListener('change', () => { if (reduced.matches) { paused = true; schedule(); } });
  schedule();
}
