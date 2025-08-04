import os
from jira import JIRA, JIRAError

class JiraClient:
    def __init__(self, url, api_token, verify_ssl=True):
        self.url = url
        self.api_token = api_token
        self.verify_ssl = verify_ssl
        self.jira = None

        try:
            jira_options = {'server': self.url, 'verify': self.verify_ssl}
            self.jira = JIRA(options=jira_options, token_auth=self.api_token)
            # Perform a simple API call to verify the connection is truly alive
            self.jira.myself()
        except JIRAError as e:
            print(f"DEBUG: JIRAError details: {e}")
            raise ConnectionError(f"Failed to connect to Jira: {e.text}") from e
        except Exception as e:
            print(f"DEBUG: Unexpected exception type: {type(e)}, details: {e}")
            raise ConnectionError(f"An unexpected error occurred during Jira client initialization or verification: {e}") from e

    def query_issues(self, jql_query, project_key=None, components=None, max_results=50):
        """
        Queries Jira issues using JQL (Jira Query Language), with optional project and component filters.

        Args:
            jql_query (str): The JQL query string.
            project_key (str, optional): The key of the Jira project to filter by.
            components (list, optional): A list of component names to filter by.
            max_results (int): Maximum number of issues to retrieve.

        Returns:
            list: A list of dictionaries, each representing an issue, or an error message.
        """
        if not self.jira:
            return "Jira connection not established."

        full_jql_query = jql_query
        if project_key and 'project' not in jql_query.lower():
            full_jql_query = f"project = \"{project_key}\" AND {full_jql_query}"
        
        if components:
            component_jql = " OR ".join([f'component = "{c}"' for c in components])
            full_jql_query = f"({full_jql_query}) AND ({component_jql})"

        print(f"DEBUG: Executing Jira query with JQL: {full_jql_query}, Max Results: {max_results}")
        try:
            issues = self.jira.search_issues(full_jql_query, maxResults=max_results)
            print(f"DEBUG: Jira search_issues returned {len(issues)} issues.")
            result = []
            for issue in issues:
                issue_data = {
                    'key': issue.key,
                    'summary': issue.fields.summary,
                    'status': issue.fields.status.name,
                    'assignee': issue.fields.assignee.displayName if issue.fields.assignee else 'Unassigned',
                    'reporter': issue.fields.reporter.displayName if issue.fields.reporter else 'Unknown',
                    'created': issue.fields.created,
                    'updated': issue.fields.updated,
                    'priority': issue.fields.priority.name if issue.fields.priority else 'N/A',
                    'issue_type': issue.fields.issuetype.name,
                    'url': f"{self.url}/browse/{issue.key}"
                }
                result.append(issue_data)
            return result
        except JIRAError as e:
            return f"Error querying Jira: {e.text}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

    def get_current_user(self):
        """
        Retrieves the details of the currently authenticated user.

        Returns:
            dict: A dictionary containing user details, or an error message.
        """
        if not self.jira:
            return "Jira connection not established."
        
        try:
            user = self.jira.myself()
            return {
                'name': user.get('name', 'N/A'),
                'displayName': user.get('displayName', 'N/A'),
                'emailAddress': user.get('emailAddress', 'N/A'),
                'timeZone': user.get('timeZone', 'N/A')
            }
        except JIRAError as e:
            return f"Error retrieving user information: {e.text}"
        except Exception as e:
            return f"An unexpected error occurred: {e}"

if __name__ == '__main__':
    # Example Usage:
    # Set these environment variables or replace with your actual Jira credentials
    JIRA_URL = os.getenv("JIRA_URL", "YOUR_JIRA_URL")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "YOUR_JIRA_API_TOKEN")

    if JIRA_URL == "YOUR_JIRA_URL" or JIRA_API_TOKEN == "YOUR_JIRA_API_TOKEN":
        print("Please set JIRA_URL and JIRA_API_TOKEN environment variables or replace placeholders in jira_client.py")
    else:
        print(f"Attempting to connect to Jira at: {JIRA_URL}")
        # Example of disabling SSL verification:
        client = JiraClient(JIRA_URL, JIRA_API_TOKEN, verify_ssl=False)

        if client.jira:
            print("\n--- Example: Querying 5 issues from a project (e.g., 'YOURPROJECT') ---")
            # Replace 'YOURPROJECT' with an actual project key in your Jira instance
            project_to_query = "YOURPROJECT"
            jql = "ORDER BY created DESC"
            issues = client.query_issues(jql, project_key=project_to_query, max_results=5)
            if isinstance(issues, list):
                for issue in issues:
                    print(f"  Key: {issue['key']}, Summary: {issue['summary']}, Status: {issue['status']}")
            else:
                print(f"Error: {issues}")

            print("\n--- Example: Querying issues assigned to a specific user (no project filter) ---")
            # Replace 'your_username' with an actual Jira username
            jql_assigned = "assignee = currentUser() AND status in ('To Do', 'In Progress') ORDER BY priority DESC"
            assigned_issues = client.query_issues(jql_assigned, max_results=3)
            if isinstance(assigned_issues, list):
                print(f"Found {len(assigned_issues)} issues assigned to current user:")
                for issue in assigned_issues:
                    print(f"  Key: {issue['key']}, Summary: {issue['summary']}, Status: {issue['status']}")
            else:
                print(f"Error: {assigned_issues}")
        else:
            print("Failed to establish Jira connection. Check your credentials and URL.")