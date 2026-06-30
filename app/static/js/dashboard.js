// ================= GLOBAL STATE =================

let lastTestResult = null;

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

function postHeaders() {
    return {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken()
    };
}


// ================= DOM ELEMENTS =================

const runTestBtn = document.getElementById("run-test-btn");
const downloadPdfBtn = document.getElementById("download-btn");
const downloadExcelBtn = document.getElementById("download-excel-btn");
const resultsContainer = document.getElementById("results-container");
const spinnerEl = document.getElementById("spinner");
const generateScriptConfirmBtn = document.getElementById("generate-script-confirm-btn");
const translateBtn = document.getElementById("translate-btn");
const voiceBtn = document.getElementById("start-voice");
const saveBtn = document.getElementById("save-btn");
const approveBaselineBtn = document.getElementById("approve-baseline-btn");


// ================= RUN TEST =================

async function runTest(isVisualTest = false) {
    const url        = document.getElementById("url").value.trim();
    const commands   = document.getElementById("commands").value.trim();
    const testCaseId = document.getElementById("test-case-id")?.value || null;

    if (!url || !commands) {
        showToast("Please enter a URL and test commands.", "warning");
        return;
    }

    if (spinnerEl) spinnerEl.classList.remove("d-none");
    resultsContainer.innerHTML = "";
    tloShow();

    if (runTestBtn) { runTestBtn.classList.add("is-loading"); runTestBtn.disabled = true; }

    try {
        // ── Step 1: Submit the job ──
        const submitResp = await fetch("/run-test", {
            method:  "POST",
            headers: postHeaders(),
            body:    JSON.stringify({
                url:           url,
                commands:      commands,
                is_visual_test: isVisualTest,
                test_case_id:  testCaseId
            })
        });

        if (!submitResp.ok) {
            const err = await submitResp.json().catch(() => ({}));
            throw new Error(err.error || `Server error ${submitResp.status}`);
        }

        const { job_id } = await submitResp.json();

        // ── Step 2: Poll until done ──
        const data = await pollJob(job_id);

        if (!data.success) {
            resultsContainer.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>${data.error}
                </div>`;
            showToast("Test execution failed.", "error");
            return;
        }

        lastTestResult = data;
        displayResults(data.results);
        showToast("Test completed successfully!", "success");

        downloadPdfBtn.classList.remove("d-none");
        downloadExcelBtn.classList.remove("d-none");

        const visualActionsEl = document.getElementById("visual-test-actions");
        if (isVisualTest && visualActionsEl) {
            const hasBaseline = data.results.some(r => r.status === "New Baseline");
            if (hasBaseline) visualActionsEl.classList.remove("d-none");
        }

        if (data.probable_cause || data.suggested_fix) {
            let suggHtml = `<div class="card dashboard-card mt-3 fade-in"><div class="card-body">
                <h5 class="card-title"><i class="fas fa-brain"></i> AI Bug Assistant</h5>`;
            if (data.probable_cause)
                suggHtml += `<p><strong style="color:var(--color-warning);">Probable Cause:</strong><br>${data.probable_cause}</p>`;
            if (data.suggested_fix)
                suggHtml += `<p><strong style="color:var(--color-success);">Suggested Fix:</strong><br>${data.suggested_fix}</p>`;
            suggHtml += `</div></div>`;
            resultsContainer.insertAdjacentHTML('afterend', suggHtml);
        }

    } catch (error) {
        console.error(error);
        resultsContainer.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-circle me-2"></i>${error.message || "Error running test. Please try again."}
            </div>`;
        showToast("An unexpected error occurred.", "error");
    } finally {
        if (spinnerEl) spinnerEl.classList.add("d-none");
        tloHide();
        if (runTestBtn) { runTestBtn.classList.remove("is-loading"); runTestBtn.disabled = false; }
    }
}


// ── Poll /job/<id> every 1.5 s until status != "running" ──
async function pollJob(jobId, intervalMs = 1500, maxWaitMs = 300000) {
    const deadline = Date.now() + maxWaitMs;
    while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, intervalMs));
        const resp = await fetch(`/job/${jobId}`);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            throw new Error(err.error || `Job poll error ${resp.status}`);
        }
        const payload = await resp.json();
        if (payload.status === "running") continue;
        return payload;   // "done" or "error"
    }
    throw new Error("Test timed out after 5 minutes.");
}




// ================= DISPLAY RESULTS =================

function displayResults(results) {
    if (!results || results.length === 0) {
        resultsContainer.innerHTML = `
            <div class="text-center py-4">
                <i class="fas fa-inbox" style="font-size: 2rem; color: var(--text-muted); opacity: 0.4;"></i>
                <p class="text-muted mt-2 mb-0">No results returned.</p>
            </div>`;
        return;
    }

    let html = `
        <table class="table table-dark table-hover align-middle mb-0">
            <thead>
                <tr>
                    <th>Step</th>
                    <th>Command</th>
                    <th>Status</th>
                    <th>Details</th>
                </tr>
            </thead>
            <tbody>
    `;

    results.forEach((r, index) => {
        const isFailed = r.status.toLowerCase().includes("fail") || r.status.toLowerCase().includes("mismatch");
        const isBaseline = r.status === "New Baseline";

        let badgeClass = 'bg-success';
        let iconClass = 'fa-check';
        if (isFailed) { badgeClass = 'bg-danger'; iconClass = 'fa-times'; }
        else if (isBaseline) { badgeClass = 'bg-info'; iconClass = 'fa-camera'; }

        let detailsHtml = r.details || "—";
        if (r.status === "Visual Mismatch" && r.baseline && r.current_screenshot) {
            const uniqueId = `vis-compare-${index}`;
            detailsHtml += `
                <div class="visual-inspector mt-3">
                    <div class="btn-group btn-group-sm mb-2" role="group" aria-label="Visual comparison modes" style="border: 1px solid var(--glass-border); border-radius: 6px; padding: 2px; background: rgba(0,0,0,0.2);">
                        <button type="button" class="btn btn-outline-info active btn-vis-opt" onclick="toggleVisualMode('${uniqueId}', 'baseline')" style="border: none; border-radius: 4px;">
                            <i class="fas fa-history me-1"></i> Baseline
                        </button>
                        <button type="button" class="btn btn-outline-warning btn-vis-opt" onclick="toggleVisualMode('${uniqueId}', 'diff')" style="border: none; border-radius: 4px;">
                            <i class="fas fa-circle-exclamation me-1"></i> Diff Delta
                        </button>
                        <button type="button" class="btn btn-outline-success btn-vis-opt" onclick="toggleVisualMode('${uniqueId}', 'current')" style="border: none; border-radius: 4px;">
                            <i class="fas fa-camera me-1"></i> Current Run
                        </button>
                    </div>
                    <div class="visual-media-container" id="${uniqueId}-container" style="max-width: 480px; position: relative;">
                        <div class="visual-pane pane-baseline" id="${uniqueId}-baseline">
                            <img src="data:image/png;base64,${r.baseline}" class="img-fluid rounded border border-info" style="max-height: 320px; object-fit: contain; box-shadow: 0 4px 12px rgba(0,0,0,0.3);" alt="Baseline Image">
                            <div class="badge bg-info mt-1 d-block text-center py-2" style="font-size:0.75rem;">Baseline Image (Reference)</div>
                        </div>
                        <div class="visual-pane pane-diff d-none" id="${uniqueId}-diff">
                            <img src="data:image/png;base64,${r.screenshot}" class="img-fluid rounded border border-warning" style="max-height: 320px; object-fit: contain; box-shadow: 0 4px 12px rgba(0,0,0,0.3);" alt="Mismatch Difference">
                            <div class="badge bg-warning text-dark mt-1 d-block text-center py-2" style="font-size:0.75rem;">Highlighted Difference (Delta)</div>
                        </div>
                        <div class="visual-pane pane-current d-none" id="${uniqueId}-current">
                            <img src="data:image/png;base64,${r.current_screenshot}" class="img-fluid rounded border border-success" style="max-height: 320px; object-fit: contain; box-shadow: 0 4px 12px rgba(0,0,0,0.3);" alt="Current Screenshot">
                            <div class="badge bg-success mt-1 d-block text-center py-2" style="font-size:0.75rem;">Current Run Screenshot</div>
                        </div>
                    </div>
                </div>
            `;
        } else if (r.screenshot) {
            const label = r.status === "New Baseline" ? "New Baseline" : "Visual Match";
            const badgeColor = r.status === "New Baseline" ? "info" : "success";
            detailsHtml += `
                <div class="mt-3" style="max-width: 320px;">
                    <img src="data:image/png;base64,${r.screenshot}" 
                         class="img-fluid rounded border border-${badgeColor}"
                         style="max-height: 240px; object-fit: contain; box-shadow: 0 4px 12px rgba(0,0,0,0.3);"
                         alt="Screenshot">
                    <span class="badge bg-${badgeColor} d-block text-center mt-1 py-2" style="font-size:0.75rem;">${label}</span>
                </div>
            `;
        }

        html += `
            <tr class="fade-in" style="animation-delay: ${index * 0.05}s;">
                <td><span style="font-weight: 600; color: var(--text-secondary);">#${r.step}</span></td>
                <td style="font-size: 0.88rem; font-family: var(--font-mono, monospace);">${r.command}</td>
                <td>
                    <span class="badge ${badgeClass}">
                        <i class="fas ${iconClass} me-1"></i>${r.status}
                    </span>
                </td>
                <td style="font-size: 0.85rem; color: var(--text-secondary);">${detailsHtml}</td>
            </tr>
        `;
    });

    html += "</tbody></table>";
    resultsContainer.innerHTML = html;
}


// ================= VOICE INPUT =================

if (voiceBtn) {
    let recognition = null;
    let isListening = false;

    voiceBtn.addEventListener("click", () => {
        if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
            showToast("Voice recognition is not supported in your browser. Try Chrome.", "warning");
            return;
        }

        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

        if (isListening && recognition) {
            recognition.stop();
            return;
        }

        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = false;

        // Detect language from any hint or default to English
        const langMap = {
            'en': 'en-US', 'hi': 'hi-IN', 'mr': 'mr-IN', 'es': 'es-ES', 'fr': 'fr-FR'
        };
        recognition.lang = 'en-US';

        recognition.onstart = () => {
            isListening = true;
            voiceBtn.innerHTML = '<i class="fas fa-microphone-slash"></i> Stop Voice';
            voiceBtn.classList.remove('btn-info');
            voiceBtn.classList.add('btn-danger');
            showToast("🎤 Listening... Speak your commands.", "info");
        };

        recognition.onresult = (event) => {
            const commandsArea = document.getElementById("commands");
            let transcript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                if (event.results[i].isFinal) {
                    transcript += event.results[i][0].transcript + '\n';
                }
            }
            if (transcript) {
                commandsArea.value += (commandsArea.value ? '\n' : '') + transcript.trim();
            }
        };

        recognition.onerror = (event) => {
            console.error("Speech error:", event.error);
            if (event.error !== 'no-speech') {
                showToast(`Voice error: ${event.error}`, "error");
            }
        };

        recognition.onend = () => {
            isListening = false;
            voiceBtn.innerHTML = '<i class="fas fa-microphone"></i> Voice Input';
            voiceBtn.classList.remove('btn-danger');
            voiceBtn.classList.add('btn-info');
        };

        recognition.start();
    });
}


// ================= TRANSLATE (NL -> Commands) =================

if (translateBtn) {
    translateBtn.addEventListener("click", async () => {
        const commandsArea = document.getElementById("commands");
        const text = commandsArea.value.trim();

        if (!text) {
            showToast("Please enter some natural language text to translate.", "warning");
            return;
        }

        translateBtn.classList.add("is-loading");
        translateBtn.disabled = true;

        try {
            const response = await fetch("/translate", {
                method: "POST",
                headers: postHeaders(),
                body: JSON.stringify({ text: text })
            });

            const data = await response.json();

            if (data.error) {
                showToast(data.error, "error");
            } else if (data.translated) {
                commandsArea.value = data.translated;
                showToast("Commands translated successfully!", "success");
            }
        } catch (err) {
            console.error(err);
            showToast("Failed to translate commands.", "error");
        } finally {
            translateBtn.classList.remove("is-loading");
            translateBtn.disabled = false;
        }
    });
}


// ================= SAVE TEST CASE =================

if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
        const commands = document.getElementById("commands").value.trim();

        if (!commands) {
            showToast("Please enter test commands before saving.", "warning");
            return;
        }

        const name = prompt("Enter a name for this test suite:");
        if (!name || !name.trim()) return;

        saveBtn.classList.add("is-loading");
        saveBtn.disabled = true;

        try {
            const response = await fetch("/save-test-case", {
                method: "POST",
                headers: postHeaders(),
                body: JSON.stringify({ name: name.trim(), commands: commands })
            });

            const data = await response.json();

            if (data.error) {
                showToast(data.error, "error");
            } else {
                showToast(data.message || "Test suite saved!", "success");
            }
        } catch (err) {
            console.error(err);
            showToast("Failed to save test suite.", "error");
        } finally {
            saveBtn.classList.remove("is-loading");
            saveBtn.disabled = false;
        }
    });
}


// ================= APPROVE VISUAL BASELINE =================

if (approveBaselineBtn) {
    approveBaselineBtn.addEventListener("click", async () => {
        const testCaseId = document.getElementById("test-case-id")?.value;

        if (!testCaseId || !lastTestResult) {
            showToast("No test case or results to approve.", "warning");
            return;
        }

        approveBaselineBtn.classList.add("is-loading");
        approveBaselineBtn.disabled = true;

        try {
            const response = await fetch("/approve-baseline", {
                method: "POST",
                headers: postHeaders(),
                body: JSON.stringify({
                    test_case_id: testCaseId,
                    results: lastTestResult.results
                })
            });

            const data = await response.json();

            if (data.error) {
                showToast(data.error, "error");
            } else {
                showToast(data.message || "Baseline approved!", "success");
                document.getElementById("visual-test-actions").classList.add("d-none");
            }
        } catch (err) {
            console.error(err);
            showToast("Failed to approve baseline.", "error");
        } finally {
            approveBaselineBtn.classList.remove("is-loading");
            approveBaselineBtn.disabled = false;
        }
    });
}


// ================= GENERATE SCRIPT (AI) =================

if (generateScriptConfirmBtn) {
    generateScriptConfirmBtn.addEventListener("click", async () => {
        const url = document.getElementById("url").value.trim();
        const goal = document.getElementById("test-goal-input").value.trim();

        if (!url || !goal) {
            showToast("Please enter a website URL and test goal.", "warning");
            return;
        }

        generateScriptConfirmBtn.classList.add("is-loading");
        generateScriptConfirmBtn.disabled = true;

        try {
            const response = await fetch("/generate-script", {
                method: "POST",
                headers: postHeaders(),
                body: JSON.stringify({ url: url, goal: goal })
            });

            const data = await response.json();

            if (data.error) {
                showToast(data.error, "error");
                return;
            }

            document.getElementById("commands").value = data.script;
            showToast("AI script generated successfully!", "success");

            document.activeElement.blur();
            const modalEl = document.getElementById("generateScriptModal");
            const modal = bootstrap.Modal.getInstance(modalEl);
            modal.hide();

        } catch (err) {
            console.error(err);
            showToast("Failed to generate script.", "error");
        } finally {
            generateScriptConfirmBtn.classList.remove("is-loading");
            generateScriptConfirmBtn.disabled = false;
        }
    });
}


// ================= DOWNLOAD PDF =================

function downloadPDF() {
    if (!lastTestResult) { showToast("Please run a test first.", "warning"); return; }

    downloadPdfBtn.classList.add("is-loading"); downloadPdfBtn.disabled = true;

    fetch("/export/pdf", {
        method: "POST",
        headers: postHeaders(),
        body: JSON.stringify({
            url: document.getElementById("url").value.trim(),
            summary: lastTestResult.summary,
            results: lastTestResult.results
        })
    })
    .then(res => res.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "Test_Report.pdf"; a.click();
        showToast("PDF report downloaded!", "success");
    })
    .catch(err => { console.error(err); showToast("Failed to download PDF.", "error"); })
    .finally(() => { downloadPdfBtn.classList.remove("is-loading"); downloadPdfBtn.disabled = false; });
}


// ================= DOWNLOAD EXCEL =================

function downloadExcel() {
    if (!lastTestResult) { showToast("Please run a test first.", "warning"); return; }

    downloadExcelBtn.classList.add("is-loading"); downloadExcelBtn.disabled = true;

    fetch("/export/excel", {
        method: "POST",
        headers: postHeaders(),
        body: JSON.stringify({ results: lastTestResult.results })
    })
    .then(res => res.blob())
    .then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = "Test_Report.xlsx"; a.click();
        showToast("Excel report downloaded!", "success");
    })
    .catch(err => { console.error(err); showToast("Failed to download Excel.", "error"); })
    .finally(() => { downloadExcelBtn.classList.remove("is-loading"); downloadExcelBtn.disabled = false; });
}


// ================= BUTTON EVENTS =================

if (runTestBtn) {
    const isVisual = document.getElementById("is-visual-test")?.value === 'True';
    runTestBtn.addEventListener("click", () => runTest(isVisual));
}

if (downloadPdfBtn) downloadPdfBtn.addEventListener("click", downloadPDF);
if (downloadExcelBtn) downloadExcelBtn.addEventListener("click", downloadExcel);


// ================= PREMIUM TEST LOADING OVERLAY v2 (TLO) =================

(function () {
    const overlay    = document.getElementById('test-loading-overlay');
    if (!overlay) return;

    const progressEl  = document.getElementById('tlo-progress');
    const labelEl     = document.getElementById('tlo-progress-label');
    const subtitleEl  = document.getElementById('tlo-subtitle');
    const tickerEl    = document.getElementById('tlo-ticker-text');
    const navBar      = document.getElementById('nav-progress-bar');

    const STEPS = 5;
    let _timer  = null;
    let _ptimer = null;
    let _ttimer = null;
    let _step   = -1;
    let _pct    = 0;
    let _subIdx = 0;
    let _tickIdx = 0;

    const SUBTITLES = [
        'Initialising test environment\u2026',
        'Launching headless browser\u2026',
        'Navigating to target URL\u2026',
        'Executing test commands\u2026',
        'Waiting for DOM elements\u2026',
        'Running assertions\u2026',
        'AI is analysing results\u2026',
        'Compiling test report\u2026',
    ];

    const TICKER_CMDS = [
        'init selenium driver --headless',
        'webdriver.Chrome(options)',
        'driver.get("' + (document.getElementById('url')?.value || 'target_url') + '")',
        'WebDriverWait(driver, 10)',
        'find_element(By.ID, ...)',
        'element.send_keys(...)',
        'element.click()',
        'assert text_in_page(...)',
        'driver.get_screenshot_as_png()',
        'running ai bug analysis...',
        'generate_pdf_report()',
        'test run complete ✓',
    ];

    const STEP_TIMINGS = [600, 1600, 2800, 4200, 5800];
    const STEP_PCTS    = [12,   30,   55,   78,   93];

    const PARTICLE_CONFIGS = [
        { color: '#6366f1', minSize: 3, maxSize: 6 },
        { color: '#818cf8', minSize: 2, maxSize: 4 },
        { color: '#06b6d4', minSize: 3, maxSize: 5 },
        { color: '#22d3ee', minSize: 2, maxSize: 3 },
        { color: '#8b5cf6', minSize: 4, maxSize: 7 },
        { color: '#ffffff', minSize: 1, maxSize: 2 },
    ];

    // ── Particles ──
    function spawnParticles() {
        overlay.querySelectorAll('.tlo-particle').forEach(p => p.remove());
        for (let i = 0; i < 24; i++) {
            const cfg      = PARTICLE_CONFIGS[Math.floor(Math.random() * PARTICLE_CONFIGS.length)];
            const size     = cfg.minSize + Math.random() * (cfg.maxSize - cfg.minSize);
            const duration = 5 + Math.random() * 8;
            const delay    = Math.random() * 6;
            const left     = 3 + Math.random() * 94;
            const bottom   = 5 + Math.random() * 25;
            const p = document.createElement('div');
            p.className = 'tlo-particle';
            p.style.cssText =
                `left:${left}%;bottom:${bottom}%;` +
                `width:${size}px;height:${size}px;` +
                `background:${cfg.color};` +
                `animation-duration:${duration}s;animation-delay:${delay}s;`;
            overlay.appendChild(p);
        }
    }

    // ── Progress ──
    function setProgress(pct) {
        _pct = Math.min(100, pct);
        if (progressEl) progressEl.style.width = _pct + '%';
        if (labelEl)    labelEl.textContent     = Math.round(_pct) + '%';
        // mirror on nav bar
        if (navBar) {
            navBar.style.width = _pct + '%';
            navBar.classList.add('running');
        }
    }

    // ── Steps ──
    const ORIG_ICONS = ['fa-server','fa-globe','fa-list-check','fa-brain','fa-file-chart-column'];
    function activateStep(idx) {
        for (let i = 0; i < STEPS; i++) {
            const el = document.getElementById('tlo-step-' + i);
            if (!el) continue;
            el.classList.remove('active', 'done');
            if (i < idx)  el.classList.add('done');
            if (i === idx) el.classList.add('active');
            const icon = el.querySelector('.tlo-step-icon i');
            if (!icon) continue;
            icon.className = 'fas ' + (i < idx ? 'fa-check' : (ORIG_ICONS[i] || 'fa-circle'));
        }
        _step = idx;
    }

    // ── Subtitle cycler ──
    function cycleSubtitle() {
        if (!subtitleEl) return;
        subtitleEl.style.opacity = '0';
        setTimeout(() => {
            _subIdx = (_subIdx + 1) % SUBTITLES.length;
            subtitleEl.textContent = SUBTITLES[_subIdx];
            subtitleEl.style.opacity = '1';
        }, 350);
    }

    // ── Terminal ticker cycler ──
    function cycleTicker() {
        if (!tickerEl) return;
        // Update the URL step's arg dynamically
        const urlVal = document.getElementById('url')?.value?.trim();
        if (urlVal) TICKER_CMDS[2] = 'driver.get("' + urlVal.substring(0, 28) + (urlVal.length > 28 ? '…' : '') + '")';
        _tickIdx = (_tickIdx + 1) % TICKER_CMDS.length;
        tickerEl.textContent = TICKER_CMDS[_tickIdx];
    }

    // ── Reset ──
    function resetAll() {
        setProgress(0);
        _step = -1; _subIdx = 0; _tickIdx = 0;
        if (subtitleEl) { subtitleEl.style.opacity = '1'; subtitleEl.textContent = SUBTITLES[0]; }
        if (tickerEl)   tickerEl.textContent = TICKER_CMDS[0];
        for (let i = 0; i < STEPS; i++) {
            const el = document.getElementById('tlo-step-' + i);
            if (!el) continue;
            el.classList.remove('active', 'done');
            const icon = el.querySelector('.tlo-step-icon i');
            if (icon) icon.className = 'fas ' + (ORIG_ICONS[i] || 'fa-circle');
        }
    }

    // ── Public API ──
    window.tloShow = function () {
        resetAll();
        spawnParticles();
        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';

        const startTime = Date.now();
        _timer = setInterval(() => {
            const elapsed = Date.now() - startTime;
            for (let i = STEPS - 1; i >= 0; i--) {
                if (elapsed >= STEP_TIMINGS[i] && _step < i) {
                    activateStep(i);
                    setProgress(STEP_PCTS[i]);
                    break;
                }
            }
        }, 100);

        _ptimer = setInterval(cycleSubtitle, 2800);
        _ttimer = setInterval(cycleTicker,   1200);
    };

    window.tloHide = function () {
        activateStep(STEPS - 1);
        setProgress(100);
        if (navBar) navBar.style.width = '100%';
        setTimeout(() => {
            overlay.classList.remove('active');
            document.body.style.overflow = '';
            if (navBar) {
                navBar.style.opacity = '0';
                setTimeout(() => {
                    navBar.style.width   = '0%';
                    navBar.style.opacity = '';
                    navBar.classList.remove('running');
                }, 400);
            }
            clearInterval(_timer);
            clearInterval(_ptimer);
            clearInterval(_ttimer);
        }, 550);
    };

    // ── Nav progress bar for page links ──
    // Shows a slim bar at top when clicking any non-ajax <a> link
    document.addEventListener('click', function (e) {
        const a = e.target.closest('a[href]');
        if (!a || !navBar) return;
        const href = a.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript') ||
            a.getAttribute('target') === '_blank' || e.ctrlKey || e.metaKey) return;
        // Skip download links
        if (a.hasAttribute('download')) return;
        navBar.style.width   = '0%';
        navBar.style.opacity = '1';
        navBar.classList.add('running');
        setTimeout(() => { navBar.style.width = '70%'; }, 30);
    });

    window.toggleVisualMode = function(uniqueId, mode) {
        const baselinePane = document.getElementById(`${uniqueId}-baseline`);
        const diffPane     = document.getElementById(`${uniqueId}-diff`);
        const currentPane  = document.getElementById(`${uniqueId}-current`);
        
        if (!baselinePane || !diffPane || !currentPane) return;
        
        baselinePane.classList.add('d-none');
        diffPane.classList.add('d-none');
        currentPane.classList.add('d-none');
        
        if (mode === 'baseline') baselinePane.classList.remove('d-none');
        else if (mode === 'diff') diffPane.classList.remove('d-none');
        else if (mode === 'current') currentPane.classList.remove('d-none');
        
        const container = document.getElementById(`${uniqueId}-container`);
        if (container) {
            const btnGroup = container.previousElementSibling;
            if (btnGroup) {
                btnGroup.querySelectorAll('button').forEach(btn => {
                    const btnText = btn.textContent.toLowerCase();
                    const isActive = btnText.includes(mode) || (mode === 'current' && btnText.includes('current'));
                    btn.classList.toggle('active', isActive);
                });
            }
        }
    };

})();

