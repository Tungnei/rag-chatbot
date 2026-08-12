// Document management for the RAG API.
//
// Source names and uploaded filenames are user-supplied, so the same rule as the chat
// page holds: nodes are built with createElement and filled with textContent. The
// markup-injecting DOM APIs are barred outright and a test scans this file for them.

(function () {
  "use strict";

  // /ingest/upload reads the whole file into memory before writing it to disk and
  // enforces no size limit of its own. This is a courtesy bar on the browser side —
  // anyone can still POST directly. The real limit belongs on the server, in P3.
  var MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
  var ALLOWED_EXTENSIONS = [".txt", ".md", ".pdf"];

  var uploadForm = document.getElementById("upload-form");
  var fileInput = document.getElementById("file-input");
  var uploadStatus = document.getElementById("upload-status");
  var urlForm = document.getElementById("url-form");
  var urlInput = document.getElementById("url-input");
  var urlStatus = document.getElementById("url-status");
  var documentsList = document.getElementById("documents-list");
  var collectionCount = document.getElementById("collection-count");
  var listStatus = document.getElementById("list-status");
  var deleteForm = document.getElementById("delete-form");
  var deleteSourceInput = document.getElementById("delete-source-input");
  var deleteStatus = document.getElementById("delete-status");

  function setStatus(node, message, isError) {
    node.textContent = message;
    node.classList.toggle("error", Boolean(isError));
  }

  function hasAllowedExtension(name) {
    var lower = name.toLowerCase();
    return ALLOWED_EXTENSIONS.some(function (extension) {
      return lower.endsWith(extension);
    });
  }

  async function readError(response) {
    var text = await response.text();
    return "Lỗi " + response.status + ": " + text;
  }

  // The list and the chunk count come from two separate calls. Refreshing only one
  // leaves the page contradicting itself, so both always move together.
  async function refresh() {
    try {
      var [documentsResponse, collectionResponse] = await Promise.all([
        fetch("/documents"),
        fetch("/collections"),
      ]);

      if (!documentsResponse.ok) {
        setStatus(listStatus, await readError(documentsResponse), true);
        return;
      }

      var payload = await documentsResponse.json();
      renderDocuments(payload.documents || []);

      if (collectionResponse.ok) {
        var info = await collectionResponse.json();
        collectionCount.textContent =
          payload.total + " nguồn · " + info.points_count + " chunk";
      }
      setStatus(listStatus, "");
    } catch (err) {
      setStatus(listStatus, "Không gọi được API: " + err.message, true);
    }
  }

  function renderDocuments(documents) {
    documentsList.replaceChildren();

    if (!documents.length) {
      var empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Index đang rỗng.";
      documentsList.appendChild(empty);
      return;
    }

    documents.forEach(function (doc) {
      var row = document.createElement("div");
      row.className = "doc-row";

      var label = document.createElement("span");
      var title = doc.title ? " — " + doc.title : "";
      label.textContent = doc.source + title + " (" + doc.chunks + " chunk)";

      var button = document.createElement("button");
      button.type = "button";
      button.className = "danger-button";
      button.textContent = "Xoá";
      button.addEventListener("click", function () {
        removeSource(doc.source, doc.chunks);
      });

      row.appendChild(label);
      row.appendChild(button);
      documentsList.appendChild(row);
    });
  }

  // Deleting a source drops every chunk of it and cannot be undone, and the button
  // sits right next to the row — so the name and the cost are spelled out first.
  async function removeSource(source, chunks) {
    var detail = chunks === undefined ? "" : " (" + chunks + " chunk)";
    var confirmed = window.confirm(
      "Xoá toàn bộ chunk của nguồn “" + source + "”" + detail + "?\nKhông hoàn tác được."
    );
    if (!confirmed) {
      return;
    }

    try {
      var response = await fetch("/documents?source=" + encodeURIComponent(source), {
        method: "DELETE",
      });
      // 204 carries no body: parsing it as JSON would throw on a successful delete.
      if (response.status !== 204) {
        setStatus(deleteStatus, await readError(response), true);
        return;
      }
      setStatus(deleteStatus, "Đã xoá nguồn " + source + ".");
      await refresh();
    } catch (err) {
      setStatus(deleteStatus, "Không gọi được API: " + err.message, true);
    }
  }

  uploadForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    var file = fileInput.files[0];
    if (!file) {
      return;
    }
    if (!hasAllowedExtension(file.name)) {
      setStatus(uploadStatus, "Chỉ nhận .txt, .md, .pdf.", true);
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setStatus(uploadStatus, "File lớn hơn 10 MB, bị chặn trước khi gửi.", true);
      return;
    }

    var body = new FormData();
    body.append("file", file);
    setStatus(uploadStatus, "Đang tải lên và index…");

    try {
      var response = await fetch("/ingest/upload", { method: "POST", body: body });
      if (!response.ok) {
        setStatus(uploadStatus, await readError(response), true);
        return;
      }
      var result = await response.json();
      // Re-uploading a name replaces it: the pipeline drops the old chunks first.
      setStatus(
        uploadStatus,
        "Đã index " + result.source + ": " + result.chunks_indexed + " chunk (ghi đè nếu trùng tên)."
      );
      uploadForm.reset();
      await refresh();
    } catch (err) {
      setStatus(uploadStatus, "Không gọi được API: " + err.message, true);
    }
  });

  urlForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    var url = urlInput.value.trim();
    if (!url) {
      return;
    }
    setStatus(urlStatus, "Đang tải trang và index…");

    try {
      // /ingest takes exactly one of path or url; sending both is a 422. The page
      // keeps them on separate forms so that cannot happen by accident.
      var response = await fetch("/ingest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: url }),
      });
      if (!response.ok) {
        setStatus(urlStatus, await readError(response), true);
        return;
      }
      var result = await response.json();
      setStatus(urlStatus, "Đã index " + result.source + ": " + result.chunks_indexed + " chunk.");
      urlForm.reset();
      await refresh();
    } catch (err) {
      setStatus(urlStatus, "Không gọi được API: " + err.message, true);
    }
  });

  deleteForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var source = deleteSourceInput.value.trim();
    if (!source) {
      return;
    }
    deleteForm.reset();
    removeSource(source, undefined);
  });

  refresh();
})();
