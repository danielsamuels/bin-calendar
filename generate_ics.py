import os

from client import generate_calendar

url = os.getenv("SOURCE_URL")
assert url, "SOURCE_URL environment variable not set"

if __name__ == '__main__':
    calendar = generate_calendar(url)
    filename = os.getenv('OUTPUT_FILENAME', 'bin-calendar.ics')
    with open(filename, 'w+') as f:
        f.writelines(calendar.serialize_iter())
