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

document.addEventListener('DOMContentLoaded', function () {
    const analyzeCodeBtn = document.getElementById('analyze-code-btn');
    const generateTestsBtn = document.getElementById('generate-tests-btn');
    const refactorCodeBtn = document.getElementById('refactor-code-btn');
    const codeInput = document.getElementById('code-input');
    const resultsOutput = document.getElementById('results-output');
    const spinner = document.getElementById('spinner-analysis');
    const downloadPdfBtn = document.getElementById('download-analysis-pdf');

    let lastAIResultMarkdown = ''; // Store the last AI Markdown result

    // --- PDF Download Logic ---
    downloadPdfBtn.addEventListener('click', async () => {
        if (!lastAIResultMarkdown) {
            showToast("Please generate an analysis before downloading.", "warning");
            return;
        }

        // Loading state
        downloadPdfBtn.classList.add('is-loading');
        downloadPdfBtn.disabled = true;

        try {
            const response = await fetch('/download_code_analysis_pdf', {
                method: 'POST',
                headers: postHeaders(),
                body: JSON.stringify({
                    ai_result_markdown: lastAIResultMarkdown,
                    code: codeInput.value
                }),
            });

            if (response.ok) {
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.style.display = 'none';
                a.href = url;
                a.download = 'ai_code_analysis_report.pdf';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                showToast("PDF report downloaded!", "success");
            } else {
                const errorData = await response.json();
                showToast(`Error generating PDF: ${errorData.error || response.statusText}`, "error");
            }
        } catch (error) {
            console.error('Download PDF error:', error);
            showToast("An error occurred while downloading the PDF.", "error");
        } finally {
            downloadPdfBtn.classList.remove('is-loading');
            downloadPdfBtn.disabled = false;
        }
    });

    // --- AI Request Logic ---
    const handleAIRequest = async (endpoint) => {
        const code = codeInput.value;
        if (!code) {
            showToast("Please enter some code first.", "warning");
            return;
        }

        spinner.classList.remove('d-none');
        resultsOutput.innerHTML = `
            <div class="text-center py-4">
                <p class="loading-text">AI is analyzing your code...</p>
            </div>`;

        // Disable all action buttons
        analyzeCodeBtn.classList.add('is-loading');
        generateTestsBtn.classList.add('is-loading');
        refactorCodeBtn.classList.add('is-loading');
        analyzeCodeBtn.disabled = true;
        generateTestsBtn.disabled = true;
        refactorCodeBtn.disabled = true;
        downloadPdfBtn.disabled = true;

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: postHeaders(),
                body: JSON.stringify({ code: code }),
            });

            const data = await response.json();

            if (data.result) {
                lastAIResultMarkdown = data.result;
                resultsOutput.innerHTML = marked.parse(data.result);
                resultsOutput.querySelectorAll('pre code').forEach((block) => {
                    hljs.highlightElement(block);
                });
                showToast("Analysis complete!", "success");
            } else {
                resultsOutput.innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-circle me-2"></i>Error: ${data.error}
                    </div>`;
                lastAIResultMarkdown = '';
                showToast("Analysis failed.", "error");
            }
        } catch (error) {
            resultsOutput.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle me-2"></i>An unexpected error occurred: ${error}
                </div>`;
            lastAIResultMarkdown = '';
            showToast("An unexpected error occurred.", "error");
        } finally {
            spinner.classList.add('d-none');
            analyzeCodeBtn.classList.remove('is-loading');
            generateTestsBtn.classList.remove('is-loading');
            refactorCodeBtn.classList.remove('is-loading');
            analyzeCodeBtn.disabled = false;
            generateTestsBtn.disabled = false;
            refactorCodeBtn.disabled = false;
            if (lastAIResultMarkdown) {
                downloadPdfBtn.disabled = false;
            }
        }
    };

    analyzeCodeBtn.addEventListener('click', () => {
        handleAIRequest('/analyze-code');
    });

    generateTestsBtn.addEventListener('click', () => {
        handleAIRequest('/generate-tests');
    });

    refactorCodeBtn.addEventListener('click', () => {
        handleAIRequest('/refactor-code');
    });
});