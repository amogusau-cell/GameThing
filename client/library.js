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

function makePlaceholderDataUrl(label) {
  const text = String(label || "No image");
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="800" height="450">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#2a2a2a"/>
          <stop offset="100%" stop-color="#1a1a1a"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#g)"/>
      <text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle"
            fill="#b0b0b0" font-family="Arial, Helvetica, sans-serif" font-size="28">
        ${text}
      </text>
    </svg>
  `;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

const PLACEHOLDER_IMAGE = makePlaceholderDataUrl("No image");
const PLACEHOLDER_SCREENSHOTS = makePlaceholderDataUrl("No screenshots");

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

async function resolveCachedImage(gameId, fileName) {
  const api = window.pywebview?.api;
  if (api && typeof api.get_cached_image_url === "function") {
    try {
      const url = await api.get_cached_image_url(gameId, fileName);
      return url || "";
    } catch (e) {
      return "";
    }
  }
  return imgUrl(gameId, fileName);
}

function formatCacheInfo(info) {
  if (!info) return "No cache info.";
  const config = info.config || {};
  const manifest = info.manifest || {};
  const images = info.images || {};
  const total = info.total_bytes || 0;
  return [
    `Config: ${config.exists ? formatBytes(config.bytes) : "none"}`,
    `Manifest: ${manifest.exists ? formatBytes(manifest.bytes) : "none"}`,
    `Images: ${images.count || 0} file(s) (${formatBytes(images.bytes || 0)})`,
    `Total: ${formatBytes(total)}`
  ].join(" | ");
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
    if (img) {
      img.classList.add("is-placeholder");
      setImageWithFallback(img, "", PLACEHOLDER_IMAGE);
      resolveCachedImage(game.id, "header.jpg").then((url) => {
        if (!img.isConnected) return;
        img.classList.toggle("is-placeholder", !url);
        setImageWithFallback(img, url, PLACEHOLDER_IMAGE);
      });
    }

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

async function loadScreenshots(gameId) {
  const imgEl = document.getElementById("screenshot-img");
  if (!imgEl) return;

  stopSlideshow();
  state.slideshowToken += 1;
  const token = state.slideshowToken;

  const screenshots = [];
  imgEl.classList.add("is-placeholder");
  setImageWithFallback(imgEl, "", PLACEHOLDER_SCREENSHOTS);

  const hasCacheApi = window.pywebview?.api && typeof window.pywebview.api.get_cached_image_url === "function";
  if (!hasCacheApi) {
    const basePath = `http://${state.serverIp}/games/${gameId}/images/`;
    const ext = `.jpg?api-key=${state.apiKey}`;
    const detect = (i = 0) => {
      if (token !== state.slideshowToken) return;
      const testImg = new Image();
      testImg.onload = () => {
        if (screenshots.length === 0) {
          imgEl.classList.remove("is-placeholder");
          imgEl.src = testImg.src;
        }
        screenshots.push(testImg.src);
        detect(i + 1);
      };
      testImg.onerror = () => {
        if (screenshots.length >= 1) {
          imgEl.src = screenshots[0];
          startSlideshow(imgEl, screenshots, 5000);
        } else {
          imgEl.classList.add("is-placeholder");
          setImageWithFallback(imgEl, "", PLACEHOLDER_SCREENSHOTS);
        }
      };
      testImg.src = `${basePath}screenshot_${i}${ext}`;
    };
    detect();
    return;
  }

  const maxScreenshots = 50;
  for (let i = 0; i < maxScreenshots; i += 1) {
    if (token !== state.slideshowToken) return;
    const url = await resolveCachedImage(gameId, `screenshot_${i}.jpg`);
    if (!url) break;
    screenshots.push(url);
    if (screenshots.length === 1) {
      imgEl.classList.remove("is-placeholder");
      imgEl.src = url;
    }
  }

  if (token !== state.slideshowToken) return;

  if (screenshots.length >= 1) {
    startSlideshow(imgEl, screenshots, 5000);
  } else {
    imgEl.classList.add("is-placeholder");
    setImageWithFallback(imgEl, "", PLACEHOLDER_SCREENSHOTS);
  }
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

  if (background) {
    background.classList.add("is-placeholder");
    setImageWithFallback(background, "", PLACEHOLDER_IMAGE);
    resolveCachedImage(gameId, "background.jpg").then((bgUrl) => {
      if (gameId !== state.selectedId) return;
      background.classList.toggle("is-placeholder", !bgUrl);
      setImageWithFallback(background, bgUrl, PLACEHOLDER_IMAGE);
    });
  }

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
  const installText = document.getElementById("install-text");
  const status = document.getElementById("game-status");
  const downloadBtn = document.getElementById("download");

  const current = state.selectedId ? state.downloads.get(state.selectedId) : null;
  const game = state.games.find((g) => g.id === state.selectedId);
  const installed = game ? game.installed : false;
  const download = current ? current.download : (installed ? 1 : 0);
  const process = current ? current.process : (installed ? 1 : 0);

  if (installBar) installBar.style.width = `${Math.round(process * 100)}%`;
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
    await waitForApiMethod("get_cached_image_url");
    await waitForApiMethod("get_cache_info");
    await waitForApiMethod("clear_cache");

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
  const cacheInfo = document.getElementById("cache-info");
  const cacheInfoBtn = document.getElementById("cache-info-btn");
  const cacheClearBtn = document.getElementById("cache-clear-btn");

  const loadCacheInfo = async () => {
    if (!cacheInfo || !state.selectedId) return;
    cacheInfo.textContent = "Loading cache info...";
    try {
      const res = await window.pywebview.api.get_cache_info(state.selectedId);
      if (res.status === "ok") {
        cacheInfo.textContent = formatCacheInfo(res.info);
      } else {
        cacheInfo.textContent = res.message || "Failed to load cache info.";
      }
    } catch (err) {
      cacheInfo.textContent = "Failed to load cache info.";
    }
  };

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
        await loadCacheInfo();
      } catch (err) {
        settingsConfig.value = "";
        settingsMessage.textContent = "Failed to load config.";
        if (cacheInfo) cacheInfo.textContent = "Cache info unavailable.";
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

  if (cacheInfoBtn) {
    cacheInfoBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      await loadCacheInfo();
    });
  }

  if (cacheClearBtn) {
    cacheClearBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      if (!state.selectedId) return;
      if (!confirm("Clear cached files for this game?")) return;
      const res = await window.pywebview.api.clear_cache(state.selectedId);
      if (res.status === "ok") {
        await loadCacheInfo();
      } else if (cacheInfo) {
        cacheInfo.textContent = res.message || "Failed to clear cache.";
      }
    });
  }

  await refreshDownloads();
  setInterval(refreshDownloads, 500);
});
