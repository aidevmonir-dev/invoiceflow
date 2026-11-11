(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var doc = JSON.parse($("payload").textContent);
  var linesBody = $("lines"), saved = $("saved");
  var timer = null, saving = null;

  function csrf() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" },
      body: payload ? JSON.stringify(payload) : null,
    }).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
        return data;
      });
    });
  }

  function get(obj, path) {
    return path.split(".").reduce(function (o, k) { return o == null ? null : o[k]; }, obj);
  }
  function put(obj, path, value) {
    var parts = path.split("."), last = parts.pop();
    var target = parts.reduce(function (o, k) { o[k] = o[k] || {}; return o[k]; }, obj);
    target[last] = value;
  }
  function show(value) { return value === null || value === undefined ? "" : String(value); }

  // ---- render ------------------------------------------------------------------------------
  var SOURCE = {
    ai: "Values read from the document by the AI model. Compare them with the original before approving.",
    "stored-example": "Stored example: no AI model is connected, so these are the values printed on the sample, loaded from a file.",
    manual: "Entered by hand.",
  };

  function renderStatus() {
    var pill = $("status-pill");
    pill.textContent = doc.status_label;
    pill.className = "pill pill-" + doc.status;
    $("source").textContent = SOURCE[doc.source] || "";
    var approved = doc.status === "approved";
    $("approve").hidden = approved;
    $("reopen").hidden = !approved;
    $("form").querySelectorAll("input, select, button").forEach(function (el) { el.disabled = approved; });
  }

  function renderChecks() {
    var box = $("checks");
    box.textContent = "";
    document.querySelectorAll(".flag").forEach(function (el) { el.classList.remove("flag"); });
    if (!doc.checks) return;
    var head = document.createElement("p");
    head.className = "checks-head " + (doc.checks.failed ? "bad" : "good");
    head.textContent = doc.checks.failed
      ? doc.checks.failed + (doc.checks.failed === 1 ? " check needs" : " checks need") + " attention before approving"
      : "All " + doc.checks.passed + " checks passed";
    box.appendChild(head);
    var list = document.createElement("ul");
    doc.checks.checks.forEach(function (c) {
      var li = document.createElement("li");
      li.className = c.ok ? "ok" : "fail";
      li.textContent = c.message;
      list.appendChild(li);
      if (!c.ok && c.field) {
        var target = document.querySelector('[data-field="' + c.field + '"]');
        if (target) target.classList.add("flag");
      }
    });
    box.appendChild(list);
  }

  function lineRow(item) {
    var tr = document.createElement("tr");
    [["description", "text"], ["quantity", "num"], ["unit_price", "num"], ["amount", "num"], ["vat_rate", "num"]].forEach(function (col) {
      var td = document.createElement("td");
      if (col[1] === "num") td.className = "num";
      var input = document.createElement("input");
      input.type = "text";
      input.inputMode = col[1] === "num" ? "decimal" : "text";
      input.setAttribute("data-col", col[0]);
      input.setAttribute("aria-label", col[0].replace("_", " "));
      input.value = show(item[col[0]]);
      td.appendChild(input);
      tr.appendChild(td);
    });
    var td = document.createElement("td");
    var remove = document.createElement("button");
    remove.type = "button";
    remove.className = "link";
    remove.textContent = "Remove";
    remove.addEventListener("click", function () { tr.remove(); schedule(); });
    td.appendChild(remove);
    tr.appendChild(td);
    return tr;
  }

  function renderForm() {
    document.querySelectorAll("#fields [data-key]").forEach(function (el) {
      el.value = show(get(doc.data, el.getAttribute("data-key")));
    });
    linesBody.textContent = "";
    (doc.data.line_items || []).forEach(function (item) { linesBody.appendChild(lineRow(item)); });
  }

  function render() {
    renderStatus();
    if (doc.status === "failed") {
      $("failed").hidden = false;
      $("failed").textContent = doc.error + " ";
      var manual = document.createElement("button");
      manual.type = "button";
      manual.className = "link";
      manual.textContent = "Enter the values by hand";
      manual.addEventListener("click", function () {
        post("/api/documents/" + doc.id + "/manual").then(function (d) { doc = d; $("failed").hidden = true; render(); });
      });
      $("failed").appendChild(manual);
      $("editor").hidden = true;
      return;
    }
    $("editor").hidden = false;
    renderForm();
    renderChecks();
  }

  // ---- edit and save -----------------------------------------------------------------------
  function collect() {
    var data = JSON.parse(JSON.stringify(doc.data));
    document.querySelectorAll("#fields [data-key]").forEach(function (el) {
      var value = el.value.trim();
      put(data, el.getAttribute("data-key"), value === "" ? null : value);
    });
    data.line_items = Array.prototype.map.call(linesBody.querySelectorAll("tr"), function (tr) {
      var item = {};
      tr.querySelectorAll("input").forEach(function (input) {
        var value = input.value.trim();
        item[input.getAttribute("data-col")] = value === "" ? null : value;
      });
      return item;
    });
    // A reviewer who edits a field has checked it, so it is no longer flagged as uncertain.
    data.uncertain_fields = [];
    return data;
  }

  function saveNow() {
    clearTimeout(timer);
    saved.textContent = "Saving...";
    saving = post("/api/documents/" + doc.id + "/save", { data: collect() })
      .then(function (d) {
        doc = d;
        renderChecks();
        saved.textContent = "Saved";
      })
      .catch(function (err) { saved.textContent = err.message; });
    return saving;
  }

  function schedule() {
    saved.textContent = "";
    clearTimeout(timer);
    timer = setTimeout(saveNow, 700);
  }

  $("form").addEventListener("input", schedule);
  $("form").addEventListener("change", schedule);
  $("add-line").addEventListener("click", function () {
    linesBody.appendChild(lineRow({}));
    linesBody.lastChild.querySelector("input").focus();
  });

  $("approve").addEventListener("click", function () {
    var pending = timer ? saveNow() : (saving || Promise.resolve());
    pending.then(function () {
      if (doc.checks && doc.checks.failed && !window.confirm(doc.checks.failed + " check(s) still fail. Approve anyway?")) return;
      return post("/api/documents/" + doc.id + "/approve").then(function (d) { doc = d; render(); saved.textContent = "Approved. It is now included in the export."; });
    }).catch(function (err) { saved.textContent = err.message; });
  });
  $("reopen").addEventListener("click", function () {
    post("/api/documents/" + doc.id + "/reopen").then(function (d) { doc = d; render(); saved.textContent = "Reopened for changes."; });
  });
  $("delete").addEventListener("click", function () {
    if (!window.confirm("Delete this document and its data?")) return;
    post("/api/documents/" + doc.id + "/delete").then(function () { window.location.href = "/"; });
  });

  render();
})();
