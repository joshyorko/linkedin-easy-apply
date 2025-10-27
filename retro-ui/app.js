// LinkedIn Easy Apply Retro Terminal UI
// Main Application Logic

// Configuration
const CONFIG = {
    ACTION_SERVER_URL: 'http://localhost:8082',  // Updated to match running server
    PROXY_SERVER_URL: 'http://localhost:3001',
    REFRESH_INTERVAL: 5000,  // Fast polling (5 seconds) - optimized to be silent
};

// State Management
const state = {
    jobs: [],
    currentRunId: null,
    stats: {
        totalJobs: 0,
        goodFitJobs: 0,
        appliedJobs: 0,
        activeProfile: 'NONE'
    },
    operations: [],
    recentRuns: [],
    panels: {
        'console-panel': { title: 'Console Output', collapsed: false, hidden: false, initialized: false },
        'jobs-panel': { title: 'Job Listings', collapsed: false, hidden: false, initialized: false }
    },
    hiddenPanels: []
};

const OPERATIONS_HISTORY_LIMIT = 8;
const RECENT_RUN_LIMIT = 6;
const toastRegistry = new Map();

// Toast Notifications
function showToast(message, type = 'info', options = {}) {
    const container = document.getElementById('toast-container');
    if (!container) {
        return null;
    }

    const toastId = `toast_${Date.now()}_${Math.random().toString(16).slice(2)}`;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.dataset.toastId = toastId;
    toast.setAttribute('role', 'alert');

    const icon = document.createElement('div');
    icon.className = 'toast-icon';
    icon.textContent = getToastIcon(type);

    const body = document.createElement('div');
    body.className = 'toast-message';
    body.textContent = message;

    const closeBtn = document.createElement('button');
    closeBtn.className = 'toast-dismiss';
    closeBtn.setAttribute('aria-label', 'Dismiss notification');
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', () => dismissToast(toastId));

    toast.appendChild(icon);
    toast.appendChild(body);
    toast.appendChild(closeBtn);
    container.appendChild(toast);

    requestAnimationFrame(() => {
        toast.classList.add('show');
    });

    const sticky = options.sticky === true;
    const autoCloseDelay = options.autoClose ?? 4000;

    let timerId = null;
    if (!sticky) {
        timerId = setTimeout(() => dismissToast(toastId), autoCloseDelay);
    }

    toastRegistry.set(toastId, { element: toast, timerId });
    return toastId;
}

function updateToast(toastId, { message, type, autoClose, sticky } = {}) {
    const toastEntry = toastRegistry.get(toastId);
    if (!toastEntry) {
        return;
    }

    const { element } = toastEntry;
    const icon = element.querySelector('.toast-icon');
    const messageNode = element.querySelector('.toast-message');

    if (type) {
        element.classList.remove('success', 'error', 'warning', 'pending', 'info');
        element.classList.add(type);
        if (icon) {
            icon.textContent = getToastIcon(type);
        }
    }

    if (message && messageNode) {
        messageNode.textContent = message;
    }

    if (toastEntry.timerId) {
        clearTimeout(toastEntry.timerId);
        toastEntry.timerId = null;
    }

    const shouldAutoClose = sticky === true ? false : sticky === false ? true : autoClose !== undefined;
    if (shouldAutoClose) {
        const delay = autoClose ?? 4000;
        toastEntry.timerId = setTimeout(() => dismissToast(toastId), delay);
    }

    toastRegistry.set(toastId, toastEntry);
}

function dismissToast(toastId) {
    const toastEntry = toastRegistry.get(toastId);
    if (!toastEntry) {
        return;
    }

    const { element, timerId } = toastEntry;
    if (timerId) {
        clearTimeout(timerId);
    }

    element.classList.remove('show');
    setTimeout(() => {
        if (element.parentNode) {
            element.parentNode.removeChild(element);
        }
    }, 200);

    toastRegistry.delete(toastId);
}

function getToastIcon(type) {
    switch (type) {
        case 'success':
            return '✔';
        case 'error':
            return '✖';
        case 'warning':
            return '⚠';
        case 'pending':
            return '⏳';
        default:
            return 'ℹ';
    }
}

// Panel Management
function getPanelState(panelId) {
    if (!state.panels[panelId]) {
        state.panels[panelId] = { title: panelId, collapsed: false, hidden: false, initialized: false };
    }

    const panel = document.getElementById(panelId);
    if (!panel) {
        return state.panels[panelId];
    }

    const defaultHidden = panel.dataset.panelDefaultHidden === 'true';
    const derivedTitle = panel.dataset.panelTitle || panel.querySelector('.panel-title')?.textContent?.trim() || panelId;

    state.panels[panelId].title = derivedTitle;

    if (!state.panels[panelId].initialized) {
        const isCollapsed = panel.classList.contains('panel-collapsed');
        const isHidden = defaultHidden ? false : (panel.classList.contains('panel-hidden') || panel.style.display === 'none');

        state.panels[panelId].collapsed = isCollapsed;
        state.panels[panelId].hidden = isHidden;
        state.panels[panelId].initialized = true;
    }

    return state.panels[panelId];
}

function togglePanelCollapse(panelId, control) {
    const panel = document.getElementById(panelId);
    if (!panel) {
        return;
    }

    const panelState = getPanelState(panelId);
    if (panelState.hidden) {
        showPanel(panelId, { preserveCollapse: false });
    }

    const collapsed = !panelState.collapsed;
    panelState.collapsed = collapsed;
    panel.classList.toggle('panel-collapsed', collapsed);

    panel.querySelectorAll('[data-panel-body]').forEach(node => {
        node.setAttribute('aria-hidden', collapsed.toString());
    });

    if (control) {
        control.setAttribute('aria-expanded', (!collapsed).toString());
        control.setAttribute('title', collapsed ? 'Expand panel' : 'Collapse panel');
        control.textContent = collapsed ? '▸' : '▾';
    }
}

function hidePanel(panelId, options = {}) {
    const panel = document.getElementById(panelId);
    if (!panel) {
        return;
    }

    const { addToTray = true, silent = false } = options;
    const panelState = getPanelState(panelId);

    if (panelState.hidden) {
        return;
    }

    panelState.hidden = true;
    panelState.collapsed = false;

    panel.classList.add('panel-hidden');
    panel.classList.remove('panel-collapsed');
    panel.style.display = 'none';
    panel.setAttribute('data-hidden', 'true');

    const collapseControl = panel.querySelector('[data-panel-action="collapse"]');
    if (collapseControl) {
        collapseControl.setAttribute('aria-expanded', 'true');
        collapseControl.textContent = '▾';
        collapseControl.setAttribute('title', 'Collapse panel');
    }

    if (addToTray) {
        addHiddenPanelBadge(panelId, panelState.title);
    } else {
        removeHiddenPanelBadge(panelId);
    }

    updateHiddenPanelsTrayVisibility();

    if (!silent && panelId === 'console-panel' && addToTray) {
        log('info', 'Console output hidden. Restore it via the Hidden Panels tray below.');
    }
}

function showPanel(panelId, options = {}) {
    const panel = document.getElementById(panelId);
    if (!panel) {
        return;
    }

    const panelState = getPanelState(panelId);
    panelState.hidden = false;

    panel.classList.remove('panel-hidden');
    panel.removeAttribute('data-hidden');
    panel.style.display = options.display || 'block';

    if (!options.preserveCollapse) {
        panel.classList.remove('panel-collapsed');
        panelState.collapsed = false;
    }

    const collapseControl = panel.querySelector('[data-panel-action="collapse"]');
    if (collapseControl) {
        collapseControl.setAttribute('aria-expanded', 'true');
        collapseControl.textContent = '▾';
        collapseControl.setAttribute('title', 'Collapse panel');
    }

    panel.querySelectorAll('[data-panel-body]').forEach(node => {
        node.setAttribute('aria-hidden', 'false');
    });

    removeHiddenPanelBadge(panelId);
    updateHiddenPanelsTrayVisibility();
}

function restorePanel(panelId) {
    showPanel(panelId);
    const panelState = getPanelState(panelId);
    if (panelState?.title) {
        log('info', `${panelState.title} restored.`);
    }
}

function addHiddenPanelBadge(panelId, title) {
    const tray = document.getElementById('hidden-panels-tray');
    if (!tray) {
        return;
    }

    if (!state.hiddenPanels.includes(panelId)) {
        state.hiddenPanels.push(panelId);
    }

    let button = tray.querySelector(`[data-restore-panel="${panelId}"]`);
    if (!button) {
        button = document.createElement('button');
        button.className = 'retro-btn btn-small';
        button.dataset.restorePanel = panelId;
        button.textContent = `Show ${title}`;
        button.addEventListener('click', () => restorePanel(panelId));
        tray.appendChild(button);
    } else {
        button.textContent = `Show ${title}`;
    }
}

function removeHiddenPanelBadge(panelId) {
    const tray = document.getElementById('hidden-panels-tray');
    if (!tray) {
        return;
    }

    const index = state.hiddenPanels.indexOf(panelId);
    if (index !== -1) {
        state.hiddenPanels.splice(index, 1);
    }

    const button = tray.querySelector(`[data-restore-panel="${panelId}"]`);
    if (button) {
        button.remove();
    }
}

function updateHiddenPanelsTrayVisibility() {
    const tray = document.getElementById('hidden-panels-tray');
    if (!tray) {
        return;
    }

    const hasHiddenPanels = state.hiddenPanels.length > 0;
    tray.classList.toggle('active', hasHiddenPanels);
    tray.style.display = hasHiddenPanels ? 'flex' : 'none';
}

function syncInitialPanelState() {
    Object.keys(state.panels).forEach(panelId => {
        const panel = document.getElementById(panelId);
        if (!panel) {
            return;
        }

        const panelState = getPanelState(panelId);

        panel.classList.toggle('panel-collapsed', panelState.collapsed);

        panel.querySelectorAll('[data-panel-body]').forEach(node => {
            node.setAttribute('aria-hidden', panelState.collapsed.toString());
        });

        const collapseControl = panel.querySelector('[data-panel-action="collapse"]');
        if (collapseControl) {
            collapseControl.setAttribute('aria-expanded', (!panelState.collapsed).toString());
            collapseControl.textContent = panelState.collapsed ? '▸' : '▾';
            collapseControl.setAttribute('title', panelState.collapsed ? 'Expand panel' : 'Collapse panel');
        }

        if (panelState.hidden) {
            panel.classList.add('panel-hidden');
            panel.style.display = 'none';
            addHiddenPanelBadge(panelId, panelState.title);
        }
    });

    updateHiddenPanelsTrayVisibility();
}

// Operation Tracking
function createOperation({ label, action, runId = null, meta = {} }) {
    const operation = {
        id: `op_${Date.now()}_${Math.random().toString(16).slice(2)}`,
        label,
        action,
        status: 'pending',
        runId,
        meta,
        detail: '',
        startedAt: Date.now(),
        updatedAt: Date.now(),
        completedAt: null
    };

    state.operations = [operation, ...state.operations].slice(0, OPERATIONS_HISTORY_LIMIT);
    renderOperations();
    return operation;
}

function updateOperation(operationId, updates = {}) {
    const index = state.operations.findIndex(op => op.id === operationId);
    if (index === -1) {
        return null;
    }

    const updatedOperation = {
        ...state.operations[index],
        ...updates,
        updatedAt: Date.now()
    };

    if (updates.status && updates.status !== 'pending' && !updatedOperation.completedAt) {
        updatedOperation.completedAt = Date.now();
    }

    state.operations[index] = updatedOperation;
    renderOperations();
    return updatedOperation;
}

function finalizeOperation(operationId, status, detail = '', extra = {}) {
    return updateOperation(operationId, {
        status,
        detail,
        ...extra
    });
}

function clearOperations() {
    const initialCount = state.operations.length;
    state.operations = state.operations.filter(op => op.status === 'pending');
    const removedCount = initialCount - state.operations.length;
    renderOperations();
    if (removedCount > 0) {
        showToast(`Cleared ${removedCount} completed operation${removedCount === 1 ? '' : 's'}`, 'info', { autoClose: 2500 });
    } else if (initialCount > 0) {
        showToast('No completed operations to clear', 'warning', { autoClose: 2500 });
    }
}

function renderOperations() {
    const liveContainer = document.getElementById('operations-live');
    if (!liveContainer) {
        return;
    }

    liveContainer.innerHTML = '';

    const activeOps = state.operations.filter(op => op.status === 'pending');
    const completedOps = state.operations.filter(op => op.status !== 'pending');

    if (activeOps.length === 0 && completedOps.length === 0) {
        liveContainer.classList.add('empty');
        liveContainer.textContent = 'No active operations';
        return;
    }

    liveContainer.classList.remove('empty');

    const fragment = document.createDocumentFragment();
    activeOps.forEach(op => fragment.appendChild(buildOperationElement(op)));

    if (completedOps.length > 0) {
        const divider = document.createElement('div');
        divider.className = 'operations-subheading';
        divider.textContent = 'Recently completed';
        fragment.appendChild(divider);

        completedOps.slice(0, OPERATIONS_HISTORY_LIMIT).forEach(op => {
            fragment.appendChild(buildOperationElement(op));
        });
    }

    liveContainer.appendChild(fragment);
}

function buildOperationElement(operation) {
    const element = document.createElement('div');
    element.className = `operation-item ${operation.status}`;

    const statusIcon = document.createElement('div');
    statusIcon.className = 'operation-status-icon';

    if (operation.status === 'pending') {
        statusIcon.classList.add('spinner');
    } else if (operation.status === 'success') {
        statusIcon.textContent = '✔';
    } else if (operation.status === 'error') {
        statusIcon.textContent = '✖';
    } else {
        statusIcon.textContent = 'ℹ';
    }

    const content = document.createElement('div');
    content.className = 'operation-content';

    const title = document.createElement('div');
    title.className = 'operation-title';
    title.textContent = truncateText(operation.label, 60);

    if (operation.runId) {
        const pill = document.createElement('span');
        pill.className = 'badge badge-remote';
        pill.textContent = operation.runId;
        title.appendChild(pill);
    }

    const meta = document.createElement('div');
    meta.className = 'operation-meta';
    meta.textContent = buildOperationMeta(operation);

    const detail = document.createElement('div');
    detail.className = 'operation-detail';
    detail.textContent = operation.detail || '';

    content.appendChild(title);
    content.appendChild(meta);
    if (operation.detail) {
        content.appendChild(detail);
    }

    element.appendChild(statusIcon);
    element.appendChild(content);
    return element;
}

function buildOperationMeta(operation) {
    const timestamps = [];
    if (operation.status === 'pending') {
        timestamps.push(`Started ${formatRelativeTime(operation.startedAt)}`);
    } else if (operation.completedAt) {
        timestamps.push(`Finished ${formatRelativeTime(operation.completedAt)}`);
    }

    if (operation.meta && operation.meta.context) {
        timestamps.push(operation.meta.context);
    }

    return timestamps.join(' • ');
}

function formatRelativeTime(timestamp) {
    if (!timestamp) {
        return 'just now';
    }
    const diffMs = Date.now() - timestamp;
    const diffSeconds = Math.max(1, Math.floor(diffMs / 1000));

    if (diffSeconds < 60) {
        return `${diffSeconds}s ago`;
    }

    const diffMinutes = Math.floor(diffSeconds / 60);
    if (diffMinutes < 60) {
        return `${diffMinutes}m ago`;
    }

    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) {
        return `${diffHours}h ago`;
    }

    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
}

function truncateText(text, maxLength) {
    if (!text) {
        return '';
    }
    if (text.length <= maxLength) {
        return text;
    }
    return `${text.slice(0, maxLength - 3)}...`;
}

// Action Run Monitoring
async function refreshActionRuns(isAutoRefresh = false) {
    const container = document.getElementById('operations-recent');
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/runs-with-stats`);
        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const data = await response.json();
        state.recentRuns = Array.isArray(data.results) ? data.results.slice(0, RECENT_RUN_LIMIT) : [];
        renderRecentRuns();

        if (!isAutoRefresh && state.recentRuns.length > 0) {
            showToast('Recent run history updated', 'success', { autoClose: 2500 });
        }
    } catch (error) {
        if (container) {
            container.classList.add('empty');
            container.textContent = `Failed to load run history: ${error.message}`;
        }
        if (!isAutoRefresh) {
            showToast(`Failed to load run history: ${error.message}`, 'error', { autoClose: 5000 });
        }
    }
}

function renderRecentRuns() {
    const container = document.getElementById('operations-recent');
    if (!container) {
        return;
    }

    container.innerHTML = '';
    if (!state.recentRuns || state.recentRuns.length === 0) {
        container.classList.add('empty');
        container.textContent = 'No runs recorded yet';
        return;
    }

    container.classList.remove('empty');
    const fragment = document.createDocumentFragment();

    state.recentRuns.forEach(run => {
        fragment.appendChild(buildRecentRunElement(run));
    });

    container.appendChild(fragment);
}

function buildRecentRunElement(run) {
    const element = document.createElement('div');
    element.className = 'recent-run-item';

    const title = document.createElement('div');
    title.className = 'recent-run-title';
    const runType = run.run_id ? run.run_id.split('_')[0].toUpperCase() : 'RUN';
    title.textContent = `${runType} • ${truncateText(run.run_id || 'unknown', 28)}`;

    const meta = document.createElement('div');
    meta.className = 'recent-run-meta';
    const jobCount = run.job_count || 0;
    const applied = run.applied_jobs ? run.applied_jobs.split(',').filter(Boolean).length : 0;
    const timestamp = run.timestamp ? new Date(run.timestamp).toLocaleString() : 'Unknown time';

    const jobsLabel = document.createElement('span');
    jobsLabel.textContent = 'Jobs: ';

    const jobsValue = document.createElement('span');
    jobsValue.className = 'recent-run-jobs';
    jobsValue.textContent = jobCount;

    const appliedSpan = document.createElement('span');
    appliedSpan.textContent = ` • Applied: ${applied}`;

    const timestampSpan = document.createElement('span');
    timestampSpan.textContent = ` • ${timestamp}`;

    meta.appendChild(jobsLabel);
    meta.appendChild(jobsValue);
    meta.appendChild(appliedSpan);
    meta.appendChild(timestampSpan);

    element.appendChild(title);
    element.appendChild(meta);
    return element;
}

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    initializeUI();
    checkServerStatus();
    loadStats();
    startAutoRefresh();  // Poll for updates
    setupKeyboardShortcuts();
});

// UI Initialization
function initializeUI() {
    updateTimestamp();
    setInterval(updateTimestamp, 1000);
    renderOperations();
    renderRecentRuns();
    syncInitialPanelState();
    refreshActionRuns(true);
    log('info', 'UI initialized successfully');
}

// Update timestamp in header
function updateTimestamp() {
    const now = new Date();
    const timestamp = now.toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    });
    document.getElementById('timestamp').textContent = timestamp;
}

// Console Logging
function log(level, message) {
    const console = document.getElementById('console-output');
    const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
    
    const line = document.createElement('div');
    line.className = `log-line ${level}`;
    line.innerHTML = `<span class="log-timestamp">[${timestamp}]</span>${message}`;
    
    console.appendChild(line);
    console.scrollTop = console.scrollHeight;
}

function clearConsole() {
    const console = document.getElementById('console-output');
    console.innerHTML = '';
    log('info', 'Console cleared');
}

// Server Status Check
async function checkServerStatus() {
    try {
        // Check if action server root is accessible
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/`);
        if (response.ok) {
            document.getElementById('server-status').textContent = 'ONLINE';
            document.getElementById('server-status').style.color = '#00ff00';
            log('success', 'Action server is online');
        } else {
            throw new Error('Server returned error');
        }
    } catch (error) {
        document.getElementById('server-status').textContent = 'OFFLINE';
        document.getElementById('server-status').style.color = '#ff3333';
        log('error', `Action server offline: ${error.message}`);
    }
}

// Load Statistics from Database
async function loadStats() {
    try {
        // Silent background refresh - no console logging during auto-refresh
        const isAutoRefresh = arguments[0] === true;
        
        if (!isAutoRefresh) {
            log('info', 'Loading statistics from database...');
        }
        
        // Query total jobs
        const totalResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/total-jobs`);
        
        if (totalResponse.ok) {
            const totalData = await totalResponse.json();
            const newTotal = totalData.results[0]?.count || 0;
            if (state.stats.totalJobs !== newTotal) {
                state.stats.totalJobs = newTotal;
                document.getElementById('total-jobs').textContent = state.stats.totalJobs;
            }
        }
        
        // Query good fit jobs
        const goodFitResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/good-fit-count`);
        
        if (goodFitResponse.ok) {
            const goodFitData = await goodFitResponse.json();
            const newGoodFit = goodFitData.results[0]?.count || 0;
            if (state.stats.goodFitJobs !== newGoodFit) {
                state.stats.goodFitJobs = newGoodFit;
                document.getElementById('good-fit-jobs').textContent = state.stats.goodFitJobs;
            }
        }
        
        // Query applied jobs
        const appliedResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/applied-count`);
        
        if (appliedResponse.ok) {
            const appliedData = await appliedResponse.json();
            const newApplied = appliedData.results[0]?.count || 0;
            if (state.stats.appliedJobs !== newApplied) {
                state.stats.appliedJobs = newApplied;
                document.getElementById('applied-jobs').textContent = state.stats.appliedJobs;
            }
        }
        
        // Query active profile
        const profileResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/active-profile`);
        
        if (profileResponse.ok) {
            const profileData = await profileResponse.json();
            const profileName = profileData.results[0]?.profile_name || 'NONE';
            if (state.stats.activeProfile !== profileName) {
                state.stats.activeProfile = profileName;
                document.getElementById('active-profile').textContent = profileName;
            }
        }
        
        if (!isAutoRefresh) {
            log('success', 'Statistics loaded successfully');
        }
    } catch (error) {
        // Only log errors during manual refresh, silent during auto-refresh
        if (arguments[0] !== true) {
            log('error', `Failed to load statistics: ${error.message}`);
        }
    }
}

// Auto-refresh stats (polling for updates)
function startAutoRefresh() {
    let pollCount = 0;
    setInterval(() => {
        loadStats(true);  // Pass true to indicate auto-refresh (silent mode)
        checkServerStatus();
        renderOperations();

        pollCount += 1;
        if (pollCount % 2 === 0) {
            refreshActionRuns(true);
        }
    }, CONFIG.REFRESH_INTERVAL);
}

// Keyboard Shortcuts
function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        if (e.key === 'F1') {
            e.preventDefault();
            showHelp();
        } else if (e.key === 'F2') {
            e.preventDefault();
            showSearchForm();
        } else if (e.key === 'F3') {
            e.preventDefault();
            enrichJobs();
        } else if (e.key === 'F4') {
            e.preventDefault();
            showApplyMenu();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            closeModal();
            closeJobsPanel();
        }
    });
}

// Show Help
function showHelp() {
    const helpContent = `
        <div style="color: #00ff00;">
            <h2 style="text-align: center; margin-bottom: 20px;">█ HELP DOCUMENTATION █</h2>
            
            <h3>KEYBOARD SHORTCUTS:</h3>
            <ul style="list-style-type: none; margin-left: 20px;">
                <li>[F1] - Show this help menu</li>
                <li>[F2] - Open job search form</li>
                <li>[F3] - Start AI enrichment</li>
                <li>[F4] - Open application menu</li>
                <li>[ESC] - Close modal/panel</li>
            </ul>
            
            <h3>WORKFLOW:</h3>
            <ol style="margin-left: 20px;">
                <li>SEARCH - Use search form to scrape LinkedIn jobs</li>
                <li>ENRICH - Run AI analysis to identify good fits</li>
                <li>REVIEW - View good fit jobs and filter candidates</li>
                <li>APPLY - Auto-apply to selected jobs</li>
            </ol>
            
            <h3>FEATURES:</h3>
            <ul style="list-style-type: none; margin-left: 20px;">
                <li>⚡ Real-time database monitoring</li>
                <li>🤖 OpenAI-powered job matching</li>
                <li>🔄 Automated form filling</li>
                <li>📊 Application tracking</li>
                <li>💾 Persistent browser sessions</li>
            </ul>
            
            <h3>DATABASE ACCESS:</h3>
            <p style="margin-left: 20px;">
                All data is stored in: <strong>linkedin_jobs.sqlite</strong><br>
                Query via SQL console or export to CSV
            </p>
        </div>
    `;
    openModal('HELP & DOCUMENTATION', helpContent);
}

// Search Form
function showSearchForm() {
    const formHtml = `
        <form id="search-form" onsubmit="executeSearch(event)">
            <div class="form-group">
                <label class="form-label">SEARCH QUERY</label>
                <input type="text" class="form-input" id="search-query" 
                       placeholder="e.g., Python Developer, DevOps Engineer" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">MAXIMUM JOBS</label>
                <input type="number" class="form-input" id="search-max-jobs" 
                       value="25" min="1" max="100" required>
            </div>
            
            <div class="form-group">
                <label class="form-label">LOCATION TYPE</label>
                <select class="form-select" id="search-location-type">
                    <option value="all">All Types</option>
                    <option value="remote">Remote Only</option>
                    <option value="hybrid">Hybrid</option>
                    <option value="onsite">On-site</option>
                </select>
            </div>
            
            <div class="form-group">
                <label class="form-label">
                    <input type="checkbox" class="form-checkbox" id="search-easy-apply" checked>
                    EASY APPLY ONLY
                </label>
            </div>
            
            <button type="submit" class="retro-btn">▶ START SEARCH</button>
        </form>
    `;
    openModal('JOB SEARCH', formHtml);
}

// Execute Search
async function executeSearch(event) {
    event.preventDefault();
    closeModal();
    
    const query = document.getElementById('search-query').value;
    const maxJobs = parseInt(document.getElementById('search-max-jobs').value);
    const locationType = document.getElementById('search-location-type').value;
    const easyApplyOnly = document.getElementById('search-easy-apply').checked;
    
    log('info', `Initiating search: "${query}" (max ${maxJobs} jobs)...`);
    log('info', 'This may take several minutes...');

    const contextParts = [`Max ${maxJobs} jobs`];
    if (locationType !== 'all') {
        contextParts.push(`Location: ${locationType.toUpperCase()}`);
    }
    if (easyApplyOnly) {
        contextParts.push('Easy Apply required');
    }

    const pendingToast = showToast(`Starting search for "${truncateText(query, 48)}"`, 'pending', { sticky: true });
    const operation = createOperation({
        label: `Search • ${truncateText(query, 42)}`,
        action: 'search',
        meta: {
            context: contextParts.join(' • ')
        }
    });
    
    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/search-linkedin-easy-apply/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                max_jobs: maxJobs,
                location_type: locationType !== 'all' ? locationType : undefined
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            log('success', `Search completed! Found ${result.result?.jobs_found || 0} jobs`);
            log('info', `Run ID: ${result.result?.run_id || 'unknown'}`);
            state.currentRunId = result.result?.run_id;
            loadStats();

            if (operation) {
                const jobsFound = result.result?.jobs_found ?? 0;
                finalizeOperation(operation.id, 'success', `Found ${jobsFound} jobs`, {
                    runId: result.result?.run_id || null,
                    meta: {
                        ...operation.meta,
                        context: contextParts.join(' • ')
                    }
                });
            }

            if (pendingToast) {
                updateToast(pendingToast, {
                    message: `Search complete: ${result.result?.jobs_found || 0} jobs found`,
                    type: 'success',
                    autoClose: 4000
                });
            }

            refreshActionRuns(true);
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Search failed: ${error.message}`);

        if (operation) {
            finalizeOperation(operation.id, 'error', error.message);
        }

        if (pendingToast) {
            updateToast(pendingToast, {
                message: `Search failed: ${error.message}`,
                type: 'error',
                autoClose: 6000
            });
        }
    }
}

// View Recent Searches
async function viewRecentSearches() {
    log('info', 'Loading recent searches...');
    
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/search-history`);
        
        if (response.ok) {
            const data = await response.json();
            displaySearchHistory(data.results);
        }
    } catch (error) {
        log('error', `Failed to load searches: ${error.message}`);
    }
}

function displaySearchHistory(searches) {
    const tableHtml = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>RUN ID</th>
                    <th>JOBS FOUND</th>
                    <th>DATE</th>
                    <th>ACTION</th>
                </tr>
            </thead>
            <tbody>
                ${searches.map(search => `
                    <tr>
                        <td>${search.run_id}</td>
                        <td>${search.job_count}</td>
                        <td>${new Date(search.last_scraped).toLocaleString()}</td>
                        <td>
                            <button class="retro-btn" onclick="loadJobsByRunId('${search.run_id}')" 
                                    style="margin: 0; padding: 5px 10px; font-size: 16px;">
                                VIEW JOBS
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    openModal('RECENT SEARCHES', tableHtml);
}

// Load Jobs by Run ID
async function loadJobsByRunId(runId) {
    closeModal();
    log('info', `Loading jobs from run: ${runId}...`);
    
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/jobs-by-run/${runId}`);
        
        if (response.ok) {
            const data = await response.json();
            state.jobs = data.results;
            displayJobs(state.jobs);
            log('success', `Loaded ${data.results.length} jobs`);
        }
    } catch (error) {
        log('error', `Failed to load jobs: ${error.message}`);
    }
}

// Display Jobs
function displayJobs(jobs) {
    showPanel('jobs-panel');
    const panel = document.getElementById('jobs-panel');
    const content = document.getElementById('jobs-content');
    
    if (jobs.length === 0) {
        content.innerHTML = '<div style="text-align: center; padding: 50px; color: #ff3333;">NO JOBS FOUND</div>';
    } else {
        content.innerHTML = jobs.map(job => `
            <div class="job-item" onclick="viewJobDetails('${job.job_id}')">
                <div class="job-title">${job.title || 'N/A'}</div>
                <div class="job-company">${job.company || 'Unknown Company'}</div>
                <div class="job-meta">${job.location_raw || 'Location not specified'}</div>
                <div class="job-badges">
                    ${job.good_fit ? '<span class="badge badge-fit">✓ GOOD FIT</span>' : ''}
                    ${job.is_applied ? '<span class="badge badge-applied">✓ APPLIED</span>' : ''}
                    ${job.fit_score ? `<span class="badge badge-remote">FIT: ${(job.fit_score * 100).toFixed(0)}%</span>` : ''}
                </div>
            </div>
        `).join('');
    }
}

function closeJobsPanel() {
    hidePanel('jobs-panel', { addToTray: false, silent: true });
}

// View Job Details
async function viewJobDetails(jobId) {
    log('info', `Loading details for job: ${jobId}...`);
    
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/job-details/${jobId}`);
        
        if (response.ok) {
            const data = await response.json();
            if (data.results.length > 0) {
                displayJobDetail(data.results[0]);
            }
        }
    } catch (error) {
        log('error', `Failed to load job details: ${error.message}`);
    }
}

function displayJobDetail(job) {
    const detailHtml = `
        <div style="line-height: 1.6;">
            <h2 style="color: #00ff00; margin-bottom: 20px;">${job.title}</h2>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #00aaaa;">COMPANY:</strong> ${job.company || 'N/A'}<br>
                <strong style="color: #00aaaa;">LOCATION:</strong> ${job.location_raw || 'N/A'}<br>
                <strong style="color: #00aaaa;">TYPE:</strong> ${job.location_type || 'N/A'}<br>
                <strong style="color: #00aaaa;">EXPERIENCE:</strong> ${job.experience_level || 'N/A'}<br>
            </div>
            
            ${job.good_fit !== null ? `
                <div style="margin-bottom: 15px; padding: 10px; border: 1px solid #00ff00; background: rgba(0,255,0,0.05);">
                    <strong style="color: #00ff00;">AI FIT ANALYSIS:</strong><br>
                    Good Fit: ${job.good_fit ? '✓ YES' : '✗ NO'}<br>
                    Fit Score: ${job.fit_score ? (job.fit_score * 100).toFixed(0) + '%' : 'N/A'}<br>
                    Confidence: ${job.ai_confidence_score ? (job.ai_confidence_score * 100).toFixed(0) + '%' : 'N/A'}
                </div>
            ` : ''}
            
            ${job.job_description ? `
                <div style="margin-bottom: 15px;">
                    <strong style="color: #00aaaa;">DESCRIPTION:</strong><br>
                    <div style="max-height: 300px; overflow-y: auto; padding: 10px; background: rgba(0,0,0,0.3);">
                        ${job.job_description.substring(0, 1000)}${job.job_description.length > 1000 ? '...' : ''}
                    </div>
                </div>
            ` : ''}
            
            <div style="margin-top: 20px; text-align: center;">
                <button class="retro-btn" onclick="window.open('${job.job_url}', '_blank')" 
                        style="display: inline-block; width: auto; margin: 5px;">
                    🔗 OPEN IN LINKEDIN
                </button>
                ${!job.is_applied && job.good_fit ? `
                    <button class="retro-btn" onclick="applyToSingleJob('${job.job_id}')" 
                            style="display: inline-block; width: auto; margin: 5px;">
                        ✉️ APPLY NOW
                    </button>
                ` : ''}
            </div>
        </div>
    `;
    openModal('JOB DETAILS', detailHtml);
}

// Enrich Jobs
async function enrichJobs() {
    log('info', 'Starting AI enrichment process...');
    log('info', 'This will analyze jobs and generate application answers...');
    
    const runId = state.currentRunId || prompt('Enter run_id to enrich (or leave blank for all):');

    const enrichmentLabel = runId ? `Enrich • ${truncateText(runId, 42)}` : 'Enrich • All runs';
    const pendingToast = showToast('Enrichment started...', 'pending', { sticky: true });
    const operation = createOperation({
        label: enrichmentLabel,
        action: 'enrich',
        meta: {
            context: runId ? `Run: ${runId}` : 'Scope: All'
        }
    });
    
    try {
        const payload = runId ? { run_id: runId } : {};
        
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/enrich-and-generate-answers/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            const result = await response.json();
            log('success', 'Enrichment completed!');
            log('info', `Processed: ${result.result?.jobs_processed || 0} jobs`);
            loadStats();

            if (operation) {
                finalizeOperation(operation.id, 'success', `Processed ${result.result?.jobs_processed || 0} jobs`, {
                    runId: runId || null,
                    meta: {
                        ...operation.meta,
                        context: runId ? `Run: ${runId}` : 'Scope: All'
                    }
                });
            }

            if (pendingToast) {
                updateToast(pendingToast, {
                    message: `Enrichment finished (${result.result?.jobs_processed || 0} jobs)`,
                    type: 'success',
                    autoClose: 4500
                });
            }

            refreshActionRuns(true);
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Enrichment failed: ${error.message}`);

        if (operation) {
            finalizeOperation(operation.id, 'error', error.message);
        }

        if (pendingToast) {
            updateToast(pendingToast, {
                message: `Enrichment failed: ${error.message}`,
                type: 'error',
                autoClose: 6000
            });
        }
    }
}

// View Good Fit Jobs
async function viewGoodFitJobs() {
    log('info', 'Loading good fit jobs...');
    
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/good-fit-jobs`);
        
        if (response.ok) {
            const jobs = await response.json();
            state.jobs = jobs;
            displayJobs(state.jobs);
            log('success', `Loaded ${jobs.length} good fit jobs`);
        }
    } catch (error) {
        log('error', `Failed to load good fit jobs: ${error.message}`);
    }
}

// Apply to Jobs
function showApplyMenu() {
    const menuHtml = `
        <div style="display: flex; flex-direction: column; gap: 15px;">
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 15px;">
                <div style="border: 1px solid #00ff00; padding: 15px; background: rgba(0, 255, 0, 0.05);">
                    <div style="font-weight: bold; margin-bottom: 12px; color: #00ff00; letter-spacing: 2px;">
                        BATCH ACTIONS
                    </div>
                    <button class="retro-btn" onclick="applyToGoodFitJobs()" style="width: 100%; margin: 0 0 10px 0;">
                        ▶ APPLY TO ALL GOOD FITS
                    </button>
                    <button class="retro-btn" onclick="showBatchApplyByRunIdForm()" style="width: 100%; margin: 0;">
                        ▶ BATCH APPLY BY RUN ID
                    </button>
                </div>
                <div style="border: 1px solid #00ff00; padding: 15px; background: rgba(0, 255, 0, 0.05);">
                    <div style="font-weight: bold; margin-bottom: 12px; color: #00ff00; letter-spacing: 2px;">
                        TARGETED ACTIONS
                    </div>
                    <button class="retro-btn" onclick="applyToSelectedJobs()" style="width: 100%; margin: 0 0 10px 0;">
                        ▶ APPLY TO SELECTED JOBS
                    </button>
                    <button class="retro-btn" onclick="showApplyByUrlForm()" style="width: 100%; margin: 0;">
                        ▶ APPLY BY URL
                    </button>
                </div>
            </div>
            <p style="margin: 0; color: #ffaa00; text-align: center;">
                ⚠️ WARNING: Automated applications will use your saved profile details.
            </p>
        </div>
    `;
    openModal('APPLICATION MENU', menuHtml);
}

function showBatchApplyByRunIdForm() {
    const defaultRunId = state.currentRunId || '';
    const formHtml = `
        <form id="batch-apply-run-form" onsubmit="submitBatchApplyByRunId(event)">
            <div class="form-group">
                <label class="form-label">RUN ID</label>
                <input type="text" class="form-input" id="batch-run-id" value="${defaultRunId}" required
                       placeholder="search_YYYYMMDD_HHMMSS">
            </div>
            <div class="form-group">
                <label class="form-label">MAX APPLICATIONS</label>
                <input type="number" class="form-input" id="batch-max-applications" value="10" min="1" max="100">
            </div>
            <div class="form-group">
                <label class="form-label">
                    <input type="checkbox" class="form-checkbox" id="batch-headless" checked>
                    Run in headless mode (recommended)
                </label>
            </div>
            <div class="form-group">
                <label class="form-label">
                    <input type="checkbox" class="form-checkbox" id="batch-allow-submit">
                    Actually submit applications (unchecked = dry run)
                </label>
            </div>
            <button type="submit" class="retro-btn">▶ START BATCH APPLY</button>
        </form>
    `;
    openModal('BATCH APPLY BY RUN ID', formHtml);
}

async function submitBatchApplyByRunId(event) {
    event.preventDefault();

    const runId = document.getElementById('batch-run-id').value.trim();
    const maxApplicationsInput = parseInt(document.getElementById('batch-max-applications').value, 10);
    const headless = document.getElementById('batch-headless').checked;
    const allowSubmit = document.getElementById('batch-allow-submit').checked;

    if (!runId) {
        log('error', 'Run ID is required to start a batch apply operation.');
        return;
    }

    const maxApplications = Number.isNaN(maxApplicationsInput) ? 10 : Math.max(1, maxApplicationsInput);

    closeModal();
    log('info', `Starting batch apply for run: ${runId} (max ${maxApplications} jobs)...`);
    if (!allowSubmit) {
        log('warning', 'DRY RUN mode - applications will NOT be submitted. Enable "Actually submit" to apply for real.');
    }
    log('info', 'This process may take several minutes depending on the number of jobs.');

    const metaContextParts = [`Max ${maxApplications} jobs`, headless ? 'Headless' : 'Visible browser'];
    if (!allowSubmit) {
        metaContextParts.push('Dry run');
    }

    const pendingToast = showToast(`Batch apply started for ${runId}`, 'pending', { sticky: true });
    const operation = createOperation({
        label: `Batch Apply • ${truncateText(runId, 42)}`,
        action: 'batch-apply',
        meta: {
            context: metaContextParts.join(' • ')
        }
    });

    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/batch-apply-by-run-id/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                run_id: runId,
                headless: headless,
                allow_submit: allowSubmit,
                max_applications: maxApplications
            })
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        const result = await response.json();
        const payload = result.result || {};

        if (payload.success) {
            log('success', `Batch apply completed for run: ${runId}`);

            if (typeof payload.applied === 'number' || typeof payload.skipped === 'number' || typeof payload.failed === 'number') {
                log('info', `Applied: ${payload.applied || 0} | Skipped: ${payload.skipped || 0} | Failed: ${payload.failed || 0}`);
            }

            if (payload.message) {
                log('info', payload.message);
            }

            if (Array.isArray(payload.results) && payload.results.length > 0) {
                const preview = payload.results.slice(0, 5);
                preview.forEach(item => {
                    const status = item.status || item.result || 'completed';
                    log('info', `• ${item.job_id || 'job'} - ${status}`);
                });
                if (payload.results.length > preview.length) {
                    log('info', `…and ${payload.results.length - preview.length} more results.`);
                }
            }
        } else {
            const errorMessage = payload.error || payload.message || 'Unknown error during batch apply.';
            log('error', `Batch apply failed: ${errorMessage}`);
        }

        loadStats();

        if (operation) {
            if (payload.success) {
                const detailMessage = `Applied: ${payload.applied || 0} • Skipped: ${payload.skipped || 0} • Failed: ${payload.failed || 0}`;
                finalizeOperation(operation.id, 'success', detailMessage, {
                    runId,
                    meta: {
                        ...operation.meta,
                        context: metaContextParts.join(' • ')
                    }
                });
            } else {
                const errorMessage = payload.error || payload.message || 'Unknown error';
                finalizeOperation(operation.id, 'error', errorMessage);
            }
        }

        if (pendingToast) {
            if (payload.success) {
                updateToast(pendingToast, {
                    message: `Batch apply finished • Applied ${payload.applied || 0}`,
                    type: 'success',
                    autoClose: 4500
                });
            } else {
                updateToast(pendingToast, {
                    message: `Batch apply failed: ${payload.error || payload.message || 'Unknown error'}`,
                    type: 'error',
                    autoClose: 6500
                });
            }
        }

        refreshActionRuns(true);
    } catch (error) {
        log('error', `Batch apply failed: ${error.message}`);

        if (operation) {
            finalizeOperation(operation.id, 'error', error.message);
        }

        if (pendingToast) {
            updateToast(pendingToast, {
                message: `Batch apply failed: ${error.message}`,
                type: 'error',
                autoClose: 6500
            });
        }
    }
}

// Apply by URL Form
function showApplyByUrlForm() {
    const formHtml = `
        <form onsubmit="applyByUrl(event)">
            <div class="form-group">
                <label>LinkedIn Job URL or ID:</label>
                <input type="text" id="apply-job-url" required 
                       placeholder="https://www.linkedin.com/jobs/view/1234567890 or just 1234567890">
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="apply-headless" checked>
                    Run in headless mode (no visible browser)
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="apply-allow-submit">
                    Actually submit application (unchecked = dry run)
                </label>
            </div>
            <button type="submit" class="retro-btn">▶ APPLY NOW</button>
        </form>
    `;
    openModal('APPLY BY URL', formHtml);
}

// Execute Apply by URL
async function applyByUrl(event) {
    event.preventDefault();
    closeModal();
    
    const jobUrl = document.getElementById('apply-job-url').value;
    const headless = document.getElementById('apply-headless').checked;
    const allowSubmit = document.getElementById('apply-allow-submit').checked;
    
    log('info', `Applying to job: ${jobUrl}...`);
    if (!allowSubmit) {
        log('warning', 'DRY RUN mode - application will NOT be submitted');
    }
    log('info', 'This may take a few minutes...');

    const contextParts = [headless ? 'Headless' : 'Visible browser'];
    if (!allowSubmit) {
        contextParts.push('Dry run');
    }

    const pendingToast = showToast(`Starting Easy Apply for ${truncateText(jobUrl, 48)}`, 'pending', { sticky: true });
    const operation = createOperation({
        label: `Apply • ${truncateText(jobUrl, 42)}`,
        action: 'apply-single',
        meta: {
            context: contextParts.join(' • ')
        }
    });
    
    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/apply-to-job-by-url/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_url: jobUrl,
                headless: headless,
                allow_submit: allowSubmit
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.result?.success) {
                log('success', 'Application completed!');
                log('info', `Job ID: ${result.result.job_id || 'unknown'}`);
                if (result.result.easy_apply_available === false) {
                    log('warning', 'Job does not have Easy Apply option');
                }

                if (operation) {
                    finalizeOperation(operation.id, 'success', 'Application completed', {
                        runId: result.result?.run_id || null,
                        meta: {
                            ...operation.meta,
                            context: contextParts.join(' • ')
                        }
                    });
                }

                if (pendingToast) {
                    updateToast(pendingToast, {
                        message: 'Application completed successfully',
                        type: 'success',
                        autoClose: 4500
                    });
                }
            } else {
                log('error', `Application failed: ${result.result?.error || 'Unknown error'}`);

                if (operation) {
                    finalizeOperation(operation.id, 'error', result.result?.error || 'Unknown error');
                }

                if (pendingToast) {
                    updateToast(pendingToast, {
                        message: `Application failed: ${result.result?.error || 'Unknown error'}`,
                        type: 'error',
                        autoClose: 6000
                    });
                }
            }
            loadStats();
            refreshActionRuns(true);
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Application failed: ${error.message}`);

        if (operation) {
            finalizeOperation(operation.id, 'error', error.message);
        }

        if (pendingToast) {
            updateToast(pendingToast, {
                message: `Application failed: ${error.message}`,
                type: 'error',
                autoClose: 6000
            });
        }
    }
}

// Check Ready Jobs
async function checkReadyJobs() {
    log('info', 'Checking which jobs are ready to apply...');
    log('info', 'This queries the database for enriched jobs with good fit scores...');

    const pendingToast = showToast('Scanning for ready jobs...', 'pending', { sticky: true });
    const operation = createOperation({
        label: 'Check Ready Jobs',
        action: 'check-ready',
        meta: {
            context: 'Filtering enriched answers'
        }
    });
    
    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/check-which-jobs-ready/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        if (response.ok) {
            const result = await response.json();
            const stats = result.result?.filtering_stats || {};
            const jobIds = result.result?.job_ids_ready || [];
            
            log('success', `✓ Found ${jobIds.length} jobs ready to apply!`);
            log('info', `📊 Statistics:`);
            log('info', `  • Total with answers: ${stats.total_with_answers || 0}`);
            log('info', `  • Already applied: ${stats.already_applied || 0}`);
            log('info', `  • Bad fit filtered: ${stats.bad_fit_filtered || 0}`);
            log('info', `  • Ready to apply: ${stats.ready_to_apply || 0}`);
            
            if (jobIds.length > 0) {
                log('info', `📋 Loading full job details for ${jobIds.length} jobs...`);
                
                // Fetch full job details from database
                const jobIdsParam = jobIds.join(',');
                const dbResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/jobs-by-ids?ids=${encodeURIComponent(jobIdsParam)}`);
                
                if (dbResponse.ok) {
                    const data = await dbResponse.json();
                    displayReadyJobs(data.results);
                    log('success', `✓ Jobs displayed in Job Listings panel below!`);
                    log('info', `💡 Scroll down to see the full list and apply to individual jobs`);

                    if (operation) {
                        finalizeOperation(operation.id, 'success', `Ready to apply: ${jobIds.length}`, {
                            meta: {
                                ...operation.meta,
                                context: `Ready: ${jobIds.length} • Total answers: ${stats.total_with_answers || 0}`
                            }
                        });
                    }

                    if (pendingToast) {
                        updateToast(pendingToast, {
                            message: `${jobIds.length} jobs ready to apply`,
                            type: 'success',
                            autoClose: 4500
                        });
                    }
                } else {
                    throw new Error('Failed to fetch job details from database');
                }
            } else {
                displayReadyJobs([]);
                log('warning', '⚠️ No jobs ready to apply. Make sure to:');
                log('info', '  1. Run a job search first');
                log('info', '  2. Run AI enrichment to analyze jobs');
                log('info', '  3. Check that you have a profile uploaded');

                if (operation) {
                    finalizeOperation(operation.id, 'success', 'No jobs ready yet', {
                        meta: {
                            ...operation.meta,
                            context: `Answers: ${stats.total_with_answers || 0} • Ready: 0`
                        }
                    });
                }

                if (pendingToast) {
                    updateToast(pendingToast, {
                        message: 'No jobs are ready yet. Try enriching first.',
                        type: 'warning',
                        autoClose: 5500
                    });
                }
            }
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `❌ Check failed: ${error.message}`);
        log('error', 'Make sure the Action Server is running and accessible');

        if (operation) {
            finalizeOperation(operation.id, 'error', error.message);
        }

        if (pendingToast) {
            updateToast(pendingToast, {
                message: `Ready check failed: ${error.message}`,
                type: 'error',
                autoClose: 6500
            });
        }
    }
}

// Display Ready Jobs in Panel
function displayReadyJobs(jobs) {
    showPanel('jobs-panel');
    const jobsPanel = document.getElementById('jobs-panel');
    const jobsContent = document.getElementById('jobs-content');
    
    if (!jobs || jobs.length === 0) {
        jobsContent.innerHTML = '<div class="job-item" style="text-align: center; color: #ffaa00;">NO JOBS READY TO APPLY</div>';
        return;
    }
    
    let html = '';
    
    jobs.forEach((job, index) => {
        const fitScore = job.fit_score ? (job.fit_score * 100).toFixed(0) : '0';
        html += `
            <div class="job-item" style="border-left: 3px solid #00ff00;">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                    <div style="flex: 1;">
                        <div class="job-title">${index + 1}. ${job.title || 'Unknown Title'}</div>
                        <div class="job-company">${job.company || 'Unknown Company'}</div>
                        <div class="job-meta">${job.location_raw || 'Location not specified'}</div>
                        ${job.date_posted ? `<div class="job-meta" style="margin-top: 5px;">Posted: ${job.date_posted}</div>` : ''}
                    </div>
                    <div style="text-align: right;">
                        <span class="badge badge-fit" style="font-size: 18px; padding: 8px 12px;">
                            ✓ ${fitScore}% FIT
                        </span>
                    </div>
                </div>
                <div class="job-badges" style="margin-top: 10px; display: flex; gap: 10px;">
                    <button class="retro-btn" onclick="applyToSingleJob('${job.job_id}')" 
                            style="flex: 1; margin: 0; padding: 10px; font-size: 18px;">
                        ⚡ APPLY NOW
                    </button>
                    <a href="${job.job_url}" target="_blank" class="retro-btn" 
                       style="flex: 1; margin: 0; padding: 10px; font-size: 18px; text-decoration: none; display: block; text-align: center;">
                        🔗 VIEW ON LINKEDIN
                    </a>
                    <button class="retro-btn" onclick="viewJobDetails('${job.job_id}')" 
                            style="margin: 0; padding: 10px; font-size: 18px;">
                        📋 DETAILS
                    </button>
                </div>
            </div>
        `;
    });
    
    jobsContent.innerHTML = html;
    log('info', `Displaying ${jobs.length} ready jobs in Job Listings panel below`);
}

async function applyToGoodFitJobs() {
    closeModal();
    log('info', 'Starting batch application to all good fit jobs...');
    log('warning', 'This may take several minutes per job...');
    
    // Implementation would call the batch apply action
    log('info', 'Feature in development - use individual apply for now');
}

async function applyToSingleJob(jobId) {
    closeModal();
    
    // Show confirmation modal with options
    const confirmHtml = `
        <div style="text-align: center;">
            <p style="margin-bottom: 20px;">Apply to job: <strong>${jobId}</strong></p>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="confirm-headless" checked>
                    Run in headless mode (no visible browser)
                </label>
            </div>
            <div class="form-group">
                <label>
                    <input type="checkbox" id="confirm-submit" checked>
                    Actually submit application (uncheck for dry run)
                </label>
            </div>
            <button class="retro-btn" onclick="confirmApply('${jobId}')">✅ CONFIRM & APPLY</button>
            <button class="retro-btn" onclick="closeModal()">❌ CANCEL</button>
        </div>
    `;
    openModal('CONFIRM APPLICATION', confirmHtml);
}

async function confirmApply(jobId) {
    const headless = document.getElementById('confirm-headless').checked;
    const allowSubmit = document.getElementById('confirm-submit').checked;
    
    closeModal();
    log('info', `Applying to job: ${jobId} using prepared answers...`);
    if (!allowSubmit) {
        log('warning', 'DRY RUN mode - application will NOT be submitted');
    }

    const contextParts = [headless ? 'Headless' : 'Visible browser'];
    if (!allowSubmit) {
        contextParts.push('Dry run');
    }

    const pendingToast = showToast(`Applying to ${jobId}`, 'pending', { sticky: true });
    const operation = createOperation({
        label: `Apply Prepared • ${truncateText(jobId, 36)}`,
        action: 'apply-single',
        meta: {
            context: contextParts.join(' • ')
        }
    });
    
    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/apply-to-single-job/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                job_id: jobId,
                headless: headless,
                allow_submit: allowSubmit
            })
        });
        
        if (response.ok) {
            const result = await response.json();
            if (result.result?.success) {
                log('success', `Application completed for job: ${jobId}`);
                if (result.result.easy_apply_available === false) {
                    log('warning', 'Job does not have Easy Apply option');
                }

                if (operation) {
                    finalizeOperation(operation.id, 'success', 'Application submitted', {
                        runId: result.result?.run_id || null,
                        meta: {
                            ...operation.meta,
                            context: contextParts.join(' • ')
                        }
                    });
                }

                if (pendingToast) {
                    updateToast(pendingToast, {
                        message: `Application completed for ${jobId}`,
                        type: 'success',
                        autoClose: 4500
                    });
                }
            } else {
                log('error', `Application failed: ${result.result?.error || 'Unknown error'}`);

                if (operation) {
                    finalizeOperation(operation.id, 'error', result.result?.error || 'Unknown error');
                }

                if (pendingToast) {
                    updateToast(pendingToast, {
                        message: `Application failed: ${result.result?.error || 'Unknown error'}`,
                        type: 'error',
                        autoClose: 6000
                    });
                }
            }
            loadStats();
            refreshActionRuns(true);
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Application failed: ${error.message}`);

        if (operation) {
            finalizeOperation(operation.id, 'error', error.message);
        }

        if (pendingToast) {
            updateToast(pendingToast, {
                message: `Application failed: ${error.message}`,
                type: 'error',
                autoClose: 6000
            });
        }
    }
}

// View Profile
async function viewProfile() {
    log('info', 'Loading active profile...');
    
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/profile`);
        
        if (response.ok) {
            const data = await response.json();
            if (data.results.length > 0) {
                displayProfile(data.results[0]);
            } else {
                openModal('PROFILE', '<div style="text-align: center; color: #ff3333;">NO ACTIVE PROFILE FOUND</div>');
            }
        }
    } catch (error) {
        log('error', `Failed to load profile: ${error.message}`);
    }
}

function displayProfile(profile) {
    const profileHtml = `
        <div style="line-height: 1.6;">
            <h2 style="color: #00ff00; margin-bottom: 20px;">${profile.profile_name || 'User Profile'}</h2>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #00aaaa;">NAME:</strong> ${profile.full_name || 'N/A'}<br>
                <strong style="color: #00aaaa;">EMAIL:</strong> ${profile.email || 'N/A'}<br>
                <strong style="color: #00aaaa;">PHONE:</strong> ${profile.phone || 'N/A'}<br>
                <strong style="color: #00aaaa;">LOCATION:</strong> ${profile.location || 'N/A'}<br>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #00aaaa;">WORK AUTHORIZATION:</strong> ${profile.work_authorization || 'N/A'}<br>
                <strong style="color: #00aaaa;">EXPERIENCE:</strong> ${profile.years_of_experience || 'N/A'} years<br>
                <strong style="color: #00aaaa;">SALARY RANGE:</strong> $${profile.salary_min || 'N/A'} - $${profile.salary_max || 'N/A'}<br>
            </div>
            
            <div style="margin-bottom: 15px;">
                <strong style="color: #00aaaa;">APPLICATIONS:</strong> ${profile.applications_count || 0}<br>
                <strong style="color: #00aaaa;">SUCCESS RATE:</strong> ${profile.success_rate ? (profile.success_rate * 100).toFixed(1) + '%' : 'N/A'}<br>
                <strong style="color: #00aaaa;">LAST USED:</strong> ${profile.last_used_at ? new Date(profile.last_used_at).toLocaleString() : 'Never'}<br>
            </div>
        </div>
    `;
    openModal('ACTIVE PROFILE', profileHtml);
}

// View Application History
async function viewApplicationHistory() {
    log('info', 'Loading application history...');
    
    try {
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/application-history`);
        
        if (response.ok) {
            const data = await response.json();
            displayApplicationHistory(data.results);
        }
    } catch (error) {
        log('error', `Failed to load history: ${error.message}`);
    }
}

function displayApplicationHistory(applications) {
    const tableHtml = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>TITLE</th>
                    <th>COMPANY</th>
                    <th>DATE APPLIED</th>
                </tr>
            </thead>
            <tbody>
                ${applications.map(app => `
                    <tr onclick="viewJobDetails('${app.job_id}')" style="cursor: pointer;">
                        <td>${app.title}</td>
                        <td>${app.company}</td>
                        <td>${new Date(app.updated_at).toLocaleString()}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
    openModal('APPLICATION HISTORY', tableHtml);
}

// View Logs
async function viewLogs() {
    log('info', 'Loading available log files from output directory...');
    
    try {
        // Use the proxy server to query for action runs
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query/runs-with-stats`);
        
        if (response.ok) {
            const data = await response.json();
            displayLogsList(data.results);
        } else {
            throw new Error('Failed to fetch log data');
        }
    } catch (error) {
        log('error', `Failed to load logs: ${error.message}`);
        // Fallback to basic message
        const logContent = `
            <div style="color: #ff3333; text-align: center;">
                <h3>Unable to load logs from database</h3>
                <p style="margin: 20px 0;">
                    Error: ${error.message}
                </p>
                <p>
                    Log files are stored in: <strong>output/</strong> directory<br>
                    Each run creates a folder with log.html inside.
                </p>
            </div>
        `;
        openModal('LOG FILES', logContent);
    }
}

function displayLogsList(runs) {
    const tableHtml = `
        <div style="margin-bottom: 15px; color: #00aaaa;">
            <strong>Available Action Logs</strong><br>
            <span style="font-size: 16px;">Each run creates detailed logs with screenshots in the output/ directory</span>
        </div>
        <table class="data-table">
            <thead>
                <tr>
                    <th>RUN ID</th>
                    <th>TYPE</th>
                    <th>JOBS</th>
                    <th>APPLIED</th>
                    <th>TIMESTAMP</th>
                    <th>ACTIONS</th>
                </tr>
            </thead>
            <tbody>
                ${runs.map(run => {
                    const runType = run.run_id.split('_')[0].toUpperCase();
                    const appliedCount = run.applied_jobs ? run.applied_jobs.split(',').length : 0;
                    const timestamp = run.timestamp ? new Date(run.timestamp).toLocaleString() : 'N/A';
                    const logPath = `output/${run.run_id}/log.html`;
                    
                    return `
                        <tr>
                            <td style="font-family: 'VT323', monospace; font-size: 14px;">${run.run_id}</td>
                            <td>
                                <span class="badge ${runType === 'SEARCH' ? 'badge-fit' : runType === 'APPLY' ? 'badge-applied' : 'badge-remote'}">
                                    ${runType}
                                </span>
                            </td>
                            <td>${run.job_count || 0}</td>
                            <td>${appliedCount}</td>
                            <td style="font-size: 14px;">${timestamp}</td>
                            <td>
                                <button class="retro-btn" 
                                        onclick="openLogFile('${run.run_id}')" 
                                        style="margin: 0; padding: 5px 10px; font-size: 16px;">
                                    📜 VIEW LOG
                                </button>
                            </td>
                        </tr>
                    `;
                }).join('')}
            </tbody>
        </table>
        <div style="margin-top: 20px; text-align: center; padding: 15px; border: 1px solid #00aaaa; background: rgba(0,170,170,0.1);">
            <strong style="color: #00aaaa;">� TIP:</strong> 
            Log files include detailed execution traces, screenshots, and error messages.<br>
            Files are stored in: <code>output/{run_id}/log.html</code>
        </div>
    `;
    openModal('ACTION LOGS', tableHtml);
}

function openLogFile(runId) {
    // Construct the correct path - going up one level from retro-ui to reach output/
    const logUrl = `/output/${runId}/log.html`;
    log('info', `Opening log file for: ${runId}`);
    log('info', `URL: ${logUrl}`);
    
    // Open in new tab
    const newWindow = window.open(logUrl, '_blank');
    
    // Check if popup was blocked
    if (!newWindow || newWindow.closed || typeof newWindow.closed == 'undefined') {
        log('error', 'Pop-up blocked! Please allow pop-ups for this site.');
        // Fallback: try to navigate in same window
        window.location.href = logUrl;
    }
}

// Modal Functions
function openModal(title, content) {
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-body').innerHTML = content;
    document.getElementById('modal').style.display = 'flex';
}

function closeModal() {
    document.getElementById('modal').style.display = 'none';
}

function applyToSelectedJobs() {
    closeModal();
    log('info', 'Selected job application feature coming soon...');
}

// Export for debugging
window.appState = state;
window.appConfig = CONFIG;
