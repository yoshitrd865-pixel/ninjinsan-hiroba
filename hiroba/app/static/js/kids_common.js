/* ==================================================================
   ひろば - 共通JSヘルパー (kids_common.js)
   全キッズ向けページで読み込む共通関数群。
   ================================================================== */

window.Hiroba = (function () {
  /**
   * fetch のラッパー。JSON形式のAPIレスポンスを想定し、
   * エラー時は detail 付きの Error を throw する。
   */
  async function api(url, options) {
    options = options || {};
    const res = await fetch(url, Object.assign({ credentials: "same-origin" }, options));
    let data = null;
    try {
      data = await res.json();
    } catch (e) {
      data = null;
    }
    if (!res.ok) {
      const err = new Error((data && data.detail) || "エラーがおきました");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  /**
   * 現在ログイン中か確認し、未ログインならログイン画面へ遷移する。
   * ログイン中ならユーザー情報を返す。
   */
  async function requireLogin(redirectTo) {
    try {
      const me = await api("/api/auth/me");
      if (!me || !me.logged_in) {
        window.location.href = redirectTo || "/login";
        return null;
      }
      return me.user;
    } catch (e) {
      window.location.href = redirectTo || "/login";
      return null;
    }
  }

  /** カウント数字などにポン！と弾む数値変化アニメーションを付ける */
  function bump(el) {
    if (!el) return;
    el.classList.remove("is-bumped");
    void el.offsetWidth; // reflow でアニメーションを再始動させる
    el.classList.add("is-bumped");
    setTimeout(function () {
      el.classList.remove("is-bumped");
    }, 500);
  }

  /** ボタン自体をぽよんと跳ねさせる */
  function bounce(el) {
    if (!el) return;
    el.classList.remove("is-bouncing");
    void el.offsetWidth;
    el.classList.add("is-bouncing");
    setTimeout(function () {
      el.classList.remove("is-bouncing");
    }, 600);
  }

  // ===================================================================
  // Web Audio APIによる面白い音 ＆ 300回クリック爆発破壊機能
  // ===================================================================
  let audioCtx = null;
  function getAudioContext() {
    if (!audioCtx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (AudioContext) {
        audioCtx = new AudioContext();
      }
    }
    if (audioCtx && audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    return audioCtx;
  }

  function playFunnySound(clickCount) {
    const ctx = getAudioContext();
    if (!ctx) return;

    const now = ctx.currentTime;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (clickCount >= 300) {
      // 爆発音 (ホワイトノイズバースト＋低音グロウル)
      const bufferSize = ctx.sampleRate * 0.8;
      const buffer = ctx.createBuffer(1, bufferSize, ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < bufferSize; i++) {
        data[i] = Math.random() * 2 - 1;
      }
      const noise = ctx.createBufferSource();
      noise.buffer = buffer;
      const noiseGain = ctx.createGain();
      noiseGain.gain.setValueAtTime(1.0, now);
      noiseGain.gain.exponentialRampToValueAtTime(0.01, now + 0.8);
      noise.connect(noiseGain);
      noiseGain.connect(ctx.destination);
      noise.start(now);
      noise.stop(now + 0.8);

      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(180, now);
      osc.frequency.exponentialRampToValueAtTime(30, now + 0.8);
      gain.gain.setValueAtTime(0.9, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.8);
      osc.start(now);
      osc.stop(now + 0.8);
      return;
    }

    const soundType = clickCount % 5;
    if (soundType === 0) {
      // ピコーン
      osc.type = "sine";
      osc.frequency.setValueAtTime(450 + (clickCount % 500), now);
      osc.frequency.exponentialRampToValueAtTime(1400, now + 0.15);
      gain.gain.setValueAtTime(0.3, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.15);
      osc.start(now);
      osc.stop(now + 0.15);
    } else if (soundType === 1) {
      // ポヨヨン
      osc.type = "triangle";
      osc.frequency.setValueAtTime(320, now);
      osc.frequency.linearRampToValueAtTime(700, now + 0.1);
      osc.frequency.linearRampToValueAtTime(220, now + 0.25);
      gain.gain.setValueAtTime(0.35, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
      osc.start(now);
      osc.stop(now + 0.25);
    } else if (soundType === 2) {
      // ププッ
      osc.type = "square";
      osc.frequency.setValueAtTime(250, now);
      osc.frequency.setValueAtTime(500, now + 0.08);
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.2);
      osc.start(now);
      osc.stop(now + 0.2);
    } else if (soundType === 3) {
      // キラリーン
      osc.type = "sine";
      osc.frequency.setValueAtTime(900, now);
      osc.frequency.setValueAtTime(1200, now + 0.06);
      osc.frequency.setValueAtTime(1500, now + 0.12);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.25);
      osc.start(now);
      osc.stop(now + 0.25);
    } else {
      // ボコッ
      osc.type = "sine";
      osc.frequency.setValueAtTime(200, now);
      osc.frequency.exponentialRampToValueAtTime(50, now + 0.12);
      gain.gain.setValueAtTime(0.4, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    }
  }

  // リアクションごとのクリック回数管理
  const clickCounts = {};

  function checkExplosionAndSound(btn, postId, reactionType) {
    const key = postId + "_" + reactionType;
    if (!clickCounts[key]) {
      clickCounts[key] = 0;
    }
    clickCounts[key]++;
    const count = clickCounts[key];

    playFunnySound(count);

    if (count >= 300) {
      triggerExplosion(btn, postId, reactionType);
      return true;
    }
    return false;
  }

  function triggerExplosion(btn, postId, reactionType) {
    btn.disabled = true;

    // 爆発パーティクル
    const rect = btn.getBoundingClientRect();
    const container = document.createElement("div");
    container.style.position = "fixed";
    container.style.left = (rect.left + rect.width / 2) + "px";
    container.style.top = (rect.top + rect.height / 2) + "px";
    container.style.zIndex = "9999";
    container.style.pointerEvents = "none";
    document.body.appendChild(container);

    const emojis = ["💥", "✨", "🔥", "⭐", "💫", "💨", "🚀", "🌟"];
    for (let i = 0; i < 35; i++) {
      const p = document.createElement("div");
      p.textContent = emojis[Math.floor(Math.random() * emojis.length)];
      p.style.position = "absolute";
      p.style.fontSize = (Math.random() * 26 + 18) + "px";
      p.style.transition = "all 0.7s ease-out";
      container.appendChild(p);

      const angle = Math.random() * Math.PI * 2;
      const dist = Math.random() * 200 + 60;
      const tx = Math.cos(angle) * dist;
      const ty = Math.sin(angle) * dist;

      requestAnimationFrame(function () {
        p.style.transform = "translate(" + tx + "px, " + ty + "px) scale(" + (Math.random() + 0.6) + ") rotate(" + (Math.random() * 360) + "deg)";
        p.style.opacity = "0";
      });
    }

    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<span style="color: #c0392b; font-weight: bold; font-size: 14px;">💥 ボカーン！こわれた！ 💥</span>';
    btn.style.backgroundColor = "#fadbd8";
    btn.style.borderColor = "#c0392b";
    btn.style.cursor = "not-allowed";

    setTimeout(function () {
      container.remove();
    }, 1200);

    setTimeout(function () {
      btn.innerHTML = originalHTML;
      btn.style.backgroundColor = "";
      btn.style.borderColor = "";
      btn.style.cursor = "pointer";
      btn.disabled = false;
      clickCounts[postId + "_" + reactionType] = 0;
    }, 6000);
  }

  /** HTML特殊文字のエスケープ（テキストをそのままHTMLに差し込む場合の安全対策） */
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&",
        "<": "<",
        ">": ">",
        '"': """,
        "'": "&#39;",
      }[c];
    });
  }

  return {
    api: api,
    requireLogin: requireLogin,
    bump: bump,
    bounce: bounce,
    escapeHtml: escapeHtml,
    checkExplosionAndSound: checkExplosionAndSound,
  };
})();
