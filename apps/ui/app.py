"""Streamlit Chat UI — Phase 8.

Features:
  - Login / Register flow
  - Multi-turn chat with session persistence
  - Citations displayed below each answer
  - Latency badge per response
"""

import os

import requests
import streamlit as st

API_BASE = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="AWS Docs Assistant",
    page_icon="☁️",
    layout="centered",
)

# ── Session state defaults ────────────────────────────────────────────────────
_DEFAULTS: dict[str, object] = {
    "token": None,
    "session_id": None,
    "messages": [],
    "email": "",
}
for key, default in _DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ───────────────────────────────────────────────────────────────────


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def _api_post(path: str, payload: dict, auth: bool = True) -> requests.Response:
    headers = _auth_headers() if auth else {}
    return requests.post(f"{API_BASE}{path}", json=payload, headers=headers, timeout=120)


# ── Auth page ─────────────────────────────────────────────────────────────────


def show_auth_page() -> None:
    st.title("☁️ AWS Docs Assistant")
    st.caption("Ask questions about any AWS service, answered from official documentation.")

    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        if st.button("Login", use_container_width=True):
            resp = _api_post("/auth/login", {"email": email, "password": password}, auth=False)
            if resp.status_code == 200:
                data = resp.json()
                st.session_state.token = data["access_token"]
                st.session_state.email = email
                st.success("Logged in!")
                st.rerun()
            else:
                st.error(resp.json().get("detail", "Login failed"))

    with tab_register:
        reg_email = st.text_input("Email", key="reg_email")
        reg_password = st.text_input("Password", type="password", key="reg_password")
        if st.button("Create account", use_container_width=True):
            resp = _api_post(
                "/auth/register",
                {"email": reg_email, "password": reg_password},
                auth=False,
            )
            if resp.status_code == 201:
                st.success("Account created! Please log in.")
            else:
                st.error(resp.json().get("detail", "Registration failed"))


# ── Chat page ─────────────────────────────────────────────────────────────────


def show_chat_page() -> None:
    # Sidebar
    with st.sidebar:
        st.title("☁️ AWS Docs Assistant")
        st.caption(f"Signed in as **{st.session_state.email}**")
        st.divider()
        if st.button("New conversation", use_container_width=True):
            st.session_state.session_id = None
            st.session_state.messages = []
            st.rerun()
        if st.button("Logout", use_container_width=True):
            for key in ["token", "session_id", "messages", "email"]:
                st.session_state[key] = (
                    None if key == "token" else ([] if key == "messages" else "")
                )
            st.rerun()

    st.header("Ask about AWS")

    # Render existing messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander(
                    f"📎 {len(msg['sources'])} source(s)  •  {msg.get('latency_ms', 0):.0f} ms"
                ):
                    for src in msg["sources"]:
                        st.markdown(f"- [{src['title']}]({src['url']})")

    # Chat input
    if prompt := st.chat_input("e.g. How do I enable S3 versioning?"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Searching AWS docs…"):
                payload: dict = {"query": prompt}
                if st.session_state.session_id:
                    payload["session_id"] = st.session_state.session_id

                resp = _api_post("/chat", payload)

            if resp.status_code == 200:
                data = resp.json()
                st.session_state.session_id = data["session_id"]
                answer = data["answer"]
                sources = data.get("sources", [])
                latency = data.get("latency_ms", 0)

                st.markdown(answer)
                if sources:
                    with st.expander(f"📎 {len(sources)} source(s)  •  {latency:.0f} ms"):
                        for src in sources:
                            st.markdown(f"- [{src['title']}]({src['url']})")

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sources": sources,
                        "latency_ms": latency,
                    }
                )
            elif resp.status_code == 401:
                st.error("Session expired. Please log in again.")
                st.session_state.token = None
                st.rerun()
            elif resp.status_code == 429:
                st.warning("Rate limit reached. Please wait a moment and try again.")
            else:
                st.error(f"Error {resp.status_code}: {resp.json().get('detail', 'Unknown error')}")


# ── Router ────────────────────────────────────────────────────────────────────

if st.session_state.token:
    show_chat_page()
else:
    show_auth_page()
