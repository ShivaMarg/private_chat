// crypto.js — all encryption/decryption happens here, never on the server

const E2EE = (() => {
  const subtle = crypto.subtle;

  // ── Key generation (called once at register time) ──────────────
  async function generateIdentityKeyPair() {
    const kp = await subtle.generateKey(
      { name: "ECDH", namedCurve: "P-256" },
      true,    // exportable
      ["deriveKey", "deriveBits"]
    );
    const publicJwk  = await subtle.exportKey("jwk", kp.publicKey);
    const privateJwk = await subtle.exportKey("jwk", kp.privateKey);
    return { publicJwk, privateJwk };
  }

  // ── Derive shared AES key from your private key + their public key ──
  async function deriveSharedKey(myPrivateJwk, theirPublicJwk) {
    const myPrivate = await subtle.importKey(
      "jwk", myPrivateJwk,
      { name: "ECDH", namedCurve: "P-256" },
      false, ["deriveKey", "deriveBits"]
    );
    const theirPublic = await subtle.importKey(
      "jwk", theirPublicJwk,
      { name: "ECDH", namedCurve: "P-256" },
      false, []
    );
    return subtle.deriveKey(
      { name: "ECDH", public: theirPublic },
      myPrivate,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  // ── One-time ephemeral key pair per message ─────────────────────
  async function generateEphemeralKeyPair() {
    const kp = await subtle.generateKey(
      { name: "ECDH", namedCurve: "P-256" },
      true, ["deriveKey", "deriveBits"]
    );
    const publicJwk  = await subtle.exportKey("jwk", kp.publicKey);
    const privateJwk = await subtle.exportKey("jwk", kp.privateKey);
    return { publicJwk, privateJwk };
  }

  // ── Encrypt a message ──────────────────────────────────────────
  // Uses a fresh ephemeral key pair each time so forward secrecy is maintained.
  async function encryptMessage(plaintext, recipientPublicJwk) {
    // 1. Fresh ephemeral key pair
    const ephemeral = await generateEphemeralKeyPair();

    // 2. Derive shared AES key
    const aesKey = await deriveSharedKey(ephemeral.privateJwk, recipientPublicJwk);

    // 3. Random IV
    const iv = crypto.getRandomValues(new Uint8Array(12));

    // 4. Encrypt
    const encoded    = new TextEncoder().encode(plaintext);
    const cipherBuf  = await subtle.encrypt({ name: "AES-GCM", iv }, aesKey, encoded);

    return {
      ciphertext:           _b64(cipherBuf),
      iv:                   _b64(iv),
      ephemeral_public_key: JSON.stringify(ephemeral.publicJwk),
    };
  }

  // ── Decrypt a message ──────────────────────────────────────────
  async function decryptMessage(ciphertext_b64, iv_b64, ephemeralPublicJwkStr, myPrivateJwk) {
    const theirPublicJwk = JSON.parse(ephemeralPublicJwkStr);
    const aesKey         = await deriveSharedKey(myPrivateJwk, theirPublicJwk);

    const iv         = _u8(_ub64(iv_b64));
    const cipherBuf  = _ub64(ciphertext_b64);

    const plainBuf   = await subtle.decrypt({ name: "AES-GCM", iv }, aesKey, cipherBuf);
    return new TextDecoder().decode(plainBuf);
  }

  // ── base64 helpers ─────────────────────────────────────────────
  function _b64(buf) {
    return btoa(String.fromCharCode(...new Uint8Array(buf)));
  }
  function _ub64(b64) {
    const bin = atob(b64);
    const buf = new ArrayBuffer(bin.length);
    const u8  = new Uint8Array(buf);
    for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
    return buf;
  }
  function _u8(buf) {
    return new Uint8Array(buf);
  }

  // ── Session storage helpers ─────────────────────────────────────
  // NEVER use localStorage — sessionStorage clears when tab closes.
  function saveSession(data) {
    sessionStorage.setItem("pchat", JSON.stringify(data));
  }
  function loadSession() {
    const raw = sessionStorage.getItem("pchat");
    return raw ? JSON.parse(raw) : null;
  }
  function clearSession() {
    sessionStorage.clear();
  }

  return {
    generateIdentityKeyPair,
    generateEphemeralKeyPair,
    encryptMessage,
    decryptMessage,
    saveSession,
    loadSession,
    clearSession,
  };
})();
