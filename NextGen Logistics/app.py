from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import os
import random
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# Configuration
app.config['DATA_FOLDER'] = 'data'
app.config['STATIC_FOLDER'] = 'static'
app.config['TEMPLATES_FOLDER'] = 'templates'

# Ensure directories exist
os.makedirs(app.config['DATA_FOLDER'], exist_ok=True)
os.makedirs(app.config['STATIC_FOLDER'], exist_ok=True)

# ======================
# DATA LOADING
# ======================

def load_data():
    """Load all data files"""
    try:
        # Order data
        orders_file = os.path.join(app.config['DATA_FOLDER'], "cleaned_sales_data.csv")
        df_orders = pd.read_csv(orders_file)
        df_orders.columns = df_orders.columns.str.strip()
        
        # Shipment data
        shipments_file = os.path.join(app.config['DATA_FOLDER'], "shipments.csv")
        df_shipments = pd.read_csv(shipments_file, dtype={"order_id": str})
        df_shipments["order_id"] = df_shipments["order_id"].astype(str).str.replace(".0", "", regex=False)
        
        # Convert shipments to dictionary
        shipments = {
            row["order_id"]: {
                "lat": row["lat"],
                "lng": row["lng"],
                "destination": [row["destination_lat"], row["destination_lng"]]
            } for _, row in df_shipments.iterrows()
        }
        
        return df_orders, shipments
    
    except Exception as e:
        print(f"Error loading data files: {e}")
        exit(1)

df_orders, shipments = load_data()

# ======================
# SHIPMENT TRACKER
# ======================

def save_shipments():
    """Save shipments data back to CSV"""
    df = pd.DataFrame([
        {
            "order_id": order_id, 
            "lat": data["lat"], 
            "lng": data["lng"], 
            "destination_lat": data["destination"][0], 
            "destination_lng": data["destination"][1]
        } for order_id, data in shipments.items()
    ])
    df.to_csv(os.path.join(app.config['DATA_FOLDER'], "shipments.csv"), index=False)

@app.route('/track_shipment')
def track_shipment():
    order_id = request.args.get("order_id")
    if not order_id:
        return jsonify({"error": "Order ID is required"}), 400
    
    order_id = str(order_id)
    shipment = shipments.get(order_id)
    if not shipment:
        return jsonify({"error": "Order not found"}), 404
    
    # Simulate movement
    shipment['lat'] += random.uniform(-0.01, 0.01)
    shipment['lng'] += random.uniform(-0.01, 0.01)
    save_shipments()
    
    return jsonify({
        "lat": shipment["lat"],
        "lng": shipment["lng"],
        "destination": shipment["destination"]
    })

@app.route('/add_shipment', methods=['POST'])
def add_shipment():
    data = request.json
    order_id = str(data.get("order_id"))
    lat = data.get("lat")
    lng = data.get("lng")
    destination_lat = data.get("destination_lat")
    destination_lng = data.get("destination_lng")
    
    if not all([order_id, lat, lng, destination_lat, destination_lng]):
        return jsonify({"error": "All fields are required"}), 400
    
    if order_id in shipments:
        return jsonify({"error": "Order ID already exists"}), 409
    
    shipments[order_id] = {
        "lat": lat,
        "lng": lng,
        "destination": [destination_lat, destination_lng]
    }
    save_shipments()
    
    return jsonify({"message": "Shipment added successfully"}), 201

# ======================
# ORDER DASHBOARD
# ======================

@app.route("/orders", methods=["GET"])
def get_orders():
    customer_id = request.args.get("customer_id")

    if not customer_id:
        return jsonify({"error": "Customer ID is required"}), 400

    customer_id = customer_id.strip().upper()
    filtered_orders = df_orders[df_orders["Customer ID"] == customer_id]

    if filtered_orders.empty:
        return jsonify({"message": "No orders found for this Customer ID"}), 404

    orders_data = filtered_orders[[
        "Customer ID", "Product Name", "Shipping Status", "Total Price", "Order Date"
    ]].rename(columns={
        "Customer ID": "customer_id",
        "Product Name": "product",
        "Shipping Status": "status",
        "Total Price": "price",
        "Order Date": "delivery_date"
    })

    return jsonify(orders_data.to_dict(orient="records"))

@app.route("/chart/orders/<customer_id>")
def order_status_chart(customer_id):
    customer_id = customer_id.strip().upper()
    filtered_orders = df_orders[df_orders["Customer ID"] == customer_id]

    if filtered_orders.empty:
        return jsonify({"error": "No orders found"}), 404

    status_counts = filtered_orders["Shipping Status"].value_counts()

    plt.figure(figsize=(6, 6))
    status_counts.plot.pie(autopct="%1.1f%%", colors=["yellow", "blue", "green", "red"])
    plt.title("Order Status Distribution for Customer " + customer_id)
    plt.ylabel("")

    chart_path = os.path.join(app.config['STATIC_FOLDER'], f"order_status_{customer_id}.png")
    plt.savefig(chart_path, dpi=80)
    plt.close()

    return send_file(chart_path, mimetype="image/png", max_age=0)

@app.route("/chart/spending/<customer_id>")
def spending_trend_chart(customer_id):
    customer_id = customer_id.strip().upper()
    filtered_orders = df_orders[df_orders["Customer ID"] == customer_id]

    if filtered_orders.empty:
        return jsonify({"error": "No orders found"}), 404

    filtered_orders = filtered_orders.copy()
    filtered_orders.loc[:, "Order Date"] = pd.to_datetime(filtered_orders["Order Date"])
    filtered_orders = filtered_orders.sort_values(by="Order Date")

    plt.figure(figsize=(8, 4))
    sns.lineplot(x=filtered_orders["Order Date"], y=filtered_orders["Total Price"], marker="o")
    plt.xlabel("Order Date")
    plt.ylabel("Total Price")
    plt.title("Spending Trend for Customer " + customer_id)
    plt.xticks(rotation=45)

    chart_path = os.path.join(app.config['STATIC_FOLDER'], f"spending_trend_{customer_id}.png")
    plt.savefig(chart_path, dpi=80)
    plt.close()

    return send_file(chart_path, mimetype="image/png", max_age=0)

# ======================
# RATE CALCULATOR
# ======================

@app.route('/api/calculate-rate', methods=['POST'])
def calculate_rate():
    try:
        data = request.get_json()
        
        # Validate input
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        weight = float(data.get('weight', 0))
        distance = float(data.get('distance', 0))
        service_type = data.get('service_type', 'standard').lower()
        insurance = bool(data.get('insurance', False))

        # Validate values
        if weight <= 0 or distance <= 0:
            return jsonify({"error": "Weight and distance must be positive numbers"}), 400

        # Calculate costs
        base_rate = 5
        weight_cost = max(1.0, weight * 1.5)  # $1.5/kg with $1 minimum
        distance_cost = distance * (0.2 if distance < 100 else 0.3)
        
        service_multiplier = {
            'standard': 1.0,
            'express': 1.5,
            'overnight': 2.0
        }.get(service_type, 1.0)
        
        insurance_cost = 10 if insurance else 0
        
        subtotal = base_rate + weight_cost + distance_cost
        total_cost = round(subtotal * service_multiplier + insurance_cost, 2)
        
        return jsonify({
            "total_cost": total_cost,
            "breakdown": {
                "base_rate": base_rate,
                "weight_cost": weight_cost,
                "distance_cost": distance_cost,
                "service_multiplier": service_multiplier,
                "insurance_cost": insurance_cost
            }
        })

    except ValueError:
        return jsonify({"error": "Invalid number format"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =======
# CHATBOT 
# =======

@app.route('/api/chatbot', methods=['POST'])
def chatbot():
    try:
        data = request.get_json()
        message = data.get('message', '').lower()

        if not message:
            return jsonify({"error": "Message is required"}), 400

        if "track" in message:
            response = {
                "text": "You can track your shipments using our tracker:",
                "link": "/shipment-tracker",
                "link_text": "Track Shipment",
                "new_tab": True
            }
        elif "rate" in message or "price" in message:
            response = {
                "text": "Calculate shipping rates here:",
                "link": "/rate-calculator",
                "link_text": "Rate Calculator", 
                "new_tab": True
            }
        elif "order" in message or "dashboard" in message:
            response = {
                "text": "View your order dashboard:",
                "link": "/order-dashboard",
                "link_text": "Order Dashboard",
                "new_tab": True
            }
        elif "help" in message:
            response = {
                "text": "I can help with: shipment tracking, rate calculation, and order information."
            }
        elif "hello" in message or "hi" in message:
            response = {"text": "Hello! How can I assist you with your logistics needs today?"}
        else:
            response = {
                "text": "I'm your logistics assistant. Try asking about:",
                "options": [
                    {"text": "Track a shipment", "example": "Where is my order?"},
                    {"text": "Calculate rates", "example": "How much to ship to NY?"},
                    {"text": "View orders", "example": "Show my recent orders"}
                ]
            }

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/shipment-tracker')
def shipment_tracker_page():
    return render_template('Shipment_Tracker.html')

@app.route('/order-dashboard')
def order_dashboard_page():
    return render_template('Order_Dashboard.html')

@app.route('/rate-calculator')
def rate_calculator_page():
    return render_template('rate_calculator.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)