// frontend/static/js/interface_bridge.js
// Universal Input Bridge - primitive gesture reporter + input toolbar + virtual pointer + clipboard middleware
// IIFE. Public: IB.toggle(), IB.setModuleActions(), IB.cfg(), IB.init(), IB.attachWS(), IB.clipboard
const IB = (() => {

    // -- Feature Flags --
    // Defaults. Server overrides via hydrate OOB - #im-cfg-state JSON, or ws {"t":"cfg"}.
    // All toggleable at runtime via IB.cfg(key, val).
    const _cfg = {
        long_press:  true,   // detect long_press and fire intent (vs pass through)
        double_tap:  true,   // detect double_tap (adds DT_WINDOW delay to all taps)
        swipe:       false,  // if false: fast drags are ignored by reporter (browser handles scroll etc.)
        pointer:     false,  // virtual pointer active
        bridge_open: false,  // bridge toolbar visible
    };

    // -- Constants --
    const DRAG_THRESHOLD = 8;   // px movement before drag_start fires
    const LP_DELAY       = 500; // ms hold before long_press fires
    const DT_WINDOW      = 280; // ms between taps to count as double_tap
    const VP_STEP        = 20;  // px per arrow key in pointer mode
    const SWIPE_MAX_MS   = 250; // drag under this duration = swipe (only relevant if swipe:true)
    const _sendQueue = [];      // message serialization queue

    const UNIVERSAL = [
        { id:'select_all',     icon:'&#x25A3;', label:'All',   fn:() => { if (!_cmCmd('selectAll')) document.execCommand('selectAll'); } },
        { id:'copy',           icon:'&#x2398;', label:'Copy',  fn:() => { if (!_cmCmd('copy')) {document.execCommand('copy'); const sel = window.getSelection()?.toString(); if (sel) clipboard.copy(sel);}}},
        { id:'paste',          icon:'&#x2399;', label:'Paste', fn:() => { if (!_cmCmd('paste')) clipboard.paste(t => { const el = _getFocus(); if (!el) return; if ('value' in el) {const s = el.selectionStart; el.value = el.value.slice(0, s) + t + el.value.slice(el.selectionEnd); el.selectionStart = el.selectionEnd = s + t.length;} else document.execCommand('insertText', false, t); }); }},
        { id:'clip_pull',      icon:'&#x2BD1;', label:'Pull',  fn:() => clipboard.pullFromBrowser() },
        { id:'undo',           icon:'&#x21B6;', label:'Undo',  fn:() => { if (!_cmCmd('undo')) document.execCommand('undo'); } },
        { id:'redo',           icon:'&#x21B7;', label:'Redo',  fn:() => { if (!_cmCmd('redo')) document.execCommand('redo'); } },
        { id:'arrow_up',       icon:'&#x25B2;', label:'Up',    fn:() => _simKey('ArrowUp') },
        { id:'arrow_down',     icon:'&#x25BC;', label:'Down',  fn:() => _simKey('ArrowDown') },
        { id:'arrow_left',     icon:'&#x25C4;', label:'Left',  fn:() => _simKey('ArrowLeft') },
        { id:'arrow_right',    icon:'&#x25BA;', label:'Right', fn:() => _simKey('ArrowRight') },
        { id:'menu',           icon:'&#x2630;', label:'Menu',  fn:() => { const el = _getFocus(); if (!el) return; const r = el.getBoundingClientRect(); el.dispatchEvent(new MouseEvent('contextmenu', { bubbles:true, cancelable:true, clientX:r.left+r.width/2, clientY:r.top+r.height/2 })); }},
        { id:'enter',          icon:'&#x23CE;', label:'Enter', fn:() => _simKey('Enter') },
        { id:'escape',         icon:'&#x238B;', label:'Esc',   fn:() => _simKey('Escape') },
        { id:'tab_key',        icon:'&#x21E5;', label:'Tab',   fn:() => _simKey('Tab') },
        { id:'pointer_toggle', icon:'&#x2316;', label:'Ptr',   fn:() => { cfg('pointer', !_cfg.pointer); htmx.ajax('POST', '/in/in', { values: { type: 'set_cfg', key: 'pointer', value: String(_cfg.pointer) }, swap: 'none' });
        }},
    ];
    const _uByID = Object.fromEntries(UNIVERSAL.map(a => [a.id, a]));

    // -- State --
    let _pd = null;       // active pointer context
    let _drag = false;    // drag state flag
    let _kbDrag = null;   // keyboard drag tracking
    let _lpTimer = null;  // long_press timer reference
    let _dtTimer = null;  // double_tap window reference
    let _killDrag = false;// server interruption sentinel
    let _cbValue = null;  // local cache of remote clipboard
    let _ws = null;       // primary socket reference
    let _open = false;    // visual bar state visibility
    let _modActions = []; // contextual extension maps
    const _vp = { x: 0, y: 0, el: null }; // virtual node tracking

    // -- Element Targeting --
    function _imTarget(e) { if (e.target.closest('[data-im-bridge]')) return null; return e.target.closest('[data-im-role], [data-im-id]') || null; }
    function _elData(el) {
        if (!el) return { id: '', role: '', scope: '' };
        return { id: el.dataset?.imId || el.id || '', role: el.dataset?.imRole || '', scope: el.dataset?.imScope || '' };
    }
    function _elAt(x, y, exclude) { for (const el of document.elementsFromPoint(x, y)) { if (el === exclude) continue; if (el.dataset?.imRole || el.dataset?.imId || el.id) return el; } return null; }
    function _shellContext(el) {
        const s = (el && el.closest('[data-shell]')) || document.querySelector('[data-shell]');
        if (!s) return {lvl: '1', branch: ''};
        return { lvl: s.getAttribute('data-shell') || '1', branch: s.getAttribute('data-im-scope') || '' };
    }
    function _report(primitive, el, extra = {}) {
        const d = _elData(el);
        const ctx = _shellContext(el);
        const readSel = el.dataset.imRead;
        if (readSel) extra.selected = Array.from(el.querySelectorAll(readSel)).filter(c => c.checked).map(c => c.value);
        htmx.ajax('POST', '/im/in', {values: { type: primitive, element_id: d.id, element_role: d.role, element_scope: d.scope, t: Date.now(), ...ctx, ...extra }, swap: 'none'});
    }
    // -- Pointer Event Detection --
    document.addEventListener('pointerdown', e => {
        if (e.button && e.button > 0) return;
        const el = _imTarget(e);
        if (!el) return;
        _pd = { el, x0: e.clientX, y0: e.clientY, t0: Date.now(), pointerId: e.pointerId };
        _drag = false;
        _killDrag = false;
        if (_cfg.long_press) { _lpTimer = setTimeout(() => { if (_pd && !_drag) { _lpTimer = null; _report('long_press', _pd.el); _pd = null; } }, LP_DELAY); }
    });
    document.addEventListener('pointermove', e => {
        if (!_pd || e.pointerId !== _pd.pointerId || _drag) return;
        if (Math.hypot(e.clientX - _pd.x0, e.clientY - _pd.y0) < DRAG_THRESHOLD) return;
        clearTimeout(_lpTimer); _lpTimer = null;
        _drag = true;
        if (_killDrag) { _pd = null; return; }
        _report('drag_start', _pd.el, { t_start: _pd.t0 });
    });
    document.addEventListener('pointerup', e => {
        clearTimeout(_lpTimer); _lpTimer = null;
        if (!_pd || e.pointerId !== _pd.pointerId) return;
        const { el, t0 } = _pd;
        const t_end = Date.now();
        _pd = null;
        if (_drag) {
            _drag = false;
            if (_killDrag) { _killDrag = false; return; }
            const target = _elAt(e.clientX, e.clientY, el);
            const duration = t_end - t0;
            if (!_cfg.swipe && duration < SWIPE_MAX_MS) return;
            _report('drag_end', el, { target_id: _elData(target).id, t_start: t0, t_end });
            return;
        }
        if (el.tagName === 'BUTTON' && el.type === 'submit') {
            const form = el.closest('form');
            if (form) {
                if (form.hasAttribute('hx-post') || form.hasAttribute('hx-get') || form.hasAttribute('data-hx-post') || form.hasAttribute('data-hx-get')) return;
                e.preventDefault();
                _processFormSubmission(el, form);
                return;
            }
        }
        // if (el.tagName === 'BUTTON' && el.type === 'submit') { const form = el.closest('form'); if (form) { e.preventDefault(); _processFormSubmission(el, form); return; } }
        if (_cfg.double_tap && _dtTimer) { clearTimeout(_dtTimer); _dtTimer = null; _report('double_tap', el);
        } else if (_cfg.double_tap) { _dtTimer = setTimeout(() => { _dtTimer = null; _report('tap', el); }, DT_WINDOW);
        } else { _report('tap', el); }
    });
    function _processFormSubmission(triggerEl, formEl) {
        let actionEl = triggerEl;
        if (formEl && triggerEl.tagName !== 'BUTTON') { actionEl = formEl.querySelector('button[type="submit"]') || triggerEl; }
        const ctx = _shellContext(actionEl);
        let data = { type: 'submit', element_id: actionEl.id || actionEl.name || actionEl.dataset?.imId || '', element_role: actionEl.dataset?.imRole || (actionEl.tagName === 'BUTTON' ? 'button' : 'input'), element_scope: actionEl.dataset?.imScope || '', ...ctx };
        if (formEl) { new FormData(formEl).forEach((v, k) => { data[k] = v; });
        } else if ('value' in triggerEl) { const key = triggerEl.name || triggerEl.id || 'value'; data[key] = triggerEl.value; }
        if (!wsSend(data)) { htmx.ajax('POST', '/im/in', { values: data, swap: 'none' }); }
        if (formEl) { const txt = formEl.querySelector('textarea, input[type="text"]'); if (txt) { txt.value = ''; if (txt.style.height) txt.style.height = 'auto'; }
        } else if (triggerEl.tagName === 'TEXTAREA' || triggerEl.tagName === 'INPUT') { triggerEl.value = ''; if (triggerEl.style.height) triggerEl.style.height = 'auto'; }
    }
    document.addEventListener('pointercancel', () => { clearTimeout(_lpTimer); _lpTimer = null; _pd = null; _drag = false; });
    document.addEventListener('focusin', e => { const el = e.target.closest('[data-im-role], [data-im-id]'); if (el && el.tagName !== 'BUTTON') { _report('focus_change', el, { scroll_top: el.scrollTop, scroll_left: el.scrollLeft });}});
    // -- Keyboard Channel --
    document.addEventListener('keydown', e => {
        const focused = document.activeElement;
        if (!focused || focused === document.body) return;
        // Keyboard Drags
        if (e.altKey && ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)) {
            e.preventDefault();
            if (!_kbDrag) { _kbDrag = { el: focused, t0: Date.now() }; _report('drag_start', focused, { t_start: _kbDrag.t0, source: 'keyboard' }); }
            return;
        }
        const keyEl = e.target.closest('[data-im-keys]');
        if (keyEl && keyEl.dataset.imKeys.split(/\s+/).includes(e.key)) {
            e.preventDefault();
            _report('key', keyEl, { key: e.key });
            return;
        }
        // Transformed Actions (Enter Key Routing)
        if (e.key === 'Enter') {
            // CASE A: Command Modifier (Ctrl+Enter / Meta+Enter) -> Mirror Physical Send Button Tap
            if (e.ctrlKey || e.metaKey) {
                if (focused.tagName === 'INPUT' || focused.tagName === 'TEXTAREA') {
                    if (focused.classList.contains('cm-input')) return;
                    e.preventDefault();
                    const form = focused.closest('form') || focused.form;
                    if (form) {
                        const sendBtn = form.querySelector('.cm-send') || form.querySelector('button[type="submit"]');
                        if (sendBtn) { sendBtn.click(); return; }
                    }
                    _processFormSubmission(focused, form);
                    return;
                }
            }
            // CASE B: Plain Enter Key -> Mapped to Gesture Tap
            if (!e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey && !_kbDrag) {
                if (_cfg.double_tap && _dtTimer) { clearTimeout(_dtTimer); _dtTimer = null; _report('double_tap', focused);
                } else if (_cfg.double_tap) { _dtTimer = setTimeout(() => { _dtTimer = null; _report('tap', focused); }, DT_WINDOW);
                } else { _report('tap', focused); }
                return;
            }
        }
        // Virtual Pointer Controls
        if (_cfg.pointer && !e.altKey && ['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)) {
            e.preventDefault();
            const delta = { ArrowUp:[0,-VP_STEP], ArrowDown:[0,VP_STEP], ArrowLeft:[-VP_STEP,0], ArrowRight:[VP_STEP,0] }[e.key];
            _vpMove(_vp.x + delta[0], _vp.y + delta[1]);
            return;
        }
        if (_cfg.pointer && e.key === 'Enter' && !e.altKey) { const el = document.elementFromPoint(_vp.x, _vp.y); if (el) _report('tap', el); }
    });
    document.addEventListener('keyup', e => {
        if (!e.altKey && _kbDrag) {
            const { el, t0 } = _kbDrag;
            _kbDrag = null;
            const t_end = Date.now();
            const duration = t_end - t0;
            const target = document.activeElement !== el ? document.activeElement : null;
            if (!_cfg.swipe && duration < SWIPE_MAX_MS) return; 
            _report('drag_end', el, { target_id: _elData(target).id, t_start: t0, t_end, source: 'keyboard' });
        }
    });
    // -- Virtual Pointer Nodes --
    function _vpEl() { return document.getElementById('im-vpointer'); }
    function _vpMove(x, y) {
        _vp.x = Math.max(4, Math.min(x, window.innerWidth  - 4));
        _vp.y = Math.max(4, Math.min(y, window.innerHeight - 4));
        const dot = _vpEl(); if (dot) { dot.style.left = `${_vp.x}px`; dot.style.top = `${_vp.y}px`; }
        const el = document.elementFromPoint(_vp.x, _vp.y);
        if (el !== _vp.el) { _vp.el?.classList.remove('im-pointer-hover'); _vp.el = el; el?.classList.add('im-pointer-hover'); }
    }
    function _vpSetActive(on) {
        const dot = _vpEl(); if (dot) dot.style.display = on ? 'block' : 'none';
        if (on) _vpMove(_vp.x || window.innerWidth / 2, _vp.y || window.innerHeight / 2);
        else _vp.el?.classList.remove('im-pointer-hover');
    }
    function _vpInit() {
        if (document.getElementById('im-vpointer')) return;
        const dot = document.createElement('div');
        dot.id = 'im-vpointer';
        dot.style.cssText = `position:fixed; width:1.4rem; height:1.4rem; border-radius:50%; border:0.2rem solid var(--accent,#4af); background:transparent; pointer-events:none; z-index:9999; display:none; transform:translate(-50%,-50%); transition:left 0.04s,top 0.04s;`;
        document.body.appendChild(dot);
    }
    let _tpTouch = null;
    function _wireTrackpad(el) {
        el.addEventListener('touchstart', e => {
            if (!_cfg.pointer) return;
            _tpTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
            e.preventDefault();
        }, { passive: false });
        el.addEventListener('touchmove', e => {
            if (!_tpTouch || !_cfg.pointer) return;
            const dx = (e.touches[0].clientX - _tpTouch.x) * 1.8;
            const dy = (e.touches[0].clientY - _tpTouch.y) * 1.8;
            _tpTouch = { x: e.touches[0].clientX, y: e.touches[0].clientY };
            _vpMove(_vp.x + dx, _vp.y + dy);
            e.preventDefault();
        }, { passive: false });
        el.addEventListener('touchend', e => { _tpTouch = null; e.preventDefault(); }, { passive: false });
        el.addEventListener('click', () => {
            if (!_cfg.pointer) return;
            const el = document.elementFromPoint(_vp.x, _vp.y);
            if (el) _report('tap', el);
        });
    }
    // -- Clipboard Middleware --
    const clipboard = {
        copy(text) { _cbValue = text; htmx.ajax('POST', '/in/in', { values: { type: 'clipboard_set', value: text }, swap: 'none' }); navigator.clipboard?.writeText(text).catch(() => {}); },
        paste(fn) {
            if (_cbValue !== null) { fn(_cbValue); return; }
            fetch('/im/clipboard').then(r => r.json()).then(d => { _cbValue = d.value ?? ''; fn(_cbValue); }).catch(() => navigator.clipboard?.readText().then(fn).catch(() => fn('')));
        },
        pullFromBrowser() { navigator.clipboard?.readText().then(text => { if (text) this.copy(text); }).catch(() => {}); },
    };
    function _getFocus() { return document.activeElement !== document.body ? document.activeElement : null; }
    function _simKey(key, opts = {}) { const el = _getFocus(); if (!el) return; ['keydown','keypress','keyup'].forEach(t => el.dispatchEvent(new KeyboardEvent(t, { key, bubbles: true, cancelable: true, ...opts }))); }
    function _cmCmd(cmd) {
        const el = _getFocus(); if (!el) return false;
        if (el.CodeMirror) { el.CodeMirror.execCommand(cmd); return true; }
        const w = el.closest?.('.CodeMirror'); if (w?.CodeMirror) { w.CodeMirror.execCommand(cmd); return true; }
        return false;
    }
    // -- WebSocket Processing --
    function wsHandler(raw) {
        let d;
        try {
            d = typeof raw === 'string' ? JSON.parse(raw) : raw;
            if (typeof d === 'string' || !d || !d.t) { _processOOB(raw); return; }
        } catch (e) { _processOOB(raw); return; }

        switch (d.t) {
            case "oob": {
                const el = document.getElementById(d.id);
                if (el) { el.innerHTML = d.html; htmx.process(el); }
                break;
            }
            case 'update': {
                const el = document.getElementById(d.id); if (!el) return;
                if (d.html !== undefined) el.innerHTML = d.html;
                Object.entries(d.props   || {}).forEach(([k, v]) => { el[k] = v; });
                Object.entries(d.attrs   || {}).forEach(([k, v]) => { el.setAttribute(k, v); });
                Object.entries(d.classes || {}).forEach(([k, v]) => { el.classList.toggle(k, !!v); });
                break;
            }
            case "trigger": {
                const detail = d.detail ? (typeof d.detail === 'string' ? JSON.parse(d.detail) : d.detail) : {};
                if (d.event === "focused" && detail.url && detail._target) {
                    const targetId = detail._target.replace(/^#/, '');
                    const target = document.getElementById(targetId);
                    if (target) htmx.ajax('GET', detail.url, { target: target, swap: 'innerHTML' });
                } else {
                    document.dispatchEvent(new CustomEvent(d.event, { bubbles: true, detail: detail }));
                }
                break;
            }
            case 'query': {
                const el = document.getElementById(d.id); if (!el) return;
                const data = {};
                (d.fields || ['value', 'scrollTop', 'scrollLeft', 'innerHTML', 'checked', 'textContent']).forEach(f => { if (f in el) data[f] = el[f]; else data[f] = el.getAttribute?.(f) ?? null; });
                htmx.ajax('POST', '/im/element_data', { values: { qid: d.qid, element_id: d.id, data: JSON.stringify(data) }, swap: 'none', }); 
                break;
            }
            case 'kill_drag': {
                _killDrag = true; _drag = false; _pd = null; _kbDrag = null;
                clearTimeout(_lpTimer); _lpTimer = null;
                document.querySelectorAll('.being_dragged').forEach(e => e.classList.remove('being_dragged'));
                break;
            }
            case 'clipboard_sync': { _cbValue = d.value ?? null; break; }
            case 'cfg': { Object.assign(_cfg, d.values || {}); _vpSetActive(_cfg.pointer); break; }

            case 'pipeline_event': { document.dispatchEvent(new CustomEvent('pipeline:' + d.event, { detail: { job_id: d.job_id, ...d.payload } })); break; }
            case 'pipeline_stream': { document.dispatchEvent(new CustomEvent('pipeline:stream', { detail: { job_id: d.job_id, key: d.key, delta: d.delta } })); break; }
        }
    }
    // -- Component Generation --
    function _makeBtn(action) {
        const btn = document.createElement('button');
        btn.className = 'btn-icon';
        btn.title = action.label || action.id;
        btn.innerHTML = action.icon || action.label;
        btn.dataset.imBridge = '1';
        btn.style.cssText = 'padding:0 0.5rem;min-width:2.2rem;font-size:0.85rem;flex-shrink:0;';
        btn.addEventListener('pointerdown', e => {
            e.preventDefault();
            if (typeof action.fn === 'function') action.fn();
            else if (typeof action.fn === 'string') try { new Function(action.fn)(); } catch(err) { console.warn('IB fn:', err); }
            else if (action.intent) htmx.ajax('POST', '/in/in', { values: { type: action.intent }, swap: 'none' });
        });
        return btn;
    }
    function _render() {
        const bar = document.getElementById('im-bridge-bar'); if (!bar) return;
        bar.innerHTML = '';
        bar.style.cssText = 'display:flex;align-items:center;gap:0.15rem;padding:0 0.3rem;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;';
        const uG = document.createElement('div');
        uG.dataset.imBridge = '1';
        uG.style.cssText = 'display:flex;align-items:center;gap:0.1rem;flex-shrink:0;border-right:var(--board-thick,0.1rem) solid var(--border);padding-right:0.3rem;margin-right:0.2rem;';
        UNIVERSAL.forEach(a => uG.appendChild(_makeBtn(a)));
        bar.appendChild(uG);
        if (_modActions.length) {
            const mG = document.createElement('div');
            mG.id = 'im-bridge-module-actions';
            mG.dataset.imBridge = '1';
            mG.style.cssText = 'display:flex;align-items:center;gap:0.1rem;flex-shrink:0;';
            _modActions.forEach(a => { const r = typeof a === 'string' ? _uByID[a] : a; if (r) mG.appendChild(_makeBtn(r)); });
            bar.appendChild(mG);
        }
        const tp = document.createElement('div');
        tp.id = 'im-trackpad';
        tp.dataset.imBridge = '1';
        tp.title = 'Touch pointer pad - drag here to move virtual cursor';
        tp.style.cssText = 'width:4rem;height:1.8rem;border:0.1rem solid var(--border);border-radius:0.3rem;margin-left:0.4rem;flex-shrink:0;touch-action:none;display:flex;align-items:center;justify-content:center;font-size:0.65rem;opacity:0.5;cursor:crosshair;';
        tp.textContent = 'track pad';
        _wireTrackpad(tp);
        bar.appendChild(tp);
    }
    const _oobSeen = new Set();
    function _processOOB(html) {
        var tmp = document.createElement('div');
        tmp.innerHTML = html;
        Array.from(tmp.children).forEach(function(el) {
            var tid = el.id;
            var spec = el.getAttribute('hx-swap-oob') || 'outerHTML'; 
            var target = document.getElementById(tid);
            if (!target) { console.warn("[DEBUG] OOB Target not found in DOM:", tid); return; }
            try {
                if (spec === 'innerHTML') {
                    target.innerHTML = el.innerHTML; htmx.process(target);
                    requestAnimationFrame(function() {
                        if (tid.startsWith('cm-stream-')) { target.scrollTop = target.scrollHeight; }
                        var tb = target.querySelector('.cm-think-body');
                        if (tb) tb.scrollTop = tb.scrollHeight;
                    });
                } else if (spec === 'beforeend') {
                    var scratch = document.createElement('div');
                    scratch.innerHTML = el.innerHTML;
                    var childIds = Array.from(scratch.querySelectorAll('[id]')).map(function(c){ return c.id; });
                    var dup = childIds.some(function(cid){ return document.getElementById(cid) || _oobSeen.has(cid); });
                    if (!dup) {
                        childIds.forEach(function(cid){ _oobSeen.add(cid); });
                        var frag = document.createRange().createContextualFragment(el.innerHTML);
                        target.appendChild(frag);
                        if (target.lastElementChild) htmx.process(target.lastElementChild);
                    }
                    if (target.classList.contains('cm-msgs') && target.dataset.pinned === 'true')
                        requestAnimationFrame(function(){ target.scrollTo({top: target.scrollHeight, behavior: 'smooth'}); });
                } else {
                    var fresh = el.cloneNode(true); fresh.removeAttribute('hx-swap-oob');
                    target.replaceWith(fresh);
                    var refound = document.getElementById(tid);
                    if (refound) htmx.process(refound);
                }
            } catch(err) { console.warn('[IB] OOB swap error:', tid, err); }
        });
    }
    function wsSend(data) {
        if (_ws && _ws.readyState === 1) { _ws.send(typeof data === 'string' ? data : JSON.stringify(data)); return true; }
        if (_ws && _ws.readyState === 0) { _sendQueue.push(data); return true; } 
        return false;
    }
    function attachWS(socket) {
        _ws = socket;
        socket.addEventListener('message', e => wsHandler(e.data));
        socket.addEventListener('open', function() { while (_sendQueue.length && _ws && _ws.readyState === 1) _ws.send(typeof _sendQueue[0] === 'string' ? _sendQueue.shift() : JSON.stringify(_sendQueue.shift())); });
    }
    // -- Public Framework API Surface --
    function toggle() {
        _open = !_open;
        const wrapper = document.getElementById('im-bridge-wrapper');
        const btn     = document.getElementById('im-bridge-toggle');
        if (wrapper) wrapper.style.display = _open ? 'flex' : 'none';
        if (btn) btn.innerHTML = (_open ? '&#x2304;' : '&#x2303;') + ' Bridge';
        htmx.ajax('POST', '/in/in', { values: { type: 'set_bridge', open: String(_open) }, swap: 'none' });
    }
    function setModuleActions(actions) { _modActions = actions || []; _render(); }
    function cfg(key, val) { _cfg[key] = val; if (key === 'pointer') _vpSetActive(val);}
    function init() {
        _vpInit();
        _render();
        const stEl = document.getElementById('im-bridge-state');
        if (stEl?.textContent) {
            try {
                const saved = JSON.parse(stEl.textContent);
                Object.assign(_cfg, saved);
                _open = !!_cfg.bridge_open;
                const wrapper = document.getElementById('im-bridge-wrapper');
                if (wrapper) wrapper.style.display = _open ? 'flex' : 'none';
                _vpSetActive(_cfg.pointer);
            } catch(e) { console.warn('[IB] Initialization configuration parsing failure:', e); }
        }
    }
    return { toggle, setModuleActions, cfg, init, attachWS, clipboard };
})()
// --- Tab drag-reorder ---
// Wired to the data-* attrs UI.tab()/tab_bar_from_state already emit: data-tab-id (hyphenated -> dataset.tabId), data-reorder_type / data-branch / data-lvl (underscore variants stay literal in dataset, not camelCased).
function tabDragStart(e) {
	var tab = e.target.closest('.tab[data-tab-id]');
	if (!tab) return;
	e.dataTransfer.setData('text/tab-id', tab.dataset.tabId);
	e.dataTransfer.effectAllowed = 'move';
}
function tabDrop(e) {
	e.preventDefault();
	var srcId = e.dataTransfer.getData('text/tab-id');
	var dstTab = e.target.closest('.tab[data-tab-id]');
	if (!srcId || !dstTab || dstTab.dataset.tabId === srcId) return;
	htmx.ajax('POST', '/im/in', { values: { type: dstTab.dataset.reorder_type, branch: dstTab.dataset.branch, lvl: dstTab.dataset.lvl, from: srcId, to: dstTab.dataset.tabId }, swap: 'none' });
};