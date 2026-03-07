# Inventory-Management

Streamlit inventory management app with persistent stock tracking and strict withdrawal controls.

## Features

- Register products with `name`, `brand`, `quantity`, and `notes`
- Increase stock for existing products
- Withdraw stock with validation (cannot withdraw more than available)
- Keep a persistent database (`inventory.db`) updated in real time
- View current inventory and movement history

## Setup

1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

## Files

- `app.py`: Streamlit application
- `requirements.txt`: Python dependencies
- `inventory.db`: SQLite database file (auto-created on first run)
