/** Keep a large supplier carousel from downloading every original on arrival. */
export function mountSupplierBannerMedia(root, Observer = globalThis.MutationObserver) {
  if (!root) return () => {};
  const slides = [...root.querySelectorAll('.shop-banner-slide')];
  const load = slide => {
    if (!slide) return;
    for (const source of slide.querySelectorAll('[data-banner-srcset]')) {
      source.setAttribute('srcset', source.getAttribute('data-banner-srcset'));
      source.removeAttribute('data-banner-srcset');
    }
    for (const image of slide.querySelectorAll('[data-banner-src]')) {
      image.setAttribute('src', image.getAttribute('data-banner-src'));
      image.removeAttribute('data-banner-src');
    }
  };
  const update = () => {
    const active = slides.findIndex(slide => slide.classList.contains('is-active'));
    if (active < 0) return;
    load(slides[active]);
    load(slides[(active + 1) % slides.length]);
  };
  update();
  if (!Observer) return () => {};
  const observer = new Observer(update);
  observer.observe(root, {subtree: true, attributes: true, attributeFilter: ['class']});
  return () => observer.disconnect();
}

if (typeof document !== 'undefined') {
  for (const root of document.querySelectorAll('.shop-banner')) mountSupplierBannerMedia(root);
}
