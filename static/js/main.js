/**
 * LinkSwift - Client side scripting file
 * Handles AJAX forms, clipboard copier, base64 downloads, click simulation, and toasts.
 */

// Global state to track currently generated slug for downloads
let activeShortCode = "";
let activeShortUrl = "";

/**
 * Toggle Custom Code slug drawer
 */
function toggleCustomCode() {
    const container = document.getElementById("custom-code-container");
    const chevron = document.getElementById("toggle-chevron");
    
    if (container.classList.contains("expanded")) {
        container.classList.remove("expanded");
        chevron.style.transform = "rotate(0deg)";
    } else {
        container.classList.add("expanded");
        chevron.style.transform = "rotate(180deg)";
    }
}

/**
 * Handles AJAX Submission for URL Shortening
 */
async function handleShorten(event) {
    event.preventDefault();
    
    const originalUrlInput = document.getElementById("original_url");
    const customCodeInput = document.getElementById("custom_code");
    const btnSubmit = document.getElementById("btn-submit");
    const btnSpinner = document.getElementById("btn-spinner");
    const btnText = document.getElementById("btn-text");
    const btnIcon = document.getElementById("btn-icon-arrow");
    
    const original_url = originalUrlInput.value.trim();
    const custom_code = customCodeInput.value.trim();
    
    if (!original_url) {
        showToast("Please enter a destination URL", "error");
        return;
    }
    
    // UI Loading State
    btnSubmit.disabled = true;
    btnSpinner.style.display = "inline-block";
    btnText.textContent = "Processing...";
    btnIcon.style.display = "none";
    
    try {
        const response = await fetch("/shorten", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ original_url, custom_code })
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === "success") {
            // Store variables
            activeShortUrl = data.short_url;
            activeShortCode = data.short_code;
            
            // Hydrate Success Card details
            document.getElementById("result-short-url").textContent = data.short_url;
            document.getElementById("result-qr-img").src = data.qr_code_base64;
            
            const analyticsBtn = document.getElementById("result-analytics-btn");
            analyticsBtn.href = `/analytics/${data.short_code}`;
            
            // Toggle form out and success card in
            document.getElementById("shorten-card").style.display = "none";
            document.getElementById("result-panel").style.display = "block";
            
            showToast("Short link generated successfully!", "success");
            
            // Add row directly to table history if it exists
            injectHistoryRow(data);
            
        } else {
            showToast(data.message || "An error occurred while shortening", "error");
            resetSubmitButton();
        }
    } catch (error) {
        showToast("Network connection error. Try again.", "error");
        resetSubmitButton();
    }
}

/**
 * Resets Submit Button State on failure
 */
function resetSubmitButton() {
    const btnSubmit = document.getElementById("btn-submit");
    const btnSpinner = document.getElementById("btn-spinner");
    const btnText = document.getElementById("btn-text");
    const btnIcon = document.getElementById("btn-icon-arrow");
    
    btnSubmit.disabled = false;
    btnSpinner.style.display = "none";
    btnText.textContent = "Generate Swift Link";
    btnIcon.style.display = "inline-block";
}

/**
 * Clean UI Reset to shorten another URL
 */
function resetForm() {
    // Clear form inputs
    document.getElementById("original_url").value = "";
    document.getElementById("custom_code").value = "";
    
    // Collapse custom alias panel
    const customContainer = document.getElementById("custom-code-container");
    const chevron = document.getElementById("toggle-chevron");
    customContainer.classList.remove("expanded");
    chevron.style.transform = "rotate(0deg)";
    
    // Toggle UI panels
    document.getElementById("result-panel").style.display = "none";
    document.getElementById("shorten-card").style.display = "block";
    
    resetSubmitButton();
    
    activeShortCode = "";
    activeShortUrl = "";
}

/**
 * Copies the freshly generated Short URL to Clipboard
 */
async function copyResultUrl() {
    if (!activeShortUrl) return;
    
    try {
        await navigator.clipboard.writeText(activeShortUrl);
        showToast("Link copied to clipboard!", "success");
        
        // Visual toggle on copy button icon
        const copyIcon = document.getElementById("copy-btn-icon");
        copyIcon.className = "fa-solid fa-check";
        copyIcon.style.color = "var(--color-green)";
        
        setTimeout(() => {
            copyIcon.className = "fa-regular fa-copy";
            copyIcon.style.color = "";
        }, 2000);
        
    } catch (err) {
        showToast("Failed to copy link.", "error");
    }
}

/**
 * Clipboard utility matching individual table rows
 */
async function copyLinkDirect(link, slug) {
    try {
        await navigator.clipboard.writeText(link);
        showToast(`/${slug} copied!`, "success");
        
        const btn = document.getElementById(`copy-direct-${slug}`) || document.getElementById("copy-btn-analytics");
        if (btn) {
            const icon = btn.querySelector("i");
            if (icon) {
                const originalClass = icon.className;
                icon.className = "fa-solid fa-check";
                icon.style.color = "var(--color-green)";
                setTimeout(() => {
                    icon.className = originalClass;
                    icon.style.color = "";
                }, 2000);
            }
        }
    } catch (err) {
        showToast("Copy command failed.", "error");
    }
}

/**
 * Triggers Base64 QR Image Download download
 */
function downloadQrCode() {
    const qrImg = document.getElementById("result-qr-img");
    if (!qrImg || !qrImg.src) return;
    
    const link = document.createElement("a");
    link.href = qrImg.src;
    link.download = `swift_qr_${activeShortCode || "code"}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showToast("QR code downloaded!", "success");
}

/**
 * Injects simulated logs to SQLite for testing
 */
async function triggerSimulation(urlId) {
    const btnText = document.getElementById("simulate-btn-text");
    const btnSimulate = document.getElementById("btn-simulate");
    const btnSimulateEmpty = document.getElementById("btn-simulate-empty");
    
    const loadingMessage = "Simulating tracking...";
    
    if (btnSimulate) btnSimulate.disabled = true;
    if (btnSimulateEmpty) btnSimulateEmpty.disabled = true;
    if (btnText) btnText.textContent = loadingMessage;
    
    showToast("Generating high-fidelity tracking data...", "success");
    
    try {
        const response = await fetch("/api/simulate", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ url_id: urlId })
        });
        
        const data = await response.json();
        
        if (response.ok && data.status === "success") {
            showToast("Simulation complete. Refreshing dashboard...", "success");
            setTimeout(() => {
                window.location.reload();
            }, 1200);
        } else {
            showToast(data.message || "Simulation request failed", "error");
            restoreSimulationBtn();
        }
    } catch (err) {
        showToast("Server connection error during simulation", "error");
        restoreSimulationBtn();
    }
}

/**
 * Restore simulation buttons on failure
 */
function restoreSimulationBtn() {
    const btnText = document.getElementById("simulate-btn-text");
    const btnSimulate = document.getElementById("btn-simulate");
    const btnSimulateEmpty = document.getElementById("btn-simulate-empty");
    
    if (btnSimulate) btnSimulate.disabled = false;
    if (btnSimulateEmpty) btnSimulateEmpty.disabled = false;
    if (btnText) btnText.textContent = "Simulate Clicks";
}

/**
 * Dynamic injection of new rows into history tables
 */
function injectHistoryRow(data) {
    const tableBody = document.querySelector("table tbody");
    const tableContainer = document.querySelector(".table-container");
    
    // Create new row elements
    const newRow = document.createElement("tr");
    newRow.id = `row-${data.short_code}`;
    newRow.style.animation = "slideUp 0.4s ease-out forwards";
    
    newRow.innerHTML = `
        <td class="col-short">
            <a href="${data.short_url}" target="_blank" style="color: var(--color-purple); text-decoration: none; font-weight: 600;">
                ${data.short_code}
            </a>
        </td>
        <td class="col-url" title="${data.original_url}">${data.original_url}</td>
        <td style="color: var(--text-secondary); font-size: 0.9rem;">Just now</td>
        <td style="text-align: right;">
            <div class="table-actions" style="justify-content: flex-end;">
                <button class="btn-icon" onclick="copyLinkDirect('${data.short_url}', '${data.short_code}')" title="Copy URL" id="copy-direct-${data.short_code}">
                    <i class="fa-regular fa-copy"></i>
                </button>
                <a href="/analytics/${data.short_code}" class="btn-icon" title="View Dashboard" id="analytics-direct-${data.short_code}">
                    <i class="fa-solid fa-chart-line"></i>
                </a>
            </div>
        </td>
    `;
    
    // Check if table contains empty state container instead of table layout
    const emptyState = tableContainer.querySelector("div[style*='padding']");
    if (emptyState) {
        // Build table skeleton dynamically
        tableContainer.innerHTML = `
            <table>
                <thead>
                    <tr>
                        <th>Short Link</th>
                        <th>Original Destination</th>
                        <th>Created At</th>
                        <th style="text-align: right;">Actions</th>
                    </tr>
                </thead>
                <tbody></tbody>
            </table>
        `;
        tableContainer.querySelector("tbody").appendChild(newRow);
    } else if (tableBody) {
        // Prepend new link row to top of the history list
        tableBody.insertBefore(newRow, tableBody.firstChild);
        
        // Keep history list bounded to last 8 elements
        if (tableBody.children.length > 8) {
            tableBody.removeChild(tableBody.lastChild);
        }
    }
}

/**
 * Global custom float-notification system
 */
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    
    let iconClass = "fa-circle-check";
    if (type === "error") iconClass = "fa-circle-xmark";
    else if (type === "warning") iconClass = "fa-circle-exclamation";
    
    toast.innerHTML = `
        <i class="fa-solid ${iconClass}"></i>
        <span>${message}</span>
    `;
    
    container.appendChild(toast);
    
    // Animate out and remove after timeout
    setTimeout(() => {
        toast.style.animation = "toastOut 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards";
        toast.addEventListener("animationend", () => {
            toast.remove();
        });
    }, 3500);
}

// Keyframes definitions for toast out inserted dynamically inside CSS header
if (!document.getElementById("dynamic-toast-animations")) {
    const style = document.createElement("style");
    style.id = "dynamic-toast-animations";
    style.innerHTML = `
        @keyframes toastOut {
            to {
                opacity: 0;
                transform: translateX(120%);
            }
        }
    `;
    document.head.appendChild(style);
}
