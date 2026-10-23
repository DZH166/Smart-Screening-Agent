"use strict";
// Navigation only. Authentication and all mutations remain server-enforced.
(() => {
  const links = [...document.querySelectorAll(".admin-nav-item")];
  const sections = [...document.querySelectorAll("[data-admin-section]")];
  function show(name) {
    if (!["keys", "functions", "help"].includes(name)) name = "keys";
    sections.forEach(section => section.classList.toggle("hidden", section.dataset.adminSection !== name));
    links.forEach(link => {
      const selected = link.getAttribute("href") === `#${name}`;
      link.classList.toggle("active", selected);
      if (selected) link.setAttribute("aria-current", "page"); else link.removeAttribute("aria-current");
    });
    // Leaving the ledger also clears revealed credentials through its existing handler.
    const ledger = document.getElementById("ledger-details");
    if (name !== "keys" && ledger?.open) ledger.open = false;
  }
  links.forEach(link => link.addEventListener("click", event => {
    event.preventDefault();
    const name = link.getAttribute("href").slice(1);
    history.replaceState(null, "", `#${name}`); show(name);
  }));
  window.addEventListener("hashchange", () => show(location.hash.slice(1)));
  show(location.hash.slice(1));
})();
