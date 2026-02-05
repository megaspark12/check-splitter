/**
 * Receipt Splitter - Frontend Application
 * Enhanced UI with per-person tip calculation
 */

const API_BASE = '/api';

// State
let currentSession = null;
let currentParticipant = null;
let isHost = false;
let currentTipPercentage = 20;
let currency = { code: 'USD', symbol: '$', name: 'US Dollar' };

// DOM Elements
const pages = {
    landing: document.getElementById('landing-page'),
    session: document.getElementById('session-page'),
    participant: document.getElementById('participant-page')
};

// Utility Functions
function showPage(pageName) {
    Object.values(pages).forEach(page => page.classList.remove('active'));
    pages[pageName].classList.add('active');
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
            console.log('Detected currency:', currency);
        }
    } catch (error) {
        console.warn('Failed to fetch currency, using default:', error);
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

function showError(message) {
    alert(message);
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
        currentTipPercentage = currentParticipant?.tip_percentage || 20;
        
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
        
        const participant = await apiRequest(`/sessions/${code}/participants`, {
            method: 'POST',
            body: JSON.stringify({ name: name })
        });
        
        currentParticipant = participant;
        currentTipPercentage = participant.tip_percentage || 20;
        isHost = false;
        
        document.getElementById('participant-session-code').textContent = code;
        document.getElementById('participant-name-display').textContent = name;
        
        await loadParticipantView();
        showPage('participant');
        
    } catch (error) {
        showError('Failed to join session: ' + error.message);
    }
}

async function loadSession(code) {
    try {
        const session = await apiRequest(`/sessions/${code}`);
        currentSession = session;
        
        // Update host participant reference
        if (isHost && !currentParticipant) {
            currentParticipant = session.participants.find(p => p.is_host);
            currentTipPercentage = currentParticipant?.tip_percentage || 20;
        }
        
        await loadParticipants();
        
        if (session.items && session.items.length > 0) {
            displayItems(session.items);
            displayHostSelectableItems(session.items);
            document.getElementById('items-section').hidden = false;
            document.getElementById('host-selection-section').hidden = false;
            document.getElementById('items-count').textContent = session.items.filter(i => !i.is_tax && !i.is_tip_suggestion).length;
            document.getElementById('calculate-btn').hidden = false;
            updateStepIndicator(2);
            updateHostTotal();
        }
        
    } catch (error) {
        showError('Failed to load session: ' + error.message);
    }
}

async function loadParticipants() {
    try {
        const participants = await apiRequest(`/sessions/${currentSession.code}/participants`);
        const list = document.getElementById('participants-list');
        const count = document.getElementById('participants-count');
        
        count.textContent = participants.length;
        
        list.innerHTML = participants.map(p => `
            <div class="participant-chip ${p.is_host ? 'host' : ''}">
                <div class="participant-avatar">${p.name.charAt(0).toUpperCase()}</div>
                <span>${p.name}</span>
            </div>
        `).join('');
        
    } catch (error) {
        console.error('Failed to load participants:', error);
    }
}

// Receipt Upload
let selectedFile = null;

function setupUploadHandlers() {
    const uploadArea = document.getElementById('upload-area');
    const fileInput = document.getElementById('receipt-input');
    const cameraInput = document.getElementById('camera-input');
    const cameraBtn = document.getElementById('camera-btn');
    const galleryBtn = document.getElementById('gallery-btn');
    const processBtn = document.getElementById('process-btn');
    const preview = document.getElementById('receipt-preview');
    const placeholder = uploadArea.querySelector('.upload-placeholder');
    
    // Camera button - opens camera on mobile
    cameraBtn.addEventListener('click', () => cameraInput.click());
    
    // Gallery button - opens file picker
    galleryBtn.addEventListener('click', () => fileInput.click());
    
    // Upload area click also opens file picker
    uploadArea.addEventListener('click', () => fileInput.click());
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('drag-over');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('drag-over');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('drag-over');
        if (e.dataTransfer.files.length) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });
    
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
            placeholder.hidden = true;
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
        cardHeader.textContent = '✅ Receipt Processed';
        
        alert(`Found ${result.items_found} items on the receipt!`);
        
    } catch (error) {
        status.hidden = true;
        processBtn.disabled = false;
        processBtn.hidden = false;
        showError('Failed to process receipt: ' + error.message);
    }
}

function displayItems(items) {
    const list = document.getElementById('items-list');
    
    const regularItems = items.filter(i => !i.is_tax && !i.is_tip_suggestion);
    const taxItems = items.filter(i => i.is_tax);
    
    list.innerHTML = regularItems.map(item => `
        <div class="item-row" data-id="${item.id}">
            <div class="item-details">
                <span class="item-name">${item.name}</span>
                ${item.quantity > 1 ? `<span class="item-quantity">× ${item.quantity}</span>` : ''}
            </div>
            <span class="item-price">${formatCurrency(item.price)}</span>
            <button class="item-delete" onclick="deleteItem('${item.id}')" title="Remove">✕</button>
        </div>
    `).join('') + taxItems.map(item => `
        <div class="item-row" data-id="${item.id}" style="background: rgba(245, 158, 11, 0.1);">
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

// Host Item Selection
function displayHostSelectableItems(items) {
    const list = document.getElementById('host-items-list');
    const selectableItems = items.filter(i => !i.is_tax && !i.is_tip_suggestion);
    
    list.innerHTML = selectableItems.map(item => {
        const myAssignment = item.assignments?.find(a => a.participant_id === currentParticipant?.id);
        const isSelected = myAssignment && myAssignment.share_count > 0;
        
        return `
            <div class="item-row ${isSelected ? 'selected' : ''}" 
                 data-id="${item.id}"
                 onclick="toggleHostItemSelection('${item.id}')">
                <div class="item-checkbox"></div>
                <div class="item-details">
                    <span class="item-name">${item.name}</span>
                    ${item.quantity > 1 ? `<span class="item-quantity">× ${item.quantity}</span>` : ''}
                </div>
                <span class="item-price">${formatCurrency(item.price)}</span>
            </div>
        `;
    }).join('');
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

// Participant View
async function loadParticipantView() {
    try {
        const session = await apiRequest(`/sessions/${currentSession.code}`);
        currentSession = session;
        
        // Get all participants to show who selected what
        const participants = await apiRequest(`/sessions/${currentSession.code}/participants`);
        
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
        
        updateYourTotal();
        
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
        console.error('Failed to update tip:', error);
        updateYourTotal();
        updateHostTotal();
    }
}

function updateYourTotal() {
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
}

// Summary Calculation (Host)
async function calculateSummary() {
    try {
        const summary = await apiRequest(`/sessions/${currentSession.code}/summary`);
        
        const content = document.getElementById('summary-content');
        
        content.innerHTML = summary.participants.map(p => `
            <div class="summary-row">
                <div>
                    <span class="name">${p.participant_name}</span>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">
                        Items: ${formatCurrency(p.items_subtotal)} + Tax: ${formatCurrency(p.tax_share)} + Tip: ${formatCurrency(p.tip_amount)}
                    </div>
                </div>
                <span class="amount">${formatCurrency(p.total)}</span>
            </div>
        `).join('');
        
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
        updateStepIndicator(3);
        
    } catch (error) {
        showError('Failed to calculate summary: ' + error.message);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
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
    setupTipHandlers();
    
    // Add item button
    document.getElementById('add-item-btn').addEventListener('click', addItem);
    
    // Calculate button
    document.getElementById('calculate-btn').addEventListener('click', calculateSummary);
    
    // Refresh button (participant)
    document.getElementById('refresh-btn').addEventListener('click', loadParticipantView);
    
    // Fetch user's currency based on location
    fetchUserCurrency();
});
