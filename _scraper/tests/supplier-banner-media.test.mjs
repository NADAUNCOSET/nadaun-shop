import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const code = fs.readFileSync('assets/shop/supplier-banner-media.js', 'utf8');
const {mountSupplierBannerMedia} = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
function setup() {
  const media = (name, value) => ({attrs: {[name]: value}, calls: 0,
    getAttribute(key) {return this.attrs[key];},
    setAttribute(key, value) {this.attrs[key] = value; this.calls++;},
    removeAttribute(key) {delete this.attrs[key];}});
  const slides = Array.from({length: 32}, (_, i) => ({active: i === 0,
    image: media('data-banner-src', `/banner-${i}.jpg`),
    source: media('data-banner-srcset', `/banner-${i}-mobile.jpg`),
    classList: {contains() {return slides[i].active;}},
    querySelectorAll(selector) {
      const element = selector === '[data-banner-src]' ? this.image : this.source;
      return element.getAttribute(selector.slice(1, -1)) ? [element] : [];
    }}));
  const root = {querySelectorAll: () => slides};
  let observer;
  class Observer {constructor(callback) {this.callback = callback; observer = this;}
    observe(root, options) {this.options = options;} disconnect() {this.stopped = true;}}
  const stop = mountSupplierBannerMedia(root, Observer);
  return {slides, observer, stop};
}
test('only the current and next originals load on initial arrival, regardless of carousel length', () => {
  const state = setup();
  assert.deepEqual(state.slides.filter(s => s.image.calls).map(s => s.image.attrs.src), ['/banner-0.jpg', '/banner-1.jpg']);
  assert.equal(state.slides[2].image.calls, 0);
  assert.deepEqual(state.observer.options.attributeFilter, ['class']);
});
test('manual/automatic slide changes load the new neighbor once, including mobile sources', () => {
  const state = setup();state.slides[0].active = false;state.slides[1].active = true;
  state.observer.callback();state.observer.callback();
  assert.equal(state.slides[2].image.attrs.src, '/banner-2.jpg');
  assert.equal(state.slides[2].source.attrs.srcset, '/banner-2-mobile.jpg');
  assert.equal(state.slides[2].image.calls, 1);assert.equal(state.slides[3].image.calls, 0);
  state.stop();assert.equal(state.observer.stopped, true);
});
test('empty/missing roots remain harmless and no inactive originals are loaded without an active slide', () => {
  assert.equal(typeof mountSupplierBannerMedia(null), 'function');
  const state = setup();for (const slide of state.slides) slide.active = false;
  state.observer.callback();assert.equal(state.slides[2].image.calls, 0);
});
