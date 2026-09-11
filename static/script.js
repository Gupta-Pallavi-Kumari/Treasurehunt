(() => {
  const body = document.body;
  const timer = document.querySelector('#timer');
  const scanMessage = document.querySelector('#scan-message');
  const scanner = document.querySelector('#scanner');
  const camera = document.querySelector('#camera-video');
  const cameraContainer = document.querySelector('#camera');
  let stream;
  let qrScanner;
  let scanInProgress = false;
  let lastViolation = 0;

  function formatDuration(seconds) {
    const hours = String(Math.floor(seconds / 3600)).padStart(2, '0');
    const minutes = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
    const remainder = String(seconds % 60).padStart(2, '0');
    return `${hours}:${minutes}:${remainder}`;
  }

  function updateTimer() {
    const timerElement = timer || document.querySelector('#game-timer');
    if (!timerElement || !body.dataset.gameStarted) return;
    const end = body.dataset.gameStopped ? new Date(body.dataset.gameStopped) : new Date();
    timerElement.textContent = formatDuration(Math.max(0, Math.floor((end - new Date(body.dataset.gameStarted)) / 1000)));
  }

  async function reportViolation() {
    if (!body.dataset.started || body.dataset.gameStatus !== 'RUNNING' || Date.now() - lastViolation < 2000 || body.dataset.status !== 'PLAYING') return;
    lastViolation = Date.now();
    const response = await fetch('/api/interruption', { method: 'POST' });
    const result = await response.json();
    if (!result.ok) return;
    body.dataset.status = result.status;
    const label = document.querySelector('#violation-label');
    if (label) label.textContent = `${result.violations} / 3 violations`;
    if (result.status === 'ELIMINATED') window.location.reload();
    else if (scanMessage) scanMessage.textContent = `Warning: Leaving the competition page is not allowed. (${result.violations}/3)`;
  }

  async function submitToken(token) {
    if (!token || scanInProgress) return;
    scanInProgress = true;
    scanMessage.textContent = 'Checking QR code...';
    const form = new FormData();
    form.append('token', token);
    const result = await (await fetch('/api/scan', { method: 'POST', body: form })).json();
    if (!result.ok) { scanMessage.textContent = result.message; scanInProgress = false; return; }
    if (result.completed) { window.location.reload(); return; }
    document.querySelector('#level-label').textContent = result.level.level_number;
    document.querySelector('#progress-bar').style.width = `${(result.level.level_number - 1) * 100 / 8}%`;
    document.querySelector('#clue').textContent = result.level.clue;
    document.querySelector('#hint-text').textContent = result.hint;
    document.querySelector('#hint .kicker').textContent = `Clue revealed for level ${result.revealed_level}`;
    document.querySelector('#hint').hidden = false;
    scanMessage.textContent = 'Correct QR code. Find the next location.';
    closeScanner();
    scanInProgress = false;
  }

  async function closeScanner() {
    if (qrScanner) {
      try { await qrScanner.stop(); } catch (_) { /* scanner may already be stopped */ }
      qrScanner.clear();
      qrScanner = null;
    }
    if (stream) stream.getTracks().forEach(track => track.stop());
    if (scanner) scanner.hidden = true;
  }

  document.querySelector('#manual-scan')?.addEventListener('submit', event => {
    event.preventDefault();
    const value = document.querySelector('#token').value.trim();
    submitToken(value.includes('/scan/') ? value.split('/scan/')[1].split(/[?#]/)[0] : value);
  });
  document.querySelector('#scan-button')?.addEventListener('click', async () => {
    scanner.hidden = false;
    if (window.Html5Qrcode && cameraContainer) {
      try {
        qrScanner = new Html5Qrcode('camera');
        await qrScanner.start({ facingMode: 'environment' }, { fps: 10, qrbox: { width: 240, height: 240 } }, decodedText => {
          submitToken(decodedText.split('/').pop());
        }, () => {});
        return;
      } catch (_) {
        await closeScanner();
        scanner.hidden = false;
      }
    }
    if (!('BarcodeDetector' in window) || !navigator.mediaDevices) {
      scanMessage.textContent = 'Camera scanning is unavailable here. Use the token fallback below.';
      return;
    }
    try {
      if (cameraContainer) cameraContainer.hidden = true;
      if (camera) camera.hidden = false;
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } } });
      camera.srcObject = stream;
      await camera.play();
      const detector = new BarcodeDetector({ formats: ['qr_code'] });
      const read = async () => {
        if (scanner.hidden) return;
        const codes = await detector.detect(camera);
        if (codes.length) { submitToken(codes[0].rawValue.split('/').pop()); return; }
        requestAnimationFrame(read);
      };
      read();
    } catch (_) { scanMessage.textContent = 'Camera access is required to scan the QR code. Please allow camera permission.'; }
  });
  document.querySelector('#close-scanner')?.addEventListener('click', closeScanner);
  document.addEventListener('visibilitychange', () => { if (document.hidden) reportViolation(); });
  window.addEventListener('blur', reportViolation);
  if (body.dataset.scan) submitToken(body.dataset.scan);
  updateTimer();
  if (timer) setInterval(updateTimer, 1000);
  if (document.querySelector('#game-timer')) setInterval(updateTimer, 1000);
  if (body.dataset.gameStatus === 'RUNNING' && document.querySelector('.admin-shell')) setTimeout(() => window.location.reload(), 10000);
  document.querySelectorAll('.duration').forEach(cell => {
    const started = cell.dataset.started;
    const finished = cell.dataset.finished;
    if (started) cell.textContent = formatDuration(Math.max(0, Math.floor(((finished ? new Date(finished) : new Date()) - new Date(started)) / 1000)));
  });
})();
