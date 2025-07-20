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
                print(f"DEBUG: Raw launches_data from ReportPortal: {launches_data}")
                
                # ReportPortal API for launches usually returns a 'content' field with a list of launches
                if 'content' in launches_data and isinstance(launches_data['content'], list):
                    # Extract relevant information: name, id, and construct a UI URL
                    # The UI URL construction might vary based on ReportPortal setup.
                    # A common pattern is {endpoint}/ui/#{projectName}/launches/all/{launchId}
                    formatted_launches = []
                    for launch in launches_data['content']:
                        print(f"DEBUG: Raw launch data before formatting: {launch}")
                        launch_id = launch.get('id')
                        launch_name = launch.get('name')
                        launch_url = f"{self.endpoint}/ui/#{self.project}/launches/all/{launch_id}" if launch_id else "N/A"
                        
                        pass_rate = "N/A"
                        total = 0
                        passed = 0
                        failed = 0
                        skipped = 0
                        defects = {}

                        if 'statistics' in launch:
                            if 'executions' in launch['statistics']:
                                executions = launch['statistics']['executions']
                                total = executions.get('total', 0)
                                passed = executions.get('passed', 0)
                                failed = executions.get('failed', 0)
                                skipped = executions.get('skipped', 0)
                                if total > 0:
                                    pass_rate = f"{(passed / total * 100):.2f}%"
                            if 'defects' in launch['statistics']:
                                defects = launch['statistics']['defects']

                        launch_start_time = launch.get('startTime')
                        launch_attributes = launch.get('attributes', [])
                        formatted_launches.append({
                            'name': launch_name,
                            'id': launch_id, # Add launch_id here
                            'url': launch_url,
                            'pass_rate': pass_rate,
                            'total': total,
                            'passed': passed,
                            'failed': failed,
                            'skipped': skipped,
                            'defects': defects,
                            'startTime': launch_start_time,
                            'attributes': launch_attributes
                        })
                    return formatted_launches
                else:
                    return "Unexpected response format from ReportPortal API."
            except requests.exceptions.RequestException as e:
                return f"Error connecting to ReportPortal API: {e}"
            except Exception as e:
                return f"Error processing ReportPortal launches: {e}"
        return "ReportPortal configuration incomplete (endpoint, UUID, or project missing)."

    def get_test_items_for_launch(self, launch_id, item_filter=None):
        if self.endpoint and self.project and self.uuid and launch_id:
            try:
                headers = {
                    "Authorization": f"Bearer {self.uuid}"
                }
                # ReportPortal API to get test items for a specific launch
                # Assuming a common endpoint structure, adjust if different
                url = f"{self.endpoint}/api/v1/{self.project}/item?filter.eq.launchId={launch_id}&page.size=1000"
                if item_filter:
                    url += f"&{item_filter}"
                
                req = Request('GET', url, headers=headers)
                prepped = self.session.prepare_request(req)
                response = self.session.send(prepped, verify=self.verify_ssl)
                response.raise_for_status()
                test_items_data = response.json()

                if 'content' in test_items_data and isinstance(test_items_data['content'], list):
                    formatted_test_items = []
                    for item in test_items_data['content']:
                        formatted_test_items.append({
                            'name': item.get('name'),
                            'status': item.get('status'),
                            'type': item.get('type'),
                            'issue_type': item.get('issue', {}).get('issueType', 'N/A')
                        })
                    return formatted_test_items
                else:
                    return "Unexpected response format for test items from ReportPortal API."
            except requests.exceptions.RequestException as e:
                return f"Error connecting to ReportPortal API for test items: {e}"
            except Exception as e:
                return f"Error processing ReportPortal test items: {e}"
        return "ReportPortal configuration incomplete (endpoint, UUID, project, or launch_id missing)."
