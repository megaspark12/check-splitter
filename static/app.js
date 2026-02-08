/**
 * Check Splitter - Frontend Application
 * Enhanced UI with per-person tip calculation
 */

const API_BASE = '/api';

// State
let currentSession = null;
let currentParticipant = null;
let isHost = false;
let currentTipPercentage = 10;
let syncInterval = null;
let currency = { code: 'USD', symbol: '$', name: 'US Dollar' };

// WebSocket state
let websocket = null;
let wsReconnectAttempts = 0;
const MAX_WS_RECONNECT_ATTEMPTS = 5;
let wsPingInterval = null;

// Adaptive sync configuration (fallback when WebSocket disconnected)
let lastUserAction = Date.now();
const SYNC_INTERVAL_ACTIVE = 2000;   // 2 seconds when active (fast sync)
const SYNC_INTERVAL_IDLE = 5000;     // 5 seconds when idle
const IDLE_THRESHOLD = 30000;        // 30 seconds to consider idle

// Session History (localStorage)
const SESSION_HISTORY_KEY = 'checkSplitter_sessionHistory';
const LAST_SESSION_KEY = 'checkSplitter_lastSession';
const MAX_HISTORY_ITEMS = 10;

function saveSessionToHistory(code, participantId, participantName, hostName, isHostFlag) {
    const entry = {
        code: code.toUpperCase(),
        participantId,
        participantName,
        hostName,
        isHost: isHostFlag,
        timestamp: Date.now()
    };
    
    // Save as last session for quick rejoin
    localStorage.setItem(LAST_SESSION_KEY, JSON.stringify(entry));
    
    // Add to history (dedup by code)
    let history = getSessionHistory();
    history = history.filter(h => h.code !== entry.code);
    history.unshift(entry);
    history = history.slice(0, MAX_HISTORY_ITEMS);
    localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(history));
}

function getSessionHistory() {
    try {
        return JSON.parse(localStorage.getItem(SESSION_HISTORY_KEY)) || [];
    } catch { return []; }
}

function getLastSession() {
    try {
        return JSON.parse(localStorage.getItem(LAST_SESSION_KEY));
    } catch { return null; }
}

function clearLastSession() {
    localStorage.removeItem(LAST_SESSION_KEY);
}

function touchLastSessionTimestamp() {
    // Update the timestamp of the last session so the 5-min auto-rejoin window stays fresh
    try {
        const last = getLastSession();
        if (last) {
            last.timestamp = Date.now();
            localStorage.setItem(LAST_SESSION_KEY, JSON.stringify(last));
        }
    } catch { /* ignore */ }
}

function removeSessionFromHistory(code) {
    let history = getSessionHistory();
    history = history.filter(h => h.code !== code);
    localStorage.setItem(SESSION_HISTORY_KEY, JSON.stringify(history));
    
    const last = getLastSession();
    if (last && last.code === code) {
        clearLastSession();
    }
}

async function rejoinSession(code) {
    // Look up entry from history
    const history = getSessionHistory();
    const entry = history.find(h => h.code === code);
    if (!entry) {
        showError('Session not found in history');
        return;
    }
    try {
        // First check if session still exists
        const session = await apiRequest(`/sessions/${entry.code}`);
        currentSession = session;
        
        if (entry.isHost) {
            isHost = true;
            currentParticipant = session.participants.find(p => p.is_host);
            currentTipPercentage = currentParticipant?.tip_percentage || 10;
            
            await loadSession(session.code);
            document.getElementById('display-code').textContent = session.code;
            showPage('session');
            updateStepIndicator(session.items?.length > 0 ? 2 : 1);
            showToast('Rejoined your session!', 'success');
        } else {
            // Check if participant still exists in this session
            const existingParticipant = session.participants.find(p => p.id === entry.participantId);
            
            if (existingParticipant) {
                // Rejoin as the same participant
                currentParticipant = existingParticipant;
                currentTipPercentage = existingParticipant.tip_percentage || 10;
                isHost = false;
                
                document.getElementById('participant-session-code').textContent = entry.code;
                document.getElementById('participant-name-display').textContent = existingParticipant.name;
                
                await loadParticipantView();
                showPage('participant');
                showToast('Rejoined the session!', 'success');
            } else {
                // Participant was removed, rejoin as new
                const participant = await apiRequest(`/sessions/${entry.code}/participants`, {
                    method: 'POST',
                    body: JSON.stringify({ name: entry.participantName })
                });
                
                currentParticipant = participant;
                currentTipPercentage = participant.tip_percentage || 10;
                isHost = false;
                
                // Update history with new participant ID
                saveSessionToHistory(entry.code, participant.id, entry.participantName, entry.hostName, false);
                
                document.getElementById('participant-session-code').textContent = entry.code;
                document.getElementById('participant-name-display').textContent = entry.participantName;
                
                await loadParticipantView();
                showPage('participant');
                showToast('Rejoined as new participant!', 'success');
            }
        }
    } catch (error) {
        // Session no longer exists
        removeSessionFromHistory(entry.code);
        showError('Session no longer exists');
        renderSessionHistory();
        hideRejoinBanner();
    }
}

function renderRejoinBanner() {
    const banner = document.getElementById('rejoin-banner');
    if (!banner) return;
    
    const last = getLastSession();
    if (!last) {
        banner.style.display = 'none';
        return;
    }
    
    // Only show banner for sessions created/joined in the last 6 hours
    const sixHours = 6 * 60 * 60 * 1000;
    if (Date.now() - last.timestamp > sixHours) {
        banner.style.display = 'none';
        return;
    }
    
    const roleText = last.isHost ? 'Host' : 'Guest';
    const sessionLabel = last.isHost 
        ? `Your session (${last.code})` 
        : `${last.hostName}'s session (${last.code})`;
    
    banner.innerHTML = `
        <div class="rejoin-content">
            <div class="rejoin-info">
                <span class="rejoin-icon">⚡</span>
                <div>
                    <div class="rejoin-title">Continue where you left off?</div>
                    <div class="rejoin-detail">${sessionLabel} • ${roleText}</div>
                </div>
            </div>
            <div class="rejoin-actions">
                <button class="btn btn-primary btn-small rejoin-btn" onclick="rejoinSession('${last.code}')">Rejoin</button>
                <button class="btn btn-ghost btn-small rejoin-dismiss" onclick="dismissRejoinBanner()">✕</button>
            </div>
        </div>
    `;
    banner.style.display = 'block';
}

function dismissRejoinBanner() {
    const banner = document.getElementById('rejoin-banner');
    if (banner) {
        banner.style.display = 'none';
    }
    clearLastSession();
}

function hideRejoinBanner() {
    const banner = document.getElementById('rejoin-banner');
    if (banner) banner.style.display = 'none';
}

function renderSessionHistory() {
    const container = document.getElementById('session-history-panel');
    if (!container) return;
    
    const history = getSessionHistory();
    
    if (history.length === 0) {
        container.style.display = 'none';
        return;
    }
    
    container.style.display = 'block';
    const list = container.querySelector('.session-history-list');
    if (!list) return;
    
    list.innerHTML = history.map(entry => {
        const timeAgo = getTimeAgo(new Date(entry.timestamp).toISOString());
        const roleIcon = entry.isHost ? '👑' : '👤';
        const roleText = entry.isHost ? 'Host' : 'Guest';
        const sessionLabel = entry.isHost 
            ? 'Your session' 
            : `${entry.hostName}'s session`;
        
        return `
            <div class="history-item" onclick="rejoinSession('${entry.code}')">
                <div class="history-item-info">
                    <div class="history-item-top">
                        <span class="history-role">${roleIcon} ${roleText}</span>
                        <span class="history-code">${entry.code}</span>
                    </div>
                    <div class="history-item-detail">
                        ${sessionLabel} • ${entry.participantName} • ${timeAgo}
                    </div>
                </div>
                <span class="history-join-arrow">→</span>
            </div>
        `;
    }).join('');
}

// DOM Elements
const pages = {
    landing: document.getElementById('landing-page'),
    session: document.getElementById('session-page'),
    participant: document.getElementById('participant-page')
};

// Track user activity for adaptive sync
function trackUserAction() {
    lastUserAction = Date.now();
}

// Utility Functions
function showPage(pageName) {
    Object.values(pages).forEach(page => page.classList.remove('active'));
    pages[pageName].classList.add('active');
    
    // Manage sync based on page
    if (pageName === 'landing') {
        stopSync();
        // Refresh landing page data
        renderRejoinBanner();
        renderSessionHistory();
        fetchNearbySessions();
    } else {
        startSync();
    }
}

function getSyncInterval() {
    const timeSinceAction = Date.now() - lastUserAction;
    return timeSinceAction > IDLE_THRESHOLD ? SYNC_INTERVAL_IDLE : SYNC_INTERVAL_ACTIVE;
}

function startSync() {
    if (syncInterval) return; // Already syncing
    
    // Connect WebSocket for real-time updates
    connectWebSocket();
    
    const doSync = async () => {
        if (!currentSession) return;
        
        try {
            await syncSession();
        } catch (error) {
            // Sync errors are handled inside syncSession
        }
        
        // Schedule next sync with adaptive interval (fallback polling)
        if (syncInterval) {
            clearTimeout(syncInterval);
            syncInterval = setTimeout(doSync, getSyncInterval());
        }
    };
    
    // Start with active interval
    syncInterval = setTimeout(doSync, SYNC_INTERVAL_ACTIVE);
}

function stopSync() {
    if (syncInterval) {
        clearTimeout(syncInterval);
        syncInterval = null;
    }
    disconnectWebSocket();
}

// WebSocket Functions
function connectWebSocket() {
    if (!currentSession) return;
    
    // Don't connect if already connected
    if (websocket && websocket.readyState === WebSocket.OPEN) return;
    
    // Build WebSocket URL
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/sessions/ws/${currentSession.code}`;
    
    try {
        websocket = new WebSocket(wsUrl);
        
        websocket.onopen = () => {
            console.log('WebSocket connected');
            wsReconnectAttempts = 0;
            
            // Start ping interval to keep connection alive
            if (wsPingInterval) clearInterval(wsPingInterval);
            wsPingInterval = setInterval(() => {
                if (websocket && websocket.readyState === WebSocket.OPEN) {
                    websocket.send(JSON.stringify({ type: 'ping' }));
                }
            }, 30000); // Ping every 30 seconds
        };
        
        websocket.onmessage = async (event) => {
            try {
                const data = JSON.parse(event.data);
                
                if (data.type === 'sync') {
                    // Session data was updated, refresh the view
                    await syncSession();
                } else if (data.type === 'pong') {
                    // Pong received, connection is alive
                }
            } catch (error) {
                console.error('WebSocket message error:', error);
            }
        };
        
        websocket.onclose = (event) => {
            console.log('WebSocket closed:', event.code, event.reason);
            if (wsPingInterval) {
                clearInterval(wsPingInterval);
                wsPingInterval = null;
            }
            
            // Attempt reconnection if not intentionally closed
            if (currentSession && wsReconnectAttempts < MAX_WS_RECONNECT_ATTEMPTS) {
                wsReconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts), 30000);
                console.log(`WebSocket reconnecting in ${delay}ms (attempt ${wsReconnectAttempts})`);
                setTimeout(connectWebSocket, delay);
            }
        };
        
        websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
        
    } catch (error) {
        console.error('Failed to create WebSocket:', error);
    }
}

function disconnectWebSocket() {
    if (wsPingInterval) {
        clearInterval(wsPingInterval);
        wsPingInterval = null;
    }
    if (websocket) {
        websocket.close();
        websocket = null;
    }
    wsReconnectAttempts = 0;
}

async function syncSession() {
    try {
        const session = await apiRequest(`/sessions/${currentSession.code}`);
        
        // Keep last-session timestamp fresh so auto-rejoin works after refresh
        touchLastSessionTimestamp();
        
        // Check if current participant was removed (for non-hosts)
        if (!isHost && currentParticipant) {
            const stillInSession = session.participants.some(p => p.id === currentParticipant.id);
            if (!stillInSession) {
                // Participant was removed by host
                stopSync();
                currentSession = null;
                currentParticipant = null;
                showToast('You have been removed from the session', 'warning', 4000);
                showPage('landing');
                return;
            }
            
            // Update current participant's data (tip changes from server)
            const updatedParticipant = session.participants.find(p => p.id === currentParticipant.id);
            if (updatedParticipant) {
                currentParticipant = updatedParticipant;
            }
        }
        
        // Check if any data changed (items, participants, discounts, or assignments)
        const oldDataJson = JSON.stringify({
            items: currentSession.items,
            participants: currentSession.participants,
            discounts: currentSession.discounts || []
        });
        const newDataJson = JSON.stringify({
            items: session.items,
            participants: session.participants,
            discounts: session.discounts || []
        });
        
        const hasChanges = oldDataJson !== newDataJson;
        currentSession = session;
        
        if (isHost) {
            // Update host view when data changes
            if (hasChanges) {
                renderParticipantsList();
                updateDiscountParticipantDropdown();
                renderDiscountsList();  // Use session.discounts directly, no API call
                if (session.items && session.items.length > 0) {
                    displayItems(session.items, session.participants);
                    updateHostTotal();
                }
            }
            // Always update summary to reflect tip changes from participants
            if (session.items && session.items.length > 0) {
                await updateSummary();
            }
        } else {
            // Participant view - always refresh to get latest server-calculated totals
            if (hasChanges) {
                await loadParticipantView();
            } else {
                // Even if no item/participant changes, update totals (discounts may have changed)
                updateYourTotal();
            }
        }
    } catch (error) {
        // Session may have been deleted or expired
        if (error.message.includes('not found') || error.message.includes('404')) {
            stopSync();
            currentSession = null;
            currentParticipant = null;
            showToast('Session has ended', 'warning', 4000);
            showPage('landing');
        }
    }
}

async function updateSummary() {
    try {
        const summary = await apiRequest(`/sessions/${currentSession.code}/summary`);
        
        const content = document.getElementById('summary-content');
        
        content.innerHTML = summary.participants.map(p => {
            const hasDiscount = p.discount_amount && p.discount_amount > 0;
            const discountBadges = p.applied_discounts && p.applied_discounts.length > 0
                ? p.applied_discounts.map(d => `<span class="discount-badge">${d.name}</span>`).join('')
                : '';
            
            let breakdown = `Items: ${formatCurrency(p.items_subtotal)}`;
            if (hasDiscount) {
                breakdown += ` - Discount: ${formatCurrency(p.discount_amount)}`;
            }
            breakdown += ` + Tax: ${formatCurrency(p.tax_share)} + Tip: ${formatCurrency(p.tip_amount)}`;
            
            return `
                <div class="summary-row">
                    <div>
                        <span class="name">${p.participant_name}</span>
                        ${discountBadges ? `<div class="summary-discounts">${discountBadges}</div>` : ''}
                        <div style="font-size: 0.75rem; color: var(--text-muted);">
                            ${breakdown}
                        </div>
                    </div>
                    <span class="amount">${formatCurrency(p.total)}</span>
                </div>
            `;
        }).join('');
        
        // Add total discount row if any discounts applied
        if (summary.total_discount && summary.total_discount > 0) {
            content.innerHTML += `
                <div class="summary-row summary-discount">
                    <span class="name">🏷️ Total Discounts</span>
                    <span class="amount">-${formatCurrency(summary.total_discount)}</span>
                </div>
            `;
        }
        
        // Add unassigned items warning if any
        if (summary.unassigned_total > 0) {
            content.innerHTML += `
                <div class="summary-row" style="border: 1px solid var(--accent);">
                    <span class="name">⚠️ Unassigned Items</span>
                    <span class="amount" style="color: var(--accent);">${formatCurrency(summary.unassigned_total)}</span>
                </div>
            `;
        }
        
        document.getElementById('summary-section').hidden = false;
        
    } catch (error) {
        // Summary not ready yet, hide section
        document.getElementById('summary-section').hidden = true;
    }
}

function formatCurrency(amount) {
    const num = parseFloat(amount) || 0;
    return currency.symbol + num.toFixed(2);
}

// Fetch user's currency based on location
async function fetchUserCurrency() {
    try {
        const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
        const response = await fetch(`${API_BASE}/currency?timezone=${encodeURIComponent(timezone)}`);
        if (response.ok) {
            currency = await response.json();
        }
    } catch (error) {
        // Use default currency
    }
}

async function apiRequest(endpoint, options = {}) {
    const response = await fetch(API_BASE + endpoint, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers
        },
        ...options
    });
    
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || 'Request failed');
    }
    
    if (response.status === 204) return null;
    return response.json();
}

// Toast Notifications
function showToast(message, type = 'info', duration = 3000) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'toast ' + type;
    
    // Trigger reflow for animation
    void toast.offsetWidth;
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, duration);
}

function showError(message) {
    showToast(message, 'error', 4000);
}

function showSuccess(message) {
    showToast(message, 'success', 3000);
}

// Confirmation Modal
function showConfirm(title, message, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    
    const okBtn = document.getElementById('confirm-ok');
    const cancelBtn = document.getElementById('confirm-cancel');
    
    const cleanup = () => {
        modal.classList.remove('active');
        okBtn.replaceWith(okBtn.cloneNode(true));
        cancelBtn.replaceWith(cancelBtn.cloneNode(true));
    };
    
    document.getElementById('confirm-ok').addEventListener('click', () => {
        cleanup();
        onConfirm();
    });
    
    document.getElementById('confirm-cancel').addEventListener('click', cleanup);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) cleanup();
    });
    
    modal.classList.add('active');
}

function updateStepIndicator(step) {
    document.querySelectorAll('.step').forEach((el, index) => {
        el.classList.remove('active', 'completed');
        if (index + 1 < step) el.classList.add('completed');
        if (index + 1 === step) el.classList.add('active');
    });
}

// Session Management
async function createSession(hostName) {
    try {
        const session = await apiRequest('/sessions', {
            method: 'POST',
            body: JSON.stringify({ host_name: hostName })
        });
        
        currentSession = session;
        isHost = true;
        
        // Find the host participant
        currentParticipant = session.participants.find(p => p.is_host);
        currentTipPercentage = currentParticipant?.tip_percentage || 10;
        
        // Save to session history for quick rejoin
        saveSessionToHistory(session.code, currentParticipant?.id, hostName, hostName, true);
        
        await loadSession(session.code);
        
        document.getElementById('display-code').textContent = session.code;
        showPage('session');
        updateStepIndicator(1);
        
    } catch (error) {
        showError('Failed to create session: ' + error.message);
    }
}

async function joinSession(code, name) {
    try {
        const session = await apiRequest(`/sessions/${code}`);
        currentSession = session;
        
        // --- Smart rejoin: check if this user was already in this session ---
        let participant = null;
        let wasRejoined = false;
        
        // 1. Check localStorage for a saved participant ID for this session
        const history = getSessionHistory();
        const savedEntry = history.find(h => h.code === code.toUpperCase());
        if (savedEntry && savedEntry.participantId) {
            participant = session.participants.find(p => p.id === savedEntry.participantId);
            if (participant) wasRejoined = true;
        }
        
        // 2. If not found by ID, check by exact name match (case-insensitive, non-host)
        if (!participant) {
            participant = session.participants.find(
                p => !p.is_host && p.name.toLowerCase() === name.toLowerCase()
            );
            if (participant) wasRejoined = true;
        }
        
        // 3. If still not found, create a new participant
        if (!participant) {
            participant = await apiRequest(`/sessions/${code}/participants`, {
                method: 'POST',
                body: JSON.stringify({ name: name })
            });
        }
        
        currentParticipant = participant;
        currentTipPercentage = participant.tip_percentage || 10;
        isHost = false;
        
        // Save to session history for quick rejoin (use server name for consistency)
        const host = session.participants.find(p => p.is_host);
        saveSessionToHistory(code, participant.id, participant.name, host?.name || 'Unknown', false);
        
        document.getElementById('participant-session-code').textContent = code;
        document.getElementById('participant-name-display').textContent = participant.name;
        
        await loadParticipantView();
        showPage('participant');
        
        if (wasRejoined) {
            showToast('Welcome back! Your selections are preserved.', 'success');
        }
        
    } catch (error) {
        showError('Failed to join session: ' + error.message);
    }
}

// Nearby Sessions (like Spotify Jam)
async function fetchNearbySessions() {
    try {
        const response = await apiRequest('/sessions/nearby');
        const panel = document.getElementById('nearby-sessions-panel');
        const list = document.getElementById('nearby-sessions-list');
        
        if (response.sessions && response.sessions.length > 0) {
            panel.style.display = 'block';
            list.innerHTML = response.sessions.map(session => `
                <div class="nearby-session-item" onclick="openQuickJoinModal('${session.code}', '${session.host_name}')">
                    <div class="nearby-session-info">
                        <span class="nearby-host">🧑‍🍳 ${session.host_name}'s Session</span>
                        <span class="nearby-meta">${session.participant_count} participant${session.participant_count !== 1 ? 's' : ''} • ${getTimeAgo(session.created_at)}</span>
                    </div>
                    <span class="nearby-join-arrow">→</span>
                </div>
            `).join('');
        } else {
            panel.style.display = 'none';
        }
    } catch (error) {
        document.getElementById('nearby-sessions-panel').style.display = 'none';
    }
}

function getTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.floor(diffHours / 24)}d ago`;
}

function openQuickJoinModal(code, hostName) {
    document.getElementById('quick-join-code').value = code;
    document.getElementById('quick-join-host-name').textContent = `Join ${hostName}'s session`;
    document.getElementById('quick-join-name').value = '';
    document.getElementById('quick-join-modal').classList.add('active');
    document.getElementById('quick-join-name').focus();
}

function closeQuickJoinModal() {
    document.getElementById('quick-join-modal').classList.remove('active');
}

function quickJoinNearby(code) {
    // Pre-fill the session code and scroll to join form
    document.getElementById('session-code').value = code;
    document.getElementById('join-name').focus();
    document.getElementById('join-name').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

async function loadSession(code) {
    try {
        const session = await apiRequest(`/sessions/${code}`);
        currentSession = session;
        
        // Update host participant reference
        if (isHost && !currentParticipant) {
            currentParticipant = session.participants.find(p => p.is_host);
            currentTipPercentage = currentParticipant?.tip_percentage || 10;
        }
        
        // Use session data directly - no separate API calls
        renderParticipantsList();
        
        // Update discount participant dropdown and render discounts (host only)
        if (isHost) {
            updateDiscountParticipantDropdown();
            renderDiscountsList();
        }
        
        if (session.items && session.items.length > 0) {
            displayItems(session.items, session.participants);
            document.getElementById('items-section').hidden = false;
            document.getElementById('items-count').textContent = session.items.filter(i => !i.is_tax && !i.is_tip_suggestion).length;
            updateStepIndicator(2);
            updateHostTotal();
            await updateSummary(); // Auto-calculate summary
        }
        
    } catch (error) {
        showError('Failed to load session: ' + error.message);
    }
}

// Render participants from session data (no API call)
function renderParticipantsList() {
    if (!currentSession) return;
    
    const participants = currentSession.participants || [];
    const list = document.getElementById('participants-list');
    const count = document.getElementById('participants-count');
    
    count.textContent = participants.length;
    
    list.innerHTML = participants.map(p => `
        <div class="participant-chip ${p.is_host ? 'host' : ''}">
            <div class="participant-avatar">${p.name.charAt(0).toUpperCase()}</div>
            <span>${p.name}</span>
            ${isHost && !p.is_host ? `<button class="participant-remove" onclick="event.stopPropagation(); removeParticipant('${p.id}')" title="Remove">✕</button>` : ''}
        </div>
    `).join('');
}

// Keep loadParticipants for backward compatibility but use renderParticipantsList
async function loadParticipants() {
    renderParticipantsList();
}

async function removeParticipant(participantId) {
    // Find participant name for confirmation message
    const participant = currentSession.participants.find(p => p.id === participantId);
    const name = participant?.name || 'this participant';
    
    showConfirm(
        'Remove Participant',
        `Remove ${name} from the session? They will be returned to the home screen.`,
        async () => {
            try {
                await apiRequest(`/sessions/${currentSession.code}/participants/${participantId}`, {
                    method: 'DELETE'
                });
                await loadSession(currentSession.code);
            } catch (error) {
                showError('Failed to remove participant: ' + error.message);
            }
        }
    );
}

// Receipt Upload
let selectedFile = null;

function setupUploadHandlers() {
    const fileInput = document.getElementById('receipt-input');
    const cameraInput = document.getElementById('camera-input');
    const cameraBtn = document.getElementById('camera-btn');
    const galleryBtn = document.getElementById('gallery-btn');
    const processBtn = document.getElementById('process-btn');
    const preview = document.getElementById('receipt-preview');

    // Camera button - opens camera on mobile
    cameraBtn.addEventListener('click', () => cameraInput.click());

    // Gallery button - opens file picker
    galleryBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    cameraInput.addEventListener('change', (e) => {
        if (e.target.files.length) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (!file.type.match(/^image\/(jpeg|png|webp|heic|heif)$/i)) {
            showError('Please select a JPEG, PNG, WebP, or HEIC image');
            return;
        }

        selectedFile = file;
        processBtn.disabled = false;

        const reader = new FileReader();
        reader.onload = (e) => {
            preview.src = e.target.result;
            preview.hidden = false;
        };
        reader.readAsDataURL(file);
    }

    processBtn.addEventListener('click', uploadReceipt);
}

async function uploadReceipt() {
    if (!selectedFile || !currentSession) return;
    
    const processBtn = document.getElementById('process-btn');
    const status = document.getElementById('processing-status');
    
    processBtn.disabled = true;
    processBtn.hidden = true;
    status.hidden = false;
    
    try {
        const formData = new FormData();
        formData.append('file', selectedFile);
        
        const response = await fetch(`${API_BASE}/sessions/${currentSession.code}/receipt`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
        
        const result = await response.json();
        
        await loadSession(currentSession.code);
        
        status.hidden = true;
        
        const cardHeader = document.getElementById('upload-section').querySelector('.card-header h2');
        cardHeader.textContent = `✅ Found ${result.items_found} items`;
        
    } catch (error) {
        status.hidden = true;
        processBtn.disabled = false;
        processBtn.hidden = false;
        showError('Failed to process receipt: ' + error.message);
    }
}

function displayItems(items, participants = []) {
    const list = document.getElementById('items-list');
    
    const regularItems = items.filter(i => !i.is_tax && !i.is_tip_suggestion);
    const taxItems = items.filter(i => i.is_tax);
    
    // Combined view: selectable items with delete button (host only)
    list.innerHTML = regularItems.map(item => {
        const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant?.id);
        const isSelected = myAssignment && myAssignment.share_count > 0;
        
        // Get names of other people who selected this item
        const selectors = [];
        if (item.assignments) {
            item.assignments.forEach(a => {
                if (a.share_count > 0) {
                    const participant = participants.find(p => p.id === a.participant_id);
                    if (participant && participant.id !== currentParticipant?.id) {
                        selectors.push(participant.name);
                    }
                }
            });
        }
        
        const totalShares = item.assignments?.reduce((sum, a) => sum + a.share_count, 0) || 0;
        
        return `
            <div class="item-row ${isSelected ? 'selected' : ''}" data-id="${item.id}">
                <div class="item-checkbox" onclick="toggleHostItemSelection('${item.id}')"></div>
                <div class="item-details" onclick="toggleHostItemSelection('${item.id}')" style="flex: 1;">
                    <span class="item-name">${item.name}</span>
                    ${selectors.length > 0 ? `
                        <div class="item-selectors">
                            ${selectors.map(name => `<span class="selector-chip">${name}</span>`).join('')}
                        </div>
                    ` : ''}
                    ${totalShares > 1 ? `<span class="item-quantity">Split ${totalShares} ways</span>` : ''}
                    ${item.quantity > 1 ? `<span class="item-quantity">× ${item.quantity}</span>` : ''}
                </div>
                <span class="item-price">${formatCurrency(item.price)}</span>
                <button class="item-delete" onclick="event.stopPropagation(); deleteItem('${item.id}')" title="Remove">✕</button>
            </div>
        `;
    }).join('') + taxItems.map(item => `
        <div class="item-row tax-item" data-id="${item.id}">
            <span class="item-name">🏷️ ${item.name}</span>
            <span class="item-price">${formatCurrency(item.price)}</span>
        </div>
    `).join('');
}

async function deleteItem(itemId) {
    try {
        await apiRequest(`/sessions/${currentSession.code}/items/${itemId}`, {
            method: 'DELETE'
        });
        await loadSession(currentSession.code);
    } catch (error) {
        showError('Failed to delete item: ' + error.message);
    }
}

async function toggleHostItemSelection(itemId) {
    if (!currentParticipant) {
        showError('Session not properly initialized');
        return;
    }
    
    try {
        const item = currentSession.items.find(i => i.id === itemId);
        const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant.id);
        
        if (myAssignment) {
            await apiRequest(`/sessions/${currentSession.code}/assignments/${myAssignment.id}`, {
                method: 'DELETE'
            });
        } else {
            await apiRequest(`/sessions/${currentSession.code}/assignments`, {
                method: 'POST',
                body: JSON.stringify({
                    item_id: itemId,
                    participant_id: currentParticipant.id,
                    share_count: 1
                })
            });
        }
        
        await loadSession(currentSession.code);
        
    } catch (error) {
        showError('Failed to update selection: ' + error.message);
    }
}

function updateHostTotal() {
    if (!currentSession || !currentParticipant) return;
    
    const items = currentSession.items.filter(i => !i.is_tax && !i.is_tip_suggestion);
    const taxItem = currentSession.items.find(i => i.is_tax);
    
    let myItemsTotal = 0;
    let totalAssignedValue = 0;
    
    items.forEach(item => {
        const totalShares = item.assignments?.reduce((sum, a) => sum + a.share_count, 0) || 0;
        const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant.id);
        
        if (myAssignment && totalShares > 0) {
            const myShare = (item.price * item.quantity * myAssignment.share_count) / totalShares;
            myItemsTotal += myShare;
        }
        
        if (totalShares > 0) {
            totalAssignedValue += item.price * item.quantity;
        }
    });
    
    // Calculate proportional tax
    let myTax = 0;
    if (taxItem && totalAssignedValue > 0) {
        myTax = (myItemsTotal / totalAssignedValue) * taxItem.price;
    }
    
    // Calculate tip
    const tipAmount = (myItemsTotal + myTax) * (currentTipPercentage / 100);
    const grandTotal = myItemsTotal + myTax + tipAmount;
    
    document.getElementById('host-items-total').textContent = formatCurrency(myItemsTotal);
    document.getElementById('host-tax').textContent = formatCurrency(myTax);
    document.getElementById('host-tip-percent').textContent = currentTipPercentage;
    document.getElementById('host-tip').textContent = formatCurrency(tipAmount);
    document.getElementById('host-grand-total').textContent = formatCurrency(grandTotal);
}

async function addItem() {
    const nameInput = document.getElementById('new-item-name');
    const priceInput = document.getElementById('new-item-price');
    
    const name = nameInput.value.trim();
    const price = parseFloat(priceInput.value);
    
    if (!name || isNaN(price) || price < 0) {
        showError('Please enter a valid item name and price');
        return;
    }
    
    try {
        await apiRequest(`/sessions/${currentSession.code}/items`, {
            method: 'POST',
            body: JSON.stringify({ name, price, quantity: 1 })
        });
        
        nameInput.value = '';
        priceInput.value = '';
        
        await loadSession(currentSession.code);
    } catch (error) {
        showError('Failed to add item: ' + error.message);
    }
}

// QR Code
function setupQRHandlers() {
    const showBtn = document.getElementById('show-qr-btn');
    const modal = document.getElementById('qr-modal');
    const closeBtn = modal.querySelector('.close-btn');
    const shareBtn = document.getElementById('share-link-btn');

    showBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`${API_BASE}/sessions/${currentSession.code}/qr`);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);

            document.getElementById('qr-image').src = url;
            document.getElementById('qr-code-text').textContent = currentSession.code;
            modal.classList.add('active');
        } catch (error) {
            showError('Failed to load QR code');
        }
    });

    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('active');
    });

    // Share link handler
    if (shareBtn && !shareBtn.dataset.bound) {
        shareBtn.addEventListener('click', () => {
            const url = `${window.location.origin}/?code=${currentSession.code}`;
            if (navigator.share) {
                navigator.share({
                    title: 'Join my Check Splitter session',
                    text: `Session code: ${currentSession.code}`,
                    url
                });
            } else {
                navigator.clipboard.writeText(url);
                showToast('Session link copied!', 'success');
            }
        });
        shareBtn.dataset.bound = 'true';
    }
}

// Copy Code
function setupCopyHandler() {
    document.getElementById('copy-code-btn').addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(currentSession.code);
            const textSpan = document.getElementById('copy-btn-text');
            const originalText = textSpan.textContent;
            textSpan.textContent = 'Copied!';
            setTimeout(() => textSpan.textContent = originalText, 1500);
        } catch (e) {
            // Fallback for older browsers
            const textSpan = document.getElementById('copy-btn-text');
            // Create a temporary input to copy
            const tempInput = document.createElement('input');
            tempInput.value = currentSession.code;
            document.body.appendChild(tempInput);
            tempInput.select();
            document.execCommand('copy');
            document.body.removeChild(tempInput);
            textSpan.textContent = 'Copied!';
            setTimeout(() => textSpan.textContent = 'Copy Code', 1500);
        }
    });
}

// End Session
function setupEndSessionHandler() {
    document.getElementById('end-session-btn').addEventListener('click', () => {
        showConfirm(
            'End Session',
            'This will end the session for everyone. All participants will be returned to the home screen.',
            async () => {
                try {
                    const sessionCode = currentSession.code;
                    await apiRequest(`/sessions/${currentSession.code}`, {
                        method: 'DELETE'
                    });
                    stopSync();
                    removeSessionFromHistory(sessionCode);
                    currentSession = null;
                    currentParticipant = null;
                    isHost = false;
                    showToast('Session ended', 'success');
                    showPage('landing');
                    renderSessionHistory();
                    renderRejoinBanner();
                } catch (error) {
                    showError('Failed to end session: ' + error.message);
                }
            }
        );
    });
}

// Participant View
async function loadParticipantView() {
    try {
        const session = await apiRequest(`/sessions/${currentSession.code}`);
        currentSession = session;
        
        // Use participants from session data (no separate API call)
        const participants = session.participants;
        
        const list = document.getElementById('participant-items-list');
        const items = session.items.filter(i => !i.is_tax && !i.is_tip_suggestion);
        
        list.innerHTML = items.map(item => {
            const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant.id);
            const isSelected = myAssignment && myAssignment.share_count > 0;
            
            // Get names of people who selected this item
            const selectors = [];
            if (item.assignments) {
                item.assignments.forEach(a => {
                    if (a.share_count > 0) {
                        const participant = participants.find(p => p.id === a.participant_id);
                        if (participant && participant.id !== currentParticipant.id) {
                            selectors.push(participant.name);
                        }
                    }
                });
            }
            
            const totalShares = item.assignments?.reduce((sum, a) => sum + a.share_count, 0) || 0;
            
            return `
                <div class="item-row ${isSelected ? 'selected' : ''}" 
                     data-id="${item.id}"
                     onclick="toggleItemSelection('${item.id}')">
                    <div class="item-checkbox"></div>
                    <div class="item-details" style="flex: 1;">
                        <span class="item-name">${item.name}</span>
                        ${selectors.length > 0 ? `
                            <div class="item-selectors">
                                ${selectors.map(name => `<span class="selector-chip">${name}</span>`).join('')}
                            </div>
                        ` : ''}
                        ${totalShares > 1 ? `<span class="item-quantity">Split ${totalShares} ways</span>` : ''}
                    </div>
                    <span class="item-price">${formatCurrency(item.price)}</span>
                </div>
            `;
        }).join('');
        
        // Render discounts for participant view
        renderParticipantDiscounts();
        
        updateYourTotal();

        // Setup participant code actions if not already
        setupParticipantCodeActions();
        
    } catch (error) {
        showError('Failed to load items: ' + error.message);
    }
}

async function toggleItemSelection(itemId) {
    try {
        const item = currentSession.items.find(i => i.id === itemId);
        const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant.id);
        
        if (myAssignment) {
            await apiRequest(`/sessions/${currentSession.code}/assignments/${myAssignment.id}`, {
                method: 'DELETE'
            });
        } else {
            await apiRequest(`/sessions/${currentSession.code}/assignments`, {
                method: 'POST',
                body: JSON.stringify({
                    item_id: itemId,
                    participant_id: currentParticipant.id,
                    share_count: 1
                })
            });
        }
        
        await loadParticipantView();
        
    } catch (error) {
        showError('Failed to update selection: ' + error.message);
    }
}

// Tip Selection
function setupTipHandlers() {

    // Participant code actions
    function setupParticipantCodeActions() {
        // Copy code
        const copyBtn = document.getElementById('participant-copy-code-btn');
        if (copyBtn && !copyBtn.dataset.bound) {
            copyBtn.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(currentSession.code);
                    const textSpan = document.getElementById('participant-copy-btn-text');
                    const originalText = textSpan.textContent;
                    textSpan.textContent = 'Copied!';
                    setTimeout(() => textSpan.textContent = originalText, 1500);
                } catch (e) {
                    const textSpan = document.getElementById('participant-copy-btn-text');
                    const tempInput = document.createElement('input');
                    tempInput.value = currentSession.code;
                    document.body.appendChild(tempInput);
                    tempInput.select();
                    document.execCommand('copy');
                    document.body.removeChild(tempInput);
                    textSpan.textContent = 'Copied!';
                    setTimeout(() => textSpan.textContent = 'Copy Code', 1500);
                }
            });
            copyBtn.dataset.bound = 'true';
        }

        // QR code
        const qrBtn = document.getElementById('participant-show-qr-btn');
        const qrModal = document.getElementById('participant-qr-modal');
        const qrCloseBtn = document.getElementById('participant-qr-close-btn');
        if (qrBtn && !qrBtn.dataset.bound) {
            qrBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch(`${API_BASE}/sessions/${currentSession.code}/qr`);
                    const blob = await response.blob();
                    const url = URL.createObjectURL(blob);
                    document.getElementById('participant-qr-image').src = url;
                    document.getElementById('participant-qr-code-text').textContent = currentSession.code;
                    qrModal.classList.add('active');
                } catch (error) {
                    showError('Failed to load QR code');
                }
            });
            qrBtn.dataset.bound = 'true';
        }
        if (qrCloseBtn && !qrCloseBtn.dataset.bound) {
            qrCloseBtn.addEventListener('click', () => qrModal.classList.remove('active'));
            qrCloseBtn.dataset.bound = 'true';
        }
        qrModal.addEventListener('click', (e) => {
            if (e.target === qrModal) qrModal.classList.remove('active');
        });

        // Share link
        const shareBtn = document.getElementById('participant-share-link-btn');
        const shareModalBtn = document.getElementById('participant-share-link-modal-btn');
        function shareSessionLink() {
            const url = `${window.location.origin}/?code=${currentSession.code}`;
            if (navigator.share) {
                navigator.share({
                    title: 'Join my Check Splitter session',
                    text: `Session code: ${currentSession.code}`,
                    url
                });
            } else {
                navigator.clipboard.writeText(url);
                showToast('Session link copied!', 'success');
            }
        }
        if (shareBtn && !shareBtn.dataset.bound) {
            shareBtn.addEventListener('click', shareSessionLink);
            shareBtn.dataset.bound = 'true';
        }
        if (shareModalBtn && !shareModalBtn.dataset.bound) {
            shareModalBtn.addEventListener('click', shareSessionLink);
            shareModalBtn.dataset.bound = 'true';
        }

        // Leave session
        const leaveBtn = document.getElementById('participant-leave-session-btn');
        if (leaveBtn && !leaveBtn.dataset.bound) {
            leaveBtn.addEventListener('click', () => {
                showConfirm(
                    'Leave Session',
                    'Are you sure you want to leave? You can rejoin from the home screen.',
                    async () => {
                        try {
                            stopSync();
                            currentSession = null;
                            currentParticipant = null;
                            isHost = false;
                            showToast('You left the session', 'success');
                            showPage('landing');
                            renderSessionHistory();
                            renderRejoinBanner();
                        } catch (error) {
                            showError('Failed to leave session: ' + error.message);
                        }
                    }
                );
            });
            leaveBtn.dataset.bound = 'true';
        }
    }
    // Participant tip buttons
    const participantTipBtns = document.querySelectorAll('#participant-page .tip-btn');
    const customInput = document.getElementById('custom-tip-value');
    
    participantTipBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            participantTipBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const tip = parseInt(btn.dataset.tip);
            currentTipPercentage = tip;
            customInput.value = '';
            
            await updateTip(tip);
        });
    });
    
    customInput.addEventListener('input', async () => {
        const tip = parseInt(customInput.value) || 0;
        currentTipPercentage = tip;
        
        participantTipBtns.forEach(b => b.classList.remove('active'));
        
        await updateTip(tip);
    });
    
    // Host tip buttons
    const hostTipBtns = document.querySelectorAll('.host-tip-btn');
    
    hostTipBtns.forEach(btn => {
        btn.addEventListener('click', async () => {
            hostTipBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            const tip = parseInt(btn.dataset.tip);
            currentTipPercentage = tip;
            
            await updateTip(tip);
        });
    });
}

async function updateTip(percentage) {
    // Update participant page display if it exists
    const tipDisplay = document.getElementById('tip-percent-display');
    if (tipDisplay) {
        tipDisplay.textContent = percentage;
    }
    
    // Update host page display
    const hostTipDisplay = document.getElementById('host-tip-percent');
    if (hostTipDisplay) {
        hostTipDisplay.textContent = percentage;
    }
    
    if (!currentParticipant) {
        updateYourTotal();
        updateHostTotal();
        return;
    }
    
    try {
        await apiRequest(`/sessions/${currentSession.code}/participants/${currentParticipant.id}`, {
            method: 'PUT',
            body: JSON.stringify({ tip_percentage: percentage })
        });
        
        currentParticipant.tip_percentage = percentage;
        updateYourTotal();
        updateHostTotal();
        
    } catch (error) {
        // Still update local UI even if server update failed
        updateYourTotal();
        updateHostTotal();
    }
}

function updateYourTotal() {
    // Use server-calculated summary for accurate totals including discounts
    updateYourTotalFromServer();
}

async function updateYourTotalFromServer() {
    try {
        const summary = await apiRequest(`/sessions/${currentSession.code}/summary`);
        
        // Find my summary in the response
        const mySummary = summary.participants.find(p => p.participant_id === currentParticipant.id);
        
        if (mySummary) {
            // Update display with server-calculated values
            document.getElementById('your-items-total').textContent = formatCurrency(mySummary.items_subtotal);
            document.getElementById('your-tax').textContent = formatCurrency(mySummary.tax_share);
            document.getElementById('your-tip').textContent = formatCurrency(mySummary.tip_amount);
            document.getElementById('tip-percent-display').textContent = currentTipPercentage;
            document.getElementById('your-grand-total').textContent = formatCurrency(mySummary.total);
            
            // Show discount row if there's a discount
            const discountRow = document.getElementById('your-discount-row');
            const discountAmount = document.getElementById('your-discount');
            
            if (mySummary.discount_amount && mySummary.discount_amount > 0) {
                discountRow.style.display = 'flex';
                discountAmount.textContent = '-' + formatCurrency(mySummary.discount_amount);
            } else {
                discountRow.style.display = 'none';
            }
        } else {
            // Fallback to local calculation if not in summary
            updateYourTotalLocal();
        }
    } catch (error) {
        // Fallback to local calculation if API fails
        updateYourTotalLocal();
    }
}

function updateYourTotalLocal() {
    // Local calculation fallback (without discounts)
    const items = currentSession.items.filter(i => !i.is_tax && !i.is_tip_suggestion);
    const taxItem = currentSession.items.find(i => i.is_tax);
    
    let itemsTotal = 0;
    let totalBillItems = 0;
    
    items.forEach(item => {
        const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant.id);
        const totalShares = item.assignments?.reduce((sum, a) => sum + a.share_count, 0) || 0;
        
        totalBillItems += parseFloat(item.price) * item.quantity;
        
        if (myAssignment && totalShares > 0) {
            const myShare = (parseFloat(item.price) * item.quantity * myAssignment.share_count) / totalShares;
            itemsTotal += myShare;
        }
    });
    
    // Calculate proportional tax
    let tax = 0;
    if (taxItem && totalBillItems > 0) {
        tax = (itemsTotal / totalBillItems) * parseFloat(taxItem.price);
    }
    
    // Calculate tip based on YOUR items only
    const tipPercentage = currentTipPercentage;
    const tip = itemsTotal * (tipPercentage / 100);
    
    const grandTotal = itemsTotal + tax + tip;
    
    document.getElementById('your-items-total').textContent = formatCurrency(itemsTotal);
    document.getElementById('your-tax').textContent = formatCurrency(tax);
    document.getElementById('your-tip').textContent = formatCurrency(tip);
    document.getElementById('tip-percent-display').textContent = tipPercentage;
    document.getElementById('your-grand-total').textContent = formatCurrency(grandTotal);
    
    // Hide discount row for local calculation
    const discountRow = document.getElementById('your-discount-row');
    if (discountRow) discountRow.style.display = 'none';
}

// Discounts Management
function toggleDiscountsSection() {
    const section = document.getElementById('discounts-section');
    const content = document.getElementById('discount-content');
    const chevron = section.querySelector('.discount-chevron');
    const hint = section.querySelector('.discount-hint');
    
    const isExpanded = !content.hidden;
    content.hidden = isExpanded;
    chevron.textContent = isExpanded ? '▸' : '▾';
    if (hint) hint.textContent = isExpanded ? 'Tap to expand' : 'Tap to collapse';
}

function renderDiscountsList() {
    if (!currentSession) return;
    
    const discounts = currentSession.discounts || [];
    const list = document.getElementById('discounts-list');
    const count = document.getElementById('discounts-count');
    
    if (count) count.textContent = discounts.length;
    
    if (!list) return;
    
    if (discounts.length === 0) {
        list.innerHTML = '<p class="help-text">No discounts added yet</p>';
        return;
    }
    
    list.innerHTML = discounts.map(d => {
        const targetName = d.participant_id 
            ? currentSession.participants.find(p => p.id === d.participant_id)?.name || 'Unknown'
            : 'Everyone';
        const valueDisplay = d.discount_type === 'percentage' 
            ? `${d.value}%` 
            : formatCurrency(d.value);
        
        return `
            <div class="discount-item" data-id="${d.id}">
                <div class="discount-item-info">
                    <div class="discount-item-name">${d.name}</div>
                    <div class="discount-item-meta">
                        <span class="discount-item-value">${valueDisplay} off</span>
                        <span class="discount-item-target">→ ${targetName}</span>
                    </div>
                </div>
                <button class="discount-remove-btn" onclick="deleteDiscount('${d.id}')" title="Remove">✕</button>
            </div>
        `;
    }).join('');
}

// Keep loadDiscounts for backward compatibility
async function loadDiscounts() {
    renderDiscountsList();
}

async function addDiscount() {
    trackUserAction();
    
    const nameInput = document.getElementById('discount-name');
    const typeSelect = document.getElementById('discount-type');
    const valueInput = document.getElementById('discount-value');
    const targetSelect = document.getElementById('discount-target');
    
    const name = nameInput.value.trim() || null; // Optional - server will auto-generate
    const discountType = typeSelect.value;
    const value = parseFloat(valueInput.value);
    const participantId = targetSelect.value || null;
    
    if (isNaN(value) || value <= 0) {
        showError('Please enter a valid discount amount');
        return;
    }
    
    if (discountType === 'percentage' && value > 100) {
        showError('Percentage cannot exceed 100%');
        return;
    }
    
    try {
        await apiRequest(`/sessions/${currentSession.code}/discounts`, {
            method: 'POST',
            body: JSON.stringify({
                name,
                discount_type: discountType,
                value,
                participant_id: participantId
            })
        });
        
        // Clear form
        nameInput.value = '';
        valueInput.value = '';
        
        // Reload session to get updated discounts
        await loadSession(currentSession.code);
        showSuccess('Discount added');
        
    } catch (error) {
        showError('Failed to add discount: ' + error.message);
    }
}

async function deleteDiscount(discountId) {
    trackUserAction();
    
    try {
        await apiRequest(`/sessions/${currentSession.code}/discounts/${discountId}`, {
            method: 'DELETE'
        });
        
        // Reload session to get updated discounts
        await loadSession(currentSession.code);
        showSuccess('Discount removed');
        
    } catch (error) {
        showError('Failed to remove discount: ' + error.message);
    }
}

function updateDiscountParticipantDropdown() {
    const select = document.getElementById('discount-target');
    if (!select || !currentSession) return;
    
    // Preserve current selection if possible
    const currentValue = select.value;
    
    // Reset with "Everyone" option
    select.innerHTML = '<option value="">Everyone</option>';
    
    // Add all participants
    currentSession.participants.forEach(p => {
        const option = document.createElement('option');
        option.value = p.id;
        option.textContent = p.name;
        select.appendChild(option);
    });
    
    // Restore selection if participant still exists
    if (currentValue && currentSession.participants.some(p => p.id === currentValue)) {
        select.value = currentValue;
    }
}

// Initialize
// Register Service Worker for PWA
async function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
        try {
            const registration = await navigator.serviceWorker.register('/static/sw.js');
            
            // Check for updates
            registration.addEventListener('updatefound', () => {
                const newWorker = registration.installing;
                newWorker.addEventListener('statechange', () => {
                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                        // New content available, show refresh prompt
                        showConfirm(
                            'Update Available',
                            'A new version is available. Reload to update?',
                            () => window.location.reload()
                        );
                    }
                });
            });
        } catch (error) {
            // Service worker not supported or blocked
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Register service worker
    registerServiceWorker();
    
    // Create session form
    document.getElementById('create-session-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const hostName = document.getElementById('host-name').value.trim();
        if (hostName) {
            await createSession(hostName);
        }
    });
    
    // Join session form
    document.getElementById('join-session-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const code = document.getElementById('session-code').value.trim().toUpperCase();
        const name = document.getElementById('join-name').value.trim();
        if (code && name) {
            await joinSession(code, name);
        }
    });
    
    // Setup handlers
    setupUploadHandlers();
    setupQRHandlers();
    setupCopyHandler();
    setupEndSessionHandler();
    setupTipHandlers();
    
    // Add item button
    document.getElementById('add-item-btn').addEventListener('click', () => {
        trackUserAction();
        addItem();
    });
    
    // Discount section toggle
    const discountToggle = document.getElementById('discount-toggle');
    if (discountToggle) {
        discountToggle.addEventListener('click', toggleDiscountsSection);
    }
    
    // Add discount button
    const addDiscountBtn = document.getElementById('add-discount-btn');
    if (addDiscountBtn) {
        addDiscountBtn.addEventListener('click', addDiscount);
    }
    
    // Track user activity for adaptive sync
    document.addEventListener('click', trackUserAction);
    document.addEventListener('keydown', trackUserAction);
    
    // Refresh button (participant)
    document.getElementById('refresh-btn').addEventListener('click', loadParticipantView);
    
    // Refresh nearby sessions button
    const refreshNearbyBtn = document.getElementById('refresh-nearby-btn');
    if (refreshNearbyBtn) {
        refreshNearbyBtn.addEventListener('click', fetchNearbySessions);
    }
    
    // Quick join form (nearby sessions modal)
    const quickJoinForm = document.getElementById('quick-join-form');
    if (quickJoinForm) {
        quickJoinForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const code = document.getElementById('quick-join-code').value.trim().toUpperCase();
            const name = document.getElementById('quick-join-name').value.trim();
            if (code && name) {
                closeQuickJoinModal();
                await joinSession(code, name);
            }
        });
    }
    
    // Close quick join modal when clicking outside
    const quickJoinModal = document.getElementById('quick-join-modal');
    if (quickJoinModal) {
        quickJoinModal.addEventListener('click', (e) => {
            if (e.target === quickJoinModal) {
                closeQuickJoinModal();
            }
        });
    }
    
    // Fetch user's currency based on location
    fetchUserCurrency();
    
    // Fetch nearby sessions on page load
    fetchNearbySessions();
    
    // --- Auto-rejoin logic ---
    const urlParams = new URLSearchParams(window.location.search);
    const codeFromUrl = urlParams.get('code');
    const lastSession = getLastSession();
    
    if (codeFromUrl) {
        // QR code / link join: check if we have a saved identity for this session
        const codeUpper = codeFromUrl.toUpperCase();
        const history = getSessionHistory();
        const savedEntry = history.find(h => h.code === codeUpper);
        
        if (savedEntry && savedEntry.participantId) {
            // We were in this session before — auto-rejoin (works for host + guest)
            rejoinSession(codeUpper);
        } else {
            // New session for this user — pre-fill code, let them type their name
            document.getElementById('session-code').value = codeUpper;
            document.getElementById('join-name').focus();
            document.querySelector('.card-secondary')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            renderRejoinBanner();
            renderSessionHistory();
        }
    } else if (lastSession && (Date.now() - lastSession.timestamp < 5 * 60 * 1000)) {
        // Last session was active within 5 minutes — likely an accidental refresh
        // Auto-rejoin immediately (works for both host and guest via rejoinSession)
        rejoinSession(lastSession.code);
    } else {
        // Normal landing page
        renderRejoinBanner();
        renderSessionHistory();
    }
});
