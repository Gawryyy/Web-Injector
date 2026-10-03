const appState = {
    type: "html",
    targets: [],
    selected: "test-game",
    pendingTarget: null
};

const payload = document.querySelector("#payload");
const message = document.querySelector("#message");
const injectButton = document.querySelector("#inject-button");
const editorLanguage = document.querySelector("#editor-language");
const targetStatus = document.querySelector("#target-status");
const targetLabel = document.querySelector("#target-label");
const targetSelect = document.querySelector("#target-select");
const flowTarget = document.querySelector("#flow-target");
const deleteTargetButton = document.querySelector("#delete-target");
const saveDialog = document.querySelector("#save-dialog");
const payloadName = document.querySelector("#payload-name");
const trustDialog = document.querySelector("#trust-dialog");
const trustHost = document.querySelector("#trust-host");
const trustConfirm = document.querySelector("#trust-confirm");

const presets = {
    badge: {
        type: "html",
        code: `<div id="injector-test-card" style="
position:fixed;
top:24px;
right:24px;
z-index:999999;
padding:16px 18px;
border-radius:16px;
background:rgba(12,14,24,.94);
border:1px solid #ff69b9;
box-shadow:0 0 35px rgba(255,105,185,.24);
color:white;
font-family:Inter,system-ui,sans-serif;">
  <b style="color:#ff91cf">INJECTION WORKS</b>
  <div style="margin-top:5px;color:#9da5b8;font-size:12px;">
    This HTML was added by Web Injector.
  </div>
</div>`
    },

    outline: {
        type: "css",
        code: `* {
    outline: 1px solid rgba(255, 105, 185, .12);
}

button, a, input, textarea, select {
    outline: 1px solid rgba(103, 196, 255, .35) !important;
}`
    },

    darken: {
        type: "css",
        code: `body::after {
    content: "";
    position: fixed;
    inset: 0;
    z-index: 999998;
    pointer-events: none;
    background: rgba(7, 9, 15, .18);
}`
    },

    console: {
        type: "js",
        code: `console.log("[Web Injector] JavaScript injection works.");
document.documentElement.dataset.webInjectorTest = "active";`
    },

    title: {
        type: "js",
        code: `document.title = "Injected • " + document.title;
console.log("[Web Injector] Page title changed.");`
    }
};

function setMessage(text, kind = "") {
    message.textContent = text;
    message.className = `message ${kind}`.trim();
}

async function jsonFetch(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {})
        },
        ...options
    });

    let data = {};

    try {
        data = await response.json();
    } catch (_) {}

    if (!response.ok || data.ok === false) {
        throw new Error(data.error || `Request failed (${response.status})`);
    }

    return data;
}

function setType(type) {
    appState.type = type;

    document.querySelectorAll(".tab").forEach(tab => {
        tab.classList.toggle("active", tab.dataset.type === type);
    });

    const names = {
        html: "HTML",
        css: "CSS",
        js: "JAVASCRIPT"
    };

    editorLanguage.textContent = names[type];
    injectButton.textContent = `Inject ${type === "js" ? "JavaScript" : names[type]}`;

    payload.placeholder = {
        html: "Paste HTML here and press Inject…",
        css: "Paste CSS here and press Inject…",
        js: "Paste JavaScript here and press Inject…"
    }[type];
}

function selectedTargetObject() {
    return appState.targets.find(target => target.id === appState.selected) || null;
}

function renderTargets() {
    targetSelect.innerHTML = "";

    for (const target of appState.targets) {
        const option = document.createElement("option");
        option.value = target.id;
        option.textContent = target.kind === "builtin"
            ? `${target.name} • built in`
            : `${target.name} • ${target.url}`;

        option.selected = target.id === appState.selected;
        targetSelect.appendChild(option);
    }

    const current = selectedTargetObject();

    targetLabel.textContent = current?.name || "No target";
    flowTarget.textContent = current?.kind === "builtin"
        ? current.name
        : (current?.url || "No target");

    deleteTargetButton.disabled = !current || Boolean(current.protected);
}

async function loadTargets() {
    try {
        const data = await jsonFetch("/api/targets");

        appState.targets = Array.isArray(data.targets) ? data.targets : [];
        appState.selected = data.selected || "test-game";

        renderTargets();
        await refreshStatus();
    } catch (error) {
        setMessage(error.message, "bad");
    }
}

async function chooseTarget(targetId = targetSelect.value) {
    try {
        const data = await jsonFetch("/api/targets/select", {
            method: "POST",
            body: JSON.stringify({ id: targetId })
        });

        appState.selected = data.selected;
        renderTargets();
        await refreshStatus();
        setMessage("Target selected. Open the proxied target tab.", "good");
    } catch (error) {
        setMessage(error.message, "bad");
    }
}

async function submitTarget(name, url, trustPublic = false) {
    const response = await fetch("/api/targets/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            name,
            url,
            trust_public: trustPublic
        })
    });

    let data = {};
    try {
        data = await response.json();
    } catch (_) {}

    if (response.status === 409 && data.requires_trust) {
        return {
            requiresTrust: true,
            host: data.host,
            error: data.error
        };
    }

    if (!response.ok || data.ok === false) {
        throw new Error(data.error || `Request failed (${response.status})`);
    }

    return data;
}

async function addTarget() {
    const nameInput = document.querySelector("#new-target-name");
    const urlInput = document.querySelector("#new-target-url");
    const name = nameInput.value.trim();
    const url = urlInput.value.trim();

    try {
        const data = await submitTarget(name, url, false);

        if (data.requiresTrust) {
            appState.pendingTarget = { name, url };
            trustHost.textContent = data.host;
            trustConfirm.checked = false;
            trustDialog.showModal();
            setMessage(data.error);
            return;
        }

        nameInput.value = "";
        urlInput.value = "";

        await loadTargets();

        if (data.selected) {
            appState.selected = data.selected;
            renderTargets();
        }

        setMessage(`Added ${data.target.name}.`, "good");
    } catch (error) {
        setMessage(error.message, "bad");
    }
}

async function deleteTarget() {
    const current = appState.targets.find(target => target.id === targetSelect.value);

    if (!current || current.protected) {
        setMessage("The built-in Test Game cannot be deleted.", "bad");
        return;
    }

    if (!confirm(`Delete "${current.name}" from Web Injector?`)) {
        return;
    }

    try {
        await jsonFetch(`/api/targets/${encodeURIComponent(current.id)}`, {
            method: "DELETE"
        });

        await loadTargets();
        setMessage("Target removed.", "good");
    } catch (error) {
        setMessage(error.message, "bad");
    }
}

async function refreshStatus() {
    try {
        const response = await fetch("/api/target/status", { cache: "no-store" });
        const data = await response.json();

        if (!response.ok || data.ok === false) {
            throw new Error("Target offline");
        }

        if (data.target) {
            const found = appState.targets.find(target => target.id === data.target.id);

            if (found) {
                appState.selected = found.id;
                renderTargets();
            }
        }

        targetStatus.className = "status online";
        targetStatus.querySelector("span").textContent = "Connected";
    } catch (_) {
        targetStatus.className = "status offline";
        targetStatus.querySelector("span").textContent = "Offline";
    }
}

async function inject() {
    const code = payload.value;

    if (!code.trim()) {
        setMessage("Paste something into the editor first.", "bad");
        return;
    }

    injectButton.disabled = true;
    injectButton.textContent = "Injecting…";
    setMessage("Sending payload to the selected target…");

    try {
        const data = await jsonFetch("/api/target/inject", {
            method: "POST",
            body: JSON.stringify({
                type: appState.type,
                code
            })
        });

        setMessage(
            `${appState.type.toUpperCase()} injected • revision ${data.revision}`,
            "good"
        );
    } catch (error) {
        setMessage(error.message, "bad");
    } finally {
        injectButton.disabled = false;
        setType(appState.type);
    }
}

function savedPayloads() {
    try {
        const parsed = JSON.parse(localStorage.getItem("web_injector_payloads") || "[]");
        return Array.isArray(parsed) ? parsed : [];
    } catch (_) {
        return [];
    }
}

function writeSavedPayloads(items) {
    localStorage.setItem("web_injector_payloads", JSON.stringify(items));
}

function renderSavedPayloads() {
    const wrap = document.querySelector("#saved-payloads");
    const items = savedPayloads();

    wrap.innerHTML = "";

    if (!items.length) {
        const empty = document.createElement("div");
        empty.className = "saved-empty";
        empty.textContent = "Save an HTML, CSS or JavaScript payload and it will appear here.";
        wrap.appendChild(empty);
        return;
    }

    items.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "saved-row";

        const load = document.createElement("button");
        load.className = "saved-load";
        load.innerHTML = `<b></b><small></small>`;
        load.querySelector("b").textContent = item.name;
        load.querySelector("small").textContent = item.type;
        load.addEventListener("click", () => {
            setType(item.type);
            payload.value = item.code;
            payload.focus();
            setMessage(`Loaded "${item.name}".`);
        });

        const remove = document.createElement("button");
        remove.className = "saved-delete";
        remove.textContent = "×";
        remove.title = `Delete ${item.name}`;
        remove.addEventListener("click", () => {
            const current = savedPayloads();
            current.splice(index, 1);
            writeSavedPayloads(current);
            renderSavedPayloads();
            setMessage("Saved payload removed.");
        });

        row.append(load, remove);
        wrap.appendChild(row);
    });
}

function saveCurrentPayload() {
    const name = payloadName.value.trim();
    const code = payload.value;

    if (!name) {
        setMessage("Give the payload a name.", "bad");
        return false;
    }

    if (!code.trim()) {
        setMessage("There is nothing in the editor to save.", "bad");
        return false;
    }

    const items = savedPayloads();

    items.unshift({
        name: name.slice(0, 60),
        type: appState.type,
        code
    });

    writeSavedPayloads(items.slice(0, 50));
    renderSavedPayloads();
    payloadName.value = "";
    setMessage(`Saved "${name}".`, "good");
    return true;
}

document.querySelector(".tabs").addEventListener("click", event => {
    const tab = event.target.closest("[data-type]");
    if (!tab) return;
    setType(tab.dataset.type);
});

document.querySelectorAll("[data-preset]").forEach(button => {
    button.addEventListener("click", () => {
        const preset = presets[button.dataset.preset];
        if (!preset) return;

        setType(preset.type);
        payload.value = preset.code;
        payload.focus();
        setMessage(`Loaded preset: ${button.textContent.trim()}`);
    });
});

document.querySelector("#select-target").addEventListener("click", () => {
    chooseTarget();
});

targetSelect.addEventListener("change", () => {
    const target = appState.targets.find(item => item.id === targetSelect.value);
    deleteTargetButton.disabled = !target || Boolean(target.protected);
});

document.querySelector("#add-target").addEventListener("click", addTarget);
deleteTargetButton.addEventListener("click", deleteTarget);

document.querySelector("#open-target").addEventListener("click", () => {
    window.open("/target/", "_blank", "noopener");
});

document.querySelector("#reload-target").addEventListener("click", async () => {
    try {
        await jsonFetch("/api/target/reset", {
            method: "POST",
            body: "{}"
        });

        setMessage("Reload signal sent to the proxied target.", "good");
    } catch (error) {
        setMessage(error.message, "bad");
    }
});

document.querySelector("#clear-editor").addEventListener("click", () => {
    payload.value = "";
    payload.focus();
    setMessage("Editor cleared.");
});

document.querySelector("#save-payload").addEventListener("click", () => {
    if (!payload.value.trim()) {
        setMessage("There is nothing in the editor to save.", "bad");
        return;
    }

    saveDialog.showModal();
    setTimeout(() => payloadName.focus(), 0);
});

document.querySelector("#save-form").addEventListener("submit", event => {
    const submitter = event.submitter;

    if (submitter?.value === "cancel") {
        return;
    }

    event.preventDefault();

    if (saveCurrentPayload()) {
        saveDialog.close();
    }
});

document.querySelector("#trust-form").addEventListener("submit", async event => {
    const submitter = event.submitter;

    if (submitter?.value === "cancel") {
        appState.pendingTarget = null;
        return;
    }

    event.preventDefault();

    if (!trustConfirm.checked) {
        setMessage("Confirm that you own/control the domain first.", "bad");
        return;
    }

    const pending = appState.pendingTarget;
    if (!pending) {
        trustDialog.close();
        return;
    }

    try {
        const data = await submitTarget(pending.name, pending.url, true);

        document.querySelector("#new-target-name").value = "";
        document.querySelector("#new-target-url").value = "";

        appState.pendingTarget = null;
        trustDialog.close();

        await loadTargets();

        if (data.selected) {
            appState.selected = data.selected;
            renderTargets();
        }

        setMessage(`Trusted and added ${data.target.name}.`, "good");
    } catch (error) {
        setMessage(error.message, "bad");
    }
});

injectButton.addEventListener("click", inject);

payload.addEventListener("keydown", event => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        event.preventDefault();
        inject();
    }

    if (event.key === "Tab") {
        event.preventDefault();

        const start = payload.selectionStart;
        const end = payload.selectionEnd;

        payload.setRangeText("    ", start, end, "end");
    }
});

setType("html");
renderSavedPayloads();
loadTargets();
setInterval(refreshStatus, 2500);