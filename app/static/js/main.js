/**
 * 縁側（えんがわ） フロントエンドJS
 * 実際のバックエンドAPIと通信して動作する。
 */

(function () {
  "use strict";

  function qs(selector, root) {
    return (root || document).querySelector(selector);
  }
  function qsa(selector, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(selector));
  }

  async function postForm(url, data) {
    const formData = new FormData();
    Object.keys(data).forEach(function (key) {
      if (data[key] !== undefined && data[key] !== null) {
        formData.append(key, data[key]);
      }
    });
    const res = await fetch(url, {
      method: "POST",
      body: formData,
    });
    const json = await res.json().catch(function () {
      return {};
    });
    if (!res.ok) {
      const err = new Error(json.detail || "エラーが発生しました");
      err.data = json;
      throw err;
    }
    return json;
  }

  // ===================================================================
  // ログイン画面
  // ===================================================================
  function initLoginPage() {
    const stepPhone = qs("#step-phone");
    const stepCode = qs("#step-code");
    const phoneInput = qs("#phone-input");
    const btnSendCode = qs("#btn-send-code");
    const btnConfirmCode = qs("#btn-confirm-code");
    const btnResend = qs("#btn-resend");
    const codeBoxes = qsa(".code-box");
    const codeStatus = qs("#code-status");
    const debugNote = qs("#debug-code-note");
    const errorBox = qs("#login-error");

    let currentPhone = "";

    function showError(message) {
      errorBox.textContent = message;
      errorBox.hidden = false;
    }
    function clearError() {
      errorBox.hidden = true;
      errorBox.textContent = "";
    }

    function getCode() {
      return codeBoxes.map(function (box) {
        return box.value;
      }).join("");
    }

    function updateConfirmButton() {
      const code = getCode();
      btnConfirmCode.disabled = code.length !== 4;
    }

    function goToCodeStep() {
      stepPhone.classList.remove("login-step--active");
      stepCode.classList.add("login-step--active");
      codeBoxes.forEach(function (box) {
        box.value = "";
        box.classList.remove("code-box--filled");
      });
      updateConfirmButton();
      codeBoxes[0].focus();
    }

    async function sendCode() {
      clearError();
      currentPhone = (phoneInput.value || "").trim();
      if (currentPhone.length < 10) {
        showError("正しい携帯電話番号を入力してください");
        return;
      }
      btnSendCode.disabled = true;
      btnSendCode.textContent = "送信中…";
      try {
        const result = await postForm("/api/auth/send-code", {
          phone_number: currentPhone,
        });
        if (result.debug_code) {
          debugNote.hidden = false;
          debugNote.textContent =
            "【開発モード】認証コード：" + result.debug_code;
        } else {
          debugNote.hidden = true;
        }
        codeStatus.textContent = result.message || "コードを入力してください";
        goToCodeStep();
      } catch (e) {
        showError(e.message);
      } finally {
        btnSendCode.disabled = false;
        btnSendCode.textContent = "認証コードを送る";
      }
    }

    async function verifyCode() {
      clearError();
      const code = getCode();
      if (code.length !== 4) return;

      btnConfirmCode.disabled = true;
      btnConfirmCode.textContent = "確認中…";
      try {
        const result = await postForm("/api/auth/verify-code", {
          phone_number: currentPhone,
          code: code,
        });
        codeStatus.textContent = "認証できました！";
        window.location.href = result.redirect || "/";
      } catch (e) {
        showError(e.message);
        btnConfirmCode.disabled = false;
        btnConfirmCode.textContent = "つぎへ";
      }
    }

    btnSendCode.addEventListener("click", sendCode);
    phoneInput.addEventListener("keydown", function (e) {
      if (e.key === "Enter") sendCode();
    });

    btnResend.addEventListener("click", sendCode);

    codeBoxes.forEach(function (box, idx) {
      box.addEventListener("input", function () {
        box.value = box.value.replace(/[^0-9]/g, "").slice(0, 1);
        if (box.value) {
          box.classList.add("code-box--filled");
          if (idx < codeBoxes.length - 1) {
            codeBoxes[idx + 1].focus();
          }
        } else {
          box.classList.remove("code-box--filled");
        }
        updateConfirmButton();
        if (getCode().length === 4) {
          verifyCode();
        }
      });
      box.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !box.value && idx > 0) {
          codeBoxes[idx - 1].focus();
        }
      });
    });

    btnConfirmCode.addEventListener("click", verifyCode);
  }

  // ===================================================================
  // マイページ・かんたん投稿
  // ===================================================================
  function initHomePage() {
    const steps = qsa(".post-step");
    const dots = qsa(".step-dot");
    const photoInput = qs("#photo-input");
    const photoPreview = qs("#photo-preview");
    const btnSkipPhoto = qs("#btn-skip-photo");
    const stampBtns = qsa(".stamp-btn");
    const confirmPhoto = qs("#confirm-photo");
    const confirmStamp = qs("#confirm-stamp");
    const btnSubmitPost = qs("#btn-submit-post");
    const btnBackPost = qs("#btn-back-post");
    const postSuccess = qs("#post-success");
    const postError = qs("#post-error");
    const timelineList = qs("#timeline-list");
    const timelineEmpty = qs("#timeline-empty");

    if (!steps.length) return;

    let selectedPhotoFile = null;
    let selectedStamp = null;
    let selectedStampLabel = null;
    let currentStep = 1;

    function goToStep(step) {
      currentStep = step;
      steps.forEach(function (el, idx) {
        el.classList.toggle("post-step--active", idx === step - 1);
      });
      dots.forEach(function (dot) {
        const dotStep = parseInt(dot.dataset.step, 10);
        dot.classList.toggle("step-dot--active", dotStep === step);
        dot.classList.toggle("step-dot--done", dotStep < step);
      });
    }

    photoInput.addEventListener("change", function () {
      const file = photoInput.files && photoInput.files[0];
      if (!file) return;
      selectedPhotoFile = file;
      const reader = new FileReader();
      reader.onload = function (e) {
        photoPreview.src = e.target.result;
        photoPreview.hidden = false;
      };
      reader.readAsDataURL(file);
      setTimeout(function () {
        goToStep(2);
      }, 300);
    });

    btnSkipPhoto.addEventListener("click", function () {
      selectedPhotoFile = null;
      photoPreview.hidden = true;
      goToStep(2);
    });

    stampBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        stampBtns.forEach(function (b) {
          b.classList.remove("stamp-btn--selected");
        });
        btn.classList.add("stamp-btn--selected");
        selectedStamp = btn.dataset.stamp;
        selectedStampLabel = btn.dataset.label;

        if (selectedPhotoFile) {
          confirmPhoto.src = photoPreview.src;
          confirmPhoto.hidden = false;
        } else {
          confirmPhoto.hidden = true;
        }
        confirmStamp.textContent = selectedStamp + " " + selectedStampLabel;

        setTimeout(function () {
          goToStep(3);
        }, 300);
      });
    });

    btnBackPost.addEventListener("click", function () {
      goToStep(1);
      postError.hidden = true;
    });

    btnSubmitPost.addEventListener("click", async function () {
      if (!selectedStamp) return;
      postError.hidden = true;
      btnSubmitPost.disabled = true;
      btnSubmitPost.textContent = "投稿中…";

      try {
        const formData = new FormData();
        formData.append("stamp", selectedStamp);
        if (selectedPhotoFile) {
          formData.append("photo", selectedPhotoFile);
        }
        const res = await fetch("/api/posts", {
          method: "POST",
          body: formData,
        });
        const json = await res.json();
        if (!res.ok) {
          throw new Error(json.detail || "投稿に失敗しました");
        }

        // タイムラインに新しい投稿を先頭に追加
        if (timelineEmpty) timelineEmpty.hidden = true;
        const list = timelineList || createTimelineList();
        const li = document.createElement("li");
        li.className = "timeline-item";
        let photoHtml = "";
        if (json.post.image_path) {
          photoHtml =
            '<img class="timeline-item__photo" src="' +
            json.post.image_path +
            '" alt="投稿写真">';
        }
        li.innerHTML =
          photoHtml +
          '<div class="timeline-item__body">' +
          '<p class="timeline-item__stamp">' +
          json.post.stamp +
          " " +
          json.post.stamp_label +
          "</p>" +
          '<p class="timeline-item__date">' +
          json.post.created_at +
          "</p>" +
          "</div>";
        list.insertBefore(li, list.firstChild);

        postSuccess.hidden = false;
        setTimeout(function () {
          postSuccess.hidden = true;
          resetPostWidget();
        }, 2000);
      } catch (e) {
        postError.textContent = e.message;
        postError.hidden = false;
      } finally {
        btnSubmitPost.disabled = false;
        btnSubmitPost.textContent = "この内容で投稿する";
      }
    });

    function createTimelineList() {
      const section = qs(".post-timeline");
      const ul = document.createElement("ul");
      ul.className = "timeline-list";
      ul.id = "timeline-list";
      section.appendChild(ul);
      return ul;
    }

    function resetPostWidget() {
      selectedPhotoFile = null;
      selectedStamp = null;
      selectedStampLabel = null;
      photoInput.value = "";
      photoPreview.hidden = true;
      stampBtns.forEach(function (b) {
        b.classList.remove("stamp-btn--selected");
      });
      goToStep(1);
    }
  }

  // ===================================================================
  // おしゃべり・通話画面
  // ===================================================================
  function initTalkPage() {
    const btnOpen = qs("#btn-open-ai-call");
    const btnEnd = qs("#btn-end-call");
    const modal = qs("#ai-call-modal");
    const chatLog = qs("#chat-log");
    const chatForm = qs("#chat-form");
    const chatInput = qs("#chat-input");

    if (!btnOpen) return;

    function appendBubble(role, text) {
      const div = document.createElement("div");
      div.className = "chat-bubble chat-bubble--" + role;
      div.textContent = text;
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    btnOpen.addEventListener("click", function () {
      modal.hidden = false;
      chatLog.scrollTop = chatLog.scrollHeight;
      chatInput.focus();
    });

    btnEnd.addEventListener("click", function () {
      modal.hidden = true;
    });

    chatForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      const message = chatInput.value.trim();
      if (!message) return;

      appendBubble("user", message);
      chatInput.value = "";
      chatInput.disabled = true;

      const thinkingDiv = document.createElement("div");
      thinkingDiv.className = "chat-bubble chat-bubble--assistant chat-bubble--thinking";
      thinkingDiv.textContent = "…";
      chatLog.appendChild(thinkingDiv);
      chatLog.scrollTop = chatLog.scrollHeight;

      try {
        const formData = new FormData();
        formData.append("message", message);
        const res = await fetch("/api/talk/message", {
          method: "POST",
          body: formData,
        });
        const json = await res.json();
        thinkingDiv.remove();
        if (!res.ok) {
          appendBubble("assistant", json.detail || "エラーが発生しました");
        } else {
          appendBubble("assistant", json.reply);
        }
      } catch (err) {
        thinkingDiv.remove();
        appendBubble("assistant", "通信エラーが発生しました。もう一度お試しください。");
      } finally {
        chatInput.disabled = false;
        chatInput.focus();
      }
    });
  }

  // ===================================================================
  // お茶の間（グループおしゃべり）
  // ===================================================================
  function initOchanomaPage() {
    const introSection = qs("#ochanoma-intro");
    if (!introSection) return; // このページでなければ何もしない

    const waitingSection = qs("#ochanoma-waiting");
    const roomSection = qs("#ochanoma-room");
    const matchModal = qs("#match-modal");
    const matchModalDesc = qs("#match-modal-desc");

    const prefBtns = qsa(".pref-btn");
    const topicBtns = qsa(".topic-btn");
    const btnStartWaiting = qs("#btn-start-waiting");
    const btnCancelWaiting = qs("#btn-cancel-waiting");
    const btnJoinRoom = qs("#btn-join-room");
    const btnSkipRoom = qs("#btn-skip-room");
    const btnLeaveRoom = qs("#btn-leave-room");
    const waitingStatus = qs("#waiting-status");
    const errorBox = qs("#ochanoma-error");

    const roomParticipants = qs("#room-participants");
    const roomTopicBadge = qs("#room-topic-badge");
    const roomStatus = qs("#room-status");
    const chatLog = qs("#ochanoma-chat-log");
    const chatForm = qs("#ochanoma-chat-form");
    const chatInput = qs("#ochanoma-chat-input");
    const quickReplyBtns = qsa(".quick-reply-btn");

    let selectedStyle = null;
    const selectedTopics = [];
    let statusPollTimer = null;
    let messagesPollTimer = null;
    let currentRoomId = null;
    let renderedMessageCount = 0;

    function showError(message) {
      if (!errorBox) return;
      errorBox.textContent = message;
      errorBox.hidden = false;
    }
    function clearError() {
      if (!errorBox) return;
      errorBox.hidden = true;
    }

    function showSection(name) {
      introSection.hidden = name !== "intro";
      waitingSection.hidden = name !== "waiting";
      roomSection.hidden = name !== "room";
    }

    // ---- スタイル・話題選択 ----
    prefBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        prefBtns.forEach(function (b) {
          b.classList.remove("pref-btn--selected");
        });
        btn.classList.add("pref-btn--selected");
        selectedStyle = btn.dataset.style;
      });
    });

    topicBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const topic = btn.dataset.topic;
        const idx = selectedTopics.indexOf(topic);
        if (idx === -1) {
          selectedTopics.push(topic);
          btn.classList.add("topic-btn--selected");
        } else {
          selectedTopics.splice(idx, 1);
          btn.classList.remove("topic-btn--selected");
        }
      });
    });

    // ---- 待機開始 ----
    async function startWaiting() {
      clearError();
      if (!selectedStyle) {
        showError("今日のスタイルをえらんでください");
        return;
      }
      btnStartWaiting.disabled = true;
      try {
        const result = await postForm("/api/ochanoma/join", {
          style: selectedStyle,
          topics: selectedTopics.join(","),
        });
        handleStatus(result);
      } catch (e) {
        showError(e.message);
      } finally {
        btnStartWaiting.disabled = false;
      }
    }

    function startStatusPolling() {
      stopStatusPolling();
      statusPollTimer = setInterval(pollStatus, 2000);
    }
    function stopStatusPolling() {
      if (statusPollTimer) {
        clearInterval(statusPollTimer);
        statusPollTimer = null;
      }
    }

    async function pollStatus() {
      try {
        const res = await fetch("/api/ochanoma/status");
        const json = await res.json();
        handleStatus(json);
      } catch (e) {
        // 通信エラーはポーリングなので静かに無視する
      }
    }

    function handleStatus(status) {
      if (status.status === "idle") {
        stopStatusPolling();
        showSection("intro");
      } else if (status.status === "waiting") {
        showSection("waiting");
        waitingStatus.textContent =
          "あと" + status.waiting_for + "人待っています…";
        startStatusPolling();
      } else if (status.status === "matched") {
        stopStatusPolling();
        currentRoomId = status.room_id;
        if (status.confirmed) {
          enterRoom(status.room_id);
        } else {
          openMatchModal(status.topic);
        }
      }
    }

    function openMatchModal(topic) {
      matchModalDesc.textContent = topic
        ? "「" + topic + "」でお茶の間が開きます。参加しますか？"
        : "仲間が集まりました。参加しますか？";
      matchModal.hidden = false;
    }

    btnStartWaiting.addEventListener("click", startWaiting);
    btnCancelWaiting.addEventListener("click", async function () {
      stopStatusPolling();
      try {
        await postForm("/api/ochanoma/cancel", {});
      } catch (e) {
        /* noop */
      }
      showSection("intro");
    });

    btnJoinRoom.addEventListener("click", async function () {
      if (!currentRoomId) return;
      matchModal.hidden = true;
      try {
        await postForm("/api/ochanoma/room/" + currentRoomId + "/confirm", {});
        enterRoom(currentRoomId);
      } catch (e) {
        showError(e.message);
        showSection("intro");
      }
    });

    btnSkipRoom.addEventListener("click", async function () {
      matchModal.hidden = true;
      try {
        await postForm("/api/ochanoma/cancel", {});
      } catch (e) {
        /* noop */
      }
      showSection("intro");
    });

    btnLeaveRoom.addEventListener("click", async function () {
      stopMessagesPolling();
      const roomId = currentRoomId;
      currentRoomId = null;
      try {
        if (roomId) {
          await postForm("/api/ochanoma/room/" + roomId + "/leave", {});
        }
      } catch (e) {
        /* noop */
      }
      resetRoomUi();
      showSection("intro");
    });

    // ---- お茶の間ルーム ----
    function renderParticipants(participants) {
      roomParticipants.innerHTML = "";
      participants.forEach(function (p) {
        const div = document.createElement("div");
        div.className =
          "room-participant" + (p.is_self ? " room-participant--self" : "");
        div.innerHTML =
          '<div class="room-participant__avatar">' +
          p.avatar +
          "</div>" +
          '<div class="room-participant__name">' +
          (p.is_self ? "あなた" : p.name) +
          "</div>";
        roomParticipants.appendChild(div);
      });
    }

    function appendMessage(msg) {
      const div = document.createElement("div");
      let bubbleClass = "chat-bubble--assistant";
      let label = "";
      if (msg.role === "ai") {
        bubbleClass = "chat-bubble--assistant";
        label = "🤖 AI司会";
        roomStatus.textContent = "AI司会：" + msg.content;
      } else if (msg.role === "user") {
        bubbleClass = "chat-bubble--user";
      } else if (msg.role === "participant") {
        bubbleClass = "chat-bubble--participant";
        label = msg.avatar + " " + msg.name;
      }
      div.className = "chat-bubble " + bubbleClass;
      const nameHtml = label
        ? '<span class="chat-bubble__name">' + label + "</span>"
        : "";
      div.innerHTML = nameHtml + escapeHtml(msg.content);
      chatLog.appendChild(div);
      chatLog.scrollTop = chatLog.scrollHeight;
    }

    function escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text;
      return div.innerHTML;
    }

    function resetRoomUi() {
      chatLog.innerHTML = "";
      roomParticipants.innerHTML = "";
      renderedMessageCount = 0;
      roomStatus.textContent = "AI司会が進行しています";
    }

    async function enterRoom(roomId) {
      currentRoomId = roomId;
      try {
        const res = await fetch("/api/ochanoma/room/" + roomId);
        const json = await res.json();
        if (!res.ok) throw new Error(json.detail || "お茶の間の取得に失敗しました");

        resetRoomUi();
        roomTopicBadge.textContent = "話題：" + (json.room.topic || "雑談");
        renderParticipants(json.room.participants);
        json.room.messages.forEach(appendMessage);
        renderedMessageCount = json.room.messages.length;

        showSection("room");
        startMessagesPolling();
      } catch (e) {
        showError(e.message);
        showSection("intro");
      }
    }

    function startMessagesPolling() {
      stopMessagesPolling();
      messagesPollTimer = setInterval(pollMessages, 3000);
    }
    function stopMessagesPolling() {
      if (messagesPollTimer) {
        clearInterval(messagesPollTimer);
        messagesPollTimer = null;
      }
    }

    async function pollMessages() {
      if (!currentRoomId) return;
      try {
        const res = await fetch(
          "/api/ochanoma/room/" + currentRoomId + "/messages"
        );
        const json = await res.json();
        if (!res.ok) return;
        const messages = json.messages || [];
        for (let i = renderedMessageCount; i < messages.length; i++) {
          appendMessage(messages[i]);
        }
        renderedMessageCount = messages.length;
      } catch (e) {
        /* noop */
      }
    }

    async function sendRoomMessage(text) {
      if (!currentRoomId || !text) return;
      try {
        const res = await fetch(
          "/api/ochanoma/room/" + currentRoomId + "/messages",
          {
            method: "POST",
            body: (function () {
              const fd = new FormData();
              fd.append("text", text);
              return fd;
            })(),
          }
        );
        const json = await res.json();
        if (!res.ok) throw new Error(json.detail || "送信に失敗しました");
        const messages = json.messages || [];
        for (let i = renderedMessageCount; i < messages.length; i++) {
          appendMessage(messages[i]);
        }
        renderedMessageCount = messages.length;
      } catch (e) {
        /* noop */
      }
    }

    chatForm.addEventListener("submit", function (e) {
      e.preventDefault();
      const text = chatInput.value.trim();
      if (!text) return;
      chatInput.value = "";
      sendRoomMessage(text);
    });

    quickReplyBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        sendRoomMessage(btn.dataset.text);
      });
    });

    // ---- 初期状態の復元（他ページから戻ってきた場合など） ----
    (async function restoreState() {
      try {
        const res = await fetch("/api/ochanoma/status");
        const json = await res.json();
        handleStatus(json);
      } catch (e) {
        showSection("intro");
      }
    })();
  }

  // ===================================================================
  // みんなの縁側（グローバルタイムライン）
  // ===================================================================
  function initTimelinePage() {
    const list = qs("#global-timeline-list");
    if (!list) return; // このページでなければ何もしない

    async function react(postId, reactionType, btn) {
      try {
        const result = await postForm(
          "/api/posts/" + postId + "/react",
          { reaction_type: reactionType }
        );
        btn.classList.toggle("reaction-btn--active", result.reacted);
        const countEl = qs(".reaction-btn__count", btn);
        if (countEl) {
          countEl.textContent =
            reactionType === "warm" ? result.warm_count : result.cheer_count;
        }
      } catch (e) {
        // 通信エラー時は静かに無視（シニア向けUIでは余計なエラー表示を避ける）
      }
    }

    qsa(".reaction-btn", list).forEach(function (btn) {
      btn.addEventListener("click", function () {
        const postId = btn.dataset.postId;
        const reactionType = btn.dataset.reactionType;
        if (!postId || !reactionType) return;
        react(postId, reactionType, btn);
      });
    });
  }

  window.Engawa = {
    initLoginPage: initLoginPage,
    initHomePage: initHomePage,
    initTalkPage: initTalkPage,
    initOchanomaPage: initOchanomaPage,
    initTimelinePage: initTimelinePage,
  };

})();


