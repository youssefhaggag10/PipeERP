export function printA4() {
  const style = window.document.createElement("style");
  style.id = "pipeerp-print-page-size";
  style.textContent = "@page { size: A4 portrait; margin: 0; }";
  window.document.getElementById(style.id)?.remove();
  window.document.head.appendChild(style);
  window.addEventListener("afterprint", () => style.remove(), { once: true });
  window.setTimeout(() => window.print(), 80);
}
