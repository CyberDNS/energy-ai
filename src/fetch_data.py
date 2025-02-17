import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Define the URL to fetch data from
URL = os.getenv("FETCH_DATA_URL")

# Define the path to the "fetched_data" subfolder
FETCHED_DATA_PATH = os.path.join(os.getenv("DATA_PATH"), "fetched_data")

# Create the "fetched_data" subfolder if it doesn't exist
os.makedirs(FETCHED_DATA_PATH, exist_ok=True)


def fetch_and_store_data(url):
    try:
        # Fetch the data from the URL
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        # Iterate over each entry in the fetched data
        for i, entry in enumerate(data):
            # Create a filename based on the attribute which contains the timestamp
            filename = f"{entry}.json"
            filepath = os.path.join(FETCHED_DATA_PATH, filename)

            # Store the content behind the entry in a JSON file
            with open(filepath, "w") as f:
                json.dump({"data": data[entry]}, f, indent=4)

            print(f"Entry {i} successfully fetched and stored in {filepath}")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except Exception as e:
        print(f"Error storing data: {e}")


if __name__ == "__main__":
    fetch_and_store_data(URL)
