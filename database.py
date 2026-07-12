import json
import os
from datetime import datetime, timedelta
from config import INITIAL_DEBT, INTEREST_RATE, INTEREST_START_DATE

DATA_FILE = "sergobank_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "current_debt": INITIAL_DEBT,
        "initial_debt": INITIAL_DEBT,
        "last_interest_date": None,
        "payment_history": [],
        "interest_history": [],
        "messages_sent": 0,
        "start_date": datetime.now().isoformat()
    }

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def calculate_interest():
    data = load_data()
    today = datetime.now().date()
    interest_start = datetime.strptime(INTEREST_START_DATE, "%Y-%m-%d").date()
    
    if today >= interest_start:
        last_date = data.get("last_interest_date")
        if last_date:
            last_date = datetime.strptime(last_date, "%Y-%m-%d").date()
            days_passed = (today - last_date).days
        else:
            days_passed = (today - interest_start).days
        
        if days_passed > 0:
            monthly_interest = data["current_debt"] * INTEREST_RATE
            daily_interest = monthly_interest / 30
            total_interest = daily_interest * days_passed
            
            if total_interest > 0:
                data["current_debt"] += total_interest
                data["interest_history"].append({
                    "date": today.isoformat(),
                    "amount": round(total_interest, 2),
                    "total_debt": round(data["current_debt"], 2)
                })
                data["last_interest_date"] = today.isoformat()
                save_data(data)
    
    return data

def add_payment(amount):
    data = load_data()
    data["current_debt"] -= amount
    data["payment_history"].append({
        "date": datetime.now().isoformat(),
        "amount": amount,
        "remaining": round(data["current_debt"], 2)
    })
    save_data(data)
    return data

def get_debt_info():
    data = calculate_interest()
    return {
        "current_debt": round(data["current_debt"], 2),
        "initial_debt": data["initial_debt"],
        "total_interest": round(data["current_debt"] - data["initial_debt"], 2),
        "payment_count": len(data["payment_history"]),
        "messages_sent": data["messages_sent"]
    }

def increment_messages():
    data = load_data()
    data["messages_sent"] += 1
    save_data(data)
