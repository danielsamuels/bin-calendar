import os

from client import generate_calendar

uprn = os.getenv("UPRN")
auth_token = os.getenv("AUTH_TOKEN")
assert uprn, "UPRN environment variable not set"
assert auth_token, "AUTH_TOKEN environment variable not set"


def lambda_handler(event, context):
    calendar = generate_calendar(uprn, auth_token)
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/calendar; charset=utf-8',
        },
        'body': calendar
    }


if __name__ == '__main__':
    print(lambda_handler(None, None))
