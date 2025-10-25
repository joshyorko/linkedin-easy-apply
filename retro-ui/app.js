// LinkedIn Easy Apply Retro Terminal UI
// Main Application Logic

// Configuration
const CONFIG = {
    ACTION_SERVER_URL: 'http://localhost:8082',  // Updated to match running server
    PROXY_SERVER_URL: 'http://localhost:3001',
    REFRESH_INTERVAL: 5000,
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
    startAutoRefresh();
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
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions`);
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
        log('info', 'Loading statistics from database...');
        
        // Query total jobs
        const totalResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'SELECT COUNT(*) as count FROM job_postings'
            })
        });
        
        if (totalResponse.ok) {
            const totalData = await totalResponse.json();
            state.stats.totalJobs = totalData.results[0]?.count || 0;
            document.getElementById('total-jobs').textContent = state.stats.totalJobs;
        }
        
        // Query good fit jobs
        const goodFitResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'SELECT COUNT(*) as count FROM job_postings WHERE good_fit = 1'
            })
        });
        
        if (goodFitResponse.ok) {
            const goodFitData = await goodFitResponse.json();
            state.stats.goodFitJobs = goodFitData.results[0]?.count || 0;
            document.getElementById('good-fit-jobs').textContent = state.stats.goodFitJobs;
        }
        
        // Query applied jobs
        const appliedResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'SELECT COUNT(*) as count FROM job_postings WHERE is_applied = 1'
            })
        });
        
        if (appliedResponse.ok) {
            const appliedData = await appliedResponse.json();
            state.stats.appliedJobs = appliedData.results[0]?.count || 0;
            document.getElementById('applied-jobs').textContent = state.stats.appliedJobs;
        }
        
        // Query active profile
        const profileResponse = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'SELECT profile_name FROM user_profiles WHERE is_active = 1'
            })
        });
        
        if (profileResponse.ok) {
            const profileData = await profileResponse.json();
            const profileName = profileData.results[0]?.profile_name || 'NONE';
            state.stats.activeProfile = profileName;
            document.getElementById('active-profile').textContent = profileName;
        }
        
        log('success', 'Statistics loaded successfully');
    } catch (error) {
        log('error', `Failed to load statistics: ${error.message}`);
    }
}

// Auto-refresh stats
function startAutoRefresh() {
    setInterval(() => {
        loadStats();
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
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/search-linkedin-easy-apply/run`, {
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
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: `SELECT DISTINCT run_id, COUNT(*) as job_count, 
                        MAX(scraped_at) as last_scraped 
                        FROM job_postings 
                        WHERE run_id LIKE 'search_%' 
                        GROUP BY run_id 
                        ORDER BY last_scraped DESC 
                        LIMIT 10`
            })
        });
        
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
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: `SELECT job_id, title, company, location_raw, good_fit, 
                        is_applied, fit_score, job_url 
                        FROM job_postings 
                        WHERE run_id = '${runId}' 
                        ORDER BY fit_score DESC`
            })
        });
        
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
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: `SELECT * FROM job_postings WHERE job_id = '${jobId}'`
            })
        });
        
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
        
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/enrich-and-generate-answers/run`, {
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
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: `SELECT job_id, title, company, location_raw, good_fit, 
                        is_applied, fit_score, job_url 
                        FROM job_postings 
                        WHERE good_fit = 1 
                        ORDER BY fit_score DESC 
                        LIMIT 50`
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            state.jobs = data.results;
            displayJobs(state.jobs);
            log('success', `Loaded ${data.results.length} good fit jobs`);
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

async function applyToGoodFitJobs() {
    closeModal();
    log('info', 'Starting batch application to all good fit jobs...');
    log('warning', 'This may take several minutes per job...');
    
    // Implementation would call the batch apply action
    log('info', 'Feature in development - use individual apply for now');
}

async function applyToSingleJob(jobId) {
    closeModal();
    log('info', `Applying to job: ${jobId}...`);
    
    try {
        const response = await fetch(`${CONFIG.ACTION_SERVER_URL}/api/actions/apply-to-job-by-url/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_id: jobId })
        });
        
        if (response.ok) {
            const result = await response.json();
            log('success', `Application submitted for job: ${jobId}`);
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
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: 'SELECT * FROM user_profiles WHERE is_active = 1'
            })
        });
        
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
        const response = await fetch(`${CONFIG.PROXY_SERVER_URL}/api/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: `SELECT job_id, title, company, updated_at 
                        FROM job_postings 
                        WHERE is_applied = 1 
                        ORDER BY updated_at DESC 
                        LIMIT 50`
            })
        });
        
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
function viewLogs() {
    const logContent = `
        <div style="color: #00ff00;">
            <h3>Recent Log Files:</h3>
            <p style="margin: 20px 0;">
                Log files are stored in: <strong>output/</strong> directory<br>
                Each search/apply session creates a separate log folder.
            </p>
            <p>
                To view detailed logs with screenshots:<br>
                1. Navigate to <code>output/{run_id}/log.html</code><br>
                2. Open in browser for full report
            </p>
            <div style="margin-top: 30px; text-align: center;">
                <button class="retro-btn" onclick="window.open('output/', '_blank')" 
                        style="display: inline-block; width: auto;">
                    📂 OPEN OUTPUT FOLDER
                </button>
            </div>
        </div>
    `;
    openModal('LOG FILES', logContent);
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
