// DOM smoke test for audit.html — requires: npm i jsdom (any dir, then run node audit_ui_test.js)
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const HTML = fs.readFileSync(path.join(__dirname, "audit.html"), "utf8");

let pass = 0, fail = 0;
const check = (name, cond, extra) => {
  if (cond) { pass++; console.log("  ok  " + name); }
  else { fail++; console.log("  FAIL " + name + (extra !== undefined ? " => " + JSON.stringify(extra) : "")); }
};

const dom = new JSDOM(HTML, {
  url: "http://localhost/",
  runScripts: "dangerously",
  pretendToBeVisual: true
});
const { window } = dom;
const doc = window.document;
window.Element.prototype.scrollIntoView = function () {};

setTimeout(() => {
  const $ = s => doc.querySelector(s);
  check("engine exported to window", !!window.AQ);
  check("dropzone visible initially", $("#drop").style.display !== "none");
  check("report hidden initially", $("#report").style.display === "none");
  check("settings hidden initially", $("#settings").style.display !== "block");
  check("loading overlay hidden initially", !$("#loading").classList.contains("on"));

  // --- load example (async now) ---
  $("#exampleBtn").click();
  check("loading overlay appears synchronously on upload",
    $("#loading").classList.contains("on"));

  setTimeout(() => {
    check("loading overlay hidden after analyze done",
      !$("#loading").classList.contains("on"));
    check("report shown after example", $("#report").style.display === "block");
    check("dropzone hidden after example", $("#drop").style.display === "none");
    check("save button shown", $("#saveBtn").style.display === "inline-block");
    check("summary cards rendered", $("#cards").children.length === 5,
      $("#cards").children.length);
    check("score card has number", /\d+/.test($("#cards").textContent));
    const issues = doc.querySelectorAll("#issues details.issue");
    check("issue cards rendered", issues.length > 5, issues.length);
    check("issue count label filled", $("#issueCount").textContent.length > 2,
      $("#issueCount").textContent);
    const colRows = doc.querySelectorAll("#cols tbody tr");
    check("column profile rows = 7", colRows.length === 7, colRows.length);
    const sampleRows = doc.querySelectorAll("#sample tbody tr");
    check("sample rows = 8", sampleRows.length === 8, sampleRows.length);
    check("filter chips rendered", doc.querySelectorAll("#filters .chip").length >= 10);

    // --- upper report of a 2nd upload still works + overlay for xlsx-less path ---
    $("#exampleBtn").click();                    // re-uploading overwrites
    check("overlay again on re-upload", $("#loading").classList.contains("on"));

    // --- filter ---
    const critChip = [...doc.querySelectorAll("#filters .chip")]
      .find(c => c.dataset.f === "critical");
    critChip.click();
    const critIssues = doc.querySelectorAll("#issues details.issue");
    check("critical filter narrows list", critIssues.length > 0 &&
      critIssues.length < issues.length, critIssues.length);
    check("critical filter shows only critical",
      [...critIssues].every(d => d.querySelector(".badge.b-critical")),
      [...critIssues].map(d => d.className));
    [...doc.querySelectorAll("#filters .chip")]
      .find(c => c.dataset.f === "all").click();
    check("all filter restores list",
      doc.querySelectorAll("#issues details.issue").length === issues.length);

    // --- local search ---
    const q = $("#q");
    q.value = "duplicate";
    q.dispatchEvent(new window.Event("input"));
    setTimeout(() => {
      const results = doc.querySelectorAll("#results .r[data-ref]");
      check("search finds duplicates", results.length > 0, results.length);
      check("search results have badges",
        [...results].every(r => r.querySelector(".badge")));
      results[0].click();
      const ref = results[0].dataset.ref;
      check("clicked result opens its issue", doc.getElementById(ref).open === true);

      // no-hit query
      q.value = "zzzznotfound";
      q.dispatchEvent(new window.Event("input"));
      setTimeout(() => {
        check("no-hit message shown", /No finding matches/.test($("#results").textContent),
          $("#results").textContent.slice(0, 80));

        // --- Ask AI: local provider without a model (default) ---
        window.localStorage.clear();
        check("provider defaults to local", $("#provider").value === "local");
        check("ollama status text filled (unreachable here)",
          $("#ollamaStatus").textContent.length > 0, $("#ollamaStatus").textContent);
        q.value = "which columns have missing values";
        $("#aiBtn").click();
        check("local-no-model explains + opens settings",
          $("#ai").textContent.includes("No local model selected") &&
          $("#settings").style.display === "block",
          $("#ai").textContent.slice(0, 160));

        // --- Ask AI: Gemini without a key ---
        $("#provider").value = "gemini";
        $("#gmodel").value = "gemini-3.5-flash-lite";
        $("#apiKey").value = "";
        q.value = "are there duplicates?";
        $("#aiBtn").click();
        setTimeout(() => {
          check("gemini-no-key error + opens settings",
            $("#ai").textContent.includes("no Gemini API key") &&
            $("#settings").style.display === "block",
            $("#ai").textContent.slice(-160));

          // --- AI second opinion with Gemini + no key → graceful failure box ---
          $("#scanBtn").click();
          setTimeout(() => {
          const scan = $("#aiscan").textContent || "";
          check("second-opinion failure box rendered",
            /failed|Second opinion/.test(scan), scan.slice(0, 120));

          // --- settings save persists provider ---
          $("#provider").value = "gemini";
          $("#apiKey").value = "test-key-123";
          $("#gmodel").value = "gemini-3.8-flash";
          $("#saveSet").click();
          check("gemini key saved to localStorage",
            window.localStorage.getItem("audit_gemini_key") === "test-key-123");
          check("gemini model saved to localStorage",
            window.localStorage.getItem("audit_gemini_model") === "gemini-3.8-flash");
          check("provider saved to localStorage",
            window.localStorage.getItem("audit_provider") === "gemini");
          check("settings closed after save", $("#settings").style.display === "none");

          console.log(`\n${pass} passed, ${fail} failed`);
          process.exit(fail ? 1 : 0);
          }, 200);
        }, 150);
      }, 250);
    }, 250);
  }, 200);
}, 100);