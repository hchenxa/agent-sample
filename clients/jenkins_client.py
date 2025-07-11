import jenkins

class JenkinsClient:
    def __init__(self, url, username, password):
        self.server = jenkins.Jenkins(url, username=username, password=password)
        self.server._session.verify = False

    def get_all_jobs(self, filter_keyword: str = None):
        """
        Retrieves a list of all jobs on the Jenkins server.
        """
        try:
            jobs = self.server.get_jobs()
            if filter_keyword:
                jobs = [job for job in jobs if filter_keyword.lower() in job['name'].lower()]
            return [job['name'] for job in jobs]
        except jenkins.JenkinsException as e:
            return f"Error connecting to Jenkins or fetching jobs: {e}"

    def get_job_info(self, job_name):
        """
        Retrieves detailed information about a specific Jenkins job.
        """
        try:
            info = self.server.get_job_info(job_name)
            return info
        except jenkins.JenkinsException as e:
            return f"Error fetching info for job '{job_name}': {e}"

    def build_job(self, job_name, parameters=None):
        """
        Triggers a build for a specific Jenkins job, optionally with parameters.
        """
        try:
            if parameters:
                self.server.build_job(job_name, parameters)
            else:
                self.server.build_job(job_name)
            return f"Job '{job_name}' triggered successfully."
        except jenkins.JenkinsException as e:
            return f"Error triggering job '{job_name}': {e}"

    def get_all_views(self):
        """
        Retrieves a list of all views on the Jenkins server.
        """
        try:
            views = self.server.get_views()
            return views # Return full view objects
        except jenkins.JenkinsException as e:
            return f"Error connecting to Jenkins or fetching views: {e}"

    def get_job_status_and_url(self, job_name):
        """
        Retrieves the status and URL for a specific Jenkins job.
        """
        try:
            info = self.server.get_job_info(job_name)
            raw_color = info.get('color', 'N/A')
            
            status_map = {
                "red": "🔴 Failed",
                "blue": "🟢 Success",
                "yellow": "🟡 Unstable",
                "aborted": "⚫ Aborted",
                "notbuilt": "⚪ Not Built",
                "disabled": "⚪ Disabled",
                "grey": "⚪ Not Run",
                "red_anime": "🔄 Building (Failed)",
                "blue_anime": "🔄 Building (Success)",
                "yellow_anime": "🔄 Building (Unstable)",
                "aborted_anime": "🔄 Building (Aborted)",
                "grey_anime": "🔄 Building (Not Run)",
            }
            
            status = status_map.get(raw_color, f"❓ {raw_color}")
            url = info.get('url', 'N/A')
            return {'name': job_name, 'status': status, 'url': url}
        except jenkins.JenkinsException as e:
            return f"Error fetching status/URL for job '{job_name}': {e}"

    def get_view_job_count(self, view_name):
        """
        Retrieves the number of jobs in a specific Jenkins view.
        """
        try:
            jobs_in_view = self.server.get_jobs(view_name=view_name)
            return len(jobs_in_view)
        except jenkins.JenkinsException as e:
            return f"Error fetching job count for view '{view_name}': {e}"

    def get_build_parameters(self, job_name: str, build_number: int):
        """
        Retrieves parameters used for a specific build of a Jenkins job.
        """
        try:
            build_info = self.server.get_build_info(job_name, build_number)
            parameters = {}
            for action in build_info.get('actions', []):
                if '_class' in action and 'parameters' in action and "ParametersAction" in action['_class']:
                    for param in action['parameters']:
                        if 'name' in param and 'value' in param:
                            parameters[param['name']] = param['value']
                    break
            return parameters
        except jenkins.JenkinsException as e:
            return f"Error fetching parameters for build {build_number} of job '{job_name}': {e}"

if __name__ == '__main__':
    # Example Usage (replace with your Jenkins details)
    JENKINS_URL = 'http://localhost:8080'
    JENKINS_USERNAME = 'your_username'
    JENKINS_API_TOKEN = 'your_api_token'

    try:
        client = JenkinsClient(JENKINS_URL, JENKINS_USERNAME, JENKINS_API_TOKEN)

        print("\n--- All Jenkins Jobs ---")
        jobs = client.get_all_jobs()
        print(jobs)

        # Example: Get info for a specific job
        # job_name = 'your_job_name'
        # print(f"\n--- Info for job '{job_name}' ---")
        # info = client.get_job_info(job_name)
        # print(info)

        # Example: Trigger a job
        # job_to_trigger = 'your_job_name'
        # print(f"\n--- Triggering job '{job_to_trigger}' ---")
        # trigger_result = client.build_job(job_to_trigger)
        # print(trigger_result)

        # Example: Trigger a job with parameters
        # job_with_params = 'your_parameterized_job_name'
        # params = {'PARAM1': 'value1', 'PARAM2': 'value2'}
        # print(f"\n--- Triggering job '{job_with_params}' with parameters ---")
        # trigger_result_params = client.build_job(job_with_params, params)
        # print(trigger_result_params)

    except Exception as e:
        print(f"An error occurred during Jenkins client example usage: {e}")
