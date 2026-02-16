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

function renderUploaded(listEl, games) {
  listEl.innerHTML = "";
  if (!games.length) {
    const empty = document.createElement("div");
    empty.className = "list-item";
    empty.textContent = "No uploaded games.";
    listEl.appendChild(empty);
    return;
  }

  games.forEach((game) => {
    const item = document.createElement("div");
    item.className = "list-item";
    item.textContent = `${game.name || game.id}`;
    listEl.appendChild(item);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  await waitForPywebview();

  const usernameEl = document.getElementById("account-username");
  const usageEl = document.getElementById("account-usage");
  const listEl = document.getElementById("uploaded-list");
  const currentInput = document.getElementById("current-password");
  const newInput = document.getElementById("new-password");
  const changeBtn = document.getElementById("change-password");
  const changeMsg = document.getElementById("change-message");
  const deleteInput = document.getElementById("delete-password");
  const deleteBtn = document.getElementById("delete-account");
  const deleteMsg = document.getElementById("delete-message");
  const logoutBtn = document.getElementById("logout-button");

  try {
    const userData = await window.pywebview.api.get_user();
    const user = JSON.parse(userData);
    if (usernameEl) usernameEl.textContent = `Username: ${user.username}`;
  } catch (e) {
    if (usernameEl) usernameEl.textContent = "Username: --";
  }

  try {
    const usage = await window.pywebview.api.get_local_usage();
    if (usageEl) {
      usageEl.textContent = `Storage used: ${formatBytes(usage.total)} (games ${formatBytes(usage.games)}, downloads ${formatBytes(usage.downloads)})`;
    }
  } catch (e) {
    if (usageEl) usageEl.textContent = "Storage used: --";
  }

  try {
    const uploaded = await window.pywebview.api.get_uploaded_games();
    renderUploaded(listEl, uploaded.games || []);
  } catch (e) {
    renderUploaded(listEl, []);
  }

  changeBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    changeMsg.textContent = "";
    const currentPassword = currentInput.value.trim();
    const newPassword = newInput.value.trim();
    if (!currentPassword || !newPassword) {
      changeMsg.textContent = "Please enter current and new password.";
      return;
    }

    const res = await window.pywebview.api.change_password(
      currentPassword,
      newPassword
    );
    if (res.status === "ok") {
      changeMsg.textContent = "Password changed.";
      currentInput.value = "";
      newInput.value = "";
    } else {
      changeMsg.textContent = res.message || "Failed to change password.";
    }
  });

  deleteBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    deleteMsg.textContent = "";
    const currentPassword = deleteInput.value.trim();
    if (!currentPassword) {
      deleteMsg.textContent = "Please enter your password.";
      return;
    }
    if (!confirm("Delete your account? This cannot be undone.")) return;

    const res = await window.pywebview.api.delete_account(currentPassword);
    if (res && res.status === "error") {
      deleteMsg.textContent = res.message || "Failed to delete account.";
    }
  });

  logoutBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    await window.pywebview.api.logout();
  });
});
