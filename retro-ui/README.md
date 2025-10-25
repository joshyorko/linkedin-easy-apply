# LinkedIn Easy Apply - Retro Terminal UI

<div align="center">

```
╔══════════════════════════════════════════════════════════════════════╗
║  ██╗     ██╗███╗   ██╗██╗  ██╗███████╗██████╗ ██╗███╗   ██╗        ║
║  ██║     ██║████╗  ██║██║ ██╔╝██╔════╝██╔══██╗██║████╗  ██║        ║
║  ██║     ██║██╔██╗ ██║█████╔╝ █████╗  ██║  ██║██║██╔██╗ ██║        ║
║  ██║     ██║██║╚██╗██║██╔═██╗ ██╔══╝  ██║  ██║██║██║╚██╗██║        ║
║  ███████╗██║██║ ╚████║██║  ██╗███████╗██████╔╝██║██║ ╚████║        ║
║  ╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═╝╚═╝  ╚═══╝        ║
║                                                                      ║
║           EASY APPLY ACTION SERVER - RETRO TERMINAL v2.0            ║
╚══════════════════════════════════════════════════════════════════════╝
```

**A retro 80s terminal-style interface for the LinkedIn Easy Apply Action Server**

</div>

## 🎮 Features

- **🎨 Authentic CRT Terminal Aesthetic** - Green phosphor display, scan lines, and CRT glow
- **⚡ Real-time Dashboard** - Live stats from SQLite database
- **🔍 Job Search & Scraping** - Direct integration with action server
- **🤖 AI Enrichment** - OpenAI-powered job analysis and fit scoring
- **✉️ Auto-Apply** - Automated application workflow
- **📊 Application Tracking** - View history and success metrics
- **⌨️ Keyboard Shortcuts** - Navigate like it's 1985

## 🚀 Quick Start

### Prerequisites

- Node.js 16+ installed
- LinkedIn Easy Apply Action Server running on port 8080
- SQLite database at `../src/linkedin_jobs.sqlite`

### Installation

```bash
cd retro-ui
npm install
```

### Run the UI

```bash
npm start
```

The UI will be available at: **http://localhost:3001/index.html**

### Development Mode

```bash
npm run dev
```

## 🎯 Usage

### Keyboard Shortcuts

- **F1** - Show help documentation
- **F2** - Open job search form
- **F3** - Start AI enrichment
- **F4** - Open application menu
- **ESC** - Close modal/panel

### Workflow

1. **SEARCH** - Use the search form to scrape LinkedIn jobs
   - Enter search query (e.g., "Python Developer")
   - Set maximum jobs to fetch
   - Choose location type (Remote/Hybrid/On-site)
   - Enable "Easy Apply Only" filter

2. **ENRICH** - Run AI analysis on scraped jobs
   - Automatically identifies good fit jobs
   - Generates form answers using OpenAI
   - Calculates fit scores and confidence levels

3. **REVIEW** - Browse good fit jobs
   - View detailed job information
   - Check AI fit analysis and reasoning
   - Filter by location, experience, etc.

4. **APPLY** - Auto-apply to selected jobs
   - Single job application
   - Batch apply to all good fits
   - Apply by run_id

## 📁 File Structure

```
retro-ui/
├── index.html      # Main UI structure with terminal layout
├── style.css       # Retro CRT styling with animations
├── app.js          # Frontend logic and API calls
├── server.js       # Express backend for SQLite queries
├── package.json    # Node.js dependencies
└── README.md       # This file
```

## 🔌 API Endpoints

### Database Queries

- `POST /api/query` - Execute SQL queries (SELECT only)
- `GET /api/stats` - Get database statistics
- `GET /api/recent-searches` - Recent search runs
- `GET /api/jobs/:runId` - Jobs by run ID
- `GET /api/job/:jobId` - Single job details
- `GET /api/good-fit-jobs` - All good fit jobs
- `GET /api/application-history` - Application history
- `GET /api/profile` - Active user profile
- `GET /api/health` - Health check

### Action Server Proxy

- `POST /api/action-server/*` - Proxy requests to action server

## 🎨 Design Philosophy

This UI embraces the aesthetic of 80s/90s terminal interfaces with:

- **Green phosphor CRT display** - Classic terminal color scheme
- **VT323 monospace font** - Authentic retro typography
- **Scan lines & flicker** - CRT screen effects
- **ASCII art headers** - Old-school graphics
- **Keyboard-first navigation** - Function key shortcuts
- **Terminal-style logging** - Real-time console output

## 🔧 Configuration

Edit `app.js` to customize:

```javascript
const CONFIG = {
    ACTION_SERVER_URL: 'http://localhost:8080',  // Action server
    PROXY_SERVER_URL: 'http://localhost:3001',    // This backend
    REFRESH_INTERVAL: 5000,                       // Stats refresh (ms)
};
```

## 🛠️ Troubleshooting

### Database Connection Issues

If the server can't find the SQLite database:

```javascript
// In server.js, adjust DB_PATH:
const DB_PATH = path.join(__dirname, 'path', 'to', 'linkedin_jobs.sqlite');
```

### Action Server Offline

Ensure the action server is running:

```bash
cd ..
action-server start --port 8080
```

### CORS Errors

The backend includes CORS middleware. If issues persist, check that both servers are running on localhost.

## 📊 Database Schema

The UI queries these main tables:

- `job_postings` - Job listings with AI enrichment
- `user_profiles` - User profile data for applications
- `enriched_answers` - Generated form answers (if separate table)

## 🎯 Features In Development

- [ ] Batch application with progress tracking
- [ ] Advanced filtering and sorting
- [ ] Export jobs to CSV/JSON
- [ ] Custom SQL query console
- [ ] Profile management UI
- [ ] Application analytics dashboard
- [ ] Dark/green/amber theme switcher

## 📝 Notes

- **Read-only database access** - All queries are SELECT only for safety
- **No server modifications** - UI connects to existing action server
- **Live data** - All stats are real-time from your database
- **Browser compatibility** - Best viewed in modern browsers (Chrome, Firefox, Edge)

## 🎮 Have Fun!

This UI is designed to make job hunting feel like a retro hacking adventure. Navigate your career search like it's 1985! 🚀

---

**Built with ❤️ and nostalgia for 80s computing**
