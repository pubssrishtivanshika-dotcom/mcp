document.getElementById('authorizeForm').addEventListener('submit', function () {
  const btn     = document.getElementById('authorizeBtn');
  const spinner = document.getElementById('spinner');
  const btnText = document.getElementById('btnText');
  btn.disabled = true;
  spinner.style.display = 'block';
  btnText.textContent = 'Verifying credentials…';
});
