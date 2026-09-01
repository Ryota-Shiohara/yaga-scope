(() => {
  "use strict";

  const RECONNECT_DELAY_MS = 2000;
  const BOTTOM_THRESHOLD_PX = 96;
  const MAX_VISIBLE_TRANSCRIPTS = 1000;
  const TOKYO_TIME = new Intl.DateTimeFormat("ja-JP", {
    timeZone: "Asia/Tokyo",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });

  const container = document.querySelector("#transcript-container");
  const list = document.querySelector("#transcript-list");
  const emptyState = document.querySelector("#empty-state");
  const jumpLatest = document.querySelector("#jump-latest");
  const countLabel = document.querySelector("#transcript-count");
  const connectionBadge = document.querySelector("#connection-badge");
  const connectionLabel = document.querySelector("#connection-label");
  const componentElements = {
    microphone: document.querySelector("#mic-status"),
    vad: document.querySelector("#vad-status"),
    transcription: document.querySelector("#asr-status"),
  };

  let socket = null;
  let reconnectTimer = null;
  let transcriptCount = 0;
  let followLatest = true;
  let hasConnected = false;
  let scrollFrame = null;

  const componentLabels = {
    microphone: {
      initializing: "準備中",
      running: "稼働中",
      error: "エラー",
    },
    vad: {
      initializing: "準備中",
      idle: "待機中",
      speech: "発話中",
      error: "エラー",
    },
    transcription: {
      initializing: "準備中",
      idle: "待機中",
      processing: "認識中",
      error: "エラー",
    },
  };

  function websocketUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws`;
  }

  function setConnectionState(state, label) {
    connectionBadge.dataset.state = state;
    connectionLabel.textContent = label;
  }

  function connect() {
    if (
      socket &&
      (socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }
    window.clearTimeout(reconnectTimer);
    setConnectionState(
      "connecting",
      hasConnected ? "再接続中" : "接続中",
    );
    socket = new WebSocket(websocketUrl());

    socket.addEventListener("open", () => {
      hasConnected = true;
      setConnectionState("connected", "接続中");
    });

    socket.addEventListener("message", (event) => {
      let payload;
      try {
        payload = JSON.parse(event.data);
      } catch (error) {
        console.warn("不正なWebSocketメッセージを無視しました", error);
        return;
      }
      if (payload.type === "transcript") {
        appendTranscript(payload);
      } else if (payload.type === "status") {
        updateSystemStatus(payload);
      }
    });

    socket.addEventListener("close", () => {
      socket = null;
      if (!navigator.onLine) {
        setConnectionState("disconnected", "切断");
        return;
      }
      setConnectionState("connecting", "再接続中");
      reconnectTimer = window.setTimeout(connect, RECONNECT_DELAY_MS);
    });

    socket.addEventListener("error", () => socket?.close());
  }

  function updateSystemStatus(payload) {
    Object.entries(componentElements).forEach(([key, element]) => {
      const state = payload[key];
      const label = componentLabels[key]?.[state];
      if (!label) return;
      element.dataset.state = state;
      element.querySelector(".status-value").textContent = label;
    });
  }

  function appendTranscript(payload) {
    const article = document.createElement("article");
    article.className = "transcript-entry";
    article.dataset.eventId = payload.id;

    const meta = document.createElement("div");
    meta.className = "transcript-meta";

    const time = document.createElement("time");
    const startedAt = new Date(payload.started_at);
    time.dateTime = payload.started_at;
    time.textContent = Number.isNaN(startedAt.getTime())
      ? "--:--:--"
      : TOKYO_TIME.format(startedAt);

    const source = document.createElement("span");
    source.className = "source-label";
    source.textContent = payload.source || "unknown";

    const text = document.createElement("p");
    text.className = "transcript-text";
    text.textContent = payload.text;

    meta.append(time, source);
    article.append(meta, text);
    emptyState?.remove();
    list.append(article);
    transcriptCount += 1;
    countLabel.textContent = `発話 ${transcriptCount}件`;

    const entries = list.querySelectorAll(".transcript-entry");
    if (entries.length > MAX_VISIBLE_TRANSCRIPTS) {
      entries[0].remove();
    }

    if (followLatest) {
      scrollToLatest(false);
    } else {
      jumpLatest.hidden = false;
    }
  }

  function isNearBottom() {
    const remaining =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    return remaining <= BOTTOM_THRESHOLD_PX;
  }

  function scrollToLatest(smooth) {
    container.scrollTo({
      top: container.scrollHeight,
      behavior: smooth ? "smooth" : "auto",
    });
    followLatest = true;
    jumpLatest.hidden = true;
  }

  container.addEventListener(
    "scroll",
    () => {
      if (scrollFrame !== null) return;
      scrollFrame = window.requestAnimationFrame(() => {
        followLatest = isNearBottom();
        jumpLatest.hidden = followLatest;
        scrollFrame = null;
      });
    },
    { passive: true },
  );

  jumpLatest.addEventListener("click", () => scrollToLatest(true));
  window.addEventListener("offline", () => {
    window.clearTimeout(reconnectTimer);
    setConnectionState("disconnected", "切断");
  });
  window.addEventListener("online", connect);
  connect();
})();
