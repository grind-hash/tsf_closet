(() => {
  const tabs = Array.from(document.querySelectorAll("[data-view-target]"));
  const panels = Array.from(document.querySelectorAll(".view-panel"));

  const activateView = (targetId, focusTab = false) => {
    tabs.forEach((tab) => {
      const isActive = tab.dataset.viewTarget === targetId;
      tab.setAttribute("aria-selected", String(isActive));
      tab.tabIndex = isActive ? 0 : -1;
      tab.classList.toggle("view-switcher__button--active", isActive);
      if (isActive && focusTab) tab.focus();
    });
    panels.forEach((panel) => {
      panel.hidden = panel.id !== targetId;
    });
  };

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => activateView(tab.dataset.viewTarget));
    tab.addEventListener("keydown", (event) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      event.preventDefault();
      const offset = event.key === "ArrowRight" ? 1 : -1;
      const nextIndex = (index + offset + tabs.length) % tabs.length;
      activateView(tabs[nextIndex].dataset.viewTarget, true);
    });
  });
})();
