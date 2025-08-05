"""Handles the setup and management of various client configurations within the Streamlit application."""
import os
import streamlit as st
import truststore
import requests
from clients.model_rest import AssistantClient
from clients.ollama_client import OllamaClient
from clients.jenkins_client import JenkinsClient
from clients.rp_client import ReportPortalManager
from clients.jira_client import JiraClient

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

def setup_configurations():
    """
    Sets up and returns various client configurations based on user input in the Streamlit sidebar.

    This function initializes clients for:
    - LLM (Models.corp or Ollama)
    - Jenkins
    - ReportPortal
    - Jira

    It retrieves API keys, URLs, and other settings from environment variables or Streamlit text inputs.
    SSL verification can be optionally disabled for each service.

    Returns:
        tuple: A tuple containing initialized client objects and configuration parameters:
               (client, jenkins_client, rp_manager, jira_client, jira_project_key, provider, ollama_model)
    """
    client = None
    jenkins_client = None
    rp_manager = None
    jira_client = None
    ollama_model = None # Initialize ollama_model
    jira_project_key = os.environ.get("JIRA_PROJECT_KEY", "ACM") # Default value

    st.sidebar.title("Configuration")

    provider = st.sidebar.selectbox("Provider", ["Models.corp", "ollama"])

    if provider == "Models.corp":
        model_api = st.sidebar.text_input("Model API", value=os.environ.get("MODEL_API", ""))
        model_id = st.sidebar.text_input("Model ID", value=os.environ.get("MODEL_ID", ""))
        access_token = st.sidebar.text_input("Access Token", value=os.environ.get("ACCESS_TOKEN", ""), type="password")
        disable_ssl_verification = st.sidebar.checkbox("Disable SSL Verification (Insecure)", value=True, help="Check this only if you are experiencing SSL certificate errors and understand the security implications.")

        truststore.inject_into_ssl()

        if model_api and model_id and access_token:
            client = AssistantClient(base_url=model_api, model=model_id, api_key=access_token, verify_ssl=not disable_ssl_verification)
        else:
            st.warning("Please configure the Models.corp credentials in the sidebar.")
            st.stop()

    elif provider == "ollama":
        ollama_host = st.sidebar.text_input("Ollama Host", value=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
        
        if ollama_host:
            available_models = get_ollama_models(ollama_host)
            if available_models:
                ollama_model = st.sidebar.selectbox("Ollama Model", available_models)
                client = OllamaClient(host=ollama_host)
            else:
                st.warning("Could not fetch models from Ollama. Please ensure the host is correct and running.")
                st.stop()
        else:
            st.warning("Please configure the Ollama host in the sidebar.")
            st.stop()

    with st.sidebar.expander("Jenkins Configuration"):
        jenkins_client = None
        jenkins_url = st.text_input("Jenkins URL", value=os.environ.get("JENKINS_URL", ""))
        jenkins_username = st.text_input("Jenkins Username", value=os.environ.get("JENKINS_USERNAME", ""))
        jenkins_api_token = st.text_input("Jenkins API Token", value=os.environ.get("JENKINS_API_TOKEN", ""), type="password")
    
        if jenkins_url and jenkins_username and jenkins_api_token:
            try:
                jenkins_client = JenkinsClient(url=jenkins_url, username=jenkins_username, password=jenkins_api_token)
                st.success("Jenkins client initialized successfully!")
                print("DEBUG: Jenkins client initialized.")
            except Exception as e:
                st.error(f"Failed to initialize Jenkins client: {e}")
                print(f"DEBUG: Failed to initialize Jenkins client: {e}")
    
    with st.sidebar.expander("ReportPortal Configuration"):
        rp_endpoint = st.text_input("ReportPortal Endpoint", value=os.environ.get("RP_ENDPOINT", ""))
        rp_uuid = st.text_input("ReportPortal UUID", value=os.environ.get("RP_UUID", ""), type="password")
        rp_project = st.text_input("ReportPortal Project", value=os.environ.get("RP_PROJECT", ""))
        disable_ssl_verification_rp = st.checkbox("Disable SSL Verification for ReportPortal (Insecure)", value=True, help="Check this only if you are experiencing SSL certificate errors with ReportPortal and understand the security implications.")
        
        if rp_endpoint and rp_uuid and rp_project:
            rp_manager = ReportPortalManager(endpoint=rp_endpoint, uuid=rp_uuid, project=rp_project, verify_ssl=not disable_ssl_verification_rp)
            st.success("ReportPortal integration enabled.")
    
    with st.sidebar.expander("Jira Configuration"):
        jira_url = st.text_input("Jira URL", value=os.environ.get("JIRA_URL", ""))
        jira_api_token = st.text_input("Jira Personal Access Token", value=os.environ.get("JIRA_API_TOKEN", ""), type="password")
        jira_project_key = st.text_input("Jira Project Key (Optional)", value=jira_project_key, help="Enter a default Jira project key to filter issues.")
        disable_ssl_verification_jira = st.checkbox("Disable SSL Verification for Jira (Insecure)", value=True, help="Check this only if you are experiencing SSL certificate errors with Jira and understand the security implications.")
    
        if jira_url and jira_api_token:
            try:
                jira_client = JiraClient(url=jira_url, api_token=jira_api_token, verify_ssl=not disable_ssl_verification_jira)
                st.success("Jira client initialized successfully!")
                print("DEBUG: Jira client initialized.")
                st.session_state['jira_client_initialized'] = True
            except Exception as e:
                st.error(f"Failed to initialize Jira client: {e}")
                print(f"DEBUG: Failed to initialize Jira client: {e}")
                st.session_state['jira_client_initialized'] = False
        else:
            st.session_state['jira_client_initialized'] = False
    
        print(f"DEBUG: jira_client_initialized session state: {st.session_state.get('jira_client_initialized')}")
    
        if st.button("Test Jira Connection", key="test_jira_connection"):
            if jira_url and jira_api_token:
                try:
                    test_jira_client = JiraClient(url=jira_url, api_token=jira_api_token, verify_ssl=not disable_ssl_verification_jira)
                    st.success("Jira connection successful!")
                except ConnectionError as e:
                    st.error(f"Jira connection failed: {e}")
                except Exception as e:
                    st.error(f"An unexpected error occurred during Jira connection test: {e}")
                else:
                    st.warning("Please fill in all Jira configuration fields to test the connection.")
        
        return client, jenkins_client, rp_manager, jira_client, jira_project_key, provider, ollama_model
