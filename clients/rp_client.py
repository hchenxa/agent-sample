import os
import requests
from requests import Request, Session
import urllib.parse
import logging

class ReportPortalManager:
    def __init__(self, endpoint, uuid, project, verify_ssl=True):
        self.endpoint = endpoint
        self.uuid = uuid
        self.project = project
        self.verify_ssl = verify_ssl
        self.session = Session()

    def get_launches(self, attribute_filter=None):
        if self.endpoint and self.project and self.uuid:
            try:
                headers = {
                    "Authorization": f"Bearer {self.uuid}"
                }
                url = f"{self.endpoint}/api/v1/{self.project}/launch?page.sort=startTime%2Cdesc"
                print(f"DEBUG: attribute is : {attribute_filter}")
                if attribute_filter:
                    logging.debug(f"attribute is : {attribute_filter}")
                    url += f"&filter.has.compositeAttribute={attribute_filter}"
                print(f"DEBUG: url is: {url}")
                req = Request('GET', url, headers=headers)
                prepped = self.session.prepare_request(req)
                response = self.session.send(prepped, verify=self.verify_ssl)
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
