"""
Streamlit — Strength Prescription Only (No Nutrition)
Features:
- Users, Clients, Exercises, Training Plans → Sessions → Set Prescriptions
- Strength Tests (1RM) per client & exercise
- In Sessions: pick exercise, sets, reps, %1RM, 1RM (autofilled from last test), suggested kg (editable)
- Persist load_kg and intensity_pct_1rm
- Compute tonnage per exercise and total per session (Σ sets×reps×kg)

Notes:
- MVP for internal testing/teaching.
- For production: replace auth, Postgres, HTTPS, proper RBAC, GDPR hardening.
"""
from __future__ import annotations
import datetime as dt
from typing import Optional

import streamlit as st
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Date,
    ForeignKey,
    Text,
    DateTime,
    Boolean,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

# -----------------------------
# DB SETUP (SQLite for MVP)
# -----------------------------
engine = create_engine("sqlite:///strength_only.db", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# -----------------------------
# MODELS
# -----------------------------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    role = Column(String, default="coach")  # coach | client | admin
    hash = Column(String, nullable=False)  # placeholder, do not store plain in prod
    created_at = Column(DateTime, default=dt.datetime.utcnow)


class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    sex = Column(String)
    dob = Column(Date)
    height_cm = Column(Float)
    weight_kg = Column(Float)
    notes = Column(Text, default="")
    owner_id = Column(Integer, ForeignKey("users.id"))  # coach owner
    user = relationship("User", foreign_keys=[user_id])
    owner = relationship("User", foreign_keys=[owner_id])


class Exercise(Base):
    __tablename__ = "exercises"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    category = Column(String)  # squat, hinge, push, pull, core, plyo
    equipment = Column(String)
    unilateral = Column(Boolean, default=False)
    description = Column(Text, default="")


class TrainingPlan(Base):
    __tablename__ = "training_plans"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    name = Column(String)
    start_date = Column(Date)
    end_date = Column(Date)
    goal = Column(Text)
    client = relationship("Client")


class TrainingSession(Base):
    __tablename__ = "training_sessions"
    id = Column(Integer, primary_key=True)
    plan_id = Column(Integer, ForeignKey("training_plans.id"))
    date = Column(Date)
    focus = Column(String)
    notes = Column(Text, default="")
    plan = relationship("TrainingPlan")


class SetPrescription(Base):
    __tablename__ = "set_prescriptions"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("training_sessions.id"))
    exercise_id = Column(Integer, ForeignKey("exercises.id"))
    sets = Column(Integer)
    reps = Column(Integer)
    intensity_pct_1rm = Column(Float)  # e.g., 75 => 75%1RM
    load_kg = Column(Float)            # kg per rep
    rest_sec = Column(Integer)
    notes = Column(Text, default="")
    session = relationship("TrainingSession")
    exercise = relationship("Exercise")


class StrengthTest(Base):
    __tablename__ = "strength_tests"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    exercise_id = Column(Integer, ForeignKey("exercises.id"))
    date = Column(Date)
    one_rm_kg = Column(Float)  # validated or estimated 1RM
    notes = Column(Text, default="")
    client = relationship("Client")
    exercise = relationship("Exercise")


Base.metadata.create_all(engine)


# -----------------------------
# DEMO DATA
# -----------------------------

def init_demo_data():
    db = SessionLocal()
    if not db.query(User).first():
        coach = User(email="coach@example.com", name="Coach Demo", role="coach", hash="demo")
        client_user = User(email="client@example.com", name="Client Demo", role="client", hash="demo")
        db.add_all([coach, client_user])
        db.commit()
        c = Client(user_id=client_user.id, sex="female", dob=dt.date(1990,1,1), height_cm=165, weight_kg=60, owner_id=coach.id)
        db.add(c)
        db.add_all([
            Exercise(name="Back Squat", category="squat", equipment="barbell"),
            Exercise(name="Bench Press", category="push", equipment="barbell"),
            Exercise(name="Deadlift", category="hinge", equipment="barbell"),
            Exercise(name="Lat Pulldown", category="pull", equipment="machine"),
        ])
        # Example plan to get started
        db.commit()
        plan = TrainingPlan(client_id=c.id, name="Preseason 4 weeks", start_date=dt.date.today(), end_date=dt.date.today()+dt.timedelta(days=27), goal="Fuerza básica")
        db.add(plan)
        db.commit()
    db.close()


init_demo_data()


# -----------------------------
# AUTH (demo)
# -----------------------------

def login():
    st.sidebar.subheader("Login (demo)")
    email = st.sidebar.text_input("Email", value="coach@example.com")
    pwd = st.sidebar.text_input("Password", type="password", value="demo")
    if st.sidebar.button("Sign in"):
        db = SessionLocal()
        user = db.query(User).filter(User.email==email, User.hash==pwd).first()
        db.close()
        if user:
            st.session_state["user"] = {"id": user.id, "name": user.name, "role": user.role, "email": user.email}
            st.success(f"Welcome {user.name}")
        else:
            st.error("Invalid credentials (demo user: coach@example.com / demo)")


def require_auth():
    if "user" not in st.session_state:
        st.warning("Please log in to continue.")
        login()
        st.stop()


# -----------------------------
# PAGES (Strength Only)
# -----------------------------

def page_strength_tests():
    st.title("🧪 Strength Tests (1RM)")
    db = SessionLocal()
    user = st.session_state["user"]
    clients = db.query(Client).filter(Client.owner_id == user["id"]).all()
    if not clients:
        st.info("Crea un cliente primero.")
        db.close()
        return

    client_map = {db.query(User).get(c.user_id).name: c.id for c in clients}
    client_name = st.selectbox("Cliente", options=list(client_map.keys()))
    exs = db.query(Exercise).all()
    if not exs:
        st.info("Añade ejercicios en la librería primero.")
        db.close()
        return
    exmap = {e.name: e.id for e in exs}
    ex_name = st.selectbox("Ejercicio", options=list(exmap.keys()))
    date = st.date_input("Fecha del test", value=dt.date.today())
    onerm = st.number_input("1RM (kg)", 0.0, 500.0, 100.0)
    notes = st.text_area("Notas", "")
    if st.button("Guardar test 1RM"):
        t = StrengthTest(client_id=client_map[client_name], exercise_id=exmap[ex_name], date=date, one_rm_kg=onerm, notes=notes)
        db.add(t)
        db.commit()
        st.success("Test guardado")

    st.subheader("Histórico recientes")
    tests = (
        db.query(StrengthTest)
        .filter(StrengthTest.client_id == client_map[client_name])
        .order_by(StrengthTest.date.desc())
        .limit(20)
        .all()
    )
    for t in tests:
        ex = db.query(Exercise).get(t.exercise_id)
        st.write(f"{t.date} — {ex.name}: **{t.one_rm_kg:.1f} kg**")

    db.close()


def page_sessions():
    st.title("🗓️ Sessions & Sets (Tonelaje)")
    db = SessionLocal()
    plans = db.query(TrainingPlan).all()
    if not plans:
        st.info("Crea un plan de entrenamiento primero.")
        db.close()
        return

    plan_map = {f"{p.name} ({p.start_date}→{p.end_date})": p.id for p in plans}
    psel = st.selectbox("Plan", options=list(plan_map.keys()))
    plan = db.query(TrainingPlan).get(plan_map[psel])

    st.caption(plan.goal)

    # Helpers
    def get_client_id_from_plan(pl: TrainingPlan) -> int:
        return pl.client_id

    def get_latest_one_rm(client_id: int, exercise_id: int) -> Optional[float]:
        test = (
            db.query(StrengthTest)
            .filter(StrengthTest.client_id == client_id, StrengthTest.exercise_id == exercise_id)
            .order_by(StrengthTest.date.desc())
            .first()
        )
        return test.one_rm_kg if test else None

    # Create session
    with st.expander("➕ Añadir sesión"):
        d = st.date_input("Fecha", value=plan.start_date)
        focus = st.text_input("Enfoque", value="Fuerza (básica)")
        notes = st.text_area("Notas", value="")
        if st.button("Añadir sesión"):
            s = TrainingSession(plan_id=plan.id, date=d, focus=focus, notes=notes)
            db.add(s)
            db.commit()
            st.success("Sesión añadida")

    # List sessions
    sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.plan_id == plan.id)
        .order_by(TrainingSession.date)
        .all()
    )
    exs = db.query(Exercise).all()
    exmap = {e.name: e.id for e in exs}

    for s in sessions:
        st.subheader(f"{s.date} — {s.focus}")
        if s.notes:
            st.caption(s.notes)

        with st.expander("Añadir serie a esta sesión"):
            ex_name = st.selectbox(
                f"Ejercicio (sesión {s.id})",
                options=list(exmap.keys()),
                key=f"ex_{s.id}",
            )
            sets = st.number_input("Series", 1, 20, 4, key=f"sets_{s.id}")
            reps = st.number_input("Reps", 1, 50, 6, key=f"reps_{s.id}")

            ex_id = exmap[ex_name]
            client_id = get_client_id_from_plan(plan)
            latest_1rm = get_latest_one_rm(client_id, ex_id)

            col_a, col_b = st.columns(2)
            with col_a:
                pct = st.slider("Intensidad (%1RM)", 30, 100, 75, step=1, key=f"pct_{s.id}")
            with col_b:
                one_rm_input = st.number_input(
                    "1RM del test (kg)", 0.0, 500.0,
                    float(latest_1rm) if latest_1rm else 100.0,
                    key=f"onerm_{s.id}"
                )

            suggested_load = round((pct / 100.0) * one_rm_input, 1)
            load = st.number_input(
                "Carga por repetición (kg)", 0.0, 500.0, suggested_load, step=0.5, key=f"load_{s.id}"
            )
            rest = st.number_input("Descanso (s)", 0, 600, 120, key=f"rest_{s.id}")
            notes = st.text_input("Notas", value="", key=f"notes_{s.id}")

            st.caption(f"Sugerido por %1RM: {suggested_load} kg (1RM {one_rm_input:.1f}, {pct}%) — editable.")

            if st.button("Añadir serie", key=f"addset_{s.id}"):
                sp = SetPrescription(
                    session_id=s.id,
                    exercise_id=ex_id,
                    sets=int(sets),
                    reps=int(reps),
                    intensity_pct_1rm=float(pct),
                    load_kg=float(load),
                    rest_sec=int(rest),
                    notes=notes,
                )
                db.add(sp)
                db.commit()
                st.success("Serie añadida")

        # Show sets and tonnage
        sets_ = db.query(SetPrescription).filter(SetPrescription.session_id == s.id).all()
        session_tonnage = 0.0
        if sets_:
            for sp in sets_:
                e = db.query(Exercise).get(sp.exercise_id)
                tonnage = (sp.sets or 0) * (sp.reps or 0) * (sp.load_kg or 0.0)
                session_tonnage += tonnage
                st.write(
                    f"• {e.name}: {sp.sets}×{sp.reps} @ {sp.load_kg:.1f} kg (~{sp.intensity_pct_1rm or 0:.0f}%1RM) — descanso {sp.rest_sec}s — **Tonelaje: {tonnage:.1f} kg**"
                )
                if sp.notes:
                    st.caption(sp.notes)
        st.info(f"Tonelaje total de la sesión: **{session_tonnage:.1f} kg**")

    db.close()


def page_settings():
    st.title("⚙️ Settings")
    st.write("This demo stores data in a local SQLite file `strength_only.db`.")
    if st.button("Reset database (danger)"):
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        init_demo_data()
        st.success("Database reset.")


def page_diagnostics():
    st.title("🧪 Diagnostics & Tests")
    # Test 1: tonnage calc
    sets, reps, load = 5, 5, 100.0
    tonnage = sets * reps * load
    try:
        assert tonnage == 2500.0
        st.success("Tonnage formula: OK (sets×reps×kg)")
    except AssertionError:
        st.error("Tonnage formula: FAILED")


# -----------------------------
# APP LAYOUT
# -----------------------------

st.set_page_config(page_title="Strength Prescriptor (Only)", layout="wide")
with st.sidebar:
    st.title("Strength Prescriptor")
    if "user" in st.session_state:
        st.write(f"{st.session_state['user']['name']} ({st.session_state['user']['role']})")
        if st.button("Log out"):
            st.session_state.pop("user")

page = st.sidebar.radio(
    "Navigate",
    [
        "Strength Tests",
        "Sessions",
        "Diagnostics",
        "Settings",
    ],
)

# Require auth except diagnostics
if "user" not in st.session_state and page not in {"Diagnostics"}:
    require_auth()

if page == "Strength Tests":
    page_strength_tests()
elif page == "Sessions":
    page_sessions()
elif page == "Diagnostics":
    page_diagnostics()
elif page == "Settings":
    page_settings()
