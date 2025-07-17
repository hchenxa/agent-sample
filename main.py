import os
import streamlit as st
from clients.model_rest import AssistantClient
from clients.ollama_client import OllamaClient
from clients.jenkins_client import JenkinsClient
from clients.rp_client import ReportPortalManager
import truststore
import dotenv
import requests
import yaml
import uuid

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
    rp_attribute_filter_input = st.text_input("Launch Attribute Filter (e.g., key=value)", key="rp_attribute_filter_input")
    
    if rp_endpoint and rp_uuid and rp_project:
        rp_manager = ReportPortalManager(endpoint=rp_endpoint, uuid=rp_uuid, project=rp_project, verify_ssl=not disable_ssl_verification_rp)
        rp_manager.start_service()
        rp_manager.start_launch("AI-Copilot Chat")
        st.success("ReportPortal integration enabled.")

# --- Chat History Management ---
MAX_CHATS = 5

if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = []
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None
if "renaming_chat_id" not in st.session_state:
    st.session_state.renaming_chat_id = None

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
    if prompt.strip().lower() == "/new-chat":
        new_chat()
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

                if prompt.strip() == "/" or prompt.strip().lower() == "/help":
                    resp = """Available Commands:
- `/new-chat`: Start a new chat session.
- Jenkins Commands (if configured):
  - `/jenkins list jobs [related to <keyword>]` or `list jenkins jobs [containing <keyword>]`
  - `/jenkins list views` or `list jenkins views`
  - `/jenkins check job <job_name>` or `check jenkins job <job_name>`
  - `/jenkins trigger job <job_name> [with params param1=value1,param2=value2]` or `trigger jenkins job <job_name> [with params param1=value1,param2=value2]`
- ReportPortal Commands (if configured):
    - `/rp list launches`
- General Chat: Any other query will be handled by the selected LLM (Models.corp or Ollama)."""
                    jenkins_handled = True # Mark as handled to skip LLM
                    print(f"DEBUG: Help command handled. jenkins_handled: {jenkins_handled}")

                if not jenkins_handled and rp_manager and prompt.lower().startswith("/rp"):
                    rp_prompt = prompt[len("/rp"):].strip()
                    if rp_prompt.lower().startswith("list launches"):
                        attribute_filter = None
                        filter_part = rp_prompt[len("list launches"):].strip()
                        if filter_part:
                            try:
                                key, value = filter_part.split("=", 1)
                                attribute_filter = {key.strip(): value.strip()}
                            except ValueError:
                                resp = "Invalid attribute filter format. Please use 'key=value'."
                                rp_handled = True
                        
                        if not rp_handled:
                            launches = rp_manager.get_launches(attribute_filter=attribute_filter)
                            if isinstance(launches, list) and launches:
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
                                resp += f"- **Last Build:** {info.get('lastBuild', {}).get('number', 'N/A')} (URL: {info.get('lastBuild', {}).get('url', 'N/A')})\n"
                                resp += f"- **Last Successful Build:** {info.get('lastSuccessfulBuild', {}).get('number', 'N/A')}\n"
                                resp += f"- **Last Failed Build:** {info.get('lastFailedBuild', {}).get('number', 'N/A')}\n"
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

                print(f"DEBUG: jenkins_handled before LLM check: {jenkins_handled}")
                if not jenkins_handled and not rp_handled:
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
                    st.rerun()

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

if rp_manager:
    import atexit
    atexit.register(rp_manager.finish_launch)