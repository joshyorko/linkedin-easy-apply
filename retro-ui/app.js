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
    }
};

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
    setInterval(() => {
        loadStats(true);  // Pass true to indicate auto-refresh (silent mode)
        checkServerStatus();
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
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Search failed: ${error.message}`);
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
    
    panel.style.display = 'block';
}

function closeJobsPanel() {
    document.getElementById('jobs-panel').style.display = 'none';
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
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Enrichment failed: ${error.message}`);
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
        <div style="text-align: center;">
            <button class="retro-btn" onclick="applyToGoodFitJobs()">
                ▶ APPLY TO ALL GOOD FITS
            </button>
            <button class="retro-btn" onclick="applyByRunId()">
                ▶ APPLY BY RUN ID
            </button>
            <button class="retro-btn" onclick="applyToSelectedJobs()">
                ▶ APPLY TO SELECTED JOBS
            </button>
            <p style="margin-top: 20px; color: #ffaa00;">
                ⚠️ WARNING: This will automatically apply to jobs using saved profile
            </p>
        </div>
    `;
    openModal('APPLICATION MENU', menuHtml);
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
            } else {
                log('error', `Application failed: ${result.result?.error || 'Unknown error'}`);
            }
            loadStats();
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Application failed: ${error.message}`);
    }
}

// Check Ready Jobs
async function checkReadyJobs() {
    log('info', 'Checking which jobs are ready to apply...');
    log('info', 'This queries the database for enriched jobs with good fit scores...');
    
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
                } else {
                    throw new Error('Failed to fetch job details from database');
                }
            } else {
                displayReadyJobs([]);
                log('warning', '⚠️ No jobs ready to apply. Make sure to:');
                log('info', '  1. Run a job search first');
                log('info', '  2. Run AI enrichment to analyze jobs');
                log('info', '  3. Check that you have a profile uploaded');
            }
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `❌ Check failed: ${error.message}`);
        log('error', 'Make sure the Action Server is running and accessible');
    }
}

// Display Ready Jobs in Panel
function displayReadyJobs(jobs) {
    const jobsPanel = document.getElementById('jobs-panel');
    const jobsContent = document.getElementById('jobs-content');
    
    if (!jobs || jobs.length === 0) {
        jobsContent.innerHTML = '<div class="job-item" style="text-align: center; color: #ffaa00;">NO JOBS READY TO APPLY</div>';
        jobsPanel.style.display = 'block';
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
    jobsPanel.style.display = 'block';
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
    log('info', `Applying to job: ${jobId}...`);
    if (!allowSubmit) {
        log('warning', 'DRY RUN mode - application will NOT be submitted');
    }
    
    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/linkedin-easy-apply-server/apply-to-job-by-url/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                job_url: jobId,
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
            } else {
                log('error', `Application failed: ${result.result?.error || 'Unknown error'}`);
            }
            loadStats();
        } else {
            throw new Error(`Server returned ${response.status}`);
        }
    } catch (error) {
        log('error', `Application failed: ${error.message}`);
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

// Utility Functions
function applyByRunId() {
    const runId = prompt('Enter run_id to apply:');
    if (runId) {
        closeModal();
        log('info', `Applying to all jobs in run: ${runId}...`);
        // Implementation would call batch apply by run_id
        log('info', 'Feature in development');
    }
}

function applyToSelectedJobs() {
    closeModal();
    log('info', 'Selected job application feature coming soon...');
}

// Export for debugging
window.appState = state;
window.appConfig = CONFIG;
