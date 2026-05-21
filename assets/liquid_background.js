(function () {
  const root = document.documentElement;
  let targetX = 0.5;
  let targetY = 0.35;
  let currentX = targetX;
  let currentY = targetY;
  let ticking = false;

  function update() {
    currentX += (targetX - currentX) * 0.08;
    currentY += (targetY - currentY) * 0.08;

    root.style.setProperty("--mouse-x", `${(currentX * 100).toFixed(2)}%`);
    root.style.setProperty("--mouse-y", `${(currentY * 100).toFixed(2)}%`);
    root.style.setProperty("--float-x", `${((currentX - 0.5) * 28).toFixed(2)}px`);
    root.style.setProperty("--float-y", `${((currentY - 0.5) * 28).toFixed(2)}px`);

    if (Math.abs(targetX - currentX) > 0.001 || Math.abs(targetY - currentY) > 0.001) {
      window.requestAnimationFrame(update);
    } else {
      ticking = false;
    }
  }

  function onPointerMove(event) {
    targetX = event.clientX / Math.max(window.innerWidth, 1);
    targetY = event.clientY / Math.max(window.innerHeight, 1);
    if (!ticking) {
      ticking = true;
      window.requestAnimationFrame(update);
    }
  }

  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    window.addEventListener("pointermove", onPointerMove, { passive: true });
  }
})();
