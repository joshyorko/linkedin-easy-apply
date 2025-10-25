# Quick Start Guide - Retro Terminal UI

## 🚀 Launch the UI

### Option 1: Easy Startup Script
```bash
cd retro-ui
./start.sh
```

### Option 2: Manual Startup
```bash
cd retro-ui
npm install  # First time only
node server.js
```

Then open in browser: **http://localhost:3001/index.html**

## ⚡ Prerequisites Checklist

- [x] Node.js 16+ installed
- [x] Action server running on port 8080
- [x] SQLite database exists at `../src/linkedin_jobs.sqlite`

To start action server:
```bash
cd ..
action-server start --port 8080
```

## 🎮 Quick Workflow

### 1️⃣ Search for Jobs
- Press **F2** or click "🔍 SEARCH JOBS"
- Enter: "DevOps Engineer" or "Python Developer"
- Set max jobs: 25
- Click "▶ START SEARCH"
- Wait 2-5 minutes for scraping

### 2️⃣ Enrich with AI
- Press **F3** or click "🤖 ENRICH JOBS"
- Confirm run_id or leave blank for all
- AI analyzes fit and generates answers
- Watch console for progress

### 3️⃣ Review Good Fits
- Click "⭐ VIEW GOOD FITS"
- Browse jobs with high fit scores
- Click any job for details
- Check AI reasoning

### 4️⃣ Apply to Jobs
- Press **F4** or click "✉️ APPLY TO JOBS"
- Choose single or batch mode
- Confirm application
- Track in "📊 HISTORY"

## ⌨️ Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **F1** | Help & Documentation |
| **F2** | Open Search Form |
| **F3** | Start AI Enrichment |
| **F4** | Application Menu |
| **ESC** | Close Modal/Panel |

## 🎨 UI Features

### Dashboard Stats
- **TOTAL JOBS** - All scraped jobs in database
- **GOOD FIT** - Jobs AI marked as good matches
- **APPLIED** - Successfully submitted applications
- **ACTIVE PROFILE** - Current user profile name

### Console Output
- Real-time logging of all operations
- Color-coded messages:
  - 🟢 **Green** = Success
  - 🔵 **Blue** = Info
  - 🟡 **Yellow** = Warning
  - 🔴 **Red** = Error

### Job Listings
- Click any job to view full details
- Badges show: Good Fit ✓, Applied ✓, Fit Score %
- Direct links to LinkedIn postings

## 🔧 Troubleshooting

### Server Won't Start
```bash
# Check if port 3001 is in use
lsof -i :3001

# Kill existing process
kill $(lsof -t -i:3001)

# Restart
node server.js
```

### Database Not Found
```bash
# Check database location
ls -la ../src/linkedin_jobs.sqlite

# If in different location, edit server.js:
const DB_PATH = path.join(__dirname, 'your', 'path', 'linkedin_jobs.sqlite');
```

### Action Server Offline
```bash
# Start action server
cd ..
action-server start --port 8080

# Or check if running
curl http://localhost:8080/api/actions
```

### Browser Shows Blank Page
1. Check browser console (F12) for errors
2. Verify server is running: `curl http://localhost:3001/api/health`
3. Try different browser (Chrome/Firefox recommended)
4. Hard refresh: Ctrl+Shift+R (Cmd+Shift+R on Mac)

## 📊 Sample Queries

The UI provides quick access to common queries, but you can also use custom SQL:

### View Recent Searches
```sql
SELECT run_id, COUNT(*) as jobs 
FROM job_postings 
WHERE run_id LIKE 'search_%' 
GROUP BY run_id 
ORDER BY scraped_at DESC;
```

### Top Fit Jobs
```sql
SELECT title, company, fit_score 
FROM job_postings 
WHERE good_fit = 1 
ORDER BY fit_score DESC 
LIMIT 10;
```

### Application Success Rate
```sql
SELECT 
  COUNT(*) as total_applications,
  SUM(CASE WHEN is_applied = 1 THEN 1 ELSE 0 END) as successful
FROM job_postings 
WHERE answers_json IS NOT NULL;
```

## 🎯 Tips & Tricks

1. **Run searches during off-peak hours** to avoid LinkedIn rate limits
2. **Start with 10-15 jobs** for testing before scaling to 50+
3. **Review AI fit reasoning** to improve profile accuracy
4. **Use keyboard shortcuts** for faster navigation
5. **Monitor console output** to catch issues early
6. **Export good fits to CSV** before batch applying

## 🆘 Need Help?

- Press **F1** in the UI for built-in help
- Check `README.md` for full documentation
- View action server logs in `../output/` directory
- Inspect database with: `sqlite3 ../src/linkedin_jobs.sqlite`

## 🎨 Customization

### Change Color Theme
Edit `style.css`:
```css
:root {
    --color-primary: #00ff00;  /* Green phosphor */
    --color-bg: #0a0e0a;       /* Dark background */
}
```

Try these alternatives:
- **Amber**: `#ffaa00` (classic amber monitor)
- **Blue**: `#00aaff` (IBM blue screen)
- **White**: `#ffffff` (paper white)

### Adjust Refresh Rate
Edit `app.js`:
```javascript
const CONFIG = {
    REFRESH_INTERVAL: 5000,  // Milliseconds (default: 5 seconds)
};
```

## 📝 Notes

- All operations are logged to console
- Database is read-only from UI (safe)
- Action server handles all write operations
- Browser session persists across page reloads

---

**Happy Job Hunting! 🚀**
