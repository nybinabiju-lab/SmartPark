# SmartPark — Smart Parking Management Website

A Flask + SQLite academic prototype with a responsive HTML/CSS/JavaScript frontend. The graph algorithms run on the server; ordinary users never need to select an algorithm.

## Features included
- Account registration and login using **email or phone number + password**.
- Responsive landing page, user dashboard, and parking-slot grid.
- Slot labels and status display: available, occupied, reserved during the current time.
- Automatic slot assignment filtered by reservation time, vehicle size, accessibility needs, EV charging requirement, and reachability; users can optionally choose a space themselves.
- Dijkstra's algorithm runs in the backend to calculate the shortest route from the entrance to the assigned slot.
- Reservation conflict checks for overlapping time ranges.
- Reservation list and cancellation.
- In-app booking alerts and reminders for reservations ending within 30 minutes when the user opens the dashboard/alerts.
- Admin dashboard to mark a slot occupied/available and block/reopen a road.
- Recalculates routes over the remaining unblocked graph edges.
- SQLite persistence and hashed passwords.

## Technology stack
- Frontend: HTML, CSS, JavaScript, Jinja templates
- Backend: Python + Flask
- Database: SQLite
- Algorithms: Dijkstra shortest path; rule-based filtering and minimum-distance selection for automatic slot assignment

## Run on macOS / Windows
1. Install Python 3.10+.
2. Open Terminal (macOS) or Command Prompt/PowerShell (Windows), and move into this folder.
3. Create a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows use `py -m venv .venv` then `.venv\\Scripts\\activate`.
4. Install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```
5. Start the website:

   ```bash
   python app.py
   ```
6. Open `http://127.0.0.1:5000` in your browser.

The database and demo parking layout are created automatically on first run.

## Demo administrator
- Email: `admin@smartpark.local`
- Password: `Admin123!`

Log in, then open **Admin** to block/reopen roads or change slot status. Change these credentials before showing the project outside your local demo.

## Important prototype limitations
- Phone login is by phone number and password; **SMS OTP is not implemented**. OTP needs an SMS provider and credentials.
- Alerts are in-app only; no actual SMS/email is sent.
- The map is a simplified fixed graph with illustrative route-distance units, not a surveyed real parking-lot map.
- Automatic assignment is a single-request filter-and-rank method (shortest reachable eligible slot), not a global multi-user Hungarian/bipartite matching optimizer.
- `debug=True` and the default Flask secret are for local development only. Before deployment, set a strong `SMARTPARK_SECRET`, disable debug mode, add CSRF protection/rate limits, use HTTPS, and configure a production database/server.
- The demo admin password is intentionally visible in this academic prototype; replace it before any public deployment.
