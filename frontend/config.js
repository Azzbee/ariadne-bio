/* Override before app.js when deploying the frontend separately from the API. */
window.ARIADNE_CONFIG = Object.assign({
  apiBase: '/api',
  snapshotManifest: './data/manifest.json',
  repository: 'https://github.com/Azzbee/ariadne-bio'
}, window.ARIADNE_CONFIG || {});
