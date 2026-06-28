/*
 * MediaGallery — responsive thumbnail grid backed by GLightbox.
 *
 * Renders an array of Publive media-asset objects (as returned by the
 * list_media_assets / get_media_asset MCP tools) into a grid of thumbnails.
 * Clicking any thumbnail opens a fullscreen lightbox; all assets share one
 * data-gallery group so next/prev arrows, keyboard nav, and touch-swipe
 * walk the whole set.
 *
 * Plain (non-module) script — exposes `resolveMediaUrl` and `MediaGallery`
 * on `window`, matching the rest of authentication/static/js.
 */
(function (global) {
  'use strict';

  // Publive image CDN. Relative storage paths are resolved through this
  // fit-in/<size>/filters:format(webp) pattern; absolute URLs are passed through.
  var CDN_BASE = 'https://img-cdn.publive.online';

  // Inline SVG placeholder shown when an image fails to load, so a broken
  // asset never collapses the grid layout.
  var PLACEHOLDER =
    'data:image/svg+xml;charset=utf-8,' +
    encodeURIComponent(
      '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="150">' +
        '<rect width="100%" height="100%" fill="#f3f4f6"/>' +
        '<path d="M64 96l24-30 18 22 14-16 22 24z" fill="#d1d5db"/>' +
        '<circle cx="74" cy="58" r="9" fill="#d1d5db"/>' +
        '<text x="100" y="125" font-family="sans-serif" font-size="11" ' +
          'fill="#9ca3af" text-anchor="middle">image unavailable</text>' +
      '</svg>'
    );

  /**
   * Resolve a media asset `path` to a fully-qualified CDN URL.
   *
   * - Already-absolute URLs (http/https) are returned unchanged — no double-prefixing.
   * - Relative storage paths (e.g. "odishatv/media/media_files/photo-x.jpeg")
   *   are wrapped in the CDN fit-in/<size>/webp transform.
   *
   * @param {string} path  storage path or absolute URL
   * @param {string} [size="1200x800"]  "<width>x<height>" for the CDN transform
   * @returns {string}
   */
  function resolveMediaUrl(path, size) {
    if (!path) return '';
    if (/^https?:\/\//i.test(path)) return path; // already a full URL — use as-is
    size = size || '1200x800';
    var clean = String(path).replace(/^\/+/, ''); // drop any leading slashes
    return CDN_BASE + '/fit-in/' + size + '/filters:format(webp)/' + clean;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // GLightbox reads title/description from the `data-glightbox` attribute when
  // formatted as "title: ...; description: ...".
  function buildCaption(asset) {
    var title = asset.alt_text || asset.filename || '';
    var desc = asset.caption || '';
    var parts = [];
    if (title) parts.push('title: ' + title);
    if (desc) parts.push('description: ' + desc);
    return parts.join('; ');
  }

  /**
   * @param {string|HTMLElement} container  element or selector to render into
   * @param {object} [options]
   * @param {string} [options.thumbSize="200x150"]  CDN size for grid thumbnails
   * @param {string} [options.fullSize="1200x800"]  CDN size for the lightbox view
   * @param {string} [options.galleryName="publive-media"]  shared data-gallery group
   */
  function MediaGallery(container, options) {
    this.el =
      typeof container === 'string'
        ? document.querySelector(container)
        : container;
    if (!this.el) throw new Error('MediaGallery: container not found');

    options = options || {};
    this.thumbSize = options.thumbSize || '200x150';
    this.fullSize = options.fullSize || '1200x800';
    this.galleryName = options.galleryName || 'publive-media';
    this.lightbox = null;
    this.assets = [];
  }

  MediaGallery.prototype._itemHtml = function (asset) {
    var thumb = resolveMediaUrl(asset.path, this.thumbSize);
    var full = resolveMediaUrl(asset.path, this.fullSize);
    var caption = buildCaption(asset);
    var label = asset.filename || asset.alt_text || 'Media asset';

    // The <a> is the GLightbox trigger; the <img> is the visible thumbnail.
    return (
      '<a class="mg-item glightbox" href="' + escapeHtml(full) + '"' +
      ' data-gallery="' + escapeHtml(this.galleryName) + '"' +
      ' data-glightbox="' + escapeHtml(caption) + '"' +
      ' data-type="image" aria-label="' + escapeHtml(label) + '">' +
      '<img class="mg-thumb" loading="lazy" alt="' + escapeHtml(asset.alt_text || label) + '"' +
      ' src="' + escapeHtml(thumb) + '"' +
      ' onerror="this.onerror=null;this.src=\'' + PLACEHOLDER + '\';' +
      'this.classList.add(\'mg-thumb--broken\');" />' +
      (asset.caption || asset.filename
        ? '<span class="mg-caption">' + escapeHtml(asset.caption || asset.filename) + '</span>'
        : '') +
      '</a>'
    );
  };

  MediaGallery.prototype.render = function () {
    if (!this.assets.length) {
      this.el.innerHTML = '<p class="mg-empty">No media assets to display.</p>';
      return;
    }
    var html = '';
    for (var i = 0; i < this.assets.length; i++) {
      html += this._itemHtml(this.assets[i]);
    }
    this.el.innerHTML = html;
  };

  // Destroy any prior instance before re-creating, so paginating/filtering the
  // asset list never leaves stale bindings pointing at removed DOM nodes.
  MediaGallery.prototype._initLightbox = function () {
    if (this.lightbox) {
      this.lightbox.destroy();
      this.lightbox = null;
    }
    if (typeof global.GLightbox !== 'function') {
      console.warn('MediaGallery: GLightbox not loaded — thumbnails will open as plain links.');
      return;
    }
    this.lightbox = global.GLightbox({
      selector: '.glightbox[data-gallery="' + this.galleryName + '"]',
      touchNavigation: true, // mobile swipe
      keyboardNavigation: true, // desktop arrows
      loop: true,
    });
  };

  /**
   * Replace the displayed assets and rebuild the lightbox. Safe to call on
   * every pagination / filter change.
   * @param {Array<object>} assets
   */
  MediaGallery.prototype.setAssets = function (assets) {
    this.assets = Array.isArray(assets) ? assets : [];
    this.render();
    this._initLightbox();
    return this;
  };

  MediaGallery.prototype.destroy = function () {
    if (this.lightbox) {
      this.lightbox.destroy();
      this.lightbox = null;
    }
    this.el.innerHTML = '';
  };

  global.resolveMediaUrl = resolveMediaUrl;
  global.MediaGallery = MediaGallery;
})(window);
