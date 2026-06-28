/*
 * Gallery page controller — fetches media assets from /media/assets (a thin
 * session-authenticated proxy over the list_media_assets CMS tool) and feeds
 * them into a MediaGallery. Pagination re-runs setAssets(), which destroys and
 * re-creates the GLightbox instance so bindings never go stale.
 */
(function () {
  'use strict';

  var gallery = new MediaGallery('#mediaGrid', { galleryName: 'publive-media' });

  var state = { page: 1, limit: 24 };

  var statusEl = document.getElementById('galleryStatus');
  var prevBtn = document.getElementById('prevPage');
  var nextBtn = document.getElementById('nextPage');
  var pageLabel = document.getElementById('pageLabel');

  function setBusy(busy) {
    if (prevBtn) prevBtn.disabled = busy || state.page <= 1;
    if (nextBtn) nextBtn.disabled = busy;
  }

  async function load() {
    setBusy(true);
    if (statusEl) statusEl.textContent = 'Loading media…';
    try {
      var res = await fetch(
        '/media/assets?page=' + state.page + '&limit=' + state.limit,
        { credentials: 'include' }
      );
      if (res.status === 401) {
        window.location.href = '/connect';
        return;
      }
      var data = await res.json();
      var assets = data.assets || [];
      gallery.setAssets(assets);

      if (pageLabel) pageLabel.textContent = 'Page ' + state.page;
      if (statusEl) {
        statusEl.textContent = assets.length
          ? assets.length + ' asset' + (assets.length === 1 ? '' : 's') + ' on this page'
          : 'No more assets.';
      }
      // Disable "next" when the page came back short of a full page.
      if (nextBtn) nextBtn.disabled = assets.length < state.limit;
      if (prevBtn) prevBtn.disabled = state.page <= 1;
    } catch (e) {
      if (statusEl) statusEl.textContent = 'Could not load media. Please try again.';
    } finally {
      if (prevBtn && state.page <= 1) prevBtn.disabled = true;
    }
  }

  if (prevBtn) {
    prevBtn.addEventListener('click', function () {
      if (state.page > 1) {
        state.page -= 1;
        load();
      }
    });
  }
  if (nextBtn) {
    nextBtn.addEventListener('click', function () {
      state.page += 1;
      load();
    });
  }

  load();
})();
