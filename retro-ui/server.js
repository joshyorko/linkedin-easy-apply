const express = require('express');
const cors = require('cors');
const path = require('path');
const fetch = require('node-fetch');

const app = express();
const PORT = process.env.PORT || 3001;
const ACTION_SERVER_URL = process.env.ACTION_SERVER_URL || 'http://localhost:8082';
// Optional API key to authenticate with action server (kept server-side)
const ACTION_SERVER_API_KEY = process.env.ACTION_SERVER_API_KEY || null;
const DATABASE_TYPE = process.env.DATABASE_TYPE || 'sqlite';

// Database setup based on type
let db;
let dbType = DATABASE_TYPE;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

// Serve output directory (logs) from parent folder
app.use('/output', express.static(path.join(__dirname, '..', 'output')));

// Database connection
function initDatabase() {
    if (dbType === 'postgres') {
        // PostgreSQL setup
        const { Client } = require('pg');
        const DATABASE_URL = process.env.DATABASE_URL || 'postgresql://linkedin_user:dev_password@postgres:5432/linkedin_jobs';
        
        db = new Client({ connectionString: DATABASE_URL });
        db.connect()
            .then(() => {
                console.log('✅ PostgreSQL database connected successfully');
                console.log('📂 Database URL:', DATABASE_URL.replace(/:[^:@]+@/, ':****@')); // Hide password
            })
            .catch(err => {
                console.error('❌ Error connecting to PostgreSQL:', err.message);
                console.log('Falling back to SQLite...');
                dbType = 'sqlite';
                initSQLite();
            });
    } else {
        initSQLite();
    }
}

function initSQLite() {
    const sqlite3 = require('sqlite3').verbose();
    const DB_PATH = process.env.DB_PATH || path.join(__dirname, '..', 'src', 'linkedin_jobs.sqlite');
    
    db = new sqlite3.Database(DB_PATH, sqlite3.OPEN_READONLY, (err) => {
        if (err) {
            console.error('❌ Error opening database:', err.message);
            console.log('Looking for database at:', DB_PATH);
            // Try alternate path
            const alternatePath = path.join(__dirname, '..', 'linkedin_jobs.sqlite');
            db = new sqlite3.Database(alternatePath, sqlite3.OPEN_READONLY, (err2) => {
                if (err2) {
                    console.error('❌ Error opening alternate database:', err2.message);
                    process.exit(1);
                }
                console.log('✅ SQLite database connected (alternate path)');
            });
        } else {
            console.log('✅ SQLite database connected successfully');
            console.log('📂 Database path:', DB_PATH);
        }
    });
}

// Helper function to execute queries based on database type
async function executeQuery(query, params = []) {
    return new Promise((resolve, reject) => {
        if (dbType === 'postgres') {
            db.query(query, params)
                .then(result => resolve(result.rows))
                .catch(err => reject(err));
        } else {
            // SQLite
            db.all(query, params, (err, rows) => {
                if (err) reject(err);
                else resolve(rows);
            });
        }
    });
}

// API Routes

// Internal query helper - NOT exposed as endpoint
async function internalQuery(query, params = []) {
    try {
        const rows = await executeQuery(query, params);
        return { success: true, results: rows, count: rows.length };
    } catch (err) {
        console.error('❌ Query error:', err.message);
        throw err;
    }
}

// Predefined safe query endpoints - no raw SQL exposure
app.get('/api/query/total-jobs', async (req, res) => {
    try {
        const result = await internalQuery('SELECT COUNT(*) as count FROM job_postings');
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/good-fit-count', async (req, res) => {
    try {
        const result = await internalQuery('SELECT COUNT(*) as count FROM job_postings WHERE good_fit = true OR good_fit = 1');
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/applied-count', async (req, res) => {
    try {
        const result = await internalQuery('SELECT COUNT(*) as count FROM job_postings WHERE is_applied = true OR is_applied = 1');
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/active-profile', async (req, res) => {
    try {
        const result = await internalQuery('SELECT profile_name FROM user_profiles WHERE is_active = true OR is_active = 1');
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/runs-with-stats', async (req, res) => {
    try {
        const query = `
            SELECT DISTINCT run_id, 
            COUNT(*) as job_count,
            MAX(scraped_at) as timestamp,
            GROUP_CONCAT(DISTINCT CASE WHEN is_applied = 1 THEN job_id END) as applied_jobs
            FROM job_postings 
            GROUP BY run_id 
            ORDER BY timestamp DESC 
            LIMIT 20
        `;
        const result = await internalQuery(query);
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/job-details/:jobId', async (req, res) => {
    const { jobId } = req.params;
    try {
        const query = dbType === 'postgres' 
            ? 'SELECT * FROM job_postings WHERE job_id = $1'
            : 'SELECT * FROM job_postings WHERE job_id = ?';
        const result = await internalQuery(query, [jobId]);
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/jobs-by-run/:runId', async (req, res) => {
    const { runId } = req.params;
    try {
        const query = `
            SELECT job_id, title, company, location_raw, location_type, 
                   good_fit, is_applied, fit_score, job_url, 
                   ai_confidence_score, experience_level
            FROM job_postings 
            WHERE run_id = ${dbType === 'postgres' ? '$1' : '?'}
            ORDER BY fit_score DESC
        `;
        const result = await internalQuery(query, [runId]);
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/jobs-by-ids', async (req, res) => {
    const { ids } = req.query;
    if (!ids) {
        return res.status(400).json({ error: 'ids parameter required' });
    }
    
    try {
        const jobIds = ids.split(',').map(id => id.trim());
        const placeholders = jobIds.map((_, i) => dbType === 'postgres' ? `$${i+1}` : '?').join(',');
        const query = `
            SELECT job_id, title, company, location_raw, good_fit, 
                   fit_score, job_url, date_posted 
            FROM job_postings 
            WHERE job_id IN (${placeholders})
            ORDER BY fit_score DESC
        `;
        const result = await internalQuery(query, jobIds);
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/search-history', async (req, res) => {
    try {
        const query = `
            SELECT DISTINCT run_id, COUNT(*) as job_count, 
                    MAX(scraped_at) as last_scraped 
            FROM job_postings 
            WHERE run_id LIKE 'search_%' 
            GROUP BY run_id 
            ORDER BY last_scraped DESC 
            LIMIT 10
        `;
        const result = await internalQuery(query);
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

app.get('/api/query/application-history', async (req, res) => {
    const limit = req.query.limit || 50;
    try {
        const query = `
            SELECT job_id, title, company, updated_at 
            FROM job_postings 
            WHERE is_applied = ${dbType === 'postgres' ? 'true' : '1'} 
            ORDER BY updated_at DESC 
            LIMIT ${dbType === 'postgres' ? '$1' : '?'}
        `;
        const result = await internalQuery(query, [limit]);
        res.json(result);
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

// Query database (safe, read-only) - DEPRECATED but kept for backwards compatibility
// TODO: Remove this in future version after migrating all calls to specific endpoints
app.post('/api/query', async (req, res) => {
    const { query } = req.body;
    
    if (!query) {
        return res.status(400).json({ error: 'Query is required' });
    }
    
    // Security: Only allow SELECT queries
    if (!query.trim().toLowerCase().startsWith('select')) {
        return res.status(403).json({ error: 'Only SELECT queries are allowed' });
    }
    
    console.log('⚠️  DEPRECATED: /api/query endpoint used. Please migrate to specific endpoints.');
    console.log('📊 Executing query:', query);
    
    try {
        const rows = await executeQuery(query, []);
        res.json({
            success: true,
            results: rows,
            count: rows.length
        });
    } catch (err) {
        console.error('❌ Query error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get database stats
app.get('/api/stats', async (req, res) => {
    try {
        const stats = {};
        
        const totalResult = await executeQuery('SELECT COUNT(*) as count FROM job_postings');
        stats.totalJobs = totalResult[0].count;
        
        const goodFitResult = await executeQuery('SELECT COUNT(*) as count FROM job_postings WHERE good_fit = true OR good_fit = 1');
        stats.goodFitJobs = goodFitResult[0].count;
        
        const appliedResult = await executeQuery('SELECT COUNT(*) as count FROM job_postings WHERE is_applied = true OR is_applied = 1');
        stats.appliedJobs = appliedResult[0].count;
        
        const profileResult = await executeQuery('SELECT profile_name FROM user_profiles WHERE is_active = true OR is_active = 1');
        stats.activeProfile = profileResult.length > 0 ? profileResult[0].profile_name : 'NONE';
        
        res.json(stats);
    } catch (err) {
        console.error('❌ Stats error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get recent searches
app.get('/api/recent-searches', async (req, res) => {
    const query = `
        SELECT DISTINCT run_id, 
               COUNT(*) as job_count, 
               MAX(scraped_at) as last_scraped 
        FROM job_postings 
        WHERE run_id LIKE 'search_%' 
        GROUP BY run_id 
        ORDER BY last_scraped DESC 
        LIMIT 10
    `;
    
    try {
        const rows = await executeQuery(query);
        res.json(rows);
    } catch (err) {
        console.error('❌ Recent searches error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get jobs by run_id
app.get('/api/jobs/:runId', async (req, res) => {
    const { runId } = req.params;
    
    const query = `
        SELECT job_id, title, company, location_raw, location_type, 
               good_fit, is_applied, fit_score, job_url, 
               ai_confidence_score, experience_level
        FROM job_postings 
        WHERE run_id = $1 
        ORDER BY fit_score DESC
    `;
    
    try {
        const rows = await executeQuery(dbType === 'postgres' ? query : query.replace('$1', '?'), [runId]);
        res.json(rows);
    } catch (err) {
        console.error('❌ Jobs by run_id error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get single job details
app.get('/api/job/:jobId', async (req, res) => {
    const { jobId } = req.params;
    
    const query = dbType === 'postgres' 
        ? 'SELECT * FROM job_postings WHERE job_id = $1'
        : 'SELECT * FROM job_postings WHERE job_id = ?';
    
    try {
        const rows = await executeQuery(query, [jobId]);
        if (rows.length === 0) {
            return res.status(404).json({ error: 'Job not found' });
        }
        res.json(rows[0]);
    } catch (err) {
        console.error('❌ Job details error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get good fit jobs
app.get('/api/good-fit-jobs', async (req, res) => {
    const limit = req.query.limit || 50;
    
    const query = `
        SELECT job_id, title, company, location_raw, location_type,
               good_fit, is_applied, fit_score, job_url,
               ai_confidence_score, experience_level
        FROM job_postings 
        WHERE good_fit = ${dbType === 'postgres' ? 'true' : '1'} 
        ORDER BY fit_score DESC 
        LIMIT ${dbType === 'postgres' ? '$1' : '?'}
    `;
    
    try {
        const rows = await executeQuery(query, [limit]);
        res.json(rows);
    } catch (err) {
        console.error('❌ Good fit jobs error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get application history
app.get('/api/application-history', async (req, res) => {
    const limit = req.query.limit || 50;
    
    const query = `
        SELECT job_id, title, company, location_raw, job_url, updated_at
        FROM job_postings 
        WHERE is_applied = ${dbType === 'postgres' ? 'true' : '1'} 
        ORDER BY updated_at DESC 
        LIMIT ${dbType === 'postgres' ? '$1' : '?'}
    `;
    
    try {
        const rows = await executeQuery(query, [limit]);
        res.json(rows);
    } catch (err) {
        console.error('❌ Application history error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get active profile
app.get('/api/profile', async (req, res) => {
    const query = dbType === 'postgres'
        ? 'SELECT * FROM user_profiles WHERE is_active = true'
        : 'SELECT * FROM user_profiles WHERE is_active = 1';

    try {
        const rows = await executeQuery(query);
        // Always return { results: [...] }
        res.json({ results: rows });
    } catch (err) {
        console.error('❌ Profile error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get all profiles (for profile selector)
app.get('/api/profiles', async (req, res) => {
    const limit = req.query.limit || 50;
    const query = `
        SELECT 
            profile_id, profile_name, profile_type, is_active,
            full_name, email, phone, phone_country,
            linkedin_url, github, website, portfolio_url,
            location, title, summary, skills,
            first_name, last_name,
            address_street, address_city, address_state, address_zip, address_country,
            work_authorization, requires_visa_sponsorship, security_clearance,
            veteran_status, disability_status, gender, race_ethnicity,
            salary_min, salary_max, salary_currency, earliest_start_date,
            willing_to_relocate, remote_preference, years_of_experience,
            applications_count, success_rate,
            source_file, source_type, version,
            created_at, updated_at, last_used_at
        FROM user_profiles 
        ORDER BY is_active DESC, updated_at DESC
        LIMIT ${dbType === 'postgres' ? '$1' : '?'}
    `;

    try {
        const rows = await executeQuery(query, [limit]);
        res.json({ success: true, profiles: rows });
    } catch (err) {
        console.error('❌ Profiles list error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Get single profile by ID
app.get('/api/profile/:profileId', async (req, res) => {
    const { profileId } = req.params;
    const query = dbType === 'postgres'
        ? 'SELECT * FROM user_profiles WHERE profile_id = $1'
        : 'SELECT * FROM user_profiles WHERE profile_id = ?';

    try {
        const rows = await executeQuery(query, [profileId]);
        if (rows.length === 0) {
            return res.status(404).json({ error: 'Profile not found' });
        }
        res.json({ success: true, profile: rows[0] });
    } catch (err) {
        console.error('❌ Profile fetch error:', err.message);
        res.status(500).json({ error: err.message });
    }
});

// Set active profile
app.post('/api/profile/:profileId/activate', async (req, res) => {
    const { profileId } = req.params;
    
    // Need writable database connection for this operation
    // Re-initialize with write access if needed
    if (dbType === 'sqlite') {
        const sqlite3 = require('sqlite3').verbose();
        const DB_PATH = process.env.DB_PATH || require('path').join(__dirname, '..', 'src', 'linkedin_jobs.sqlite');
        const writeDb = new sqlite3.Database(DB_PATH);
        
        try {
            await new Promise((resolve, reject) => {
                writeDb.run('UPDATE user_profiles SET is_active = 0', (err) => {
                    if (err) reject(err);
                    else resolve();
                });
            });
            
            await new Promise((resolve, reject) => {
                writeDb.run('UPDATE user_profiles SET is_active = 1, updated_at = datetime("now") WHERE profile_id = ?', [profileId], function(err) {
                    if (err) reject(err);
                    else if (this.changes === 0) reject(new Error('Profile not found'));
                    else resolve();
                });
            });
            
            writeDb.close();
            res.json({ success: true, message: 'Profile activated successfully' });
        } catch (err) {
            writeDb.close();
            console.error('❌ Profile activation error:', err.message);
            res.status(500).json({ error: err.message });
        }
    } else {
        // PostgreSQL
        try {
            await db.query('UPDATE user_profiles SET is_active = false');
            const result = await db.query('UPDATE user_profiles SET is_active = true, updated_at = NOW() WHERE profile_id = $1', [profileId]);
            if (result.rowCount === 0) {
                return res.status(404).json({ error: 'Profile not found' });
            }
            res.json({ success: true, message: 'Profile activated successfully' });
        } catch (err) {
            console.error('❌ Profile activation error:', err.message);
            res.status(500).json({ error: err.message });
        }
    }
});

// Update profile fields
app.put('/api/profile/:profileId', async (req, res) => {
    const { profileId } = req.params;
    const updates = req.body;
    
    // Whitelist of allowed fields to update
    const allowedFields = [
        'profile_name', 'full_name', 'first_name', 'last_name', 'email', 'phone', 'phone_country',
        'linkedin_url', 'github', 'website', 'portfolio_url', 'location', 'title', 'summary', 'skills',
        'address_street', 'address_city', 'address_state', 'address_zip', 'address_country',
        'work_authorization', 'requires_visa_sponsorship', 'security_clearance',
        'veteran_status', 'disability_status', 'gender', 'race_ethnicity',
        'salary_min', 'salary_max', 'salary_currency', 'earliest_start_date',
        'willing_to_relocate', 'remote_preference', 'years_of_experience'
    ];
    
    // Filter updates to only allowed fields
    const filteredUpdates = {};
    for (const [key, value] of Object.entries(updates)) {
        if (allowedFields.includes(key)) {
            filteredUpdates[key] = value;
        }
    }
    
    if (Object.keys(filteredUpdates).length === 0) {
        return res.status(400).json({ error: 'No valid fields to update' });
    }
    
    // Build update query
    const fields = Object.keys(filteredUpdates);
    const values = Object.values(filteredUpdates);
    
    if (dbType === 'sqlite') {
        const sqlite3 = require('sqlite3').verbose();
        const DB_PATH = process.env.DB_PATH || require('path').join(__dirname, '..', 'src', 'linkedin_jobs.sqlite');
        const writeDb = new sqlite3.Database(DB_PATH);
        
        const setClause = fields.map(f => `${f} = ?`).join(', ');
        const query = `UPDATE user_profiles SET ${setClause}, updated_at = datetime("now") WHERE profile_id = ?`;
        values.push(profileId);
        
        try {
            await new Promise((resolve, reject) => {
                writeDb.run(query, values, function(err) {
                    if (err) reject(err);
                    else if (this.changes === 0) reject(new Error('Profile not found'));
                    else resolve();
                });
            });
            
            writeDb.close();
            res.json({ success: true, message: 'Profile updated successfully', updatedFields: fields });
        } catch (err) {
            writeDb.close();
            console.error('❌ Profile update error:', err.message);
            res.status(500).json({ error: err.message });
        }
    } else {
        // PostgreSQL
        const setClause = fields.map((f, i) => `${f} = $${i + 1}`).join(', ');
        const query = `UPDATE user_profiles SET ${setClause}, updated_at = NOW() WHERE profile_id = $${fields.length + 1}`;
        values.push(profileId);
        
        try {
            const result = await db.query(query, values);
            if (result.rowCount === 0) {
                return res.status(404).json({ error: 'Profile not found' });
            }
            res.json({ success: true, message: 'Profile updated successfully', updatedFields: fields });
        } catch (err) {
            console.error('❌ Profile update error:', err.message);
            res.status(500).json({ error: err.message });
        }
    }
});

// Proxy to action server (forward GET/POST requests and attach API key if configured)
app.get('/api/action-server/*', async (req, res) => {
    const actionPath = req.params[0];
    const actionServerUrl = `${ACTION_SERVER_URL}/${actionPath}`;

    console.log('🔄 Proxying GET to action server:', actionServerUrl);

    try {
        const headers = {};
        if (ACTION_SERVER_API_KEY) {
            headers['Authorization'] = `Bearer ${ACTION_SERVER_API_KEY}`;
            headers['X-API-Key'] = ACTION_SERVER_API_KEY;
        }

        const response = await fetch(actionServerUrl, {
            method: 'GET',
            headers
        });

        const data = await response.text();
        // Try to parse JSON but fall back to text
        try {
            const json = JSON.parse(data);
            res.status(response.status).json(json);
        } catch (e) {
            res.status(response.status).send(data);
        }
    } catch (error) {
        console.error('❌ Proxy GET error:', error.message);
        res.status(500).json({ error: 'Failed to connect to action server' });
    }
});

app.post('/api/action-server/*', async (req, res) => {
    const actionPath = req.params[0];
    const actionServerUrl = `${ACTION_SERVER_URL}/${actionPath}`;
    
    console.log('🔄 Proxying POST to action server:', actionServerUrl);
    
    try {
        const headers = {
            'Content-Type': 'application/json',
        };
        if (ACTION_SERVER_API_KEY) {
            headers['Authorization'] = `Bearer ${ACTION_SERVER_API_KEY}`;
            headers['X-API-Key'] = ACTION_SERVER_API_KEY;
        }

        const response = await fetch(actionServerUrl, {
            method: 'POST',
            headers,
            body: JSON.stringify(req.body)
        });
        
        const data = await response.json();
        res.status(response.status).json(data);
    } catch (error) {
        console.error('❌ Proxy POST error:', error.message);
        res.status(500).json({ error: 'Failed to connect to action server' });
    }
});

// Health check
app.get('/api/health', (req, res) => {
    res.json({
        status: 'OK',
        database: db ? 'connected' : 'disconnected',
        databaseType: dbType,
        timestamp: new Date().toISOString()
    });
});

// Error handling
app.use((err, req, res, next) => {
    console.error('❌ Server error:', err);
    res.status(500).json({ error: 'Internal server error' });
});

// Start server
initDatabase();

app.listen(PORT, () => {
    console.log('');
    console.log('╔══════════════════════════════════════════════════════╗');
    console.log('║  LINKEDIN EASY APPLY - RETRO UI BACKEND SERVER      ║');
    console.log('╚══════════════════════════════════════════════════════╝');
    console.log('');
    console.log(`🚀 Server running on http://localhost:${PORT}`);
    console.log(`�️  Database Type: ${dbType.toUpperCase()}`);
    console.log(`🔗 Action Server: ${ACTION_SERVER_URL}`);
    console.log(`🔐 Action Server API key configured: ${ACTION_SERVER_API_KEY ? 'yes' : 'no'}`);
    console.log('');
    console.log('📖 Available Endpoints:');
    console.log('   POST /api/query - Execute SQL queries');
    console.log('   GET  /api/stats - Get database statistics');
    console.log('   GET  /api/recent-searches - Recent search runs');
    console.log('   GET  /api/jobs/:runId - Jobs by run ID');
    console.log('   GET  /api/job/:jobId - Single job details');
    console.log('   GET  /api/good-fit-jobs - All good fit jobs');
    console.log('   GET  /api/application-history - Application history');
    console.log('   GET  /api/profile - Active user profile');
    console.log('   GET  /api/health - Health check');
    console.log('');
    console.log(`🌐 Open UI at: http://localhost:${PORT}/index.html`);
    console.log('');
});

// Graceful shutdown
process.on('SIGINT', async () => {
    console.log('\n🛑 Shutting down server...');
    
    if (dbType === 'postgres' && db) {
        try {
            await db.end();
            console.log('✅ PostgreSQL connection closed');
        } catch (err) {
            console.error('❌ Error closing PostgreSQL:', err.message);
        }
    } else if (dbType === 'sqlite' && db) {
        db.close((err) => {
            if (err) {
                console.error('❌ Error closing SQLite:', err.message);
            } else {
                console.log('✅ SQLite connection closed');
            }
        });
    }
    
    process.exit(0);
});
