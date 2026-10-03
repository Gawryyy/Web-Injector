const ui = {
    name: document.querySelector('#player-name'),
    coins: document.querySelector('#coins'),
    level: document.querySelector('#level'),
    healthText: document.querySelector('#health-text'),
    healthBar: document.querySelector('#health-bar'),
    injectedHtml: document.querySelector('#injected-html'),
};

const injectedStyle = document.createElement('style');
injectedStyle.id = 'web-injector-style';
document.head.appendChild(injectedStyle);

function render(state) {
    const player = state.player;
    ui.name.textContent = player.name;
    ui.coins.textContent = Number(player.coins).toLocaleString();
    ui.level.textContent = player.level;
    ui.healthText.textContent = `${player.health} / ${player.max_health}`;
    const percentage = player.max_health > 0 ? (player.health / player.max_health) * 100 : 0;
    ui.healthBar.style.width = `${Math.max(0, Math.min(100, percentage))}%`;
}

async function loadState() {
    const response = await fetch('/api/state');
    if (!response.ok) throw new Error('Could not load state');
    render(await response.json());
}

function applyInjection(kind, code) {
    if (kind === 'html') {
        ui.injectedHtml.insertAdjacentHTML('beforeend', code);
        return;
    }

    if (kind === 'css') {
        injectedStyle.textContent += `\n${code}\n`;
        return;
    }

    if (kind === 'js') {
        const run = new Function(code);
        run();
    }
}

function resetInjections() {
    injectedStyle.textContent = '';
    ui.injectedHtml.innerHTML = '';
}

const events = new EventSource('/events');
events.onmessage = (event) => {
    const payload = JSON.parse(event.data);

    if (payload.type === 'state') render(payload.state);
    if (payload.type === 'inject') applyInjection(payload.kind, payload.code);
    if (payload.type === 'reset-injections') resetInjections();
};

events.onerror = () => {
    console.warn('Live connection interrupted. The browser will retry automatically.');
};

loadState().catch(console.error);
