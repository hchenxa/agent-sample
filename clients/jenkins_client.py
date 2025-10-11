import jenkins
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


class JenkinsClient:
    def __init__(self, url, username, password):
        self.server = jenkins.Jenkins(
            url, username=username, password=password)
        self.server._session.verify = False
        self._analytics_cache = None
        self._cache_timestamp = None
        self._cache_ttl = 300  # Cache for 5 minutes

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

    def get_all_jobs_with_status(self, filter_keyword=None):
        """
        Retrieves all jobs with their status and URL in parallel.
        Much faster than calling get_job_status_and_url() for each job.

        Args:
            filter_keyword (str): Optional keyword to filter jobs

        Returns:
            list: List of dicts with job name, status, and URL
        """
        try:
            # Get all jobs first
            jobs = self.server.get_jobs()

            if filter_keyword:
                jobs = [
                    job for job in jobs
                    if filter_keyword.lower() in job['name'].lower()
                ]

            job_names = [job['name'] for job in jobs]

            if not job_names:
                return []

            print(f"DEBUG: Fetching status for {len(job_names)} jobs in parallel...")

            # Define status map
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

            def fetch_job_status(job_name):
                """Helper to fetch single job status"""
                try:
                    info = self.server.get_job_info(job_name)
                    raw_color = info.get('color', 'N/A')
                    status = status_map.get(raw_color, f"❓ {raw_color}")
                    url = info.get('url', 'N/A')
                    return {'name': job_name, 'status': status, 'url': url}
                except Exception as e:
                    return {
                        'name': job_name,
                        'status': f"❌ Error",
                        'url': 'N/A'
                    }

            # Fetch all job statuses in parallel
            results = []
            with ThreadPoolExecutor(max_workers=20) as executor:
                future_to_job = {
                    executor.submit(fetch_job_status, job_name): job_name
                    for job_name in job_names
                }

                for future in as_completed(future_to_job):
                    results.append(future.result())

            # Sort by job name for consistent output
            results.sort(key=lambda x: x['name'])

            print(f"DEBUG: Fetched status for {len(results)} jobs")
            return results

        except jenkins.JenkinsException as e:
            return f"Error fetching jobs with status: {e}"

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

    def _process_single_job(self, job_name, current_time, days_threshold):
        """
        Helper method to process a single job's analytics.
        Used for parallel processing.
        """
        try:
            job_info = self.server.get_job_info(job_name)

            # Skip folders - only process actual jobs
            job_class = job_info.get('_class', '')
            if 'folder' in job_class.lower():
                return None

            last_build = job_info.get('lastBuild')

            job_data = {
                'name': job_name,
                'url': job_info.get('url'),
                'color': job_info.get('color', 'grey'),
                'buildable': job_info.get('buildable', False)
            }

            if not last_build:
                # Job never built
                job_data['status'] = 'Never Built'
                job_data['days_since_last_build'] = None
                job_data['total_builds'] = 0
                job_data['category'] = 'never_built'
                return job_data

            # Get last build info
            last_build_number = last_build.get('number', 0)
            first_build = job_info.get('firstBuild', {})
            first_build_number = first_build.get('number', 0)

            total_builds = last_build_number - first_build_number + 1

            # Get timestamp
            last_build_info = self.server.get_build_info(
                job_name, last_build_number
            )
            timestamp_ms = last_build_info.get('timestamp', 0)
            last_build_time = datetime.fromtimestamp(timestamp_ms / 1000.0)
            days_since = (current_time - last_build_time).days

            job_data['last_build_number'] = last_build_number
            job_data['total_builds'] = total_builds
            job_data['days_since_last_build'] = days_since
            job_data['last_build_time'] = last_build_time.strftime(
                '%Y-%m-%d %H:%M:%S'
            )

            # Calculate build health metrics (limit to last 5 builds for speed)
            builds_to_check = min(5, last_build_number)
            success_count = 0
            build_results = []
            total_duration = 0
            duration_count = 0

            for i in range(builds_to_check):
                try:
                    build_num = last_build_number - i
                    build_info = self.server.get_build_info(job_name, build_num)
                    result = build_info.get('result', 'UNKNOWN')
                    build_results.append(result)

                    if result == 'SUCCESS':
                        success_count += 1

                    # Track duration
                    duration = build_info.get('duration', 0)
                    if duration > 0:
                        total_duration += duration
                        duration_count += 1
                except Exception:
                    continue

            # Calculate metrics
            if builds_to_check > 0:
                success_rate = (success_count / builds_to_check) * 100
                job_data['success_rate'] = round(success_rate, 1)
                job_data['build_health'] = build_results[:5]

                # Determine health status
                if success_rate >= 90:
                    job_data['health_status'] = '🟢 Healthy'
                elif success_rate >= 70:
                    job_data['health_status'] = '🟡 Unstable'
                elif success_rate >= 50:
                    job_data['health_status'] = '🟠 Poor'
                else:
                    job_data['health_status'] = '🔴 Critical'

                # Check if flaky (alternating pass/fail)
                if len(build_results) >= 4:
                    changes = sum(
                        1 for i in range(len(build_results) - 1)
                        if build_results[i] != build_results[i + 1]
                    )
                    if changes >= len(build_results) / 2:
                        job_data['health_status'] += ' (FLAKY)'
            else:
                job_data['success_rate'] = None
                job_data['health_status'] = 'Unknown'

            # Calculate average duration
            if duration_count > 0:
                avg_duration_ms = total_duration / duration_count
                job_data['avg_duration'] = round(
                    avg_duration_ms / 1000 / 60, 1
                )
            else:
                job_data['avg_duration'] = None

            # Categorize by activity
            if days_since > days_threshold:
                job_data['status'] = 'Inactive'
                job_data['category'] = 'inactive'
            else:
                job_data['status'] = 'Active'
                # Further categorize active jobs
                if total_builds > 100 or days_since < 7:
                    job_data['category'] = 'highly_active'
                elif total_builds > 20 or days_since < 14:
                    job_data['category'] = 'moderately_active'
                else:
                    job_data['category'] = 'rarely_active'

            return job_data

        except Exception as e:
            print(f"Error processing job {job_name}: {e}")
            return None

    def get_jenkins_health(self, days_threshold=30):
        """
        Comprehensive Jenkins health report including:
        - Active vs inactive jobs summary
        - Jobs recommended for deprecation
        - Failure rate analysis
        - Stability metrics with charts data

        Returns:
            dict: Complete health report with analytics and chart data
        """
        try:
            # Get job analytics first
            analytics = self.get_job_usage_analytics(days_threshold)
            if not isinstance(analytics, dict):
                return analytics  # Return error if analytics failed

            # Prepare health report
            health_report = {
                'summary': {
                    'total_jobs': analytics['total_jobs'],
                    'active_jobs': len(analytics['active_jobs']),
                    'inactive_jobs': len(analytics['inactive_jobs']),
                    'highly_active_jobs': len(analytics['highly_active_jobs']),
                    'never_built_jobs': len(analytics['never_built_jobs']),
                },
                'health_metrics': {},
                'chart_data': {},
                'recommendations': []
            }

            # Health metrics
            if analytics.get('health_summary'):
                health_summary = analytics['health_summary']
                health_report['health_metrics'] = {
                    'critical_jobs': len(health_summary.get('critical_jobs', [])),
                    'poor_jobs': len(health_summary.get('poor_jobs', [])),
                    'flaky_jobs': len(health_summary.get('flaky_jobs', [])),
                    'avg_success_rate': health_summary.get('avg_success_rate', 0),
                    'critical_job_list': health_summary.get('critical_jobs', [])[:10],
                    'flaky_job_list': health_summary.get('flaky_jobs', [])[:10],
                }

            # Top active jobs
            health_report['top_active_jobs'] = analytics['highly_active_jobs'][:10]

            # Jobs to deprecate (inactive + never built)
            deprecated_candidates = (
                analytics['inactive_jobs'] +
                analytics['never_built_jobs']
            )
            health_report['deprecated_candidates'] = deprecated_candidates[:20]

            # Prepare chart data for failures and stability
            all_jobs_with_health = [
                j for j in analytics['active_jobs'] + analytics['inactive_jobs']
                if j.get('success_rate') is not None
            ]

            # Chart 1: Job Failure Rates (top 15 failing jobs)
            failing_jobs = sorted(
                [j for j in all_jobs_with_health if j.get('success_rate', 100) < 90],
                key=lambda x: x.get('success_rate', 100)
            )[:15]

            health_report['chart_data']['failure_rates'] = {
                'job_names': [j['name'] for j in failing_jobs],
                'success_rates': [j['success_rate'] for j in failing_jobs],
                'failure_rates': [100 - j['success_rate'] for j in failing_jobs]
            }

            # Chart 2: Job Stability (healthy vs unhealthy)
            stability_counts = {
                'Healthy (>90%)': len([j for j in all_jobs_with_health if j.get('success_rate', 0) >= 90]),
                'Unstable (70-90%)': len([j for j in all_jobs_with_health if 70 <= j.get('success_rate', 0) < 90]),
                'Poor (50-70%)': len([j for j in all_jobs_with_health if 50 <= j.get('success_rate', 0) < 70]),
                'Critical (<50%)': len([j for j in all_jobs_with_health if j.get('success_rate', 0) < 50]),
            }
            health_report['chart_data']['stability_distribution'] = stability_counts

            # Chart 3: Build frequency over time (top 10 active jobs)
            top_10_active = analytics['highly_active_jobs'][:10]
            health_report['chart_data']['build_frequency'] = {
                'job_names': [j['name'] for j in top_10_active],
                'total_builds': [j.get('total_builds', 0) for j in top_10_active],
                'days_since_last': [j.get('days_since_last_build', 0) for j in top_10_active]
            }

            # Recommendations
            if health_report['summary']['inactive_jobs'] > 0:
                health_report['recommendations'].append(
                    f"Consider archiving {health_report['summary']['inactive_jobs']} inactive jobs (>30 days)"
                )

            if health_report['health_metrics'].get('critical_jobs', 0) > 0:
                health_report['recommendations'].append(
                    f"⚠️ {health_report['health_metrics']['critical_jobs']} jobs have critical health (<50% success rate)"
                )

            if health_report['health_metrics'].get('flaky_jobs', 0) > 0:
                health_report['recommendations'].append(
                    f"⚡ {health_report['health_metrics']['flaky_jobs']} flaky jobs detected - investigate for intermittent failures"
                )

            return health_report

        except Exception as e:
            return f"Error generating Jenkins health report: {e}"

    def get_job_usage_analytics(self, days_threshold=30, use_cache=True):
        """
        Analyzes job usage patterns to identify frequently used jobs
        and potentially deprecated jobs.

        Args:
            days_threshold (int): Number of days to consider
                a job as inactive
            use_cache (bool): Whether to use cached results if available

        Returns:
            dict: Analytics data including active jobs, inactive jobs,
                and usage statistics
        """
        # Check cache first
        if use_cache and self._analytics_cache and self._cache_timestamp:
            cache_age = time.time() - self._cache_timestamp
            if cache_age < self._cache_ttl:
                print(
                    f"DEBUG: Using cached analytics "
                    f"(age: {cache_age:.1f}s)"
                )
                return self._analytics_cache

        try:
            print("DEBUG: Fetching fresh analytics data from Jenkins...")
            jobs = self.server.get_jobs()
            current_time = datetime.now()
            analytics = {
                'total_jobs': 0,
                'active_jobs': [],
                'inactive_jobs': [],
                'highly_active_jobs': [],
                'moderately_active_jobs': [],
                'rarely_active_jobs': [],
                'never_built_jobs': []
            }

            # Use parallel processing for better performance
            job_names = [job['name'] for job in jobs]
            print(f"DEBUG: Processing {len(job_names)} jobs in parallel...")

            with ThreadPoolExecutor(max_workers=10) as executor:
                # Submit all jobs for processing
                future_to_job = {
                    executor.submit(
                        self._process_single_job,
                        job_name,
                        current_time,
                        days_threshold
                    ): job_name
                    for job_name in job_names
                }

                # Collect results as they complete
                completed = 0
                for future in as_completed(future_to_job):
                    completed += 1
                    if completed % 10 == 0:
                        print(
                            f"DEBUG: Processed {completed}/{len(job_names)} jobs"
                        )

                    job_data = future.result()
                    if job_data is None:
                        continue  # Skip folders

                    analytics['total_jobs'] += 1

                    # Categorize the job
                    category = job_data.get('category', 'unknown')
                    if category == 'never_built':
                        analytics['never_built_jobs'].append(job_data)
                        analytics['inactive_jobs'].append(job_data)
                    elif category == 'inactive':
                        analytics['inactive_jobs'].append(job_data)
                    elif category == 'highly_active':
                        analytics['active_jobs'].append(job_data)
                        analytics['highly_active_jobs'].append(job_data)
                    elif category == 'moderately_active':
                        analytics['active_jobs'].append(job_data)
                        analytics['moderately_active_jobs'].append(job_data)
                    elif category == 'rarely_active':
                        analytics['active_jobs'].append(job_data)
                        analytics['rarely_active_jobs'].append(job_data)

            print(f"DEBUG: Completed processing all {analytics['total_jobs']} jobs")

            # Sort jobs by days since last build
            analytics['inactive_jobs'].sort(
                key=lambda x: x.get('days_since_last_build')
                if x.get('days_since_last_build') is not None else 999999,
                reverse=True
            )
            analytics['active_jobs'].sort(
                key=lambda x: x.get('days_since_last_build', 0))

            # Add health summary statistics
            all_jobs_with_builds = [
                j for j in analytics['active_jobs'] +
                analytics['inactive_jobs']
                if j.get('success_rate') is not None
            ]

            if all_jobs_with_builds:
                # Find critical jobs
                critical_jobs = [
                    j for j in all_jobs_with_builds
                    if '🔴' in j.get('health_status', '')
                ]
                poor_jobs = [
                    j for j in all_jobs_with_builds
                    if '🟠' in j.get('health_status', '')
                ]
                flaky_jobs = [
                    j for j in all_jobs_with_builds
                    if 'FLAKY' in j.get('health_status', '')
                ]

                analytics['health_summary'] = {
                    'critical_jobs': critical_jobs,
                    'poor_jobs': poor_jobs,
                    'flaky_jobs': flaky_jobs,
                    'avg_success_rate': round(
                        sum(j['success_rate']
                            for j in all_jobs_with_builds) /
                        len(all_jobs_with_builds), 1
                    )
                }

            # Cache the results
            self._analytics_cache = analytics
            self._cache_timestamp = time.time()
            print("DEBUG: Analytics cached for future use")

            return analytics

        except jenkins.JenkinsException as e:
            return f"Error fetching job usage analytics: {e}"

    def get_jobs_for_ai_categorization(self):
        """
        Retrieves job information formatted for AI categorization.
        Returns job names, descriptions, and recent build info.
        Optimized with parallel processing.
        """
        try:
            jobs = self.server.get_jobs()
            job_names = [job['name'] for job in jobs]

            if not job_names:
                return []

            print(f"DEBUG: Fetching {len(job_names)} jobs for AI categorization in parallel...")

            def fetch_job_for_categorization(job_name):
                """Helper to fetch single job info for categorization"""
                try:
                    job_info = self.server.get_job_info(job_name)

                    # Skip folders - only process actual jobs
                    job_class = job_info.get('_class', '')
                    if 'folder' in job_class.lower():
                        return None

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
                        job_data['last_success_number'] = last_success.get('number')
                    else:
                        job_data['has_successful_builds'] = False

                    return job_data

                except Exception as e:
                    print(f"Error fetching info for job {job_name}: {e}")
                    return None

            # Fetch all jobs in parallel
            jobs_data = []
            with ThreadPoolExecutor(max_workers=15) as executor:
                future_to_job = {
                    executor.submit(fetch_job_for_categorization, job_name): job_name
                    for job_name in job_names
                }

                for future in as_completed(future_to_job):
                    result = future.result()
                    if result is not None:
                        jobs_data.append(result)

            # Sort by name for consistent output
            jobs_data.sort(key=lambda x: x['name'])

            print(f"DEBUG: Fetched {len(jobs_data)} jobs for categorization")
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
