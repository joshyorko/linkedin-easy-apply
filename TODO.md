# TODO

## ✅ COMPLETED

### Profile Management UI (Dec 2025)
~~Add a UI feature in the Profile section that allows users to load a different User Profile from the database or edit the current profile directly. Present the user with a form displaying the current profile details and editable sections, enabling real-time updates. This lets users quickly adjust their profile if they notice the LLM is not generating accurate responses based on their resume parsing or if they need to update skills and other information.~~

**Implemented:**
- Profile selector dropdown to switch between saved profiles
- Full profile edit form with all fields organized into sections:
  - Basic Information (name, title, experience)
  - Contact Information (email, phone, LinkedIn, GitHub, etc.)
  - Address (street, city, state, zip)
  - Work Authorization & Employment (visa status, clearance, start date)
  - Salary & Preferences (salary range, remote preference, relocation)
  - Skills (comma-separated, editable)
  - Summary
- Real-time profile switching with "Activate" button
- Save changes to database
- Profile statistics display (applications count, success rate)
- New API endpoints:
  - `GET /api/profiles` - List all profiles
  - `GET /api/profile/:id` - Get single profile
  - `POST /api/profile/:id/activate` - Set active profile
  - `PUT /api/profile/:id` - Update profile fields

## Pending

(Add future tasks here)