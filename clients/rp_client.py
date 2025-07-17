import os
from reportportal_client import RPClient
from reportportal_client.helpers import timestamp

class ReportPortalManager:
    def __init__(self, endpoint, uuid, project, verify_ssl=True):
        self.endpoint = endpoint
        self.uuid = uuid
        self.project = project
        self.verify_ssl = verify_ssl
        self.client = None

    def start_service(self):
        if not self.client:
            self.client = RPClient(
                endpoint=self.endpoint,
                project=self.project,
                api_key=self.uuid
            )
            self.client.start()

    def start_launch(self, launch_name):
        if self.client:
            self.client.start_launch(
                name=launch_name,
                start_time=timestamp()
            )

    def get_launches(self, attribute_filter=None):
        import requests
        if self.endpoint and self.project and self.uuid:
            try:
                headers = {
                    "Authorization": f"Bearer {self.uuid}"
                }
                # Assuming the API endpoint for launches is /api/v1/{projectName}/launch
                # The documentation mentioned /api/v1/:projectName/launch/names, but a more general launch endpoint might be needed
                # Let's try a common one and adjust if necessary.
                # A more robust solution would involve checking ReportPortal API documentation for the exact endpoint.
                url = f"{self.endpoint}/api/v1/{self.project}/launch"
                params = {}
                if attribute_filter:
                    for key, value in attribute_filter.items():
                        params[f"attribute.{key}"] = value
                
                print(f"DEBUG: ReportPortal API Request URL: {url}")
                print(f"DEBUG: ReportPortal API Request Params: {params}")
                response = requests.get(url, headers=headers, verify=self.verify_ssl, params=params)
                response.raise_for_status() # Raise an exception for HTTP errors
                launches_data = response.json()
                
                # ReportPortal API for launches usually returns a 'content' field with a list of launches
                if 'content' in launches_data and isinstance(launches_data['content'], list):
                    # Extract relevant information: name, id, and construct a UI URL
                    # The UI URL construction might vary based on ReportPortal setup.
                    # A common pattern is {endpoint}/ui/#{projectName}/launches/all/{launchId}
                    formatted_launches = []
                    for launch in launches_data['content']:
                        launch_id = launch.get('id')
                        launch_name = launch.get('name')
                        launch_url = f"{self.endpoint}/ui/#{self.project}/launches/all/{launch_id}" if launch_id else "N/A"
                        
                        pass_rate = "N/A"
                        if 'statistics' in launch and 'executions' in launch['statistics']:
                            executions = launch['statistics']['executions']
                            total = executions.get('total', 0)
                            passed = executions.get('passed', 0)
                            if total > 0:
                                pass_rate = f"{(passed / total * 100):.2f}%"

                        formatted_launches.append({
                            'name': launch_name,
                            'url': launch_url,
                            'pass_rate': pass_rate
                        })
                    return formatted_launches
                else:
                    return "Unexpected response format from ReportPortal API."
            except requests.exceptions.RequestException as e:
                return f"Error connecting to ReportPortal API: {e}"
            except Exception as e:
                return f"Error processing ReportPortal launches: {e}"
        return "ReportPortal configuration incomplete (endpoint, UUID, or project missing)."

    def finish_launch(self):
        if self.client:
            self.client.finish_launch(
                end_time=timestamp()
            )
            self.client.terminate()

    def terminate_service(self):
        if self.client:
            self.client.terminate()