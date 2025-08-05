import streamlit as st
import uuid

MAX_CHATS = 5

def new_chat():
    """Creates a new chat session and sets it as active. Limits the number of active chats."""
    if len(st.session_state.chat_sessions) >= MAX_CHATS:
        st.sidebar.error(f"Max chats ({MAX_CHATS}) reached. Delete one to create a new chat.")
        return
    
    # Save current chat if it has messages before creating a new one.
    if st.session_state.active_chat_id and get_active_chat()["messages"]:
        save_chat_session()

    chat_id = str(uuid.uuid4())
    st.session_state.chat_sessions.append({"id": chat_id, "name": "New Chat", "messages": []})
    st.session_state.active_chat_id = chat_id
    st.rerun()

def switch_chat(chat_id):
    """Switches the active chat session to the specified chat_id."""
    st.session_state.active_chat_id = chat_id
    st.session_state.renaming_chat_id = None
    st.rerun()

def delete_chat(chat_id):
    """Deletes the chat session with the given chat_id."""
    st.session_state.chat_sessions = [chat for chat in st.session_state.chat_sessions if chat["id"] != chat_id]
    if st.session_state.active_chat_id == chat_id:
        st.session_state.active_chat_id = st.session_state.chat_sessions[0]["id"] if st.session_state.chat_sessions else None
    st.rerun()

def rename_chat(chat_id):
    """Renames the chat session with the given chat_id based on user input."""
    new_name = st.session_state[f"new_name_{chat_id}"]
    for session in st.session_state.chat_sessions:
        if session["id"] == chat_id:
            session["name"] = new_name
            break
    st.session_state.renaming_chat_id = None
    st.rerun()

def get_active_chat():
    """Retrieves the currently active chat session. Creates a new one if none exists."""
    if not st.session_state.active_chat_id:
        if not st.session_state.chat_sessions:
            # If no chats exist, create one.
            chat_id = str(uuid.uuid4())
            st.session_state.chat_sessions.append({"id": chat_id, "name": "New Chat", "messages": []})
            st.session_state.active_chat_id = chat_id
        else:
            st.session_state.active_chat_id = st.session_state.chat_sessions[0]["id"]
    
    for session in st.session_state.chat_sessions:
        if session["id"] == st.session_state.active_chat_id:
            return session
    
    # Fallback in case active_chat_id is invalid or not found.
    if st.session_state.chat_sessions:
        st.session_state.active_chat_id = st.session_state.chat_sessions[0]["id"]
        return st.session_state.chat_sessions[0]
    
    # If all fallbacks fail, create a new chat.
    chat_id = str(uuid.uuid4())
    st.session_state.chat_sessions.append({"id": chat_id, "name": "New Chat", "messages": []})
    st.session_state.active_chat_id = chat_id
    return st.session_state.chat_sessions[0]

def save_chat_session():
    """Saves the current chat session, renaming 'New Chat' sessions based on the first user message."""
    active_chat = get_active_chat()
    if active_chat and active_chat["messages"] and active_chat["name"] == "New Chat":
        first_user_message = next((msg["content"] for msg in active_chat["messages"] if msg["role"] == "user"), "Chat")
        active_chat["name"] = first_user_message[:30] + "..." if len(first_user_message) > 30 else first_user_message

def render_chat_history_sidebar():
    """Renders the chat history sidebar, allowing users to switch, rename, or delete chats."""
    with st.sidebar.expander("Chat History", expanded=True):
        for session in st.session_state.chat_sessions:
            if st.session_state.renaming_chat_id == session["id"]:
                st.text_input(
                    "New name",
                    value=session["name"],
                    on_change=rename_chat,
                    args=(session["id"],),
                    key=f"new_name_{session['id']}"
                )
            else:
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    if st.button(session["name"], key=f"switch_{session['id']}", use_container_width=True):
                        switch_chat(session["id"])
                with col2:
                    if st.button("✏️", key=f"rename_{session['id']}"):
                        st.session_state.renaming_chat_id = session["id"]
                        st.rerun()
                with col3:
                    if st.button("X", key=f"delete_{session['id']}"):
                        delete_chat(session["id"])