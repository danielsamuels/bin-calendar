import os

from client import generate_calendar

url = os.getenv("SOURCE_URL")
assert url, "SOURCE_URL environment variable not set"


def lambda_handler(event, context):
    calendar = generate_calendar(url)
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'text/calendar; charset=utf-8',
        },
        'body': calendar
    }


if __name__ == '__main__':
    print(lambda_handler(None, None))
