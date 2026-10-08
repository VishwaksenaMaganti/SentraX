/**
 * Ask SentraX copilot drawer
 * Streams answers from POST /api/ai/chat (Server-Sent Events) and renders them with a
 * small, HTML-escaping markdown subset. The backend holds the conversation per session id.
 */

(() => {
    const $ = (id) => document.getElementById(id);
    const escapeHtml = (window.SentraxUI && window.SentraxUI.escapeHtml) || ((s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[c])));

    const newSessionId = () => (crypto.randomUUID ? crypto.randomUUID() : `sx-${Date.now()}-${Math.random().toString(16).slice(2)}`);

    const state = {
        sessionId: newSessionId(),
        busy: false,
        controller: null,
        statusLoaded: false
    };

    // -----------------------------------------------------------------
    // Markdown subset: paragraphs, **bold**, *italic*, `code`, lists, ### headings
    // -----------------------------------------------------------------
    function inline(text) {
        return escapeHtml(text)
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
            .replace(/(^|[\s(])\*([^*\s][^*]*)\*(?=[\s).,;:!?]|$)/g, '$1<em>$2</em>');
    }

    function renderMarkdown(src) {
        const lines = src.replace(/\r/g, '').split('\n');
        const out = [];
        let para = [];
        let list = null; // { tag, items }

        const flushPara = () => {
            if (para.length) out.push(`<p>${para.map(inline).join('<br>')}</p>`);
            para = [];
        };
        const flushList = () => {
            if (list) out.push(`<${list.tag}>${list.items.map((i) => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`);
            list = null;
        };

        for (const raw of lines) {
            const line = raw.trimEnd();
            const bullet = line.match(/^\s*[-*]\s+(.*)$/);
            const numbered = line.match(/^\s*\d+[.)]\s+(.*)$/);
            const heading = line.match(/^#{1,4}\s+(.*)$/);
            if (!line.trim()) { flushPara(); flushList(); continue; }
            if (heading) { flushPara(); flushList(); out.push(`<h4>${inline(heading[1])}</h4>`); continue; }
            if (bullet || numbered) {
                flushPara();
                const tag = bullet ? 'ul' : 'ol';
                if (!list || list.tag !== tag) { flushList(); list = { tag, items: [] }; }
                list.items.push((bullet || numbered)[1]);
                continue;
            }
            if (list && /^\s{2,}\S/.test(raw)) { list.items[list.items.length - 1] += ' ' + line.trim(); continue; }
            flushList();
            para.push(line);
        }
        flushPara();
        flushList();
        return out.join('');
    }

    // -----------------------------------------------------------------
    // Drawer open / close
    // -----------------------------------------------------------------
    const isOpen = () => document.body.classList.contains('copilot-open');

    function open() {
        document.body.classList.add('copilot-open');
        $('copilot').setAttribute('aria-hidden', 'false');
        if (!state.statusLoaded) loadStatus();
        setTimeout(() => $('copilot-input')?.focus(), 120);
    }

    function close() {
        document.body.classList.remove('copilot-open');
        $('copilot').setAttribute('aria-hidden', 'true');
    }

    function prettyModel(id) {
        const name = String(id || '').replace(/^claude-/, '').replace(/-(\d+)-(\d+)$/, ' $1.$2').replace(/-(\d+)$/, ' $1');
        return 'Claude ' + name.replace(/\b\w/g, (c) => c.toUpperCase());
    }

    async function loadStatus() {
        try {
            const res = await fetch('/api/ai/status');
            if (!res.ok) return;
            const s = await res.json();
            state.statusLoaded = true;
            $('copilot-model').textContent = `${prettyModel(s.model)}, read-only access to live data`;
            $('copilot-notice').hidden = Boolean(s.api_key_configured);
        } catch (err) {
            /* server restarting; try again next open */
        }
    }

    // -----------------------------------------------------------------
    // Messages
    // -----------------------------------------------------------------
    const log = () => $('copilot-log');

    function nearBottom() {
        const el = log();
        return el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    }

    function scrollToEnd(force) {
        const el = log();
        if (force || nearBottom()) el.scrollTop = el.scrollHeight;
    }

    function addUserMessage(text) {
        const wrap = document.createElement('div');
        wrap.className = 'msg';
        wrap.innerHTML = `<div class="msg-user">${escapeHtml(text)}</div>`;
        log().appendChild(wrap);
        scrollToEnd(true);
    }

    function addAssistantMessage() {
        const wrap = document.createElement('div');
        wrap.className = 'msg';
        wrap.innerHTML = '<div class="msg-status">Thinking</div><div class="msg-ai"></div>';
        log().appendChild(wrap);
        scrollToEnd(true);
        return {
            status: wrap.querySelector('.msg-status'),
            body: wrap.querySelector('.msg-ai'),
            wrap
        };
    }

    function showError(view, message) {
        view.status?.remove();
        const err = document.createElement('div');
        err.className = 'msg-error';
        err.textContent = message;
        view.wrap.appendChild(err);
        scrollToEnd(true);
    }

    function setBusy(busy) {
        state.busy = busy;
        const btn = $('copilot-send');
        btn.classList.toggle('is-stop', busy);
        btn.setAttribute('aria-label', busy ? 'Stop' : 'Send');
        btn.innerHTML = busy ? '<i class="ph-fill ph-stop"></i>' : '<i class="ph-bold ph-arrow-up"></i>';
    }

    async function send(text) {
        const question = String(text || '').trim();
        if (!question || state.busy) return;

        $('copilot-empty')?.remove();
        addUserMessage(question);
        const view = addAssistantMessage();
        let answer = '';

        setBusy(true);
        state.controller = new AbortController();

        try {
            const res = await fetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: state.sessionId, message: question }),
                signal: state.controller.signal
            });
            if (!res.ok || !res.body) {
                showError(view, `The copilot endpoint returned ${res.status}. Check the server logs.`);
                return;
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            const handle = (evt) => {
                if (evt.type === 'text') {
                    answer += evt.text;
                    if (view.status) { view.status.remove(); view.status = null; }
                    view.body.innerHTML = renderMarkdown(answer);
                    view.body.classList.add('typing-caret');
                    scrollToEnd(false);
                } else if (evt.type === 'status') {
                    if (!view.status) {
                        view.status = document.createElement('div');
                        view.status.className = 'msg-status';
                        view.wrap.appendChild(view.status);
                    }
                    view.status.textContent = evt.label;
                    scrollToEnd(false);
                } else if (evt.type === 'error') {
                    showError(view, evt.message);
                }
            };

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                let idx;
                while ((idx = buffer.indexOf('\n\n')) !== -1) {
                    const chunk = buffer.slice(0, idx);
                    buffer = buffer.slice(idx + 2);
                    const data = chunk.split('\n').filter((l) => l.startsWith('data: ')).map((l) => l.slice(6)).join('');
                    if (!data) continue;
                    try { handle(JSON.parse(data)); } catch (e) { /* ignore a malformed frame */ }
                }
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                const note = document.createElement('div');
                note.className = 'msg-status is-static';
                note.textContent = 'Stopped';
                view.status?.remove();
                view.status = null;
                view.wrap.appendChild(note);
            } else {
                showError(view, 'Lost the connection to the SentraX server.');
            }
        } finally {
            view.body.classList.remove('typing-caret');
            view.status?.remove();
            if (!view.body.innerHTML) view.body.remove();
            state.controller = null;
            setBusy(false);
        }
    }

    function resetConversation() {
        state.controller?.abort();
        const oldId = state.sessionId;
        state.sessionId = newSessionId();
        fetch('/api/ai/reset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: oldId })
        }).catch(() => {});
        log().innerHTML = '';
        log().appendChild(emptyTemplate.cloneNode(true));
        bindAskButtons(log());
        $('copilot-input').focus();
    }

    function bindAskButtons(root) {
        root.querySelectorAll('[data-ask]').forEach((btn) => {
            if (btn.__sxBound) return;
            btn.__sxBound = true;
            btn.addEventListener('click', () => {
                open();
                send(btn.dataset.ask);
            });
        });
    }

    let emptyTemplate = null;

    document.addEventListener('DOMContentLoaded', () => {
        emptyTemplate = $('copilot-empty').cloneNode(true);

        document.querySelectorAll('[data-copilot-open]').forEach((btn) => btn.addEventListener('click', open));
        bindAskButtons(document);

        $('copilot-close').addEventListener('click', close);
        $('copilot-scrim').addEventListener('click', close);
        $('copilot-reset').addEventListener('click', resetConversation);

        const input = $('copilot-input');
        const autosize = () => {
            input.style.height = 'auto';
            input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
        };
        input.addEventListener('input', autosize);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                $('copilot-form').requestSubmit();
            }
        });

        $('copilot-form').addEventListener('submit', (e) => {
            e.preventDefault();
            if (state.busy) {
                state.controller?.abort();
                return;
            }
            const text = input.value;
            input.value = '';
            autosize();
            send(text);
        });

        document.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
                e.preventDefault();
                isOpen() ? close() : open();
            } else if (e.key === 'Escape' && isOpen() && !document.querySelector('.modal-backdrop.open')) {
                close();
            }
        });
    });
})();
