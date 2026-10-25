# Voltline — EV Charging Management System

Voltline is a web-based dashboard for managing an electric vehicle (EV) charging network. It is designed for a network manager who needs to keep track of charging stations, charging slots, users, vehicles, sessions, tariffs, bills, payments, technicians, and maintenance records in one place.

The application uses **Python, Flask, MySQL, HTML, CSS, and JavaScript**. Flask handles the server-side routes and database operations, MySQL stores the project data, and the frontend provides the dashboard and forms used to manage the network.

## Project Features

### 1. Manager Login and Access

- The application includes a login page for the manager.
- Login details are checked by the Flask backend against the user information stored in MySQL.
- Passwords are handled using the project's password-verification code rather than being treated as plain text.
- The manager can sign in to access the dashboard and its management pages.
- The manager account can be configured with the setup script.

### 2. Charging Station Management

- View and manage the charging stations recorded in the database.
- See station information in a readable list.
- Use station details to understand which charging slots belong to each location.
- Keep station records organized for use in the rest of the dashboard.

### 3. Charging Slot Management

- View charging slots and the station each slot belongs to.
- Check slot information, including charger type and availability status.
- Use slot information when creating and reviewing charging sessions.
- Slot availability is connected to the session and maintenance records through the database rules configured for this project.

### 4. Charging Session Management

- View charging sessions along with related vehicle, user, slot, station, and tariff details.
- Create and update session records using the fields supported by the database schema.
- Review session information such as booking time, duration, energy consumed, and status.
- The application uses the existing `session_details` view to present joined session information in a readable form.
- A session is connected to its charging slot and vehicle; the station and user details are obtained through the related records rather than duplicated in the session table.

### 5. Tariff Plan Management

- View the available tariff plans.
- Check charger type and the rate associated with a plan.
- Use tariff details when creating and reviewing charging sessions.
- Database rules help prevent a session from using a tariff that does not match the relevant charger type.

### 6. Bills and Payments

- View bills along with the related session and user information.
- Generate a bill for a completed charging session using the database procedure `sp_generate_bill`.
- Review payment records and their related bill details.
- Record more than one payment against a bill when the database design allows it.
- The database is responsible for the bill/payment status rules configured for this project.

### 7. Maintenance and Technician Records

- Manage maintenance records for charging equipment.
- View the technician assigned to a maintenance task.
- Review maintenance status and the station or equipment involved.
- Slot availability is coordinated with maintenance through the project's database rules, helping prevent a slot under maintenance from being treated as freely available.

### 8. User and Vehicle Management

- View registered user records.
- Manage vehicle information and see each vehicle's owner.
- Use vehicle and owner details when reviewing charging sessions.
- The database links a session to a vehicle, and the vehicle record links back to the user.

### 9. Dashboard, Reports, and Network Overview

- View a summary of important charging-network information.
- Review session and energy information grouped by station.
- Review revenue information based on recorded payments.
- View maintenance records grouped by their status.
- Use joined data to make reports easier to read without having to manually combine table information.

### 10. SQL Playground

- Explore example SQL queries from inside the dashboard.
- Examples are grouped by topic so they are easier to find.
- Topics include basic relational operations, joins, subqueries, aggregate functions, filtering, sorting, views, and query-plan inspection.
- The playground is intended to help demonstrate and understand SQL queries as part of the database project.
- Queries that can change data or database structure require an additional confirmation in the interface.

## Technology Stack

| Part | Technology |
| --- | --- |
| Backend | Python, Flask |
| Database | MySQL |
| Database access | `mysql-connector-python` with parameterized SQL queries |
| Frontend | HTML, CSS, JavaScript |
| Configuration | Environment variables loaded from a local `.env` file |

## Database Design

The project uses an existing MySQL schema that is configured separately in MySQL Workbench. The Flask application reads and updates data through SQL queries; the Python setup process is not intended to create or alter the schema.

### Tables

The database contains the following tables:

- `users` — user and manager account information.
- `charging_stations` — charging station records.
- `technicians` — technician details.
- `vehicles` — vehicles and their owners.
- `charging_slots` — charging slots belonging to stations.
- `tariff_plans` — charging tariff information.
- `charging_sessions` — bookings and charging-session details.
- `maintenance` — maintenance tasks and their status.
- `bills` — bills associated with charging sessions.
- `payments` — payment records for bills.
- `slot_status_log` — recorded slot-status changes.

### Existing Database Objects

The application also uses the following database objects, which must already exist in the database:

- `session_details` — a view used to show charging-session information together with related records.
- `charging_history` — an existing view used for charging history.
- `sp_generate_bill` — a stored procedure used to generate a bill for a completed session.

Some status checks and consistency rules are enforced by triggers in the database. Since these objects are part of the existing schema, check that they have been applied in MySQL Workbench before running the application.

## Project Structure

```text
.
├── README.md
├── .gitignore
├── backend/
│   ├── app.py
│   ├── setup_admin.py
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── templates/
    └── static/
        ├── app.js
        └── style.css
```

## Setup and Run Locally

### Requirements

- Python installed on your computer.
- MySQL Server running locally or reachable from your computer.
- The project's database tables, views, stored procedure, and triggers already configured in MySQL Workbench.

### 1. Open the project

Open the project folder in VS Code. Run the commands below from the project root, where `README.md`, `backend`, and `frontend` are located.

### 2. Create a virtual environment

On Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install Python packages

```powershell
python -m pip install -r backend/requirements.txt
```

### 4. Configure database settings

Copy `backend/.env.example` to a new file named `backend/.env`. Update the values to match your local MySQL setup.

Typical settings look like this:

```dotenv
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_mysql_username
DB_PASSWORD=your_mysql_password
DB_NAME=your_database_name
FLASK_SECRET_KEY=replace_with_a_random_secret
FLASK_DEBUG=false
PORT=5000
```

Use your own values; the example above is not a set of working credentials. Do not commit `backend/.env` to GitHub or share your database password publicly.

### 5. Configure the manager account

Run the setup script:

```powershell
python backend/setup_admin.py
```

Follow the prompts shown by the script. This step uses the configured database connection, so confirm that the credentials are correct first.

### 6. Start the application

```powershell
python backend/app.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

To stop the local server, return to the terminal and press `Ctrl+C`.

## Important Notes

- **Database setup is separate:** Create and maintain the schema in MySQL Workbench. The application does not ship with a schema SQL file and does not create or alter tables automatically.
- **Use the correct database:** The table and object names in this README must match the database you configured locally.
- **Keep credentials private:** Store local database credentials in `backend/.env`. Only the example configuration belongs in version control.
- **Demo credentials are not published here:** Configure the manager account using `backend/setup_admin.py`; there are no fixed demo usernames or passwords documented in this README.
- **Local testing matters:** The application needs to be tested with the same MySQL tables, views, procedure, and triggers used by your project.

## Purpose of the Project

Voltline demonstrates how a relational database can support the day-to-day management of an EV charging network. It brings related records into one dashboard and uses SQL joins, reports, views, and stored database rules to make station operations, charging sessions, billing, payments, and maintenance easier to review.
