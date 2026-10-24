# Voltline — EV Charging Management

A simple Flask + MySQL dashboard for managing an EV charging network.

## Setup

1. Create and activate a virtual environment:
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies: `pip install -r backend/requirements.txt`
3. Copy `backend/.env.example` to `backend/.env` and enter your MySQL connection details.
4. Run `python backend/setup_admin.py` to configure the manager login.
5. Run `python backend/app.py` and open http://127.0.0.1:5000.

The application uses your existing database. Python does not create or alter tables.

## Tables

`users`, `charging_stations`, `technicians`, `vehicles`, `charging_slots`, `tariff_plans`, `charging_sessions`, `maintenance`, `bills`, `payments`, `slot_status_log`.

The app also reads the existing `session_details` and `charging_history` views and calls `sp_generate_bill`.
