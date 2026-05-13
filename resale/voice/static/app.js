// Resale Voice Copilot — browser frontend
// - Web Speech API for STT (push-to-talk)
// - SSE stream from /api/chat for Claude reply
// - SpeechSynthesis for TTS, queued by sentence as deltas arrive

(() => {
  const $ = (id) => document.getElementById(id);
  const transcriptEl = $("transcript");
  const micBtn = $("mic-btn");
  const camBtn = $("cam-btn");
  const statusEl = $("status");
  const resetBtn = $("reset-btn");

  // ---- Camera capture state ----
  let pendingPhotos = []; // [{data: base64, media_type: "image/jpeg"}]
  let cameraStream = null;

  camBtn.addEventListener("click", () => openCamera());

  function openCamera() {
    const overlay = $("camera-overlay");
    const video = $("camera-video");
    const thumbs = $("camera-thumbs");
    const shutterBtn = $("camera-shutter");
    const closeBtn = $("camera-close");
    const countEl = $("camera-count");

    thumbs.innerHTML = "";
    countEl.textContent = pendingPhotos.length;

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 } }, audio: false })
      .then((stream) => {
        cameraStream = stream;
        video.srcObject = stream;
        overlay.classList.remove("hidden");

        shutterBtn.onclick = () => {
          const canvas = document.createElement("canvas");
          const scale = Math.min(1568 / video.videoWidth, 1568 / video.videoHeight, 1);
          canvas.width = Math.round(video.videoWidth * scale);
          canvas.height = Math.round(video.videoHeight * scale);
          canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
          const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
          pendingPhotos.push({ data: dataUrl.split(",")[1], media_type: "image/jpeg" });
          countEl.textContent = pendingPhotos.length;

          // Thumbnail
          const img = document.createElement("img");
          img.src = dataUrl;
          img.className = "camera-thumb";
          thumbs.appendChild(img);
          thumbs.scrollLeft = thumbs.scrollWidth;

          // Flash
          shutterBtn.style.transform = "scale(1.3)";
          setTimeout(() => (shutterBtn.style.transform = ""), 120);
        };

        closeBtn.onclick = () => closeCamera();
      })
      .catch((err) => {
        setStatus("Camera: " + err.message + ". HTTPS required on phone.", "error");
      });
  }

  function closeCamera() {
    const overlay = $("camera-overlay");
    overlay.classList.add("hidden");
    if (cameraStream) {
      cameraStream.getTracks().forEach((t) => t.stop());
      cameraStream = null;
    }
    if (pendingPhotos.length) {
      // Show thumbnails in transcript
      const strip = document.createElement("div");
      strip.className = "photo-strip";
      pendingPhotos.forEach((p) => {
        const img = document.createElement("img");
        img.src = "data:" + p.media_type + ";base64," + p.data;
        strip.appendChild(img);
      });
      transcriptEl.appendChild(strip);
      transcriptEl.scrollTop = transcriptEl.scrollHeight;
      setStatus(pendingPhotos.length + " photo(s). Tap mic to tell me about the item.");
    }
  }

  // ---- Session id (persists across reloads on same browser) ----
  let sessionId = localStorage.getItem("resale_session_id");
  if (!sessionId) {
    sessionId =
      "sess_" + Date.now().toString(36) + "_" +
      Math.random().toString(36).slice(2, 10);
    localStorage.setItem("resale_session_id", sessionId);
  }

  // ---- STT setup ----
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    statusEl.textContent =
      "Voice input not supported in this browser. Try Chrome, Edge, or Android Chrome.";
    statusEl.classList.add("error");
    micBtn.disabled = true;
    return;
  }

  const recognition = new SR();
  recognition.lang = "en-US";
  recognition.interimResults = true;
  recognition.continuous = false;
  recognition.maxAlternatives = 1;

  let isRecording = false;
  let isSpeaking = false;
  let currentTranscript = "";
  let partialBubble = null;

  function setStatus(text, cls = "hint") {
    statusEl.textContent = text;
    statusEl.className = cls;
  }

  function addBubble(role, text = "") {
    const el = document.createElement("div");
    el.className = `msg ${role}`;
    el.textContent = text;
    transcriptEl.appendChild(el);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
    return el;
  }

  function startRecording() {
    if (isSpeaking) {
      // Barge-in: cut off TTS so the operator can interrupt
      window.speechSynthesis.cancel();
      isSpeaking = false;
    }
    currentTranscript = "";
    partialBubble = addBubble("user partial", "…");
    try {
      recognition.start();
    } catch (e) {
      // Already started — ignore
    }
  }

  function stopRecording() {
    try {
      recognition.stop();
    } catch (e) {}
  }

  micBtn.addEventListener("click", () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  });

  recognition.addEventListener("start", () => {
    isRecording = true;
    micBtn.classList.add("recording");
    setStatus("Listening…", "listening");
  });

  recognition.addEventListener("result", (event) => {
    let final = "";
    let interim = "";
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const r = event.results[i];
      if (r.isFinal) final += r[0].transcript;
      else interim += r[0].transcript;
    }
    currentTranscript = (currentTranscript + final).trim();
    if (partialBubble) {
      partialBubble.textContent = (currentTranscript + " " + interim).trim() || "…";
    }
  });

  recognition.addEventListener("error", (e) => {
    setStatus(`Mic error: ${e.error}`, "error");
    isRecording = false;
    micBtn.classList.remove("recording");
    if (partialBubble && !currentTranscript) {
      partialBubble.remove();
      partialBubble = null;
    }
  });

  recognition.addEventListener("end", async () => {
    isRecording = false;
    micBtn.classList.remove("recording");

    let message = currentTranscript.trim();
    if (!message && pendingPhotos.length === 0) {
      setStatus("Didn't catch that. Tap to try again.");
      if (partialBubble) {
        partialBubble.remove();
        partialBubble = null;
      }
      return;
    }
    // If photos are pending but no voice, send with a default prompt
    if (!message && pendingPhotos.length > 0) {
      message = "What's this? Quick ID and price estimate.";
    }

    // Promote the partial bubble to final
    if (partialBubble) {
      partialBubble.textContent = message;
      partialBubble.classList.remove("partial");
      partialBubble = null;
    }

    setStatus("Thinking…");
    await sendMessage(message);
  });

  // ---- SSE chat stream + TTS sentence queueing ----
  const TOOL_LABELS = {
    capture: "📝 saving",
    recall: "🔎 recalling",
    list_open: "📋 reading list",
    complete: "✓ marking done",
  };

  function addToolChip(toolName) {
    const el = document.createElement("div");
    el.className = "tool-chip";
    el.textContent = TOOL_LABELS[toolName] || `🔧 ${toolName}`;
    transcriptEl.appendChild(el);
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
    return el;
  }

  async function sendMessage(message) {
    let replyBubble = addBubble("assistant", "");
    let buffer = "";
    let spokenUpTo = 0;
    let pendingToolChip = null;

    try {
      // Drain pending photos so they're sent exactly once
      const images = pendingPhotos.splice(0);
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message, images }),
      });

      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let raw = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        raw += decoder.decode(value, { stream: true });

        // SSE: events separated by \n\n, each line starts with `data: `
        const events = raw.split("\n\n");
        raw = events.pop(); // keep last (possibly incomplete) chunk
        for (const ev of events) {
          const line = ev.trim();
          if (!line.startsWith("data:")) continue;
          const payload = JSON.parse(line.slice(5).trim());

          if (payload.error) {
            replyBubble.textContent = `[error] ${payload.error}`;
            setStatus("Error from API.", "error");
            return;
          }

          if (payload.tool_start) {
            // If reply bubble has no text yet, remove it; tool chip
            // will sit by itself, then a fresh bubble starts after.
            if (!buffer && replyBubble) {
              replyBubble.remove();
              replyBubble = null;
              spokenUpTo = 0;
            }
            pendingToolChip = addToolChip(payload.tool_start.name);
            continue;
          }

          if (payload.tool_done) {
            if (pendingToolChip) {
              pendingToolChip.classList.add("done");
              pendingToolChip = null;
            }
            continue;
          }

          if (payload.delta !== undefined) {
            // Start a new bubble after tool calls if needed
            if (!replyBubble) {
              replyBubble = addBubble("assistant", "");
              buffer = "";
              spokenUpTo = 0;
            }
            buffer += payload.delta;
            replyBubble.textContent = buffer;
            transcriptEl.scrollTop = transcriptEl.scrollHeight;

            // Flush complete sentences to TTS as they arrive
            spokenUpTo = flushSentencesToTTS(buffer, spokenUpTo);
          }

          if (payload.done) {
            // Speak whatever tail remains (no terminal punctuation)
            const tail = buffer.slice(spokenUpTo).trim();
            if (tail) speak(tail);
            const u = payload.usage || {};
            const cacheHit = u.cache_read > 0
              ? ` · cache ${u.cache_read} read`
              : "";
            setStatus(
              `Done · ${u.output_tokens || 0} out${cacheHit}. Tap mic to reply.`,
            );
          }
        }
      }
    } catch (err) {
      if (replyBubble) replyBubble.textContent = `[error] ${err.message}`;
      setStatus("Network error.", "error");
    }
  }

  // Find sentence boundaries in `buffer[startIdx:]` and queue each to TTS.
  // Returns the new index up to which we've spoken.
  function flushSentencesToTTS(buffer, startIdx) {
    const tail = buffer.slice(startIdx);
    // Match sentences ending in . ! ? followed by whitespace OR end-of-string-ish
    const re = /[^.!?]+[.!?]+(?=\s|$)/g;
    let consumed = 0;
    let m;
    while ((m = re.exec(tail)) !== null) {
      speak(m[0].trim());
      consumed = m.index + m[0].length;
    }
    return startIdx + consumed;
  }

  function speak(text) {
    if (!text) return;
    const u = new SpeechSynthesisUtterance(text);
    // Try to pick a nicer voice if available
    const voices = window.speechSynthesis.getVoices();
    const preferred =
      voices.find((v) => /Samantha|Google US English|Microsoft Aria/i.test(v.name)) ||
      voices.find((v) => v.lang === "en-US");
    if (preferred) u.voice = preferred;
    u.rate = 1.05;
    u.pitch = 1.0;
    u.onstart = () => {
      isSpeaking = true;
      micBtn.classList.add("speaking");
    };
    u.onend = () => {
      // speaking flag clears only when the utterance queue drains
      if (!window.speechSynthesis.speaking) {
        isSpeaking = false;
        micBtn.classList.remove("speaking");
      }
    };
    window.speechSynthesis.speak(u);
  }

  // Voices may load asynchronously — kick the list once the event fires
  window.speechSynthesis.onvoiceschanged = () => {};

  // ---- Reset button ----
  resetBtn.addEventListener("click", async () => {
    if (!confirm("Clear this conversation?")) return;
    window.speechSynthesis.cancel();
    transcriptEl.innerHTML = "";
    setStatus("Cleared. Tap mic to start fresh.");
    await fetch("/api/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }),
    });
  });

  setStatus("Ready. Tap the mic to talk.");
})();
