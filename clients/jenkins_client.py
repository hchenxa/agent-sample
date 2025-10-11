import jenkins
from datetime import datetime


class JenkinsClient:
    def __init__(self, url, username, password):
        self.server = jenkins.Jenkins(
            url, username=username, password=password)
        self.server._session.verify = False

    def get_all_jobs(self, filter_keyword: str = None):
        """
        Retrieves a list of all jobs on the Jenkins server.
        """
        try:
            jobs = self.server.get_jobs()
            if filter_keyword:
                jobs = [job for job in jobs if filter_keyword.lower()
                        in job['name'].lower()]
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
            return views  # Return full view objects
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
                if '_class' in action and 'parameters' in action and "ParametersAction" in action[
                        '_class']:
                    for param in action['parameters']:
                        if 'name' in param and 'value' in param:
                            parameters[param['name']] = param['value']
                    break
            return parameters
        except jenkins.JenkinsException as e:
            return f"Error fetching parameters for build {build_number} of job '{job_name}': {e}"

    def get_server_info(self):
        """
        Retrieves Jenkins server information including version,
        plugins, and system info.
        """
        try:
            version = self.server.get_version()
            info = self.server.get_whoami()
            plugins = self.server.get_plugins_info()

            return {
                'version': version,
                'whoami': info,
                'plugin_count': len(plugins),
                'plugins': plugins
            }
        except jenkins.JenkinsException as e:
            return f"Error fetching server info: {e}"

    def get_job_usage_analytics(self, days_threshold=30):
        """
        Analyzes job usage patterns to identify frequently used jobs
        and potentially deprecated jobs.

        Args:
            days_threshold (int): Number of days to consider
                a job as inactive

        Returns:
            dict: Analytics data including active jobs, inactive jobs,
                and usage statistics
        """
        try:
            jobs = self.server.get_jobs()
            current_time = datetime.now()
            analytics = {
                'total_jobs': 0,  # Will be updated as we count actual jobs
                'active_jobs': [],
                'inactive_jobs': [],
                'highly_active_jobs': [],
                'moderately_active_jobs': [],
                'rarely_active_jobs': [],
                'never_built_jobs': []
            }

            for job in jobs:
                job_name = job['name']
                try:
                    job_info = self.server.get_job_info(job_name)

                    # Skip folders - only process actual jobs
                    job_class = job_info.get('_class', '')
                    if 'folder' in job_class.lower():
                        print(
                            f"DEBUG: Skipping folder: {job_name} "
                            f"(class: {job_class})")
                        continue

                    last_build = job_info.get('lastBuild')

                    job_data = {
                        'name': job_name,
                        'url': job_info.get('url'),
                        'color': job_info.get('color', 'grey'),
                        'buildable': job_info.get('buildable', False)
                    }

                    # Increment total jobs count (only for actual jobs)
                    analytics['total_jobs'] += 1

                    if not last_build:
                        # Job never built
                        job_data['status'] = 'Never Built'
                        job_data['days_since_last_build'] = None
                        job_data['total_builds'] = 0
                        analytics['never_built_jobs'].append(job_data)
                        analytics['inactive_jobs'].append(job_data)
                    else:
                        # Get last build info
                        last_build_number = last_build.get('number', 0)
                        first_build = job_info.get('firstBuild', {})
                        first_build_number = first_build.get('number', 0)

                        total_builds = last_build_number - \
                            first_build_number + 1

                        # Get timestamp
                        last_build_info = self.server.get_build_info(
                            job_name, last_build_number)
                        timestamp_ms = last_build_info.get('timestamp', 0)
                        last_build_time = datetime.fromtimestamp(
                            timestamp_ms / 1000.0)
                        days_since = (
                            current_time - last_build_time).days

                        job_data['last_build_number'] = last_build_number
                        job_data['total_builds'] = total_builds
                        job_data['days_since_last_build'] = days_since
                        job_data['last_build_time'] = \
                            last_build_time.strftime('%Y-%m-%d %H:%M:%S')

                        # Categorize by activity
                        if days_since > days_threshold:
                            job_data['status'] = 'Inactive'
                            analytics['inactive_jobs'].append(job_data)
                        else:
                            job_data['status'] = 'Active'
                            analytics['active_jobs'].append(job_data)

                            # Further categorize active jobs by build frequency
                            if total_builds > 100 or days_since < 7:
                                analytics['highly_active_jobs'].append(
                                    job_data)
                            elif total_builds > 20 or days_since < 14:
                                analytics['moderately_active_jobs'].append(
                                    job_data)
                            else:
                                analytics['rarely_active_jobs'].append(
                                    job_data)

                except jenkins.JenkinsException as e:
                    print(f"Error analyzing job {job_name}: {e}")
                    continue

            # Sort jobs by days since last build
            analytics['inactive_jobs'].sort(
                key=lambda x: x.get('days_since_last_build')
                if x.get('days_since_last_build') is not None else 999999,
                reverse=True
            )
            analytics['active_jobs'].sort(
                key=lambda x: x.get('days_since_last_build', 0))

            return analytics

        except jenkins.JenkinsException as e:
            return f"Error fetching job usage analytics: {e}"

    def get_jobs_for_ai_categorization(self):
        """
        Retrieves job information formatted for AI categorization.
        Returns job names, descriptions, and recent build info.
        """
        try:
            jobs = self.server.get_jobs()
            jobs_data = []

            for job in jobs:
                job_name = job['name']
                try:
                    job_info = self.server.get_job_info(job_name)

                    # Skip folders - only process actual jobs
                    job_class = job_info.get('_class', '')
                    if 'folder' in job_class.lower():
                        continue

                    job_data = {
                        'name': job_name,
                        'description': job_info.get('description', ''),
                        'url': job_info.get('url', ''),
                        'buildable': job_info.get('buildable', False),
                        'color': job_info.get('color', 'grey')
                    }

                    # Get last successful build info if available
                    last_success = job_info.get('lastSuccessfulBuild')
                    if last_success:
                        job_data['has_successful_builds'] = True
                        job_data['last_success_number'] = \
                            last_success.get('number')
                    else:
                        job_data['has_successful_builds'] = False

                    jobs_data.append(job_data)

                except jenkins.JenkinsException as e:
                    print(f"Error fetching info for job {job_name}: {e}")
                    continue

            return jobs_data

        except jenkins.JenkinsException as e:
            return f"Error fetching jobs for categorization: {e}"


if __name__ == '__main__':
    # Example Usage: Replace with your Jenkins details and uncomment to run.
    JENKINS_URL = 'http://localhost:8080'
    JENKINS_USERNAME = 'your_username'
    JENKINS_API_TOKEN = 'your_api_token'

    try:
        client = JenkinsClient(
            JENKINS_URL,
            JENKINS_USERNAME,
            JENKINS_API_TOKEN)

        print("\n--- All Jenkins Jobs ---")
        jobs = client.get_all_jobs()
        print(jobs)

        # # Example: Get info for a specific job
        # job_name = 'your_job_name'
        # info = client.get_job_info(job_name)
        # print(f"\n--- Info for job '{job_name}' ---\n{info}")

        # # Example: Trigger a job
        # job_to_trigger = 'your_job_name'
        # trigger_result = client.build_job(job_to_trigger)
        # print(f"\n--- Triggering job '{job_to_trigger}' ---\n{trigger_result}")

        # # Example: Trigger a job with parameters
        # job_with_params = 'your_parameterized_job_name'
        # params = {'PARAM1': 'value1', 'PARAM2': 'value2'}
        # trigger_result_params = client.build_job(job_with_params, params)
        # print(
        #     f"\n--- Triggering job '{job_with_params}' "
        #     f"with parameters ---\n{trigger_result_params}"
        # )

    except Exception as e:
        print(f"An error occurred during Jenkins client example usage: {e}")
