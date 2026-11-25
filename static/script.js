// Browser side of the sales call.
//
// The backend does not remember the chat by itself. This page keeps the
// transcript and sends the recent turns with every message. SQLite is used
// only after "Save lead".
//
// Speech recognition is browser-provided and may not be available in every browser.

const STORAGE_KEY = "routiqo-sales-agent-session";

const SpeechRecognitionAPI =
  window.SpeechRecognition || window.webkitSpeechRecognition;
const supportsSpeechInput = Boolean(SpeechRecognitionAPI);
const supportsSpeechOutput = "speechSynthesis" in window;
const SPEECH_HINTS = [
  "Routiqo",
  "Fleet management",
  "Route optimization",
  "Logistics",
  "Vehicle tracking",
  "Dispatch management",
  "Last-mile delivery",
];
const MAX_RESTARTS = 3;

const state = {
  conversationId: null,
  history: [],
  active: false,
  phase: "idle",
  recognition: null,
  recognitionRunning: false,
  stopRequested: false,
  pauseRequested: false,
  resumeAfterPause: false,
  clearRequested: false,
  recognitionError: null,
  phraseHintsDisabled: false,
  phraseHintFallbackPending: false,
  shownSpeechNotices: new Set(),
  restartAttempts: 0,
  restartTimer: null,
  finalTranscript: "",
  interimTranscript: "",
  currentResults: new Map(),
  manual: {},
  lastSummary: null,
  selectedLeadId: null,
};

const els = {
  connection: document.getElementById("connection-status"),
  aiMode: document.getElementById("ai-mode"),
  activity: document.getElementById("activity-status"),
  banner: document.getElementById("demo-banner"),
  transcript: document.getElementById("transcript"),
  draft: document.getElementById("draft-line"),
  support: document.getElementById("speech-support"),
  start: document.getElementById("start-btn"),
  stop: document.getElementById("stop-btn"),
  clearTranscript: document.getElementById("clear-transcript"),
  language: document.getElementById("recognition-language"),
  mic: document.getElementById("mic-btn"),
  textForm: document.getElementById("text-form"),
  message: document.getElementById("message-input"),
  send: document.getElementById("send-btn"),
  leadForm: document.getElementById("lead-form"),
  name: document.getElementById("customer-name"),
  company: document.getElementById("company-name"),
  email: document.getElementById("email"),
  vehicles: document.getElementById("vehicle-count"),
  problem: document.getElementById("business-problem"),
  demo: document.getElementById("demo-interest"),
  demoFlag: document.getElementById("demo-requested"),
  score: document.getElementById("lead-score"),
  status: document.getElementById("qualification-status"),
  action: document.getElementById("next-action"),
  breakdown: document.getElementById("score-breakdown"),
  formError: document.getElementById("form-error"),
  save: document.getElementById("save-lead"),
  summaryRequirements: document.getElementById("summary-requirements"),
  summaryPain: document.getElementById("summary-pain"),
  summarySize: document.getElementById("summary-size"),
  summaryScore: document.getElementById("summary-score"),
  summaryDemo: document.getElementById("summary-demo"),
  summaryText: document.getElementById("summary-text"),
  summaryAction: document.getElementById("summary-action"),
  summaryMode: document.getElementById("summary-mode"),
  readSummary: document.getElementById("read-summary"),
  leadsBody: document.getElementById("leads-body"),
  leadsCount: document.getElementById("leads-count"),
  leadsEmpty: document.getElementById("leads-empty"),
  refresh: document.getElementById("refresh-leads"),
  newConversation: document.getElementById("new-conversation"),
};

const fieldMap = {
  customer_name: els.name,
  company_name: els.company,
  email: els.email,
  vehicle_count: els.vehicles,
  business_problem: els.problem,
  interested_in_demo: els.demo,
};

function setPhase(phase) {
  state.phase = phase;
  document.body.dataset.phase = phase;
  const labels = {
    idle: "Idle",
    listening: "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
  };
  els.activity.textContent = labels[phase] || "Idle";
  const listening = phase === "listening";
  els.mic.setAttribute("aria-pressed", listening ? "true" : "false");
  const current = {
    listening: "stage-listen",
    thinking: "stage-reply",
    speaking: "stage-reply",
  }[phase];
  document.querySelectorAll(".stages li").forEach((item) => {
    item.classList.toggle("is-current", item.id === current);
  });
}

function setStage(id) {
  document.querySelectorAll(".stages li").forEach((item) => {
    item.classList.toggle("is-current", item.id === id);
  });
}

function addMessage(role, text, meta) {
  const wrap = document.createElement("article");
  wrap.className = `message ${role}`;
  const who = document.createElement("div");
  who.className = "who";
  who.textContent =
    role === "user" ? "Customer" : role === "assistant" ? "Routiqo" : "Note";
  const bubble = document.createElement("p");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.append(who, bubble);
  if (meta) {
    const line = document.createElement("p");
    line.className = "meta-line";
    line.textContent = meta;
    wrap.append(line);
  }
  els.transcript.append(wrap);
  els.transcript.scrollTop = els.transcript.scrollHeight;
}

function addSpeechNoticeOnce(key, text) {
  if (state.shownSpeechNotices.has(key)) return;
  state.shownSpeechNotices.add(key);
  addMessage("system", text);
}

function showError(message) {
  els.formError.hidden = false;
  els.formError.textContent = message;
}

function clearError() {
  els.formError.hidden = true;
  els.formError.textContent = "";
}

function errorText(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  if (Array.isArray(data.detail)) {
    return data.detail.map((item) => item.msg).join(" ");
  }
  return fallback;
}

async function api(path, options) {
  const response = await fetch(path, options);
  let data = null;
  try {
    data = await response.json();
  } catch (_error) {
    data = null;
  }
  if (!response.ok) {
    throw new Error(errorText(data, `Request failed (${response.status}).`));
  }
  return data;
}

function transcriptText() {
  return state.history
    .map(
      (item) =>
        `${item.role === "user" ? "Customer" : "Assistant"}: ${item.content}`,
    )
    .join("\n");
}

function currentLeadFields() {
  const demoValue = els.demo.value;
  const vehicles = els.vehicles.value.trim();
  return {
    customer_name: els.name.value.trim(),
    company_name: els.company.value.trim(),
    email: els.email.value.trim(),
    vehicle_count: vehicles === "" ? null : Number(vehicles),
    business_problem: els.problem.value.trim(),
    interested_in_demo:
      demoValue === "yes" ? true : demoValue === "no" ? false : null,
  };
}

function applyHints(hints) {
  if (!hints) return;
  const mapping = {
    customer_name: hints.customer_name,
    company_name: hints.company_name,
    email: hints.email,
    vehicle_count: hints.vehicle_count,
    business_problem: hints.business_problem,
  };
  Object.entries(mapping).forEach(([key, value]) => {
    if (value === undefined || value === null || state.manual[key]) return;
    fieldMap[key].value = value;
  });
  if (
    hints.interested_in_demo !== undefined &&
    hints.interested_in_demo !== null &&
    !state.manual.interested_in_demo
  ) {
    els.demo.value = hints.interested_in_demo ? "yes" : "no";
  }
  els.demoFlag.hidden = els.demo.value !== "yes";
}

function renderScore(lead) {
  els.score.textContent = lead.lead_score;
  els.status.textContent = lead.qualification_status;
  els.status.className = "status-pill";
  if (lead.qualification_status === "Qualified")
    els.status.classList.add("qualified");
  if (lead.qualification_status === "Potential")
    els.status.classList.add("potential");
  if (lead.qualification_status === "Not Qualified")
    els.status.classList.add("unqualified");
  els.action.textContent =
    lead.recommended_next_action || lead.next_action || "";
  const breakdown = lead.score_breakdown;
  els.breakdown.replaceChildren();
  if (!breakdown) {
    els.breakdown.hidden = true;
    return;
  }
  const rows = [
    ["Vehicles (10 or more)", breakdown.vehicle_count, 30],
    ["Logistics problem", breakdown.business_problem, 30],
    ["Demo interest", breakdown.demo_interest, 25],
    ["Contact email", breakdown.contact_information, 15],
  ];
  rows.forEach(([label, points, max]) => {
    const item = document.createElement("li");
    const name = document.createElement("span");
    name.textContent = label;
    const value = document.createElement("span");
    value.textContent = `${points} / ${max}`;
    item.append(name, value);
    els.breakdown.append(item);
  });
  els.breakdown.hidden = false;
}

function renderSummary(summary, sourceLabel) {
  state.lastSummary = summary;
  els.summaryRequirements.textContent = summary.customer_requirements || "—";
  els.summaryPain.textContent = summary.pain_points || "—";
  const vehicles = currentLeadFields().vehicle_count;
  els.summarySize.textContent =
    vehicles === null || Number.isNaN(vehicles) ? "—" : `${vehicles} vehicles`;
  const score = summary.lead_score;
  const status = summary.qualification_status;
  els.summaryScore.textContent =
    score === null || score === undefined ? "—" : `${score} (${status})`;
  els.summaryDemo.textContent = summary.demo_interest || "—";
  els.summaryText.textContent = summary.summary || "—";
  els.summaryAction.textContent = summary.next_action || "—";
  els.summaryMode.textContent = sourceLabel;
}

function showSavedLead(lead) {
  state.selectedLeadId = lead.id;
  renderSummary(
    {
      customer_requirements: lead.business_problem || "Not stated",
      pain_points: lead.business_problem || "Not stated",
      lead_score: lead.lead_score,
      qualification_status: lead.qualification_status,
      demo_interest: lead.interested_in_demo
        ? "Demo requested"
        : "No demo requested",
      summary: lead.call_summary || "No summary stored.",
      next_action: lead.next_action,
    },
    `Saved lead #${lead.id}. Loaded from SQLite.`,
  );
  els.summarySize.textContent = `${lead.vehicle_count} vehicles`;
  document.querySelectorAll("#leads-body tr").forEach((row) => {
    row.classList.toggle("is-selected", Number(row.dataset.id) === lead.id);
  });
}

function renderLeads(payload) {
  els.leadsBody.replaceChildren();
  const leads = payload.leads || [];
  els.leadsCount.textContent =
    leads.length === 1 ? "1 saved lead" : `${leads.length} saved leads`;
  els.leadsEmpty.hidden = leads.length !== 0;
  leads.forEach((lead) => {
    const row = document.createElement("tr");
    row.dataset.id = String(lead.id);
    row.tabIndex = 0;
    const values = [
      lead.company_name,
      lead.customer_name,
      lead.vehicle_count,
      lead.lead_score,
      lead.qualification_status,
      lead.interested_in_demo ? "Demo requested" : "No",
      formatDate(lead.created_at),
    ];
    values.forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.append(cell);
    });
    row.addEventListener("click", () => showSavedLead(lead));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter") showSavedLead(lead);
    });
    els.leadsBody.append(row);
  });
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function persistSession() {
  const payload = {
    conversationId: state.conversationId,
    history: state.history,
    finalTranscript: state.finalTranscript,
    fields: currentLeadFields(),
    demoValue: els.demo.value,
    manual: state.manual,
  };
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
}

function restoreSession() {
  const raw = sessionStorage.getItem(STORAGE_KEY);
  if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    state.conversationId = saved.conversationId || null;
    state.history = Array.isArray(saved.history) ? saved.history : [];
    state.finalTranscript =
      typeof saved.finalTranscript === "string" ? saved.finalTranscript : "";
    state.manual = saved.manual || {};
    if (saved.fields) {
      els.name.value = saved.fields.customer_name || "";
      els.company.value = saved.fields.company_name || "";
      els.email.value = saved.fields.email || "";
      els.vehicles.value = saved.fields.vehicle_count ?? "";
      els.problem.value = saved.fields.business_problem || "";
      els.demo.value = saved.demoValue || "unknown";
    }
    if (state.history.length) {
      els.transcript.replaceChildren();
      state.history.forEach((item) => addMessage(item.role, item.content));
    }
    els.demoFlag.hidden = els.demo.value !== "yes";
    renderSpeechDraft();
  } catch (_error) {
    sessionStorage.removeItem(STORAGE_KEY);
  }
}

function ensureConversation() {
  if (!state.conversationId) {
    state.conversationId = crypto.randomUUID().replace(/-/g, "");
  }
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || state.sending) return;
  clearError();
  ensureConversation();
  addMessage("user", message);
  const historyToSend = state.history.slice(-12);
  state.history.push({ role: "user", content: message });
  persistSession();
  els.message.value = "";
  if (state.sending) return;
  state.sending = true;
  els.send.disabled = true;
  updateRecognitionControls();
  setPhase("thinking");
  setStage("stage-reply");
  try {
    const data = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: state.conversationId,
        message,
        conversation_history: historyToSend,
      }),
    });
    state.conversationId = data.conversation_id;
    state.history.push({ role: "assistant", content: data.response });
    const bits = [
      data.mode === "gemini" ? "Gemini response" : "Demo mode response",
    ];
    if (data.knowledge_sections && data.knowledge_sections.length) {
      bits.push(`Knowledge: ${data.knowledge_sections.join(", ")}`);
    }
    addMessage("assistant", data.response, bits.join(" · "));
    if (data.notice) addMessage("system", data.notice);
    applyHints(data.lead_hints);
    persistSession();
    setStage("stage-qualify");
    await speak(data.response);
  } catch (error) {
    addMessage("system", error.message || "The message could not be sent.");
    setPhase(state.active ? "listening" : "idle");
    if (state.active) startListening();
  } finally {
    state.sending = false;
    els.send.disabled = false;
    updateRecognitionControls();
  }
}

function speak(text) {
  if (!supportsSpeechOutput || !text) {
    if (state.active) startListening();
    else setPhase("idle");
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    const voice = window.speechSynthesis
      .getVoices()
      .find((item) => item.lang && item.lang.toLowerCase().startsWith("en"));
    if (voice) utterance.voice = voice;
    utterance.onstart = () => setPhase("speaking");
    const finish = () => {
      if (state.active) startListening();
      else setPhase("idle");
      resolve();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    // A short pause keeps the microphone from hearing the last word of playback.
    window.setTimeout(() => window.speechSynthesis.speak(utterance), 150);
  });
}

function joinedText(first, second) {
  return [first.trim(), second.trim()].filter(Boolean).join(" ");
}

function currentRecognitionText() {
  const results = [...state.currentResults.entries()].sort(
    ([left], [right]) => left - right,
  );
  return {
    final: results
      .filter(([, result]) => result.isFinal)
      .map(([, result]) => result.text)
      .join(" ")
      .trim(),
    interim: results
      .filter(([, result]) => !result.isFinal)
      .map(([, result]) => result.text)
      .join(" ")
      .trim(),
  };
}

function renderSpeechDraft() {
  const current = currentRecognitionText();
  state.interimTranscript = current.interim;
  const finalized = joinedText(state.finalTranscript, current.final);
  els.draft.replaceChildren();
  if (finalized) {
    const finalPart = document.createElement("span");
    finalPart.className = "draft-final";
    finalPart.textContent = finalized;
    els.draft.append(finalPart);
  }
  if (state.interimTranscript) {
    if (finalized) els.draft.append(document.createTextNode(" "));
    const interimPart = document.createElement("span");
    interimPart.className = "draft-interim";
    interimPart.textContent = state.interimTranscript;
    els.draft.append(interimPart);
  }
  els.draft.hidden = !finalized && !state.interimTranscript;
}

function commitCurrentResults() {
  const current = currentRecognitionText();
  state.finalTranscript = joinedText(state.finalTranscript, current.final);
  state.currentResults.clear();
  state.interimTranscript = "";
  renderSpeechDraft();
  persistSession();
}

function updateRecognitionControls() {
  els.start.disabled =
    !supportsSpeechInput ||
    !state.recognition ||
    state.active ||
    state.recognitionRunning ||
    state.sending;
  els.stop.disabled =
    state.sending || (!state.active && !state.finalTranscript.trim());
  els.language.disabled = !supportsSpeechInput || state.active || state.sending;
  els.mic.disabled =
    !supportsSpeechInput || !state.recognition || state.sending;
  els.mic.setAttribute("aria-pressed", state.active ? "true" : "false");
}

function finishCapture() {
  state.stopRequested = false;
  state.active = false;
  updateRecognitionControls();
  setPhase("idle");
  const transcript = state.finalTranscript.trim();
  if (!transcript) {
    els.support.textContent =
      "No finalized speech was captured. Try again or type your message.";
    addSpeechNoticeOnce(
      "empty-capture",
      "No finalized speech to send. Try speaking again or use the text box.",
    );
    return;
  }
  state.finalTranscript = "";
  state.interimTranscript = "";
  state.currentResults.clear();
  renderSpeechDraft();
  persistSession();
  els.support.textContent = "Listening stopped. Final transcript sent to chat.";
  sendMessage(transcript);
}

function handleRecognitionError(error) {
  const messages = {
    "audio-capture":
      "No microphone was detected. Check the selected input device and browser permissions.",
    "no-speech": "No speech was detected. Press Start Listening and try again.",
    "not-allowed":
      "Microphone permission was denied. Allow microphone access for this site in your browser settings.",
    "service-not-allowed":
      "This browser blocked its speech service. Try Chrome, check browser settings, or type your message.",
    network:
      "The browser speech service reported a network error. Brave support varies; try Chrome or use the text box.",
  };
  state.recognitionError = error;
  if (!state.stopRequested) state.active = false;
  els.support.textContent =
    messages[error] ||
    `Speech recognition error: ${error}. Retry or type your message.`;
  updateRecognitionControls();
  setPhase("idle");
  if (error !== "aborted" || (!state.stopRequested && !state.clearRequested)) {
    addMessage(
      "system",
      messages[error] ||
        `Speech recognition error: ${error}. You can retry or type your message.`,
    );
  }
}

function startRecognitionRun() {
  if (!state.active || !state.recognition || state.recognitionRunning) return;
  state.currentResults.clear();
  state.interimTranscript = "";
  state.recognition.lang = els.language.value;
  renderSpeechDraft();
  try {
    state.recognition.start();
  } catch (error) {
    state.active = false;
    updateRecognitionControls();
    setPhase("idle");
    els.support.textContent =
      "Recognition could not start. Check browser support and try again.";
    addMessage(
      "system",
      `Could not start speech recognition: ${error.message}`,
    );
  }
}

function finishRecognitionRun() {
  state.recognitionRunning = false;
  const retryWithoutHints = state.phraseHintFallbackPending;
  if (retryWithoutHints) {
    state.phraseHintFallbackPending = false;
    state.recognition = null;
    setupRecognition();
  }
  if (state.clearRequested) {
    state.clearRequested = false;
    updateRecognitionControls();
    setPhase("idle");
    return;
  }
  commitCurrentResults();
  if (state.stopRequested) {
    finishCapture();
    return;
  }
  if (state.pauseRequested) {
    state.pauseRequested = false;
    updateRecognitionControls();
    setPhase("idle");
    if (state.resumeAfterPause) {
      state.resumeAfterPause = false;
      startListening();
    }
    return;
  }
  if (state.recognitionError) {
    updateRecognitionControls();
    setPhase("idle");
    return;
  }
  if (!state.active) {
    updateRecognitionControls();
    setPhase("idle");
    return;
  }
  if (retryWithoutHints) {
    if (!state.recognition) {
      state.active = false;
      updateRecognitionControls();
      setPhase("idle");
      addMessage(
        "system",
        "Speech recognition could not restart without phrase hints. Type your message instead.",
      );
      return;
    }
    state.restartTimer = window.setTimeout(() => {
      state.restartTimer = null;
      startRecognitionRun();
    }, 300);
    return;
  }
  if (state.restartAttempts >= MAX_RESTARTS) {
    state.active = false;
    updateRecognitionControls();
    setPhase("idle");
    addMessage(
      "system",
      "Speech recognition stopped unexpectedly. Your finalized words are kept; press Start Listening to continue.",
    );
    return;
  }
  state.restartAttempts += 1;
  state.restartTimer = window.setTimeout(() => {
    state.restartTimer = null;
    startRecognitionRun();
  }, 300);
}

function setupRecognition() {
  if (!supportsSpeechInput || state.recognition) return;
  try {
    const recognition = new SpeechRecognitionAPI();
    recognition.lang = els.language.value;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 3;
    if (
      !state.phraseHintsDisabled &&
      "phrases" in recognition &&
      typeof window.SpeechRecognitionPhrase === "function"
    ) {
      try {
        recognition.phrases = SPEECH_HINTS.map(
          (phrase) => new window.SpeechRecognitionPhrase(phrase, 5),
        );
      } catch (error) {
        console.info(
          "Speech phrase hints are unsupported in this browser:",
          error,
        );
      }
    }

    recognition.onstart = () => {
      state.recognitionRunning = true;
      setPhase("listening");
      setStage("stage-listen");
      els.support.textContent = `Listening (${recognition.lang}). Browser speech support varies.`;
      updateRecognitionControls();
    };
    recognition.onresult = (event) => {
      for (
        let index = event.resultIndex;
        index < event.results.length;
        index += 1
      ) {
        const result = event.results[index];
        const text = result[0]?.transcript?.trim();
        if (!text) continue;
        const previous = state.currentResults.get(index);
        if (result.isFinal) {
          state.currentResults.set(index, { text, isFinal: true });
        } else if (!previous?.isFinal) {
          state.currentResults.set(index, { text, isFinal: false });
        }
      }
      renderSpeechDraft();
    };
    recognition.onerror = (event) => {
      if (
        event.error === "aborted" &&
        (state.stopRequested || state.pauseRequested || state.clearRequested)
      )
        return;
      if (
        event.error === "phrases-not-supported" &&
        !state.phraseHintsDisabled
      ) {
        state.phraseHintsDisabled = true;
        state.recognitionError = null;
        const recognitionInProgress =
          state.active ||
          state.recognitionRunning ||
          state.stopRequested ||
          state.pauseRequested;
        state.phraseHintFallbackPending = recognitionInProgress;
        els.support.textContent = recognitionInProgress
          ? "Phrase hints are unsupported here; retrying without them."
          : "Phrase hints are unsupported here. Recognition will continue without them.";
        addSpeechNoticeOnce(
          "phrase-hints-unsupported",
          "This browser does not support speech phrase hints. Continuing without them.",
        );
        if (!recognitionInProgress) {
          state.recognition = null;
          setupRecognition();
          updateRecognitionControls();
        }
        return;
      }
      handleRecognitionError(event.error);
    };
    recognition.onend = finishRecognitionRun;
    state.recognition = recognition;
  } catch (error) {
    els.support.textContent =
      "Speech recognition could not be initialized. Type your message instead.";
    console.warn("Could not initialize browser speech recognition:", error);
  }
}

function startListening() {
  if (!supportsSpeechInput || !state.recognition) {
    addMessage(
      "system",
      "Speech recognition is not available in this browser. Brave support is not guaranteed; type your message instead.",
    );
    els.message.focus();
    return;
  }
  if (state.active || state.recognitionRunning || state.sending) return;
  setupRecognition();
  state.active = true;
  state.stopRequested = false;
  state.pauseRequested = false;
  state.resumeAfterPause = false;
  state.clearRequested = false;
  state.recognitionError = null;
  state.restartAttempts = 0;
  if (state.restartTimer) window.clearTimeout(state.restartTimer);
  state.restartTimer = null;
  updateRecognitionControls();
  els.support.textContent = "Starting browser speech recognition…";
  startRecognitionRun();
}

function stopListening() {
  if (!state.active && !state.recognitionRunning) {
    commitCurrentResults();
    finishCapture();
    return;
  }
  state.stopRequested = true;
  state.active = false;
  if (state.restartTimer) window.clearTimeout(state.restartTimer);
  state.restartTimer = null;
  updateRecognitionControls();
  if (state.recognitionRunning) {
    try {
      state.recognition.stop();
    } catch (error) {
      addMessage(
        "system",
        `Could not stop speech recognition cleanly: ${error.message}`,
      );
      state.recognitionRunning = false;
      commitCurrentResults();
      finishCapture();
    }
  } else {
    commitCurrentResults();
    finishCapture();
  }
}

function stopConversation() {
  state.active = false;
  state.stopRequested = false;
  state.pauseRequested = true;
  if (state.restartTimer) window.clearTimeout(state.restartTimer);
  state.restartTimer = null;
  if (state.recognitionRunning) {
    try {
      state.recognition.stop();
    } catch (error) {
      addMessage(
        "system",
        `Could not stop speech recognition cleanly: ${error.message}`,
      );
      state.recognitionRunning = false;
      commitCurrentResults();
      state.pauseRequested = false;
    }
  } else {
    commitCurrentResults();
    state.pauseRequested = false;
  }
  if (supportsSpeechOutput) window.speechSynthesis.cancel();
  updateRecognitionControls();
  setPhase("idle");
}

function abortRecognitionAndDiscard() {
  state.active = false;
  state.stopRequested = false;
  state.pauseRequested = false;
  state.resumeAfterPause = false;
  state.clearRequested = state.recognitionRunning;
  if (state.restartTimer) window.clearTimeout(state.restartTimer);
  state.restartTimer = null;
  if (state.recognitionRunning) {
    try {
      state.recognition.abort();
    } catch (error) {
      addMessage(
        "system",
        `Could not clear the active recognition session: ${error.message}`,
      );
      state.clearRequested = false;
      state.recognitionRunning = false;
    }
  }
  state.finalTranscript = "";
  state.interimTranscript = "";
  state.currentResults.clear();
  renderSpeechDraft();
  updateRecognitionControls();
  setPhase("idle");
}

async function loadHealth() {
  try {
    const health = await api("/api/health");
    els.connection.textContent =
      health.status === "ok" ? "API connected" : "Database unavailable";
    els.connection.className =
      health.status === "ok" ? "chip is-ok" : "chip is-bad";
    if (health.demo_mode) {
      els.aiMode.textContent = "Demo mode";
      els.aiMode.className = "chip is-warn";
      els.banner.hidden = false;
      els.banner.textContent = health.config_issue
        ? `${health.config_issue} Lead scoring and saving still run on this computer. Demo replies are not live Gemini output.`
        : "Demo mode is on. Replies are scripted from the local knowledge file.";
    } else {
      els.aiMode.textContent = `Gemini: ${health.model}`;
      els.aiMode.className = "chip is-ok";
      els.banner.hidden = true;
      els.banner.textContent = "";
    }
  } catch (error) {
    els.connection.textContent = "Backend offline";
    els.connection.className = "chip is-bad";
    els.aiMode.textContent = "Unavailable";
    els.banner.hidden = false;
    els.banner.textContent = error.message || "The backend is not reachable.";
  }
}

async function loadLeads() {
  const data = await api("/api/leads");
  renderLeads(data);
}

async function saveLead(event) {
  event.preventDefault();
  clearError();
  const fields = currentLeadFields();
  if (
    !fields.customer_name ||
    !fields.company_name ||
    fields.vehicle_count === null ||
    Number.isNaN(fields.vehicle_count)
  ) {
    showError(
      "Customer name, company name, and vehicle count are required before a lead can be saved.",
    );
    return;
  }
  if (fields.email && !els.email.checkValidity()) {
    showError("Enter a valid email address or leave it blank.");
    return;
  }
  els.save.disabled = true;
  els.save.textContent = "Saving...";
  setStage("stage-save");
  const transcript = transcriptText();
  let summary = null;
  try {
    if (transcript) {
      try {
        summary = await api("/api/summarize", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            transcript,
            customer_name: fields.customer_name,
            company_name: fields.company_name,
            email: fields.email || null,
            vehicle_count: fields.vehicle_count,
            business_problem: fields.business_problem,
            interested_in_demo: fields.interested_in_demo,
          }),
        });
        renderSummary(
          summary,
          summary.mode === "gemini"
            ? "Summary source: Gemini"
            : "Summary source: local fallback",
        );
        if (summary.lead_score !== null && summary.lead_score !== undefined) {
          renderScore({
            lead_score: summary.lead_score,
            qualification_status: summary.qualification_status,
            recommended_next_action: summary.next_action,
            score_breakdown: summary.score_breakdown,
          });
        }
      } catch (summaryError) {
        addMessage(
          "system",
          `${summaryError.message} The lead will still be saved with a local summary.`,
        );
      }
    }
    const saved = await api("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_name: fields.customer_name,
        company_name: fields.company_name,
        email: fields.email || null,
        vehicle_count: fields.vehicle_count,
        business_problem: fields.business_problem,
        interested_in_demo: fields.interested_in_demo === true,
        call_summary: summary ? summary.summary : null,
      }),
    });
    renderScore(saved);
    if (!summary) {
      renderSummary(
        {
          customer_requirements: saved.business_problem || "Not stated",
          pain_points: saved.business_problem || "Not stated",
          lead_score: saved.lead_score,
          qualification_status: saved.qualification_status,
          demo_interest: saved.interested_in_demo
            ? "Demo requested"
            : "No demo requested",
          summary: saved.call_summary,
          next_action: saved.next_action,
        },
        "Summary source: local fallback",
      );
      els.summarySize.textContent = `${saved.vehicle_count} vehicles`;
    }
    addMessage(
      "system",
      `Lead #${saved.id} saved for ${saved.company_name}. Score ${saved.lead_score}, ${saved.qualification_status}.`,
    );
    await loadLeads();
    persistSession();
  } catch (error) {
    showError(error.message || "The lead could not be saved.");
  } finally {
    els.save.disabled = false;
    els.save.textContent = "Save lead and summarize";
  }
}

function resetConversation() {
  abortRecognitionAndDiscard();
  state.conversationId = crypto.randomUUID().replace(/-/g, "");
  state.history = [];
  state.finalTranscript = "";
  state.interimTranscript = "";
  state.manual = {};
  state.lastSummary = null;
  els.transcript.replaceChildren();
  addMessage(
    "system",
    "New conversation started. Earlier chat was cleared in this browser. Saved leads stay in the database.",
  );
  els.leadForm.reset();
  els.demoFlag.hidden = true;
  els.score.textContent = "—";
  els.status.textContent = "Not scored";
  els.status.className = "status-pill";
  els.action.textContent =
    "Score is calculated on the server when the lead is saved.";
  els.breakdown.hidden = true;
  clearError();
  [
    "summary-requirements",
    "summary-pain",
    "summary-size",
    "summary-score",
    "summary-demo",
    "summary-text",
    "summary-action",
  ].forEach((id) => {
    document.getElementById(id).textContent =
      id === "summary-requirements" ? "No summary yet." : "—";
  });
  els.summaryMode.textContent = "";
  sessionStorage.removeItem(STORAGE_KEY);
  persistSession();
}

Object.entries(fieldMap).forEach(([key, element]) => {
  element.addEventListener("input", () => {
    state.manual[key] = true;
    if (key === "interested_in_demo")
      els.demoFlag.hidden = els.demo.value !== "yes";
    persistSession();
  });
  element.addEventListener("change", () => {
    state.manual[key] = true;
    els.demoFlag.hidden = els.demo.value !== "yes";
    persistSession();
  });
});

els.start.addEventListener("click", startListening);
els.mic.addEventListener("click", () => {
  if (state.active) stopListening();
  else startListening();
});
els.stop.addEventListener("click", stopListening);
els.language.addEventListener("change", () => {
  if (state.recognition) state.recognition.lang = els.language.value;
});
els.clearTranscript.addEventListener("click", () => {
  abortRecognitionAndDiscard();
  state.conversationId = crypto.randomUUID().replace(/-/g, "");
  state.history = [];
  els.transcript.replaceChildren();
  els.support.textContent = supportsSpeechInput
    ? `Transcript cleared. Listening language: ${els.language.value}.`
    : "Speech recognition is not supported here. Type your message instead.";
  sessionStorage.removeItem(STORAGE_KEY);
  persistSession();
});
els.textForm.addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.active) stopConversation();
  sendMessage(els.message.value);
});
els.leadForm.addEventListener("submit", saveLead);
els.refresh.addEventListener("click", () => {
  loadLeads().catch((error) => addMessage("system", error.message));
});
els.newConversation.addEventListener("click", resetConversation);
els.readSummary.addEventListener("click", () => {
  const text = els.summaryText.textContent;
  if (!text || text === "—") return;
  if (!supportsSpeechOutput) {
    addMessage("system", "This browser cannot read the summary aloud.");
    return;
  }
  const wasActive = state.active;
  state.resumeAfterPause = wasActive;
  stopConversation();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.onstart = () => setPhase("speaking");
  utterance.onend = () => {
    setPhase("idle");
    if (wasActive && !state.recognitionRunning) {
      state.resumeAfterPause = false;
      startListening();
    }
  };
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
});

els.support.textContent = supportsSpeechInput
  ? "Browser speech recognition varies by browser; Brave support is not guaranteed."
  : "Speech recognition is not supported here. Type your message instead.";
setupRecognition();
restoreSession();
if (!state.conversationId) ensureConversation();
setPhase("idle");
updateRecognitionControls();
loadHealth();
loadLeads().catch((error) => {
  els.leadsCount.textContent = error.message;
});
