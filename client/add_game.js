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

document.addEventListener("DOMContentLoaded", async () => {
  console.log("DOM yüklendi");

  await waitForPywebview();
  console.log("pywebview hazır 🚀");

  const usernameText = document.getElementById("username-text");
  const link = document.getElementById("select-file");
  const p = document.getElementById("path-display");

  const userData = await window.pywebview.api.get_user();
  const user = JSON.parse(userData);

  usernameText.textContent = "Username: " + user.username;

  let path = "";

  link.addEventListener("click", async (e) => {
    e.preventDefault();
    p.textContent = "Waiting for path...";

    path = await window.pywebview.api.open_file();

    p.textContent = path?.endsWith(".zip")
      ? "Selected: " + path
      : "Please input a zip file";
  });

  const config = document.getElementById("config");
  config.value = `name: Game Name
id: game_name
run: path/to/exe
saveInGameFolder: true
savePath: path/to/savefolder
isSteamGame: true
getSteamData: true
uploadEndCommand: null
processEndCommand: null`;

  let configAdditionalData =
`url: null
user: ${user.username}`;

  const config2 = document.getElementById("config2");
  config2.value = config.value + "\n" + configAdditionalData;

  const startUploadBtn = document.getElementById("start-upload");
  const urlInput = document.getElementById("url-input");

  startUploadBtn.addEventListener("click", async (e) => {
    e.preventDefault();

    if (path && path.endsWith(".zip")) {
      const configData = config.value + "\n" + configAdditionalData;
      await window.pywebview.api.send_file(path, configData);
    } else if (urlInput.value !== "") {
      const configAdditionalData2 =
`url: ${urlInput.value}
user: ${user.username}`;
      const configData = config.value + "\n" + configAdditionalData2;
      await window.pywebview.api.download_file(configData);
    }
  });

  // Initial load
  const initialProcesses = await window.pywebview.api.get_processes();
  syncSidebar(initialProcesses);

  // Update loop (NO FLASHING)
  setInterval(async () => {
    const processes = await window.pywebview.api.get_processes();
    syncSidebar(processes);
  }, 250);
});

function onProgressUpdate(p) {
  console.log("Progress:", p);
  const progress_text = document.getElementById("upload-percent");
  if (progress_text) {
    progress_text.innerText = p + "%";
  }
}

/* ------------------------
   ITEM HANDLING
------------------------ */

function onItemClick(id) {
  console.log("Clicked item id:", id);
  removeItem(id);
}

function addOrUpdateItem({ id, title, status = "" }) {
  const sidebar = document.getElementById("sidebar");
  const addBtn = document.getElementById("add-btn");

  let item = sidebar.querySelector(`.sidebar-item[data-id="${id}"]`);

  if (!item) {
    item = document.createElement("a");
    item.href = "#";
    item.className = "sidebar-item";
    item.dataset.id = id;

    item.innerHTML = `
      <span class="title"></span>
      <span class="status"></span>
    `;

    sidebar.insertBefore(item, addBtn);
  }

  item.querySelector(".title").textContent = title;
  item.querySelector(".status").textContent = status;
}

function removeItem(id) {
  const item = document.querySelector(`.sidebar-item[data-id="${id}"]`);
  if (item) item.remove();
}

function clearSidebarItems() {
  const sidebar = document.getElementById("sidebar");

  sidebar.querySelectorAll(".sidebar-item").forEach(item => {
    if (item.id !== "add-btn") {
      item.remove();
    }
  });
}

/* ------------------------
   SIDEBAR SYNC (NO FLASH)
------------------------ */

function syncSidebar(processes) {
  const sidebar = document.getElementById("sidebar");
  const seen = new Set();

  processes.processes.forEach(proc => {
    const status =
      "Download: " + Math.round(parseFloat(proc.download) * 100) + "% " +
      "Process: " + Math.round(parseFloat(proc.process) * 100) + "%";

    addOrUpdateItem({
      id: proc.id,
      title: proc.id,
      status
    });

    seen.add(proc.id);
  });

  sidebar.querySelectorAll(".sidebar-item").forEach(item => {
    const id = item.dataset.id;
    if (id && !seen.has(id) && item.id !== "add-btn") {
      item.remove();
    }
  });
}

/* ------------------------
   SIDEBAR CLICK HANDLING
------------------------ */

document.addEventListener("DOMContentLoaded", () => {
  const sidebar = document.getElementById("sidebar");

  sidebar.addEventListener("click", (e) => {
    const item = e.target.closest(".sidebar-item");
    if (!item) return;

    e.preventDefault();

    if (item.id === "add-btn") {
      console.log("add'e tıklandı");
      return;
    }

    const id = item.dataset.id;
    if (id) {
      console.log("Clicked item id:", id);
    }
  });
});
