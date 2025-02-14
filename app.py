from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime

app = Flask(__name__, template_folder="templates")
app.secret_key = 'your_secret_key'  # Required for flashing messages

# Initialize Database
def init_db():
    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        # Create Trucks Table (Stores EMI per truck)
        cursor.execute('''CREATE TABLE IF NOT EXISTS trucks (
                            truck_number TEXT PRIMARY KEY,
                            emi_per_month REAL
                        )''')

        # Create Trips Table with new fields
        cursor.execute('''CREATE TABLE IF NOT EXISTS trips (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            truck_number TEXT NOT NULL,
                            trip_start DATE,
                            trip_end DATE,
                            trip_start_location TEXT,
                            trip_end_location TEXT,
                            fuel_consumed REAL,
                            fuel_cost REAL,
                            def_consumed REAL,
                            def_cost REAL,
                            toll REAL,
                            other_expenses REAL,
                            transporter TEXT,
                            broker TEXT,
                            broker_commission REAL,
                            total_fare REAL,
                            amount_received REAL DEFAULT 0,
                            FOREIGN KEY (truck_number) REFERENCES trucks(truck_number)
                        )''')

        # Create Payment History Table
        cursor.execute('''CREATE TABLE IF NOT EXISTS payments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            trip_id INTEGER NOT NULL,
                            payment_amount REAL NOT NULL,
                            payment_date TEXT NOT NULL,
                            FOREIGN KEY (trip_id) REFERENCES trips(id)
                        )''')

        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

# Run Database Initialization
init_db()

# Home Page - Show Trips & Payment History
@app.route("/")
def home():
    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        # Fetch all trips
        cursor.execute("SELECT * FROM trips")
        trips = cursor.fetchall()

        # Fetch all trucks (ensuring even trucks without trips appear)
        cursor.execute("SELECT truck_number, emi_per_month FROM trucks")
        all_trucks = cursor.fetchall()

        # Fetch truck-wise summaries (Only trucks with trips)
        cursor.execute("SELECT truck_number, SUM(fuel_cost), SUM(other_expenses), SUM(total_fare), SUM(amount_received) FROM trips GROUP BY truck_number")
        truck_summary = {row[0]: row[1:] for row in cursor.fetchall()}  # Store in dictionary

        # Prepare profit/loss data (include trucks even if they have no trips)
        profit_data = []
        for truck in all_trucks:
            truck_number, emi_per_month = truck
            total_fuel_cost, total_other_expenses, total_fare, total_received = truck_summary.get(truck_number, (0, 0, 0, 0))

            total_expenses = total_fuel_cost + total_other_expenses + emi_per_month
            profit = total_received - total_expenses  # Profit based on total received, not just fare

            profit_data.append((truck_number, total_fare, total_expenses, emi_per_month, profit))

        # Fetch payment history with trip details
        cursor.execute("""
            SELECT p.trip_id, t.truck_number, t.trip_start, t.trip_end, p.payment_amount, p.payment_date 
            FROM payments p 
            JOIN trips t ON p.trip_id = t.id 
            ORDER BY p.payment_date DESC
        """)
        payments = cursor.fetchall()

    except sqlite3.Error as e:
        flash(f"An error occurred while fetching data: {e}", "error")
        trips, profit_data, payments = [], [], []
    finally:
        conn.close()

    return render_template("index.html", trips=trips, profit_data=profit_data, payments=payments)

# Add a new trip
@app.route("/add", methods=["POST"])
def add_trip():
    try:
        truck_number = request.form["truck_number"]
        trip_start = request.form["trip_start"]
        trip_end = request.form["trip_end"]
        trip_start_location = request.form["trip_start_location"]
        trip_end_location = request.form["trip_end_location"]
        fuel_consumed = float(request.form["fuel_consumed"])
        fuel_cost = float(request.form["fuel_cost"])
        def_consumed = float(request.form["def_consumed"])
        def_cost = float(request.form["def_cost"])
        toll = float(request.form["toll"])
        other_expenses = float(request.form["other_expenses"])
        transporter = request.form["transporter"]
        broker = request.form["broker"]
        broker_commission = float(request.form.get("broker_commission", 0))  # Optional field
        total_fare = float(request.form["total_fare"])
        amount_received = float(request.form["amount_received"])

        # Validate input
        if amount_received > total_fare:
            flash("Amount received cannot be greater than total fare.", "error")
            return redirect(url_for("home"))

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trips (
                truck_number, trip_start, trip_end, trip_start_location, trip_end_location,
                fuel_consumed, fuel_cost, def_consumed, def_cost, toll, other_expenses,
                transporter, broker, broker_commission, total_fare, amount_received
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            truck_number, trip_start, trip_end, trip_start_location, trip_end_location,
            fuel_consumed, fuel_cost, def_consumed, def_cost, toll, other_expenses,
            transporter, broker, broker_commission, total_fare, amount_received
        ))
        conn.commit()
        flash("Trip added successfully!", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"An error occurred: {e}", "error")
    except ValueError as e:
        flash(f"Invalid input: {e}", "error")
    finally:
        conn.close()
    
    return redirect(url_for("home"))

# Set EMI per Truck
@app.route("/set_emi", methods=["POST"])
def set_emi():
    try:
        truck_number = request.form["truck_number"]
        emi_per_month = float(request.form["emi_per_month"])

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO trucks (truck_number, emi_per_month) VALUES (?, ?) ON CONFLICT(truck_number) DO UPDATE SET emi_per_month=?", 
                       (truck_number, emi_per_month, emi_per_month))
        conn.commit()
        flash("EMI set successfully!", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"An error occurred: {e}", "error")
    except ValueError as e:
        flash(f"Invalid input: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("home"))

# Route to settle due for a trip
@app.route("/settle_due/<int:id>", methods=["POST"])
def settle_due(id):
    try:
        payment_amount = float(request.form["payment_amount"])

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        # Update amount received
        cursor.execute("UPDATE trips SET amount_received = amount_received + ? WHERE id=?", (payment_amount, id))
        
        # Record payment history
        payment_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO payments (trip_id, payment_amount, payment_date) VALUES (?, ?, ?)", 
                       (id, payment_amount, payment_date))

        conn.commit()
        flash("Payment settled successfully!", "success")
    except sqlite3.Error as e:
        conn.rollback()
        flash(f"An error occurred: {e}", "error")
    except ValueError as e:
        flash(f"Invalid input: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)