# Inventory-Management

Streamlit inventory management app with persistent stock tracking and strict withdrawal controls using Neon Postgres.

## Features

- Register products with `name`, `brand`, `quantity`, and `notes`
- Increase stock for existing products
- Withdraw stock with validation (cannot withdraw more than available)
- Keep a persistent Neon Postgres database updated in real time
- View current inventory and movement history

## Setup

1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure Neon credentials.

Create `.streamlit/secrets.toml` based on `.streamlit/secrets.toml.example` and fill in your project values:

```toml
NEON_DB_URL = "postgresql+psycopg2://[TU_USUARIO]:[TU_PASSWORD]@[TU_HOST_NEON]/[TU_DATABASE]?sslmode=require"
```

4. Run the app:

```bash
streamlit run app.py
```

## Files

- `app.py`: Streamlit application
- `requirements.txt`: Python dependencies
- `.streamlit/secrets.toml.example`: Neon connection template
