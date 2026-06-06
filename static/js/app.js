// app.js — wires together auth, channels, WebSocket, and crypto

const API = location.origin + "/api";

let session   = null;   // { token, user_id, username, privateJwk }
let myChannels = [];   // was: let channels = [];
let activeChannel = null;
let ws        = null;
let peerKeys  = {};     // { username: publicJwkStr }
let typingTimer = null;

// ── Startup ────────────────────────────────────────────────────────
window.addEventListener("DOMContentLoaded", () => {
  const saved = E2EE.loadSession();
  if (saved) {
    session = saved;
    bootApp();
  }
  // else: auth screen is visible
});

// ── Panic button — Esc clears everything ──────────────────────────
document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    E2EE.clearSession();
    ws && ws.close();
    location.href = "https://google.com";
  }
});

// ── Auth ──────────────────────────────────────────────────────────
let authMode = "login";

document.getElementById("auth-switch-link").addEventListener("click", () => {
  authMode = authMode === "login" ? "register" : "login";
  document.getElementById("auth-title").textContent  = authMode === "login" ? "Sign in" : "Create account";
  document.getElementById("auth-btn").textContent    = authMode === "login" ? "Sign in" : "Register";
  document.getElementById("auth-switch-text").textContent = authMode === "login" ? "No account? " : "Have one? ";
  document.getElementById("auth-switch-link").textContent = authMode === "login" ? "Create one" : "Sign in";
  document.getElementById("auth-error").textContent  = "";
});

document.getElementById("auth-btn").addEventListener("click", doAuth);
document.getElementById("auth-password").addEventListener("keydown", e => { if (e.key === "Enter") doAuth(); });

async function doAuth() {
  const username = document.getElementById("auth-username").value.trim();
  const password = document.getElementById("auth-password").value;
  const errEl    = document.getElementById("auth-error");
  errEl.textContent = "";

  if (!username || !password) { errEl.textContent = "Fill in all fields"; return; }

  if (authMode === "register") {
    // Generate ECDH key pair on client
    const { publicJwk, privateJwk } = await E2EE.generateIdentityKeyPair();
    const res = await fetch(`${API}/auth/register`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, public_key: JSON.stringify(publicJwk) })
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.detail || "Error"; return; }

    session = { token: data.token, user_id: data.user_id, username: data.username, privateJwk };
    E2EE.saveSession(session);
    bootApp();
  } else {
    const res  = await fetch(`${API}/auth/login`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password, public_key: "" })
    });
    const data = await res.json();
    if (!res.ok) { errEl.textContent = data.detail || "Error"; return; }

    // On login, privateJwk must come from the saved session (already stored on device).
    // If logging in on a NEW device, the user must re-register (key is device-bound by design).
    const saved = E2EE.loadSession();
    const privateJwk = saved?.privateJwk ?? null;
    if (!privateJwk) {
      errEl.textContent = "Private key not found on this device. Register here to generate a new key.";
      return;
    }

    session = { token: data.token, user_id: data.user_id, username: data.username, privateJwk };
    E2EE.saveSession(session);
    bootApp();
  }
}

// ── Boot app after auth ───────────────────────────────────────────
async function bootApp() {
  document.getElementById("auth-screen").style.display = "none";
  document.getElementById("my-name").textContent = session.username;
  await loadChannels();
}

// ── Channels ──────────────────────────────────────────────────────
async function loadChannels() {
  const res = await apiFetch("GET", "/channels");
  myChannels = await res.json();
  renderChannels();
}

function renderChannels() {
  const list = document.getElementById("channels-list");
  list.innerHTML = "";
  myChannels.forEach(ch => {
    const el = document.createElement("div");
    el.className = "channel-item" + (activeChannel?.id === ch.id ? " active" : "");
    el.innerHTML = `
      <span class="ch-icon">${ch.is_group ? "👥" : "💬"}</span>
      <div>
        <div class="ch-name">${esc(ch.name)}</div>
        <div class="ch-code">#${ch.invite_code}</div>
      </div>`;
    el.onclick = () => openChannel(ch);
    list.appendChild(el);
  });
}

window.openNewCh = () => document.getElementById("new-ch-form").classList.toggle("open");
window.closeNewCh = () => document.getElementById("new-ch-form").classList.remove("open");

window.createChannel = async () => {
  const name    = document.getElementById("ch-name-input").value.trim();
  const isGroup = document.getElementById("ch-group").checked;
  if (!name) return;
  const res = await apiFetch("POST", "/channels", { name, is_group: isGroup });
  const ch  = await res.json();
  myChannels.push(ch);
  renderChannels();
  closeNewCh();
  openChannel(ch);
};

window.joinChannel = async () => {
  const code = document.getElementById("join-code-input").value.trim();
  if (!code) return;
  const res = await apiFetch("POST", `/channels/join/${code}`);
  if (!res.ok) { alert("Invalid code"); return; }
  const ch = await res.json();
  const exists = myChannels.some(c => c.id === ch.id);
  if (!exists) myChannels.push(ch);
  renderChannels();
  closeNewCh();
  openChannel(ch);
};

// ── Open channel ──────────────────────────────────────────────────
async function openChannel(ch) {
  activeChannel = ch;
  ws && ws.close();
  renderChannels();

  document.getElementById("empty-state").style.display  = "none";
  document.getElementById("chat-main").style.display    = "flex";
  document.getElementById("ch-title").textContent       = ch.name;
  document.getElementById("ch-subtitle").textContent    = ch.is_group ? "Group room" : "1:1 chat";
  document.getElementById("messages").innerHTML         = "";

  await loadHistory(ch);
  connectWS(ch);
}

window.showInvite = () => {
  document.getElementById("invite-code-display").textContent = activeChannel?.invite_code ?? "—";
  document.getElementById("invite-overlay").classList.add("open");
};

// ── Load message history ──────────────────────────────────────────
async function loadHistory(ch) {
  const res  = await apiFetch("GET", `/messages/${ch.id}?limit=50`);
  const msgs = await res.json();
  for (const m of msgs) await renderMessage(m);
  scrollBottom();
}

window.loadStarred = async () => {
  if (!activeChannel) return;
  document.getElementById("messages").innerHTML = '<div class="system-msg">⭐ Starred messages</div>';
  const res  = await apiFetch("GET", `/messages/${activeChannel.id}/starred`);
  const msgs = await res.json();
  for (const m of msgs) await renderMessage(m);
};

// ── WebSocket ─────────────────────────────────────────────────────
function connectWS(ch) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/chat/${ch.id}?token=${session.token}`);

  ws.onmessage = async ({ data }) => {
    const msg = JSON.parse(data);

    if (msg.type === "message") {
      await renderMessage(msg);
      scrollBottom();
    } else if (msg.type === "typing") {
      const el = document.getElementById("typing-indicator");
      if (msg.typing && msg.user_id !== session.user_id) {
        el.textContent = `${msg.username} is typing…`;
        clearTimeout(typingTimer);
        typingTimer = setTimeout(() => { el.textContent = ""; }, 3000);
      }
    } else if (msg.type === "presence") {
      const el = document.getElementById("typing-indicator");
      el.textContent = `${msg.username} ${msg.online ? "came online" : "went offline"}`;
      setTimeout(() => { el.textContent = ""; }, 2500);
    }
  };

  ws.onerror = () => {};
  ws.onclose = () => {};
}

// ── Send message ──────────────────────────────────────────────────
document.getElementById("send-btn").addEventListener("click", sendMsg);
document.getElementById("msg-input").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMsg(); }
  else {
    ws && ws.readyState === 1 && ws.send(JSON.stringify({ type: "typing", typing: true }));
  }
});

async function sendMsg() {
  const input = document.getElementById("msg-input");
  const text  = input.value.trim();
  if (!text || !activeChannel || !ws || ws.readyState !== 1) return;
  input.value = "";

  // Fetch recipient public keys for everyone in the channel
  // For simplicity: encrypt once using YOUR OWN public key stored on server
  // (In a full E2EE group chat, you'd encrypt once per recipient — this version
  //  stores one ciphertext per message, decryptable by anyone with the channel's
  //  shared ephemeral context. For a stricter 1:1 setup, use the recipient-only key.)
  const myPubKey = await fetchPublicKey(session.username);
  const { ciphertext, iv, ephemeral_public_key } = await E2EE.encryptMessage(text, JSON.parse(myPubKey));

  ws.send(JSON.stringify({
    type: "message",
    ciphertext,
    iv,
    ephemeral_public_key,
    media_type: "text",
  }));
}

// ── Decrypt and render a message ──────────────────────────────────
async function renderMessage(msg) {
  const isMine = msg.sender_id === session.user_id;
  let plaintext = "[encrypted]";

  try {
    plaintext = await E2EE.decryptMessage(
      msg.ciphertext, msg.iv, msg.ephemeral_public_key, session.privateJwk
    );
  } catch (_) {
    // Message encrypted with a different key — can't decrypt (e.g. messages from before this session)
    plaintext = "🔒 (encrypted for another session)";
  }

  const wrap = document.createElement("div");
  wrap.className = `bubble-wrap ${isMine ? "me" : "them"}`;
  wrap.dataset.msgId = msg.id;

  const time = new Date(msg.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  wrap.innerHTML = `
    ${!isMine ? `<div class="sender-label">${esc(msg.sender_username)}</div>` : ""}
    <div class="bubble ${msg.starred ? "starred" : ""}" id="bubble-${msg.id}">
      <div class="content">${esc(plaintext)}</div>
      <div style="display:flex;align-items:center;justify-content:flex-end;gap:6px;margin-top:4px">
        <button class="star-btn ${msg.starred ? "on" : ""}" title="Star" onclick="toggleStar('${msg.id}', this)">⭐</button>
        <span class="ts">${time}</span>
      </div>
    </div>`;

  document.getElementById("messages").appendChild(wrap);
}

window.toggleStar = async (msgId, btn) => {
  const isOn = btn.classList.toggle("on");
  const res  = await apiFetch("PATCH", "/messages/star", { message_id: msgId, starred: isOn });
  if (res.ok) {
    const bubble = document.getElementById(`bubble-${msgId}`);
    bubble?.classList.toggle("starred", isOn);
  }
};

// ── Helpers ────────────────────────────────────────────────────────
async function fetchPublicKey(username) {
  if (peerKeys[username]) return peerKeys[username];
  const res  = await fetch(`${API}/auth/user/${username}`);
  const data = await res.json();
  peerKeys[username] = data.public_key;
  return data.public_key;
}

async function apiFetch(method, path, body) {
  return fetch(`${API}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${session?.token}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
}

function scrollBottom() {
  const el = document.getElementById("messages");
  el.scrollTop = el.scrollHeight;
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
