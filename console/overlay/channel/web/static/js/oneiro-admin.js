/* Oneiro's own settings: the file, the layers, and the page that edits them.
 *
 * The API belongs to Oneiro, not to this console: `python/config.py` owns the
 * settings file and `dashboard/server.py` exposes it at /api/settings. This
 * module asks and shows; it never keeps a second copy of a value, so what is
 * saved here is what the runtime reads. A field that was not touched is not
 * sent at all, and every row says which layer answered — a value from the
 * environment is not a preference the owner stored, and the page says so
 * instead of pretending it is.
 */
(function () {
    'use strict';

    // The settings API is Oneiro's own panel, served on this very origin: the
    // console proxies /oneiro/ to the panel process, so this is a path on the
    // address the page was loaded from - no host to guess, no port to hunt, no
    // CORS to allow. This module used to look for the panel on 8130, 8131 and
    // 8132 and remember the one that answered in localStorage; that seam
    // existed only while the panel had an address of its own.
    const API_BASE = '/oneiro';
    const SOURCE_KEYS = { file: 'source_file', env: 'source_env', default: 'source_default' };
    const state = { rows: [], loading: false, saving: false, draft: {} };

    const el = (suffix) => document.getElementById('oneiro-' + suffix);
    const text = (key) => (typeof window.t === 'function' ? window.t('oneiro_' + key) : key);

    function api() {
        return API_BASE;
    }

    function message(kind, body) {
        const host = el('banner');
        if (!host) return;
        host.textContent = '';
        if (!body) {
            host.className = 'hidden';
            return;
        }
        host.className = kind === 'error' ? 'oneiro-banner oneiro-banner-error'
            : kind === 'hint' ? 'oneiro-banner oneiro-banner-hint' : 'oneiro-banner';
        host.appendChild(document.createTextNode(body));
    }

    function tagged(tag, className, body) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (body != null) node.textContent = String(body);
        return node;
    }

    function field(row) {
        const id = 'oneiro-field-' + row.key.replace(/\./g, '-');
        const wrap = tagged('div', 'oneiro-field');

        const head = tagged('div', 'oneiro-field-head');
        const label = tagged('label', 'oneiro-field-label', row.label || row.key);
        label.setAttribute('for', id);
        head.appendChild(label);
        head.appendChild(tagged('span', 'oneiro-source oneiro-source-' + row.source,
            text(SOURCE_KEYS[row.source] || 'source_default')));
        wrap.appendChild(head);

        const input = document.createElement('input');
        input.id = id;
        input.className = 'mcp-input w-full';
        input.dataset.oneiroKey = row.key;
        input.spellcheck = false;
        if (row.secret) {
            input.type = 'password';
            input.autocomplete = 'new-password';
            input.placeholder = row.set ? text('secret_set') : '';
        } else {
            input.type = row.kind === 'int' ? 'number' : 'text';
            input.value = row.value == null ? '' : String(row.value);
            if (row.kind === 'path') input.className += ' font-mono';
        }
        input.addEventListener('input', () => {
            state.draft[row.key] = input.value;
        });
        wrap.appendChild(input);

        const actions = tagged('div', 'oneiro-field-foot');
        actions.appendChild(tagged('p', 'oneiro-help', row.help || ''));
        const env = tagged('code', 'oneiro-env', row.env);
        actions.appendChild(env);
        if (row.secret && row.stored) {
            const forget = tagged('button', 'oneiro-forget', text('forget_one'));
            forget.type = 'button';
            forget.addEventListener('click', () => forgetKeys([row.key]));
            actions.appendChild(forget);
        }
        wrap.appendChild(actions);
        return wrap;
    }

    function group(name, rows) {
        const section = tagged('section', 'mcp-panel');
        const heading = tagged('div', 'mcp-panel-heading');
        const block = tagged('div');
        block.appendChild(tagged('h3', '', name));
        heading.appendChild(block);
        section.appendChild(heading);
        const body = tagged('div', 'mt-4 space-y-4');
        rows.forEach((row) => body.appendChild(field(row)));
        section.appendChild(body);
        return section;
    }

    function render(payload) {
        state.rows = payload.settings || [];
        state.draft = {};
        const host = el('form');
        if (!host) return;
        host.textContent = '';

        const order = [];
        const byGroup = new Map();
        for (const row of state.rows) {
            if (!byGroup.has(row.group)) {
                byGroup.set(row.group, []);
                order.push(row.group);
            }
            byGroup.get(row.group).push(row);
        }
        for (const name of order) host.appendChild(group(name, byGroup.get(name)));

        const file = el('file');
        if (file) file.textContent = payload.path || '';
        const legacy = el('error');
        if (legacy) {
            legacy.textContent = payload.error || '';
            legacy.className = payload.error ? 'oneiro-banner oneiro-banner-error mt-3' : 'hidden';
        }
        message(payload.error ? 'error' : 'hint', payload.error ? text('file_broken') : '');
    }

    function collect() {
        const patch = {};
        for (const [key, value] of Object.entries(state.draft)) {
            const row = state.rows.find((r) => r.key === key);
            if (!row) continue;
            if (row.secret) {
                if (value !== '') patch[key] = value;   // empty leaves a stored key alone
                continue;
            }
            if (String(value) === String(row.value)) continue;   // untouched, so unsent
            patch[key] = value;
        }
        return patch;
    }

    async function request(url, options) {
        const response = await fetch(api() + url, options || {});
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || payload.status === 'error') {
            throw new Error(payload.message || ('HTTP ' + response.status));
        }
        return payload;
    }

    async function load() {
        if (state.loading) return;
        state.loading = true;
        const button = el('reload');
        if (button) button.disabled = true;
        message('hint', text('loading'));
        try {
            render(await request('/api/settings'));
            if (!state.rows.some((row) => row.changed)) {
                message('hint', text('nothing_changed'));
            } else {
                message('hint', '');
            }
        } catch (error) {
            // The panel is a separate process behind /oneiro/: when it is down
            // the proxy answers 502 and this says the page could not reach it,
            // instead of pretending the settings file itself is unreachable.
            message('error', text('unreachable') + ' ' + error.message);
            const host = el('form');
            if (host) host.textContent = '';
        } finally {
            state.loading = false;
            if (button) button.disabled = false;
        }
    }

    async function save() {
        if (state.saving) return;
        const patch = collect();
        if (!Object.keys(patch).length) {
            message('hint', text('nothing_to_save'));
            return;
        }
        state.saving = true;
        const button = el('save');
        if (button) button.disabled = true;
        try {
            render(await request('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ values: patch }),
            }));
            message('hint', text('saved') + ' ' + text('saved_hint'));
        } catch (error) {
            message('error', text('save_failed') + ' ' + error.message);
        } finally {
            state.saving = false;
            if (button) button.disabled = false;
        }
    }

    async function forgetKeys(keys) {
        const what = keys.length === 1 ? text('forget_one') : text('forget_all');
        if (!window.confirm(what + '?')) return;
        try {
            render(await request('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action: 'reset', keys: keys }),
            }));
            message('hint', text('forgotten'));
        } catch (error) {
            message('error', text('save_failed') + ' ' + error.message);
        }
    }

    function bind() {
        el('reload')?.addEventListener('click', load);
        el('save')?.addEventListener('click', save);
        el('forget')?.addEventListener('click', () => forgetKeys(null));
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') maybeLoad();
        });
        const view = document.getElementById('view-oneiro');
        if (view) {
            new MutationObserver(maybeLoad).observe(view, { attributes: true, attributeFilter: ['class'] });
        }
    }

    function maybeLoad() {
        const view = document.getElementById('view-oneiro');
        if (view && view.classList.contains('active') && !state.rows.length) load();
    }

    window.OneiroSettings = { load, save, forget: forgetKeys, api };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bind, { once: true });
    } else {
        bind();
    }
})();
