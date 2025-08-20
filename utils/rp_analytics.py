"""Enhanced analytics utilities for ReportPortal data analysis."""
import pandas as pd
import numpy as np
from collections import Counter, defaultdict
import re
from datetime import datetime, timedelta
import statistics

class ReportPortalAnalytics:
    """Advanced analytics for ReportPortal data."""
    
    def __init__(self, launches_data, test_items_data=None):
        """
        Initialize analytics with launch and test data.
        
        Args:
            launches_data (list): List of launch dictionaries
            test_items_data (dict): Dictionary mapping launch_id to test items list
        """
        self.launches_data = launches_data
        self.test_items_data = test_items_data or {}
        self.df_launches = pd.DataFrame(launches_data) if launches_data else pd.DataFrame()
        
    def calculate_test_execution_metrics(self):
        """Calculate comprehensive test execution metrics."""
        if self.df_launches.empty:
            return {}
            
        # Convert timestamps for proper analysis
        if 'startTime' in self.df_launches.columns:
            self.df_launches['start_time'] = pd.to_datetime(self.df_launches['startTime'], unit='ms')
            
        metrics = {
            'total_launches': len(self.df_launches),
            'total_tests_executed': self.df_launches['total'].sum(),
            'avg_tests_per_launch': self.df_launches['total'].mean(),
            'median_tests_per_launch': self.df_launches['total'].median(),
            'total_passed': self.df_launches['passed'].sum(),
            'total_failed': self.df_launches['failed'].sum(),
            'total_skipped': self.df_launches['skipped'].sum(),
            'overall_pass_rate': (self.df_launches['passed'].sum() / 
                                (self.df_launches['passed'].sum() + self.df_launches['failed'].sum()) * 100) 
                               if (self.df_launches['passed'].sum() + self.df_launches['failed'].sum()) > 0 else 0,
            'avg_pass_rate': self._calculate_avg_pass_rate(),
            'pass_rate_std': self._calculate_pass_rate_std(),
            'test_execution_trend': self._calculate_test_trend()
        }
        
        return metrics
    
    def detect_flaky_tests(self, min_occurrences=3):
        """
        Detect flaky tests based on inconsistent results across launches.
        
        Args:
            min_occurrences (int): Minimum times a test must appear to be considered for flaky analysis
            
        Returns:
            list: List of potentially flaky tests with their inconsistency scores
        """
        if not self.test_items_data:
            return []
            
        test_results = defaultdict(list)
        
        # Collect all test results across launches
        for launch_id, items in self.test_items_data.items():
            if isinstance(items, list):
                for item in items:
                    test_name = item.get('name', '')
                    status = item.get('status', '')
                    if test_name and status:
                        test_results[test_name].append(status)
        
        flaky_tests = []
        for test_name, statuses in test_results.items():
            if len(statuses) >= min_occurrences:
                # Calculate inconsistency score
                status_counts = Counter(statuses)
                total_runs = len(statuses)
                
                # A test is flaky if it has multiple different outcomes
                if len(status_counts) > 1:
                    # Calculate flakiness score (0-100, higher = more flaky)
                    passed_count = status_counts.get('PASSED', 0)
                    failed_count = status_counts.get('FAILED', 0)
                    
                    if passed_count > 0 and failed_count > 0:
                        # Flaky score based on how often it switches between pass/fail
                        switches = sum(1 for i in range(1, len(statuses)) 
                                     if statuses[i] != statuses[i-1])
                        flaky_score = (switches / (len(statuses) - 1)) * 100 if len(statuses) > 1 else 0
                        
                        flaky_tests.append({
                            'test_name': test_name,
                            'total_runs': total_runs,
                            'passed': passed_count,
                            'failed': failed_count,
                            'skipped': status_counts.get('SKIPPED', 0),
                            'flaky_score': flaky_score,
                            'status_distribution': dict(status_counts)
                        })
        
        # Sort by flaky score descending
        return sorted(flaky_tests, key=lambda x: x['flaky_score'], reverse=True)
    
    def analyze_failure_patterns(self):
        """Analyze failure patterns and group similar failures."""
        if not self.test_items_data:
            return {}
            
        failure_patterns = defaultdict(list)
        error_messages = []
        
        for launch_id, items in self.test_items_data.items():
            if isinstance(items, list):
                for item in items:
                    if item.get('status') == 'FAILED':
                        test_name = item.get('name', '')
                        description = item.get('description', '')
                        
                        # Extract potential error patterns
                        error_pattern = self._extract_error_pattern(description)
                        if error_pattern:
                            failure_patterns[error_pattern].append({
                                'test_name': test_name,
                                'launch_id': launch_id,
                                'description': description
                            })
                            error_messages.append(description)
        
        # Categorize failures
        categories = self._categorize_failures(error_messages)
        
        return {
            'failure_patterns': dict(failure_patterns),
            'failure_categories': categories,
            'top_failure_patterns': self._get_top_patterns(failure_patterns),
            'total_unique_failures': len(failure_patterns)
        }
    
    def calculate_test_duration_analytics(self):
        """Calculate test duration analytics if duration data is available."""
        if not self.test_items_data:
            return {}
            
        durations = []
        test_durations = {}
        
        for launch_id, items in self.test_items_data.items():
            if isinstance(items, list):
                for item in items:
                    duration = item.get('duration', 0)
                    if duration > 0:
                        durations.append(duration / 1000)  # Convert to seconds
                        test_name = item.get('name', '')
                        if test_name not in test_durations:
                            test_durations[test_name] = []
                        test_durations[test_name].append(duration / 1000)
        
        if not durations:
            return {}
            
        # Calculate duration statistics
        analytics = {
            'avg_test_duration': statistics.mean(durations),
            'median_test_duration': statistics.median(durations),
            'min_test_duration': min(durations),
            'max_test_duration': max(durations),
            'duration_std': statistics.stdev(durations) if len(durations) > 1 else 0,
            'total_tests_with_duration': len(durations)
        }
        
        # Find slowest tests
        avg_durations = {name: statistics.mean(times) for name, times in test_durations.items() if times}
        slowest_tests = sorted(avg_durations.items(), key=lambda x: x[1], reverse=True)[:10]
        analytics['slowest_tests'] = [{'test_name': name, 'avg_duration': duration} 
                                     for name, duration in slowest_tests]
        
        return analytics
    
    def generate_historical_comparison(self, days_back=30):
        """Generate historical comparison metrics."""
        if self.df_launches.empty or 'start_time' not in self.df_launches.columns:
            return {}
            
        now = datetime.now()
        cutoff_date = now - timedelta(days=days_back)
        
        # Split data into recent and historical
        recent_data = self.df_launches[self.df_launches['start_time'] >= cutoff_date]
        historical_data = self.df_launches[self.df_launches['start_time'] < cutoff_date]
        
        if recent_data.empty or historical_data.empty:
            return {}
            
        recent_metrics = self._calculate_metrics_for_df(recent_data)
        historical_metrics = self._calculate_metrics_for_df(historical_data)
        
        comparison = {}
        for metric in ['avg_pass_rate', 'avg_tests_per_launch', 'total_tests']:
            recent_val = recent_metrics.get(metric, 0)
            historical_val = historical_metrics.get(metric, 0)
            
            if historical_val > 0:
                change_pct = ((recent_val - historical_val) / historical_val) * 100
                comparison[f'{metric}_change'] = change_pct
                comparison[f'{metric}_recent'] = recent_val
                comparison[f'{metric}_historical'] = historical_val
        
        return comparison
    
    def generate_executive_summary(self):
        """Generate executive summary with key metrics."""
        exec_metrics = self.calculate_test_execution_metrics()
        flaky_tests = self.detect_flaky_tests()
        failure_analysis = self.analyze_failure_patterns()
        duration_analytics = self.calculate_test_duration_analytics()
        historical_comparison = self.generate_historical_comparison()
        
        # Calculate quality indicators
        quality_score = self._calculate_quality_score(exec_metrics, flaky_tests, failure_analysis)
        
        summary = {
            'overview': {
                'total_launches': exec_metrics.get('total_launches', 0),
                'total_tests': exec_metrics.get('total_tests_executed', 0),
                'overall_pass_rate': round(exec_metrics.get('overall_pass_rate', 0), 2),
                'quality_score': quality_score
            },
            'test_stability': {
                'flaky_tests_detected': len(flaky_tests),
                'top_flaky_tests': flaky_tests[:5] if flaky_tests else [],
                'pass_rate_stability': exec_metrics.get('pass_rate_std', 0)
            },
            'failure_insights': {
                'unique_failure_patterns': failure_analysis.get('total_unique_failures', 0),
                'top_failure_categories': failure_analysis.get('failure_categories', {}),
                'critical_issues': self._identify_critical_issues(failure_analysis)
            },
            'performance': duration_analytics,
            'trends': historical_comparison
        }
        
        return summary
    
    def _calculate_avg_pass_rate(self):
        """Calculate average pass rate across launches."""
        if self.df_launches.empty:
            return 0
            
        pass_rates = []
        for _, launch in self.df_launches.iterrows():
            total_decisive = launch['passed'] + launch['failed']
            if total_decisive > 0:
                pass_rate = (launch['passed'] / total_decisive) * 100
                pass_rates.append(pass_rate)
        
        return statistics.mean(pass_rates) if pass_rates else 0
    
    def _calculate_pass_rate_std(self):
        """Calculate standard deviation of pass rates."""
        if self.df_launches.empty:
            return 0
            
        pass_rates = []
        for _, launch in self.df_launches.iterrows():
            total_decisive = launch['passed'] + launch['failed']
            if total_decisive > 0:
                pass_rate = (launch['passed'] / total_decisive) * 100
                pass_rates.append(pass_rate)
        
        return statistics.stdev(pass_rates) if len(pass_rates) > 1 else 0
    
    def _calculate_test_trend(self):
        """Calculate test execution trend."""
        if self.df_launches.empty or 'start_time' not in self.df_launches.columns:
            return 0
            
        # Sort by start time and calculate trend
        sorted_df = self.df_launches.sort_values('start_time')
        if len(sorted_df) < 2:
            return 0
            
        # Simple linear trend calculation
        x = list(range(len(sorted_df)))
        y = sorted_df['total'].tolist()
        
        if len(x) < 2:
            return 0
            
        # Calculate slope
        n = len(x)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] * x[i] for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x) if (n * sum_x2 - sum_x * sum_x) != 0 else 0
        return slope
    
    def _extract_error_pattern(self, description):
        """Extract error pattern from test description/logs."""
        if not description:
            return None
            
        # Common error patterns
        patterns = [
            r'TimeoutException',
            r'ConnectionError',
            r'AssertionError',
            r'NullPointerException',
            r'FileNotFoundException',
            r'HTTP \d{3}',
            r'Database.*Error',
            r'Authentication.*Failed',
            r'Permission.*Denied'
        ]
        
        for pattern in patterns:
            if re.search(pattern, description, re.IGNORECASE):
                return pattern
        
        # Extract first error-like word
        error_match = re.search(r'\b\w*(?:Error|Exception|Failed|Timeout)\b', description, re.IGNORECASE)
        if error_match:
            return error_match.group()
        
        return 'Unknown Error'
    
    def _categorize_failures(self, error_messages):
        """Categorize failures into types."""
        categories = {
            'Infrastructure': 0,
            'Timeout': 0,
            'Assertion': 0,
            'Configuration': 0,
            'Data': 0,
            'Unknown': 0
        }
        
        for msg in error_messages:
            if any(keyword in msg.lower() for keyword in ['connection', 'network', 'server', 'http']):
                categories['Infrastructure'] += 1
            elif any(keyword in msg.lower() for keyword in ['timeout', 'time out', 'timed out']):
                categories['Timeout'] += 1
            elif any(keyword in msg.lower() for keyword in ['assert', 'expected', 'actual']):
                categories['Assertion'] += 1
            elif any(keyword in msg.lower() for keyword in ['config', 'property', 'setting']):
                categories['Configuration'] += 1
            elif any(keyword in msg.lower() for keyword in ['data', 'database', 'sql', 'record']):
                categories['Data'] += 1
            else:
                categories['Unknown'] += 1
        
        return categories
    
    def _get_top_patterns(self, failure_patterns):
        """Get top failure patterns by frequency."""
        pattern_counts = {pattern: len(failures) for pattern, failures in failure_patterns.items()}
        return sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    def _calculate_metrics_for_df(self, df):
        """Calculate metrics for a specific dataframe."""
        if df.empty:
            return {}
            
        return {
            'avg_pass_rate': df.apply(lambda row: (row['passed'] / (row['passed'] + row['failed']) * 100) 
                                    if (row['passed'] + row['failed']) > 0 else 0, axis=1).mean(),
            'avg_tests_per_launch': df['total'].mean(),
            'total_tests': df['total'].sum()
        }
    
    def _calculate_quality_score(self, exec_metrics, flaky_tests, failure_analysis):
        """Calculate overall quality score (0-100)."""
        # Base score from pass rate
        pass_rate = exec_metrics.get('overall_pass_rate', 0)
        score = pass_rate
        
        # Deduct for flaky tests
        if len(flaky_tests) > 0:
            flaky_penalty = min(len(flaky_tests) * 2, 20)  # Max 20 point penalty
            score -= flaky_penalty
        
        # Deduct for high failure pattern diversity (indicates systemic issues)
        unique_failures = failure_analysis.get('total_unique_failures', 0)
        if unique_failures > 5:
            pattern_penalty = min((unique_failures - 5) * 1.5, 15)  # Max 15 point penalty
            score -= pattern_penalty
        
        # Deduct for pass rate instability
        pass_rate_std = exec_metrics.get('pass_rate_std', 0)
        if pass_rate_std > 10:
            stability_penalty = min((pass_rate_std - 10) * 0.5, 10)  # Max 10 point penalty
            score -= stability_penalty
        
        return max(0, min(100, round(score, 1)))
    
    def _identify_critical_issues(self, failure_analysis):
        """Identify critical issues from failure analysis."""
        critical_issues = []
        
        failure_categories = failure_analysis.get('failure_categories', {})
        total_failures = sum(failure_categories.values())
        
        if total_failures == 0:
            return critical_issues
        
        # Infrastructure issues > 30% of failures
        infra_pct = (failure_categories.get('Infrastructure', 0) / total_failures) * 100
        if infra_pct > 30:
            critical_issues.append(f"High infrastructure failure rate ({infra_pct:.1f}%)")
        
        # Timeout issues > 20% of failures
        timeout_pct = (failure_categories.get('Timeout', 0) / total_failures) * 100
        if timeout_pct > 20:
            critical_issues.append(f"Frequent timeout issues ({timeout_pct:.1f}%)")
        
        # Too many unique failure patterns
        unique_failures = failure_analysis.get('total_unique_failures', 0)
        if unique_failures > 15:
            critical_issues.append(f"High failure pattern diversity ({unique_failures} unique patterns)")
        
        return critical_issues