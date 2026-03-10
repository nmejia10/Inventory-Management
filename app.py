import os
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError
from streamlit.errors import StreamlitSecretNotFoundError
import tomllib


LOW_STOCK_DEFAULT = 10
NEON_DB_URL_PLACEHOLDER = (
    "postgresql+psycopg2://[TU_USUARIO]:[TU_PASSWORD]"
    "@[TU_HOST_NEON]/[TU_DATABASE]?sslmode=require"
)
LOCAL_SECRETS_EXAMPLE = Path(".streamlit/secrets.toml.example")


def get_database_url() -> str:
    try:
        secret_url = st.secrets.get("NEON_DB_URL", "").strip()
        if secret_url:
            return normalize_database_url(secret_url)
    except StreamlitSecretNotFoundError:
        pass

    try:
        legacy_secret_url = st.secrets.get("SUPABASE_DB_URL", "").strip()
        if legacy_secret_url:
            return normalize_database_url(legacy_secret_url)
    except StreamlitSecretNotFoundError:
        pass

    env_url = os.getenv("NEON_DB_URL", "").strip()
    if env_url:
        return normalize_database_url(env_url)

    legacy_env_url = os.getenv("SUPABASE_DB_URL", "").strip()
    if legacy_env_url:
        return normalize_database_url(legacy_env_url)

    if LOCAL_SECRETS_EXAMPLE.exists():
        local_secret_url = load_local_example_secret()
        if local_secret_url:
            return normalize_database_url(local_secret_url)

    return normalize_database_url(NEON_DB_URL_PLACEHOLDER)


def normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return database_url


def load_local_example_secret() -> str:
    try:
        parsed = tomllib.loads(LOCAL_SECRETS_EXAMPLE.read_text())
    except Exception:
        return ""
    return str(parsed.get("NEON_DB_URL") or parsed.get("SUPABASE_DB_URL") or "").strip()


@st.cache_resource(show_spinner=False)
def get_engine() -> Engine:
    database_url = get_database_url()
    if "[TU_PASSWORD]" in database_url or "[TU_HOST_NEON]" in database_url:
        raise RuntimeError("Neon no esta configurado todavia.")

    return create_engine(database_url, pool_pre_ping=True)


def show_database_setup_error() -> None:
    st.error("Falta configurar la conexion a Neon.")
    st.code(
        """
NEON_DB_URL = "postgresql+psycopg2://[TU_USUARIO]:[TU_PASSWORD]@[TU_HOST_NEON]/[TU_DATABASE]?sslmode=require"
        """.strip(),
        language="toml",
    )
    st.caption(
        "Agrega ese valor en `.streamlit/secrets.toml` o como variable de entorno `NEON_DB_URL`."
    )


def init_db(conn: Connection) -> None:
    conn.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS products (
            id BIGSERIAL PRIMARY KEY,
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
    )
    conn.execute(
        text(
            """
        CREATE TABLE IF NOT EXISTS movements (
            id BIGSERIAL PRIMARY KEY,
            product_id BIGINT NOT NULL,
            movement_type TEXT NOT NULL CHECK(movement_type IN ('IN', 'OUT')),
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            notes TEXT,
            timestamp TEXT NOT NULL,
            FOREIGN KEY(product_id) REFERENCES products(id)
        );
        """
        )
    )


def normalize_text(value: str) -> str:
    return " ".join(value.strip().split())


def add_new_product(conn: Connection, name: str, brand: str, quantity: int, notes: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        text(
            """
        INSERT INTO products (name, brand, quantity, notes, created_at, updated_at)
        VALUES (:name, :brand, :quantity, :notes, :created_at, :updated_at);
        """
        ),
        {
            "name": name,
            "brand": brand,
            "quantity": quantity,
            "notes": notes,
            "created_at": now,
            "updated_at": now,
        },
    )
    product_id = conn.execute(
        text("SELECT id FROM products WHERE name = :name AND brand = :brand;"),
        {"name": name, "brand": brand},
    ).scalar_one()
    conn.execute(
        text(
            """
        INSERT INTO movements (product_id, movement_type, quantity, notes, timestamp)
        VALUES (:product_id, 'IN', :quantity, :notes, :timestamp);
        """
        ),
        {
            "product_id": product_id,
            "quantity": quantity,
            "notes": f"Existencias iniciales. {notes}".strip(),
            "timestamp": now,
        },
    )


def increase_stock(conn: Connection, product_id: int, quantity: int, notes: str) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    conn.execute(
        text(
            """
        UPDATE products
        SET quantity = quantity + :quantity, updated_at = :updated_at
        WHERE id = :product_id;
        """
        ),
        {"quantity": quantity, "updated_at": now, "product_id": product_id},
    )
    conn.execute(
        text(
            """
        INSERT INTO movements (product_id, movement_type, quantity, notes, timestamp)
        VALUES (:product_id, 'IN', :quantity, :notes, :timestamp);
        """
        ),
        {
            "product_id": product_id,
            "quantity": quantity,
            "notes": notes,
            "timestamp": now,
        },
    )


def withdraw_stock(
    conn: Connection, product_id: int, quantity: int, notes: str
) -> tuple[bool, str]:
    row = conn.execute(
        text("SELECT quantity, name, brand FROM products WHERE id = :product_id;"),
        {"product_id": product_id},
    ).mappings().fetchone()
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
        text(
            """
        UPDATE products
        SET quantity = quantity - :quantity, updated_at = :updated_at
        WHERE id = :product_id;
        """
        ),
        {"quantity": quantity, "updated_at": now, "product_id": product_id},
    )
    conn.execute(
        text(
            """
        INSERT INTO movements (product_id, movement_type, quantity, notes, timestamp)
        VALUES (:product_id, 'OUT', :quantity, :notes, :timestamp);
        """
        ),
        {
            "product_id": product_id,
            "quantity": quantity,
            "notes": notes,
            "timestamp": now,
        },
    )
    return True, "Salida de inventario registrada correctamente."


def fetch_products(conn: Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        text(
            """
        SELECT id, name, brand, quantity, notes, updated_at
        FROM products
        ORDER BY name ASC, brand ASC;
        """
        ),
        conn,
    )


def fetch_movements(conn: Connection) -> pd.DataFrame:
    return pd.read_sql_query(
        text(
            """
        SELECT m.id, p.name, p.brand, m.movement_type, m.quantity, m.notes, m.timestamp
        FROM movements m
        JOIN products p ON p.id = m.product_id
        ORDER BY m.id DESC;
        """
        ),
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

    try:
        engine = get_engine()
    except RuntimeError:
        show_database_setup_error()
        return
    except Exception as exc:
        st.error("No se pudo inicializar la conexion con Neon.")
        st.caption(str(exc))
        return

    try:
        with engine.begin() as conn:
            init_db(conn)

        with engine.connect() as conn:
            products_df = fetch_products(conn)
            movements_df = fetch_movements(conn)
    except Exception as exc:
        st.error("No se pudo conectar con la base de datos de Neon.")
        st.caption(str(exc))
        return

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

    #render_hero()
    #render_metrics(products_df, movements_df, low_stock_limit)
    #st.write("")

    if page == "Panel":
        render_hero()
        render_metrics(products_df, movements_df, low_stock_limit)
        st.write("")
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
                name = st.text_input("Nombre del Producto", max_chars=120, placeholder="Ejemplo: Cemento")
                brand = st.text_input("Marca", max_chars=120, placeholder="Ejemplo: Cemex")
                quantity = st.number_input("Cantidad Inicial", min_value=1, step=1)
                notes = st.text_area("Notas Adicionales", max_chars=500, placeholder="Detalles opcionales.")
                submitted = st.form_submit_button("Crear Producto")

                if submitted:
                    clean_name = normalize_text(name)
                    clean_brand = normalize_text(brand)
                    clean_notes = normalize_text(notes)
                    if not clean_name or not clean_brand:
                        st.error("El nombre del producto y la marca son obligatorios.")
                    else:
                        try:
                            with engine.begin() as conn:
                                add_new_product(
                                    conn,
                                    clean_name,
                                    clean_brand,
                                    int(quantity),
                                    clean_notes,
                                )
                            st.success("Producto creado y existencias iniciales registradas.")
                            st.rerun()
                        except IntegrityError:
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
                        with engine.begin() as conn:
                            increase_stock(
                                conn,
                                product_id,
                                int(qty_to_add),
                                normalize_text(add_notes),
                            )
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
                    with engine.begin() as conn:
                        ok, message = withdraw_stock(
                            conn,
                            product_id,
                            int(qty_to_withdraw),
                            normalize_text(out_notes),
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

if __name__ == "__main__":
    main()
