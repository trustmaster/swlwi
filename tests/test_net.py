import unittest

from swlwi.net import extract_domain_from_url


class TestExtractDomainFromUrl(unittest.TestCase):
    def test_valid_url(self):
        url = "https://www.example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_with_subdomain(self):
        url = "https://subdomain.example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_without_www(self):
        url = "https://example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_with_multiple_subdomains(self):
        url = "https://sub.subdomain.example.com/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_with_different_tld(self):
        url = "https://example.co.uk/path/to/page"
        expected_domain = "co.uk"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_without_protocol(self):
        url = "www.example.com/path/to/page"
        expected_domain = "unknown"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_invalid_url(self):
        url = "invalid_url"
        expected_domain = "unknown"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_empty_url(self):
        url = ""
        expected_domain = "unknown"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_with_ip_address(self):
        url = "https://192.168.0.1/path/to/page"
        expected_domain = "unknown"
        self.assertEqual(extract_domain_from_url(url), expected_domain)

    def test_url_with_port(self):
        url = "https://example.com:8080/path/to/page"
        expected_domain = "example.com"
        self.assertEqual(extract_domain_from_url(url), expected_domain)


# class TestRateLimiter(unittest.TestCase):

#     def setUp(self):
#         # Reset the singleton instance before each test
#         RateLimiter._instance = None
#         self.rate_limiter = RateLimiter()
#         self.rate_limiter._timeout = 0.1  # Set a smaller timeout for testing

#     def tearDown(self):
#         # Reset the singleton instance after each test
#         RateLimiter._instance = None

#     def test_singleton(self):
#         # Ensure that RateLimiter is a singleton
#         rate_limiter1 = RateLimiter()
#         rate_limiter2 = RateLimiter()
#         self.assertIs(rate_limiter1, rate_limiter2)

#     @patch('swlwi.scrape.datetime')
#     @patch('swlwi.scrape.time.sleep', return_value=None)
#     def test_rate_limiting(self, mock_sleep, mock_datetime):
#         # Mock the current time
#         base_time = datetime(2023, 1, 1, 12, 0, 0)
#         mock_datetime.now.return_value = base_time
#         domain = "example.com"

#         # First request should not sleep
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.05 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.05)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.15 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.15)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.2 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.2)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.25 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.25)
#         start_time = time.time()
#         self.rate_limiter.wait(domain)
#         end_time = time.time()
#         self.assertGreater(end_time - start_time, 0.05)
#         mock_sleep.assert_called_once()

#     @patch('swlwi.scrape.datetime')
#     @patch('swlwi.scrape.time.sleep', return_value=None)
#     def test_rate_limiting_multiple_domains(self, mock_sleep, mock_datetime):
#         # Mock the current time
#         base_time = datetime(2023, 1, 1, 12, 0, 0)
#         mock_datetime.now.return_value = base_time
#         domain1 = "example.com"
#         domain2 = "test.com"

#         # First request for domain1 should not sleep
#         start_time = time.time()
#         self.rate_limiter.wait(domain1)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # First request for domain2 should not sleep
#         start_time = time.time()
#         self.rate_limiter.wait(domain2)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.05 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.05)
#         start_time = time.time()
#         self.rate_limiter.wait(domain1)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.15 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.15)
#         start_time = time.time()
#         self.rate_limiter.wait(domain2)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.2 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.2)
#         start_time = time.time()
#         self.rate_limiter.wait(domain1)
#         end_time = time.time()
#         self.assertLess(end_time - start_time, 0.1)
#         mock_sleep.assert_not_called()

#         # Mock the time to be 0.25 seconds later
#         mock_datetime.now.return_value = base_time + timedelta(seconds=0.25)
#         start_time = time.time()
#         self.rate_limiter.wait(domain2)
#         end_time = time.time()
#         self.assertGreater(end_time - start_time, 0.05)
#         mock_sleep.assert_called_once()
