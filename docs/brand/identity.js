(() => {
  const rail = document.querySelector("[data-rail]");
  const menuButton = document.querySelector("[data-menu]");
  const navLinks = [...document.querySelectorAll('.rail-nav a[href^="#"]')];
  const sections = [...document.querySelectorAll("[data-section]")];

  const closeMenu = () => {
    if (!rail || !menuButton) return;
    rail.dataset.open = "false";
    menuButton.setAttribute("aria-expanded", "false");
    menuButton.setAttribute("aria-label", "فتح الفصول");
  };

  menuButton?.addEventListener("click", () => {
    const willOpen = rail?.dataset.open !== "true";
    if (rail) rail.dataset.open = String(willOpen);
    menuButton.setAttribute("aria-expanded", String(willOpen));
    menuButton.setAttribute("aria-label", willOpen ? "إغلاق الفصول" : "فتح الفصول");
  });

  navLinks.forEach((link) => link.addEventListener("click", closeMenu));

  if ("IntersectionObserver" in window) {
    const linkById = new Map(navLinks.map((link) => [link.hash.slice(1), link]));
    const visible = new Map();

    const updateCurrent = () => {
      const current = [...visible.entries()]
        .filter(([, ratio]) => ratio > 0)
        .sort((a, b) => b[1] - a[1])[0]?.[0];

      if (!current) return;
      navLinks.forEach((link) => link.removeAttribute("aria-current"));
      linkById.get(current)?.setAttribute("aria-current", "true");
    };

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => visible.set(entry.target.id, entry.intersectionRatio));
        updateCurrent();
      },
      { rootMargin: "-18% 0px -62%", threshold: [0, 0.1, 0.25, 0.5, 0.75] },
    );

    sections.forEach((section) => observer.observe(section));
  }

  const directionButton = document.querySelector("[data-direction-toggle]");
  const directionSurface = document.querySelector("[data-direction-surface]");

  directionButton?.addEventListener("click", () => {
    if (!directionSurface) return;
    const next = directionSurface.dir === "rtl" ? "ltr" : "rtl";
    directionSurface.dir = next;
    directionButton.textContent = next === "rtl" ? "عرض LTR" : "عرض RTL";
  });
})();
