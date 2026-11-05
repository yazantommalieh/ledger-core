const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto("file://" + process.cwd() + "/architecture.html", { waitUntil: "load" });
  await p.pdf({ path: "architecture.pdf", format: "A4", printBackground: true, preferCSSPageSize: true,
    displayHeaderFooter: true, headerTemplate: "<span></span>",
    margin: { top: "9mm", bottom: "11.5mm", left: "14mm", right: "14mm" },
    footerTemplate: `<div style="font-size:6.6pt;color:#8a929c;width:100%;padding:0 14mm;font-family:Inter,Arial;line-height:1.3">
      <div style="display:flex;justify-content:space-between;align-items:flex-end">
        <div style="max-width:88%">References: CBUAE Consumer Protection Standards (Circular 8/2020) Art. 8 · CBUAE Regulations 29/2011 Annexure 2 (2018) · Federal Decree-Law No. 10 of 2025 · Visa/Mastercard hold timeframes. Drafted with Claude, as disclosed in the Part 1 WORKLOG.</div>
        <div><span class="pageNumber"></span> / <span class="totalPages"></span></div>
      </div></div>` });
  await b.close();
})();
