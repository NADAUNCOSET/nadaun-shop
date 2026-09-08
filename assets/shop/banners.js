/** Auto-starting banners. Reduced-motion CSS removes the animated transition. */
export function mountBanners(root, env = window) {
  if (!root) return;
  const slides = [...root.querySelectorAll('.shop-banner-slide')];
  if (slides.length < 2) return;
  const doc = root.ownerDocument;
  const pause = root.querySelector('[data-banner-pause]');
  let index = 0, timer, paused = false, focusPaused = false;
  const stop = () => { env.clearTimeout(timer); root.classList.remove('is-playing'); };
  const schedule = () => {
    stop();
    const running = !paused && !focusPaused && !doc.hidden;
    root.dataset.bannerState = doc.hidden ? 'hidden' : paused ? 'paused' : focusPaused ? 'focused' : 'playing';
    if (pause) {
      pause.textContent = paused ? '배너 자동 넘김 켜기' : '배너 자동 넘김 멈추기';
      pause.setAttribute('aria-pressed', String(paused));
    }
    if (running) {
      // Restart the visual timer after every manual or automatic transition.
      void root.offsetWidth;
      root.classList.add('is-playing');
      timer = env.setTimeout(() => show(index + 1), 5000);
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
  const manual = (step, event) => { focusPaused = event.detail === 0; show(index + step, true); };
  root.querySelector('[data-banner-prev]').addEventListener('click', event => manual(-1, event));
  root.querySelector('[data-banner-next]').addEventListener('click', event => manual(1, event));
  // The keyboard/screen-reader pause control is revealed only when focused.
  pause?.addEventListener('click', () => { paused = !paused; schedule(); });
  root.addEventListener('focusin', event => {
    if (event.target.matches(':focus-visible')) { focusPaused = true; schedule(); }
  });
  root.addEventListener('focusout', event => {
    if (!root.contains(event.relatedTarget)) { focusPaused = false; schedule(); }
  });
  doc.addEventListener('visibilitychange', schedule);
  show(0);
}
