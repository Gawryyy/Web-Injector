const statusEl = document.querySelector('#status');

function setStatus(message, type = '') {
    statusEl.textContent = message;
    statusEl.className = `status ${type}`.trim();
}

async function post(url, body = {}) {
    const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Request failed');
    return data;
}

document.querySelectorAll('.tab').forEach((button) => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((tab) => tab.classList.remove('active'));
        document.querySelectorAll('.tab-page').forEach((page) => page.classList.remove('active'));
        button.classList.add('active');
        document.querySelector(`[data-page="${button.dataset.tab}"]`).classList.add('active');
    });
});

document.querySelectorAll('[data-add-coins]').forEach((button) => {
    button.addEventListener('click', async () => {
        try {
            await post('/api/coins/add', { amount: Number(button.dataset.addCoins) });
            setStatus(`Added ${button.dataset.addCoins} coins.`, 'ok');
        } catch (error) { setStatus(error.message, 'error'); }
    });
});

document.querySelector('#coins-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        const amount = Number(document.querySelector('#coins-input').value);
        await post('/api/coins/set', { amount });
        setStatus(`Coins set to ${amount}.`, 'ok');
    } catch (error) { setStatus(error.message, 'error'); }
});

document.querySelector('#damage').addEventListener('click', async () => {
    try { await post('/api/health/change', { amount: -10 }); setStatus('Damaged player by 10 HP.', 'ok'); }
    catch (error) { setStatus(error.message, 'error'); }
});

document.querySelector('#heal').addEventListener('click', async () => {
    try { await post('/api/health/change', { amount: 10 }); setStatus('Healed player by 10 HP.', 'ok'); }
    catch (error) { setStatus(error.message, 'error'); }
});

document.querySelector('#full-health').addEventListener('click', async () => {
    try { await post('/api/health/set', { amount: 100 }); setStatus('Health restored.', 'ok'); }
    catch (error) { setStatus(error.message, 'error'); }
});

document.querySelector('#player-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    try {
        const name = document.querySelector('#name-input').value;
        const level = Number(document.querySelector('#level-input').value);
        await post('/api/name/set', { name });
        await post('/api/level/set', { level });
        setStatus('Player settings updated.', 'ok');
    } catch (error) { setStatus(error.message, 'error'); }
});

document.querySelector('#reset').addEventListener('click', async () => {
    try { await post('/api/reset'); setStatus('Game reset.', 'ok'); }
    catch (error) { setStatus(error.message, 'error'); }
});

const samples = {
    css: `#playground {\n    box-shadow: inset 0 0 80px rgba(255, 79, 163, .18);\n}`,
    html: `<div style="padding:16px;border:1px solid #ff5da8;border-radius:14px;">Injected HTML works ✨</div>`,
    js: `document.querySelector('.game-object').textContent = 'Changed by injected JavaScript';`,
};

const kindSelect = document.querySelector('#inject-kind');
const codeArea = document.querySelector('#inject-code');
kindSelect.addEventListener('change', () => {
    codeArea.value = samples[kindSelect.value];
});

document.querySelector('#inject').addEventListener('click', async () => {
    try {
        await post('/api/inject', { kind: kindSelect.value, code: codeArea.value });
        setStatus(`${kindSelect.value.toUpperCase()} sent to the local test game.`, 'ok');
    } catch (error) { setStatus(error.message, 'error'); }
});
