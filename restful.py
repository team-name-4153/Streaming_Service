
from flask import jsonify

def error_response(message, status_code):
    """
    Helper function to create a JSON error response.
    """
    response = jsonify({'error': message})
    response.status_code = status_code
    return response