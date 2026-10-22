# Voltline — EV Charging Network Management

A beginner-friendly Flask + MySQL management dashboard based on the supplied `ev_charging_management` schema. It is intended for a private manager, not public customer booking.

## What is included

- Manager login and logout using a password hash stored in the existing `users.password_hash` column.
- Database-driven overview, station/slot/session/tariff/technician/maintenance/bill/payment/user/vehicle screens.
- Create, read, update, and delete operations where supported by existing foreign keys.
- Reports for successful payment totals, station session/energy summaries, and maintenance statuses.
- SQL Playground with 13 schema-matched examples and single-statement execution.
- `.env.example`, setup script, and Windows commands.

## Important schema notes

- Database name: `ev_charging_management`.
- The project does not create, drop, or reset tables. Run your existing schema only if you have not already created these tables.
- `users` already contains the `role` and `password_hash` columns, so manager authentication reuses them.
- The supplied sample admin password value (`DEMO_HASH_3`) is a placeholder, not a usable password. Run `python setup_admin.py` to set a real hashed password for an existing `ADMIN` email (or create an admin if that email is not present).
- Your schema has no dedicated slot-to-maintenance relationship or session end timestamp trigger. The application uses the relationships that exist and avoids creating schema changes.
- SQL Playground executes against the real database. Use it carefully. It limits each submission to one statement and asks for confirmation before common data-changing statements. This is an educational feature, not a hardened production SQL console.

## Requirements

- Windows 10/11
- Python 3.10 or newer
- MySQL Server running locally (MySQL Workbench is a client; it does not itself run the database server)
- Existing database and tables from your SQL schema
- VS Code recommended

## Run on Windows / PowerShell

1. Extract the ZIP to a folder such as `C:\Projects\evcharging_app`.
2. Open that folder in VS Code, then open Terminal → New Terminal (PowerShell).
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use this for the current terminal only:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\.venv\Scripts\Activate.ps1
   ```

4. Install dependencies:

   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. Copy the sample environment file and edit it:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

   Enter your actual MySQL host, port, username, password, and database name. Keep `.env` private; it is excluded from the delivered ZIP.

6. Confirm your existing database contains the expected tables. In Workbench, run:

   ```sql
   USE ev_charging_management;
   SHOW TABLES;
   ```

   Expected tables: `users`, `charging_stations`, `technicians`, `vehicles`, `charging_slots`, `tariff_plans`, `charging_sessions`, `maintenance`, `bills`, `payments`. Your other SQL file also creates a `charging_history` view and `idx_session_status` index; these are not required for the application to start.

7. Set up manager access (the database must be running and `.env` correct):

   ```powershell
   python setup_admin.py
   ```

   Use an existing email whose role is `ADMIN` to replace its placeholder password, or enter a new email to create an admin account. Password input is hidden in the terminal.

8. Start the app:

   ```powershell
   python app.py
   ```

9. Open `http://127.0.0.1:5000` in your browser. Sign in with the manager email/password set in step 7.

10. Optional connection test: visit `http://127.0.0.1:5000/health` after the app is running. A successful response reports the connected database name and MySQL version. A failure response means the connection has not succeeded; inspect `.env`, MySQL service status, database name, and privileges.

## Folder structure

```text
 evcharging_app/
 ├── app.py                 # Flask routes, database queries, validation
 ├── setup_admin.py         # Securely set up manager password
 ├── requirements.txt
 ├── .env.example           # Copy to .env and add local credentials
 ├── README.md
 ├── templates/             # Jinja HTML templates
 └── static/
     ├── style.css          # Dashboard design system
     └── app.js             # SQL example loader and small interactions
```

## Architecture in simple language

1. The browser displays HTML templates styled by `static/style.css`.
2. When you submit a form, Flask receives the values and validates them.
3. Flask connects to MySQL using `mysql-connector-python` and parameterized SQL for normal operations.
4. Successful changes are committed. Failed database operations are rolled back and shown as readable errors where possible.
5. The page reloads its data from MySQL, so normal management screens do not use hardcoded records.

## Testing checklist

Because this package was created without access to your running MySQL Server or your private `.env` credentials, live database tests have **not** been claimed as passed. After configuration, test:

- `/health` returns `ok: true`.
- Login rejects wrong passwords and accepts the manager password you configured.
- Add a station, refresh the page, and verify it persists in Workbench.
- Add a slot to that station and check its status.
- Add/edit a tariff and maintenance record.
- Create a session using a matching station/slot/user/vehicle/tariff. Test invalid cross-station slot and mismatched vehicle/user cases.
- Verify deletion is rejected by MySQL when a record has dependent rows.
- Open Reports and compare its totals with SQL queries in Workbench.
- Run each prebuilt SQL Playground example. Examples are based on table/column names in your supplied schema, but must be executed against your local database to confirm compatibility with its exact MySQL version and current data.
- Test a query with a deliberate syntax error, and test a data-changing query only on records you are comfortable modifying.

## SQL Playground safety

The playground is intended for college demonstrations and can run data-changing SQL on the real database. Confirmation is added for common destructive/update statements and multiple statements are blocked. This is not a security boundary against a malicious authenticated manager. Avoid production credentials and make a database backup before demonstrations. MySQL DDL statements can implicitly commit and cannot always be rolled back.

## Viva quick guide

- **Flask:** Python web framework; routes connect browser requests to Python functions.
- **MySQL Connector:** Opens a connection to MySQL and runs SQL statements.
- **CRUD:** Create (`INSERT`), Read (`SELECT`), Update (`UPDATE`), Delete (`DELETE`).
- **Primary key:** Uniquely identifies a row, e.g. `station_id`.
- **Foreign key:** Keeps relationships valid, e.g. `charging_slots.station_id` references `charging_stations.station_id`.
- **JOIN:** Combines related records, such as a session with its station and vehicle.
- **LEFT JOIN:** Keeps all rows from the left table even when no related session exists.
- **Aggregate functions:** `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` calculate summaries.
- **GROUP BY:** Creates one result group per status, station, or payment mode.
- **HAVING:** Filters grouped aggregate results; `WHERE` filters rows before grouping.
- **Subquery:** A query nested inside another query.
- **Parameterized SQL:** Passes user values separately from SQL text, reducing SQL injection risk for normal application forms.
- **Transactions:** `commit()` saves a successful transaction; `rollback()` cancels pending changes after an error.
- **Password hashing:** Stores a one-way hash rather than a plain-text password.
- **Schema constraint:** A foreign key or check constraint can reject invalid or orphaning operations.

## Limitations to understand

- No real payment gateway is integrated.
- No chart library is used; tables and status summaries keep the implementation simple.
- The manager role is checked for login, but generic user management is available to the manager and does not provide separate permissions per page.
- A production deployment would need stronger SQL Playground isolation, CSRF protection, rate limiting, audit logging, and more comprehensive concurrency-safe slot reservation logic.
