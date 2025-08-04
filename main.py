import os
import argparse
import sys
import streamlit as st
from clients.model_rest import AssistantClient
from clients.ollama_client import OllamaClient
from clients.jenkins_client import JenkinsClient
from clients.rp_client import ReportPortalManager
from clients.jira_client import JiraClient
import truststore
import dotenv
import requests
import yaml
import uuid
import re
import pandas as pd
from collections import Counter
import matplotlib.pyplot as plt
import subprocess
import select
import socket
import io
import base64

dotenv.load_dotenv()

# --- Argument Parsing ---
parser = argparse.ArgumentParser(description="Run Echo Chatbot with optional features.")
parser.add_argument('--enable-slidev', action='store_true', help='Enable Slidev presentation generation for ReportPortal reports.')
args, unknown = parser.parse_known_args()

if 'enable_slidev' not in st.session_state:
    st.session_state.enable_slidev = args.enable_slidev

# Initialize flags at a higher scope to ensure they are always defined
jenkins_handled = False
rp_handled = False
jira_handled = False
skip_llm_analysis = False
charts_and_analysis_rendered = False

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

@st.cache_data(ttl=300) # Cache for 5 minutes
def fetch_url_content(url):
    """Fetches content from a given URL."""
    if not url:
        return ""
    try:
        response = requests.get(url)
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        return response.text
    except requests.exceptions.RequestException as e:
        st.error(f"Failed to fetch content from {url}: {e}")
        return ""

# --- Sidebar Configuration ---
st.sidebar.title("Configuration")

provider = st.sidebar.selectbox("Provider", ["Models.corp", "ollama"])

client = None

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
    rp_manager = None
    rp_endpoint = st.text_input("ReportPortal Endpoint", value=os.environ.get("RP_ENDPOINT", ""))
    rp_uuid = st.text_input("ReportPortal UUID", value=os.environ.get("RP_UUID", ""), type="password")
    rp_project = st.text_input("ReportPortal Project", value=os.environ.get("RP_PROJECT", ""))
    disable_ssl_verification_rp = st.checkbox("Disable SSL Verification for ReportPortal (Insecure)", value=True, help="Check this only if you are experiencing SSL certificate errors with ReportPortal and understand the security implications.")
    
    if rp_endpoint and rp_uuid and rp_project:
        rp_manager = ReportPortalManager(endpoint=rp_endpoint, uuid=rp_uuid, project=rp_project, verify_ssl=not disable_ssl_verification_rp)
        st.success("ReportPortal integration enabled.")

with st.sidebar.expander("Jira Configuration"):
    jira_client = None
    jira_url = st.text_input("Jira URL", value=os.environ.get("JIRA_URL", ""))
    jira_api_token = st.text_input("Jira Personal Access Token", value=os.environ.get("JIRA_API_TOKEN", ""), type="password")
    jira_project_key = st.text_input("Jira Project Key (Optional)", value=os.environ.get("JIRA_PROJECT_KEY", "ACM"), help="Enter a default Jira project key to filter issues.")
    disable_ssl_verification_jira = st.checkbox("Disable SSL Verification for Jira (Insecure)", value=True, help="Check this only if you are experiencing SSL certificate errors with Jira and understand the security implications.")

    if jira_url and jira_api_token:
        try:
            jira_client = JiraClient(url=jira_url, api_token=jira_api_token, verify_ssl=not disable_ssl_verification_jira)
            st.success("Jira client initialized successfully!")
            print("DEBUG: Jira client initialized.")
            st.session_state['jira_client_initialized'] = True # Set a session state flag
        except Exception as e:
            st.error(f"Failed to initialize Jira client: {e}")
            print(f"DEBUG: Failed to initialize Jira client: {e}")
            st.session_state['jira_client_initialized'] = False # Set a session state flag
    else:
        st.session_state['jira_client_initialized'] = False # Ensure flag is set if credentials are missing

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

# --- Chat History Management ---
MAX_CHATS = 5

if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = []
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None
if "renaming_chat_id" not in st.session_state:
    st.session_state.renaming_chat_id = None
if "jira_component_rules_content" not in st.session_state:
    st.session_state.jira_component_rules_content = ""

def new_chat():
    if len(st.session_state.chat_sessions) >= MAX_CHATS:
        st.sidebar.error(f"Max chats ({MAX_CHATS}) reached. Delete one to create a new chat.")
        return
    
    # Save current chat if it has messages
    if st.session_state.active_chat_id and get_active_chat()["messages"]:
        save_chat_session()

    chat_id = str(uuid.uuid4())
    st.session_state.chat_sessions.append({"id": chat_id, "name": "New Chat", "messages": []})
    st.session_state.active_chat_id = chat_id
    st.rerun()

def switch_chat(chat_id):
    st.session_state.active_chat_id = chat_id
    st.session_state.renaming_chat_id = None
    st.rerun()

def delete_chat(chat_id):
    st.session_state.chat_sessions = [chat for chat in st.session_state.chat_sessions if chat["id"] != chat_id]
    if st.session_state.active_chat_id == chat_id:
        st.session_state.active_chat_id = st.session_state.chat_sessions[0]["id"] if st.session_state.chat_sessions else None
    st.rerun()

def rename_chat(chat_id):
    new_name = st.session_state[f"new_name_{chat_id}"]
    for session in st.session_state.chat_sessions:
        if session["id"] == chat_id:
            session["name"] = new_name
            break
    st.session_state.renaming_chat_id = None
    st.rerun()

def get_active_chat():
    if not st.session_state.active_chat_id:
        if not st.session_state.chat_sessions:
            # If no chats exist, create one
            chat_id = str(uuid.uuid4())
            st.session_state.chat_sessions.append({"id": chat_id, "name": "New Chat", "messages": []})
            st.session_state.active_chat_id = chat_id
        else:
            st.session_state.active_chat_id = st.session_state.chat_sessions[0]["id"]
    
    for session in st.session_state.chat_sessions:
        if session["id"] == st.session_state.active_chat_id:
            return session
    
    # Fallback in case active_chat_id is invalid
    if st.session_state.chat_sessions:
        st.session_state.active_chat_id = st.session_state.chat_sessions[0]["id"]
        return st.session_state.chat_sessions[0]
    
    # If all fallbacks fail, create a new chat
    chat_id = str(uuid.uuid4())
    st.session_state.chat_sessions.append({"id": chat_id, "name": "New Chat", "messages": []})
    st.session_state.active_chat_id = chat_id
    return st.session_state.chat_sessions[0]


def save_chat_session():
    active_chat = get_active_chat()
    if active_chat and active_chat["messages"] and active_chat["name"] == "New Chat":
        first_user_message = next((msg["content"] for msg in active_chat["messages"] if msg["role"] == "user"), "Chat")
        active_chat["name"] = first_user_message[:30] + "..." if len(first_user_message) > 30 else first_user_message

# --- Sidebar Chat History ---
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


# --- Main App Layout ---
st.title("Echo Chatbot")
active_chat = get_active_chat()

# Display past messages
if active_chat:
    for message in active_chat["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# Chat input
if prompt := st.chat_input("What is up?"):
    # Initialize flags at a higher scope
    jenkins_handled = False
    rp_handled = False
    skip_llm_analysis = False
    jira_command_handled_successfully = False

    if prompt.strip().lower() == "/new-chat":
        new_chat()
    # elif prompt.strip().lower().startswith("/rules add "):
    #     rules_url = prompt.strip()[len("/rules add "):].strip()
    #     if rules_url:
    #         with st.spinner(f"Loading rules from {rules_url}..."):
    #             content = fetch_url_content(rules_url)
    #             if content:
    #                 st.session_state.jira_component_rules_content = content
    #                 resp = f"Successfully loaded Jira component rules from {rules_url}."
    #             else:
    #                 resp = f"Failed to load Jira component rules from {rules_url}. Please check the URL and try again."
    #         with st.chat_message("assistant"):
    #             st.markdown(resp)
    #             active_chat["messages"].append({"role": "assistant", "content": resp})
    #             save_chat_session()
    #     else:
    #         resp = "Please provide a URL for the rules file. Usage: `/rules add <url>`"
    #         with st.chat_message("assistant"):
    #             st.markdown(resp)
    #             active_chat["messages"].append({"role": "assistant", "content": resp})
    #             save_chat_session()
    elif active_chat:
        active_chat["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = None
                jenkins_handled = False
                rp_handled = False
                jenkins_command_explicit = False

                print(f"DEBUG: Prompt received: {prompt}")

                # New logic to parse general prompts for ReportPortal filters
                if rp_manager and not jenkins_handled:
                    print(f"DEBUG: Attempting general RP prompt parsing for: {prompt}")
                    rp_general_match = re.search(r"(?:test report for|test report of|analysis for|data for)\s+(?:component\s*=\s*|component\s*:\s*)?([a-zA-Z0-9_.-]+)(?:\s+in\s+release\s*=\s*|\s+in\s+release\s*:\s*)?([a-zA-Z0-9_.-]+)?", prompt.lower())
                    
                    extracted_filters = []
                    if rp_general_match:
                        component = rp_general_match.group(1)
                        release = rp_general_match.group(2)
                        print(f"DEBUG: rp_general_match found. Component: {component}, Release: {release}")
                        if component:
                            extracted_filters.append(f"component:{component}")
                        if release:
                            extracted_filters.append(f"release:{release}")
                        
                        if extracted_filters:
                            attribute_filter = ",".join(extracted_filters)
                            print(f"DEBUG: Extracted RP filters: {attribute_filter}")
                            
                            launches = rp_manager.get_launches(attribute_filter=attribute_filter)
                            print(f"DEBUG: get_launches called. Result type: {type(launches)}")
                            if isinstance(launches, list):
                                st.session_state['rp_launches_data'] = launches # Store for charting
                                print(f"DEBUG: st.session_state['rp_launches_data'] set to: {st.session_state['rp_launches_data']}")
                                if launches:
                                    table_header = "| Launch Name | Pass Rate | URL |\n|---|---|---|\n"
                                    table_rows = []
                                    for launch in launches:
                                        table_rows.append(f"| {launch['name']} | {launch['pass_rate']} | [Link]({launch['url']}) |")
                                    resp = "### ReportPortal Launches:\n" + table_header + "\n".join(table_rows)
                                else:
                                    resp = "No launches found in ReportPortal with the given filter."
                            else:
                                resp = launches # Error message from RP client
                            rp_handled = True # Mark as handled if RP logic was engaged
                            print(f"DEBUG: rp_handled set to {rp_handled}")

                if prompt.strip() == "/" or prompt.strip().lower() == "/help":
                    resp = """Available Commands:
- `/new-chat`: Start a new chat session.
- `/rules add <url>`: Load Jira component rules from a markdown file at the given URL.
- Jenkins Commands (if configured):
  - `/jenkins list jobs [related to <keyword>]` or `list jenkins jobs [containing <keyword>]`
  - `/jenkins list views` or `list jenkins views`
  - `/jenkins check job <job_name>` or `check jenkins job <job_name>`
  - `/jenkins trigger job <job_name> [with params param1=value1,param2=value2]` or `trigger jenkins job <job_name> [with params param1=value1,param2=value2]`
- ReportPortal Commands (if configured):
    - `/rp list launches [attribute_key=attribute_value]`
- Jira Commands (if configured):
    - `/jira query <natural_language_query>` (e.g., `/jira query globalhub bugs to be fixed in current release`)
    - `/jira whoami`: Get information about the current Jira user.
- General Chat: Any other query will be handled by the selected LLM (Models.corp or Ollama)."""
                    jenkins_handled = True # Mark as handled to skip LLM
                    print(f"DEBUG: Help command handled. {jenkins_handled=}")

                skip_llm_analysis = False # Initialize flag

                # Explicit /rp commands (only if not already handled by general RP parsing)
                if not jenkins_handled and rp_manager and prompt.lower().startswith("/rp") and not rp_handled:
                    rp_prompt = prompt[len("/rp"):].strip()
                    if rp_prompt.lower().startswith("list launches"):
                        attribute_filter = None
                        filter_part = rp_prompt[len("list launches"):].strip()
                        if filter_part:
                            try:
                                # Support multiple attributes separated by commas, and key=value or key:value
                                attributes = []
                                for attr_pair_str in filter_part.split(","):
                                    if "=" in attr_pair_str:
                                        key, value = attr_pair_str.split("=", 1)
                                    elif ":" in attr_pair_str:
                                        key, value = attr_pair_str.split(":", 1)
                                    else:
                                        raise ValueError("Invalid attribute filter format. Use 'key=value' or 'key:value'.")
                                    attributes.append(f"{key.strip()}:{value.strip()}")
                                attribute_filter = ",".join(attributes)
                            except ValueError as e:
                                resp = f"Invalid attribute filter format: {e}. Please use 'key=value,key1=value1' or 'key:value,key1:value1'."
                                rp_handled = True
                        
                        if not rp_handled:
                            launches = rp_manager.get_launches(attribute_filter=attribute_filter)
                            if isinstance(launches, list) and launches:
                                st.session_state['rp_launches_data'] = launches # Store for charting
                                table_header = "| Launch Name | Pass Rate | URL |\n|---|---|---|\n"
                                table_rows = []
                                for launch in launches:
                                    table_rows.append(f"| {launch['name']} | {launch['pass_rate']} | [Link]({launch['url']}) |")
                                resp = "### ReportPortal Launches:\n" + table_header + "\n".join(table_rows)
                            elif isinstance(launches, list):
                                resp = "No launches found in ReportPortal with the given filter."
                            else:
                                resp = launches # Error message
                        rp_handled = True
                        skip_llm_analysis = True # Set flag to skip LLM analysis for explicit /rp commands
                    else:
                        resp = "I didn't understand your ReportPortal command. Try 'list launches [attribute_key=attribute_value]'."
                        rp_handled = True

                # Jira Commands
                print(f"DEBUG: Checking Jira client. jira_client is None: {jira_client is None}, jira_command_handled_successfully: {jira_command_handled_successfully}")
                if not jenkins_handled and not rp_handled and jira_client:
                    jira_prompt = prompt
                    
                    if jira_prompt.lower().strip() == "/jira whoami":
                        print(f"DEBUG: Entered /jira whoami block. jira_client: {jira_client})")
                        user_info = jira_client.get_current_user()
                        print(f"DEBUG: user_info from jira_client.get_current_user(): {user_info})")
                        if isinstance(user_info, dict):
                            resp = f"### Current Jira User:\n\n"
                            resp += f"- **Display Name:** {user_info.get('displayName', 'N/A')}\n"
                            resp += f"- **Email:** {user_info.get('emailAddress', 'N/A')}\n"
                            resp += f"- **Time Zone:** {user_info.get('timeZone', 'N/A')}\n"
                        else:
                            resp = user_info # Error message
                        print(f"DEBUG: resp after whoami processing: {resp})")
                        jira_command_handled_successfully = True
                        skip_llm_analysis = True
                        jira_handled = True
                    elif prompt.lower().startswith("/jira query"):
                        jira_prompt = prompt[len("/jira query"):].strip()
                        if client: # Ensure LLM client is available
                            # Programmatically handle date ranges and remove them from the prompt before sending to LLM
                            date_jql = ""
                            clean_jira_prompt = jira_prompt
                            if "last month" in jira_prompt.lower():
                                date_jql = "AND updated >= startOfMonth(-1) AND updated <= endOfMonth(-1)"
                                clean_jira_prompt = clean_jira_prompt.lower().replace("last month", "").strip()
                            elif "this month" in jira_prompt.lower():
                                date_jql = "AND updated >= startOfMonth() AND updated <= endOfMonth()"
                                clean_jira_prompt = clean_jira_prompt.lower().replace("this month", "").strip()

                            llm_jira_prompt = f"""You are an expert in Jira JQL. Based on the following user request, generate ONLY the JQL query string. It is very important to preserve the exact names for components and versions as provided in the user request. DO NOT include the 'project', 'component', or any date-related clauses (like 'created', 'updated', or 'duedate') in the JQL, as these will be handled separately by the application. DO NOT include any other text or markdown, just the JQL string.

User Request: {clean_jira_prompt}

Example JQL output for 'all bugs in the "Web UI" component for the "v2.1" release':
issuetype = Bug AND fixVersion = "v2.1"

Example JQL output for 'my open tasks':
assignee = currentUser() AND status in ("To Do", "In Progress") AND issuetype = Task
"""

                            try:
                                print(f"DEBUG: LLM Jira prompt being sent: {llm_jira_prompt}")
                                if provider == "ollama":
                                    llm_response = client.chat(model=ollama_model, messages=[{"role": "user", "content": llm_jira_prompt}])
                                else: # For Models.corp
                                    llm_response = client.chat([{"role": "user", "content": llm_jira_prompt}])
                                
                                print(f"DEBUG: LLM raw response for Jira: {llm_response}")
                                
                                # Extract JQL from code block or use directly
                                jql_match = re.search(r"```(?:jql)?\n(.*?)```", llm_response, re.DOTALL)
                                if jql_match:
                                    llm_generated_jql = jql_match.group(1).strip()
                                else:
                                    llm_generated_jql = llm_response.strip()

                                # Ensure a default JQL if LLM returns nothing useful
                                if not llm_generated_jql:
                                    llm_generated_jql = "ORDER BY created DESC"

                                # Extract component from the prompt
                                component_match = re.search(r"([a-zA-Z\s]+) bugs", jira_prompt)
                                components = [component_match.group(1).strip()] if component_match else None

                                # Explicitly prepend project to JQL, and filter out any project clauses LLM might have added
                                # This ensures the configured jira_project_key is always used.
                                cleaned_jql_parts = [part.strip() for part in llm_generated_jql.split(' AND ') if not part.strip().lower().startswith('project =')]
                                base_jql = ' AND '.join(cleaned_jql_parts)
                                
                                # Start with the project key
                                final_jql_query = f'project = "{jira_project_key}"'
                                
                                # Add the base JQL from the LLM if it's not empty
                                if base_jql:
                                    final_jql_query += f" AND {base_jql}"

                                # Add the programmatically generated date JQL
                                if date_jql:
                                    final_jql_query += f" {date_jql}"

                                # If the prompt is about issues "to be fixed", ensure we only get open issues.
                                if "to be fixed" in jira_prompt.lower() and "status" not in final_jql_query.lower():
                                    final_jql_query += ' AND status != "Closed"'
                                    print(f"DEBUG: Appended 'status != Closed' to JQL. New query: {final_jql_query}")

                                # if the prompt is about issues "assigned to me", get the current user and add it to the query
                                if "assigned to me" in jira_prompt.lower() and "assignee" not in final_jql_query.lower():
                                    user_info = jira_client.get_current_user()
                                    if isinstance(user_info, dict):
                                        final_jql_query += f" AND assignee = {user_info.get('name')}"
                                        print(f"DEBUG: Appended 'assignee' to JQL. New query: {final_jql_query}")
                                
                                print(f"DEBUG: Final JQL query for Jira: {final_jql_query}")
                                print(f"DEBUG: Calling jira_client.query_issues with project_key={jira_project_key}, components={components}")
                                
                                issues = jira_client.query_issues(final_jql_query, project_key=jira_project_key, components=components)
                                
                                print(f"DEBUG: Jira client raw response type: {type(issues)}")
                                print(f"DEBUG: Jira client raw response: {issues}")

                                if isinstance(issues, list):
                                    if issues:
                                        table_header = "| Key | Summary | Status | Priority | Assignee |\n|---|---|---|---|---|\n"
                                        table_rows = []
                                        for issue in issues:
                                            issue_url = issue.get('url', f"{jira_client.url}/browse/{issue['key']}")
                                            table_rows.append(f"| [{issue['key']}]({issue_url}) | {issue['summary']} | {issue['status']} | {issue['priority']} | {issue['assignee']} |")
                                        resp = "### Jira Issues:\n" + table_header + "\n".join(table_rows)
                                    else:
                                        resp = "No Jira issues found with the given query."
                                else:
                                    resp = issues # Error message from client
                                
                                jira_command_handled_successfully = True
                                skip_llm_analysis = True
                            except Exception as e:
                                resp = f"An error occurred during Jira query processing: {e}. Raw LLM response: {llm_response}"
                                jira_command_handled_successfully = True # Set to True even on error to prevent fallback
                        else:
                            resp = "LLM client is not configured. Cannot process natural language Jira queries."
                    
                    # Only show this if no Jira command was recognized
                    elif not jira_command_handled_successfully:
                        resp = "I didn't understand your Jira command. Try '/jira query <natural_language_query>' or '/jira whoami'."
                        print(f"DEBUG: Jira explicit command not understood. resp: {resp}")

                # Common charting and LLM analysis for ReportPortal data
                if rp_handled and 'rp_launches_data' in st.session_state and st.session_state['rp_launches_data'] and not charts_and_analysis_rendered:
                    slidev_output_dir = os.path.join(os.getcwd(), "slidev_presentations")
                    os.makedirs(slidev_output_dir, exist_ok=True)
                    launches_for_charting_and_analysis = st.session_state['rp_launches_data']
                    df = pd.DataFrame(launches_for_charting_and_analysis)

                    # Pass Rate Trend Chart
                    pass_rate_chart_path = os.path.join(slidev_output_dir, "pass_rate_trend.png")
                    st.subheader("Pass Rate Trend")
                    df['pass_rate_numeric'] = df['pass_rate'].str.replace('%', '').astype(float)
                    # Ensure 'startTime' is converted to datetime for proper sorting and plotting
                    df['start_time'] = pd.to_datetime(df['startTime'], unit='ms')
                    df = df.sort_values(by='start_time')
                    
                    fig_pass_rate, ax_pass_rate = plt.subplots(figsize=(10, 6))
                    ax_pass_rate.plot(df['start_time'], df['pass_rate_numeric'], marker='o')
                    ax_pass_rate.set_title('Pass Rate Trend')
                    ax_pass_rate.set_xlabel('Date')
                    ax_pass_rate.set_ylabel('Pass Rate (%)')
                    ax_pass_rate.grid(True)
                    plt.xticks(rotation=45)
                    plt.tight_layout()
                    fig_pass_rate.savefig(pass_rate_chart_path)
                    plt.close(fig_pass_rate) # Close the figure to free memory
                    st.image(pass_rate_chart_path)

                    # OCP Platform Test Coverage Chart
                    st.subheader("OCP Platform Test Coverage")
                    
                    def get_ocp_version_from_attributes(attributes):
                        for attr in attributes:
                            if attr.get('key') == 'ocpImage':
                                return attr.get('value', 'OCP_Unknown')
                        return 'OCP_Unknown'

                    df['ocp_version'] = df['attributes'].apply(get_ocp_version_from_attributes)
                    
                    # Calculate total tests per OCP version
                    ocp_coverage = df.groupby('ocp_version').agg(total_tests=('total', 'sum')).reset_index()

                    # Create a pie chart using matplotlib
                    ocp_coverage_chart_path = os.path.join(slidev_output_dir, "ocp_coverage.png")
                    print(f"DEBUG: OCP Coverage Chart Path: {ocp_coverage_chart_path}")
                    print(f"DEBUG: OCP Coverage DataFrame:\n{ocp_coverage}")
                    fig_ocp_coverage, ax_ocp_coverage = plt.subplots()
                    ax_ocp_coverage.pie(ocp_coverage['total_tests'], labels=ocp_coverage['ocp_version'], autopct='%1.1f%%', startangle=90)
                    ax_ocp_coverage.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
                    fig_ocp_coverage.savefig(ocp_coverage_chart_path)
                    plt.close(fig_ocp_coverage) # Close the figure to free memory
                    st.image(ocp_coverage_chart_path)
                    if os.path.exists(ocp_coverage_chart_path):
                        print(f"DEBUG: OCP Coverage Chart file exists at {ocp_coverage_chart_path}")
                    else:
                        print(f"DEBUG: OCP Coverage Chart file DOES NOT exist at {ocp_coverage_chart_path}")

                    # Analyze and display most frequent failure cases
                    st.subheader("Most Frequent Failure Cases")
                    all_failed_test_names = []
                    all_skipped_test_names = [] # New list for skipped tests
                    all_failed_issue_types = [] # Keep for potential future use or existing LLM analysis

                    # Define filters for failed and skipped test items separately
                    failed_item_filter = "filter.eq.hasStats=true&filter.eq.hasChildren=false&filter.in.type=STEP&filter.in.status=FAILED"
                    skipped_item_filter = "filter.eq.hasStats=true&filter.eq.hasChildren=false&filter.in.type=STEP&filter.in.status=SKIPPED"

                    for launch in launches_for_charting_and_analysis:
                        launch_id = launch.get('id')
                        failed_count = launch.get('failed', 0)
                        skipped_count = launch.get('skipped', 0)
                        
                        if launch_id and failed_count > 0:
                            test_items = rp_manager.get_test_items_for_launch(launch_id, item_filter=failed_item_filter)
                            if isinstance(test_items, list):
                                for item in test_items:
                                    all_failed_test_names.append(item.get('name', 'Unknown Test'))
                                    all_failed_issue_types.append(item.get('issue_type', 'Unknown Issue Type'))
                            else:
                                st.warning(f"Could not retrieve failed test items for launch {launch_id}: {test_items}")

                        if launch_id and skipped_count > 0:
                            test_items = rp_manager.get_test_items_for_launch(launch_id, item_filter=skipped_item_filter)
                            if isinstance(test_items, list):
                                for item in test_items:
                                    all_skipped_test_names.append(item.get('name', 'Unknown Test'))
                            else:
                                st.warning(f"Could not retrieve skipped test items for launch {launch_id}: {test_items}")
                    
                    
                    

                    if all_failed_test_names:
                        top_failed_tests = Counter(all_failed_test_names).most_common(5) # Top 5 failing tests
                        st.markdown("**Top 5 Failing Tests:**")
                        for test_name, count in top_failed_tests:
                            st.markdown(f"- {test_name} (Failed {count} times)")
                    else:
                        st.markdown("No failed tests found in the selected launches.")

                    # Display most frequent skipped cases
                    st.subheader("Most Frequent Skipped Cases")
                    if all_skipped_test_names:
                        top_skipped_tests = Counter(all_skipped_test_names).most_common(5) # Top 5 skipped tests
                        st.markdown("**Top 5 Skipped Tests:**")
                        for test_name, count in top_skipped_tests:
                            st.markdown(f"- {test_name} (Skipped {count} times)")
                    else:
                        st.markdown("No skipped tests found in the selected launches.")

                    # LLM Analysis
                    if provider == "Models.corp" and client and not skip_llm_analysis:
                        analysis_prompt = f"The user asked: '{prompt}'. Here is a list of ReportPortal launches:\n\n"
                        for launch in launches_for_charting_and_analysis:
                            analysis_prompt += f"- Name: {launch['name']}, Pass Rate: {launch['passed']}/{launch['total']} ({launch['pass_rate']}), URL: {launch['url']}\n"
                        
                        if all_failed_test_names:
                            analysis_prompt += "\nMost Frequent Failing Tests:\n"
                            for test_name, count in Counter(all_failed_test_names).most_common(5):
                                analysis_prompt += f"- {test_name} (Failed {count} times)\n"

                        if all_skipped_test_names:
                            analysis_prompt += "\nMost Frequent Skipped Tests:\n"
                            for test_name, count in Counter(all_skipped_test_names).most_common(5):
                                analysis_prompt += f"- {test_name} (Skipped {count} times)\n"

                        analysis_prompt += "\nBased on this data and the user's original request, please provide a comprehensive analysis. Focus on aspects like pass rates, test coverage across platforms, and identifying unstable tests."
                        
                        try:
                            llm_analysis_resp = client.chat(messages=[{"role": "user", "content": analysis_prompt}])
                            st.markdown("\n\n### LLM Analysis:\n" + llm_analysis_resp)
                            active_chat["messages"].append({"role": "assistant", "content": "\n\n### LLM Analysis:\n" + llm_analysis_resp}) # Add to chat history
                        except Exception as e:
                            st.markdown(f"\n\nError during LLM analysis: {e}")
                            active_chat["messages"].append({"role": "assistant", "content": f"\n\nError during LLM analysis: {e}"}) # Add error to chat history


                # --- Slidev Presentation Generation ---
                    if st.session_state.enable_slidev:
                        slidev_output_dir = os.path.join(os.getcwd(), "slidev_presentations")
                        os.makedirs(slidev_output_dir, exist_ok=True)

                        # Generate Slidev Markdown content
                        slidev_content = "# ReportPortal Analysis\n\n"
                        slidev_content += "---\n\n"
                        slidev_content += "## ReportPortal Launches\n\n"
                        if launches_for_charting_and_analysis:
                            slidev_content += "| Launch Name | Pass Rate | URL |\n"
                            slidev_content += "|---|---|---|\n"
                            for launch in launches_for_charting_and_analysis:
                                slidev_content += f"| {launch['name']} | {launch['pass_rate']} | [Link]({launch['url']}) |\n"
                        else:
                            slidev_content += "No launches found in ReportPortal with the given filter.\n"

                        slidev_content += "---\n\n"
                        slidev_content += "## Pass Rate Trend\n\n"
                        slidev_content += f"![Pass Rate Trend](/pass_rate_trend.png)\n\n"

                        slidev_content += "---\n\n"
                        slidev_content += "## OCP Platform Test Coverage\n\n"
                        slidev_content += f"![OCP Platform Test Coverage](/ocp_coverage.png)\n\n"

                        slidev_content += "---\n\n"
                        slidev_content += "## Most Frequent Failure Cases\n\n"
                        if all_failed_test_names:
                            top_failed_tests = Counter(all_failed_test_names).most_common(5)
                            for test_name, count in top_failed_tests:
                                slidev_content += f"- {test_name} (Failed {count} times)\n"
                        else:
                            slidev_content += "No failed tests found in the selected launches.\n"

                        slidev_content += "---\n\n"
                        slidev_content += "## Most Frequent Skipped Cases\n\n"
                        if all_skipped_test_names:
                            top_skipped_tests = Counter(all_skipped_test_names).most_common(5)
                            for test_name, count in top_skipped_tests:
                                slidev_content += f"- {test_name} (Skipped {count} times)\n"
                        else:
                            slidev_content += "No skipped tests found in the selected launches.\n"

                        if 'llm_analysis_resp' in locals():
                            slidev_content += "---\n\n"
                            slidev_content += "## LLM Analysis\n\n"
                            
                            # Process LLM analysis response to add slide breaks for sub-sections
                            processed_llm_analysis = []
                            lines = llm_analysis_resp.splitlines()
                            for line in lines:
                                if line.strip().startswith("## ") or line.strip().startswith("### "):
                                    processed_llm_analysis.append("---\n\n") # Add slide separator before new section
                                processed_llm_analysis.append(line)
                            
                            slidev_content += "\n".join(processed_llm_analysis) + "\n\n"

                        # Print the generated Slidev content for debugging
                        print("DEBUG: Generated Slidev Content:\n" + slidev_content)

                        # Write the content to serve.md
                        with open(os.path.join(slidev_output_dir, "serve.md"), "w") as f:
                            f.write(slidev_content)

                        # Check if npx is available

                        # Check if npx is available
                        npx_check = subprocess.run(["which", "npx"], capture_output=True, text=True)
                        if npx_check.returncode != 0:
                            st.warning("npx (Node.js package runner) not found. Please install Node.js and npm to serve Slidev presentations. You can still find the Markdown file at the path mentioned.")
                            resp += f"\n\n**Slidev Presentation:** To view, please install Node.js and npm, then go to `{slidev_output_dir}` and run `npx slidev serve`."
                        else:
                            if 'slidev_server_started' not in st.session_state or not st.session_state.slidev_server_started:
                                st.info(f"Starting Slidev server in {slidev_output_dir}...")
                                # Get the server's local IP address
                                try:
                                    server_ip = socket.gethostbyname(socket.gethostname())
                                except socket.gaierror:
                                    server_ip = "localhost" # Fallback if IP cannot be determined

                                process = subprocess.Popen(
                                    ["npx", "slidev", "--port", "3030", "--remote"], # Use a fixed port and bind to all interfaces
                                    cwd=slidev_output_dir,
                                    stdout=subprocess.DEVNULL, # Detach stdout
                                    stderr=subprocess.DEVNULL, # Detach stderr
                                    preexec_fn=os.setsid # Detach process from parent
                                )
                                server_url = f"http://{server_ip}:3030/" # Use server's IP
                                st.session_state.slidev_server_url = server_url
                                st.session_state.slidev_server_started = True
                                resp += f"\n\n**Slidev Presentation:** [Click here to open]({server_url})\n(Slidev server started on port 3030 in the background. To access from your local machine, create an SSH tunnel:\n`ssh -L 3030:localhost:3030 user@{server_ip}`\nThen open `{server_url}` in your local browser. If the link doesn't work, port 3030 might be in use on the remote server or {server_ip} is not publicly accessible.)"
                            else:
                                # If server is already started, just provide the existing URL
                                if 'slidev_server_url' in st.session_state and st.session_state.slidev_server_url:
                                    resp += f"\n\n**Slidev Presentation:** [Click here to open]({st.session_state.slidev_server_url})\n(Server already running. Remember to use SSH tunneling if accessing remotely.)"
                                else:
                                    # Fallback if URL is missing but server was marked as started
                                    try:
                                        server_ip = socket.gethostbyname(socket.gethostname())
                                    except socket.gaierror:
                                        server_ip = "localhost"
                                    server_url = f"http://{server_ip}:3030/"
                                    st.session_state.slidev_server_url = server_url
                                    resp += f"\n\n**Slidev Presentation:** [Click here to open]({server_url})\n(Slidev server was previously started on port 3030. Remember to use SSH tunneling if accessing remotely.)"


                        # This is a placeholder for the "send me a link" part.
                        # In a real scenario, you'd need a way to start a web server
                        # and get its URL. For now, we instruct the user.
                        # resp += f"\n\n**Slidev Presentation:** To view, go to `{slidev_output_dir}` and run `npx slidev serve`."
                        
                if not jenkins_handled and not rp_handled and jenkins_client:
                    jenkins_prompt = prompt
                    if prompt.lower().startswith("/jenkins"):
                        jenkins_prompt = prompt[len("/jenkins"):].strip()
                        jenkins_command_explicit = True
                    print(f"DEBUG: jenkins_command_explicit: {jenkins_command_explicit}, jenkins_prompt: {jenkins_prompt}")

                    prompt_lower = jenkins_prompt.lower()
                    import re
                    
                    list_jobs_match = re.search(r"(list|show me|get) (all )?jobs(?: (?:related to|containing) (.+))?", prompt_lower)
                    list_views_match = re.search(r"(list|show me|get) (all )?views", prompt_lower)
                    check_job_match = re.search(r"(check|get info for|status of) job (.+)", prompt_lower)
                    trigger_job_match = re.search(r"(trigger|run|start) job (.+?)( with params (.+))?$", prompt_lower)

                    print(f"DEBUG: list_jobs_match: {bool(list_jobs_match)}, check_job_match: {bool(check_job_match)}, trigger_job_match: {bool(trigger_job_match)}")

                    if list_jobs_match or check_job_match or trigger_job_match or list_views_match:
                        if list_jobs_match:
                            print("DEBUG: Matched list jobs command.")
                            jobs = jenkins_client.get_all_jobs(filter_keyword=list_jobs_match.group(3))
                            if isinstance(jobs, list):
                                if jobs:
                                    table_header = "| Job Name | Status | URL |\n|---|---|---|\n"
                                    table_rows = []
                                    for job_name in jobs:
                                        job_details = jenkins_client.get_job_status_and_url(job_name)
                                        if isinstance(job_details, dict):
                                            table_rows.append(f"| {job_details['name']} | {job_details['status']} | {job_details['url']} |")
                                        else:
                                            table_rows.append(f"| {job_name} | Error: {job_details} | N/A |")
                                    resp = "### Available Jenkins Jobs:\n" + table_header + "\n".join(table_rows)
                                else:
                                    resp = "No Jenkins jobs found."
                            else:
                                resp = jobs  # Error message from client
                            jenkins_handled = True
                        elif list_views_match:
                            print("DEBUG: Matched list views command.")
                            views = jenkins_client.get_all_views()
                            if isinstance(views, list):
                                if views:
                                    table_header = "| View Name | Number of Jobs | URL |\n|---|---|---|\n"
                                    table_rows = []
                                    for view in views:
                                        view_name = view.get('name', 'N/A')
                                        view_url = view.get('url', 'N/A')
                                        job_count = jenkins_client.get_view_job_count(view_name)
                                        if isinstance(job_count, int):
                                            table_rows.append(f"| {view_name} | {job_count} | {view_url} |")
                                        else:
                                            table_rows.append(f"| {view_name} | Error: {job_count} | {view_url} |")
                                        resp = "### Available Jenkins Views:\n" + table_header + "\n".join(table_rows)
                                    else:
                                        resp = "No Jenkins views found."
                                else:
                                    resp = views # Error message from client
                                jenkins_handled = True
                        elif check_job_match:
                            print("DEBUG: Matched check job command.")
                            job_name = check_job_match.group(2).strip()
                            info = jenkins_client.get_job_info(job_name)
                            print("DEBUG: The jobs info is: ", info)
                            if isinstance(info, dict):
                                resp = f"### Details for Jenkins Job: {job_name}\n\n"
                                resp += f"- **Description:** {info.get('description', 'N/A')}\n"
                                resp += f"- **URL:** {info.get('url', 'N/A')}\n"
                                resp += f"- **Buildable:** {info.get('buildable', 'N/A')}\n"
                                resp += f"- **Last Build:** {info.get('lastBuild', {{}}).get('number', 'N/A')} (URL: {info.get('lastBuild', {{}}).get('url', 'N/A')})\n"
                                resp += f"- **Last Successful Build:** {info.get('lastSuccessfulBuild', {{}}).get('number', 'N/A')}\n"
                                resp += f"- **Last Failed Build:** {info.get('lastFailedBuild', {{}}).get('number', 'N/A')}\n"
                                resp += f"- **Health Report:**\n"
                                health_report = info.get('healthReport', [])
                                if health_report:
                                    for report in health_report:
                                        resp += f"  - {report.get('description', 'N/A')} (Score: {report.get('score', 'N/A')})\n"
                                else:
                                    resp += "  N/A\n"
                                resp += f"- **Color/Status:** {info.get('color', 'N/A').replace("_anime", " (building)")}\n"
                                
                                # Store info for later expander rendering
                                st.session_state['jenkins_job_info_for_expander'] = {
                                    'job_name': job_name,
                                    'last_build_number': info.get('lastBuild', {}).get('number'),
                                    'jenkins_client': jenkins_client
                                }

                            else:
                                resp = info  # Error message from client
                            jenkins_handled = True
                        elif trigger_job_match:
                            print("DEBUG: Matched trigger job command.")
                            job_name = trigger_job_match.group(2).strip()
                            params_str = trigger_job_match.group(4)
                            parameters = None
                            if params_str:
                                parameters = {} 
                                for param_pair in params_str.split(","):
                                    key_value = param_pair.split("=")
                                    if len(key_value) == 2:
                                        parameters[key_value[0].strip()] = key_value[1].strip()
                            resp = jenkins_client.build_job(job_name, parameters)
                            jenkins_handled = True
                    
                    if not jenkins_handled and jenkins_command_explicit:
                        resp = "I didn't understand your Jenkins command. Try 'list jenkins jobs', 'check jenkins job <job_name>', or 'trigger jenkins job <job_name> [with params param1=value1,param2=value2]'."
                        jenkins_handled = True # Ensure it's handled by Jenkins logic, even if unrecognized
                        print(f"DEBUG: Jenkins explicit command not understood. resp: {resp}")

                if not jenkins_handled and not rp_handled and not jira_command_handled_successfully:
                    try:
                        if client:
                            if provider == "ollama":
                                resp = client.chat(model=ollama_model, messages=active_chat["messages"])
                            else:  # For Models.corp
                                resp = client.chat(active_chat["messages"])
                        else:
                            resp = "Chat client is not configured. Please check your settings in the sidebar."
                    except Exception as e:
                        resp = f"An error occurred with the LLM client: {e}"
                
                print(f"DEBUG: Final response: {resp}")
                if resp:
                    st.markdown(resp)
                    active_chat["messages"].append({"role": "assistant", "content": resp})
                    save_chat_session()

                    # Render Jenkins parameters expander if applicable
                    if jenkins_handled and 'jenkins_job_info_for_expander' in st.session_state and st.session_state['jenkins_job_info_for_expander']:
                        job_info_for_expander = st.session_state.pop('jenkins_job_info_for_expander') # Pop to clear after use
                        job_name_for_expander = job_info_for_expander['job_name']
                        last_build_number_for_expander = job_info_for_expander['last_build_number']
                        jenkins_client_for_expander = job_info_for_expander['jenkins_client']

                        if last_build_number_for_expander:
                            with st.expander(f"Parameters (Last Build #{last_build_number_for_expander})", expanded=False):
                                build_params = jenkins_client_for_expander.get_build_parameters(job_name_for_expander, last_build_number_for_expander)
                                if isinstance(build_params, dict) and build_params:
                                    for param_name, param_value in build_params.items():
                                        st.markdown(f"- **{param_name}**: {param_value}")
                                else:
                                    st.markdown(f"None found or error: {build_params}")
                        else:
                            st.markdown("- **Parameters (Last Build):** No last build found to retrieve parameters.")

                else:
                    st.error("No response generated.")
    else:
        st.warning("No active chat selected.")
        
if not st.session_state.chat_sessions:
    new_chat()

# Moved ReportPortal charting and analysis outside the spinner
#if rp_handled and 'rp_launches_data' in st.session_state and st.session_state['rp_launches_data'] and not charts_and_analysis_rendered:
#    launches_for_charting_and_analysis = st.session_state['rp_launches_data']
#    df = pd.DataFrame(launches_for_charting_and_analysis)
#
#    # OCP Platform Test Coverage Chart
#    st.subheader("OCP Platform Test Coverage")
#    
#    def get_ocp_version_from_attributes(attributes):
#        for attr in attributes:
#            if attr.get('key') == 'ocpImage':
#                return attr.get('value', 'OCP_Unknown')
#        return 'OCP_Unknown'
#
#    df['ocp_version'] = df['attributes'].apply(get_ocp_version_from_attributes)
#    
#
#    # Analyze and display most frequent failure cases
#    st.subheader("Most Frequent Failure Cases")
#    all_failed_test_names = []
#    all_failed_issue_types = []
#
#    for launch in launches_for_charting_and_analysis:
#        launch_id = launch.get('id')
#        if launch_id:
#            test_items = rp_manager.get_test_items_for_launch(launch_id)
#            if isinstance(test_items, list):
#                for item in test_items:
#                    if item.get('status') == 'FAILED':
#                        all_failed_test_names.append(item.get('name', 'Unknown Test'))
#                        all_failed_issue_types.append(item.get('issue_type', 'Unknown Issue Type'))
#            else:
#                st.warning(f"Could not retrieve test items for launch {launch_id}: {test_items}")
#    
#    if all_failed_test_names:
#        top_failed_tests = Counter(all_failed_test_names).most_common(5) # Top 5 failing tests
#        st.markdown("**Top 5 Failing Tests:**")
#        for test_name, count in top_failed_tests:
#            st.markdown(f"- {test_name} (Failed {count} times)")
#    else:
#        st.markdown("No failed tests found in the selected launches.")
#
#
#    # LLM Analysis
#    if provider == "Models.corp" and client and not skip_llm_analysis:
#        analysis_prompt = f"The user asked: '{prompt}'. Here is a list of ReportPortal launches:\n\n"
#        for launch in launches_for_charting_and_analysis:
#            analysis_prompt += f"- Name: {launch['name']}, Pass Rate: {launch['passed']}/{launch['total']} ({launch['pass_rate']}), URL: {launch['url']}\n"
#        
#        if all_failed_test_names:
#            analysis_prompt += "\nMost Frequent Failing Tests:\n"
#            for test_name, count in Counter(all_failed_test_names).most_common(5):
#                analysis_prompt += f"- {test_name} (Failed {count} times)\n"
#        
#        analysis_prompt += "\nBased on this data, including the Pass Rate Trend Chart and OCP Platform Test Coverage Chart, and the user's original request, please provide a comprehensive analysis. Focus on aspects like pass rates, test coverage across platforms, and identifying unstable tests. Describe the trends and insights observed in the charts."
#        
#        try:
#            llm_analysis_resp = client.chat(messages=[{"role": "user", "content": analysis_prompt}])
#            st.markdown("\n\n### LLM Analysis:\n" + llm_analysis_resp)
#        except Exception as e:
#            st.markdown(f"\n\nError during LLM analysis: {e}")
#    charts_and_analysis_rendered = True # Set flag to True after rendering
#