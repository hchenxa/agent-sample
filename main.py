import os
import argparse
import streamlit as st
import dotenv
import uuid
import re
import pandas as pd
from collections import Counter
import matplotlib.pyplot as plt
import subprocess
import socket
from utils.config_manager import setup_configurations
from utils.chat_history_manager import new_chat, get_active_chat, save_chat_session, render_chat_history_sidebar
from utils.rp_analytics import ReportPortalAnalytics

dotenv.load_dotenv()

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

client, jenkins_client, rp_manager, jira_client, jira_project_key, provider, ollama_model = setup_configurations()

def read_prompt_file(filename):
    with open(os.path.join("prompt", filename), "r") as f:
        return f.read()

if "chat_sessions" not in st.session_state:
    st.session_state.chat_sessions = []
if "active_chat_id" not in st.session_state:
    st.session_state.active_chat_id = None
if "renaming_chat_id" not in st.session_state:
    st.session_state.renaming_chat_id = None
if "jira_component_rules_content" not in st.session_state:
    st.session_state.jira_component_rules_content = ""

render_chat_history_sidebar()

# File Upload Section in Sidebar
with st.sidebar.expander("Upload File", expanded=False):
    uploaded_file = st.file_uploader("Choose a file", type=["txt", "csv", "json", "log", "md", "py", "xml", "html", "css", "js", "ts", "tsx", "java", "c", "cpp", "h", "hpp", "go", "rs", "toml", "yaml", "yml", "ini", "cfg", "conf", "sh", "bash", "Dockerfile", "sql", "jsonl", "tsv", "parquet", "feather", "avro", "orc", "xlsx", "xls", "odt", "ods", "odp", "doc", "docx", "ppt", "pptx", "pdf", "png", "jpg", "jpeg", "gif", "bmp", "svg", "webp"]) # Broad range of types
    if uploaded_file is not None:
        file_details = {"filename": uploaded_file.name, "filetype": uploaded_file.type, "filesize": uploaded_file.size}
        st.write(file_details)

        # Read file content based on type
        if uploaded_file.type and ("text" in uploaded_file.type or uploaded_file.type in [
            "application/json", "application/xml", "application/x-sh", "application/x-yaml",
            "text/markdown", "text/csv", "text/plain", "text/html", "text/css", "text/javascript",
            "application/x-python", "text/x-java-source", "text/x-c", "text/x-c++", "text/x-go", "text/x-rust",
            "application/toml", "application/x-ini", "application/x-config", "application/x-sql",
            "application/jsonl", "text/tab-separated-values"
        ]):
            string_data = uploaded_file.read().decode("utf-8")
            st.session_state['uploaded_file_content'] = string_data
            st.session_state['uploaded_file_name'] = uploaded_file.name
            st.success(f"File '{uploaded_file.name}' uploaded and content stored.")
            with st.expander("View File Content", expanded=False):
                st.code(string_data, language=uploaded_file.name.split('.')[-1])
        elif uploaded_file.type and ("image" in uploaded_file.type or uploaded_file.type == "application/pdf"):
            st.warning(f"File '{uploaded_file.name}' is a binary file ({uploaded_file.type}). Content cannot be displayed directly as text.")
            st.session_state['uploaded_file_content'] = uploaded_file.getvalue() # Store binary content
            st.session_state['uploaded_file_name'] = uploaded_file.name
        else:
            st.warning(f"Unsupported file type: {uploaded_file.type}. Content not stored for LLM analysis.")
            st.session_state['uploaded_file_content'] = None
            st.session_state['uploaded_file_name'] = None

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
                    resp = read_prompt_file("help_message.txt")
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

                            llm_jira_prompt = read_prompt_file("jira_query_prompt.txt").format(clean_jira_prompt=clean_jira_prompt)

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

                    # Gather detailed test data for enhanced analytics
                    test_items_data = {}
                    all_failed_test_names = []
                    all_skipped_test_names = []
                    all_failed_issue_types = []

                    # Define filters for failed and skipped test items
                    failed_item_filter = "filter.eq.hasStats=true&filter.eq.hasChildren=false&filter.in.type=STEP&filter.in.status=FAILED"
                    skipped_item_filter = "filter.eq.hasStats=true&filter.eq.hasChildren=false&filter.in.type=STEP&filter.in.status=SKIPPED"
                    all_items_filter = "filter.eq.hasStats=true&filter.eq.hasChildren=false&filter.in.type=STEP"

                    for launch in launches_for_charting_and_analysis:
                        launch_id = launch.get('id')
                        failed_count = launch.get('failed', 0)
                        skipped_count = launch.get('skipped', 0)
                        
                        if launch_id:
                            # Get all test items for this launch for analytics
                            all_test_items = rp_manager.get_test_items_for_launch(launch_id, item_filter=all_items_filter)
                            if isinstance(all_test_items, list):
                                test_items_data[launch_id] = all_test_items
                            
                            # Get failed tests
                            if failed_count > 0:
                                test_items = rp_manager.get_test_items_for_launch(launch_id, item_filter=failed_item_filter)
                                if isinstance(test_items, list):
                                    for item in test_items:
                                        all_failed_test_names.append(item.get('name', 'Unknown Test'))
                                        all_failed_issue_types.append(item.get('issue_type', 'Unknown Issue Type'))

                            # Get skipped tests  
                            if skipped_count > 0:
                                test_items = rp_manager.get_test_items_for_launch(launch_id, item_filter=skipped_item_filter)
                                if isinstance(test_items, list):
                                    for item in test_items:
                                        all_skipped_test_names.append(item.get('name', 'Unknown Test'))

                    # Initialize enhanced analytics
                    analytics = ReportPortalAnalytics(launches_for_charting_and_analysis, test_items_data)
                    
                    # Generate executive summary
                    exec_summary = analytics.generate_executive_summary()
                    exec_metrics = analytics.calculate_test_execution_metrics()
                    flaky_tests = analytics.detect_flaky_tests()
                    failure_analysis = analytics.analyze_failure_patterns()
                    duration_analytics = analytics.calculate_test_duration_analytics()
                    historical_comparison = analytics.generate_historical_comparison()

                    # Display Executive Summary Dashboard
                    st.subheader("📊 Executive Summary")
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("Total Launches", exec_summary['overview']['total_launches'])
                        st.metric("Quality Score", f"{exec_summary['overview']['quality_score']}/100")
                    
                    with col2:
                        st.metric("Total Tests", exec_summary['overview']['total_tests'])
                        st.metric("Overall Pass Rate", f"{exec_summary['overview']['overall_pass_rate']:.1f}%")
                    
                    with col3:
                        st.metric("Flaky Tests", exec_summary['test_stability']['flaky_tests_detected'])
                        if duration_analytics.get('avg_test_duration'):
                            st.metric("Avg Test Duration", f"{duration_analytics['avg_test_duration']:.1f}s")
                    
                    with col4:
                        st.metric("Failure Patterns", exec_summary['failure_insights']['unique_failure_patterns'])
                        if historical_comparison.get('avg_pass_rate_change'):
                            change = historical_comparison['avg_pass_rate_change']
                            st.metric("Pass Rate Trend", f"{change:+.1f}%")

                    # Test Execution Metrics
                    st.subheader("📈 Test Execution Metrics")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write("**Test Volume:**")
                        st.write(f"- Average tests per launch: {exec_metrics.get('avg_tests_per_launch', 0):.1f}")
                        st.write(f"- Median tests per launch: {exec_metrics.get('median_tests_per_launch', 0):.1f}")
                        st.write(f"- Total passed: {exec_metrics.get('total_passed', 0):,}")
                        st.write(f"- Total failed: {exec_metrics.get('total_failed', 0):,}")
                        st.write(f"- Total skipped: {exec_metrics.get('total_skipped', 0):,}")
                    
                    with col2:
                        st.write("**Quality Metrics:**")
                        st.write(f"- Average pass rate: {exec_metrics.get('avg_pass_rate', 0):.1f}%")
                        st.write(f"- Pass rate stability (σ): {exec_metrics.get('pass_rate_std', 0):.1f}%")
                        trend = exec_metrics.get('test_execution_trend', 0)
                        trend_direction = "📈 Increasing" if trend > 0 else "📉 Decreasing" if trend < 0 else "➡️ Stable"
                        st.write(f"- Test volume trend: {trend_direction}")

                    # Test Stability Analysis
                    if flaky_tests:
                        st.subheader("⚠️ Test Stability Analysis")
                        st.write("**Top Flaky Tests:**")
                        for i, test in enumerate(flaky_tests[:5], 1):
                            with st.expander(f"{i}. {test['test_name']} (Flaky Score: {test['flaky_score']:.1f}%)"):
                                st.write(f"- **Total runs:** {test['total_runs']}")
                                st.write(f"- **Passed:** {test['passed']} times")
                                st.write(f"- **Failed:** {test['failed']} times")
                                st.write(f"- **Skipped:** {test['skipped']} times")
                                st.write("- **Status distribution:**", test['status_distribution'])

                    # Enhanced Failure Analysis
                    if failure_analysis.get('failure_categories'):
                        st.subheader("🔍 Failure Pattern Analysis")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Failure Categories:**")
                            for category, count in failure_analysis['failure_categories'].items():
                                if count > 0:
                                    st.write(f"- {category}: {count}")
                        
                        with col2:
                            st.write("**Top Failure Patterns:**")
                            for pattern, count in failure_analysis.get('top_failure_patterns', [])[:5]:
                                st.write(f"- {pattern}: {count} occurrences")

                        # Critical Issues Alert
                        critical_issues = exec_summary['failure_insights'].get('critical_issues', [])
                        if critical_issues:
                            st.error("**🚨 Critical Issues Detected:**")
                            for issue in critical_issues:
                                st.write(f"- {issue}")

                    # Performance Analytics
                    if duration_analytics:
                        st.subheader("⏱️ Performance Analytics")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write("**Duration Statistics:**")
                            st.write(f"- Average: {duration_analytics.get('avg_test_duration', 0):.1f}s")
                            st.write(f"- Median: {duration_analytics.get('median_test_duration', 0):.1f}s")
                            st.write(f"- Min: {duration_analytics.get('min_test_duration', 0):.1f}s")
                            st.write(f"- Max: {duration_analytics.get('max_test_duration', 0):.1f}s")
                        
                        with col2:
                            slowest_tests = duration_analytics.get('slowest_tests', [])
                            if slowest_tests:
                                st.write("**Slowest Tests:**")
                                for test in slowest_tests[:5]:
                                    st.write(f"- {test['test_name']}: {test['avg_duration']:.1f}s")

                    # Historical Comparison
                    if historical_comparison:
                        st.subheader("📊 Historical Trends (Last 30 Days)")
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            if 'avg_pass_rate_change' in historical_comparison:
                                change = historical_comparison['avg_pass_rate_change']
                                delta_color = "normal" if abs(change) < 5 else ("inverse" if change < 0 else "normal")
                                st.metric("Pass Rate Change", f"{change:+.1f}%", delta_color=delta_color)
                        
                        with col2:
                            if 'avg_tests_per_launch_change' in historical_comparison:
                                change = historical_comparison['avg_tests_per_launch_change']
                                st.metric("Test Volume Change", f"{change:+.1f}%")
                        
                        with col3:
                            if 'total_tests_change' in historical_comparison:
                                change = historical_comparison['total_tests_change']
                                st.metric("Total Tests Change", f"{change:+.1f}%")

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

                    # Legacy Failure and Skipped Analysis (now included in enhanced analytics above)
                    st.subheader("Most Frequent Failure Cases")
                    if all_failed_test_names:
                        top_failed_tests = Counter(all_failed_test_names).most_common(5)
                        st.markdown("**Top 5 Failing Tests:**")
                        for test_name, count in top_failed_tests:
                            st.markdown(f"- {test_name} (Failed {count} times)")
                    else:
                        st.markdown("No failed tests found in the selected launches.")

                    # Display most frequent skipped cases
                    st.subheader("Most Frequent Skipped Cases")
                    if all_skipped_test_names:
                        top_skipped_tests = Counter(all_skipped_test_names).most_common(5)
                        st.markdown("**Top 5 Skipped Tests:**")
                        for test_name, count in top_skipped_tests:
                            st.markdown(f"- {test_name} (Skipped {count} times)")
                    else:
                        st.markdown("No skipped tests found in the selected launches.")

                    # Enhanced LLM Analysis with new metrics
                    if provider == "Models.corp" and client and not skip_llm_analysis:
                        analysis_prompt = f"The user asked: '{prompt}'. Here is comprehensive ReportPortal analysis data:\n\n"
                        
                        # Executive Summary
                        analysis_prompt += f"## Executive Summary:\n"
                        analysis_prompt += f"- Total Launches: {exec_summary['overview']['total_launches']}\n"
                        analysis_prompt += f"- Total Tests: {exec_summary['overview']['total_tests']:,}\n"
                        analysis_prompt += f"- Overall Pass Rate: {exec_summary['overview']['overall_pass_rate']:.1f}%\n"
                        analysis_prompt += f"- Quality Score: {exec_summary['overview']['quality_score']}/100\n"
                        analysis_prompt += f"- Flaky Tests Detected: {exec_summary['test_stability']['flaky_tests_detected']}\n"
                        analysis_prompt += f"- Unique Failure Patterns: {exec_summary['failure_insights']['unique_failure_patterns']}\n\n"
                        
                        # Test Execution Metrics
                        analysis_prompt += f"## Test Execution Metrics:\n"
                        analysis_prompt += f"- Average tests per launch: {exec_metrics.get('avg_tests_per_launch', 0):.1f}\n"
                        analysis_prompt += f"- Pass rate stability (std dev): {exec_metrics.get('pass_rate_std', 0):.1f}%\n"
                        trend = exec_metrics.get('test_execution_trend', 0)
                        trend_text = "increasing" if trend > 0 else "decreasing" if trend < 0 else "stable"
                        analysis_prompt += f"- Test volume trend: {trend_text}\n\n"
                        
                        # Flaky Tests
                        if flaky_tests:
                            analysis_prompt += f"## Top Flaky Tests:\n"
                            for test in flaky_tests[:3]:
                                analysis_prompt += f"- {test['test_name']}: {test['flaky_score']:.1f}% flaky score ({test['passed']}/{test['total_runs']} pass rate)\n"
                            analysis_prompt += "\n"
                        
                        # Failure Analysis
                        if failure_analysis.get('failure_categories'):
                            analysis_prompt += f"## Failure Categories:\n"
                            for category, count in failure_analysis['failure_categories'].items():
                                if count > 0:
                                    analysis_prompt += f"- {category}: {count} failures\n"
                            analysis_prompt += "\n"
                            
                            # Critical Issues
                            critical_issues = exec_summary['failure_insights'].get('critical_issues', [])
                            if critical_issues:
                                analysis_prompt += f"## Critical Issues:\n"
                                for issue in critical_issues:
                                    analysis_prompt += f"- {issue}\n"
                                analysis_prompt += "\n"
                        
                        # Historical Trends
                        if historical_comparison:
                            analysis_prompt += f"## Historical Trends (Last 30 Days):\n"
                            for metric, value in historical_comparison.items():
                                if metric.endswith('_change'):
                                    metric_name = metric.replace('_change', '').replace('_', ' ').title()
                                    analysis_prompt += f"- {metric_name}: {value:+.1f}% change\n"
                            analysis_prompt += "\n"
                        
                        # Performance Data
                        if duration_analytics:
                            analysis_prompt += f"## Performance Metrics:\n"
                            analysis_prompt += f"- Average test duration: {duration_analytics.get('avg_test_duration', 0):.1f}s\n"
                            analysis_prompt += f"- Median test duration: {duration_analytics.get('median_test_duration', 0):.1f}s\n"
                            slowest_tests = duration_analytics.get('slowest_tests', [])
                            if slowest_tests:
                                analysis_prompt += f"- Slowest test: {slowest_tests[0]['test_name']} ({slowest_tests[0]['avg_duration']:.1f}s)\n"
                            analysis_prompt += "\n"
                        
                        # Traditional data for compatibility
                        for launch in launches_for_charting_and_analysis:
                            analysis_prompt += f"- Launch: {launch['name']}, Pass Rate: {launch['passed']}/{launch['total']} ({launch['pass_rate']})\n"
                        
                        analysis_prompt += "\nBased on this comprehensive analysis, please provide insights on test quality, stability, performance, and recommendations for improvement. Focus on identifying trends, root causes, and actionable next steps."
                        
                        try:
                            llm_analysis_resp = client.chat(messages=[{"role": "user", "content": analysis_prompt}])
                            st.markdown("\n\n### 🤖 AI-Powered Analysis:\n" + llm_analysis_resp)
                            active_chat["messages"].append({"role": "assistant", "content": "\n\n### 🤖 AI-Powered Analysis:\n" + llm_analysis_resp})
                        except Exception as e:
                            st.markdown(f"\n\nError during LLM analysis: {e}")
                            active_chat["messages"].append({"role": "assistant", "content": f"\n\nError during LLM analysis: {e}"})


                # --- Slidev Presentation Generation ---
                    if st.session_state.enable_slidev:
                        slidev_output_dir = os.path.join(os.getcwd(), "slidev_presentations")
                        os.makedirs(slidev_output_dir, exist_ok=True)

                        # Generate Enhanced Slidev Markdown content
                        slidev_content = "---\ntheme: default\nclass: text-center\nhighlighter: shiki\nlineNumbers: false\ninfo: |\n  ## ReportPortal Enhanced Analysis\n  Comprehensive test quality and performance insights\ndrawings:\n  persist: false\ntransition: slide-left\ntitle: ReportPortal Analysis\n---\n\n"
                        slidev_content += "# 📊 ReportPortal Enhanced Analysis\n\n"
                        slidev_content += "Comprehensive Test Quality & Performance Report\n\n"
                        slidev_content += f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                        
                        # Executive Summary Slide
                        slidev_content += "---\n\n"
                        slidev_content += "# 📈 Executive Summary\n\n"
                        slidev_content += "<div class=\"grid grid-cols-2 gap-10 pt-4 -mb-6\">\n\n"
                        slidev_content += "<div>\n\n"
                        slidev_content += "## Key Metrics\n\n"
                        slidev_content += f"- **Total Launches**: {exec_summary['overview']['total_launches']}\n"
                        slidev_content += f"- **Total Tests**: {exec_summary['overview']['total_tests']:,}\n"
                        slidev_content += f"- **Overall Pass Rate**: {exec_summary['overview']['overall_pass_rate']:.1f}%\n"
                        slidev_content += f"- **Quality Score**: {exec_summary['overview']['quality_score']}/100\n\n"
                        slidev_content += "</div>\n\n"
                        slidev_content += "<div>\n\n"
                        slidev_content += "## Quality Indicators\n\n"
                        slidev_content += f"- **Flaky Tests**: {exec_summary['test_stability']['flaky_tests_detected']}\n"
                        slidev_content += f"- **Failure Patterns**: {exec_summary['failure_insights']['unique_failure_patterns']}\n"
                        slidev_content += f"- **Pass Rate Stability**: {exec_metrics.get('pass_rate_std', 0):.1f}% σ\n"
                        if historical_comparison.get('avg_pass_rate_change'):
                            change = historical_comparison['avg_pass_rate_change']
                            trend_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                            slidev_content += f"- **30-Day Trend**: {trend_emoji} {change:+.1f}%\n"
                        slidev_content += "\n</div>\n\n"
                        slidev_content += "</div>\n\n"

                        # Test Execution Metrics
                        slidev_content += "---\n\n"
                        slidev_content += "# 📊 Test Execution Metrics\n\n"
                        slidev_content += "<div class=\"grid grid-cols-2 gap-10 pt-4 -mb-6\">\n\n"
                        slidev_content += "<div>\n\n"
                        slidev_content += "## Volume Metrics\n\n"
                        slidev_content += f"- **Avg Tests/Launch**: {exec_metrics.get('avg_tests_per_launch', 0):.1f}\n"
                        slidev_content += f"- **Median Tests/Launch**: {exec_metrics.get('median_tests_per_launch', 0):.1f}\n"
                        slidev_content += f"- **Total Passed**: {exec_metrics.get('total_passed', 0):,}\n"
                        slidev_content += f"- **Total Failed**: {exec_metrics.get('total_failed', 0):,}\n"
                        slidev_content += f"- **Total Skipped**: {exec_metrics.get('total_skipped', 0):,}\n\n"
                        slidev_content += "</div>\n\n"
                        slidev_content += "<div>\n\n"
                        slidev_content += "## Quality Metrics\n\n"
                        slidev_content += f"- **Average Pass Rate**: {exec_metrics.get('avg_pass_rate', 0):.1f}%\n"
                        trend = exec_metrics.get('test_execution_trend', 0)
                        trend_direction = "📈 Increasing" if trend > 0 else "📉 Decreasing" if trend < 0 else "➡️ Stable"
                        slidev_content += f"- **Volume Trend**: {trend_direction}\n"
                        if duration_analytics:
                            slidev_content += f"- **Avg Duration**: {duration_analytics.get('avg_test_duration', 0):.1f}s\n"
                            slidev_content += f"- **Median Duration**: {duration_analytics.get('median_test_duration', 0):.1f}s\n"
                        slidev_content += "\n</div>\n\n"
                        slidev_content += "</div>\n\n"

                        # Flaky Tests Analysis
                        if flaky_tests:
                            slidev_content += "---\n\n"
                            slidev_content += "# ⚠️ Test Stability Analysis\n\n"
                            slidev_content += "## Top Flaky Tests\n\n"
                            for i, test in enumerate(flaky_tests[:5], 1):
                                slidev_content += f"### {i}. {test['test_name']}\n"
                                slidev_content += f"- **Flaky Score**: {test['flaky_score']:.1f}%\n"
                                slidev_content += f"- **Total Runs**: {test['total_runs']}\n"
                                slidev_content += f"- **Pass Rate**: {test['passed']}/{test['total_runs']} ({(test['passed']/test['total_runs']*100):.1f}%)\n\n"

                        # Failure Analysis
                        if failure_analysis.get('failure_categories'):
                            slidev_content += "---\n\n"
                            slidev_content += "# 🔍 Failure Pattern Analysis\n\n"
                            slidev_content += "<div class=\"grid grid-cols-2 gap-10 pt-4 -mb-6\">\n\n"
                            slidev_content += "<div>\n\n"
                            slidev_content += "## Failure Categories\n\n"
                            for category, count in failure_analysis['failure_categories'].items():
                                if count > 0:
                                    slidev_content += f"- **{category}**: {count}\n"
                            slidev_content += "\n</div>\n\n"
                            slidev_content += "<div>\n\n"
                            slidev_content += "## Top Patterns\n\n"
                            for pattern, count in failure_analysis.get('top_failure_patterns', [])[:5]:
                                slidev_content += f"- **{pattern}**: {count}x\n"
                            slidev_content += "\n</div>\n\n"
                            slidev_content += "</div>\n\n"
                            
                            # Critical Issues
                            critical_issues = exec_summary['failure_insights'].get('critical_issues', [])
                            if critical_issues:
                                slidev_content += "## 🚨 Critical Issues\n\n"
                                for issue in critical_issues:
                                    slidev_content += f"- {issue}\n"
                                slidev_content += "\n"

                        # Performance Analytics
                        if duration_analytics and duration_analytics.get('slowest_tests'):
                            slidev_content += "---\n\n"
                            slidev_content += "# ⏱️ Performance Analytics\n\n"
                            slidev_content += "<div class=\"grid grid-cols-2 gap-10 pt-4 -mb-6\">\n\n"
                            slidev_content += "<div>\n\n"
                            slidev_content += "## Duration Statistics\n\n"
                            slidev_content += f"- **Average**: {duration_analytics.get('avg_test_duration', 0):.1f}s\n"
                            slidev_content += f"- **Median**: {duration_analytics.get('median_test_duration', 0):.1f}s\n"
                            slidev_content += f"- **Min**: {duration_analytics.get('min_test_duration', 0):.1f}s\n"
                            slidev_content += f"- **Max**: {duration_analytics.get('max_test_duration', 0):.1f}s\n\n"
                            slidev_content += "</div>\n\n"
                            slidev_content += "<div>\n\n"
                            slidev_content += "## Slowest Tests\n\n"
                            for test in duration_analytics['slowest_tests'][:5]:
                                slidev_content += f"- **{test['test_name']}**: {test['avg_duration']:.1f}s\n"
                            slidev_content += "\n</div>\n\n"
                            slidev_content += "</div>\n\n"

                        # Historical Trends
                        if historical_comparison:
                            slidev_content += "---\n\n"
                            slidev_content += "# 📈 Historical Trends (30 Days)\n\n"
                            slidev_content += "## Performance Changes\n\n"
                            for metric, value in historical_comparison.items():
                                if metric.endswith('_change'):
                                    metric_name = metric.replace('_change', '').replace('_', ' ').title()
                                    trend_emoji = "📈" if value > 0 else "📉" if value < 0 else "➡️"
                                    slidev_content += f"- **{metric_name}**: {trend_emoji} {value:+.1f}%\n"
                            slidev_content += "\n"

                        # Traditional charts
                        slidev_content += "---\n\n"
                        slidev_content += "# 📈 Pass Rate Trend\n\n"
                        slidev_content += f"![Pass Rate Trend](/pass_rate_trend.png)\n\n"

                        slidev_content += "---\n\n"
                        slidev_content += "# 🏗️ Platform Test Coverage\n\n"
                        slidev_content += f"![OCP Platform Test Coverage](/ocp_coverage.png)\n\n"

                        # Launch Details
                        slidev_content += "---\n\n"
                        slidev_content += "# 🚀 Launch Details\n\n"
                        if launches_for_charting_and_analysis:
                            slidev_content += "| Launch Name | Pass Rate | Total Tests |\n"
                            slidev_content += "|---|---|---|\n"
                            for launch in launches_for_charting_and_analysis:
                                slidev_content += f"| {launch['name']} | {launch['pass_rate']} | {launch['total']} |\n"
                        else:
                            slidev_content += "No launches found in ReportPortal with the given filter.\n"

                        # Traditional failure analysis (simplified for slides)
                        if all_failed_test_names:
                            slidev_content += "---\n\n"
                            slidev_content += "# ❌ Top Failing Tests\n\n"
                            top_failed_tests = Counter(all_failed_test_names).most_common(5)
                            for i, (test_name, count) in enumerate(top_failed_tests, 1):
                                slidev_content += f"{i}. **{test_name}** - {count} failures\n"

                        if all_skipped_test_names:
                            slidev_content += "---\n\n"
                            slidev_content += "# ⏭️ Most Skipped Tests\n\n"
                            top_skipped_tests = Counter(all_skipped_test_names).most_common(5)
                            for i, (test_name, count) in enumerate(top_skipped_tests, 1):
                                slidev_content += f"{i}. **{test_name}** - {count} skips\n"

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

                # Prepare messages for LLM, including uploaded file content if available.
                messages_for_llm = active_chat["messages"]
                if 'uploaded_file_content' in st.session_state and st.session_state['uploaded_file_content'] is not None:
                    file_name = st.session_state.get('uploaded_file_name', 'uploaded_file')
                    file_content = st.session_state['uploaded_file_content']
                    
                    # Prepend file content to the user's prompt for LLM context.
                    # For text files, include content directly. For binary, just mention it.
                    if isinstance(file_content, str): # Assuming text content
                        file_message = f"The user has provided a file named '{file_name}' with the following content:\n\n```\n{file_content}\n```\n\n"
                    else: # Binary content (image, pdf, etc.)
                        # We don't have uploaded_file.type directly here, so we'll use a generic message.
                        file_message = f"The user has provided a file named '{file_name}'. "\
                                       f"Its content is not directly readable as text, but it is available for context if needed.\n\n"
                    
                    # Add the file content as a system message or prepend to the user's last message.
                    # For simplicity, let's prepend to the current user prompt for LLM processing.
                    # A more sophisticated approach might involve a separate message role or tool for file content.
                    # For now, we'll modify the last user message or add a new one if the last is not user.
                    
                    # Find the last user message to prepend the file content
                    last_message_index = -1
                    for i, msg in enumerate(messages_for_llm):
                        if msg["role"] == "user":
                            last_message_index = i
                    
                    if last_message_index != -1:
                        messages_for_llm[last_message_index]["content"] = file_message + messages_for_llm[last_message_index]["content"]
                    else:
                        # If for some reason there's no user message yet (e.g., first interaction after upload),
                        # add it as a new user message before the current prompt.
                        messages_for_llm.append({"role": "user", "content": file_message})
                    
                    # Clear the uploaded file content from session state after it's been processed by the LLM
                    st.session_state['uploaded_file_content'] = None
                    st.session_state['uploaded_file_name'] = None

                if not jenkins_handled and not rp_handled and not jira_command_handled_successfully:
                    try:
                        if client:
                            if provider == "ollama":
                                resp = client.chat(model=ollama_model, messages=messages_for_llm)
                            else:  # For Models.corp
                                resp = client.chat(messages_for_llm)
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