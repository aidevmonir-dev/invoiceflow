(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var status = $("status"), form = $("upload"), input = $("file");
  var busy = false;

  function csrf() {
    var m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = "status" + (kind ? " " + kind : "");
  }

  function post(url, body) {
    return fetch(url, { method: "POST", body: body, credentials: "same-origin", headers: { "X-CSRFToken": csrf() } })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
          return data;
        });
      });
  }

  function start(promise, label) {
    if (busy) return;
    busy = true;
    document.body.classList.add("working");
    setStatus(label + " This usually takes 10 to 30 seconds.", "");
    promise
      .then(function (doc) { window.location.href = "/documents/" + doc.id + "/"; })
      .catch(function (err) { setStatus(err.message, "bad"); busy = false; document.body.classList.remove("working"); });
  }

  function upload(file) {
    if (!file) return;
    var data = new FormData();
    data.append("file", file);
    start(post("/api/documents", data), "Reading " + file.name + ".");
    input.value = "";
  }

  $("pick").addEventListener("click", function () { input.click(); });
  input.addEventListener("change", function () { upload(input.files[0]); });
  ["dragenter", "dragover"].forEach(function (name) {
    form.addEventListener(name, function (e) { e.preventDefault(); form.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (name) {
    form.addEventListener(name, function (e) { e.preventDefault(); form.classList.remove("over"); });
  });
  form.addEventListener("drop", function (e) { upload(e.dataTransfer.files[0]); });

  document.querySelectorAll(".sample").forEach(function (btn) {
    btn.addEventListener("click", function () {
      start(post("/api/samples/" + btn.getAttribute("data-key")), "Reading the sample.");
    });
  });
})();
