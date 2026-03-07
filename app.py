import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st


DB_PATH = Path("inventory.db")
LOW_STOCK_DEFAULT = 5


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            brand TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0),
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(name, brand)
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL CHECK(movement_type IN ('IN', 'OUT')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            notes TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        """
    )
    conn.commit()


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def add_new_product(
    conn: sqlite3.Connection, name: str, brand: str, quantity: int, notes: str
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO products (name, brand, quantity, notes, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (name, brand, quantity, notes, now, now),
    )
    product_id = conn.execute(
        "SELECT id FROM products WHERE name = ? AND brand = ?;", (name, brand)
    ).fetchone()["id"]
    conn.execute(
        """
        INSERT INTO movements (product_id, movement_type, quantity, notes, timestamp)
        VALUES (?, 'IN', ?, ?, ?);
        """,
        (product_id, quantity, f"Existencias iniciales. {notes}".strip(), now),
    )
    conn.commit()


def increase_stock(
    conn: sqlite3.Connection, product_id: int, quantity: int, notes: str
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE products
        SET quantity = quantity + ?, updated_at = ?
        WHERE id = ?;
        """,
        (quantity, now, product_id),
    )
    conn.execute(
        """
        INSERT INTO movements (product_id, movement_type, quantity, notes, timestamp)
        VALUES (?, 'IN', ?, ?, ?);
        """,
        (product_id, quantity, notes, now),
    )
    conn.commit()


def withdraw_stock(
    conn: sqlite3.Connection, product_id: int, quantity: int, notes: str
) -> tuple[bool, str]:
    row = conn.execute(
        "SELECT quantity, name, brand FROM products WHERE id = ?;", (product_id,)
    ).fetchone()
    if row is None:
        return False, "El producto seleccionado no existe."

    current_qty = int(row["quantity"])
    if quantity > current_qty:
        return (
            False,
            f"No se pueden retirar {quantity}. Solo hay {current_qty} unidades disponibles de "
            f"{row['name']} ({row['brand']}).",
        )

    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        """
        UPDATE products
        SET quantity = quantity - ?, updated_at = ?
        WHERE id = ?;
        """,
        (quantity, now, product_id),
    )
    conn.execute(
        """
        INSERT INTO movements (product_id, movement_type, quantity, notes, timestamp)
        VALUES (?, 'OUT', ?, ?, ?);
        """,
        (product_id, quantity, notes, now),
    )
    conn.commit()
    return True, "Salida de inventario registrada correctamente."


def fetch_products(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT id, name, brand, quantity, notes, updated_at
        FROM products
        ORDER BY name ASC, brand ASC;
        """,
        conn,
    )


def fetch_movements(conn: sqlite3.Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        """
        SELECT m.id, p.name, p.brand, m.movement_type, m.quantity, m.notes, m.timestamp
        FROM movements m
        JOIN products p ON p.id = m.product_id
        ORDER BY m.id DESC;
        """,
        conn,
    )


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Manrope:wght@400;500;600;700&display=swap');

        :root {
            --bg-1: #f5f7fa;
            --bg-2: #eaf6f4;
            --surface: rgba(255, 255, 255, 0.85);
            --text: #16252f;
            --muted: #55717f;
            --accent: #0f766e;
            --accent-2: #0891b2;
            --danger: #b42318;
            --border: rgba(22, 37, 47, 0.12);
        }

        .stApp {
            background:
                radial-gradient(1200px 420px at 5% -10%, #d3efe9 0%, transparent 60%),
                radial-gradient(900px 360px at 95% -20%, #cbe9f6 0%, transparent 55%),
                linear-gradient(180deg, var(--bg-1), var(--bg-2));
            color: var(--text);
            font-family: 'Manrope', sans-serif;
        }

        .stApp, .stMarkdown, .stCaption, .stText, .stAlert, p, label, span, div {
            color: var(--text);
        }

        h1, h2, h3 {
            font-family: 'Space Grotesk', sans-serif !important;
            color: var(--text);
            letter-spacing: -0.02em;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #d9efeb, #d4edf6) !important;
            border-right: 1px solid rgba(22, 37, 47, 0.12);
        }

        [data-testid="stSidebar"] * {
            color: #10222d !important;
        }

        [data-testid="stSidebar"] .stRadio label {
            color: #10222d !important;
            font-weight: 650 !important;
        }

        [data-testid="stSidebar"] .stRadio [role="radiogroup"] label {
            background: rgba(255, 255, 255, 0.7);
            border: 1px solid rgba(16, 34, 45, 0.16);
            border-radius: 10px;
            padding: 0.35rem 0.5rem;
            margin-bottom: 0.35rem;
        }

        .stRadio label, .stSelectbox label, .stNumberInput label, .stTextInput label, .stTextArea label {
            color: var(--text) !important;
            font-weight: 600;
        }

        .stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div {
            color: var(--text) !important;
            background: rgba(255, 255, 255, 0.95) !important;
            border-color: rgba(22, 37, 47, 0.24) !important;
        }

        .stTextInput input::placeholder, .stTextArea textarea::placeholder {
            color: #6a7f8b !important;
            opacity: 1 !important;
        }

        .stDataFrame, .stDataFrame * {
            color: #13232d !important;
        }

        .hero {
            border: 1px solid var(--border);
            background: linear-gradient(130deg, rgba(255,255,255,0.95), rgba(236,251,248,0.9));
            border-radius: 18px;
            padding: 1.2rem 1.3rem;
            margin: 0.2rem 0 1rem 0;
            animation: fadeUp 0.45s ease-out;
        }

        .hero-title {
            margin: 0;
            font-size: 1.25rem;
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 700;
            color: var(--text);
        }

        .hero-sub {
            margin-top: 0.35rem;
            color: var(--muted);
            font-size: 0.97rem;
        }

        .chip {
            display: inline-block;
            border: 1px solid rgba(15, 118, 110, 0.25);
            background: rgba(15, 118, 110, 0.08);
            color: #0c5c56;
            border-radius: 999px;
            font-size: 0.78rem;
            padding: 0.2rem 0.55rem;
            margin-bottom: 0.4rem;
            font-weight: 600;
        }

        [data-testid="stMetric"] {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 0.6rem 0.8rem;
            backdrop-filter: blur(3px);
            animation: fadeUp 0.45s ease-out;
        }

        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1rem;
            backdrop-filter: blur(3px);
            animation: fadeUp 0.45s ease-out;
        }

        .section-title {
            font-size: 1.05rem;
            margin-bottom: 0.35rem;
            color: var(--text);
            font-family: 'Space Grotesk', sans-serif;
            font-weight: 650;
        }

        .section-caption {
            color: var(--muted);
            margin-bottom: 1rem;
            font-size: 0.92rem;
        }

        .stButton > button, .stFormSubmitButton > button {
            background: linear-gradient(140deg, var(--accent), var(--accent-2));
            color: #ffffff;
            border: none;
            border-radius: 10px;
            font-weight: 600;
            padding: 0.5rem 1rem;
        }

        .stButton > button:hover, .stFormSubmitButton > button:hover {
            filter: brightness(1.05);
            transform: translateY(-1px);
            transition: all 120ms ease-in-out;
        }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 880px) {
            .hero-title { font-size: 1.06rem; }
            .hero-sub { font-size: 0.9rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_product_options(products_df: pd.DataFrame, quantity_label: str) -> dict[str, int]:
    return {
        f"{row['name']} | {row['brand']} ({quantity_label}: {row['quantity']})": int(
            row["id"]
        )
        for _, row in products_df.iterrows()
    }


def render_hero() -> None:
    st.markdown(
        """
        <div class="hero">
            <div class="chip">OPERACION EN VIVO</div>
            <p class="hero-title">Centro de Control de Almacen</p>
            <p class="hero-sub">
                Gestiona entradas, salidas y estado del inventario desde una sola interfaz.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(products_df: pd.DataFrame, movements_df: pd.DataFrame, low_stock_limit: int) -> None:
    total_skus = int(len(products_df))
    total_units = int(products_df["quantity"].sum()) if not products_df.empty else 0
    low_stock_items = (
        int((products_df["quantity"] <= low_stock_limit).sum()) if not products_df.empty else 0
    )

    recent_cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_moves = 0
    if not movements_df.empty:
        moves = movements_df.copy()
        moves["timestamp"] = pd.to_datetime(moves["timestamp"], errors="coerce")
        recent_moves = int((moves["timestamp"] >= recent_cutoff).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Productos", f"{total_skus}")
    c2.metric("Unidades en Existencia", f"{total_units}")
    c3.metric("Productos con Pocas Existencias", f"{low_stock_items}")
    c4.metric("Movimientos (24h)", f"{recent_moves}")


def section_heading(title: str, caption: str) -> None:
    st.markdown(
        f"""
        <div class="card">
            <div class="section-title">{title}</div>
            <div class="section-caption">{caption}</div>
        """,
        unsafe_allow_html=True,
    )


def close_section() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="Control de Inventario", page_icon=":package:", layout="wide")
    inject_styles()

    conn = get_connection()
    init_db(conn)
    products_df = fetch_products(conn)
    movements_df = fetch_movements(conn)

    with st.sidebar:
        st.markdown("### Navegacion")
        page = st.radio(
            "Ir a",
            ["Panel", "Entrada de Inventario", "Salida de Inventario", "Historial"],
            label_visibility="collapsed",
        )
        st.markdown("---")
        low_stock_limit = st.slider("Umbral de bajo stock", 1, 50, LOW_STOCK_DEFAULT)
        st.caption("Los productos en o por debajo de esta cantidad se marcan como bajo stock.")

    render_hero()
    render_metrics(products_df, movements_df, low_stock_limit)
    st.write("")

    if page == "Panel":
        c1, c2 = st.columns([1.4, 1], gap="large")
        with c1:
            section_heading("Inventario Actual", "Cantidades en tiempo real por producto y marca.")
            if products_df.empty:
                st.info("El inventario esta vacio.")
            else:
                display_df = products_df.drop(columns=["id"]).rename(
                    columns={
                        "name": "Producto",
                        "brand": "Marca",
                        "quantity": "Cantidad",
                        "notes": "Notas",
                        "updated_at": "Ultima Actualizacion (UTC)",
                    }
                )
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            close_section()

        with c2:
            section_heading("Alerta de Pocas Existencias", "Panel de alerta rapida para control estricto.")
            if products_df.empty:
                st.info("No hay productos para analizar.")
            else:
                low_df = products_df[products_df["quantity"] <= low_stock_limit].copy()
                if low_df.empty:
                    st.success("No hay productos con bajo stock en este momento.")
                else:
                    st.warning(f"{len(low_df)} producto(s) por debajo del umbral.")
                    st.dataframe(
                        low_df[["name", "brand", "quantity"]].rename(
                            columns={"name": "Producto", "brand": "Marca", "quantity": "Cant."}
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
            close_section()

    elif page == "Entrada de Inventario":
        left, right = st.columns(2, gap="large")

        with left:
            section_heading("Registrar Nuevo Producto", "Crea un producto con existencias iniciales y notas.")
            with st.form("new_product_form", clear_on_submit=True):
                name = st.text_input("Nombre del Producto", max_chars=120, placeholder="Ejemplo: Cuchilla")
                brand = st.text_input("Marca", max_chars=120, placeholder="Ejemplo: Stanley")
                quantity = st.number_input("Cantidad Inicial", min_value=1, step=1)
                notes = st.text_area("Notas Adicionales", max_chars=500, placeholder="Detalles opcionales...")
                submitted = st.form_submit_button("Crear Producto")

                if submitted:
                    clean_name = normalize_text(name)
                    clean_brand = normalize_text(brand)
                    clean_notes = normalize_text(notes)
                    if not clean_name or not clean_brand:
                        st.error("El nombre del producto y la marca son obligatorios.")
                    else:
                        try:
                            add_new_product(conn, clean_name, clean_brand, int(quantity), clean_notes)
                            st.success("Producto creado y existencias iniciales registradas.")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("Este producto y marca ya existen.")
            close_section()

        with right:
            section_heading(
                "Aumentar Existencias",
                "Actualiza cantidad para productos ya registrados.",
            )
            if products_df.empty:
                st.info("Aun no hay productos disponibles.")
            else:
                options = build_product_options(products_df, "Actual")
                with st.form("increase_stock_form", clear_on_submit=True):
                    selected_label = st.selectbox("Seleccionar Producto", list(options.keys()))
                    qty_to_add = st.number_input("Cantidad a Agregar", min_value=1, step=1)
                    add_notes = st.text_area(
                        "Notas de Actualizacion", max_chars=500, placeholder="Motivo / lote..."
                    )
                    submit_add = st.form_submit_button("Aumentar Existencias")

                    if submit_add:
                        product_id = options[selected_label]
                        increase_stock(conn, product_id, int(qty_to_add), normalize_text(add_notes))
                        st.success("Existencias aumentadas correctamente.")
                        st.rerun()
            close_section()

    elif page == "Salida de Inventario":
        section_heading(
            "Retirar Productos",
            "Registra salidas de inventario con validacion estricta de disponibilidad.",
        )
        if products_df.empty:
            st.info("No hay productos disponibles para retirar.")
        else:
            options = build_product_options(products_df, "Disponible")
            with st.form("withdraw_stock_form", clear_on_submit=True):
                selected_label = st.selectbox("Seleccionar Producto", list(options.keys()))
                qty_to_withdraw = st.number_input(
                    "Cuantos productos se van a retirar?",
                    min_value=1,
                    step=1,
                )
                out_notes = st.text_area(
                    "Notas de Salida", max_chars=500, placeholder="Pedido #, area, motivo..."
                )
                submit_withdraw = st.form_submit_button("Retirar Existencias")

                if submit_withdraw:
                    product_id = options[selected_label]
                    ok, message = withdraw_stock(
                        conn, product_id, int(qty_to_withdraw), normalize_text(out_notes)
                    )
                    if ok:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
        close_section()

    elif page == "Historial":
        section_heading("Movimientos de Inventario", "Trazabilidad completa de entradas y salidas.")
        if movements_df.empty:
            st.info("Aun no hay movimientos registrados.")
        else:
            log_df = movements_df.rename(
                columns={
                    "name": "Producto",
                    "brand": "Marca",
                    "movement_type": "Tipo",
                    "quantity": "Cantidad",
                    "notes": "Notas",
                    "timestamp": "Fecha y Hora (UTC)",
                }
            )
            log_df["Tipo"] = log_df["Tipo"].map({"IN": "Entrada", "OUT": "Salida"}).fillna(log_df["Tipo"])
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        close_section()

    conn.close()


if __name__ == "__main__":
    main()
