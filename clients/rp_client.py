import os
from reportportal_client import RPClient
from reportportal_client.helpers import timestamp

class ReportPortalManager:
    def __init__(self, endpoint, uuid, project):
        self.endpoint = endpoint
        self.uuid = uuid
        self.project = project
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

    def get_launches(self):
        if self.client:
            try:
                launches = self.client.get_launch_ui_urls()
                return launches
            except Exception as e:
                return f"Error getting launches: {e}"
        return "ReportPortal client not initialized."

    def finish_launch(self):
        if self.client:
            self.client.finish_launch(
                end_time=timestamp()
            )
            self.client.terminate()

    def terminate_service(self):
        if self.client:
            self.client.terminate()