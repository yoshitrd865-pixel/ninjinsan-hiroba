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

  /** HTML特殊文字のエスケープ（テキストをそのままHTMLに差し込む場合の安全対策） */
  function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c];
    });
  }

  return { api: api, requireLogin: requireLogin, bump: bump, bounce: bounce, escapeHtml: escapeHtml };
})();
