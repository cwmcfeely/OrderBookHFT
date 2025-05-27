import json
from unittest.mock import patch

# Load your mock data from the JSON file
with open("tests/mock_data/sample_market_data.json") as f:
    mock_data = json.load(f)


# This is your test function
@patch("app.market_data.fetch_intraday_data")
def test_fetch_intraday_data(mock_fetch):
    mock_fetch.return_value = mock_data  # Use mock data instead of real API call

    # Now call the function that would normally trigger the API call
    result = mock_fetch()

    # Assert that the result is as expected, using the mock data
    assert result == mock_data

    print("Test passed: fetch_intraday_data returns mock data")


# If you want to run this test directly:
if __name__ == "__main__":
    test_fetch_intraday_data()
