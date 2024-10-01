import requests

def test_stream():
    url = 'http://localhost:5000/stream/123'  # Replace '123' with an actual userId from your database for testing
    response = requests.get(url)
    print("Status Code:", response.status_code)
    print("Headers:", response.headers)
    print("Content:", response.text[:5000])  # Print only first 500 characters to avoid too long output

if __name__ == '__main__':
    test_stream()
