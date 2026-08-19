// Chat page for the RAG API.
//
// Every string that reaches the DOM here originates in an indexed document, so it is
// untrusted: nodes are built with createElement and filled with textContent only.
// The markup-injecting DOM APIs are barred outright, and a test enforces that by
// scanning this file — which is why they are not even named here.

(function () {
  "use strict";

  var STORAGE_KEY = "rag-chat-params";

  // Page memory only, deliberately never written to storage: persisting it would
  // turn every stale assistant turn into long-lived input for the prompt. Pushed
  // strictly in user+assistant pairs, so the length stays even and slice(-6)
  // always starts on a user turn.
  var history = [];
  var MAX_HISTORY = 6;

  var form = document.getElementById("chat-form");
  var input = document.getElementById("question-input");
  var sendButton = document.getElementById("send-button");
  var messages = document.getElementById("messages");
  var sourcesPanel = document.getElementById("sources-panel");
  var sourcesCount = document.getElementById("sources-count");
  var topK = document.getElementById("top-k");
  var topKValue = document.getElementById("top-k-value");
  var includeSources = document.getElementById("include-sources");
  var historyCount = document.getElementById("history-count");

  // Cards for whichever answer's sources the panel is currently showing. Never a
  // record of "the latest answer": each answer owns its own source list and clicking
  // one of its citations repaints the panel from that list.
  var shownCards = [];

  function loadParams() {
    try {
      var saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      if (saved.topK >= 1 && saved.topK <= 20) {
        topK.value = String(saved.topK);
      }
      if (typeof saved.includeSources === "boolean") {
        includeSources.checked = saved.includeSources;
      }
    } catch (err) {
      // A corrupt entry is not worth failing the page over; defaults stand.
    }
    topKValue.textContent = topK.value;
  }

  function saveParams() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          topK: Number(topK.value),
          includeSources: includeSources.checked,
        })
      );
    } catch (err) {
      // Private mode or a full quota: parameters simply do not persist.
    }
  }

  function scrollToLatest() {
    messages.scrollTop = messages.scrollHeight;
  }

  function addMessage(className, text) {
    var node = document.createElement("div");
    node.className = "msg " + className;
    node.textContent = text;
    messages.appendChild(node);
    scrollToLatest();
    return node;
  }

  function highlight(number) {
    shownCards.forEach(function (card, index) {
      card.classList.toggle("active", index === number - 1);
    });
    var target = shownCards[number - 1];
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  // Splits on [n] with a capturing group, so odd indices are the numbers themselves.
  // A number with no matching source stays plain text: the model can cite [4] while
  // only three passages came back, and that must not throw or fake a link.
  //
  // Each answer closes over its OWN sources. A citation in an older answer therefore
  // repaints the panel with that answer's passages instead of indexing into whatever
  // the most recent question happened to return.
  function appendAnswer(container, text, sources) {
    var sourceTotal = sources.length;
    var parts = String(text).split(/\[(\d+)\]/g);
    parts.forEach(function (part, index) {
      if (index % 2 === 0) {
        if (part) {
          container.appendChild(document.createTextNode(part));
        }
        return;
      }
      var number = Number(part);
      if (number >= 1 && number <= sourceTotal) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "citation";
        button.textContent = "[" + number + "]";
        button.addEventListener("click", function () {
          renderSources(sources);
          highlight(number);
        });
        container.appendChild(button);
        return;
      }
      container.appendChild(document.createTextNode("[" + part + "]"));
    });
  }

  function renderSources(sources) {
    sourcesPanel.replaceChildren();
    shownCards = [];

    if (!sources.length) {
      var empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Câu trả lời này không kèm nguồn nào.";
      sourcesPanel.appendChild(empty);
      sourcesCount.textContent = "";
      return;
    }

    sources.forEach(function (source, index) {
      var card = document.createElement("article");
      card.className = "source-card";

      var head = document.createElement("div");
      head.className = "source-head";

      var name = document.createElement("span");
      var page = source.page ? ", trang " + source.page : "";
      name.textContent = "[" + (index + 1) + "] " + source.source + page;

      var score = document.createElement("span");
      score.className = "muted";
      score.textContent = Number(source.score).toFixed(3);

      head.appendChild(name);
      head.appendChild(score);

      var snippet = document.createElement("p");
      snippet.className = "snippet";
      snippet.textContent = source.snippet;

      card.appendChild(head);
      card.appendChild(snippet);
      sourcesPanel.appendChild(card);
      shownCards.push(card);
    });

    sourcesCount.textContent = sources.length + " đoạn";
  }

  function showSkeleton() {
    var skeleton = document.createElement("div");
    skeleton.className = "skeleton";
    for (var i = 0; i < 3; i += 1) {
      skeleton.appendChild(document.createElement("span"));
    }
    messages.appendChild(skeleton);
    scrollToLatest();
    return skeleton;
  }

  function renderAnswer(payload) {
    var sources = payload.sources || [];
    var node = document.createElement("div");
    node.className = "msg msg-bot";
    appendAnswer(node, payload.answer, sources);

    var meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent =
      payload.model +
      " · " +
      payload.latency_ms +
      " ms · " +
      payload.tokens_used +
      " tokens";
    node.appendChild(meta);

    messages.appendChild(node);
    renderSources(sources);
    scrollToLatest();
  }

  function rememberExchange(question, answer) {
    history.push({ role: "user", content: question });
    history.push({ role: "assistant", content: answer });
    if (history.length > MAX_HISTORY) {
      history = history.slice(-MAX_HISTORY);
    }
    updateHistoryCount();
  }

  function updateHistoryCount() {
    if (historyCount) {
      historyCount.textContent = "Đang gửi kèm: " + history.length / 2 + " lượt.";
    }
  }

  async function ask(question) {
    var skeleton = showSkeleton();
    // The textarea has to be disabled too, not just the button: requestSubmit() on
    // Enter submits regardless of the submit button's disabled state, which would let
    // two /query calls overlap and land their answers out of order.
    sendButton.disabled = true;
    input.disabled = true;

    try {
      var response = await fetch("/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: question,
          top_k: Number(topK.value),
          include_sources: includeSources.checked,
          history: history.slice(-MAX_HISTORY),
        }),
      });

      skeleton.remove();

      if (!response.ok) {
        var detail = await response.text();
        addMessage("msg-error", "Lỗi " + response.status + ": " + detail);
        return;
      }

      var payload = await response.json();
      renderAnswer(payload);
      // Recorded only once a real answer exists, and as a pair. Pushing the user turn
      // at submit time would leave an orphan behind whenever a request failed, and the
      // next request would then carry a history ending on a user turn.
      // A refusal still counts: the next turn needs to know this one found nothing.
      rememberExchange(question, payload.answer);
    } catch (err) {
      skeleton.remove();
      // Reached when the API is unreachable — including the case where the server
      // never started because Qdrant was down, in which case this page would not
      // have loaded either.
      addMessage("msg-error", "Không gọi được API: " + err.message);
    } finally {
      sendButton.disabled = false;
      input.disabled = false;
      input.focus();
    }
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var question = input.value.trim();
    if (!question) {
      return;
    }
    addMessage("msg-user", question);
    input.value = "";
    ask(question);
  });

  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  topK.addEventListener("input", function () {
    topKValue.textContent = topK.value;
    saveParams();
  });

  includeSources.addEventListener("change", saveParams);

  loadParams();
  input.focus();
})();
