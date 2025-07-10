import os
import streamlit as st
from clients.model_rest import AssistantClient
import truststore
import dotenv
import requests
import yaml

truststore.inject_into_ssl()
dotenv.load_dotenv()

# --- Helper Functions ---
@st.cache_data(ttl=60)
def get_ollama_models(host):
    """Fetches the list of models from an Ollama host."""
    try:
        response = requests.get(f"{host}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
        return [model["name"] for model in models]
    except (requests.exceptions.RequestException, KeyError) as e:
        st.error(f"Failed to connect to Ollama at {host}. Please check the host address and ensure Ollama is running. Error: {e}")
        return []

# --- Sidebar Configuration ---
st.sidebar.title("Configuration")
provider = st.sidebar.selectbox("Provider", ["Models.corp", "ollama"])

client = None

if provider == "Models.corp":
    model_api = st.sidebar.text_input("Model API", value=os.environ.get("MODEL_API", ""))
    model_id = st.sidebar.text_input("Model ID", value=os.environ.get("MODEL_ID", ""))
    access_token = st.sidebar.text_input("Access Token", value=os.environ.get("ACCESS_TOKEN", ""), type="password")

    if model_api and model_id and access_token:
        client = AssistantClient(base_url=model_api, model=model_id, api_key=access_token)
    else:
        st.warning("Please configure the Models.corp credentials in the sidebar.")
        st.stop()

elif provider == "ollama":
    ollama_host = st.sidebar.text_input("Ollama Host", value=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    
    if ollama_host:
        available_models = get_ollama_models(ollama_host)
        if available_models:
            ollama_model = st.sidebar.selectbox("Ollama Model", available_models)
            client = AssistantClient(base_url=f"{ollama_host}/v1", model=ollama_model, api_key="ollama")
        else:
            st.warning("Could not fetch models from Ollama. Please ensure the host is correct and running.")
            st.stop()
    else:
        st.warning("Please configure the Ollama host in the sidebar.")
        st.stop()


# --- Main App ---
st.title("Echo Chatbot")

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display past messages
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("What is up?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                if client:
                    resp = client.chat(st.session_state.messages)
                    st.markdown(resp)
                    st.session_state.messages.append({"role": "assistant", "content": resp})
                else:
                    st.error("Chat client is not configured. Please check your settings in the sidebar.")
            except Exception as e:
                st.error(f"An error occurred: {e}")

