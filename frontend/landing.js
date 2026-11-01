import { demoState, RECORDED_CASE } from './landing-model.js';
import { provenanceExampleURL } from './provenance-model.js';

/** Enhance the static introduction. No model inference or API calls occur here. */
export function initializeLanding(document, window) {
  const root = document.getElementById('overview-view');
  if (!root) return;
  const figure = document.getElementById('landing-case');
  const buttons = [...root.querySelectorAll('[data-demo-step]')];
  const write = (id, text) => { document.getElementById(id).textContent = text; };
  const format = value => new Intl.NumberFormat('en-US').format(value);
  for (const link of root.querySelectorAll('[data-example-link]')) link.href = provenanceExampleURL(window.location.href);

  function selectStep(key) {
    const step = demoState(key);
    figure.dataset.step = key;
    for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.demoStep === key));
    write('landing-rank', format(step.rank));
    write('landing-rank-label', step.rankLabel);
    write('landing-case-state', step.label);
    write('landing-case-status', step.status);
    write('landing-case-explanation', step.explanation);
    write('landing-case-detail', step.detail);
    write('landing-path-count', step.paths === null ? 'All choices checked' : `${format(step.paths)} supporting paths`);
    write('landing-demo-announcement', `${step.label}. ${step.rankLabel}: ${format(step.rank)}. ${step.detail}`);
  }
  for (const button of buttons) button.addEventListener('click', () => selectStep(button.dataset.demoStep));
  document.getElementById('landing-certificate-id').textContent = RECORDED_CASE.certificate.slice(0, 12);

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const motionButton = document.getElementById('landing-motion');
  let paused = reduced.matches;
  function updateMotion() {
    root.classList.toggle('motion-paused', paused || document.hidden);
    motionButton.setAttribute('aria-pressed', String(paused));
    motionButton.textContent = paused ? 'Play motion' : 'Pause motion';
  }
  motionButton.addEventListener('click', () => { paused = !paused; updateMotion(); });
  reduced.addEventListener('change', event => { paused = event.matches; updateMotion(); });
  document.addEventListener('visibilitychange', updateMotion);
  updateMotion();

  // Visible content is the default; an unavailable observer never hides it.
  if ('IntersectionObserver' in window && !reduced.matches) {
    const observer = new window.IntersectionObserver(entries => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-revealed');
          observer.unobserve(entry.target);
        }
      }
    }, { threshold: 0.12 });
    root.querySelectorAll('[data-reveal]').forEach(element => observer.observe(element));
  }
}
