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
  await waitForPywebview();

  const loginBtn = document.getElementById("login-button");
  const registerBtn = document.getElementById("register-button");
  const username = document.getElementById("username");
  const password = document.getElementById("password");
  const confirm = document.getElementById("password-confirm");
  const ip = document.getElementById("ip");
  const error = document.getElementById("error");

  loginBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    error.textContent = await window.pywebview.api.login(
        username.value,
        password.value,
        ip.value,
    );
  });

  registerBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    if (password.value !== confirm.value) {
      error.textContent = "Passwords do not match.";
      return;
    }
    error.textContent = await window.pywebview.api.register(
        username.value,
        password.value,
        ip.value,
    );
  });
});
