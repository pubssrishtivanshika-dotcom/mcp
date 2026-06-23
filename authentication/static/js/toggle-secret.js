// Shared show/hide toggle for the API Secret field.
// Used by both the connect and authorize pages.
(function () {
  const toggle = document.getElementById('toggleSecret');
  const input = document.getElementById('apiSecret');
  if (!toggle || !input) return;

  toggle.addEventListener('click', function () {
    const isHidden = input.type === 'password';
    input.type = isHidden ? 'text' : 'password';
    const icon = toggle.querySelector('svg');
    if (icon) icon.style.opacity = isHidden ? '0.5' : '1';
  });
})();
