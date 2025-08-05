import os
import requests
from requests import Request, Session
import urllib.parse
import logging

class ReportPortalManager:
    """Manages interactions with the ReportPortal API to retrieve launch and test item data."""
    def __init__(self, endpoint, uuid, project, verify_ssl=True):
        """
        Initializes the ReportPortalManager.

        Args:
            endpoint (str): The ReportPortal API endpoint URL.
            uuid (str): The ReportPortal API UUID (personal access token).
            project (str): The ReportPortal project name.
            verify_ssl (bool, optional): Whether to verify SSL certificates. Defaults to True.
        """
        self.endpoint = endpoint
        self.uuid = uuid
        self.project = project
        self.verify_ssl = verify_ssl
        self.session = Session()

    def get_launches(self, attribute_filter=None):
        """
        Retrieves a list of launches from ReportPortal, optionally filtered by attributes.

        Args:
            attribute_filter (str, optional): A comma-separated string of attribute filters (e.g., "component:foo,release:bar").

        Returns:
            list: A list of dictionaries, each representing a formatted launch, or an error message string.
        """
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
                
                # ReportPortal API for launches usually returns a 'content' field with a list of launches.
                if 'content' in launches_data and isinstance(launches_data['content'], list):
                    # Extract relevant information (name, id, URL, pass rate, statistics) and format it.
                    formatted_launches = []
                    for launch in launches_data['content']:
                        print(f"DEBUG: Raw launch data before formatting: {launch}")
                        launch_id = launch.get('id')
                        launch_name = launch.get('name')
                        # Construct the UI URL based on common ReportPortal patterns.
                        launch_url = f"{self.endpoint}/ui/#{self.project}/launches/all/{launch_id}" if launch_id else "N/A"
                        
                        pass_rate = "0.00%" # Initialize pass rate as a string.
                        total = 0
                        passed = 0
                        failed = 0
                        skipped = 0
                        defects = {}

                        if 'statistics' in launch and 'executions' in launch['statistics']:
                            executions = launch['statistics']['executions']
                            total = executions.get('total', 0)
                            passed = executions.get('passed', 0)
                            failed = executions.get('failed', 0)
                            skipped = executions.get('skipped', 0)
                            # Calculate pass rate based on passed and failed tests.
                            total_for_pass_rate = passed + failed
                            if total_for_pass_rate > 0:
                                pass_rate = f"{(passed / total_for_pass_rate * 100):.2f}%"
                        if 'statistics' in launch and 'defects' in launch['statistics']:
                            defects = launch['statistics']['defects']

                        launch_start_time = launch.get('startTime')
                        launch_attributes = launch.get('attributes', [])
                        formatted_launches.append({
                            'name': launch_name,
                            'id': launch_id, 
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
        """
        Retrieves test items for a specific ReportPortal launch, optionally filtered.

        Args:
            launch_id (int): The ID of the launch to retrieve test items from.
            item_filter (str, optional): A filter string for test items (e.g., "filter.eq.status=FAILED").

        Returns:
            list: A list of dictionaries, each representing a formatted test item, or an error message string.
        """
        if self.endpoint and self.project and self.uuid and launch_id:
            try:
                headers = {
                    "Authorization": f"Bearer {self.uuid}"
                }
                # Construct the URL to get test items for a specific launch.
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
