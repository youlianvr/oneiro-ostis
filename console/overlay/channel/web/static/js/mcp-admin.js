/* CowAgent host operations and MCP administration. */
(function () {
    'use strict';

    const state = { snapshot: null, dirty: false, loading: false, busy: false, timer: null };
    const id = (suffix) => document.getElementById('mcp-' + suffix);
    const text = (key) => (typeof window.t === 'function' ? window.t('mcp_' + key) : key);

    function html(value) {
        const node = document.createElement('span');
        node.textContent = String(value == null ? '' : value);
        return node.innerHTML;
    }

    function statusLabel(status) {
        const labels = {
            ready: text('status_ready'), pending: text('status_pending'), failed: text('status_failed'),
            needs_auth: text('status_needs_auth'), configured: text('status_configured'),
            disabled: text('status_disabled'), approval_required: text('status_approval'),
            pending_apply: text('status_pending_apply'),
        };
        return labels[status] || status || text('status_unknown');
    }

    function setMessage(message, isError) {
        const el = id('status');
        if (!el) return;
        el.textContent = message || '';
        el.className = 'text-xs ' + (isError ? 'text-red-500' : 'text-emerald-600 dark:text-emerald-400');
    }

    async function request(url, options) {
        const response = await fetch(url, options || {});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.status === 'error') {
            throw new Error(payload.message || `HTTP ${response.status}`);
        }
        return payload;
    }

    function renderHost(host) {
        const target = id('host-status');
        if (!target) return;
        target.innerHTML = `
            <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div class="mcp-host-stat"><span>${html(text('host_version'))}</span><strong>${html(host.version)}</strong></div>
                <div class="mcp-host-stat"><span>${html(text('host_runtime'))}</span><strong>${html(host.python)} · ${html(host.platform)}</strong></div>
                <div class="mcp-host-stat"><span>${html(text('host_network'))}</span><strong>${html(host.web_host)}:${html(host.web_port)}</strong></div>
                <div class="mcp-host-stat"><span>${html(text('host_access'))}</span><strong>${html(host.password_protected ? text('host_protected') : text('host_unprotected'))}</strong></div>
            </div>
            <div class="mt-4 flex flex-wrap gap-2">${(host.agents || []).map(agent => `
                <span class="mcp-agent-pill ${agent.enabled ? '' : 'opacity-50'}">
                    <i class="fas fa-circle text-[7px] ${agent.enabled ? 'text-emerald-500' : 'text-slate-400'}"></i>
                    ${html(agent.name)} <small>${html(agent.id)} · ${html(agent.mcp_servers)} MCP</small>
                </span>`).join('')}
            </div>`;
    }

    function renderServers(snapshot) {
        const target = id('server-list');
        if (!target) return;
        if (!snapshot.servers || !snapshot.servers.length) {
            target.innerHTML = `<div class="mcp-empty"><i class="fas fa-plug-circle-xmark"></i><p>${html(text('empty'))}</p></div>`;
            return;
        }
        target.innerHTML = snapshot.servers.map(server => `
            <article class="mcp-server-card">
                <div class="mcp-server-main">
                    <div class="min-w-0">
                        <h4>${html(server.name)}</h4>
                        <p>${html(server.transport)} · ${html(statusLabel(server.status))} · ${html(server.tool_count)} ${html(text('tools'))}</p>
                    </div>
                    <button type="button" class="mcp-link-btn" data-edit-server="${html(server.name)}"><i class="fas fa-pen"></i>${html(text('edit'))}</button>
                </div>
                ${server.tools && server.tools.length ? `<div class="mcp-tools-list">${server.tools.map(tool => `<span>${html(tool)}</span>`).join('')}</div>` : ''}
                ${server.status === 'approval_required' ? `<div class="mcp-warning-note"><i class="fas fa-shield-halved"></i>${html(text('approval_note'))}</div>` : ''}
            </article>`).join('');
        target.querySelectorAll('[data-edit-server]').forEach(button => button.addEventListener('click', () => {
            const name = button.dataset.editServer;
            try {
                const config = JSON.parse(id('config').value || '{}').mcpServers || {};
                if (config[name]) {
                    id('config').value = JSON.stringify({ mcpServers: { [name]: config[name] } }, null, 2);
                    state.dirty = true;
                    updateDirty();
                    id('config').focus();
                }
            } catch (_) { /* The editor's validation reports malformed drafts. */ }
        }));
    }

    function renderSecrets(snapshot) {
        const target = id('secrets');
        if (!target) return;
        const variables = snapshot.environment || [];
        target.innerHTML = variables.length ? variables.map(variable => `
            <div class="mcp-secret-row"><code>${html(variable.name)}</code>
                <span class="${variable.configured ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}">${html(variable.configured ? text('secret_set') : text('secret_missing'))}</span>
            </div>`).join('') : `<p class="text-xs text-slate-400">${html(text('secrets_empty'))}</p>`;
    }

    function renderArchive(snapshot) {
        const target = id('archive');
        if (!target) return;
        const archived = snapshot.archived || [];
        target.innerHTML = archived.length ? `
            <details class="mcp-archive">
                <summary>${html(text('archived'))} · ${archived.length}</summary>
                <div class="mt-2 space-y-2">${archived.map(server => `
                    <div class="mcp-archive-row"><span><strong>${html(server.name)}</strong><small>${html(server.transport)} · ${html(server.archived_at)}</small></span>
                        <button type="button" class="mcp-link-btn" data-restore-server="${html(server.name)}">${html(text('restore'))}</button></div>`).join('')}
                </div>
            </details>` : '';
        target.querySelectorAll('[data-restore-server]').forEach(button => button.addEventListener('click', async () => {
            if (!window.confirm(text('restore_confirm').replace('{name}', button.dataset.restoreServer))) return;
            try {
                await request('/api/mcp/restore', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ agent_id: selectedAgent(), name: button.dataset.restoreServer }) });
                await refresh();
                setMessage(text('restored'), false);
            } catch (error) { setMessage(error.message, true); }
        }));
    }

    function render(snapshot) {
        state.snapshot = snapshot;
        const select = id('agent');
        if (select && !select.dataset.ready) {
            select.innerHTML = (snapshot.agents || []).map(agent => `<option value="${html(agent.id)}">${html(agent.name)}${agent.id === snapshot.default_agent_id ? ' · default' : ''}${agent.enabled ? '' : ' · disabled'}</option>`).join('');
            select.value = snapshot.agent.id;
            select.dataset.ready = '1';
        }
        renderServers(snapshot);
        renderSecrets(snapshot);
        renderArchive(snapshot);
    }

    function selectedAgent() {
        return id('agent')?.value || '';
    }

    function updateDirty() {
        const save = id('save');
        const apply = id('apply');
        if (save) save.disabled = state.busy || !state.dirty;
        if (apply) apply.disabled = state.busy || state.dirty;
        if (id('dirty-hint')) id('dirty-hint').classList.toggle('hidden', !state.dirty);
    }

    async function refresh() {
        if (state.loading) return;
        state.loading = true;
        try {
            const [host, snapshot] = await Promise.all([
                request('/api/host/status'),
                request(`/api/mcp?agent_id=${encodeURIComponent(selectedAgent())}`),
            ]);
            renderHost(host);
            render(snapshot);
            if (!state.dirty) id('config').value = snapshot.config;
            updateDirty();
        } catch (error) {
            setMessage(error.message, true);
        } finally { state.loading = false; }
    }

    async function withBusy(action) {
        if (state.busy) return;
        state.busy = true;
        updateDirty();
        try { await action(); }
        catch (error) { setMessage(error.message, true); }
        finally { state.busy = false; updateDirty(); }
    }

    async function saveConfig() {
        await withBusy(async () => {
            const payload = JSON.parse(id('config').value || '{}');
            const result = await request('/api/mcp', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: selectedAgent(), config: payload }),
            });
            state.dirty = false;
            await refresh();
            setMessage(result.message + (result.requires_apply ? ' · ' + text('needs_apply') : ''), false);
        });
    }

    async function applyConfig() {
        await withBusy(async () => {
            const payload = JSON.parse(id('config').value || '{}');
            const servers = payload.mcpServers || {};
            const local = Object.entries(servers).filter(([, config]) => (config.type || (config.url ? 'sse' : 'stdio')) === 'stdio');
            let confirmed = false;
            if (local.length) {
                const commands = local.map(([name, config]) => `${name}: ${config.command || ''} ${(config.args || []).join(' ')}`.trim()).join('\n');
                confirmed = window.confirm(text('confirm_local_start').replace('{commands}', commands));
                if (!confirmed) return;
            }
            const result = await request('/api/mcp/apply', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: selectedAgent(), confirmed }),
            });
            setMessage(result.message, false);
            setTimeout(refresh, 900);
        });
    }

    async function testDraft() {
        await withBusy(async () => {
            const payload = JSON.parse(id('config').value || '{}');
            const servers = payload.mcpServers || {};
            const names = Object.keys(servers);
            if (!names.length) throw new Error(text('choose_server'));
            const name = names.length === 1 ? names[0] : window.prompt(text('choose_server_prompt'), names[0]);
            if (!name || !servers[name]) return;
            const config = servers[name];
            const transport = config.type || (config.url ? 'sse' : 'stdio');
            let confirmed = false;
            if (transport === 'stdio') {
                confirmed = window.confirm(text('confirm_test_local').replace('{name}', name).replace('{command}', `${config.command || ''} ${(config.args || []).join(' ')}`));
                if (!confirmed) return;
            }
            const result = await request('/api/mcp/test', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: selectedAgent(), name, config, confirmed }),
            });
            const tools = (result.tools || []).map(tool => tool.name).join(', ');
            setMessage(`${text('test_success')}: ${result.tool_count} ${text('tools')}${tools ? ' · ' + tools : ''}`, false);
        });
    }

    async function saveSecret() {
        await withBusy(async () => {
            const name = id('secret-name').value.trim();
            const value = id('secret-value').value;
            if (!name) throw new Error(text('secret_name_required'));
            await request('/api/mcp/secrets', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent_id: selectedAgent(), name, value }),
            });
            id('secret-value').value = '';
            id('secret-value').type = 'password';
            id('show-secret').checked = false;
            await refresh();
            setMessage(text('secret_saved'), false);
        });
    }

    function newTemplate(type) {
        const templates = {
            stdio: { type: 'stdio', command: 'npx', args: ['-y', 'PACKAGE'], env: {}, cwd: '', timeout: 120, inherit_full_env: false },
            sse: { type: 'sse', url: 'https://example.com/sse', headers: {}, timeout: 120 },
            http: { type: 'streamable-http', url: 'https://example.com/mcp', headers: {}, timeout: 120, scope: '' },
        };
        const name = window.prompt(text('new_server_name'));
        if (!name) return;
        let payload;
        try { payload = JSON.parse(id('config').value || '{}'); }
        catch (_) { payload = { mcpServers: {} }; }
        payload.mcpServers = payload.mcpServers || {};
        if (payload.mcpServers[name] && !window.confirm(text('overwrite_server').replace('{name}', name))) return;
        payload.mcpServers[name] = templates[type] || templates.stdio;
        id('config').value = JSON.stringify(payload, null, 2);
        state.dirty = true;
        updateDirty();
        id('config').focus();
    }

    function bind() {
        id('refresh')?.addEventListener('click', refresh);
        id('save')?.addEventListener('click', saveConfig);
        id('apply')?.addEventListener('click', applyConfig);
        id('test')?.addEventListener('click', testDraft);
        id('add-stdio')?.addEventListener('click', () => newTemplate('stdio'));
        id('add-sse')?.addEventListener('click', () => newTemplate('sse'));
        id('add-http')?.addEventListener('click', () => newTemplate('http'));
        id('save-secret')?.addEventListener('click', saveSecret);
        id('show-secret')?.addEventListener('change', event => {
            id('secret-value').type = event.target.checked ? 'text' : 'password';
        });
        id('agent')?.addEventListener('change', async () => {
            state.dirty = false;
            id('config').value = '';
            id('agent').dataset.ready = '1';
            await refresh();
        });
        id('config')?.addEventListener('input', () => {
            state.dirty = true;
            updateDirty();
        });
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && window.currentView === 'mcp') refresh();
        });
        state.timer = setInterval(() => {
            if (window.currentView === 'mcp' && !state.dirty) refresh();
        }, 5000);
        document.addEventListener('DOMContentLoaded', () => {
            const observer = new MutationObserver(() => {
                const view = document.getElementById('view-mcp');
                if (view && view.classList.contains('active')) refresh();
            });
            const view = document.getElementById('view-mcp');
            if (view) observer.observe(view, { attributes: true, attributeFilter: ['class'] });
        });
    }

    window.refreshMcpAdminView = refresh;
    window.initMcpAdmin = bind;
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind, { once: true });
    else bind();
})();
