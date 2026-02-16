function waitForPywebview() {
  return new Promise((resolve) => {
    const check = () => {
      if (window.pywebview && window.pywebview.api) {
        resolve();
      } else {
        setTimeout(check, 50);
      }
    };
    check();
  });
}

async function waitForApiMethod(name, timeoutMs = 4000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api[name] === "function") {
      return;
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  return;
}

const state = {
  serverIp: "",
  apiKey: "",
  games: [],
  selectedId: null,
  slideshowTimer: null,
  slideshowToken: 0,
  downloads: new Map(),
};

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let val = bytes;
  while (val >= 1024 && i < units.length - 1) {
    val /= 1024;
    i += 1;
  }
  return `${val.toFixed(1)} ${units[i]}`;
}

function imgUrl(gameId, fileName) {
  if (!state.serverIp) return "";
  return `http://${state.serverIp}/games/${gameId}/images/${fileName}?api-key=${state.apiKey}`;
}

function normalizeServerIp(ip) {
  return ip.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

function setImageWithFallback(imgEl, url, fallbackUrl) {
  if (!imgEl) return;
  imgEl.onerror = () => {
    imgEl.onerror = null;
    if (fallbackUrl) imgEl.src = fallbackUrl;
  };
  imgEl.src = url || fallbackUrl || "";
}

function renderSidebar() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;

  sidebar.innerHTML = "";

  if (!state.games.length) {
    const empty = document.createElement("div");
    empty.className = "sidebar-item";
    empty.textContent = "No games found";
    sidebar.appendChild(empty);
    return;
  }

  state.games.forEach((game) => {
    const item = document.createElement("a");
    item.href = "#";
    item.className = "sidebar-item";
    item.dataset.id = game.id;

    item.innerHTML = `
      <img src="" alt="${game.name}" />
      <span>${game.name}</span>
    `;

    const img = item.querySelector("img");
    setImageWithFallback(
      img,
      imgUrl(game.id, "header.jpg"),
      "images/image.png"
    );

    sidebar.appendChild(item);
  });
}

async function refreshLibrary(keepSelection = true) {
  const previous = state.selectedId;
  state.games = await window.pywebview.api.get_library();
  renderSidebar();

  if (keepSelection && previous && state.games.find((g) => g.id === previous)) {
    selectGame(previous);
  } else if (state.games.length) {
    selectGame(state.games[0].id);
  } else {
    state.selectedId = null;
    updateProgressUI();
  }
}

function updateSelectionUI() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;
  sidebar.querySelectorAll(".sidebar-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.id === state.selectedId);
  });
}

function stopSlideshow() {
  if (state.slideshowTimer) {
    clearInterval(state.slideshowTimer);
    state.slideshowTimer = null;
  }
}

function startSlideshow(imgEl, screenshots, delay) {
  if (!imgEl || screenshots.length <= 1) return;
  let index = 0;
  state.slideshowTimer = setInterval(() => {
    imgEl.classList.add("slide-out-left");

    setTimeout(() => {
      index = (index + 1) % screenshots.length;
      imgEl.src = screenshots[index];

      imgEl.classList.remove("slide-out-left");
      imgEl.classList.add("slide-in-right");

      requestAnimationFrame(() => {
        imgEl.classList.remove("slide-in-right");
      });
    }, 600);
  }, delay);
}

function loadScreenshots(gameId) {
  const imgEl = document.getElementById("screenshot-img");
  if (!imgEl) return;

  stopSlideshow();
  state.slideshowToken += 1;
  const token = state.slideshowToken;

  const basePath = `http://${state.serverIp}/games/${gameId}/images/`;
  const ext = `.jpg?api-key=${state.apiKey}`;
  const screenshots = [];

  const detect = (i = 0) => {
    if (token !== state.slideshowToken) return;
    const testImg = new Image();
    testImg.onload = () => {
      screenshots.push(testImg.src);
      detect(i + 1);
    };
    testImg.onerror = () => {
      if (screenshots.length >= 1) {
        imgEl.src = screenshots[0];
        startSlideshow(imgEl, screenshots, 5000);
      } else {
        setImageWithFallback(imgEl, "images/image.png", "images/image.png");
      }
    };
    testImg.src = `${basePath}screenshot_${i}${ext}`;
  };

  detect();
}

function selectGame(gameId) {
  state.selectedId = gameId;
  updateSelectionUI();

  const game = state.games.find((g) => g.id === gameId);
  if (!game) return;

  const title = document.getElementById("game-title");
  const size = document.getElementById("game-size");
  const status = document.getElementById("game-status");
  const background = document.getElementById("background-img");
  const downloadBtn = document.getElementById("download");

  if (title) title.textContent = game.name;
  if (size) size.textContent = formatBytes(game.size_bytes);
  if (status) status.textContent = game.installed ? "Installed" : "Not installed";

  setImageWithFallback(
    background,
    imgUrl(gameId, "background.jpg"),
    "images/image.png"
  );

  loadScreenshots(gameId);

  if (downloadBtn) {
    if (game.installed) {
      downloadBtn.textContent = "Installed";
      downloadBtn.classList.add("disabled");
    } else {
      downloadBtn.textContent = "Download";
      downloadBtn.classList.remove("disabled");
    }
  }

  updateProgressUI();
}

function updateProgressUI() {
  const downloadBar = document.getElementById("download-bar");
  const installBar = document.getElementById("install-bar");
  const downloadText = document.getElementById("download-text");
  const installText = document.getElementById("install-text");
  const status = document.getElementById("game-status");
  const downloadBtn = document.getElementById("download");

  const current = state.selectedId ? state.downloads.get(state.selectedId) : null;
  const game = state.games.find((g) => g.id === state.selectedId);
  const installed = game ? game.installed : false;
  const download = current ? current.download : (installed ? 1 : 0);
  const process = current ? current.process : (installed ? 1 : 0);

  if (downloadBar) downloadBar.style.width = `${Math.round(download * 100)}%`;
  if (installBar) installBar.style.width = `${Math.round(process * 100)}%`;
  if (downloadText) downloadText.textContent = `${Math.round(download * 100)}%`;
  if (installText) installText.textContent = `${Math.round(process * 100)}%`;

  if (status && current) {
    status.textContent = current.status || status.textContent;
  } else if (status && installed) {
    status.textContent = "Installed";
  }

  if (downloadBtn) {
    if (current && (current.status === "downloading" || current.status === "processing")) {
      downloadBtn.textContent = current.status === "downloading" ? "Downloading..." : "Processing...";
      downloadBtn.classList.add("disabled");
    } else if (installed) {
      downloadBtn.textContent = "Installed";
      downloadBtn.classList.add("disabled");
    } else {
      downloadBtn.textContent = "Download";
      downloadBtn.classList.remove("disabled");
    }
  }
}

async function refreshDownloads() {
  const result = await window.pywebview.api.get_downloads();
  const downloads = result.downloads || [];
  state.downloads = new Map(downloads.map((d) => [d.id, d]));

  state.games = state.games.map((game) => {
    const d = state.downloads.get(game.id);
    if (!d) return game;
    return { ...game, installed: !!d.installed };
  });

  updateProgressUI();
}

document.addEventListener("DOMContentLoaded", async () => {
  await waitForPywebview();

  let attempts = 0;
  while (attempts < 10) {
    attempts += 1;
    await waitForApiMethod("get_server_ip");
    await waitForApiMethod("get_auth_token");
    await waitForApiMethod("get_library");
    await waitForApiMethod("start_game_download");
    await waitForApiMethod("stop_game_download");
  await waitForApiMethod("get_downloads");
  await waitForApiMethod("open_game_folder");
  await waitForApiMethod("delete_game_folder");
  await waitForApiMethod("get_server_config");
  await waitForApiMethod("update_server_config");
  await waitForApiMethod("delete_server_game");

    if (window.pywebview?.api?.get_server_ip) break;
    await new Promise((r) => setTimeout(r, 200));
  }

  state.serverIp = normalizeServerIp(await window.pywebview.api.get_server_ip());
  state.apiKey = await window.pywebview.api.get_auth_token();

  await refreshLibrary(false);

  const sidebar = document.getElementById("sidebar");
  if (sidebar) {
    sidebar.addEventListener("click", (e) => {
      const item = e.target.closest(".sidebar-item");
      if (!item || !item.dataset.id) return;
      e.preventDefault();
      selectGame(item.dataset.id);
    });
  }

  const downloadBtn = document.getElementById("download");
  if (downloadBtn) {
    downloadBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      const game = state.games.find((g) => g.id === state.selectedId);
      if (game && game.installed) return;
      await window.pywebview.api.start_game_download(state.selectedId);
    });
  }

  const stopBtn = document.getElementById("stop-download");
  if (stopBtn) {
    stopBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      await window.pywebview.api.stop_game_download(state.selectedId);
    });
  }

  const openBtn = document.getElementById("open-folder");
  if (openBtn) {
    openBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      await window.pywebview.api.open_game_folder(state.selectedId);
    });
  }

  const deleteBtn = document.getElementById("delete-game");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      await window.pywebview.api.delete_game_folder(state.selectedId);
      const game = state.games.find((g) => g.id === state.selectedId);
      if (game) game.installed = false;
      state.downloads.delete(state.selectedId);
      await refreshDownloads();
      updateProgressUI();
      selectGame(state.selectedId);
    });
  }

  const settingsBtn = document.getElementById("settings");
  const settingsPanel = document.getElementById("settings-panel");
  const settingsClose = document.getElementById("settings-close");
  const settingsConfig = document.getElementById("settings-config");
  const settingsSave = document.getElementById("settings-save");
  const settingsDeleteServer = document.getElementById("settings-delete-server");
  const settingsMessage = document.getElementById("settings-message");

  if (settingsBtn) {
    settingsBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId || !settingsPanel) return;
      settingsMessage.textContent = "";
      settingsConfig.value = "Loading...";
      settingsPanel.classList.remove("hidden");
      try {
        const text = await window.pywebview.api.get_server_config(state.selectedId);
        settingsConfig.value = text;
      } catch (err) {
        settingsConfig.value = "";
        settingsMessage.textContent = "Failed to load config.";
      }
    });
  }

  if (settingsClose) {
    settingsClose.addEventListener("click", (e) => {
      e.preventDefault();
      settingsPanel?.classList.add("hidden");
    });
  }

  if (settingsSave) {
    settingsSave.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      settingsMessage.textContent = "";
      const res = await window.pywebview.api.update_server_config(
        state.selectedId,
        settingsConfig.value
      );
      if (res.status === "ok") {
        settingsMessage.textContent = "Config updated.";
        await refreshLibrary(true);
      } else {
        settingsMessage.textContent = res.message || "Failed to update config.";
      }
    });
  }

  if (settingsDeleteServer) {
    settingsDeleteServer.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      settingsMessage.textContent = "";
      if (!confirm("Remove this game from the server?")) return;
      const res = await window.pywebview.api.delete_server_game(state.selectedId);
      if (res.status === "ok") {
        settingsMessage.textContent = "Removed from server.";
        settingsPanel?.classList.add("hidden");
        await refreshLibrary(false);
      } else {
        settingsMessage.textContent = res.message || "Failed to remove game.";
      }
    });
  }

  await refreshDownloads();
  setInterval(refreshDownloads, 500);
});
